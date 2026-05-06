"""Phase 29 — LLM egress proxy route.

The bot's outbound LLM call (OpenRouter / OpenAI / Anthropic) lands here
instead of going to the upstream provider directly. This route:

  1. Identifies the caller via the bot container's bridge IP
     (``request.client.host``) -> ``app.state.proxy_ip_map`` lookup,
     PLUS a defense-in-depth ``Authorization: Bearer ap-proxy-<token>``
     match against ``agent_containers.inapp_auth_token`` (D-07).
  2. Resolves the (provider, decrypted-BYOK-key) tuple via
     ``app.state.proxy_byok_cache`` (Plan 05 ships the cache; this
     plan's tests stub it).
  3. Mutates the outbound request body — injects ``stream_options.
     include_usage`` for OpenAI/OpenRouter streams (D-14) and the
     ``user`` parameter for OpenRouter sticky-routing (D-08).
     Anthropic adds ``OpenTelemetry`` header instead of body mutation.
  4. AMD-03 idempotency: if ``Idempotency-Key`` header is present,
     try ``insert_reserved_row``; on duplicate, poll for the original
     caller's verdict and replay it (single-charge under retries).
  5. Opens an upstream stream via ``app.state.proxy_upstream_client``
     (AMD-05 — separate httpx instance from ``bot_http_client``,
     timeout=600s for LLM streaming).
  6. Tees each chunk: bot receives bytes verbatim AND ``StreamUsageParser``
     captures the trailing ``usage`` block.
  7. After stream-close (in the StreamingResponse generator's finally
     block), persists a ``usage_logs`` row with the parsed tokens +
     proxy/upstream latency split (D-11).
  8. On 4xx/5xx upstream, the bot receives the error body verbatim AND
     a ``usage_logs`` row is written with ``status='failed'`` (D-15).

BYOK redaction (T-29-01): every exception text passed to the logger
goes through ``_redact_creds(text, key)`` so the BYOK key never leaks
to logs even if a traceback echoes it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import traceback
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from temporalio.exceptions import WorkflowAlreadyStartedError

from ..models.errors import ErrorCode, make_error_envelope
from ..services.idempotency import (
    finalize_reserved_row,
    insert_reserved_row,
    poll_for_completion,
)
from ..services.proxy_dispatcher import PROVIDERS
from ..services.stream_parser import StreamUsageParser
from ..services.usage_recorder import ParsedUsage
from ..temporal.activities.backfill_openrouter_cost import (
    BackfillOpenRouterCostInput,
)
from ..temporal.workflows.backfill_openrouter_cost import (
    BackfillOpenRouterCostWorkflow,
)

router = APIRouter()
_log = logging.getLogger("api_server.llm_proxy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(status: int, code: str, message: str) -> JSONResponse:
    """Stripe-shape error envelope. Mirror routes/agent_lifecycle.py::_err."""
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message),
    )


def _redact_creds(text: str, key: str | None) -> str:
    """Replace BYOK key with ``<REDACTED>`` before logging.

    Mirrors ``routes/agent_lifecycle.py::_redact_creds`` — only redact
    keys ≥8 chars (shorter values are too likely to collide with a
    common substring). Phase 29 acceptance gate #6.
    """
    if not text or not key or len(key) < 8:
        return text
    return text.replace(key, "<REDACTED>")


def _log_exception_redacted(
    logger: logging.Logger,
    msg: str,
    exc: BaseException,
    key: str | None,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an exception + redacted traceback at ERROR level.

    ``logging.Logger.exception`` auto-attaches the raw traceback string,
    which echoes the unredacted exception args. To honour the BYOK
    redaction contract (Phase 29 acceptance gate #6) we format the
    traceback ourselves, redact the BYOK key, and log via ``error()``
    so no auto-traceback is appended.
    """
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    raw_tb = "".join(tb_lines)
    redacted_tb = _redact_creds(raw_tb, key)
    redacted_msg = _redact_creds(msg, key)
    logger.error(
        "%s\n%s", redacted_msg, redacted_tb,
        extra=extra or {},
    )


