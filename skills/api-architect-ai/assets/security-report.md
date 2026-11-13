# API Security Review

> **System:** <name> · **Scope:** <repos, contracts, environments> · **Date:** <YYYY-MM-DD>
> **Method:** static review of code/config/contract <and/or authorized non-destructive testing in
> <environment>> · **Not a penetration test or certification.**

<!-- Never include secrets. Redact tokens/keys (e.g. sk_live_****). Label Verified / Inferred. -->

## 1. Summary

> ⚠️ Unresolved critical findings: <IDs or "none identified in the reviewed scope">

| Severity | Count |
|---|---:|
| Critical | |
| High | |
| Medium | |
| Low | |
| Informational | |

Key message (2–4 lines, no "secure" claims):

## 2. Scope, Evidence and Limitations

| Item | Location | Reviewed |
|---|---|---|

Not reviewed: <…>

## 3. Authentication Model

| Consumer type | Mechanism | Token / credential validation | Evidence | Assessment |
|---|---|---|---|---|

JWT validation checklist (signature, pinned algorithms, `iss`, `aud`, `exp`/`nbf`, `typ`, key rotation):

| Control | Status (Verified present / Verified missing / Not located) | Evidence |
|---|---|---|

## 4. Authorization Model

| Level | Mechanism | Evidence | Gaps |
|---|---|---|---|
| Object (BOLA) | | | |
| Property (mass assignment / exposure) | | | |
| Function (admin / privileged) | | | |
| Tenant isolation | | | |

## 5. OWASP API Security Top 10 (2023) Coverage

| ID | Risk | Result (Finding IDs / No issue found in scope / Not assessed) | Notes |
|---|---|---|---|
| API1 | Broken Object Level Authorization | | |
| API2 | Broken Authentication | | |
| API3 | Broken Object Property Level Authorization | | |
| API4 | Unrestricted Resource Consumption | | |
| API5 | Broken Function Level Authorization | | |
| API6 | Unrestricted Access to Sensitive Business Flows | | |
| API7 | Server-Side Request Forgery | | |
| API8 | Security Misconfiguration | | |
| API9 | Improper Inventory Management | | |
| API10 | Unsafe Consumption of APIs | | |

## 6. Other Controls

CORS · TLS · rate limiting/quotas · input validation · secrets management · audit logging · token
expiry/rotation · webhook signatures · replay protection · error handling.

## 7. Findings

<!-- Full structured format per finding: -->

```text
Finding ID:
Category:
Title:
Severity:
Confidence:
Location:
Evidence:
Technical impact:
Business impact:
Recommended solution:
Alternative solutions:
Estimated effort:
Verification method:
Status:
```

## 8. Remediation Plan

| Priority | Finding | Action | Effort | Verification | Owner role |
|---|---|---|---|---|---|

## 9. Security Regression Tests

| Test ID | Finding | Scenario | Expected result | Environment |
|---|---|---|---|---|

## 10. Assumptions and Remaining Risks
