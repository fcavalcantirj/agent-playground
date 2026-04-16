---
phase: 10-error-taxonomy-timeout-enforcement
plan: 03
subsystem: testing
tags: [json-schema, taxonomy, tightening, category, detail, required-flip]

# Dependency graph
requires:
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "Plan 10-01 loosened schema (optional category/detail + 11-value enum) — the required-array flip would reject all 5 recipes without 10-02's migration landing first"
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "Plan 10-02 migrated all 5 committed recipes with {category, detail} on every verified_cells[] and known_incompatible_cells[] entry — precondition for tightening"
  - phase: 09-spec-lint-test-harness-foundations
    provides: "test_lint / test_recipe_regression / test_roundtrip pytest harness — gates this tightening"
provides:
  - "tools/ap.recipe.schema.json smoke.verified_cells.items.required is now ['model','verdict','category','detail']"
  - "tools/ap.recipe.schema.json smoke.known_incompatible_cells.items.required is now ['model','verdict','category','detail']"
  - "Schema invariant closing the D-01/D-02 contract — future recipe authors cannot omit category+detail"
  - "Step C of the 5-step sequencing (PATTERNS.md §CRITICAL ORDERING) complete"
affects:
  - 10-04 (runner can now assume every lint-green recipe carries category/detail — no null-guard needed when reading migrated cells)
  - 10-05 (test_categories.py regression fixtures can rely on lint-time rejection of missing-category cells)
  - 15-stochasticity (when remapping hermes × gemini-2.5-flash back to STOCHASTIC, the tightening still enforces category presence — no loosening needed)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Enum-addition 3-step sequencing (PATTERNS.md §CRITICAL ORDERING + RESEARCH.md §Pitfall 1): optional-add → data-migrate → required-flip. Step C here closes the contract."
    - "Surgical required-array tightening via Edit with disambiguating context — the two target required arrays are textually identical, so the Edit old_string must include the enclosing verified_cells/known_incompatible_cells container line for uniqueness."

key-files:
  created: []
  modified:
    - "tools/ap.recipe.schema.json (+2/-2: two required-array flips)"
    - "tools/tests/conftest.py (+6/-1: minimal_valid_recipe fixture updated to honor tightened contract — Rule 3 blocking fix)"

key-decisions:
  - "Preserved existing scope boundary: known_incompatible_cells.items.verdict stays plain string (no enum) per PATTERNS.md §recipes/hermes.yaml note — STOCHASTIC legacy slack retained in that field even though Plan 02 removed all live STOCHASTIC values"
  - "Did NOT tighten verified_cells.items.verdict enum — stays ['PASS', 'FAIL'] — STOCHASTIC semantically belongs in `category`, not `verdict`, per D-02"
  - "Updated conftest.minimal_valid_recipe as a Rule 3 (blocking) fix — the fixture feeds TestLintPositive.test_minimal_valid_recipe_passes which is a precondition of the 'full pytest suite green' done criterion; no other test fixture required changes (broken_recipes YAMLs each keep their original single-violation shape, just with 2 extra 'missing category/detail' messages that don't disturb the `assert errors` checks or the uniqueness invariant)"

patterns-established:
  - "Rule 3 minimal-fixture-update pattern: when tightening a declarative contract, update ONLY the positive fixture that represents a valid recipe; negative fixtures (broken_recipes/*.yaml) can stay stale because they assert on `errors != []` and additional messages don't break that assertion"
  - "Two-edit surgical schema tightening: for JSON schema changes where the target strings are non-unique, disambiguate via the enclosing array-definition line (e.g. include `\"verified_cells\": { \"type\": \"array\", \"minItems\": 1, \"items\": { \"type\": \"object\", \"required\": ...` as the old_string anchor)"

requirements-completed: [D-01, D-02]

# Metrics
duration: 4min
completed: 2026-04-16
---

# Phase 10 Plan 03: Schema Tightening — category+detail REQUIRED on both cell types Summary

**Step C of the 5-step enum-addition sequencing: both `verified_cells.items.required` and `known_incompatible_cells.items.required` flipped from `["model","verdict"]` to `["model","verdict","category","detail"]`, closing the D-01/D-02 verdict-shape contract at the schema level.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-16T20:59:xx (after Plan 02 landed)
- **Completed:** 2026-04-16T21:03Z (commit `4dbba32`)
- **Tasks:** 1
- **Files modified:** 2 (schema + one test fixture)
- **Files created:** 0

## Accomplishments

- `tools/ap.recipe.schema.json` — two surgical `required`-array flips (schema lines 313 and 361)
- All 5 committed recipes (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) still lint-green under the tightened schema — confirmed via `python3 tools/run_recipe.py --lint-all` (5/5 PASS)
- Full pytest suite green: 48/48 passed (was 47/48 after schema edit alone; fixture update closed the gap)
- Negative path validated: a cell with just `{model, verdict}` is now rejected with two clear error messages (`'category' is a required property`, `'detail' is a required property`)
- Enum on `verified_cells.items.verdict` unchanged (`[PASS, FAIL]`) — STOCHASTIC remains a category, not a verdict, per D-02
- `known_incompatible_cells.items.verdict` still plain `"type": "string"` (no enum) — explicit scope boundary honored per PATTERNS.md

