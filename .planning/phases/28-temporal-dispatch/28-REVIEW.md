---
phase: 28-temporal-dispatch
reviewed: 2026-05-05T00:00:00Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - api_server/alembic/versions/011_phase28_workflow_id_idempotency.py
  - api_server/src/api_server/main.py
  - api_server/src/api_server/routes/agent_messages.py
  - api_server/src/api_server/services/inapp_dispatcher.py
  - api_server/src/api_server/services/inapp_messages_store.py
  - api_server/src/api_server/temporal/__init__.py
  - api_server/src/api_server/temporal/activities/__init__.py
  - api_server/src/api_server/temporal/activities/check_container_ready.py
  - api_server/src/api_server/temporal/activities/debit_balance.py
  - api_server/src/api_server/temporal/activities/emit_inapp_outbound.py
  - api_server/src/api_server/temporal/activities/forward_to_agent.py
  - api_server/src/api_server/temporal/activities/mark_message_done.py
  - api_server/src/api_server/temporal/activities/mark_message_failed.py
  - api_server/src/api_server/temporal/activities/record_usage.py
  - api_server/src/api_server/temporal/client.py
  - api_server/src/api_server/temporal/worker.py
  - api_server/src/api_server/temporal/workflows/__init__.py
  - api_server/src/api_server/temporal/workflows/dispatch_message.py
  - api_server/src/api_server/temporal/workflows/types.py
  - api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py
  - api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py
  - api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py
  - api_server/tests/test_migration_011_phase28.py
  - mobile/lib/features/chat/chat_screen.dart
  - mobile/lib/features/dashboard/dashboard_screen.dart
  - mobile/test/features/usage/usage_ticker_widget_remount_test.dart
  - tools/migrate_phase28_stuck_rows.py
findings:
  critical: 0
  warning: 5
  info: 10
  total: 15
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-05-05
**Depth:** standard
**Files Reviewed:** 28
**Status:** issues_found

## Summary

Phase 28 introduces Temporal-backed durable message dispatch, replacing the
asyncpg pump in `services/inapp_dispatcher.py` with `DispatchMessageWorkflow`
plus seven activities. The implementation is generally well-structured: it
mirrors MSV's `messaging/` shape for Go portability (D-09), enforces the
sandbox/activity boundary via `workflow.unsafe.imports_passed_through()`,
preserves D-22's no-op `debit_balance` for Phase B forward-compat, and
defends idempotency in three layers (request-middleware TTL, partial UNIQUE
index, ON CONFLICT idempotent insert).

Notable strengths: thorough docstrings recording every Rule-1 deviation
(revision-id length, `Decimal('0')` JSON failure, `ActivityError` vs
`ApplicationError` catch); a clean class-bound activity pattern with
load-loud module-level `NotImplementedError` placeholders; a real
WorkflowEnvironment spike (B) and live Postgres testcontainer for
migration 011; and a conservative one-shot cutover script with dry-run +
safety cap. The Phase 28 Mobile work (Dashboard/Chat AppBar tickers
Consumer-scoped) is a small, surgical fix with a regression test that
exercises the exact navigation race that broke Phase 27.

The findings below are mostly Warning- and Info-level: a defense-in-depth
gap in `insert_pending` (bypassing the SQL-layer user_id filter for
idempotent replays), three Temporal-specific behavioral concerns (the
`bot_timeout_seconds + 30` start_to_close vs. transport-retry budget,
single-attempt forward at workflow level, `mark_message_failed` skipping
the event when no container row exists), and a couple of correctness
edges. No Critical issues — no SQL injection, no hardcoded secrets, no
crash-prone null derefs, no cross-user leak vectors.

## Warnings

### WR-01: `insert_pending` returns the existing row's id without verifying ownership

**File:** `api_server/src/api_server/services/inapp_messages_store.py:96-107`

**Issue:** The Phase 28 `INSERT ... ON CONFLICT (user_id, idempotency_key) DO UPDATE SET content = inapp_messages.content RETURNING id` matches on `(user_id, idempotency_key)`, so for the SAME caller the partial-unique index does the right thing. But the route handler in `agent_messages.py:236-243` passes the request's `agent_id` along with the resolved `user_id` and the user-supplied `idempotency_key`. Consider the case where a legitimate caller sends the same `Idempotency-Key` for two DIFFERENT `agent_id` values (e.g. a misbehaving SDK retrying after switching agents): the second INSERT will `DO UPDATE SET content = inapp_messages.content` (a no-op write), and `RETURNING id` will return the FIRST agent's row id. The route then back-fills `workflow_id` and returns 202 with a `message_id` belonging to a different agent — a confusing replay that crosses agents.

