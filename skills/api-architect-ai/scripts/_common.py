"""Shared helpers for API Architect AI scripts.

Standard library only, except PyYAML which is imported lazily and only for YAML input.
Exit-code convention for all scripts:
    0  success / check passed
    1  check failed (validation errors, breaking changes, critical alert when requested)
    2  invalid input or usage (file missing, parse error, wrong structure)
    3  missing dependency or unsupported runtime
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_INPUT = 2
EXIT_DEPENDENCY = 3

MIN_PYTHON = (3, 9)


class ScriptError(Exception):
    """Error carrying an exit code and a user-facing message."""

    def __init__(self, message: str, code: int = EXIT_INPUT):
        super().__init__(message)
        self.code = code


def check_runtime() -> None:
    if sys.version_info < MIN_PYTHON:
        raise ScriptError(
            "Python %d.%d+ is required (running %d.%d)."
            % (MIN_PYTHON[0], MIN_PYTHON[1], sys.version_info[0], sys.version_info[1]),
            EXIT_DEPENDENCY,
        )


def load_document(path_str: str) -> Any:
    """Load a JSON or YAML document. YAML requires PyYAML (safe_load only)."""
    path = Path(path_str)
    if not path.is_file():
        raise ScriptError("File not found: %s" % path_str, EXIT_INPUT)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScriptError("Cannot read %s: %s" % (path_str, exc), EXIT_INPUT)

    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ScriptError("Invalid JSON in %s: %s" % (path_str, exc), EXIT_INPUT)

    # YAML (or unknown extension): try JSON first, which needs no dependency.
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    try:
        import yaml  # type: ignore
    except ImportError:
        raise ScriptError(
            "PyYAML is required to read YAML files. Install it with "
            "'python3 -m pip install -r requirements.txt' or provide JSON input.",
            EXIT_DEPENDENCY,
        )
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise ScriptError("Invalid YAML in %s: %s" % (path_str, exc), EXIT_INPUT)


def unescape_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def escape_pointer_token(token: str) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def resolve_pointer(document: Any, ref: str) -> Tuple[bool, Any]:
    """Resolve a local JSON pointer like '#/components/schemas/X'. Returns (found, value)."""
    if not ref.startswith("#"):
        return False, None
    pointer = ref[1:]
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    node = document
    for raw in pointer.split("/")[1:]:
        token = unescape_pointer_token(raw)
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return False, None
    return True, node


def deref(document: Any, node: Any, max_depth: int = 20) -> Any:
    """Follow local $ref chains on a node (shallow). Unresolvable refs return the node unchanged."""
    seen = set()
    depth = 0
    while isinstance(node, dict) and isinstance(node.get("$ref"), str) and depth < max_depth:
        ref = node["$ref"]
        if ref in seen:
            break
        seen.add(ref)
        found, target = resolve_pointer(document, ref)
        if not found:
            break
        node = target
        depth += 1
    return node


def emit(payload: Dict[str, Any], text: str, fmt: str, stream=None) -> None:
    stream = stream or sys.stdout
    if fmt == "json":
        stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        stream.write(text if text.endswith("\n") else text + "\n")


def fail(message: str, code: int, fmt: Optional[str] = "text") -> int:
    if fmt == "json":
        sys.stdout.write(json.dumps({"error": message, "exit_code": code}) + "\n")
    else:
        sys.stderr.write("error: %s\n" % message)
    return code
