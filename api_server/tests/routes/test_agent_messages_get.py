"""Phase 23-03 (D-03 + D-04 + REQ API-02) — GET /v1/agents/:id/messages tests.

Plan 23-03 implements the chat-history endpoint mobile loads on Chat-screen
open. The endpoint returns terminal-state rows from the existing
``inapp_messages`` table (D-01 reuse — NO new tables, NO new migrations)
ordered by ``created_at`` ASC, default limit=200, max=1000.

Status mapping (D-03):
  * ``done``      → emits 2 events: (role=user, content=im.content)
                                    AND (role=assistant, content=im.bot_response)
  * ``failed``    → emits 2 events: (role=user, content=im.content)
                                    AND (role=assistant, kind='error',
                                         content='⚠️ delivery failed: <last_error>')
  * ``pending`` / ``forwarded`` → EXCLUDED from the response (in-flight hidden)

Real Postgres + Redis via testcontainers (golden rule #1 — no mocks). The
``async_client`` + ``authenticated_cookie`` + ``second_authenticated_cookie``
+ ``db_pool`` fixtures come from ``tests/conftest.py``. The
``_seed_agent_for_user`` helper is re-used (imported) from
``tests/routes/test_agent_messages_post.py`` so there is one source of
truth for the agent-seeding shape.

Coverage matrix (≥7 tests required by plan AC):
  * empty agent → 200 + ``messages: []``
  * done row    → emits (user, assistant) pair
  * failed row  → emits (user, error) pair with verbatim "⚠️ delivery failed:" prefix
  * pending/forwarded rows → EXCLUDED (in-flight hidden)
  * ordering   → created_at ASC
  * limit > 1000 → clamped (200 OK, no error)
  * limit < 1   → 400 INVALID_REQUEST envelope (param=limit)
  * cross-user → 404 (avoid existence leak per D-19/D-22c-AUTH)
  * unauthenticated → 401 require_user gate
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

# Re-use the seed helper from the analog POST module — keeps the
# agent-seeding shape (agent_instances + agent_containers) DRY.
from .test_agent_messages_post import _seed_agent_for_user


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def test_get_messages_empty_agent_returns_empty_list(
    async_client, db_pool, authenticated_cookie,
):
    """Cold agent (zero inapp_messages) → 200 + ``{messages: []}``."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"messages": []}


async def test_get_messages_done_row_emits_user_and_assistant(
    async_client, db_pool, authenticated_cookie,
):
    """D-03: a ``done`` row → 2 events (user message, assistant message)."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    # Seed one done row directly via SQL — testing the read path, not the
    # write/state-machine path. The single-seam rule applies to PRODUCTION
    # code, not tests; tests verify behavior across all states the
    # production code might leave the row in.
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, bot_response, created_at)
            VALUES ($1, $2, $3, 'hello', 'done', 'hi back', NOW())
            """,
            uuid4(), agent_id, user_id,
        )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 2, msgs
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["kind"] == "message"
    assert msgs[1]["content"] == "hi back"


async def test_get_messages_failed_row_emits_user_and_error(
    async_client, db_pool, authenticated_cookie,
):
    """D-03: a ``failed`` row → 2 events (user message, error-shaped assistant).

    The verbatim "⚠️ delivery failed: <last_error>" prefix is contractual —
    mobile UI may grep on it. Do NOT alter the wording.
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, last_error, created_at)
            VALUES ($1, $2, $3, 'oops', 'failed', 'bot timeout', NOW())
            """,
            uuid4(), agent_id, user_id,
        )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    msgs = r.json()["messages"]
    assert len(msgs) == 2, msgs
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "oops"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["kind"] == "error"
    # Verbatim prefix (D-03) — mobile UI may match on this exact string.
    assert msgs[1]["content"] == "⚠️ delivery failed: bot timeout"


async def test_get_messages_in_flight_rows_excluded(
    async_client, db_pool, authenticated_cookie,
):
    """D-03: ``pending`` and ``forwarded`` rows are NOT returned.

    In-flight messages are hidden — the user is supposed to see them via
    the SSE stream, not the history snapshot. Mobile renders an in-flight
    "sending..." bubble client-side from the local 202 reply.
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    async with db_pool.acquire() as conn:
        for status in ("pending", "forwarded"):
            await conn.execute(
                """
                INSERT INTO inapp_messages
                    (id, agent_id, user_id, content, status, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                uuid4(), agent_id, user_id, f"msg-{status}", status,
            )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"messages": []}


