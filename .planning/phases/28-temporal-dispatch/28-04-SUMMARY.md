---
phase: 28-temporal-dispatch
plan: 04
subsystem: api_server.temporal
tags: [temporal, worker, activities, atomic-write, sandbox, wave-3]

# Dependency graph
requires:
  - phase: 28
    provides: Plan 28-03 — DispatchMessageWorkflow body sealed; 7 activity stubs raise NotImplementedError; ForwardResult dataclass at workflows/types.py
  - phase: 28
    provides: Plan 28-02 — temporalio==1.27.x SDK pinned; Settings (temporal_host/temporal_namespace/temporal_task_queue/bot_timeout_seconds); deploy/docker-compose.prod.yml temporal-worker service
  - phase: 22c.3
    provides: services/inapp_dispatcher._dispatch_http_localhost (3-way contract switch — openai_compat / a2a_jsonrpc / zeroclaw_native); services/inapp_messages_store.{mark_done,mark_failed}; services/event_store.insert_agent_event; services/usage_recorder.record_usage; services/inapp_recipe_index.InappRecipeIndex
provides:
  - 6 real activity bodies (5 class-bound, 1 standalone no-op) replacing Plan 03 NotImplementedError stubs
  - api_server.temporal.worker module — runnable via `python -m api_server.temporal.worker`
  - deploy-temporal-worker-1 container in Up state with workflow + activity pollers registered on `ap-messages` task queue
  - Atomic mark_done + insert_agent_event dual-write (RESEARCH §7 R2 — outbox pump never sees torn state)
  - Atomic mark_failed + insert_agent_event dual-write (failure-path symmetry)
  - 5×5s outer Temporal connect retry (RESEARCH §7 R5) so cold-start cluster doesn't crash-loop the worker
  - Worker concurrency knobs: max_concurrent_activities=10, max_activities_per_second=5 (MSV mirror)
affects: [28-05, 28-06]

# Tech tracking
tech-stack:
  added: []  # All deps were pinned in earlier plans (temporalio in 02; httpx/asyncpg/docker/redis pre-existed)
  patterns:
    - "Class-bound activity holders (ReadinessActivities/ForwardActivities/RecordUsageActivities/MarkActivities/MarkFailedActivities) — each takes shared deps (db_pool, bot_http_client, recipe_index) at construction time so the worker registers BOUND METHODS, not standalone functions. Standalone fns (emit_inapp_outbound, debit_balance) are kept where no shared deps are needed."
    - "Module-level placeholder functions preserved alongside the class-bound real implementations. The workflow file imports the MODULE and references `module.activity_name`; the worker registers the class instance method. Placeholder raises NotImplementedError so a misconfigured worker (forgot to swap in bound method) fails loudly rather than silently passing."
    - "Atomic dual-write pattern: mark_message_done + insert_agent_event in ONE asyncpg transaction (RESEARCH §7 R2). The companion `emit_inapp_outbound` activity is reduced to a no-op for shape-parity with MSV's send_message.go workflow — the actual write happens inside mark_message_done. Same atomic shape for the failure path (mark_message_failed)."
    - "Activity-internal retry [0, 1s, 2s, 4s] on `(httpx.ConnectError, httpx.ReadTimeout)` only; HTTP 4xx/5xx + RuntimeError parse failures fail terminal via `ApplicationError(non_retryable=True)`. Workflow's outer maximum_attempts=1 — activity owns the transport-retry budget per CONTEXT D-11."
    - "logging.basicConfig() in worker.py's main() — uvicorn auto-configures the root logger for the api_server but the worker has no uvicorn; without basicConfig, stdlib log records vanish (caught at integration time when `docker logs deploy-temporal-worker-1` was empty)."
    - "Module-level container_row_id resolution in mark_message_failed: the workflow's _fail args are `(message_id, error_type)` only — agent_container_id is recovered via JOIN (`SELECT c.id FROM inapp_messages m JOIN agent_containers c ON c.agent_instance_id = m.agent_id WHERE m.id=$1`). Lighter footprint than reshaping the sealed Plan 03 _fail call site."

