"""Phase B Plan B-stripe-02 — services/ledger.py atomic-helpers test suite.

Mirrors Wave 0 spike-c shape: real Postgres 17 testcontainer + asyncpg pool
+ direct migration apply, then the ledger helpers exercised at unit and
8-way concurrency. Per CLAUDE.md Golden Rule #1: NO sqlite, NO in-memory
fakes; the ledger talks to a real PG instance because the conservation
proof is what makes D-17 ledger-as-truth load-bearing.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

Tests:

  * test_debit_user_inserts_negative_amount_and_rebuilds_balance
  * test_debit_user_idempotent_on_unique_violation_returns_original_amount
  * test_credit_user_inserts_positive_amount_and_rebuilds_balance
  * test_record_tier_change_inserts_zero_amount_audit_row
  * test_8_concurrent_debits_conserve_balance — spike-c equivalent

The ``debit_user`` / ``credit_user`` helpers are caller-owned-tx —
the test wraps each call in ``async with conn.transaction(): ...``.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.api_integration

API_SERVER_DIR = Path(__file__).resolve().parent.parent


def _normalize(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _alembic(container: PostgresContainer, *args: str) -> None:
    dsn = _normalize(container.get_connection_url())
    env = {**os.environ, "DATABASE_URL": dsn}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {args} exited {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        _alembic(container, "upgrade", "head")
        yield container


@pytest_asyncio.fixture
async def pool(pg):
    """Per-test asyncpg pool (min/max=8 so the concurrent-debit test
    actually runs concurrently — pool size below the concurrency level
    serializes us behind connection acquire and hides the race we want
    to exercise).
    """
    dsn = _normalize(pg.get_connection_url()).replace(
        "postgresql://", "postgres://"
    )
    p = await asyncpg.create_pool(dsn, min_size=8, max_size=12)
    try:
        yield p
    finally:
        await p.close()


@pytest_asyncio.fixture
async def user_id(pool) -> UUID:
    """Seed a user; return its UUID. Truncates ledger + balances before
    yielding so each test sees a clean slate (the module-scoped migration
    fixture builds the schema once; per-test isolation is via TRUNCATE).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE TABLE credit_transactions, credit_balances, "
            "users RESTART IDENTITY CASCADE"
        )
        uid = await conn.fetchval(
            "INSERT INTO users (id, display_name, tier) "
            "VALUES (gen_random_uuid(), 'ledger-test', 'ultra') "
            "RETURNING id"
        )
    return uid


# ---------------------------------------------------------------------
# debit_user
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debit_user_inserts_negative_amount_and_rebuilds_balance(
    pool, user_id,
):
    """debit_user inserts kind='debit', amount_cents = -abs(cost), and
    UPDATEs the balance cache from the SUM. Returns Decimal-USD.
    """
    from api_server.services.ledger import debit_user

    async with pool.acquire() as conn:
        # Seed a topup so the balance has truth to debit from.
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, 5000)",
            user_id,
        )
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents, reference_id, reference_type) "
            "  VALUES ($1, 'topup', 5000, 'seed', 'manual')",
            user_id,
        )

        async with conn.transaction():
            usd = await debit_user(
                conn,
                user_id=user_id,
                cost_cents=123,
                reference_id="usage_log_42",
                reference_type="usage_log",
            )

    assert usd == Decimal("1.23")
    async with pool.acquire() as conn:
        bal = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id=$1",
            user_id,
        )
        assert bal == 5000 - 123, f"balance cache drift: {bal}"
        sum_ledger = await conn.fetchval(
            "SELECT SUM(amount_cents) FROM credit_transactions "
            "WHERE user_id=$1",
            user_id,
        )
        assert sum_ledger == 5000 - 123
        # Debit row landed with negative amount and correct reference.
        row = await conn.fetchrow(
            "SELECT kind, amount_cents, reference_id, reference_type "
            "FROM credit_transactions WHERE reference_id='usage_log_42'"
        )
        assert row is not None
        assert row["kind"] == "debit"
        assert row["amount_cents"] == -123
        assert row["reference_type"] == "usage_log"


@pytest.mark.asyncio
async def test_debit_user_idempotent_on_unique_violation_returns_original_amount(
    pool, user_id,
):
    """Calling debit_user twice with the same (reference_id, reference_type)
    raises asyncpg.UniqueViolationError on the SECOND insert; the helper
    catches the violation and returns the originally-debited Decimal.

    The first call's transaction is committed; the ledger has exactly
    one debit row for that reference.
    """
    from api_server.services.ledger import debit_user

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, 5000)",
            user_id,
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            first = await debit_user(
                conn,
                user_id=user_id,
                cost_cents=200,
                reference_id="dup_ref",
                reference_type="usage_log",
            )
        assert first == Decimal("2.00")

    # Second call with same reference: the UNIQUE partial index raises
    # UniqueViolationError; the helper catches and returns the same Decimal
    # — must NOT propagate the exception.
    async with pool.acquire() as conn:
        async with conn.transaction():
            second = await debit_user(
                conn,
                user_id=user_id,
                cost_cents=200,
                reference_id="dup_ref",
                reference_type="usage_log",
            )
        assert second == Decimal("2.00")

    # Exactly one debit row exists.
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE reference_id='dup_ref' AND reference_type='usage_log'"
        )
        assert cnt == 1, f"idempotency broken — {cnt} debit rows for dup_ref"


