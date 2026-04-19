# Phase 22b: agent-event-stream — Research

**Researched:** 2026-04-18
**Domain:** Real-time log observation + long-poll event stream on top of Postgres + asyncio + Docker SDK; per-recipe multi-source watcher; automatable SC-03 gate via `direct_interface`.
**Confidence:** HIGH (all 10 spikes executed, 8 PASS + 2 PASS_WITH_FLAG, every mechanism empirically validated against real infra)

## Summary

22b is the smallest phase the project has taken in a while that is also fully de-risked by spikes. The CONTEXT.md is dense (22 locked decisions, D-01..D-22) but every decision has a corresponding spike artifact under `22b-SPIKES/`. The job of this research is NOT to explore alternatives — those are locked — but to translate each decision into concrete substrate files the planner can turn into tasks, and to surface the two gaps the spikes uncovered that CONTEXT.md has not absorbed: **D-23 (multi-source watcher)** and **openclaw `/start` env-var mapping**.

The substrate is mature. `runner_bridge.execute_persistent_*` shows exactly how to bridge blocking Docker operations into asyncio. `run_store.insert_pending_agent_container` + `write_agent_container_running` shows the two-phase write idiom for a new `agent_events` table. `agent_lifecycle.start_agent` gives us the extension points for spawning / cancelling watcher tasks. The 5 recipes already carry populated `event_log_regex` + `event_source_fallback` + `direct_interface` markup from spikes 01a-01e — the planner's recipe-side work is mostly formalizing what the spikes already wrote by hand.

**Primary recommendation:** Plan as **6 plans across 4 waves**. Wave 0 (prep) adds the `docker` package + unblocks openclaw `/start`; Wave 1 is the migration + watcher service skeleton in parallel; Wave 2 wires `/start` + `/stop` + lifespan + long-poll endpoint in parallel; Wave 3 rewrites the harness and runs the SC-03 gates A+B. See §Plan Shape Recommendation.

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-22)

**Ingest & Parsing:**
- D-01 — Docker logs scrape as primary ingest (REVISED by spikes 01c/01e — see D-23 below).
- D-02 — Docker SDK `logs(follow=True, stream=True)` bridged via `asyncio.to_thread`; add `docker` package to `api_server/pyproject.toml`.
- D-03 — Every log line through recipe's `event_log_regex` dict; unmatched lines discarded immediately.
- D-04 — `event_log_regex` lives under `channels.telegram.event_log_regex.{reply_sent, reply_failed, agent_error}`. `agent_ready` reuses `persistent.spec.ready_log_regex` (D-14).

**Event Schema & Privacy:**
- D-05 — Fixed 4 kinds: `reply_sent`, `reply_failed`, `agent_ready`, `agent_error`. CHECK constraint enforces.
- D-06 — **Metadata-only payload**. Reply text NEVER stored. `reply_sent` payload = `{chat_id, length_chars, captured_at}`. BYOK discipline.
- D-07 — `correlation_id` = send-side UUID embedded in outbound text; extracted from `reply_sent` log line via named capture group. Fallback: timestamp-window match flagged per recipe.
- D-08 — Typed-per-kind Pydantic models in `api_server/src/api_server/models/events.py`; validated on INSERT and on API response projection.

**Delivery & Lifecycle:**
- D-09 — **Long-poll** at `GET /v1/agents/:id/events?since_seq=N&kinds=...&timeout_s=30`. Server holds on `asyncio.Event` per-agent in `app.state.event_poll_signals[agent_id]`. No SSE/WebSocket.
- D-10 — Watcher task registry: `app.state.log_watchers: dict[container_row_id, asyncio.Task]`. Spawned in `/start` after `write_agent_container_running`; cancelled in `/stop` before `execute_persistent_stop`.
- D-11 — Lifespan re-attaches watchers for `container_status='running'` rows on startup. Events emitted during API crash are LOST (documented acceptable gap).
- D-12 — Per-watcher `asyncio.Queue(maxsize=500)` with drop-oldest on full. Batched INSERT: 100 rows/commit OR 100ms window (whichever first). Matched-line rate bounds queue pressure.
- D-13 — One long-poll per `(caller, agent_id)` via `asyncio.Lock`; second caller gets `429 CONCURRENT_POLL_LIMIT`.

**Readiness, Auth, Seq, Retention:**
- D-14 — Watcher matches `persistent.spec.ready_log_regex` to emit `agent_ready`. `/start` handler's synchronous probe stays as-is (HTTP response only, not a durable event).
- D-15 — Auth: Bearer + ownership (all users map to `ANONYMOUS_USER_ID` today) OR `AP_SYSADMIN_TOKEN` env-var bypass. Env-var discipline mirrors `AP_CHANNEL_MASTER_KEY`.
- D-16 — **REVISED by spike 05**: `seq` allocation = `pg_advisory_xact_lock(hashtext($1::text))` + `SELECT COALESCE(MAX(seq),0)+1 FROM agent_events WHERE agent_container_id=$1` + INSERT. `UNIQUE (agent_container_id, seq)` backstop. `FOR UPDATE` is NOT USED (Postgres rejects `FOR UPDATE` with `MAX()` aggregate).
- D-17 — `ON DELETE CASCADE` from `agent_containers`; no TTL job in 22b ship.

**Direct Interface (D-19..D-22) — the SC-03 Gate A primary path:**
- D-19 — Every recipe declares `direct_interface: {kind, spec}` as additive v0.2 field.
- D-20 — Two kinds locked: `docker_exec_cli` (argv_template + reply_extract_regex + timeout_s) and `http_chat_completions` (port + path + auth + request_template + response_jsonpath).
- D-21 — Per-recipe mapping: hermes/picoclaw/nullclaw → `docker_exec_cli`; nanobot/openclaw → `http_chat_completions`.
- D-22 — Correlation is trivial: harness embeds UUID in `{prompt}`, parses reply from the declared surface, asserts UUID appears.

**Harness:**
- D-18 / D-18a — Two subcommands. Primary `send-direct-and-read` (Gate A, 15/15 PASS); secondary `send-telegram-and-watch-events` (Gate B, 5/5 PASS). `mtproto-send-and-read` deferred (Gate C manual). Legacy `send-and-wait` (getUpdates) deleted.

### Claude's Discretion (per CONTEXT.md)

- Exact retry/backoff tuning when `docker logs(follow=True)` iterator raises transient errors.
- `pydantic.model_validator` vs explicit `__post_init__` for per-kind payload validation.
- Naming of the `agent_events(agent_container_id, seq)` partial index.
- Lifespan re-attach behavior when `container_id` no longer exists in Docker (mark stopped / emit `agent_error` / skip).

### Deferred Ideas (OUT OF SCOPE)

- Rich kinds (`llm_call`, `token_usage`, `pair_code_issued`, `webhook_inbound`).
- Cross-channel (`channels.discord.event_log_regex`, `slack`, `webhook`).
- Agent-side HTTP emit (`POST /internal/events` from inside container).
- Frontend event viewer panel.
- TTL/purge job.
- **MTProto user-impersonation harness** (Gate C automation).
- WebSocket/SSE live-feed.
- Multi-tenant event-specific rate limits.

## Phase Requirements

22b has no REQ-IDs mapped. Its exit gate is SC-03 from Phase 22:

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-03-Gate-A | 15/15 `direct_interface` round-trips across 5 recipes × 3 rounds via `send-direct-and-read` harness subcommand | §D-19..D-22 locked; spikes 01a + 06 proved argv/URL surfaces for all 5 recipes |
| SC-03-Gate-B | 5/5 `reply_sent` events recorded after bot→self `sendMessage` probe via `send-telegram-and-watch-events` | §D-23 multi-source watcher; spikes 01a..01e wrote regexes and fallback configs in 5 recipe YAMLs |
| SC-03-Gate-C | Manual user-in-the-loop Telegram round-trip, 1/recipe, once per release | Release checklist, not per-commit; out of 22b CI scope |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Container stdout observation | API / Backend (log-watcher service) | — | Docker daemon is on the API host; ingest lives in the same process that owns the lifecycle. |
| Event row persistence | Database / Storage (Postgres 17 `agent_events` table) | — | Durable audit record; survives API restart; foundation for Gate B verification and future frontend |
| Long-poll delivery | API / Backend (FastAPI handler + `asyncio.Event` signal) | — | Server-side wait-and-signal; client is dumb (curl) |
| Watcher task lifecycle | API / Backend (lifespan + `/start` + `/stop` + `app.state.log_watchers`) | — | Extends existing `runner_bridge` pattern; same process that owns `app.state.image_tag_locks` |
| Direct-interface invocation (Gate A) | Test harness (Python CLI) | API (must expose `container_id` via `/status` — already done) | Harness runs `docker exec` or HTTP POST locally; no API round-trip needed for Gate A |
| Recipe-level observation config | Recipe YAML (`channels.telegram.event_log_regex` + `event_source_fallback` + `direct_interface`) | API recipe loader | Authorial ground truth; v0.2 additive; v0.1 loaders already ignore unknown keys |
| Log parsing (regex dispatch) | API / Backend (per-watcher coroutine) | — | Intelligence in the server per Golden Rule 2 |

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.0 | HTTP framework | Already the API foundation (Phase 19) `[VERIFIED: api_server/pyproject.toml]` |
| asyncpg | >=0.31.0,<0.32 | Postgres driver | Already used throughout `run_store.py`; connection-per-scope pattern locked `[VERIFIED: substrate]` |
| Pydantic | >=2.11 | Request/response models | Already used in `models/agents.py`, `models/errors.py` `[VERIFIED: substrate]` |
| asgi-correlation-id | >=4.3.4 | Request-scoped IDs | Already mounted as `CorrelationIdMiddleware`; orthogonal to event `correlation_id` `[VERIFIED: substrate]` |
| Alembic | >=1.18.4,<1.19 | Schema migrations | 003_agent_containers.py is the template for 004 `[VERIFIED: substrate]` |
| testcontainers[postgres] | >=4.14.2 | Real-Postgres tests | Session-scoped PG 17 container in `conftest.py`; Golden Rule 1 (no mocks) compliant `[VERIFIED: conftest.py]` |

