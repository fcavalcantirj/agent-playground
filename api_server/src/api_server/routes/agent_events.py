"""Agent event-stream long-poll endpoint (Phase 22b-05).

One endpoint: ``GET /v1/agents/:id/events`` — long-poll with since_seq +
kinds filter + timeout_s.

Canonical flow (short — no runner call):

  1. Parse ``Authorization: Bearer <token>`` — D-15 auth posture
  2. If Bearer == AP_SYSADMIN_TOKEN -> bypass ownership; else:
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

Auth posture (D-15):

- Bearer is REQUIRED. Missing or empty -> 401 UNAUTHORIZED.
- If Bearer matches ``os.environ[AP_SYSADMIN_TOKEN_ENV]`` (when set),
  skip the ownership check entirely (sysadmin bypass for the test
  harness in Plan 22b-06).
- Otherwise resolve ``user_id = ANONYMOUS_USER_ID`` (Phase 19 MVP seam)
  and ``fetch_agent_instance`` filters by user_id at the SQL layer —
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
from typing import Any
from uuid import UUID

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
    sysadmin_token = os.environ.get(AP_SYSADMIN_TOKEN_ENV) or ""
    is_sysadmin = bool(sysadmin_token) and bearer == sysadmin_token

    pool = request.app.state.db
    if not is_sysadmin:
        async with pool.acquire() as conn:
            agent = await fetch_agent_instance(
                conn, agent_id, ANONYMOUS_USER_ID
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


__all__ = ["router", "get_events", "_err", "_project"]
