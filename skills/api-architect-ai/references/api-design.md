# Mode A — API Design

Use this reference when turning business requirements, user stories, functional specifications,
NFRs or integration requirements into a REST API design.

## Contents
1. Design workflow
2. Resource discovery
3. URI and naming conventions
4. HTTP method semantics
5. Request/response schema design
6. Validation rules
7. Pagination, filtering, sorting
8. Errors (RFC 9457)
9. Idempotency and concurrency
10. Long-running and bulk operations
11. Versioning and compatibility
12. Design deliverables checklist

---

## 1. Design workflow

1. **Consumers and capabilities.** List consumers (web/mobile front ends, partners, internal
   services, batch jobs) and the business capabilities each needs. Record: trust level
   (first-party / partner / public), expected volume, latency sensitivity, offline/mobile constraints.
2. **Domain boundaries.** Group capabilities into bounded contexts. One API usually maps to one
   bounded context. Avoid exposing persistence models; design around consumer use cases.
3. **Resources.** Derive nouns (aggregates, entities, sub-resources) and their lifecycles (states and
   transitions). Write the state machine for any resource with status (e.g. policy:
   `draft → quoted → bound → active → cancelled|expired`).
4. **Operations.** Map each use case to a method + URI. When a state transition carries business
   meaning, prefer a sub-resource or action resource (see §4) over a free-form `PATCH status`.
5. **Schemas.** Define request, response and error schemas; separate *create*, *update* and
   *read* representations to prevent mass assignment.
6. **Cross-cutting.** Security model, pagination, errors, idempotency, concurrency, versioning,
   observability headers, rate limits.
7. **Contract.** Produce OpenAPI 3.1 (default) — see `openapi-standards.md` — and validate it with
   `scripts/validate_openapi.py`.
8. **Decisions.** Record non-obvious choices as ADRs (`assets/adr-template.md`).
9. **Tests.** Derive the test strategy (`testing-strategy.md`).

Ask only essential questions. Typical *essential* gaps: who the consumers are, multi-tenancy, data
sensitivity (PII, PCI, PHI), required authentication model, hard latency/availability targets.
Everything else: proceed with recorded assumptions (`ASM-###`).

## 2. Resource discovery

| Signal in requirements | Design consequence |
|---|---|
| "A policy has many coverages, never shared" | Sub-resource `/policies/{policyId}/coverages` |
| Entity referenced by many aggregates | Top-level resource with its own ID; link by ID |
| Verb with business meaning ("cancel", "approve", "bind") | Action sub-resource `POST /policies/{id}/cancellation` or a state-transition resource |
| Report / search spanning aggregates | Dedicated query resource (`GET /policy-search?...`) or `POST /policy-searches` when the query is large or sensitive |
| Process taking more than a few seconds | Asynchronous job resource (§10) |
| Data owned by another system | Do not duplicate its write model; reference it or proxy it explicitly |

Limit nesting to **one level** below an aggregate root (`/customers/{id}/addresses`). Deeper
nesting couples URIs to hierarchy and complicates authorization.

## 3. URI and naming conventions

- Plural nouns, kebab-case path segments: `/insurance-policies/{policyId}`.
- Path parameters identify; query parameters filter, sort, paginate, select fields.
- IDs are opaque strings (UUID/ULID). Avoid exposing sequential database IDs to untrusted consumers —
  they ease enumeration (sequential IDs are not a vulnerability by themselves; missing object-level
  authorization is).
- JSON property naming: pick one convention (camelCase is most common) and enforce it via lint.
- No verbs in paths except action resources; no file extensions; no trailing slashes.
- Timestamps: RFC 3339 with offset, UTC preferred (`2026-11-13T10:15:30Z`).
- Money: `{ "amount": "1250.00", "currency": "EUR" }` — decimal string or integer minor units, never
  binary floating point; ISO 4217 currency codes.
- Enumerations: one casing convention; document that clients must tolerate unknown values if the
  enum may grow (see `interoperability.md`).

