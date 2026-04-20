"""Agent event-stream long-poll endpoint (Phase 22b-05) + dev-only inject (Phase 22b-08).

Two endpoints exposed via TWO routers (so main.py can conditionally include
the inject route when ``settings.env != 'prod'``):

  ``GET /v1/agents/:id/events`` (always registered)
      Long-poll for new agent_events rows.

  ``POST /v1/agents/:id/events/inject-test-event`` (dev-only — Phase 22b-08)
      Sysadmin-only synthetic event injection for SC-03 Gate B closure.
      Writes a REAL row to the REAL agent_events table (golden rule 1 —
      no mocks) then wakes the same long-poll signal a watcher INSERT does.
      Defense-in-depth: route invisible in prod (separate router not
      included by main.py) AND handler requires Bearer == AP_SYSADMIN_TOKEN
      env value (404 if either gate fails). See Phase 22b-08 plan + Spike B
      2026-04-19 for the URL-key contract evidence (URL ``agent_id`` IS
      ``agent_containers.id`` for ALL events-router endpoints).

Canonical flow (short — no runner call):

  1. Parse ``Authorization: Bearer <token>`` — D-15 auth posture
  2. If Bearer == AP_SYSADMIN_TOKEN -> bypass ownership; else:
     Resolve user_id via ``require_user`` (plan 22c-05 / 22c-06) —
     authenticated session cookie mandatory for the non-sysadmin path;
     Lookup agent_instance by (agent_id, user_id); 404 if missing;
     Ownership check enforced at the SQL layer by fetch_agent_instance's
     user_id filter (defense in depth).
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

Auth posture (D-15):

- Bearer is REQUIRED. Missing or empty -> 401 UNAUTHORIZED.
- If Bearer matches ``os.environ[AP_SYSADMIN_TOKEN_ENV]`` (when set),
  skip the ownership check entirely (sysadmin bypass for the test
  harness in Plan 22b-06).
- Otherwise resolve ``user_id`` via ``require_user`` (authenticated
  ``ap_session`` cookie mandatory for the non-sysadmin path) and
  ``fetch_agent_instance`` filters by user_id at the SQL layer —
  cross-tenant reads are impossible because the WHERE clause includes
  user_id (defense in depth).

Concurrent-poll cap (D-13): per-agent ``asyncio.Lock`` from
``app.state.event_poll_locks``. Second concurrent poll for the same
agent_id while the first is still waiting returns 429
CONCURRENT_POLL_LIMIT. Prevents a misbehaving client from spawning N
parallel pollers and pinning the pool.

V13 defense (kinds CSV): the ``kinds`` query param is parsed against
``models.events.VALID_KINDS`` whitelist BEFORE reaching the DB.
``fetch_events_after_seq`` then binds via ``$3::text[]`` — never
interpolated into SQL.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth.deps import require_user
from ..constants import AP_SYSADMIN_TOKEN_ENV
from ..models.errors import ErrorCode, make_error_envelope
from ..models.events import VALID_KINDS
from ..services.event_store import fetch_events_after_seq, insert_agent_event
from ..services.run_store import fetch_agent_instance
from ..services.watcher_service import _get_poll_lock, _get_poll_signal

router = APIRouter()
_log = logging.getLogger("api_server.agent_events")


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Build a Stripe-shape error envelope ``JSONResponse``.

    Mirrors ``routes/agent_lifecycle.py::_err`` byte-for-byte so every
    4xx/5xx response across the persistent-mode + event-stream surface
    uses the same construction.
    """
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )


def _project(
    rows: list[dict[str, Any]],
    since_seq: int,
    agent_id: UUID,
    timed_out: bool,
) -> JSONResponse:
    """Project event_store rows into the AgentEventsResponse JSON shape.

    asyncpg JSONB default codec returns the column as a JSON string
    (Plan 22b-02 SUMMARY decision); be defensive and json.loads() if so
    (the long-poll handler is the documented codec-conversion site).
    """
    events = []
    next_seq = since_seq
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        events.append({
            "seq": int(r["seq"]),
            "kind": r["kind"],
            "payload": payload,
            "correlation_id": r.get("correlation_id"),
            "ts": (
                r["ts"].isoformat()
                if hasattr(r["ts"], "isoformat")
                else str(r["ts"])
            ),
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
    """Long-poll for new agent_events rows.

    See module docstring for the 9-step flow + auth posture + V13/D-13
    rationale.
    """
    # --- Step 1: Bearer parse (D-15) ---
    if not authorization.startswith("Bearer "):
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token required",
            param="Authorization",
        )
    bearer = authorization[len("Bearer "):].strip()
    if not bearer:
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token is empty",
            param="Authorization",
        )

    # --- Step 2: sysadmin bypass OR ownership check ---
    # Sysadmin bypass MUST run first — it short-circuits BEFORE require_user
    # so the test harness (plan 22b-06) can probe events against a
    # synthetic agent_id without minting a session cookie. When NOT
    # sysadmin, require_user gates the path (Phase 22c-06) and
    # fetch_agent_instance's WHERE-user_id enforces cross-tenant
    # isolation at the SQL layer.
    sysadmin_token = os.environ.get(AP_SYSADMIN_TOKEN_ENV) or ""
    is_sysadmin = bool(sysadmin_token) and bearer == sysadmin_token

    pool = request.app.state.db
    if not is_sysadmin:
        session_result = require_user(request)
        if isinstance(session_result, JSONResponse):
            return session_result
        user_id: UUID = session_result

        async with pool.acquire() as conn:
            agent = await fetch_agent_instance(
                conn, agent_id, user_id
            )
        if agent is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )

    # --- Step 2b: kinds CSV parse + V13 whitelist defense ---
    kinds_set: set[str] | None = None
    if kinds:
        parsed = {k.strip() for k in kinds.split(",") if k.strip()}
        bad = parsed - VALID_KINDS
        if bad:
            return _err(
                400,
                ErrorCode.INVALID_REQUEST,
                f"unknown kind(s): {sorted(bad)}",
                param="kinds",
            )
        kinds_set = parsed

    # --- Step 3: per-agent long-poll lock (D-13) ---
    poll_lock = await _get_poll_lock(request.app.state, agent_id)
    if poll_lock.locked():
        return _err(
            429,
            ErrorCode.CONCURRENT_POLL_LIMIT,
            "another long-poll is already active for this agent",
            param="agent_id",
        )

    async with poll_lock:
        # --- Step 3b: CLEAR the wake signal BEFORE any fetch.
        # If we cleared AFTER the fast-path fetch, a watcher INSERT
        # between fetch and clear would have its .set() overwritten,
        # causing a missed wake. Clear-then-fetch means any set() after
        # the clear (i.e. any INSERT after our fetch) will survive for
        # the subsequent signal.wait() to observe.
        signal = _get_poll_signal(request.app.state, agent_id)
        signal.clear()

        # --- Step 4: DB scope 1 (fast path), wake signal armed ---
        async with pool.acquire() as conn:
            rows = await fetch_events_after_seq(
                conn, agent_id, since_seq, kinds_set
            )
        # --- Step 5: immediate return if rows exist ---
        if rows:
            return _project(rows, since_seq, agent_id, timed_out=False)

        # --- Step 6: NO DB held during the wait (Pitfall 4) ---
        try:
            await asyncio.wait_for(signal.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            # --- Step 7: timeout returns 200 empty ---
            return _project([], since_seq, agent_id, timed_out=True)

        # --- Step 8: DB scope 2 (re-query after signal fires) ---
        async with pool.acquire() as conn:
            rows = await fetch_events_after_seq(
                conn, agent_id, since_seq, kinds_set
            )
        # --- Step 9: project + return ---
        return _project(rows, since_seq, agent_id, timed_out=False)


# ============================================================================
# Phase 22b-08 — Gap 2 closure: synthetic event injection for SC-03 Gate B.
#
# This endpoint is registered ONLY when ``settings.env != 'prod'`` — main.py
# wraps the include_router call in an env conditional so a prod build never
# advertises the path (FastAPI 404 for unregistered routes). The HANDLER
# itself is also gated on ``AP_SYSADMIN_TOKEN`` env-var being SET AND matching
# the Bearer; either gate alone is enough, both together is defense-in-depth
# per CLAUDE.md golden rule 1 + threat-register T-22b-08-01.
#
# Why this exists: 22b-VERIFICATION.md gap 2 — the bot-self sendMessage path
# that ``cmd_send_telegram_and_watch_events`` uses is filtered by every
# recipe's ``channels.telegram.allowFrom: [tg:152099202]``. The bot's own
# outbound messages are NOT a real user, so no ``reply_sent`` event flows.
# Path A (allowFrom relaxation) is a security regression. Path C (formal
# demotion) loses the long-poll integration coverage. Path B (this endpoint)
# preserves the REAL DB INSERT + REAL signal-wake + REAL long-poll cycle —
# the synthetic origin is honest about what's being tested (the API plumbing,
# not the watcher's log-extraction).
#
# URL key contract: per Spike B 2026-04-19 (live-tested 3 ways), the
# events-router's URL ``agent_id`` IS ``agent_containers.id`` (container_row_id),
# NOT ``agent_instances.id``. Step 4 of the handler does a direct SELECT on
# agent_containers by PK to match this convention. Long-poll wakes ONLY
# when both inject AND long-poll use the SAME URL value (the signal is
# keyed on whatever the URL handler passed to ``_get_poll_signal``).
#
# Synthetic-event marker: ``correlation_id`` is prefixed with ``test:`` so
# the row is trivially distinguishable from real reply_sent events. Future
# cleanup: ``DELETE FROM agent_events WHERE correlation_id LIKE 'test:%'``.
# ============================================================================


inject_router = APIRouter()


class InjectTestEventBody(BaseModel):
    """Body schema for ``POST /v1/agents/:id/events/inject-test-event``.

    ``extra='forbid'`` catches typos like ``chatid`` vs ``chat_id`` at
    request-parse time rather than silently dropping the field. Mirrors
    D-06 strict-shape discipline at the request layer.
    """

    model_config = {"extra": "forbid"}

    kind: str = Field(default="reply_sent", description="One of VALID_KINDS")
    correlation_id: str = Field(
        ..., min_length=1, max_length=64,
        description="Short hex/alphanum identifier; prefixed with 'test:' before insert",
    )
    chat_id: str = Field(
        ..., min_length=1, max_length=64,
        description="Stored as payload.chat_id; mirrors real reply_sent shape",
    )
    length_chars: int = Field(
        default=12, ge=0, le=10000,
        description="Stored as payload.length_chars",
    )


@inject_router.post(
    "/agents/{agent_id}/events/inject-test-event", status_code=200
)
async def inject_test_event(
    request: Request,
    agent_id: UUID,
    body: InjectTestEventBody,
    authorization: str = Header(default=""),
):
    """POST handler — see module docstring + 22b-08 plan for full context."""
    # Step 1 — Bearer parse (same convention as GET handler; reuses _err).
    if not authorization.startswith("Bearer "):
        return _err(
            401, ErrorCode.UNAUTHORIZED,
            "Bearer token required", param="Authorization",
        )
    bearer = authorization[len("Bearer "):].strip()
    if not bearer:
        return _err(
            401, ErrorCode.UNAUTHORIZED,
            "Bearer token is empty", param="Authorization",
        )

    # Step 2 — defense-in-depth gate: AP_SYSADMIN_TOKEN MUST be set AND match.
    # Failure = 404 (not 403) so a probe gets the same response as if the
    # route didn't exist — keeps the surface area opaque to non-sysadmin
    # callers (T-22b-08-02). The empty-string fallback short-circuits when
    # the env var is unset (a misconfigured dev box must NOT expose admin
    # actions to anyone presenting any Bearer).
    sysadmin_token = os.environ.get(AP_SYSADMIN_TOKEN_ENV) or ""
    if not sysadmin_token or bearer != sysadmin_token:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            "no such route", param=None,
        )

    # Step 3 — kind whitelist (V13 discipline; mirrors GET handler kinds CSV gate).
    if body.kind not in VALID_KINDS:
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            f"unknown kind: {body.kind!r}", param="kind",
        )

    # Step 4 — Spike B 2026-04-19: URL ``agent_id`` is ``agent_containers.id``
    # (container_row_id), NOT ``agent_instances.id``. We look the row up by
    # container PK to confirm the container exists AND is in 'running'
    # status. This matches the GET /events handler convention and the
    # test_events_long_poll.py ``seed_agent_container`` fixture pattern.
    pool = request.app.state.db
    async with pool.acquire() as conn:
        container_row = await conn.fetchrow(
            "SELECT id, container_status FROM agent_containers WHERE id = $1",
            agent_id,
        )
    if container_row is None or container_row["container_status"] != "running":
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} has no running container",
            param="agent_id",
        )

    # By URL-key contract, ``agent_id`` IS the container_row_id. The aliased
    # variable name keeps the handler reading naturally without hiding the
    # contractual identity.
    container_row_id = agent_id

    # Step 5 — Build the payload to match ReplySentPayload exactly.
    # ``captured_at`` is the synthesis timestamp (ISO 8601 with Z suffix
    # per D-06 convention). Note: Pydantic's ReplySentPayload accepts
    # ``datetime`` for captured_at; the JSONB encoder serializes the dict
    # version we build here as a plain string — both shapes are valid on
    # the round-trip because the read-side AgentEvent.payload is loose dict.
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {
        "chat_id": body.chat_id,
        "length_chars": body.length_chars,
        "captured_at": captured_at,
    }

    # Step 6 — INSERT the row (real DB write, real advisory-lock seq
    # allocation — golden rule 1). ``insert_agent_event`` is the same
    # function the watcher uses; we are NOT taking a different code path
    # than production. Spike B 2026-04-19 EMPIRICALLY VERIFIED:
    # ``insert_agent_event`` returns the allocated seq as a plain ``int``
    # — NOT a dict, NOT a row. We capture ``inserted_seq: int`` directly.
    # ``ts`` for the response is synthesized from ``datetime.now(timezone.utc)``
    # BEFORE the INSERT (within ms of the Postgres ``now()`` the row gets —
    # close enough for a synthetic-event response; a SELECT-back is not
    # warranted for the extra round-trip).
    test_correlation_id = f"test:{body.correlation_id}"
    response_ts = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        try:
            inserted_seq = await insert_agent_event(
                conn, container_row_id, body.kind, payload,
                correlation_id=test_correlation_id,
            )
        except Exception as exc:
            _log.exception(
                "phase22b.inject_test_event.insert_failed",
                extra={
                    "agent_id": str(agent_id),
                    "container_row_id": str(container_row_id),
                },
            )
            return _err(
                500, ErrorCode.INTERNAL,
                f"insert failed: {type(exc).__name__}", param=None,
            )

    # Step 7 — Wake any pending long-poll on the SAME URL ``agent_id`` key.
    # Spike B 2026-04-19 EMPIRICALLY VERIFIED: the long-poll route at
    # ``/v1/agents/{agent_id}/events`` treats URL agent_id as
    # ``agent_containers.id`` (the container_row_id), NOT as
    # ``agent_instances.id``. So we wake the signal keyed on
    # ``container_row_id`` (== ``agent_id`` here). The signal is in-process
    # (same uvicorn worker) so ``signal.set()`` is observed by a concurrent
    # ``signal.wait()`` in the long-poll handler within microseconds.
    _get_poll_signal(request.app.state, agent_id).set()

    # Step 8 — Project the response. ``seq`` is the int returned from
    # ``insert_agent_event``; ``ts`` is the response_ts captured pre-INSERT.
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


__all__ = [
    "router", "get_events", "_err", "_project",
    "inject_router", "inject_test_event", "InjectTestEventBody",
]
