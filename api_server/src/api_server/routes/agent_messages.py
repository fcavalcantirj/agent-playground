"""Phase 22c.3-08 — in-app chat channel HTTP handlers.

Three endpoints:

  - ``POST   /v1/agents/:id/messages``        — fast-ack inbound (D-07, D-29)
  - ``GET    /v1/agents/:id/messages/stream`` — SSE outbound (D-01, D-25, D-26)
  - ``DELETE /v1/agents/:id/messages``        — clear conversation history (D-43, D-44)

Auth: every handler uses ``require_user`` (D-18, D-19) — the
``ap_session`` cookie is mandatory; ownership is filtered at the SQL
layer via :func:`fetch_agent_instance`.

URL contract: for ALL Phase 22c.3 endpoints the URL ``agent_id`` is
``agent_instances.id``. The handlers internally resolve to
``agent_containers.id`` when querying ``agent_events`` (which is keyed
on ``agent_container_id`` per Phase 22b convention). The existing
``GET /v1/agents/:id/events`` route's contract is UNCHANGED (it still
treats URL ``agent_id`` as ``agent_containers.id``).

D-09 channel naming: ``agent:inapp:<agent_instances.id>``. Outbox pump
(Plan 22c.3-07) JOINs ``agent_containers`` to derive the
``agent_instance_id`` from ``agent_container_id``; the SSE handler
subscribes via the same naming scheme.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..services import inapp_messages_store as ims
from ..services.run_store import fetch_agent_instance


router = APIRouter()
_log = logging.getLogger("api_server.agent_messages")


# Whitelisted kinds for the SSE stream + DELETE history sweep. Anything
# else (e.g. reply_sent) is excluded by design — the chat surface is
# scoped to the 3 inapp_* event kinds (D-13, D-24).
INAPP_KINDS: tuple[str, ...] = (
    "inapp_inbound",
    "inapp_outbound",
    "inapp_outbound_failed",
)

# BYOK leak defense (CONTEXT.md anti-pattern: chat content might
# accidentally carry an API key — refuse to persist). Matches the
# common envvar names + Anthropic / OpenAI / OpenRouter sk-* shape.
_BYOK_LEAK_RE = re.compile(
    r"(OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|sk-[a-zA-Z0-9]{40,})"
)


# SSE replay cap (D-26): if the client's Last-Event-Id is more than 500
# events behind, send the first 500 + emit ``replay_truncated`` and
# CONTINUE TO SUBSCRIBE. The stream stays open — replay_truncated is
# informational, not a close signal. Client backfills the trimmed
# range via GET /v1/agents/:id/events?kinds=inapp_*&since_seq=...
REPLAY_HARD_CAP = 500

# 30s heartbeat (Pitfall 8) — Cloudflare/middleboxes idle-disconnect at
# ~60s. sse-starlette emits ``: ping\n\n`` comment lines via this knob.
SSE_PING_S = 30


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Build a Stripe-shape error envelope ``JSONResponse``.

    Mirrors ``routes/agent_events.py::_err`` byte-for-byte so every
    4xx/5xx response across the persistent-mode + event-stream + chat
    surface uses the same construction.
    """
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category,
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/agents/:id/messages — fast-ack inbound (D-07, D-29)
# ---------------------------------------------------------------------------


class PostMessageRequest(BaseModel):
    """Request body for ``POST /v1/agents/:id/messages``.

    D-39 ``Idempotency-Key`` is sent as an HTTP header (consumed by
    ``IdempotencyMiddleware``); it is NOT a body field.

    Per D-41 there is no API-side cap on ``content`` length — the
    underlying recipe / bot may impose its own; we forward verbatim.
    Empty content is still rejected (``min_length=1``).
    """

    content: str = Field(..., min_length=1)


