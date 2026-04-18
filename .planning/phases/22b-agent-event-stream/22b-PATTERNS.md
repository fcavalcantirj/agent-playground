# Phase 22b: agent-event-stream — Pattern Map

**Mapped:** 2026-04-18
**Files analyzed:** 19 new/modified (10 src, 3 tests seed, 2 test harness, 2 recipes+schema, 1 alembic, 1 pyproject)
**Analogs found:** 17 / 19 (2 greenfield — `DockerLogsStreamSource` and `FileTailInContainerSource` have no existing codebase analog; borrow from spike artifacts + `runner_bridge` idiom)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `api_server/alembic/versions/004_agent_events.py` | migration | one-shot DDL | `api_server/alembic/versions/003_agent_containers.py` | exact |
| `api_server/src/api_server/models/events.py` | model (Pydantic) | request-response | `api_server/src/api_server/models/agents.py` | exact |
| `api_server/src/api_server/models/errors.py` (ADD-TO) | model / error taxonomy | request-response | `api_server/src/api_server/models/errors.py` (self-extend) | exact |
| `api_server/src/api_server/services/event_store.py` | store (CRUD) | CRUD + advisory-lock seq | `api_server/src/api_server/services/run_store.py` | exact role, new seq-allocation twist |
| `api_server/src/api_server/services/watcher_service.py` | service (async bridge + pump) | streaming | `api_server/src/api_server/services/runner_bridge.py` | role-match (bridge pattern); watcher semantics NEW |
| `api_server/src/api_server/routes/agent_events.py` | route (long-poll) | event-driven + request-response | `api_server/src/api_server/routes/agent_lifecycle.py` (stop_agent handler closest) | exact role, new long-poll twist |
| `api_server/src/api_server/routes/agent_lifecycle.py` (ADD-TO) | route (CRUD + watcher spawn/cancel) | request-response | self-extend | exact |
| `api_server/src/api_server/main.py` (ADD-TO) | bootstrap / lifespan | startup-shutdown | self-extend | exact |
| `api_server/src/api_server/constants.py` (ADD-TO) | config constants | — | self-extend | exact |
| `api_server/pyproject.toml` (ADD-TO) | deps | — | self-extend | exact |
| `api_server/tests/conftest.py` (ADD-TO) | test fixture | — | self-extend (Wave 0) | exact |
| `api_server/tests/test_events_migration.py` | test | schema DDL | `api_server/tests/test_migration.py` | exact |
| `api_server/tests/test_events_store.py` | test (CRUD + concurrency) | CRUD | `api_server/tests/test_run_concurrency.py` | exact |
| `api_server/tests/test_events_watcher_*.py` (3 files) | test (watcher source kinds + teardown + backpressure) | streaming | spike artifacts (spike-02, 03) | spike-port |
| `api_server/tests/test_events_long_poll.py` | test (HTTP integration) | event-driven HTTP | `api_server/tests/test_runs.py` | exact |
| `api_server/tests/test_events_lifespan_reattach.py` | test (app lifecycle) | startup-reattach | NEW shape | greenfield |
| `test/lib/agent_harness.py` (renamed from `telegram_harness.py`) | test harness CLI | request-response | `test/lib/telegram_harness.py` (rewrite), `test/smoke-api.sh` (style) | exact role, new subcommands |
| `test/e2e_channels_v0_2.sh` (REWRITE step 4/5) | e2e harness | request-response | self-extend | exact |
| `recipes/*.yaml` (5 recipes — ADD-TO) | recipe-schema-extension | — | `recipes/openclaw.yaml` + `recipes/nullclaw.yaml` (already have `event_log_regex` + `event_source_fallback` from spikes) | exact |

---

## Pattern Assignments

### `api_server/alembic/versions/004_agent_events.py` (migration, DDL)

**Analog:** `api_server/alembic/versions/003_agent_containers.py`

**Header + revision metadata** (003 lines 1-57):
```python
"""Phase 22b-01 — agent_events table (durable event stream).

Adds a new `agent_events` table ...
Columns ... Indexes ... Revision ID ...
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_agent_events"
down_revision = "003_agent_containers"
branch_labels = None
depends_on = None
```

**Table creation + CHECK constraint + partial-unique-index idiom** (003 lines 60-136):
```python
def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),  # BIGSERIAL
        sa.Column(
            "agent_container_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_containers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_agent_events_kind",
        "agent_events",
        "kind IN ('reply_sent', 'reply_failed', 'agent_ready', 'agent_error')",
    )
    op.create_unique_constraint(
        "uq_agent_events_container_seq",
        "agent_events",
        ["agent_container_id", "seq"],
    )
    op.create_index(
        "ix_agent_events_container_seq_desc",
        "agent_events",
        ["agent_container_id", sa.text("seq DESC")],
    )
```

**Downgrade ordering discipline** (003 lines 139-158): drop indexes + constraints before the table.

**CASCADE FK pattern** (003 line 72): `sa.ForeignKey("agent_instances.id", ondelete="CASCADE")` — 004 uses `agent_containers.id` with the same `ondelete="CASCADE"` so an agent_containers row delete purges its events (D-17 retention hook).

---

### `api_server/src/api_server/models/events.py` (model, request-response)

**Analog:** `api_server/src/api_server/models/agents.py`

**Imports + docstring pattern** (agents.py lines 24-29):
```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
```

**`ConfigDict(extra="forbid")` discipline** (agents.py lines 55-87) — every per-kind payload class uses this to reject unknown fields at parse time (V5 input validation):
```python
class ReplySentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(..., min_length=1, max_length=64)
    length_chars: int = Field(..., ge=0)
    captured_at: datetime
```

**Per-kind model structure** (agents.py lines 55-192 — one class per persistent-mode lifecycle shape) — mirror four classes: `ReplySentPayload`, `ReplyFailedPayload`, `AgentReadyPayload`, `AgentErrorPayload`. D-06 privacy discipline: NO `reply_text` / `body` field anywhere. `payload` keeps metadata only.

