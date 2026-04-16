---
phase: 10-error-taxonomy-timeout-enforcement
plan: 01
subsystem: testing
tags: [json-schema, jsonschema, taxonomy, timeout, enum, recipe-format]

# Dependency graph
requires:
  - phase: 09-spec-lint-test-harness-foundations
    provides: "tools/ap.recipe.schema.json v0.1 + lint/regression/roundtrip pytest harness"
provides:
  - "Schema surface that ACCEPTS optional {category, detail} on verified_cells[] and known_incompatible_cells[]"
  - "Full 11-value category enum (9 live + STOCHASTIC + SKIP reserved) declared twice so later phases need no schema migration"
  - "Optional build.timeout_s (default 900s per D-03) and build.clone_timeout_s (default 300s per D-03) integer fields"
affects:
  - 10-02 (recipe migration — will now be schema-valid after adding category/detail)
  - 10-03 (schema tightening — will flip required[] to include category/detail)
  - 10-04 (runner timeout enforcement — will read the new build.timeout_s / clone_timeout_s)
  - 15-stochasticity (STOCHASTIC enum slot pre-reserved, zero schema churn)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive-first JSON Schema evolution: add new properties WITHOUT touching required[] in step A, tighten required[] in step C after all data migrates in step B (per PATTERNS.md §CRITICAL SEQUENCING CONSTRAINT)"

key-files:
  created: []
  modified:
    - "tools/ap.recipe.schema.json (+52 lines, 0 deletions)"

key-decisions:
  - "Inline-duplicate the category/detail property definitions in both verified_cells and known_incompatible_cells rather than factoring into a $def — matches Phase 09's existing inline pattern and keeps diff readable"
  - "Ship the full 11-value enum now (including STOCHASTIC + SKIP reserved placeholders) so phases 15 and the later UX phase add no schema migration"
  - "Keep required: [model, verdict] UNCHANGED on both cell-type blocks — Plan 03 tightens this after Plan 02 migrates the 5 committed recipes (avoids the Pitfall 1 ordering trap)"

patterns-established:
  - "Step-A-of-three schema evolution: loosen first (accept new fields) → migrate data → tighten (require new fields). Each intermediate commit stays green."

requirements-completed: [D-01, D-03]

# Metrics
duration: 5min
completed: 2026-04-16
---

# Phase 10 Plan 01: Schema Loosening for Error Taxonomy + Build Timeouts Summary

**JSON Schema v0.1 loosened to accept optional `{category, detail}` on both cell-type blocks plus `build.timeout_s` / `build.clone_timeout_s`, with the full 11-value category enum pre-declared so phases 15 and later avoid schema migration.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-16T20:47:46Z (commit base ccea9cb)
- **Completed:** 2026-04-16T20:52:41Z (commit fed2a17)
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added optional `category` (11-value enum) + `detail` (free-form string) properties to `smoke.verified_cells.items.properties`
- Mirrored the same two optional properties on `smoke.known_incompatible_cells.items.properties` (inline duplication — matches Phase 09 pattern)
- Added optional `build.timeout_s` and `build.clone_timeout_s` integer fields (both `minimum: 1`) to `build.properties`
- Preserved the existing `required: [model, verdict]` on both cell blocks — intentional non-requirement so Plan 02's recipe migration lands before Plan 03's tightening

## Task Commits

Each task was committed atomically:

1. **Task 1: Schema loosening (category/detail optional + 11-value enum + build timeouts)** — `fed2a17` (feat)

## Files Created/Modified

- `tools/ap.recipe.schema.json` — +52 lines (0 deletions). Three additive edits:
  - `smoke.verified_cells.items.properties`: appended `category` (enum) + `detail` (string) after `notes`
  - `smoke.known_incompatible_cells.items.properties`: appended identical `category` + `detail` pair
  - `build.properties`: appended `timeout_s` + `clone_timeout_s` integers (both `minimum: 1`)

## Decisions Made

