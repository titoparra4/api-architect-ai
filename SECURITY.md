# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private vulnerability
reporting ("Security" tab → "Report a vulnerability") on this repository. Include:

- affected file(s) and version or commit,
- a description of the issue and its impact,
- minimal reproduction steps (no real credentials or personal data).

We aim to acknowledge reports within 5 business days. This is a best-effort target, not a
contractual SLA.

## Scope

In scope:
- Scripts in `skills/api-architect-ai/scripts/` (e.g. unsafe parsing, path handling, secret leakage
  in generated reports).
- Skill instructions that could lead an agent to take unsafe actions, such as following embedded
  instructions, executing untrusted code, revealing secrets or running unauthorized tests.

Out of scope:
- Findings produced by the skill about *your* API. Those belong to your own security process.
- Vulnerabilities in third-party agents or the skills CLI. Report those to their maintainers.

## Design safeguards

- Scripts only read the files passed as arguments. They use `yaml.safe_load`, make no network
  calls, never execute analyzed code, and refuse to overwrite report files without `--force`.
- `generate_report.py` redacts common secret formats (JWTs, cloud keys, bearer tokens,
  credentials in URLs, `password=` pairs). Redaction is defense in depth, not a guarantee. Do not put
  secrets into assessment files.
- The skill is read-only by default. It asks for explicit approval before it modifies files or runs
  commands.
