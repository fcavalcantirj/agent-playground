---
phase: 22b
plan: 05
type: execute
wave: 3
depends_on: ["22b-02", "22b-04"]
files_modified:
  - api_server/src/api_server/models/errors.py
  - api_server/src/api_server/routes/agent_events.py
  - api_server/src/api_server/main.py
  - api_server/tests/test_events_long_poll.py
  - api_server/tests/test_events_auth.py
autonomous: true
requirements:
  - SC-03-GATE-A
  - SC-03-GATE-B

must_haves:
  truths:
    - "models/errors.py exports two new ErrorCode constants: CONCURRENT_POLL_LIMIT (mapped to 'rate_limit_error') and EVENT_STREAM_UNAVAILABLE (mapped to 'infra_error')"
    - "GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent,reply_failed&timeout_s=30 returns rows seq>since_seq filtered by kinds with two DB scopes flanking asyncio.wait_for(signal.wait()) — NO pool connection held across the wait (Pitfall 4)"
    - "Bearer token required (401 UNAUTHORIZED if missing/empty); AP_SYSADMIN_TOKEN env-var bypass skips the ownership check when Bearer matches exactly (D-15)"
    - "Ownership check uses ANONYMOUS_USER_ID per Phase 19 MVP seam; 404 AGENT_NOT_FOUND if resolve-fails and caller is not sysadmin"
    - "Per-agent asyncio.Lock from app.state.event_poll_locks — second concurrent poll returns 429 CONCURRENT_POLL_LIMIT (D-13)"
    - "kinds CSV is parsed against a VALID_KINDS whitelist; any unknown kind returns 400 INVALID_REQUEST — NEVER interpolated into SQL (V13 defense)"
    - "Long-poll timeout (timeout_s param) returns 200 with {events:[], timed_out: true}; signal wake returns 200 with the new rows"
    - "Main.py includes agent_events router under /v1 prefix with tags=['agents']"
  artifacts:
    - path: "api_server/src/api_server/models/errors.py"
      provides: "Two new error codes in ErrorCode + _CODE_TO_TYPE mapping"
      contains: "CONCURRENT_POLL_LIMIT"
    - path: "api_server/src/api_server/routes/agent_events.py"
      provides: "GET /v1/agents/:id/events long-poll route"
      exports: ["router","get_events","_err","_project"]
    - path: "api_server/src/api_server/main.py"
      provides: "agent_events router mounted under /v1"
      contains: "agent_events"
    - path: "api_server/tests/test_events_long_poll.py"
      provides: "Timeout, signal-wake, since_seq, kinds filter, 429 concurrent tests"
      contains: "def test_long_poll"
    - path: "api_server/tests/test_events_auth.py"
      provides: "Bearer missing/empty, ownership 404, AP_SYSADMIN_TOKEN bypass tests"
      contains: "AP_SYSADMIN_TOKEN"
  key_links:
    - from: "api_server/src/api_server/routes/agent_events.py::get_events"
      to: "api_server/src/api_server/services/event_store.py::fetch_events_after_seq"
      via: "two DB scopes flanking asyncio.wait_for(signal.wait())"
      pattern: "fetch_events_after_seq"
    - from: "api_server/src/api_server/routes/agent_events.py::get_events"
      to: "app.state.event_poll_locks"
      via: "_get_poll_lock + 429 if already held"
      pattern: "_get_poll_lock"
    - from: "api_server/src/api_server/routes/agent_events.py::get_events"
      to: "app.state.event_poll_signals"
      via: "signal.clear() then await signal.wait() with timeout"
      pattern: "event_poll_signals\\|_get_poll_signal"
    - from: "api_server/src/api_server/main.py"
      to: "api_server/src/api_server/routes/agent_events.py"
      via: "app.include_router(agent_events_route.router, prefix='/v1', tags=['agents'])"
      pattern: "agent_events"
---

<objective>
Expose the event stream as a long-poll HTTP endpoint that the Gate B test harness (Plan 22b-06) consumes.

**Endpoint contract (D-09 + D-13 + D-15):**

```
GET /v1/agents/{agent_id}/events?since_seq=<int>&kinds=<csv>&timeout_s=<int>
Headers:
  Authorization: Bearer <token>
```

- `since_seq` defaults to 0; rows returned are strictly `seq > since_seq`.
- `kinds` is a CSV subset of `{reply_sent, reply_failed, agent_ready, agent_error}`; unknown kinds → 400. Default = all kinds.
- `timeout_s` is 1..60; defaults to 30.

**Response shapes:**

- **200 with rows:** `{"agent_id": "...", "events": [...], "next_since_seq": <max seq>, "timed_out": false}`
- **200 empty (timeout):** `{"agent_id": "...", "events": [], "next_since_seq": <since_seq>, "timed_out": true}`
- **400 INVALID_REQUEST:** unknown kind in CSV
- **401 UNAUTHORIZED:** missing or empty Bearer
- **403 UNAUTHORIZED:** ownership check failed (reserved for post-MVP — today all users map to `ANONYMOUS_USER_ID` so this path is unreachable without multi-tenant)
- **404 AGENT_NOT_FOUND:** agent_id resolve failure and caller is not sysadmin
- **429 CONCURRENT_POLL_LIMIT:** per-agent `asyncio.Lock` is already held (D-13)
- **503 EVENT_STREAM_UNAVAILABLE:** reserved for future watcher-dead detection — out of 22b scope, code is reserved so the enum is forward-compatible

