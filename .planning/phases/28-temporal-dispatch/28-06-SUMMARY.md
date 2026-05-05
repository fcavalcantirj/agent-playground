---
phase: 28-temporal-dispatch
plan: 06
subsystem: api_server / temporal
tags: [cutover, temporal, dispatcher, big-bang, defense-in-depth]
requires:
  - alembic head 011_phase28_workflow_id_idem (Plan 28-05)
  - tools/migrate_phase28_stuck_rows.py (Plan 28-05)
  - DispatchMessageWorkflow + 7 activities (Plans 28-03 + 28-04)
  - app.state.settings carries temporal_host / temporal_namespace / temporal_task_queue / bot_timeout_seconds (Plan 28-02)
provides:
  - app.state.temporal_client owned by FastAPI lifespan
  - POST /v1/agents/:id/messages starts DispatchMessageWorkflow
  - inapp_messages.workflow_id back-fill for ops correlation
  - documented rollback recipe (Step 6, written down — not executed)
  - reduced-role services/inapp_dispatcher.py (helpers only; pump deleted)
affects:
  - api_server/src/api_server/main.py (lifespan)
  - api_server/src/api_server/routes/agent_messages.py (POST handler)
  - api_server/src/api_server/services/inapp_messages_store.py (insert_pending + set_workflow_id)
  - api_server/src/api_server/services/inapp_dispatcher.py (pump deleted; helpers kept)
  - api_server/src/api_server/temporal/activities/check_container_ready.py (dict→namespace coerce)
  - api_server/src/api_server/temporal/activities/forward_to_agent.py (dict→namespace coerce)
  - api_server/src/api_server/temporal/activities/debit_balance.py (return type str, not Decimal)
tech-stack:
  added: []
  patterns:
    - Lifespan-owned Temporal client (5×5s connect retry mirror of worker.py)
    - Per-start execution_timeout=timedelta(minutes=5) (D-13 — only enforcement path in temporalio==1.27.0)
    - User-scoped workflow ID `msg-{user_id}-{message_uuid}` (D-08 revised)
    - WorkflowAlreadyStartedError treated as idempotent replay (paired with REJECT_DUPLICATE policy)
    - Postgres ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO UPDATE no-op idiom (D-14 column-level defense)
    - SimpleNamespace shim for activities reading DispatchMessageInput-shape inputs typed as Any
key-files:
  created:
    - .planning/phases/28-temporal-dispatch/28-06-SUMMARY.md
  modified:
    - api_server/src/api_server/main.py
    - api_server/src/api_server/routes/agent_messages.py
    - api_server/src/api_server/services/inapp_messages_store.py
    - api_server/src/api_server/services/inapp_dispatcher.py
    - api_server/src/api_server/temporal/activities/check_container_ready.py
    - api_server/src/api_server/temporal/activities/forward_to_agent.py
    - api_server/src/api_server/temporal/activities/debit_balance.py
decisions:
  - "Workflow ID format `msg-{user_id}-{message_id}` (D-08 revised) — Temporal UI search ``msg-{user_id}-*`` lists every workflow for that user; defense-in-depth against cross-user mis-dispatch."
  - "execution_timeout=timedelta(minutes=5) passed per start_workflow call — D-13 confirms this is the only enforcement path in temporalio==1.27.0 (defn-level + worker-level defaults are not exposed)."
  - "WorkflowIDReusePolicy.REJECT_DUPLICATE pairs with the IdempotencyMiddleware 24h TTL AND the column-level UNIQUE partial index from migration 011 — three layers of duplicate-key defense (D-14 defense-in-depth)."
  - "_handle_row + dispatcher_loop deleted; _dispatch_http_localhost + _truncate_error_type + _KNOWN_ERROR_TYPES + _row_get retained because activities import them. inapp_dispatcher.py module docstring updated with a banner explaining the reduced role."
  - "insert_pending now accepts idempotency_key kwarg; INSERT uses ON CONFLICT DO UPDATE SET content=inapp_messages.content RETURNING id (Postgres no-op idempotent insert idiom layered on top of the partial UNIQUE index from migration 011)."
