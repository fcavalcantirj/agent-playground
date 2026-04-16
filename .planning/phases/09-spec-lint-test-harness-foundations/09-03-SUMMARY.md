---
phase: 09-spec-lint-test-harness-foundations
plan: 03
subsystem: testing
tags: [pytest, jsonschema, ruamel-yaml, pass-if-verbs, recipe-lint, round-trip]

# Dependency graph
requires:
  - phase: 09-01
    provides: "JSON Schema (ap.recipe.schema.json), extracted runner functions (evaluate_pass_if, lint_recipe, load_recipe)"
provides:
  - "Complete pytest test suite under tools/tests/ with 48 tests across 4 modules"
  - "12 broken recipe fragments for lint negative testing"
  - "conftest.py with 5 reusable fixtures (yaml_rt, schema, mock_subprocess, minimal_valid_recipe, broken_recipes_dir)"
  - "Regression gate: all 5 committed recipes pass lint and round-trip losslessly"
affects: [10-error-taxonomy-timeout-enforcement, 11-linux-host-owner-uid-correctness, 12-provenance-output-bounds, 13-determinism-sha-pinning, 14-isolation-limits-default-deny, 15-stochasticity-multi-run-determinism, 16-dead-verb-coverage, 17-doc-runner-sync-check]

# Tech tracking
tech-stack:
  added: [pytest]
  patterns: [parametrized-recipe-glob, broken-recipe-fragment-testing, yaml-round-trip-fidelity-check]

key-files:
  created:
    - tools/tests/__init__.py
    - tools/tests/conftest.py
    - tools/tests/test_pass_if.py
    - tools/tests/test_lint.py
    - tools/tests/test_roundtrip.py
    - tools/tests/test_recipe_regression.py
    - tools/tests/broken_recipes/missing_api_version.yaml
    - tools/tests/broken_recipes/wrong_api_version.yaml
    - tools/tests/broken_recipes/missing_name.yaml
    - tools/tests/broken_recipes/invalid_name_chars.yaml
    - tools/tests/broken_recipes/missing_build_mode.yaml
    - tools/tests/broken_recipes/unknown_build_mode.yaml
    - tools/tests/broken_recipes/missing_needle.yaml
    - tools/tests/broken_recipes/missing_regex.yaml
    - tools/tests/broken_recipes/unknown_top_level_key.yaml
    - tools/tests/broken_recipes/missing_smoke_prompt.yaml
    - tools/tests/broken_recipes/missing_verified_cells.yaml
    - tools/tests/broken_recipes/image_pull_no_image.yaml
  modified: []

key-decisions:
  - "Used ruamel.yaml safe loader for broken recipe fragments in test_lint.py (no comments needed, simpler)"
  - "Added case_insensitive needle test to test_pass_if.py beyond plan minimum (ensures full coverage of _contains helper)"

patterns-established:
  - "broken-recipe-fragment: one YAML per schema violation, base template minus one field, confirms isolated error"
  - "parametrized-recipe-glob: test discovers recipes via Path.glob, auto-parametrizes, new recipes get tested automatically"
  - "round-trip-fidelity: load + dump must produce byte-identical output to prevent spurious --write-back diffs"

requirements-completed: [D-11, D-12, D-13, D-14, D-15, D-18]

# Metrics
duration: 4min
completed: 2026-04-16
---

# Phase 09 Plan 03: Pytest Test Harness Summary

**48-test pytest suite covering pass_if verbs, lint negatives with 12 broken fragments, YAML round-trip fidelity, and recipe regression gate -- all passing in 1.09s**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-16T03:03:48Z
- **Completed:** 2026-04-16T03:07:25Z
- **Tasks:** 2/2
- **Files created:** 18

## Accomplishments
- All 5 pass_if verbs (response_contains_name, response_contains_string, response_not_contains, response_regex, exit_zero) have PASS + FAIL + edge-case coverage across 18 tests
- 12 broken recipe fragments each targeting exactly one schema violation, all confirmed to produce lint errors
- All 5 committed recipes (hermes, openclaw, picoclaw, nullclaw, nanobot) pass YAML round-trip losslessly
- All 5 committed recipes pass the regression lint gate
- Suite completes in 1.09s (target was <10s)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create conftest.py fixtures and broken recipe fragments** - `fb8b6e2` (test)
2. **Task 2: Create all 4 test modules (pass_if, lint, roundtrip, regression)** - `8ab909d` (test)

## Files Created/Modified
- `tools/tests/__init__.py` - Package marker (empty)
- `tools/tests/conftest.py` - 5 shared fixtures: yaml_rt, schema, mock_subprocess, minimal_valid_recipe, broken_recipes_dir
- `tools/tests/test_pass_if.py` - 18 unit tests for all 5 evaluate_pass_if verbs
- `tools/tests/test_lint.py` - 20 tests: positive lint, apiVersion, additionalProperties, cross-field invariants, 12 parametrized broken recipes
- `tools/tests/test_roundtrip.py` - 5 parametrized round-trip tests (one per committed recipe)
- `tools/tests/test_recipe_regression.py` - 5 parametrized lint-gate tests (one per committed recipe)
- `tools/tests/broken_recipes/*.yaml` - 12 broken recipe fragments (missing_api_version, wrong_api_version, missing_name, invalid_name_chars, missing_build_mode, unknown_build_mode, missing_needle, missing_regex, unknown_top_level_key, missing_smoke_prompt, missing_verified_cells, image_pull_no_image)

## Decisions Made
- Used `YAML(typ="safe")` in test_lint.py for loading broken recipes -- no comment preservation needed, simpler than round-trip loader
- Added one extra test case (case_insensitive needle in response_contains_string) beyond the plan minimum to ensure the shared `_contains` helper is fully exercised

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Test harness is complete and gates all downstream phases (10-17)
- Any future runner change must pass `pytest tools/tests/ -v`
- New recipes added to `recipes/` will be automatically picked up by the parametrized round-trip and regression tests

## Self-Check: PASSED

- All 18 created files exist on disk
- 12 broken recipe fragments confirmed
- Both task commits (fb8b6e2, 8ab909d) found in git log
- SUMMARY.md exists at expected path

---
*Phase: 09-spec-lint-test-harness-foundations*
*Completed: 2026-04-16*
