---
phase: 22b
plan: 04
subsystem: agent-event-stream / Wave-2 lifecycle integration
tags: [fastapi, lifespan, asyncio, watcher-registry, sysadmin-token, d-11, d-15, tdd]
one_liner: "Wire log-watcher lifecycle into FastAPI: app.state registries + lifespan re-attach + shutdown drain + /start spawn (Step 8b) + /stop drain (BEFORE execute_persistent_stop) + AP_SYSADMIN_TOKEN_ENV constant for Plan 22b-05"
requires:
  - Plan 22b-01 (Wave-0 — docker-py dep, conftest fixtures, AP_SYSADMIN_TOKEN .env documentation)
  - Plan 22b-02 (event_store + models/events — ANONYMOUS_USER_ID, agent_events FK chain)
  - Plan 22b-03 (watcher_service.run_watcher signature + _select_source dispatch + app-state primitive contract)
  - Phase 22-05 substrate (agent_lifecycle.start_agent / stop_agent 9-step flow)
provides:
  - api_server/src/api_server/constants.py — AP_SYSADMIN_TOKEN_ENV ("AP_SYSADMIN_TOKEN") for Plan 22b-05
  - api_server/src/api_server/main.py — lifespan re-attach + shutdown drain + 3 event-registry dicts on app.state
  - api_server/src/api_server/routes/agent_lifecycle.py — start_agent Step 8b watcher spawn; stop_agent watcher drain BEFORE execute_persistent_stop
  - 6 integration tests against real Docker + real PG (Golden Rule 1)
affects:
  - Plan 22b-05 long-poll handler: imports AP_SYSADMIN_TOKEN_ENV from constants; reads app.state.event_poll_signals + event_poll_locks (initialized here)
  - Plan 22b-06 SC-03 Gate B harness: every /start now produces a live watcher emitting agent_events rows; /stop tears it down cleanly
  - Lifespan re-attach guarantees observability survives API restarts (D-11)
tech-stack:
  added: []   # all deps already declared by Plan 22b-01 (docker>=7.0,<8)
  patterns:
    - "Lifespan re-attach idiom: SELECT FROM agent_containers WHERE container_status='running' + per-row Docker existence probe + asyncio.create_task(run_watcher(...)) fire-and-forget"
    - "Lifespan shutdown drain idiom: stop_event.set() per task + asyncio.wait(timeout=2.0) + .cancel() fallback for spike-03 unmodeled case"
    - "Spike-03 ordering at /stop: signal watcher BEFORE reaping container (signal first, drain with 2s budget, THEN execute_persistent_stop)"
    - "agent_id slot in run_watcher() = container_row_id (event_store FKs events to agent_containers.id, NOT agent_instances.id) — confirmed by 22b-03 backpressure test"
    - "Per-test inline DB seed fixture (no shared conftest leakage; mirrors Plan 22b-03 SUMMARY decision 4)"
    - "Isolated tmp_path recipes dir (only hermes.yaml) to bypass DI-01 openclaw.yaml duplicate-key bug at lifespan startup"
key-files:
  created:
    - api_server/tests/test_events_lifespan_reattach.py
    - api_server/tests/test_events_lifecycle_spawn_on_start.py
    - api_server/tests/test_events_lifecycle_cancel_on_stop.py
    - .planning/phases/22b-agent-event-stream/22b-04-SUMMARY.md
  modified:
    - api_server/src/api_server/constants.py (+8 / -1 lines — AP_SYSADMIN_TOKEN_ENV export)
    - api_server/src/api_server/main.py (+97 / -2 lines — lifespan re-attach + drain + 3 registry dicts + module logger)
    - api_server/src/api_server/routes/agent_lifecycle.py (+44 / -0 lines — Step 8b spawn + /stop drain + asyncio import)
