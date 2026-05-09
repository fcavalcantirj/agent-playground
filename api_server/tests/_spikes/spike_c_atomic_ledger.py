"""Phase B Wave 0 spike C — atomic ledger conservation under 8-way concurrency.

Proves the D-17 ledger-as-truth invariant: 8 concurrent debit transactions
each INSERTing a debit row + UPDATE-ing the balance from SUM, all inside
``async with conn.transaction()``, conserve sum(deltas) without race
artifacts (no double-decrement, no lost update, no skew between cache and
ledger).

The pattern under test mirrors Wave 1's ``services/ledger.py::debit_user``:

    INSERT credit_transactions (debit row)
    UPDATE credit_balances SET balance_cents = (SELECT SUM(amount_cents) ...)

both inside one transaction. Postgres's MVCC + the implicit row lock taken
by the UPDATE ensure the second concurrent transaction sees the first's
commit before computing its own SUM.

Real Postgres testcontainer (Golden Rule #1).

Run via::

    cd api_server && uv run --extra dev python tests/_spikes/spike_c_atomic_ledger.py
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import asyncpg
from testcontainers.postgres import PostgresContainer


CONCURRENT_DEBITS = 8
USER_ID = uuid4()
SEED_BALANCE_CENTS = 10_000


def _normalize_dsn(raw: str) -> str:
    return (
        raw
        .replace("postgresql+psycopg2://", "postgres://")
        .replace("postgresql://", "postgres://")
        .replace("+psycopg2", "")
    )


async def _create_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE users (
                id uuid PRIMARY KEY,
                tier text NOT NULL DEFAULT 'free'
            );
            CREATE TABLE credit_balances (
                user_id uuid PRIMARY KEY,
                balance_cents bigint NOT NULL DEFAULT 0,
                updated_at timestamptz NOT NULL DEFAULT NOW()
            );
            CREATE TABLE credit_transactions (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id uuid NOT NULL,
                kind text NOT NULL CHECK (kind IN ('topup','debit','refund','tier_change','admin_writeoff')),
                amount_cents bigint NOT NULL,
                reference_id text,
                reference_type text,
                created_at timestamptz NOT NULL DEFAULT NOW()
            );
            CREATE UNIQUE INDEX uq_credit_transactions_reference
                ON credit_transactions (reference_id, reference_type)
                WHERE reference_id IS NOT NULL;
            """
        )
        # Seed user + ledger-shaped topup so the SUM rebuild has truth to work
        # with. balance cache mirrors the seed.
        await conn.execute(
            "INSERT INTO users (id, tier) VALUES ($1, 'ultra')",
            USER_ID,
        )
        await conn.execute(
            """
            INSERT INTO credit_transactions
                (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1, 'topup', $2, 'spike-c-seed', 'stripe_session')
            """,
            USER_ID, SEED_BALANCE_CENTS,
        )
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, $2)",
            USER_ID, SEED_BALANCE_CENTS,
        )


async def _atomic_debit(pool: asyncpg.Pool, *, idx: int, amount_cents: int) -> None:
    """One ledger debit transaction.

    DISCOVERY (Wave 0 spike-c): the naive

        INSERT debit row;
        UPDATE balance_cents = (SELECT SUM(...) FROM credit_transactions ...);

    pattern at READ COMMITTED (Postgres default) does NOT serialize. Each
    transaction's INSERT is visible to siblings only AFTER commit; the SUM
    subquery in each transaction's UPDATE evaluates against its own
    snapshot and misses concurrent inserts → lost cache updates.

    Wave-1-correct pattern: take an explicit row lock on credit_balances
    *first* (``SELECT ... FOR UPDATE``). All concurrent debit transactions
    serialize on that row lock; by the time each transaction reads SUM,
    every prior transaction has committed (their lock release is what
    woke us up). Mirrors MSV ``poken_service.go:180`` row-lock-then-read
    discipline.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialization point — row lock on the cache row.
            # This is the load-bearing call: without it, the SUM in the
            # UPDATE below races. See spike-c discovery note above.
            await conn.execute(
                "SELECT 1 FROM credit_balances WHERE user_id = $1 FOR UPDATE",
                USER_ID,
            )
            await conn.execute(
                """
                INSERT INTO credit_transactions
                    (user_id, kind, amount_cents, reference_id, reference_type)
                VALUES ($1, 'debit', $2, $3, 'usage_log')
                """,
                USER_ID, -amount_cents, f"spike-c-debit-{idx}",
            )
            await conn.execute(
                """
                UPDATE credit_balances
                   SET balance_cents = (SELECT COALESCE(SUM(amount_cents), 0)
                                        FROM credit_transactions
                                        WHERE user_id = $1),
                       updated_at = NOW()
                 WHERE user_id = $1
                """,
                USER_ID,
            )


async def _run() -> int:
    print("Booting Postgres 17 testcontainer ...")
    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        # Use a pool size >= concurrency so each task can acquire a separate
        # connection (otherwise the pool serializes us and we don't actually
        # exercise the race).
        pool = await asyncpg.create_pool(
            dsn,
            min_size=CONCURRENT_DEBITS,
            max_size=CONCURRENT_DEBITS + 2,
        )
        try:
            await _create_schema(pool)
            print(f"  seeded balance: {SEED_BALANCE_CENTS} cents")

            # Each task debits a different amount so we can detect lost
            # updates: total expected debit = 100+200+...+800 = 3600.
            deltas = [100 * (i + 1) for i in range(CONCURRENT_DEBITS)]
            expected_total_debit = sum(deltas)
            print(f"  spawning {CONCURRENT_DEBITS} concurrent debits "
                  f"({deltas}) totaling {expected_total_debit}")

            await asyncio.gather(*[
                _atomic_debit(pool, idx=i, amount_cents=deltas[i])
                for i in range(CONCURRENT_DEBITS)
            ])

            # ---- assertions --------------------------------------------
            async with pool.acquire() as conn:
                cache_bal = await conn.fetchval(
                    "SELECT balance_cents FROM credit_balances "
                    "WHERE user_id = $1",
                    USER_ID,
                )
                ledger_sum = await conn.fetchval(
                    "SELECT SUM(amount_cents) FROM credit_transactions "
                    "WHERE user_id = $1",
                    USER_ID,
                )
                debit_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM credit_transactions "
                    "WHERE user_id = $1 AND kind = 'debit'",
                    USER_ID,
                )

            expected_balance = SEED_BALANCE_CENTS - expected_total_debit
            print(f"  cache balance:  {cache_bal}")
            print(f"  ledger sum:     {ledger_sum}")
            print(f"  debit rows:     {debit_count}")
            print(f"  expected:       {expected_balance}")

            assert debit_count == CONCURRENT_DEBITS, (
                f"expected {CONCURRENT_DEBITS} debit rows, got {debit_count}"
            )
            assert ledger_sum == expected_balance, (
                f"ledger SUM {ledger_sum} != expected {expected_balance}"
            )
            assert cache_bal == expected_balance, (
                f"cache balance {cache_bal} != expected {expected_balance} — "
                "lost-update detected (concurrent debit race)"
            )
            assert cache_bal == ledger_sum, (
                f"cache/ledger drift: cache={cache_bal} ledger_sum={ledger_sum}"
            )
        finally:
            await pool.close()
    print("PASS spike-c")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
