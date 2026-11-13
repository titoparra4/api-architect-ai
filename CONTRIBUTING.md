# Contributing to API Architect AI

Thank you for helping improve the skill. Contributions of knowledge, rules, tests and examples
are welcome.

## Principles

1. **Technical correctness first.** Cite the standard (RFC, OWASP, OpenAPI section) behind any new
   rule. Mark IETF drafts as drafts.
2. **Evidence over opinion.** New guidance must tell the agent what evidence to collect and how to
   verify a recommendation.
3. **Keep `SKILL.md` concise.** Put depth in `references/`, link it from the mode table, and keep it
   under 500 lines.
4. **No new runtime dependencies** in scripts without discussion. Scripts use the standard library,
   plus PyYAML for YAML input.
5. **Safety rules are non-negotiable.** Read-only by default, untrusted input, secret redaction and
   authorized testing only.

## Workflow

```bash
git checkout -b feature/my-change
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 skills/api-architect-ai/scripts/validate_openapi.py examples/api-design-example/openapi.yaml --strict
```

- Add or update tests for every script change. Use meaningful exit codes and document them in the
  script docstring.
- If you add a file under `references/` or `assets/`, link it from `SKILL.md`.
  `tests/test_skill_structure.py` enforces this.
- Update `CHANGELOG.md`.
- Never commit secrets, real personal data or real customer contracts. Use synthetic examples.

## Pull requests

Describe the problem, the standard or evidence behind the change, and how you validated it. Paste
the real test output; do not summarize results you did not run.

## Reporting issues

Use GitHub issues for bugs and proposals. For security issues, follow [SECURITY.md](SECURITY.md).