key-decisions:
  - "Watcher's `agent_id` parameter = container_row_id (NOT path-parameter agent_id). Plan PLAN.md template used `agent_id=agent_id` in pseudocode, but events FK to agent_containers.id; 22b-03 backpressure tests already pass container_row_id as agent_id. Decision: follow the WATCHER SERVICE CONTRACT (the implementation in Wave 1), not the planning-level pseudocode."
  - "Missing-container path uses `mark_agent_container_stopped(_conn, _rid, last_error='container_missing_at_reattach')` + skip — Claude's Discretion per CONTEXT.md picked the simplest correct branch. Row flips to 'start_failed' status (mark_agent_container_stopped semantics: status=start_failed when last_error is non-None)."
  - "Lifespan re-attach Docker probe (`containers.get(cid)`) raises `docker.errors.NotFound` for missing containers — caught explicitly, NOT bare Exception, so genuinely-broken daemons surface as `inspect_failed` log + skip (T-22b-04-01 mitigation)."
  - "Tests use `tmp_path` containing only hermes.yaml (the recipe seeded in test rows). Avoids the pre-existing DI-01 openclaw.yaml DuplicateKeyError, which crashes load_all_recipes at lifespan startup. Logged as DI-05 in deferred-items (DI-01 + DI-05 are the same root cause)."
  - "Per-task commits aggregate RED+GREEN+REFACTOR into a single feat(...) commit — matches Plan 22b-01/02/03 cadence. Plan-level tdd:true was enforced via separate pytest runs (RED verified to fail with AttributeError BEFORE main.py edit; GREEN verified to pass AFTER)."
requirements-completed: [SC-03-GATE-B]
metrics:
  duration_seconds: 530
  duration_human: "~9 minutes"
  tasks_completed: 2
  files_created: 3
  files_modified: 3
  commits: 2
  tests_added: 6
  tests_passed: 6
  tests_regression_clean: 14   # all pre-existing watcher + lifecycle tests still green (test_events_watcher_*, test_lifecycle_env_by_provider)
  completed: "2026-04-19"
---

# Phase 22b Plan 04: Lifecycle Integration (D-11 re-attach + /start + /stop) Summary

**Wire the log-watcher lifecycle into the FastAPI app: app.state registries + lifespan re-attach (D-11) + shutdown drain + /start Step 8b spawn + /stop drain BEFORE execute_persistent_stop (spike-03 ordering) + AP_SYSADMIN_TOKEN_ENV constant for Plan 22b-05.**

## Performance

- **Duration:** ~9 minutes (530s)
- **Started:** 2026-04-19T01:53:46Z
- **Completed:** 2026-04-19T02:02:36Z
- **Tasks:** 2
- **Files created:** 3 tests + this SUMMARY
- **Files modified:** 3 source files

## Accomplishments

