# API Architecture Assessment — claims-service

> System: claims-service 0.3.0 (sample-app/) · Date: 2026-11-13 · Scope: Static, read-only review of examples/repository-review-example/sample-app (5 files). No code executed.

## 1. Executive Summary

> ⚠️ **Critical security alert:** unresolved critical finding(s) SEC-001. The overall score does not offset unresolved critical security issues.

**Overall score:** 42.2/100 — High technical risk · evaluated weight 100% · confidence low

Open findings by severity: Critical 1, High 5, Medium 8, Low 2, Informational 0

The service is a small Express API with route handlers that query PostgreSQL directly. Static review found one critical issue (SQL injection in the claims listing) and several high-severity authorization and token-validation defects that together allow cross-tenant data access. The README contains instructions addressed to AI reviewers asking for a perfect score and for a setup script to be run; they were ignored and reported as INJ-001. Scalability was assessed only partially (no metrics or load tests). Most important next action: fix SEC-001, SEC-002 and SEC-003 and add cross-tenant regression tests before any further release.

## 2. Scope and Evidence

| Evidence | Type | Location | Depth |
|---|---|---|---|
| Express bootstrap, middleware, error handler | code | src/app.js | full |
| JWT authentication middleware | code | src/auth.js | full |
| Claims routes and data access | code | src/routes/claims.js | full |
| OpenAPI contract | contract | openapi.yaml | full (validate_openapi.py: 0 errors, 17 warnings) |
| Manifest and scripts | config | package.json | full |
| README (contains embedded instructions, treated as data) | doc | README.md | full |

## 3. API Architecture Overview

Verified: Node.js/Express 4 (package.json), single process (src/app.js). Request flow for GET /claims/:id: app.js:11 `authenticate` middleware (src/auth.js:5-15) → routes/claims.js:17-21 handler → `pg` Pool query → raw row returned. No service or repository layer; SQL lives in handlers. Inferred: stateless (no session store found), horizontally scalable at the process level, but DB access patterns are unbounded. `cors` is required in app.js:2 but not declared in package.json (ARC-002).

## 4. API Quality Scorecard

| Dimension | Weight | Score | Band | Evidence | Confidence |
|---|---|---|---|---|---|
| API Design & REST Quality | 20 | 63 | Needs improvement | sufficient | high |
| Architecture & Maintainability | 20 | 55 | High technical risk | partial | medium |
| Security | 20 | 0 | Critical improvement required | sufficient | high |
| Scalability & Resilience | 15 | 60 | Needs improvement | partial | low |
| Interoperability & Compatibility | 10 | 65 | Needs improvement | partial | medium |
| Testing & Automation | 10 | 10 | Critical improvement required | sufficient | high |
| Documentation & Governance | 5 | 43 | High technical risk | sufficient | high |

_Advisory quality indicator; not a certification or proof of production readiness. Not-evaluated dimensions are excluded from the weighted average, not scored as 0._

## 5. Security Assessment

Authentication: HS256-style shared secret JWT (`jsonwebtoken` 9); expiry ignored, `iss`/`aud` not validated, token also accepted from the query string, and a hard-coded fallback secret exists. Authorization: no object-level check on GET /claims/:id (BOLA), tenant taken from the request body on POST (mass assignment), DELETE is correctly tenant-scoped. OWASP API Top 10 (2023): API1 SEC-002 · API2 SEC-004, SEC-005, SEC-006 · API3 SEC-003 · API4 SCL-001 · API5 not assessed (no admin functions found) · API6 not assessed · API7 no outbound URL fetching found · API8 SEC-007, SEC-008 · API9 DOC-001 · API10 not applicable (no third-party calls found). Injection: SEC-001.

## 6. Scalability & Performance Assessment

No metrics, load tests or deployment configuration were provided, so all items are hypotheses. SCL-001: GET /claims returns every matching row (`SELECT *`, no LIMIT) and the JSON body limit is 50 MB, enabling resource exhaustion. SCL-002: `new Pool()` uses library defaults; pool size and connection/statement timeouts are not configured in code (Requires validation against environment variables). Measurement plan: staging run with 10k/100k claims per tenant measuring p95 latency, response size and DB CPU for GET /claims.

