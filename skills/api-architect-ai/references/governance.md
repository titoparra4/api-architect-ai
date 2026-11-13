# Mode E (part 2) — Governance, Lifecycle and Versioning

## Contents
1. Governance model
2. Versioning policy
3. Lifecycle, deprecation and sunset
4. Consumer-driven contract testing
5. API inventory
6. Style guide and automated linting
7. Change management checklist

---

## 1. Governance model

Governance should be **lightweight and automated**: a style guide, a contract-first or
contract-verified workflow, lint and breaking-change checks in CI, and a review step for new APIs
and breaking changes. Avoid central committees for routine additive changes.

Roles: API owner (accountable per API), platform/governance team (style guide, tooling), consumers
(contract tests, feedback).

## 2. Versioning policy

- **Separate concepts:** `openapi:` (specification version, e.g. `3.1.1`) vs `info.version` (API
  release, e.g. `1.4.0`) vs the major version exposed to clients (`/v1`).
- Use semantic versioning for `info.version`: MAJOR = breaking, MINOR = additive, PATCH =
  documentation/bug fix without contract change.
- Expose only the MAJOR version to clients (URI or media type). MINOR/PATCH changes must be
  backward compatible.
- Maximum concurrently supported majors (e.g. 2). New major only with a migration guide.

## 3. Lifecycle, deprecation and sunset

States: `design → preview/beta → GA → deprecated → sunset (retired)`.

- Mark deprecated operations/parameters/schemas with `deprecated: true` in OpenAPI and describe the
  replacement.
- Runtime signals: `Deprecation` response header (RFC 9745, value is a structured date such as
  `@1767225600`) and `Sunset` header (RFC 8594, HTTP-date). Add a `Link` with `rel="deprecation"` or
  `rel="sunset"` to the migration documentation.
- Deprecation window agreed per consumer type (e.g. internal 3 months, partners 6–12 months, mobile
  apps longer); communicate through changelog, consumer mailing list and developer portal.
- Measure usage of deprecated features (per client ID) before sunset; contact remaining consumers.
- After sunset: `410 Gone` (or `404`) with Problem Details pointing to the replacement.

## 4. Consumer-driven contract testing

- Consumers publish expectations (e.g. Pact); provider CI verifies them before release.
- Complement with provider-side OpenAPI validation (responses validated against the contract in
  integration tests) and bi-directional checks where tooling supports it.
- Breaking-change gate in CI: `scripts/compare_contracts.py base.yaml head.yaml --fail-on breaking`
  (optionally oasdiff as an external tool).
- Contract tests verify shape and semantics consumers depend on, not every provider field.

## 5. API inventory

Maintain an inventory (OWASP API9): API name, owner, environments and hosts, versions exposed,
lifecycle state, data classification, authentication, consumers, contract location. Compare inventory
with gateway routes and code routes periodically to detect shadow and zombie APIs.

## 6. Style guide and automated linting

Minimum rules to automate (Spectral or `scripts/validate_openapi.py` lint warnings):
- Every operation has `operationId`, `summary`, tags, at least one 4xx response and an error schema.
- Errors use `application/problem+json`.
- Security declared globally or per operation; public operations explicitly `security: []`.
- Collections paginated with a bounded `limit`.
- Request strings/arrays bounded (`maxLength`, `maxItems`).
- Naming conventions (kebab-case paths, camelCase properties).
- No `http://` server URLs except localhost.
- Examples for request and response bodies.

## 7. Change management checklist

- [ ] Contract updated first (contract-first) or regenerated and reviewed (code-first)
- [ ] Lint passes; breaking-change check run and result attached
- [ ] If breaking: new major or approved exception, deprecation plan, consumer communication
- [ ] Changelog entry with consumer impact
- [ ] Contract/regression tests updated
- [ ] Documentation and examples updated
- [ ] Observability for new operations (metrics, logs, traces)
