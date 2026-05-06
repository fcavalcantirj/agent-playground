"""Phase 27 + Phase 29 — unit + integration tests for usage_recorder.

Real Postgres via testcontainers (golden rule #1 — no mocks for core
substrate). Tests cover:

  * resolve_provider — extract runtime.provider from recipe dict
  * _parse_openai_compat — both OpenAI shape AND Anthropic-passthrough shape
  * _parse_openai_compat — cache token paths (Anthropic + OpenAI o1 details)
  * _parse_anthropic_native — non-streaming Anthropic /v1/messages JSON dict
    shape (Phase 29 D-12; the streaming path lives in services/stream_parser.py)
  * record_usage — INSERT happy path for openai_compat / openrouter
  * record_usage — INSERT for anthropic-direct path with cache tokens
  * record_usage — INSERT for stripped contract (a2a_jsonrpc) → status='unknown'
  * record_usage — cost computation reconciles with cost_weights seed
  * record_usage — missing cost_weights row → cost_usd=0, no exception
  * record_usage — recorder failure (e.g. invalid agent_instance_id) is
    swallowed; returns None instead of raising
  * record_usage — Phase 29 proxy_latency_ms + upstream_latency_ms kwargs
    write to migration-013 columns (or NULL when omitted)

The cost-arithmetic asserts use the migration-010 seeded weights (haiku
$1/$5 per 1M tokens etc.) — test breaks if the seed values drift, which
is the right kind of break (it surfaces a pricing regression).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest

from api_server.services import usage_recorder


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers — seed a user + agent_instance pair so the FK constraints pass
# ---------------------------------------------------------------------------


async def _seed_user_and_agent(
    pool: asyncpg.Pool, *, model: str = "anthropic/claude-haiku-4.5"
) -> tuple[UUID, UUID]:
    user_id = uuid4()
    agent_id = uuid4()
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "usage-test",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'test-recipe', $3, $4)
            """,
            agent_id, user_id, model, name,
        )
    return user_id, agent_id


async def _fetch_one_log(
    pool: asyncpg.Pool, user_id: UUID
) -> dict[str, object]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM usage_logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            user_id,
        )
    assert row is not None, f"no usage_logs row for user {user_id}"
    return dict(row)


# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------


def test_resolve_provider_reads_runtime_block() -> None:
    assert usage_recorder.resolve_provider({"runtime": {"provider": "anthropic"}}) == "anthropic"
    assert usage_recorder.resolve_provider({"runtime": {"provider": "openrouter"}}) == "openrouter"


def test_resolve_provider_returns_none_when_missing() -> None:
    assert usage_recorder.resolve_provider({}) is None
    assert usage_recorder.resolve_provider({"runtime": {}}) is None
    assert usage_recorder.resolve_provider(None) is None
    assert usage_recorder.resolve_provider({"runtime": "not-a-dict"}) is None


def test_parse_openai_compat_openai_shape() -> None:
    """Standard OpenAI/OpenRouter envelope — prompt_tokens / completion_tokens."""
    response = {
        "id": "gen-abc-123",
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {
            "prompt_tokens": 14,
            "completion_tokens": 4,
            "total_tokens": 18,
        },
    }
    parsed = usage_recorder._parse_openai_compat(response, "openrouter")
    assert parsed.input_tokens == 14
    assert parsed.output_tokens == 4
    assert parsed.cache_read_tokens == 0
    assert parsed.cache_creation_tokens == 0
    assert parsed.upstream_request_id == "gen-abc-123"
    assert parsed.stop_reason == "stop"
    assert parsed.status == "success"


def test_parse_openai_compat_anthropic_passthrough() -> None:
    """Bot exposes OpenAI envelope but preserves Anthropic native usage shape."""
    response = {
        "id": "msg_01XhTAJWvcpkQzSCJhJzfmaH",
        "choices": [{"finish_reason": "end_turn", "message": {"content": "ok"}}],
        "usage": {
            "input_tokens": 14,
            "output_tokens": 4,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 50,
        },
    }
    parsed = usage_recorder._parse_openai_compat(response, "anthropic")
    assert parsed.input_tokens == 14
    assert parsed.output_tokens == 4
    assert parsed.cache_read_tokens == 100
    assert parsed.cache_creation_tokens == 50
    assert parsed.upstream_request_id == "msg_01XhTAJWvcpkQzSCJhJzfmaH"
    assert parsed.stop_reason == "end_turn"
    assert parsed.status == "success"


