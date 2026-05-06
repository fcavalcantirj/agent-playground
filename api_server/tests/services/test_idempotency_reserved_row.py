"""Phase 29 Plan 04 Task 3 — AMD-03 reserved-row idempotency tests.

Real PG17 via testcontainers (golden rule #1). Migration 013 has
already added the ``status`` column + relaxed ``verdict_json`` to
NULLABLE on ``idempotency_keys`` (Plan 29-02 shipped 2026-05-06).

Coverage matrix (8 tests):

  1. ``test_insert_reserved_row_creates_in_flight_row``
  2. ``test_insert_reserved_row_returns_true_on_first_call``
  3. ``test_insert_reserved_row_returns_false_on_duplicate``
  4. ``test_poll_for_completion_returns_success_verdict``
  5. ``test_poll_for_completion_returns_none_on_timeout``
  6. ``test_poll_for_completion_returns_none_on_status_failed``
  7. ``test_concurrent_retry_single_charge_invariant`` — load-bearing
     AMD-03 invariant (counter == 1, NOT 2)
  8. ``test_existing_primitives_unchanged`` — regression: chat-path
     callers continue to work
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import asyncpg
import pytest

from api_server.services.idempotency import (
    check_or_reserve,
    finalize_reserved_row,
    hash_body,
    insert_reserved_row,
    poll_for_completion,
    write_idempotency,
)


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(pool: asyncpg.Pool) -> UUID:
    """Insert a fresh user for an isolated idempotency_keys row scope."""
    uid = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            uid, "idem-amd03-test",
        )
    return uid


# ---------------------------------------------------------------------------
# Test 1 — insert_reserved_row creates an in_flight row
# ---------------------------------------------------------------------------


async def test_insert_reserved_row_creates_in_flight_row(
    db_pool: asyncpg.Pool,
) -> None:
    """First call creates a row with status='in_flight', verdict_json IS NULL."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-" + uuid4().hex
    body_hash = hash_body(b'{"prompt":"hi"}')

    async with db_pool.acquire() as conn:
        reserved = await insert_reserved_row(
            conn, user_id=user_id, key=key,
            request_body_hash=body_hash, ttl_seconds=3600,
        )
        assert reserved is True
        row = await conn.fetchrow(
            """
            SELECT status, verdict_json, request_body_hash,
                   expires_at > NOW() AS not_expired
            FROM idempotency_keys
            WHERE user_id=$1 AND key=$2
            """,
            user_id, key,
        )
    assert row is not None
    assert row["status"] == "in_flight"
    assert row["verdict_json"] is None
    assert row["request_body_hash"] == body_hash
    assert row["not_expired"] is True


# ---------------------------------------------------------------------------
# Test 2 — first call returns True
# ---------------------------------------------------------------------------


async def test_insert_reserved_row_returns_true_on_first_call(
    db_pool: asyncpg.Pool,
) -> None:
    """First insert wins the in-flight slot → ``reserved=True``."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-first-" + uuid4().hex

    async with db_pool.acquire() as conn:
        reserved = await insert_reserved_row(
            conn, user_id=user_id, key=key,
            request_body_hash="hashfirst",
        )
    assert reserved is True


# ---------------------------------------------------------------------------
# Test 3 — duplicate returns False (ON CONFLICT DO NOTHING)
# ---------------------------------------------------------------------------


async def test_insert_reserved_row_returns_false_on_duplicate(
    db_pool: asyncpg.Pool,
) -> None:
    """Second insert with same (user_id, key) returns False; existing row unchanged."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-dupe-" + uuid4().hex

    async with db_pool.acquire() as conn:
        first = await insert_reserved_row(
            conn, user_id=user_id, key=key,
            request_body_hash="hashfirst",
        )
        assert first is True

        # Second insert — same (user_id, key); body_hash differs but
        # ON CONFLICT DO NOTHING means we don't overwrite. Returns False.
        second = await insert_reserved_row(
            conn, user_id=user_id, key=key,
            request_body_hash="hashsecond-different",
        )
    assert second is False

    # Existing row's body hash is still the FIRST value — never overwritten.
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, request_body_hash FROM idempotency_keys "
            "WHERE user_id=$1 AND key=$2",
            user_id, key,
        )
    assert row is not None
    assert row["status"] == "in_flight"
    assert row["request_body_hash"] == "hashfirst"