metrics:
  duration: "~22m"
  completed: "2026-05-05"
  tasks: 2
  files_modified: 7
  files_created: 1
  commits: 3
---

# Phase 28 Plan 06: Cutover — DispatchMessageWorkflow replaces the asyncpg pump

**One-liner:** the load-bearing big-bang swap. POST /v1/agents/:id/messages now starts a DispatchMessageWorkflow via the lifespan-owned Temporal client; the legacy ``dispatcher_loop`` + ``_handle_row`` are deleted; reaper + outbox preserved. Live end-to-end smoke against two contracts (openai_compat → nano-kaiku-test, zeroclaw_native → zeroclaw-mimo) PASS.

## Cutover Commit Chain

| # | Hash | Message |
|---|------|---------|
| 1 | `843d8be` | feat(28-06): wire Temporal client into lifespan; delete dispatcher_loop task |
| 2 | `6feb361` | feat(28-06): cutover — POST /messages starts DispatchMessageWorkflow; delete dispatcher_loop + _handle_row |
| 3 | `1b33198` | fix(28-06): unblock cutover smoke — 3 Rule-1 fixes surfaced by live workflow run |

The headline cutover commit is **`6feb361`** — that is the commit a future operator passes to ``git revert`` per the rollback recipe below.

## Step 0 — Pre-flight Cutover Sweep Evidence

Plan 05's `tools/migrate_phase28_stuck_rows.py` was invoked BEFORE any code edits landed (per RESEARCH §7 R1). On `deploy-postgres-1` (the running dev stack at base commit `31deef7`):

| Phase | Command | row_count |
|-------|---------|-----------|
| pre   | `docker exec deploy-api_server-1 python /app/tools/migrate_phase28_stuck_rows.py --dry-run` | **0** |
| live  | (skipped — pre count was 0; no rows to transition) | **0** |
| post  | `docker exec deploy-api_server-1 python /app/tools/migrate_phase28_stuck_rows.py --dry-run` | **0** |

Stack was clean before the cutover. Re-running the dry-run after the entire plan also returned `row_count=0`. The sweep script is idempotent + safety-capped per Plan 05.

## Smoke Evidence

### Live curl test #1 — openai_compat contract (nanobot recipe → claude-haiku)

```
SESSION_ID="9ab75330-7b43-43a4-b3f9-0652c9159b8e"
AGENT_ID="335340fc-d306-42c9-b2a6-0c0dc8c8695c"  # nano-kaiku-test
curl -sS -X POST "http://127.0.0.1:8000/v1/agents/${AGENT_ID}/messages" \
  -H "Content-Type: application/json" \
  -H "Cookie: ap_session=${SESSION_ID}" \
  -H "Idempotency-Key: phase28-cutover-smoke-v3-$(date +%s)" \
  -d '{"content": "phase28 cutover v3 smoke"}'
```

- HTTP 202 with `{"message_id":"64c4dc16-2c75-450e-97d6-1c32c2ad92dd","status":"pending","queued_at":"2026-05-05T21:53:02.606699+00:00"}`
- Temporal workflow id: **`msg-e6ef1f9e-d8be-4f87-92b9-822a175f08fd-64c4dc16-2c75-450e-97d6-1c32c2ad92dd`** (D-08 revised user-scoped format)
- Workflow run id: `019dfa21-587c-7102-bd46-8599fb125e7b`
- temporal-worker logs:
  - `phase28.forward_to_agent.attempt` (attempt 1, no retry)
  - `phase28.emit_inapp_outbound.noop`
- Final DB state: `status='done'`, `bot_response="I'm ready to help with the phase28 cutover v3 smoke test. ..."`, `workflow_id` back-filled, completed-at − created-at = **2.81 s**.

### Live curl test #2 — zeroclaw_native contract (zeroclaw recipe → mimo)

- POST → 202 `{"message_id":"b35b75f7-1dd9-4c40-977f-186e84d09ec7","status":"pending"}`.
- 8 s later: `status='done'`, `bot_response="Hey there! 👋 What can I help you with today?"`.

Both contracts work end-to-end through the new Temporal pump.

### Temporal UI

