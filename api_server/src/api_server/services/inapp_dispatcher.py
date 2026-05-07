"""Phase 22c.3-05 inapp dispatcher — REDUCED ROLE post Phase 28 cutover.

NOTE (Phase 28, Plan 28-06 cutover, 2026-05-05):
This module's role is REDUCED. The asyncpg-pump ``dispatcher_loop`` and
its per-row handler ``_handle_row`` were DELETED at cutover (D-06). The
DispatchMessageWorkflow (``api_server/src/api_server/temporal/workflows/
dispatch_message.py``) replaces the asyncpg pump end-to-end.

The module is KEPT for two load-bearing helpers the Temporal activities
import verbatim, with no behavioral change relative to Phase 22c.3:

* :func:`_dispatch_http_localhost` — the 3-way contract switch
  (openai_compat / a2a_jsonrpc / zeroclaw_native) consumed by
  ``api_server.temporal.activities.forward_to_agent.ForwardActivities.
  forward_to_agent``. The contract logic is the load-bearing core; copying
  it into the activity would risk drift, so the activity imports it.
* :func:`_truncate_error_type` + :data:`_KNOWN_ERROR_TYPES` — the AP
  error-taxonomy enum mapper consumed by
  ``api_server.temporal.activities.mark_message_failed.MarkFailedActivities``.

The legacy ``dispatcher_loop`` 250ms tick + the per-row state machine
(``_handle_row`` + ``_terminal_failure``) are gone. The reaper
(``services/inapp_reaper.py``) and outbox pump
(``services/inapp_outbox.py``) are unchanged — RESEARCH §7 R1 keeps the
reaper for legacy stuck rows during the transition window; R7 keeps the
outbox pump as the redis-fan-out path.

Original module documentation (kept verbatim for the contract switch):

3-way contract adapter switch:

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
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import asyncpg
import httpx
import websockets
import websockets.exceptions

from .inapp_recipe_index import InappChannelConfig


# ---------------------------------------------------------------------------
# Tunable constants — kept module-level so tests can monkey-patch them.
# ---------------------------------------------------------------------------

#: Per-bot-call timeout (D-40 — 600s = 10 minutes). The Phase 28
#: forward_to_agent activity reads this as the default; the activity owns
#: per-call retry semantics independently of the timeout.
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
) -> tuple[str, dict | None]:
    """Forward one message to the bot. Returns ``(reply_text, raw_response_dict)``.

    Phase 27 — the raw response dict is preserved so the
    :mod:`usage_recorder` can extract the upstream ``usage`` block
    (token counts) before the dict is dropped. ``None`` is returned for
    contracts whose response shape carries no usable usage data
    (a2a_jsonrpc / zeroclaw_native today); the recorder treats that
    as ``status='unknown'``.

    The 3-way ``match inapp.contract:`` is the load-bearing core of
    this module — adding a 4th contract later is a single new ``case``
    arm + a ``Literal`` extension on
    :class:`InappChannelConfig.contract`.

    Adapter contracts (verbatim from RESEARCH §Pitfall 6 +
    §Per-Recipe Feasibility Matrix):

    * ``openai_compat``  — POST ``{url}{endpoint}`` with body
      ``{"model": <contract_model_name or "agent">, "messages": [{"role":"user","content": <content>}]}``;
      parses ``data["choices"][0]["message"]["content"]``. Returns
      the full ``data`` dict so the recorder can read ``data["usage"]``.
    * ``a2a_jsonrpc``    — POST ``{url}/a2a`` (the recipe declares
      ``/a2a`` as ``endpoint``) with the JSON-RPC 2.0 envelope
      ``message/send``; parses
      ``data["result"]["artifacts"][0]["parts"][0]["text"]``. Returns
      ``None`` for the dict — the protocol strips usage.
    * ``zeroclaw_native``— POST ``{url}/webhook`` with body
      ``{"message": <content>}``; sends ``X-Session-Id`` header
      (always) + ``X-Idempotency-Key`` header (when present on the
      row). Parses ``data["response"]``. Returns ``None`` — native
      shape has no usage.

    Raises:

    * ``httpx.TimeoutException`` — single attempt's ``timeout_seconds``
      elapsed (D-40 600s default; tests override).
    * ``httpx.HTTPStatusError`` — bot returned 4xx / 5xx (the activity
      converts 5xx to ``bot_5xx:<status>``; 4xx is a misuse — surfaces
      as the same).
    * ``RuntimeError`` — known parse failures (per-contract path) +
      ``unknown_contract:<value>`` for an unsupported contract value.
    * ``json.JSONDecodeError`` (via httpx ``resp.json()``) — bot
      returned non-JSON 200; activity converts to
      ``bot_invalid_response``.
    """
    url = f"http://{container_ip}:{inapp.port}{inapp.endpoint}"
    headers = {"Content-Type": "application/json"}

    # Phase 25 Wave 5: hoist the auth_mode='bearer' Authorization header
    # OUT of the openai_compat-only branch so a2a_jsonrpc + zeroclaw_native
    # contracts also receive it. Per nullclaw upstream HEAD ≥ 2026-05, the
    # gateway's /a2a endpoint enforces bearer auth even with require_pairing
    # =false (drift from 2026-04-30 verified_cell). The recipe pre-seeds
    # gateway.paired_tokens=[INAPP_AUTH_TOKEN]; this header completes the
    # pair so /a2a returns 200.
    if inapp.auth_mode == "bearer" and row["inapp_auth_token"]:
        headers["Authorization"] = f"Bearer {row['inapp_auth_token']}"
    elif inapp.auth_mode == "token" and row["inapp_auth_token"]:
        # Token auth with a recipe-declared header name (goose's
        # X-Secret-Key). Bearer is the dominant SDK convention; "token"
        # mode is the escape hatch for bots that pick a different header
        # name. The dispatcher trusts the recipe's auth_header_name —
        # the loader (_parse_inapp_block) parses it, the dispatcher
        # forwards it. No casing rewrite — recipe value lands verbatim.
        if not inapp.auth_header_name:
            raise RuntimeError(
                "auth_mode=token requires channels.inapp.auth_header_name"
            )
        headers[inapp.auth_header_name] = row["inapp_auth_token"]

    match inapp.contract:
        case "openai_compat":
            # Resolve the model field. Most recipes pin a fixed alias
            # (hermes='hermes-agent', openclaw='openclaw') because the
            # bot accepts that alias internally. Some bots (nanobot)
            # enforce literal match against the model the agent was
            # deployed with — for those, the recipe declares the
            # sentinel "$AGENT_MODEL" and the dispatcher substitutes
            # the agent_instances.model value joined into the row by
            # the workflow input.
            model_name = inapp.contract_model_name or "agent"
            if model_name == "$AGENT_MODEL":
                model_name = row["agent_model"]
            body: dict[str, Any] = {
                "model": model_name,
                "messages": [{"role": "user", "content": row["content"]}],
            }
            resp = await http_client.post(
                url, json=body, headers=headers, timeout=timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"], data
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
                # a2a_jsonrpc strips usage at the protocol layer (Phase 27);
                # return None as the response dict so the recorder marks
                # the row status='unknown'.
                return data["result"]["artifacts"][0]["parts"][0]["text"], None
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"a2a_parse_error:{e}") from e

        case "agentscope_runtime":
            # QwenPaw POST /api/console/chat — AgentScope Runtime SSE shape.
            # Body uses `input[*].role/content[*].text` (NOT OpenAI's
            # `messages[*].content`) and response is `data: {...}\n\n` SSE
            # events terminated by `status: "completed"`. Documented at
            # https://qwenpaw.agentscope.io/docs/api-tutorial.
            #
            # The X-Agent-Id header selects which QwenPaw agent to talk to;
            # 'default' is the first/only agent on a fresh QwenPaw install
            # (the recipe's bootstrap heredoc doesn't create extra agents).
            agent_id_header = inapp.contract_model_name or "default"
            body = {
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": row["content"]},
                        ],
                    },
                ],
                "session_id": f"inapp:{row['user_id']}:{row['agent_id']}",
                "user_id": str(row["user_id"]),
                "channel": "console",
            }
            sse_headers = {**headers, "X-Agent-Id": agent_id_header}
            final_text: str | None = None
            async with http_client.stream(
                "POST",
                url,
                json=body,
                headers=sse_headers,
                timeout=timeout_seconds,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[len("data: "):])
                    except json.JSONDecodeError:
                        continue
                    status = event.get("status")
                    obj = event.get("object")
                    # AgentScope Runtime emits a tree of nested events:
                    # `object: content` and `object: message` events fire
                    # for intermediate streaming chunks AND tool-call
                    # results, each with their own status transitions
                    # (created → in_progress → completed). The OUTER
                    # `object: response` event is the only one whose
                    # `completed` status indicates the entire turn is
                    # done with the final assistant text in `output`.
                    # Filtering on `object == "response"` here is the
                    # difference between exiting the SSE loop on the
                    # first sub-event completion (wrong — output empty)
                    # and waiting for the agent loop to finish (right).
                    if obj != "response":
                        continue
                    if status == "failed":
                        err = event.get("error") or {}
                        msg = (
                            err.get("message", "unknown")
                            if isinstance(err, dict)
                            else "unknown"
                        )
                        raise RuntimeError(
                            f"agentscope_runtime_error:{msg}"
                        )
                    if status == "completed":
                        # Concatenate every assistant text piece. QwenPaw
                        # may emit multiple output messages for a single
                        # turn (assistant + tool-result interleavings);
                        # the inapp dispatcher only forwards the user-
                        # facing assistant text.
                        texts: list[str] = []
                        for out_msg in event.get("output") or []:
                            if not isinstance(out_msg, dict):
                                continue
                            if out_msg.get("role") != "assistant":
                                continue
                            for piece in out_msg.get("content") or []:
                                if (
                                    isinstance(piece, dict)
                                    and piece.get("type") == "text"
                                    and piece.get("text")
                                ):
                                    texts.append(str(piece["text"]))
                        final_text = "".join(texts) if texts else None
                        break
            if not final_text:
                # Stream ended without a `status: completed` event carrying
                # assistant text. Mirror a2a_jsonrpc's parse-error shape so
                # the activity converts to bot_invalid_response.
                raise RuntimeError(
                    "agentscope_runtime_no_completed_event"
                )
            # agentscope_runtime usage is captured at the proxy layer
            # (the recipe routes through ${AP_PROXY_BASE_URL} and the
            # proxy writes usage_logs from the upstream OpenRouter
            # response). Return None for the dispatcher-side response
            # dict so the recorder marks the dispatcher row as
            # status='unknown' — the proxy row carries the canonical
            # token counts + cost.
            return final_text, None

        case "goose_native":
            # block/goose 3-step protocol (HTTP+SSE).
            # Reference: crates/goose-server/src/routes/{agent,reply}.rs.
            #
            # Empirical findings from the 2026-05-07 spike:
            #
            #   1. POST /agent/start mints a session_id (server-generated,
            #      e.g. "20260507_1" — date+counter, NOT a UUID we can
            #      pre-pick). Body: {"working_dir": "/root"}. Returns
            #      Session JSON with `id` field.
            #   2. POST /agent/update_provider wires the LLM provider for
            #      that session. WITHOUT this call /reply returns
            #      `{"type":"Error","error":"Provider not set"}`. Body:
            #      {"provider": "openai", "model": <slug>, "session_id":
            #      <minted-id>}. Goose then reads OPENAI_BASE_URL +
            #      OPENAI_API_KEY env vars to build the provider.
            #   3. POST /reply with the minted session_id streams the
            #      reply via SSE.
            #
            # The "openai" provider name is HARD-CODED here, not pulled
            # from the recipe — every via_proxy goose instance uses the
            # openai provider plugin (with OPENAI_BASE_URL pointed at
            # the AP egress proxy) regardless of what's actually upstream
            # of the proxy (anthropic, openrouter, etc.). See
            # recipes/goose.yaml::warnings.openai_provider_for_openrouter_routing
            # for why we don't use goose's native openrouter provider.
            #
            # SSE event shape (data: {...}\n\n) discriminated by `type`:
            #   - Message{message, token_state}   — assistant text chunk
            #   - Finish{reason, token_state}     — TERMINAL signal
            #   - Error{error}                    — terminal failure
            #   - Notification / UpdateConversation /
            #     ActiveRequests / Ping            — intermediate
            #
            # Per spike: message.role is LOWERCASE "assistant" in the
            # Message event payload (the role enum serializes lowercase
            # via rmcp::model::Role's serde derive).
            base_url = f"http://{container_ip}:{inapp.port}"

            # Step 1 — mint a session.
            start_resp = await http_client.post(
                f"{base_url}/agent/start",
                json={"working_dir": "/root"},
                headers=headers,
                timeout=timeout_seconds,
            )
            start_resp.raise_for_status()
            try:
                session_id = start_resp.json()["id"]
            except (KeyError, TypeError, ValueError) as e:
                raise RuntimeError(f"goose_start_parse_error:{e}") from e

            # Step 2 — wire provider for that session.
            update_resp = await http_client.post(
                f"{base_url}/agent/update_provider",
                json={
                    "provider": "openai",
                    "model": row["agent_model"],
                    "session_id": session_id,
                },
                headers=headers,
                timeout=timeout_seconds,
            )
            update_resp.raise_for_status()

            # Step 3 — POST /reply, stream until Finish.
            body = {
                "user_message": {
                    "role": "user",
                    "created": int(time.time()),
                    "content": [
                        {"type": "text", "text": row["content"]},
                    ],
                    "metadata": {"userVisible": True, "agentVisible": True},
                },
                "session_id": session_id,
                "override_conversation": None,
                "recipe_name": None,
                "recipe_version": None,
            }
            assistant_chunks: list[str] = []
            finish_seen = False
            async with http_client.stream(
                "POST",
                url,
                json=body,
                headers=headers,
                timeout=timeout_seconds,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[len("data: "):])
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type == "Error":
                        err_msg = event.get("error") or "unknown"
                        raise RuntimeError(f"goose_error:{err_msg}")
                    if event_type == "Message":
                        msg = event.get("message") or {}
                        if msg.get("role") != "assistant":
                            continue
                        for piece in msg.get("content") or []:
                            if (
                                isinstance(piece, dict)
                                and piece.get("type") == "text"
                                and piece.get("text")
                            ):
                                assistant_chunks.append(str(piece["text"]))
                        continue
                    if event_type == "Finish":
                        finish_seen = True
                        break
                    # Notification / UpdateConversation / ActiveRequests /
                    # Ping fall through to the next iteration.
            if not finish_seen:
                # Stream ended without Finish — connection dropped or
                # server crashed mid-turn. Mirror agentscope_runtime's
                # parse-error shape.
                raise RuntimeError("goose_no_finish_event")
            final_text = "".join(assistant_chunks)
            if not final_text:
                # Finish arrived but no assistant text was streamed.
                # Could be a tool-only turn or a bug in the bot.
                raise RuntimeError("goose_finish_without_text")
            # Usage is captured at the proxy layer (recipe routes through
            # ${AP_PROXY_BASE_URL}); return None for the dispatcher-side
            # response dict so the recorder marks status='unknown' on the
            # dispatcher row — the proxy row carries canonical token
            # counts + cost.
            return final_text, None

        case "zeroclaw_native":
            body = {"message": row["content"]}
            # Built-in idempotency: when the inbound POST carried an
            # Idempotency-Key, we forward it to zeroclaw so the bot's
            # built-in dedup window applies. The row dict may surface
            # it via a future schema extension. Defensive: support both
            # Record-with-key and dict.get fall-through.
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
                # zeroclaw_native has no usage block; return None for the
                # response dict so the recorder marks status='unknown'.
                return data["response"], None
            except (KeyError, TypeError) as e:
                raise RuntimeError(f"zeroclaw_parse_error:{e}") from e

        case other:
            # Unknown contract is an explicit failure, never a silent
            # fall-through. The Phase 28 ``forward_to_agent`` activity
            # converts this RuntimeError to
            # ``ApplicationError(type='unknown_contract', non_retryable=True)``.
            raise RuntimeError(f"unknown_contract:{other}")


# ---------------------------------------------------------------------------
# Adapter — _dispatch_websocket_chat
# ---------------------------------------------------------------------------


async def _dispatch_websocket_chat(
    row: Any,
    inapp: InappChannelConfig,
    container_ip: str,
    *,
    timeout_seconds: float = BOT_TIMEOUT_SECONDS,
) -> tuple[str, dict | None]:
    """Forward one message to the bot over a WebSocket. Returns ``(text, None)``.

    WebSocket sibling of :func:`_dispatch_http_localhost`. Activated when
    a recipe declares ``channels.inapp.transport: websocket_chat``.
    Currently supports a single contract — ``pico_native`` (sipeed/picoclaw)
    — but the ``match inapp.contract:`` shape mirrors the HTTP dispatcher
    so a future ``aionui_bridge`` arm is a single ``case`` extension.

    Pico Protocol notes (cross-checked against pkg/channels/pico/ in
    upstream picoclaw):

    * Connections are keyed by ``?session_id=<sid>`` URL query param at
      handshake — NOT by the ``session_id`` field in the ``message.send``
      envelope. Without the URL param, the server assigns a fresh UUID
      and the agent's outbound reply finds no connection
      (``"no active connections for session ..."``).
    * Auth: ``Authorization: Bearer <token>`` header (recipe sets
      ``auth_mode: bearer`` and the dispatcher pulls
      ``inapp_auth_token`` off the row).
    * Send envelope: ``{type:"message.send", session_id, payload:{content}}``.
    * Server-side stream: ``typing.start`` → ``typing.stop`` →
      ``message.create`` events. Intermediate ``message.create`` events
      with ``payload.kind in {"thought", "tool_calls"}`` (or the legacy
      ``payload.thought == True`` boolean marker) are reasoning / tool
      steps and MUST be skipped. The terminal assistant reply is the
      ``message.create`` whose payload has no ``kind`` (None / absent)
      AND non-empty ``content``.

    Returns ``(reply_text, None)`` — the ``pico_native`` contract carries
    no upstream-LLM usage block. Phase 27 cost capture for picoclaw
    happens at the proxy layer (the recipe routes through
    ``${AP_PROXY_BASE_URL}`` and the proxy writes ``usage_logs`` from
    the upstream OpenRouter response).

    Raises (mapped to the activity's existing 4-bucket exception
    taxonomy in ``forward_to_agent`` so no activity changes are needed
    for transport-error handling):

    * ``httpx.ConnectError`` — TCP / handshake failure (retryable per
      CONTEXT D-11; final attempt converts to ``bot_timeout``).
    * ``httpx.ReadTimeout`` — overall ``timeout_seconds`` exceeded
      (retryable; final attempt converts to ``bot_timeout``).
    * ``RuntimeError("bot_5xx:<code>")`` — WS handshake rejected with
      an HTTP status code (auth fail = 401, etc.); terminal, mapped to
      ``bot_5xx`` by the activity's leading-colon-prefix rule.
    * ``RuntimeError("pico_*")`` — protocol-level failure
      (parse error, premature ``ConnectionClosed``, no terminal event);
      terminal, mapped to ``internal`` by ``_truncate_error_type``.
    * ``RuntimeError("unknown_contract:<value>")`` — caller passed a
      transport+contract pair the WS dispatcher does not know.
    """
    sid = f"inapp:{row['user_id']}:{row['agent_id']}"

    match inapp.contract:
        case "pico_native":
            url = (
                f"ws://{container_ip}:{inapp.port}{inapp.endpoint}"
                f"?session_id={sid}"
            )
            extra_headers: list[tuple[str, str]] = []
            if inapp.auth_mode == "bearer":
                token = _row_get(row, "inapp_auth_token")
                if token:
                    extra_headers.append(("Authorization", f"Bearer {token}"))
            send_envelope = {
                "type": "message.send",
                "session_id": sid,
                "payload": {"content": row["content"]},
            }
            try:
                async with asyncio.timeout(timeout_seconds):
                    try:
                        ws = await websockets.connect(
                            url, additional_headers=extra_headers
                        )
                    except websockets.exceptions.InvalidStatus as e:
                        # The server returned a non-101 to the upgrade.
                        # `e.response.status_code` is the HTTP code (401
                        # for auth failure, 503 for "channel not running",
                        # etc.). Mirror httpx's HTTPStatusError shape via
                        # the leading-colon-prefix RuntimeError so the
                        # activity converts to bot_5xx.
                        code = getattr(getattr(e, "response", None), "status_code", 0)
                        raise RuntimeError(f"bot_5xx:{code}") from e
                    except (OSError, websockets.exceptions.WebSocketException) as e:
                        # TCP refused, DNS failure, or handshake protocol
                        # error before we got a structured InvalidStatus.
                        # Treat as a transport error so the activity's
                        # [0,1,2,4]s retry budget gets to apply.
                        raise httpx.ConnectError(f"pico_ws_connect:{e}") from e

                    async with ws:
                        await ws.send(json.dumps(send_envelope))
                        while True:
                            try:
                                raw = await ws.recv()
                            except websockets.exceptions.ConnectionClosed as e:
                                raise RuntimeError(
                                    f"pico_ws_closed:{e.code}"
                                ) from e
                            try:
                                msg = json.loads(raw)
                            except (json.JSONDecodeError, TypeError) as e:
                                raise RuntimeError(
                                    f"pico_parse_error:{e}"
                                ) from e
                            if not isinstance(msg, dict):
                                continue
                            if msg.get("type") != "message.create":
                                # typing.start / typing.stop / pong / etc.
                                # are stream-noise for the unary wrapper.
                                continue
                            payload = msg.get("payload") or {}
                            if not isinstance(payload, dict):
                                continue
                            kind = payload.get("kind")
                            content = payload.get("content")
                            # Intermediate reasoning / tool-call events
                            # (mirrors `isThoughtPayload` in
                            # pkg/channels/pico/protocol.go).
                            if kind in ("thought", "tool_calls"):
                                continue
                            if payload.get("thought") is True:
                                continue
                            if not content:
                                # `message.create` with empty content
                                # (e.g. media-only) is not the terminal
                                # text reply; keep listening.
                                continue
                            return str(content), None
            except asyncio.TimeoutError as e:
                # Overall budget exceeded waiting for terminal event.
                # Mirror httpx.ReadTimeout so the activity's transient
                # retry path applies.
                raise httpx.ReadTimeout(
                    f"pico_ws_read_timeout:{timeout_seconds}s"
                ) from e

        case other:
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
# Error-taxonomy enum mapping (consumed by the Phase 28
# ``mark_message_failed`` activity).
# ---------------------------------------------------------------------------

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
    values. The legacy dispatcher used richer free-form strings on
    ``inapp_messages.last_error`` (e.g. "bot_5xx:503", "unknown_contract:foo");
    the Phase 28 ``forward_to_agent`` activity preserves the same
    taxonomy. For the agent_events payload we map to the leading enum
    keyword; unknown / unmapped values fall through to ``internal``
    (the documented "defensive bucket for unclassified bugs").
    """
    leading = value.split(":", 1)[0] if value else ""
    if leading in _KNOWN_ERROR_TYPES:
        return leading
    # Special-case: "unknown_contract:..." and "*_parse_error:..." surface
    # as ``internal`` — they're internal failures the user can't act on.
    # ``recipe_lacks_inapp_channel`` collapses to
    # ``recipe_no_inapp_channel`` (the canonical Pydantic enum value
    # per InappOutboundFailedPayload).
    if leading == "recipe_lacks_inapp_channel":
        return "recipe_no_inapp_channel"
    return "internal"


__all__ = [
    "BOT_TIMEOUT_SECONDS",
    "_dispatch_http_localhost",
    "_dispatch_websocket_chat",
    "_row_get",
    "_KNOWN_ERROR_TYPES",
    "_truncate_error_type",
]