**Response envelope pattern** (agents.py lines 110-134 `AgentStatusResponse` with optional fields):
```python
class AgentEventsResponse(BaseModel):
    agent_id: UUID
    events: list[AgentEvent] = Field(default_factory=list)
    next_since_seq: int      # caller's follow-up cursor
    timed_out: bool = False  # True when long-poll expired empty

class AgentEvent(BaseModel):
    seq: int
    kind: str
    payload: dict  # typed-per-kind, validated at INSERT; loose on read projection
    correlation_id: str | None = None
    ts: datetime
```

---

### `api_server/src/api_server/models/errors.py` (ADD-TO)

**Analog:** `api_server/src/api_server/models/errors.py` (self-extend)

**Add two new `ErrorCode` constants** (errors.py lines 31-56 — current class):
```python
class ErrorCode:
    # ... existing codes ...
    # Phase 22b: event-stream error codes.
    CONCURRENT_POLL_LIMIT = "CONCURRENT_POLL_LIMIT"   # 429 — D-13
    EVENT_STREAM_UNAVAILABLE = "EVENT_STREAM_UNAVAILABLE"   # 503 — watcher dead
```

**Add entries to `_CODE_TO_TYPE`** (errors.py lines 58-78):
```python
_CODE_TO_TYPE = {
    # ... existing mappings ...
    ErrorCode.CONCURRENT_POLL_LIMIT: "rate_limit_error",
    ErrorCode.EVENT_STREAM_UNAVAILABLE: "infra_error",
}
```

**Shared pre-edit coordination** (RESEARCH.md §Parallelizability): Wave 2's plans 22b-03 and 22b-04 both need these codes — land the errors.py edit as a tiny shared pre-edit at the start of Wave 2 so both plans merge without conflict.

---

### `api_server/src/api_server/services/event_store.py` (store, CRUD)

**Analog:** `api_server/src/api_server/services/run_store.py`

**Module docstring + parameterized-query discipline** (run_store.py lines 1-16):
```python
"""asyncpg repository for ``agent_events`` table.

Every query uses ``$1, $2, ...`` placeholders. No string interpolation,
no f-strings with user input. Pydantic per-kind payload validators in
``models/events.py`` provide schema-level input hardening; parameterized
queries here are the defense-in-depth layer (V13).

Schema reference: ``api_server/alembic/versions/004_agent_events.py``.
"""
from __future__ import annotations
import asyncpg
from uuid import UUID
```

**One function per state transition** (run_store.py lines 244-351 — `insert_pending_agent_container` / `write_agent_container_running` / `mark_agent_container_stopped`): event_store exposes `insert_agent_event`, `insert_agent_events_batch`, `fetch_events_after_seq` — one function per durable op, same discipline.

**Advisory-lock seq allocation** (NEW — derived from spike-05; no existing analog in substrate):
```python
async def insert_agent_event(conn: asyncpg.Connection, agent_id: UUID, kind: str,
                              payload: dict, correlation_id: str | None = None) -> int:
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_id))
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM agent_events "
            "WHERE agent_container_id=$1", agent_id)
        next_seq = row["next_seq"]
        await conn.execute(
            """INSERT INTO agent_events
                 (agent_container_id, seq, kind, payload, correlation_id)
               VALUES ($1, $2, $3, $4::jsonb, $5)""",
            agent_id, next_seq, kind, json.dumps(payload), correlation_id)
    return next_seq
```

**Batched insert — advisory lock once, `executemany` underneath** (NEW — from spike-04, 12.4x speedup):
```python
async def insert_agent_events_batch(conn, agent_id, rows: list[tuple[str, dict, str | None]]) -> list[int]:
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_id))
        base = await conn.fetchval(
            "SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE agent_container_id=$1", agent_id)
        values = [(agent_id, base + i + 1, kind, json.dumps(payload), cid)
                  for i, (kind, payload, cid) in enumerate(rows)]
        await conn.executemany(
            "INSERT INTO agent_events (agent_container_id, seq, kind, payload, correlation_id) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)", values)
    return [base + i + 1 for i in range(len(rows))]
```

**Dict-returning read path** (run_store.py lines 181-220 — `fetch_run` casts UUID/NUMERIC to text/float; returns dict not Record):
```python
async def fetch_events_after_seq(conn, agent_id: UUID, since_seq: int,
                                  kinds: set[str] | None = None) -> list[dict]:
    query = (
        "SELECT seq, kind, payload, correlation_id, ts "
        "FROM agent_events WHERE agent_container_id=$1 AND seq > $2 "
    )
    params = [agent_id, since_seq]
    if kinds:
        # NEVER interpolate; use IN (SELECT unnest($3::text[])) for asyncpg array binding
        query += "AND kind = ANY($3::text[]) "
        params.append(list(kinds))
    query += "ORDER BY seq ASC"
    rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]
```

**`__all__` export discipline** (run_store.py lines 27-42) — explicit export list so routes have one import site.

---

### `api_server/src/api_server/services/watcher_service.py` (service, streaming)

**Analog:** `api_server/src/api_server/services/runner_bridge.py` (for the `asyncio.to_thread` idiom and app.state-scoped resources).

**Module docstring style** (runner_bridge.py lines 1-28 — documents every primitive):
```python
"""Per-container log-watcher service — async bridge + source dispatch.

Mirrors runner_bridge's Pattern 2 in reverse: instead of one-shot
``to_thread(run_cell)``, watchers are long-lived pump coroutines that
bridge a blocking iterator (docker-py logs, subprocess.Popen stdout,
or docker exec polls) into asyncio via ``asyncio.to_thread``.

Key primitives:
- ``app.state.log_watchers: dict[container_row_id, (Task, Event)]``
- ``app.state.event_poll_signals: dict[agent_id, asyncio.Event]`` — one per agent
- ``app.state.event_poll_locks: dict[agent_id, asyncio.Lock]`` — D-13 429 cap
- ``asyncio.Queue(maxsize=500)`` per watcher (NOT in app.state — watcher-local)

BYOK invariant: chat_id_hint is the ONLY channel-derived value the watcher
receives; it is a numeric user ID, not a secret. Bearer tokens never reach
the watcher.
"""
from __future__ import annotations
import asyncio, json, logging, re, time
from typing import Protocol, AsyncIterator
from uuid import UUID
import docker

_log = logging.getLogger("api_server.watcher")   # module-scope logger per substrate convention
BATCH_SIZE = 100
BATCH_WINDOW_MS = 100
```

