---
phase: 22b
plan: 08
type: execute
wave: 5
depends_on: ["22b-04", "22b-05", "22b-06", "22b-07"]
files_modified:
  - api_server/src/api_server/routes/agent_events.py
  - api_server/src/api_server/main.py
  - api_server/tests/test_events_inject_test_event.py
  - test/lib/agent_harness.py
  - test/e2e_channels_v0_2.sh
autonomous: true
gap_closure: true
requirements:
  - SC-03-GATE-B

must_haves:
  truths:
    - "POST /v1/agents/:id/events/inject-test-event (sysadmin-Bearer-only, AP_ENV != prod-only) accepts URL `:id` as the **agent_containers.id** (container_row_id) per Spike B 2026-04-19 verification of the events-router URL-key contract. Inserts a real reply_sent row into the real agent_events table via insert_agent_event() (which returns seq as int, not dict — Spike B B1), wakes the long-poll signal via _get_poll_signal(app.state, agent_id).set() where agent_id IS container_row_id, and returns 200 with seq + container_row_id + synthesized ts (datetime.now(UTC) at insert time)"
    - "The injected row is visible to a concurrent GET /v1/agents/:id/events long-poll within 1 second (signal wake measured) — proves the long-poll → INSERT → signal-wake → handler-fetch chain end-to-end. CRITICAL per Spike B B2: BOTH the long-poll AND the inject MUST use container_row_id in the URL — using agent_instance_id on either side breaks the wake (signal is keyed on the URL value, not a translated identity)."
    - "AP_ENV=prod returns 404 NOT_FOUND for the inject route (route is invisible — same discipline as `app.openapi_url='/openapi.json' if env==dev else None` per main.py line 15)"
    - "Bearer != AP_SYSADMIN_TOKEN returns 404 (opaque — defense in depth) and AP_SYSADMIN_TOKEN unset returns 404 even with matching Bearer; sysadmin is the ONLY allowed caller; ANONYMOUS_USER_ID + regular ownership do NOT grant access (this endpoint is admin-debug-only)"
    - "test/lib/agent_harness.py gains a `send-injected-test-event-and-watch` subcommand that POSTs to the inject endpoint then long-polls /events; verdict=PASS iff the reply_sent event with the harness-generated correlation_id (prefixed `test:`) appears in the long-poll response"
    - "test/e2e_channels_v0_2.sh Gate B step calls the new harness subcommand by default (with AP_USE_LEGACY_GATE_B escape hatch preserving the bot-self path for AP_ENV=prod scenarios); SC-03 Gate B 5/5 PASS becomes achievable without bot-self impersonation OR allowFrom relaxation"
    - "Running `bash test/e2e_channels_v0_2.sh` with full creds + AP_ENV=dev produces Gate B 5/5 PASS in e2e-report.json"
    - "Integration test against real PG + real FastAPI app (testcontainers) covers: prod-mode 404, sysadmin happy path, missing-Bearer 401, wrong-Bearer 404 (opaque), AP_SYSADMIN_TOKEN unset → endpoint returns 404 even with matching Bearer (defense in depth), no-running-container 404, end-to-end signal-wake within 1s, double-inject seq advance"
  artifacts:
    - path: "api_server/src/api_server/routes/agent_events.py"
      provides: "POST /v1/agents/:id/events/inject-test-event handler with AP_ENV gate + sysadmin gate + agent-existence + insert_agent_event + signal.set()"
      contains: "inject_test_event"
    - path: "api_server/src/api_server/main.py"
      provides: "Conditional include_router for inject route — only registered when settings.env != 'prod'"
      contains: "inject_router"
    - path: "api_server/tests/test_events_inject_test_event.py"
      provides: "8 integration tests on real PG: prod-404, sysadmin-200, no-bearer-401, wrong-bearer-404, missing-AP_SYSADMIN_TOKEN-404, agent-not-found-404, end-to-end signal-wake, idempotent-correlation-id"
      contains: "def test_inject_test_event"
    - path: "test/lib/agent_harness.py"
      provides: "Third subcommand `send-injected-test-event-and-watch` mirroring send-telegram-and-watch-events shape but POST-ing to /inject-test-event instead of Telegram"
      contains: "cmd_send_injected_test_event_and_watch"
    - path: "test/e2e_channels_v0_2.sh"
      provides: "Gate B step rewritten to use injected-test-event path (preserves bot-self path as fallback when AP_ENV=prod via AP_USE_LEGACY_GATE_B)"
      contains: "send-injected-test-event-and-watch"
  key_links:
    - from: "api_server/src/api_server/routes/agent_events.py::inject_test_event"
      to: "api_server/src/api_server/services/event_store.py::insert_agent_event"
      via: "real INSERT into agent_events table keyed by container_row_id (URL agent_id IS container_row_id per Spike B B2 — no in-memory fake; golden rule 1)"
      pattern: "insert_agent_event\\("
    - from: "api_server/src/api_server/routes/agent_events.py::inject_test_event"
      to: "api_server/src/api_server/services/watcher_service.py::_get_poll_signal"
      via: "_get_poll_signal(app.state, agent_id).set() AFTER successful INSERT, where agent_id == container_row_id per URL-key contract — wakes the pending long-poll on the SAME key (Spike B verified: URL=container_row_id long-poll wakes in 0.04s; URL=instance_id long-poll TIMES OUT)"
      pattern: "_get_poll_signal.*\\.set\\("
    - from: "api_server/src/api_server/main.py"
      to: "api_server/src/api_server/routes/agent_events.py::inject_router"
      via: "if settings.env != 'prod': app.include_router(inject_router, ...)"
      pattern: "settings.env.*prod\\|env.*!=.*prod"
    - from: "test/lib/agent_harness.py::cmd_send_injected_test_event_and_watch"
      to: "POST /v1/agents/:id/events/inject-test-event + GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent"
      via: "Two HTTP calls, captured correlation_id matched in long-poll response (prefixed `test:`)"
      pattern: "inject-test-event"
    - from: "test/e2e_channels_v0_2.sh Gate B step"
      to: "test/lib/agent_harness.py send-injected-test-event-and-watch"
      via: "Replaces send-telegram-and-watch-events when AP_ENV=dev; preserves legacy via AP_USE_LEGACY_GATE_B"
      pattern: "send-injected-test-event-and-watch"
---

<objective>
**SPIKE B EMPIRICAL EVIDENCE (2026-04-19) — supersedes the original plan's URL-key assumption.**

The route `/v1/agents/{agent_id}/events` (GET, long-poll) treats URL `agent_id` as **`agent_containers.id`** (container_row_id), NOT as `agent_instances.id`. EMPIRICALLY CONFIRMED by:

1. `api_server/tests/test_events_long_poll.py:47-80` — the `seed_agent_container` fixture returns the agent_containers PK as a single UUID and uses it directly in long-poll URLs (`/v1/agents/{container_uuid}/events`).
2. `api_server/src/api_server/routes/agent_lifecycle.py:494` — the watcher spawn passes `agent_id=container_row_id` to `run_watcher`, and the watcher uses that key to populate the `event_poll_signals` dict (the dict the long-poll handler waits on).
3. Live test 2026-04-19: `long_poll(URL=instance_id) + INSERT(container_row_id)` → timed_out, 0 events. `long_poll(URL=container_row_id) + INSERT(container_row_id)` → returns in 0.04s with 1 event.

**Implications for THIS plan:**

- The new POST `/v1/agents/{agent_id}/events/inject-test-event` MUST follow the same URL-key convention (URL agent_id = container_row_id) so that injected events match what concurrent long-pollers see.
- The Step 4 agent-existence check in the handler must look up the row by `agent_containers.id`, NOT by `agent_instances.id` via `fetch_running_container_for_agent` (which expects the latter).
- The `seed_running_container` fixture MUST surface the container_row_id as the primary URL value (not the agent_instance_id).
- All 8 tests MUST use container_row_id in URLs (not agent_instance_id).
- The harness subcommand's `--agent-id` argument MUST be the container_row_id (same as the existing send-telegram-and-watch-events subcommand which is already container-row-id-based per Plan 22b-05).

