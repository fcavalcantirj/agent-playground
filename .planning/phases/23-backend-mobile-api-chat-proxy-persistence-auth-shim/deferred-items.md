# Phase 23 — Deferred Items (out-of-scope discoveries)

Items found during plan execution that are NOT directly caused by the current
plan's changes. Per SCOPE BOUNDARY rule (executor): logged here, not fixed.

---

## Pre-existing test failure: `tests/test_idempotency.py::test_same_key_different_users_isolated`

**Discovered during:** Phase 23 Plan 02 verify run.
**Status:** PRE-EXISTING — confirmed by stashing Plan 02 changes and re-running the test, which still fails.
**Failure:** `asyncpg.exceptions.NotNullViolationError: null value in column "name" of relation "agent_instances" violates not-null constraint`.
**Root cause:** The test inserts `agent_instances` rows directly via SQL without supplying `name`, but a migration since the test was written added a NOT NULL constraint on `agent_instances.name`. The seed SQL `INSERT INTO agent_instances (id, user_id, recipe_name, model) VALUES (gen_random_uuid(), $1, 'x', 'm')` is missing the `name` column.
**Fix shape:** Add `name` (e.g. `'u1-test-agent'` / `'u2-test-agent'`) to both INSERTs at `tests/test_idempotency.py:132-141`.
**Impact on Phase 23-02:** None. The failing test is a DB-direct test for cross-user idempotency_keys collision; it doesn't exercise the chat-path handler at all, and the chat-path replay scenario is covered by `tests/routes/test_messages_idempotency_required.py::test_post_message_replay_returns_cached_202` (added by Plan 23-02).
**Suggested owner:** Plan 23-08 (integration sweep) or its own quick-fix plan; adding `name` to the seed inserts is a 2-line change.
