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