@router.post("/agents/{agent_id}/messages", status_code=202)
async def post_message(
    request: Request,
    agent_id: UUID,
    body: PostMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """D-07 + D-29: fast-ack 202 with ``{message_id}``. Dispatcher picks the row.

    9-step flow:

      1. Session cookie → ``user_id`` via ``require_user`` (D-18).
      2. Ownership at SQL — ``fetch_agent_instance`` filters by user_id;
         404 AGENT_NOT_FOUND if missing (NOT 403, to avoid existence leak).
      3. BYOK leak defense — refuse to persist content that looks like
         it carries an API key.
      4. ``insert_pending`` writes the row in 'pending' state.
      5. Return 202 with ``{message_id, status, queued_at}`` within ~50ms.

    The dispatcher loop (Plan 22c.3-05) picks up the row in <1s and
    forwards to the bot. Per D-46 this endpoint does NOT bump
    ``agent_instances.total_runs`` — that counter is reserved for
    ``/v1/runs`` (one-shot) and ``/v1/agents/:id/start`` (persistent).
    """
    # --- D-09: Idempotency-Key REQUIRED enforcement ---
    # Runs BEFORE require_user so a missing header is a request-shape
    # failure independent of auth state (Pitfall 8 — gating on auth
    # would risk a cross-user idempotency leak).
    if not idempotency_key or not idempotency_key.strip():
        return _err(
            400,
            ErrorCode.INVALID_REQUEST,
            "Idempotency-Key header is required",
            param="Idempotency-Key",
        )

    # --- Step 1: require_user (D-18) ---
    sess = require_user(request)
    if isinstance(sess, JSONResponse):
        return sess
    user_id: UUID = sess

    # --- Step 2: ownership (D-19) ---
    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
    if agent is None:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found", param="agent_id",
        )

    # --- Step 3: BYOK leak defense (CONTEXT.md anti-pattern) ---
    if _BYOK_LEAK_RE.search(body.content):
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "content appears to contain an API key — refusing to persist",
            param="content",
        )

    # --- Step 4: INSERT pending (Plan 22c.3-04 store seam) ---
    async with pool.acquire() as conn:
        message_id = await ims.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content=body.content,
        )

    # --- Step 5: 202 with message_id (D-29 fast-ack) ---
    return JSONResponse(
        status_code=202,
        content={
            "message_id": str(message_id),
            "status": "pending",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# GET /v1/agents/:id/messages — Phase 23-03 chat-history snapshot (D-03 + D-04)
# ---------------------------------------------------------------------------
#
# Default + max LIMIT come straight from REQUIREMENTS.md API-02 / D-04. The
# default of 200 covers ~50 user/assistant turns (each turn = 2 events) which
# matches mobile's typical chat-screen viewport without paginating; the cap of
# 1000 keeps an absent-minded `?limit=1000000` from scanning a multi-month
# conversation in one shot. Pagination is OUT of MVP per CONTEXT.md decisions.
_HISTORY_DEFAULT_LIMIT = 200
_HISTORY_MAX_LIMIT = 1000


@router.get("/agents/{agent_id}/messages", status_code=200)
async def get_messages(
    request: Request,
    agent_id: UUID,
    limit: int = _HISTORY_DEFAULT_LIMIT,
):
    """D-03 + D-04 + REQ API-02 — chat-history snapshot for the Chat screen.

    Mobile loads this on Chat-screen open. Returns terminal-state rows from
    ``inapp_messages`` (D-01 reuse — NO new tables) ordered by ``created_at``
    ASC, default limit=200, max=1000. ``done`` rows emit (user, assistant)
    pair; ``failed`` rows emit (user, error-shaped assistant) so the UI can
    render delivery-failed messages distinctly. ``pending``/``forwarded``
    rows are EXCLUDED (in-flight messages observed via SSE, not history).

    Step-by-step flow:

      1. Validate ``limit`` (D-04): values < 1 → 400 INVALID_REQUEST envelope
         with param="limit"; values > 1000 are silently clamped server-side.
         The clamp runs BEFORE the auth check so a client probing the
         endpoint with a malformed limit doesn't need a valid session to
         learn the contract.
      2. ``require_user`` (D-18) — same pattern as POST/SSE/DELETE on
         this router; 401 with ap_session envelope on missing/invalid
         session cookie.
      3. Ownership at SQL — ``fetch_agent_instance`` filters by user_id;
         404 AGENT_NOT_FOUND if the agent doesn't exist OR doesn't belong
         to the caller (T-23-V4-XUSER mitigation: NOT 403, avoid existence
         leak).
      4. ``list_history_for_agent`` — single SQL seam in
         ``services/inapp_messages_store.py``; never inline SQL outside
         that module.
      5. Map rows to events (D-03):
            - ``done``    → (role=user, content=im.content)
                            + (role=assistant, kind=message,
                               content=im.bot_response)
            - ``failed``  → (role=user, content=im.content)
                            + (role=assistant, kind=error,
                               content="⚠️ delivery failed: <last_error>")
                            (verbatim prefix — mobile UI may match on it)
         Each event carries ``inapp_message_id`` so the client can dedup
         against SSE replays of the same row.
    """
    # --- Step 1: limit validation (D-04) ---
    if limit < 1:
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "limit must be >= 1", param="limit",
        )
    effective_limit = min(limit, _HISTORY_MAX_LIMIT)

    # --- Step 2: require_user (D-18) ---
    sess = require_user(request)
    if isinstance(sess, JSONResponse):
        return sess
    user_id: UUID = sess

    # --- Step 3: ownership (D-19) ---
    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
    if agent is None:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found", param="agent_id",
        )

    # --- Step 4: read terminal-state history (single SQL seam) ---
    async with pool.acquire() as conn:
        rows = await ims.list_history_for_agent(
            conn, agent_id=agent_id, limit=effective_limit,
        )

    # --- Step 5: row → event mapping (D-03) ---
    events: list[dict] = []
    for r in rows:
        created_iso = (
            r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat")
            else str(r["created_at"])
        )
        message_id = str(r["id"])
        # Every terminal row has a user message — emit it first.
        events.append({
            "role": "user",
            "kind": "message",
            "content": r["content"],
            "created_at": created_iso,
            "inapp_message_id": message_id,
        })
        # Assistant-side event keyed on status (D-03).
        if r["status"] == "done":
            events.append({
                "role": "assistant",
                "kind": "message",
                "content": r["bot_response"] or "",
                "created_at": created_iso,
                "inapp_message_id": message_id,
            })
        elif r["status"] == "failed":
            err_text = r.get("last_error") or "unknown error"
            events.append({
                "role": "assistant",
                "kind": "error",
                # Verbatim prefix per D-03 — mobile UI may match on this.
                "content": f"⚠️ delivery failed: {err_text}",
                "created_at": created_iso,
                "inapp_message_id": message_id,
            })
        # 'pending'/'forwarded' rows already filtered at SQL level.

    return JSONResponse(
        status_code=200, content={"messages": events},
    )