- `curl -fsS http://127.0.0.1:8088/` → HTTP 200 (Temporal UI reachable on the local-overlay port).
- The workflow execution above is visible in the UI under namespace `default`, task queue `ap-messages`, status COMPLETED.

### Lifespan + worker logs

```
deploy-api_server-1   — healthz=200; no `inapp-dispatcher` / `inapp_dispatcher` task name in logs.
deploy-temporal-worker-1:
  phase28.worker.boot
  phase28.worker.db_pool_ready
  phase28.worker.redis_ping_ok
  phase28.worker.connected
  phase28.worker.registered
  phase28.worker.running
```

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Lifespan wiring — temporal_client up, dispatcher_loop down | `843d8be` | `api_server/src/api_server/main.py` |
| 2 | Cutover sequence — pre-flight sweep, route handler edits, dispatcher deletion, smoke, rollback recipe | `6feb361` | `api_server/src/api_server/routes/agent_messages.py`, `api_server/src/api_server/services/inapp_messages_store.py`, `api_server/src/api_server/services/inapp_dispatcher.py` |
| 2 (deviation fixes) | Auto-fixed 3 Rule-1 bugs that prevented the cutover smoke | `1b33198` | `api_server/src/api_server/routes/agent_messages.py`, `api_server/src/api_server/temporal/activities/check_container_ready.py`, `api_server/src/api_server/temporal/activities/debit_balance.py`, `api_server/src/api_server/temporal/activities/forward_to_agent.py` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] WorkflowIDReusePolicy import path**
- **Found during:** Task 2 Step 5 — first restart of api_server with new code surfaced `ImportError: cannot import name 'WorkflowIDReusePolicy' from 'temporalio.client'` at module load. Container couldn't even reach healthz.
- **Issue:** Plan 06 prescribed `from temporalio.client import WorkflowIDReusePolicy`. The symbol actually lives in `temporalio.common` (verified via `dir(temporalio.common)` against the pinned `temporalio==1.27.0` SDK in deploy-temporal-worker-1).
- **Fix:** changed import to `from temporalio.common import WorkflowIDReusePolicy`. Behavior identical — the enum value is the same.
- **Files modified:** `api_server/src/api_server/routes/agent_messages.py`
- **Commit:** `1b33198`

**2. [Rule 1 — Bug] Activities receive a dict, not the DispatchMessageInput dataclass**
- **Found during:** Task 2 Step 5 — first end-to-end smoke. The api_server returned 202 and the Temporal workflow started, but `check_container_ready` raised `AttributeError: 'dict' object has no attribute 'container_row_id'` 5 times in a row, exhausting its retry budget.
- **Issue:** Plan 03's activity-stub discipline declares `inp: Any` to sidestep the workflows ↔ activities circular import at `@activity.defn` decoration time. With `Any` as the runtime type-hint, Temporal's default JSON payload converter deserializes the dataclass into a plain dict on receive — but the activity bodies use attribute access (`inp.container_row_id`, `inp.recipe_name`, etc.). The two activities consuming `DispatchMessageInput`-shaped inputs (`check_container_ready` and `forward_to_agent`) both broke; the other 5 activities use `dict[str, Any]` hints + dict-key access so they were unaffected.
- **Fix:** added a module-private `_coerce_inp(inp)` helper in both `check_container_ready.py` and `forward_to_agent.py` that wraps dict-shaped inputs in `types.SimpleNamespace`. Already-namespaced inputs (e.g. tests passing dataclasses) pass through untouched. The activity bodies stay readable; the fix is a single line per activity (`inp = _coerce_inp(inp)` before the first attribute access).
- **Files modified:** `api_server/src/api_server/temporal/activities/check_container_ready.py`, `api_server/src/api_server/temporal/activities/forward_to_agent.py`
- **Commit:** `1b33198`

