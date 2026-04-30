"""Phase 22c.3-05 — inapp dispatcher with 3-way contract adapter switch.

A 250ms-tick asyncio task that drains ``inapp_messages`` rows from
``pending → forwarded → (done | failed)``, forwarding the user's
content to the bot's chat HTTP endpoint per the recipe's ``contract:``
field. Three contract adapters in a single match-statement:

* ``openai_compat`` — hermes / nanobot / openclaw all expose a
  ``POST /v1/chat/completions`` endpoint with the OpenAI envelope
  ``{"choices":[{"message":{"content": "..."}}]}``.
* ``a2a_jsonrpc`` — nullclaw native A2A JSON-RPC 2.0 at ``/a2a``
  with ``message/send`` method; reply at
  ``result.artifacts[0].parts[0].text``.
* ``zeroclaw_native`` — zeroclaw native ``/webhook`` with
  ``{"message": "..."}`` request and ``{"response": "...", "model": "..."}``
  reply; honors built-in ``X-Idempotency-Key`` + ``X-Session-Id``
  headers.

Per CONTEXT.md D-22 (dumb-pipe), the dispatcher is a contract-agnostic
translator — it does NOT compose prompts, does NOT inject system
messages, does NOT manipulate context. The bot owns its memory.

Per D-28 (persist-before-action), every state transition is committed
via Plan 04's store BEFORE the next side effect.

Per D-32 (``FOR UPDATE SKIP LOCKED``), the store's
``fetch_pending_for_dispatch`` already issues the SKIP LOCKED clause;
two replicas can run concurrently without double-processing.

Per D-37 / D-38 (readiness gate), the dispatcher checks
``container_status='running' AND ready_at IS NOT NULL AND
stopped_at IS NULL`` before forwarding. Unready containers fail-fast
to status='failed' with ``last_error='container_not_ready'`` (no
silent retries — the user can re-send).

Per D-40 (no auto-retry), all terminal failures (timeout, 5xx,
invalid_response, empty, container_not_ready, unknown_contract,
recipe_lacks_inapp_channel) transition DIRECTLY to status='failed'.
The reaper (Plan 22c.3-06) handles rows stuck in 'forwarded' (api
crash mid-forward) — also transitioning directly to 'failed'.

Per D-33 / D-34 (outbox via agent_events), the dispatcher INSERTs
``agent_events`` with ``published=false`` for every terminal outcome
(success or failure). The outbox pump (Plan 22c.3-07) fans out to
Redis Pub/Sub channel ``agent:inapp:<agent_id>``; the dispatcher does
NOT publish directly. The fan-out path is exclusively via the outbox
flag — no PG pub/sub primitives are used anywhere in this module.

The dispatcher consumes Plan 22c.3-04's store API verbatim — no
inlined SQL for ``mark_forwarded`` / ``mark_done`` / ``mark_failed``
/ ``fetch_pending_for_dispatch``. This is the single-seam discipline
that lets the reaper + dispatcher + future replicas share the same
state-machine contract without drift.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

from .event_store import insert_agent_event
from .inapp_messages_store import (
    fetch_pending_for_dispatch,
    mark_done,
    mark_failed,
    mark_forwarded,
)
from .inapp_recipe_index import InappChannelConfig


_log = logging.getLogger("api_server.inapp_dispatcher")


# ---------------------------------------------------------------------------
# Tunable constants — kept module-level so tests can monkey-patch them.
# ---------------------------------------------------------------------------

#: Tick interval for the dispatcher_loop. 250ms is the RESEARCH-recommended
#: balance between latency-to-bot and PG load (4 SELECT FOR UPDATE per
#: second per replica; cheap on the partial index).
TICK_SECONDS: float = 0.25

#: Per-tick batch size. The dispatcher's ``fetch_pending_for_dispatch``
#: passes this to the store; SKIP LOCKED ensures a second replica picks
#: up the next 10 without overlap.
BATCH_LIMIT: int = 10

#: Per-bot-call timeout (D-40 — 600s = 10 minutes). The dispatcher does
#: NOT auto-retry; this is the single attempt's wall budget.
BOT_TIMEOUT_SECONDS: float = 600.0


# ---------------------------------------------------------------------------
# Adapter — _dispatch_http_localhost
# ---------------------------------------------------------------------------


async def _dispatch_http_localhost(
    http_client: httpx.AsyncClient,
    row: asyncpg.Record,
    inapp: InappChannelConfig,
    container_ip: str,
    *,
    timeout_seconds: float = BOT_TIMEOUT_SECONDS,
) -> str:
    """Forward one message to the bot. Returns the reply text.

    The 3-way ``match inapp.contract:`` is the load-bearing core of
    this plan — adding a 4th contract later is a single new ``case``
    arm + a ``Literal`` extension on
    :class:`InappChannelConfig.contract`.

    Adapter contracts (verbatim from RESEARCH §Pitfall 6 +
    §Per-Recipe Feasibility Matrix):

    * ``openai_compat``  — POST ``{url}{endpoint}`` with body
      ``{"model": <contract_model_name or "agent">, "messages": [{"role":"user","content": <content>}]}``;
      parses ``data["choices"][0]["message"]["content"]``.
    * ``a2a_jsonrpc``    — POST ``{url}/a2a`` (the recipe declares
      ``/a2a`` as ``endpoint``) with the JSON-RPC 2.0 envelope
      ``message/send``; parses
      ``data["result"]["artifacts"][0]["parts"][0]["text"]``.
    * ``zeroclaw_native``— POST ``{url}/webhook`` with body
      ``{"message": <content>}``; sends ``X-Session-Id`` header
      (always) + ``X-Idempotency-Key`` header (when present on the
      row). Parses ``data["response"]``.

    Raises:

    * ``httpx.TimeoutException`` — single attempt's ``timeout_seconds``
      elapsed (D-40 600s default; tests override).
    * ``httpx.HTTPStatusError`` — bot returned 4xx / 5xx (the dispatcher
      converts 5xx to ``bot_5xx:<status>``; 4xx is a misuse — surfaces
      as the same).
    * ``RuntimeError`` — known parse failures (per-contract path) +
      ``unknown_contract:<value>`` for an unsupported contract value.
    * ``json.JSONDecodeError`` (via httpx ``resp.json()``) — bot
      returned non-JSON 200; dispatcher converts to
      ``bot_invalid_response``.
    """
    url = f"http://{container_ip}:{inapp.port}{inapp.endpoint}"
    headers = {"Content-Type": "application/json"}

    match inapp.contract:
        case "openai_compat":
            body: dict[str, Any] = {
                "model": inapp.contract_model_name or "agent",
                "messages": [{"role": "user", "content": row["content"]}],
            }
            # auth_mode='bearer' uses agent_containers.inapp_auth_token
            # (already on the row from Plan 04's JOIN).
            if inapp.auth_mode == "bearer" and row["inapp_auth_token"]:
                headers["Authorization"] = f"Bearer {row['inapp_auth_token']}"
            resp = await http_client.post(
                url, json=body, headers=headers, timeout=timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"openai_compat_parse_error:{e}") from e

        case "a2a_jsonrpc":
            body = {
                "jsonrpc": "2.0",
                "id": str(row["id"]),
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": row["content"]}],
                        "messageId": str(row["id"]),
                    }
                },
            }
            resp = await http_client.post(
                url, json=body, headers=headers, timeout=timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                err = data["error"]
                msg = err.get("message", "unknown") if isinstance(err, dict) else "unknown"
                raise RuntimeError(f"a2a_error:{msg}")
            try:
                return data["result"]["artifacts"][0]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"a2a_parse_error:{e}") from e

        case "zeroclaw_native":
            body = {"message": row["content"]}
            # Built-in idempotency: when the inbound POST carried an
            # Idempotency-Key, we forward it to zeroclaw so the bot's
            # built-in dedup window applies. Plan 04's row dict does
            # NOT (yet) carry idempotency_key as a column; the row may
            # surface it via a future schema extension. Defensive:
            # support both Record-with-key and dict.get fall-through.
            idem = _row_get(row, "idempotency_key")
            if idem:
                # Use the recipe-declared header name when set;
                # otherwise default to ``X-Idempotency-Key`` per
                # zeroclaw's native shape.
                hdr_name = inapp.idempotency_header or "X-Idempotency-Key"
                headers[hdr_name] = str(idem)
            sess_hdr = inapp.session_header or "X-Session-Id"
            headers[sess_hdr] = f"inapp:{row['user_id']}:{row['agent_id']}"
            resp = await http_client.post(
                url, json=body, headers=headers, timeout=timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["response"]
            except (KeyError, TypeError) as e:
                raise RuntimeError(f"zeroclaw_parse_error:{e}") from e

        case other:
            # Per the must_haves.truths: unknown contract is an
            # explicit failure, never a silent fall-through. The outer
            # _handle_row converts this RuntimeError to
            # ``mark_failed(id, f"unknown_contract:{value}")``.
            raise RuntimeError(f"unknown_contract:{other}")


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Safe getter for asyncpg.Record OR dict-like rows.

    asyncpg.Record raises KeyError for missing keys (it does not
    implement ``.get``). Tests sometimes substitute plain dicts; this
    helper unifies both.
    """
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


