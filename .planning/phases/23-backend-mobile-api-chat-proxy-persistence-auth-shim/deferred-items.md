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

---

## Pre-existing test failure: `tests/spikes/test_truncate_cascade.py::test_truncate_cascade_clears_all_tables_preserves_alembic_version`

**Discovered during:** Phase 23 Plan 05 regression sweep (`pytest tests/routes/ tests/spikes/ -x`).
**Status:** PRE-EXISTING — confirmed by `git diff 35330e1 515f72f --stat` (only `services/openrouter_models.py`, `routes/models.py`, and `main.py` touched by Plan 05 — no migrations or DB schema changes). The spike's `subprocess.run(["python", "-m", "alembic", "upgrade", "005_sessions_and_oauth_users"])` returns non-zero before any of Plan 05's code is exercised.
**Failure:** `subprocess.CalledProcessError: ... '-m', 'alembic', 'upgrade', '005_sessions_and_oauth_users']' returned non-zero exit status 1.`
**Root cause:** Not investigated (out of scope) — likely a migration revision-id drift between this Wave-0-spike's hardcoded `005_sessions_and_oauth_users` target and the live alembic chain (post-Phase 22c.3 the migration tree extended past 005, and this spike was never re-tested).
**Impact on Phase 23-05:** None. Plan 23-05 touches no migrations, models, or DB; the new `tests/routes/test_models.py` (6 tests) passes cleanly, and `tests/routes/` sweep is fully green (58 passed). The Wave 0 GZip×SSE spike (`test_gzip_sse_compat.py`) — the spike that DOES validate Plan 05's middleware ordering — passes (2/2).
**Suggested owner:** Plan 23-08 (integration sweep) or a separate migration-spike maintenance ticket.