# ---------------------------------------------------------------------------
# Test 4 — poll_for_completion returns the verdict on success
# ---------------------------------------------------------------------------


async def test_poll_for_completion_returns_success_verdict(
    db_pool: asyncpg.Pool,
) -> None:
    """When status flips to 'success', poll_for_completion returns verdict_json."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-poll-" + uuid4().hex

    async with db_pool.acquire() as conn:
        await insert_reserved_row(
            conn, user_id=user_id, key=key, request_body_hash="hashpoll",
        )

    expected_verdict = {"status_code": 200, "tokens": 99, "label": "winner"}

    async def _flipper() -> None:
        # Flip the row to success after a short delay so poll has to spin.
        await asyncio.sleep(0.20)
        async with db_pool.acquire() as conn:
            await finalize_reserved_row(
                conn, user_id=user_id, key=key,
                verdict_json=expected_verdict, status="success",
            )

    async def _poller() -> dict | None:
        async with db_pool.acquire() as conn:
            return await poll_for_completion(
                conn, user_id=user_id, key=key,
                max_wait_s=2.0, poll_interval_s=0.05,
            )

    flip_task = asyncio.create_task(_flipper())
    result = await _poller()
    await flip_task

    assert result == expected_verdict


# ---------------------------------------------------------------------------
# Test 5 — poll returns None on timeout
# ---------------------------------------------------------------------------


async def test_poll_for_completion_returns_none_on_timeout(
    db_pool: asyncpg.Pool,
) -> None:
    """A row that stays 'in_flight' past max_wait_s returns None."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-timeout-" + uuid4().hex

    async with db_pool.acquire() as conn:
        await insert_reserved_row(
            conn, user_id=user_id, key=key, request_body_hash="hashtimeout",
        )
        # Don't finalize — poll should time out.
        result = await poll_for_completion(
            conn, user_id=user_id, key=key,
            max_wait_s=0.30, poll_interval_s=0.05,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Test 6 — poll returns None on status='failed'
# ---------------------------------------------------------------------------


async def test_poll_for_completion_returns_none_on_status_failed(
    db_pool: asyncpg.Pool,
) -> None:
    """Status='failed' surfaces as None — caller decides retry-from-scratch."""
    user_id = await _seed_user(db_pool)
    key = "amd03-key-failed-" + uuid4().hex

    async with db_pool.acquire() as conn:
        await insert_reserved_row(
            conn, user_id=user_id, key=key, request_body_hash="hashfailed",
        )
        await finalize_reserved_row(
            conn, user_id=user_id, key=key,
            verdict_json={"error": "upstream_500"}, status="failed",
        )

        result = await poll_for_completion(
            conn, user_id=user_id, key=key,
            max_wait_s=1.0, poll_interval_s=0.05,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Test 7 — concurrent retry single-charge invariant (LOAD-BEARING)
# ---------------------------------------------------------------------------


async def test_concurrent_retry_single_charge_invariant(
    db_pool: asyncpg.Pool,
) -> None:
    """Two coroutines 50ms apart with same key → upstream called ONCE.

    This is the AMD-03 load-bearing invariant — the same one PROBE-VAL-06
    demonstrated. Without the reserved-row pattern the existing primitive
    double-charges; with the pattern the second caller polls and replays
    the first's verdict.

    counter == 1 (NOT 2) is the test of record.
    """
    user_id = await _seed_user(db_pool)
    key = "amd03-race-" + uuid4().hex
    body_hash = hash_body(b'{"prompt":"race-test"}')

    counter = {"upstream_calls": 0}
    expected_verdict = {"status_code": 200, "tokens": 42}

    async def _try_idempotency_or_forward(label: str) -> dict | None:
        """The pattern Plan 29-04's route handler implements.

        - Try to reserve the in-flight slot. If we win, "call upstream"
          (increment counter), then finalize with the verdict.
        - If we lose, poll for completion and return the cached verdict.
        """
        async with db_pool.acquire() as conn:
            reserved = await insert_reserved_row(
                conn, user_id=user_id, key=key,
                request_body_hash=body_hash,
            )
        if reserved:
            # We won — simulate the upstream call (3s like PROBE-VAL-06).
            counter["upstream_calls"] += 1
            await asyncio.sleep(0.5)
            async with db_pool.acquire() as conn:
                await finalize_reserved_row(
                    conn, user_id=user_id, key=key,
                    verdict_json=expected_verdict, status="success",
                )
            return expected_verdict
        else:
            # We lost — poll for the winner's verdict.
            async with db_pool.acquire() as conn:
                return await poll_for_completion(
                    conn, user_id=user_id, key=key,
                    max_wait_s=5.0, poll_interval_s=0.05,
                )

    async def _start_two() -> tuple[dict | None, dict | None]:
        t1 = asyncio.create_task(_try_idempotency_or_forward("a"))
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(_try_idempotency_or_forward("b"))
        return await asyncio.gather(t1, t2)

    a, b = await _start_two()

    # Single-charge invariant: upstream called EXACTLY ONCE despite
    # two concurrent attempts.
    assert counter["upstream_calls"] == 1, (
        f"AMD-03 invariant broken: upstream called {counter['upstream_calls']} times; "
        "expected exactly 1 (single-charge under concurrent retries)"
    )
    # Both callers see the SAME verdict (winner replays to loser).
    assert a == expected_verdict
    assert b == expected_verdict


# ---------------------------------------------------------------------------
# Test 8 — existing primitives unchanged (regression)
# ---------------------------------------------------------------------------


async def test_existing_primitives_unchanged(db_pool: asyncpg.Pool) -> None:
    """check_or_reserve + write_idempotency continue to work for chat-path callers.

    Migration 013 added a ``status`` column with default 'success' — old
    callers don't pass ``status`` and the column default carries them
    through. Any verdict_json round-trip must still hit/match.
    """
    user_id = await _seed_user(db_pool)
    key = "legacy-" + uuid4().hex
    body = b'{"recipe":"hermes","model":"m"}'
    body_hash_1 = hash_body(body)

    async with db_pool.acquire() as conn:
        # First call: miss → write.
        tag, verdict = await check_or_reserve(conn, user_id, key, body_hash_1)
        assert tag == "miss"
        assert verdict is None
        await write_idempotency(
            conn, user_id, key, body_hash_1,
            run_id="01HQZX9MZVJ5KQXYZ1111111AA",
            verdict_json={"run_id": "01HQZX9MZVJ5KQXYZ1111111AA", "verdict": "PASS"},
        )

        # Second call: hit → replay.
        tag2, verdict2 = await check_or_reserve(conn, user_id, key, body_hash_1)
        assert tag2 == "hit"
        assert verdict2 == {
            "run_id": "01HQZX9MZVJ5KQXYZ1111111AA",
            "verdict": "PASS",
        }

        # Third call: same key, DIFFERENT body → mismatch.
        body_hash_2 = hash_body(b'{"recipe":"hermes","model":"different"}')
        tag3, verdict3 = await check_or_reserve(conn, user_id, key, body_hash_2)
        assert tag3 == "mismatch"
        assert verdict3 is None

        # The persisted row carries status='success' (column default
        # after the legacy write_idempotency path completes).
        row = await conn.fetchrow(
            "SELECT status FROM idempotency_keys WHERE user_id=$1 AND key=$2",
            user_id, key,
        )
        assert row is not None
        assert row["status"] == "success"