def test_parse_openai_compat_o1_cached_tokens() -> None:
    """OpenAI o1+ surfaces cache hits under prompt_tokens_details.cached_tokens."""
    response = {
        "id": "chatcmpl-o1-test",
        "usage": {
            "prompt_tokens": 200,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 80},
        },
    }
    parsed = usage_recorder._parse_openai_compat(response, "openai")
    assert parsed.input_tokens == 200
    assert parsed.cache_read_tokens == 80


def test_parse_openai_compat_missing_usage() -> None:
    """Bot stripped usage entirely — status='unknown', preserve id."""
    response = {"id": "gen-no-usage", "choices": [{"message": {"content": "x"}}]}
    parsed = usage_recorder._parse_openai_compat(response, "openrouter")
    assert parsed.status == "unknown"
    assert parsed.input_tokens == 0
    assert parsed.upstream_request_id == "gen-no-usage"


# ---------------------------------------------------------------------------
# DB integration tests
# ---------------------------------------------------------------------------


async def test_record_usage_openrouter_haiku_cost_arithmetic(
    db_pool: asyncpg.Pool,
) -> None:
    """End-to-end: insert a row for an OpenRouter haiku call, verify USD."""
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="anthropic/claude-haiku-4.5"
    )
    response = {
        "id": "gen-test-123",
        "choices": [{"finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            row_id = await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                response=response,
                latency_ms=850,
            )
    assert row_id is not None

    log = await _fetch_one_log(db_pool, user_id)
    assert log["provider"] == "openrouter"
    assert log["model"] == "anthropic/claude-haiku-4.5"
    assert log["input_tokens"] == 1000
    assert log["output_tokens"] == 500
    assert log["cache_read_tokens"] == 0
    assert log["status"] == "success"
    assert log["stop_reason"] == "stop"
    assert log["upstream_request_id"] == "gen-test-123"
    assert log["latency_ms"] == 850
    # Haiku cost: 1000 * $1/1M + 500 * $5/1M = $0.001 + $0.0025 = $0.0035
    assert log["cost_usd"] == Decimal("0.00350000")


async def test_record_usage_anthropic_direct_with_cache_tokens(
    db_pool: asyncpg.Pool,
) -> None:
    """Anthropic-direct call with prompt cache hits + writes — full cost."""
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="claude-sonnet-4-5"
    )
    response = {
        "id": "msg_anthropic_test",
        "choices": [{"finish_reason": "end_turn"}],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 500,
        },
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider="anthropic",
                model="claude-sonnet-4-5",
                response=response,
                latency_ms=1200,
            )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["provider"] == "anthropic"
    assert log["input_tokens"] == 100
    assert log["output_tokens"] == 50
    assert log["cache_read_tokens"] == 1000
    assert log["cache_creation_tokens"] == 500
    # Sonnet 4.5: $3 input / $15 output / $0.30 cache_read / $3.75 cache_create per 1M
    # 100*3 + 50*15 + 1000*0.30 + 500*3.75 = 300 + 750 + 300 + 1875 = 3225
    # 3225 / 1_000_000 = 0.003225 USD
    assert log["cost_usd"] == Decimal("0.00322500")


async def test_record_usage_stripped_contract_is_unknown(
    db_pool: asyncpg.Pool,
) -> None:
    """a2a_jsonrpc / zeroclaw_native: row written with status='unknown', cost=0."""
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="a2a_jsonrpc",
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                response=None,
                latency_ms=500,
            )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["status"] == "unknown"
    assert log["input_tokens"] == 0
    assert log["output_tokens"] == 0
    assert log["cost_usd"] == Decimal("0E-8")  # NUMERIC zero


