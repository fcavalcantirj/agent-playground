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

## 2026-05-06 — Plan 29-04 Task 4 regression sweep

**`tests/auth/test_cross_user_isolation.py::test_two_users_see_only_their_own_agents`** —
PRE-EXISTING failure landed by Plan 29-02. The test enforces an
`ALLOWED_HEADS` set assertion against alembic head — the comment says
"Append new HEADs here as later migrations land", but Plan 29-02
(migration `013_phase29_proxy_columns`) didn't update the set. The
current head is `013_phase29_proxy_columns`, which is not in:

```python
ALLOWED_HEADS = {
    "006_purge_anonymous", "007_inapp_messages",
    "008_idempotency_relax_run_fk", "009_auth_events_revoked_reason",
    "010_usage_logs_cost_weights", "011_phase28_workflow_id_idem",
}
```

Plan 29-02 should have appended `"012_cost_weights_extra"` and
`"013_phase29_proxy_columns"`. Trivial 2-line fix. Out of Plan 29-04
scope.

Owner: out of Phase 29-04 scope. Plan 29-02 cleanup.
