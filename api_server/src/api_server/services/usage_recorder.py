"""Phase 27 — UsageRecorder. Insert one row into ``usage_logs`` per
upstream LLM call so the AppBar ticker + per-agent breakdown can read
"what does this agent cost the user?" without a paywall, a debit, or a
proxy. Pure visibility.

Provider-agnostic: a single :func:`record_usage` entry point branches
on the (contract, provider) pair and dispatches to one of three
parsers. The 3 contracts ship with these capture properties:

* ``openai_compat`` + ``anthropic`` — bot proxies the Anthropic
  Messages API with the OpenAI envelope; the bot can preserve
  Anthropic's native ``usage`` block (``input_tokens`` / ``output_tokens``
  / ``cache_read_input_tokens`` / ``cache_creation_input_tokens``)
  verbatim, OR translate to OpenAI fields. We try the OpenAI shape
  first (``usage.prompt_tokens`` / ``completion_tokens``), then fall
  back to the Anthropic shape.

* ``openai_compat`` + ``openrouter`` — bot proxies OpenRouter's
  OpenAI-compatible endpoint; ``usage.prompt_tokens`` / ``completion_tokens``
  are reliable. Cache details are lost at the chat-completion layer
  but recoverable post-hoc via OpenRouter's ``/api/v1/generation``
  endpoint (Phase 27 deferred — a follow-up will wire this when a
  recipe needs sub-cent precision).

* ``a2a_jsonrpc`` / ``zeroclaw_native`` — bots strip usage data from
  the response envelope. We insert a row with ``status='unknown'`` +
  zero tokens + zero cost so the message count + last_activity are
  still queryable. A future post-hoc OpenRouter fetch (gated on the
  recipe declaring ``runtime.provider=openrouter``) will backfill
  these rows; for now they are deliberate observability gaps.

Cost computation reads ``cost_weights`` (provider, model) for the
per-1M-token multipliers and applies the four token classes:
``input``, ``output``, ``cache_read``, ``cache_creation``. The
``ap_multiplier`` column carries the Phase B markup vehicle (Phase A
leaves it at 1.0; raise per-row when the paywall ships).

Failures in this module MUST NOT break the chat path. The dispatcher's
``mark_done`` transaction calls :func:`record_usage` last; a recorder
failure is logged + swallowed so the user still sees the reply. A
missing usage row is acceptable visibility loss; a missing reply is
a regression.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg


_log = logging.getLogger("api_server.usage_recorder")


# ---------------------------------------------------------------------------
# Parsed usage shape — what each provider/contract pair distills to
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedUsage:
    """Token counts + diagnostic metadata extracted from an upstream response.

    Cost is NOT computed here; that's :func:`_compute_cost`'s job.
    Status differentiates a successful capture from "the contract
    stripped usage; row exists for message-count purposes only".
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    upstream_request_id: str | None = None
    stop_reason: str | None = None
    status: str = "success"  # 'success' | 'unknown' | 'failed'
    # Phase 30 D-09 — OpenRouter returns ``usage.cost`` (USD) inline in
    # every response (last SSE chunk for streams; top-level for
    # non-streaming). When populated AND provider == "openrouter", the
    # proxy persists this directly as usage_logs.cost_usd. None means
    # "not present in upstream response — fall back to cost_weights
    # computation". Anthropic + OpenAI direct never populate this
    # field (D-10 + Pitfall 1 — provider-gate exclusivity).
    inline_cost_usd: float | None = None


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def resolve_provider(recipe_yaml: dict | None) -> str | None:
    """Return the recipe's ``runtime.provider`` string or ``None``.

    The 5 v0.2 recipes all declare ``runtime.provider`` at the top
    level (``openrouter`` or ``anthropic``). Older one-shot recipes
    may lack it; ``None`` means "we can't compute cost — record the
    row with status='unknown'".
    """
    if not isinstance(recipe_yaml, dict):
        return None
    runtime = recipe_yaml.get("runtime")
    if not isinstance(runtime, dict):
        return None
    provider = runtime.get("provider")
    return str(provider) if provider else None


