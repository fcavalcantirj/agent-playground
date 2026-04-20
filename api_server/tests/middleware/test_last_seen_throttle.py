"""D-22c-MIG-05 acceptance tests for the per-worker last_seen_at throttle.

The SessionMiddleware UPDATEs ``sessions.last_seen_at`` at most once every
60s per session per worker. The throttle cache is a per-worker in-memory
dict on ``app.state.session_last_seen`` (no Redis in the Python stack).

Covers:
  * Two rapid requests with the same cookie in the same worker →
    exactly ONE ``UPDATE sessions SET last_seen_at`` fires.
  * After rewinding the cache entry to "now - 61s", the next request
    fires a second UPDATE.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _seed_user_and_session(pool):
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, display_name, provider, sub, email) "
            "VALUES (gen_random_uuid(), $1, 'google', $2, $3) RETURNING id::text",
            "Throttle User",
            f"sub-{uuid.uuid4()}",
            f"throttle-{uuid.uuid4()}@example.com",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2)
            RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )
    return user_id, session_id


async def _count_last_seen_updates(pool, session_id) -> datetime:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT last_seen_at FROM sessions WHERE id = $1", session_id,
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_two_requests_in_same_worker_trigger_one_update(
    session_test_app, session_client,
):
    """Two rapid requests with same cookie → exactly ONE UPDATE fires.

    Observed via ``sessions.last_seen_at``:
      * after request 1: last_seen_at bumped to t1 (≠ seeded timestamp)
      * after request 2 (same session within the 60s window):
        last_seen_at unchanged from t1
    """
    app, pool = session_test_app
    # Fresh cache so the first request MUST hit the UPDATE path.
    app.state.session_last_seen = {}

    _user_id, session_id = await _seed_user_and_session(pool)
    seed_last_seen = await _count_last_seen_updates(pool, session_id)

    # Request 1 — UPDATE fires; last_seen_at moves forward.
    r1 = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r1.status_code == 200, r1.text
    after_r1 = await _count_last_seen_updates(pool, session_id)
    assert after_r1 > seed_last_seen, (
        f"request 1 did not bump last_seen_at: seed={seed_last_seen} "
        f"after_r1={after_r1}"
    )

    # Request 2 (immediately after) — throttle hits; last_seen_at MUST NOT move.
    r2 = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r2.status_code == 200, r2.text
    after_r2 = await _count_last_seen_updates(pool, session_id)
    assert after_r2 == after_r1, (
        f"request 2 issued a second UPDATE within the 60s throttle window: "
        f"after_r1={after_r1} after_r2={after_r2} (D-22c-MIG-05 regression)"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_request_after_60s_triggers_second_update(
    session_test_app, session_client,
):
    """After rewinding the cache entry by >60s → next request re-UPDATES."""
    app, pool = session_test_app
    app.state.session_last_seen = {}

    _user_id, session_id = await _seed_user_and_session(pool)

    # Request 1 — seeds the cache + fires the first UPDATE.
    r1 = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r1.status_code == 200, r1.text
    after_r1 = await _count_last_seen_updates(pool, session_id)

    # Rewind the cache entry to 61s ago — the middleware sees the delta as
    # exceeding LAST_SEEN_THROTTLE (60s) and must re-issue the UPDATE.
    cache_key = uuid.UUID(session_id)
    assert cache_key in app.state.session_last_seen, (
        "request 1 failed to populate the throttle cache"
    )
    app.state.session_last_seen[cache_key] = (
        datetime.now(timezone.utc) - timedelta(seconds=61)
    )

    # Request 2 — cache entry expired, UPDATE must fire again.
    # Small sleep ensures NOW() at PG time is strictly greater than after_r1.
    import asyncio

    await asyncio.sleep(0.05)
    r2 = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r2.status_code == 200, r2.text
    after_r2 = await _count_last_seen_updates(pool, session_id)
    assert after_r2 > after_r1, (
        f"request 2 did not re-issue UPDATE after 61s rewind: "
        f"after_r1={after_r1} after_r2={after_r2}"
    )