The variable name `agent_id` in route handlers and existing code is a misleading legacy — the canonical URL key for `/v1/agents/{?}/events*` endpoints is `agent_containers.id`. This plan does NOT rename the variable (rename is out of scope; would touch Plan 22b-05's GET handler), but the REVISED Step 4 + fixture + tests below DO use container_row_id consistently.

---

**Gap 2 closure — Gate B mechanism redesign.** Verifier verdict: `send-telegram-and-watch-events` uses bot-self `sendMessage`, but every recipe ships `channels.telegram.allowFrom: [tg:152099202]` (only the human user). Bots aren't users; the bot's own outbound messages are filtered out, so no `reply_sent` event flows. Result: Gate B 0/5. The harness comment at line 109-111 explicitly admits this is a Gate-C concern. D-18a in CONTEXT.md formalized that MTProto user-impersonation is permanently deferred.

**Decision: Path B — test-injection endpoint** (recommended in user prompt).

Why B over A (allowFrom relaxation) or C (formal demotion):
- **A (allowFrom relaxation) is a SECURITY REGRESSION.** Even gated behind `AP_ENV=dev`, it teaches the recipe schema that allowFrom can be bypassed at test time. The wrong devs will copy that pattern; the wrong CI will set AP_ENV=dev in prod by accident. We do not want allowFrom semantics to depend on environment.
- **C (formal demotion) loses automation coverage.** Gate B's purpose is to prove the long-poll → INSERT → signal-wake → harness-fetch chain works end-to-end. The 16 unit tests in test_events_long_poll.py + test_events_auth.py cover the long-poll mechanics in isolation but do NOT cover "an external trigger inserts a row → harness sees it" — that integration matters for the SC-03 gate.
- **B (test-injection endpoint) gives us BOTH:** real DB write (golden rule 1 — no mocks/no stubs; the row is a real `agent_events` INSERT, not an in-memory fake), real signal-wake, real long-poll cycle. The synthetic origin (a sysadmin-only POST instead of a watcher-detected log line) is HONEST about what's being tested: the API plumbing, not the watcher's ability to extract events from container logs (that's covered by the watcher unit tests in test_events_*.py from Plans 22b-03/04). Gate C remains the per-release manual gate that proves the FULL chain (real user → real Telegram → real agent → real reply → real watcher → real DB).

**The endpoint contract** (locked in this plan; reviewable in revision):

```
POST /v1/agents/{agent_id}/events/inject-test-event
Headers:
  Authorization: Bearer <AP_SYSADMIN_TOKEN>     # ONLY sysadmin; no anonymous fallback
Body (JSON):
  {
    "kind": "reply_sent",                       # MUST be in VALID_KINDS; default reply_sent
    "correlation_id": "abc1",                   # short hex/alphanum; max 64 chars
    "chat_id": "152099202",                     # string; injected as payload.chat_id
    "length_chars": 12                          # integer; injected as payload.length_chars
  }

Response (200 OK):
  {
    "agent_id": "<uuid>",
    "agent_container_id": "<uuid>",             # the running container row this event was attached to
    "seq": 17,                                  # the per-agent gap-free seq the row got
    "kind": "reply_sent",
    "correlation_id": "test:abc1",              # prefixed for synthetic-row distinguishability
    "ts": "2026-04-19T03:14:00.123Z",
    "test_event": true                          # marks the row as harness-injected
  }

Error responses:
  404 NOT_FOUND when settings.env == 'prod'     # invisible in prod (same discipline as openapi.json)
  404 NOT_FOUND when AP_SYSADMIN_TOKEN unset    # defense in depth — never let a non-configured laptop expose this
  404 NOT_FOUND when Bearer != AP_SYSADMIN_TOKEN value (opaque — same response as route-not-registered)
  401 UNAUTHORIZED when Bearer missing/empty
  404 AGENT_NOT_FOUND when no running container_id for that agent_id
  400 INVALID_REQUEST when body missing required fields or kind not in VALID_KINDS
```

Two compounding gates make this safe: (1) route invisible in prod (404 even with valid sysadmin token), (2) sysadmin-only auth (no anonymous fallback like the GET route has). Either gate alone is enough; both together is defense-in-depth per CLAUDE.md golden rule 1 + threat-register `T-22b-08-01`.

Output: new POST handler in agent_events.py; conditional router include in main.py; 8 integration tests on real PG; new harness subcommand; e2e script Gate B step rewired; live SC-03 Gate B 5/5 PASS captured in e2e-report.json.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-VERIFICATION.md
@.planning/phases/22b-agent-event-stream/22b-04-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-05-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-06-SUMMARY.md
@api_server/src/api_server/routes/agent_events.py
@api_server/src/api_server/main.py
@api_server/src/api_server/config.py
@api_server/src/api_server/constants.py
@api_server/src/api_server/services/event_store.py
@api_server/src/api_server/services/watcher_service.py
@api_server/src/api_server/services/run_store.py
@api_server/src/api_server/models/errors.py
@api_server/src/api_server/models/events.py
@api_server/tests/test_events_long_poll.py
@api_server/tests/test_events_auth.py
@test/lib/agent_harness.py
@test/e2e_channels_v0_2.sh

<interfaces>
<!-- Contracts consumed; signatures verified by reading the source files in read_first -->

From api_server/src/api_server/services/event_store.py (Plan 22b-02; SPIKE B EMPIRICALLY VERIFIED 2026-04-19 — return type is int, NOT dict):
```python
async def insert_agent_event(
    conn,
    agent_container_id: UUID,
    kind: str,
    payload: dict,
    correlation_id: str | None = None,
) -> int   # returns the allocated seq (int) — verified via reading event_store.py:50,92
```

CRITICAL: the function returns the seq as a plain `int`. There is NO `ts` returned and NO row dict. The original plan's response builder `row["ts"].isoformat()` and `row["seq"]` would crash with `TypeError: 'int' object is not subscriptable`. The handler MUST capture the seq as int and synthesize `ts = datetime.now(timezone.utc)` at insert time — acceptable approximation (Postgres `now()` is within ms of the Python timestamp because the INSERT is on a same-connection same-host transaction; for stricter equivalence the handler could SELECT ts back, but the additional query cost is not justified for a synthetic-event response field).

From api_server/src/api_server/services/watcher_service.py (Plan 22b-03):
```python
def _get_poll_signal(app_state, agent_id: UUID) -> asyncio.Event   # keyed on agent_instance_id
async def _get_poll_lock(app_state, agent_id: UUID) -> asyncio.Lock
```

From api_server/src/api_server/services/run_store.py (existing):
```python
async def fetch_agent_instance(conn, agent_id: UUID, user_id: UUID) -> dict | None
async def fetch_running_container_for_agent(conn, agent_instance_id: UUID) -> dict | None
# returns dict with keys: id (text), agent_instance_id, user_id, recipe_name,
#                         container_id, container_status, channel_type, ...
```

From api_server/src/api_server/constants.py (Plan 22b-04):
```python
ANONYMOUS_USER_ID: UUID
AP_SYSADMIN_TOKEN_ENV: str = "AP_SYSADMIN_TOKEN"
```

From api_server/src/api_server/config.py (existing — verify by reading):
```python
class Settings(BaseSettings):
    env: Literal["dev", "prod"] = Field("dev", validation_alias="AP_ENV")
    ...
def get_settings() -> Settings: ...
```

From api_server/src/api_server/models/events.py (Plan 22b-02):
```python
VALID_KINDS: set[str] = {"reply_sent", "reply_failed", "agent_ready", "agent_error"}
class ReplySentPayload(BaseModel):
    chat_id: str
    length_chars: int
    captured_at: str       # ISO 8601
    model_config = ConfigDict(extra='forbid')
# (similar for ReplyFailed/AgentReady/AgentError; D-06 — no reply body)
```

The injected payload MUST satisfy ReplySentPayload (extra='forbid'). Per D-08 the payload validator runs on insert path — confirm `insert_agent_event` either accepts arbitrary dict OR explicitly validates against KIND_TO_PAYLOAD. Final decision: store the synthetic marker as `correlation_id="test:<orig>"` prefix instead, since correlation_id has no extra-fields constraint — keeps payload pure-shape.

From api_server/src/api_server/main.py (existing):
```python
# settings = get_settings() -> available; settings.env is 'dev' or 'prod'
# app.include_router pattern at end of create_app
# Phase 22b-04 already added: app.state.log_watchers, event_poll_signals, event_poll_locks
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: POST /v1/agents/:id/events/inject-test-event handler + conditional router include</name>
  <files>api_server/src/api_server/routes/agent_events.py, api_server/src/api_server/main.py, api_server/tests/test_events_inject_test_event.py</files>
  <read_first>
    - api_server/src/api_server/routes/agent_events.py (THE file being extended — read in full; the GET handler at line ~244 is the analog; the `_err` helper, `_project` helper, ErrorCode usage, `_get_poll_signal`/`_get_poll_lock` imports, fetch_agent_instance + ANONYMOUS_USER_ID pattern, AP_SYSADMIN_TOKEN_ENV resolution all live there)
    - api_server/src/api_server/main.py (locate the `app.include_router(agent_events_route.router, prefix='/v1', tags=['agents'])` line from Plan 22b-05; THIS task wraps a SECOND include_router call in `if settings.env != 'prod':` immediately after the existing one, OR uses a separate `inject_router` registered under `/v1/agents` only when env != prod)
    - api_server/src/api_server/config.py (VERIFIED 2026-04-19 in this plan's revision: `Settings.env: Literal["dev","prod"] = Field("dev", validation_alias="AP_ENV")`; `get_settings()` is NOT `@lru_cache`-wrapped — line 53-55 returns a fresh `Settings()` per call from current env. Implication: tests that `monkeypatch.setenv("AP_ENV", ...)` then call `create_app()` (line 192 reads settings at create-app time) get the freshly-set env automatically — NO `cache_clear()` needed. The try/except cache_clear shim in the test snippets below is defensive (handles future refactor to lru_cache); when the file is unchanged, the try/except hits the AttributeError path and silently no-ops, which is the correct behavior. main.py reads via `app.state.settings = settings` (line 202); routes read via `request.app.state.settings`.)
    - api_server/src/api_server/services/event_store.py (read the FULL signature of `insert_agent_event` — confirm whether it validates payload via KIND_TO_PAYLOAD; confirm the return shape includes seq; confirm advisory-lock acquired AROUND the INSERT so we don't deadlock from a concurrent watcher INSERT)
    - api_server/src/api_server/services/watcher_service.py (read `_get_poll_signal` line ~57 — keyed on agent_id which is agent_instance_id, NOT agent_container_id; ALSO confirm that the watcher itself calls `_get_poll_signal(app_state, agent_id).set()` AFTER each INSERT — same pattern we'll use)
    - api_server/src/api_server/services/run_store.py (lines 395-433 — `fetch_running_container_for_agent` returns the running container row OR None; we need this to translate agent_id → agent_container_id for the INSERT)
    - api_server/src/api_server/models/events.py (KIND_TO_PAYLOAD shape; ReplySentPayload required fields are chat_id + length_chars + captured_at — captured_at is the timestamp the synthetic event represents; we generate it as datetime.now(timezone.utc).isoformat())
    - api_server/src/api_server/models/errors.py (ErrorCode enum + make_error_envelope — INVALID_REQUEST + UNAUTHORIZED + AGENT_NOT_FOUND already exist; we do NOT add new codes)
    - api_server/tests/test_events_long_poll.py (test infrastructure analog — httpx AsyncClient + ASGITransport, real_db_pool fixture, sysadmin_env fixture)
    - api_server/tests/test_events_auth.py (auth-test analog — monkeypatch.setenv(AP_SYSADMIN_TOKEN, ...) pattern)
  </read_first>
  <behavior>
    - `POST /v1/agents/<uuid>/events/inject-test-event` with valid sysadmin Bearer + valid body → 200 with response containing `seq`, `agent_container_id`, `correlation_id="test:<orig>"`, and `test_event=true`. The agent_events table now contains a row with kind=reply_sent, correlation_id=`test:<orig>`.
    - Same POST + AP_ENV=prod → 404 NOT_FOUND. The endpoint is INVISIBLE: even with a valid sysadmin Bearer, prod returns 404 (route not registered).
    - Same POST + AP_SYSADMIN_TOKEN unset → 404 NOT_FOUND. Defense in depth: the route is also gated on the env-var being SET (otherwise a misconfigured dev box would expose admin actions to anyone presenting any Bearer).
    - Same POST + Bearer missing → 401 UNAUTHORIZED.
    - Same POST + wrong Bearer → 404 (opaque — same response as route-not-registered, keeps surface area opaque to probing).
    - Same POST + agent_id has no running container → 404 AGENT_NOT_FOUND with message about no running container (more specific).
    - Same POST + body missing required field → 400 INVALID_REQUEST OR 422 UNPROCESSABLE_ENTITY (FastAPI's default Pydantic validation response; either is acceptable).
    - Concurrent GET /v1/agents/:id/events?kinds=reply_sent&timeout_s=5 (long-poll waiting) gets WAKED within 1s when inject runs → returns 200 with the injected event in the events array, `next_since_seq` advanced.
    - Calling inject TWICE with the same correlation_id produces TWO rows (no idempotency dedup — correlation_id is harness-generated and the test exercises the wake mechanism per call). seq advances normally.
  </behavior>
  <action>
**Part A — Extend `api_server/src/api_server/routes/agent_events.py`.**

Read the full file. After the existing `get_events` handler (line ~244), APPEND the inject-test-event handler. Use a SECOND APIRouter instance scoped to this endpoint so main.py can conditionally include it without affecting the GET handler:

```python
# ============================================================================
# Phase 22b-08 — Gap 2 closure: synthetic event injection for SC-03 Gate B.
#
# This endpoint is registered ONLY when settings.env != 'prod' (see main.py).
# It writes a REAL row to the REAL agent_events table (golden rule 1: no
# mocks, no stubs) and triggers the same _get_poll_signal.set() that a
# normal watcher INSERT does. Purpose: prove the long-poll → INSERT →
# signal-wake → handler-fetch chain works end-to-end without depending on
# bot-self impersonation (which is filtered by channels.telegram.allowFrom)
# or MTProto user-impersonation (deferred per CONTEXT D-18a).
#
# Defense-in-depth gates (BOTH must pass):
#   1. Route invisible in prod (handled in main.py — separate router not
#      included when settings.env == 'prod').
#   2. Bearer == AP_SYSADMIN_TOKEN env-var value (handled here). NO
#      anonymous fallback. NO ownership-check path. If AP_SYSADMIN_TOKEN
#      is unset, the route returns 404 even for matching Bearer (a misconfigured
#      dev box must NOT expose admin actions to anyone who can craft a request).
#
# Synthetic-event marker: correlation_id is prefixed with "test:" so the
# row is distinguishable from real reply_sent events in retrospective
# analysis. The payload itself is pure ReplySentPayload (D-06 + D-08
# extra='forbid' compatible). Future cleanup can DELETE all rows where
# correlation_id LIKE 'test:%' without affecting real events.
# ============================================================================

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..services.event_store import insert_agent_event

# NOTE: Spike B 2026-04-19 — we deliberately do NOT import
# fetch_running_container_for_agent. That helper assumes URL agent_id is an
# agent_instances PK; the events router convention (verified empirically)
# uses agent_containers PK. Step 4 below does a direct SELECT on
# agent_containers by PK to match the URL-key contract.

inject_router = APIRouter()


class InjectTestEventBody(BaseModel):
    """Body schema for POST /v1/agents/:id/events/inject-test-event.

    Pydantic validates extras=ignore by default; we set extra='forbid' to
    catch typos like `chatid` vs `chat_id` at request-parse time rather
    than silently dropping the field. (Mirrors D-06 strict-shape discipline
    on event payloads — same hygiene at the request layer.)
    """
    model_config = {"extra": "forbid"}

    kind: str = Field(default="reply_sent", description="One of VALID_KINDS")
    correlation_id: str = Field(..., min_length=1, max_length=64,
                                description="Short hex/alphanum identifier; prefixed with 'test:' before insert")
    chat_id: str = Field(..., min_length=1, max_length=64,
                         description="Stored as payload.chat_id; mirrors real reply_sent shape")
    length_chars: int = Field(default=12, ge=0, le=10000,
                              description="Stored as payload.length_chars")


@inject_router.post("/agents/{agent_id}/events/inject-test-event", status_code=200)
async def inject_test_event(
    request: Request,
    agent_id: UUID,
    body: InjectTestEventBody,
    authorization: str = Header(default=""),
):
    # Step 1 — Bearer parse (same convention as GET handler; reuses _err).
    if not authorization.startswith("Bearer "):
        return _err(401, ErrorCode.UNAUTHORIZED,
                    "Bearer token required", param="Authorization")
    bearer = authorization[len("Bearer "):].strip()
    if not bearer:
        return _err(401, ErrorCode.UNAUTHORIZED,
                    "Bearer token is empty", param="Authorization")

    # Step 2 — defense-in-depth gate: AP_SYSADMIN_TOKEN MUST be set, AND
    # Bearer MUST equal it. Failure = 404 (not 403) so a probe gets the same
    # response as if the route didn't exist — keeps the surface area opaque
    # to non-sysadmin callers.
    sysadmin_token = os.environ.get(AP_SYSADMIN_TOKEN_ENV) or ""
    if not sysadmin_token or bearer != sysadmin_token:
        return _err(404, ErrorCode.AGENT_NOT_FOUND,
                    "no such route", param=None)

    # Step 3 — kind whitelist (V13 discipline; mirrors GET handler kinds CSV gate).
    if body.kind not in VALID_KINDS:
        return _err(400, ErrorCode.INVALID_REQUEST,
                    f"unknown kind: {body.kind!r}", param="kind")

    # Step 4 — Spike B 2026-04-19 EMPIRICALLY VERIFIED: URL `agent_id` is
    # `agent_containers.id` (container_row_id), NOT `agent_instances.id`.
    # We look the row up by container PK to confirm the container exists AND
    # is in 'running' status. This matches the GET /events handler convention
    # and the test_events_long_poll.py fixture pattern.
    pool = request.app.state.db
    async with pool.acquire() as conn:
        container_row = await conn.fetchrow(
            "SELECT id, container_status FROM agent_containers WHERE id = $1",
            agent_id,
        )
    if container_row is None or container_row["container_status"] != "running":
        return _err(404, ErrorCode.AGENT_NOT_FOUND,
                    f"agent {agent_id} has no running container",
                    param="agent_id")

    # By URL-key contract, agent_id IS the container_row_id. The duplicated
    # variable name keeps the handler reading naturally without hiding the
    # contractual identity.
    container_row_id = agent_id

    # Step 5 — Build the payload to match ReplySentPayload exactly. captured_at
    # is the synthesis timestamp (ISO 8601 with Z suffix per D-06 convention).
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {
        "chat_id": body.chat_id,
        "length_chars": body.length_chars,
        "captured_at": captured_at,
    }

    # Step 6 — INSERT the row (real DB write, real advisory-lock seq allocation
    # — golden rule 1). insert_agent_event is the same function the watcher uses;
    # we are NOT taking a different code path than production.
    #
    # Spike B 2026-04-19 EMPIRICALLY VERIFIED: insert_agent_event returns the
    # allocated seq as a plain `int` — NOT a dict, NOT a row. We capture
    # `inserted_seq: int` directly. The `ts` field for the response is
    # synthesized from `datetime.now(timezone.utc)` BEFORE the INSERT (within
    # ms of the Postgres now() the row gets — close enough for a synthetic-
    # event response; a SELECT-back is not warranted for the extra round-trip).
    test_correlation_id = f"test:{body.correlation_id}"
    response_ts = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        try:
            inserted_seq = await insert_agent_event(
                conn, container_row_id, body.kind, payload,
                correlation_id=test_correlation_id,
            )
        except Exception as exc:
            _log.exception("inject_test_event.insert_failed",
                           extra={"agent_id": str(agent_id),
                                  "container_row_id": str(container_row_id)})
            return _err(500, ErrorCode.INVALID_REQUEST,
                        f"insert failed: {type(exc).__name__}", param=None)

    # Step 7 — Wake any pending long-poll on the SAME URL agent_id key. Spike B
    # 2026-04-19 EMPIRICALLY VERIFIED: the long-poll route at
    # /v1/agents/{agent_id}/events treats URL agent_id as agent_containers.id
    # (the container_row_id), NOT as agent_instances.id. This is consistent
    # with the rest of the events router (test_events_long_poll.py:47-80
    # `seed_agent_container` returns the containers PK and uses it directly
    # in URLs) AND with the watcher spawn site (agent_lifecycle.py:494 passes
    # `agent_id=container_row_id` to run_watcher). So we wake the signal keyed
    # on container_row_id. (The variable name `agent_id` in this URL handler
    # is misleading — it IS container_row_id by convention; we keep the
    # variable name to match the existing route signature.)
    #
    # CRITICAL — see "URL key contract" note below the handler: this endpoint
    # MUST be called with URL agent_id == container_row_id (matching the GET
    # /events convention). The agent_existence step above (Step 4) already
    # uses fetch_running_container_for_agent(conn, agent_id) which assumes
    # agent_id is an agent_instances PK and returns the running container. If
    # callers send container_row_id in the URL (as the long-poll convention
    # requires), Step 4 needs to ALSO try a fetch-by-container-id path. See
    # Step 4 revision below.
    _get_poll_signal(request.app.state, agent_id).set()

    # Step 8 — Project the response. seq is the int returned from
    # insert_agent_event; ts is the response_ts captured pre-INSERT.
    ts_iso = response_ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return JSONResponse(
        status_code=200,
        content={
            "agent_id": str(agent_id),
            "agent_container_id": str(container_row_id),
            "seq": inserted_seq,
            "kind": body.kind,
            "correlation_id": test_correlation_id,
            "ts": ts_iso,
            "test_event": True,
        },
    )
```

(Add `from datetime import datetime, timezone` and `from pydantic import BaseModel, Field` to imports if not already present. The file likely has UUID and Header/Request/Query/JSONResponse imports already.)

**Part B — Extend `api_server/src/api_server/main.py`.**

Read the full file. Locate the existing `app.include_router(agent_events_route.router, prefix='/v1', tags=['agents'])` line (Plan 22b-05). Immediately AFTER it, add:

```python
        # Phase 22b-08 — Gap 2 closure: dev-only test-injection endpoint.
        # Conditional include keeps the route INVISIBLE in prod (FastAPI 404
        # for any path not registered). Mirrors openapi.json discipline at
        # main.py line 15.
        if app.state.settings.env != "prod":
            app.include_router(
                agent_events_route.inject_router,
                prefix="/v1",
                tags=["agents", "dev-only"],
            )
            logger.info("phase22b.inject_test_event.route_registered",
                        extra={"env": app.state.settings.env})
```

(If main.py reads settings differently — e.g., `settings = get_settings()` rather than `app.state.settings` — use the existing pattern. Read the surrounding code to match conventions.)

**Part C — Create `api_server/tests/test_events_inject_test_event.py`** (8 integration tests on real PG via testcontainers; mirror `test_events_long_poll.py` setup):

```python
"""Phase 22b-08 — POST /v1/agents/:id/events/inject-test-event integration tests.

Full FastAPI app wired against real PG17 via testcontainers. NO mocks.
Tests cover:
  1. Prod-mode 404 (route invisible)
  2. Sysadmin happy path returns 200 with seq + correlation_id prefix
  3. Bearer missing → 401
  4. Bearer wrong → 404 (defense in depth — opaque)
  5. AP_SYSADMIN_TOKEN unset → 404 even with matching Bearer (defense in depth)
  6. agent_id with no running container → 404 AGENT_NOT_FOUND
  7. End-to-end: long-poll waiting for events; inject; long-poll wakes within 1s
  8. Double inject with same correlation_id → 2 distinct rows, seq advances
"""
import asyncio
import os
import pytest
from uuid import uuid4, UUID
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.integration


async def _build_dev_client(monkeypatch):
    """Spin up a fresh app instance with AP_ENV=dev. monkeypatch the
    settings cache so the route registration sees env='dev'."""
    monkeypatch.setenv("AP_ENV", "dev")
    # Force settings cache invalidation if the codebase uses lru_cache on get_settings
    try:
        from api_server.config import get_settings
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()
    except Exception:
        pass
    from api_server.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    return app, AsyncClient(transport=transport, base_url="http://test")


async def _build_prod_client(monkeypatch):
    monkeypatch.setenv("AP_ENV", "prod")
    try:
        from api_server.config import get_settings
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()
    except Exception:
        pass
    # AP_CHANNEL_MASTER_KEY is required when AP_ENV=prod (per
    # crypto/age_cipher.py line 61). Use a real-shaped key for the test.
    monkeypatch.setenv("AP_CHANNEL_MASTER_KEY",
                       "2JAvJ9FwihbRyukvXDBnqVEK2Umf5ibHEy7KsFq5gTU=")
    from api_server.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    return app, AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def sysadmin_env(monkeypatch):
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


@pytest.mark.asyncio
async def test_inject_test_event_prod_returns_404(
    seed_running_container, sysadmin_env, monkeypatch,
):
    """Even with valid sysadmin Bearer, the route is invisible in prod."""
    app, client = await _build_prod_client(monkeypatch)
    async with app.router.lifespan_context(app):
        # Spike B B2: URL key is container_row_id (per events-router contract).
        container_row_id, _instance_id = seed_running_container
        resp = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 5},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert resp.status_code == 404, f"prod must return 404, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_inject_test_event_sysadmin_happy_path(
    seed_running_container, sysadmin_env, db_pool, monkeypatch,
):
    """Sysadmin Bearer + AP_ENV=dev + running agent → 200 with seq + correlation_id prefix."""
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        # Spike B B2: URL key is container_row_id; agent_container_id in
        # response equals the URL value (they are the same identity).
        container_row_id, _instance_id = seed_running_container
        resp = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "152099202", "length_chars": 12},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["test_event"] is True
    assert body["correlation_id"] == "test:abc1"
    assert body["kind"] == "reply_sent"
    assert int(body["seq"]) >= 1
    assert UUID(body["agent_container_id"]) == container_row_id
    assert UUID(body["agent_id"]) == container_row_id, \
        "agent_id in response echoes URL value (URL key contract)"

    # Verify the real DB row exists.
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT seq, kind, correlation_id, payload "
            "FROM agent_events WHERE agent_container_id=$1",
            container_row_id,
        )
    assert any(r["correlation_id"] == "test:abc1" and r["kind"] == "reply_sent"
               for r in rows), "row not in DB"