The Stripe semantic (and the request-layer middleware in `services/idempotency.py`) is to reject this as `IDEMPOTENCY_BODY_MISMATCH` (different request body for the same key). The middleware DOES catch this for the request body, but it does NOT see the `agent_id` (URL path param) as part of the body hash, and the SQL-level defense layer doesn't check `agent_id` either.

**Fix:** Either (a) include `agent_id` in the unique index tuple — `(user_id, agent_id, idempotency_key)` — at migration time so the second INSERT collides only when the agent_id matches; or (b) after the `RETURNING id` in `insert_pending`, fetch the full row and assert `row.agent_id == agent_id`, returning a 422 mismatch error if not. Option (a) is the cleaner long-term answer and matches the existing middleware's request-scope semantics. If the design intent is "Idempotency-Key is global per user," document it explicitly and add a SELECT-after-INSERT assertion in the handler so the cross-agent replay is detected and rejected rather than silently returning the wrong message_id.

---

### WR-02: `forward_to_agent` activity start_to_close budget can shorten transport-retry budget

**File:** `api_server/src/api_server/temporal/workflows/dispatch_message.py:148-152` and `api_server/src/api_server/temporal/activities/forward_to_agent.py:144-164`

**Issue:** The workflow sets `start_to_close_timeout=timedelta(seconds=inp.bot_timeout_seconds + 30.0)`. The activity body, on transport failure, retries through `[0, 1, 2, 4]` seconds (7s of cumulative sleep) with each attempt also paying up to `inp.bot_timeout_seconds` of httpx budget. With the documented default `BOT_TIMEOUT_SECONDS = 600.0`, that's a worst case of `4 * 600 + 7 = 2407s` per activity execution — far exceeding the `bot_timeout_seconds + 30` (= 630s) start-to-close budget. Once the start-to-close fires, Temporal cancels the activity mid-retry; the workflow's `except (ActivityError, ApplicationError)` then classifies the cause as a generic `ActivityError(CancelledError)` — `_classify_forward_failure` walks `__cause__` looking for an `ApplicationError.type` and falls all the way through to `"internal_error"`. Users see `error_type="internal_error"` instead of the more accurate `bot_timeout`.

The 250ms readiness retry budget (`check_container_ready` step 1) is fine because its activity-internal retries fit inside the 10s start-to-close. The forward step is the one with a mismatched budget.