**Two DB scopes (Pitfall 4):** scope-1 is the fast-path `fetch_events_after_seq` before the wait; if rows exist, return immediately. If none, release the pool connection, `_get_poll_signal(app_state, agent_id).clear()` then `await asyncio.wait_for(signal.wait(), timeout_s)`. On wake (or timeout), scope-2 re-queries and projects rows.

**Auth posture (D-15):** Bearer REQUIRED. If Bearer matches `os.environ[AP_SYSADMIN_TOKEN_ENV]` (when set), skip ownership check. Else resolve `user_id = ANONYMOUS_USER_ID`, look up agent_instance, 404 if resolve-fail. Ownership check `agent.user_id == user_id` is effectively `ANON==ANON` today — the seam is wired for multi-tenant tightening post-MVP.

**Shared edit to `models/errors.py`:** Plan 22b-04 does NOT modify errors.py; this plan owns the two new codes exclusively. The Wave 2 parallelizability is preserved because both plans converge on errors.py only via imports (Plan 22b-04's lifecycle module doesn't need these codes — it handles lifecycle errors, not events).

**Router registration in main.py:** This plan lands a second edit to `main.py` — only the router mount line. This is an ADDITIVE edit and does not conflict with Plan 22b-04's lifespan/app.state/router-scope edits (main.py is edited twice but in distinct regions). **Coordination:** Plan 22b-04 lands first (Wave 2 depends_on); Plan 22b-05 then adds the router-include line.

Purpose: SC-03 Gate A needs no endpoint (it uses `docker exec`), but SC-03 Gate B does — the harness `send-telegram-and-watch-events` subcommand (Plan 22b-06) long-polls this endpoint after the bot→self sendMessage probe.

Output: errors.py (2 new codes), agent_events.py (~150 lines new route module), main.py (router mount), 2 test files covering the long-poll contract + auth matrix.
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
@.planning/phases/22b-agent-event-stream/22b-02-SUMMARY.md
@api_server/src/api_server/models/errors.py
@api_server/src/api_server/routes/agent_lifecycle.py
@api_server/src/api_server/main.py
@api_server/src/api_server/constants.py
@api_server/src/api_server/services/event_store.py
@api_server/src/api_server/services/run_store.py
@api_server/tests/test_runs.py

<interfaces>
<!-- Imports this plan needs (from prior plans + existing substrate). -->

From api_server/src/api_server/services/event_store.py (Plan 22b-02):
```python
async def fetch_events_after_seq(conn, agent_container_id: UUID, since_seq: int,
                                  kinds: set[str] | None = None) -> list[dict]
```

From api_server/src/api_server/models/events.py (Plan 22b-02):
```python
VALID_KINDS: set[str] = {"reply_sent","reply_failed","agent_ready","agent_error"}
class AgentEvent(BaseModel): seq, kind, payload, correlation_id, ts
class AgentEventsResponse(BaseModel): agent_id, events, next_since_seq, timed_out
```

From api_server/src/api_server/services/watcher_service.py (Plan 22b-03):
```python
async def _get_poll_lock(app_state, agent_id: UUID) -> asyncio.Lock
def _get_poll_signal(app_state, agent_id: UUID) -> asyncio.Event
```

From api_server/src/api_server/services/run_store.py (existing):
```python
async def fetch_agent_instance(conn, agent_id: UUID, user_id: UUID) -> dict | None
```
(Verify the exact signature during execution — PATTERNS.md lines 444-450 documents the canonical call site in agent_lifecycle.py.)

From api_server/src/api_server/constants.py (Plan 22b-04):
```python
ANONYMOUS_USER_ID: UUID
AP_SYSADMIN_TOKEN_ENV: str = "AP_SYSADMIN_TOKEN"
```

From api_server/src/api_server/models/errors.py (existing — to be extended):
```python
class ErrorCode:
    UNAUTHORIZED, AGENT_NOT_FOUND, INVALID_REQUEST  # already present
def make_error_envelope(code, message, *, param, category) -> dict
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add CONCURRENT_POLL_LIMIT + EVENT_STREAM_UNAVAILABLE to errors.py</name>
  <files>api_server/src/api_server/models/errors.py, api_server/tests/test_events_auth.py</files>
  <read_first>
    - api_server/src/api_server/models/errors.py (the file being extended — read class ErrorCode and _CODE_TO_TYPE fully to understand existing shape and ordering)
    - 22b-PATTERNS.md §"api_server/src/api_server/models/errors.py (ADD-TO)" (authoritative add-only shape)
    - 22b-CONTEXT.md D-13 (concurrent poll lock) — CONCURRENT_POLL_LIMIT is the 429 return code
    - 22b-RESEARCH.md §"Pitfalls" + §"Common Pitfalls" — EVENT_STREAM_UNAVAILABLE is reserved for future watcher-dead detection
  </read_first>
  <behavior>
    - `from api_server.models.errors import ErrorCode; assert ErrorCode.CONCURRENT_POLL_LIMIT == "CONCURRENT_POLL_LIMIT"` succeeds.
    - `from api_server.models.errors import ErrorCode; assert ErrorCode.EVENT_STREAM_UNAVAILABLE == "EVENT_STREAM_UNAVAILABLE"` succeeds.
    - `make_error_envelope("CONCURRENT_POLL_LIMIT", "msg", param="agent_id", category=None)` returns a dict whose nested `error.type` equals `"rate_limit_error"`.
    - `make_error_envelope("EVENT_STREAM_UNAVAILABLE", "msg", param=None, category=None)` returns a dict whose nested `error.type` equals `"infra_error"`.
  </behavior>
  <action>
**Part A — Extend `api_server/src/api_server/models/errors.py`.**

Read the full file first. Locate `class ErrorCode:` (existing begins ~line 31 with `INVALID_REQUEST`). APPEND two new constants at the END of the class, AFTER the Phase 22-05 block:

```python
    # Phase 22b-05: event-stream error codes.
    CONCURRENT_POLL_LIMIT = "CONCURRENT_POLL_LIMIT"       # 429 — D-13
    EVENT_STREAM_UNAVAILABLE = "EVENT_STREAM_UNAVAILABLE" # 503 — reserved (watcher-dead future)