# ---------------------------------------------------------------------------
# Per-contract parsers
# ---------------------------------------------------------------------------


def _parse_openai_compat(response: dict, provider: str | None) -> ParsedUsage:
    """Extract usage from an OpenAI-compatible chat completion envelope.

    Two shapes coexist:

    * Pure OpenAI / OpenRouter — ``usage.prompt_tokens`` /
      ``completion_tokens``. Cache hits surface as
      ``usage.prompt_tokens_details.cached_tokens`` (OpenAI o1+) or
      may be absent (OpenRouter wraps it but doesn't always pass it
      through).

    * Anthropic-direct passthrough — bot exposes the OpenAI envelope
      but preserves Anthropic's native ``input_tokens`` /
      ``output_tokens`` + ``cache_read_input_tokens`` /
      ``cache_creation_input_tokens`` keys at the same path.

    We try OpenAI first, then fall back to the Anthropic shape if the
    OpenAI keys are missing.
    """
    if not isinstance(response, dict):
        return ParsedUsage(status="unknown")
    usage = response.get("usage")
    if not isinstance(usage, dict):
        # Bot stripped usage entirely — record the row but flag it.
        return ParsedUsage(
            status="unknown",
            upstream_request_id=_str_or_none(response.get("id")),
        )

    # OpenAI / OpenRouter shape first.
    input_tokens = _int_or_zero(usage.get("prompt_tokens"))
    output_tokens = _int_or_zero(usage.get("completion_tokens"))

    # Fallback: Anthropic-direct shape passed through verbatim.
    if input_tokens == 0 and output_tokens == 0:
        input_tokens = _int_or_zero(usage.get("input_tokens"))
        output_tokens = _int_or_zero(usage.get("output_tokens"))

    # Cache tokens. OpenAI surfaces cache hits under
    # prompt_tokens_details.cached_tokens; Anthropic-direct exposes
    # the cache_read_input_tokens / cache_creation_input_tokens
    # fields. We try both — at most one shape will be present.
    cache_read = _int_or_zero(usage.get("cache_read_input_tokens"))
    if cache_read == 0:
        details = usage.get("prompt_tokens_details") or {}
        if isinstance(details, dict):
            cache_read = _int_or_zero(details.get("cached_tokens"))

    cache_creation = _int_or_zero(usage.get("cache_creation_input_tokens"))

    # Phase 30 D-09 — OpenRouter inline cost extraction.
    # Defensive cast handles JSON-number, JSON-string, and missing shapes
    # (RESEARCH A5). Downstream Decimal(str(...)) in routes/llm_proxy.py
    # re-coerces. None means "fall back to cost_weights computation".
    inline_cost = usage.get("cost")
    inline_cost_usd = float(inline_cost) if inline_cost is not None else None

    return ParsedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        upstream_request_id=_str_or_none(response.get("id")),
        stop_reason=_str_or_none(_first_choice_finish_reason(response)),
        status="success" if (input_tokens or output_tokens) else "unknown",
        inline_cost_usd=inline_cost_usd,
    )


def _parse_stripped(response: dict | None) -> ParsedUsage:
    """Parser for contracts that strip usage (a2a_jsonrpc, zeroclaw_native).

    We still record a row so message_count + last_activity stay
    queryable. Phase 27 marks this as a deliberate observability
    gap; a future post-hoc OpenRouter fetch will backfill.

    Phase 30 cleanup deletes this once the proxy lands and the legacy
    contract paths are retired (D-12). Until then it remains as the
    shape callers without a usable response dict get.
    """
    return ParsedUsage(status="unknown")