**`asyncio.to_thread` bridge over blocking iterator** (runner_bridge.py lines 117-131 — the pattern):
```python
# Pattern: wrap every blocking docker-py / subprocess call in to_thread
# so a long-lived watcher does not stall the event loop.
chunk = await asyncio.to_thread(next, it, None)
```

**app.state-scoped locks + mutex** (runner_bridge.py lines 82-94 — the `_get_tag_lock` idiom):
```python
async def _get_poll_lock(app_state, agent_id: UUID) -> asyncio.Lock:
    """Return (creating if needed) the per-agent long-poll ``asyncio.Lock``.

    Pitfall 1 safe — mirrors ``runner_bridge._get_tag_lock``. Mutations to
    ``event_poll_locks`` dict happen under ``app_state.locks_mutex`` so
    concurrent setdefault-races cannot leave two coroutines holding
    different Lock objects for the same agent_id.
    """
    async with app_state.locks_mutex:
        lock = app_state.event_poll_locks.get(agent_id)
        if lock is None:
            lock = asyncio.Lock()
            app_state.event_poll_locks[agent_id] = lock
    return lock


def _get_poll_signal(app_state, agent_id: UUID) -> asyncio.Event:
    return app_state.event_poll_signals.setdefault(agent_id, asyncio.Event())
```

**Source Protocol + dispatch** (NEW — RESEARCH §Architecture Pattern 1 is authoritative shape):
```python
class EventSource(Protocol):
    async def lines(self) -> AsyncIterator[str]: ...

class DockerLogsStreamSource:
    """docker_logs_stream — hermes, picoclaw, nanobot.
    Spike 02 verdict: iterator ends cleanly on ``docker rm -f`` in <270ms;
    no Task.cancel() needed. Bridge via asyncio.to_thread(next, it, None).
    """
    def __init__(self, container_id: str, stop_event: asyncio.Event): ...

class DockerExecPollSource:
    """docker_exec_poll — nullclaw.
    Closest substrate analog: runner_bridge.execute_persistent_exec (lines 351-384)
    wraps mod.exec_in_persistent in to_thread + semaphore. The watcher's poll
    loop calls the same primitive repeatedly at ``poll_interval_s`` cadence.
    """

class FileTailInContainerSource:
    """file_tail_in_container — openclaw.
    Runs ``docker exec tail -F`` inside the container; streams stdout via
    subprocess.Popen + asyncio.to_thread(proc.stdout.readline, ...).
    Line-buffering probe (Wave 0 / assumption A3 — BusyBox tail) required.
    Session-id drift: re-resolve sessions_manifest on tail exit (Pitfall 2).
    """
```

**`_select_source` dispatch** — verbatim per RESEARCH §D-23 Dispatch:
```python
def _select_source(recipe, channel, container_id, chat_id_hint, stop_event):
    channel_spec = recipe.get("channels", {}).get(channel, {})
    fallback = channel_spec.get("event_source_fallback")
    if fallback is None:
        return DockerLogsStreamSource(container_id, stop_event)
    kind = fallback.get("kind")
    if kind == "docker_exec_poll":
        return DockerExecPollSource(container_id, fallback["spec"], chat_id_hint, stop_event)
    if kind == "file_tail_in_container":
        return FileTailInContainerSource(container_id, fallback["spec"], chat_id_hint, stop_event)
    raise ValueError(f"unknown event_source_fallback.kind: {kind!r}")
```

**Consumer batch-or-window pattern + signal set** — use RESEARCH §Code Examples Example 1 verbatim (lines 585-638). Key points:
- Queue `maxsize=500` matched tuples only
- Flush at `len(pending) >= 100` OR `(now - last_flush) * 1000 >= 100ms`
- `async with app_state.db.acquire() as conn` acquired ONLY during the batch INSERT (connection-per-scope)
- `app_state.event_poll_signals[agent_id].set()` after successful batch commit to wake pollers

**Drop coalescing on `QueueFull`** (NEW — spike-02 reproducer):
```python
try:
    queue.put_nowait((kind, payload, corr))
except asyncio.QueueFull:
    try:
        queue.get_nowait()        # drop oldest
    except asyncio.QueueEmpty:
        pass
    queue.put_nowait((kind, payload, corr))
    drops += 1
    if drops == 1 or drops % 100 == 0:
        _log.warning("watcher queue drop", extra={"agent_id": str(agent_id), "drops": drops})
```

---

### `api_server/src/api_server/routes/agent_events.py` (route, event-driven long-poll)

**Analog:** `api_server/src/api_server/routes/agent_lifecycle.py` (closest = `stop_agent` handler at lines 442-533 — auth parse, recipe lookup, short flow).

**Module docstring + 9-step flow convention** (agent_lifecycle.py lines 1-36):
```python
"""Agent event-stream long-poll endpoint (Phase 22b).

One endpoint: ``GET /v1/agents/:id/events`` — long-poll with since_seq +
kinds filter + timeout_s.

Canonical flow (short — no runner call):

    1. Parse ``Authorization: Bearer <token>`` — D-15 auth posture
    2. If Bearer == AP_SYSADMIN_TOKEN → bypass ownership; else:
       Resolve user_id = ANONYMOUS_USER_ID (Phase 19 MVP seam);
       Lookup agent_instance; 404 if missing;
       Ownership check: agent.user_id == user_id (403 if mismatch)
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
import asyncio, logging, os
from uuid import UUID
import asyncpg
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from ..constants import ANONYMOUS_USER_ID
from ..models.errors import ErrorCode, make_error_envelope
from ..services.event_store import fetch_events_after_seq
from ..services.run_store import fetch_agent_instance

router = APIRouter()
_log = logging.getLogger("api_server.agent_events")
```