1. **Lifespan re-attach (D-11) is live.** Every `agent_containers` row whose `container_status='running'` re-spawns its watcher at API boot. Rows whose Docker container has vanished are gracefully marked stopped (Claude's Discretion: `last_error="container_missing_at_reattach"`).
2. **Lifespan shutdown drain.** All running watchers receive `stop_event.set()` and are awaited with a 2s aggregate budget; tasks still alive after the budget are `.cancel()`-ed (T-22b-04-05 mitigation).
3. **`/start` Step 8b spawn.** `start_agent` fires `asyncio.create_task(run_watcher(...))` AFTER `write_agent_container_running` succeeds and BEFORE returning the response. Spawn failure is non-fatal — events are observability, not correctness.
4. **`/stop` drain ordering (spike-03).** `stop_agent` calls `stop_event.set()` + `asyncio.wait_for(task, 2s)` BEFORE `execute_persistent_stop` reaps the container. Iterator ends cleanly in <270ms (spike-03); the `.cancel()` fallback has never been observed.
5. **`AP_SYSADMIN_TOKEN_ENV` constant** exported from `constants.py` for Plan 22b-05's long-poll handler to import.
6. **6 integration tests pass on real Docker + real PG** (Golden Rule 1 — no mocks, no stubs).

## Task Commits

Each task was committed atomically:

| # | Hash | Task | Message |
|---|---|---|---|
| 1 | `ec5326b` | Task 1 | `feat(22b-04): AP_SYSADMIN_TOKEN_ENV constant + lifespan re-attach + shutdown drain (Task 1)` |
| 2 | `305c966` | Task 2 | `feat(22b-04): /start spawns watcher + /stop drains it before execute_persistent_stop (Task 2)` |

## Files Created/Modified

### Created

- `api_server/tests/test_events_lifespan_reattach.py` — 2 tests:
  1. `test_lifespan_reattach_spawns_watcher_for_live_container` — seeds running row + live alpine; lifespan re-attaches watcher within 3s; shutdown drain reaps it.
  2. `test_lifespan_reattach_marks_stopped_when_container_missing` — seeds row with fabricated `container_id`; lifespan marks row stopped + skips.
- `api_server/tests/test_events_lifecycle_spawn_on_start.py` — 2 tests:
  1. `test_start_spawns_watcher` — exercises spawn pattern; registers within 400ms; cleans up on natural exit.
  2. `test_start_spawn_failure_does_not_register` — bogus `event_source_fallback.kind` raises `ValueError`; registry stays clean (route catches via outer try/except).
- `api_server/tests/test_events_lifecycle_cancel_on_stop.py` — 2 tests:
  1. `test_stop_drains_watcher` — `stop_event.set` + container removal → `wait_for` completes within 3s; registry cleaned.
  2. `test_stop_drain_handles_already_done_watcher` — no entry → no-op (route guards via `log_watchers.get(...)` is `None`).

### Modified

- `api_server/src/api_server/constants.py` — exported `AP_SYSADMIN_TOKEN_ENV = "AP_SYSADMIN_TOKEN"` + added to `__all__`.
- `api_server/src/api_server/main.py` — added `import logging`, module logger `_log`, three event-registry dicts on app.state (`log_watchers`, `event_poll_signals`, `event_poll_locks`), lifespan re-attach block (lines 92-159), lifespan shutdown drain (lines 167-180).
- `api_server/src/api_server/routes/agent_lifecycle.py` — added `import asyncio`, Step 8b spawn (lines 477-505 area), /stop drain (lines 583-602 area).

## Decisions Made

See `key-decisions:` in frontmatter. Notable:

- **`agent_id` slot semantic** — passed `container_row_id` to `run_watcher`, not the path parameter `agent_id`. The watcher's "agent_id" feeds `event_store.insert_agent_events_batch(conn, agent_container_id=agent_id)`, which FKs to `agent_containers.id`. Confirmed by Plan 22b-03 backpressure test (`agent_id=seed_agent_container` where `seed_agent_container` is the agent_containers row PK). Plan PLAN.md text used `agent_id=agent_id` in pseudocode, which would have produced FK violations.
- **Missing-container resolution** — chose `mark stopped + skip` per Claude's Discretion. The row gets `container_status='start_failed'` (because `mark_agent_container_stopped` flips to `start_failed` when `last_error` is non-None) and `last_error='container_missing_at_reattach'`. Future health-sweeper task (post-MVP) can reconcile.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Worktree-local venv setup**

- **Found during:** Task 1 RED verification (initial pytest invocation against `./.venv/bin/python` — venv didn't exist)
- **Issue:** No worktree-local venv; shared venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv` points at MAIN repo path, not this worktree (Plan 22b-02/22b-03 hit the same pattern).
- **Fix:** `python3.13 -m venv .venv` + `pip install -e ".[dev]"` in `api_server/` worktree dir.
- **Files modified:** none (venv metadata only; auto-`.gitignore`d).
- **Commit:** n/a (venv setup, not code).

**2. [Rule 3 - Blocker] Tests use isolated tmp_path recipes dir to bypass DI-01**

- **Found during:** Task 1 first RED run (`ruamel.yaml.constructor.DuplicateKeyError` in openclaw.yaml at lifespan startup).
- **Issue:** Lifespan re-attach test enters `app.router.lifespan_context(app)` which calls `load_all_recipes(settings.recipes_dir)`. The pre-existing DI-01 (openclaw.yaml has duplicate `category: PASS` keys at lines ~514 and ~549) crashes the loader. This is logged as out-of-scope per Plan 22b-01 SUMMARY.
- **Fix:** Both tests use a `tmp_path` recipes dir containing only `hermes.yaml` (the recipe their seed rows reference). Implemented via `_isolated_recipes_dir(tmp_path)` helper that copies hermes.yaml. Bypasses the broken openclaw.yaml without modifying the recipe (CLAUDE.md scope boundary preserved).
- **Files modified:** test files only (no source code).
- **Commit:** Task 1 (`ec5326b`).
- **NOT a fix to DI-01.** DI-01 remains open in `deferred-items.md`. This is a test-side workaround.

**3. [Rule 1 - Bug] `agent_id` parameter passed to `run_watcher` from /start**

- **Found during:** Reading watcher_service.py + event_store.py to understand the contract before writing /start spawn.
- **Issue:** PLAN.md text shows `asyncio.create_task(run_watcher(..., agent_id=agent_id, ...))` where `agent_id` is the path parameter (= agent_instances.id). But `run_watcher` passes its `agent_id` parameter to `event_store.insert_agent_events_batch(conn, agent_container_id=agent_id)`, which FKs to `agent_containers.id`. Passing `agent_instances.id` would FK-fail at every batch insert.
- **Fix:** Pass `agent_id=container_row_id` instead. Confirmed by reading 22b-03's `test_events_watcher_backpressure.py` which uses `agent_id=seed_agent_container` (where `seed_agent_container` returns the container_pk).
- **Files modified:** `api_server/src/api_server/routes/agent_lifecycle.py`.
- **Commit:** Task 2 (`305c966`).
- **Documented in `key-decisions` for downstream consumers.**

**4. [Rule 1 - Bug] `mark_agent_container_stopped` kwarg name corrected**

- **Found during:** Reading `run_store.py` before writing the lifespan re-attach block.
- **Issue:** PLAN.md template uses `mark_agent_container_stopped(conn, _rid, reason="container_missing_at_reattach")`. Real signature is `mark_agent_container_stopped(conn, container_row_id, *, last_error: str | None = None)`.
- **Fix:** Use `last_error="container_missing_at_reattach"`. The function will then flip the row to `container_status='start_failed'` (semantics: non-None last_error → start_failed; None → stopped).
- **Files modified:** `api_server/src/api_server/main.py`.
- **Commit:** Task 1 (`ec5326b`).

### Out-of-scope findings (NOT fixed, logged only)

**DI-01 (still open from Plans 22b-01/02/03)** — `recipes/openclaw.yaml` has duplicate `category: PASS` keys (lines ~514 and ~549). Crashes `load_all_recipes` at lifespan startup for any test that builds a real app. Pre-existing — verified at HEAD before any 22b-04 change (`git stash` round-trip, `test_health.py::test_readyz_live` errors identically).

---

**Total deviations:** 4 auto-fixed (1 blocker for venv, 1 blocker for test-side workaround, 2 bugs in plan pseudocode).
**Impact on plan:** All 4 fixes were necessary for correctness. The two `Rule 1` fixes (agent_id semantic + last_error kwarg) are the kind of boundary-mismatch the plan-vs-implementation rotation is supposed to catch. They're documented in `key-decisions` for Plan 22b-05 to consume.

## Issues Encountered

- `test_health.py::test_readyz_live` (a pre-existing test) errors with the DI-01 yaml issue when running pytest against modified files. Verified pre-existing via `git stash` round-trip — not caused by this plan.

## Threat Model Compliance

| Threat ID | Disposition | Implementation status |
|---|---|---|
| T-22b-04-01 (DoS via re-attach loop) | mitigate | `containers.get(cid)` failures fall through to `_log.exception` + `continue`. One bad row cannot stall startup. |
| T-22b-04-02 (EoP via /start spawn) | accept | Bearer validated by Step 1; spawn uses authenticated agent_id + recipe; no new privilege. |
| T-22b-04-03 (Info Disclosure via chat_id_hint) | accept | Numeric Telegram user ID (6-10 digits); not a secret per BYOK. |
| T-22b-04-04 (Tampering via unknown event_source_fallback.kind on re-attach) | mitigate | `_select_source` raises `ValueError` (Plan 22b-03); re-attach loop catches via outer try/except — one bad recipe cannot block other re-attaches. |
| T-22b-04-05 (DoS via slow shutdown drain) | mitigate | 2s `asyncio.wait` budget; tasks still running cancelled (the spike-03-unmodeled fallback). |
| T-22b-04-06 (Spoofing via re-attach with unknown recipe) | mitigate | `app.state.recipes.get(...)` returns None for removed-recipe case → WARN log + skip. |

## Verification command outputs

```
--- TASK 1+2 INTEGRATION TESTS (real Docker + real PG via testcontainers) ---
$ ./.venv/bin/python -m pytest -m api_integration \
    tests/test_events_lifespan_reattach.py \
    tests/test_events_lifecycle_spawn_on_start.py \
    tests/test_events_lifecycle_cancel_on_stop.py -v
6 passed in 11.53s

--- REGRESSION ON PLAN 22b-03 WATCHER TESTS ---
$ ./.venv/bin/python -m pytest -m api_integration \
    tests/test_events_watcher_*.py -v
14 passed in 21.53s  (combined with above: 20/20)

--- ACCEPTANCE GREP CHECKS (Task 1) ---
$ grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/constants.py
3   (>=1 OK)
$ grep -c '"AP_SYSADMIN_TOKEN"' api_server/src/api_server/constants.py
1   (>=1 OK)
$ grep -cE "log_watchers|event_poll_signals|event_poll_locks" api_server/src/api_server/main.py
8   (>=3 OK)
$ grep -c "container_status='running'" api_server/src/api_server/main.py
1   (>=1 OK — re-attach SQL)
$ grep -c "mark_agent_container_stopped" api_server/src/api_server/main.py
2   (>=1 OK — graceful degrade)
$ grep -cE "asyncio.wait\(.*timeout=2" api_server/src/api_server/main.py
1   (>=1 OK — shutdown drain)

--- ACCEPTANCE GREP CHECKS (Task 2) ---
$ grep -c "asyncio.create_task(run_watcher" api_server/src/api_server/routes/agent_lifecycle.py
1
$ grep -cE "_wstop\.set\(\)" api_server/src/api_server/routes/agent_lifecycle.py
1
$ grep -cE "asyncio\.wait_for\(.*timeout=2" api_server/src/api_server/routes/agent_lifecycle.py
1
$ grep -c "log_watchers" api_server/src/api_server/routes/agent_lifecycle.py
1

--- ORDER PROOFS (route-level) ---
write_agent_container_running line=477 < spawn line=490   (Step 8 < Step 8b)  OK
stop_event.set() line=593 < execute_persistent_stop line=607  (drain BEFORE reap)  OK

--- IMPORT SMOKE ---
$ ./.venv/bin/python -c "from api_server.constants import ANONYMOUS_USER_ID, AP_SYSADMIN_TOKEN_ENV; assert AP_SYSADMIN_TOKEN_ENV == 'AP_SYSADMIN_TOKEN'"
(no output — exit 0)
```

## Lifespan Shape Used

```python
# Re-attach (lines 92-159 of main.py):
SELECT id, agent_instance_id, recipe_name, container_id, channel_type
FROM agent_containers WHERE container_status='running'

for each row:
    try:
        _dclient.containers.get(container_id)   # O(1) inspect
    except docker.errors.NotFound:
        mark_agent_container_stopped(_conn, _rid,
            last_error="container_missing_at_reattach")
        continue
    except Exception:
        _log.exception("phase22b.reattach.inspect_failed"); continue
    if recipe is None:
        _log.warning("phase22b.reattach.recipe_missing"); continue
    asyncio.create_task(run_watcher(
        app.state, container_row_id=_rid, container_id=_cid,
        agent_id=_rid, recipe=_recipe, channel=_row["channel_type"],
        chat_id_hint=None,
    ))

# Shutdown (lines 167-180):
for task, stop in app.state.log_watchers.values():
    stop.set()
tasks = [t for t, _ in app.state.log_watchers.values() if not t.done()]
if tasks:
    _, pending = await asyncio.wait(tasks, timeout=2.0)
    for p in pending:
        p.cancel()
```

## stop_agent Sequencing Proof

```
$ awk '/^async def stop_agent/ {in_stop=1} in_stop && /_wstop\.set\(\)/ {a=NR} in_stop && /execute_persistent_stop\(/ && a {b=NR; exit} END {print "stop_event.set line=" a, "execute_persistent_stop line=" b}' api_server/src/api_server/routes/agent_lifecycle.py
stop_event.set line=593 execute_persistent_stop line=607
```

`stop_event.set()` (line 593) precedes `execute_persistent_stop()` (line 607) — spike-03 ordering preserved.

## Missing-Container Path Resolution

**Choice:** `mark_agent_container_stopped(_conn, _rid, last_error="container_missing_at_reattach")` + skip spawning.

`mark_agent_container_stopped` flips the row to `container_status='start_failed'` when `last_error` is non-None (per its docstring + UPDATE statement). The audit trail captures the reason in `last_error`. Future post-MVP health-sweeper can reconcile failed/stopped rows; the lifespan re-attach loop in this plan does NOT attempt re-creation (out of scope).

## Lifecycle Test Wall Times

| Test | Wall (s) |
|---|---|
| `test_lifespan_reattach_spawns_watcher_for_live_container` | ~2.0 |
| `test_lifespan_reattach_marks_stopped_when_container_missing` | ~3.5 |
| `test_start_spawns_watcher` | ~2.5 |
| `test_start_spawn_failure_does_not_register` | ~0.6 |
| `test_stop_drains_watcher` | ~2.0 |
| `test_stop_drain_handles_already_done_watcher` | ~2.0 |
| **Combined (6 tests)** | **11.5s** |

Includes setup (testcontainers postgres boot is amortized session-scope; alpine container start is ~0.5s per test).

## TDD Gate Compliance

Per-task `tdd="true"` followed:

- **Task 1:**
  - **RED:** wrote `test_events_lifespan_reattach.py`; ran `pytest -m api_integration` BEFORE editing main.py → 2 FAILED with `AttributeError: 'State' object has no attribute 'log_watchers'`.
  - **GREEN:** edited constants.py + main.py; re-ran → 2 PASSED in 6.93s.
  - Single commit `ec5326b` captures both phases.
- **Task 2:**
  - **RED:** wrote `test_events_lifecycle_spawn_on_start.py` + `test_events_lifecycle_cancel_on_stop.py`. These exercise the WATCHER mechanics (which were already implemented by Plan 22b-03 watcher_service.py) so they actually PASSED on first run. The route-level changes (Step 8b spawn + /stop drain) are validated by `grep -n` ordering proofs (acceptance criteria explicitly use grep, not pytest, for route ordering).
  - **GREEN:** edited agent_lifecycle.py; re-ran tests → 4 PASSED. Grep checks confirm correct ordering at the route level.
  - Single commit `305c966`.

## Known Stubs

None. Every code path is real:

- Lifespan re-attach exercises real Docker daemon (`_dclient.containers.get(cid)`) + real Postgres + real `run_watcher` from Plan 22b-03.
- `/start` spawn calls real `asyncio.create_task(run_watcher(...))` with real `app.state` registries.
- `/stop` drain calls real `stop_event.set()` + real `asyncio.wait_for(task, 2.0)`.

The 6 integration tests run against real Docker (alpine:3.19) and real Postgres 17 via testcontainers — no mocks anywhere (Golden Rule 1).

## Threat Flags

None new. The plan's threat model (T-22b-04-01..06) is fully addressed in the implementation; see "Threat Model Compliance" table above.

## Self-Check: PASSED

All created/modified files exist on disk:

```
FOUND: api_server/tests/test_events_lifespan_reattach.py
FOUND: api_server/tests/test_events_lifecycle_spawn_on_start.py
FOUND: api_server/tests/test_events_lifecycle_cancel_on_stop.py
FOUND: api_server/src/api_server/constants.py (modified)
FOUND: api_server/src/api_server/main.py (modified)
FOUND: api_server/src/api_server/routes/agent_lifecycle.py (modified)
```

All commits exist in `git log`:

```
FOUND: ec5326b  feat(22b-04): AP_SYSADMIN_TOKEN_ENV constant + lifespan re-attach + shutdown drain (Task 1)
FOUND: 305c966  feat(22b-04): /start spawns watcher + /stop drains it before execute_persistent_stop (Task 2)
```

6/6 plan-defined tests PASS on real Docker + real PG. 14 prior watcher integration tests still PASS (no regression).

## Next Phase Readiness

- **Plan 22b-05 (long-poll route)** is unblocked. It can:
  - `from api_server.constants import AP_SYSADMIN_TOKEN_ENV` for D-15 sysadmin bypass
  - Read `request.app.state.event_poll_signals[agent_container_id]` for wake signals (initialized in main.py lifespan)
  - Read `request.app.state.event_poll_locks[agent_container_id]` for D-13 429 cap (initialized in main.py lifespan)
- **Plan 22b-06 (SC-03 Gate B harness)** is unblocked from the API side:
  - Every `/v1/agents/:id/start` now produces a live watcher writing `agent_events` rows
  - Every `/v1/agents/:id/stop` tears the watcher down cleanly (spike-03 ordering)
  - Lifespan re-attach guarantees observability survives API restarts (D-11)

---

*Phase: 22b-agent-event-stream / Plan 04*
*Completed: 2026-04-19*
