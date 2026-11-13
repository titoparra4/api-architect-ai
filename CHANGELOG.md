# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-13

### Added
- `api-architect-ai` skill (`SKILL.md`) with six modes: API design, architecture review, security
  review, scalability & resilience, interoperability & governance, testing & quality engineering.
- Ten reference guides loaded on demand (progressive disclosure).
- Assets: OpenAPI 3.1 template, 15-section architecture report, security report, ADR, test case
  and machine-readable scorecard templates.
- Scripts: `validate_openapi.py`, `compare_contracts.py`, `calculate_score.py`,
  `generate_report.py` (standard library + PyYAML; documented exit codes).
- Examples: API design, repository review (with prompt-injection case), security assessment
  (Spanish), API testing (Postman, pytest, regression selection).
- Test suite (unittest/pytest) and GitHub Actions validation workflow (Python 3.10–3.13).
