"""Phase B Wave 0 spike G — race-free lazy customer create.

Proves Pitfall 5: two concurrent first-clicks for the SAME user must result
in EXACTLY ONE Stripe Customer create, not two. The defense is
``SELECT ... FOR UPDATE`` on the user row inside the same transaction:
the first request takes the row lock, creates the Customer, writes
``users.stripe_customer_id``, and commits. The second request blocks on
the row lock; when it wakes up it re-reads ``stripe_customer_id`` (now
populated) and skips the create.

The "Stripe Customer create" is replaced with a counter-incrementing
fake. The test asserts the counter went up by exactly 1, not 2.
Without the FOR UPDATE clause, both transactions would observe
``stripe_customer_id IS NULL`` at READ COMMITTED and both would call
the fake — that's the race we're defending against.

Real Postgres testcontainer (Golden Rule #1).

Run via::

    cd api_server && uv run --extra dev python tests/_spikes/spike_g_lazy_customer_create.py
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import asyncpg
from testcontainers.postgres import PostgresContainer


USER_ID = uuid4()
USER_EMAIL = "spike-g@example.test"


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
                email text NOT NULL,
                stripe_customer_id text
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO users (id, email, stripe_customer_id)
            VALUES ($1, $2, NULL)
            """,
            USER_ID, USER_EMAIL,
        )


class FakeStripe:
    """A counter-incrementing stand-in for ``client.customers.create``.

    Each invocation appends to ``calls`` so the test can assert exactly
    one call across the concurrent racers. The synthetic latency
    (``await asyncio.sleep``) widens the race window and makes the
    without-FOR-UPDATE failure deterministic.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, *, email: str) -> str:
        self.calls.append({"email": email})
        # Simulate Stripe HTTP latency. Without this, the testcontainer's
        # connection-establishment serialization hides the race.
        await asyncio.sleep(0.1)
        # Customer ID format mirrors Stripe ('cus_<random>').
        return f"cus_test_{len(self.calls):03d}"


async def lazy_create_with_lock(
    pool: asyncpg.Pool,
    *,
    user_id,
    fake: FakeStripe,
) -> str:
    """Wave-1 lazy customer create under SELECT ... FOR UPDATE.

    The transaction:
      1. SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE
      2. If stripe_customer_id is NULL → create + UPDATE
      3. Else → return the existing customer_id

    The FOR UPDATE clause is the load-bearing one — it serializes
    concurrent requests on the user row.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT email, stripe_customer_id FROM users "
                "WHERE id = $1 FOR UPDATE",
                user_id,
            )
            if row["stripe_customer_id"] is None:
                cid = await fake.create(email=row["email"])
                await conn.execute(
                    "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
                    cid, user_id,
                )
                return cid
            return row["stripe_customer_id"]


async def lazy_create_without_lock(
    pool: asyncpg.Pool,
    *,
    user_id,
    fake: FakeStripe,
) -> str:
    """Counter-example: same logic WITHOUT FOR UPDATE — races at READ COMMITTED.

    Used to demonstrate that the FOR UPDATE clause is load-bearing, not
    superfluous. Two concurrent invocations both observe stripe_customer_id
    IS NULL and both call ``fake.create``.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT email, stripe_customer_id FROM users "
                "WHERE id = $1",
                user_id,
            )
            if row["stripe_customer_id"] is None:
                cid = await fake.create(email=row["email"])
                await conn.execute(
                    "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
                    cid, user_id,
                )
                return cid
            return row["stripe_customer_id"]


async def _reset_user(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET stripe_customer_id = NULL WHERE id = $1",
            USER_ID,
        )


async def _run() -> int:
    print("Booting Postgres 17 testcontainer ...")
    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        # Pool size >= 2 so concurrent requests get distinct connections.
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4)
        try:
            await _create_schema(pool)

            # ---- (a) negative control: WITHOUT FOR UPDATE → races -----
            await _reset_user(pool)
            fake_no_lock = FakeStripe()
            results_no_lock = await asyncio.gather(
                lazy_create_without_lock(pool, user_id=USER_ID, fake=fake_no_lock),
                lazy_create_without_lock(pool, user_id=USER_ID, fake=fake_no_lock),
            )
            print(f"  (a) WITHOUT lock: fake.calls={len(fake_no_lock.calls)} "
                  f"results={results_no_lock}")
            # The counter-example MUST race (>=2 calls). If it doesn't,
            # this spike isn't testing what we think (e.g. asyncpg serialized
            # us behind the scenes) and Wave 1 is invalid.
            assert len(fake_no_lock.calls) >= 2, (
                f"counter-example didn't race: only {len(fake_no_lock.calls)} call(s). "
                "spike-g is invalid until the race is empirically reproduced."
            )

            # ---- (b) positive case: WITH FOR UPDATE → exactly one ------
            await _reset_user(pool)
            fake_locked = FakeStripe()
            results_locked = await asyncio.gather(
                lazy_create_with_lock(pool, user_id=USER_ID, fake=fake_locked),
                lazy_create_with_lock(pool, user_id=USER_ID, fake=fake_locked),
            )
            print(f"  (b) WITH lock:    fake.calls={len(fake_locked.calls)} "
                  f"results={results_locked}")
            assert len(fake_locked.calls) == 1, (
                f"FOR UPDATE failed to serialize: {len(fake_locked.calls)} fake "
                f"calls (expected 1)"
            )
            # Both racers must return the SAME customer id.
            assert results_locked[0] == results_locked[1], (
                f"racers returned different customer ids: {results_locked!r}"
            )

            # ---- (c) third call sees populated id, no fake call --------
            fake_locked_2 = FakeStripe()
            existing = await lazy_create_with_lock(
                pool, user_id=USER_ID, fake=fake_locked_2,
            )
            assert existing == results_locked[0]
            assert len(fake_locked_2.calls) == 0, (
                f"third call hit Stripe again ({len(fake_locked_2.calls)} calls)"
            )
            print(f"  (c) third call:   fake.calls=0 (already-populated path)")
        finally:
            await pool.close()
    print("PASS spike-g")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
