---
phase: 10-error-taxonomy-timeout-enforcement
plan: 02
subsystem: testing
tags: [yaml, ruamel, migration, recipes, category, detail, taxonomy]

# Dependency graph
requires:
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "Plan 10-01 schema loosening (optional category/detail + 11-value enum) — the migrated recipes would fail lint without it"
  - phase: 09-spec-lint-test-harness-foundations
    provides: "test_lint / test_recipe_regression / test_roundtrip pytest harness — gates this migration"
provides:
  - "All 5 committed recipes carry {category, detail} on every verified_cells[] and known_incompatible_cells[] entry"
  - "D-04 STOCHASTIC→FAIL+ASSERT_FAIL mapping applied to hermes × google/gemini-2.5-flash (temporary; Phase 15 restores STOCHASTIC)"
  - "scripts/migrate_recipes_phase10.py — reusable, idempotent one-shot ruamel round-trip migrator retained for audit trail"
affects:
  - 10-03 (schema tightening — required[] flip is now safe; all 5 recipes have the new fields)
  - 10-04 (runner emits Verdict → can land against already-migrated recipes without writing category/detail retroactively)
  - 15-stochasticity (will re-map the hermes cell back from ASSERT_FAIL to STOCHASTIC once the multi-run machinery lands)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-shot ruamel round-trip migration: byte-identical YAML configuration copied verbatim from tools/run_recipe.py so test_roundtrip.py stays green (Pattern A, PATTERNS.md §Shared Patterns)"
    - "Idempotent data migration via dict.setdefault() — re-running produces zero diffs, no state-machine required"

key-files:
  created:
    - "scripts/migrate_recipes_phase10.py (+76 lines)"
  modified:
    - "recipes/hermes.yaml (+7/-1: 2 verified_cells migrated, 1 known_incompat remapped from STOCHASTIC)"
    - "recipes/openclaw.yaml (+4: 1 verified_cell migrated, 1 known_incompat derived-detail)"
    - "recipes/picoclaw.yaml (+2: 1 verified_cell migrated)"
    - "recipes/nullclaw.yaml (+2: 1 verified_cell migrated)"
    - "recipes/nanobot.yaml (+2: 1 verified_cell migrated)"

key-decisions:
  - "Keep migration script committed (not deleted) for audit trail — CONTEXT.md §specifics + RESEARCH.md Assumption A4 both allow either; retaining it makes future drift re-runs a one-liner"
  - "Accept ruamel setdefault appending keys to end of CommentedMap (so category/detail land AFTER notes, not between verdict and wall_time_s) — key ordering is cosmetic, doesn't affect lint or round-trip, and hand-reordering would risk comment/whitespace drift"
  - "For openclaw × gpt-4o-mini detail: derive from notes.split('.', 1)[0] as plan specified — the result is a multi-line scalar because the first period appears after a line break, but YAML quoting handles it and lint passes"

patterns-established:
  - "D-04 backwards-compat migration pattern: idempotent, ruamel-preserving, script-over-hand-edit for any multi-recipe field addition touching ≥5 files"
  - "STOCHASTIC→ASSERT_FAIL temporary mapping: the verdict field is hard-swapped (not setdefault) because STOCHASTIC is not in the verdict enum; category uses setdefault so future re-runs stay no-op"

requirements-completed: [D-04]

# Metrics
duration: 4min
completed: 2026-04-16
---

# Phase 10 Plan 02: Recipe Migration — category + detail on all 5 recipes Summary

**All 5 committed recipes migrated with {category, detail} per D-04, including the STOCHASTIC→FAIL+ASSERT_FAIL remap of hermes × gemini-2.5-flash, via a reusable idempotent ruamel script that keeps round-trip tests byte-identical.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-16T20:55:00Z (worktree base 3c27b5a8)
- **Completed:** 2026-04-16T20:58:02Z (commit e30c7d9)
- **Tasks:** 2
- **Files modified:** 5 recipes
- **Files created:** 1 migration script

## Accomplishments