# ---------------------------------------------------------------------------
# DELETE /v1/agents/:id/messages — D-43, D-44 transactional 2-table delete
# ---------------------------------------------------------------------------


@router.delete("/agents/{agent_id}/messages")
async def delete_history(request: Request, agent_id: UUID):
    """D-43 + D-44: clear inapp_messages + agent_events (inapp_* kinds).

    Atomic 2-table delete in one transaction:

      1. ``inapp_messages`` rows for ``(agent_id, user_id)``.
      2. ``agent_events`` rows whose container's ``agent_instance_id``
         matches AND ``kind IN inapp_*`` (defense-in-depth V13 binding
         via ``kind = ANY($2::text[])`` — never interpolated into SQL).

    The ``agent_instances`` + ``agent_containers`` rows are UNTOUCHED
    (D-44 — deleting messages is a separate action from deleting the
    agent). Returns 204.
    """
    sess = require_user(request)
    if isinstance(sess, JSONResponse):
        return sess
    user_id: UUID = sess

    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
    if agent is None:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found", param="agent_id",
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await ims.delete_history_for_agent_user(
                conn, agent_id=agent_id, user_id=user_id,
            )
            # V13 defense (PATTERNS line 137-150): bind kinds via
            # ``$2::text[]`` — never interpolate into SQL even though
            # the values come from the module-level INAPP_KINDS tuple.
            await conn.execute(
                """
                DELETE FROM agent_events
                WHERE agent_container_id IN (
                    SELECT id FROM agent_containers
                    WHERE agent_instance_id = $1
                )
                  AND kind = ANY($2::text[])
                """,
                agent_id, list(INAPP_KINDS),
            )

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /v1/agents/:id/messages/stream — SSE outbound (D-01, D-25, D-26)
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/messages/stream")
async def messages_stream(
    request: Request,
    agent_id: UUID,
    last_event_id: str | None = Header(default=None, alias="Last-Event-Id"),
):
    """SSE outbound stream — D-01, D-25, D-26.

    URL contract: ``agent_id`` IS ``agent_instances.id`` for ALL
    Phase 22c.3 endpoints (POST /messages, GET /messages/stream,
    DELETE /messages). This DIFFERS from the Phase 22b
    ``GET /v1/agents/:id/events`` route which uses
    ``agent_containers.id`` — that route's contract is unchanged. The
    Phase 22c.3 router resolves ``agent_instances.id`` to the most-recent
    ``agent_containers.id`` internally before querying ``agent_events``.

    Stream lifecycle:

      1. ``require_user`` + ``fetch_agent_instance`` (ownership at SQL).
      2. Resolve container_row_id from ``agent_containers`` (prefer
         running, fall back to most-recent stopped). 404 if none.
      3. PG replay from ``Last-Event-Id`` capped at 500 events. If
         truncated, emit ``replay_truncated`` event AND CONTINUE.
      4. Capture ``current_max_seq`` AFTER replay (Pitfall 1 race window).
      5. Subscribe to redis channel ``agent:inapp:<agent_instance_id>``.
      6. Differential second replay for ``seq > last_yielded`` (live
         consumer de-duplicates via ``last_yielded_seq`` guard).
      7. Live-stream from Redis; ping every 30s (Pitfall 8); client
         disconnect terminates the generator.

    Pitfall 4 (two-scope DB): the SSE generator NEVER holds a connection
    across the redis subscribe loop. Each PG read opens its own scope
    that releases before the loop continues.
    """
    sess = require_user(request)
    if isinstance(sess, JSONResponse):
        return sess
    user_id: UUID = sess

    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
    if agent is None:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found", param="agent_id",
        )

    # Parse Last-Event-Id (D-25). Defensive: any non-int / negative
    # value is treated as "start from the beginning".
    since_seq = 0
    if last_event_id:
        try:
            since_seq = max(0, int(last_event_id))
        except ValueError:
            since_seq = 0

    redis_client = request.app.state.redis
    # D-09 channel naming: agent:inapp:<agent_instance_id>. URL agent_id
    # IS agent_instances.id for Phase 22c.3 endpoints.
    channel = f"agent:inapp:{agent_id}"
    inapp_kinds = set(INAPP_KINDS)

    # Resolve agent_instances.id → most-recent agent_containers.id BEFORE
    # querying agent_events (which is keyed on agent_container_id).
    # Prefer a running container; fall back to most-recently-created.
    # 404 if no container row exists.
    async with pool.acquire() as conn:
        container_row_id = await conn.fetchval(
            """
            SELECT id FROM agent_containers
            WHERE agent_instance_id = $1
            ORDER BY (stopped_at IS NULL) DESC, created_at DESC
            LIMIT 1
            """,
            agent_id,
        )
    if container_row_id is None:
        return _err(
            404, ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} has no container", param="agent_id",
        )

    async def event_generator():
        from ..services.event_store import fetch_events_after_seq

        # ----- Phase 1: PG replay (DB scope released at end) -----
        # fetch_events_after_seq is keyed on agent_container_id (= the
        # row id of the most-recent agent_containers row resolved above).
        async with pool.acquire() as conn:
            rows = await fetch_events_after_seq(
                conn, container_row_id, since_seq, inapp_kinds,
            )
            current_max_seq = await conn.fetchval(
                "SELECT COALESCE(MAX(seq), 0) FROM agent_events "
                "WHERE agent_container_id = $1 AND kind = ANY($2::text[])",
                container_row_id, list(INAPP_KINDS),
            )
        truncated = False
        if len(rows) > REPLAY_HARD_CAP:
            rows = rows[:REPLAY_HARD_CAP]
            truncated = True

        last_yielded_seq = since_seq
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            seq_int = int(r["seq"])
            yield ServerSentEvent(
                id=str(seq_int),
                event=r["kind"],
                data=json.dumps({
                    "seq": seq_int,
                    "kind": r["kind"],
                    "payload": payload,
                    "correlation_id": r.get("correlation_id"),
                    "ts": (
                        r["ts"].isoformat()
                        if hasattr(r["ts"], "isoformat")
                        else str(r["ts"])
                    ),
                }),
            )
            last_yielded_seq = max(last_yielded_seq, seq_int)
        if truncated:
            # D-26: emit informational event; stream STAYS OPEN. Client
            # uses GET /v1/agents/:id/events?kinds=inapp_*&since_seq=...
            # to fetch the events seq <= (since_seq + 500) that were
            # trimmed off.
            yield ServerSentEvent(
                event="replay_truncated",
                data=json.dumps({
                    "hint": (
                        "stream continues; backfill trimmed range via "
                        "GET /v1/agents/:id/events"
                    ),
                    "trimmed_above_seq": (
                        int(rows[-1]["seq"]) if rows else since_seq
                    ),
                }),
            )

        # ----- Phase 2: Subscribe + differential replay -----
        async with redis_client.pubsub() as pubsub:
            await pubsub.subscribe(channel)

            # Pitfall 1 mitigation: events INSERTed between phase 1's
            # query and the subscribe attach are LIVE-missable. Run
            # ANOTHER PG query for ``seq > last_yielded`` AFTER the
            # subscribe. Then attach the live consumer; the
            # last_yielded_seq guard de-duplicates any overlap with
            # subsequent live Redis messages carrying the same seq.
            async with pool.acquire() as conn:
                gap_rows = await fetch_events_after_seq(
                    conn, container_row_id, last_yielded_seq, inapp_kinds,
                )
            for r in gap_rows:
                seq_int = int(r["seq"])
                payload = r["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                yield ServerSentEvent(
                    id=str(seq_int), event=r["kind"],
                    data=json.dumps({
                        "seq": seq_int, "kind": r["kind"],
                        "payload": payload,
                        "correlation_id": r.get("correlation_id"),
                        "ts": (
                            r["ts"].isoformat()
                            if hasattr(r["ts"], "isoformat")
                            else str(r["ts"])
                        ),
                    }),
                )
                last_yielded_seq = max(last_yielded_seq, seq_int)

            # ----- Phase 3: live consumer -----
            while True:
                if await request.is_disconnected():
                    return
                try:
                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0,
                    )
                except Exception:
                    _log.exception(
                        "phase22c3.sse.pubsub_get_message_failed"
                    )
                    # Defensive re-subscribe + PG catch-up (Pitfall 4 redux).
                    try:
                        await pubsub.unsubscribe(channel)
                    except Exception:
                        pass
                    await pubsub.subscribe(channel)
                    async with pool.acquire() as conn:
                        catch_up = await fetch_events_after_seq(
                            conn, container_row_id,
                            last_yielded_seq, inapp_kinds,
                        )
                    for r in catch_up:
                        seq_int = int(r["seq"])
                        payload = r["payload"]
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        yield ServerSentEvent(
                            id=str(seq_int), event=r["kind"],
                            data=json.dumps({
                                "seq": seq_int, "kind": r["kind"],
                                "payload": payload,
                                "correlation_id": r.get("correlation_id"),
                                "ts": (
                                    r["ts"].isoformat()
                                    if hasattr(r["ts"], "isoformat")
                                    else str(r["ts"])
                                ),
                            }),
                        )
                        last_yielded_seq = max(last_yielded_seq, seq_int)
                    continue
                if msg is None:
                    continue
                data = msg["data"]
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8")
                try:
                    parsed = json.loads(data)
                    seq_int = int(parsed["seq"])
                    if seq_int <= last_yielded_seq:
                        # Already yielded via differential replay; the
                        # live message arrived after we caught up.
                        continue
                    yield ServerSentEvent(
                        id=str(seq_int),
                        event=parsed["kind"],
                        data=data,
                    )
                    last_yielded_seq = seq_int
                except Exception:
                    _log.exception("phase22c3.sse.malformed_redis_message")
                    continue

    return EventSourceResponse(event_generator(), ping=SSE_PING_S)


__all__ = [
    "router",
    "post_message",
    "get_messages",
    "delete_history",
    "messages_stream",
    "PostMessageRequest",
    "INAPP_KINDS",
    "REPLAY_HARD_CAP",
    "SSE_PING_S",
]