### New dependencies to add

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| docker (docker-py) | >=7.0,<8 | Docker Engine SDK | Spike 02 validated `APIClient().logs(stream=True, follow=True)` + `asyncio.to_thread(next, it, None)` pattern; no FD/RSS leaks, no priority inversion `[VERIFIED: spike-02]`. **Install in `api_server/pyproject.toml` [project.dependencies].** |

**Version verification:** Run `pip index versions docker` at plan time to confirm current; 7.1.0 is the stable line as of early 2026 `[ASSUMED]` — planner verifies. Note: the MSV stack uses Go's `moby/moby/client`; in Python-land, `docker-py` is the canonical binding (`docker.APIClient` for low-level streaming). Do not use `aiodocker` — spike 02 empirically validated the `asyncio.to_thread(next, it, None)` bridge against `docker.APIClient` with zero FD leak; switching to a separate async client buys nothing and adds a dependency.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| docker-py + `asyncio.to_thread` | `aiodocker` | Spike 02 already proved the to_thread bridge works; aiodocker adds a dep and a different API surface for no measurable benefit `[VERIFIED: spike-02]` |
| Long-poll | SSE / WebSocket | D-09 locked on long-poll; SSE/WS deferred. Response schema is stable enough that `useEventStream(agentId)` hook can consume unchanged later `[CITED: CONTEXT.md §specifics]` |
| Single source (docker logs) | Multi-source (docker_logs_stream / docker_exec_poll / file_tail_in_container) | Spikes 01c + 01e proved multi-source is REQUIRED (40% of catalog) — not optional `[VERIFIED: spike-01c, spike-01e]` |
| `FOR UPDATE` locking for seq | `pg_advisory_xact_lock(hashtext($1))` | Postgres rejects `FOR UPDATE` + aggregate (`FeatureNotSupportedError`); advisory lock is correct AND faster `[VERIFIED: spike-04, spike-05]` |

**Installation:**
```bash
# In api_server/pyproject.toml [project.dependencies], add:
#   "docker>=7.0,<8",
# Then:
cd api_server && pip install -e '.[dev]'
```

## Architecture Patterns

### System Architecture Diagram

```
                ┌────────────────────────────────────────────────────────────────┐
                │                         API server process                     │
                │                                                                │
 /start  ──────►│ agent_lifecycle.start_agent ──► execute_persistent_start       │
                │           │                                                    │
                │           ▼                                                    │
                │  write_agent_container_running (DB scope 2)                    │
                │           │                                                    │
                │           ▼                                                    │
                │  ┌── watcher_service.spawn(container_row_id, recipe) ──┐       │
                │  │                                                     │       │
                │  │  app.state.log_watchers[cid] = asyncio.Task         │       │
                │  │                                                     │       │
                │  │  Source dispatch (NEW — D-23):                      │       │
                │  │   - docker_logs_stream   (hermes/picoclaw/nanobot)  │       │
                │  │   - docker_exec_poll     (nullclaw)                 │       │
                │  │   - file_tail_in_container (openclaw)               │       │
                │  └─────────────┬───────────────────────────────────────┘       │
                │                │                                               │
                │                ▼  (raw line / polled snapshot / file line)     │
                │      matcher(recipe.event_log_regex.*)                         │
                │                │                                               │
                │                ▼ (matched match, otherwise drop)               │
                │      asyncio.Queue(maxsize=500)                                │
                │                │                                               │
                │                ▼                                               │
                │      batcher (100 rows OR 100ms)  ──► asyncpg pool.acquire()   │
                │                                            │                   │
                │                                            ▼                   │
                │                                    advisory_xact_lock +        │
                │                                    MAX(seq)+1 + INSERT         │
                │                                            │                   │
                │                                            ▼                   │
                │                                    app.state.event_poll_signals│
                │                                            [agent_id].set()    │
                │                                                                │
 GET /v1/agents │                                                                │
   /:id/events  │                                                                │
   ?since_seq= ─┼──► long-poll handler: acquire event_poll_locks[agent_id]       │
                │         ├─ SELECT rows WHERE seq > since_seq                   │
                │         ├─ if none: await asyncio.wait_for(signal.wait(), T)   │
                │         │          re-query, release lock, return              │
                │         └─ return rows projected as typed-per-kind payloads    │
                │                                                                │
 /stop   ──────►│ agent_lifecycle.stop_agent                                     │
                │    ├── cancel-or-await app.state.log_watchers[cid] (2s budget) │
                │    └── execute_persistent_stop (iterator ends cleanly)         │
                │                                                                │
 lifespan ─────►│ startup: for each running row, watcher_service.spawn(...)      │
                │ shutdown: gather(*watcher_tasks, timeout=2s)                   │
                └────────────────────────────────────────────────────────────────┘
                                            │
                          ┌─────────────────┴──────────────────┐
                          ▼                                    ▼
                    ┌───────────┐                       ┌────────────┐
                    │ Postgres  │                       │   Docker   │
                    │agent_events│                      │   daemon   │
                    │+agent_contai│                     │ (unix sock)│
                    │   ners    │                       │            │
                    └───────────┘                       └────────────┘
```

### Recommended project structure

```
api_server/src/api_server/
├── models/
│   └── events.py               # NEW — Pydantic per-kind payloads + request/response models
├── services/
│   ├── event_store.py          # NEW — CRUD: insert_agent_event, fetch_events_after_seq
│   └── watcher_service.py      # NEW — multi-source watcher (D-23); task registry helpers
├── routes/
│   └── agent_events.py         # NEW — GET /v1/agents/:id/events long-poll handler
├── routes/
│   └── agent_lifecycle.py      # EXTEND — /start spawns, /stop cancels
├── main.py                     # EXTEND — lifespan re-attach + shutdown; app.state init
└── constants.py                # EXTEND — add AP_SYSADMIN_TOKEN read, kind enum

api_server/alembic/versions/
└── 004_agent_events.py         # NEW — BIGSERIAL, JSONB, UNIQUE(agent_container_id,seq), CASCADE

api_server/tests/
├── test_event_store.py         # NEW — seq allocation, advisory-lock race (spike 05 port)
├── test_watcher_source_docker_logs.py  # NEW — testcontainers alpine sidecar, log regex match
├── test_watcher_source_exec_poll.py    # NEW — nullclaw-style poll-and-diff
├── test_watcher_source_file_tail.py    # NEW — openclaw-style JSONL tail in container
├── test_agent_events_endpoint.py       # NEW — long-poll timeout, since_seq, 429 concurrent
└── test_watcher_lifecycle.py   # NEW — spawn-on-start, cancel-on-stop, reattach-on-lifespan

test/
├── lib/
│   └── agent_harness.py        # RENAME from telegram_harness.py — two subcommands
├── e2e_channels_v0_2.sh        # REWRITE Step 4-5 — Gate A primary, Gate B secondary
└── smoke-api.sh                # style reference, unchanged

recipes/
├── hermes.yaml                 # add direct_interface block (spike 01a/06 argv)
├── picoclaw.yaml               # add direct_interface block (spike 06)
├── nullclaw.yaml               # add direct_interface (spike 06) — event_source_fallback already in
├── nanobot.yaml                # add direct_interface (spike 06)
└── openclaw.yaml               # add direct_interface (spike 06) — event_source_fallback already in
```

### Pattern 1: Multi-source watcher via Protocol (D-23) — **NEW**

**What:** A single `Watcher` coroutine dispatches to one of three `EventSource` implementations based on `recipe.channels.<channel>.event_source_fallback.kind`. Default (no fallback declared) = `docker_logs_stream`.

**When to use:** Every running `agent_container`. The recipe declares the source kind; the watcher service instantiates the right implementation at `spawn()` time.

**Source interface (Python Protocol, duck-typed):**

```python
# services/watcher_service.py — Source: CONTEXT.md D-23 proposed + spike 01c/01e evidence
from typing import Protocol, AsyncIterator

class EventSource(Protocol):
    """Abstract source of raw event lines for one container.

    Every concrete source yields raw lines (bytes → str) that the watcher's
    matcher runs through the recipe's event_log_regex dict. The source
    owns its own teardown (iterator-end OR poll-loop-break) — the watcher
    never Task.cancel()s the source; it signals via stop_event.
    """
    async def lines(self) -> AsyncIterator[str]:
        """Yield raw lines until the container ends or stop_event is set."""


class DockerLogsStreamSource:
    """Source kind: docker_logs_stream (hermes, picoclaw, nanobot).

    Uses docker.APIClient().logs(stream=True, follow=True) bridged via
    asyncio.to_thread(next, it, None). Spike 02 verdict: iterator ends
    cleanly on docker rm -f in <270ms; no Task.cancel() needed.
    """
    def __init__(self, container_id: str, stop_event: asyncio.Event):
        self.container_id = container_id
        self.stop_event = stop_event

    async def lines(self):
        client = docker.APIClient()
        it = client.logs(
            container=self.container_id,
            stream=True, follow=True, stdout=True, stderr=True,
            tail=0,                # do NOT re-read historical buffer
        )
        while not self.stop_event.is_set():
            chunk = await asyncio.to_thread(next, it, None)
            if chunk is None:
                break                       # iterator ended (container reaped)
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                yield line


class DockerExecPollSource:
    """Source kind: docker_exec_poll (nullclaw).

    Periodically runs the recipe-declared argv inside the container via
    docker exec; diffs the result against the previous snapshot; yields
    synthetic lines for new entries. session_id_template is substituted
    at spawn time from chat_id (derived from channel_inputs).

    Poll interval default 500ms (D-23 Claude's discretion per spike 01c).
    """
    def __init__(self, container_id: str, argv_template: list[str],
                 session_id: str, poll_interval_s: float = 0.5,
                 stop_event: asyncio.Event | None = None):
        ...

    async def lines(self):
        prev_messages: list[dict] = []
        while not self.stop_event.is_set():
            out = await asyncio.to_thread(subprocess.run,
                ["docker", "exec", self.container_id, *self.argv],
                capture_output=True, text=True, timeout=5, check=False)
            current = json.loads(out.stdout).get("messages", [])
            for msg in current[len(prev_messages):]:
                yield json.dumps(msg)       # synthetic "line" — matcher parses as JSON-aware regex
            prev_messages = current
            await asyncio.sleep(self.poll_interval_s)


class FileTailInContainerSource:
    """Source kind: file_tail_in_container (openclaw).

    docker exec <cid> sh -c 'cat sessions.json | jq -r .sessionId' to resolve
    the current session_id at attach time; then
    docker exec <cid> tail -n0 -F /path/to/<session_id>.jsonl
    streamed via asyncio.to_thread on the Popen stdout.

    Session-id drift: re-resolve when file disappears or tail exits.
    Spike 01e observed the JSONL is authoritative (reply body is in the
    assistant message's content[].text); matcher is JSON-aware.
    """
    def __init__(self, container_id: str, sessions_manifest: str,
                 session_log_template: str, chat_id: str,
                 stop_event: asyncio.Event):
        ...

    async def lines(self):
        # 1. docker exec <cid> cat <sessions_manifest> → resolve session_id by origin.from
        # 2. docker exec <cid> tail -n0 -F <session_log_template.format(session_id=...)>
        # 3. stream stdout via asyncio.to_thread(proc.stdout.readline, ...)
        # 4. yield each raw line; matcher does json.loads + role-based extract
        ...
```

