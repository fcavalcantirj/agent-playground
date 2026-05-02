"""Phase 23-02 (D-09) — POST /v1/agents/:id/messages requires Idempotency-Key.

Plan: 23-02 enforces D-09 — the existing POST /v1/agents/:id/messages
handler MUST require an Idempotency-Key header. Missing/empty/whitespace
values return 400 with a Stripe-shape envelope. The check runs BEFORE
``require_user`` (Pitfall 8) so a request-shape failure is independent
of auth state and cannot leak any cross-user idempotency cache state.

Real Postgres + Redis via testcontainers (golden rule #1 — no mocks).
The ``async_client`` + ``authenticated_cookie`` + ``db_pool`` fixtures
come from ``tests/conftest.py``; the ``_seed_agent_for_user`` helper is
re-used (imported) from ``tests/routes/test_agent_messages_post.py`` so
there is one source of truth for the agent-seeding shape.

Coverage:

  * ``test_post_message_returns_400_when_idempotency_key_header_missing``
  * ``test_post_message_returns_400_when_idempotency_key_whitespace``
  * ``test_post_message_400_fires_before_require_user`` — D-09 + Pitfall 8
    ordering invariant
  * ``test_post_message_with_valid_idempotency_key_returns_202`` — happy
    path (regression sanity for the existing 202 contract)
"""
from __future__ import annotations

from uuid import uuid4

import pytest

# Re-use the seed helper from the analog test module — keeps the
# agent-seeding shape (agent_instances + agent_containers) DRY.
from .test_agent_messages_post import _seed_agent_for_user


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def test_post_message_returns_400_when_idempotency_key_header_missing(
    async_client, db_pool, authenticated_cookie,
):
    """Missing Idempotency-Key header → 400 INVALID_REQUEST envelope."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},  # NO Idempotency-Key
        json={"content": "hi"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "Idempotency-Key"
    assert "required" in body["error"]["message"].lower()


async def test_post_message_returns_400_when_idempotency_key_whitespace(
    async_client, db_pool, authenticated_cookie,
):
    """Whitespace-only Idempotency-Key → 400 INVALID_REQUEST envelope."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={
            "Cookie": authenticated_cookie["Cookie"],
            "Idempotency-Key": "   ",
        },
        json={"content": "hi"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "Idempotency-Key"


async def test_post_message_400_fires_before_require_user(async_client, db_pool):
    """D-09 + Pitfall 8: missing-header check runs BEFORE auth check.

    No Cookie header AND no Idempotency-Key → 400 (NOT 401). This proves
    the check ordering invariant: a request-shape failure is independent
    of auth state, which avoids any cross-user idempotency cache-leak
    risk surfaced in RESEARCH §Pitfall 8.
    """
    agent_id = uuid4()  # need not exist; the 400 fires before lookup
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={},  # no Cookie, no Idempotency-Key
        json={"content": "hi"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "Idempotency-Key"


async def test_post_message_with_valid_idempotency_key_returns_202(
    async_client, db_pool, authenticated_cookie,
):
    """Valid Idempotency-Key + valid auth → existing 202 happy path unchanged."""
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={
            "Cookie": authenticated_cookie["Cookie"],
            "Idempotency-Key": str(uuid4()),
        },
        json={"content": "hi"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert "message_id" in body
    assert body["status"] == "pending"


async def test_post_message_replay_returns_cached_202(
    async_client, db_pool, authenticated_cookie,
):
    """Plan 23-02 must_haves truth #3: same Idempotency-Key replays the
    cached 202 response (existing IdempotencyMiddleware behavior intact).

    Sends two POSTs with the SAME Idempotency-Key + identical body; the
    second call must return the SAME message_id as the first (proves the
    middleware cached the chat-path 202 verdict per Phase 22c.3-08
    cache-write extension to status_code in {200, 202}).
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    key = str(uuid4())
    headers = {
        "Cookie": authenticated_cookie["Cookie"],
        "Idempotency-Key": key,
    }
    body_json = {"content": "replay-me"}

    r1 = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json=body_json,
    )
    assert r1.status_code == 202, r1.text
    msg_id_1 = r1.json()["message_id"]

    r2 = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json=body_json,
    )
    # Idempotency replay returns the cached verdict — same message_id.
    # Note: middleware replays cached body at status 200 (see _send_json
    # in middleware/idempotency.py — replay always emits 200 regardless
    # of original status; the cached body retains the original 202 shape).
    assert r2.status_code in (200, 202), r2.text
    assert r2.json()["message_id"] == msg_id_1, (
        f"replay returned new message_id {r2.json()['message_id']} != "
        f"original {msg_id_1} — cache miss (middleware regression)"
    )

    # Defense in depth: only ONE inapp_messages row was created.
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM inapp_messages WHERE agent_id=$1",
            agent_id,
        )
    assert count == 1, (
        f"replay inserted a duplicate row; got {count} rows, expected 1"
    )
