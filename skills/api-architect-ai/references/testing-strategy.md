# Mode F — API Testing & Quality Engineering

## Contents
1. Principles
2. Test strategy structure
3. Test design techniques per area
4. Assertion quality rules
5. Framework selection
6. Automation examples
7. CI/CD integration
8. Regression selection after contract changes

---

## 1. Principles

- Risk-based: depth follows business criticality, data sensitivity and change frequency.
- Every test traces to a requirement, contract operation, risk or finding ID.
- **Meaningful assertions**: status code + headers + schema + business values + side effects.
  Status-code-only tests are insufficient.
- Deterministic and isolated: own test data, no order dependence, cleanup.
- Security and resilience tests only in approved, non-production environments.
- **Never report tests as passed without executing them.** Report the command and the actual output.

## 2. Test strategy structure

1. Scope and objectives (operations, versions, environments).
2. Risk analysis (top risks → test focus).
3. Test levels: unit (validators, policies), component/integration (API + real DB in a container),
   contract (OpenAPI conformance, consumer contracts), end-to-end (critical journeys only),
   non-functional (performance, resilience, security).
4. Test data strategy (synthetic, per-tenant fixtures, no production PII).
5. Environments and access (who approves security/performance tests).
6. Automation framework and CI integration.
7. Entry/exit criteria and reporting.
8. Traceability matrix (`assets/test-case-template.md`).

## 3. Test design techniques per area

**Functional:** positive paths per operation; negative (missing/invalid fields, wrong types, unknown
fields); boundary values (min/max length, `limit` = 0/1/max/max+1, date boundaries, numeric
precision); business rules (decision tables); CRUD lifecycle (create → read → update → delete → read
404); state transitions (valid and invalid); pagination (first/last page, tampered cursor, stable
ordering); filtering (each allowed filter; disallowed filter → 400); sorting (each allowed field,
direction, tiebreaker).

**Contract:** invalid requests rejected with Problem Details; responses validated against the schema
for every status; implementation vs OpenAPI (undocumented status codes or fields); backward
compatibility (`scripts/compare_contracts.py`); consumer-driven contracts (Pact).

**Security:** no token → 401; malformed / expired / wrong `aud` / wrong `iss` / `alg: none` / tampered
token → 401; missing scope → 403; cross-tenant and cross-owner object access (BOLA) → 404/403;
function-level access (non-admin on admin routes, all methods); mass assignment of read-only fields;
rate-limit enforcement (429 + `Retry-After`); sensitive data exposure (only allowed fields; no stack
traces in errors); CORS preflight from a disallowed origin.

**Resilience:** dependency timeout (stub responds slowly → API returns 503/504 within its budget);
dependency failure → graceful degradation or Problem Details; retry behavior (stub fails N times →
verify retry count and backoff); duplicate requests with the same `Idempotency-Key` → one side effect
and the same response; same key with a different payload → 422; partial failures in bulk operations;
concurrent updates with stale `If-Match` → 412.

**Regression:** existing endpoint behavior (golden responses with volatile fields masked); schema
compatibility; version changes; one test per previously reported defect ID.

## 4. Assertion quality rules

Each API test asserts, where applicable:
1. Status code.
2. Critical headers (`Content-Type`, `Location`, `ETag`, `Retry-After`, `Cache-Control`).
3. Body schema (JSON Schema / OpenAPI validation).
4. Business values (computed premium, state, owner, totals).
5. Side effects (resource persisted/changed/unchanged; event published; audit log written).
6. Negative space (no extra sensitive fields; no internal details in errors).

## 5. Framework selection

Choose by the repository's stack and the user's preference; do not introduce a new language only for
tests unless asked.