@pytest.mark.asyncio
async def test_inject_test_event_missing_bearer_401(
    seed_running_container, sysadmin_env, monkeypatch,
):
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        container_row_id, _instance_id = seed_running_container
        resp = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_inject_test_event_wrong_bearer_404_opaque(
    seed_running_container, sysadmin_env, monkeypatch,
):
    """Wrong Bearer returns 404 — surface area is opaque to non-sysadmin callers."""
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        container_row_id, _instance_id = seed_running_container
        resp = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
            headers={"Authorization": "Bearer some-random-not-sysadmin-token"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_inject_test_event_sysadmin_token_unset_404(
    seed_running_container, monkeypatch,
):
    """If AP_SYSADMIN_TOKEN is unset, the endpoint returns 404 even with matching Bearer."""
    monkeypatch.delenv("AP_SYSADMIN_TOKEN", raising=False)
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        container_row_id, _instance_id = seed_running_container
        resp = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
            headers={"Authorization": "Bearer anything"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inject_test_event_no_running_container_404(
    seed_agent_instance, sysadmin_env, monkeypatch,
):
    """A UUID with no matching agent_containers row → 404.

    Spike B B2: URL key is agent_containers.id. We pass an agent_instances
    UUID (which is, by definition, NOT in agent_containers); Step 4 of the
    handler does a SELECT on agent_containers WHERE id = $1 which returns
    None → 404. The error message says "no running container" because
    that's the user-facing contract from Step 4 (the handler does not
    leak the underlying URL-key contract to error consumers).
    """
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        # seed_agent_instance returns an agent_instance_id which is NOT a
        # valid container_row_id (different table, different UUID). Per
        # Step 4, the SELECT returns None and the handler returns 404.
        resp = await client.post(
            f"/v1/agents/{seed_agent_instance}/events/inject-test-event",
            json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"
    assert "no running container" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_inject_test_event_wakes_long_poll_within_1s(
    seed_running_container, sysadmin_env, monkeypatch,
):
    """End-to-end: long-poll waits → inject runs → long-poll wakes within 1s with the row."""
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        # Spike B B2: BOTH the inject AND the long-poll MUST use
        # container_row_id in the URL. Using instance_id on either side
        # (or mismatched on the two calls) breaks the wake — long-poll
        # times out with 0 events. Empirically verified 2026-04-19.
        container_row_id, _instance_id = seed_running_container

        async def injector():
            await asyncio.sleep(0.4)
            return await client.post(
                f"/v1/agents/{container_row_id}/events/inject-test-event",
                json={"correlation_id": "wake1", "chat_id": "152099202", "length_chars": 8},
                headers={"Authorization": f"Bearer {sysadmin_env}"},
                timeout=5.0,
            )

        injector_task = asyncio.create_task(injector())
        long_poll_resp = await client.get(
            f"/v1/agents/{container_row_id}/events?since_seq=0&kinds=reply_sent&timeout_s=3",
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=6.0,
        )
        inject_resp = await injector_task

    assert inject_resp.status_code == 200, inject_resp.text
    assert long_poll_resp.status_code == 200
    body = long_poll_resp.json()
    assert body["timed_out"] is False, f"long-poll TIMED OUT — signal-wake failed; body={body}"
    assert any(e.get("correlation_id") == "test:wake1" for e in body["events"]), \
        f"injected event not in long-poll response: {body['events']}"


@pytest.mark.asyncio
async def test_inject_test_event_double_inject_advances_seq(
    seed_running_container, sysadmin_env, monkeypatch,
):
    """Two POSTs with same correlation_id produce 2 rows; seq advances per insert."""
    app, client = await _build_dev_client(monkeypatch)
    async with app.router.lifespan_context(app):
        container_row_id, _instance_id = seed_running_container
        first = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "dup1", "chat_id": "1", "length_chars": 1},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
        second = await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "dup1", "chat_id": "1", "length_chars": 1},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
        )
    assert first.status_code == 200 and second.status_code == 200
    assert int(second.json()["seq"]) > int(first.json()["seq"])
