"""Tests for scripts/compare_contracts.py."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, run_json, run_script

from compare_contracts import Comparator

BASE = {
    "openapi": "3.1.1",
    "info": {"title": "T", "version": "1.0.0"},
    "paths": {
        "/items": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "required": ["name"],
                    "properties": {"name": {"type": "string", "maxLength": 50},
                                   "kind": {"type": "string", "enum": ["A", "B"]}}}}}},
                "responses": {"201": {"description": "c", "content": {"application/json": {"schema": {
                    "type": "object", "required": ["id", "name"],
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                                   "kind": {"type": "string", "enum": ["A", "B"]}}}}}}},
            }
        }
    },
}


def diff(mutate):
    new = copy.deepcopy(BASE)
    mutate(new)
    comparator = Comparator(copy.deepcopy(BASE), new)
    comparator.run()
    return {(c["level"], c["rule"]) for c in comparator.changes}


def req_schema(doc):
    return doc["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]


def resp_schema(doc):
    return doc["paths"]["/items"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]


class ComparatorUnitTest(unittest.TestCase):
    def test_identical_contracts_have_no_changes(self):
        self.assertEqual(diff(lambda d: None), set())

    def test_new_required_request_property_is_breaking(self):
        def m(d):
            req_schema(d)["properties"]["sku"] = {"type": "string"}
            req_schema(d)["required"].append("sku")
        self.assertIn(("breaking", "required-property-added"), diff(m))

    def test_new_optional_request_property_is_non_breaking(self):
        changes = diff(lambda d: req_schema(d)["properties"].__setitem__("sku", {"type": "string"}))
        self.assertEqual(changes, {("non-breaking", "property-added")})

    def test_request_enum_value_removed_is_breaking_but_response_removal_is_not(self):
        def m(d):
            req_schema(d)["properties"]["kind"]["enum"] = ["A"]
            resp_schema(d)["properties"]["kind"]["enum"] = ["A"]
        changes = diff(m)
        self.assertIn(("breaking", "enum-value-removed"), changes)
        self.assertIn(("non-breaking", "enum-value-removed"), changes)

    def test_response_enum_value_added_is_potentially_breaking(self):
        changes = diff(lambda d: resp_schema(d)["properties"]["kind"]["enum"].append("C"))
        self.assertEqual(changes, {("potentially-breaking", "enum-value-added")})

    def test_request_constraint_tightened_and_relaxed(self):
        self.assertIn(("breaking", "constraint-tightened"),
                      diff(lambda d: req_schema(d)["properties"]["name"].__setitem__("maxLength", 10)))
        self.assertEqual(diff(lambda d: req_schema(d)["properties"]["name"].__setitem__("maxLength", 100)), set())

    def test_response_property_removed_is_breaking(self):
        def m(d):
            del resp_schema(d)["properties"]["name"]
            resp_schema(d)["required"].remove("name")
        self.assertIn(("breaking", "response-property-removed"), diff(m))

    def test_type_change_is_breaking(self):
        changes = diff(lambda d: resp_schema(d)["properties"]["id"].__setitem__("type", "integer"))
        self.assertIn(("breaking", "type-changed"), changes)

    def test_request_type_widening_is_non_breaking(self):
        changes = diff(lambda d: req_schema(d)["properties"]["name"].__setitem__("type", ["string", "null"]))
        self.assertEqual(changes, set())

    def test_response_nullable_30_style_is_breaking(self):
        changes = diff(lambda d: resp_schema(d)["properties"]["id"].__setitem__("nullable", True))
        self.assertIn(("breaking", "response-became-nullable"), changes)

    def test_success_response_removed_is_breaking(self):
        def m(d):
            responses = d["paths"]["/items"]["post"]["responses"]
            responses["200"] = responses.pop("201")
        changes = diff(m)
        self.assertIn(("breaking", "success-response-removed"), changes)
        self.assertIn(("potentially-breaking", "response-added"), changes)

    def test_request_media_type_removed_is_breaking(self):
        def m(d):
            content = d["paths"]["/items"]["post"]["requestBody"]["content"]
            content["application/xml"] = content.pop("application/json")
        changes = diff(m)
        self.assertIn(("breaking", "request-media-type-removed"), changes)
        self.assertIn(("non-breaking", "request-media-type-added"), changes)

    def test_security_added_to_public_operation_is_breaking(self):
        def m(d):
            d["components"] = {"securitySchemes": {"k": {"type": "apiKey", "in": "header", "name": "X-Key"}}}
            d["paths"]["/items"]["post"]["security"] = [{"k": []}]
        self.assertIn(("breaking", "security-added"), diff(m))

    def test_path_parameter_rename_is_not_a_change(self):
        old = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": {"/a/{x}": {"get": {
            "parameters": [{"name": "x", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok"}}}}}}
        new = copy.deepcopy(old)
        new["paths"] = {"/a/{y}": new["paths"]["/a/{x}"]}
        new["paths"]["/a/{y}"]["get"]["parameters"][0]["name"] = "y"
        comparator = Comparator(old, new)
        comparator.run()
        self.assertEqual(comparator.changes, [])

    def test_recursive_schemas_terminate(self):
        node = {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Node"}}}
        doc = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"},
               "components": {"schemas": {"Node": node}},
               "paths": {"/n": {"get": {"responses": {"200": {"description": "ok", "content": {
                   "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}}}}}}
        comparator = Comparator(doc, copy.deepcopy(doc))
        comparator.run()
        self.assertEqual(comparator.changes, [])


class ComparatorCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.result = run_json("compare_contracts.py", str(FIXTURES / "orders-v1.yaml"),
                                        str(FIXTURES / "orders-v2.yaml"))
        cls.by_rule = {}
        for change in cls.result["changes"]:
            cls.by_rule.setdefault(change["rule"], []).append(change)

    def test_exit_code_signals_breaking_changes(self):
        self.assertEqual(self.code, 1)
        self.assertGreater(self.result["summary"]["breaking"], 0)

    def test_expected_breaking_changes_detected(self):
        expected = {"operation-removed", "required-parameter-added", "constraint-tightened", "enum-value-removed",
                    "response-property-removed", "response-property-optional", "response-became-nullable",
                    "required-property-added", "security-added", "security-requirements-changed"}
        breaking = {c["rule"] for c in self.result["changes"] if c["level"] == "breaking"}
        self.assertTrue(expected <= breaking, "missing: %s" % (expected - breaking))

    def test_specific_locations(self):
        removed = self.by_rule["operation-removed"][0]
        self.assertEqual(removed["operation"], "DELETE /orders/{orderId}")
        self.assertIn("/health", self.by_rule["security-added"][0]["operation"])
        self.assertTrue(any("region" in c["message"] for c in self.by_rule["required-parameter-added"]))

    def test_non_breaking_and_info_changes(self):
        levels = {(c["level"], c["rule"]) for c in self.result["changes"]}
        self.assertIn(("non-breaking", "operation-added"), levels)
        self.assertIn(("non-breaking", "optional-parameter-added"), levels)
        self.assertIn(("info", "operation-deprecated"), levels)
        self.assertIn(("potentially-breaking", "enum-value-added"), levels)

    def test_path_param_rename_not_reported(self):
        renamed = [c for c in self.result["changes"]
                   if c["rule"] in ("parameter-removed", "required-parameter-added", "optional-parameter-added")
                   and "path" in c["location"]]
        self.assertEqual(renamed, [])

    def test_ids_are_sequential(self):
        ids = [c["id"] for c in self.result["changes"]]
        self.assertEqual(ids, ["CHG-%03d" % i for i in range(1, len(ids) + 1)])

    def test_fail_on_none_and_same_file(self):
        proc = run_script("compare_contracts.py", str(FIXTURES / "orders-v1.yaml"), str(FIXTURES / "orders-v2.yaml"),
                          "--fail-on", "none")
        self.assertEqual(proc.returncode, 0)
        proc = run_script("compare_contracts.py", str(FIXTURES / "orders-v1.yaml"), str(FIXTURES / "orders-v1.yaml"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("No differences detected", proc.stdout)

    def test_non_openapi_input_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
            proc = run_script("compare_contracts.py", str(path), str(path))
            self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