**`_err` helper — copied byte-for-byte** (agent_lifecycle.py lines 87-106):
```python
def _err(status: int, code: str, message: str, *, param: str | None = None,
         category: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```

**Bearer parse + sysadmin-token bypass** (agent_lifecycle.py lines 174-189 — existing pattern) + D-15 addition:
```python
if not authorization.startswith("Bearer "):
    return _err(401, ErrorCode.UNAUTHORIZED, "Bearer token required", param="Authorization")
bearer = authorization[len("Bearer "):].strip()
if not bearer:
    return _err(401, ErrorCode.UNAUTHORIZED, "Bearer token is empty", param="Authorization")

sysadmin_token = os.environ.get("AP_SYSADMIN_TOKEN") or ""
is_sysadmin = bool(sysadmin_token) and bearer == sysadmin_token
```

**Ownership check pattern** (agent_lifecycle.py lines 192-201 — `fetch_agent_instance` + 404):
```python
pool = request.app.state.db
async with pool.acquire() as conn:
    agent = await fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)
if agent is None and not is_sysadmin:
    return _err(404, ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id} not found", param="agent_id")
```

**Long-poll flow — two DB scopes flanking the wait** (NEW — RESEARCH §Pattern 2 is authoritative):
```python
poll_lock = await _get_poll_lock(request.app.state, agent_id)
if poll_lock.locked():
    return _err(429, ErrorCode.CONCURRENT_POLL_LIMIT,
                "another long-poll is already active for this agent",
                param="agent_id")

async with poll_lock:
    # DB scope 1 — fast-path
    async with pool.acquire() as conn:
        rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds_set)
    if rows:
        return _project(rows, since_seq, timed_out=False)

    # NO DB held during wait (Pitfall 4)
    signal = _get_poll_signal(request.app.state, agent_id)
    signal.clear()
    try:
        await asyncio.wait_for(signal.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return _project([], since_seq, timed_out=True)

    # DB scope 2 — re-query after signal fires
    async with pool.acquire() as conn:
        rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds_set)
    return _project(rows, since_seq, timed_out=False)
```

**Query-param validation** (V5) — FastAPI `Query(..., ge=0)` + explicit `kinds` CSV parser with enum whitelist (RESEARCH §Threat Patterns: SQL injection via `kinds`):
```python
from fastapi import Query

VALID_KINDS = {"reply_sent", "reply_failed", "agent_ready", "agent_error"}

@router.get("/agents/{agent_id}/events")
async def get_events(
    request: Request,
    agent_id: UUID,
    since_seq: int = Query(0, ge=0),
    kinds: str | None = Query(None, max_length=256),
    timeout_s: int = Query(30, ge=1, le=60),
    authorization: str = Header(default=""),
):
    kinds_set: set[str] | None = None
    if kinds:
        parsed = {k.strip() for k in kinds.split(",") if k.strip()}
        bad = parsed - VALID_KINDS
        if bad:
            return _err(400, ErrorCode.INVALID_REQUEST,
                        f"unknown kind(s): {sorted(bad)}", param="kinds")
        kinds_set = parsed
```

---

### `api_server/src/api_server/routes/agent_lifecycle.py` (ADD-TO — /start and /stop extensions)

**Analog:** self-extend.

**`/start` extension** — append AFTER Step 8 `write_agent_container_running` success (current lines 364-419), BEFORE the `return AgentStartResponse` at line 422. RESEARCH §Code Examples Example 2 is authoritative:
```python
# --- Step 8b (NEW): spawn log-watcher task (fire-and-forget) ---
from ..services.watcher_service import run_watcher   # top-of-file in real edit
try:
    asyncio.create_task(run_watcher(
        request.app.state,
        container_row_id=container_row_id,
        container_id=container_id,
        agent_id=agent_id,
        recipe=recipe,
        channel=body.channel,
        chat_id_hint=body.channel_inputs.get("TELEGRAM_ALLOWED_USER")
                    or body.channel_inputs.get("TELEGRAM_ALLOWED_USERS"),
    ))
except Exception:
    # Never fail /start on watcher-spawn failure — events are observability,
    # not correctness. Lifespan re-attach will retry on next restart.
    _log.exception("watcher spawn failed", extra={"agent_id": str(agent_id)})
```

**`/stop` extension** — insert BEFORE the `execute_persistent_stop` call at current line 497. Pattern from RESEARCH §Code Examples Example 3 (spike-03: iterator ends cleanly on `docker rm -f` in <270ms):
```python
# --- NEW: signal watcher stop before stopping the container ---
watcher_entry = request.app.state.log_watchers.get(UUID(running["id"]))
if watcher_entry:
    task, stop_event = watcher_entry
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()       # fallback — spike-03 never triggered this path
```

**Redaction discipline** (lines 109-131 — `_redact_creds`) — already present; watcher spawn does NOT handle Bearer tokens, but document in docstring that `chat_id_hint` is the only cred-adjacent value and it's numeric (not a secret).

**Openclaw env-var-by-provider fix** (RESEARCH §Openclaw `/start` Env-Var Gap) — lands in Wave 0. At current line 248-256 replace:
```python
api_key_var = recipe.get("runtime", {}).get("process_env", {}).get("api_key")
```
with a provider-aware helper:
```python
api_key_var = _resolve_api_key_var(recipe, agent["model"])
# _resolve_api_key_var consults process_env.api_key_by_provider first
# (new field), falls back to process_env.api_key (legacy), picks by
# model prefix: "anthropic/..." → "anthropic", "openrouter/..." → "openrouter".
```

---

### `api_server/src/api_server/main.py` (ADD-TO — lifespan + app.state init)

**Analog:** self-extend.

