# Phase 02 — Deferred Items

Tracked out-of-scope issues discovered during plan execution.

## Pre-existing test failure: TestMigrator_Idempotent

- **Found during:** 02-05 execution
- **File:** `api/pkg/migrate/migrate_test.go:116`
- **Symptom:** Test asserts `schema_migrations` row count == 1, but Plan 02-04 added `002_sessions.sql`, making the real count 2.
- **Scope:** Pre-existing at 02-05 start (verified via `git stash` + re-run on clean tree from Plan 02-04 tip). NOT caused by Plan 05.
- **Fix direction:** Update the assertion to match the number of migration files discovered at test time (e.g. `require.GreaterOrEqual(t, count, 1)`) or read the `EmbeddedMigrations()` slice length. Belongs in a 02-04 follow-up or the Phase 02 cleanup plan.
- **Visible only without `-short`:** Plan 02-05's success criterion gate is `go test ./... -count=1 -short`, which skips `TestMigrator_Idempotent` (it has a `testing.Short()` early-return guard). The full suite without `-short` fails. Noted but not blocking.
