---
phase: 18-schema-maturity
plan: 01
subsystem: testing
tags: [tdd, pytest, json-schema, meta-schema, self-validation, regression-gate, draft-2020-12]

requires:
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "category enum baseline (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP) that Test 3 indirectly validates via lint_recipe"
provides:
  - "tools/tests/test_schema_selfcheck.py — self-validation gate enforcing D-10.1/D-10.2/D-10.3 as pytest"
  - "Reusable _collect_refs helper for schema-tree $ref walks"
  - "Always-correct conditional pattern for $defs well-formedness + reachability"
affects: [18-02-schema-refactor, 18-03-spec-sync]

tech-stack:
  added: []
  patterns:
    - "Conditional TDD seam: test asserts `IF X THEN Y` so it passes vacuously today and becomes load-bearing once X exists"

key-files:
  created:
    - tools/tests/test_schema_selfcheck.py
  modified: []

key-decisions:
  - "Chose always-correct conditional over xfail-now-pass-later for Test 2 ($defs well-formedness). Vacuous-true today, load-bearing after Plan 02 — cleaner TDD seam, no marker bookkeeping."
  - "Test 3 intentionally duplicates tools/tests/test_recipe_regression.py. The duplication is load-bearing: D-10 requires the full 3-test contract visible in one file for a reviewer of Plan 02's diff."
  - "Reachability test walks `$ref` strings recursively using a pure dict/list visitor (no eval, no dynamic import). Mitigates T-18-01."

patterns-established:
  - "Conditional-contract TDD: tests shaped as IF-THEN activate when the schema evolves; no RED-then-GREEN churn required."
  - "Self-check module colocates D-10 subcontracts — future D-10 extensions land in this same file."

requirements-completed: [D-10]

duration: ~8min
completed: 2026-04-16
---

# Phase 18 Plan 01: Schema Self-Validation Gate Summary

**Added `tools/tests/test_schema_selfcheck.py` — three pytest-native assertions pinning the schema as a valid draft-2020-12 JSON Schema, with conditional `$defs` well-formedness + reachability and the 5-recipe regression gate restated at the self-check layer.**

## Performance

- **Duration:** ~8 min wall-clock (read-context + write-file + verify + commit)
- **Started:** 2026-04-16T22:25:00Z (approx — matched to parent agent spawn)
- **Completed:** 2026-04-16T22:33:04Z
- **Tasks:** 1 (of 1 in this plan)
- **Files modified:** 1 created, 0 modified

## Accomplishments

- `test_schema_validates_against_draft_2020_12_meta_schema` — `Draft202012Validator.check_schema()` is the canonical API; raises `jsonschema.SchemaError` on any meta-schema violation. Green today (schema declares `$schema: .../draft/2020-12/schema` at line 2).
- `test_defs_are_well_formed_and_reachable` — conditional IF/THEN. If `$defs` exists and is non-empty, every entry is a `dict` declaring at least one shape keyword (`type`/`oneOf`/`$ref`/`enum`/`const`/`allOf`/`anyOf`) AND every entry name appears in a `#/$defs/<name>` `$ref` somewhere in the schema tree. Vacuously green today. Becomes load-bearing when Plan 02 lands `$defs.v0_1` + `$defs.category`.
- `test_all_committed_recipes_validate_against_schema` — parametrized over `recipes/*.yaml` with `p.stem` ids (hermes, nanobot, nullclaw, openclaw, picoclaw). 5 green test cells.
- `_collect_refs` helper — pure dict/list traversal collecting every `$ref` string in the schema tree. No `eval`, no dynamic imports; mitigates T-18-01 per the plan's threat model.

## Task Commits

1. **Task 1: Create test_schema_selfcheck.py with 3 tests (meta-schema, $defs well-formedness, 5-recipe regression)** — `098bc61` (test)

_No REFACTOR commit — first draft passed verification with no cleanup needed._

## Files Created/Modified

- `tools/tests/test_schema_selfcheck.py` (139 lines) — the D-10 self-check contract.

## Decisions Made