async def test_get_messages_ordered_ascending(
    async_client, db_pool, authenticated_cookie,
):
    """D-04: ``ORDER BY created_at ASC`` (oldest first).

    Each terminal row contributes 2 events, so the resulting flat list
    interleaves: (user_first, assistant_first, user_second, assistant_second).
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    async with db_pool.acquire() as conn:
        # Insert two done rows with explicit timestamps so ordering is
        # deterministic — the SECOND insert happens to be older than the
        # FIRST insert; the GET response should still order by created_at,
        # not by insert order.
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, bot_response, created_at)
            VALUES ($1, $2, $3, 'second', 'done', 'r2', NOW())
            """,
            uuid4(), agent_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, bot_response, created_at)
            VALUES ($1, $2, $3, 'first', 'done', 'r1', NOW() - INTERVAL '1 second')
            """,
            uuid4(), agent_id, user_id,
        )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    msgs = r.json()["messages"]
    # Order: user(first), assistant(r1), user(second), assistant(r2)
    assert [m["content"] for m in msgs] == ["first", "r1", "second", "r2"]


async def test_get_messages_limit_clamped_to_1000(
    async_client, db_pool, authenticated_cookie,
):
    """D-04: ``limit > 1000`` is clamped server-side; request still 200s."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages?limit=5000",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    # Request succeeds and is internally clamped — no 4xx for over-spec.
    assert r.status_code == 200, r.text


async def test_get_messages_limit_zero_returns_400(
    async_client, db_pool, authenticated_cookie,
):
    """D-04: ``limit < 1`` (zero/negative) → 400 INVALID_REQUEST envelope."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages?limit=0",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "limit"


async def test_get_messages_limit_negative_returns_400(
    async_client, db_pool, authenticated_cookie,
):
    """D-04: negative limit → 400 INVALID_REQUEST envelope."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages?limit=-1",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "limit"


async def test_get_messages_explicit_limit_respected(
    async_client, db_pool, authenticated_cookie,
):
    """``?limit=N`` returns up to N TERMINAL ROWS (each row → up to 2 events).

    Seed 3 done rows and request limit=2 — response should contain at most
    4 events (2 rows × 2 events each).
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    async with db_pool.acquire() as conn:
        for i in range(3):
            await conn.execute(
                """
                INSERT INTO inapp_messages
                    (id, agent_id, user_id, content, status, bot_response, created_at)
                VALUES ($1, $2, $3, $4, 'done', $5, NOW() + ($6 || ' ms')::interval)
                """,
                uuid4(), agent_id, user_id,
                f"msg-{i}", f"reply-{i}", str(i * 10),
            )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages?limit=2",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    msgs = r.json()["messages"]
    # 2 rows × 2 events = 4 events; oldest two rows should appear.
    assert len(msgs) == 4
    assert [m["content"] for m in msgs] == [
        "msg-0", "reply-0", "msg-1", "reply-1",
    ]


async def test_get_messages_cross_user_returns_404(
    async_client, db_pool, authenticated_cookie, second_authenticated_cookie,
):
    """User A asks for user B's agent → 404 (cross-user isolation).

    Threat T-23-V4-XUSER mitigation: ``fetch_agent_instance`` filters at
    the SQL layer by user_id, so the agent appears not-found rather than
    returning 403 (which would leak existence).
    """
    # Bob owns the agent.
    agent_id_b = await _seed_agent_for_user(
        db_pool, second_authenticated_cookie["_user_id"],
    )
    # Alice tries to GET Bob's agent's history.
    r = await async_client.get(
        f"/v1/agents/{agent_id_b}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},  # alice's cookie
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["code"] == "AGENT_NOT_FOUND"


async def test_get_messages_unauthenticated_returns_401(
    async_client, db_pool,
):
    """No ap_session cookie → 401 require_user gate (UNAUTHORIZED envelope)."""
    agent_id = uuid4()
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={},  # no Cookie
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


async def test_get_messages_inapp_message_id_present_for_dedup(
    async_client, db_pool, authenticated_cookie,
):
    """Each event carries ``inapp_message_id`` so the client can dedup
    against SSE replays of the same row.

    Both events emitted from the SAME row share the same id (the row's
    id) — so a client receiving SSE inapp_outbound for row X AFTER the
    history GET can match on this and skip rendering a duplicate bubble.
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    row_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, bot_response, created_at)
            VALUES ($1, $2, $3, 'q', 'done', 'a', NOW())
            """,
            row_id, agent_id, user_id,
        )
    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    msgs = r.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["inapp_message_id"] == str(row_id)
    assert msgs[1]["inapp_message_id"] == str(row_id)
