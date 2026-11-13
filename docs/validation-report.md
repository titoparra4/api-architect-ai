# Validation Report — API Architect AI 1.0.0

Date: 2026-11-13 · Environment: macOS, Python 3.9.6, PyYAML 6.0.3, pytest 8.x,
openapi-spec-validator 0.7.x (isolated virtualenv). All results below come from commands that were
actually run.

## Passed checks

| # | Check (QA item) | Evidence |
|---|---|---|
| 1 | SKILL.md frontmatter and naming rules | `test_skill_structure`: name format/length/dir match, description 946 chars (≤ 1024), allowed fields only; frontmatter also parsed with `yaml.safe_load` |
| 2 | All referenced files exist | `test_all_referenced_paths_exist`, `test_internal_paths_in_references_exist`, `test_required_files_exist` |
| 3 | Progressive disclosure | SKILL.md is 176 lines (< 500); every `references/` and `assets/` file is linked from SKILL.md; long references have a table of contents |
| 4 | Example OpenAPI documents valid | Template and design example: `--strict --external` → 0 errors, 0 warnings, exit 0. Sample app contract: 0 errors, 17 lint warnings (intentional) |
| 5 | Score calculations | 15 scorecard tests: weighted average, normalization, bands at boundaries, invalid input. Template asset = 64.4 (5470/85, checked by hand) |
| 6 | Breaking-change detection | 23 comparison tests; fixture diff = 17 breaking, 4 potentially-breaking, 5 non-breaking, 2 info, exit 1; path-parameter rename not reported |
| 7 | Findings from incomplete evidence | Insufficient dimensions are excluded rather than scored 0; < 50 % weight → "indicative only", low confidence; security not evaluated → warning |
| 9 | Malicious instructions in inputs | Injected OpenAPI descriptions do not change the validator's verdict; a literal `$ref` inside an example is not resolved; the sample repository's injection comment is reported as `INJ-001` |
| 10 | Missing dependencies / runtime | YAML input without PyYAML → exit 3 with guidance; JSON input still works; `--external` without the package → exit 3; runtime check for Python < 3.9 → exit 3 |
| — | Secret redaction | Report generator removes the JWT and `password=` values in the fixture; `test_no_secrets_committed` scans the repository |
| — | Unit/integration suite | `python3 -m unittest discover -s tests` → **81 tests OK**; `python -m pytest` (venv) → **81 passed** |

## Failed checks

None remaining. During development, 3 tests initially failed: the SKILL.md description was 1109
characters (over the 1024 limit, now shortened), and two test filters were wrong. All three were
fixed and the full suite was re-run.

## Checks not executed

| Check | Reason |
|---|---|
| 8. Behavioral test of read-only repository analysis by a live agent | Needs agent-in-the-loop evaluation runs. Covered only statically (safety rules in SKILL.md, worked example) |
| 11. Installation via `npx skills add titoparra4/api-architect-ai` and skills.sh discovery | Repository not yet pushed to GitHub. Steps are documented in README |
| GitHub Actions workflow | Not run on GitHub yet. Its commands were run locally on Python 3.9 only |
| `examples/api-testing-example` pytest/Newman suites | Need a running implementation and an approved environment. Checked for syntax only; pytest skips the module (16 skipped) |
| Python 3.10–3.13 | Only 3.9 is available locally. The CI matrix covers the other versions |

## Remaining risks

- Skill activation and the quality of agent output depend on the host agent. The description and
  instructions have not been evaluated against an agent eval set.
- `compare_contracts.py` handles composition keywords (`oneOf`/`anyOf`/`allOf`) coarsely and cannot
  detect semantic changes.
- `validate_openapi.py` is not a full JSON Schema meta-validator unless `--external` is used.
  External `$ref`s are not resolved. 3.2 checks cover only the main structural additions.
- The skills CLI flags shown in README (`--skill`, `--list`) should be checked against the CLI
  version in use.