```

Locate `_CODE_TO_TYPE` (existing dict ~line 58). APPEND two new mappings at the END:

```python
    # Phase 22b-05 additions.
    ErrorCode.CONCURRENT_POLL_LIMIT: "rate_limit_error",
    ErrorCode.EVENT_STREAM_UNAVAILABLE: "infra_error",
```

Do NOT touch any other constant, any other mapping, or the Pydantic model definitions below.

**Part B — Start `api_server/tests/test_events_auth.py`** with the enum + envelope-type assertions (the full auth tests come in Task 3):

```python
"""Phase 22b-05 Task 1 — errors.py extension + Task 3 — full auth matrix.

This file is populated across two tasks:
- Task 1: Unit tests for the two new ErrorCode constants (this commit).
- Task 3: Integration tests that hit GET /v1/agents/:id/events with
  various Authorization shapes (next commit).
"""
from api_server.models.errors import ErrorCode, make_error_envelope


def test_concurrent_poll_limit_constant():
    assert ErrorCode.CONCURRENT_POLL_LIMIT == "CONCURRENT_POLL_LIMIT"


def test_event_stream_unavailable_constant():
    assert ErrorCode.EVENT_STREAM_UNAVAILABLE == "EVENT_STREAM_UNAVAILABLE"


def test_concurrent_poll_limit_maps_to_rate_limit_type():
    envelope = make_error_envelope(
        ErrorCode.CONCURRENT_POLL_LIMIT,
        "another long-poll is already active for this agent",
        param="agent_id",
        category=None,
    )
    assert envelope["error"]["code"] == "CONCURRENT_POLL_LIMIT"
    assert envelope["error"]["type"] == "rate_limit_error"
    assert envelope["error"]["param"] == "agent_id"


def test_event_stream_unavailable_maps_to_infra_type():
    envelope = make_error_envelope(
        ErrorCode.EVENT_STREAM_UNAVAILABLE,
        "watcher dead",
        param=None,
        category=None,
    )
    assert envelope["error"]["code"] == "EVENT_STREAM_UNAVAILABLE"
    assert envelope["error"]["type"] == "infra_error"
```

Verify:
```bash
cd api_server && pytest -x tests/test_events_auth.py -v 2>&1 | tail -10
```
4 tests green.
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.models.errors import ErrorCode; assert ErrorCode.CONCURRENT_POLL_LIMIT == 'CONCURRENT_POLL_LIMIT' and ErrorCode.EVENT_STREAM_UNAVAILABLE == 'EVENT_STREAM_UNAVAILABLE'" && pytest -x tests/test_events_auth.py -v 2>&1 | grep -qE "4 passed|passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "CONCURRENT_POLL_LIMIT = \"CONCURRENT_POLL_LIMIT\"" api_server/src/api_server/models/errors.py` returns `1`
    - `grep -c "EVENT_STREAM_UNAVAILABLE = \"EVENT_STREAM_UNAVAILABLE\"" api_server/src/api_server/models/errors.py` returns `1`
    - `grep -c "ErrorCode.CONCURRENT_POLL_LIMIT: \"rate_limit_error\"" api_server/src/api_server/models/errors.py` returns `1`
    - `grep -c "ErrorCode.EVENT_STREAM_UNAVAILABLE: \"infra_error\"" api_server/src/api_server/models/errors.py` returns `1`
    - Existing codes are UNCHANGED: `grep -c "INVALID_REQUEST\|AGENT_NOT_FOUND\|UNAUTHORIZED" api_server/src/api_server/models/errors.py` returns a count >=6 (3 constants × 2 appearances each: class + _CODE_TO_TYPE)
    - `cd api_server && pytest -x tests/test_events_auth.py -v 2>&1 | grep -cE "PASSED"` returns `>=4`
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression
  </acceptance_criteria>
  <done>2 new ErrorCode constants + 2 new _CODE_TO_TYPE mappings; envelope projection is correct (rate_limit_error + infra_error); 4 unit tests green; no regression in any existing error test.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: agent_events route + main.py router mount + long-poll tests</name>
  <files>api_server/src/api_server/routes/agent_events.py, api_server/src/api_server/main.py, api_server/tests/test_events_long_poll.py</files>
  <read_first>
    - api_server/src/api_server/routes/agent_lifecycle.py (ANALOG — read `_err` helper lines 87-106, Bearer parse lines 174-189, `fetch_agent_instance` usage lines 192-201, 9-step docstring lines 1-36)
    - api_server/src/api_server/main.py (the file being extended — locate existing `app.include_router(...)` call sites for the routing pattern)
    - api_server/src/api_server/services/event_store.py (Plan 22b-02 — fetch_events_after_seq signature)
    - api_server/src/api_server/services/watcher_service.py (Plan 22b-03 — _get_poll_lock, _get_poll_signal)
    - 22b-PATTERNS.md §"api_server/src/api_server/routes/agent_events.py" (AUTHORITATIVE — lines 376-504 contain module docstring, Bearer parse, ownership, long-poll flow, query validation)
    - 22b-RESEARCH.md §"Pattern 2: asyncpg connection-per-scope across long awaits" (authoritative two-scope flow — lines 393-425)
    - 22b-CONTEXT.md D-09, D-13, D-15
    - 22b-RESEARCH.md §"Known Threat Patterns" row "SQL injection via kinds" — VALID_KINDS whitelist parsing
    - api_server/tests/test_runs.py (analog for httpx AsyncClient + ASGITransport fixture)
  </read_first>
  <behavior>
    - `GET /v1/agents/<uuid>/events` without Authorization header → 401 `UNAUTHORIZED`.
    - `GET .../events` with `Authorization: Bearer <token-matching-AP_SYSADMIN_TOKEN>` → bypasses ownership; if agent_id doesn't exist, returns 200 with `events=[]` (sysadmin path — no ownership validation).
    - `GET .../events` with valid Bearer but no sysadmin token set → ownership check uses `ANONYMOUS_USER_ID`; 404 if agent not found.
    - `GET .../events?since_seq=0&kinds=reply_sent&timeout_s=1` — events already in DB with `seq>0` and `kind='reply_sent'` are returned immediately.
    - `GET .../events?since_seq=999&timeout_s=1` — no rows; handler releases DB connection, waits 1s on signal, returns 200 with `timed_out=true` and `events=[]`.
    - Concurrent second request for the SAME agent_id while the first is still waiting → 429 `CONCURRENT_POLL_LIMIT`.
    - `GET .../events?kinds=reply_sent,invalid_kind` → 400 `INVALID_REQUEST` (param='kinds').
    - Watcher INSERTs a new row → `_get_poll_signal(app_state, agent_id).set()` wakes the pending handler → scope-2 fetch returns the new row → handler returns 200 with the row.
  </behavior>
  <action>
