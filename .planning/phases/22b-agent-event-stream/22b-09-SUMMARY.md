---
phase: 22b-agent-event-stream
plan: 09
subsystem: testing

tags: [json-schema, lint, recipe-format, regression-guard, jsonschema]

# Dependency graph
requires:
  - phase: 22b-agent-event-stream
    provides: "Plan 22b-06 added direct_interface + event_log_regex to all 5 recipes; Plan 22b-08 (gap closure) carries event_source_fallback for nullclaw + openclaw"
provides:
  - "tools/ap.recipe.schema.json v0.2 schema extended with direct_interface_block + event_source_fallback $defs (oneOf-discriminated)"
  - "event_log_regex declaration on channel_entry (object map: kind name → regex string OR null)"
  - "Spike C 2026-04-19 retrofits: boot_wall_s/first_reply_wall_s relaxed to oneOf:[number, ~N string]; PASS_WITH_FLAG appended to verdict + channel_category enums; category dropped from channel_verified_cell required; spike_artifact field declared; api_key_by_provider declared on v0_2 process_env"
  - "TestLintRealRecipes regression-guard test class — 5 parametrized + 2 sanity tests assert all 5 committed recipes lint clean against the v0.2 schema"
affects: [22b-10-and-beyond, format-v0.1-consolidation, sc-03-gate, recipe-additions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JSON Schema oneOf discrimination via const kind enum (direct_interface_block, event_source_fallback)"
    - "Real-recipe regression-guard test class — explicit fixture list (not glob) to force code review on recipe additions"
    - "Spike-evidence-driven schema widening (don't rewrite recipes; widen the schema where 5 committed recipes empirically diverged from the original spec)"

key-files:
  created: []
  modified:
    - "tools/ap.recipe.schema.json (1356 → 1574 lines; +227 -9; 9 schema changes — 2 new $defs + 3 new property refs + 4 retrofit hunks)"
    - "tools/tests/test_lint.py (107 → 156 lines; +49; new TestLintRealRecipes class)"
    - "tools/tests/conftest.py (238 → 256 lines; +18; new real_recipes fixture)"
    - ".planning/phases/22b-agent-event-stream/deferred-items.md (DI-05 added — pre-existing test_roundtrip failures on openclaw + picoclaw)"

key-decisions:
  - "Spike C bug A1+A2 fix (drop outer additionalProperties:false on direct_interface_block + event_source_fallback) — JSON Schema does not propagate oneOf-branch property declarations to the parent's known-properties set; outer additionalProperties:false would reject `kind` and `spec` BEFORE oneOf branches validate. Inner branches retain additionalProperties:false which IS the actual closure mechanism."
  - "Spike C B5 — schema-relax path for nanobot[0] missing category (drop category from channel_verified_cell.required) instead of recipe-edit path; preserves the 5-recipes-no-rewrite project memory rule"
  - "Inline fix during Task 1 verification: add `notes:{type:string}` to each event_source_fallback oneOf branch's properties — outer-only `notes` declaration was rejected by oneOf branches' own additionalProperties:false (JSON Schema oneOf validates whole instance against each subschema independently). The plan's hoisted-notes intent required per-branch declaration, not parent-level only."

patterns-established:
  - "Pattern: When a JSON Schema $def uses oneOf with kind discrimination, do NOT add outer additionalProperties:false. Each oneOf branch validates the whole instance and must declare ALL allowed properties (including outer-shared ones like `notes`). The outer schema's properties block is informational only — JSON Schema does NOT merge oneOf branch properties into the parent's known set."
  - "Pattern: Real-recipe regression guard. The TestLintRealRecipes class (5 parametrized + 2 sanity) catches schema-vs-recipe drift at the SAME revision boundary — no future SC-03 gate run can surprise us with a 'recipe gained a field the schema doesn't allow' regression. The fixture is an explicit list (not glob) so adding a recipe requires updating the test = forced code review."

requirements-completed: [SC-03-GATE-A, SC-03-GATE-B]

# Metrics
duration: ~8min
completed: 2026-04-19
---

# Phase 22b Plan 09: Lint Schema Additions for direct_interface + event_log_regex + event_source_fallback (+6 Spike C Retrofits) Summary

**v0.2 schema extended with 9 changes — 27 baseline lint errors across 5 recipes closed to 0; new TestLintRealRecipes regression guard locks the win in.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-19T17:13:54Z
- **Completed:** 2026-04-19T17:22:03Z
- **Tasks:** 2
- **Files modified:** 4 (1 schema + 2 tests + 1 deferred-items)

## Accomplishments

- **27 baseline lint errors → 0** across all 5 committed recipes (hermes, picoclaw, nullclaw, nanobot, openclaw). Empirical post-fix proof:
  ```
  hermes:   PASS (0 errors)
  picoclaw: PASS (0 errors)
  nullclaw: PASS (0 errors)
  nanobot:  PASS (0 errors)
  openclaw: PASS (0 errors)
  ```
- Schema gained 2 new $defs (`direct_interface_block` oneOf docker_exec_cli|http_chat_completions; `event_source_fallback` oneOf docker_logs_stream|docker_exec_poll|file_tail_in_container) + 3 new property refs (v0_2.direct_interface, channel_entry.event_log_regex, channel_entry.event_source_fallback)
- 6 Spike C 2026-04-19 retrofit hunks for pre-existing schema-vs-recipe drifts that the original planner's "only 2 errors per recipe" framing missed
- TestLintRealRecipes regression-guard class added — 5 parametrized + 2 sanity tests, all green; future schema drift caught immediately
- 20 → 27 lint tests, all green; 12 broken-recipe negative tests STILL fail lint (no regression in TestLintBrokenRecipes); minimal_valid_recipe STILL passes (no regression in TestLintPositive)

## Per-recipe lint error count: BEFORE → AFTER

| Recipe | Before (Spike C 2026-04-19 baseline) | After Task 1 |
|--------|--------------------------------------|--------------|
| hermes | 2 errors (direct_interface, event_log_regex) | **0** |
| picoclaw | 5 errors (+ spike_artifact, boot_wall_s 2.85, first_reply_wall_s 3.2) | **0** |
| nullclaw | 7 errors (+ spike_artifact, boot_wall_s 2.46, first_reply_wall_s '~3', verdict PASS_WITH_FLAG, category PASS_WITH_FLAG, event_source_fallback) | **0** |
| nanobot | 6 errors (+ spike_artifact, boot_wall_s 23.36, first_reply_wall_s '~6', verified_cells[0] missing category) | **0** |
| openclaw | 7 errors (+ spike_artifact, first_reply_wall_s '~6', verdict + category PASS_WITH_FLAG, runtime.process_env.api_key_by_provider, event_source_fallback) | **0** |
| **TOTAL** | **27** | **0** |

## Schema diff stats: tools/ap.recipe.schema.json

- Lines: **1356 → 1574** (+227, -9 — 9 distinct hunks)
- New $defs: 2 (`direct_interface_block`, `event_source_fallback`)
- New property refs: 3 (`v0_2.direct_interface`, `channel_entry.event_log_regex`, `channel_entry.event_source_fallback`)
- Retrofit hunks (per Spike C 2026-04-19):
  - **B1+B2:** `boot_wall_s` + `first_reply_wall_s` widened from `integer` to `oneOf:[number, ~N string]`
  - **B3:** `PASS_WITH_FLAG` appended to channel_verified_cell.verdict enum
  - **B4:** `PASS_WITH_FLAG` appended to channel_category enum
  - **B5:** `category` dropped from channel_verified_cell.required (schema-relax path; nanobot[0] now valid)
  - **B6:** `spike_artifact: {type: string}` declared on channel_verified_cell.properties
  - **B7:** `api_key_by_provider: {type: object, additionalProperties: string}` declared on v0_2.runtime.process_env.properties
- Spike C bug fixes:
  - **A1:** Outer `additionalProperties: false` REMOVED from `direct_interface_block` (oneOf branch properties don't propagate to parent's known set; inner branches retain closure)
  - **A2:** Same on `event_source_fallback`; outer-level `notes: {type: string}` hoisted (load-bearing in nullclaw + openclaw recipes)

## Test counts (tools/tests/test_lint.py)

| Class | Before | After | Notes |
|-------|--------|-------|-------|
| TestLintPositive | 1 | 1 | unchanged (minimal_valid_recipe still passes — uses ap.recipe/v0.1, not v0.2) |
| TestLintApiVersion | 2 | 2 | unchanged |
| TestLintAdditionalProperties | 1 | 1 | unchanged |
| TestLintCrossFieldInvariants | 3 | 3 | unchanged |
| TestLintBrokenRecipes | 13 (1 sanity + 12 parametrized) | 13 | unchanged (12 broken recipes STILL fail lint — no negative-test regression) |
| **TestLintRealRecipes** | **0** | **7** | **NEW: 5 parametrized (hermes/picoclaw/nullclaw/nanobot/openclaw) + 2 sanity (test_all_5_recipes_listed, test_all_5_recipe_files_exist)** |
| **TOTAL** | **20** | **27** | All green; full suite runs in ~1s |

## Task Commits

Each task was committed atomically:

1. **Task 1: Schema additions (9 changes — 2 new $defs + 3 new refs + 6 Spike C retrofits)** — `3c4cddc` (feat)
2. **Task 2: TestLintRealRecipes regression guard + DI-05 deferred note** — `072de2f` (test)

## Files Created/Modified

- `tools/ap.recipe.schema.json` (modified) — 9 schema changes; 1356 → 1574 lines; +227 -9
- `tools/tests/test_lint.py` (modified) — TestLintRealRecipes class (5 parametrized + 2 sanity tests); +49 lines
- `tools/tests/conftest.py` (modified) — `real_recipes` fixture (explicit list of 5 recipes); +18 lines
- `.planning/phases/22b-agent-event-stream/deferred-items.md` (modified) — DI-05 entry for pre-existing test_roundtrip failures on openclaw + picoclaw

## Decisions Made

- **JSON Schema oneOf-with-additionalProperties:false architectural decision (Spike C bug A1+A2 fix):** Drop outer additionalProperties:false on direct_interface_block + event_source_fallback $defs. JSON Schema does NOT merge oneOf branch properties into the parent's known set, so an outer additionalProperties:false would reject every property even when an inner branch declares it. Inner branches retain additionalProperties:false which IS the actual closure mechanism. (Same defect would affect any future $def using oneOf-discrimination with branch-local properties.)
- **Spike C B5 — schema-relax over recipe-edit:** Drop `category` from channel_verified_cell.required (instead of editing nanobot.yaml to add `category: PASS` at line 337). Preserves the project-memory rule "do not rewrite the 5 existing recipes unless minimal retrofit". The schema-relax path is conservative; recipe-edit was the orchestrator-overridable alternative.
- **Inline notes-on-each-branch fix (deviation Rule 1 — auto-fix bug):** The plan's intent was to "hoist notes to outer-level only" of event_source_fallback. Empirical lint after Task 1 showed nullclaw + openclaw STILL failed because oneOf branches' own additionalProperties:false rejected the outer-declared notes. JSON Schema oneOf validates the WHOLE instance against each subschema; properties at the parent level are NOT inherited by oneOf branches. Fix: add `notes: { type: string }` as an optional property in each of the 3 oneOf branches' `properties` blocks. This is the minimal correct fix (NOT a relax-to-additionalProperties:true bandaid).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Outer-only `notes` property on event_source_fallback rejected by oneOf branches**

- **Found during:** Task 1 verification (post-edit lint of nullclaw + openclaw)
- **Issue:** Plan declared `notes: {type: string}` at the OUTER level of `event_source_fallback` $def with the intent it would apply to all oneOf branches. Empirically, JSON Schema oneOf validates the WHOLE instance against each subschema independently — outer-declared properties do NOT propagate. Each oneOf branch had `additionalProperties: false`, so they rejected the recipe's `notes` field even though it was declared at the parent.
- **Symptom:**
  ```
  channels.telegram.event_source_fallback: {kind: docker_exec_poll, ..., notes: '...'} is not valid under any of the given schemas
  ```
- **Fix:** Add `notes: { type: string }` as an optional property in each of the 3 oneOf branches' `properties` blocks (docker_logs_stream, docker_exec_poll, file_tail_in_container). NOT a relax-to-additionalProperties:true bandaid.
- **Files modified:** tools/ap.recipe.schema.json
- **Verification:** Re-ran lint — nullclaw + openclaw both PASS (0 errors)
- **Committed in:** 3c4cddc (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — Bug)
**Impact on plan:** Necessary correctness fix for the load-bearing `notes` field on event_source_fallback. Does not change plan scope; is a strict-correctness adjustment to the JSON Schema mechanism.

## Issues Encountered

- One pre-existing test failure surfaced when running the full tools/tests/ suite (NOT in test_lint.py): `tests/test_roundtrip.py::test_yaml_roundtrip_is_lossless[openclaw]` and `[picoclaw]`. Verified via `git stash` round-trip 2026-04-19 — both fail against HEAD~1 (before any 22b-09 changes). Likely linked to DI-01 (openclaw duplicate `category: PASS` key). Logged as DI-05 in deferred-items.md, NOT fixed (out of scope per CLAUDE.md scope-boundary rule).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **SC-03-GATE-A and SC-03-GATE-B fully unblocked** for the lint dimension. Any future PLAN that runs `lint_recipe` against the 5 committed recipes will get 0 errors. The api_server lint endpoint (which loads tools/ap.recipe.schema.json per services/lint_service.py:80) is unaffected by this change — the schema extension is strictly additive to the previously-rejected fields, and existing schema invariants (12 broken-recipe negative tests) still hold.
- **TestLintRealRecipes lock-in:** Future schema drift (e.g. a new schema $def that accidentally tightens an existing field) will be caught at test time, not at SC-03 runtime. The 5-recipe explicit list (NOT glob) means adding a 6th recipe requires updating the fixture and forces code review.
- **Tech-debt flagged:** The Go-side legacy schemas at `agents/schemas/recipe.schema.json` and `api/internal/recipes/schema/recipe.schema.json` are pre-v0.2 (declare id/runtime/launch/chat_io/isolation — fields that don't exist in v0.2 recipes). Untouched in this plan; flag for a future cleanup phase.
- **Open follow-ups:** DI-01 (openclaw duplicate `category: PASS` key) + DI-05 (test_roundtrip failures on openclaw + picoclaw) remain in deferred-items. Both likely resolvable by removing the duplicate-key in openclaw recipe.

## Self-Check: PASSED

All claims verified:
- `tools/ap.recipe.schema.json` exists and is 1574 lines (was 1356)
- `tools/tests/test_lint.py` contains `class TestLintRealRecipes` (verified by grep)
- `tools/tests/conftest.py` contains `def real_recipes` (verified by grep)
- Commits exist: `3c4cddc` (Task 1) + `072de2f` (Task 2) — verified by `git log --oneline`
- All 5 recipes lint clean: empirically verified via `lint_recipe(recipe, schema)` returning `[]` for each
- TestLintRealRecipes 7 tests green: `pytest tests/test_lint.py::TestLintRealRecipes -v` shows 7 PASSED
- Full lint suite green (27/27): `pytest tests/test_lint.py -q` shows `27 passed`
- Go-side legacy schemas untouched: `git diff --stat agents/schemas/ api/internal/recipes/schema/` returns empty

---
*Phase: 22b-agent-event-stream*
*Completed: 2026-04-19*