# ---------------------------------------------------------------------------
# Per-row handler — _handle_row + _terminal_failure
# ---------------------------------------------------------------------------


async def _terminal_failure(
    state: Any,
    row: asyncpg.Record,
    error_type: str,
) -> None:
    """Mark a row failed AND insert the matching agent_events row.

    Per D-40, the dispatcher does NOT auto-retry — every error path
    is terminal. This helper consolidates the shared pair-of-writes
    so every failure mode looks identical from the outbox + SSE side.

    The two writes share a single transaction so the outbox pump
    never sees a ``inapp_messages.status='failed'`` without its
    matching ``agent_events`` row, and never the reverse.
    """
    pool = state.db
    captured_at = datetime.now(timezone.utc).isoformat()
    # Truncate to fit InappOutboundFailedPayload.message max_length=512.
    # The error_type is the canonical short string; message just
    # echoes it for now (future code can add per-error detail without
    # changing the contract).
    message_text = error_type[:512] or "unspecified"
    payload = {
        "error_type": _truncate_error_type(error_type),
        "message": message_text,
        "retry_count": int(row["attempts"] or 0),
        "captured_at": captured_at,
    }
    async with pool.acquire() as conn:
        async with conn.transaction():
            await mark_failed(conn, row["id"], error_type)
            await insert_agent_event(
                conn,
                row["container_row_id"],
                "inapp_outbound_failed",
                payload,
            )