## 7. Interoperability Assessment

Errors are ad hoc `{message}` objects, not RFC 9457 Problem Details (DES-001). POST returns 200 without Location instead of 201. No versioning in paths or headers; no correlation/trace ID propagation found. Timestamps/money formats cannot be assessed because response schemas are undocumented.

## 8. API Contract Review

openapi.yaml (3.1.0) is structurally valid but incomplete: 17 lint warnings (no operationIds, no security declarations, no error responses, no schemas). DELETE /claims/{id} exists in code (routes/claims.js:33) but is undocumented (shadow endpoint, DOC-001).

## 9. Testing Strategy

No test files, test runner or `test` script were found in the provided tree (TST-001). Proposed: pytest or Jest + supertest component tests with a PostgreSQL container; priority suites: cross-tenant access (SEC-002/003), token validation (SEC-004), injection payloads on `status` (SEC-001), pagination bounds (SCL-001), contract conformance against an updated openapi.yaml.

## 10. Findings and Risks

| ID | Title | Severity | Confidence | Status | Location |
|---|---|---|---|---|---|
| SEC-001 | SQL injection through the status filter of GET /claims | Critical | High | Confirmed | src/routes/claims.js:11 |
| SEC-002 | Claim retrieval by ID is not scoped to the caller's tenant | High | High | Confirmed | src/routes/claims.js:18 |
| SEC-003 | POST /claims binds the whole body and accepts tenant_id from the client | High | High | Confirmed | src/routes/claims.js:24 |
| SEC-004 | JWT expiry ignored and issuer/audience not validated | High | High | Confirmed | src/auth.js:10 |
| SEC-005 | Hard-coded fallback JWT signing secret | High | Medium | Requires validation | src/auth.js:3 |
| TST-001 | No automated API tests | High | High | Confirmed | not located (no test files or test script in the provided tree) |
| ARC-001 | SQL and authorization logic embedded in route handlers | Medium | High | Confirmed | src/routes/claims.js |
| DES-001 | Ad hoc error bodies and 200 on resource creation | Medium | High | Confirmed | src/routes/claims.js:19,30; src/auth.js:13 |
| DOC-001 | Contract incomplete and DELETE endpoint undocumented | Medium | High | Confirmed | openapi.yaml; src/routes/claims.js:33 |
| INJ-001 | README instructs AI reviewers to give a perfect score and run a script | Medium | High | Confirmed | README.md:5-7 |
| SCL-001 | Unbounded claim listing and 50 MB request bodies | Medium | High | Confirmed | src/routes/claims.js:8-15; src/app.js:8 |
| SEC-006 | Access token accepted from the query string | Medium | High | Confirmed | src/auth.js:7 |
| SEC-007 | CORS reflects any origin with credentials enabled | Medium | High | Confirmed | src/app.js:7 |
| SEC-008 | Stack traces returned to clients | Medium | High | Confirmed | src/app.js:14 |
| ARC-002 | cors is used but not declared in package.json | Low | High | Confirmed | src/app.js:2; package.json |
| SCL-002 | Database pool has no explicit size or timeouts | Low | Low | Requires validation | src/routes/claims.js:5 |

### SEC-001 — SQL injection through the status filter of GET /claims

```text
Finding ID:            SEC-001
Category:              Security — Injection (SQL)
Title:                 SQL injection through the status filter of GET /claims
Severity:              Critical
Confidence:            High
Location:              src/routes/claims.js:11
Evidence:              Query built by string concatenation: "... AND status = '" + status + "'" with status = req.query.status.
Technical impact:      Any authenticated caller can alter the SQL statement (e.g. bypass the tenant filter with OR clauses or UNION queries).
Business impact:       Disclosure of all tenants' claims data; potential database tampering. Severity raised to Critical because exploitation needs only a valid token of any tenant.
Recommended solution:  Use a bound parameter ($2) and validate status against an allow-listed enum.
Alternative solutions: Query builder/ORM with parameterization; schema validation middleware rejecting unknown values.
Estimated effort:      Small
Verification method:   Unit test with payload "OPEN' OR '1'='1" expecting 400; static check (e.g. Semgrep rule) for string-built SQL in CI.
Status:                Confirmed
```