**Part A — Create `api_server/src/api_server/routes/agent_events.py`.**

Follow 22b-PATTERNS.md §"api_server/src/api_server/routes/agent_events.py" (lines 376-504) for the authoritative shape. The module has four concerns: imports + logger + `_err` helper + `_project` helper + the GET route.

```python
"""Agent event-stream long-poll endpoint (Phase 22b-05).

One endpoint: ``GET /v1/agents/:id/events`` — long-poll with since_seq +
kinds filter + timeout_s.

Canonical flow (short — no runner call):

  1. Parse ``Authorization: Bearer <token>`` — D-15 auth posture
  2. If Bearer == AP_SYSADMIN_TOKEN → bypass ownership; else:
     Resolve user_id = ANONYMOUS_USER_ID (Phase 19 MVP seam);
     Lookup agent_instance; 404 if missing;
     Ownership check: agent.user_id == user_id (already enforced by
     fetch_agent_instance's user_id filter in run_store.py).
  3. Acquire per-agent long-poll lock (D-13); 429 if already held
  4. DB scope 1: fetch_events_after_seq(since_seq, kinds) — fast path
  5. If rows: return immediately
  6. NO DB held during wait (Pitfall 4):
     await asyncio.wait_for(signal.wait(), timeout_s)
  7. On timeout: return 200 with events=[] + timed_out=true
  8. DB scope 2: re-query + project
  9. Return AgentEventsResponse

Pitfall 4 (DB pool exhaustion): two distinct ``async with pool.acquire()``
scopes flank the 30s ``asyncio.wait_for(signal.wait())``. Holding the
connection across the wait exhausts the pool under modest poll-fanout.
"""
from __future__ import annotations
import asyncio
import logging
import os
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from ..constants import ANONYMOUS_USER_ID, AP_SYSADMIN_TOKEN_ENV
from ..models.errors import ErrorCode, make_error_envelope
from ..models.events import VALID_KINDS
from ..services.event_store import fetch_events_after_seq
from ..services.run_store import fetch_agent_instance
from ..services.watcher_service import _get_poll_lock, _get_poll_signal

router = APIRouter()
_log = logging.getLogger("api_server.agent_events")


def _err(status: int, code: str, message: str, *, param: str | None = None,
         category: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )


def _project(rows: list[dict], since_seq: int, agent_id: UUID,
             timed_out: bool) -> JSONResponse:
    """Project event_store rows into the AgentEventsResponse shape."""
    events = []
    next_seq = since_seq
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            # asyncpg may decode JSONB to str in some codecs; be defensive.
            import json as _json
            payload = _json.loads(payload)
        events.append({
            "seq": int(r["seq"]),
            "kind": r["kind"],
            "payload": payload,
            "correlation_id": r.get("correlation_id"),
            "ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"]),
        })
        if int(r["seq"]) > next_seq:
            next_seq = int(r["seq"])
    return JSONResponse(
        status_code=200,
        content={
            "agent_id": str(agent_id),
            "events": events,
            "next_since_seq": next_seq,
            "timed_out": timed_out,
        },
    )


@router.get("/agents/{agent_id}/events")
async def get_events(
    request: Request,
    agent_id: UUID,
    since_seq: int = Query(0, ge=0),
    kinds: str | None = Query(None, max_length=256),
    timeout_s: int = Query(30, ge=1, le=60),
    authorization: str = Header(default=""),
):
    # Step 1 — Bearer parse.
    if not authorization.startswith("Bearer "):
        return _err(401, ErrorCode.UNAUTHORIZED,
                    "Bearer token required", param="Authorization")
    bearer = authorization[len("Bearer "):].strip()
    if not bearer:
        return _err(401, ErrorCode.UNAUTHORIZED,
                    "Bearer token is empty", param="Authorization")

    # Step 2 — sysadmin bypass OR ownership check.
    sysadmin_token = os.environ.get(AP_SYSADMIN_TOKEN_ENV) or ""
    is_sysadmin = bool(sysadmin_token) and bearer == sysadmin_token

    pool = request.app.state.db
    if not is_sysadmin:
        async with pool.acquire() as conn:
            agent = await fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)
        if agent is None:
            return _err(404, ErrorCode.AGENT_NOT_FOUND,
                        f"agent {agent_id} not found", param="agent_id")

    # Step 2b — kinds param (V5 input validation + V13 defense).
    kinds_set: set[str] | None = None
    if kinds:
        parsed = {k.strip() for k in kinds.split(",") if k.strip()}
        bad = parsed - VALID_KINDS
        if bad:
            return _err(400, ErrorCode.INVALID_REQUEST,
                        f"unknown kind(s): {sorted(bad)}", param="kinds")
        kinds_set = parsed

    # Step 3 — per-agent long-poll lock (D-13).
    poll_lock = await _get_poll_lock(request.app.state, agent_id)
    if poll_lock.locked():
        return _err(429, ErrorCode.CONCURRENT_POLL_LIMIT,
                    "another long-poll is already active for this agent",
                    param="agent_id")

    async with poll_lock:
        # Step 3b — CLEAR the wake signal BEFORE any fetch. If we cleared AFTER
        # the fast-path fetch, a watcher INSERT between fetch and clear would
        # have its .set() overwritten, causing a missed wake. Clear-then-fetch
        # means any set() after the clear (i.e. any INSERT after our fetch)
        # will survive for the subsequent signal.wait() to observe.
        signal = _get_poll_signal(request.app.state, agent_id)
        signal.clear()

        # Step 4 — DB scope 1 (fast path), with the wake signal armed.
        async with pool.acquire() as conn:
            rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds_set)
        # Step 5 — immediate return if rows exist.
        if rows:
            return _project(rows, since_seq, agent_id, timed_out=False)

        # Step 6 — NO DB held during the wait (Pitfall 4).
        try:
            await asyncio.wait_for(signal.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # Step 7 — timeout returns 200 empty.
            return _project([], since_seq, agent_id, timed_out=True)

        # Step 8 — DB scope 2 (re-query after signal fires).
        async with pool.acquire() as conn:
            rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds_set)
        # Step 9 — project + return.
        return _project(rows, since_seq, agent_id, timed_out=False)
```

