---
phase: 09-spec-lint-test-harness-foundations
plan: 01
subsystem: testing
tags: [json-schema, jsonschema, ruamel-yaml, python-packaging, recipe-validation]

# Dependency graph
requires:
  - phase: 03-recipe-format-v0.1
    provides: 5 committed recipes and docs/RECIPE-SCHEMA.md canonical spec
provides:
  - tools/ap.recipe.schema.json (Draft 2020-12 JSON Schema for ap.recipe/v0.1)
  - tools/pyproject.toml (Python packaging with runtime + dev deps)
  - load_recipe(), lint_recipe(), evaluate_pass_if() importable from tools/run_recipe.py
  - All 5 recipes bumped to apiVersion ap.recipe/v0.1
affects: [09-02, 09-03, 09-04, 10-error-taxonomy, 13-sha-pinning, 17-doc-runner-sync]

# Tech tracking
tech-stack:
  added: [jsonschema>=4.23 (Draft202012Validator), setuptools (pyproject.toml packaging)]
  patterns: [JSON Schema cross-field invariants via if/then/allOf, JSON normalization for ruamel-to-jsonschema bridge]

key-files:
  created:
    - tools/ap.recipe.schema.json
    - tools/pyproject.toml
  modified:
    - tools/run_recipe.py
    - recipes/hermes.yaml
    - recipes/openclaw.yaml
    - recipes/picoclaw.yaml
    - recipes/nullclaw.yaml
    - recipes/nanobot.yaml
    - .gitignore

key-decisions:
  - "JSON normalization via json.dumps(default=str) round-trip before schema validation to handle ruamel.yaml date coercion"
  - "setuptools.build_meta backend instead of setuptools.backends._legacy for Python 3.10.10 compat"

patterns-established:
  - "lint_recipe() normalizes through JSON round-trip before validation — all future lint consumers should use this function, not raw jsonschema"
  - "Cross-field invariants encoded as top-level allOf with if/then blocks — conditional required constraints only, property declarations stay in properties block"

requirements-completed: [D-01, D-02, D-03, D-04, D-05, D-16, D-17, D-19]

# Metrics
duration: 6min
completed: 2026-04-16
---

# Phase 9 Plan 01: Schema + Importable API Summary

**Draft 2020-12 JSON Schema with 5 cross-field invariants, 3 importable functions extracted from runner, Python packaging via pyproject.toml, all 5 recipes bumped to v0.1**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-16T02:54:05Z
- **Completed:** 2026-04-16T02:59:57Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Created `tools/ap.recipe.schema.json` (Draft 2020-12) with `additionalProperties: false` everywhere and 5 cross-field if/then invariants covering needle, regex, source, and image conditional requirements
- Extracted `load_recipe()`, `lint_recipe()`, and `evaluate_pass_if()` as importable functions from `tools/run_recipe.py` -- tests can now call them without Docker or CLI invocation
- Created `tools/pyproject.toml` enabling `pip install -e tools/[dev]` for editable development
- Bumped all 5 committed recipes from `ap.recipe/v0` to `ap.recipe/v0.1`
- All 5 recipes pass schema validation with zero errors
- Schema correctly rejects unknown keys, missing conditional fields, and invalid enum values

## Task Commits

Each task was committed atomically:

1. **Task 1: Create JSON Schema + pyproject.toml + bump recipes to v0.1** - `e2a90ac` (feat)
2. **Task 2: Extract load_recipe() and lint_recipe() into importable functions** - `cac394a` (feat)

**Additional commits:**
- `c9803d1` - fix(09-01): setuptools.build_meta backend for dev machine compat
- `8b01ff6` - chore(09-01): add Python generated file patterns to .gitignore

## Files Created/Modified
- `tools/ap.recipe.schema.json` - Draft 2020-12 JSON Schema for ap.recipe/v0.1, 317 lines
- `tools/pyproject.toml` - Python packaging with ruamel.yaml + jsonschema + pytest deps
- `tools/run_recipe.py` - Added load_recipe(), lint_recipe(), _load_schema(), _SCHEMA_PATH; main() delegates to load_recipe()
- `recipes/hermes.yaml` - apiVersion bumped to ap.recipe/v0.1
- `recipes/openclaw.yaml` - apiVersion bumped to ap.recipe/v0.1
- `recipes/picoclaw.yaml` - apiVersion bumped to ap.recipe/v0.1
- `recipes/nullclaw.yaml` - apiVersion bumped to ap.recipe/v0.1
- `recipes/nanobot.yaml` - apiVersion bumped to ap.recipe/v0.1
- `.gitignore` - Added __pycache__/, *.egg-info/, *.pyc patterns

## Decisions Made
- **JSON normalization in lint_recipe()**: ruamel.yaml's round-trip loader preserves YAML types (datetime.date for date scalars, CommentedMap for mappings) which jsonschema cannot type-check. Solution: `json.loads(json.dumps(recipe, default=str))` normalizes to plain Python dicts/strings before validation. This is invisible to callers.
- **setuptools.build_meta instead of _legacy backend**: The plan specified `setuptools.backends._legacy:_Backend` which requires setuptools>=68. Dev machine has 65.6.3. Switched to `setuptools.build_meta` which is the standard backend and works on >=65.0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruamel.yaml date coercion breaking schema validation**
- **Found during:** Task 2 (lint_recipe implementation)
- **Issue:** `ruamel.yaml` round-trip loader coerces YAML date values (e.g. `2026-04-15`) to `datetime.date` objects. jsonschema's type checker sees these as non-strings and rejects `metadata.recon_date`.
- **Fix:** Added JSON round-trip normalization (`json.loads(json.dumps(recipe, default=str))`) inside `lint_recipe()` before validation.
- **Files modified:** tools/run_recipe.py
- **Verification:** All 5 recipes pass lint; `metadata.recon_date` correctly validates as string matching `^\d{4}-\d{2}-\d{2}$`
- **Committed in:** cac394a (Task 2 commit)

**2. [Rule 1 - Bug] Fixed pyproject.toml build backend incompatibility**
- **Found during:** Task 1 verification (`pip install -e tools/[dev]`)
- **Issue:** `setuptools.backends._legacy:_Backend` module does not exist in setuptools 65.6.3 (requires >=68)
- **Fix:** Changed to `setuptools.build_meta` (standard backend, available since setuptools 40+)
- **Files modified:** tools/pyproject.toml
- **Verification:** `pip install -e tools/[dev]` completes successfully
- **Committed in:** c9803d1

**3. [Rule 3 - Blocking] Added Python generated files to .gitignore**
- **Found during:** Post-Task 2 (after pip install created __pycache__/ and *.egg-info/)
- **Issue:** `pip install -e` created untracked generated directories
- **Fix:** Added `__pycache__/`, `*.egg-info/`, `*.pyc` to .gitignore
- **Files modified:** .gitignore
- **Committed in:** 8b01ff6

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- JSON Schema at `tools/ap.recipe.schema.json` is ready for Plan 02 (--lint subcommand integration)
- `load_recipe()` and `lint_recipe()` are ready for Plan 03 (pytest test suite)
- `pyproject.toml` enables `pip install -e tools/[dev]` for the pytest harness in Plan 03
- All 5 recipes are at v0.1 and pass validation -- regression baseline established

## Self-Check: PASSED

All 9 files verified present. All 4 commits verified in git log.

---
*Phase: 09-spec-lint-test-harness-foundations*
*Completed: 2026-04-16*