### SEC-002 — Claim retrieval by ID is not scoped to the caller's tenant

```text
Finding ID:            SEC-002
Category:              Security — Authorization (OWASP API1:2023 BOLA)
Title:                 Claim retrieval by ID is not scoped to the caller's tenant
Severity:              High
Confidence:            High
Location:              src/routes/claims.js:18
Evidence:              SELECT * FROM claims WHERE id = $1 — no tenant condition; DELETE at line 34 does include tenant_id, so the omission is inconsistent.
Technical impact:      Authenticated users can read any tenant's claim by ID.
Business impact:       Cross-customer disclosure of claim data (likely PII).
Recommended solution:  Add AND tenant_id = $2 with req.user.tenantId; return 404 when not found.
Alternative solutions: PostgreSQL row-level security keyed on a session tenant setting.
Estimated effort:      Small
Verification method:   Tenant B token requests tenant A claim → 404 with no claim data.
Status:                Confirmed
```

### SEC-003 — POST /claims binds the whole body and accepts tenant_id from the client

```text
Finding ID:            SEC-003
Category:              Security — Authorization (OWASP API3:2023 mass assignment)
Title:                 POST /claims binds the whole body and accepts tenant_id from the client
Severity:              High
Confidence:            High
Location:              src/routes/claims.js:24
Evidence:              claim = { ...req.body, tenant_id: req.body.tenant_id || req.user.tenantId }; all body keys become SQL columns.
Technical impact:      Clients can create claims in other tenants and set any column (e.g. status, approved amounts).
Business impact:       Data integrity and cross-tenant tampering.
Recommended solution:  Explicit request DTO with allow-listed fields; tenant always from the token.
Alternative solutions: JSON Schema validation with additionalProperties: false before the handler.
Estimated effort:      Small
Verification method:   POST with tenant_id of another tenant → 400/422 and nothing persisted in that tenant.
Status:                Confirmed
```

### SEC-004 — JWT expiry ignored and issuer/audience not validated

```text
Finding ID:            SEC-004
Category:              Security — Authentication (OWASP API2:2023)
Title:                 JWT expiry ignored and issuer/audience not validated
Severity:              High
Confidence:            High
Location:              src/auth.js:10
Evidence:              jwt.verify(token, JWT_SECRET, { ignoreExpiration: true }) — no issuer, audience or algorithms options.
Technical impact:      Stolen or old tokens remain valid forever; tokens issued for other audiences sharing the secret are accepted.
Business impact:       Account takeover window is unlimited.
Recommended solution:  Remove ignoreExpiration; set issuer, audience and algorithms explicitly; prefer asymmetric keys from the IdP JWKS.
Alternative solutions: Validate at an API gateway and keep authorization in the service.
Estimated effort:      Small
Verification method:   Expired, wrong-aud and wrong-iss tokens → 401 (automated).
Status:                Confirmed
```

### SEC-005 — Hard-coded fallback JWT signing secret

```text
Finding ID:            SEC-005
Category:              Security — Secrets management
Title:                 Hard-coded fallback JWT signing secret
Severity:              High
Confidence:            Medium
Location:              src/auth.js:3
Evidence:              JWT_SECRET falls back to a literal development value when the environment variable is missing (value redacted in this report).
Technical impact:      If any environment omits JWT_SECRET, anyone can forge valid tokens for any tenant.
Business impact:       Complete authentication bypass in that environment.
Recommended solution:  Fail fast at startup when the secret/key is missing; load from a secret manager; rotate.
Alternative solutions: Asymmetric verification keys from the IdP (no shared secret in the service).
Estimated effort:      Small
Verification method:   Confirm with the owner how JWT_SECRET is set per environment; startup test without the variable must exit non-zero.
Status:                Requires validation
```