- **Always-correct over xfail (deviation from PLAN.md body; honoring executor directive).** The plan body spec'd Test 2 as a RED canary that fails today and goes GREEN after Plan 02. The executor prompt's `<parallel_execution>` block overrode this with an explicit recommendation: "tests that are always-correct, not xfail-now-pass-later." Implementation: Test 2 is a conditional (`if not defs: return`). Passes today because `$defs` is absent from the current schema. Becomes load-bearing the moment Plan 02 introduces `$defs.v0_1` or `$defs.category` — at that point the well-formedness check AND the reachability check both activate. No `xfail` markers, no strict=False bookkeeping, no green-then-red-then-green churn. The TDD seam is still there — it's just shaped as "contract activates when prerequisite lands" rather than "test flips color when prerequisite lands."
- **Test 3 duplicates `test_recipe_regression.py` on purpose.** D-10 requires the full 3-test contract visible in one file so a Plan 02 reviewer can read the regression gate in one place.

## Deviations from Plan

**1. [Executor directive override] Test 2 shape — conditional, not RED canary.**
- **Found during:** pre-task reading (executor's `<parallel_execution>` block)
- **Issue:** Plan body `<behavior>` for Test 2 specified a hard assertion `assert "$defs" in schema` that would fail today; executor directive explicitly preferred an always-correct conditional.
- **Fix:** Wrote Test 2 with `defs = schema.get("$defs"); if not defs: return` vacuous-pass guard. Well-formedness + reachability checks run only when `$defs` is present.
- **Files modified:** `tools/tests/test_schema_selfcheck.py`
- **Verification:** All 7 test cells green on current schema (1 meta-schema + 1 conditional $defs + 5 recipes). Simulated a post-Plan-02 schema with `$defs.v0_1` + `$defs.category` + a hypothetical `orphan` — the logic correctly flagged `orphan` as unreachable, proving the activation point works.
- **Committed in:** `098bc61` (part of task commit)

---

**Total deviations:** 1 directive-driven shape change ("always-correct conditional" recommendation from executor prompt)
**Impact on plan:** Positive — delivers the same D-10 contract with a cleaner TDD seam. Plan 02 executor will NOT need to flip this test from RED to GREEN; they need only land the `$defs` refactor and the test activates automatically.

## Issues Encountered

None.

## User Setup Required

None — this plan is pure pytest addition with no external service or environment configuration.

## Next Phase Readiness

- **Plan 02 (schema refactor)** can proceed. Test 2 is already on disk shaped to activate when `$defs.v0_1` + `$defs.category` land. The Plan 02 executor's verification step should include `cd tools && pytest tests/test_schema_selfcheck.py -v` and confirm all 7 test cells remain green after the refactor.
- **Plan 03 (spec markdown sync)** unaffected — this plan touched no markdown.
- No blockers, no deferred items.

## TDD Gate Compliance

Plan frontmatter declares `type: execute` (not `type: tdd`) but the single task is marked `tdd="true"`. Only the RED-equivalent commit is landed here: the test exists in `test()` form at `098bc61`. GREEN transition for Test 2 is a Plan 02 deliverable, by design.

## Self-Check: PASSED

- [x] `tools/tests/test_schema_selfcheck.py` exists (139 lines) — verified via `ls`.
- [x] Commit `098bc61` exists — verified via `git log`.
- [x] Test file contains all required tokens: `Draft202012Validator`, `check_schema`, `$defs`, `reachable`, `RECIPE_FILES`, `draft-2020-12`.
- [x] 7/7 test cells pass on current schema (1 meta-schema + 1 conditional-$defs-vacuous + 5 recipe parametrized).
- [x] Pre-existing suites still green: `test_lint.py` + `test_recipe_regression.py` + `test_roundtrip.py` = 30 passed.
- [x] Zero edits to `tools/ap.recipe.schema.json`, `tools/run_recipe.py`, `recipes/*.yaml`, `docs/RECIPE-SCHEMA.md`.

---
*Phase: 18-schema-maturity*
*Plan: 01*
*Completed: 2026-04-16*