## Task Commits

1. **Task 1: Tighten required arrays on both cell types** — `4dbba32` (feat)

## Files Modified

- `tools/ap.recipe.schema.json` — Two required-array flips; no other schema surface touched
- `tools/tests/conftest.py` — `minimal_valid_recipe` fixture cell updated to include `category: PASS`, `detail: ""` (Rule 3 blocking fix)

## Decisions Made

- **Preserved known_incompatible_cells.verdict as plain string (no enum).** PATTERNS.md §"recipes/hermes.yaml" explicitly flags this as out-of-scope for Phase 10; the field keeps historical slack for recon notes even though Plan 02 removed all live STOCHASTIC values from verdict.
- **Did NOT add STOCHASTIC to verified_cells.verdict enum.** STOCHASTIC is a category, not a verdict — see D-02. The enum stays `[PASS, FAIL]`.
- **Updated conftest minimal_valid_recipe fixture** rather than loosening the tightening or adding a schema escape hatch. The fixture represents a recipe that `lint_recipe()` should return `[]` for — a contract-valid cell now REQUIRES category+detail, so the fixture must carry them.
- **Did NOT update broken_recipes/*.yaml fixtures.** Each is designed to produce a specific targeted violation via `assert errors != []`. The tightening adds two extra "missing category/detail" messages per fixture, which does not break `assert errors != []` and does not introduce duplicate messages (each fixture has a single cell), so the uniqueness invariant at test_lint.py:104 still holds. Empirically confirmed: 47/48 passed after schema edit alone (only the positive fixture failed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated `conftest.minimal_valid_recipe` fixture to honor tightened contract**
- **Found during:** Task 1 verification step (`pytest tests/test_lint.py tests/test_recipe_regression.py tests/test_roundtrip.py -x -q`)
- **Issue:** After the required-array flip, `TestLintPositive.test_minimal_valid_recipe_passes` failed with `["smoke.verified_cells.0: 'category' is a required property", "smoke.verified_cells.0: 'detail' is a required property"]`. The fixture's cell was `{"model": "test/model", "verdict": "PASS"}` — shape was valid pre-tightening, invalid post-tightening. The plan's `done` criterion mandates "Full pytest suite green" so this was blocking.
- **Fix:** Added `"category": "PASS"` and `"detail": ""` to the fixture's single verified_cells cell. Represents the canonical happy-path shape (category PASS + empty detail) that Plan 02's migration script produced for every PASS cell across the 5 recipes.
- **Files modified:** `tools/tests/conftest.py` (+6/-1 lines on the fixture)
- **Verification:** Full suite goes from 47/48 → 48/48. Only this one fixture required modification (empirically confirmed by running pytest without `-x`).
- **Committed in:** `4dbba32` (same commit as the schema tightening — they are a single semantic change: "tighten contract and update the single positive fixture that honors it")

---

**Total deviations:** 1 auto-fixed (Rule 3 blocking)
**Impact on plan:** Minimal. The plan's `files_modified` only listed `tools/ap.recipe.schema.json`, but the contract tightening necessarily invalidates any positive fixture that doesn't carry the new required fields. This is the test analog of Plan 02's recipe migration — Plan 02 migrated production recipes, this fix migrated the one test fixture Plan 02 didn't cover. No scope creep: one fixture, two new keys, same commit as the schema change.

## Issues Encountered

- None. Task 1's `action` was textually ambiguous for `Edit` (two identical `"required": ["model", "verdict"],` strings at lines 313 and 361) — resolved by using the enclosing container line (`"verified_cells": { "type": "array", "minItems": 1, "items": { "type": "object", "required": ...`) as the disambiguating anchor. This is now captured in patterns-established.

## Next Phase Readiness

- **10-04 (runner emits Verdict)** is now fully unblocked — every lint-green recipe is guaranteed to carry category+detail, so the runner's cell-reading paths don't need null-guards.
- **10-05 (test_categories.py)** gains schema-level enforcement: a regression test that creates a cell without category will now fail lint at the schema layer (not just at a Python assertion), closing the loop on D-01/D-02 enforcement.
- **Phase 15 (stochasticity)** remains unaffected — the tightening enforces presence, not value; when Phase 15 restores STOCHASTIC semantics for hermes × gemini-2.5-flash, it will re-map the `category` field value (already required) without any schema change.

## Self-Check: PASSED

Verified:
- `tools/ap.recipe.schema.json` exists and parses (Python json.load succeeds)
- `verified_cells.items.required == ['model','verdict','category','detail']` (Python assertion)
- `known_incompatible_cells.items.required == ['model','verdict','category','detail']` (Python assertion)
- `verified_cells.items.verdict.enum == ['PASS', 'FAIL']` unchanged (Python assertion)
- `known_incompatible_cells.items.verdict` has no `enum` key (Python assertion)
- Commit `4dbba32` exists in git log (`git log --oneline | grep 4dbba32`)
- All 5 committed recipes lint-green (`python3 tools/run_recipe.py --lint-all` → 5 PASS)
- Full pytest suite green (`pytest -x -q` → 48 passed)
- Negative path: cell missing category+detail is rejected with clear errors (empirically verified)

---
*Phase: 10-error-taxonomy-timeout-enforcement*
*Completed: 2026-04-16*