**app.state init block** (main.py lines 63-72 — extend the existing block):
```python
# EXISTING (lines 70-72):
app.state.image_tag_locks = {}
app.state.locks_mutex = asyncio.Lock()
app.state.run_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

# NEW — Phase 22b:
app.state.log_watchers = {}          # container_row_id -> (asyncio.Task, asyncio.Event)
app.state.event_poll_signals = {}    # agent_id -> asyncio.Event (watcher .set()s, handler .clear()+.wait()s)
app.state.event_poll_locks = {}      # agent_id -> asyncio.Lock (D-13: one poll at a time per agent)
```

**Lifespan re-attach on startup** (NEW — RESEARCH §Example 4, D-11) — insert after recipes load at line 69, before `yield`:
```python
# Phase 22b: re-attach log-watchers for containers that survived an API restart.
# Events emitted between crash and re-attach are LOST (D-11); correlation_id
# prevents false-PASS in the harness because reply_sent with matching id only
# counts if ts > send_time.
async with app.state.db.acquire() as conn:
    rows = await conn.fetch(
        "SELECT id, agent_instance_id, recipe_name, container_id, channel_type "
        "FROM agent_containers WHERE container_status='running'"
    )
for row in rows:
    recipe = app.state.recipes.get(row["recipe_name"])
    if recipe is None:
        continue   # stale row; skip (a GC sweep is a separate concern)
    asyncio.create_task(run_watcher(
        app.state,
        container_row_id=row["id"],
        container_id=row["container_id"],
        agent_id=row["agent_instance_id"],
        recipe=recipe,
        channel=row["channel_type"],
        chat_id_hint=None,   # A6: degrade gracefully — watcher uses glob session match
    ))
```

**Shutdown phase — cancel all watchers with 2s budget** (NEW — RESEARCH §Plan Shape Wave 2):
```python
finally:
    # Phase 22b: signal all watcher stop_events + gather with budget
    for _task, _stop_event in list(app.state.log_watchers.values()):
        _stop_event.set()
    if app.state.log_watchers:
        tasks = [t for t, _ in app.state.log_watchers.values()]
        await asyncio.wait(tasks, timeout=2.0)
    await close_pool(app.state.db)
```

**Router mount — new events route** (main.py lines 107-123 style):
```python
from .routes import agent_events as agent_events_route
# ...
app.include_router(agent_events_route.router, prefix="/v1", tags=["agents"])
```

---

### `api_server/src/api_server/constants.py` (ADD-TO)

**Analog:** self-extend. Lines 1-19 already define `ANONYMOUS_USER_ID`. Add:

```python
# Phase 22b: sysadmin bypass for event-stream auth (D-15).
# Per-laptop / per-deploy state — mirrors AP_CHANNEL_MASTER_KEY discipline.
# NEVER committed to .env* files.
AP_SYSADMIN_TOKEN_ENV = "AP_SYSADMIN_TOKEN"   # env-var NAME, not the value

__all__ = ["ANONYMOUS_USER_ID", "AP_SYSADMIN_TOKEN_ENV"]
```

Route reads `os.environ.get(AP_SYSADMIN_TOKEN_ENV)` at handler time — NOT at import time (supports per-request env changes in tests).

---

### `test/lib/agent_harness.py` (renamed from `telegram_harness.py`)

**Analog:** `test/lib/telegram_harness.py` (existing) for the argparse + urllib skeleton; `test/smoke-api.sh` for the style guide (`_pass/_fail/_skip`, `API_BASE`, jq assertions).

**Skeleton + imports** (telegram_harness.py lines 48-58):
```python
#!/usr/bin/env python3
"""Agent test harness — two subcommands.

  send-direct-and-read: primary (Gate A). Invokes recipe.direct_interface
    (docker_exec_cli or http_chat_completions) and reads the reply.
  send-telegram-and-watch-events: secondary (Gate B). Bot->self sendMessage
    + long-poll GET /v1/agents/:id/events.

Legacy send-and-wait (getUpdates-based) DELETED per D-18.

Stdlib-only (urllib, subprocess, argparse). No requests dep."""
from __future__ import annotations
import argparse, json, subprocess, sys, time, uuid
import urllib.error, urllib.request
```

**HTTP helpers pattern** (telegram_harness.py lines 61-98 `_post` / `_get` — copy verbatim for Telegram and event-poll calls):
```python
def _post(url: str, body: dict, timeout: int = 10, headers: dict | None = None) -> dict: ...
def _get(url: str, timeout: int = 40, headers: dict | None = None) -> dict: ...
```

**Output JSON shape convention** (telegram_harness.py lines 20-26 — every subcommand emits one JSON line to stdout):
```python
# Gate A output:
{"gate": "A", "recipe": "hermes", "correlation_id": "a3f1",
 "sent_text": "...", "reply_text": "...", "wall_s": 2.1,
 "verdict": "PASS", "error": null}
# Gate B output:
{"gate": "B", "recipe": "hermes", "correlation_id": "a3f1",
 "sent_text": "...", "reply_sent_event": {"seq": 42, "correlation_id": "a3f1", ...},
 "wall_s": 3.4, "verdict": "PASS", "error": null}
```

**Exit-code convention** (telegram_harness.py lines 28-32 — copy):
```
0  round-trip PASS
1  timeout (no reply in window)
2  send failed (HTTP error, bot bad, etc.)
3  usage error (argparse)
```