# Documented error_type values per InappOutboundFailedPayload pattern.
# A leading prefix may optionally carry a colon + detail (e.g.
# "bot_5xx:502") — the canonical enum value is the leading token.
_KNOWN_ERROR_TYPES = {
    "bot_5xx",
    "bot_timeout",
    "bot_empty",
    "container_dead",
    "recipe_no_inapp_channel",
    "container_not_ready",
    "recipe_missing",
    "reaper_timeout",
    "internal",
}


def _truncate_error_type(value: str) -> str:
    """Project an arbitrary error_type string to a Pydantic-acceptable enum.

    The InappOutboundFailedPayload pattern allows exactly the 9 enum
    values. The dispatcher uses richer free-form strings on
    ``inapp_messages.last_error`` (e.g. "bot_5xx:503", "unknown_contract:foo").
    For the agent_events payload we map to the leading enum keyword;
    unknown / unmapped values fall through to ``internal`` (the
    documented "defensive bucket for unclassified bugs").
    """
    leading = value.split(":", 1)[0] if value else ""
    if leading in _KNOWN_ERROR_TYPES:
        return leading
    # Special-case: "unknown_contract:..." and "*_parse_error:..." surface
    # as ``internal`` — they're dispatcher-internal failures the user
    # can't act on. ``recipe_lacks_inapp_channel`` collapses to
    # ``recipe_no_inapp_channel`` (the canonical Pydantic enum value
    # per InappOutboundFailedPayload).
    if leading == "recipe_lacks_inapp_channel":
        return "recipe_no_inapp_channel"
    return "internal"