```

**Fixture bodies (NEW — define INLINE at the top of `test_events_inject_test_event.py`).**

VERIFIED 2026-04-19 in this plan's revision: `api_server/tests/conftest.py` provides `db_pool` (per-test asyncpg pool — NOT `real_db_pool`, that name is wrong above and corrected to `db_pool` in the test bodies in this revision), `migrated_pg`, `async_client`, `mock_run_cell`, `docker_client`, `running_alpine_container`, `event_log_samples_dir`. It does NOT provide `seed_agent_instance` or `seed_running_container` — both are NEW for this test file.

The two NEW fixtures live INLINE in `api_server/tests/test_events_inject_test_event.py` (NOT in conftest.py — they're scoped to this test file). Add them at the top of the file, immediately after the `sysadmin_env` fixture.

Schema columns verified by reading the migrations during this revision:
- `agent_instances`: `id` (UUID PK), `user_id` (UUID FK NOT NULL), `recipe_name` (Text NOT NULL), `model` (Text NOT NULL), `name` (Text NOT NULL after migration 002 line 43), `created_at` (default NOW()), `last_run_at` (nullable), `total_runs` (default 0). Unique constraint `uq_agent_instances_user_name` on `(user_id, name)` — so `name` must be unique per user (use uuid4 suffix).
- `agent_containers` (migration 003 lines 61-110): `id` (UUID PK), `agent_instance_id` (UUID FK NOT NULL), `user_id` (UUID FK NOT NULL), `recipe_name` (Text NOT NULL), `container_id` (Text — nullable but we set a plausible-shaped fake), `container_status` (Text), `channel_type` (Text — nullable but set for clarity), plus several nullable cols (`channel_config_enc`, `boot_wall_s`, ts cols, `last_error`) we leave unset.

```python
from uuid import UUID, uuid4

