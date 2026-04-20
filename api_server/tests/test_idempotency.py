"""SC-06 + threat tests for ``IdempotencyMiddleware``.

Covers:

- **SC-06**: second POST with same ``Idempotency-Key`` replays the
  cached verdict without re-running the runner.
- T-19-05-03: same ``Idempotency-Key`` + different request body
  returns 422 IDEMPOTENCY_BODY_MISMATCH (Pitfall 6 mitigation).
- T-19-05-02: cross-user collision is impossible — two users can use
  the same key ``"abc"`` independently (proven via direct DB inserts
  because Phase 19 has only the anonymous user at the HTTP layer).
- 24h TTL honored: a row whose ``expires_at`` is in the past is
  ignored, and the next request re-runs + mints a new ``run_id``.
"""
from __future__ import annotations

import uuid

import pytest

AUTH = {"Authorization": "Bearer sk-test"}


def _key() -> str:
    """Fresh uuid4 per test — avoids cross-test collisions in the shared pool."""
    return str(uuid.uuid4())


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_same_key_returns_cache(
    async_client, authenticated_cookie, monkeypatch,
):
    """SC-06: second POST with same Idempotency-Key returns cached run_id.

    We count runner invocations by patching ``asyncio.to_thread`` with a
    counter-wrapping fake. The second POST MUST NOT increment the
    counter — the middleware's cache hit must short-circuit before the
    route ever calls execute_run. Phase 22c-06: both calls carry the
    ``authenticated_cookie`` so require_user lets them through.
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

    key = _key()
    body = {"recipe_name": "hermes", "model": "m", "prompt": "p"}
    headers = {**AUTH, "Idempotency-Key": key, "Cookie": authenticated_cookie["Cookie"]}

    r1 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r1.status_code == 200, r1.text
    run_id_1 = r1.json()["run_id"]

    r2 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r2.status_code == 200, r2.text
    assert r2.json()["run_id"] == run_id_1
    assert call_count["n"] == 1, (
        f"runner was called {call_count['n']} times; expected 1 "
        "(second call should hit the cache)"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_body_mismatch_returns_422(
    async_client, authenticated_cookie, mock_run_cell,
):
    """T-19-05-03: same key + different body → 422 IDEMPOTENCY_BODY_MISMATCH.

    Phase 22c-06: both POSTs carry the ``authenticated_cookie`` so
    require_user passes; the mismatch is detected at the middleware layer.
    """
    mock_run_cell(verdict_category="PASS")
    key = _key()
    headers = {**AUTH, "Idempotency-Key": key, "Cookie": authenticated_cookie["Cookie"]}

    r1 = await async_client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p1"},
    )
    assert r1.status_code == 200, r1.text

    r2 = await async_client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p2"},
    )
    assert r2.status_code == 422, r2.text
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_BODY_MISMATCH"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_same_key_different_users_isolated(db_pool):
    """T-19-05-02: cross-user ``(user_id, key)`` collision is impossible.

    Pre-22c the codebase had a single HTTP-visible ANONYMOUS user; post-22c
    each test seeds its own user via direct DB insert. This test operates
    at the DB layer, so we stage two users (u1, u2) and verify that the
    UNIQUE constraint on ``(user_id, key)`` allows both users to use
    ``"abc"`` for different runs without collision. If the schema were
    UNIQUE on ``key`` alone the second INSERT would fail — that's what
    T-19-05-02 mitigates.
    """
    async with db_pool.acquire() as conn:
        # Stage two users so cross-user behavior can be proven at the DB
        # layer (no HTTP auth involved).
        u1_row = await conn.fetchrow(
            "INSERT INTO users (id, display_name) "
            "VALUES (gen_random_uuid(), 'u1') RETURNING id::text"
        )
        u1 = u1_row["id"]
        u2_row = await conn.fetchrow(
            "INSERT INTO users (id, display_name) "
            "VALUES (gen_random_uuid(), 'u2') RETURNING id::text"
        )
        u2 = u2_row["id"]

        # Each idempotency_keys row needs a real runs.id → agent_instances.id
        # chain of FKs. Stage agent_instances + runs for both users.
        aid1 = await conn.fetchval(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model) "
            "VALUES (gen_random_uuid(), $1, 'x', 'm') RETURNING id::text",
            u1,
        )
        aid2 = await conn.fetchval(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model) "
            "VALUES (gen_random_uuid(), $1, 'x', 'm') RETURNING id::text",
            u2,
        )
        # ULIDs are 26-char Crockford base32; handcrafted literals
        # that happen to be Crockford-legal are fine for test data.
        rid1 = "01HQZX9MZVJ5KQXYZ1111111AA"
        rid2 = "01HQZX9MZVJ5KQXYZ2222222BB"
        await conn.execute(
            "INSERT INTO runs (id, agent_instance_id, prompt) "
            "VALUES ($1, $2, 'p')",
            rid1, aid1,
        )
        await conn.execute(
            "INSERT INTO runs (id, agent_instance_id, prompt) "
            "VALUES ($1, $2, 'p')",
            rid2, aid2,
        )

        # Both users insert with key='abc' — different body hashes.
        await conn.execute(
            "INSERT INTO idempotency_keys "
            "(user_id, key, run_id, verdict_json, "
            " request_body_hash, expires_at) "
            "VALUES ($1, 'abc', $2, '{}'::jsonb, 'h1', "
            "        NOW() + INTERVAL '1 hour')",
            u1, rid1,
        )
        await conn.execute(
            "INSERT INTO idempotency_keys "
            "(user_id, key, run_id, verdict_json, "
            " request_body_hash, expires_at) "
            "VALUES ($1, 'abc', $2, '{}'::jsonb, 'h2', "
            "        NOW() + INTERVAL '1 hour')",
            u2, rid2,
        )

        # Both rows coexist — T-19-05-02 proven.
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM idempotency_keys WHERE key = 'abc'"
        )
        assert count == 2, (
            f"expected 2 rows (one per user); got {count} — schema UNIQUE "
            "constraint is too tight and cross-user isolation breaks"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_expired_key_re_runs(
    async_client, authenticated_cookie, mock_run_cell, db_pool,
):
    """24h TTL: expiring the cache row makes the next request re-run."""
    mock_run_cell(verdict_category="PASS")
    key = _key()
    body = {"recipe_name": "hermes", "model": "m", "prompt": "p"}
    headers = {**AUTH, "Idempotency-Key": key, "Cookie": authenticated_cookie["Cookie"]}

    r1 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r1.status_code == 200, r1.text
    rid1 = r1.json()["run_id"]

    # Fast-forward: flip the row's expires_at into the past so the
    # middleware's `expires_at > NOW()` predicate filters it out.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE idempotency_keys SET expires_at = NOW() - INTERVAL '1 hour' "
            "WHERE key = $1",
            key,
        )

    r2 = await async_client.post("/v1/runs", headers=headers, json=body)
    assert r2.status_code == 200, r2.text
    # A fresh run_id is minted because the old cache entry is expired.
    assert r2.json()["run_id"] != rid1, (
        "expired idempotency row should force a re-run; got a replay instead"
    )
