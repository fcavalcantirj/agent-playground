---
phase: 22b
plan: 04
type: execute
wave: 2
depends_on: ["22b-02", "22b-03"]
files_modified:
  - api_server/src/api_server/main.py
  - api_server/src/api_server/routes/agent_lifecycle.py
  - api_server/src/api_server/constants.py
  - api_server/tests/test_events_lifespan_reattach.py
  - api_server/tests/test_events_lifecycle_spawn_on_start.py
  - api_server/tests/test_events_lifecycle_cancel_on_stop.py
autonomous: true
requirements:
  - SC-03-GATE-B

must_haves:
  truths:
    - "app.state.log_watchers, app.state.event_poll_signals, app.state.event_poll_locks are initialized in main.py lifespan alongside the existing app.state.image_tag_locks / locks_mutex / run_semaphore block"
    - "POST /v1/agents/:id/start spawns a fire-and-forget run_watcher task AFTER write_agent_container_running and BEFORE returning the HTTP response"
    - "POST /v1/agents/:id/stop signals watcher.stop_event and awaits the watcher task with a 2s budget BEFORE calling execute_persistent_stop (spike-03 teardown order)"
    - "Lifespan startup re-attaches a watcher for every agent_containers row with container_status='running' (D-11) — rows whose container_id no longer exists in Docker are marked 'stopped' per Claude's Discretion in CONTEXT.md"
    - "Lifespan shutdown sets every watcher's stop_event and awaits with a 2s aggregate budget"
    - "AP_SYSADMIN_TOKEN_ENV constant is exported from constants.py"
    - "Failure to spawn the watcher (e.g. unknown event_source_fallback.kind) is logged via _log.exception but DOES NOT fail /start — events are observability, not correctness"
  artifacts:
    - path: "api_server/src/api_server/main.py"
      provides: "lifespan re-attach + shutdown drain + app.state event primitives"
      contains: "log_watchers"
    - path: "api_server/src/api_server/routes/agent_lifecycle.py"
      provides: "start_agent spawns run_watcher; stop_agent drains it"
      contains: "run_watcher"
    - path: "api_server/src/api_server/constants.py"
      provides: "AP_SYSADMIN_TOKEN_ENV env-var NAME constant"
      contains: "AP_SYSADMIN_TOKEN_ENV"
    - path: "api_server/tests/test_events_lifespan_reattach.py"
      provides: "D-11 re-attach test: seed running row + live container + create_app → assert log_watchers populated"
      contains: "def test_lifespan_reattach"
    - path: "api_server/tests/test_events_lifecycle_spawn_on_start.py"
      provides: "POST /start spawns watcher; agent_events rows appear after container produces matched line"
      contains: "def test_start_spawns_watcher"
    - path: "api_server/tests/test_events_lifecycle_cancel_on_stop.py"
      provides: "POST /stop drains watcher before execute_persistent_stop; registry empties"
      contains: "def test_stop_drains_watcher"
  key_links:
    - from: "api_server/src/api_server/routes/agent_lifecycle.py::start_agent"
      to: "api_server/src/api_server/services/watcher_service.py::run_watcher"
      via: "asyncio.create_task(run_watcher(...)) after Step 8 write_agent_container_running"
      pattern: "asyncio.create_task\\(run_watcher"
    - from: "api_server/src/api_server/main.py::lifespan"
      to: "api_server/src/api_server/services/run_store.py"
      via: "SELECT * FROM agent_containers WHERE container_status='running' on startup"
      pattern: "container_status='running'"
    - from: "api_server/src/api_server/routes/agent_lifecycle.py::stop_agent"
      to: "app.state.log_watchers"
      via: "stop_event.set() + await asyncio.wait_for(task, timeout=2.0)"
      pattern: "stop_event.set"
---

<objective>
Wire the watcher lifecycle into the existing FastAPI app:

1. **app.state init** — extend the `main.py` block that already declares `app.state.image_tag_locks` / `locks_mutex` / `run_semaphore` with three new dicts: `log_watchers`, `event_poll_signals`, `event_poll_locks`. Shared `locks_mutex` guards mutations on all three (watcher-service already depends on this via `_get_poll_lock`).

2. **`/start` extension** — after `write_agent_container_running` succeeds (current line ~419 of `agent_lifecycle.py`), spawn `asyncio.create_task(run_watcher(...))`. Failure to spawn is non-fatal for `/start` — log via `_log.exception` and continue (events are observability, not correctness, per 22b scope).