## 4. HTTP method semantics (RFC 9110)

| Method | Safe | Idempotent | Typical use | Success codes |
|---|---|---|---|---|
| GET | yes | yes | Read resource/collection | 200, 304 |
| HEAD | yes | yes | Metadata only | 200, 304 |
| POST | no | **no** | Create in collection, actions, complex queries | 201 + `Location`, 200, 202 |
| PUT | no | yes | Full replacement (or create with client-chosen ID) | 200, 204, 201 |
| PATCH | no | not guaranteed | Partial update (JSON Merge Patch RFC 7396 or JSON Patch RFC 6902) | 200, 204 |
| DELETE | no | yes | Remove | 204, 200, 202 |
| QUERY | yes | yes | Safe query with body (IETF httpbis draft; first-class in OpenAPI 3.2) | 200 |

Rules:
- GET must not change state and should not carry a request body.
- POST that creates returns `201 Created` with `Location` and the representation (or a link).
- Use `202 Accepted` + status resource for asynchronous work.
- Use `PATCH` with a declared media type (`application/merge-patch+json`); document null semantics
  (in Merge Patch, `null` removes the member).
- `QUERY` support is limited in gateways, proxies and clients; prefer `GET` or `POST /searches`
  unless the whole toolchain supports it.

## 5. Request/response schema design

- Separate schemas: `PolicyCreate`, `PolicyUpdate`, `Policy` (read). Read-only fields (`id`,
  `createdAt`, `status`) never appear in create/update schemas → prevents mass assignment.
- Set `additionalProperties: false` on request schemas when the server rejects unknown fields; on
  response schemas leave it open so fields can be added compatibly.
- Mark `required` deliberately. Required response fields are a promise; required request fields are a
  burden on consumers.
- Nullability (OpenAPI 3.1): `type: [string, "null"]`. Distinguish *absent*, *null* and *empty*.
- Collections are wrapped: `{ "data": [...], "page": {...} }` — never a bare top-level array (cannot be
  extended compatibly).
- Use `format` (`uuid`, `date`, `date-time`, `email`, `uri`) and constraints (`maxLength`, `pattern`,
  `minimum`, `maxItems`). Every string and array in requests should have an upper bound (resource
  exhaustion, OWASP API4).
- Hypermedia links are optional; if used, use one format consistently.

## 6. Validation rules

Document per field: type, format, required, bounds, pattern, enum, cross-field rules (e.g.
`endDate > startDate`), and business rules (e.g. "coverage limit ≤ product maximum") with error code.
Syntactic validation → `400` or `422` (choose one convention and document it); business-rule
violations → `422`, state conflicts → `409`. Never rely on client-side validation.

## 7. Pagination, filtering, sorting

| Strategy | Use when | Trade-offs |
|---|---|---|
| Cursor (opaque `cursor`/`nextCursor`) | Large or frequently changing collections, infinite scroll | Stable under inserts; no random page access; cursor must be opaque and tamper-safe |
| Offset/limit | Small, stable collections; UIs needing page numbers | Simple; deep offsets are slow (`OFFSET n` scans) and unstable under concurrent writes |
| Keyset (`after=<sortKey>`) | Ordered by indexed key | Efficient; exposes sort-key semantics |

Always: default page size, **maximum page size** enforced server-side, deterministic sort with a
unique tiebreaker. Avoid `totalCount` by default on large tables (expensive `COUNT(*)`); make it
opt-in if needed.

Filtering: explicit allow-list of filterable fields (`?status=ACTIVE&effectiveFrom=2026-01-01`);
never pass raw filter expressions to the database. Sorting: `?sort=-createdAt,policyNumber` against an
allow-list of indexed fields. Field selection (`?fields=`) only if justified by payload size.

## 8. Errors (RFC 9457 Problem Details)