async def test_record_usage_missing_cost_weights_logs_warning_no_crash(
    db_pool: asyncpg.Pool, caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown (provider, model) pair: log + cost_usd=0; row still written."""
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="some-unseeded-model"
    )
    response = {
        "id": "gen-no-weights",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10},
    }
    with caplog.at_level("WARNING"):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await usage_recorder.record_usage(
                    conn,
                    user_id=user_id,
                    agent_instance_id=agent_id,
                    message_id=None,
                    contract="openai_compat",
                    provider="openrouter",
                    model="some-unseeded-model",
                    response=response,
                )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["status"] == "success"
    assert log["input_tokens"] == 100
    assert log["cost_usd"] == Decimal("0E-8")
    # The "weights_missing" warning must surface so ops can grep + add the row.
    assert any("weights_missing" in record.message for record in caplog.records)


async def test_record_usage_savepoint_isolates_outer_txn(
    db_pool: asyncpg.Pool,
) -> None:
    """A recorder failure must NOT poison the outer transaction.

    The dispatcher writes record_usage in the same txn as mark_done +
    insert_agent_event. If the recorder's INSERT fails (FK violation,
    constraint, …), the savepoint inside record_usage must roll back
    only the savepoint — the outer txn must survive so the chat reply
    is still durable. This is the load-bearing safety property.
    """
    user_id, real_agent = await _seed_user_and_agent(db_pool)
    bogus_agent = uuid4()  # No matching agent_instances row

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # First a "real" INSERT to verify the outer txn is alive.
            await conn.execute(
                "INSERT INTO usage_logs (user_id, agent_instance_id, "
                "provider, model) VALUES ($1, $2, 'sentinel', 'sentinel')",
                user_id, real_agent,
            )

            # Now the failing record_usage — bogus FK target.
            result = await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=bogus_agent,
                message_id=None,
                contract="openai_compat",
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                response={"id": "x", "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            )
            assert result is None  # Recorder swallowed the FK violation

            # The outer txn MUST still be usable — perform another INSERT
            # that depends on the outer txn not being aborted.
            await conn.execute(
                "INSERT INTO usage_logs (user_id, agent_instance_id, "
                "provider, model) VALUES ($1, $2, 'sentinel2', 'sentinel2')",
                user_id, real_agent,
            )

    # Both sentinel rows must persist after commit.
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_logs WHERE user_id = $1 "
            "AND provider IN ('sentinel', 'sentinel2')",
            user_id,
        )
    assert cnt == 2, "outer txn was aborted by recorder failure"


async def test_record_usage_no_provider_marks_unknown(
    db_pool: asyncpg.Pool,
) -> None:
    """Recipe without runtime.provider → no cost lookup → row='unknown'."""
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    response = {
        "id": "gen-x",
        "usage": {"prompt_tokens": 50, "completion_tokens": 5},
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider=None,
                model="some-model",
                response=response,
            )
    log = await _fetch_one_log(db_pool, user_id)
    # No provider → recorder skips cost computation → row stored as 'unknown'
    # provider field. Tokens still parsed for visibility.
    assert log["provider"] == "unknown"
    assert log["input_tokens"] == 50
    assert log["output_tokens"] == 5
    assert log["cost_usd"] == Decimal("0E-8")


# ---------------------------------------------------------------------------
# Phase 29 — _parse_anthropic_native (non-streaming dict-mode parser)
# ---------------------------------------------------------------------------


def test_parse_anthropic_native_happy_path() -> None:
    """Non-streaming Anthropic /v1/messages response parses to ParsedUsage.

    Shape (verbatim from RESEARCH.md and Anthropic docs):
      {"id":"msg_abc","model":"claude-haiku-4-5",
       "usage":{"input_tokens":42,"output_tokens":17,
                "cache_creation_input_tokens":100,"cache_read_input_tokens":5}}
    """
    response = {
        "id": "msg_abc",
        "model": "claude-haiku-4-5",
        "usage": {
            "input_tokens": 42,
            "output_tokens": 17,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 5,
        },
    }
    parsed = usage_recorder._parse_anthropic_native(response)
    assert parsed.input_tokens == 42
    assert parsed.output_tokens == 17
    assert parsed.cache_creation_tokens == 100
    assert parsed.cache_read_tokens == 5
    assert parsed.upstream_request_id == "msg_abc"
    assert parsed.status == "success"


def test_parse_anthropic_native_missing_cache_fields_default_zero() -> None:
    """Missing cache_* fields default to 0; status still 'success'."""
    response = {
        "id": "msg_no_cache",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    parsed = usage_recorder._parse_anthropic_native(response)
    assert parsed.input_tokens == 5
    assert parsed.output_tokens == 3
    assert parsed.cache_read_tokens == 0
    assert parsed.cache_creation_tokens == 0
    assert parsed.status == "success"


def test_parse_anthropic_native_missing_usage_block_failed() -> None:
    """No usage block at all → status='failed' (Phase 29 D-15 convention).

    Phase 29 widened ck_usage_logs_status to allow 'failed' specifically
    for proxy-side capture failures. The non-streaming parser uses
    'failed' here (not the legacy 'unknown') because this code path is
    a Phase 29 capture; 'unknown' is reserved for legacy stripped
    contracts (a2a_jsonrpc, zeroclaw_native).
    """
    parsed = usage_recorder._parse_anthropic_native({"id": "msg_x"})
    assert parsed.status == "failed"
    assert parsed.input_tokens == 0
    assert parsed.output_tokens == 0


def test_parse_anthropic_native_propagates_stop_reason() -> None:
    """stop_reason from the top-level response surfaces on ParsedUsage."""
    response = {
        "id": "msg_stop",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    parsed = usage_recorder._parse_anthropic_native(response)
    assert parsed.stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# Phase 29 — record_usage signature extension (proxy_latency_ms + upstream_latency_ms)
# ---------------------------------------------------------------------------


async def test_record_usage_persists_proxy_and_upstream_latency_ms(
    db_pool: asyncpg.Pool,
) -> None:
    """Phase 29: passing proxy_latency_ms + upstream_latency_ms writes
    to migration-013 columns of the same name."""
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="anthropic/claude-haiku-4.5"
    )
    response = {
        "id": "gen-with-latency",
        "choices": [{"finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                response=response,
                latency_ms=499,
                proxy_latency_ms=12,
                upstream_latency_ms=487,
            )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["proxy_latency_ms"] == 12
    assert log["upstream_latency_ms"] == 487
    # Legacy latency_ms still populated by the caller for back-compat reads.
    assert log["latency_ms"] == 499


async def test_record_usage_omitted_latency_kwargs_write_null(
    db_pool: asyncpg.Pool,
) -> None:
    """Backward compat: existing callers that don't pass the new kwargs
    must continue to work; the new columns store NULL.

    Pre-Phase-29 callers (Temporal record_usage activity, dispatcher
    paths) don't supply proxy_latency_ms / upstream_latency_ms; they
    must remain operational without code changes.
    """
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="anthropic/claude-haiku-4.5"
    )
    response = {
        "id": "gen-no-new-kwargs",
        "choices": [{"finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                response=response,
                latency_ms=200,
            )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["proxy_latency_ms"] is None
    assert log["upstream_latency_ms"] is None


async def test_record_usage_anthropic_native_dict_mode_via_parser(
    db_pool: asyncpg.Pool,
) -> None:
    """End-to-end: a non-streaming Anthropic dict response parsed by
    _parse_anthropic_native flows through record_usage's openai_compat
    path (because the anthropic-passthrough fallback inside
    _parse_openai_compat already handles the same shape).

    This test pins the assertion that the Phase 29 non-streaming dict
    shape — usage.input_tokens / output_tokens / cache_*_input_tokens —
    is correctly persisted by the existing record_usage() entry point.
    """
    user_id, agent_id = await _seed_user_and_agent(
        db_pool, model="claude-haiku-4-5"
    )
    response = {
        "id": "msg_native_test",
        "model": "claude-haiku-4-5",
        "usage": {
            "input_tokens": 50,
            "output_tokens": 25,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await usage_recorder.record_usage(
                conn,
                user_id=user_id,
                agent_instance_id=agent_id,
                message_id=None,
                contract="openai_compat",
                provider="anthropic",
                model="claude-haiku-4-5",
                response=response,
                latency_ms=320,
                proxy_latency_ms=8,
                upstream_latency_ms=312,
            )
    log = await _fetch_one_log(db_pool, user_id)
    assert log["provider"] == "anthropic"
    assert log["input_tokens"] == 50
    assert log["output_tokens"] == 25
    assert log["upstream_request_id"] == "msg_native_test"
    assert log["proxy_latency_ms"] == 8
    assert log["upstream_latency_ms"] == 312
    # Haiku ($1 input / $5 output per 1M): 50*1 + 25*5 = 175 / 1M
    assert log["cost_usd"] == Decimal("0.00017500")