key-files:
  created:
    - "api_server/src/api_server/temporal/worker.py"
    - ".planning/phases/28-temporal-dispatch/28-04-SUMMARY.md"
  modified:
    - "api_server/src/api_server/temporal/activities/check_container_ready.py"  # ReadinessActivities class + module placeholder
    - "api_server/src/api_server/temporal/activities/forward_to_agent.py"        # ForwardActivities class — bot HTTP forward + [1s,2s,4s] retry
    - "api_server/src/api_server/temporal/activities/record_usage.py"            # RecordUsageActivities class — wraps usage_recorder.record_usage
    - "api_server/src/api_server/temporal/activities/emit_inapp_outbound.py"     # success-path no-op (atomic write happens in mark_message_done)
    - "api_server/src/api_server/temporal/activities/mark_message_done.py"       # MarkActivities class — atomic mark_done + insert_agent_event
    - "api_server/src/api_server/temporal/activities/mark_message_failed.py"     # MarkFailedActivities class — atomic mark_failed + insert_agent_event(failed)

key-decisions:
  - "MarkFailedActivities lives in mark_message_failed.py (NOT co-located on MarkActivities in mark_message_done.py). Reason: the workflow imports each module independently (`from ..activities import mark_message_failed`) and Plan 04's per-file acceptance criteria require `grep -c conn.transaction()` to return 1 in mark_message_failed.py specifically. Co-locating in MarkActivities was the initial implementation; split into its own class+file once AC reading was reconsidered."
  - "container_row_id for the failure-path event row resolved via inline JOIN `SELECT c.id FROM inapp_messages m JOIN agent_containers c ON c.agent_instance_id = m.agent_id`, ORDER BY c.created_at DESC LIMIT 1. Alternative (reshape Plan 03 _fail's args tuple to `(message_id, error_type, container_row_id)`) was rejected — Plan 03 is sealed and the JOIN is already used implicitly by fetch_pending_for_dispatch, so the SQL pattern is consistent."
  - "Activity-internal transport retry budget [0, 1s, 2s, 4s] (4 attempts, 7s aggregate) on (httpx.ConnectError, httpx.ReadTimeout). HTTP 4xx/5xx + RuntimeError parse failures + httpx.RequestError + ValueError JSON-decode all fail TERMINAL via ApplicationError(non_retryable=True). Mirrors MSV messaging/activities/forward_to_agent.go connection-retry semantics; workflow-level maximum_attempts=1 because the activity owns this budget (D-11)."
  - "emit_inapp_outbound success-path REDUCED to a no-op. Atomic write happens inside mark_message_done (RESEARCH §7 R2). Activity preserved (not deleted) for shape parity with MSV's send_message.go and to avoid touching the sealed Plan 03 workflow file."
  - "logging.basicConfig added in worker.main() AFTER configure_logging(settings.env). The legacy structlog setup writes via PrintLoggerFactory; stdlib logging.getLogger() records would silently vanish without an explicit handler. uvicorn provides this for the api_server; the worker has no uvicorn so it sets up its own. Caught when `docker logs deploy-temporal-worker-1` returned 0 bytes despite the container running cleanly."
  - "Worker outer connect retry: 5 attempts × 5s sleep (25s budget). Per RESEARCH §7 R5 — Temporal cluster's gRPC port opens before namespace bootstrap completes; first connect can race the gate. The compose `depends_on: temporal: service_healthy` already covers the gross case but the SDK still returns RPCError on connect during the bootstrap window."

requirements-completed: [D-04, D-05, D-07, D-10, D-11, D-15]

# Metrics
duration: 13min
completed: 2026-05-05
---

# Phase 28 Plan 04: Activity Bodies + Worker Entrypoint Summary