**Part B — Extend `api_server/src/api_server/main.py`** with the router mount.

Read main.py to locate the existing `app.include_router(...)` calls. ADD, after them:

```python
from .routes import agent_events as agent_events_route
app.include_router(agent_events_route.router, prefix="/v1", tags=["agents"])
```

(If Plan 22b-04 has already been merged, the file may already have prior imports — add the new import alongside them; do NOT duplicate.)

**Part C — Create `api_server/tests/test_events_long_poll.py`:**

```python
"""Phase 22b-05 Task 2 — long-poll contract tests.

Hits GET /v1/agents/:id/events with various since_seq / kinds / timeout_s
combinations + concurrent-poll 429. Uses httpx AsyncClient + ASGITransport
per the test_runs.py pattern; real PG via testcontainers; NO docker required
for these tests (watcher is simulated by directly inserting rows via
insert_agent_event and setting signal manually).
"""
import asyncio
import os
import pytest
from uuid import uuid4, UUID

pytestmark = pytest.mark.asyncio


async def _get_app_and_client():
    from api_server.main import create_app
    from httpx import AsyncClient, ASGITransport
    app = create_app()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return app, client


@pytest.fixture
def sysadmin_env(monkeypatch):
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


async def test_long_poll_returns_existing_rows_immediately(
    seed_agent_container, real_db_pool, sysadmin_env,
):
    from api_server.services.event_store import insert_agent_event
    async with real_db_pool.acquire() as conn:
        await insert_agent_event(
            conn, seed_agent_container, "reply_sent",
            {"chat_id": "1", "length_chars": 3, "captured_at": "2026-04-18T00:00:00Z"},
            correlation_id="abc1",
        )
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=2",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["timed_out"] is False
    assert len(body["events"]) == 1
    assert body["events"][0]["kind"] == "reply_sent"
    assert body["next_since_seq"] == 1


async def test_long_poll_timeout_empty(seed_agent_container, real_db_pool, sysadmin_env):
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=9999&timeout_s=1",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=5.0,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timed_out"] is True
    assert body["events"] == []
    assert body["next_since_seq"] == 9999


async def test_long_poll_signal_wake(seed_agent_container, real_db_pool, sysadmin_env):
    """INSERT a row mid-wait; signal.set() should wake the handler."""
    from api_server.services.event_store import insert_agent_event
    from api_server.services.watcher_service import _get_poll_signal
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        async def waker():
            await asyncio.sleep(0.5)
            async with real_db_pool.acquire() as conn:
                await insert_agent_event(
                    conn, seed_agent_container, "reply_sent",
                    {"chat_id":"1","length_chars":1,"captured_at":"2026-04-18T00:00:00Z"},
                    correlation_id="wake1",
                )
            _get_poll_signal(app.state, seed_agent_container).set()

        waker_task = asyncio.create_task(waker())
        resp = await client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=3",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=5.0,
        )
        await waker_task
    assert resp.status_code == 200
    body = resp.json()
    assert body["timed_out"] is False
    assert len(body["events"]) >= 1


async def test_long_poll_kinds_filter(seed_agent_container, real_db_pool, sysadmin_env):
    from api_server.services.event_store import insert_agent_event
    async with real_db_pool.acquire() as conn:
        await insert_agent_event(conn, seed_agent_container, "reply_sent",
            {"chat_id":"1","length_chars":1,"captured_at":"2026-04-18T00:00:00Z"})
        await insert_agent_event(conn, seed_agent_container, "agent_error",
            {"severity":"ERROR","detail":"x","captured_at":"2026-04-18T00:00:01Z"})
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=0&kinds=reply_sent&timeout_s=1",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    body = resp.json()
    kinds_returned = {e["kind"] for e in body["events"]}
    assert kinds_returned == {"reply_sent"}


async def test_long_poll_unknown_kind_400(seed_agent_container, sysadmin_env):
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{seed_agent_container}/events?kinds=bogus&timeout_s=1",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


async def test_long_poll_concurrent_poll_429(seed_agent_container, real_db_pool, sysadmin_env):
    """Second concurrent poll on the SAME agent → 429."""
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        # First poll waits 2s with no rows
        first = asyncio.create_task(client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=9998&timeout_s=2",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=5.0,
        ))
        await asyncio.sleep(0.2)   # let first grab the lock
        second = await client.get(
            f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=1",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=3.0,
        )
        await first
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "CONCURRENT_POLL_LIMIT"
```