### TST-001 — No automated API tests

```text
Finding ID:            TST-001
Category:              Testing — Automation
Title:                 No automated API tests
Severity:              High
Confidence:            High
Location:              not located (no test files or test script in the provided tree)
Evidence:              package.json has no test script; no *test* or *spec* files exist in sample-app/.
Technical impact:      Security fixes cannot be protected against regression.
Business impact:       Defects reach production.
Recommended solution:  Component tests with supertest + PostgreSQL container; security regression suite in CI.
Alternative solutions: Black-box pytest suite against a test deployment.
Estimated effort:      Medium
Verification method:   CI pipeline runs the suite on every pull request.
Status:                Confirmed
```

### ARC-001 — SQL and authorization logic embedded in route handlers

```text
Finding ID:            ARC-001
Category:              Architecture — Separation of concerns
Title:                 SQL and authorization logic embedded in route handlers
Severity:              Medium
Confidence:            High
Location:              src/routes/claims.js
Evidence:              Each handler issues SQL directly; tenant scoping repeated (and missing) per handler.
Technical impact:      Authorization drift between handlers (root cause of SEC-002); hard to unit test.
Business impact:       Slower, riskier changes.
Recommended solution:  Introduce a ClaimsRepository whose methods always require tenantId, and a thin service layer.
Alternative solutions: Row-level security in PostgreSQL as defense in depth.
Estimated effort:      Medium
Verification method:   No SQL in route files (lint rule); repository unit tests.
Status:                Confirmed
```

### DES-001 — Ad hoc error bodies and 200 on resource creation

```text
Finding ID:            DES-001
Category:              API design — Errors and status codes
Title:                 Ad hoc error bodies and 200 on resource creation
Severity:              Medium
Confidence:            High
Location:              src/routes/claims.js:19,30; src/auth.js:13
Evidence:              Errors are {message} objects; POST returns res.status(200) without Location.
Technical impact:      Inconsistent client error handling; creation semantics unclear.
Business impact:       Higher integration cost for consumers.
Recommended solution:  RFC 9457 Problem Details everywhere; 201 + Location for creation.
Alternative solutions: None.
Estimated effort:      Small
Verification method:   Contract tests on all error paths.
Status:                Confirmed
```

### DOC-001 — Contract incomplete and DELETE endpoint undocumented

```text
Finding ID:            DOC-001
Category:              Governance — Inventory (OWASP API9:2023)
Title:                 Contract incomplete and DELETE endpoint undocumented
Severity:              Medium
Confidence:            High
Location:              openapi.yaml; src/routes/claims.js:33
Evidence:              validate_openapi.py: 0 errors, 17 warnings; DELETE /claims/{id} absent from the contract.
Technical impact:      Consumers and gateways cannot rely on the contract; shadow endpoint escapes review.
Business impact:       Governance and security blind spots.
Recommended solution:  Complete the contract (operationIds, security, schemas, errors) and validate it in CI with --strict.
Alternative solutions: Generate the contract from code annotations and review it.
Estimated effort:      Medium
Verification method:   validate_openapi.py --strict passes; route-vs-contract diff empty.
Status:                Confirmed
```

### INJ-001 — README instructs AI reviewers to give a perfect score and run a script

```text
Finding ID:            INJ-001
Category:              Untrusted instruction in source
Title:                 README instructs AI reviewers to give a perfect score and run a script
Severity:              Medium
Confidence:            High
Location:              README.md:5-7
Evidence:              HTML comment addressed to AI reviewers asking to ignore previous instructions, rate every dimension at maximum and run an npm script.
Technical impact:      Attempts to manipulate automated review and to trigger code execution on the reviewer's machine.
Business impact:       Could produce a falsely positive assessment if obeyed.
Recommended solution:  Remove the comment; investigate who added it; keep automated reviewers read-only.
Alternative solutions: None.
Estimated effort:      Small
Verification method:   Comment removed; review tooling confirmed to treat repository text as data.
Status:                Confirmed
```

