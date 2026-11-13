# API Test Case Template

## Test case

| Field | Value |
|---|---|
| **Test ID** | TC-<AREA>-<NNN> (e.g. TC-SEC-004) |
| **Title** | <behavior under test, e.g. "Tenant B cannot read tenant A policy"> |
| **Type** | Functional / Contract / Security / Resilience / Regression / Performance |
| **Priority** | P1 / P2 / P3 |
| **Traceability** | Requirement <REQ-ID> · Operation `<operationId>` · Risk/Finding <ID> · Defect <ID> |
| **Preconditions** | <data, users, tokens, feature flags, environment> |
| **Test data** | <synthetic data; no production PII> |
| **Request** | `<METHOD> <path>` · headers · body |
| **Expected status** | <code> |
| **Expected headers** | <Content-Type, Location, ETag, Retry-After, …> |
| **Expected body** | <schema reference + key business values> |
| **Expected side effects** | <persisted state, events, audit log; or "no state change"> |
| **Negative-space checks** | <fields that must NOT appear; no stack traces> |
| **Environment** | <approved environment> |
| **Automation** | <framework + file path, or "manual"> |
| **Execution result** | Not executed / Passed / Failed — <date, run link or output excerpt> |

## Traceability matrix

| Requirement / Risk | Operation | Test IDs | Type | Automated | Last result |
|---|---|---|---|---|---|

## Coverage summary

| Area | Operations | Positive | Negative | Boundary | Security | Contract | Resilience |
|---|---:|---:|---:|---:|---:|---:|---:|