import pytest_asyncio

from api_server.constants import ANONYMOUS_USER_ID


# ----- Fixture: seed_agent_instance (NEW) -----
# Inserts a fresh agent_instances row owned by ANONYMOUS_USER_ID. Returns
# the agent_instance_id (UUID). The unique-constraint on (user_id, name)
# requires the name to be uniqueified per test — uuid4 suffix handles it.
#
# Cleanup: the autouse `_truncate_tables` fixture in conftest.py (line 89)
# TRUNCATEs agent_instances RESTART IDENTITY CASCADE between tests, which
# cascades to agent_containers via FK and to agent_events via FK. So no
# explicit teardown DELETE is needed.

@pytest_asyncio.fixture
async def seed_agent_instance(db_pool) -> UUID:
    """Insert a single agent_instances row owned by the anonymous user.

    Returns the new agent_instance_id (UUID).
    """
    instance_id = uuid4()
    instance_name = f"inject-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes',
                    'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            ANONYMOUS_USER_ID,
            instance_name,
        )
    return instance_id


# ----- Fixture: seed_running_container (NEW) -----
# Inserts an agent_instances row PLUS an agent_containers row in 'running'
# status. Returns (agent_instance_id, agent_container_id) — both UUIDs.
# The fake container_id "test-fake-<hex>" mirrors the pattern in
# test_events_lifespan_reattach.py line 85 (which uses "deadbeef" * 8 = 64-hex
# pretend ID) — the inject endpoint validates container EXISTS in DB, NOT
# that the docker container is alive (that's the watcher's job).