Verify:
```bash
cd api_server && pytest -x tests/test_events_long_poll.py -v 2>&1 | tail -20
```
All 6 tests green.
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.routes.agent_events import router, get_events, _err, _project" && pytest -x tests/test_events_long_poll.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 6 { exit 0 } { exit 1 }'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@router.get(\"/agents/{agent_id}/events\")" api_server/src/api_server/routes/agent_events.py` returns `1`
    - `grep -c "async def get_events" api_server/src/api_server/routes/agent_events.py` returns `1`
    - `grep -c "pool.acquire()" api_server/src/api_server/routes/agent_events.py` returns `>=2` (two DB scopes per Pitfall 4)
    - `grep -c "asyncio.wait_for(signal.wait" api_server/src/api_server/routes/agent_events.py` returns `1`
    - The FIRST `signal.clear()` in agent_events.py precedes the FIRST `fetch_events_after_seq` call: `awk '/signal\.clear\(\)/ {a=NR} /fetch_events_after_seq/ {b=NR} END {exit !(a && b && a < b)}' api_server/src/api_server/routes/agent_events.py` exits 0 (arms the wake signal before the fast-path fetch — prevents missed-wake race per the D-13 long-poll contract)
    - `grep -c "CONCURRENT_POLL_LIMIT" api_server/src/api_server/routes/agent_events.py` returns `>=1`
    - `grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/routes/agent_events.py` returns `>=1`
    - `grep -c "VALID_KINDS" api_server/src/api_server/routes/agent_events.py` returns `>=1`
    - `grep -c "include_router(agent_events_route.router" api_server/src/api_server/main.py` returns `1` (OR equivalent formulation `include_router(agent_events.router` if imports were named differently — verify main.py has exactly one router mount for this module)
    - `grep -c "agent_events" api_server/src/api_server/main.py` returns `>=2` (import + include_router)
    - `cd api_server && pytest -x tests/test_events_long_poll.py -v 2>&1 | grep -cE "PASSED"` returns `>=6`
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression
  </acceptance_criteria>
  <done>Long-poll route lands with two DB scopes flanking the wait; kinds whitelist parsing; concurrent-poll 429; router mounted under /v1; 6 contract tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Full auth matrix — Bearer required, AP_SYSADMIN_TOKEN bypass, ownership 404</name>
  <files>api_server/tests/test_events_auth.py</files>
  <read_first>
    - api_server/tests/test_events_auth.py (the file being extended — Task 1 seeded it with 4 unit tests; Task 3 APPENDS the integration tests)
    - api_server/src/api_server/routes/agent_events.py (Task 2 output — the auth code path being tested)
    - 22b-CONTEXT.md D-15 (the full auth posture spec)
    - api_server/tests/test_runs.py (httpx + ASGITransport pattern for integration tests against the real route)
    - api_server/src/api_server/services/run_store.py — fetch_agent_instance filters by user_id (so ownership is enforced at SQL-level; the handler just converts "agent is None" into 404)
  </read_first>
  <behavior>
    - `GET .../events` without Authorization header → 401 `UNAUTHORIZED`, param='Authorization'.
    - `GET .../events` with `Authorization: NotBearer token` → 401 (no "Bearer " prefix).
    - `GET .../events` with `Authorization: Bearer ` (empty after prefix) → 401 UNAUTHORIZED ("Bearer token is empty").
    - `GET .../events` with `Authorization: Bearer <AP_SYSADMIN_TOKEN value>` and agent_id that DOES NOT EXIST in the DB → 200 with `events=[]` and `timed_out=true` (sysadmin bypass skips the ownership/existence check).
    - `GET .../events` with a random-not-sysadmin Bearer and an agent_id that DOES NOT EXIST → 404 `AGENT_NOT_FOUND`.
    - `GET .../events` with a random-not-sysadmin Bearer and an agent_id that DOES EXIST (belongs to ANONYMOUS_USER_ID per Phase 19 MVP) → 200 (ownership check passes).
  </behavior>
  <action>
APPEND to `api_server/tests/test_events_auth.py`:

```python
# ----------- Integration auth tests (Task 3) -----------

import pytest
from uuid import uuid4


pytestmark_integration = pytest.mark.integration


async def _get_app_and_client():
    from api_server.main import create_app
    from httpx import AsyncClient, ASGITransport
    app = create_app()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return app, client


@pytest.fixture
def sysadmin_env(monkeypatch):
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


@pytest.mark.asyncio
async def test_missing_authorization_returns_401():
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(f"/v1/agents/{uuid4()}/events?timeout_s=1")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    assert resp.json()["error"].get("param") == "Authorization"


@pytest.mark.asyncio
async def test_non_bearer_scheme_returns_401():
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{uuid4()}/events?timeout_s=1",
            headers={"Authorization": "Token abc123"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_empty_bearer_returns_401():
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{uuid4()}/events?timeout_s=1",
            headers={"Authorization": "Bearer "},
        )
    assert resp.status_code == 401
    assert "empty" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_sysadmin_bypass_on_nonexistent_agent(sysadmin_env):
    """AP_SYSADMIN_TOKEN bypass: even a made-up agent_id returns 200 empty."""
    app, client = await _get_app_and_client()
    random_agent = uuid4()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{random_agent}/events?timeout_s=1",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=5.0,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["events"] == []
    assert body["timed_out"] is True


@pytest.mark.asyncio
async def test_non_sysadmin_nonexistent_agent_404(monkeypatch):
    """Without sysadmin bypass and no matching agent_instance → 404."""
    monkeypatch.delenv("AP_SYSADMIN_TOKEN", raising=False)
    app, client = await _get_app_and_client()
    random_agent = uuid4()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{random_agent}/events?timeout_s=1",
            headers={"Authorization": "Bearer anyvalue"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_anonymous_user_existing_agent_200(seed_agent_instance, monkeypatch):
    """Regular bearer (non-sysadmin) + real agent owned by ANONYMOUS_USER_ID → 200 empty."""
    monkeypatch.delenv("AP_SYSADMIN_TOKEN", raising=False)
    app, client = await _get_app_and_client()
    async with app.router.lifespan_context(app):
        resp = await client.get(
            f"/v1/agents/{seed_agent_instance}/events?since_seq=9999&timeout_s=1",
            headers={"Authorization": "Bearer some-regular-bearer"},
            timeout=5.0,
        )
    assert resp.status_code == 200
    assert resp.json()["timed_out"] is True
```

Note: `seed_agent_instance` is a fixture created (or to be created) in the Phase 22 conftest that seeds an `agent_instances` row owned by `ANONYMOUS_USER_ID`. If it does not exist, define it inline in this test file using asyncpg against `real_db_pool`.

Verify:
```bash
cd api_server && pytest -x tests/test_events_auth.py -v 2>&1 | tail -20
```
All 10 tests green (4 unit from Task 1 + 6 integration from Task 3).
  </action>
  <verify>
    <automated>cd api_server && pytest -x tests/test_events_auth.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 10 { exit 0 } { exit 1 }'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def test_missing_authorization_returns_401\|def test_non_bearer_scheme_returns_401\|def test_empty_bearer_returns_401" api_server/tests/test_events_auth.py` returns `3`
    - `grep -c "def test_sysadmin_bypass_on_nonexistent_agent\|def test_non_sysadmin_nonexistent_agent_404\|def test_anonymous_user_existing_agent_200" api_server/tests/test_events_auth.py` returns `3`
    - `cd api_server && pytest -x tests/test_events_auth.py -v 2>&1 | grep -cE "PASSED"` returns `>=10`
    - `cd api_server && pytest -x tests/test_events_long_poll.py tests/test_events_auth.py -v 2>&1 | tail -3 | grep -E "passed" | grep -cvE "failed|error"` returns `>=1`
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression
  </acceptance_criteria>
  <done>Full auth matrix covered: missing/non-Bearer/empty all 401; sysadmin bypass returns 200 on nonexistent; non-sysadmin + nonexistent = 404; non-sysadmin + existing ANON-owned = 200 timeout; 6 integration tests green on real PG + full FastAPI stack.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP client → `/v1/agents/:id/events` | Bearer token + query params cross here (untrusted); handler validates before any DB work |
| `kinds` CSV → event_store.fetch_events_after_seq | Untrusted CSV converted to `set[str]` → whitelist-filtered against `VALID_KINDS` → passed as `list[str]` to asyncpg `$3::text[]` binding; SQL injection impossible |
| Bearer → `os.environ[AP_SYSADMIN_TOKEN]` comparison | Constant-time comparison NOT used — acceptable because the sysadmin path is local-only (dev laptop) per CONTEXT.md §specifics; V6 doesn't require constant-time for the admin bypass surface in 22b (documented as post-MVP hardening) |
| Pool connection → long-poll wait | NOT held across `await signal.wait()` (Pitfall 4); two distinct `async with pool.acquire()` scopes |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-05-01 | Elevation of Privilege | AP_SYSADMIN_TOKEN bypass | mitigate | Token is a 32-byte urlsafe random value per CLAUDE.md env-var discipline; Bearer equality check gates the bypass; handler still fetches agent_id from path param (typo-checked via UUID route validation). Ownership check is skipped ONLY when sysadmin matches exactly — never for partial or case-different values. Test `test_sysadmin_bypass_on_nonexistent_agent` and `test_non_sysadmin_nonexistent_agent_404` are the regression guard |
| T-22b-05-02 | Injection | `kinds` CSV | mitigate | Parse CSV → `set[str]` → filter by `VALID_KINDS` whitelist → any non-whitelisted value returns 400. Plan 22b-02's `fetch_events_after_seq` binds via `kind = ANY($3::text[])`; no interpolation anywhere in the chain. Test `test_long_poll_unknown_kind_400` + grep for no string-format in fetch_events_after_seq (Plan 22b-02's acceptance criterion) |
| T-22b-05-03 | Denial of Service | Long-poll connection exhaustion | mitigate | Two-scope DB pattern (Pitfall 4) releases the pool connection BEFORE the 30s wait; FastAPI default pool size 10 can sustain hundreds of concurrent pollers. D-13 per-agent lock (429) prevents a single agent from spawning more than one live poll at a time |
| T-22b-05-04 | Denial of Service | Timeout parameter abuse (timeout_s=999999) | mitigate | `Query(30, ge=1, le=60)` clamps timeout_s to [1, 60]; out-of-range returns 422 via FastAPI's built-in validation |
| T-22b-05-05 | Information Disclosure | Error message leaking Bearer value | mitigate | Error envelopes never include the Bearer; `_log.exception` inside the handler doesn't receive the Bearer directly (it's held in a local variable only used for the sysadmin comparison). Defense-in-depth: the `_redact_creds` helper from `agent_lifecycle.py` could be imported if we ever log the Bearer, but current code does not |
| T-22b-05-06 | Elevation of Privilege | Cross-tenant read via forged agent_id | mitigate | Non-sysadmin path: `fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)` filters by `user_id` at the SQL level (existing substrate behavior). Cross-tenant reads require the attacker to know a valid agent UUID owned by someone else AND bypass the ANON→ANON check (impossible in Phase 19 MVP seam). Post-MVP multi-tenant tightening is a one-liner |
| T-22b-05-07 | Denial of Service | Per-agent lock stuck after handler panic | accept | `async with poll_lock:` releases on exception; Python's `contextlib` guarantees. A crashed process loses all locks (they live in app.state). Test `test_long_poll_concurrent_poll_429` is the happy-path verification; a panic-recovery test would require simulating an async exception mid-wait, out of 22b scope |
| T-22b-05-08 | Information Disclosure | ReDoS on kinds CSV | accept | CSV splitting is stdlib; no regex on user input in this handler (regex compilation is only on recipe-authored strings, which live in Plan 22b-03's watcher) |
</threat_model>

<verification>
- `cd api_server && pytest -x tests/test_events_long_poll.py tests/test_events_auth.py -v 2>&1 | tail -10` shows all 10+ tests PASSED
- `python3 -c "from api_server.routes.agent_events import router, get_events, _err, _project; from api_server.models.errors import ErrorCode; assert ErrorCode.CONCURRENT_POLL_LIMIT == 'CONCURRENT_POLL_LIMIT' and ErrorCode.EVENT_STREAM_UNAVAILABLE == 'EVENT_STREAM_UNAVAILABLE'"` exits 0
- `python3 -c "from api_server.main import create_app; app = create_app(); routes = [r.path for r in app.routes]; assert any('/agents/' in p and '/events' in p for p in routes)"` exits 0
- Two `pool.acquire()` scopes verified by grep: `grep -c 'pool.acquire()' api_server/src/api_server/routes/agent_events.py` returns `2`
- `asyncio.wait_for(signal.wait())` NOT inside a pool.acquire scope — verify by inspecting the file structure (Task 2 acceptance criteria is the grep guard)
- No regression: `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no red
</verification>

<success_criteria>
1. `CONCURRENT_POLL_LIMIT` (429) + `EVENT_STREAM_UNAVAILABLE` (503) codes added to `models/errors.py`
2. `routes/agent_events.py` implements `GET /v1/agents/:id/events` with: Bearer auth + sysadmin bypass + kinds whitelist + two-scope Pitfall-4 pattern + per-agent lock + 429 on concurrent
3. Router mounted at `/v1` in `main.py`
4. 10+ tests green: 4 unit error-code + 6 long-poll contract + 6 auth-matrix = 16+ total (some shared via fixtures)
5. Bearer token + kinds CSV handled per D-15 + D-13; no SQL injection surface; no pool-exhaustion risk
6. No regression in existing test suite
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-05-SUMMARY.md` with:
- The 2 ErrorCode additions and their envelope-type mappings
- The route module size + the exact `_project` shape used (datetime.isoformat() vs str — may differ from spec if asyncpg returns naive datetime; document the chosen format)
- Measured wall times for the timeout + signal-wake tests (should be approximately timeout_s for timeout path; ≤ 0.7s for signal wake)
- The final grep output proving exactly 2 `pool.acquire()` scopes in agent_events.py
- Any deviation from PATTERNS.md §"routes/agent_events.py" authoritative shape
- Which test file path (`seed_agent_instance`) fixture — whether inherited or inline-defined
</output>