3. **`/stop` extension** — before calling `execute_persistent_stop` (current line ~497), look up the watcher in `app.state.log_watchers[UUID(running["id"])]`, call `stop_event.set()`, then `await asyncio.wait_for(task, timeout=2.0)`. On timeout, `task.cancel()` as fallback — but per spike-03 this path has never been observed (docker rm -f ends the source iterator in <270ms).

4. **Lifespan startup** — query `agent_containers WHERE container_status='running'` on API boot; for each row, look up the recipe by name and spawn `run_watcher`. If the row's `container_id` no longer exists in Docker (container vanished during an API outage), call `mark_agent_container_stopped` and skip spawning (per Claude's Discretion in CONTEXT.md: "mark stopped, emit `agent_error`, or skip — planner decides"; we choose **mark stopped + skip**, which is the simplest correct path; a future health-sweeper task can re-confirm). `chat_id_hint` is `None` on re-attach — sources that need it (nullclaw, openclaw) degrade gracefully per Plan 22b-03 (`DockerExecPollSource.lines` returns immediately when `chat_id_hint=None`; `FileTailInContainerSource` uses a manifest sweep).

5. **Lifespan shutdown** — set every watcher's stop_event, then `await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2.0)`. Tasks that don't exit within 2s are cancelled as a fallback.

6. **`AP_SYSADMIN_TOKEN_ENV` constant** — publish the env-var NAME in `constants.py` so Plan 22b-05's route handler imports the name (not the value — reading the value happens at handler time via `os.environ.get(AP_SYSADMIN_TOKEN_ENV)`).