| Stack / need | Recommended |
|---|---|
| Python services, or language-neutral black-box tests | pytest + requests/httpx + jsonschema (schemathesis for property-based) |
| Java/Kotlin (Spring) | REST Assured + JUnit 5 (+ Testcontainers) |
| TypeScript/JavaScript, teams already on Playwright | Playwright `APIRequestContext` |
| Shareable collections, QA teams | Postman collections + Newman in CI |
| .NET | xUnit + `WebApplicationFactory` |
| Load | k6, Gatling, JMeter, Locust (approved environments only) |

## 6. Automation examples

pytest:

```python
import os, uuid, requests
from jsonschema import validate

BASE = os.environ["API_BASE_URL"]

def test_create_policy_returns_201_location_and_body(agent_token, policy_payload, policy_schema):
    r = requests.post(f"{BASE}/v1/policies", json=policy_payload,
                      headers={"Authorization": f"Bearer {agent_token}",
                               "Idempotency-Key": str(uuid.uuid4())}, timeout=10)
    assert r.status_code == 201
    assert r.headers["Content-Type"].startswith("application/json")
    body = r.json()
    assert r.headers["Location"].endswith(f"/v1/policies/{body['id']}")
    validate(body, policy_schema)
    assert body["status"] == "DRAFT"
    assert body["holder"]["customerId"] == policy_payload["holder"]["customerId"]

def test_cannot_read_policy_from_other_tenant(tenant_b_token, tenant_a_policy_id):
    r = requests.get(f"{BASE}/v1/policies/{tenant_a_policy_id}",
                     headers={"Authorization": f"Bearer {tenant_b_token}"}, timeout=10)
    assert r.status_code == 404
    assert r.headers["Content-Type"].startswith("application/problem+json")
    assert "holder" not in r.json()
```

REST Assured:

```java
given().auth().oauth2(agentToken).contentType(JSON)
       .header("Idempotency-Key", UUID.randomUUID().toString())
       .body(payload)
.when().post("/v1/policies")
.then().statusCode(201)
       .header("Location", matchesPattern(".*/v1/policies/[0-9a-f-]{36}$"))
       .body("status", equalTo("DRAFT"))
       .body(matchesJsonSchemaInClasspath("schemas/policy.json"));
```

Playwright:

```ts
test('expired token is rejected with problem details', async ({ request }) => {
  const res = await request.get('/v1/policies', { headers: { Authorization: `Bearer ${expiredToken}` } });
  expect(res.status()).toBe(401);
  expect(res.headers()['www-authenticate']).toContain('Bearer');
  expect(res.headers()['content-type']).toContain('application/problem+json');
  const body = await res.json();
  expect(body.status).toBe(401);
  expect(JSON.stringify(body)).not.toMatch(/stack|exception/i);
});
```

Postman test script and Newman:

```javascript
pm.test("201 with Location and DRAFT status", () => {
  pm.response.to.have.status(201);
  pm.expect(pm.response.headers.get("Location")).to.match(/\/v1\/policies\/[0-9a-f-]{36}$/);
  const body = pm.response.json();
  pm.expect(body.status).to.eql("DRAFT");
  pm.expect(body).to.not.have.property("internalRiskScore");
  pm.collectionVariables.set("policyId", body.id);
});
```

```bash
npx newman run collection.json -e env.staging.json --reporters cli,junit --reporter-junit-export results.xml
```

A complete example lives in the repository under `examples/api-testing-example/`.

## 7. CI/CD integration

Stages: lint contract → breaking-change check against the main branch → unit/component tests →
contract tests (provider verification) → deploy to test env → API functional + security regression
(Newman / pytest) → optional performance smoke. Publish JUnit reports; fail on breaking changes unless
an approved exception exists; secrets from the CI secret store, never committed.

## 8. Regression selection after contract changes

Run `scripts/compare_contracts.py old new --format json` and select:
- operations with a `breaking` or `potentially-breaking` change → full functional + contract suite,
  plus consumer contract verification;
- operations sharing a changed component schema → contract tests;
- security requirement changes → full security suite for those operations;
- always: smoke tests for critical journeys and tests linked to previously reported defects.
