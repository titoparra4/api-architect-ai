# Mode E (part 1) — Interoperability & Compatibility

Use with `governance.md` and `openapi-standards.md`.

## Contents
1. REST and HTTP conformance checklist
2. Data format conventions
3. Compatibility rules (what breaks consumers)
4. Integration scenarios
5. Choosing REST, async messaging, webhooks, GraphQL or gRPC

---

## 1. REST and HTTP conformance checklist

- Methods used with correct semantics (safe/idempotent; see `api-design.md` §4).
- Status codes consistent and meaningful: `201` + `Location` on creation, `204` without body,
  `401` vs `403` distinguished, `409`/`412`/`422` used deliberately, `429` with `Retry-After`.
- Errors as RFC 9457 Problem Details (`application/problem+json`) across all endpoints.
- Content negotiation: `Content-Type` validated (`415` on unsupported), `Accept` honored (`406` when
  impossible), charset UTF-8 for JSON.
- Caching headers (`ETag`, `Last-Modified`, `Cache-Control`) where reads are cacheable.
- Correlation: accept/propagate W3C `traceparent`; return a request/trace ID in responses and in
  Problem Details.
- Header naming: no new `X-` prefixed headers for standardized concepts (RFC 6648); use standard or
  well-known headers (`Idempotency-Key`, `RateLimit-*` drafts, `Deprecation`, `Sunset`).

## 2. Data format conventions

| Topic | Rule |
|---|---|
| Timestamps | RFC 3339 with explicit offset; store and transmit UTC; dates without time as `date` (`2026-11-13`); document the business time zone for date-only semantics (e.g. "policy effective at 00:00 in the insurer's time zone"). |
| Durations | ISO 8601 durations (`PT30M`) or explicit units in the field name (`timeoutSeconds`). |
| Numbers | Decimal amounts as strings or integer minor units; avoid integers beyond 2^53 in JSON for JavaScript consumers — use strings for 64-bit IDs. |
| Unicode & localization | UTF-8 everywhere; validate length in characters, not bytes, and document it; locale-specific text via `Accept-Language`; store language-neutral codes, localize display text at the edge. |
| Nullability | Document absent vs `null` vs empty; in OpenAPI 3.1 use `type: [X, "null"]`; avoid using `null` to mean "unknown" and "not applicable" at the same time. |
| Optional vs required | Required = always present in responses / mandatory in requests. Making an optional request field required, or a required response field optional, breaks consumers. |
| Enums | Clients must tolerate unknown enum values if the enum may grow (document it, or model as an extensible string with known values). |
| Identifiers | Opaque strings; never require clients to parse them. |
| Booleans | Avoid tri-state booleans; prefer enums when a third state appears. |

## 3. Compatibility rules (what breaks consumers)

**Breaking for existing consumers:**
- Removing or renaming a path, operation, parameter, property or enum value in a response consumers
  may rely on.
- Adding a required request parameter/property, or making an optional one required.
- Changing a type, format or the meaning of a field; tightening constraints on requests (smaller
  `maxLength`, new `pattern`, removed request enum value).
- Making a response property nullable or optional when it was required and non-null.
- Changing success status codes, media types, authentication or required scopes.
- Changing default behavior (default sort order, default page size if clients depend on it).

**Potentially breaking (depends on consumer tolerance):** adding response enum values, adding new
error status codes, changing pagination defaults, adding `additionalProperties: false` to requests.

**Non-breaking (additive):** new optional request fields/parameters, new response fields (if clients
ignore unknown fields — make this a published consumer rule), new operations, relaxed request
constraints.

Detect mechanically with `scripts/compare_contracts.py OLD NEW`; confirm semantic changes manually
(the script cannot detect meaning changes).

## 4. Integration scenarios

| Scenario | Considerations |
|---|---|
| Legacy systems (SOAP, mainframe, batch files) | Anti-corruption layer translating legacy models; do not leak legacy codes/field names into the public API; handle legacy availability windows with queues and `202`; idempotent replay of batch loads. |
| Third-party APIs | Treat responses as untrusted (validate schemas, bounds); timeouts and circuit breakers; respect their rate limits; isolate credentials per partner; monitor contract drift. |
| Internal services | Consistent auth (service identities), shared error and tracing conventions, contract tests between producer and consumers. |
| Enterprise platforms (ERP, CRM, IAM, ESB/iPaaS) | Canonical model only where it reduces mapping cost; avoid platform lock-in in public contracts; event or batch integration for bulk sync. |
| API gateways | Verify contract features the gateway supports (OpenAPI version, `QUERY` method, request validation, large headers); route-level rate limits; JWT validation at the gateway **and** authorization in the service. |
| Cross-platform consumers | Mobile clients cannot be upgraded instantly → longer deprecation windows; JavaScript number precision; generated SDK compatibility; time zones. |

## 5. Choosing REST, async messaging, webhooks, GraphQL or gRPC

| Need | Best fit | Trade-offs |
|---|---|---|
| Resource-oriented CRUD + workflows for heterogeneous/external consumers | REST/HTTP + OpenAPI | Ubiquitous tooling, caching; chattiness for complex screens |
| Notify external consumers of events | Webhooks (signed) | Consumers must expose endpoints; delivery retries, ordering not guaranteed |
| Decoupled internal workflows, high fan-out, buffering | Async messaging (Kafka, AMQP) + AsyncAPI | Eventual consistency, operational complexity, harder debugging |
| Many client-specific views of a rich graph, first-party front ends | GraphQL (or a BFF) | Query cost control, caching and authorization per field are harder |
| Low-latency internal service-to-service with strong schemas, streaming | gRPC + Protobuf | Limited browser support (gRPC-Web), gateways/proxies need HTTP/2, less human-readable |
| Large file transfer | Pre-signed object-storage URLs | Expiry and scope of signed URLs |

Document the trade-off; do not force REST where events or streaming are the natural fit, and do not
recommend GraphQL/gRPC/messaging without a concrete requirement that REST serves poorly.