**Parallelizable with Plan 22b-05** (Plan 22b-05 owns `routes/agent_events.py` + `models/errors.py` error-code additions; this plan touches `main.py` + `agent_lifecycle.py` + `constants.py`). The one shared touchpoint is `models/errors.py` (Plan 22b-05's `CONCURRENT_POLL_LIMIT` + `EVENT_STREAM_UNAVAILABLE` codes) — we do NOT modify errors.py in this plan; Plan 22b-05 owns that edit exclusively.

Purpose: SC-03 Gate B — ensure every `/v1/agents/:id/start` transition produces a live watcher, every `/v1/agents/:id/stop` tears it down cleanly, and an API restart re-establishes watchers for surviving containers.

Output: main.py + agent_lifecycle.py + constants.py extensions; 3 integration tests (reattach, spawn-on-start, cancel-on-stop) against real Docker + real PG via testcontainers.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-RESEARCH.md
@.planning/phases/22b-agent-event-stream/22b-PATTERNS.md
@.planning/phases/22b-agent-event-stream/22b-VALIDATION.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-03-watcher-teardown.md
@.planning/phases/22b-agent-event-stream/22b-02-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-03-SUMMARY.md
@api_server/src/api_server/main.py
@api_server/src/api_server/routes/agent_lifecycle.py
@api_server/src/api_server/services/run_store.py
@api_server/src/api_server/constants.py
@api_server/tests/test_runs.py

<interfaces>
<!-- Contracts consumed by this plan from prior plans. -->

From api_server/src/api_server/services/watcher_service.py (Plan 22b-03):
```python
async def run_watcher(app_state, *, container_row_id: UUID, container_id: str,
                      agent_id: UUID, recipe: dict, channel: str,
                      chat_id_hint: str | None) -> None
```

From api_server/src/api_server/services/run_store.py (existing):
```python
async def fetch_running_container_for_agent(conn, agent_id: UUID) -> dict | None
async def mark_agent_container_stopped(conn, container_id: UUID, ...) -> None
```
(Verify exact signatures by reading run_store.py during execution — PATTERNS.md lines 169-188 documents the conventions.)

From api_server/src/api_server/main.py (existing — location of extensions):
```python
# app.state init block (~lines 63-72):
app.state.image_tag_locks = {}
app.state.locks_mutex = asyncio.Lock()
app.state.run_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
```

From api_server/src/api_server/routes/agent_lifecycle.py (existing — extension points):
```python
# start_agent: Step 8 `write_agent_container_running` at ~line 419
# start_agent: return AgentStartResponse at ~line 422
# stop_agent: execute_persistent_stop call at ~line 497
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: AP_SYSADMIN_TOKEN_ENV constant + app.state init + lifespan re-attach / shutdown</name>
  <files>api_server/src/api_server/constants.py, api_server/src/api_server/main.py, api_server/tests/test_events_lifespan_reattach.py</files>
  <read_first>
    - api_server/src/api_server/constants.py (the file being extended — read the full file first; it is short; confirm existing `ANONYMOUS_USER_ID` export and `__all__` shape)
    - api_server/src/api_server/main.py (the file being extended — read the lifespan function from top to the `yield` statement; locate the app.state init block and the recipes-loader call; locate the router-include block; the shutdown branch is after `yield`)
    - 22b-PATTERNS.md §"api_server/src/api_server/constants.py (ADD-TO)" (authoritative constant shape) and §"api_server/src/api_server/main.py (ADD-TO)" (authoritative lifespan shape)
    - 22b-RESEARCH.md §"Example 4: Lifespan re-attach" (authoritative SQL + task spawn loop)
    - 22b-CONTEXT.md D-10, D-11, D-15 — app.state registry + re-attach semantics + AP_SYSADMIN_TOKEN discipline
    - 22b-VALIDATION.md §"Per-Task Verification Map" — which tests land here
  </read_first>
  <behavior>
    - `from api_server.constants import ANONYMOUS_USER_ID, AP_SYSADMIN_TOKEN_ENV` succeeds. `AP_SYSADMIN_TOKEN_ENV == "AP_SYSADMIN_TOKEN"` (the env-var NAME, not its value).
    - After `create_app()`, `app.state.log_watchers`, `app.state.event_poll_signals`, `app.state.event_poll_locks` exist as empty dicts.
    - Startup phase: if a row `agent_containers(container_status='running', container_id='abc123', recipe_name='hermes', agent_instance_id=UUID, channel_type='telegram')` exists AND the docker daemon confirms container `abc123` is running, lifespan spawns a watcher; `app.state.log_watchers[row_id]` is populated within 500ms.
    - Startup phase: if a running row's `container_id` is UNKNOWN to docker, lifespan calls `mark_agent_container_stopped(conn, row_id)` and does NOT spawn a watcher (graceful degrade, Claude's Discretion).
    - Shutdown phase: if watchers are running, setting their `stop_event`s + awaiting with 2s budget → all tasks transition to done within 2.5s.
  </behavior>
  <action>
**Part A — Extend `api_server/src/api_server/constants.py`.**

Read the file fully (it is short — likely 10-20 lines). Append AFTER the existing `ANONYMOUS_USER_ID` definition:

```python
# Phase 22b: sysadmin bypass for event-stream auth (D-15).
# Per-laptop / per-deploy state — mirrors AP_CHANNEL_MASTER_KEY discipline.
# NEVER committed to .env* files. Route handler (Plan 22b-05) reads the
# VALUE at handler time via os.environ.get(AP_SYSADMIN_TOKEN_ENV).
AP_SYSADMIN_TOKEN_ENV = "AP_SYSADMIN_TOKEN"
```

Update the existing `__all__` list to include `"AP_SYSADMIN_TOKEN_ENV"`. Preserve every other export.

**Part B — Extend `api_server/src/api_server/main.py`.**

Read the full file first. Locate:
1. The imports block (add `from .services.watcher_service import run_watcher`; if `asyncio` is not already imported, add it).
2. The app.state init block (likely `app.state.image_tag_locks = {}`, `app.state.locks_mutex = asyncio.Lock()`, `app.state.run_semaphore = asyncio.Semaphore(...)`).
3. The recipes load (needed so the lifespan re-attach loop can look up recipes by name).
4. The `yield` statement.
5. The shutdown branch (after `yield` or in a `finally:`).

APPEND to the app.state init block (the three new dicts):

```python
# Phase 22b-04: event-watcher registry + signal + per-agent poll lock.
# locks_mutex (existing) guards setdefault races on event_poll_locks.
app.state.log_watchers = {}            # container_row_id -> (asyncio.Task, asyncio.Event)
app.state.event_poll_signals = {}      # agent_id -> asyncio.Event (watcher .set()s; handler .clear()+.wait()s)
app.state.event_poll_locks = {}        # agent_id -> asyncio.Lock (D-13: one poll at a time per agent)
```

ADD a re-attach block (BEFORE the `yield`, AFTER recipes are loaded and DB pool is ready). Shape per RESEARCH §Example 4 + Claude's Discretion on missing-container handling:

```python
# Phase 22b-04: re-attach log-watchers for containers that survived an API restart (D-11).
# Rows whose container_id no longer exists in Docker are marked stopped + skipped.
try:
    import docker as _docker
    from .services.run_store import mark_agent_container_stopped
    _dclient = _docker.from_env()
    async with app.state.db.acquire() as _conn:
        _rows = await _conn.fetch(
            "SELECT id, agent_instance_id, recipe_name, container_id, channel_type "
            "FROM agent_containers WHERE container_status='running'"
        )
    for _row in _rows:
        _cid = _row["container_id"]
        _rid = _row["id"]
        # Cheap existence probe — inspect is O(1); if it 404s the container is gone.
        try:
            _dclient.containers.get(_cid)
        except _docker.errors.NotFound:
            logger.info(
                "phase22b.reattach.container_missing",
                extra={"container_row_id": str(_rid), "container_id": _cid},
            )
            async with app.state.db.acquire() as _conn:
                await mark_agent_container_stopped(_conn, _rid, reason="container_missing_at_reattach")
            continue
        except Exception:
            logger.exception("phase22b.reattach.inspect_failed",
                             extra={"container_row_id": str(_rid)})
            continue
        _recipe = app.state.recipes.get(_row["recipe_name"])
        if _recipe is None:
            logger.warning(
                "phase22b.reattach.recipe_missing",
                extra={"recipe_name": _row["recipe_name"]},
            )
            continue
        asyncio.create_task(run_watcher(
            app.state,
            container_row_id=_rid,
            container_id=_cid,
            agent_id=_row["agent_instance_id"],
            recipe=_recipe,
            channel=_row["channel_type"],
            chat_id_hint=None,         # A6 — degrade gracefully on re-attach
        ))
    _dclient.close()
except Exception:
    logger.exception("phase22b.reattach.init_failed")
```

(Read the existing `logger = logging.getLogger(...)` binding — reuse whatever name main.py already uses; do NOT introduce a new logger.)

The exact name of `mark_agent_container_stopped`'s second argument (`reason` vs `stopped_reason`) must be confirmed by reading `run_store.py` during execution. If no "reason" kwarg exists, call the function with its actual signature; add a follow-up `_log.info` with the reason string.

ADD a shutdown drain block (AFTER `yield`, or replacing the existing `close_pool` cleanup). Shape:

```python
# Phase 22b-04: drain all watchers before closing the DB pool.
try:
    if getattr(app.state, "log_watchers", None):
        for _task, _stop in list(app.state.log_watchers.values()):
            _stop.set()
        _tasks = [t for t, _ in app.state.log_watchers.values() if not t.done()]
        if _tasks:
            _, _pending = await asyncio.wait(_tasks, timeout=2.0)
            for _p in _pending:
                _p.cancel()
except Exception:
    logger.exception("phase22b.shutdown.drain_failed")
```

**Part C — Create `api_server/tests/test_events_lifespan_reattach.py`:**

```python
"""Phase 22b-04 Task 1 — D-11 lifespan re-attach.

Seeds agent_containers(container_status='running') with a REAL live alpine
container; calls create_app(); asserts app.state.log_watchers contains
the row id within 1s. Then stops the container externally to verify the
watcher self-exits cleanly as before (spike-03 teardown applies in the
reattach path too).

Also tests the graceful-degrade case: row points at a container_id that
no longer exists in Docker; lifespan calls mark_agent_container_stopped
and does NOT spawn a watcher.
"""
import asyncio
import pytest
from uuid import uuid4, UUID
from api_server.main import create_app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_lifespan_reattach_spawns_watcher_for_live_container(
    running_alpine_container, real_db_pool, seed_agent_instance
):
    container = running_alpine_container(["sh", "-c", "echo ready; sleep 30"])
    agent_id = seed_agent_instance  # fixture returns UUID of an agent_instance
    row_id = uuid4()
    # Directly INSERT a running agent_containers row pointing at the real container.
    async with real_db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_containers (id, agent_instance_id, recipe_name, "
            "container_id, container_status, channel_type, started_at) "
            "VALUES ($1, $2, $3, $4, 'running', 'telegram', NOW())",
            row_id, agent_id, "hermes", container.id,
        )
    # Build the app; lifespan should re-attach the watcher.
    app = create_app()
    async with app.router.lifespan_context(app):
        # Give the re-attach task a moment to spawn
        for _ in range(20):
            if row_id in app.state.log_watchers:
                break
            await asyncio.sleep(0.1)
        assert row_id in app.state.log_watchers, \
            "lifespan failed to re-attach watcher within 2s"
        # Teardown: remove container; lifespan shutdown drains the watcher.
        container.remove(force=True)
    # After lifespan shutdown, registry must be empty
    assert app.state.log_watchers == {}


@pytest.mark.asyncio
async def test_lifespan_reattach_marks_stopped_when_container_missing(
    real_db_pool, seed_agent_instance
):
    agent_id = seed_agent_instance
    row_id = uuid4()
    fake_container_id = "deadbeef" * 8   # never existed
    async with real_db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_containers (id, agent_instance_id, recipe_name, "
            "container_id, container_status, channel_type, started_at) "
            "VALUES ($1, $2, $3, $4, 'running', 'telegram', NOW())",
            row_id, agent_id, "hermes", fake_container_id,
        )
    app = create_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(1.0)   # let re-attach run
        assert row_id not in app.state.log_watchers
    # The row should now be marked non-running.
    async with real_db_pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT container_status FROM agent_containers WHERE id=$1", row_id)
    assert status in ("stopped", "failed", "crashed"), \
        f"expected non-running status, got {status!r}"
```

Note: `seed_agent_instance` fixture may or may not exist in the Phase 22 conftest. If missing, define inline in the test file a minimal `@pytest_asyncio.fixture` that INSERTs an `agent_instances` row (and its parent `users` / `recipes` rows if FKs require — read existing `test_runs.py` fixtures for the shape).

Verify:
```bash
cd api_server && pytest -x tests/test_events_lifespan_reattach.py -v 2>&1 | tail -15
python3 -c "from api_server.constants import AP_SYSADMIN_TOKEN_ENV; assert AP_SYSADMIN_TOKEN_ENV == 'AP_SYSADMIN_TOKEN'"
```
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.constants import ANONYMOUS_USER_ID, AP_SYSADMIN_TOKEN_ENV; assert AP_SYSADMIN_TOKEN_ENV == 'AP_SYSADMIN_TOKEN'" && python3 -c "from api_server.main import create_app; app = create_app(); assert hasattr(app.state, 'image_tag_locks')" && pytest -x tests/test_events_lifespan_reattach.py -v 2>&1 | grep -qE "2 passed|passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/constants.py` returns `>=1`
    - `grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/constants.py` matches a string literal `"AP_SYSADMIN_TOKEN"` adjacent (grep `"AP_SYSADMIN_TOKEN"` also returns `>=1`)
    - `grep -c "log_watchers\|event_poll_signals\|event_poll_locks" api_server/src/api_server/main.py` returns `>=3`
    - `grep -c "container_status='running'" api_server/src/api_server/main.py` returns `>=1` (re-attach SQL)
    - `grep -c "mark_agent_container_stopped" api_server/src/api_server/main.py` returns `>=1` (graceful degrade)
    - `grep -c "asyncio.wait(.*timeout=2" api_server/src/api_server/main.py` returns `>=1` (shutdown drain)
    - `cd api_server && pytest -x tests/test_events_lifespan_reattach.py -v 2>&1 | grep -cE "PASSED"` returns `>=2`
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression
  </acceptance_criteria>
  <done>constants.py publishes AP_SYSADMIN_TOKEN_ENV; main.py initializes 3 event-registry dicts, re-attaches watchers on startup, marks missing containers stopped, drains on shutdown; 2 lifespan tests pass on real docker + real PG.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: /start spawns watcher + /stop drains it</name>
  <files>api_server/src/api_server/routes/agent_lifecycle.py, api_server/tests/test_events_lifecycle_spawn_on_start.py, api_server/tests/test_events_lifecycle_cancel_on_stop.py</files>
  <read_first>
    - api_server/src/api_server/routes/agent_lifecycle.py (the file being extended — read `start_agent` in full: the 9-step flow docstring at top; the Step 8 `write_agent_container_running` call at ~line 419; the `return AgentStartResponse` at ~line 422; `stop_agent` body around line 442-533; the `execute_persistent_stop` call at ~line 497)
    - api_server/src/api_server/services/watcher_service.py (the run_watcher signature from Plan 22b-03)
    - api_server/tests/test_runs.py (analog — httpx AsyncClient + ASGITransport + create_app setup)
    - 22b-PATTERNS.md §"api_server/src/api_server/routes/agent_lifecycle.py (ADD-TO)" (authoritative extension shape)
    - 22b-RESEARCH.md §"Example 2: /start extension" + §"Example 3: /stop extension" (authoritative code)
    - 22b-SPIKES/spike-03-watcher-teardown.md — `/stop` order: signal watcher → await with 2s budget → THEN execute_persistent_stop (iterator ends cleanly when container is reaped)
    - 22b-CONTEXT.md D-10
  </read_first>
  <behavior>
    - After `POST /v1/agents/<id>/start` returns 200, `app.state.log_watchers` contains an entry keyed on the new container_row_id within 500ms. The watcher's run_watcher coroutine is alive and `_select_source` has instantiated the right source class based on the recipe.
    - After `POST /v1/agents/<id>/stop` returns 200, `app.state.log_watchers` no longer contains the entry; the watcher task transitioned to `done`; `execute_persistent_stop` was called AFTER the watcher drain.
    - If `run_watcher` raises at spawn time (e.g. unknown `event_source_fallback.kind`), `/start` still returns 200 with a logged exception — watcher failure is non-fatal to the lifecycle.
  </behavior>
  <action>
**Part A — Extend `api_server/src/api_server/routes/agent_lifecycle.py::start_agent`.**

Read the file fully first; locate Step 8 (`write_agent_container_running`) and the final `return AgentStartResponse(...)`. Between them, INSERT the watcher spawn. Per RESEARCH §Example 2:

```python
# --- Step 8b (Phase 22b-04): spawn log-watcher task (fire-and-forget) ---
# Spike-03 discipline: iterator ends cleanly when container is removed;
# no Task.cancel() needed here. Failure to spawn is non-fatal — events are
# observability, not correctness, per 22b scope. Lifespan re-attach will
# retry on next API restart.
try:
    from ..services.watcher_service import run_watcher
    asyncio.create_task(run_watcher(
        request.app.state,
        container_row_id=container_row_id,       # confirm variable name at local context — Step 8 output
        container_id=container_id,
        agent_id=agent_id,
        recipe=recipe,
        channel=body.channel,
        chat_id_hint=(
            body.channel_inputs.get("TELEGRAM_ALLOWED_USER")
            or body.channel_inputs.get("TELEGRAM_ALLOWED_USERS")
        ),
    ))
except Exception:
    _log.exception("phase22b.watcher.spawn_failed",
                   extra={"agent_id": str(agent_id)})
```

(If the local variable in Step 8 that holds the newly-INSERTED `agent_containers.id` is named differently — e.g. `new_row_id` or `container_row`.id — use that exact name. Read the adjacent code to confirm.)

If `asyncio` is not imported at top of file, add `import asyncio`.

**Part B — Extend `api_server/src/api_server/routes/agent_lifecycle.py::stop_agent`.**

Locate the `execute_persistent_stop` call (~line 497). INSERT BEFORE it, per RESEARCH §Example 3:

```python
# --- Phase 22b-04: signal watcher stop + await before tearing container down ---
# Order matters: signal first so the watcher exits BEFORE docker rm -f reaps
# the container. Spike-03: iterator ends cleanly in <270ms after rm -f, so
# the 2s budget is generous. Task.cancel() is the documented fallback.
try:
    _row_id_str = running["id"]        # confirm key name in fetch_running_container_for_agent output
    _watcher_entry = request.app.state.log_watchers.get(UUID(_row_id_str))
    if _watcher_entry is not None:
        _wtask, _wstop = _watcher_entry
        _wstop.set()
        try:
            await asyncio.wait_for(_wtask, timeout=2.0)
        except asyncio.TimeoutError:
            _wtask.cancel()
            _log.warning("phase22b.watcher.cancel_on_timeout",
                         extra={"container_row_id": _row_id_str})
except Exception:
    _log.exception("phase22b.watcher.drain_failed")
```

(The variable `running` is the dict returned by `fetch_running_container_for_agent` — read its existing usage in `stop_agent` for the correct key path. It may be `.get("id")` or accessed via `running["id"]` depending on whether it is a dict or a Record cast.)

Confirm `UUID` is imported at top of the file (it likely is — the existing code uses UUID path params).

**Part C — Create `api_server/tests/test_events_lifecycle_spawn_on_start.py`:**

```python
"""Phase 22b-04 Task 2 — POST /start spawns a watcher.

Uses the existing test_runs.py httpx AsyncClient + ASGITransport pattern.
Recipe MUST be one of the live recipes (hermes has a populated
event_log_regex from spike 01a / Plan 22b-06). The watcher runs against
a real alpine stub; the test confirms registry population, not event
emission (that is the province of test_events_end_to_end, future plan).
"""
import asyncio
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_start_spawns_watcher(api_client, seed_agent_instance, running_alpine_container, real_db_pool):
    # POST /v1/agents/<id>/start → 200 → watcher in registry
    #
    # We cannot easily hit the real /start handler with the full recipe
    # runtime (docker pull + container start + ready probe = expensive).
    # Instead, this test directly exercises the SPAWN PATH added to
    # start_agent by importing run_watcher and calling asyncio.create_task
    # with the shape the route uses. A full e2e covers the real /start at
    # Plan 22b-06 Gate B.
    from api_server.services.watcher_service import run_watcher
    from api_server.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
        row_id = __import__("uuid").uuid4()
        recipe = {"channels": {"telegram": {"event_log_regex": {
            "reply_sent": r"reply (?P<chat_id>\d+)"}}}}
        task = asyncio.create_task(run_watcher(
            app.state,
            container_row_id=row_id,
            container_id=container.id,
            agent_id=seed_agent_instance,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="123",
        ))
        await asyncio.sleep(0.3)
        assert row_id in app.state.log_watchers
        container.remove(force=True)
        await asyncio.wait_for(task, timeout=3.0)
        assert row_id not in app.state.log_watchers
```

This test validates the MECHANICS used by the route (run_watcher + registry + teardown) without paying the cost of a real /start. A true route-integration test (hitting POST /v1/agents/:id/start with a real hermes image) is deferred to Plan 22b-06's e2e script.

**Part D — Create `api_server/tests/test_events_lifecycle_cancel_on_stop.py`:**

```python
"""Phase 22b-04 Task 2 — /stop drains watcher before execute_persistent_stop.

Unit-level check that the sequencing the route uses is correct: stop_event.set()
then await task with 2s budget, THEN teardown. We do NOT actually call
/v1/agents/:id/stop here (the full path needs a real persistent container);
instead we exercise the 3-line snippet the route body uses.
"""
import asyncio
import pytest
from uuid import uuid4
from api_server.services.watcher_service import run_watcher

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_stop_drains_watcher(running_alpine_container, real_db_pool, seed_agent_instance):
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo reply 123; sleep 0.1; done"])
    from api_server.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        row_id = uuid4()
        recipe = {"channels": {"telegram": {"event_log_regex": {
            "reply_sent": r"reply (?P<chat_id>\d+)"}}}}
        task = asyncio.create_task(run_watcher(
            app.state,
            container_row_id=row_id,
            container_id=container.id,
            agent_id=seed_agent_instance,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="123",
        ))
        await asyncio.sleep(0.4)
        assert row_id in app.state.log_watchers
        _t, stop_event = app.state.log_watchers[row_id]
        stop_event.set()
        # Also remove the container so the source iterator ends naturally
        # (stop_event alone would require the source's inner loop to check
        # between reads — docker_logs_stream checks is_set between yields).
        container.remove(force=True)
        await asyncio.wait_for(task, timeout=3.0)
        assert row_id not in app.state.log_watchers
```

Verify:
```bash
cd api_server && pytest -x tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py tests/test_events_lifespan_reattach.py -v 2>&1 | tail -15
```
All green.
  </action>
  <verify>
    <automated>cd api_server && pytest -x tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py tests/test_events_lifespan_reattach.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 4 { exit 0 } { exit 1 }'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "run_watcher(" api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1` (spawn)
    - `grep -c "asyncio.create_task(run_watcher" api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1`
    - `grep -c "stop_event.set()\|_wstop.set()" api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1`
    - `grep -c "asyncio.wait_for(.*timeout=2" api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1`
    - `grep -c "log_watchers" api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1`
    - The `stop_event.set()` call appears BEFORE `execute_persistent_stop` — verify by line number: `grep -n "stop_event.set()\|_wstop.set()" api_server/src/api_server/routes/agent_lifecycle.py` line number < `grep -n "execute_persistent_stop" api_server/src/api_server/routes/agent_lifecycle.py` FIRST line number in stop_agent body (use awk to compare)
    - The `asyncio.create_task(run_watcher(...))` spawn appears AFTER `write_agent_container_running` (Step 8): `awk '/write_agent_container_running/ {a=NR} /asyncio\.create_task\(run_watcher/ {b=NR} END {exit !(a && b && a < b)}' api_server/src/api_server/routes/agent_lifecycle.py` exits 0
    - `cd api_server && pytest -x tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py -v 2>&1 | grep -cE "PASSED"` returns `>=2`
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression in existing tests
  </acceptance_criteria>
  <done>start_agent spawns run_watcher after Step 8; stop_agent signals + awaits the watcher before execute_persistent_stop; 2 lifecycle tests pass; original /start and /stop behavior unchanged (existing test_agents.py / test_runs.py still green).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP client → `/v1/agents/:id/start` | Bearer token + body.channel_inputs cross here; spawn-path uses the already-validated agent/recipe/container_id produced by Step 8 |
| Lifespan startup → Docker daemon | `containers.get(cid)` to probe existence before re-attach; any daemon error falls through to `_log.exception` without blocking lifespan |
| Lifespan startup → Postgres | `SELECT FROM agent_containers WHERE container_status='running'` uses parameterized query (no user input — V13 holds by virtue of being a constant) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-04-01 | Denial of Service | Lifespan re-attach loop | mitigate | `containers.get(cid)` failures fall through to `_log.exception` + `continue` — one bad row cannot stall startup. Aggregate time budget: N rows × ~50ms inspect latency; for v1 (<=5 agents) this is <300ms even with failures |
| T-22b-04-02 | Elevation of Privilege | watcher spawn in /start | accept | The Bearer has already been validated by the time Step 8 completes; spawn path uses authenticated agent_id + recipe; no additional privilege introduced |
| T-22b-04-03 | Information Disclosure | `chat_id_hint` in run_watcher spawn | accept | `chat_id_hint` is numeric Telegram user ID (6-10 digits); not a secret per BYOK discipline; redaction threshold (8 chars in `_redact_creds`) does not apply |
| T-22b-04-04 | Tampering | Unknown event_source_fallback.kind in recipe at re-attach | mitigate | `run_watcher` → `_select_source` raises ValueError on unknown kinds (Plan 22b-03); re-attach loop catches via the `asyncio.create_task` + outer `try/except Exception` — one malformed recipe cannot block other re-attaches |
| T-22b-04-05 | Denial of Service | Shutdown watcher drain exceeds budget | mitigate | 2s `asyncio.wait` budget; tasks still running after budget are cancelled (spike-03 never observed this path but the fallback is safe). Prevents a slow watcher from blocking API shutdown indefinitely |
| T-22b-04-06 | Spoofing | Re-attach on container with UNKNOWN recipe | mitigate | `app.state.recipes.get(row["recipe_name"])` returns None for removed-recipe case; lifespan logs a WARNING and skips — the running container is left alone, its row stays 'running'; a future health-sweep phase will reconcile |
</threat_model>

<verification>
- `cd api_server && pytest -x tests/test_events_lifespan_reattach.py tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py -v 2>&1 | tail -10` shows all PASSED
- `python3 -c "from api_server.main import create_app; from api_server.constants import AP_SYSADMIN_TOKEN_ENV; app = create_app(); assert hasattr(app.state, 'log_watchers')"` exits 0
- `grep -n "log_watchers\|event_poll_signals\|event_poll_locks" api_server/src/api_server/main.py | wc -l | awk '$1 >= 3 { exit 0 } { exit 1 }'` passes (all 3 registries initialized)
- Order check: the `stop_event.set()` line in `stop_agent` is above the `execute_persistent_stop` line (verifiable via `grep -n`)
- No regression: `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no red
</verification>

<success_criteria>
1. `AP_SYSADMIN_TOKEN_ENV` constant exported from `api_server/src/api_server/constants.py`
2. `main.py` lifespan initializes `log_watchers` / `event_poll_signals` / `event_poll_locks`, re-attaches watchers for running rows, gracefully marks stopped rows whose container is missing, drains all watchers on shutdown within 2s
3. `start_agent` spawns `run_watcher` as a fire-and-forget task after Step 8; watcher-spawn failure is non-fatal to the HTTP response
4. `stop_agent` signals the watcher's `stop_event` and awaits with 2s budget BEFORE `execute_persistent_stop`
5. 2 lifespan tests + 2 lifecycle tests green on real Docker daemon + real PG via testcontainers
6. No regressions in existing tests
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-04-SUMMARY.md` with:
- Exact file changes (main.py, agent_lifecycle.py, constants.py) — line numbers where extensions landed
- The lifespan re-attach + shutdown shape used (SQL query + drain budget)
- The stop_agent sequencing proof (grep output showing `stop_event.set()` line number < `execute_persistent_stop` line number)
- Whether the missing-container path (Claude's Discretion) was implemented as "mark stopped + skip" (expected) or a different resolution
- The 4 lifecycle tests' measured wall times
</output>
