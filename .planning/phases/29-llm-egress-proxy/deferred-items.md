# Phase 29 — Deferred items (out-of-scope discoveries)

## 2026-05-06 — Plan 29-04 Task 3

**`tests/test_idempotency.py::test_same_key_different_users_isolated`** —
PRE-EXISTING failure (NOT caused by Plan 29-04). The legacy chat-path
test inserts into `agent_instances` without a `name` value:

```sql
INSERT INTO agent_instances (id, user_id, recipe_name, model)
VALUES (gen_random_uuid(), $1, 'x', 'm')
```

`agent_instances.name` was made NOT NULL by migration `002_agent_name_personality`
(Phase 22a). The test predates that migration. Verified pre-existing by
stashing all Plan 29-04 changes and re-running the test in isolation:
same `NotNullViolationError`.

Fix shape: add a `name` value to the two INSERTs (e.g. `'x-test-1'` /
`'x-test-2'`). Trivial 2-line fix to the test file.

Owner: out of Phase 29 scope. Pre-existing test bug.
