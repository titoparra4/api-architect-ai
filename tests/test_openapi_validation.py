"""Tests for scripts/validate_openapi.py."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, ROOT, SKILL_DIR, run_json, run_script

from validate_openapi import Validator


def rules(result, severity="errors"):
    return {issue["rule"] for issue in result[severity]}


def minimal(**overrides):
    doc = {
        "openapi": "3.1.1",
        "info": {"title": "T", "version": "1.0.0", "description": "d"},
        "servers": [{"url": "https://api.example.com"}],
        "security": [],
        "paths": {
            "/things/{thingId}": {
                "get": {
                    "operationId": "getThing", "summary": "s", "tags": ["T"],
                    "parameters": [{"name": "thingId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok"}, "404": {"description": "nf"}},
                }
            }
        },
        "tags": [{"name": "T"}],
    }
    doc.update(overrides)
    return doc


class ValidatorUnitTest(unittest.TestCase):
    def validate(self, doc, lint=True):
        v = Validator(doc, lint=lint)
        v.run()
        return v

    def test_minimal_document_is_valid_without_warnings(self):
        v = self.validate(minimal())
        self.assertEqual(v.errors, [])
        self.assertEqual(v.warnings, [])

    def test_swagger_2_rejected(self):
        v = self.validate({"swagger": "2.0", "info": {}, "paths": {}})
        self.assertEqual({e["rule"] for e in v.errors}, {"unsupported-version"})

    def test_openapi_30_accepted_with_warning(self):
        v = self.validate(minimal(openapi="3.0.3"))
        self.assertEqual(v.errors, [])
        self.assertIn("legacy-version", {w["rule"] for w in v.warnings})

    def test_openapi_32_query_method_allowed_only_in_32(self):
        query_op = {"operationId": "searchThings", "summary": "s", "tags": ["T"],
                    "responses": {"200": {"description": "ok"}, "400": {"description": "bad"}}}
        doc31 = minimal()
        doc31["paths"]["/things"] = {"query": dict(query_op)}
        self.assertIn("method-unsupported", {e["rule"] for e in self.validate(doc31).errors})
        doc32 = minimal(openapi="3.2.0")
        doc32["paths"]["/things"] = {"query": dict(query_op)}
        self.assertEqual(self.validate(doc32).errors, [])

    def test_unquoted_numeric_version_is_reported(self):
        v = self.validate(minimal(openapi=3.1))
        self.assertIn("openapi-field", {e["rule"] for e in v.errors})

    def test_path_param_must_be_required(self):
        doc = minimal()
        doc["paths"]["/things/{thingId}"]["get"]["parameters"][0]["required"] = False
        self.assertIn("path-param-required", {e["rule"] for e in self.validate(doc).errors})

    def test_declared_path_param_missing_from_template(self):
        doc = minimal()
        doc["paths"]["/things/{thingId}"]["get"]["parameters"].append(
            {"name": "other", "in": "path", "required": True, "schema": {"type": "string"}})
        self.assertIn("path-param-in-template", {e["rule"] for e in self.validate(doc).errors})

    def test_ambiguous_paths(self):
        doc = minimal()
        doc["paths"]["/things/{id}"] = {"get": {"operationId": "x", "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok"}}}}
        self.assertIn("path-ambiguous", {e["rule"] for e in self.validate(doc).errors})

    def test_paths_optional_in_31_with_components(self):
        doc = minimal()
        del doc["paths"]
        doc["components"] = {"schemas": {"A": {"type": "string"}}}
        self.assertEqual(self.validate(doc).errors, [])

    def test_example_with_ref_key_is_literal_data(self):
        doc = minimal(components={"schemas": {"A": {"type": "object", "example": {"$ref": "#/nope"}},
                                              "B": {"type": "object", "properties": {
                                                  "value": {"$ref": "#/components/schemas/Missing"}}}}})
        errors = self.validate(doc).errors
        self.assertEqual([e["location"] for e in errors if e["rule"] == "ref-resolves"],
                         ["#/components/schemas/B/properties/value"])

    def test_oauth2_deprecated_flows_warned(self):
        doc = minimal(components={"securitySchemes": {"o": {"type": "oauth2", "flows": {
            "implicit": {"authorizationUrl": "https://a", "scopes": {}},
            "password": {"tokenUrl": "https://a", "scopes": {}}}}}})
        warnings = {w["rule"] for w in self.validate(doc).warnings}
        self.assertTrue({"oauth2-implicit", "oauth2-password"} <= warnings)

    def test_no_lint_suppresses_warnings(self):
        doc = minimal()
        del doc["servers"]
        self.assertEqual(self.validate(doc, lint=False).warnings, [])

    def test_missing_security_declaration_warned(self):
        doc = minimal()
        del doc["security"]
        self.assertIn("security-declared", {w["rule"] for w in self.validate(doc).warnings})


class ValidatorCliTest(unittest.TestCase):
    def test_template_and_examples_are_valid(self):
        specs = [SKILL_DIR / "assets" / "openapi-template.yaml"] + sorted((ROOT / "examples").rglob("openapi*.yaml"))
        self.assertGreaterEqual(len(specs), 3)
        for spec in specs:
            code, result = run_json("validate_openapi.py", str(spec))
            self.assertEqual(code, 0, "%s: %s" % (spec, result["errors"]))
            self.assertTrue(result["valid"])

    def test_template_has_no_lint_warnings_in_strict_mode(self):
        proc = run_script("validate_openapi.py", str(SKILL_DIR / "assets" / "openapi-template.yaml"), "--strict")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_invalid_fixture_reports_each_defect(self):
        code, result = run_json("validate_openapi.py", str(FIXTURES / "invalid-openapi.yaml"))
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        expected = {"info-version", "ref-resolves", "path-param-declared", "response-code",
                    "parameter-unique", "operation-id-unique", "security-scheme-defined"}
        self.assertEqual(rules(result), expected)
        self.assertIn("problem-details", rules(result, "warnings"))
        self.assertIn("pagination-bounded", rules(result, "warnings"))

    def test_embedded_instructions_are_treated_as_data(self):
        code, result = run_json("validate_openapi.py", str(FIXTURES / "malicious-openapi.yaml"))
        # Real defects are still reported; injected text does not change the verdict.
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertIn("path-param-declared", rules(result))
        self.assertTrue({"server-https", "security-declared"} <= rules(result, "warnings"))
        # The literal "$ref" inside an example must not be resolved or reported.
        self.assertNotIn("ref-resolves", rules(result))

    def test_strict_mode_fails_on_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            doc = minimal()
            del doc["servers"]
            path.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(run_script("validate_openapi.py", str(path)).returncode, 0)
            self.assertEqual(run_script("validate_openapi.py", str(path), "--strict").returncode, 1)

    def test_missing_file_exit_2(self):
        proc = run_script("validate_openapi.py", str(FIXTURES / "does-not-exist.yaml"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("File not found", proc.stderr)

    def test_unparseable_yaml_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.yaml"
            path.write_text("openapi: 3.1.0\ninfo: [unclosed\n", encoding="utf-8")
            proc = run_script("validate_openapi.py", str(path))
            self.assertEqual(proc.returncode, 2, proc.stderr)

    def test_missing_pyyaml_exit_3_but_json_still_works(self):
        proc = run_script("validate_openapi.py", str(FIXTURES / "orders-v1.yaml"), hide_yaml=True)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("PyYAML is required", proc.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            path.write_text(json.dumps(minimal()), encoding="utf-8")
            self.assertEqual(run_script("validate_openapi.py", str(path), hide_yaml=True).returncode, 0)

    def test_external_validator_missing_dependency_exit_3(self):
        try:
            import openapi_spec_validator  # noqa: F401
        except ImportError:
            proc = run_script("validate_openapi.py", str(SKILL_DIR / "assets" / "openapi-template.yaml"), "--external")
            self.assertEqual(proc.returncode, 3)
            self.assertIn("openapi-spec-validator", proc.stderr)
        else:
            proc = run_script("validate_openapi.py", str(SKILL_DIR / "assets" / "openapi-template.yaml"), "--external")
            self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
