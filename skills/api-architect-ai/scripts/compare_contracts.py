#!/usr/bin/env python3
"""Detect and classify changes between two OpenAPI 3.x contracts.

Usage:
    compare_contracts.py OLD NEW [--format text|json] [--fail-on breaking|potentially-breaking|none]

Inputs:
    OLD, NEW    Paths to OpenAPI documents (.yaml/.yml/.json), previous and proposed versions.
Options:
    --format    Output format (default: text).
    --fail-on   Exit 1 when changes at or above this level exist (default: breaking).

Output:
    JSON: {"old", "new", "summary": {level: count}, "changes": [{"id", "level", "rule",
    "operation", "location", "message"}]}. Levels: breaking, potentially-breaking, non-breaking, info.

Dependencies:
    Python 3.9+, PyYAML for YAML input.

Exit codes:
    0 no changes at/above --fail-on · 1 changes at/above --fail-on · 2 invalid input
    3 missing dependency or unsupported runtime

Limitations: only local $refs are resolved; semantic changes (same type, different meaning),
behavioral changes and composition keywords (oneOf/anyOf/allOf) are reported at a coarse level.
Always review results manually.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_INPUT,
    EXIT_OK,
    ScriptError,
    check_runtime,
    deref,
    emit,
    fail,
    load_document,
)

METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace", "query"]
LEVELS = ["breaking", "potentially-breaking", "non-breaking", "info"]
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}
PATH_PARAM_RE = re.compile(r"\{[^{}/]+\}")
MAX_DEPTH = 12

# Constraint keywords: (keyword, direction in which the value becomes stricter)
TIGHTER_IF_LOWER = ("maxLength", "maximum", "exclusiveMaximum", "maxItems", "maxProperties")
TIGHTER_IF_HIGHER = ("minLength", "minimum", "exclusiveMinimum", "minItems", "minProperties")


def type_set(schema: Dict[str, Any]) -> Set[str]:
    """Normalized set of JSON types, including 'null' (3.1 arrays and 3.0 nullable)."""
    raw = schema.get("type")
    if raw is None:
        types: Set[str] = set()
    elif isinstance(raw, list):
        types = {str(t) for t in raw}
    else:
        types = {str(raw)}
    if schema.get("nullable") is True:
        types.add("null")
    if "integer" in types and "number" in types:
        types.discard("integer")
    return types


class Comparator:
    def __init__(self, old: Dict[str, Any], new: Dict[str, Any]):
        self.old = old
        self.new = new
        self.changes: List[Dict[str, str]] = []

    def add(self, level: str, rule: str, operation: str, location: str, message: str) -> None:
        self.changes.append({"level": level, "rule": rule, "operation": operation,
                             "location": location, "message": message})

    # -- operations ----------------------------------------------------------------
    @staticmethod
    def index_operations(doc: Dict[str, Any]) -> Dict[tuple, Dict[str, Any]]:
        result = {}
        for path, item in (doc.get("paths") or {}).items():
            item = deref(doc, item)
            if not isinstance(item, dict):
                continue
            norm = PATH_PARAM_RE.sub("{}", path)
            for method in METHODS:
                op = item.get(method)
                if isinstance(op, dict):
                    result[(norm, method)] = {"path": path, "op": op, "item": item}
        return result

    def run(self) -> None:
        old_v = (self.old.get("info") or {}).get("version")
        new_v = (self.new.get("info") or {}).get("version")
        if old_v != new_v:
            self.add("info", "info-version", "-", "#/info/version", "API version changed: %s → %s" % (old_v, new_v))
        if self.old.get("openapi") != self.new.get("openapi"):
            self.add("info", "openapi-version", "-", "#/openapi",
                     "OpenAPI specification version changed: %s → %s" % (self.old.get("openapi"), self.new.get("openapi")))
        old_servers = {s.get("url") for s in self.old.get("servers") or [] if isinstance(s, dict)}
        new_servers = {s.get("url") for s in self.new.get("servers") or [] if isinstance(s, dict)}
        for url in sorted(old_servers - new_servers):
            self.add("potentially-breaking", "server-removed", "-", "#/servers", "Server URL removed: %s" % url)

        old_ops = self.index_operations(self.old)
        new_ops = self.index_operations(self.new)
        old_paths = {k[0] for k in old_ops}
        new_paths = {k[0] for k in new_ops}
        for norm in sorted(old_paths - new_paths):
            path = next(v["path"] for k, v in old_ops.items() if k[0] == norm)
            self.add("breaking", "path-removed", path, path, "Path removed: %s" % path)
        for key in sorted(old_ops):
            label = "%s %s" % (key[1].upper(), old_ops[key]["path"])
            if key not in new_ops:
                if key[0] in new_paths:
                    self.add("breaking", "operation-removed", label, label, "Operation removed: %s" % label)
                continue
            self.compare_operation(label, old_ops[key], new_ops[key])
        for key in sorted(set(new_ops) - set(old_ops)):
            label = "%s %s" % (key[1].upper(), new_ops[key]["path"])
            self.add("non-breaking", "operation-added", label, label, "Operation added: %s" % label)

    def compare_operation(self, label: str, old_entry, new_entry) -> None:
        old_op, new_op = old_entry["op"], new_entry["op"]
        if not old_op.get("deprecated") and new_op.get("deprecated"):
            self.add("info", "operation-deprecated", label, label, "Operation marked as deprecated.")
        if old_op.get("operationId") != new_op.get("operationId"):
            self.add("potentially-breaking", "operation-id-changed", label, label,
                     "operationId changed %r → %r (breaks generated SDK method names)." % (old_op.get("operationId"), new_op.get("operationId")))
        self.compare_parameters(label, old_entry, new_entry)
        self.compare_request_body(label, old_op.get("requestBody"), new_op.get("requestBody"))
        self.compare_responses(label, old_op.get("responses") or {}, new_op.get("responses") or {})
        self.compare_security(label, old_op, new_op)

    # -- parameters ----------------------------------------------------------------
    def params_of(self, doc, entry) -> Dict[tuple, Dict[str, Any]]:
        """Effective parameters (operation overrides path level). Path parameters are keyed by
        position in the template, so renaming {id} to {policyId} is not reported as a change."""
        template = PATH_PARAM_RE.findall(entry["path"])
        result = {}
        for source in (entry["item"].get("parameters") or [], entry["op"].get("parameters") or []):
            for raw in source:
                param = deref(doc, raw)
                if not (isinstance(param, dict) and param.get("name") and param.get("in")):
                    continue
                name = param["name"]
                if param["in"] == "header":
                    name = name.lower()
                elif param["in"] == "path" and "{%s}" % name in template:
                    name = "<path:%d>" % template.index("{%s}" % name)
                result[(name, param["in"])] = param
        return result

    def compare_parameters(self, label, old_entry, new_entry) -> None:
        old_params = self.params_of(self.old, old_entry)
        new_params = self.params_of(self.new, new_entry)
        for key, param in new_params.items():
            loc = "%s parameter %s (%s)" % (label, param["name"], key[1])
            if key not in old_params:
                if param.get("required"):
                    self.add("breaking", "required-parameter-added", label, loc,
                             "New required parameter '%s' in %s." % (param["name"], key[1]))
                else:
                    self.add("non-breaking", "optional-parameter-added", label, loc,
                             "New optional parameter '%s' in %s." % (param["name"], key[1]))
                continue
            old_param = old_params[key]
            if param.get("required") and not old_param.get("required"):
                self.add("breaking", "parameter-became-required", label, loc,
                         "Parameter '%s' became required." % param["name"])
            if param.get("deprecated") and not old_param.get("deprecated"):
                self.add("info", "parameter-deprecated", label, loc, "Parameter '%s' deprecated." % param["name"])
            old_schema = deref(self.old, old_param.get("schema") or {})
            new_schema = deref(self.new, param.get("schema") or {})
            self.compare_schema(label, loc, old_schema, new_schema, "request", 0, set())
        for key, param in old_params.items():
            if key not in new_params:
                loc = "%s parameter %s (%s)" % (label, param["name"], key[1])
                level = "breaking" if key[1] == "path" else "potentially-breaking"
                self.add(level, "parameter-removed", label, loc,
                         "Parameter '%s' in %s removed (clients still sending it may be rejected or silently ignored)." % (param["name"], key[1]))

    # -- request body --------------------------------------------------------------
    def compare_request_body(self, label, old_body, new_body) -> None:
        old_body = deref(self.old, old_body) if old_body else None
        new_body = deref(self.new, new_body) if new_body else None
        loc = "%s requestBody" % label
        if old_body is None and new_body is None:
            return
        if old_body is None:
            level = "breaking" if new_body.get("required") else "non-breaking"
            self.add(level, "request-body-added", label, loc,
                     "Request body added (%s)." % ("required" if new_body.get("required") else "optional"))
            return
        if new_body is None:
            self.add("potentially-breaking", "request-body-removed", label, loc, "Request body removed.")
            return
        if new_body.get("required") and not old_body.get("required"):
            self.add("breaking", "request-body-became-required", label, loc, "Request body became required.")
        old_content = old_body.get("content") or {}
        new_content = new_body.get("content") or {}
        for media in old_content:
            if media not in new_content:
                self.add("breaking", "request-media-type-removed", label, "%s %s" % (loc, media),
                         "Request media type '%s' no longer accepted." % media)
                continue
            old_schema = deref(self.old, (old_content[media] or {}).get("schema") or {})
            new_schema = deref(self.new, (new_content[media] or {}).get("schema") or {})
            self.compare_schema(label, "%s %s" % (loc, media), old_schema, new_schema, "request", 0, set())
        for media in new_content:
            if media not in old_content:
                self.add("non-breaking", "request-media-type-added", label, "%s %s" % (loc, media),
                         "Request media type '%s' added." % media)

    # -- responses -----------------------------------------------------------------
    def compare_responses(self, label, old_resps, new_resps) -> None:
        for code, old_resp in old_resps.items():
            code = str(code)
            loc = "%s response %s" % (label, code)
            new_match = new_resps.get(code, new_resps.get(int(code)) if code.isdigit() else None)
            if new_match is None:
                if code.startswith("2") or code.startswith("3"):
                    self.add("breaking", "success-response-removed", label, loc,
                             "Success response %s removed." % code)
                else:
                    self.add("info", "error-response-removed", label, loc, "Documented response %s removed." % code)
                continue
            old_r = deref(self.old, old_resp) or {}
            new_r = deref(self.new, new_match) or {}
            old_content = old_r.get("content") or {}
            new_content = new_r.get("content") or {}
            for media in old_content:
                if media not in new_content:
                    self.add("breaking", "response-media-type-removed", label, "%s %s" % (loc, media),
                             "Response media type '%s' removed." % media)
                    continue
                old_schema = deref(self.old, (old_content[media] or {}).get("schema") or {})
                new_schema = deref(self.new, (new_content[media] or {}).get("schema") or {})
                self.compare_schema(label, "%s %s" % (loc, media), old_schema, new_schema, "response", 0, set())
            for header in (old_r.get("headers") or {}):
                if header not in (new_r.get("headers") or {}):
                    self.add("potentially-breaking", "response-header-removed", label, loc,
                             "Response header '%s' removed." % header)
        old_codes = {str(c) for c in old_resps}
        for code in new_resps:
            code = str(code)
            if code not in old_codes:
                level = "potentially-breaking" if code.startswith("2") else "non-breaking"
                self.add(level, "response-added", label, "%s response %s" % (label, code),
                         "Response %s added%s." % (code, " (clients may not handle a new success code)" if level != "non-breaking" else ""))

    # -- schemas -------------------------------------------------------------------
    def compare_schema(self, label, loc, old, new, direction, depth, seen) -> None:
        """direction: 'request' (client sends) or 'response' (client receives)."""
        if depth > MAX_DEPTH or not isinstance(old, dict) or not isinstance(new, dict):
            return
        key = (id(old), id(new))
        if key in seen:
            return
        seen = seen | {key}

        old_types, new_types = type_set(old), type_set(new)
        if old_types and new_types and old_types != new_types:
            old_core, new_core = old_types - {"null"}, new_types - {"null"}
            if old_core != new_core:
                widened = old_core < new_core or ("number" in new_core and old_core == {"integer"})
                if direction == "request" and widened:
                    self.add("non-breaking", "request-type-widened", label, loc,
                             "Request type widened %s → %s." % (sorted(old_types), sorted(new_types)))
                else:
                    self.add("breaking", "type-changed", label, loc,
                             "Type changed %s → %s." % (sorted(old_types), sorted(new_types)))
            if "null" in new_types and "null" not in old_types and direction == "response":
                self.add("breaking", "response-became-nullable", label, loc,
                         "Response value may now be null (clients may not handle null).")
            if "null" in old_types and "null" not in new_types and direction == "request":
                self.add("breaking", "request-null-not-allowed", label, loc,
                         "Request value no longer accepts null.")
        elif not old_types and new_types and direction == "request":
            self.add("breaking", "request-type-restricted", label, loc,
                     "Request schema now restricts type to %s." % sorted(new_types))

        if old.get("format") != new.get("format") and (old.get("format") or new.get("format")):
            level = "breaking" if direction == "request" and new.get("format") else "potentially-breaking"
            self.add(level, "format-changed", label, loc,
                     "Format changed %r → %r." % (old.get("format"), new.get("format")))

        self.compare_enum(label, loc, old, new, direction)
        if direction == "request":
            self.compare_constraints(label, loc, old, new)
            if old.get("pattern") != new.get("pattern") and new.get("pattern"):
                self.add("breaking", "pattern-changed", label, loc,
                         "Request pattern added/changed to %r." % new.get("pattern"))
            if old.get("additionalProperties") is not False and new.get("additionalProperties") is False:
                self.add("potentially-breaking", "additional-properties-closed", label, loc,
                         "Request schema now rejects unknown properties.")

        old_props = old.get("properties") or {}
        new_props = new.get("properties") or {}
        old_req = set(old.get("required") or [])
        new_req = set(new.get("required") or [])
        for name in new_props:
            ploc = "%s.%s" % (loc, name)
            if name not in old_props:
                if direction == "request" and name in new_req:
                    self.add("breaking", "required-property-added", label, ploc,
                             "New required request property '%s'." % name)
                else:
                    self.add("non-breaking", "property-added", label, ploc, "Property '%s' added." % name)
        for name in old_props:
            ploc = "%s.%s" % (loc, name)
            if name not in new_props:
                if direction == "response":
                    self.add("breaking", "response-property-removed", label, ploc,
                             "Response property '%s' removed." % name)
                else:
                    self.add("potentially-breaking", "request-property-removed", label, ploc,
                             "Request property '%s' removed (may be rejected or ignored)." % name)
                continue
            if direction == "request" and name in new_req and name not in old_req:
                self.add("breaking", "property-became-required", label, ploc,
                         "Request property '%s' became required." % name)
            if direction == "response" and name in old_req and name not in new_req:
                self.add("breaking", "response-property-optional", label, ploc,
                         "Response property '%s' is no longer guaranteed (removed from required)." % name)
            self.compare_schema(label, ploc, deref(self.old, old_props[name]), deref(self.new, new_props[name]),
                                direction, depth + 1, seen)
        if "items" in old or "items" in new:
            self.compare_schema(label, "%s[]" % loc, deref(self.old, old.get("items") or {}),
                                deref(self.new, new.get("items") or {}), direction, depth + 1, seen)
        for keyword in ("oneOf", "anyOf", "allOf"):
            if (old.get(keyword) is None) != (new.get(keyword) is None) or \
                    len(old.get(keyword) or []) != len(new.get(keyword) or []):
                self.add("potentially-breaking", "composition-changed", label, loc,
                         "'%s' composition changed; review manually." % keyword)

    def compare_enum(self, label, loc, old, new, direction) -> None:
        if "enum" not in old and "enum" not in new:
            return
        old_values = old.get("enum")
        new_values = new.get("enum")
        if old_values is None:
            if direction == "request":
                self.add("breaking", "enum-added", label, loc, "Request value now restricted to enum %s." % new_values)
            return
        if new_values is None:
            if direction == "response":
                self.add("potentially-breaking", "enum-removed", label, loc, "Response enum restriction removed.")
            return
        removed = [v for v in old_values if v not in new_values]
        added = [v for v in new_values if v not in old_values]
        if removed:
            level = "breaking" if direction == "request" else "non-breaking"
            self.add(level, "enum-value-removed", label, loc, "Enum values removed: %s." % removed)
        if added:
            level = "potentially-breaking" if direction == "response" else "non-breaking"
            self.add(level, "enum-value-added", label, loc,
                     "Enum values added: %s%s." % (added, " (clients must tolerate unknown values)" if direction == "response" else ""))

    def compare_constraints(self, label, loc, old, new) -> None:
        for keyword in TIGHTER_IF_LOWER:
            o, n = old.get(keyword), new.get(keyword)
            if isinstance(n, (int, float)) and not isinstance(n, bool) and (o is None or (isinstance(o, (int, float)) and n < o)):
                self.add("breaking", "constraint-tightened", label, loc, "%s tightened %r → %r." % (keyword, o, n))
        for keyword in TIGHTER_IF_HIGHER:
            o, n = old.get(keyword), new.get(keyword)
            if isinstance(n, (int, float)) and not isinstance(n, bool) and (o is None or (isinstance(o, (int, float)) and n > o)):
                self.add("breaking", "constraint-tightened", label, loc, "%s tightened %r → %r." % (keyword, o, n))

    # -- security ------------------------------------------------------------------
    def effective_security(self, doc, op):
        sec = op.get("security", doc.get("security"))
        return sec if isinstance(sec, list) else []

    def compare_security(self, label, old_op, new_op) -> None:
        old_sec = self.effective_security(self.old, old_op)
        new_sec = self.effective_security(self.new, new_op)
        old_public = not old_sec or any(isinstance(r, dict) and not r for r in old_sec)
        new_public = not new_sec or any(isinstance(r, dict) and not r for r in new_sec)
        loc = "%s security" % label
        if old_public and not new_public:
            self.add("breaking", "security-added", label, loc, "Operation now requires authentication.")
            return
        if not old_public and new_public:
            self.add("info", "security-removed", label, loc,
                     "Operation no longer requires authentication — confirm this is intentional (security review).")
            return

        def scope_sets(sec):
            return [(frozenset(r.keys()), frozenset(s for v in r.values() if isinstance(v, list) for s in v))
                    for r in sec if isinstance(r, dict)]

        old_alts, new_alts = scope_sets(old_sec), scope_sets(new_sec)
        # Breaking if some previously valid alternative is no longer satisfiable by any new alternative.
        for schemes, scopes in old_alts:
            if not any(n_schemes <= schemes and n_scopes <= scopes for n_schemes, n_scopes in new_alts):
                self.add("breaking", "security-requirements-changed", label, loc,
                         "Security alternative %s with scopes %s is no longer sufficient." % (sorted(schemes), sorted(scopes)))


def render_text(result: Dict[str, Any]) -> str:
    lines = ["Contract comparison: %s → %s" % (result["old"], result["new"])]
    summary = result["summary"]
    lines.append("Summary: " + ", ".join("%s=%d" % (lvl, summary[lvl]) for lvl in LEVELS))
    for change in result["changes"]:
        lines.append("  %s [%s] %s — %s (%s)" % (change["id"], change["level"].upper(), change["rule"],
                                                 change["message"], change["location"]))
    if not result["changes"]:
        lines.append("  No differences detected.")
    lines.append("Note: semantic and behavioral changes are not detectable automatically; review manually.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changes between two OpenAPI contracts.")
    parser.add_argument("old", help="Previous contract")
    parser.add_argument("new", help="Proposed contract")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fail-on", choices=["breaking", "potentially-breaking", "none"], default="breaking")
    args = parser.parse_args(argv)
    try:
        check_runtime()
        old = load_document(args.old)
        new = load_document(args.new)
        for name, doc in (("OLD", old), ("NEW", new)):
            if not isinstance(doc, dict) or not str(doc.get("openapi", "")).startswith("3."):
                raise ScriptError("%s is not an OpenAPI 3.x document." % name, EXIT_INPUT)
    except ScriptError as exc:
        return fail(str(exc), exc.code, args.format)

    comparator = Comparator(old, new)
    comparator.run()
    changes = sorted(comparator.changes, key=lambda c: (LEVEL_RANK[c["level"]], c["operation"], c["location"]))
    for i, change in enumerate(changes, 1):
        change["id"] = "CHG-%03d" % i
    summary = {lvl: sum(1 for c in changes if c["level"] == lvl) for lvl in LEVELS}
    result = {"old": args.old, "new": args.new, "summary": summary,
              "changes": [{k: c[k] for k in ("id", "level", "rule", "operation", "location", "message")} for c in changes]}
    emit(result, render_text(result), args.format)
    if args.fail_on == "none":
        return EXIT_OK
    threshold = LEVEL_RANK[args.fail_on]
    return EXIT_FAIL if any(LEVEL_RANK[c["level"]] <= threshold for c in changes) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
