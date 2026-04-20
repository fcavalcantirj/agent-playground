"""R4: GET /v1/users/me — happy path + 401 envelope + expired/revoked session.

Covers:
  * Valid ``ap_session`` cookie → 200 + SessionUserResponse body shape
  * No cookie → 401 Stripe-shape envelope with ``code=UNAUTHORIZED``
  * Cookie pointing at an expired session → 401 (SessionMiddleware rejects
    at the SELECT-with-expires_at-filter; route never sees user_id)
  * Cookie pointing at a revoked session → 401 (same path)

All four tests exercise ``require_user`` → SessionMiddleware → real PG.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_users_me_200_with_valid_session(
    async_client, authenticated_cookie,
):
    """GET /v1/users/me with valid cookie returns the user's row."""
    r = await async_client.get(
        "/v1/users/me",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Shape assertions — every SessionUserResponse field must be present.
    assert body["id"] == authenticated_cookie["_user_id"]
    assert body["display_name"] == "Alice"
    assert body["email"] == "alice@example.com"
    assert body["provider"] == "google"
    assert "created_at" in body
    # avatar_url is nullable — the authenticated_cookie fixture doesn't set it,
    # so the field is either absent-with-None-default or null.
    assert body.get("avatar_url") is None


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_users_me_401_without_cookie(async_client):
    """No cookie → 401 + Stripe-shape envelope with code=UNAUTHORIZED."""
    r = await async_client.get("/v1/users/me")
    assert r.status_code == 401, r.text
    body = r.json()
    # Envelope shape: {"error": {"code": "...", "type": "...", ...}}.
    assert "error" in body, body
    assert body["error"]["code"] == "UNAUTHORIZED", body
    assert body["error"]["type"] == "unauthorized", body
    assert body["error"]["param"] == "ap_session", body


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_users_me_401_on_expired_session(async_client, db_pool):
    """Session with ``expires_at`` in the past → 401 (SessionMiddleware filter)."""
    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google",
            f"test-sub-{uuid4().hex[:12]}",
            "expired@example.com",
            "Expired User",
        )
        now = datetime.now(timezone.utc)
        expired_session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2)
            RETURNING id::text
            """,
            user_id, now - timedelta(days=60), now - timedelta(hours=1),
        )

    r = await async_client.get(
        "/v1/users/me",
        headers={"Cookie": f"ap_session={expired_session_id}"},
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_users_me_401_on_revoked_session(async_client, db_pool):
    """Session with ``revoked_at`` set → 401 (SessionMiddleware filter)."""
    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google",
            f"test-sub-{uuid4().hex[:12]}",
            "revoked@example.com",
            "Revoked User",
        )
        now = datetime.now(timezone.utc)
        revoked_session_id = await conn.fetchval(
            """
            INSERT INTO sessions
              (user_id, created_at, expires_at, last_seen_at, revoked_at)
            VALUES ($1, $2, $3, $2, $2)
            RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )

    r = await async_client.get(
        "/v1/users/me",
        headers={"Cookie": f"ap_session={revoked_session_id}"},
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