def _parse_anthropic_native(response: dict) -> ParsedUsage:
    """Parse a non-streaming Anthropic ``POST /v1/messages`` JSON dict.

    Shape (verbatim from Anthropic's API + RESEARCH.md, lines 247-285)::

        {
          "id": "msg_...",
          "model": "claude-haiku-4-5",
          "stop_reason": "end_turn",
          "usage": {
            "input_tokens": 5,
            "output_tokens": 17,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
          }
        }

    For the **streaming** path see ``services/stream_parser.py``
    :class:`StreamUsageParser` with ``sse_format='anthropic'``;
    AMD-07 last-wins on ``output_tokens`` lives there. AMD-10 keeps
    that branch correct under hypothetical multi-delta inputs even
    though claude-haiku-4-5 emits exactly one ``message_delta`` in
    practice.

    This parser handles the **non-streaming** dict shape only —
    distinct from ``_parse_openai_compat``'s Anthropic-passthrough
    fallback which handles the OpenAI-envelope-wrapping-Anthropic-keys
    shape some bots emit. Phase 29 D-12 calls for the native path
    explicitly so future non-streaming Anthropic calls (e.g. retry
    paths, replay) parse via the canonical native shape.

    Status semantics (Phase 29 D-15): missing ``usage`` block →
    ``status='failed'`` (the new Phase 29 widened-enum value reserved
    for proxy-side capture failures), NOT ``'unknown'`` (which is
    reserved for legacy stripped contracts).
    """
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ParsedUsage(
            status="failed",
            upstream_request_id=_str_or_none(response.get("id")),
        )
    return ParsedUsage(
        input_tokens=_int_or_zero(usage.get("input_tokens")),
        output_tokens=_int_or_zero(usage.get("output_tokens")),
        cache_read_tokens=_int_or_zero(usage.get("cache_read_input_tokens")),
        cache_creation_tokens=_int_or_zero(
            usage.get("cache_creation_input_tokens")
        ),
        upstream_request_id=_str_or_none(response.get("id")),
        stop_reason=_str_or_none(response.get("stop_reason")),
        status="success",
    )


def _first_choice_finish_reason(response: dict) -> str | None:
    """Pull ``choices[0].finish_reason`` if present (OpenAI envelope)."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    return first.get("finish_reason")


def _int_or_zero(value: Any) -> int:
    """Coerce to int, returning 0 for None / non-numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _str_or_none(value: Any) -> str | None:
    """Coerce to non-empty str or None."""
    if value is None:
        return None
    s = str(value)
    return s if s else None


# ---------------------------------------------------------------------------
# Cost computation
# ---------------------------------------------------------------------------


async def _compute_cost(
    conn: asyncpg.Connection,
    provider: str,
    model: str,
    parsed: ParsedUsage,
) -> Decimal:
    """Look up ``cost_weights`` for (provider, model) and compute USD.

    Formula: ``(input_tokens * input_per_1m + output_tokens * output_per_1m
    + cache_read_tokens * cache_read_per_1m + cache_creation_tokens *
    cache_creation_per_1m) / 1_000_000 * ap_multiplier``.

    Missing weights row → log a warning + return 0. Phase A leaves
    ap_multiplier at 1.0 across the board; Phase B raises it per row.
    Cache rates may be NULL (OpenAI cache_creation has no separate
    fee); NULL is treated as 0 for the multiplication.
    """
    row = await conn.fetchrow(
        """
        SELECT input_per_1m_usd, output_per_1m_usd,
               cache_read_per_1m_usd, cache_creation_per_1m_usd,
               ap_multiplier
        FROM cost_weights
        WHERE provider = $1 AND model = $2
        """,
        provider, model,
    )
    if row is None:
        _log.warning(
            "usage_recorder.weights_missing",
            extra={"provider": provider, "model": model},
        )
        return Decimal("0")

    input_rate = row["input_per_1m_usd"] or Decimal("0")
    output_rate = row["output_per_1m_usd"] or Decimal("0")
    cache_read_rate = row["cache_read_per_1m_usd"] or Decimal("0")
    cache_creation_rate = row["cache_creation_per_1m_usd"] or Decimal("0")
    multiplier = row["ap_multiplier"] or Decimal("1")

    raw = (
        Decimal(parsed.input_tokens) * input_rate
        + Decimal(parsed.output_tokens) * output_rate
        + Decimal(parsed.cache_read_tokens) * cache_read_rate
        + Decimal(parsed.cache_creation_tokens) * cache_creation_rate
    ) / Decimal("1000000")
    return raw * multiplier


