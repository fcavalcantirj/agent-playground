# Deferred Items - Phase 02.5

Pre-existing issues discovered during plan execution that are out of scope
for the current task. Each entry names the plan that noticed it and the
component it affects — a future plan should pick these up explicitly.

## TestMigrator_Idempotent fails (pkg/migrate)

- **Noticed by:** Plan 02.5-04 executor
- **Symptom:** `go test ./pkg/migrate/... -count=1` fails with
  `TestMigrator_Idempotent: expected 1 actual 2 - exactly one migration row
  should be recorded`.
- **Location:** `api/pkg/migrate/migrate_test.go:116`
- **Root cause (not investigated):** the migrate_test embedded postgres
  fixture records two rows where only one is expected; looks like a
  test-data leakage / ordering bug, not triggered by anything in Plan 04.
- **Plan 04 scope:** only touches `api/internal/session/bridge*`. No
  migration code modified. Per SCOPE BOUNDARY this failure is NOT fixed
  here.
- **Action:** pick up in a dedicated maintenance plan or in Plan 02.5-09
  when the handler refactor touches adjacent code.
