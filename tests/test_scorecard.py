"""Tests for scripts/calculate_score.py and scripts/generate_report.py."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, SKILL_DIR, run_json, run_script

from calculate_score import band_for, calculate
from _common import ScriptError

ALL_IDS = ["api_design", "architecture", "security", "scalability", "interoperability", "testing", "documentation"]


def card(scores, coverage="sufficient", confidence="High", findings=None):
    dims = []
    for dim_id in ALL_IDS:
        score = scores.get(dim_id)
        dims.append({"id": dim_id, "evidence_coverage": coverage if score is not None else "insufficient",
                     "score": score, "confidence": confidence})
    return {"dimensions": dims, "findings": findings or []}


class ScoreCalculationTest(unittest.TestCase):
    def test_all_dimensions_weighted_average(self):
        result = calculate(card({d: 80 for d in ALL_IDS}))
        self.assertEqual(result["overall_score"], 80.0)
        self.assertEqual(result["weight_coverage"], 1.0)
        self.assertEqual(result["band"], "Good")
        self.assertFalse(result["indicative_only"])

    def test_weights_applied(self):
        scores = {"api_design": 100, "architecture": 0, "security": 50, "scalability": 60,
                  "interoperability": 70, "testing": 80, "documentation": 90}
        expected = round((100 * 20 + 0 * 20 + 50 * 20 + 60 * 15 + 70 * 10 + 80 * 10 + 90 * 5) / 100, 1)
        self.assertEqual(calculate(card(scores))["overall_score"], expected)

    def test_insufficient_evidence_is_excluded_not_zero(self):
        result = calculate(card({"api_design": 90, "security": 70}))  # 40 % of weight
        self.assertEqual(result["overall_score"], 80.0)  # (90*20 + 70*20) / 40, not divided by 100
        self.assertEqual(len(result["not_evaluated"]), 5)
        self.assertTrue(all(d["score"] is None for d in result["not_evaluated"]))
        self.assertTrue(result["indicative_only"])
        self.assertEqual(result["confidence"], "low")

    def test_score_ignored_when_coverage_insufficient(self):
        data = card({"api_design": 60})
        data["dimensions"][2].update(evidence_coverage="insufficient", score=95)  # security
        result = calculate(data)
        self.assertEqual(result["overall_score"], 60.0)
        self.assertTrue(any("score ignored" in w for w in result["warnings"]))
        self.assertTrue(any("Security was not evaluated" in w for w in result["warnings"]))

    def test_no_evidence_at_all(self):
        result = calculate(card({}))
        self.assertIsNone(result["overall_score"])
        self.assertIsNone(result["band"])

    def test_partial_evidence_caps_confidence(self):
        result = calculate(card({d: 85 for d in ALL_IDS}, coverage="partial", confidence="High"))
        self.assertEqual(result["confidence"], "medium")

    def test_not_applicable_dimension_excluded(self):
        data = card({d: 70 for d in ALL_IDS})
        data["dimensions"][3].update(applicable=False, score=10)
        result = calculate(data)
        self.assertEqual(result["overall_score"], 70.0)
        self.assertEqual(result["not_evaluated"][0]["status"], "Not applicable")

    def test_bands(self):
        self.assertEqual(band_for(90), "Excellent")
        self.assertEqual(band_for(89.9), "Good")
        self.assertEqual(band_for(75), "Good")
        self.assertEqual(band_for(60), "Needs improvement")
        self.assertEqual(band_for(59.9), "High technical risk")
        self.assertEqual(band_for(40), "High technical risk")
        self.assertEqual(band_for(39.9), "Critical improvement required")
        self.assertEqual(band_for(0), "Critical improvement required")

    def test_critical_security_alert_regardless_of_score(self):
        findings = [{"id": "SEC-001", "severity": "Critical", "status": "Confirmed", "category": "Authorization"}]
        result = calculate(card({d: 95 for d in ALL_IDS}, findings=findings))
        self.assertEqual(result["band"], "Excellent")
        self.assertTrue(result["critical_security_alert"])
        self.assertEqual(result["critical_findings"][0]["id"], "SEC-001")

    def test_resolved_or_non_security_critical_does_not_alert(self):
        findings = [{"id": "SEC-002", "severity": "Critical", "status": "Resolved", "category": "Security"},
                    {"id": "SCL-001", "severity": "Critical", "status": "Confirmed", "category": "Resilience"}]
        result = calculate(card({"api_design": 80}, findings=findings))
        self.assertFalse(result["critical_security_alert"])
        self.assertEqual(result["open_findings_by_severity"]["Critical"], 1)

    def test_custom_weight_ignored_with_warning(self):
        data = card({d: 50 for d in ALL_IDS})
        data["dimensions"][0]["weight"] = 90
        result = calculate(data)
        self.assertEqual(result["overall_score"], 50.0)
        self.assertTrue(any("custom weight" in w for w in result["warnings"]))

    def test_invalid_inputs_rejected(self):
        bad_inputs = [
            {"dimensions": "x"},
            {"dimensions": [{"id": "unknown", "evidence_coverage": "sufficient", "score": 1}]},
            {"dimensions": [{"id": "security", "evidence_coverage": "sufficient", "score": 101, "confidence": "High"}]},
            {"dimensions": [{"id": "security", "evidence_coverage": "sufficient", "score": True, "confidence": "High"}]},
            {"dimensions": [{"id": "security", "evidence_coverage": "lots", "score": 50}]},
            {"dimensions": [{"id": "security", "evidence_coverage": "sufficient", "score": 50, "confidence": "High"},
                            {"id": "security", "evidence_coverage": "sufficient", "score": 50, "confidence": "High"}]},
            {"dimensions": [], "findings": [{"id": "X", "severity": "Severe"}]},
        ]
        for data in bad_inputs:
            with self.assertRaises(ScriptError, msg=str(data)):
                calculate(data)


class ScoreCliTest(unittest.TestCase):
    def test_template_asset(self):
        code, result = run_json("calculate_score.py", str(SKILL_DIR / "assets" / "quality-scorecard.json"))
        self.assertEqual(code, 0)
        self.assertEqual(result["overall_score"], 64.4)  # 5470 / 85
        self.assertEqual(result["weight_coverage"], 0.85)

    def test_incomplete_fixture_with_fail_on_critical(self):
        proc = run_script("calculate_score.py", str(FIXTURES / "scorecard-incomplete.json"), "--fail-on-critical")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("CRITICAL SECURITY ALERT", proc.stdout)
        self.assertIn("indicative only", proc.stdout)

    def test_invalid_input_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(run_script("calculate_score.py", str(path)).returncode, 2)


class ReportGenerationTest(unittest.TestCase):
    def test_report_has_15_sections_in_order(self):
        proc = run_script("generate_report.py", str(SKILL_DIR / "assets" / "quality-scorecard.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        headings = [line for line in proc.stdout.splitlines() if line.startswith("## ")]
        self.assertEqual(len(headings), 15)
        self.assertTrue(headings[0].startswith("## 1. Executive Summary"))
        self.assertTrue(headings[-1].startswith("## 15. Limitations and Assumptions"))
        self.assertIn("Not evaluated", proc.stdout)
        self.assertIn("not a certification", proc.stdout)

    def test_spanish_headings(self):
        proc = run_script("generate_report.py", str(SKILL_DIR / "assets" / "quality-scorecard.json"), "--lang", "es")
        self.assertIn("## 1. Resumen ejecutivo", proc.stdout)
        self.assertIn("## 15. Limitaciones y supuestos", proc.stdout)

    def test_critical_alert_first_and_secrets_redacted(self):
        proc = run_script("generate_report.py", str(FIXTURES / "scorecard-incomplete.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = proc.stdout.split("## 2.")[0]
        self.assertIn("Critical security alert", summary)
        self.assertNotIn("SuperSecret123", proc.stdout)
        self.assertNotIn("c2lnbmF0dXJlc2lnbmF0dXJl", proc.stdout)
        self.assertIn("password=****", proc.stdout)
        self.assertIn("SEC-002", proc.stdout)  # resolved findings still listed, but not alerted
        self.assertIn("_Not assessed", proc.stdout)  # empty sections say so instead of inventing content

    def test_output_file_not_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.md"
            src = str(SKILL_DIR / "assets" / "quality-scorecard.json")
            self.assertEqual(run_script("generate_report.py", src, "--output", str(out)).returncode, 0)
            self.assertEqual(run_script("generate_report.py", src, "--output", str(out)).returncode, 2)
            self.assertEqual(run_script("generate_report.py", src, "--output", str(out), "--force").returncode, 0)


if __name__ == "__main__":
    unittest.main()