**`direct_interface` dispatch (NEW — D-20/D-21):**
```python
def cmd_send_direct_and_read(args) -> int:
    # 1. GET /v1/recipes/<recipe> or load args.recipe_yaml to find direct_interface
    # 2. Dispatch on kind:
    di_kind = recipe["direct_interface"]["kind"]
    corr = uuid.uuid4().hex[:4]
    prompt = f"reply with just: ok-{args.recipe}-{corr}"
    if di_kind == "docker_exec_cli":
        argv = [a.format(prompt=prompt, model=args.model)
                for a in recipe["direct_interface"]["spec"]["argv_template"]]
        out = subprocess.run(
            ["docker", "exec", args.container_id, *argv],
            capture_output=True, text=True,
            timeout=recipe["direct_interface"]["spec"].get("timeout_s", 60),
        )
        reply = out.stdout.strip()
    elif di_kind == "http_chat_completions":
        spec = recipe["direct_interface"]["spec"]
        body = {**spec["request_template"]}
        body["messages"] = [{"role": "user", "content": prompt}]
        resp = _post(
            f"http://127.0.0.1:{spec['port']}{spec['path']}", body,
            headers={spec["auth"]["header"]: spec["auth"]["value_template"].format(api_key=args.api_key)},
            timeout=spec.get("timeout_s", 60),
        )
        reply = _jsonpath(resp, spec["response_jsonpath"])
    verdict = "PASS" if corr in (reply or "") else "FAIL"
    print(json.dumps({"gate": "A", "recipe": args.recipe, "correlation_id": corr,
                     "reply_text": reply, "verdict": verdict, ...}))
    return 0 if verdict == "PASS" else 1
```

**Gate B `send-telegram-and-watch-events` — long-poll against API** (NEW):
```python
def cmd_send_telegram_and_watch_events(args) -> int:
    corr = uuid.uuid4().hex[:4]
    text = f"ping-22b-test-{corr}"
    # 1. Bot->self sendMessage via telegram_harness existing send_message() helper
    sent = send_message(args.token, args.chat_id, text)
    if not sent.get("ok"):
        print(json.dumps({"gate": "B", "verdict": "FAIL", "error": sent.get("description")}))
        return 2
    # 2. Long-poll GET /v1/agents/<id>/events?since_seq=<N>&kinds=reply_sent&timeout_s=10
    t0 = time.time()
    url = (f"{args.api_base}/v1/agents/{args.agent_id}/events"
           f"?since_seq={args.since_seq}&kinds=reply_sent&timeout_s={args.timeout_s}")
    resp = _get(url, headers={"Authorization": f"Bearer {args.bearer}"}, timeout=args.timeout_s + 5)
    events = resp.get("events", [])
    match = next((e for e in events if (e.get("correlation_id") or "") == corr), None)
    verdict = "PASS" if match else "FAIL"
    print(json.dumps({"gate": "B", "recipe": args.recipe, "correlation_id": corr,
                     "reply_sent_event": match, "wall_s": round(time.time()-t0, 2),
                     "verdict": verdict}))
    return 0 if match else 1
```

---

### `test/e2e_channels_v0_2.sh` (REWRITE step 4/5)

**Analog:** self-extend — current step 4 (lines 160+ around `send-and-wait`) rewrites to call `send-direct-and-read`; new step 5 calls `send-telegram-and-watch-events`.

**Style pattern** (e2e_channels_v0_2.sh lines 80-100):
```bash
_pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
_fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }
_info() { printf "  \033[36mINFO\033[0m %s\n" "$1"; }
# cleanup trap is existing — keep it
```

**Step 4 rewrite (Gate A):**
```bash
# --- Step 4: Gate A — direct_interface round-trip (replaces send-and-wait) ---
GATE_A=$(python3 test/lib/agent_harness.py send-direct-and-read \
  --api-base "$API_BASE" \
  --agent-id "$AGENT_ID" \
  --recipe "$RECIPE" \
  --container-id "$ACTIVE_CONTAINER_ID" \
  --model "$MODEL" \
  --api-key "$BEARER" \
  --timeout-s 60)
VERDICT=$(jq -r '.verdict' <<<"$GATE_A")
if [[ "$VERDICT" == "PASS" ]]; then
  _pass "$RECIPE r$R Gate A direct_interface"
  PASSED=$((PASSED + 1))
else
  _fail "$RECIPE r$R Gate A: $(jq -c '.' <<<"$GATE_A")"
fi
REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"gate\":\"A\",\"verdict\":\"$VERDICT\"}")
```

**Step 5 new (Gate B — optional):**
```bash
# --- Step 5: Gate B — watch events after bot->self sendMessage (NEW) ---
if [[ "${GATE_B:-1}" == "1" ]]; then
  GATE_B_RESULT=$(python3 test/lib/agent_harness.py send-telegram-and-watch-events \
    --api-base "$API_BASE" \
    --agent-id "$AGENT_ID" \
    --bearer "$AP_SYSADMIN_TOKEN" \
    --recipe "$RECIPE" \
    --token "$TELEGRAM_BOT_TOKEN" \
    --chat-id "$TELEGRAM_CHAT_ID" \
    --timeout-s 10)
  # ... pass/fail + report line
fi
```

**MATRIX row shape — unchanged** (lines 71-77): keep the existing `recipe|provider|key_env|model|requires_pairing` format.

---

### Recipe schema extensions (5 recipes — ADD-TO)

**Analog:** `recipes/openclaw.yaml` + `recipes/nullclaw.yaml` — both already have `event_log_regex` + `event_source_fallback` blocks from spikes 01c/01e (see nullclaw.yaml lines 290-321, openclaw.yaml around 326-358).

**`direct_interface` block (NEW — D-19..D-22) — lands in recipe top-level**, not under `channels`:
```yaml
# recipes/hermes.yaml (example — per-recipe values from D-21 table)
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["hermes", "chat", "-q", "{prompt}", "-Q", "-m", "{model}", "--provider", "openrouter"]
    timeout_s: 60
    stdout_reply: true
    reply_extract_regex: "(?s)(?P<reply>.+?)(?=\\n\\s*session_id:|$)"
    exit_code_success: 0
```

**`event_log_regex` additive v0.2 — already committed in 5 recipes from spikes**. Pattern for new recipes uses the `channels.telegram.event_log_regex` sibling of `ready_log_regex` (nullclaw.yaml lines 302-307, openclaw.yaml lines 332-335):
```yaml
channels:
  telegram:
    ready_log_regex: "..."            # EXISTING — reused as agent_ready source (D-14)
    event_log_regex:                  # ADDED by spikes 01a-01e
      reply_sent: "<regex or null>"
      reply_failed: "<regex>"
      agent_error: "<regex>"
    event_source_fallback:            # OMIT for docker_logs_stream default
      kind: docker_exec_poll | file_tail_in_container
      spec: { ... }
      notes: |
        Free-form text; persisted in recipe for ops context.
```

