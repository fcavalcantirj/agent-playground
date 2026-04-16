---
phase: 09-spec-lint-test-harness-foundations
plan: 02
subsystem: testing
tags: [jsonschema, lint, cli, argparse, ansi-colors, recipe-validation]

# Dependency graph
requires:
  - phase: 09-01
    provides: lint_recipe() function, _SCHEMA_PATH, load_recipe(), ap.recipe.schema.json
provides:
  - "--lint single-recipe validation subcommand"
  - "--lint-all bulk validation of all recipes/*.yaml"
  - "--no-lint escape hatch to skip mandatory pre-step"
  - "Mandatory lint pre-step before every Docker invocation"
  - "Exit code 2 for lint failures (distinct from runtime exit code 1)"
  - "Colored ANSI output for PASS/FAIL results"
affects: [09-03, 09-04, recipe-authoring-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns: [exit-code-2-for-lint-failures, mandatory-pre-step-with-bypass, ansi-colored-cli-output]

key-files:
  created: []
  modified:
    - tools/run_recipe.py

key-decisions:
  - "Exit code 2 for lint failures per D-09 contract, keeping exit 1 for runtime failures"
  - "Mandatory lint pre-step runs before every Docker invocation with --no-lint bypass"
  - "recipe positional arg made optional (nargs='?') to support --lint-all without recipe path"

patterns-established:
  - "Lint-before-run: every Docker invocation is gated by structural validation"
  - "ANSI color output: _GREEN for PASS, _RED for FAIL, with error detail lines"
  - "Three-tier exit codes: 0=success, 1=runtime-fail, 2=lint-fail"

requirements-completed: [D-06, D-07, D-08, D-09]

# Metrics
duration: 2min
completed: 2026-04-16
---

# Phase 09 Plan 02: Lint CLI Integration Summary

**Wired --lint, --lint-all, --no-lint subcommands with colored output and mandatory pre-step gating Docker invocations**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-16T03:03:30Z
- **Completed:** 2026-04-16T03:05:14Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added --lint flag for single-recipe validation with colored PASS/FAIL output and exit 0 or 2
- Added --lint-all flag to bulk-validate all recipes/*.yaml (all 5 recipes pass)
- Integrated mandatory lint pre-step before every Docker invocation (skippable via --no-lint)
- Established three-tier exit code contract: 0=success, 1=runtime-fail, 2=lint-fail (D-09)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --lint, --lint-all, --no-lint CLI flags and colored output** - `f23a321` (feat)

## Files Created/Modified
- `tools/run_recipe.py` - Added ANSI color constants, _print_lint_result(), _lint_single(), _lint_all_recipes() helpers; updated parse_args() with three new flags; updated main() with lint-all mode, lint mode, and mandatory pre-step logic

## Decisions Made
- Exit code 2 for all lint failure paths per D-09 contract, keeping existing exit 1 for runtime failures unchanged
- Made `recipe` positional argument optional (`nargs="?"`) so `--lint-all` works without specifying a recipe path
- Mandatory lint pre-step loads and validates the recipe before any Docker operations, catching structural errors early

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Lint integration complete; all 5 existing recipes validate cleanly against the schema
- Ready for Plan 03 (pytest harness) and Plan 04 (CI integration) which consume the lint subcommands
- Invalid recipes are now caught before Docker is ever invoked

---
*Phase: 09-spec-lint-test-harness-foundations*
*Completed: 2026-04-16*
