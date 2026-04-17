"""asyncpg pool lifecycle + Postgres health probes.

Used by:

- ``main.create_app`` lifespan → ``create_pool`` at startup, ``close_pool`` at shutdown
- ``routes/health.py`` ``/readyz`` → ``probe_postgres`` every call

DSN normalization: Alembic's env.py accepts ``postgresql+asyncpg://``,
``postgresql://`` and ``postgres://``. asyncpg itself rejects the
``+asyncpg`` driver hint, so we strip it here. All other forms pass
through unchanged.
"""
from __future__ import annotations

import asyncio

import asyncpg


def _normalize_dsn(dsn: str) -> str:
    """Strip the SQLAlchemy-style ``+asyncpg`` driver hint if present.

    asyncpg itself rejects ``postgresql+asyncpg://`` but Alembic / SQLAlchemy
    emit exactly that shape. Callers may pass whichever form they have.
    """
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn[len("postgresql+asyncpg://"):]
    return dsn


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Create an asyncpg pool and verify connectivity with ``SELECT 1``.

    Pool sizing: ``min_size=2, max_size=10`` — enough headroom for ~10
    concurrent ``/v1/runs`` without thrashing. Command timeout 5s keeps a
    misbehaving Postgres from blocking the event loop indefinitely.
    """
    pool = await asyncpg.create_pool(
        _normalize_dsn(dsn),
        min_size=2,
        max_size=10,
        command_timeout=5.0,
    )
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return pool


async def close_pool(pool: asyncpg.Pool | None) -> None:
    """Close the pool if it exists; tolerate None for already-closed cases."""
    if pool is not None:
        await pool.close()


async def probe_postgres(pool: asyncpg.Pool | None) -> bool:
    """Return True iff ``SELECT 1`` round-trips within 2 seconds.

    Swallows every exception so ``/readyz`` reports ``postgres: False``
    instead of throwing 500. Defense against a temporarily unreachable DB.
    """
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await asyncio.wait_for(conn.execute("SELECT 1"), timeout=2.0)
        return True
    except Exception:
        return False
