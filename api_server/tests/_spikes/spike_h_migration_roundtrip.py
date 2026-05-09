"""Phase B Wave 0 spike H — migration 014 round-trip (upgrade/downgrade/upgrade).

Proves the draft migration in ``tests/_spikes/draft_014_migration.py`` is
idempotent and reversible BEFORE Wave 1 commits it to
``alembic/versions/014_credit_balances_and_ledger.py``.

Strategy: temporarily copy the draft into ``alembic/versions/`` for the
duration of the test, run alembic upgrade head + downgrade -1 + upgrade
head against a Postgres testcontainer, assert schema shapes at each step,
then ALWAYS remove the temp file in a finally block. The mainline
``alembic/versions/`` directory is left untouched.

Real Postgres testcontainer (Golden Rule #1).

Run via::

    cd api_server && uv run --extra dev python tests/_spikes/spike_h_migration_roundtrip.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import asyncpg
from testcontainers.postgres import PostgresContainer


API_SERVER_DIR = Path(__file__).resolve().parents[2]  # api_server/
ALEMBIC_VERSIONS_DIR = API_SERVER_DIR / "alembic" / "versions"
DRAFT_SOURCE = Path(__file__).parent / "draft_014_migration.py"
DRAFT_TARGET = ALEMBIC_VERSIONS_DIR / "014_phase_b_ledger_and_tier.py"

REVISION_ID = "014_phase_b_ledger_and_tier"
PRIOR_REVISION_ID = "013_phase29_proxy_columns"


def _normalize_dsn(raw: str) -> str:
    return (
        raw
        .replace("postgresql+psycopg2://", "postgres://")
        .replace("postgresql://", "postgres://")
        .replace("+psycopg2", "")
    )


def _alembic(container: PostgresContainer, *args: str) -> None:
    raw = container.get_connection_url()
    # alembic env.py accepts postgres://, postgresql://, or postgresql+asyncpg://.
    dsn = _normalize_dsn(raw)
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


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    raw = container.get_connection_url()
    dsn = _normalize_dsn(raw)
    return await asyncpg.connect(dsn)


async def _confirm_cost_weights_pre_migration(container: PostgresContainer) -> int:
    """Migration 010 seeds 6 baseline rows at ap_multiplier=1.0.

    Return the count so the data-migration assertion can verify the same
    count flipped to 1.15.
    """
    conn = await _connect(container)
    try:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.0"
        )
        if n < 1:
            raise RuntimeError(
                f"cost_weights has {n} rows at ap_multiplier=1.0 before "
                "migration 014 — expected migration 010 to have seeded 6"
            )
        return n
    finally:
        await conn.close()


async def _assert_post_upgrade(container: PostgresContainer) -> None:
    """Assert every schema shape Wave 1 promises after upgrade head."""
    conn = await _connect(container)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, f"head {head!r} != {REVISION_ID!r}"

        # users.tier
        col = await conn.fetchrow(
            "SELECT data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users' "
            "  AND column_name='tier'"
        )
        assert col is not None, "users.tier missing"
        assert col["data_type"] == "text", col["data_type"]
        assert col["is_nullable"] == "NO"
        assert col["column_default"] is not None and "free" in col["column_default"]

        # users.tier CHECK constraint (Postgres 12+ — pg_constraint.consrc removed,
        # use pg_get_constraintdef on the OID instead).
        ck_def = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_users_tier'"
        )
        assert ck_def is not None, "ck_users_tier missing"
        assert "free" in ck_def.lower() and "pro" in ck_def.lower() \
            and "ultra" in ck_def.lower(), f"ck_users_tier wrong: {ck_def!r}"

        # users.stripe_customer_id
        col = await conn.fetchrow(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users' "
            "  AND column_name='stripe_customer_id'"
        )
        assert col is not None, "users.stripe_customer_id missing"
        assert col["data_type"] == "text"
        assert col["is_nullable"] == "YES"

        # users.refund_writeoff_cents
        col = await conn.fetchrow(
            "SELECT data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users' "
            "  AND column_name='refund_writeoff_cents'"
        )
        assert col is not None, "users.refund_writeoff_cents missing"
        assert col["data_type"] == "bigint"
        assert col["is_nullable"] == "NO"
        assert col["column_default"] is not None and "0" in col["column_default"]

        # credit_balances table + PK + FK
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='credit_balances'"
        )
        assert tbl == 1, "credit_balances table missing"

        # credit_transactions table + UNIQUE partial index + check
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='credit_transactions'"
        )
        assert tbl == 1, "credit_transactions table missing"
        idx_def = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname='public' "
            "  AND indexname='uq_credit_transactions_reference'"
        )
        assert idx_def is not None, "uq_credit_transactions_reference missing"
        assert "WHERE" in idx_def.upper(), f"index not partial: {idx_def!r}"
        assert "reference_id" in idx_def.lower()
        # check constraint allows our 5 kinds
        ck = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_credit_transactions_kind'"
        )
        assert ck is not None, "ck_credit_transactions_kind missing"
        for kind in ("topup", "debit", "refund", "tier_change", "admin_writeoff"):
            assert kind in ck, (
                f"ck_credit_transactions_kind missing {kind!r}: {ck!r}"
            )

        # ix_credit_transactions_user_created
        idx = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname='public' "
            "  AND indexname='ix_credit_transactions_user_created'"
        )
        assert idx is not None, "ix_credit_transactions_user_created missing"

        # stripe_webhook_events + UNIQUE
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='stripe_webhook_events'"
        )
        assert tbl == 1, "stripe_webhook_events table missing"
        uq = await conn.fetchval(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_stripe_webhook_events_event_id'"
        )
        assert uq == 1, "uq_stripe_webhook_events_event_id missing"

        # cost_weights data migration: 1.0 → 1.15
        # Migration 010 seeded 6 rows at ap_multiplier=1.0; after upgrade
        # all 6 should be at 1.15 and 0 at 1.0.
        n_115 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15"
        )
        n_10 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.0"
        )
        assert n_115 >= 6, (
            f"cost_weights data-migration didn't fire: only {n_115} rows at 1.15 "
            f"(expected >= 6 from migration 010 seed)"
        )
        assert n_10 == 0, (
            f"cost_weights data-migration left {n_10} rows at 1.0 (expected 0)"
        )
    finally:
        await conn.close()


async def _assert_post_downgrade(container: PostgresContainer) -> None:
    conn = await _connect(container)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == PRIOR_REVISION_ID, (
            f"post-downgrade head {head!r} != {PRIOR_REVISION_ID!r}"
        )
        # All Phase-B columns + tables must be GONE.
        for col in ("tier", "stripe_customer_id", "refund_writeoff_cents"):
            still = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users' "
                "  AND column_name=$1",
                col,
            )
            assert still is None, f"users.{col} still present after downgrade"
        for table in ("credit_balances", "credit_transactions",
                      "stripe_webhook_events"):
            still = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=$1",
                table,
            )
            assert still is None, f"{table} table still present after downgrade"
        # ap_multiplier reverted: all 6 rows back to 1.0, none at 1.15.
        n_10 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.0"
        )
        n_115 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15"
        )
        assert n_10 >= 6, (
            f"cost_weights downgrade didn't reverse: only {n_10} rows at 1.0 "
            f"(expected >= 6)"
        )
        assert n_115 == 0, (
            f"cost_weights downgrade left {n_115} rows at 1.15 (expected 0)"
        )
    finally:
        await conn.close()


async def _run() -> int:
    print(f"Copying draft migration into {ALEMBIC_VERSIONS_DIR}/ ...")
    if DRAFT_TARGET.exists():
        raise RuntimeError(
            f"{DRAFT_TARGET} already exists — Wave 1 may have copied the "
            "draft already. Remove it before re-running spike-h."
        )
    shutil.copyfile(DRAFT_SOURCE, DRAFT_TARGET)
    try:
        with PostgresContainer("postgres:17-alpine") as pg:
            print("  upgrade head (013 → 014) ...")
            # Migration 010 seeds 6 cost_weights rows at ap_multiplier=1.0
            # before 013 runs; 013 leaves them alone, 014 flips them to 1.15.
            _alembic(pg, "upgrade", PRIOR_REVISION_ID)
            n_baseline = await _confirm_cost_weights_pre_migration(pg)
            print(f"    cost_weights baseline (ap_multiplier=1.0): {n_baseline} rows")
            _alembic(pg, "upgrade", "head")
            await _assert_post_upgrade(pg)
            print("  ✓ post-upgrade schema assertions PASS")

            print("  downgrade -1 (014 → 013) ...")
            _alembic(pg, "downgrade", "-1")
            await _assert_post_downgrade(pg)
            print("  ✓ post-downgrade schema assertions PASS")

            print("  re-upgrade head (013 → 014) ...")
            _alembic(pg, "upgrade", "head")
            await _assert_post_upgrade(pg)
            print("  ✓ re-upgrade idempotent — schema PASS")
    finally:
        # ALWAYS remove the temp file so alembic/versions/ stays clean.
        if DRAFT_TARGET.exists():
            DRAFT_TARGET.unlink()
            print(f"  cleanup: removed {DRAFT_TARGET}")
        # Also clear cached __pycache__ entry for the deleted module.
        cache = ALEMBIC_VERSIONS_DIR / "__pycache__"
        if cache.exists():
            for pyc in cache.glob(f"{DRAFT_TARGET.stem}*.pyc"):
                pyc.unlink()
    print("PASS spike-h")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