**Per-recipe `direct_interface` mapping (D-21)** — populate in Wave 3 Plan 22b-05 per the authoritative table:

| Recipe | `direct_interface.kind` | Notes |
|--------|-------------------------|-------|
| hermes | `docker_exec_cli` | proven spike-01a |
| picoclaw | `docker_exec_cli` | spike-06 pending |
| nullclaw | `docker_exec_cli` | HTTP gateway alt |
| nanobot | `http_chat_completions` | OpenAI-compatible |
| openclaw | `http_chat_completions` | MSV pattern |

---

### Test pattern assignments (seed from spikes)

**`api_server/tests/test_events_migration.py` (analog: `api_server/tests/test_migration.py`)** — DDL existence assertions. Copy the `alembic upgrade head` fixture; assert table `agent_events`, CHECK `ck_agent_events_kind`, UNIQUE `uq_agent_events_container_seq`, composite index.

**`api_server/tests/test_events_store.py` (analog: `api_server/tests/test_run_concurrency.py`)** — session-scoped PG17 fixture, truncate-between. Covers:
- `test_insert_single_happy_path` — seq=1 on empty table
- `test_seq_concurrent` — 4 writers × 50 rows, gap-free (spike-05 port)
- `test_batch_speedup` — 100-row batch vs per-row, assert ≥5× (spike-04 port with generous floor)
- `test_no_body_leak` — inspect `_build_payload` source; assert no `reply_text`/`body` capture groups (D-06 privacy)
- `test_kind_check_constraint` — `kind='bogus'` raises `asyncpg.CheckViolationError`

**`api_server/tests/test_events_watcher_*.py` (3 files — spike-02, spike-03 reproducers)** — greenfield shape using real Docker daemon + `alpine` echo-loop container. Use `docker_client` session fixture (Wave 0 add):
- `test_events_watcher_docker_logs.py` — DockerLogsStreamSource against alpine `while true; do echo ...; done`
- `test_events_watcher_exec_poll.py` — DockerExecPollSource against a fixture that writes JSON messages to a file inside the container
- `test_events_watcher_file_tail.py` — FileTailInContainerSource + line-buffering probe
- `test_events_watcher_backpressure.py` — 20k-line flood, assert queue-drop path + WARN coalesce
- `test_events_watcher_teardown.py` — `docker rm -f` → iterator-end → watcher task done within 2s, `asyncio.all_tasks()` delta == 0

**`api_server/tests/test_events_long_poll.py` (analog: `api_server/tests/test_runs.py`)** — httpx `AsyncClient` + `ASGITransport(create_app())`. Pattern: see existing `test_runs.py` for header-based auth + jq-less JSON assertions. New cases: `since_seq` filter, `kinds` CSV, `timeout_s` empty return, 429 on concurrent poll (D-13), AP_SYSADMIN_TOKEN bypass (D-15).

**`api_server/tests/test_events_lifespan_reattach.py`** — greenfield shape. Seed an `agent_containers` row with `container_status='running'` + a real docker container, call `create_app()`, assert `app.state.log_watchers[row_id]` populated after startup.

---

## Shared Patterns

### Authentication + authorization (D-15)

**Source:** `api_server/src/api_server/routes/agent_lifecycle.py` lines 174-201 (Bearer parse + `fetch_agent_instance` + 404)

**Apply to:** `routes/agent_events.py` (NEW) — plus sysadmin bypass layered on top:

```python
if not authorization.startswith("Bearer "):
    return _err(401, ErrorCode.UNAUTHORIZED, "Bearer token required", param="Authorization")
bearer = authorization[len("Bearer "):].strip()
# D-15 addition: sysadmin-token bypass
is_sysadmin = bool(os.environ.get("AP_SYSADMIN_TOKEN")) and bearer == os.environ["AP_SYSADMIN_TOKEN"]
async with pool.acquire() as conn:
    agent = await fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)
if agent is None and not is_sysadmin:
    return _err(404, ErrorCode.AGENT_NOT_FOUND, ...)
```

### Error envelope (Stripe-shape)

**Source:** `api_server/src/api_server/models/errors.py` lines 118-141 (`make_error_envelope`)

**Apply to:** every 4xx/5xx in `routes/agent_events.py`. Reuse the `_err(status, code, message, param=..., category=...)` helper from `agent_lifecycle.py` lines 87-106 verbatim — copy into the new route file so every route owns its own local `_err` (existing convention; see `routes/runs.py::_err`).

### `_redact_creds` credential redaction

**Source:** `api_server/src/api_server/routes/agent_lifecycle.py` lines 109-131

**Apply to:** any code path in 22b that might land an exception string in the DB or response. Watcher paths: the watcher does NOT handle the Bearer token, but document in watcher_service that if `chat_id_hint` happens to be long enough (≥8 chars), redact it from any `_log.exception` that surfaces it. Route paths (`/v1/agents/:id/events`): Bearer already handled by the middleware — belt-and-braces, redact `bearer` from any `_log.exception` call in the long-poll handler.

```python
# agent_lifecycle.py lines 109-131 — copy verbatim if needed
def _redact_creds(text: str, channel_inputs: dict[str, str]) -> str:
    out = text
    for var, val in channel_inputs.items():
        if not val:
            continue
        if len(val) >= 8:
            out = out.replace(val, "<REDACTED>")
        out = out.replace(f"{var}={val}", f"{var}=<REDACTED>")
    return out
```

### asyncpg connection-per-scope (Pitfall 4)

**Source:** `api_server/src/api_server/routes/agent_lifecycle.py::start_agent` docstring lines 31-35 + 9-step flow docstring lines 10-20 + body lines 258-368 (two distinct `async with pool.acquire()` scopes flanking the long `await execute_persistent_start(...)`)

