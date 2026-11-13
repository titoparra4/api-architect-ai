# OpenAPI Contract Engine

Use whenever an OpenAPI document is generated, reviewed or compared.

## Contents
1. Version selection
2. Required contract content
3. 3.1 specifics (vs 3.0)
4. 3.2 additions
5. Reusable components and conventions
6. Validation workflow
7. Breaking-change detection
8. Review checklist

---

## 1. Version selection

| Version | Use when | Notes |
|---|---|---|
| **3.1.x** (default) | New contracts; tooling supports it | JSON Schema 2020-12 alignment, `webhooks`, `type` arrays for null. Broad support in modern validators, linters, docs tools and generators — still verify the user's toolchain. |
| 3.2.x | Toolchain confirmed to support it and a 3.2 feature is needed (`QUERY` method, `querystring` parameters, hierarchical tags, streaming `itemSchema`, OAuth device flow) | Released in 2025; tooling support is still uneven. State the risk. |
| 3.0.x | Existing contracts or tools without 3.1 support (some gateways and generators) | `nullable: true`, `example` in schemas; no `webhooks`. Plan migration. |
| 2.0 (Swagger) | Legacy only | Recommend migration; bundled scripts do not validate it. |

The `openapi` field is the **specification** version. Never confuse it with `info.version` (the
API's own version).

## 2. Required contract content (when relevant)

- `info`: `title`, `version`, `description`, `contact`, `license` (3.1 allows SPDX `identifier`),
  `summary` (3.1+).
- `servers`: HTTPS URLs per environment.
- `tags`: declared with descriptions; each operation tagged.
- Operations: `operationId` (unique, camelCase verbNoun), `summary`, `description`, `parameters`,
  `requestBody`, `responses` (success + every relevant error), `security`, `deprecated` when applicable.
- `components`: `schemas`, `responses` (shared errors), `parameters` (pagination, IDs), `headers`
  (`Retry-After`, `Location`, `ETag`), `securitySchemes`, `examples`.
- Validation constraints on every request field (`maxLength`, `pattern`, `minimum`, `maxItems`,
  `enum`, `format`).
- Pagination parameters with bounded `limit` and a page envelope schema.
- RFC 9457 `Problem` schema used with `application/problem+json`.
- Examples for requests and responses (no real personal data, no real secrets).

## 3. OpenAPI 3.1 specifics (vs 3.0)

- Schemas are JSON Schema 2020-12 (dialect configurable via `jsonSchemaDialect`).
- Null: `type: [string, "null"]` instead of `nullable: true`.
- `exclusiveMinimum`/`exclusiveMaximum` are numbers, not booleans.
- `examples` (array) inside schemas; `example` is deprecated in schemas.
- `paths` is optional if `components` or `webhooks` is present; top-level `webhooks` added.
- In Schema Objects, keywords next to `$ref` are allowed; in Reference Objects only `summary` and
  `description` may override.
- `responses` is no longer required on an Operation (still strongly recommended).
- `pathItems` under `components`.
- File uploads: `contentMediaType`/`contentEncoding` instead of `format: binary`.

## 4. OpenAPI 3.2 additions (summary)

- `query` HTTP method on Path Items and `additionalOperations` for other methods.
- Parameter location `in: querystring` (entire query string as one schema).
- Hierarchical tags: `parent`, `kind`, `summary` on Tag Objects.
- Sequential/streaming media types with `itemSchema` (e.g. `text/event-stream`, JSON Lines).
- `$self` for document identity; OAuth 2.0 Device Authorization flow; `oauth2MetadataUrl`;
  `deprecated` on security schemes.

Verify each feature against the tools in use before relying on it.

## 5. Reusable components and conventions

```yaml
components:
  parameters:
    Limit:
      name: limit
      in: query
      schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
    Cursor:
      name: cursor
      in: query
      schema: { type: string, maxLength: 512 }
  responses:
    BadRequest:
      description: Malformed request
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
  schemas:
    Problem:
      type: object
      properties:
        type: { type: string, format: uri-reference, default: about:blank }
        title: { type: string }
        status: { type: integer, minimum: 100, maximum: 599 }
        detail: { type: string }
        instance: { type: string, format: uri-reference }
      additionalProperties: true
```

Full starting point: `assets/openapi-template.yaml`.

Security schemes:

```yaml
securitySchemes:
  oauth2:
    type: oauth2
    flows:
      authorizationCode:
        authorizationUrl: https://auth.example.com/oauth2/authorize
        tokenUrl: https://auth.example.com/oauth2/token
        scopes: { policies:read: Read policies, policies:write: Create and modify policies }
      clientCredentials:
        tokenUrl: https://auth.example.com/oauth2/token
        scopes: { policies:read: Read policies }
  mtls: { type: mutualTLS }
  apiKey: { type: apiKey, in: header, name: X-API-Key }
```

Declare public operations explicitly with `security: []` so omissions are visible.

## 6. Validation workflow

1. `python3 scripts/validate_openapi.py <spec> [--format json]` checks: supported version, required
   `info` fields, path syntax, declared/required path parameters, duplicate parameters, unique
   `operationId`, valid response codes, local `$ref` resolution, security requirements referencing
   defined schemes; and emits lint warnings (missing `operationId`/`summary`, no 4xx response, errors
   not using `application/problem+json`, GET with body, unbounded `limit`, non-HTTPS servers,
   undeclared tags).
2. For full JSON Schema meta-validation add `--external` (requires `openapi-spec-validator`).
3. Optionally run Spectral with the team ruleset.
4. Report the actual output. If tools could not run, say "not executed" and review manually.

## 7. Breaking-change detection

`python3 scripts/compare_contracts.py old.yaml new.yaml [--format json] [--fail-on breaking]`

Classifications: `breaking`, `potentially-breaking`, `non-breaking`, `info`. The script compares
operations by method and normalized path template, parameters, request bodies, responses, media
types, schemas (types, nullability, required, enums, constraints, properties, items) and security
requirements. It cannot detect semantic changes (same type, new meaning) — review those manually.

## 8. Review checklist

- [ ] Version suitable for the toolchain; `info.version` follows the versioning policy
- [ ] All operations have `operationId`, summary, tags, success and error responses
- [ ] Errors are RFC 9457 Problem Details
- [ ] Security declared per operation (scopes match the authorization model)
- [ ] Request schemas separate from response schemas; read-only fields excluded from requests
- [ ] Request inputs bounded; pagination bounded
- [ ] Nullable/optional/required intentional
- [ ] Examples present and valid against schemas
- [ ] Deprecations annotated with replacement and sunset
- [ ] Contract matches the implementation (drift check)