**Example recipe declaration (authoritative shape, from spike 01c and 01e):**

```yaml
# recipes/nullclaw.yaml — already committed, spike 01c
channels:
  telegram:
    event_log_regex:
      reply_sent: null                   # source=docker_logs_stream insufficient
      inbound_message: null
      agent_error: "ERROR|FATAL|panic"   # still usable from docker stdout
    event_source_fallback:
      kind: docker_exec_poll
      spec:
        argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]
        session_id_template: "agent:main:telegram:direct:{chat_id}"
        # optional:
        tail_file: "/nullclaw-data/llm_token_usage.jsonl"
```

```yaml
# recipes/openclaw.yaml — already committed, spike 01e
channels:
  telegram:
    event_log_regex:
      reply_sent: null
      inbound_message: null
      agent_error: '"logLevelName":"(?:ERROR|FATAL)"'
    event_source_fallback:
      kind: file_tail_in_container
      spec:
        sessions_manifest: /home/node/.openclaw/agents/main/sessions/sessions.json
        session_log_template: "/home/node/.openclaw/agents/main/sessions/{session_id}.jsonl"
```

**Per-recipe source mapping (from spikes 01a..01e):**

| Recipe | Source kind | Rationale (spike) |
|--------|-------------|-------------------|
| hermes | `docker_logs_stream` | 3-line canonical sequence in stdout; reply_sent regex fires on sendMessage line `[VERIFIED: spike-01a]` |
| picoclaw | `docker_logs_stream` | Dense eventbus log + bonus `response_text` with full reply body `[VERIFIED: spike-01b]` |
| nullclaw | `docker_exec_poll` | stdout barren (13 lines total); `nullclaw history show --json` is authoritative `[VERIFIED: spike-01c]` |
| nanobot | `docker_logs_stream` | ISO-timestamped structured logs; reply text in `Response to` line `[VERIFIED: spike-01d]` |
| openclaw | `file_tail_in_container` | docker stdout + file log both barren; session JSONL is authoritative (reply body at `message.content[].text`) `[VERIFIED: spike-01e]` |

### Pattern 2: asyncpg connection-per-scope across long awaits (Pitfall 4)

**What:** Every DB interaction opens its own `async with pool.acquire() as conn:` scope. Long awaits (`asyncio.Event.wait`, `to_thread(run_cell_persistent)`) MUST sit OUTSIDE any acquired connection.

**When to use:** EVERY route handler and watcher helper in 22b. The long-poll handler is the highest-risk place — easy to hold a connection across the 30s wait.

**Example (long-poll handler, authoritative shape):**

```python
# routes/agent_events.py — Source: agent_lifecycle.py step-flow + CONTEXT.md D-09
@router.get("/agents/{agent_id}/events")
async def get_events(request: Request, agent_id: UUID, since_seq: int = 0,
                      kinds: str | None = None, timeout_s: int = 30,
                      authorization: str = Header(default="")):
    # ... auth + ownership (D-15) ...

    # Acquire the per-agent long-poll lock (D-13).
    poll_lock = _get_poll_lock(request.app.state, agent_id)
    if poll_lock.locked():
        return _err(429, ErrorCode.CONCURRENT_POLL_LIMIT, "...")
    async with poll_lock:
        # DB scope 1 — fast-path: any existing rows beyond since_seq?
        async with request.app.state.db.acquire() as conn:
            rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds)
        if rows:
            return _project(rows)

        # NO DB held during wait (Pitfall 4).
        signal = _get_poll_signal(request.app.state, agent_id)
        signal.clear()       # caller acknowledges "nothing before now"
        try:
            await asyncio.wait_for(signal.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return _project([])        # 200 with empty events list

        # DB scope 2 — re-query once signal fires.
        async with request.app.state.db.acquire() as conn:
            rows = await fetch_events_after_seq(conn, agent_id, since_seq, kinds)
        return _project(rows)
```

### Pattern 3: Advisory-lock seq allocation (spike 05)

**What:** Per-agent `pg_advisory_xact_lock(hashtext($1::text))` serializes concurrent INSERTers on the same `agent_container_id`; `MAX(seq)+1` lookup is inside the locked transaction; `UNIQUE(agent_container_id, seq)` is the backstop.

**When to use:** Every `INSERT INTO agent_events`. Per-row and batched-100 paths both wrap in the same lock.

**Example (authoritative from spike 05):**

```python
# services/event_store.py — Source: spike-05-seq-ordering.md reproducer
async def insert_agent_event(conn: asyncpg.Connection, agent_id: UUID, kind: str,
                             payload: dict, correlation_id: str | None = None) -> int:
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_id))
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM agent_events WHERE agent_container_id=$1",
            agent_id)
        next_seq = row["next_seq"]
        await conn.execute(
            """INSERT INTO agent_events
                 (agent_container_id, seq, kind, payload, correlation_id)
               VALUES ($1, $2, $3, $4::jsonb, $5)""",
            agent_id, next_seq, kind, json.dumps(payload), correlation_id)
    return next_seq


async def insert_agent_events_batch(conn: asyncpg.Connection, agent_id: UUID,
                                     rows: list[tuple[str, dict, str | None]]) -> list[int]:
    """Spike 04 proved 12.4× speedup — 100 rows/txn, advisory lock ONCE."""
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_id))
        base = await conn.fetchval(
            "SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE agent_container_id=$1",
            agent_id)
        values = [(agent_id, base + i + 1, kind, json.dumps(payload), cid)
                  for i, (kind, payload, cid) in enumerate(rows)]
        await conn.executemany(
            """INSERT INTO agent_events
                 (agent_container_id, seq, kind, payload, correlation_id)
               VALUES ($1, $2, $3, $4::jsonb, $5)""",
            values)
    return [base + i + 1 for i in range(len(rows))]
```

### Anti-patterns to avoid