**Apply to:** every route handler + watcher helper in 22b. The long-poll handler in `routes/agent_events.py` is the critical application — two scopes flanking `asyncio.wait_for(signal.wait(), timeout_s)`. The consumer in `watcher_service.run_watcher` also applies this — acquire pool ONLY during `insert_agent_events_batch`, release before the next queue.get().

### app.state mutation — the `locks_mutex` + per-key lock pattern

**Source:** `api_server/src/api_server/services/runner_bridge.py::_get_tag_lock` lines 82-94

**Apply to:** `watcher_service._get_poll_lock` (D-13 per-agent long-poll lock) — one-to-one structural copy with `event_poll_locks` / `agent_id` in place of `image_tag_locks` / `image_tag`.

### Module-scope logger

**Source:** every substrate module — `agent_lifecycle.py` line 84 (`_log = logging.getLogger("api_server.agent_lifecycle")`), `runner_bridge.py` uses stdlib logger throughout.

**Apply to:** `watcher_service.py` → `_log = logging.getLogger("api_server.watcher")`; `routes/agent_events.py` → `_log = logging.getLogger("api_server.agent_events")`; `services/event_store.py` → logger optional (CRUD modules in substrate don't log; route layer does).

### Parameterized queries (V13)

**Source:** `api_server/src/api_server/services/run_store.py` module docstring lines 1-7 + every function body (every query uses `$1, $2, ...` placeholders)

**Apply to:** every query in `services/event_store.py`. Special case for `kinds` filter: bind as `$3::text[]` and use `kind = ANY($3::text[])` — NEVER interpolate the CSV into the query string.

### asyncio.to_thread bridge

**Source:** `runner_bridge.py` lines 122-131 (`result = await asyncio.to_thread(run_cell, ...)`)

**Apply to:** watcher_service's three source classes — every blocking docker-py or subprocess call wraps in `asyncio.to_thread`. Specifically: `DockerLogsStreamSource.lines` wraps `next(it, None)`; `DockerExecPollSource.lines` wraps `subprocess.run`; `FileTailInContainerSource.lines` wraps `proc.stdout.readline`.

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns + spike artifacts):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `services/watcher_service.py::DockerLogsStreamSource` | streaming | follow-iterator | No code in substrate today follows docker logs. Borrow: `runner_bridge.execute_persistent_status` (lines 296-347) spawns `docker inspect` + `docker logs --tail` via subprocess, but doesn't use `follow=True`. Use RESEARCH §Example 1 + spike-02 reproducer. |
| `services/watcher_service.py::FileTailInContainerSource` | streaming | tail-F subprocess | No code in substrate runs `docker exec tail -F`. Borrow: `runner_bridge.execute_persistent_exec` (lines 351-384) for the `exec_in_persistent` primitive, but the persistent-subprocess + asyncio.to_thread(readline) shape is new. Use spike-01e reproducer. |
| `services/event_store.py::advisory-lock seq allocation` | CRUD | per-row INSERT with lock | Substrate has no advisory-lock pattern today. Use spike-04 + spike-05 reproducers verbatim (RESEARCH §Pattern 3 lines 436-468). |
| `tests/test_events_lifespan_reattach.py` | test | startup-reattach | No existing test exercises lifespan with pre-seeded DB + live Docker. Greenfield shape; model after test_runs.py + test_lifecycle.py fixtures. |

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/{routes,services,models,middleware,crypto,util}/`
- `api_server/alembic/versions/`
- `api_server/tests/`
- `test/` (lib + bash harnesses)
- `recipes/*.yaml`
- `tools/run_recipe.py` (referenced, not directly analogous)

**Files scanned:** 35+ (all substrate files named in RESEARCH §Substrate Reuse Map + §Canonical References)

**Pattern extraction date:** 2026-04-18

**Key cross-cutting patterns identified:**
1. **9-step route flow** with `_err` helper and Bearer/ownership prelude — used in `agent_lifecycle.py::start_agent`, `stop_agent`, `pair_channel`; 22b's `get_events` uses a shorter 9-step (no runner call).
2. **asyncpg connection-per-scope** — every long `await` sits OUTSIDE `async with pool.acquire()`. Two scopes flanking the long-poll wait is the canonical application in 22b.
3. **app.state + locks_mutex + per-key lock** — established by `runner_bridge._get_tag_lock`; 22b mirrors for `event_poll_locks` (D-13) and `event_poll_signals` (handler↔watcher wake).
4. **asyncio.to_thread bridge over blocking SDK/subprocess calls** — established by `runner_bridge.execute_*`; 22b extends to long-lived pump coroutines in `watcher_service`.
5. **Pydantic `ConfigDict(extra="forbid")` + per-kind models** — established by `models/agents.py`; 22b mirrors for per-kind event payloads (`ReplySentPayload`, etc.), enforcing D-06 metadata-only.
6. **Stripe-shape error envelopes + shared `ErrorCode` constants** — established by `models/errors.py`; 22b adds `CONCURRENT_POLL_LIMIT` (429) and `EVENT_STREAM_UNAVAILABLE` (503) to the shared map.
7. **Alembic migration style (BIGSERIAL/UUID + CHECK + partial/composite indexes + CASCADE FK)** — established by `003_agent_containers.py`; 22b's `004_agent_events.py` follows the same idiom.
8. **Parameterized queries throughout (V13 defense)** — established by `run_store.py` module docstring; 22b enforces for `event_store.py` including the `kinds` filter via `ANY($3::text[])`.
9. **Harness style: stdlib-only, argparse subcommands, JSON-per-line stdout, exit-code 0/1/2/3** — established by `test/lib/telegram_harness.py`; 22b's `agent_harness.py` keeps the same skeleton, swaps subcommands.
10. **Recipe additive-field discipline** — v0.2 fields (`event_log_regex`, `event_source_fallback`, `direct_interface`) land without breaking v0.1 loaders; 5 recipes already have spike-derived `event_log_regex` and `event_source_fallback` committed.

**Ready for planning:** Planner can reference analog file + line ranges directly in PLAN.md action blocks.