# ---------------------------------------------------------------------------
# Public entry point — record_usage
# ---------------------------------------------------------------------------


async def record_usage(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    message_id: UUID | None,
    contract: str,
    provider: str | None,
    model: str,
    response: dict | None,
    latency_ms: int | None = None,
    proxy_latency_ms: int | None = None,
    upstream_latency_ms: int | None = None,
    source: str = "inapp",
) -> UUID | None:
    """INSERT one row into ``usage_logs`` for an upstream LLM call.

    Caller MUST be inside an asyncpg transaction — this function does
    not commit. The dispatcher writes the usage row in the same outer
    transaction as ``mark_done`` so the row is atomic with the message
    it describes.

    Internally the SELECT + INSERT run inside a SAVEPOINT (asyncpg's
    nested ``conn.transaction()``) so a recorder-side failure
    (FK violation, NOT NULL miss, weights table dropped, …) rolls back
    ONLY the savepoint — the outer ``mark_done`` transaction survives
    and the user still sees their reply. Without this, an aborted
    asyncpg transaction would force the outer txn into a failed state
    and roll the chat reply back too.

    Phase 29 D-11 + AMD-04 add ``proxy_latency_ms`` (wall-clock spent
    inside the proxy router) and ``upstream_latency_ms`` (wall-clock
    the upstream LLM took). Both default to ``None`` so pre-Phase-29
    callers (Temporal record_usage activity, dispatcher paths) keep
    working without code changes; the columns store NULL in that case.
    The proxy route handler (``routes/llm_proxy.py``) populates them
    from its time-monotonic measurements.

    Returns the new row id, or ``None`` if the recorder fails. A
    failure is LOGGED but never raised — the chat path's correctness
    must not depend on the recorder.
    """
    try:
        # Nested conn.transaction() opens a SAVEPOINT inside the
        # caller's txn — a failure here rolls back to the savepoint
        # without poisoning the outer transaction.
        async with conn.transaction():
            # Parse the response per (contract, provider) pair.
            if contract == "openai_compat" and isinstance(response, dict):
                parsed = _parse_openai_compat(response, provider)
            else:
                parsed = _parse_stripped(response)

            # Cost: only computable when provider AND tokens are known.
            if provider and parsed.status == "success":
                cost_usd = await _compute_cost(conn, provider, model, parsed)
            else:
                cost_usd = Decimal("0")

            row = await conn.fetchrow(
                """
                INSERT INTO usage_logs
                  (user_id, agent_instance_id, message_id,
                   provider, model, upstream_request_id,
                   input_tokens, output_tokens,
                   cache_read_tokens, cache_creation_tokens,
                   cost_usd, latency_ms, proxy_latency_ms, upstream_latency_ms,
                   status, stop_reason, source)
                VALUES
                  ($1, $2, $3,
                   $4, $5, $6,
                   $7, $8,
                   $9, $10,
                   $11, $12, $13, $14,
                   $15, $16, $17)
                RETURNING id
                """,
                user_id, agent_instance_id, message_id,
                provider or "unknown", model, parsed.upstream_request_id,
                parsed.input_tokens, parsed.output_tokens,
                parsed.cache_read_tokens, parsed.cache_creation_tokens,
                cost_usd, latency_ms, proxy_latency_ms, upstream_latency_ms,
                parsed.status, parsed.stop_reason, source,
            )
            return row["id"]
    except Exception:
        _log.exception(
            "usage_recorder.record_failed",
            extra={
                "user_id": str(user_id),
                "agent_instance_id": str(agent_instance_id),
                "message_id": str(message_id) if message_id else None,
                "contract": contract,
                "provider": provider,
                "model": model,
            },
        )
        return None


__all__ = [
    "ParsedUsage",
    "record_usage",
    "resolve_provider",
]
