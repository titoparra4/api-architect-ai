# Example — API Testing & Quality Engineering (Mode F)

**Prompts:**

> Create an API regression testing strategy for the policy API and generate Postman and pytest tests.
>
> Identify breaking changes between these OpenAPI contracts and tell me which tests to run.

**Files**

| File | Content |
|---|---|
| [`test-strategy.md`](test-strategy.md) | Risk-based strategy, levels, traceability, CI integration, regression selection |
| [`postman/policies.postman_collection.json`](postman/policies.postman_collection.json) | Postman collection with meaningful assertions (Newman-ready) |
| [`pytest-suite/test_policies_api.py`](pytest-suite/test_policies_api.py) | Black-box pytest suite: functional, boundary, BOLA, scopes, tokens, idempotency, ETag, state machine |

The tests target the contract in [`../api-design-example/openapi.yaml`](../api-design-example/openapi.yaml).

**Execution status:** these suites require a running implementation and an **approved** test
environment, which this repository does not include. They were **not executed** against a live
API. The pytest module skips itself when `API_BASE_URL` is unset. The repository CI only checks
that the files parse.

```bash
# pytest (approved environment only)
export API_BASE_URL=https://api.sandbox.example-insurer.com/v1
export TOKEN_ORG_A=... TOKEN_ORG_B=... TOKEN_READ_ONLY=... TOKEN_EXPIRED=...
python3 -m pytest examples/api-testing-example/pytest-suite -v

# Newman (tokens from an environment file kept out of version control)
npx newman run examples/api-testing-example/postman/policies.postman_collection.json \
  -e sandbox.postman_environment.json --reporters cli,junit --reporter-junit-export newman.xml
```