Media type `application/problem+json`. Members: `type` (URI identifying the problem type), `title`,
`status`, `detail`, `instance`; extension members allowed (e.g. `errors` for field-level validation,
`traceId`). RFC 9457 obsoletes RFC 7807.

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "2 fields are invalid.",
  "instance": "/v1/policies",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errors": [
    { "pointer": "/effectiveDate", "code": "DATE_IN_PAST", "detail": "must be today or later" }
  ]
}
```

Build an **error catalog**: `type` URI, status, title, when it occurs, whether retryable, client
action. Never leak stack traces, SQL, internal hostnames, or the existence of a resource to callers
who may not see it (return `404` rather than `403` when existence itself is sensitive).

Status code guide: 400 malformed · 401 missing/invalid credentials (with `WWW-Authenticate`) ·
403 authenticated but not allowed · 404 not found / hidden · 405 method not allowed · 406/415 media
type · 409 state conflict · 412 precondition failed (ETag) · 422 semantic validation · 428
precondition required · 429 rate limited (with `Retry-After`) · 500 unexpected · 502/503/504
dependency or availability problems (503 with `Retry-After` when known).

## 9. Idempotency and concurrency

- **Idempotent retries for POST:** `Idempotency-Key` request header (IETF httpapi draft). The server
  stores key + request fingerprint + response for a retention window (e.g. 24 h); same key with a
  different payload → `422`; concurrent request with the same key in progress → `409`. Scope keys
  per client/tenant.
- **Optimistic concurrency:** return `ETag`; require `If-Match` on `PUT`/`PATCH`/`DELETE` of
  contended resources; respond `412` on mismatch and `428` if the header is required but missing.
- **Natural idempotency:** prefer `PUT` with a client-generated ID when the client can own the ID.
- Document which operations are safe to retry and with what backoff.

## 10. Long-running and bulk operations

- `POST /claims-imports` → `202 Accepted`, `Location: /claims-imports/{jobId}`; the job resource
  exposes `status` (`PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED`), progress, result link, error Problem.
- Optional completion callbacks/webhooks (see `security-review.md` for webhook signing).
- Bulk endpoints: bounded batch size, per-item results, atomicity explicitly documented
  (all-or-nothing vs partial success).

## 11. Versioning and compatibility

Business API version ≠ OpenAPI document version (`openapi: 3.1.1` is the specification version;
`info.version` is your API version). Strategies:

| Strategy | Pros | Cons |
|---|---|---|
| URI major version `/v1/` | Visible, cache/gateway friendly, simplest routing | Encourages big-bang versions |
| Header / media type (`Accept: application/vnd.acme.v2+json`) | Clean URIs, per-resource evolution | Harder to test/cache, less discoverable |
| No version, strict compatibility + evolution | Fewest versions | Requires mature governance and contract testing |

Default recommendation: **major version in the URI, additive evolution within a major**, breaking
changes only in a new major with a deprecation/sunset policy (see `governance.md`). Detect breaking
changes with `scripts/compare_contracts.py`.

## 12. Design deliverables checklist

- [ ] Consumers, capabilities, assumptions (`ASM-###`), open questions (`Q-###`)
- [ ] Resource model + state machines (Mermaid allowed)
- [ ] Endpoint catalog: method, path, operationId, summary, auth/scopes, idempotency, success and
      error codes, pagination
- [ ] OpenAPI YAML, validated (report the actual validator output, or "not executed")
- [ ] Request/response examples for each operation (realistic, no real personal data)
- [ ] Authentication & authorization model (who can do what on which object)
- [ ] Error catalog (RFC 9457)
- [ ] ADRs for key decisions
- [ ] Security recommendations
- [ ] Test strategy and automation examples

Endpoint catalog format:

| # | Method | Path | operationId | Purpose | AuthZ (scope / rule) | Idempotent | Success | Errors |
|---|---|---|---|---|---|---|---|---|
| 1 | POST | /v1/policies | createPolicy | Create draft policy | `policies:write`; agent of same tenant | via `Idempotency-Key` | 201 | 400, 401, 403, 409, 422 |