async def _record_usage_from_parsed(
    pool: Any,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    provider: str,
    model: str,
    parsed: ParsedUsage,
    upstream_request_id: str | None,
    status_code: int,
    proxy_latency_ms: int,
    upstream_latency_ms: int,
    idempotency_key: str | None,
) -> UUID | None:
    """Write one ``usage_logs`` row from a parsed-usage tuple.

    The legacy ``services.usage_recorder.record_usage`` takes a raw
    ``response`` dict + a ``contract`` string; the proxy already has a
    typed :class:`ParsedUsage` from the streaming parser, so we INSERT
    directly. Plan 29-06 will extend the legacy entry point to accept
    parsed-usage shape; until then this helper owns the proxy path.

    Cost computation reads the ``cost_weights`` table for the per-1M-
    token rate; missing rows surface as cost_usd=0 (best-effort
    visibility, never blocks the response).

    Failures are logged + swallowed — a recorder failure must NEVER
    break the bot's reply path (mirrors the legacy recorder's contract).

    Returns the inserted ``usage_logs.id`` UUID on success or ``None`` on
    failure. Plan 29-07 consumes the returned id to launch the
    OpenRouter post-hoc cost backfill workflow with a stable id of
    ``backfill_or_<usage_log_id>``.
    """
    try:
        async with pool.acquire() as conn:
            # Cost: only computable when status='success' AND we have a
            # weights row. Failed rows persist with cost_usd=0 + tokens=0.
            cost_usd = Decimal("0")
            if parsed.status == "success" and (
                parsed.input_tokens or parsed.output_tokens
            ):
                weights = await conn.fetchrow(
                    """
                    SELECT input_per_1m_usd, output_per_1m_usd,
                           cache_read_per_1m_usd, cache_creation_per_1m_usd,
                           ap_multiplier
                    FROM cost_weights
                    WHERE provider = $1 AND model = $2
                    """,
                    provider, model,
                )
                if weights is not None:
                    in_rate = weights["input_per_1m_usd"] or Decimal("0")
                    out_rate = weights["output_per_1m_usd"] or Decimal("0")
                    cr_rate = weights["cache_read_per_1m_usd"] or Decimal("0")
                    cc_rate = weights["cache_creation_per_1m_usd"] or Decimal("0")
                    mult = weights["ap_multiplier"] or Decimal("1")
                    raw = (
                        Decimal(parsed.input_tokens) * in_rate
                        + Decimal(parsed.output_tokens) * out_rate
                        + Decimal(parsed.cache_read_tokens) * cr_rate
                        + Decimal(parsed.cache_creation_tokens) * cc_rate
                    ) / Decimal("1000000")
                    cost_usd = raw * mult

            # Use the provided latency split; fall back to total =
            # upstream_latency_ms for the legacy ``latency_ms`` column.
            # Plan 29-07: capture the inserted row id so the proxy can
            # launch the OpenRouter post-hoc cost backfill workflow
            # with a stable, idempotent workflow id.
            inserted_id = await conn.fetchval(
                """
                INSERT INTO usage_logs (
                    user_id, agent_instance_id, message_id,
                    provider, model, upstream_request_id,
                    input_tokens, output_tokens,
                    cache_read_tokens, cache_creation_tokens,
                    cost_usd, latency_ms, status, status_code,
                    stop_reason, source,
                    proxy_latency_ms, upstream_latency_ms
                ) VALUES (
                    $1, $2, NULL,
                    $3, $4, $5,
                    $6, $7,
                    $8, $9,
                    $10, $11, $12, $13,
                    $14, 'inapp',
                    $15, $16
                )
                RETURNING id
                """,
                user_id, agent_instance_id,
                provider, model, upstream_request_id,
                parsed.input_tokens, parsed.output_tokens,
                parsed.cache_read_tokens, parsed.cache_creation_tokens,
                cost_usd,
                upstream_latency_ms,  # legacy total-latency column
                parsed.status, status_code,
                parsed.stop_reason, proxy_latency_ms, upstream_latency_ms,
            )
            return inserted_id
    except Exception as exc:
        # No BYOK key in this scope to redact against; the recorder
        # SQL contains parameterized values only — but log via the
        # redacted helper for defense-in-depth (no-op when key=None).
        _log_exception_redacted(
            _log,
            f"proxy.record_usage_failed: {str(exc)}",
            exc, None,
            extra={
                "user_id": str(user_id),
                "agent_instance_id": str(agent_instance_id),
                "provider": provider,
                "model": model,
                "idempotency_key": idempotency_key,
            },
        )
        return None


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.post("/llm/forward/{path:path}", response_model=None)
async def forward(path: str, request: Request) -> StreamingResponse | JSONResponse:
    """Proxy POST handler for ``/v1/llm/forward/<upstream-path>``.

    Returns ``StreamingResponse`` in the happy path (streams the
    upstream response back to the bot). Auth failures return
    ``JSONResponse(401)`` with a Stripe-shape error envelope.
    """

    # ---------- 1. Caller identification (D-07 defense-in-depth) ----------
    bridge_ip = request.client.host if request.client else None
    if bridge_ip is None:
        return _err(401, ErrorCode.UNAUTHORIZED, "no client host")
    caller = await request.app.state.proxy_ip_map.get(bridge_ip)
    if caller is None:
        return _err(401, ErrorCode.UNAUTHORIZED, "unknown caller")
    user_id, agent_instance_id, expected_token = caller

    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip()
    if bearer != f"ap-proxy-{expected_token}":
        return _err(401, ErrorCode.UNAUTHORIZED, "auth token mismatch")

    # ---------- 2. Resolve provider + decrypted BYOK key ----------
    provider, key = await request.app.state.proxy_byok_cache.get(
        user_id, agent_instance_id,
    )
    if key is None or provider is None:
        return _err(500, ErrorCode.INTERNAL, "BYOK key not in cache")
    spec = PROVIDERS.get(provider)
    if spec is None:
        return _err(500, ErrorCode.INTERNAL, f"unknown provider: {provider}")

    # ---------- 3. Body mutation (D-08 + D-14) ----------
    body_bytes = await request.body()
    try:
        body: dict[str, Any] = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        return _err(400, ErrorCode.INVALID_REQUEST, "request body is not valid JSON")
    is_stream = bool(body.get("stream"))
    if provider in ("openrouter", "openai") and is_stream:
        # D-14 — include_usage gives the proxy the canonical token counts
        # in the final stream chunk.
        body["stream_options"] = {"include_usage": True}
    if provider == "openrouter":
        # D-08 — sticky routing + per-(user, agent) attribution in the
        # OpenRouter activity dashboard.
        body["user"] = f"ap_{user_id}_{agent_instance_id}"
    body_out = json.dumps(body, separators=(",", ":")).encode()
    body_hash = hashlib.sha256(body_out).hexdigest()

    # ---------- 4. Build upstream URL + headers ----------
    upstream_url = f"{spec.base_url}/{path}"
    upstream_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_out)),  # recomputed (D-14)
        spec.auth_header_name: spec.auth_value_template.format(key=key),
        **spec.extra_headers,
    }
    if provider == "anthropic":
        # D-14 — Anthropic surfaces user attribution via OpenTelemetry
        # header, NOT body field.
        upstream_headers["OpenTelemetry"] = f"ap_user={user_id}"

    # ---------- 5. Idempotency (D-16 + AMD-03) ----------
    idem_key = request.headers.get("Idempotency-Key")
    we_own_in_flight_slot = False
    if idem_key:
        async with request.app.state.db.acquire() as conn:
            we_own_in_flight_slot = await insert_reserved_row(
                conn, user_id=user_id, key=idem_key,
                request_body_hash=body_hash,
            )
            if not we_own_in_flight_slot:
                cached = await poll_for_completion(
                    conn, user_id=user_id, key=idem_key,
                )
                if cached is not None:
                    # Replay the cached verdict — no upstream call.
                    return JSONResponse(cached, status_code=200)
                # Timed out / failed — fall through to a fresh attempt.

    # ---------- 6. Open upstream stream (AMD-05 separate client) ----------
    client: httpx.AsyncClient = request.app.state.proxy_upstream_client
    t_proxy_start = time.monotonic()
    try:
        upstream_req = client.build_request(
            "POST", upstream_url, content=body_out, headers=upstream_headers,
        )
        t_upstream_start = time.monotonic()
        upstream_resp = await client.send(upstream_req, stream=True)
    except Exception as exc:
        _log_exception_redacted(
            _log,
            f"proxy.upstream_send_failed: {str(exc)}",
            exc,
            key,
            extra={
                "provider": provider,
                "user_id": str(user_id),
                "agent_instance_id": str(agent_instance_id),
            },
        )
        # Fail-closed (D-05) — surface a generic 502 to the bot.
        return _err(502, ErrorCode.INFRA_UNAVAILABLE, "upstream send failed")
    proxy_latency_ms = int((t_upstream_start - t_proxy_start) * 1000)
    upstream_request_id = (
        upstream_resp.headers.get("X-Generation-Id")
        or upstream_resp.headers.get("x-request-id")
    )
    status_code = upstream_resp.status_code

    # ---------- 7. Stream-tee back to the bot ----------
    parser = StreamUsageParser(provider=provider, sse_format=spec.sse_format)

    async def _gen():
        try:
            async for chunk in upstream_resp.aiter_raw():
                parser.feed(chunk)
                yield chunk
        finally:
            t_close = time.monotonic()
            upstream_latency_ms = int((t_close - t_upstream_start) * 1000)
            try:
                await upstream_resp.aclose()
            except Exception as exc:
                _log_exception_redacted(
                    _log,
                    f"proxy.upstream_aclose_failed: {str(exc)}",
                    exc, key,
                )
            # ParsedUsage is frozen — use dataclasses.replace for the
            # 4xx/5xx status override (D-15).
            parsed = parser.finalize()
            if status_code >= 400:
                parsed = replace(parsed, status="failed")
            usage_log_id = await _record_usage_from_parsed(
                request.app.state.db,
                user_id=user_id,
                agent_instance_id=agent_instance_id,
                provider=provider,
                model=str(body.get("model") or ""),
                parsed=parsed,
                upstream_request_id=upstream_request_id,
                status_code=status_code,
                proxy_latency_ms=proxy_latency_ms,
                upstream_latency_ms=upstream_latency_ms,
                idempotency_key=idem_key,
            )

            # Plan 29-07 — Fire-and-forget the OpenRouter post-hoc
            # cost backfill workflow. ONLY when:
            #   * provider is openrouter (only OpenRouter exposes the
            #     /api/v1/generation lookup; other providers return final
            #     usage inline and need no backfill).
            #   * upstream_request_id (X-Generation-Id) is non-empty —
            #     without it the activity has no key to look up.
            #   * status_code == 200 — no point backfilling a failed call.
            #   * usage_log_id is not None — we have a row to UPDATE.
            #
            # Workflow id is stable + idempotent: ``backfill_or_<usage_log_id>``.
            # WorkflowAlreadyStartedError is swallowed so a duplicate
            # request (same usage_log_id, e.g. retry path) does NOT
            # cascade into a 500 — Temporal's REJECT_DUPLICATE policy
            # gives us at-most-once execution per row.
            #
            # The start_workflow call is NOT wrapped in a task — it's a
            # fast gRPC RPC (the workflow body runs async on the worker).
            # We await it inline so completion of _gen()'s finally is
            # deterministic, but we swallow EVERY exception so a Temporal
            # outage cannot break the user's chat reply.
            if (
                provider == "openrouter"
                and upstream_request_id
                and status_code == 200
                and usage_log_id is not None
            ):
                temporal_client = getattr(
                    request.app.state, "temporal_client", None,
                )
                settings = getattr(request.app.state, "settings", None)
                if temporal_client is not None and settings is not None:
                    try:
                        await temporal_client.start_workflow(
                            BackfillOpenRouterCostWorkflow.run,
                            BackfillOpenRouterCostInput(
                                usage_log_id=str(usage_log_id),
                                generation_id=upstream_request_id,
                                user_id=str(user_id),
                                agent_instance_id=str(agent_instance_id),
                            ),
                            id=f"backfill_or_{usage_log_id}",
                            task_queue=settings.temporal_task_queue,
                        )
                    except WorkflowAlreadyStartedError:
                        # At-most-once: another caller already started
                        # the same backfill. No-op is the right answer.
                        _log.info(
                            "proxy.backfill_workflow_duplicate",
                            extra={"usage_log_id": str(usage_log_id)},
                        )
                    except Exception as exc:
                        _log_exception_redacted(
                            _log,
                            f"proxy.backfill_workflow_start_failed: {str(exc)}",
                            exc, key,
                            extra={
                                "usage_log_id": str(usage_log_id),
                                "generation_id": upstream_request_id,
                            },
                        )

            if idem_key and we_own_in_flight_slot:
                # Finalize the AMD-03 reserved row so a second concurrent
                # caller's poll_for_completion can replay our verdict.
                try:
                    async with request.app.state.db.acquire() as conn:
                        await finalize_reserved_row(
                            conn,
                            user_id=user_id,
                            key=idem_key,
                            verdict_json={
                                "status_code": status_code,
                                "upstream_request_id": upstream_request_id,
                            },
                            status=("success" if status_code < 400 else "failed"),
                        )
                except Exception as exc:
                    _log_exception_redacted(
                        _log,
                        f"proxy.finalize_reserved_row_failed: {str(exc)}",
                        exc, key,
                    )

    return StreamingResponse(
        _gen(),
        status_code=status_code,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )


__all__ = ["router"]
