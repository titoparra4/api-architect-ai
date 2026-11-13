# Mode C — API Security Review

Use this reference for authentication, authorization and security-control reviews of designs,
contracts and code. Security testing must be authorized, non-destructive and limited to approved
environments.

## Contents
1. Ground rules
2. OWASP API Security Top 10 (2023) checklist
3. Authentication review
4. JWT validation checklist
5. Authorization review
6. Security controls
7. Webhooks and replay protection
8. Severity calibration
9. Verification methods

---

## 1. Ground rules

- **Authentication ≠ authorization.** A valid token proves identity, not permission on a given object
  or function. Check both independently on every operation.
- Never print secrets; redact (`eyJhbGciOi…<redacted>`, `AKIA****************`).
- Static review findings are `Confirmed` only when the code path is unambiguous; otherwise
  `Suspected`, with the validation step needed.
- Never claim "secure". Say "no issues found in the reviewed scope for controls X, Y" and list what
  was not reviewed.

## 2. OWASP API Security Top 10 (2023) checklist

| ID | Risk | What to look for |
|---|---|---|
| API1 | Broken Object Level Authorization (BOLA) | Handlers loading objects by ID without checking ownership/tenant (`findById(id)` then return). Queries not scoped by tenant/owner. |
| API2 | Broken Authentication | Weak token validation, missing expiry, long-lived tokens, credentials in URLs, no brute-force protection on login/token endpoints, custom crypto. |
| API3 | Broken Object Property Level Authorization | Mass assignment (binding request body to entity), excessive data exposure (returning entities with internal/sensitive fields), no field-level permissions. |
| API4 | Unrestricted Resource Consumption | No max page size, unbounded strings/arrays, no upload limit, no rate limit/quota, expensive queries without limits, missing timeouts. |
| API5 | Broken Function Level Authorization | Admin endpoints reachable by regular users; authorization by obscure URLs; HTTP methods not covered by checks. |
| API6 | Unrestricted Access to Sensitive Business Flows | Automatable abuse (bulk quote scraping, promo abuse, mass sign-up) without anti-automation or business limits. |
| API7 | Server-Side Request Forgery | Server fetches user-supplied URLs (webhook targets, imports) without allow-list, scheme restriction, private/metadata IP blocking, DNS-rebinding protection. |
| API8 | Security Misconfiguration | Permissive CORS, verbose errors/stack traces, debug endpoints, missing TLS, default credentials, unpatched components. |
| API9 | Improper Inventory Management | Undocumented/shadow endpoints, old versions still exposed, non-production environments reachable with production data. |
| API10 | Unsafe Consumption of APIs | Trusting third-party responses without validation, blindly following redirects, disabled TLS verification, no timeouts on outbound calls. |

## 3. Authentication review

| Scenario | Recommended mechanism | Notes |
|---|---|---|
| End user via web/mobile app | OAuth 2.0 Authorization Code + PKCE (RFC 7636); OIDC for identity | Follow the OAuth 2.0 Security BCP (RFC 9700): no implicit grant, no password grant, exact redirect URI matching. |
| Service-to-service (internal) | Client Credentials with short-lived tokens, mTLS (RFC 8705 certificate-bound tokens) or workload identity (e.g. SPIFFE) | Per-service identities, not shared keys. |
| Partner / B2B | Client Credentials + mTLS or `private_key_jwt` client authentication | Scopes per partner; tenant binding. |
| Low-risk server-side integrations | API keys | Keys identify a client, they do not authenticate users. Header only, never URL; hashed at rest; scoped; rotated; rate limited per key. |
| High-value operations | Sender-constrained tokens (DPoP RFC 9449, or mTLS-bound) | Mitigates replay of stolen tokens. |

Check: access-token lifetime (minutes, not days), refresh-token rotation and revocation, revocation
path, introspection (RFC 7662) or local JWT validation with key rotation, brute-force protection,
credential storage (adaptive hashing for passwords, never plaintext).

## 4. JWT validation checklist (RFC 7519, RFC 8725, RFC 9068)

- [ ] Signature verified with keys from a trusted source (issuer JWKS via metadata), `kid`-based
      rotation and cache refresh.
- [ ] **Allowed algorithms pinned** (e.g. `RS256`, `ES256`, `PS256`); `alg: none` rejected; no
      algorithm confusion (HMAC verified with a public key).
- [ ] `iss` equals the expected issuer.
- [ ] `aud` contains this API's identifier (prevents token reuse across APIs).
- [ ] `exp` enforced; `nbf`/`iat` checked with small clock skew (≤ 60 s typical).
- [ ] `typ` checked where the profile requires it (`at+jwt` for RFC 9068 access tokens).
- [ ] Scopes/roles/claims drive authorization decisions — not just "token is valid".
- [ ] Tokens never logged and not accepted from query strings.
- [ ] ID tokens are not accepted as access tokens.
- [ ] Symmetric secrets (if HS256) are strong, not hard-coded, rotated.

Code smells: `verify_signature: False`, `verify=False`, `ignoreExpiration: true`, missing
`audience`/`issuer` options, `algorithms` not restricted.

## 5. Authorization review

- **Model:** RBAC (roles), ABAC (attributes: tenant, owner, region, amount), ReBAC (relationships).
  Recommend ABAC/ReBAC when ownership and tenancy drive access; RBAC alone usually cannot express
  object-level rules.