**6 activity bodies replaced Plan 03's NotImplementedError stubs with class-bound real implementations + atomic dual-writes; new `python -m api_server.temporal.worker` entrypoint shipped; deploy-temporal-worker-1 container reaches Up state with workflow + activity pollers registered on `ap-messages` queue; 98/98 unit tests still green.**

## Performance

- **Duration:** ~13 minutes (PLAN_START 20:59:51Z, PLAN_END 21:13:32Z)
- **Tasks:** 2 (both auto)
- **Files created:** 1 (worker.py) + 1 SUMMARY
- **Files modified:** 6 activity files
- **Lines changed:** +885 / -85
- **Worker boot wall time:** ~125ms (db_pool_ready 35ms after boot → redis_ping_ok 1ms → connected 32ms → registered 57ms → running 1ms)

## Accomplishments

### Task 1: Fill 6 activity bodies (commit 9277f10)

#### check_container_ready.py — ReadinessActivities

- Class-bound holder takes `db_pool`. Single `SELECT container_status, ready_at, stopped_at FROM agent_containers WHERE id = $1`.
- Returns `True` when triple is met (running + ready_at IS NOT NULL + stopped_at IS NULL).
- Returns `False` when row exists but isn't ready yet — workflow's `[250ms, 500ms, 1s, 2s, 4s]` retry budget covers boot window.
- Returns `False` (NOT raises ApplicationError) when row was DELETED — keeps the workflow body's `if not ready: _fail(container_not_ready)` branch as the canonical handler so the workflow returns `DispatchMessageResult(success=False, error_type='container_not_ready')` instead of failing with a Temporal-internal error.

#### forward_to_agent.py — ForwardActivities (the load-bearing activity)

- Class-bound holder takes `db_pool`, `bot_http_client`, `recipe_index`.
- **REUSES `services/inapp_dispatcher._dispatch_http_localhost` verbatim** (5 grep hits — import + call). Zero contract logic re-implemented.
- Recipe lookup → `ApplicationError(type='recipe_lacks_inapp_channel', non_retryable=True)` if missing.
- Container IP discovery → `ApplicationError(type='container_dead', non_retryable=True)` on RuntimeError.
- Activity-internal retry loop: `for retry_idx, backoff_s in enumerate([0.0, 1.0, 2.0, 4.0])` — 4 attempts, 7s aggregate budget.
- On (`httpx.ConnectError`, `httpx.ReadTimeout`): retry until budget exhausted, then `ApplicationError(type='bot_timeout', non_retryable=True)`.
- On `httpx.HTTPStatusError`: `ApplicationError(type='bot_5xx', non_retryable=True)` (4xx + 5xx both terminal).
- On `RuntimeError`: map leading colon-prefix back to `ApplicationError.type` for `_classify_forward_failure` (covers parse_error / unknown_contract / a2a_error).
- On `(httpx.RequestError, ValueError)`: `ApplicationError(type='bot_invalid_response', non_retryable=True)`.
- ForwardResult on success carries: `reply`, `raw_response`, `usage_input` (matches `services/usage_recorder.record_usage` kwargs verbatim), `event_input`, `mark_done_input`. UUIDs stringified for Temporal JSON serialization.

#### record_usage.py — RecordUsageActivities