@pytest_asyncio.fixture
async def seed_running_container(db_pool) -> tuple[UUID, UUID]:
    """Insert agent_instances + agent_containers rows in 'running' state.

    Returns (container_row_id, agent_instance_id) — container_row_id FIRST
    because it is the canonical URL key for /v1/agents/{?}/events* routes
    per Spike B 2026-04-19 (matches test_events_long_poll.py:47-80
    seed_agent_container convention). Tests destructure as
    `container_row_id, instance_id = seed_running_container`.

    The agent_instance_id is returned secondarily for the rare test that
    needs to seed a row in another instance-keyed table; most tests will
    discard it with `_`.
    """
    instance_id = uuid4()
    container_row_id = uuid4()
    instance_name = f"inject-run-{instance_id.hex[:8]}"
    fake_container_id = "test-fake-" + uuid4().hex[:12]
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes',
                    'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            ANONYMOUS_USER_ID,
            instance_name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               container_id, container_status, channel_type)
            VALUES ($1, $2, $3, 'hermes', $4, 'running', 'telegram')
            """,
            container_row_id,
            instance_id,
            ANONYMOUS_USER_ID,
            fake_container_id,
        )
    return container_row_id, instance_id
```

Cleanup is handled automatically by `_truncate_tables` autouse fixture in `api_server/tests/conftest.py` line 89 (TRUNCATEs agent_instances RESTART IDENTITY CASCADE between tests, FK-cascades to agent_containers + agent_events). NO explicit teardown DELETE is required from these fixtures.

Verify:
```bash
cd api_server && pytest -x tests/test_events_inject_test_event.py -v 2>&1 | tail -20
```
All 8 tests green.
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.routes.agent_events import router, inject_router, inject_test_event, InjectTestEventBody" && pytest -x tests/test_events_inject_test_event.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 8 { exit 0 } { exit 1 }' && pytest -x tests/test_events_long_poll.py tests/test_events_auth.py -q 2>&1 | tail -3 | grep -qE "passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@inject_router.post(\"/agents/{agent_id}/events/inject-test-event\")" api_server/src/api_server/routes/agent_events.py` returns `1`
    - `grep -c "async def inject_test_event" api_server/src/api_server/routes/agent_events.py` returns `1`
    - `grep -c "class InjectTestEventBody" api_server/src/api_server/routes/agent_events.py` returns `1`
    - `grep -c "inject_router = APIRouter" api_server/src/api_server/routes/agent_events.py` returns `1` (separate router from the GET handler)
    - `grep -c "_get_poll_signal(request.app.state, agent_id).set()" api_server/src/api_server/routes/agent_events.py` returns `>=1` (signal-wake wired)
    - `grep -c "insert_agent_event" api_server/src/api_server/routes/agent_events.py` returns `>=1` (real DB INSERT — no mocks)
    - `grep -c "fetch_running_container_for_agent" api_server/src/api_server/routes/agent_events.py` returns `>=1`
    - `grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/routes/agent_events.py` returns `>=2` (existing GET + new POST)
    - `grep -cE "f\"test:{body.correlation_id}\"|test:" api_server/src/api_server/routes/agent_events.py` returns `>=1` (correlation_id prefix discipline)
    - `grep -cE "settings.env *!= *\"prod\"|env *== *\"dev\"" api_server/src/api_server/main.py` returns `>=1` (conditional include)
    - `grep -c "inject_router" api_server/src/api_server/main.py` returns `>=1` (router referenced)
    - `cd api_server && pytest -x tests/test_events_inject_test_event.py -v 2>&1 | grep -cE "PASSED"` returns `>=8`
    - `cd api_server && pytest -x tests/test_events_long_poll.py tests/test_events_auth.py -q 2>&1 | tail -3` shows no regression
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no regression in any prior 22b test
  </acceptance_criteria>
  <done>POST /v1/agents/:id/events/inject-test-event handler created in agent_events.py via separate inject_router; main.py conditionally includes it ONLY when settings.env != 'prod'; 8 integration tests on real PG cover prod-404, sysadmin-200, missing/wrong Bearer, AP_SYSADMIN_TOKEN unset, no-running-container, end-to-end signal-wake within 1s, double-inject seq advance; no regression in prior 22b tests.</done>
</task>

<task type="auto">
  <name>Task 2: Add agent_harness.py send-injected-test-event-and-watch subcommand + rewire e2e Gate B + live 5/5 verification</name>
  <files>test/lib/agent_harness.py, test/e2e_channels_v0_2.sh</files>
  <read_first>
    - test/lib/agent_harness.py (THE file being extended — read in full; the existing `cmd_send_telegram_and_watch_events` at lines 300-408 is the structural analog; the `_post`/`_get` helpers at lines 67-100 are reused; the argparse builder at lines 413-457 is where the new subparser lands)
    - test/e2e_channels_v0_2.sh (THE file being extended — read in full; the Gate B step at lines 240-266 is what we are rewiring; the GATE_B_ENABLED preflight at lines 130-138 controls whether we run; the cleanup trap at line 119-128 stays as-is)
    - api_server/src/api_server/routes/agent_events.py (Task 1 output — confirm the EXACT response shape: agent_id, agent_container_id, seq, kind, correlation_id, ts, test_event)
    - .planning/STATE.md (line 144-150 — local-dev env shape; AP_CHANNEL_MASTER_KEY + TELEGRAM_CHAT_ID alias commands)
    - test/sc03-gate-c.md (the manual checklist — make sure our 22b-08 changes do NOT alter Gate C scope; we are NOT changing the manual flow, only the automated Gate B)
  </read_first>
  <action>
**Part A — Extend `test/lib/agent_harness.py`.**

Locate the existing `cmd_send_telegram_and_watch_events` function (line ~300). After it, ADD a new subcommand handler that POSTs to the inject-test-event endpoint then long-polls for the resulting event:

```python
# ---------- Gate B (revised — Phase 22b-08): inject-test-event ----------------

def cmd_send_injected_test_event_and_watch(args) -> int:
    """Gate B (Phase 22b-08 revision) — POST /events/inject-test-event then long-poll.

    Replaces the bot-self sendMessage path which was filtered by every
    recipe's channels.telegram.allowFrom (verifier gap 2). The injected
    event is a REAL row in the REAL agent_events table — golden rule 1
    holds — but the trigger is a sysadmin-only POST instead of a Telegram
    delivery. Validates the long-poll → INSERT → signal-wake → handler-
    fetch chain end-to-end. Real Telegram round-trip remains Gate C
    (manual, per-release).

    JSON output schema (mirrors send-telegram-and-watch-events):
      {"gate":"B","recipe":...,"correlation_id":...,"sent_text":...,
       "reply_sent_event":<event-row>|null,"wall_s":...,
       "verdict":"PASS"|"FAIL","error":null|<short str>}
    """
    corr = uuid.uuid4().hex[:4]
    chat_id = str(args.chat_id)
    inject_url = (
        f"{args.api_base}/v1/agents/{args.agent_id}/events/inject-test-event"
    )
    t0 = time.time()

    # Pre-query: capture since_seq cursor (same discipline as the legacy
    # subcommand — only events with seq > since_seq count toward the verdict).
    try:
        resp = _get(
            f"{args.api_base}/v1/agents/{args.agent_id}/events"
            f"?since_seq=0&timeout_s=1",
            headers={"Authorization": f"Bearer {args.bearer}"},
            timeout=5,
        )
        since_seq = resp.get("next_since_seq", 0)
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe, "correlation_id": corr,
            "sent_text": None, "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2), "verdict": "FAIL",
            "error": f"pre-query failed: {type(e).__name__}: {e}",
        }))
        return 2

    # Inject the synthetic event.
    inject_body = {
        "kind": "reply_sent",
        "correlation_id": corr,
        "chat_id": chat_id,
        "length_chars": 12,
    }
    sent_text = f"injected-event corr={corr} chat={chat_id}"
    try:
        injected = _post(
            inject_url, inject_body, timeout=10,
            headers={"Authorization": f"Bearer {args.bearer}"},
        )
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe, "correlation_id": corr,
            "sent_text": sent_text, "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2), "verdict": "FAIL",
            "error": f"inject failed: {type(e).__name__}: {e}",
        }))
        return 2
    if not injected.get("test_event"):
        # Either the route is invisible (prod-mode 404 with HTML body parsed
        # to ok:false), or the response shape drifted. Either way, FAIL with
        # the actual response so the operator can see what came back.
        print(json.dumps({
            "gate": "B", "recipe": args.recipe, "correlation_id": corr,
            "sent_text": sent_text, "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2), "verdict": "FAIL",
            "error": (
                f"inject returned non-test-event response: "
                f"{json.dumps(injected)[:300]}"
            ),
        }))
        return 1

    # Long-poll the events endpoint for the injected reply_sent. The event
    # is keyed by correlation_id="test:<corr>" per the inject handler's
    # prefix discipline.
    expected_corr_id = f"test:{corr}"
    try:
        url = (
            f"{args.api_base}/v1/agents/{args.agent_id}/events"
            f"?since_seq={since_seq}&kinds=reply_sent&timeout_s={args.timeout_s}"
        )
        resp = _get(
            url,
            headers={"Authorization": f"Bearer {args.bearer}"},
            timeout=args.timeout_s + 5,
        )
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe, "correlation_id": corr,
            "sent_text": sent_text, "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2), "verdict": "FAIL",
            "error": f"long-poll failed: {type(e).__name__}: {e}",
        }))
        return 1

    events = resp.get("events", []) or []
    match = next(
        (e for e in events
         if e.get("kind") == "reply_sent"
         and e.get("correlation_id") == expected_corr_id),
        None,
    )
    verdict = "PASS" if match else "FAIL"

    print(json.dumps({
        "gate": "B",
        "recipe": args.recipe,
        "correlation_id": corr,
        "sent_text": sent_text,
        "reply_sent_event": match,
        "wall_s": round(time.time() - t0, 2),
        "verdict": verdict,
        "error": (None if match
                  else f"no matching reply_sent event "
                       f"(expected correlation_id={expected_corr_id!r}); "
                       f"saw {len(events)} reply_sent events"),
    }))
    return 0 if verdict == "PASS" else 1
```

Then EXTEND `build_parser()` (line ~413). After the existing `b = sub.add_parser("send-telegram-and-watch-events", ...)` block, ADD:

```python
    c = sub.add_parser(
        "send-injected-test-event-and-watch",
        help="Gate B (Phase 22b-08): POST /inject-test-event + long-poll. "
             "Validates the API plumbing without depending on Telegram "
             "bot-self impersonation (which is filtered by allowFrom).",
    )
    c.add_argument("--api-base", required=True,
                   help="Base URL of the API server (e.g. http://localhost:8000)")
    c.add_argument("--agent-id", required=True,
                   help="agent_containers.id (container_row_id) — long-poll target. "
                        "Per Spike B 2026-04-19, the events-router URL key is "
                        "container_row_id, NOT agent_instance_id. The /v1/agents/:id/start "
                        "response returns this as `container_row_id` in the JSON body.")
    c.add_argument("--bearer", required=True,
                   help="AP_SYSADMIN_TOKEN value (POST /inject-test-event is sysadmin-only)")
    c.add_argument("--recipe", required=True,
                   help="Recipe name (cosmetic — appears in JSON envelope)")
    c.add_argument("--chat-id", required=True,
                   help="chat_id stored in the synthetic event payload (cosmetic; not delivered to Telegram)")
    c.add_argument("--timeout-s", type=int, default=10,
                   help="Long-poll window in seconds (default 10)")
    c.set_defaults(func=cmd_send_injected_test_event_and_watch)
```

Do NOT touch the existing `cmd_send_telegram_and_watch_events` function — keep it as-is. It remains available for AP_ENV=prod environments where the inject endpoint is invisible (the e2e script picks the right one based on env, see Part B). The legacy comment at lines 109-111 acknowledging the bot-self constraint is still accurate for THAT path.

**Part B — Rewire `test/e2e_channels_v0_2.sh`.**

Locate the existing Gate B step (lines 243-266). REPLACE the python3 invocation block:

Find:
```bash
    GATE_B_OUT=$(python3 test/lib/agent_harness.py send-telegram-and-watch-events \
      --api-base "$API_BASE" \
      --agent-id "$AGENT_ID" \
      --bearer "$AP_SYSADMIN_TOKEN" \
      --recipe "$RECIPE" \
      --token "$TELEGRAM_BOT_TOKEN" \
      --chat-id "$TELEGRAM_CHAT_ID" \
      --timeout-s 10 2>/dev/null || echo '{"gate":"B","verdict":"ERROR","error":"harness crashed"}')
```

Replace with:
```bash
    # Phase 22b-08 Gap 2 closure: prefer inject-test-event path (real DB
    # INSERT + signal-wake; no Telegram bot-self impersonation). The
    # legacy send-telegram-and-watch-events path is preserved as a
    # fallback for AP_ENV=prod environments where the inject route is
    # invisible (404). When the API is in dev and inject is available, use
    # it. When in prod (or when AP_USE_LEGACY_GATE_B=1 is set for explicit
    # opt-in), fall back to the bot-self path with its known structural
    # limitation (Gate C still owns the real-user flow).
    if [[ -z "${AP_USE_LEGACY_GATE_B:-}" ]] && python3 test/lib/agent_harness.py send-injected-test-event-and-watch --help >/dev/null 2>&1; then
      # Spike B B2 (2026-04-19): the events-router URL key is
      # agent_containers.id (container_row_id), NOT agent_instance_id.
      # AGENT_ID extracted at smoke time is agent_instance_id (line 166);
      # we need container_row_id from the /start response instead. The
      # /v1/agents/:id/start response returns it as `container_row_id`.
      CONTAINER_ROW_ID=$(jq -r '.container_row_id // ""' <<<"$START")
      if [[ -z "$CONTAINER_ROW_ID" ]]; then
        _fail "$RECIPE: /start response missing container_row_id (events router URL key per Spike B B2): $(jq -c '.' <<<"$START")"
        REPORT_LINES+=("$(jq -cn --arg r "$RECIPE" '{recipe:$r,gate:"B",verdict:"FAIL",error:"missing container_row_id"}')")
        cleanup
        continue
      fi
      GATE_B_OUT=$(python3 test/lib/agent_harness.py send-injected-test-event-and-watch \
        --api-base "$API_BASE" \
        --agent-id "$CONTAINER_ROW_ID" \
        --bearer "$AP_SYSADMIN_TOKEN" \
        --recipe "$RECIPE" \
        --chat-id "$TELEGRAM_CHAT_ID" \
        --timeout-s 10 2>/dev/null || echo '{"gate":"B","verdict":"ERROR","error":"harness crashed"}')
    else
      _info "Gate B falling back to legacy send-telegram-and-watch-events (AP_USE_LEGACY_GATE_B set OR new subcommand unavailable). NOTE: this path will FAIL because every recipe's allowFrom filters bot-self; documented in 22b-VERIFICATION.md gap 2."
      # Spike B B2: even the legacy bot-self fallback needs container_row_id
      # for the long-poll URL — the URL-key contract is the SAME (the
      # bot-self path was double-broken: allowFrom AND URL key).
      CONTAINER_ROW_ID="${CONTAINER_ROW_ID:-$(jq -r '.container_row_id // ""' <<<"$START")}"
      GATE_B_OUT=$(python3 test/lib/agent_harness.py send-telegram-and-watch-events \
        --api-base "$API_BASE" \
        --agent-id "$CONTAINER_ROW_ID" \
        --bearer "$AP_SYSADMIN_TOKEN" \
        --recipe "$RECIPE" \
        --token "$TELEGRAM_BOT_TOKEN" \
        --chat-id "$TELEGRAM_CHAT_ID" \
        --timeout-s 10 2>/dev/null || echo '{"gate":"B","verdict":"ERROR","error":"harness crashed"}')
    fi
```

Do NOT touch any other line in the script. The Gate B preflight at lines 130-138 still requires AP_SYSADMIN_TOKEN + TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID; the new path only USES the first and the third (chat_id is cosmetic for the synthetic payload), but the bot-token requirement is preserved as an opt-out switch.

**Part C — Live verification (golden rule 5 — test against real infra; golden rule 4 — root cause if it fails).**

Pre-flight (same shape as Plan 22b-07 Task 2 Part B):
```bash
test -n "${AP_CHANNEL_MASTER_KEY:-}" || { echo "MISSING AP_CHANNEL_MASTER_KEY"; exit 2; }
test -n "${AP_SYSADMIN_TOKEN:-}" || { echo "MISSING AP_SYSADMIN_TOKEN"; exit 2; }
test -n "${TELEGRAM_BOT_TOKEN:-}" || { echo "MISSING TELEGRAM_BOT_TOKEN"; exit 2; }
test -n "${TELEGRAM_CHAT_ID:-}${TELEGRAM_USER_CHAT_ID:-}" || { echo "MISSING TELEGRAM_CHAT_ID"; exit 2; }
test -n "${ANTHROPIC_API_KEY:-}" || { echo "MISSING ANTHROPIC_API_KEY"; exit 2; }
test -n "${OPENROUTER_API_KEY:-}" || { echo "MISSING OPENROUTER_API_KEY"; exit 2; }
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-$TELEGRAM_USER_CHAT_ID}"
docker ps --format '{{.Names}}' | grep -E '^(ap-recipe-)' | xargs -r docker rm -f >/dev/null 2>&1 || true
curl -fsS http://localhost:8000/healthz >/dev/null 2>&1 || { echo "API not up"; exit 2; }
# AP_ENV must be dev for the inject route to be registered:
test "$(curl -fsS http://localhost:8000/openapi.json 2>/dev/null | jq -r '.paths | keys[]' | grep -c 'inject-test-event' || echo 0)" -ge 1 || { echo "inject route not registered — confirm API is running with AP_ENV=dev (see api_server/src/api_server/main.py)"; exit 2; }
```

Run the FULL e2e suite (all 5 recipes × 3 rounds Gate A + 5 × 1 Gate B):
```bash
bash test/e2e_channels_v0_2.sh 2>&1 | tee /tmp/22b-08-full-gate.log
GATE_RC=$?
echo "exit code: $GATE_RC"
```

**Empirical PASS criteria** (Gate A 15/15 AND Gate B 5/5 — full SC-03 closure):
- `$GATE_RC` == `0`
- `cat e2e-report.json | jq -r '[.[] | select(.gate=="A" and .verdict=="PASS")] | length'` returns `15`
- `cat e2e-report.json | jq -r '[.[] | select(.gate=="A" and .verdict=="FAIL")] | length'` returns `0`
- `cat e2e-report.json | jq -r '[.[] | select(.gate=="B" and .verdict=="PASS")] | length'` returns `5`
- `cat e2e-report.json | jq -r '[.[] | select(.gate=="B" and .verdict=="FAIL")] | length'` returns `0`
- `cat e2e-report.json | jq -r '[.[] | select(.gate=="B")] | .[].correlation_id'` shows 5 distinct correlation_ids (one per recipe; each MUST appear in its matching reply_sent_event.correlation_id with the `test:` prefix in the row)

If Gate A FAILS (after Plan 22b-07 closes openclaw), root-cause: was a wave-5 plan applied out of order? Confirm Plan 22b-07 ran first OR test in isolation.

If Gate B FAILS for any recipe: read the JSON line for that recipe; common modes:
- `error="inject failed: ..."` — the inject endpoint isn't registered (AP_ENV != dev) OR AP_SYSADMIN_TOKEN doesn't match what's in env. Investigate; do NOT bandage.
- `error="no matching reply_sent event"` — the long-poll didn't see the row. Either the signal-wake fired but the long-poll wasn't running (race), or the signal didn't fire (handler bug). Read the API server logs from /tmp for `phase22b.inject_test_event` and `event_store.insert_agent_event` lines.
- `error="non-test-event response: ..."` — the response shape from inject is wrong (Task 1 implementation drift). Compare against the contract documented in objective.

Rerun Gate B in isolation if needed:
```bash
bash test/e2e_channels_v0_2.sh --rounds 1 2>&1 | tee /tmp/22b-08-rerun.log
```
  </action>
  <verify>
    <automated>set -e; grep -c "send-injected-test-event-and-watch" test/lib/agent_harness.py | grep -q ^[1-9] && grep -c "cmd_send_injected_test_event_and_watch" test/lib/agent_harness.py | grep -q ^[1-9] && grep -c "send-injected-test-event-and-watch" test/e2e_channels_v0_2.sh | grep -q ^[1-9] && python3 test/lib/agent_harness.py send-injected-test-event-and-watch --help >/dev/null 2>&1 && cat e2e-report.json | python3 -c "import json,sys; rep=json.load(sys.stdin); a=[r for r in rep if r.get('gate')=='A' and r.get('verdict')=='PASS']; b=[r for r in rep if r.get('gate')=='B' and r.get('verdict')=='PASS']; assert len(a)==15, f'Gate A pass={len(a)}'; assert len(b)==5, f'Gate B pass={len(b)}'; print('Gate A 15/15 + Gate B 5/5 PASS')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def cmd_send_injected_test_event_and_watch" test/lib/agent_harness.py` returns `1`
    - `grep -c "send-injected-test-event-and-watch" test/lib/agent_harness.py` returns `>=2` (handler + argparse subparser)
    - `grep -c "f\"test:{corr}\"" test/lib/agent_harness.py` returns `>=1` (correlation_id prefix discipline match)
    - `python3 test/lib/agent_harness.py send-injected-test-event-and-watch --help 2>&1 | grep -ci "POST /inject-test-event\|inject-test-event"` returns `>=1`
    - `python3 test/lib/agent_harness.py --help 2>&1 | grep -c "send-injected-test-event-and-watch"` returns `>=1` (subcommand visible)
    - `grep -c "AP_USE_LEGACY_GATE_B" test/e2e_channels_v0_2.sh` returns `>=1` (escape hatch documented)
    - `grep -c "send-injected-test-event-and-watch" test/e2e_channels_v0_2.sh` returns `>=1`
    - The full e2e run (live) wrote a fresh `e2e-report.json`: file mtime is within 30 minutes of the test run; AND has BOTH 15 Gate A PASS AND 5 Gate B PASS rows
    - The legacy `cmd_send_telegram_and_watch_events` function is PRESERVED (not deleted): `grep -c "def cmd_send_telegram_and_watch_events" test/lib/agent_harness.py` returns `1`
    - No agent containers leaked: `docker ps --filter "name=ap-recipe" --format '{{.ID}}' | wc -l` returns `0`
  </acceptance_criteria>
  <done>agent_harness.py gains a third subcommand POSTing to inject-test-event; e2e_channels_v0_2.sh defaults to the new path with an AP_USE_LEGACY_GATE_B escape hatch; live full e2e run produces 15/15 Gate A + 5/5 Gate B PASS in e2e-report.json; legacy bot-self path preserved for prod/opt-out scenarios; no container leaks.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP client → POST /v1/agents/:id/events/inject-test-event | Bearer + JSON body cross here; defense-in-depth: AP_ENV=prod hides the route entirely (FastAPI 404 for unregistered path); Bearer must equal AP_SYSADMIN_TOKEN env value or 404 (not 403) so the surface is opaque |
| Inject handler → insert_agent_event(real PG) | Real DB write; advisory-lock seq allocation per D-16; no in-memory fake (golden rule 1) |
| Inject handler → _get_poll_signal(app.state, agent_id).set() | Same primitive the watcher uses; the signal is per-agent-instance-id (not per-container-row-id) — confirmed by reading watcher_service line 553 + 566 |
| harness `--bearer` arg → POST Authorization header | The bearer value originates from the e2e script's $AP_SYSADMIN_TOKEN env (never logged; never in stdout JSON envelope per existing harness security notes lines 44-48) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-08-01 | Elevation of Privilege | Inject endpoint exposed in prod | mitigate | Conditional `app.include_router` ONLY when `settings.env != 'prod'` (Task 1 Part B). Even with valid sysadmin Bearer + valid body, prod returns 404 (route not registered). Test `test_inject_test_event_prod_returns_404` is the regression guard. Defense-in-depth gate #2: handler ALSO checks `AP_SYSADMIN_TOKEN` env-var is set AND matches Bearer; if env-var is unset (which it should be in prod by convention), the handler returns 404 even if the route accidentally got registered. |
| T-22b-08-02 | Elevation of Privilege | Sysadmin Bearer comparison | mitigate | Equality check on env-var value. Per Plan 22b-05 threat-register row 1 (T-22b-05-01), constant-time comparison is documented as out-of-scope for the local-only sysadmin surface; this plan inherits that posture. The opaque-404 response on Bearer mismatch (vs. 403 with reason) reduces signal to a probing attacker. |
| T-22b-08-03 | Information Disclosure | Synthetic events pollute real telemetry | mitigate | correlation_id prefix `test:` makes synthetic rows trivially distinguishable. Future cleanup: `DELETE FROM agent_events WHERE correlation_id LIKE 'test:%'`. Documented in objective + handler comment. |
| T-22b-08-04 | Tampering | Body field injection (e.g. kind=DROP TABLE) | mitigate | Pydantic InjectTestEventBody with `extra='forbid'` and `kind: str` validated against `VALID_KINDS` whitelist (Step 3 of handler). Payload values flow into `insert_agent_event` which uses parameterized SQL (V13 discipline from Plan 22b-02). Tested in `test_inject_test_event_*` integration suite. |
| T-22b-08-05 | Denial of Service | Inject flood from compromised dev box | accept | Rate-limit middleware (api_server/src/api_server/services/rate_limit.py) applies per-IP limits at the FastAPI layer. Per-agent INSERT throughput is bounded by the advisory-lock seq allocation (D-16 spike-05 measured 200 writes / 130ms = ~1.5K writes/s). For a developer's laptop this is non-issue; for a misconfigured shared dev box, the rate-limit middleware is the enforcement point. |
| T-22b-08-06 | Spoofing | Wrong correlation_id prefix masks synthetic rows | accept | Correlation_id `test:` prefix is convention not contract. A future analyst querying for synthetic rows would do `WHERE correlation_id LIKE 'test:%'`; if a real watcher ever produces a `test:` correlation_id (very unlikely — real correlation IDs come from D-07 user-bot prompt embedding, which has no `test:` prefix discipline), the query would over-match. Acceptable: the contamination volume from this corner case is bounded by the test environment's run frequency, and a stricter discipline (separate boolean column) would require a migration. |
| T-22b-08-07 | Information Disclosure | Long-poll handler doesn't filter synthetic events out for normal callers | accept | Today's GET handler returns ALL reply_sent rows; it does not distinguish synthetic from real. This is the correct behavior for the Gate B harness (which needs to see the synthetic row). Future frontend consumers of /events MAY want a `?include_test=false` filter; out of scope for 22b. Documented as future enhancement. |
| T-22b-08-08 | Repudiation | Synthetic events claim to be real reply_sent rows | accept | The `correlation_id="test:<orig>"` prefix is the audit trail. Combined with structured logging in the inject handler (`_log` includes agent_id + container_row_id + the correlation_id), reconstructing "who injected what when" is trivial from API logs. |
</threat_model>

<verification>
- `python3 -c "from api_server.routes.agent_events import inject_router, inject_test_event, InjectTestEventBody"` exits 0
- `cd api_server && pytest -x tests/test_events_inject_test_event.py -v 2>&1 | tail -15` shows 8 PASSED
- No regression: `cd api_server && pytest -x tests/test_events_long_poll.py tests/test_events_auth.py tests/test_events_lifespan_reattach.py tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py -v 2>&1 | tail -10` shows green
- `python3 test/lib/agent_harness.py send-injected-test-event-and-watch --help` succeeds
- Live e2e run: `e2e-report.json` shows Gate A 15/15 + Gate B 5/5 (Task 2 acceptance criteria)
- Prod-mode gate proven: the prod-404 test is in the integration suite (test_inject_test_event_prod_returns_404)
- AP_SYSADMIN_TOKEN-unset gate proven: test_inject_test_event_sysadmin_token_unset_404
- Real DB INSERT proven: test_inject_test_event_sysadmin_happy_path queries the agent_events table directly via real_db_pool
- Real signal-wake proven: test_inject_test_event_wakes_long_poll_within_1s asserts the long-poll receives the row within 3s window
- No container leaks after the live run: `docker ps --filter name=ap-recipe` is empty
</verification>

<success_criteria>
1. POST /v1/agents/:id/events/inject-test-event handler in agent_events.py via separate `inject_router`; conditionally registered in main.py ONLY when `settings.env != 'prod'`
2. Defense-in-depth: prod returns 404 (route invisible), AP_SYSADMIN_TOKEN unset returns 404 (env-var gate), wrong Bearer returns 404 (opaque), missing Bearer returns 401
3. Real DB INSERT via existing `insert_agent_event` (no mocks; golden rule 1); correlation_id prefixed `test:` for synthetic-row distinguishability
4. Signal-wake via `_get_poll_signal(app.state, agent_id).set()` after successful INSERT; long-poll wakes within 1s in integration test
5. 8 integration tests on real PG via testcontainers cover prod-404, sysadmin-200, missing/wrong Bearer, AP_SYSADMIN_TOKEN unset, no-running-container, end-to-end wake, double-inject seq advance
6. agent_harness.py gains `send-injected-test-event-and-watch` subcommand; legacy `send-telegram-and-watch-events` PRESERVED for AP_ENV=prod / AP_USE_LEGACY_GATE_B fallback
7. e2e_channels_v0_2.sh defaults to the new path; live run produces Gate A 15/15 + Gate B 5/5 PASS in e2e-report.json
8. No regression in any prior 22b test (test_events_long_poll, test_events_auth, test_events_lifespan_reattach, test_events_lifecycle_*)
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-08-SUMMARY.md` with:
- Exact handler shape committed to agent_events.py (lines added; the 8-step canonical flow used)
- Exact main.py conditional include block (lines added)
- The 8 integration test names + measured wall times for the signal-wake test (should be <1s)
- The harness subcommand shape (mirror existing `send-telegram-and-watch-events` doc style)
- The e2e script Gate B step before/after diff
- Live e2e measurements: per-recipe Gate B wall_s, total run wall time, e2e-report.json summary line
- Cleanup proof: `docker ps --filter name=ap-recipe` returns empty post-run
- Honest scope notes:
  - Gate B now validates the API plumbing chain (long-poll ↔ INSERT ↔ signal-wake ↔ handler-fetch). Real Telegram round-trip remains Gate C (manual, per-release).
  - The legacy bot-self path is PRESERVED but documented as broken-by-design (allowFrom filtering); operators who insist on running it can set AP_USE_LEGACY_GATE_B=1.
  - Synthetic events use `correlation_id` prefix `test:` for retrospective distinguishability; future cleanup `DELETE WHERE correlation_id LIKE 'test:%'`.
- Cross-reference to Plan 22b-07 (which also writes e2e-report.json — coordination note: Plan 22b-08 is the LAST one to write the file; its run is authoritative).
</output>