**Fix:** Either (a) inflate the start_to_close to `4 * bot_timeout_seconds + 30` so the activity-internal retries actually fit inside the Temporal budget, or (b) shrink the activity-internal retry budget to a single attempt with a conservative timeout (drop the `[1, 2, 4]` waits — Temporal's own retry policy can handle transport failures at the workflow level). Option (b) is more conventional for Temporal usage; the activity-internal retry was carried over from the legacy dispatcher's per-row state machine where there was no Temporal layer to do it. If keeping option (a), document the math in the workflow's docstring and verify the worker's `max_concurrent_activities=10` accounts for the longer-lived activity slot.

---

### WR-03: `mark_message_failed` silently drops the event when no container row exists

**File:** `api_server/src/api_server/temporal/activities/mark_message_failed.py:99-104`

**Issue:** When the `inapp_messages → agent_containers` JOIN finds no container row, the activity logs a `phase28.mark_message_failed.row_missing` warning and returns without inserting the `agent_events(kind='inapp_outbound_failed')` row. The `inapp_messages.status` flip to `'failed'` HAS been applied (via `mark_failed(conn, ...)` two lines earlier, inside the same transaction). So the row goes terminal but no event is published — the SSE outbox pump never sees the failure, the mobile chat screen never gets a `delivery failed: ...` update, and the user stares at "..." forever (the same UX-breaking pattern Phase 22b was supposed to eliminate).

This case is not impossible: a user could DELETE the agent (cascading container rows) between the workflow start and the failure-marker activity, or container rows could be sweep-cleaned by an unrelated reaper. The legacy dispatcher in `services/inapp_dispatcher.py` had the same JOIN but the call shape was different (it owned the transaction on the row lookup path).

**Fix:** When the JOIN returns no row, INSERT a synthetic `agent_events` row keyed on the most-recently-seen container row for that `agent_instance_id` — fall back to a `SELECT id FROM agent_containers WHERE agent_instance_id = ... ORDER BY created_at DESC LIMIT 1` (regardless of `stopped_at`). If THAT also returns nothing, the agent itself was deleted; in that case publish to a synthetic `agent:inapp:<agent_instance_id>` channel directly via the outbox layer, OR document the case in the docstring and let the mobile UI's history endpoint backfill the failed state on next chat-screen open (the `GET /v1/agents/:id/messages` handler in `agent_messages.py:336-449` already maps `status='failed'` → assistant `error` event). At minimum, surface the warning at `error` level and increment a metric so operations notices when this branch fires.

---

### WR-04: `record_usage` workflow retry policy doesn't match the activity's swallow-and-return contract

**File:** `api_server/src/api_server/temporal/workflows/dispatch_message.py:174-188` and `api_server/src/api_server/temporal/activities/record_usage.py:1-81`

**Issue:** The activity docstring states "failure is logged inside the recorder; we log a warning at the activity boundary so Temporal's history surfaces the event, but we do NOT raise" — i.e., `record_usage` is designed to never raise. The workflow nevertheless sets `RetryPolicy(maximum_attempts=3)`, which is wasted budget: if the activity always returns successfully, retries never fire. More importantly, the workflow ALSO catches `(ActivityError, ApplicationError)` on lines 184-188 — but per the activity contract, those exceptions can't be thrown. The catch is dead code under the current design.

This is a minor consistency issue, not a correctness bug — the activity body actually does NOT have a try/except wrapping `legacy_record_usage`. If `usage_recorder.record_usage` raises for any reason (e.g., asyncpg connection pool exhausted, transient PG error during the savepoint), the activity DOES propagate the exception to Temporal, which will retry up to 3 times. So the retry policy isn't dead — but the docstring claims an exception-swallowing contract the activity body does not actually implement.

**Fix:** Either (a) wrap the `legacy_record_usage` call in a try/except inside the activity that swallows + logs, matching the docstring; or (b) remove the "we do NOT raise" sentence from the docstring so it accurately reflects the propagating-exception design. Option (b) is the smaller change and matches what the workflow's retry policy assumes.

---

### WR-05: `set_workflow_id` is called outside the `insert_pending` transaction (race window)

**File:** `api_server/src/api_server/routes/agent_messages.py:236-310`

**Issue:** Step 5 acquires a fresh connection to `insert_pending` (line 236-243), commits implicitly when the `async with` exits, returns the message_id. Step 6 starts the workflow (line 252-271). Step 7 acquires ANOTHER fresh connection and calls `set_workflow_id` (line 297-301). Three windows exist:

1. Between step 5 commit and step 6 `start_workflow`: if the api_server crashes here, the row exists in `pending` with no workflow ever started — orphaned row. The reaper (`services/inapp_reaper.py`) eventually catches it via the `'forwarded'` sweep, but `pending` rows (no `last_attempt_at`) are not the reaper's primary target. Phase 28's restart sweep (`restart_sweep` in `inapp_messages_store.py:318-352`) only resets `forwarded → pending`, not `pending` rows.
2. Between step 6 success and step 7 back-fill: the row stays without `workflow_id` for the round-trip, hindering ops correlation.
3. Step 7 swallows ALL exceptions (`except Exception:`), so a transient PG error during back-fill leaves the row without `workflow_id` — the `try` is "best-effort" per the docstring, which is fine, but it WILL silently happen under load.

Window 1 is the load-bearing one. The legacy dispatcher's pump was tolerant of `pending` rows because it polled them; Phase 28's `start_workflow` is fire-and-forget and depends on `client.start_workflow` actually being called.

**Fix:** Two options.
- (a) Move the `set_workflow_id` UPDATE INTO the same transaction as `insert_pending` by computing the `workflow_id = f"msg-{user_id}-{message_id}"` BEFORE the INSERT and passing it as a column value (since `insert_pending` already builds the SQL). Then `start_workflow` runs after commit; if it fails, the row is in `pending` with a known `workflow_id`, and the cutover script + a new sweep step can detect "row has workflow_id but no Temporal execution".
- (b) Add a `pending` sweep to `restart_sweep` that resets/transitions rows older than N minutes that never got picked up. Document the symptom + recovery in the migration tools README.

Pick (a) — it removes the race entirely and the column is already nullable so legacy code paths are unaffected.

## Info

### IN-01: Spike A leaves an unused `uuid` import

**File:** `api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py:36`

**Issue:** `import uuid` is at module top but never referenced (the test uses `PROJECT_NAME` constants and `time.monotonic()` for randomness via timestamps).

**Fix:** Remove the unused import. Same for `import os` on line 31 — also unreferenced inside this file.

---

### IN-02: Spike C overwrites the compose file twice

**File:** `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py:202-245`

**Issue:** The test writes `compose_file` once with `COMPOSE_TEMPLATE.format(...)` and then immediately rewrites it with a different inline template. The first write is dead code with confusing error-shape comments ("the formatted append is wrong shape"). A future maintainer might "fix" the first write thinking the second is the bug.

**Fix:** Delete the first `write_text` call (lines 203-208) and the dangling `COMPOSE_TEMPLATE` constant (line 84-109) since only the inline template is used. Or, if `COMPOSE_TEMPLATE` is still useful as documentation, move it into the test docstring as a comment.

---

### IN-03: `_dispatch_http_localhost` mutates `body` variable type across `match` arms

**File:** `api_server/src/api_server/services/inapp_dispatcher.py:151-219`

**Issue:** The `body: dict[str, Any]` annotation on line 151 is type-hinted only in the `openai_compat` arm. In the `a2a_jsonrpc` arm (line 166), `body = {...}` rebinds without re-annotating; in `zeroclaw_native` (line 196), `body = {...}` likewise. mypy/pyright will flag this if strict mode is enabled because the annotated initial type doesn't cover the JSON-RPC envelope shape (which has `params.message.parts: list`).

**Fix:** Either annotate each branch's body separately, or drop the `dict[str, Any]` annotation and let inference handle it (`body = {...}`). Cosmetic; not a runtime bug.

---

### IN-04: `_classify_forward_failure` uses `id()` for cycle detection — fragile under exception unwrap

**File:** `api_server/src/api_server/temporal/workflows/dispatch_message.py:285-298`

**Issue:** The `seen: set[int]` of `id(cur)` will catch the `e is e.__cause__` self-loop case, but `id()` reuses memory addresses across object lifetimes. If a deeply-nested chain creates intermediate exceptions that get GC'd while the loop runs (rare in workflow context, more relevant in long-running activities), two distinct exceptions could share the same `id`. The Python idiom for this loop is `seen: set[BaseException] = set()` and `seen.add(cur)`, using the object identity as a hash via `__hash__` (default for `object` subclasses).

**Fix:** Replace `seen: set[int] = set()` with `seen: set[int] = set(); seen.add(id(cur))` is functionally fine for workflow-scope use, but documenting WHY `id()` is used (no `__hash__` on some legacy ApplicationError subclasses?) would help. If no legacy reason, switch to `set[BaseException]` for clarity.

---

### IN-05: `migrate_phase28_stuck_rows.py` truncates dry-run output silently after 50 rows

**File:** `tools/migrate_phase28_stuck_rows.py:130-143`

**Issue:** The dry-run shows the first 50 rows then logs `phase28.cutover.dry_run.truncated shown=50 total=N`. If `N` exceeds the safety cap (default 10000), the operator running `--dry-run` will not see this — the safety cap only fires in the live path. An operator could see "200 rows affected" in dry-run, miss the cap mismatch, then run live and hit the cap abort. Order is fine functionally — abort before mutate is correct — but the dry-run UX hides this.

**Fix:** In the dry-run path, also fetch `count = COUNT_SQL` and log a warning if `count > args.limit`, e.g. `phase28.cutover.dry_run.would_exceed_cap count=N limit=M`. Doesn't change behavior; just gives the operator a heads-up.

---

### IN-06: `agent_messages.py` SSE handler resolves `container_row_id` separately from POST/DELETE

**File:** `api_server/src/api_server/routes/agent_messages.py:212-229` and `581-595`

**Issue:** Three handlers (`post_message`, `messages_stream`) duplicate the same `SELECT id ... FROM agent_containers WHERE agent_instance_id = $1 ORDER BY (stopped_at IS NULL) DESC, created_at DESC LIMIT 1` query inline. The DELETE handler doesn't need it. This is a minor DRY violation; the query already lives implicitly in the `inapp_messages_store` seam (`fetch_pending_for_dispatch` uses the same JOIN), but isn't extracted.

**Fix:** Add a small helper in `inapp_messages_store.py` or `run_store.py`: `async def fetch_most_recent_container_for_agent(conn, agent_id) -> dict | None` returning `(container_row_id, container_id, inapp_auth_token)`. Both handlers call it, single SQL seam discipline (the comment header at line 4-12 of `inapp_messages_store.py` already articulates this).

---

### IN-07: `forward_to_agent` swallows `httpx.RequestError` together with `ValueError`

**File:** `api_server/src/api_server/temporal/activities/forward_to_agent.py:186-195`

**Issue:** The `except (httpx.RequestError, ValueError)` arm catches both connection-level errors not in the `ConnectError/ReadTimeout` bucket AND `json.JSONDecodeError` (which subclasses `ValueError`). Both surface as `ApplicationError(type='bot_invalid_response', non_retryable=True)`. But a generic `httpx.RequestError` (e.g., DNS failure for the bridge IP, SSL handshake error) is structurally a transport failure that COULD retry usefully — it's been bucketed with "bot returned non-JSON 200" which definitely cannot retry. The error_type taxonomy collapses them into one "this isn't going to get better" bucket, which is fine for v1 but loses operator signal.

**Fix:** Split the except arms: `except httpx.RequestError as e` → `bot_transport_error` (or absorb into the existing `[0, 1, 2, 4]s` retry budget by adding `httpx.RequestError` to the retry-eligible exceptions on line 156). `except ValueError` → keep as `bot_invalid_response`. Cosmetic taxonomy improvement; consult `_KNOWN_ERROR_TYPES` enum first to add a new value if needed.

---

### IN-08: `dashboard_screen.dart` uses `// ignore: avoid_catches_without_on_clauses`

**File:** `mobile/lib/features/dashboard/dashboard_screen.dart:217-220`

**Issue:** The `} catch (_) {` swallows any error from `await ref.read(agentsListProvider.future)`. The `ignore` comment justifies it ("error visible via RetryBanner above list"), but the catch-all also swallows programmer errors (e.g., a future change to the provider that throws a `TypeError`). At minimum, narrow the catch to `DioException` or `on Object catch` with a logging hook.

**Fix:** Replace with `} on DioException catch (_) { /* RetryBanner displays this */ }` or similar narrowing, OR add a `developer.log` call so debug builds can see the swallowed error. Cosmetic; the current behavior is correct in the happy path.

---

### IN-09: `agent_messages.py` SSE `event_generator` re-imports inside loop scope

**File:** `api_server/src/api_server/routes/agent_messages.py:597-598`

**Issue:** `from ..services.event_store import fetch_events_after_seq` is imported inside the generator function body. It's executed every time a client connects, which is fine semantically (Python caches imports) but stylistically hides the dependency from the module-level imports list. The 22c.3 dispatcher (now reduced) used late imports for circular-cycle reasons; the SSE handler doesn't have that problem.

**Fix:** Move the import to the top of `agent_messages.py`. Same applies to the late `from ..services.inapp_messages_store import restart_sweep` in `main.py:168`.

---

### IN-10: Migration test relies on hardcoded `TEST_USER_ID` UUID across tests

**File:** `api_server/tests/test_migration_011_phase28.py:52`

**Issue:** `TEST_USER_ID = "00000000-0000-0000-0000-000000000028"` is shared across the two tests in the module. Because `pg` is module-scoped and `_seed_user_and_agent` does `ON CONFLICT (id) DO NOTHING`, the two tests share user state. If a future test adds an assertion like "user has exactly N messages", test ordering will silently affect outcomes.

**Fix:** Either generate a fresh UUID per test with `uuid4()`, or scope the user fixture per-test. The current pattern works for the existing assertions (each assertion is local to its INSERT) but is a foot-gun for future test additions.

---

_Reviewed: 2026-05-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
