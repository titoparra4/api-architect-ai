#!/usr/bin/env python3
"""Render an API Architecture Assessment (Markdown) from an assessment JSON file.

Usage:
    generate_report.py ASSESSMENT [--output FILE] [--lang en|es]

Inputs:
    ASSESSMENT  JSON (or YAML) shaped like assets/quality-scorecard.json: assessment metadata,
                dimensions, findings, recommendations, adrs, roadmap, acceptance_criteria,
                limitations, assumptions, not_executed.
Options:
    --output    Write the report to FILE instead of stdout (refuses to overwrite unless --force).
    --force     Allow overwriting --output.
    --lang      Heading language: en (default) or es.

Behavior:
    * Produces the 15-section structure of assets/architecture-report.md.
    * The scorecard is computed with calculate_score.py rules (not-evaluated dimensions excluded).
    * Unresolved critical security findings are shown at the top of the Executive Summary.
    * Sections without data say so explicitly instead of inventing content.
    * Secret-like strings (tokens, keys, passwords, connection strings) are redacted.

Dependencies: Python 3.9+ (PyYAML only for YAML input).
Exit codes: 0 report written · 2 invalid input or output exists · 3 missing dependency
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EXIT_INPUT, EXIT_OK, ScriptError, check_runtime, fail, load_document  # noqa: E402
from calculate_score import calculate  # noqa: E402

SECRET_PATTERNS = [
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "<redacted-jwt>"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "<redacted-aws-key>"),
    (re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]{8,}\b"), r"\1_\2_****"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<redacted-github-token>"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "<redacted-slack-token>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted-private-key>"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 <redacted>"),
    (re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@"), r"\1****@"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|client[_-]?secret|access[_-]?token)(\s*[:=]\s*)(['\"]?)[^\s'\",;]{4,}\3"),
     r"\1\2\3****\3"),
]

HEADINGS = {
    "en": ["Executive Summary", "Scope and Evidence", "API Architecture Overview", "API Quality Scorecard",
           "Security Assessment", "Scalability & Performance Assessment", "Interoperability Assessment",
           "API Contract Review", "Testing Strategy", "Findings and Risks", "Prioritized Recommendations",
           "Architecture Decision Records", "Implementation Roadmap", "Verification & Acceptance Criteria",
           "Limitations and Assumptions"],
    "es": ["Resumen ejecutivo", "Alcance y evidencias", "Visión general de la arquitectura de la API",
           "Scorecard de calidad de la API", "Evaluación de seguridad", "Evaluación de escalabilidad y rendimiento",
           "Evaluación de interoperabilidad", "Revisión del contrato de la API", "Estrategia de pruebas",
           "Hallazgos y riesgos", "Recomendaciones priorizadas", "Registros de decisiones de arquitectura (ADR)",
           "Hoja de ruta de implementación", "Verificación y criterios de aceptación", "Limitaciones y supuestos"],
}
TEXT = {
    "en": {
        "title": "API Architecture Assessment", "none": "_Not assessed — no evidence provided for this section._",
        "alert": "**Critical security alert:** unresolved critical finding(s) {ids}. The overall score does not offset unresolved critical security issues.",
        "overall": "**Overall score:** {score}/100 — {band} · evaluated weight {cov}% · confidence {conf}",
        "indicative": " · _indicative only (less than 50% of weight evaluated)_",
        "no_score": "**Overall score:** not calculated (insufficient evidence).",
        "disclaimer": "_Advisory quality indicator; not a certification or proof of production readiness. Not-evaluated dimensions are excluded from the weighted average, not scored as 0._",
        "not_evaluated": "Not evaluated", "system": "System", "date": "Date", "scope": "Scope",
        "limitations": "Limitations", "assumptions": "Assumptions", "not_executed": "Not executed",
        "open": "Open findings by severity",
    },
    "es": {
        "title": "Evaluación de arquitectura de API", "none": "_No evaluado — no se aportó evidencia para esta sección._",
        "alert": "**Alerta crítica de seguridad:** hallazgo(s) crítico(s) sin resolver {ids}. La puntuación global no compensa problemas críticos de seguridad sin resolver.",
        "overall": "**Puntuación global:** {score}/100 — {band} · peso evaluado {cov}% · confianza {conf}",
        "indicative": " · _solo indicativa (menos del 50% del peso evaluado)_",
        "no_score": "**Puntuación global:** no calculada (evidencia insuficiente).",
        "disclaimer": "_Indicador de calidad orientativo; no es una certificación ni prueba de preparación para producción. Las dimensiones no evaluadas se excluyen de la media ponderada, no puntúan 0._",
        "not_evaluated": "No evaluada", "system": "Sistema", "date": "Fecha", "scope": "Alcance",
        "limitations": "Limitaciones", "assumptions": "Supuestos", "not_executed": "No ejecutado",
        "open": "Hallazgos abiertos por severidad",
    },
}
BAND_ES = {"Excellent": "Excelente", "Good": "Bueno", "Needs improvement": "Necesita mejoras",
           "High technical risk": "Alto riesgo técnico", "Critical improvement required": "Mejora crítica requerida"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
FINDING_FIELDS = [
    ("id", "Finding ID"), ("category", "Category"), ("title", "Title"), ("severity", "Severity"),
    ("confidence", "Confidence"), ("location", "Location"), ("evidence", "Evidence"),
    ("technical_impact", "Technical impact"), ("business_impact", "Business impact"),
    ("recommended_solution", "Recommended solution"), ("alternative_solutions", "Alternative solutions"),
    ("effort", "Estimated effort"), ("verification_method", "Verification method"), ("status", "Status"),
]


def redact(value: Any) -> str:
    text = "" if value is None else str(value)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def cell(value: Any) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return redact(value).replace("|", "\\|").replace("\n", " ")


def table(headers: List[str], rows: List[List[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(out)


def text_or_none(value: Any, t: Dict[str, str]) -> str:
    return redact(value) if value else t["none"]


def render(data: Dict[str, Any], lang: str) -> str:
    t, h = TEXT[lang], HEADINGS[lang]
    score = calculate(data)
    if lang == "es":
        score["band"] = BAND_ES.get(score["band"], score["band"])
        for d in score["dimensions"]:
            d["band"] = BAND_ES.get(d["band"], d["band"])
    meta = data.get("assessment") or {}
    findings = sorted([f for f in data.get("findings") or [] if isinstance(f, dict)],
                      key=lambda f: (SEVERITY_RANK.get(str(f.get("severity", "")).lower(), 9), str(f.get("id"))))
    out: List[str] = ["# %s" % redact(meta.get("title") or t["title"]), ""]
    out.append("> %s: %s · %s: %s · %s: %s" % (t["system"], cell(meta.get("system") or "-"), t["date"],
                                                cell(meta.get("date") or "-"), t["scope"], cell(meta.get("scope") or "-")))
    out.append("")

    def section(n: int, body: str) -> None:
        out.extend(["## %d. %s" % (n, h[n - 1]), "", body.rstrip(), ""])

    # 1 Executive summary
    parts = []
    if score["critical_security_alert"]:
        parts.append("> ⚠️ " + t["alert"].format(ids=", ".join(str(c["id"]) for c in score["critical_findings"])))
        parts.append("")
    if score["overall_score"] is None:
        parts.append(t["no_score"])
    else:
        parts.append(t["overall"].format(score=score["overall_score"], band=score["band"],
                                         cov=round(score["weight_coverage"] * 100), conf=score["confidence"])
                     + (t["indicative"] if score["indicative_only"] else ""))
    parts.append("")
    parts.append("%s: %s" % (t["open"], ", ".join("%s %d" % kv for kv in score["open_findings_by_severity"].items())))
    if meta.get("executive_summary"):
        parts += ["", redact(meta["executive_summary"])]
    section(1, "\n".join(parts))

    # 2 Scope and evidence
    evidence = meta.get("evidence") or []
    section(2, table(["Evidence", "Type", "Location", "Depth"],
                     [[e.get("item"), e.get("type"), e.get("location"), e.get("depth")] for e in evidence if isinstance(e, dict)])
            if evidence else t["none"])

    section(3, text_or_none(meta.get("architecture_overview"), t))

    # 4 Scorecard
    rows = [[d["name"], d["weight"], d["score"], d["band"], d["evidence_coverage"], d["confidence"]] for d in score["dimensions"]]
    rows += [[d["name"], d["weight"], "n/a", t["not_evaluated"], d["evidence_coverage"], d["confidence"]] for d in score["not_evaluated"]]
    body = table(["Dimension", "Weight", "Score", "Band", "Evidence", "Confidence"], rows)
    body += "\n\n" + t["disclaimer"]
    if score["warnings"]:
        body += "\n\n" + "\n".join("- %s" % redact(w) for w in score["warnings"])
    section(4, body)

    section(5, text_or_none(meta.get("security_assessment"), t))
    section(6, text_or_none(meta.get("scalability_assessment"), t))
    section(7, text_or_none(meta.get("interoperability_assessment"), t))
    section(8, text_or_none(meta.get("contract_review"), t))
    section(9, text_or_none(meta.get("testing_strategy"), t))

    # 10 Findings
    if findings:
        body = table(["ID", "Title", "Severity", "Confidence", "Status", "Location"],
                     [[f.get("id"), f.get("title"), f.get("severity"), f.get("confidence"), f.get("status"), f.get("location")]
                      for f in findings])
        for f in findings:
            body += "\n\n### %s — %s\n\n```text\n" % (cell(f.get("id")), cell(f.get("title")))
            body += "\n".join("%-22s %s" % (label + ":", redact(f.get(key, "")).replace("\n", " ")) for key, label in FINDING_FIELDS)
            body += "\n```"
        section(10, body)
    else:
        section(10, t["none"])

    recs = data.get("recommendations") or []
    section(11, table(["ID", "Recommendation", "Findings", "Priority", "Effort", "Acceptance criteria", "Validation"],
                      [[r.get("id"), r.get("title"), r.get("findings"), r.get("priority"), r.get("effort"),
                        r.get("acceptance_criteria"), r.get("validation")] for r in recs if isinstance(r, dict)])
            if recs else t["none"])
    adrs = data.get("adrs") or []
    section(12, table(["ADR", "Title", "Status"], [[a.get("id"), a.get("title"), a.get("status")] for a in adrs if isinstance(a, dict)])
            if adrs else t["none"])
    roadmap = data.get("roadmap") or []
    section(13, table(["Horizon", "Items", "Exit criteria"],
                      [[r.get("horizon"), r.get("items"), r.get("exit_criteria")] for r in roadmap if isinstance(r, dict)])
            if roadmap else t["none"])
    criteria = data.get("acceptance_criteria") or []
    section(14, table(["Criterion", "Measure", "Method", "Target"],
                      [[c.get("criterion"), c.get("measure"), c.get("method"), c.get("target")] for c in criteria if isinstance(c, dict)])
            if criteria else t["none"])

    parts = []
    for key in ("limitations", "assumptions", "not_executed"):
        items = data.get(key) or []
        if items:
            parts.append("**%s**\n\n%s" % (t[key], "\n".join("- %s" % redact(i) for i in items)))
    section(15, "\n\n".join(parts) if parts else t["none"])
    return "\n".join(out).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Markdown API architecture assessment from JSON.")
    parser.add_argument("assessment", help="Assessment JSON/YAML (see assets/quality-scorecard.json)")
    parser.add_argument("--output", help="Output Markdown file (default: stdout)")
    parser.add_argument("--force", action="store_true", help="Overwrite --output if it exists")
    parser.add_argument("--lang", choices=["en", "es"], default=None, help="Heading language (default: assessment.language or en)")
    args = parser.parse_args(argv)
    try:
        check_runtime()
        data = load_document(args.assessment)
        if not isinstance(data, dict):
            raise ScriptError("Assessment must be a JSON object.", EXIT_INPUT)
        lang = args.lang or str((data.get("assessment") or {}).get("language") or "en")
        if lang not in HEADINGS:
            lang = "en"
        report = render(data, lang)
        if args.output:
            target = Path(args.output)
            if target.exists() and not args.force:
                raise ScriptError("Output file exists: %s (use --force to overwrite)." % args.output, EXIT_INPUT)
            target.write_text(report, encoding="utf-8")
            sys.stderr.write("Report written to %s\n" % args.output)
        else:
            sys.stdout.write(report)
    except ScriptError as exc:
        return fail(str(exc), exc.code)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