**3. [Rule 1 — Bug] debit_balance returned non-JSON-serializable Decimal**
- **Found during:** Task 2 Step 5 — second end-to-end smoke (after the dict-coerce fix). Workflow advanced past `check_container_ready` + `forward_to_agent` + `record_usage`, then `debit_balance` raised `TypeError: Object of type Decimal is not JSON serializable` when Temporal attempted to encode the `Decimal('0')` activity return value into a payload.
- **Issue:** Plan 03's `debit_balance` activity returns `Decimal('0')` so the workflow logs a deterministic "0 currency units debited" trace. Temporal's default JSON payload converter does not handle Decimal natively; the wire must be JSON-serializable.
- **Fix:** changed return type from `Decimal` to `str`, returning `"0"`. Phase B can recover the typed value losslessly via `Decimal(returned_value)`. The workflow's `try/except ApplicationError` around debit_balance is unchanged; the workflow swallows the return value in Phase 28 either way (D-22 best-effort).
- **Files modified:** `api_server/src/api_server/temporal/activities/debit_balance.py`
- **Commit:** `1b33198`

These three bugs were Plan 03/04 oversights that only surfaced under live execution; static checks + grep gates were silent on them. The cutover plan was the right surface to catch them — Plan 03's spike B had verified the workflow registers cleanly, but did not exercise a full end-to-end run.

## Rollback Recipe

This is the documented procedure for reverting the cutover. **Written down now (planning time) so it is unambiguous if invoked under time pressure.** Pattern matches Phase 22c.3.1 + Phase 23 cutover plans.

### 1. Identify the cutover commit hash

The cutover landed across three commits:

- `843d8be` — Task 1 lifespan wiring
- `6feb361` — **Task 2 main cutover (the load-bearing commit)**
- `1b33198` — Rule-1 fix-ups (without these the cutover doesn't work end-to-end)

Reverting just `6feb361` may not be enough if commit `1b33198` introduced changes outside of the dispatcher cutover surface that are still wanted. In practice all three should be reverted together to return to the pre-cutover behavior.

### 2. Revert the commits

```
git revert --no-edit 1b33198 6feb361 843d8be
```

This restores:
- `api_server/src/api_server/main.py` — lifespan starts dispatcher_loop again; no temporal_client.
- `api_server/src/api_server/routes/agent_messages.py` — POST handler returns 202 after insert_pending only; no start_workflow call; no idempotency_key column write.
- `api_server/src/api_server/services/inapp_messages_store.py` — insert_pending without the idempotency_key kwarg; no set_workflow_id helper.
- `api_server/src/api_server/services/inapp_dispatcher.py` — `_handle_row`, `_terminal_failure`, and `dispatcher_loop` come back; full module restored.
- `api_server/src/api_server/temporal/activities/{check_container_ready,forward_to_agent,debit_balance}.py` — Rule-1 fixes are removed; the activities are reverted to their Plan 03/04 state. (Harmless when the worker isn't running.)

### 3. Temporal-side cleanup AFTER revert

The migration-011 columns (`workflow_id`, `idempotency_key`) were ADDED in Plan 28-05 and are SCHEMA-ONLY. Reverting Phase 28 code does NOT require running `alembic downgrade` — the columns remain nullable + harmless. The partial UNIQUE index on `(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL` likewise stays; with no writes setting `idempotency_key`, it indexes nothing.

Pending workflows started during the cutover window must be terminated so they don't conflict with the asyncpg path picking the same rows back up:

```
docker exec deploy-temporal-1 temporal workflow terminate \
    --query 'WorkflowType="DispatchMessageWorkflow" AND ExecutionStatus="Running"' \
    --reason "phase28 rollback"
```

(Run from a host that can reach `localhost:7233` — i.e. with the `deploy/docker-compose.local.yml` overlay so 7233 is host-published, OR `docker exec deploy-temporal-1 temporal workflow terminate ...`.)

Stale `inapp_messages` rows that the workflow had partially advanced (e.g. `status='forwarded'` from `forward_to_agent` but no `mark_message_done` — extremely rare given the per-attempt retry policy) are picked up by the legacy reaper at the next 11-minute cycle (`services/inapp_reaper.py`).

### 4. Post-revert verification

- `make dev-api-local` (or the `DOCKER_GID=0 docker compose ... up -d api_server temporal-worker` invocation used during the smoke test) brings the stack up.
- `curl -fsS http://127.0.0.1:8000/healthz` → 200.
- Send a curl message: it should reach `inapp_messages.bot_response` via the legacy `_handle_row` path — NOT through Temporal. The api_server logs should show the `inapp-dispatcher` task name in the lifespan startup log; NO `phase28.start_workflow` log lines.

### 5. Record revert in SUMMARY

If rollback is executed, append to this file:

```
## Rollback executed
- Revert commit hash: <hash>
- Reason: <one-line summary of why the forward fix failed>
- Pending workflows terminated: <count>
- Reaper-swept rows post-revert: <count from next reaper cycle, captured ~12 min later>
```

## Verification Status

- [x] Pre-flight cutover sweep ran with pre/live/post = 0/0/0 BEFORE any code edit.
- [x] `_handle_row` + `dispatcher_loop` DELETED from inapp_dispatcher.py (`grep -c "async def _handle_row"` → 0; `grep -c "async def dispatcher_loop"` → 0).
- [x] `_dispatch_http_localhost` + `_truncate_error_type` + `_KNOWN_ERROR_TYPES` + `_row_get` retained (forward_to_agent + mark_message_failed activities consume them).
- [x] POST /messages calls `start_workflow` with REJECT_DUPLICATE + execution_timeout=timedelta(minutes=5) (D-13).
- [x] WorkflowAlreadyStartedError handler returns 202 (idempotent replay).
- [x] User-scoped workflow ID `msg-{user_id}-{message_id}` (D-08 revised).
- [x] Lifespan owns app.state.temporal_client; no `app.state.inapp_tasks` entry for `inapp_dispatcher`.
- [x] reaper + outbox tasks unchanged (RESEARCH §7 R1 + R7).
- [x] insert_pending accepts idempotency_key kwarg; ON CONFLICT (user_id, idempotency_key) returns existing row.
- [x] set_workflow_id helper added; route back-fills the column for ops correlation.
- [x] Real message round-trip via curl works end-to-end against TWO contracts (openai_compat + zeroclaw_native), reaching the bot, getting a reply, landing in `inapp_messages.bot_response` with `status='done'`.
- [x] Temporal UI at http://127.0.0.1:8088 is reachable; workflow executions visible.
- [x] Rollback recipe documented in this SUMMARY (5 numbered steps verbatim).
- [x] Post-cutover dry-run sweep returns row_count=0.

## Self-Check: PASSED

Files exist:
- ✓ `.planning/phases/28-temporal-dispatch/28-06-SUMMARY.md`

Commits exist (verified via `git log --oneline`):
- ✓ `843d8be` — feat(28-06): wire Temporal client into lifespan; delete dispatcher_loop task
- ✓ `6feb361` — feat(28-06): cutover — POST /messages starts DispatchMessageWorkflow; delete dispatcher_loop + _handle_row
- ✓ `1b33198` — fix(28-06): unblock cutover smoke — 3 Rule-1 fixes surfaced by live workflow run

Touched files (verified via `git diff --stat 31deef7..HEAD`):
- ✓ `api_server/src/api_server/main.py`
- ✓ `api_server/src/api_server/routes/agent_messages.py`
- ✓ `api_server/src/api_server/services/inapp_messages_store.py`
- ✓ `api_server/src/api_server/services/inapp_dispatcher.py`
- ✓ `api_server/src/api_server/temporal/activities/check_container_ready.py`
- ✓ `api_server/src/api_server/temporal/activities/debit_balance.py`
- ✓ `api_server/src/api_server/temporal/activities/forward_to_agent.py`

## Plan 28-07 Handoff

Plan 28-07 owns the test rework. Its scope picks up:

1. The `tests/services/test_inapp_dispatcher.py` cases that exercised `_handle_row` directly (10+ test functions) — they need to be either deleted or moved to workflow-level tests using `WorkflowEnvironment`. RESEARCH §824 flagged this; this plan made it concrete.
2. Coverage for the new POST /messages → start_workflow flow (mock the temporal_client at the request boundary or use a real Temporal testcontainer).
3. The `_coerce_inp` helper added to `check_container_ready.py` + `forward_to_agent.py` should be unit-tested for both dict-shaped and SimpleNamespace-shaped inputs.

Plan 28-09 owns the manual smoke gate; the live evidence captured here (two contracts, end-to-end PASS, Temporal UI reachable) materially de-risks that gate.
