#!/usr/bin/env python3
"""Calculate the API Architect AI quality scorecard.

Usage:
    calculate_score.py SCORECARD [--format text|json] [--fail-on-critical]

Inputs:
    SCORECARD   JSON (or YAML) file shaped like assets/quality-scorecard.json.
Options:
    --format            Output format (default: text).
    --fail-on-critical  Exit 1 when unresolved Critical security findings exist.

Rules implemented:
    * Fixed weights: api_design 20, architecture 20, security 20, scalability 15,
      interoperability 10, testing 10, documentation 5.
    * A dimension is evaluated only if applicable, evidence_coverage is 'sufficient' or 'partial'
      and score is a number 0-100. Others are 'Not evaluated' and EXCLUDED (never scored as 0).
    * Overall = sum(score * weight) / sum(weight) over evaluated dimensions.
    * Evaluated weight coverage < 50% marks the overall score as indicative only, confidence low.
    * Unresolved Critical findings in a security category (or ID prefix SEC) raise
      critical_security_alert regardless of the score.

Output:
    JSON: {"overall_score", "band", "confidence", "weight_coverage", "indicative_only",
    "dimensions": [...], "not_evaluated": [...], "critical_security_alert", "critical_findings",
    "warnings": [...]}

Dependencies: Python 3.9+ (PyYAML only for YAML input).
Exit codes: 0 ok · 1 critical alert with --fail-on-critical · 2 invalid input · 3 missing dependency
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EXIT_FAIL, EXIT_INPUT, EXIT_OK, ScriptError, check_runtime, emit, fail, load_document  # noqa: E402

DIMENSIONS = [
    ("api_design", "API Design & REST Quality", 20),
    ("architecture", "Architecture & Maintainability", 20),
    ("security", "Security", 20),
    ("scalability", "Scalability & Resilience", 15),
    ("interoperability", "Interoperability & Compatibility", 10),
    ("testing", "Testing & Automation", 10),
    ("documentation", "Documentation & Governance", 5),
]
DIMENSION_INDEX = {d[0]: d for d in DIMENSIONS}
COVERAGE_VALUES = {"sufficient", "partial", "insufficient"}
CONFIDENCE_ORDER = ["low", "medium", "high"]
SEVERITIES = {"critical", "high", "medium", "low", "informational"}
RESOLVED_STATUSES = {"resolved", "fixed", "closed", "false positive", "accepted risk"}
BANDS = [
    (90, "Excellent"),
    (75, "Good"),
    (60, "Needs improvement"),
    (40, "High technical risk"),
    (0, "Critical improvement required"),
]


def band_for(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for floor, name in BANDS:
        if score >= floor:
            return name
    return BANDS[-1][1]


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_security_finding(finding: Dict[str, Any]) -> bool:
    fid = str(finding.get("id", "")).upper()
    category = str(finding.get("category", "")).lower()
    return fid.startswith("SEC") or "security" in category or "owasp" in category \
        or "authoriz" in category or "authentic" in category


def calculate(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("dimensions"), list):
        raise ScriptError("Input must be an object with a 'dimensions' array.", EXIT_INPUT)

    warnings: List[str] = []
    seen = set()
    evaluated, not_evaluated = [], []
    for raw in data["dimensions"]:
        if not isinstance(raw, dict) or raw.get("id") not in DIMENSION_INDEX:
            raise ScriptError("Unknown or missing dimension id: %r. Valid ids: %s"
                              % (raw.get("id") if isinstance(raw, dict) else raw, ", ".join(DIMENSION_INDEX)), EXIT_INPUT)
        dim_id = raw["id"]
        if dim_id in seen:
            raise ScriptError("Duplicate dimension id: %s" % dim_id, EXIT_INPUT)
        seen.add(dim_id)
        _, name, weight = DIMENSION_INDEX[dim_id]
        if "weight" in raw and raw["weight"] != weight:
            warnings.append("Dimension %s: custom weight %r ignored; canonical weight %d used." % (dim_id, raw["weight"], weight))
        coverage = str(raw.get("evidence_coverage", "")).lower()
        if coverage not in COVERAGE_VALUES:
            raise ScriptError("Dimension %s: evidence_coverage must be one of %s." % (dim_id, sorted(COVERAGE_VALUES)), EXIT_INPUT)
        confidence = str(raw.get("confidence", "low")).lower()
        if confidence not in CONFIDENCE_ORDER:
            raise ScriptError("Dimension %s: confidence must be High, Medium or Low." % dim_id, EXIT_INPUT)
        applicable = raw.get("applicable", True) is not False
        score = raw.get("score")
        entry = {"id": dim_id, "name": name, "weight": weight, "evidence_coverage": coverage,
                 "confidence": confidence, "score": score}

        if not applicable:
            entry.update(score=None, status="Not applicable")
            not_evaluated.append(entry)
            continue
        if coverage == "insufficient" or score is None:
            if score is not None:
                warnings.append("Dimension %s: score ignored because evidence is insufficient." % dim_id)
            entry.update(score=None, status="Not evaluated")
            not_evaluated.append(entry)
            continue
        if not is_number(score) or not 0 <= score <= 100:
            raise ScriptError("Dimension %s: score must be a number between 0 and 100." % dim_id, EXIT_INPUT)
        if coverage == "partial" and confidence == "high":
            warnings.append("Dimension %s: partial evidence capped confidence at medium." % dim_id)
            confidence = "medium"
            entry["confidence"] = confidence
        entry.update(status="Evaluated", band=band_for(score))
        evaluated.append(entry)

    for dim_id, name, weight in DIMENSIONS:
        if dim_id not in seen:
            not_evaluated.append({"id": dim_id, "name": name, "weight": weight, "evidence_coverage": "insufficient",
                                  "confidence": "low", "score": None, "status": "Not evaluated (missing from input)"})

    total_weight = sum(d["weight"] for d in evaluated)
    weight_coverage = total_weight / 100.0
    if total_weight:
        overall = round(sum(d["score"] * d["weight"] for d in evaluated) / total_weight, 1)
        for d in evaluated:
            d["normalized_weight"] = round(d["weight"] / total_weight, 4)
        confidence = min((d["confidence"] for d in evaluated), key=CONFIDENCE_ORDER.index)
    else:
        overall, confidence = None, "low"
        warnings.append("No dimension has enough evidence; overall score not calculated.")
    indicative = weight_coverage < 0.5
    if indicative and overall is not None:
        confidence = "low"
        warnings.append("Evaluated dimensions cover only %d%% of total weight; overall score is indicative only."
                        % round(weight_coverage * 100))
    if any(d["id"] == "security" for d in not_evaluated):
        warnings.append("Security was not evaluated; the score says nothing about security posture.")

    findings = data.get("findings") or []
    if not isinstance(findings, list):
        raise ScriptError("'findings' must be an array.", EXIT_INPUT)
    critical = []
    counts = {s: 0 for s in ["Critical", "High", "Medium", "Low", "Informational"]}
    for f in findings:
        if not isinstance(f, dict):
            raise ScriptError("Each finding must be an object.", EXIT_INPUT)
        severity = str(f.get("severity", "")).lower()
        if severity not in SEVERITIES:
            raise ScriptError("Finding %s: invalid severity %r." % (f.get("id"), f.get("severity")), EXIT_INPUT)
        status = str(f.get("status", "")).lower()
        if status in RESOLVED_STATUSES:
            continue
        counts[severity.capitalize()] += 1
        if severity == "critical" and is_security_finding(f):
            critical.append({"id": f.get("id"), "title": f.get("title"), "status": f.get("status")})

    return {
        "overall_score": overall,
        "band": band_for(overall),
        "confidence": confidence,
        "weight_coverage": round(weight_coverage, 2),
        "indicative_only": indicative,
        "dimensions": evaluated,
        "not_evaluated": not_evaluated,
        "open_findings_by_severity": counts,
        "critical_security_alert": bool(critical),
        "critical_findings": critical,
        "warnings": warnings,
        "disclaimer": "Advisory quality indicator; not a certification or proof of production readiness.",
    }


def render_text(result: Dict[str, Any]) -> str:
    lines = []
    if result["critical_security_alert"]:
        ids = ", ".join(str(c["id"]) for c in result["critical_findings"])
        lines.append("!! CRITICAL SECURITY ALERT: unresolved critical finding(s) %s. "
                     "The overall score does not offset them." % ids)
    if result["overall_score"] is None:
        lines.append("Overall score: not calculated (insufficient evidence)")
    else:
        lines.append("Overall score: %.1f/100 — %s%s" % (result["overall_score"], result["band"],
                                                       " (indicative only)" if result["indicative_only"] else ""))
    lines.append("Confidence: %s · Evaluated weight coverage: %d%%" % (result["confidence"], round(result["weight_coverage"] * 100)))
    lines.append("")
    lines.append("%-34s %6s %7s  %-30s %-12s %s" % ("Dimension", "Weight", "Score", "Band", "Evidence", "Confidence"))
    for d in result["dimensions"]:
        lines.append("%-34s %6d %7.1f  %-30s %-12s %s" % (d["name"], d["weight"], d["score"], d["band"],
                                                         d["evidence_coverage"], d["confidence"]))
    for d in result["not_evaluated"]:
        lines.append("%-34s %6d %7s  %-30s %-12s %s" % (d["name"], d["weight"], "n/a", d["status"],
                                                       d["evidence_coverage"], d["confidence"]))
    counts = result["open_findings_by_severity"]
    lines.append("")
    lines.append("Open findings: " + ", ".join("%s=%d" % kv for kv in counts.items()))
    for w in result["warnings"]:
        lines.append("Warning: %s" % w)
    lines.append(result["disclaimer"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate the 7-dimension API quality scorecard.")
    parser.add_argument("scorecard", help="Scorecard JSON/YAML (see assets/quality-scorecard.json)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fail-on-critical", action="store_true",
                        help="Exit 1 when unresolved critical security findings exist")
    args = parser.parse_args(argv)
    try:
        check_runtime()
        result = calculate(load_document(args.scorecard))
    except ScriptError as exc:
        return fail(str(exc), exc.code, args.format)
    emit(result, render_text(result), args.format)
    if args.fail_on_critical and result["critical_security_alert"]:
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