- **Holding a pool connection across `asyncio.wait_for(signal.wait(), ...)`** — Pitfall 4. Guaranteed pool exhaustion under load.
- **Calling `Task.cancel()` on the watcher before `docker stop`** — spike 03 proved the iterator ends cleanly in <270ms on `docker rm -f`. Order: signal via stop_event → execute_persistent_stop → `await watcher_task` with 2s timeout. Cancellation is only the fallback when the iterator hangs (hasn't been observed).
- **`FOR UPDATE` in the seq lookup** — Postgres rejects `FOR UPDATE` with aggregate (`FeatureNotSupportedError`). Use `pg_advisory_xact_lock(hashtext($1::text))`.
- **Per-drop WARN log in the matcher** — spike 02 recorded 17,470 drops in 8s under flood. Coalesce to first WARN + once-per-100 or once-per-1s.
- **Hard-coding `docker logs -f` as the sole source** — 40% of catalog (nullclaw, openclaw) needs fallback sources. See D-23.
- **Querying `fetch_running_container_for_agent` inside the long-poll wait** — keep DB scope 1 fast (since_seq check), wait OUTSIDE any acquire, then DB scope 2 for re-query.
- **Storing reply body text in `payload`** — D-06. Metadata only. `reply_sent` = `{chat_id, length_chars, captured_at}`. Even though picoclaw/nanobot/openclaw spikes captured full reply text, the watcher MUST discard it before INSERT.
- **Opening a second `getUpdates` consumer for Gate B** — that's exactly the SC-03 design flaw 22b is built to replace. Gate B uses bot→self `sendMessage` + event-stream poll.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async Docker SDK | Custom raw-HTTP client against docker unix socket | `docker-py` (`docker.APIClient`) bridged via `asyncio.to_thread` | Spike 02 validated FD/RSS stability; docker-py handles API version negotiation; raw HTTP reinvents connection reuse |
| Event signal fan-out | One `asyncio.Queue` per consumer with broadcast | One `asyncio.Event` per agent in `app.state.event_poll_signals`; watcher `.set()`s, handler `.clear()`s then `.wait()`s | Pattern used by FastAPI pubsub examples; simpler; no queue sizing questions |
| Seq allocation | Custom atomic counter in Redis or app-state | Postgres `pg_advisory_xact_lock` + `MAX(seq)+1` | Spike 05 empirically validated 4-way concurrent: 0 deadlocks, 0 UVs, 130ms for 200 serialized writes. Redis adds infra; app-state doesn't survive restart |
| Batched INSERT | Loop of per-row INSERTs | `conn.executemany()` with 100-row batches | Spike 04: 12.4× speedup (2,076/s → 25,722/s). asyncpg server-side prepared-statement reuse |
| Long-poll lifetime guard | Custom per-request timeout + cancel | `asyncio.wait_for(signal.wait(), timeout_s)` | Single stdlib primitive; auto-cancels the inner wait on timeout; no leak |
| Multi-source dispatch | `if kind == "...": elif ...` tree | `Protocol`-typed `EventSource` classes in `watcher_service.py` | Each concrete source is ~40-80 lines; Protocol keeps `spawn()` generic; easy to add a 4th kind post-MVP |
| JSONL parser for openclaw | Ad-hoc string parsing | `json.loads(line)` per line + role-based extract | openclaw's session JSONL is well-formed; one JSON per line; spike 01e proved shape |
| Telegram-reply verification | getUpdates polling | bot→self `sendMessage` + Gate B `reply_sent` event check | getUpdates single-consumer; that's the flaw 22b replaces |

**Key insight:** Every mechanism in 22b has either a stdlib / existing-dep implementation OR a spike-validated pattern. The only NEW dependency is `docker-py`. Everything else composes primitives already in the substrate.

## Runtime State Inventory

> Not a rename/refactor phase; skipping. 22b is additive (migration 004, new service, new route, new recipe fields).

## Common Pitfalls

### Pitfall 1: asyncpg connection held across long await (Pitfall 4 of existing substrate)

**What goes wrong:** Long-poll handler holds a pool connection for 30s; 10 concurrent pollers exhaust the default 10-connection pool; new requests block or timeout.

**Why it happens:** Natural Python pattern — `async with pool.acquire() as conn: ... await signal.wait()`.

**How to avoid:** Two separate `async with pool.acquire()` scopes in the long-poll handler — scope 1 for the fast-path check, scope 2 after the signal fires. Document explicitly in the handler docstring (mirror `agent_lifecycle.py::start_agent`'s 9-step doc).

**Warning signs:** Pool-acquire timeouts under load; event-handler 503s during high concurrent-poll periods.

### Pitfall 2: Openclaw session-id drift mid-watcher

**What goes wrong:** `file_tail_in_container` tails a specific `<session_id>.jsonl`; if the user creates a new Telegram chat, openclaw may create a new session_id and our tail is now pointing at a dead file. Reply events silently lost.

**Why it happens:** openclaw session-id is per-chat-origin (`sessions.json[.agent:main:main].origin.from = "telegram:<chat_id>"`).

**How to avoid:** Watcher re-reads `sessions_manifest` on `tail` exit or on a periodic interval (30s). New session_ids spawn sub-tail subprocesses. OR (simpler): watcher reads the whole sessions directory with `docker exec ls -1` and tails every `*.jsonl` — dead-file filter by stat time.

**Warning signs:** Spike 01e caught two sessions created for two different Telegram DMs; planner must probe what happens after stop-and-restart.

### Pitfall 3: nullclaw polling interval vs LLM turn timing

**What goes wrong:** 500ms poll is finer-grained than LLM turn time (~2-4s), but nullclaw's `history show --json` only reflects assistant messages AFTER the agent's turn_end commits to memory. Under heavy LLM latency, a reply_sent event may be observed 3-5s late in the event stream.

**Why it happens:** docker_exec_poll is inherently lagging compared to a docker_logs_stream source.

**How to avoid:** Document the latency gap in the recipe's `event_source_fallback.notes`. The `captured_at` field in the event payload reflects WATCHER-observe time, not ACTUAL-send time — harness correlation uses `correlation_id` not timestamps. Gate B timeout budget 10s (already noted in D-18) absorbs this.

**Warning signs:** Intermittent Gate B failures on nullclaw with "reply sent but not observed in window" — bump `--timeout-s` for the nullclaw row in `e2e_channels_v0_2.sh`.

### Pitfall 4: CHECK constraint rejects unknown kind before Pydantic validates

**What goes wrong:** Watcher matches a regex that happens to also match a typo'd kind (e.g. `reply_snt`); the row hits the `CHECK (kind IN (...))` constraint; asyncpg raises; the whole batch rolls back; 99 good rows lost.

**Why it happens:** The matcher trusts `event_log_regex` keys to be well-typed.

**How to avoid:** Matcher validates `kind` against the Pydantic enum BEFORE INSERT; unknown-kind matches logged as `_log.warning` and discarded (not raised). Extra defense: `try/except UniqueViolationError` around the batch insert and fall back to per-row with the offender skipped.

**Warning signs:** Empty `agent_events` table after a container produces real activity — check startup for "unknown kind" WARN lines.

### Pitfall 5: Docker SDK thread-pool exhaustion at scale

**What goes wrong:** Each watcher holds one Python thread via `asyncio.to_thread(next, it, None)`. Default threadpool is `min(32, cpu_count + 4)`. At 32+ concurrent running agents, new watchers block on thread acquisition.

**Why it happens:** `asyncio.to_thread` uses the default thread pool executor; docker-py's `logs(follow=True)` is a blocking generator.

**How to avoid:** v1 scale is ≤1 agent per user, so this doesn't bite in 22b. Document as a FLAG in watcher_service. Future work: `loop.set_default_executor(ThreadPoolExecutor(max_workers=128))` in lifespan, OR migrate to raw-socket event polling. Spike 02 §Planner note 4 already flagged this.

**Warning signs:** `asyncio.to_thread` coroutines stuck in "pending executor task" state; new `/start` watchers never begin emitting events.

### Pitfall 6: openclaw `/start` env-var mismatch (see dedicated section below)

**What goes wrong:** `/start` injects the bearer as `OPENROUTER_API_KEY` regardless of `recipe.provider`. Openclaw with `anthropic` provider gets the wrong env var → openclaw auto-enables its broken openrouter plugin → LLM call returns empty → user thinks Gate A failed.

**How to avoid:** See §Openclaw `/start` Env-Var Gap — Posture below.

## Code Examples

### Example 1: Watcher spawn + matcher + batched insert (authoritative shape)

```python
# services/watcher_service.py — NEW
# Source: CONTEXT.md D-02/D-03/D-10/D-12, spikes 02/04/05
import asyncio, json, logging, re, time
from typing import Protocol, AsyncIterator
import docker

_log = logging.getLogger("api_server.watcher")
BATCH_SIZE = 100
BATCH_WINDOW_MS = 100

async def run_watcher(app_state, container_row_id, container_id: str,
                      agent_id, recipe: dict, channel: str, chat_id_hint: str | None):
    """Spawn point called from /start (Step 8b) and from lifespan re-attach.
    Registers in app_state.log_watchers[container_row_id] = current_task()."""
    stop_event = asyncio.Event()
    app_state.log_watchers[container_row_id] = (asyncio.current_task(), stop_event)
    try:
        source = _select_source(recipe, channel, container_id, chat_id_hint, stop_event)
        regexes = _compile_regexes(recipe, channel)   # dict[kind → re.Pattern]
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)

        async def consumer():
            pending: list[tuple[str, dict, str | None]] = []
            last_flush = time.monotonic()
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(),
                        timeout=BATCH_WINDOW_MS / 1000)
                except asyncio.TimeoutError:
                    item = None
                if item is not None:
                    pending.append(item)
                now = time.monotonic()
                if pending and (len(pending) >= BATCH_SIZE or
                                (now - last_flush) * 1000 >= BATCH_WINDOW_MS):
                    async with app_state.db.acquire() as conn:
                        await insert_agent_events_batch(conn, agent_id, pending)
                    signal = app_state.event_poll_signals.setdefault(agent_id, asyncio.Event())
                    signal.set()
                    pending = []
                    last_flush = now
                if stop_event.is_set() and queue.empty():
                    break

        consumer_task = asyncio.create_task(consumer())

        # Producer: read lines, match, enqueue matched tuples.
        drops = 0
        async for raw_line in source.lines():
            for kind, pattern in regexes.items():
                m = pattern.search(raw_line)
                if not m:
                    continue
                try:
                    payload = _build_payload(kind, m, chat_id_hint)
                except ValueError:
                    continue    # unknown kind / malformed capture
                corr = _extract_correlation(kind, raw_line, m)
                try:
                    queue.put_nowait((kind, payload, corr))
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()    # drop oldest
                    except asyncio.QueueEmpty:
                        pass
                    queue.put_nowait((kind, payload, corr))
                    drops += 1
                    if drops == 1 or drops % 100 == 0:
                        _log.warning("watcher queue drop", extra={
                            "agent_id": str(agent_id), "drops": drops})

        stop_event.set()
        await asyncio.wait_for(consumer_task, timeout=2.0)
    finally:
        app_state.log_watchers.pop(container_row_id, None)


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
    raise ValueError(f"unknown event_source_fallback.kind: {kind}")
```

### Example 2: /start extension (spawn watcher after row-to-running)

```python
# routes/agent_lifecycle.py::start_agent — append after Step 8 "mark row running":
# Source: CONTEXT.md D-10; runner_bridge pattern
# ... existing write_agent_container_running completes ...
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
    _log.exception("watcher spawn failed", extra={"agent_id": str(agent_id)})
    # Do NOT fail the /start response — container is running, events are
    # observability only. The lifespan re-attach will try again on next
    # restart.
```

### Example 3: /stop extension (signal stop + await)

```python
# routes/agent_lifecycle.py::stop_agent — insert BEFORE execute_persistent_stop:
# Source: CONTEXT.md D-10; spike 03 (iterator ends cleanly on docker rm -f)
watcher_entry = request.app.state.log_watchers.get(UUID(running["id"]))
if watcher_entry:
    _task, stop_event = watcher_entry
    stop_event.set()
    # Graceful: let the iterator end via docker stop (spike 03 timing ~270ms).
    # Force: fall back to cancel after 2s.
    try:
        await asyncio.wait_for(_task, timeout=2.0)
    except asyncio.TimeoutError:
        _task.cancel()
```

### Example 4: Lifespan re-attach

```python
# main.py lifespan — extend startup phase:
# Source: CONTEXT.md D-11; fetch_running_container_for_agent shape
app.state.log_watchers = {}
app.state.event_poll_signals = {}
app.state.event_poll_locks = {}

async with app.state.db.acquire() as conn:
    rows = await conn.fetch(
        """SELECT id, agent_instance_id, recipe_name, container_id, channel_type
             FROM agent_containers WHERE container_status='running'""")
for row in rows:
    recipe = app.state.recipes.get(row["recipe_name"])
    if recipe is None:
        continue
    asyncio.create_task(run_watcher(
        app.state, row["id"], row["container_id"], row["agent_instance_id"],
        recipe, row["channel_type"], chat_id_hint=None))
    # chat_id_hint=None on re-attach — the hint is only needed for
    # docker_exec_poll's session_id_template which can degrade to a
    # glob-match on sessions.json. Planner: probe empirically.

# shutdown phase:
pending = [t for (t, _e) in app.state.log_watchers.values()]
for (_t, e) in app.state.log_watchers.values():
    e.set()
if pending:
    done, still = await asyncio.wait(pending, timeout=2.0)
    for t in still:
        t.cancel()
```

### Example 5: Migration 004 shape

```python
# api_server/alembic/versions/004_agent_events.py — NEW
# Source: 003_agent_containers.py template + D-16/D-17
"""Phase 22b — agent_events table (observation stream)."""
revision = "004_agent_events"
down_revision = "003_agent_containers"

def upgrade():
    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("agent_container_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_containers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_agent_events_kind",
        "agent_events",
        "kind IN ('reply_sent','reply_failed','agent_ready','agent_error')")
    op.create_index(
        "ix_agent_events_agent_seq",
        "agent_events", ["agent_container_id", "seq"],
        unique=True)
    op.create_index(
        "ix_agent_events_agent_ts_kind",
        "agent_events", ["agent_container_id", "ts", "kind"])
```

## D-23: Multi-Source Watcher Architecture (NEW DECISION — planner MUST fold)

**Gap in CONTEXT.md:** D-01..D-02 describe docker-logs-scrape as THE ingest path. Spikes 01c (nullclaw) and 01e (openclaw) empirically proved this is insufficient for 40% of the catalog. This section proposes the canonical fix.

### Recipe schema (additive v0.2)

```yaml
channels:
  telegram:                              # or any other channel key
    event_log_regex:
      reply_sent: "<regex or null>"      # null = not observable via primary source
      reply_failed: "<regex>"
      agent_error: "<regex>"
      # inbound_message / response_text are watcher-internal only
      # (correlation-attach buffer + bonus capture for picoclaw/nanobot);
      # not enumerated in `kind` enum (D-05).

    event_source_fallback:              # OMIT for default docker_logs_stream source
      kind: docker_exec_poll | file_tail_in_container
      spec:
        # kind-specific fields (see below)
      notes: |
        Free-form text; persisted in recipe for ops context.
```

### Three source kinds (Python Protocol — §Architecture Pattern 1)

| Kind | Constructor fields | Used by | Teardown |
|------|-------------------|---------|----------|
| `docker_logs_stream` (DEFAULT) | `container_id`, `stop_event` | hermes, picoclaw, nanobot | Iterator ends on `docker rm -f` (<270ms, spike 03); NO `Task.cancel` needed |
| `docker_exec_poll` | `container_id`, `argv_template` (with `{session_id}` placeholder), `session_id_template` (with `{chat_id}`), `poll_interval_s` (default 500ms), `stop_event`, optional `tail_file` | nullclaw | Loop exits on `stop_event.is_set()`; outstanding `docker exec` has timeout=5s |
| `file_tail_in_container` | `container_id`, `sessions_manifest` path, `session_log_template` (with `{session_id}`), `chat_id_hint`, `stop_event` | openclaw | `docker exec tail -F` subprocess killed on `stop_event`; re-resolves session on tail-exit |

### Dispatch (in `watcher_service._select_source`)

```python
def _select_source(recipe, channel, container_id, chat_id_hint, stop_event):
    channel_spec = recipe.get("channels", {}).get(channel, {})
    fallback = channel_spec.get("event_source_fallback")
    if fallback is None:
        return DockerLogsStreamSource(container_id, stop_event)
    kind = fallback["kind"]
    spec = fallback.get("spec", {})
    if kind == "docker_exec_poll":
        return DockerExecPollSource(container_id=container_id,
            argv_template=spec["argv_template"],
            session_id_template=spec.get("session_id_template"),
            tail_file=spec.get("tail_file"),
            chat_id_hint=chat_id_hint,
            stop_event=stop_event)
    if kind == "file_tail_in_container":
        return FileTailInContainerSource(container_id=container_id,
            sessions_manifest=spec["sessions_manifest"],
            session_log_template=spec["session_log_template"],
            chat_id_hint=chat_id_hint,
            stop_event=stop_event)
    raise ValueError(f"unknown event_source_fallback.kind: {kind!r}")
```

### Teardown semantics (identical across kinds)

- `stop_event.set()` signals "please exit cleanly soon" (called by `/stop`, lifespan shutdown, or error).
- Source `lines()` generator checks `stop_event.is_set()` between yields AND on natural iterator end (docker_logs) / poll-loop break (docker_exec_poll) / subprocess exit (file_tail).
- Consumer (batcher) drains queue; watcher `finally:` pops from `app.state.log_watchers`.
- Watcher-task completion within 2s budget; `await asyncio.wait_for(task, timeout=2.0)` in `/stop`.

### Backpressure semantics (identical)

- Per-watcher `asyncio.Queue(maxsize=500)` fed by matcher (NOT raw lines).
- Queue-full: drop oldest + coalesced WARN (first + once-per-100 thereafter).
- Matched-line rate — not raw-line rate — bounds queue pressure. Spike 02 confirmed a 20k-line flood produced 17,470 drops when the consumer was a no-op; real matchers will match a few events per minute, so drops are essentially impossible in practice.

### Sink (identical)

All three sources feed `insert_agent_events_batch(...)` via the same consumer coroutine. Seq allocation uses advisory lock once per batch (spike 04).

### Per-recipe mapping (spike-derived, authoritative)

Already captured in §Architecture Pattern 1 table. Planner copies this into the Plan N that wires watcher_service dispatch.

## Openclaw `/start` Env-Var Gap — Posture

**The gap (surfaced by spike 01e):** `/v1/agents/:id/start` in `agent_lifecycle.py` reads `api_key_var = recipe.runtime.process_env.api_key` → it's literally `"OPENROUTER_API_KEY"` for openclaw. The bearer token from `Authorization: Bearer ...` is injected as THAT env var name into the container, regardless of whether the user is providing an OpenRouter key or an Anthropic-direct key. Openclaw's auto-plugin-enable logic sees `OPENROUTER_API_KEY` and activates its (empirically broken — see `recipes/openclaw.yaml` §known_quirks) openrouter plugin. Anthropic-direct openclaw cannot be booted via the real `/start` path today. Spike 01e bypassed via direct `docker run` with `-e ANTHROPIC_API_KEY=...`.

**Recommended posture: IN-SCOPE for Phase 22b, but as a small targeted plan, not a blocker.**

### Rationale

1. **SC-03 Gate A requires it.** The harness must hit `/v1/agents/:id/start` to get an `agent_container_id`, then invoke `direct_interface` via `docker exec`. For openclaw, Gate A cannot execute via the real `/start` path without this fix. Skipping openclaw from Gate A undermines 5-recipe matrix coverage — we'd ship a 4/5 Gate A, flagging openclaw manual-only, which is a regression from what the spikes proved feasible.
2. **The fix is small and well-scoped.** Recipe declares `provider_compat.supported: [anthropic]` and `provider_compat.deferred: [openrouter]` already (openclaw.yaml lines 484-487). The fix is: `/start` consults `recipe.runtime.process_env.api_key_by_provider: {openrouter: OPENROUTER_API_KEY, anthropic: ANTHROPIC_API_KEY, ...}` with fallback to `api_key`, and picks based on the model's provider prefix (or the recipe's `provider_compat.supported[0]` if there's a single supported provider).
3. **It doesn't grow the surface.** The existing `process_env.api_key_fallback` field (`hermes.yaml` line 34: `OPENAI_API_KEY`) already hints at multi-provider awareness. This generalizes it to a per-provider map.
4. **Alternative (out-of-scope hotfix) has worse ergonomics.** If deferred to a post-22b phase, the e2e harness has to special-case openclaw with a `docker run` bypass, which means Golden Rule 2 (dumb client / intelligence in API) is violated by the test harness itself — the harness would carry openclaw-specific logic.

### Scope of the openclaw-env-var plan (Plan N in 22b waves)

- **Recipe schema addition:** `runtime.process_env.api_key_by_provider: dict[str, str]` (optional). Backward-compatible — if absent, fallback to `api_key` (current behavior).
- **Route change:** `agent_lifecycle.py::start_agent` Step 2b — when `api_key_by_provider` is present, pick the env-var name using `_detect_provider(model, recipe)` (inspect model prefix: `anthropic/...` → `anthropic`, `openrouter/...` → `openrouter`, else recipe's `provider_compat.supported[0]`).
- **Recipe update:** `recipes/openclaw.yaml` adds:
  ```yaml
  runtime:
    process_env:
      api_key: OPENROUTER_API_KEY           # default / legacy callers
      api_key_by_provider:
        openrouter: OPENROUTER_API_KEY      # deferred; bug documented
        anthropic: ANTHROPIC_API_KEY        # verified-working
      api_key_fallback: null
  ```
- **One test:** `test_start_env_var_by_provider.py` — creates agent with anthropic model, POSTs `/start` with an `ANTHROPIC_API_KEY` bearer, asserts the container gets `ANTHROPIC_API_KEY` in its env (not `OPENROUTER_API_KEY`). Real testcontainer + real openclaw image OR a tiny alpine fixture that `env | grep` and exits.
- **Estimated effort:** ~1 day. One plan, standalone.

### Alternative if user disagrees

If user classifies this as out-of-scope for 22b, the concrete consequence is: Gate A covers hermes + picoclaw + nullclaw + nanobot (4/5); openclaw is marked "Gate A manual-only" and validated via the spike-01e bypass-`docker-run` path once per release. Gate B (secondary) still covers openclaw via the watcher (file_tail_in_container fallback — which works regardless of env-var bug, since it observes the session JSONL after anthropic plugin handles the turn).

**Recommendation: in-scope.** Planner adds it as one of the 6 plans.

## Validation Architecture (Dimension 8)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio 0.23 (asyncio_mode=auto) `[VERIFIED: pyproject.toml]` |
| Config file | `api_server/pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `cd api_server && pytest tests/test_event_store.py tests/test_watcher_*.py -x` |
| Full suite command | `cd api_server && pytest` |
| Integration-only | `cd api_server && pytest -m api_integration` (requires docker daemon) |

### Phase Requirements → Test Map

Per Golden Rule 1 (no mocks, no stubs), every test hits real Postgres via testcontainers and real Docker daemon via docker-py against throwaway alpine containers. Spike artifacts become seed test cases.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC-03-A-hermes | hermes `direct_interface` round-trip | e2e | `bash test/e2e_channels_v0_2.sh --recipe hermes --rounds 3` | ❌ Wave 3 |
| SC-03-A-picoclaw | same | e2e | `bash test/e2e_channels_v0_2.sh --recipe picoclaw --rounds 3` | ❌ Wave 3 |
| SC-03-A-nullclaw | same | e2e | `bash test/e2e_channels_v0_2.sh --recipe nullclaw --rounds 3` | ❌ Wave 3 |
| SC-03-A-nanobot | same | e2e | `bash test/e2e_channels_v0_2.sh --recipe nanobot --rounds 3` | ❌ Wave 3 |
| SC-03-A-openclaw | same (requires openclaw env-var fix) | e2e | `bash test/e2e_channels_v0_2.sh --recipe openclaw --rounds 3` | ❌ Wave 3 |
| SC-03-B-any | `reply_sent` event recorded ≤10s after bot→self sendMessage | e2e | `bash test/e2e_channels_v0_2.sh --gate B` | ❌ Wave 3 |
| D-16 seq gap-free | concurrent INSERT on same agent; no gaps, no UVs, no deadlocks | integration | `pytest tests/test_event_store.py::test_seq_concurrent -x` | ❌ Wave 1 |
| D-12 batch speedup | 100-row batch ≥2× per-row throughput | integration | `pytest tests/test_event_store.py::test_batch_speedup -x` | ❌ Wave 1 |
| D-02 docker logs teardown | iterator ends cleanly on `docker rm -f` | integration | `pytest tests/test_watcher_source_docker_logs.py::test_teardown -x` | ❌ Wave 1 |
| D-23 multi-source dispatch | each of 3 kinds instantiates + yields lines | integration | `pytest tests/test_watcher_*.py -x` | ❌ Wave 1 |
| D-09 long-poll | timeout path returns 200 empty; signal path returns rows | integration | `pytest tests/test_agent_events_endpoint.py::test_longpoll_* -x` | ❌ Wave 2 |
| D-13 concurrent poll | second concurrent poll gets 429 | integration | `pytest tests/test_agent_events_endpoint.py::test_concurrent_429 -x` | ❌ Wave 2 |
| D-11 lifespan reattach | running row → watcher spawned on startup | integration | `pytest tests/test_watcher_lifecycle.py::test_reattach -x` | ❌ Wave 2 |
| D-06 privacy | reply body never appears in agent_events.payload | unit+integration | `pytest tests/test_event_store.py::test_no_body_leak -x` | ❌ Wave 1 |
| D-15 auth | ANON ownership + AP_SYSADMIN_TOKEN bypass | integration | `pytest tests/test_agent_events_endpoint.py::test_auth_* -x` | ❌ Wave 2 |

### Spike evidence → test fixture

| Spike | Feeds test |
|-------|-----------|
| spike-04-postgres-batching.md | `test_batch_speedup` — 5 agents × 200 rows, assert ≥2× vs per-row (spike measured 12.4×) |
| spike-05-seq-ordering.md | `test_seq_concurrent` — 4 concurrent writers × 50 rows on SAME agent_id; assert 200 gap-free rows, 0 UVs, 0 deadlocks |
| spike-02-docker-sdk-backpressure.md | `test_watcher_backpressure` — alpine container emits 20k lines in 8s; assert queue stays bounded, no FD/RSS leak, drop count reported |
| spike-03-watcher-teardown.md | `test_teardown_on_rm_f` — start container + watcher; `docker rm -f`; assert watcher task done within 5s, 0 dangling tasks |
| spike-01a-hermes.md | fixture regex captured in `recipes/hermes.yaml`; unit test: `test_regex_fixture_matches_sample_log` |
| spike-01b-picoclaw.md | same, picoclaw |
| spike-01c-nullclaw.md | fixture: docker_exec_poll shape; unit test on JSON-diff matcher |
| spike-01d-nanobot.md | fixture regex, nanobot |
| spike-01e-openclaw.md | fixture: file_tail source with sessions_manifest; unit test on assistant-message extractor |
| spike-06-direct-interface.md | fixture: per-recipe argv_template / HTTP spec; harness subcommand `send-direct-and-read` calls the declared interface |

### Sampling rate
- **Per task commit:** `pytest tests/test_event_store.py -x tests/test_watcher_source_docker_logs.py -x` (~10s each w/ session-scoped PG)
- **Per wave merge:** `cd api_server && pytest` (full suite, all integration)
- **Phase gate:** `bash test/e2e_channels_v0_2.sh` green (Gate A 15/15 + Gate B 5/5)

### Wave 0 gaps

- [ ] Add `docker>=7.0,<8` to `api_server/pyproject.toml` (Wave 0)
- [ ] `tests/conftest.py` — add `docker_client` session fixture + `alpine_container` factory for watcher tests (Wave 0)
- [ ] Openclaw `/start` env-var fix (Wave 0 — unblocks Gate A for openclaw)
- [ ] No framework install needed (pytest + testcontainers + docker already in dev extras after Wave 0 adds `docker`)

## Security Domain

> `security_enforcement` default = enabled. `.planning/config.json` not checked yet; planner verifies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Bearer token → `ANONYMOUS_USER_ID` today (Phase 19 MVP); `AP_SYSADMIN_TOKEN` env-var bypass for ops (D-15) |
| V3 Session Management | no | No new session concept; reuses Phase 19 anonymous |
| V4 Access Control | yes | Ownership check on `/v1/agents/:id/events` — `agent.user_id == user_id` (D-15) |
| V5 Input Validation | yes | Query params (`since_seq: int >= 0`, `kinds: csv`, `timeout_s: int`) — Pydantic validator. `agent_id: UUID` in path; parsed by FastAPI route. |
| V6 Cryptography | no | No new crypto in 22b (reuses Phase 22's age-KEK for channel config); `AP_SYSADMIN_TOKEN` is a bearer token, not a crypto primitive |
| V7 Error Handling | yes | Stripe-shape error envelopes (`make_error_envelope`); reply-body redaction (D-06 — never store body); credential redaction via `_redact_creds` from `agent_lifecycle.py` |
| V8 Data Protection | yes | D-06 metadata-only payloads; no body text; age-encrypted channel config at rest (inherited from 22-02) |
| V13 API & Web Service | yes | Parameterized queries throughout (`$1, $2, ...` in asyncpg); rate limiting middleware already mounted (per-IP) — D-13 adds per-agent long-poll lock |

### Known Threat Patterns for 22b

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Regex catastrophic backtracking (ReDoS) | Denial of Service | Every recipe's `event_log_regex.*` must be authored to avoid backtracking (e.g. no nested `.+.+` quantifiers). Pre-compile at recipe-load time; measure match time on a synthetic long-line fixture. Planner adds `tests/test_regex_safety.py` that runs each recipe's regex against a 100kB adversarial line with a 100ms time budget. |
| Long-poll connection exhaustion | DoS | D-13 per-`(caller, agent_id)` lock → 429; global FastAPI middleware already rate-limits per-IP |
| Reply body leakage to DB or API | Information Disclosure | D-06 metadata-only `payload`; planner test `test_no_body_leak` asserts no recipe regex's capture group name contains `reply_text` / `text` / `body` IS WRITTEN to the `payload` column (unit inspection of `_build_payload` function). **Inbound_message matchers capture user text for correlation buffer only — never persisted.** |
| Credential leak in event_log_regex exception traceback | Information Disclosure | `_redact_creds` (existing in `agent_lifecycle.py`) reused in watcher error paths; bearer never reaches watcher; only channel_inputs hit the watcher via chat_id_hint (numeric user ID, not secret) |
| Unauthorized `GET /v1/agents/:id/events` | Elevation of Privilege | D-15 ownership check; ANON MVP means any Bearer works today but `agent_id` still has to exist; multi-tenant tightening is a Phase 21 one-liner |
| `AP_SYSADMIN_TOKEN` committed to .env | Information Disclosure | Document in README + CLAUDE.md that `AP_SYSADMIN_TOKEN` is per-laptop state, mirrors `AP_CHANNEL_MASTER_KEY` discipline |
| SQL injection via `kinds` query param | Injection | Parse `kinds` → enum set; build IN clause from a whitelist only; never interpolate raw param |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker daemon | watcher service + integration tests | ✓ | 27.x (assumed) | — (cannot degrade; watcher is the phase) |
| Postgres 17 | event_store, tests via testcontainers | ✓ | 17-alpine | — |
| Python 3.11+ | existing | ✓ | 3.11 (from `pyproject.toml: requires-python = ">=3.11"`) | — |
| docker-py | NEW — watcher | ✗ | to install | — (add to `pyproject.toml`) |
| testcontainers-python | existing dev | ✓ | >=4.14.2 | — |
| `.env.local` Telegram creds | harness Gate B only | ✗/✓ per laptop | N/A | skip Gate B row on machines missing them (document) |
| `AP_SYSADMIN_TOKEN` | harness Gate B | ✗/✓ per laptop | N/A | harness errors cleanly if unset |

**Missing dependencies with no fallback:** docker-py (add via pyproject.toml — Wave 0 step).

**Missing dependencies with fallback:** Telegram creds for Gate B — harness prints SKIP when missing, e2e script exits success if only SKIPs; Gate A still runs without Telegram creds.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| getUpdates-based harness verification | `direct_interface` Gate A + `agent_events` Gate B | 2026-04-18 (SC-03 design flaw discovered) | Automates 5/5 recipes without Bot API limitations |
| `FOR UPDATE` + `MAX(seq)` aggregate | `pg_advisory_xact_lock(hashtext($1::text))` + `MAX(seq)` | 2026-04-18 (spike 04/05) | PG rejects the former; advisory lock works and is faster |
| Single docker-logs-scrape source | Three source kinds (D-23) | 2026-04-18 (spikes 01c + 01e) | 40% of catalog needs fallback; multi-source is required, not optional |
| `Task.cancel()`-based watcher teardown | `stop_event.set()` + iterator-end / loop-break | 2026-04-18 (spike 03) | Cleaner teardown; no cancellation-exception handling in matcher |

**Deprecated/outdated:**
- `test/lib/telegram_harness.py::send-and-wait` (getUpdates-based) — DELETE in 22b; replaced by two new subcommands.
- MATRIX row format hardcoding `openrouter/...` prefix as model — fixed pre-spike; ensure the rewritten script keeps the fix.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | docker-py 7.1.0 is current and stable `[ASSUMED]` | Standard Stack | Very low — docker-py is mature; planner can pin `>=7.0,<8` and verify at install time |
| A2 | `loop.set_default_executor` is not needed at 22b scale (<32 agents) `[ASSUMED]` | Pitfall 5 | Low — v1 is 1 active agent per user; documented as a future-scale FLAG |
| A3 | `docker exec tail -F` via subprocess.Popen streams line-by-line reliably on Alpine BusyBox `[ASSUMED — needs probe]` | D-23 file_tail_in_container | Medium — BusyBox tail's `-F` behavior can differ from GNU tail. Planner: add a sub-task early in Wave 1 to smoke-test `docker exec ap-recipe-openclaw tail -n0 -F /tmp/probe.log` line-buffered behavior |
| A4 | Telegram bot→self `sendMessage` (bot user to its own chat_id) is accepted by the Bot API and produces an outbound event in the recipe's logs `[ASSUMED]` | Gate B harness | Medium — if the Bot API rejects self-send or the bot doesn't process its own sendMessage as an inbound, Gate B becomes unreachable. Planner: spike this early in Wave 3 |
| A5 | openclaw's `sessions.json` has at least one session entry within 5s of first user DM `[ASSUMED per spike 01e]` | D-23 file_tail | Low — spike 01e observed this empirically |
| A6 | re-attach on lifespan startup can reconstruct `chat_id_hint` from `channel_config_enc` decrypt (or degrade gracefully when it can't) `[ASSUMED]` | D-11 + Example 4 | Medium — decrypting channel_config on startup means depending on `AP_CHANNEL_MASTER_KEY` being set at lifespan. Planner: confirm restart path decrypts OR document graceful degradation (docker_exec_poll without chat_id hint uses a glob session match) |
| A7 | `AP_SYSADMIN_TOKEN` naming convention follows existing `AP_*` prefix `[ASSUMED]` | D-15 | Very low — purely a style choice; planner may use another name if preferred |

Claims tagged `[ASSUMED]` should be surfaced to the planner; claims A3, A4, A6 warrant a pre-execution micro-probe (one shell command each).

## Open Questions (RESOLVED)

1. **Does `lifespan` re-attach successfully reconstruct `chat_id_hint` from the encrypted channel config?**
   - What we know: `agent_containers.channel_config_enc` is age-encrypted; decrypt requires `AP_CHANNEL_MASTER_KEY` in lifespan env.
   - What's unclear: whether the re-attach loop should decrypt (adds complexity + timing risk at startup) or degrade gracefully (watcher for docker_exec_poll / file_tail starts without a hint and uses a glob session match).
   - RESOLVED: **degrade gracefully** — lifespan re-attach starts watchers without hints; nullclaw / openclaw sources resolve session_id via manifest sweep rather than template interpolation. Simpler, no startup-decrypt race.

2. **Does `docker exec tail -F` via Popen.stdout stream line-by-line on Alpine BusyBox?**
   - What we know: Alpine's BusyBox tail supports `-F` but may buffer differently than GNU tail.
   - RESOLVED: planner adds a 10-line `tests/test_busybox_tail_line_buffer.py` in Wave 0 that writes a line to a file and asserts Popen.stdout.readline() returns within 100ms. If it fails, fallback is `docker exec sh -c "while :; do cat; sleep 0.2; done"` — less elegant but portable.

3. **Does Telegram accept bot→self `sendMessage` (bot's token to its own chat_id) and does the bot process it as an inbound?**
   - Spike 01a observed the inverse — `sendMessage` appears as bot-originated in the UI and the bot doesn't "receive" it back. So Gate B's premise — bot-originating-a-message to itself and observing `reply_sent` in our event stream — may need refinement.
   - Alternative Gate B: bot→bot's own `updates.chat` via `getMe` → NO — `sendMessage` with `chat_id` = bot's own user id is explicitly rejected by Telegram ("Bad Request: bots can't send messages to bots").
   - Real alternative: **Gate B tests the event pipeline synthetically** by having the harness manually emit a log line to the container's stdout (via `docker exec echo "...reply_sent pattern..."`) and verifying the watcher → event_store → long-poll path end-to-end. This proves the pipeline works without requiring a live Telegram turn. Pair with Gate C (manual) for real Telegram confirmation.
   - DEFERRED to execution (Wave 3 Plan 22b-06 Task 3 probe): planner probes this in Wave 3 before committing to the sendMessage approach; if it fails, the "synthetic log-inject" variant of Gate B is implementable in ~10 lines of harness. Resume trigger: Task 3 Gate B run emits FAIL verdict for all 5 recipes due to sendMessage-not-delivered-to-bot — pivot harness to the synthetic log-inject variant and re-run.

4. **Partial-index `ix_agent_events_agent_seq PARTIAL WHERE ...?`**
   - RESOLVED: CONTEXT.md D-16 calls it "partial UNIQUE" but the conditions aren't listed. Pure `UNIQUE (agent_container_id, seq)` is sufficient (no partial filter needed — every row has both columns NOT NULL). Drop the "partial" word, just a composite UNIQUE.

5. **Do we ingest `agent_ready` from docker_exec_poll / file_tail sources, or only from docker_logs_stream?**
   - `persistent.spec.ready_log_regex` is applied to docker logs today (by the runner during boot). For recipes using `event_source_fallback`, nullclaw and openclaw's readiness IS visible in docker logs (spike 01a-1e boot sequences). So: the watcher can treat `persistent.spec.ready_log_regex` as an ADDITIONAL docker_logs_stream matcher regardless of the primary event source (it's a different stream — run a lightweight secondary docker_logs_stream watcher for ready-only).
   - RESOLVED: keep `agent_ready` exclusively on docker_logs_stream, run in parallel to the primary event source for fallback recipes. Two cheap watchers per agent, not one.

## Substrate Reuse Map

| New file | Closest existing analog | Why |
|----------|------------------------|-----|
| `api_server/src/api_server/models/events.py` | `api_server/src/api_server/models/agents.py` | Same Pydantic patterns: per-kind typed payloads, `ConfigDict(extra="forbid")`, `model_dump(mode="json")` |
| `api_server/src/api_server/services/event_store.py` | `api_server/src/api_server/services/run_store.py` | Parameterized queries, connection-per-scope, BIGSERIAL + UUID idioms; two-phase INSERT → UPDATE becomes single INSERT here |
| `api_server/src/api_server/services/watcher_service.py` | `api_server/src/api_server/services/runner_bridge.py` | `asyncio.to_thread` for blocking SDK calls; app.state-scoped resources; module-scope logger `_log = logging.getLogger("api_server.watcher")` |
| `api_server/src/api_server/routes/agent_events.py` | `api_server/src/api_server/routes/agent_lifecycle.py` (stop_agent handler is closest) | 9-step flow (with fewer steps — no runner call); `_err` helper; bearer parse; ownership check |
| `api_server/alembic/versions/004_agent_events.py` | `api_server/alembic/versions/003_agent_containers.py` | CHECK constraint pattern, BIGSERIAL vs UUID decision (pick BIGSERIAL for row PK per D-16 commentary), CASCADE FK, partial/composite index |
| `api_server/tests/test_event_store.py` | `api_server/tests/test_run_concurrency.py` (existing concurrency test) | Testcontainers PG, pytest-asyncio, session-scoped container + truncate-between-tests |
| `api_server/tests/test_watcher_source_docker_logs.py` | no direct analog | NEW shape: spawn alpine with echo loop, attach watcher, assert regex capture. Model after spike 02 reproducer. |
| `api_server/tests/test_agent_events_endpoint.py` | `api_server/tests/test_runs.py` | httpx AsyncClient + ASGITransport + create_app; integration markers |
| `test/lib/agent_harness.py` (renamed from telegram_harness.py) | `test/smoke-api.sh` style | Use `_pass/_fail/_skip` helper pattern; stdlib-only (urllib); JSON emit to stdout; exit codes 0/1/2/3 consistent |

## Plan Shape Recommendation

**Recommendation: 6 plans across 4 waves, ~6-7 days total execution.** Non-binding; planner may deviate.

### Wave 0 — Preparation (single plan, single task unit; ~0.5d)
**Plan 22b-00 "deps-and-env-var-fix"**
- Add `docker>=7.0,<8` to `api_server/pyproject.toml`.
- Pin `AP_SYSADMIN_TOKEN` into `.env.example` commented + documentation in `deploy/README.md`.
- Openclaw env-var fix (§Openclaw `/start` Env-Var Gap — Posture): add `runtime.process_env.api_key_by_provider` to recipe schema, update `/start` handler, one integration test.
- Probe assumptions A3 (BusyBox tail) and A4 (Telegram bot→self sendMessage) — document findings, adjust Wave 3 harness design if needed.
- **Exit criterion:** `pip install -e '.[dev]'` green; openclaw `/start` with anthropic bearer boots cleanly.

### Wave 1 — Data layer + watcher primitives (2 plans, parallel; ~1.5d each)
**Plan 22b-01 "migration-and-event-store"** (owns `alembic/versions/004_agent_events.py`, `services/event_store.py`, `models/events.py`, `tests/test_event_store.py`)
- Migration 004 with CHECK + composite UNIQUE.
- `insert_agent_event` (per-row) and `insert_agent_events_batch` (100 per txn).
- Advisory-lock seq allocation; backport spike 05 as test.
- Pydantic per-kind payloads with `reply_sent` = `{chat_id: str, length_chars: int, captured_at: datetime}`, etc.
- Test `test_no_body_leak`, `test_seq_concurrent`, `test_batch_speedup`, `test_kind_check_constraint`.

**Plan 22b-02 "watcher-service-multi-source"** (owns `services/watcher_service.py`, `tests/test_watcher_*.py`)
- `EventSource` Protocol + 3 concrete classes (docker_logs_stream, docker_exec_poll, file_tail_in_container).
- `_select_source` dispatch per D-23.
- `run_watcher` coroutine: producer (source.lines → matcher → queue) + consumer (batch + insert).
- Stop_event semantics; graceful 2s teardown budget.
- Tests: one per source kind against a fresh alpine container; teardown test (spike 03 port); backpressure test (spike 02 port).
- **Independence:** touches no files Plan 22b-01 touches; parallelizable.

### Wave 2 — Wire into lifecycle (2 plans, parallel; ~1d each)
**Plan 22b-03 "lifecycle-integration"** (owns extensions to `routes/agent_lifecycle.py`, `main.py` lifespan)
- Extend `start_agent` to `asyncio.create_task(run_watcher(...))` after Step 8.
- Extend `stop_agent` to `stop_event.set()` + `await task, timeout=2.0` before `execute_persistent_stop`.
- Extend lifespan startup to query running rows and re-spawn watchers.
- Extend lifespan shutdown to gather all watcher tasks with 2s budget.
- `app.state.log_watchers`, `app.state.event_poll_signals`, `app.state.event_poll_locks` init.
- Tests: `test_watcher_lifecycle.py` — spawn-on-start, cancel-on-stop, reattach.

**Plan 22b-04 "long-poll-endpoint"** (owns `routes/agent_events.py`, `models/events.py` response models, `tests/test_agent_events_endpoint.py`)
- `GET /v1/agents/:id/events` handler with auth (D-15), ownership (D-15), concurrent-poll lock (D-13), long-poll wait.
- `_get_poll_lock`, `_get_poll_signal` helpers (mirror `_get_tag_lock` pattern).
- `CONCURRENT_POLL_LIMIT` and `EVENT_STREAM_UNAVAILABLE` error codes added to `models/errors.py` (coordinate with 22b-03 via shared import).
- Integration tests: timeout, signal-wake, since_seq filtering, kinds filter, 429 concurrent, auth variations.
- **Depends on:** 22b-01's event_store; parallelizable with 22b-03 because they touch disjoint route handlers (plus a single coordinated edit to `models/errors.py` that can land at Wave 2 start).

### Wave 3 — Harness + Gate execution (1 plan; ~1.5d)
**Plan 22b-05 "harness-rewrite-and-sc03-gate"** (owns `test/lib/agent_harness.py`, `test/e2e_channels_v0_2.sh`, 5 recipe YAML `direct_interface:` blocks)
- Rename `telegram_harness.py` → `agent_harness.py`; delete legacy `send-and-wait`.
- Add `send-direct-and-read`: dispatches on recipe's `direct_interface.kind`; implements `docker_exec_cli` and `http_chat_completions`.
- Add `send-telegram-and-watch-events`: bot→self sendMessage (OR synthetic log-inject fallback if A4 fails) + long-poll the new events endpoint.
- Update 5 recipe YAMLs with `direct_interface:` block per D-21 mapping. (Recipes already carry `event_log_regex` + `event_source_fallback` from spikes — don't re-edit those unless consolidating comments.)
- Rewrite `e2e_channels_v0_2.sh` Step 4 to call `send-direct-and-read` (Gate A); add Step 5 for `send-telegram-and-watch-events` (Gate B).
- Run and commit: `e2e-report.json` shows 15/15 Gate A + 5/5 Gate B.
- **Depends on:** 22b-03 + 22b-04 both merged.

### Total
- 6 plans across 4 waves
- Wave 0 (1) → Wave 1 (2 parallel) → Wave 2 (2 parallel) → Wave 3 (1)
- Critical path: 0.5d + 1.5d + 1d + 1.5d = **4.5d wall**; 6.5-7d of effort
- Each wave gates the next via its test suite green

### Parallelizability map

| Wave | Plans | Parallel? | Shared files |
|------|-------|-----------|--------------|
| 0 | 22b-00 | — | `pyproject.toml`, `openclaw.yaml`, `agent_lifecycle.py` (env-var fix) |
| 1 | 22b-01, 22b-02 | **YES** | none (fully disjoint) |
| 2 | 22b-03, 22b-04 | **YES with caveat** | `models/errors.py` (2 new codes) — land as a shared pre-edit, or coordinate commits |
| 3 | 22b-05 | — (single plan) | — |

## Project Constraints (from CLAUDE.md)

1. **No mocks, no stubs** (Golden Rule 1) — every watcher test uses real Docker daemon + real PostgreSQL via testcontainers. Spike artifacts carry the proof-of-concept; tests lift them verbatim.
2. **Dumb client, intelligence in the API** (Golden Rule 2) — harness does zero log-regex / source-kind dispatch; it invokes `direct_interface` (argv or HTTP) and calls the events endpoint. All routing / parsing / seq allocation is server-side.
3. **Root cause first** (Golden Rule 4) — if a watcher test fails, investigate the actual source behavior before tweaking regex / timing. Spikes 01c and 01e are canonical examples — FLAG'd instead of force-fitting docker_logs_stream.
4. **Test everything, probe gray areas before planning** (Golden Rule 5) — 10 spikes already landed; planner MUST address A3/A4/A6 via Wave 0 micro-probes before Wave 3.
5. **NEVER modify .env files without explicit user permission** — `AP_SYSADMIN_TOKEN` + `AP_CHANNEL_MASTER_KEY` stay per-laptop shell state; example file only.
6. **No production deploys without local end-to-end green** (Golden Rule 3) — Phase 22b's exit condition requires `bash test/e2e_channels_v0_2.sh` green locally.
7. **`response_language` not set** — all documentation, test output, log lines: English.

## Sources

### Primary (HIGH confidence)

- `.planning/phases/22b-agent-event-stream/22b-CONTEXT.md` (this repo, 2026-04-18) — locked decisions D-01..D-22
- `.planning/phases/22b-agent-event-stream/22b-SPIKES/SPIKES-PLAN.md` — matrix + 2nd-order findings
- `.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-{01a-e,02,03,04,05,06}.md` — all 10 spike artifacts with measured numbers
- `api_server/src/api_server/services/runner_bridge.py` — `execute_persistent_*` pattern for asyncio-to-thread bridge
- `api_server/src/api_server/services/run_store.py` — CRUD conventions + connection-per-scope discipline
- `api_server/src/api_server/routes/agent_lifecycle.py` — 9-step route flow template + `_redact_creds` helper
- `api_server/src/api_server/main.py` — lifespan + app.state initialization pattern
- `api_server/alembic/versions/003_agent_containers.py` — migration idiom (CHECK, partial UNIQUE, CASCADE)
- `api_server/src/api_server/constants.py` — `ANONYMOUS_USER_ID`
- `api_server/src/api_server/models/errors.py` — Stripe-shape error envelope, `ErrorCode` constants
- `api_server/tests/conftest.py` — testcontainers PG17 + truncate-between + ASGITransport patterns
- `recipes/{hermes,picoclaw,nullclaw,nanobot,openclaw}.yaml` — `event_log_regex` + `event_source_fallback` already committed from spikes
- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/forward_to_agent.go` — validates http_chat_completions kind via MSV pattern
- `.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md` — justifies 22b's existence

### Secondary (MEDIUM confidence)

- `recipes/openclaw.yaml` §known_quirks — OpenRouter plugin silent-fail; motivates the env-var-by-provider fix
- CLAUDE.md Golden Rules 1–5 — inform testing architecture + plan shape
- `memory/feedback_telegram_getupdates_is_single_consumer.md` — rules out harness alternatives

### Tertiary (LOW confidence — flagged)

- `[ASSUMED]` — docker-py 7.1.0 is the current stable line (verify at plan time via `pip index versions docker`)
- `[ASSUMED]` — BusyBox `tail -F` line-buffers stdout reliably (planner probes in Wave 0)
- `[ASSUMED]` — Telegram accepts bot→self sendMessage (planner probes in Wave 3; synthetic log-inject fallback available)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — only one new dep (docker-py); spike-validated.
- Architecture: HIGH — 10 spikes cover every mechanism. D-23 fills the only real gap.
- Pitfalls: HIGH — pitfalls 1-5 observed in spikes or existing substrate; pitfall 6 is the openclaw env-var gap with a recommended posture.
- Plan shape: MEDIUM-HIGH — 4-wave / 6-plan shape is conventional for this substrate; planner may justify 5 or 7 plans.
- Assumptions A3/A4/A6: MEDIUM — pre-execution probes reduce them to HIGH by Wave 0-3 boundaries.

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (30 days — stable substrate, spike evidence authoritative)