- `scripts/migrate_recipes_phase10.py` created — 76 lines, ruamel-based, idempotent via `setdefault`, ruamel config copied byte-identically from `tools/run_recipe.py` lines 27-39 per PATTERNS.md Pattern A
- All 6 `verified_cells[]` entries across 5 recipes received `category: PASS` + `detail: ''`
- `recipes/openclaw.yaml` known_incompat cell (openai/gpt-4o-mini) received `category: ASSERT_FAIL` + derived detail from `notes` first sentence
- `recipes/hermes.yaml` known_incompat cell (google/gemini-2.5-flash) remapped per D-04: `verdict: STOCHASTIC` → `verdict: FAIL`, added `category: ASSERT_FAIL`, added `detail: "flapping verdict — see notes"` (temporary — Phase 15 restores true STOCHASTIC semantics)
- Full test suite green: `pytest -x -q` → 48/48 passed
- `grep "verdict: STOCHASTIC" recipes/*.yaml` → zero matches (STOCHASTIC removed from verdict field everywhere)
- Idempotence confirmed empirically: second run of the migration script produces `diff` output of zero lines on all 5 recipes

## Per-Recipe Migration Counts

| Recipe | verified_cells migrated | known_incompat migrated | STOCHASTIC remapped |
|--------|-------------------------|-------------------------|---------------------|
| hermes.yaml | 2 | 1 | 1 (google/gemini-2.5-flash) |
| openclaw.yaml | 1 | 1 | 0 |
| picoclaw.yaml | 1 | 0 | 0 |
| nullclaw.yaml | 1 | 0 | 0 |
| nanobot.yaml | 1 | 0 | 0 |
| **total** | **6** | **2** | **1** |

## Task Commits

Each task was committed atomically:

1. **Task 1: Create one-shot migration script** — `1f28d03` (feat)
2. **Task 2: Run migration + verify full test suite stays green** — `e30c7d9` (feat)

## Files Created/Modified

- `scripts/migrate_recipes_phase10.py` — 76-line ruamel round-trip migrator. Module-level docstring per plan, `migrate(recipe_path)` function, `if __name__ == "__main__"` entry point iterating `sorted(Path("recipes").glob("*.yaml"))`.
- `recipes/hermes.yaml` — 2 `verified_cells` augmented; 1 `known_incompatible_cells` entry remapped (verdict STOCHASTIC→FAIL, +category, +detail).
- `recipes/openclaw.yaml` — 1 `verified_cells` augmented; 1 `known_incompatible_cells` augmented (+category, +derived detail).
- `recipes/picoclaw.yaml` — 1 `verified_cells` augmented (+category, +detail).
- `recipes/nullclaw.yaml` — 1 `verified_cells` augmented (+category, +detail).
- `recipes/nanobot.yaml` — 1 `verified_cells` augmented (+category, +detail).

## Decisions Made

- **Migration script retained, not deleted.** Per CONTEXT.md §specifics and RESEARCH.md Assumption A4, either approach is allowed. Retention provides an audit trail and makes future drift repairs a one-liner. A later phase may remove it once Phase 10 is fully sealed.
- **Key ordering left as `ruamel.setdefault` produces it.** The new `category`/`detail` keys land AFTER `notes` rather than between `verdict` and `wall_time_s` because `setdefault` on a `CommentedMap` appends to end. Per the plan (I2), this is acceptable — lint is agnostic to key order, round-trip preserves insertion order going forward, and attempting to manually reorder would risk comment/whitespace drift that `test_roundtrip.py` would catch. No hand reordering attempted.
- **Openclaw derived-detail contains an internal newline.** `notes.split(".", 1)[0]` extracts everything before the first period; for openclaw × gpt-4o-mini that chunk spans two lines. ruamel quoted the result as a double-quoted scalar with `\n` escape; lint, round-trip, and the structural assertion all pass. No post-processing applied — the plan specified the exact `split(".", 1)[0][:120]` derivation and I followed it literally.

## Deviations from Plan

None — plan executed exactly as written. Both tasks landed on first attempt; verification gates (syntax check, docstring check, YAML grep counts, full pytest) all green first invocation.

One minor observation during execution, not a deviation: I initially misread `git diff --stat` (cumulative diff vs HEAD) as evidence of non-idempotence after a second migration run. A proper snapshot-then-diff test (`cp recipe /tmp/ && migrate && diff`) confirmed byte-level idempotence. Documented for the record; no code change required.

## Issues Encountered

None. The ruamel byte-identical config copied from `tools/run_recipe.py` kept `test_roundtrip.py` green on first run, sparing the rabbit hole called out in the plan's Task 2 action block ("If test_roundtrip.py fails with YAML-formatting drift, STOP…").

## User Setup Required

None — purely local, deterministic, file-system-only migration. No credentials, no network, no external services.

## Verification Evidence

