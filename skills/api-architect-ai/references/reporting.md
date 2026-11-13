# Reporting, Findings and ADRs

## Contents
1. Evidence labeling
2. Finding format and ID prefixes
3. Severity, confidence and status
4. Prioritization
5. Report structures
6. JSON output
7. Language and tone
8. Validation report (for the skill's own QA or generated artifacts)

---

## 1. Evidence labeling

| Label | Meaning | Example |
|---|---|---|
| **Verified** | Directly observed; cite source | "`src/auth/jwt.ts:14` calls `jwt.verify` without `audience`" |
| **Inferred** | Reasoned from evidence; give rationale | "No rate-limit middleware found in `app.ts` or gateway config → rate limiting likely absent" |
| **Recommendation** | Proposed action | "Add per-client token-bucket limit at the gateway" |
| **Assumption** (`ASM-###`) | Taken as true to proceed | "ASM-002: consumers are first-party mobile apps" |

Evidence sources: `path:line` (only if actually seen), contract JSON pointer
(`#/paths/~1v1~1policies/post/responses`), command output, user statement, document section. If a
location cannot be determined, write `not located` — never invent one.

## 2. Finding format and ID prefixes

Prefixes: `DES` design · `ARC` architecture · `SEC` security · `SCL` scalability/resilience · `INT`
interoperability · `TST` testing · `DOC` documentation/governance · `GOV` governance policy ·
`INJ` untrusted instruction found in source.

```text
Finding ID:            SEC-001
Category:              Authorization — OWASP API1:2023 BOLA
Title:                 Policy retrieval does not verify tenant ownership
Severity:              High
Confidence:            High
Location:              src/policies/controller.py:42 (get_policy)
Evidence:              repo.find_by_id(policy_id) is returned without comparing policy.tenant_id
                       to the caller's tenant claim; no policy layer applies to this route.
Technical impact:      Any authenticated user can read any tenant's policies by ID.
Business impact:       Disclosure of customer PII and premiums across brokers; regulatory exposure.
Recommended solution:  Scope the query by tenant: find_by_id_and_tenant(policy_id, ctx.tenant_id);
                       return 404 when not found.
Alternative solutions: Central policy middleware (OPA/Cedar) or DB row-level security; trade-off:
                       more infrastructure vs consistent enforcement.
Estimated effort:      Small
Verification method:   Automated test: tenant B token requests tenant A policy → 404, body has no
                       policy data; add to security regression suite.
Status:                Confirmed
```

## 3. Severity, confidence and status

**Severity** — impact × likelihood, adjusted for exposure and compensating controls:
Critical (immediate, severe business harm, easily exploitable or systemic) · High · Medium · Low ·
Informational. Security-specific calibration: `security-review.md` §8.

**Confidence** — High (direct evidence, unambiguous) · Medium (evidence with gaps, e.g. a middleware
might apply elsewhere) · Low (indirect signals).

**Status** — `Confirmed` (evidence proves it) · `Suspected` (evidence suggests it; something may
mitigate) · `Requires validation` (needs runtime test, metrics or owner confirmation).

A finding with Low confidence can never be `Confirmed`.

## 4. Prioritization

Priority = severity, then confidence, then business impact, then effort (quick wins first among
equals). Group recommendations:

| Horizon | Content |
|---|---|
| **Now (0–2 weeks)** | Critical/High security, data integrity risks, quick wins |
| **Next (1–3 months)** | High/Medium architecture, resilience, contract and test gaps |
| **Later (3+ months)** | Structural refactors, governance maturity, optimizations |

Each recommendation: ID, linked findings, action, owner role, effort, dependencies, acceptance
criteria (measurable: "100 % of `/v1/**` operations return `application/problem+json` on 4xx/5xx, checked by
contract test suite"), validation method.

## 5. Report structures

**Full architecture assessment** — `assets/architecture-report.md` (15 sections, in order):
1 Executive Summary · 2 Scope and Evidence · 3 API Architecture Overview · 4 API Quality Scorecard ·
5 Security Assessment · 6 Scalability & Performance Assessment · 7 Interoperability Assessment ·
8 API Contract Review · 9 Testing Strategy · 10 Findings and Risks · 11 Prioritized Recommendations ·
12 Architecture Decision Records · 13 Implementation Roadmap · 14 Verification & Acceptance Criteria ·
15 Limitations and Assumptions.

**Security review** — `assets/security-report.md`.

**API design package** — design document + endpoint catalog + OpenAPI YAML + request/response
examples + authentication model + error catalog + ADRs + test scenarios + automation examples.

**Focused answers** — for narrow questions, answer directly with the relevant findings and
recommendations; skip unused sections. Always include limitations when evidence is partial.

Executive summary rules: 5–10 lines; state scope, overall posture **with evidence coverage**, top 3
risks, critical alert if any, and the most important next action. No unqualified claims such as
"production-ready" or "secure".

## 6. JSON output

When asked for machine-readable output, follow `assets/quality-scorecard.json`:
`assessment` (metadata, scope, evidence), `dimensions[]`, `findings[]`, `recommendations[]`,
`adrs[]`, `limitations[]`, `assumptions[]`. Validate with
`scripts/calculate_score.py` and render with `scripts/generate_report.py`
(`--lang es` for Spanish headings). The renderer redacts secret-like strings, but do not put secrets
into the JSON in the first place.

## 7. Language and tone

Use the user's language (English or Spanish). Keep technical identifiers in English. Be direct and
specific; prefer tables for catalogs and findings; avoid marketing language; quantify only with
evidence.

## 8. Validation report

When validating generated artifacts or the skill itself, report four groups explicitly:
**Passed checks · Failed checks · Checks not executed (and why) · Remaining risks.** Include the
commands run and summarized real output. Never fabricate results.