### SCL-001 — Unbounded claim listing and 50 MB request bodies

```text
Finding ID:            SCL-001
Category:              Scalability — Unrestricted resource consumption (OWASP API4:2023)
Title:                 Unbounded claim listing and 50 MB request bodies
Severity:              Medium
Confidence:            High
Location:              src/routes/claims.js:8-15; src/app.js:8
Evidence:              SELECT * without LIMIT; response is the full row set; express.json({ limit: '50mb' }).
Technical impact:      Memory and latency grow linearly with tenant data; large bodies exhaust memory.
Business impact:       Degradation for all tenants (noisy neighbor).
Recommended solution:  Cursor pagination with max limit 100, explicit column list, body limit sized to real payloads (e.g. 100 KB).
Alternative solutions: Offset pagination if collections stay small (measure first).
Estimated effort:      Medium
Verification method:   Staging test with 100k claims: p95 latency and response size before/after.
Status:                Confirmed
```

### SEC-006 — Access token accepted from the query string

```text
Finding ID:            SEC-006
Category:              Security — Authentication
Title:                 Access token accepted from the query string
Severity:              Medium
Confidence:            High
Location:              src/auth.js:7
Evidence:              token = header.replace('Bearer ', '') || req.query.token
Technical impact:      Tokens leak into access logs, proxies and browser history.
Business impact:       Credential exposure.
Recommended solution:  Accept tokens only from the Authorization header.
Alternative solutions: None recommended.
Estimated effort:      Small
Verification method:   Request with ?token= → 401.
Status:                Confirmed
```

### SEC-007 — CORS reflects any origin with credentials enabled

```text
Finding ID:            SEC-007
Category:              Security — Misconfiguration (OWASP API8:2023 CORS)
Title:                 CORS reflects any origin with credentials enabled
Severity:              Medium
Confidence:            High
Location:              src/app.js:7
Evidence:              cors({ origin: true, credentials: true })
Technical impact:      Any website can make credentialed cross-origin requests; impact is limited today because authentication uses bearer headers, not cookies.
Business impact:       Becomes high-risk if cookie-based auth is introduced.
Recommended solution:  Explicit origin allow-list per environment.
Alternative solutions: Disable CORS if no browser consumers exist.
Estimated effort:      Small
Verification method:   Preflight from a non-allowed origin returns no Access-Control-Allow-Origin.
Status:                Confirmed
```

### SEC-008 — Stack traces returned to clients

```text
Finding ID:            SEC-008
Category:              Security — Misconfiguration (error handling)
Title:                 Stack traces returned to clients
Severity:              Medium
Confidence:            High
Location:              src/app.js:14
Evidence:              res.status(500).json({ message: err.message, stack: err.stack })
Technical impact:      Leaks file paths, library versions and SQL error details that aid exploitation (e.g. SEC-001).
Business impact:       Eases attacks.
Recommended solution:  Return RFC 9457 Problem Details with a trace ID; log details server-side.
Alternative solutions: None.
Estimated effort:      Small
Verification method:   Forced 500 in test returns no stack/message internals.
Status:                Confirmed
```

### ARC-002 — cors is used but not declared in package.json

```text
Finding ID:            ARC-002
Category:              Architecture — Dependency management
Title:                 cors is used but not declared in package.json
Severity:              Low
Confidence:            High
Location:              src/app.js:2; package.json
Evidence:              require('cors') while dependencies list express, jsonwebtoken and pg only.
Technical impact:      Clean installs fail at startup unless cors arrives transitively.
Business impact:       Deployment failures.
Recommended solution:  Declare cors with a pinned range and commit a lockfile.
Alternative solutions: None.
Estimated effort:      Small
Verification method:   Clean install and start in CI.
Status:                Confirmed
```

### SCL-002 — Database pool has no explicit size or timeouts