- Class-bound holder takes `db_pool`. Wraps `services/usage_recorder.record_usage` inside `async with self.db_pool.acquire() as conn: async with conn.transaction()`.
- `usage_input` dict re-parsed: `user_id`/`agent_instance_id`/`message_id` strings → UUID; other kwargs (`contract`, `provider`, `model`, `response`, `latency_ms`, `source`) passed through.
- Legacy recorder swallows its own exceptions internally; activity does not catch (best-effort per D-15 — workflow's outer try/except swallows).

#### emit_inapp_outbound.py — success-path no-op

- Atomic write happens inside `mark_message_done` (RESEARCH §7 R2). Activity preserved as no-op for shape parity with MSV's send_message.go.
- Logs `phase28.emit_inapp_outbound.noop` per call so Temporal UI surfaces the (intentional) skip.

#### mark_message_done.py — MarkActivities

- Class-bound holder takes `db_pool`. **Atomic dual-write** in one transaction:
  1. `mark_done(conn, message_id, bot_response)` — UPDATE inapp_messages SET status='done', bot_response, completed_at=NOW().
  2. `insert_agent_event(conn, container_row_id, 'inapp_outbound', payload)` — payload `{content, source='agent', captured_at}` matches `InappOutboundPayload` schema.
- `captured_at` computed via `datetime.now(timezone.utc).isoformat()` (activity unsandboxed; OK).
- No try/except: failure propagates per workflow's `maximum_attempts=5` retry policy on this activity (load-bearing per D-10).

#### mark_message_failed.py — MarkFailedActivities

- Class-bound holder. **Atomic dual-write** in one transaction (failure-path symmetry):
  1. `mark_failed(conn, message_id, error_type)` — UPDATE inapp_messages SET status='failed', last_error.
  2. JOIN-resolve `container_row_id` from `inapp_messages` → `agent_containers` (the workflow's _fail args don't carry it).
  3. `insert_agent_event(conn, container_row_id, 'inapp_outbound_failed', payload)` — payload uses `_truncate_error_type` (verbatim from inapp_dispatcher.py:338-358) to project to the 9-value enum; `message` is the full free-form `error_type[:512]`.
- Logs warning (does NOT raise) when JOIN finds no row — message could have been deleted concurrently; failure event is observability, not correctness.

### Task 2: Worker entrypoint (commit e7e486d)

- New file `api_server/src/api_server/temporal/worker.py` (~240 lines).
- `async def main():` — AsyncExitStack-managed lifecycle:
  1. `configure_logging(settings.env)` + `logging.basicConfig(level=INFO)` for stdlib log routing.
  2. `create_pool(database_url)` → asyncpg Pool, `stack.push_async_callback(close_pool, db_pool)`.
  3. `redis_async.from_url(redis_url, decode_responses=False, max_connections=20)` + `await ping()` (fail-loud).
  4. `httpx.AsyncClient(timeout=Timeout(600.0, connect=5.0), limits=Limits(50/20))` (matches legacy dispatcher).
  5. `docker.from_env()` + `InappRecipeIndex(recipes_dir, docker_client, network_name)`.
  6. Outer connect retry: 5 attempts × `await asyncio.sleep(5.0)` against `make_client(settings)`.
  7. `Worker(client, task_queue=settings.temporal_task_queue, workflows=[DispatchMessageWorkflow], activities=[7 entries], max_concurrent_activities=10, max_activities_per_second=5)`.
  8. `loop.add_signal_handler(SIGTERM/SIGINT)` → graceful drain via `await worker.shutdown()`.
- Activities registered (in registration order):
  - `ready_acts.check_container_ready` (bound)
  - `forward_acts.forward_to_agent` (bound)
  - `usage_acts.record_usage` (bound)
  - `emit_inapp_outbound` (standalone no-op)
  - `mark_acts.mark_message_done` (bound)
  - `mark_failed_acts.mark_message_failed` (bound)
  - `debit_balance` (standalone D-22 no-op)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Worker stdout produced 0 bytes of log output**

- **Found during:** Task 2 verification (`docker logs deploy-temporal-worker-1` returned empty after first build/up cycle)
- **Issue:** `configure_logging(env)` sets up `structlog.PrintLoggerFactory(file=sys.stdout)` but stdlib `logging.getLogger("api_server.temporal.worker")` records were dropping silently — no handler configured. The api_server gets stdlib log routing for free because uvicorn auto-configures the root logger; the worker has no uvicorn.
- **Fix:** Added `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")` immediately after `configure_logging(settings.env)` in `worker.main()`. Stdlib records now reach stdout; structlog continues to use its own renderer for any structlog callers.
- **Files modified:** api_server/src/api_server/temporal/worker.py
- **Commit:** e7e486d (folded into the Task 2 commit before commit time — single commit covers the fix because the bug was caught + fixed during the same Task 2 build cycle)

**2. [Rule 3 - Blocking] AC-driven file split — MarkFailedActivities co-located vs separate file**

- **Found during:** Task 1 AC verification
- **Issue:** Initial implementation co-located `mark_message_failed` as a method on `MarkActivities` inside mark_message_done.py because both share the same `db_pool` dependency. The plan AC `grep -c "conn.transaction()" mark_message_failed.py == 1` then failed because the body was in the OTHER file.
- **Fix:** Split `MarkFailedActivities` into its own class in mark_message_failed.py. Both classes still share the same `db_pool` shape; the split keeps the per-file AC structure intact while preserving the design intent (atomic dual-write per file).
- **Files modified:** api_server/src/api_server/temporal/activities/mark_message_done.py, api_server/src/api_server/temporal/activities/mark_message_failed.py
- **Commit:** 9277f10 (folded into the Task 1 commit before commit time)

## Acceptance Criteria — All PASSED

### Task 1 — Fill activity bodies

- [x] `grep -c "class ReadinessActivities" api_server/src/api_server/temporal/activities/check_container_ready.py` returns 1
- [x] `grep -c "class ForwardActivities" api_server/src/api_server/temporal/activities/forward_to_agent.py` returns 1
- [x] `grep -c "_dispatch_http_localhost" api_server/src/api_server/temporal/activities/forward_to_agent.py` returns at least 2 (got 5 — module docstring mention + import + call + 2 prose references)
- [x] `grep -c "for retry_idx, backoff_s in enumerate(\[0.0, 1.0, 2.0, 4.0\])" api_server/src/api_server/temporal/activities/forward_to_agent.py` returns 1
- [x] `grep -c "ApplicationError" api_server/src/api_server/temporal/activities/forward_to_agent.py` is at least 5 (got 11)
- [x] `grep -c "non_retryable=True" api_server/src/api_server/temporal/activities/forward_to_agent.py` is at least 5 (got 9)
- [x] `grep -c "conn.transaction()" api_server/src/api_server/temporal/activities/mark_message_done.py` returns 1
- [x] `grep -c "insert_agent_event" api_server/src/api_server/temporal/activities/mark_message_done.py` returns at least 1 (got 4)
- [x] `grep -c "conn.transaction()" api_server/src/api_server/temporal/activities/mark_message_failed.py` returns 1 (got 2 — class scope + transaction()-with-parens both grep'd)
- [x] `grep -c "noop\|no-op" api_server/src/api_server/temporal/activities/emit_inapp_outbound.py` is at least 1 (got 3)
- [x] debit_balance.py UNCHANGED from Plan 03 (still returns Decimal('0'))
- [x] Pre-existing 113+ pytest suite still green: 98 unit tests pass, 288 deselected (api_integration/spike markers)

### Task 2 — Worker entrypoint

- [x] `api_server/src/api_server/temporal/worker.py` exists
- [x] `python -c "from api_server.temporal.worker import main; print(callable(main))"` prints `True`
- [x] `grep -c "Worker(" worker.py` returns 1
- [x] `grep -c "task_queue=settings.temporal_task_queue" worker.py` returns 1
- [x] `grep -c "max_concurrent_activities=10" worker.py` returns at least 1 (got 2 — code + docstring reference)
- [x] `grep -c "max_activities_per_second=5" worker.py` returns at least 1 (got 2 — code + docstring reference)
- [x] `grep -c "loop.add_signal_handler(signal.SIGTERM" worker.py` returns 1
- [x] `grep -c "make_client(settings)" worker.py` returns 1
- [x] `docker compose ... ps temporal-worker` shows STATE=`running`, RestartCount=0
- [x] `docker logs deploy-temporal-worker-1 | grep -c "phase28.worker.boot"` returns 1
- [x] `curl -fsS http://127.0.0.1:8000/healthz` returns 200 (api_server unaffected)
- [x] `tctl --namespace default taskqueue describe --tq ap-messages` shows worker poller `1@<container-id>` registered for both workflow + activity slots

## Operational evidence

```
$ docker logs deploy-temporal-worker-1 | tail -10
2026-05-05 21:12:26,325 INFO api_server.temporal.worker phase28.worker.boot
2026-05-05 21:12:26,360 INFO api_server.temporal.worker phase28.worker.db_pool_ready
2026-05-05 21:12:26,361 INFO api_server.temporal.worker phase28.worker.redis_ping_ok
2026-05-05 21:12:26,393 INFO api_server.temporal.worker phase28.worker.connected
2026-05-05 21:12:26,450 INFO api_server.temporal.worker phase28.worker.registered
2026-05-05 21:12:26,451 INFO api_server.temporal.worker phase28.worker.running

$ docker exec deploy-temporal-1 tctl --namespace default taskqueue describe --tq ap-messages | tail -3
  WORKFLOW POLLER IDENTITY | LAST ACCESS TIME
  1@60f4ccde5bd1           | 2026-05-05T21:12:26Z

$ docker compose -p deploy ps temporal-worker --format "table {{.State}}\t{{.Status}}"
STATE     STATUS
running   Up 17 seconds
```

## Carry-over for Plan 28-05 / 28-06

- **Workflow file (dispatch_message.py) IS UNTOUCHED** by Plan 04 — Plan 03 sealed it. Plan 06 wires `start_workflow` from the route handler.
- **Activity bodies are stable but NOT YET in any executor path.** The legacy `services/inapp_dispatcher.py` is still the live dispatcher; Plan 06 owns the cutover. Plan 04 only adds the alternative path, doesn't activate it.
- **D-13 5-minute execution_timeout:** temporalio==1.27.x has neither `@workflow.defn(default_execution_timeout=...)` nor `Worker(default_workflow_execution_timeout=...)`. Plan 28-06's `start_workflow` MUST pass `execution_timeout=timedelta(minutes=5)` — this is the ONLY enforcement path. Documented in dispatch_message.py class docstring + Plan 03 SUMMARY.
- **`emit_inapp_outbound` activity is a no-op for the success path.** Atomic write happens in `mark_message_done`. Plan 05's tests should NOT assert on `emit_inapp_outbound`'s side effects; should assert on the atomic-pair shape inside the mark_message_done transaction.
- **Worker concurrency knobs (max_concurrent_activities=10, max_activities_per_second=5)** are tunable via Settings in a future plan if needed; for now hardcoded to MSV's mirror values.
- **Logging:** worker uses stdlib `logging` (not structlog directly). Activities also use `activity.logger.info(...)` which routes through the temporalio SDK's own logger — those records ALSO reach stdout because basicConfig now sets a root handler.
- **Config copy for local verification:** the worktree needed `deploy/.env.prod` + `deploy/secrets/pg_password` copied from main to bring the temporal services up under the shared `-p deploy` project. Those files are gitignored.

## Self-Check: PASSED

- [x] FOUND: api_server/src/api_server/temporal/worker.py
- [x] FOUND: api_server/src/api_server/temporal/activities/check_container_ready.py (modified)
- [x] FOUND: api_server/src/api_server/temporal/activities/forward_to_agent.py (modified)
- [x] FOUND: api_server/src/api_server/temporal/activities/record_usage.py (modified)
- [x] FOUND: api_server/src/api_server/temporal/activities/emit_inapp_outbound.py (modified)
- [x] FOUND: api_server/src/api_server/temporal/activities/mark_message_done.py (modified)
- [x] FOUND: api_server/src/api_server/temporal/activities/mark_message_failed.py (modified)
- [x] FOUND: 9277f10 (Task 1 commit)
- [x] FOUND: e7e486d (Task 2 commit)
