#!/usr/bin/env python3
"""Validate an OpenAPI 3.1.x / 3.2.x document (3.0.x accepted with a warning).

Usage:
    validate_openapi.py SPEC [--format text|json] [--strict] [--external] [--no-lint]

Inputs:
    SPEC        Path to an OpenAPI document (.yaml, .yml or .json).
Options:
    --format    Output format (default: text).
    --strict    Treat lint warnings as failures (exit 1).
    --external  Additionally run openapi-spec-validator (must be installed; exit 3 otherwise).
    --no-lint   Only structural checks; skip governance lint warnings.

Output:
    Text report or JSON: {"file", "openapi_version", "valid", "errors": [...], "warnings": [...],
    "stats": {...}}. Each issue: {"rule", "severity", "location", "message"}.

Dependencies:
    Python 3.9+. PyYAML for YAML input. Optional: openapi-spec-validator (--external).

Exit codes:
    0 valid (warnings allowed unless --strict) · 1 errors found (or warnings with --strict)
    2 unreadable/unparseable input · 3 missing dependency or unsupported runtime

The script only reads the document. It never executes code and never fetches remote $refs.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EXIT_DEPENDENCY,
    EXIT_FAIL,
    EXIT_OK,
    ScriptError,
    check_runtime,
    emit,
    escape_pointer_token,
    fail,
    load_document,
    resolve_pointer,
    deref,
)

BASE_METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"]
PARAM_LOCATIONS_31 = {"query", "header", "path", "cookie"}
RESPONSE_CODE_RE = re.compile(r"^([1-5][0-9][0-9]|[1-5]XX|default)$")
VERSION_RE = re.compile(r"^3\.(\d+)\.(\d+)(-.+)?$")
PATH_TEMPLATE_RE = re.compile(r"\{([^{}/]+)\}")
LITERAL_KEYS = {"example", "default", "const", "enum", "value"}
# Maps whose keys are user-chosen names (a property may legitimately be called "value" or "default").
NAME_MAP_KEYS = {"properties", "patternProperties", "schemas", "parameters", "responses", "examples",
                 "headers", "securitySchemes", "links", "callbacks", "pathItems", "requestBodies",
                 "$defs", "definitions", "paths", "webhooks", "content", "encoding", "variables",
                 "dependentSchemas"}


class Validator:
    def __init__(self, doc: Any, lint: bool = True):
        self.doc = doc
        self.lint = lint
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []
        self.minor: Optional[int] = None
        self.stats = {"paths": 0, "operations": 0, "schemas": 0, "refs_checked": 0}

    # -- issue helpers -------------------------------------------------------------
    def error(self, rule: str, location: str, message: str) -> None:
        self.errors.append({"rule": rule, "severity": "error", "location": location, "message": message})

    def warn(self, rule: str, location: str, message: str) -> None:
        self.warnings.append({"rule": rule, "severity": "warning", "location": location, "message": message})

    def lint_warn(self, rule: str, location: str, message: str) -> None:
        if self.lint:
            self.warn(rule, location, message)

    # -- entry point ---------------------------------------------------------------
    def run(self) -> None:
        if not isinstance(self.doc, dict):
            self.error("root-object", "#", "Document root must be an object.")
            return
        if "swagger" in self.doc:
            self.error("unsupported-version", "#/swagger",
                       "Swagger 2.0 is not supported; migrate to OpenAPI 3.1.")
            return
        self.check_version()
        if self.minor is None:
            return
        self.check_info()
        self.check_servers()
        self.check_refs(self.doc, "#")
        self.check_paths()
        self.check_security_requirements(self.doc.get("security"), "#/security")
        self.check_components()
        self.check_tags_lint()

    # -- version / info ------------------------------------------------------------
    def check_version(self) -> None:
        version = self.doc.get("openapi")
        if not isinstance(version, str):
            self.error("openapi-field", "#/openapi",
                       "Missing or non-string 'openapi' field (quote it in YAML, e.g. openapi: '3.1.1').")
            return
        match = VERSION_RE.match(version)
        if not match:
            self.error("unsupported-version", "#/openapi",
                       "Unsupported OpenAPI version '%s'; expected 3.1.x or 3.2.x." % version)
            return
        minor = int(match.group(1))
        if minor == 0:
            self.warn("legacy-version", "#/openapi",
                      "OpenAPI 3.0.x detected: validated with 3.1 structural rules where compatible; "
                      "consider migrating to 3.1.")
        elif minor not in (1, 2):
            self.error("unsupported-version", "#/openapi",
                       "OpenAPI %s is not supported by this validator (3.1.x and 3.2.x)." % version)
            return
        self.minor = minor

    def check_info(self) -> None:
        info = self.doc.get("info")
        if not isinstance(info, dict):
            self.error("info-object", "#/info", "Missing required 'info' object.")
            return
        for field in ("title", "version"):
            if not isinstance(info.get(field), str) or not info.get(field).strip():
                self.error("info-%s" % field, "#/info/%s" % field, "info.%s is required and must be a non-empty string." % field)
        if not info.get("description"):
            self.lint_warn("info-description", "#/info/description", "info.description is recommended.")
        lic = info.get("license")
        if isinstance(lic, dict) and "identifier" in lic and "url" in lic:
            self.error("license-exclusive", "#/info/license", "license.identifier and license.url are mutually exclusive.")

    def check_servers(self) -> None:
        servers = self.doc.get("servers")
        if servers is None:
            self.lint_warn("servers-defined", "#/servers", "No servers declared.")
            return
        if not isinstance(servers, list):
            self.error("servers-array", "#/servers", "servers must be an array.")
            return
        for i, server in enumerate(servers):
            loc = "#/servers/%d" % i
            if not isinstance(server, dict) or not isinstance(server.get("url"), str):
                self.error("server-url", loc, "Each server requires a string 'url'.")
                continue
            url = server["url"]
            if url.startswith("http://") and not re.match(r"^http://(localhost|127\.0\.0\.1|\[::1\])", url):
                self.lint_warn("server-https", loc, "Server URL uses plain HTTP: %s" % url)

    # -- references ----------------------------------------------------------------
    def check_refs(self, node: Any, location: str) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                self.stats["refs_checked"] += 1
                if ref.startswith("#"):
                    found, _ = resolve_pointer(self.doc, ref)
                    if not found:
                        self.error("ref-resolves", location, "Unresolved local $ref '%s'." % ref)
                else:
                    self.warn("ref-external", location,
                              "External $ref '%s' not resolved by this validator." % ref)
            is_name_map = location.rsplit("/", 1)[-1] in NAME_MAP_KEYS
            for key, value in node.items():
                if key in LITERAL_KEYS and not is_name_map:
                    continue  # literal data: a "$ref" key inside an example is not a reference
                self.check_refs(value, "%s/%s" % (location, escape_pointer_token(key)))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                self.check_refs(item, "%s/%d" % (location, i))

    # -- paths ---------------------------------------------------------------------
    def allowed_methods(self) -> List[str]:
        return BASE_METHODS + (["query"] if self.minor == 2 else [])

    def check_paths(self) -> None:
        paths = self.doc.get("paths")
        if paths is None:
            if self.minor == 0 or not (self.doc.get("components") or self.doc.get("webhooks")):
                self.error("paths-required", "#/paths",
                           "'paths' is required (3.1+ allows omitting it only when components or webhooks exist).")
            return
        if not isinstance(paths, dict):
            self.error("paths-object", "#/paths", "'paths' must be an object.")
            return
        operation_ids: Dict[str, str] = {}
        normalized: Dict[str, str] = {}
        for path, item in paths.items():
            self.stats["paths"] += 1
            ploc = "#/paths/%s" % escape_pointer_token(path)
            if not isinstance(path, str) or not path.startswith("/"):
                self.error("path-syntax", ploc, "Path '%s' must start with '/'." % path)
                continue
            norm = PATH_TEMPLATE_RE.sub("{}", path)
            if norm in normalized:
                self.error("path-ambiguous", ploc,
                           "Path '%s' is equivalent to '%s' (same template, different parameter names)." % (path, normalized[norm]))
            normalized[norm] = path
            if self.lint:
                if path != "/" and path.endswith("/"):
                    self.warn("path-trailing-slash", ploc, "Path ends with '/'.")
                for segment in path.strip("/").split("/"):
                    if segment and not segment.startswith("{") and re.search(r"[A-Z_]", segment):
                        self.warn("path-kebab-case", ploc, "Path segment '%s' is not kebab-case." % segment)
            item = deref(self.doc, item)
            if not isinstance(item, dict):
                self.error("path-item-object", ploc, "Path item must be an object.")
                continue
            template_params = PATH_TEMPLATE_RE.findall(path)
            path_level = self.collect_params(item.get("parameters"), ploc + "/parameters")
            operations = [(m, item[m]) for m in self.allowed_methods() if m in item]
            if self.minor == 2 and isinstance(item.get("additionalOperations"), dict):
                for m, op in item["additionalOperations"].items():
                    operations.append(("additionalOperations/%s" % m, op))
            if self.minor != 2 and "query" in item:
                self.error("method-unsupported", ploc + "/query", "The 'query' method requires OpenAPI 3.2.")
            if not operations:
                self.lint_warn("path-has-operations", ploc, "Path declares no operations.")
            for method, op in operations:
                self.check_operation(path, method, op, ploc, path_level, template_params, operation_ids)

    def collect_params(self, params: Any, location: str) -> Dict[tuple, Dict[str, Any]]:
        result: Dict[tuple, Dict[str, Any]] = {}
        if params is None:
            return result
        if not isinstance(params, list):
            self.error("parameters-array", location, "parameters must be an array.")
            return result
        locations = set(PARAM_LOCATIONS_31)
        if self.minor == 2:
            locations.add("querystring")
        for i, raw in enumerate(params):
            loc = "%s/%d" % (location, i)
            param = deref(self.doc, raw)
            if not isinstance(param, dict):
                continue  # unresolved ref already reported
            name, where = param.get("name"), param.get("in")
            if not isinstance(name, str) or not name:
                self.error("parameter-name", loc, "Parameter requires a non-empty 'name'.")
                continue
            if where not in locations:
                self.error("parameter-in", loc, "Parameter '%s' has invalid 'in': %r." % (name, where))
                continue
            if where == "path" and param.get("required") is not True:
                self.error("path-param-required", loc, "Path parameter '%s' must have required: true." % name)
            if "schema" not in param and "content" not in param:
                self.error("parameter-schema", loc, "Parameter '%s' needs 'schema' or 'content'." % name)
            key = (name.lower() if where == "header" else name, where)
            if key in result:
                self.error("parameter-unique", loc, "Duplicate parameter '%s' in %s." % (name, where))
            result[key] = param
        return result

    def check_operation(self, path, method, op, ploc, path_level, template_params, operation_ids) -> None:
        self.stats["operations"] += 1
        oloc = "%s/%s" % (ploc, method)
        label = "%s %s" % (method.upper(), path)
        if not isinstance(op, dict):
            self.error("operation-object", oloc, "Operation must be an object.")
            return
        op_level = self.collect_params(op.get("parameters"), oloc + "/parameters")
        merged = dict(path_level)
        merged.update(op_level)
        declared_path = {k[0] for k in merged if k[1] == "path"}
        for name in template_params:
            if name not in declared_path:
                self.error("path-param-declared", oloc,
                           "%s: path template parameter '{%s}' is not declared as an 'in: path' parameter." % (label, name))
        for name in declared_path - set(template_params):
            self.error("path-param-in-template", oloc,
                       "%s: path parameter '%s' is not present in the path template." % (label, name))

        op_id = op.get("operationId")
        if op_id is None:
            self.lint_warn("operation-id", oloc, "%s: missing operationId." % label)
        elif op_id in operation_ids:
            self.error("operation-id-unique", oloc,
                       "%s: operationId '%s' already used by %s." % (label, op_id, operation_ids[op_id]))
        else:
            operation_ids[op_id] = label
        if not op.get("summary") and not op.get("description"):
            self.lint_warn("operation-summary", oloc, "%s: missing summary/description." % label)
        if not op.get("tags"):
            self.lint_warn("operation-tags", oloc, "%s: operation has no tags." % label)
        if method in ("get", "head", "delete") and "requestBody" in op:
            self.lint_warn("no-body-on-%s" % method, oloc, "%s: requestBody on %s is discouraged (undefined semantics)." % (label, method.upper()))

        self.check_security_requirements(op.get("security"), oloc + "/security")
        if "security" not in op and "security" not in self.doc:
            self.lint_warn("security-declared", oloc,
                           "%s: no security requirement declared (declare one, or 'security: []' if intentionally public)." % label)
        self.check_limit_params(merged, oloc, label)

        responses = op.get("responses")
        if responses is None:
            if self.minor == 0:
                self.error("responses-required", oloc, "%s: 'responses' is required in OpenAPI 3.0." % label)
            else:
                self.lint_warn("responses-defined", oloc, "%s: no responses declared." % label)
            return
        if not isinstance(responses, dict) or not responses:
            self.error("responses-object", oloc + "/responses", "%s: responses must be a non-empty object." % label)
            return
        has_success, has_4xx = False, False
        for code, resp in responses.items():
            code_str = str(code)
            rloc = "%s/responses/%s" % (oloc, escape_pointer_token(code_str))
            if not RESPONSE_CODE_RE.match(code_str):
                self.error("response-code", rloc, "%s: invalid response code '%s'." % (label, code_str))
                continue
            if code_str.startswith("2"):
                has_success = True
            if code_str.startswith("4"):
                has_4xx = True
            resp = deref(self.doc, resp)
            if not isinstance(resp, dict):
                continue
            if "description" not in resp:
                self.error("response-description", rloc, "%s: response '%s' requires 'description'." % (label, code_str))
            if self.lint and (code_str[0] in "45") and isinstance(resp.get("content"), dict):
                media = set(resp["content"].keys())
                if media and "application/problem+json" not in media:
                    self.warn("problem-details", rloc,
                              "%s: error response '%s' does not use application/problem+json (RFC 9457)." % (label, code_str))
        if not has_success and "default" not in responses:
            self.lint_warn("success-response", oloc, "%s: no 2xx response declared." % label)
        if not has_4xx:
            self.lint_warn("error-responses", oloc, "%s: no 4xx response declared." % label)

    def check_limit_params(self, params, oloc, label) -> None:
        if not self.lint:
            return
        for (name, where), param in params.items():
            if where == "query" and name.lower() in ("limit", "pagesize", "page_size", "per_page", "size"):
                schema = deref(self.doc, param.get("schema") or {})
                if isinstance(schema, dict) and "maximum" not in schema:
                    self.warn("pagination-bounded", oloc,
                              "%s: page-size parameter '%s' has no maximum (OWASP API4)." % (label, name))

    # -- security ------------------------------------------------------------------
    def check_security_requirements(self, security: Any, location: str) -> None:
        if security is None:
            return
        if not isinstance(security, list):
            self.error("security-array", location, "security must be an array of requirement objects.")
            return
        schemes = (self.doc.get("components") or {}).get("securitySchemes") or {}
        for i, requirement in enumerate(security):
            if not isinstance(requirement, dict):
                self.error("security-requirement", "%s/%d" % (location, i), "Security requirement must be an object.")
                continue
            for name, scopes in requirement.items():
                if name not in schemes:
                    self.error("security-scheme-defined", "%s/%d" % (location, i),
                               "Security requirement references undefined scheme '%s'." % name)
                if not isinstance(scopes, list):
                    self.error("security-scopes", "%s/%d/%s" % (location, i, name), "Scopes must be an array.")

    def check_components(self) -> None:
        components = self.doc.get("components") or {}
        if not isinstance(components, dict):
            self.error("components-object", "#/components", "components must be an object.")
            return
        schemas = components.get("schemas") or {}
        self.stats["schemas"] = len(schemas) if isinstance(schemas, dict) else 0
        for name, scheme in (components.get("securitySchemes") or {}).items():
            loc = "#/components/securitySchemes/%s" % escape_pointer_token(name)
            scheme = deref(self.doc, scheme)
            if not isinstance(scheme, dict):
                continue
            kind = scheme.get("type")
            valid = {"apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"}
            if kind not in valid:
                self.error("security-scheme-type", loc, "Invalid security scheme type %r." % kind)
            elif kind == "apiKey":
                if scheme.get("in") not in ("query", "header", "cookie") or not scheme.get("name"):
                    self.error("security-scheme-apikey", loc, "apiKey scheme requires 'name' and 'in'.")
                elif scheme.get("in") == "query":
                    self.lint_warn("apikey-in-query", loc, "API key in query string leaks into logs; use a header.")
            elif kind == "http" and not scheme.get("scheme"):
                self.error("security-scheme-http", loc, "http scheme requires 'scheme' (e.g. bearer).")
            elif kind == "oauth2":
                flows = scheme.get("flows")
                if not isinstance(flows, dict) or not flows:
                    self.error("security-scheme-oauth2", loc, "oauth2 scheme requires 'flows'.")
                elif self.lint:
                    if "implicit" in flows:
                        self.warn("oauth2-implicit", loc, "Implicit flow is deprecated by the OAuth 2.0 Security BCP (RFC 9700).")
                    if "password" in flows:
                        self.warn("oauth2-password", loc, "Resource owner password flow is deprecated by RFC 9700.")
            elif kind == "openIdConnect" and not scheme.get("openIdConnectUrl"):
                self.error("security-scheme-oidc", loc, "openIdConnect scheme requires 'openIdConnectUrl'.")
            if kind == "mutualTLS" and self.minor == 0:
                self.error("security-scheme-type", loc, "mutualTLS requires OpenAPI 3.1+.")

    def check_tags_lint(self) -> None:
        if not self.lint:
            return
        declared = {t.get("name") for t in (self.doc.get("tags") or []) if isinstance(t, dict)}
        used = set()
        for item in (self.doc.get("paths") or {}).values():
            item = deref(self.doc, item)
            if not isinstance(item, dict):
                continue
            for m in self.allowed_methods():
                op = item.get(m)
                if isinstance(op, dict):
                    used.update(t for t in op.get("tags") or [] if isinstance(t, str))
        for tag in sorted(used - declared):
            self.warn("tag-declared", "#/tags", "Tag '%s' is used but not declared in top-level tags." % tag)


def run_external(path: str) -> List[Dict[str, str]]:
    try:
        from openapi_spec_validator import validate  # type: ignore
        from openapi_spec_validator.readers import read_from_filename  # type: ignore
    except ImportError:
        raise ScriptError("--external requires 'openapi-spec-validator' (pip install openapi-spec-validator).",
                          EXIT_DEPENDENCY)
    spec_dict, _ = read_from_filename(path)
    try:
        validate(spec_dict)
    except Exception as exc:  # validator raises its own exception hierarchy
        message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return [{"rule": "external-validator", "severity": "error", "location": "#", "message": message}]
    return []


def render_text(result: Dict[str, Any]) -> str:
    lines = ["OpenAPI validation: %s" % result["file"],
             "Version: %s" % (result["openapi_version"] or "unknown"),
             "Result: %s (%d errors, %d warnings)" % ("VALID" if result["valid"] else "INVALID",
                                                     len(result["errors"]), len(result["warnings"]))]
    stats = result["stats"]
    lines.append("Stats: %d paths, %d operations, %d schemas, %d $refs checked" % (
        stats["paths"], stats["operations"], stats["schemas"], stats["refs_checked"]))
    for issue in result["errors"] + result["warnings"]:
        lines.append("  [%s] %s %s — %s" % (issue["severity"].upper(), issue["rule"], issue["location"], issue["message"]))
    if result.get("external") == "not-run":
        lines.append("Note: external validator not run (use --external to enable).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OpenAPI 3.1/3.2 document (structure + lint).")
    parser.add_argument("spec", help="Path to the OpenAPI document (.yaml/.yml/.json)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings too")
    parser.add_argument("--external", action="store_true", help="Also run openapi-spec-validator")
    parser.add_argument("--no-lint", action="store_true", help="Skip governance lint warnings")
    args = parser.parse_args(argv)
    try:
        check_runtime()
        doc = load_document(args.spec)
        validator = Validator(doc, lint=not args.no_lint)
        validator.run()
        external_status = "not-run"
        if args.external:
            validator.errors.extend(run_external(args.spec))
            external_status = "run"
    except ScriptError as exc:
        return fail(str(exc), exc.code, args.format)

    valid = not validator.errors
    result = {
        "file": args.spec,
        "openapi_version": doc.get("openapi") if isinstance(doc, dict) else None,
        "valid": valid,
        "errors": validator.errors,
        "warnings": validator.warnings,
        "stats": validator.stats,
        "external": external_status,
    }
    emit(result, render_text(result), args.format)
    if not valid or (args.strict and validator.warnings):
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