- **Full 11-value enum shipped now, not staged.** The enum contains all live + reserved values (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP) in that exact order. Phases 15 (STOCHASTIC emission) and the later UX phase (SKIP) require zero schema migration as a result.
- **Inline duplication over `$def` factoring.** The `category` + `detail` property definitions are duplicated verbatim in both cell-type blocks. This matches Phase 09's existing inline pattern, keeps the diff easy to review, and avoids introducing `$defs` / `$ref` indirection that Phase 09 deliberately avoided.
- **No `required[]` tightening.** Per D-04 + PATTERNS.md §CRITICAL ORDERING, making `category` / `detail` required here would red lint on all 5 committed recipes (they have no `category` field yet), blocking Plan 02's migration. Step A is permissive; Step C (Plan 03) tightens.

## Deviations from Plan

None — plan executed exactly as written. All three edits landed in a single atomic commit, verification gates passed first try (`python3 json.load` succeeded, 30/30 tests green on first invocation), grep counts matched success criteria exactly (`STOCHASTIC` x2, `clone_timeout_s` x1).

## Issues Encountered

None. The plan's `<read_first>` + precise anchor text for each edit made this a mechanical application of three textual insertions.

## User Setup Required

None — no external service configuration required.

## Verification Evidence

- `python3 -c "import json; json.load(open('tools/ap.recipe.schema.json'))"` → exit 0 (schema parses)
- Structural assertion `python3 -c "...assert vc['category']['enum'] == [...11 values in order]..."` → prints `schema OK`
- `pytest tests/test_lint.py tests/test_recipe_regression.py tests/test_roundtrip.py -x -q` → `30 passed in 1.06s`
- `grep -c '"STOCHASTIC"' tools/ap.recipe.schema.json` → `2` (matches ≥2 gate)
- `grep -c '"clone_timeout_s"' tools/ap.recipe.schema.json` → `1` (exact match)
- `grep -c '"category": {' tools/ap.recipe.schema.json` → `2` (one per cell-type block)
- `git diff --stat` → `1 file changed, 52 insertions(+)` — single file, no deletions

## Threat Flags

None. Per the plan's `<threat_model>`:

- T-10-01 (Tampering of enum): mitigated — enum is closed, unknown category strings rejected by Draft202012Validator.
- T-10-02 (Information disclosure via `detail`): accepted at schema layer — redaction is Plan 04's responsibility.

No new trust-boundary surface introduced by this plan (declarative JSON-only change, no Python code).

## Known Stubs

None. This plan intentionally adds optional-only properties; the "missing" `category`/`detail` values on the 5 committed recipes are NOT stubs — they are the intentional intermediate state that Plan 02 migrates and Plan 03 formalizes. Documented in PATTERNS.md §CRITICAL SEQUENCING CONSTRAINT.

## Next Phase Readiness

**Ready for Plan 10-02 (recipe migration).** The schema will now accept:

```yaml
verified_cells:
  - model: anthropic/claude-haiku-4-5
    category: PASS
    detail: ""
    verdict: PASS
    wall_time_s: 2.42
```

Plan 10-02 can update the 5 committed recipes (hermes, openclaw, picoclaw, nullclaw, nanobot) per D-04 without further schema work. After Plan 10-02 lands, Plan 10-03 flips the `required` arrays to include `category` (and optionally `detail`).

No blockers or concerns.

## Self-Check: PASSED

**Commit verification:**

```
$ git log --oneline | grep fed2a17
fed2a17 feat(10-01): loosen schema to accept optional category/detail + 11-value enum + build timeouts
```
FOUND: `fed2a17`

**File verification:**

- `tools/ap.recipe.schema.json` → FOUND (modified, +52 lines)
- `.planning/phases/10-error-taxonomy-timeout-enforcement/10-01-SUMMARY.md` → FOUND (this file, being written now)

All claims in this SUMMARY are backed by the verification evidence section above.

---
*Phase: 10-error-taxonomy-timeout-enforcement*
*Completed: 2026-04-16*
