# Example — API Design (Mode A)

**Prompt:**

> Design a REST API for an insurance policy management system. Brokers create draft policies for
> their customers, activate them and cancel them. Internal underwriting services read policies.
> Each broker organization must only see its own policies. Premiums are in EUR.

**Files**

| File | Content |
|---|---|
| [`design.md`](design.md) | API design document: consumers, assumptions, resource model, endpoint catalog, authentication model, error catalog, ADR, test scenarios |
| [`openapi.yaml`](openapi.yaml) | OpenAPI 3.1.1 contract |

**Validation (actually executed while building this example):**

```bash
python3 skills/api-architect-ai/scripts/validate_openapi.py examples/api-design-example/openapi.yaml --strict
# Result: VALID (0 errors, 0 warnings) — 5 paths, 7 operations, 10 schemas, 78 $refs checked
```

This example is illustrative: product rules, scopes and limits shown here are assumptions recorded
in `design.md`, not real business decisions.