# ---------------------------------------------------------------------
# credit_user
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credit_user_inserts_positive_amount_and_rebuilds_balance(
    pool, user_id,
):
    """credit_user with kind='topup' inserts a positive amount + rebuilds
    the balance cache. Returns the new balance_cents (int).
    """
    from api_server.services.ledger import credit_user

    async with pool.acquire() as conn:
        async with conn.transaction():
            new_balance = await credit_user(
                conn,
                user_id=user_id,
                kind="topup",
                amount_cents=2500,
                reference_id="cs_test_abc123",
                reference_type="stripe_session",
            )
    assert new_balance == 2500

    async with pool.acquire() as conn:
        cache = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id=$1",
            user_id,
        )
        assert cache == 2500
        row = await conn.fetchrow(
            "SELECT kind, amount_cents FROM credit_transactions "
            "WHERE reference_id='cs_test_abc123'"
        )
        assert row["kind"] == "topup"
        assert row["amount_cents"] == 2500


@pytest.mark.asyncio
async def test_credit_user_rejects_invalid_kind(pool, user_id):
    """credit_user raises ValueError for kinds outside topup/refund/admin_writeoff."""
    from api_server.services.ledger import credit_user

    async with pool.acquire() as conn:
        async with conn.transaction():
            with pytest.raises(ValueError):
                await credit_user(
                    conn,
                    user_id=user_id,
                    kind="debit",  # debit_user owns this kind
                    amount_cents=100,
                    reference_id="x",
                    reference_type="y",
                )


@pytest.mark.asyncio
async def test_credit_user_idempotent_on_unique_violation(pool, user_id):
    """credit_user catches UniqueViolationError on duplicate
    (reference_id, reference_type) and returns the existing balance cache
    without inserting a second row.
    """
    from api_server.services.ledger import credit_user

    async with pool.acquire() as conn:
        async with conn.transaction():
            await credit_user(
                conn, user_id=user_id, kind="topup",
                amount_cents=1000,
                reference_id="cs_dup", reference_type="stripe_session",
            )
        async with conn.transaction():
            second = await credit_user(
                conn, user_id=user_id, kind="topup",
                amount_cents=1000,
                reference_id="cs_dup", reference_type="stripe_session",
            )
    # Second call returned the existing balance (1000), NOT 2000.
    assert second == 1000
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE reference_id='cs_dup' AND reference_type='stripe_session'"
        )
        assert cnt == 1


# ---------------------------------------------------------------------
# record_tier_change
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_tier_change_inserts_zero_amount_audit_row(
    pool, user_id,
):
    """D-26: tier-change audit reuses ``credit_transactions`` with
    kind='tier_change', amount_cents=0, reference_id=stripe_event_id,
    reference_type='stripe_event'. Balance unchanged.
    """
    from api_server.services.ledger import record_tier_change

    async with pool.acquire() as conn:
        async with conn.transaction():
            await record_tier_change(
                conn,
                user_id=user_id,
                from_tier="free",
                to_tier="pro",
                stripe_event_id="evt_test_tier_001",
            )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT kind, amount_cents, reference_id, reference_type "
            "FROM credit_transactions WHERE reference_id='evt_test_tier_001'"
        )
        assert row is not None
        assert row["kind"] == "tier_change"
        assert row["amount_cents"] == 0
        assert row["reference_type"] == "stripe_event"


@pytest.mark.asyncio
async def test_record_tier_change_idempotent(pool, user_id):
    """Second call with same stripe_event_id is a no-op; only one audit row."""
    from api_server.services.ledger import record_tier_change

    async with pool.acquire() as conn:
        async with conn.transaction():
            await record_tier_change(
                conn, user_id=user_id, from_tier="free", to_tier="pro",
                stripe_event_id="evt_test_tier_dup",
            )
        async with conn.transaction():
            await record_tier_change(
                conn, user_id=user_id, from_tier="free", to_tier="pro",
                stripe_event_id="evt_test_tier_dup",
            )

    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE reference_id='evt_test_tier_dup'"
        )
        assert cnt == 1


# ---------------------------------------------------------------------
# 8-way concurrent debit conservation — mirrors Wave 0 spike-c
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_8_concurrent_debits_conserve_balance(pool, user_id):
    """Mirrors spike-c: 8 concurrent debit transactions each call
    debit_user; final balance == seed - sum(deltas), one debit row per call,
    cache and ledger SUM agree (no lost updates).
    """
    from api_server.services.ledger import debit_user

    SEED = 10_000
    deltas = [100 * (i + 1) for i in range(8)]  # [100..800]
    expected_total = sum(deltas)  # 3600

    async with pool.acquire() as conn:
        # Seed balance + topup ledger row.
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, $2)",
            user_id, SEED,
        )
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents, reference_id, reference_type) "
            "  VALUES ($1, 'topup', $2, 'seed', 'manual')",
            user_id, SEED,
        )

    async def _one_debit(idx: int, amount: int) -> None:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await debit_user(
                    conn,
                    user_id=user_id,
                    cost_cents=amount,
                    reference_id=f"concurrent_debit_{idx}",
                    reference_type="usage_log",
                )

    await asyncio.gather(*[
        _one_debit(i, deltas[i]) for i in range(8)
    ])

    async with pool.acquire() as conn:
        cache = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id=$1",
            user_id,
        )
        ledger_sum = await conn.fetchval(
            "SELECT SUM(amount_cents) FROM credit_transactions "
            "WHERE user_id=$1",
            user_id,
        )
        debit_count = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id=$1 AND kind='debit'",
            user_id,
        )

    expected_balance = SEED - expected_total
    assert debit_count == 8, f"expected 8 debit rows, got {debit_count}"
    assert ledger_sum == expected_balance, (
        f"ledger SUM {ledger_sum} != expected {expected_balance}"
    )
    assert cache == expected_balance, (
        f"cache balance {cache} != expected {expected_balance} — "
        "lost-update detected (concurrent debit race not defended)"
    )
    assert cache == ledger_sum, (
        f"cache/ledger drift: cache={cache} ledger_sum={ledger_sum}"
    )