- `python3 -c "import ast; ast.parse(open('scripts/migrate_recipes_phase10.py').read())"` → exit 0 (syntax OK)
- `head -15 scripts/migrate_recipes_phase10.py | grep "ONE-SHOT migration"` → match (docstring OK)
- `grep -c 'YAML(typ="rt")' scripts/migrate_recipes_phase10.py` → 1 (ruamel config copied)
- `python3 scripts/migrate_recipes_phase10.py` → 5 lines of `migrating <file>.yaml` output, zero stderr
- `grep -c "category: PASS" recipes/*.yaml` → total 6 occurrences across all 5 recipes (hermes:2, openclaw:1, picoclaw:1, nullclaw:1, nanobot:1)
- `grep -l "category: ASSERT_FAIL" recipes/*.yaml` → hermes.yaml, openclaw.yaml (both known_incompat cells migrated)
- `grep -A2 "google/gemini-2.5-flash" recipes/hermes.yaml | grep "verdict: FAIL"` → match (STOCHASTIC remap applied)
- `grep "verdict: STOCHASTIC" recipes/*.yaml` → zero matches (STOCHASTIC fully removed from verdict fields)
- `cd tools && pytest tests/test_lint.py tests/test_recipe_regression.py tests/test_roundtrip.py -x -q` → 30 passed
- `cd tools && pytest -x -q` → 48 passed (full suite)
- Structural assertion script from plan Task 2 action #4 → prints `all 5 recipes migrated correctly`
- Idempotence empirical test: `cp recipes/*.yaml /tmp/ && python3 scripts/migrate_recipes_phase10.py && diff` → zero diff output

## Threat Flags

None. Per the plan's `<threat_model>`:

- T-10-03 (Tampering of committed YAML by the script): mitigated — `setdefault` guarantees idempotence; `test_roundtrip.py` byte-identity guard catches any ruamel config drift (verified green).
- T-10-04 (STOCHASTIC remap data loss): mitigated — explicit `if cell.get("verdict") == "STOCHASTIC":` branch; original `notes: |` block preserved verbatim (verified by manual inspection and by test_roundtrip running on every commit).

No new trust boundaries introduced. The script is local-run-only, no network, no environment reads.

## Known Stubs

None. The `category: PASS` + `detail: ''` additions are not stubs — they are the authoritative Phase 10 field values for a cell that previously ran green. `detail: ''` is explicitly called out in D-02 as "acceptable when category=PASS". The STOCHASTIC→ASSERT_FAIL mapping is documented as temporary in CONTEXT.md D-04 with a pointer to Phase 15 restoration; this is a time-bounded tracking item, not a stub.

## Next Phase Readiness

**Ready for Plan 10-03 (schema tightening).** The schema can now flip `smoke.verified_cells.items.required` and `smoke.known_incompatible_cells.items.required` from `["model", "verdict"]` to `["model", "verdict", "category", "detail"]` and all 5 recipes will still lint green.

**Ready for Plan 10-04 (runner timeout enforcement).** The runner can now emit `Verdict` dataclass objects with `category` set, and when `writeback_cell` runs it will update wall_time_s without stepping on the new fields (category/detail are not touched by writeback).

**Phase 15 (stochasticity) handoff signal recorded in hermes.yaml:** the `detail: "flapping verdict — see notes"` string is the breadcrumb Phase 15 will grep for to identify cells to promote back from ASSERT_FAIL to STOCHASTIC once multi-run determinism lands.

No blockers or concerns.

## Self-Check: PASSED

**Commit verification:**

```
$ git log --oneline HEAD~2..HEAD
e30c7d9 feat(10-02): migrate 5 recipes with category+detail per D-04
1f28d03 feat(10-02): add one-shot ruamel migration for category+detail
```

FOUND: `1f28d03` (Task 1 — migration script)
FOUND: `e30c7d9` (Task 2 — migrated recipes)

**File verification:**

- `scripts/migrate_recipes_phase10.py` → FOUND (created, 76 lines)
- `recipes/hermes.yaml` → FOUND (modified, +7/-1)
- `recipes/openclaw.yaml` → FOUND (modified, +4)
- `recipes/picoclaw.yaml` → FOUND (modified, +2)
- `recipes/nullclaw.yaml` → FOUND (modified, +2)
- `recipes/nanobot.yaml` → FOUND (modified, +2)
- `.planning/phases/10-error-taxonomy-timeout-enforcement/10-02-SUMMARY.md` → FOUND (this file)

All claims in this SUMMARY are backed by the Verification Evidence section above.

---
*Phase: 10-error-taxonomy-timeout-enforcement*
*Completed: 2026-04-16*
