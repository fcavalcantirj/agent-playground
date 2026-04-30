# Deferred items — Phase 22c.3

Items discovered during execution that are out of scope for the
current plan + log here for a future task to pick up.

## From Plan 22c.3-08

### Pre-existing test_idempotency.py failure (not caused by Plan 22c.3-08)

`tests/test_idempotency.py::test_same_key_different_users_isolated`
fails on `main` with:

```
asyncpg.exceptions.NotNullViolationError: null value in column "name"
of relation "agent_instances" violates not-null constraint
```

The test seeds an `agent_instances` row directly without setting `name`
— but `agent_instances.name` was made NOT NULL by `alembic 002`
(`alembic/versions/002_agent_name_personality.py`). Verified pre-existing
by `git stash` + run on clean main: the failure persists.

Fix: add `name='test-agent'` to the test's INSERT. The 3 other tests in
the file (`test_same_key_returns_cache`, `test_body_mismatch_returns_422`,
`test_expired_key_re_runs`) all pass on the post-22c.3-08 middleware
and do NOT touch this code path.

Out of scope for Plan 22c.3-08 (scope: chat path additions only).
