"""Phase 22c-06 Task 3 — IdempotencyMiddleware user_id awareness.

Verifies the Option-A pass-through behavior from RESEARCH §Pitfall 4:

  * Anonymous request (no ``ap_session`` cookie) → NO idempotency
    reservation; the route-layer's ``require_user`` returns 401. No row
    lands in ``idempotency_keys``.
  * Authenticated request → idempotency cache behaves normally. Second
    POST with the same ``Idempotency-Key`` replays the cached verdict
    and the ``idempotency_keys`` row is owned by the authenticated user.

Uses the full ``async_client`` fixture (post-22c-06 conftest TRUNCATE
list) so the whole middleware stack (SessionMiddleware → IdempotencyMiddleware
→ routes → require_user) runs end-to-end. Idempotency row ownership is
confirmed by a direct DB query against the ``authenticated_cookie``
fixture's ``_user_id``.
"""
from __future__ import annotations

import uuid

import pytest


def _idem_key() -> str:
    """Fresh uuid4 per test — avoids cross-test collisions in the pool."""
    return str(uuid.uuid4())


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_anonymous_pass_through(async_client, db_pool):
    """Anonymous POST /v1/runs with Idempotency-Key → 401; no DB row.

    Expectations:
      * Route-layer ``require_user`` fires BEFORE the run executes (it
        runs at the top of create_run, above the Bearer parse).
      * IdempotencyMiddleware sees ``scope['state']['user_id'] is None``
        and skips the reservation → zero rows in idempotency_keys.
      * Response status is 401 (UNAUTHORIZED / ap_session).
    """
    key = _idem_key()
    body = {"recipe_name": "hermes", "model": "m", "prompt": "anon"}

    # No Cookie header → SessionMiddleware sets user_id=None → route-layer
    # require_user returns a 401 JSONResponse BEFORE any DB work.
    resp = await async_client.post(
        "/v1/runs",
        headers={
            "Authorization": "Bearer sk-test",
            "Idempotency-Key": key,
        },
        json=body,
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    # Verify no idempotency_keys row was written (belt-and-suspenders for
    # the pass-through: if the middleware had still reserved, the row
    # would exist even though the route rejected).
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM idempotency_keys WHERE key = $1", key
        )
    assert count == 0, (
        f"anonymous request created an idempotency_keys row (count={count}) "
        "— IdempotencyMiddleware should have passed through without "
        "reserving"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_authenticated_caches(
    async_client, authenticated_cookie, db_pool, monkeypatch,
):
    """Authenticated POST /v1/runs caches the verdict on the authenticated
    user; second POST with same key replays; DB row is owned by that user.

    Mirrors ``test_idempotency.py::test_same_key_returns_cache`` but
    verifies the ``idempotency_keys.user_id`` FK points at the OAuth
    user seeded by ``authenticated_cookie`` rather than the deleted
    anonymous seed.
    """
    call_count = {"n": 0}

    async def counted_to_thread(fn, *a, **kw):
        call_count["n"] += 1
        return {
            "recipe": "hermes", "model": "m", "prompt": "p",
            "pass_if": "exit_zero", "verdict": "PASS",
            "category": "PASS", "detail": "",
            "exit_code": 0, "wall_time_s": 0.1,
            "filtered_payload": "", "stderr_tail": None,
        }

    monkeypatch.setattr("asyncio.to_thread", counted_to_thread)

    key = _idem_key()
    body = {"recipe_name": "hermes", "model": "m", "prompt": "authed"}
    headers = {
        "Authorization": "Bearer sk-test",
        "Idempotency-Key": key,
        "Cookie": authenticated_cookie["Cookie"],
    }

    r1 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r1.status_code == 200, r1.text
    run_id_1 = r1.json()["run_id"]
    assert call_count["n"] == 1

    r2 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r2.status_code == 200, r2.text
    assert r2.json()["run_id"] == run_id_1, (
        "cached replay must return the SAME run_id as the first call"
    )
    assert call_count["n"] == 1, (
        f"runner was called {call_count['n']} times on the replay; the "
        "cached entry's user_id must match the authenticated user so the "
        "cache HIT path fires"
    )

    # Verify exactly one idempotency_keys row exists AND its user_id
    # matches the authenticated_cookie fixture's _user_id.
    expected_user_id = authenticated_cookie["_user_id"]
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id::text, key FROM idempotency_keys WHERE key = $1",
            key,
        )
    assert len(rows) == 1, (
        f"expected exactly one idempotency_keys row for key={key!r}; "
        f"got {len(rows)}"
    )
    assert rows[0]["user_id"] == expected_user_id, (
        f"idempotency_keys row is owned by {rows[0]['user_id']!r}; "
        f"expected the authenticated user {expected_user_id!r}"
    )
