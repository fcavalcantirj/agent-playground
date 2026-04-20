"""Phase 22b-02 — Pydantic per-kind payloads + event_store CRUD.

Two layers in one file:

1. Payload-shape tests (pure unit, no DB) — exercise
   ``ConfigDict(extra='forbid')`` (D-06: no reply_text/body anywhere),
   field validators (min/max length, enum patterns, ge=0).

2. Store tests (real PG17 via testcontainers, ``api_integration``) —
   live ``insert_agent_event`` happy path + DB-layer CHECK violation
   surface + ``fetch_events_after_seq`` kinds-filter + unknown-kinds
   filter returns ``[]``.

Spike-05 (4-way concurrent seq race) lives in
``tests/test_events_seq_concurrency.py``; spike-04 (batching speedup)
lives in ``tests/test_events_batching_perf.py``.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import asyncpg
import pytest
from pydantic import ValidationError

from api_server.models.events import (
    VALID_KINDS,
    KIND_TO_PAYLOAD,
    ReplySentPayload,
    ReplyFailedPayload,
    AgentReadyPayload,
    AgentErrorPayload,
)


# ---------------------------------------------------------------------------
# Payload tests (no DB)
# ---------------------------------------------------------------------------


def test_valid_kinds_exact():
    assert VALID_KINDS == {
        "reply_sent",
        "reply_failed",
        "agent_ready",
        "agent_error",
    }


def test_kind_to_payload_coverage():
    assert set(KIND_TO_PAYLOAD.keys()) == VALID_KINDS


def test_reply_sent_happy_path():
    p = ReplySentPayload(
        chat_id="152099202",
        length_chars=42,
        captured_at=datetime.utcnow(),
    )
    assert p.chat_id == "152099202"
    assert p.length_chars == 42


def test_reply_sent_rejects_reply_text():
    """D-06 enforcement — extra='forbid' rejects body-shaped fields."""
    with pytest.raises(ValidationError):
        ReplySentPayload(
            chat_id="1",
            length_chars=42,
            captured_at=datetime.utcnow(),
            reply_text="body content",
        )


def test_reply_sent_rejects_body():
    with pytest.raises(ValidationError):
        ReplySentPayload(
            chat_id="1",
            length_chars=42,
            captured_at=datetime.utcnow(),
            body="x",
        )


def test_reply_sent_rejects_empty_chat_id():
    with pytest.raises(ValidationError):
        ReplySentPayload(
            chat_id="",
            length_chars=42,
            captured_at=datetime.utcnow(),
        )


def test_reply_sent_rejects_negative_length():
    with pytest.raises(ValidationError):
        ReplySentPayload(
            chat_id="1",
            length_chars=-1,
            captured_at=datetime.utcnow(),
        )


def test_agent_error_severity_enum():
    AgentErrorPayload(
        severity="ERROR", detail="x", captured_at=datetime.utcnow()
    )
    AgentErrorPayload(
        severity="FATAL", detail="x", captured_at=datetime.utcnow()
    )
    with pytest.raises(ValidationError):
        AgentErrorPayload(
            severity="WARN",
            detail="x",
            captured_at=datetime.utcnow(),
        )


def test_reply_failed_optional_chat_id():
    """ReplyFailedPayload has chat_id optional (often missing in dropped reply)."""
    p = ReplyFailedPayload(
        reason="rate-limited",
        captured_at=datetime.utcnow(),
    )
    assert p.chat_id is None


def test_agent_ready_optional_log_line():
    p = AgentReadyPayload(captured_at=datetime.utcnow())
    assert p.ready_log_line is None


# ---------------------------------------------------------------------------
# Store tests (live PG17 via testcontainers)
# ---------------------------------------------------------------------------

pytestmark_store = pytest.mark.api_integration


@pytest.fixture
async def real_db_pool(db_pool):
    """Alias the conftest ``db_pool`` fixture under the plan-specified name."""
    yield db_pool


ANON_USER_ID = "00000000-0000-0000-0000-000000000001"


async def _seed_container_via_pool(pool: asyncpg.Pool) -> UUID:
    """Insert agent_instance + agent_container, return container UUID.

    Phase 22c-06: seeds users row (ON CONFLICT-safe) first.
    """
    recipe_name = f"events-store-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1::uuid, 'events-store-test-owner')
            ON CONFLICT (id) DO NOTHING
            """,
            ANON_USER_ID,
        )
        instance = await conn.fetchrow(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
            RETURNING id
            """,
            ANON_USER_ID,
            recipe_name,
            name,
        )
        container = await conn.fetchrow(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status)
            VALUES (gen_random_uuid(), $1, $2, $3,
                    'persistent', 'starting')
            RETURNING id
            """,
            instance["id"],
            ANON_USER_ID,
            recipe_name,
        )
    return container["id"]


@pytest.fixture
async def seed_agent_container(real_db_pool):
    """Return a fresh agent_containers UUID seeded against the test DB."""
    cid = await _seed_container_via_pool(real_db_pool)
    return cid


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_insert_single_happy_path(real_db_pool, seed_agent_container):
    from api_server.services.event_store import insert_agent_event

    async with real_db_pool.acquire() as conn:
        seq1 = await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 3,
                "captured_at": "2026-04-18T00:00:00Z",
            },
            correlation_id="abc1",
        )
        seq2 = await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 4,
                "captured_at": "2026-04-18T00:00:01Z",
            },
            correlation_id="abc2",
        )
    assert seq1 == 1 and seq2 == 2


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_kind_check_constraint_at_store_layer(
    real_db_pool, seed_agent_container
):
    from api_server.services.event_store import insert_agent_event

    async with real_db_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await insert_agent_event(
                conn, seed_agent_container, "bogus", {}
            )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_fetch_events_after_seq_kinds_filter(
    real_db_pool, seed_agent_container
):
    from api_server.services.event_store import (
        insert_agent_event,
        fetch_events_after_seq,
    )

    async with real_db_pool.acquire() as conn:
        await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 1,
                "captured_at": "2026-04-18T00:00:00Z",
            },
        )
        await insert_agent_event(
            conn,
            seed_agent_container,
            "agent_error",
            {
                "severity": "ERROR",
                "detail": "x",
                "captured_at": "2026-04-18T00:00:01Z",
            },
        )
        rows = await fetch_events_after_seq(
            conn, seed_agent_container, 0, kinds={"reply_sent"}
        )
    assert len(rows) == 1
    assert rows[0]["kind"] == "reply_sent"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_fetch_events_unknown_kind_returns_empty(
    real_db_pool, seed_agent_container
):
    from api_server.services.event_store import (
        insert_agent_event,
        fetch_events_after_seq,
    )

    async with real_db_pool.acquire() as conn:
        await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 1,
                "captured_at": "2026-04-18T00:00:00Z",
            },
        )
        rows = await fetch_events_after_seq(
            conn, seed_agent_container, 0, kinds={"bogus"}
        )
    assert rows == []
