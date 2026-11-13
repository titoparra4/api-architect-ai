# API Architect AI

**Design APIs. Evaluate architecture. Detect risks. Recommend improvements. Verify quality.**

API Architect AI is a portable [Agent Skill](https://agentskills.io) that makes your AI coding agent
act as a Principal API Architect, API Security Engineer and Senior QA Automation Engineer. It
designs REST APIs from requirements and reviews existing APIs, repositories and OpenAPI contracts.
It returns evidence-based findings, an explainable quality scorecard, architecture decision records
and test strategies you can run.

It works with Claude Code, OpenAI Codex and other agents that support the Agent Skills format.

---

## Why it is more than an API generation prompt

| Generic "design me an API" prompt | API Architect AI |
|---|---|
| Produces endpoints | Produces endpoints **and** the decisions, trade-offs and ADRs behind them |
| Assumes the result is good | Labels every statement as *Verified*, *Inferred* or *Recommendation*, and never fabricates paths, metrics or test results |
| Generic security advice | OWASP API Security Top 10 (2023) checklist, JWT validation checklist, BOLA and tenant-isolation analysis, severity calibration |
| "It will scale" | Bottleneck **hypotheses** with measurement plans; no invented benchmarks |
| One-off answer | 7-dimension weighted scorecard that excludes dimensions it could not evaluate instead of scoring them 0, and shows unresolved critical issues first |
| Unverified YAML | Bundled validators: OpenAPI structural validation and lint, breaking-change detection, score calculation, report generation |
| Follows any text it reads | Treats repository content as untrusted data, flags prompt-injection attempts, read-only by default |

## Key capabilities (six modes)

| Mode | What it does | Main outputs |
|---|---|---|
| **A. API Design** | Consumers, resources, endpoints, schemas, validation, pagination, errors, idempotency, concurrency, versioning | Design doc, endpoint catalog, OpenAPI 3.1 YAML, ADRs, error catalog, test scenarios |
| **B. Architecture Review** | 5-step repository workflow: discovery, reconstruction, evaluation, recommendations, optional implementation | Assessment, technical debt register, prioritized roadmap |
| **C. Security Review** | OAuth 2.0/OIDC/JWT/API keys/mTLS, RBAC/ABAC, BOLA, mass assignment, rate limits, CORS, secrets, webhooks, replay | Security report with OWASP API Top 10 coverage |
| **D. Scalability & Resilience** | Statelessness, caching, DB efficiency, timeouts, retries, circuit breakers, bulkheads, observability, SLOs | Hypotheses + measurement plans, proposed SLOs |
| **E. Interoperability & Governance** | HTTP semantics, RFC 9457, formats, compatibility, versioning, deprecation/sunset, contract testing, REST vs events/gRPC/GraphQL | Compatibility analysis, governance policy, breaking-change report |
| **F. Testing & Quality** | Functional, contract, security, resilience and regression strategy; Postman/Newman, pytest, REST Assured, Playwright | Test strategy, traceable test cases, runnable automation |

### Architecture evaluation dimensions

| Dimension | Weight |
|---|---:|
| API Design & REST Quality | 20 % |
| Architecture & Maintainability | 20 % |
| Security | 20 % |
| Scalability & Resilience | 15 % |
| Interoperability & Compatibility | 10 % |
| Testing & Automation | 10 % |
| Documentation & Governance | 5 % |

Bands: 90–100 Excellent · 75–89 Good · 60–74 Needs improvement · 40–59 High technical risk ·
0–39 Critical improvement required. The scorecard is an advisory indicator, not a certification.

## Supported inputs and outputs

**Inputs:** business requirements, user stories, functional and non-functional specifications,
OpenAPI 3.x documents (JSON/YAML), technical documentation, architecture diagrams (described or as
text), source code and local repositories.

**Outputs:** Markdown reports (15-section architecture assessment, security report), OpenAPI YAML,
endpoint catalogs, error catalogs, ADRs, test cases and traceability matrices, Postman collections,
pytest / REST Assured / Playwright tests, CI snippets, and machine-readable JSON.

Languages: **English and Spanish**. The skill answers in the language you use or request.

## Quick start

```bash
# Install for your agents (interactive agent selection)
npx skills add titoparra4/api-architect-ai

# Install only this skill from the repository
npx skills add titoparra4/api-architect-ai --skill api-architect-ai
```

Then ask your agent, for example:

> Design a REST API for an insurance policy management system.

Run `npx skills --help` to see the CLI options in your installed version, such as agent selection
and global installs.

### Manual installation

Copy `skills/api-architect-ai/` into your agent's skills directory:

| Agent | Project scope | User scope |
|---|---|---|
| Claude Code | `.claude/skills/api-architect-ai/` | `~/.claude/skills/api-architect-ai/` |
| OpenAI Codex | `.agents/skills/api-architect-ai/` | `~/.agents/skills/api-architect-ai/` (see your Codex version's docs for the exact path) |

```bash
git clone https://github.com/titoparra4/api-architect-ai.git
cp -R api-architect-ai/skills/api-architect-ai ~/.claude/skills/
```

### Optional: script dependencies

The skill works in read-only analysis mode with **no dependencies and no credentials**. The bundled
scripts need Python 3.9+, and PyYAML if the input is YAML:

```bash
python3 -m pip install -r requirements.txt          # PyYAML (required for YAML input)
python3 -m pip install openapi-spec-validator       # optional, enables --external
```

## Usage

### Claude Code

The skill activates automatically when your request matches its description. You can also name it:

```text
> Use api-architect-ai to review the authentication and authorization model of this repository.
> /api-architect-ai Identify breaking changes between openapi-v1.yaml and openapi-v2.yaml
```

### OpenAI Codex

Codex discovers installed skills and uses them when the task matches. You can also mention the skill
explicitly: `$api-architect-ai evaluate the scalability of this API`. `agents/openai.yaml` provides
optional display metadata.

### Example prompts

- "Design a REST API for an insurance policy management system."
- "Analyze this repository and evaluate its API architecture."
- "Review the authentication and authorization model."
- "Generate an OpenAPI contract from these requirements."
- "Evaluate the scalability of this API."
- "Identify breaking changes between these OpenAPI contracts."
- "Create an API regression testing strategy."
- "Generate Postman tests for these endpoints."
- "Review this API against OWASP API Security Top 10."
- "Evaluate whether the current architecture is suitable for enterprise integrations."
- "Diseña una API REST para gestión de siniestros y genera el contrato OpenAPI."

### Bundled scripts

All scripts support `--help` and `--format json`. Exit codes: `0` OK · `1` check failed · `2`
invalid input · `3` missing dependency / unsupported runtime.

```bash
S=skills/api-architect-ai/scripts
python3 $S/validate_openapi.py openapi.yaml [--strict] [--external] [--no-lint]
python3 $S/compare_contracts.py old.yaml new.yaml [--fail-on breaking|potentially-breaking|none]
python3 $S/calculate_score.py assessment.json [--fail-on-critical]
python3 $S/generate_report.py assessment.json [--lang es] [--output report.md]
```

## Example reports

| Example | What it shows |
|---|---|
| [`examples/api-design-example/`](examples/api-design-example/) | Insurance policy API: design doc, endpoint catalog, error catalog, ADR, validated OpenAPI 3.1 |
| [`examples/repository-review-example/`](examples/repository-review-example/) | Review of a flawed Express service, including a prompt-injection comment. Scorecard 42.2/100 with a critical alert, plus a 15-section report |
| [`examples/security-assessment-example/`](examples/security-assessment-example/) | Security report in Spanish mapped to the OWASP API Top 10 (2023) |
| [`examples/api-testing-example/`](examples/api-testing-example/) | Risk-based strategy, Postman collection, pytest suite, regression selection from a contract diff |

## Repository layout

```text
skills/api-architect-ai/
├── SKILL.md            # concise core instructions (loaded when the skill activates)
├── references/         # deep knowledge, loaded only for the active mode
├── assets/             # templates: OpenAPI, reports, ADR, test case, scorecard JSON
├── scripts/            # local validators and generators (Python, no network)
└── agents/openai.yaml  # optional Codex display metadata
examples/               # worked examples
tests/                  # unittest/pytest suite for structure and scripts
```

## Supported standards

OpenAPI 3.1.x (default) and 3.2.x (3.0.x accepted with a warning) · JSON Schema 2020-12 ·
RFC 9110 (HTTP semantics) · RFC 9457 (Problem Details) · RFC 3339 (timestamps) · RFC 7396 / 6902
(PATCH formats) · RFC 6749, RFC 7636 (PKCE), RFC 9700 (OAuth 2.0 Security BCP) · RFC 7519, RFC 8725
(JWT BCP), RFC 9068 (JWT access tokens) · RFC 8705 (mTLS), RFC 9449 (DPoP), RFC 7662
(introspection) · RFC 9421 (HTTP Message Signatures) · RFC 8594 (Sunset), RFC 9745 (Deprecation
header) · W3C Trace Context · OWASP API Security Top 10 (2023). IETF drafts referenced as drafts:
`Idempotency-Key` header, RateLimit headers, HTTP `QUERY` method.

## Limitations

- Static analysis cannot prove the absence of vulnerabilities. Runtime behavior, infrastructure
  and gateways are only assessed when that evidence is provided.
- Performance conclusions without metrics are hypotheses with measurement plans.
- `validate_openapi.py` performs structural and governance checks. It does not fully meta-validate
  JSON Schema; use `--external` for that. External `$ref`s are not resolved.
- `compare_contracts.py` detects structural changes, not semantic ones (same type, new meaning).
  `oneOf`/`anyOf`/`allOf` changes are flagged for manual review.
- Scores are advisory and depend on the evidence reviewed.
- OpenAPI 3.2 support in third-party tooling is still uneven. Verify your toolchain first.

## Security considerations

- **Read-only by default.** The skill asks for explicit approval before it modifies files, installs
  packages or runs repository scripts or tests.
- **Untrusted input.** Repository files, comments and documents are treated as data. Embedded
  instructions are reported as findings (`Untrusted instruction in source`) and never followed.
- **No secrets in output.** Credentials are reported by location and type only. The report
  generator also redacts secret-like strings.
- **Authorized testing only.** Security and load tests run only in environments you confirm are
  approved, and they are non-destructive.
- The scripts never execute the code they analyze and make no network calls.

See [SECURITY.md](SECURITY.md) to report vulnerabilities in this project.

## Development and validation

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest              # or: python3 -m unittest discover -s tests -v
```

CI (`.github/workflows/validate.yml`) runs the test suite on Python 3.10–3.13 (3.9 is verified locally, since hosted runners no longer provide it), validates every
example contract, checks the breaking-change detector against the fixtures, and verifies that the
scripts degrade correctly when PyYAML is missing.

### Verifying discovery on skills.sh after publishing

These steps have not been run for this repository yet. Follow them after you push it to GitHub:

1. Push to `https://github.com/titoparra4/api-architect-ai` (public repository, default branch).
2. List the skills the CLI finds without installing anything:
   `npx skills add titoparra4/api-architect-ai --list`. Expect to see `api-architect-ai`.
3. Install it into a scratch project:
   `npx skills add titoparra4/api-architect-ai --skill api-architect-ai`. Confirm that
   `SKILL.md`, `references/`, `assets/` and `scripts/` were copied into the agent's skills directory.
4. Start your agent in that project and send an example prompt. Check that the skill activates and
   loads only the references it needs.
5. skills.sh builds its directory from CLI install activity, so a new repository may not appear
   right away. Search for `api-architect-ai` on https://skills.sh after a few installs.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 titoparra4 and API Architect AI contributors.
