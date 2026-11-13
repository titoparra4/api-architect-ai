# API Test Strategy — Insurance Policy Management API v1

## 1. Scope and objectives

Operations: the 7 operations in `examples/api-design-example/openapi.yaml`. Objective: prevent
regressions in policy lifecycle, tenant isolation and contract compatibility on every change.
Environments: component tests in CI (service + PostgreSQL container); black-box regression in the
approved sandbox environment.

## 2. Risk analysis

| Risk | Impact | Likelihood driver | Test focus |
|---|---|---|---|
| R1 Cross-organization data access (BOLA) | Critical (PII, regulatory) | Multi-tenant data model | Security suite on every operation with `{policyId}` |
| R2 Duplicate policies on client retries | High (double billing) | Mobile/partner retries | Idempotency tests |
| R3 Lost updates on concurrent edits | Medium | Back-office + portal editing | ETag / `If-Match` tests |
| R4 Invalid state transitions | High | Complex lifecycle | State-machine tests (valid + invalid) |
| R5 Breaking contract changes | High (partner integrations) | Frequent releases | Contract diff gate + consumer contracts |
| R6 Resource exhaustion | Medium | Large broker portfolios | Pagination boundary tests |

## 3. Levels

| Level | Tooling | Runs | Owner |
|---|---|---|---|
| Unit (validators, policy rules, authorization policy) | Stack-native unit framework | Every commit | Dev |
| Component (API + DB container) | Stack-native + Testcontainers | Every PR | Dev |
| Contract | `validate_openapi.py --strict`, `compare_contracts.py --fail-on breaking`, response schema validation, Pact for partner consumers | Every PR | Dev + QA |
| Black-box regression | pytest suite / Newman collection | After deploy to sandbox | QA |
| Performance smoke | k6 (approved environment) | Nightly | QA + SRE |

## 4. Scenario catalog (excerpt)

| Test ID | Type | Operation | Scenario | Expected | Traces to |
|---|---|---|---|---|---|
| TC-FUN-001 | Functional | createPolicy | Valid draft | 201, Location, ETag, schema-valid body, `DRAFT` | REQ-001 |
| TC-FUN-002 | Idempotency | createPolicy | Retry same key + payload | Same id, one record | R2 |
| TC-FUN-003 | Idempotency | createPolicy | Same key, different payload | 422 Problem | R2 |
| TC-FUN-004 | State | activatePolicy | Activate CANCELLED | 409, state unchanged | R4 |
| TC-CON-001 | Contract | createPolicy | Body with `status`/`id` | 400, nothing persisted | API3 |
| TC-BND-001..004 | Boundary | listPolicies | `limit` = 1, 100, 0, 101 | 200, 200, 400, 400 | R6 |
| TC-SEC-001 | Security | getPolicy | Org B reads org A policy | 404, no policy fields | R1 |
| TC-SEC-002 | Security | listPolicies | Org B list excludes org A data | id absent | R1 |
| TC-SEC-003 | Security | cancelPolicy | Token without `policies:cancel` | 403 | Scopes |
| TC-SEC-004..006 | Security | listPolicies | No token / malformed / expired | 401 + `WWW-Authenticate` | API2 |
| TC-RES-001 | Concurrency | updateDraftPolicy | Stale `If-Match` | 412, unchanged | R3 |

Automated in `pytest-suite/test_policies_api.py` (all rows) and `postman/` (core subset).

## 5. Assertion standard

Each test asserts status, critical headers, schema, business values and side effects, plus negative
space (no foreign data, no stack traces). Status-only assertions are rejected in review.

## 6. CI/CD integration

```yaml
# Excerpt — contract gate on pull requests (GitHub Actions)
- name: Validate contract
  run: python3 skills/api-architect-ai/scripts/validate_openapi.py openapi.yaml --strict
- name: Breaking-change gate
  run: |
    git show origin/main:openapi.yaml > /tmp/base-openapi.yaml
    python3 skills/api-architect-ai/scripts/compare_contracts.py /tmp/base-openapi.yaml openapi.yaml --fail-on breaking
```

Black-box suites run after deployment to the sandbox with tokens from the CI secret store; JUnit
reports are published; a failure blocks promotion.

## 7. Regression selection after a contract change

Command actually run on the repository fixtures:

```bash
python3 skills/api-architect-ai/scripts/compare_contracts.py tests/fixtures/orders-v1.yaml tests/fixtures/orders-v2.yaml
# Summary: breaking=17, potentially-breaking=4, non-breaking=5, info=2   (exit code 1)
```

Selection rules applied to that result:

| Change (examples) | Level | Tests to run |
|---|---|---|
| `DELETE /orders/{orderId}` removed | breaking | Consumer contract verification; notify consumers; block release without new major |
| New required query parameter `region` on `GET /orders` | breaking | Full functional + boundary suite for `listOrders` |
| `total` no longer required and nullable in `Order` | breaking | Contract tests for every operation returning `Order` (shared schema) |
| `POST /orders` now also requires `orders:admin` | breaking | Full security suite for `createOrder` |
| `GET /health` now requires authentication | breaking | Monitoring/probe configuration tests |
| Enum value `RETURNED` added to `Order.status` | potentially-breaking | Consumer tolerance tests for unknown enum values |
| `PATCH /orders/{id}` added | non-breaking | New functional, security and contract tests for the new operation |

Always: smoke tests for critical journeys and tests linked to previously reported defects.

## 8. Exit criteria

All P1 tests pass; no open Critical/High defects; contract gate green; security suite green;
results recorded with run links. Tests not executed are reported as "not executed", never as passed.