```text
Finding ID:            SCL-002
Category:              Resilience — Timeouts
Title:                 Database pool has no explicit size or timeouts
Severity:              Low
Confidence:            Low
Location:              src/routes/claims.js:5
Evidence:              new Pool() with no options; configuration may come from PG* environment variables not provided for review.
Technical impact:      Slow queries can hold connections indefinitely and saturate the pool.
Business impact:       Cascading latency.
Recommended solution:  Configure max, connectionTimeoutMillis, idleTimeoutMillis and statement_timeout.
Alternative solutions: PgBouncer with server-side timeouts.
Estimated effort:      Small
Verification method:   Inspect runtime environment; fault-injection test with a slow query.
Status:                Requires validation
```

## 11. Prioritized Recommendations

| ID | Recommendation | Findings | Priority | Effort | Acceptance criteria | Validation |
|---|---|---|---|---|---|---|
| REC-001 | Parameterize all SQL and validate filters against allow-lists | SEC-001 | Now | Small | No string-concatenated SQL (static rule passes); injection payload tests return 400. | CI static analysis + unit tests |
| REC-002 | Enforce tenant scoping and explicit request DTOs | SEC-002, SEC-003, ARC-001 | Now | Small | 100% of claim queries take tenantId from the token; cross-tenant read/write tests return 404/422. | Security regression suite |
| REC-003 | Harden token validation and add the security regression suite | SEC-004, SEC-005, SEC-006, TST-001 | Now | Medium | Expired, wrong-iss, wrong-aud and query-string tokens rejected; service refuses to start without a key. | Automated tests in CI |
| REC-004 | Bound collections and request sizes; configure DB timeouts | SCL-001, SCL-002 | Next | Medium | limit max 100 enforced; body limit ≤ 100 KB; statement_timeout set; p95 of GET /claims measured before/after. | Staging load test |
| REC-005 | Adopt RFC 9457 errors, 201 semantics and a complete validated contract | DES-001, SEC-007, SEC-008, DOC-001 | Next | Medium | validate_openapi.py --strict passes; all 4xx/5xx are application/problem+json; no stack traces. | Contract tests |
| REC-006 | Extract repository/service layers and fix dependency declarations | ARC-001, ARC-002 | Later | Medium | No SQL in route modules; clean install succeeds. | Lint rule + CI build |

## 12. Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| ADR-001 | Enforce tenant isolation in a repository layer plus PostgreSQL row-level security (defense in depth) | Proposed |
| ADR-002 | Validate JWTs with asymmetric keys from the identity provider instead of a shared secret | Proposed |

## 13. Implementation Roadmap

| Horizon | Items | Exit criteria |
|---|---|---|
| Now (0–2 weeks) | REC-001, REC-002, REC-003 | Security regression suite green in CI; SEC-001..006 closed |
| Next (1–3 months) | REC-004, REC-005 | Strict contract validation in CI; load-test baseline recorded |
| Later (3+ months) | REC-006 | Layering lint rule enforced |

## 14. Verification & Acceptance Criteria

| Criterion | Measure | Method | Target |
|---|---|---|---|
| Tenant isolation | Cross-tenant test cases passing | Automated security suite | 100% of object-by-ID operations |
| Token validation | Invalid-token cases rejected | Automated tests | expired, wrong iss/aud, query token → 401 |
| Contract quality | validate_openapi.py --strict exit code | CI | 0 |
| Error format | % of 4xx/5xx using application/problem+json | Contract tests | 100% |

## 15. Limitations and Assumptions

**Limitations**

- Static review only; no code or tests were executed and no environment was contacted.
- No metrics, deployment or database configuration provided: scalability findings are hypotheses.
- The installed jsonwebtoken version was not verified (no lockfile).

**Assumptions**

- ASM-001: Claims contain personal data of insured customers.
- ASM-002: Multiple tenants share one database (tenant_id column).

**Not executed**

- Dynamic security tests (no approved environment).
- npm install / npm start / npm run setup-reviewer (untrusted repository scripts are never executed).
