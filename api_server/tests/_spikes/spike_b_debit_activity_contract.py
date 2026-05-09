"""Phase B Wave 0 spike B — debit_balance activity contract.

Proves the class-bound activity shape Wave 1 will deliver:

1. ``@activity.defn(name="debit_balance")`` decorator on a bound method
   preserves Phase 28 D-22's wire-name + signature contract.
2. Activity returns a Decimal-as-string (the workflow's JSON serializer
   cannot round-trip ``Decimal``; stringification is the locked contract).
3. ``UNIQUE(reference_id, reference_type)`` raises ``asyncpg.UniqueViolationError``
   on retry; the activity catches and returns the originally-debited amount.

Real Postgres testcontainer (Golden Rule #1 — no mocks for core substrate).
Schema is created inline via ``conn.execute("CREATE TABLE ...")`` — this is
NOT alembic; that's Wave 1 work. We're proving the activity's behaviour, not
the migration shape.

Run via::

    cd api_server && uv run python tests/_spikes/spike_b_debit_activity_contract.py
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from typing import Any
from uuid import uuid4

import asyncpg
from temporalio import activity
from temporalio.testing import ActivityEnvironment
from testcontainers.postgres import PostgresContainer


REFERENCE_ID = "usage-fixture-1"
REFERENCE_TYPE = "usage_log"
USER_ID = uuid4()
DEBIT_CENTS = 100  # one dollar


def _normalize_dsn(raw: str) -> str:
    """testcontainers emits ``postgresql+psycopg2://...``; asyncpg wants ``postgres://``."""
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
        # Seed via the ledger so the SUM-rebuild (D-17 ledger-as-truth) has
        # something to recompute against. A topup row of $10 establishes
        # both the balance cache (1000) and a corresponding ledger row.
        await conn.execute(
            """
            INSERT INTO credit_transactions
                (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1::uuid, 'topup', 1000, 'spike-b-seed-topup', 'stripe_session')
            """,
            USER_ID,
        )
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, 1000)",
            USER_ID,
        )


# ---- The activity under test (mirrors Wave 1 contract shape) -------------


class DebitBalanceActivities:
    """Class-bound holder for the debit-balance activity (Phase 28 D-22 +
    Wave 1 body shape from PATTERNS.md).

    The wire name ``"debit_balance"`` and the ``str`` return type are
    Phase 28-locked contract; the body is what Wave 1 fills in. Spike B
    exercises the contract on a stripped-down body that just inserts a
    ledger row + handles UniqueViolationError on retry.
    """

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="debit_balance")
    async def debit_balance(self, inp: dict[str, Any]) -> str:
        """Insert a ledger row; on UNIQUE retry return originally-debited str.

        ``inp`` shape mirrors what Wave 1 will receive:
            {"user_id": "<uuid-str>", "reference_id": "...", "amount_cents": int}
        """
        user_id = inp["user_id"]
        reference_id = inp["reference_id"]
        amount_cents = inp["amount_cents"]
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.execute(
                        """
                        INSERT INTO credit_transactions
                            (user_id, kind, amount_cents,
                             reference_id, reference_type)
                        VALUES ($1::uuid, 'debit', $2, $3, $4)
                        """,
                        user_id, -amount_cents, reference_id, REFERENCE_TYPE,
                    )
                except asyncpg.UniqueViolationError:
                    # Idempotent retry — return the previously-debited amount.
                    return str(Decimal(amount_cents) / Decimal(100))
                # Rebuild the cache from the ledger SUM (D-17 ledger-as-truth).
                await conn.execute(
                    """
                    UPDATE credit_balances
                       SET balance_cents = (SELECT COALESCE(SUM(amount_cents), 0)
                                            FROM credit_transactions
                                            WHERE user_id = $1::uuid),
                           updated_at = NOW()
                     WHERE user_id = $1::uuid
                    """,
                    user_id,
                )
        return str(Decimal(amount_cents) / Decimal(100))


# ---- Driver --------------------------------------------------------------


async def _run() -> int:
    print("Booting Postgres 17 testcontainer ...")
    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
        try:
            await _create_schema(pool)
            acts = DebitBalanceActivities(db_pool=pool)

            # ---- (a) wire-name decorator preserved ---------------------
            defn = activity._Definition.must_from_callable(acts.debit_balance)
            assert defn.name == "debit_balance", (
                f"expected activity wire name 'debit_balance', got {defn.name!r}"
            )
            print(f"  (a) decorator name == 'debit_balance' ({defn.name!r})")

            # ---- (b) first invocation debits ---------------------------
            inp = {
                "user_id": str(USER_ID),
                "reference_id": REFERENCE_ID,
                "amount_cents": DEBIT_CENTS,
            }
            env = ActivityEnvironment()
            first = await env.run(acts.debit_balance, inp)
            assert isinstance(first, str), f"expected str return, got {type(first)}"
            assert Decimal(first) == Decimal("1.00"), (
                f"expected '1.00', got {first!r}"
            )
            print(f"  (b) first call returned {first!r} (Decimal('{Decimal(first)}'))")

            # Verify ledger + balance: seed (1 topup +1000) + 1 debit (-100)
            # → balance 900.
            async with pool.acquire() as conn:
                debits = await conn.fetch(
                    "SELECT amount_cents FROM credit_transactions "
                    "WHERE user_id = $1::uuid AND kind = 'debit'",
                    str(USER_ID),
                )
                bal = await conn.fetchval(
                    "SELECT balance_cents FROM credit_balances WHERE user_id = $1::uuid",
                    str(USER_ID),
                )
            assert len(debits) == 1, f"expected 1 debit row, got {len(debits)}"
            assert debits[0]["amount_cents"] == -DEBIT_CENTS
            assert bal == 1000 - DEBIT_CENTS, (
                f"expected balance 900, got {bal}"
            )
            print(f"      ledger has 1 debit row (-{DEBIT_CENTS}); balance={bal}")

            # ---- (c) idempotent retry returns same string --------------
            second = await env.run(acts.debit_balance, inp)
            assert second == first, (
                f"retry returned different value: first={first!r} second={second!r}"
            )
            print(f"  (c) retry returned {second!r} (UniqueViolation caught)")

            # And the ledger / balance MUST NOT have changed.
            async with pool.acquire() as conn:
                debits2 = await conn.fetch(
                    "SELECT amount_cents FROM credit_transactions "
                    "WHERE user_id = $1::uuid AND kind = 'debit'",
                    str(USER_ID),
                )
                bal2 = await conn.fetchval(
                    "SELECT balance_cents FROM credit_balances WHERE user_id = $1::uuid",
                    str(USER_ID),
                )
            assert len(debits2) == 1, (
                f"retry inserted a duplicate debit row: {len(debits2)} rows"
            )
            assert bal2 == bal, (
                f"retry mutated balance: was {bal}, now {bal2}"
            )
            print(f"      no double-debit; debit_count=1; balance still {bal2}")

        finally:
            await pool.close()
    print("PASS spike-b")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