- **Object level (BOLA):** every read/write by ID must verify the caller may access *that* object.
  Prefer scoping the query (`WHERE id = ? AND tenant_id = ?`) over fetch-then-check.
- **Property level:** response DTOs per role; write allow-lists; sensitive fields excluded by default.
- **Function level:** deny by default; admin functions under explicit policy; all HTTP methods covered.
- **Least privilege:** fine-grained scopes (`policies:read`, `policies:write`); minimal service accounts.
- **Tenant isolation:** tenant derived from the verified token, never from a client header/body alone;
  enforced at the data layer (row-level security or mandatory tenant filter); cache keys include the
  tenant; background jobs carry tenant context; tests prove cross-tenant access is denied.
- Centralize policy evaluation (policy layer, OPA/Cedar, framework guards) and test it.

## 6. Security controls

| Control | Check |
|---|---|
| Input validation | Schema validation at the edge, bounds on all inputs, content-type enforcement, unknown fields rejected where appropriate. |
| Mass assignment | No direct binding of request bodies to persistence entities; explicit DTOs/allow-lists. |
| Injection | Parameterized queries/ORM; no string-built SQL/NoSQL/LDAP/OS commands; safe deserialization. |
| Rate limiting & quotas | Per client/key/user and per tenant; stricter on auth and expensive endpoints; `429` + `Retry-After`. |
| Resource exhaustion | Max request size, page size, array length, ReDoS-safe regexes, query complexity limits, timeouts. |
| Sensitive data exposure | Minimal responses; PII masking in logs; no secrets in URLs; `Cache-Control: no-store` on sensitive responses. |
| CORS | Explicit origin allow-list; never reflect arbitrary `Origin` together with `Access-Control-Allow-Credentials: true`; `*` only for public, credential-less APIs. |
| TLS | TLS 1.2+ (1.3 preferred); HSTS on browser-facing hosts; certificate validation on outbound calls. |
| Token expiry & rotation | Short access tokens, refresh rotation, revocation, signing-key rotation. |
| Secrets management | Secret manager/KMS; no secrets in repo, images or logs; rotation procedure. |
| Audit logging | Who, what, which object, when, from where, outcome; tamper-evident storage; no secrets. |
| Error handling | Generic messages to clients; details in logs with correlation ID. |
| Dependency hygiene | SCA in CI, pinned versions, update policy. |

## 7. Webhooks and replay protection

Outbound webhooks (you send):
- Sign payloads: HMAC-SHA256 over `timestamp + "." + rawBody` with a per-subscriber secret, or HTTP
  Message Signatures (RFC 9421). Send timestamp and unique event ID headers.
- Validate subscriber URLs against SSRF (HTTPS only; block private, loopback, link-local and cloud
  metadata ranges; re-resolve DNS at send time).
- Retries with exponential backoff and jitter; dead-letter after N attempts; document at-least-once
  delivery (consumers must deduplicate).

Inbound webhooks (you receive):
- Verify the signature with a constant-time comparison **over the raw body** before parsing.
- Reject timestamps outside a tolerance window (e.g. 5 minutes); store event IDs to reject replays.
- Acknowledge quickly (`2xx`) and process asynchronously.

Replay protection for APIs: short token lifetimes, sender-constrained tokens, `jti`/nonce tracking for
high-value operations, idempotency keys for state-changing POSTs.

## 8. Severity calibration

| Severity | Typical examples |
|---|---|
| Critical | Unauthenticated access to sensitive data or admin functions; confirmed BOLA on PII/financial data; JWT signature not verified; hard-coded production credentials; injection reachable without authentication. |
| High | BOLA requiring authentication; missing `aud`/`iss` validation; tenant isolation relying on a client header; mass assignment of privileged fields; no rate limit on authentication endpoints. |
| Medium | Permissive CORS without credentials; verbose errors leaking internals; no max page size; long-lived tokens; no audit log on sensitive operations; untrusted instruction embedded in repository content. |
| Low | Missing hardening headers on JSON APIs; inconsistent 401/403 semantics; minor information disclosure (framework version). |
| Informational | Defense-in-depth suggestions, documentation gaps. |

Adjust for exploitability, exposure (internet vs internal), data sensitivity and compensating
controls — and state the adjustment.

## 9. Verification methods

| Finding type | Verification (non-destructive, approved environment) |
|---|---|
| BOLA | Two users in different tenants; user A requests user B's object ID → expect `404`/`403`; keep as a regression test. |
| Function-level authZ | Regular-user token on admin routes and all methods → expect `403`. |
| JWT validation | Tokens with wrong `aud`, wrong `iss`, expired, `alg: none`, tampered signature → expect `401`. |
| Mass assignment | Send read-only/privileged fields (`role`, `status`, `tenantId`) → expect `400/422` or ignored; verify persisted state unchanged. |
| Rate limiting | Controlled burst slightly above the limit in a test environment → expect `429` with `Retry-After`. |
| Data exposure | Schema-based response assertions: no properties outside the allow-list. |
| CORS | Preflight from a disallowed origin → no `Access-Control-Allow-Origin`. |
| Secrets | Secret scanner in CI (e.g. gitleaks); rotation confirmed by the owner. |

Use `assets/security-report.md` for the report.