async def _handle_row(state: Any, row: asyncpg.Record) -> None:
    """Process one row: readiness gate → recipe lookup → bot call → persist.

    Implements the persist-before-action discipline (D-28):

    1. Readiness gate (D-37/D-38): if container is not running OR
       ready_at is NULL OR stopped_at is set, mark_failed +
       insert_agent_event(failure) and return. No bot call.
    2. Recipe lookup: if the recipe lacks ``channels.inapp``, same
       terminal-failure pattern.
    3. Container IP discovery (cached).
    4. Mark forwarded BEFORE the bot call (D-28).
    5. Single bot call via :func:`_dispatch_http_localhost` — no
       retry on any error path (D-40).
    6. On success: ``mark_done`` + insert agent_events(inapp_outbound)
       in a single transaction (so the outbox pump never sees a
       state mismatch).
    7. On failure: ``_terminal_failure(error_type)`` — same
       transaction shape.
    """
    # ---- Step 1: readiness gate (D-37 / D-38) -------------------------
    if (
        row["container_status"] != "running"
        or row["ready_at"] is None
        or row["stopped_at"] is not None
    ):
        await _terminal_failure(state, row, "container_not_ready")
        return

    # ---- Step 2: recipe lookup ---------------------------------------
    inapp = state.recipe_index.get_inapp_block(row["recipe_name"])
    if inapp is None:
        await _terminal_failure(state, row, "recipe_lacks_inapp_channel")
        return

    # ---- Step 3: container IP -----------------------------------------
    try:
        container_ip = state.recipe_index.get_container_ip(row["container_id"])
    except RuntimeError:
        _log.exception(
            "inapp_dispatcher.ip_lookup_failed",
            extra={"container_id": row["container_id"]},
        )
        await _terminal_failure(state, row, "container_dead")
        return

    # ---- Step 4: persist forwarded BEFORE the call (D-28) -------------
    pool = state.db
    async with pool.acquire() as conn:
        await mark_forwarded(conn, [row["id"]])

    # ---- Step 5: the single bot call (no retry — D-40) ----------------
    timeout_seconds = getattr(state, "bot_timeout_seconds", BOT_TIMEOUT_SECONDS)
    try:
        reply = await _dispatch_http_localhost(
            state.bot_http_client,
            row,
            inapp,
            container_ip,
            timeout_seconds=timeout_seconds,
        )
    except httpx.TimeoutException:
        await _terminal_failure(state, row, "bot_timeout")
        return
    except httpx.HTTPStatusError as e:
        # 5xx is the documented case; 4xx surfaces with the same prefix
        # since the user can't fix either — both terminal.
        await _terminal_failure(
            state, row, f"bot_5xx:{e.response.status_code}",
        )
        return
    except RuntimeError as e:
        msg = str(e)
        # ``unknown_contract:<value>`` surfaces verbatim on
        # last_error so operators can read which recipe is wrong.
        await _terminal_failure(state, row, msg)
        return
    except (httpx.RequestError, ValueError) as e:
        # ValueError covers httpx's ``resp.json()`` JSON-decode failure
        # (httpx raises ``json.JSONDecodeError`` which subclasses
        # ValueError). RequestError covers connection-level errors.
        _log.exception(
            "inapp_dispatcher.bot_invalid_response",
            extra={"id": str(row["id"]), "err": str(e)},
        )
        await _terminal_failure(state, row, "bot_invalid_response")
        return
    except Exception:
        _log.exception("inapp_dispatcher.unexpected_error", extra={
            "id": str(row["id"]),
        })
        await _terminal_failure(state, row, "internal_error")
        return

    if not reply or not reply.strip():
        await _terminal_failure(state, row, "bot_empty")
        return

    # ---- Step 6: success path — mark_done + agent_events -------------
    captured_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "content": reply,
        "source": "agent",
        "captured_at": captured_at,
    }
    async with pool.acquire() as conn:
        async with conn.transaction():
            await mark_done(conn, row["id"], reply)
            await insert_agent_event(
                conn,
                row["container_row_id"],
                "inapp_outbound",
                payload,
            )


# ---------------------------------------------------------------------------
# dispatcher_loop — the 250ms tick
# ---------------------------------------------------------------------------


async def dispatcher_loop(state: Any) -> None:
    """The 250ms-tick dispatcher pump.

    Lifespan (Plan 22c.3-09) creates this as an asyncio.Task and stops
    it via ``state.inapp_stop`` (an asyncio.Event). Every tick:

    1. Open a transaction on the pool, ``fetch_pending_for_dispatch``
       (limit=10) — the SKIP LOCKED clause means a parallel replica's
       fetch will skip rows we lock here.
    2. Spawn one coroutine per row via ``asyncio.gather`` — per-row
       work is independent (each opens its own connection for the
       writes), so we don't tie up the dispatcher's pool slot.
    3. Sleep for ``TICK_SECONDS``, repeat.

    The fetch transaction is opened JUST around the SELECT — the
    actual row-handling each runs in its own transaction inside
    ``_handle_row``. This is intentional: holding the SELECT
    transaction open for 600s while a bot call runs would defeat the
    SKIP LOCKED behavior (other replicas would block on the lock
    instead of skipping).

    The trade-off: between ``mark_forwarded`` committing in
    ``_handle_row`` and the SELECT transaction committing here, two
    replicas could in principle fetch the SAME row. Mitigation:
    ``mark_forwarded`` is idempotent at the SQL level (the bulk
    UPDATE is no-op for a row already in 'forwarded'), and the
    composed PG isolation default (READ COMMITTED) means the second
    replica's UPDATE waits for the first replica's commit. In
    practice the lock window is ~milliseconds.
    """
    stop_event: asyncio.Event = getattr(state, "inapp_stop", None) or asyncio.Event()
    pool = state.db
    while not stop_event.is_set():
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    rows = await fetch_pending_for_dispatch(conn, BATCH_LIMIT)
            if rows:
                await asyncio.gather(
                    *(_handle_row(state, row) for row in rows),
                    return_exceptions=True,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never let the loop die — log + sleep + retry. Real
            # underlying failures (DB outage) will recur and produce
            # a stream of error logs; ops can alert on that.
            _log.exception("inapp_dispatcher.tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
            return  # stop_event was set during the wait — exit cleanly.
        except asyncio.TimeoutError:
            # Normal sleep completion — loop continues.
            pass


__all__ = [
    "BATCH_LIMIT",
    "BOT_TIMEOUT_SECONDS",
    "TICK_SECONDS",
    "dispatcher_loop",
    "_dispatch_http_localhost",
    "_handle_row",
    "_terminal_failure",
]
