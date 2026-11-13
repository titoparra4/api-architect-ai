# API Quality Scorecard

An explainable, evidence-weighted indicator. **Advisory only — not a certification or proof of
production readiness.**

## Contents
1. Dimensions and weights
2. Scoring procedure
3. Evidence coverage and confidence
4. Rubrics per dimension
5. Critical-issue override
6. Script usage

---

## 1. Dimensions and weights

| Dimension | ID | Weight |
|---|---|---:|
| API Design & REST Quality | `api_design` | 20 |
| Architecture & Maintainability | `architecture` | 20 |
| Security | `security` | 20 |
| Scalability & Resilience | `scalability` | 15 |
| Interoperability & Compatibility | `interoperability` | 10 |
| Testing & Automation | `testing` | 10 |
| Documentation & Governance | `documentation` | 5 |

## 2. Scoring procedure

1. For each dimension decide `evidence_coverage`: `sufficient`, `partial` or `insufficient`.
2. Score 0–100 only dimensions with `sufficient` or `partial` coverage: start from the rubric band
   that matches the evidence, then deduct for findings (see §4).
3. Dimensions with `insufficient` evidence or not applicable → `score: null`, reported as
   **Not evaluated**. **Never assign 0 for lack of evidence.**
4. Overall = Σ(score × weight) / Σ(weight) over evaluated dimensions (normalized weights).
5. Report the evaluated weight coverage (Σ evaluated weights / 100). Below 50 % the overall score is
   **indicative only** and the report must say so.
6. Bands: 90–100 Excellent · 75–89 Good · 60–74 Needs improvement · 40–59 High technical risk ·
   0–39 Critical improvement required.

## 3. Evidence coverage and confidence

| Coverage | Meaning |
|---|---|
| sufficient | Main sources for the dimension reviewed (e.g. security: auth config, authorization code paths for representative operations, contract security declarations). |
| partial | Some sources reviewed, important ones missing (e.g. contract only, no code). Score allowed; confidence ≤ medium. |
| insufficient | Not enough to score. |

Confidence per dimension: `high` (direct, consistent evidence), `medium` (partial or sampled), `low`
(mostly inferred). Overall confidence = lowest confidence among evaluated dimensions, downgraded to
`low` when evaluated weight coverage < 50 %.

## 4. Rubrics per dimension

Pick a starting band from the evidence, then deduct for findings in that dimension: Critical −25,
High −15, Medium −7, Low −3 (floor 0). Do not double-count one root cause across dimensions: assign it
to its primary dimension and reference it elsewhere. State the starting band and the deductions so the
score is explainable.

**API Design & REST Quality**
- 90+: consistent naming, correct method/status semantics, RFC 9457 errors everywhere, bounded
  pagination, separate request/response models, idempotency where needed.
- ~75: minor inconsistencies (a few status codes, naming drift).
- ~60: mixed error formats, some RPC-style endpoints, unbounded collections.
- ~40: entities exposed directly, verbs everywhere, no pagination.
- <40: no coherent design; unsafe GETs; ad hoc payloads.

**Architecture & Maintainability**
- 90+: clear layers/modules aligned with capabilities, centralized cross-cutting concerns, low
  coupling, testable.
- 60–74: business logic in controllers, scattered auth checks, some circular dependencies.
- <40: god classes, shared-database integration across services, untestable.

**Security**
- 90+: standards-based authN with complete token validation; object/property/function-level authZ
  enforced and tested; rate limits; managed secrets; audit logging.
- ~75: minor hardening gaps.
- ~60: a High finding or missing controls on non-critical paths.
- <60: any confirmed Critical, or systemic BOLA / missing token validation.

**Scalability & Resilience**
- 90+: stateless; timeouts, bounded retries and circuit breakers on dependencies; caching strategy;
  bounded queries; observability with SLOs; load-test evidence.
- 60–74: missing timeouts on some dependencies, no load-test evidence, suspected N+1.
- <40: stateful instances, unbounded queries, no timeouts.
- Without metrics: at most 80, confidence at most medium.

**Interoperability & Compatibility**
- 90+: standards-compliant HTTP, consistent formats (RFC 3339, UTF-8), enforced versioning and
  compatibility policy, no breaking changes without a new major.
- <60: undocumented breaking changes, inconsistent formats.

**Testing & Automation**
- 90+: automated functional, contract, security and regression tests in CI with meaningful
  assertions; consumer contracts.
- 60–74: mostly happy-path or status-only assertions.
- <40: no automated API tests.

**Documentation & Governance**
- 90+: complete, validated contract matching the implementation; changelog; deprecation policy;
  inventory; lint in CI.
- <60: contract missing or significantly out of sync.

## 5. Critical-issue override

Unresolved **Critical security findings** (status Confirmed, Suspected or Requires validation) are
shown at the top of the executive summary and the scorecard **regardless of the overall score**, with
the statement: "The overall score does not offset unresolved critical security issues."
`scripts/calculate_score.py` sets `critical_security_alert: true` in this case.

## 6. Script usage

```bash
python3 scripts/calculate_score.py assessment.json                     # text summary
python3 scripts/calculate_score.py assessment.json --format json
python3 scripts/calculate_score.py assessment.json --fail-on-critical  # exit 1 when alert
```

Input format: `assets/quality-scorecard.json`.
