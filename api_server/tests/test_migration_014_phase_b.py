"""Phase B Plan B-stripe-02 — schema-DDL assertions for migration ``014_phase_b_ledger_and_tier``.

Mirrors :mod:`tests.test_migration_013_proxy_columns` style: a module-scoped Postgres
17 container (testcontainers), ``alembic upgrade head`` once, then per-test
asyncpg connections that assert column / table / constraint / index shape +
the cost_weights data migration (1.0 → 1.15) +
the round-trip (downgrade -1 → upgrade head) preserves the additive surface.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

Asserts (per Plan B-stripe-02 must_haves.truths):

  * ``users.tier`` (text, NOT NULL, default ``'free'``) added with
    ``ck_users_tier`` covering ('free','pro','ultra').
  * ``users.stripe_customer_id`` (text, nullable) added.
  * ``users.refund_writeoff_cents`` (bigint, NOT NULL, default 0) added.
  * ``credit_balances`` (PK on user_id, FK to users.id ON DELETE CASCADE).
  * ``credit_transactions`` with ``ck_credit_transactions_kind`` covering all
    5 kinds + UNIQUE partial index ``uq_credit_transactions_reference``
    (reference_id, reference_type) WHERE reference_id IS NOT NULL +
    ``ix_credit_transactions_user_created`` btree.
  * ``stripe_webhook_events`` with UNIQUE constraint on stripe_event_id.
  * ``cost_weights.ap_multiplier`` rows previously at 1.0 are now 1.15
    (D-08 data migration).
  * Round-trip (upgrade head → downgrade -1 → upgrade head) leaves the
    additive surface identical.

Settings extension test (no DB): ``Settings`` exposes 8 new ``stripe_*``
fields backed by ``AP_STRIPE_*`` env aliases, with placeholder fallback
in dev (env=='dev') and fail-loud in prod (env=='prod').

NOTE on revision id: the migration is ``014_phase_b_ledger_and_tier`` (27 chars,
fits the ``alembic_version.version_num`` ``varchar(32)`` constraint per spike H
discovery). The longer ``014_phase_b_credit_ledger_and_tier`` (33 chars) would
truncate; do NOT use it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.api_integration

API_SERVER_DIR = Path(__file__).resolve().parent.parent

REVISION_ID = "014_phase_b_ledger_and_tier"
PRIOR_REVISION_ID = "013_phase29_proxy_columns"


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
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        yield container


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    dsn = _normalize(container.get_connection_url()).replace(
        "postgresql://", "postgres://"
    )
    return await asyncpg.connect(dsn)


@pytest.fixture(scope="module")
def migrated(pg):
    """Apply ``alembic upgrade head`` once for the module — migration 010
    seeds 6 cost_weights rows at ap_multiplier=1.0; 014's data migration
    flips them to 1.15. The flip assertion is meaningful because the
    baseline already exists.
    """
    _alembic(pg, "upgrade", "head")
    return pg


@pytest.mark.asyncio
async def test_upgrade_creates_users_tier_column_with_default_and_check(
    migrated,
):
    """``users.tier`` is text NOT NULL DEFAULT 'free'; ``ck_users_tier``
    constrains it to ('free','pro','ultra')."""
    conn = await _connect(migrated)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, f"head {head!r} != {REVISION_ID!r}"

        col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='users'
              AND column_name='tier'
            """
        )
        assert col is not None, "users.tier missing"
        assert col["data_type"] == "text"
        assert col["is_nullable"] == "NO"
        assert col["column_default"] is not None
        assert "free" in col["column_default"], col["column_default"]

        # ck_users_tier definition (Postgres 12+ uses pg_get_constraintdef).
        ck = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_users_tier'"
        )
        assert ck is not None, "ck_users_tier missing"
        for label in ("free", "pro", "ultra"):
            assert label in ck, f"ck_users_tier missing {label!r}: {ck!r}"

        # Backfill: any pre-existing user row was set to 'free' by the
        # NOT NULL DEFAULT 'free' clause. Insert one and read it back.
        uid = await conn.fetchval(
            "INSERT INTO users (id, display_name) "
            "VALUES (gen_random_uuid(), 'mig014-tier-default') RETURNING id"
        )
        tier = await conn.fetchval(
            "SELECT tier FROM users WHERE id = $1", uid,
        )
        assert tier == "free"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upgrade_users_extra_columns(migrated):
    """``users.stripe_customer_id`` (text, nullable) +
    ``users.refund_writeoff_cents`` (bigint, NOT NULL, default 0)."""
    conn = await _connect(migrated)
    try:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='users'
              AND column_name IN ('stripe_customer_id','refund_writeoff_cents')
            ORDER BY column_name
            """
        )
        by_name = {r["column_name"]: r for r in rows}

        assert "stripe_customer_id" in by_name
        assert by_name["stripe_customer_id"]["data_type"] == "text"
        assert by_name["stripe_customer_id"]["is_nullable"] == "YES"

        assert "refund_writeoff_cents" in by_name
        assert by_name["refund_writeoff_cents"]["data_type"] == "bigint"
        assert by_name["refund_writeoff_cents"]["is_nullable"] == "NO"
        assert "0" in (by_name["refund_writeoff_cents"]["column_default"] or "")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upgrade_creates_credit_balances_with_pk_and_fk_cascade(
    migrated,
):
    """``credit_balances`` has user_id PK + FK ON DELETE CASCADE +
    balance_cents bigint NOT NULL DEFAULT 0."""
    conn = await _connect(migrated)
    try:
        # Table exists.
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='credit_balances'"
        )
        assert tbl == 1

        # PK on user_id.
        pk = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE t.relname='credit_balances' AND c.contype='p'
            """
        )
        assert pk is not None
        assert "user_id" in pk

        # FK to users.id with ON DELETE CASCADE.
        fk = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE t.relname='credit_balances' AND c.contype='f'
            """
        )
        assert fk is not None
        assert "REFERENCES users" in fk
        assert "CASCADE" in fk

        # Cascade behavior: delete user → balance row vanishes.
        uid = await conn.fetchval(
            "INSERT INTO users (id, display_name) "
            "VALUES (gen_random_uuid(), 'mig014-cb-cascade') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, 100)",
            uid,
        )
        await conn.execute("DELETE FROM users WHERE id = $1", uid)
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_balances WHERE user_id = $1", uid,
        )
        assert cnt == 0, "ON DELETE CASCADE did not cascade"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upgrade_creates_credit_transactions_with_kind_check_and_unique_index(
    migrated,
):
    """``credit_transactions`` has 5-kind CHECK + partial UNIQUE on
    (reference_id, reference_type) WHERE reference_id IS NOT NULL +
    ``ix_credit_transactions_user_created``."""
    conn = await _connect(migrated)
    try:
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='credit_transactions'"
        )
        assert tbl == 1

        ck = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_credit_transactions_kind'"
        )
        assert ck is not None
        for kind in ("topup", "debit", "refund", "tier_change", "admin_writeoff"):
            assert kind in ck, f"ck_credit_transactions_kind missing {kind!r}"

        idx = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname='public' "
            "  AND indexname='uq_credit_transactions_reference'"
        )
        assert idx is not None, "uq_credit_transactions_reference missing"
        assert "UNIQUE" in idx.upper()
        assert "WHERE" in idx.upper(), f"index not partial: {idx!r}"
        assert "reference_id" in idx.lower()

        idx2 = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname='public' "
            "  AND indexname='ix_credit_transactions_user_created'"
        )
        assert idx2 is not None, "ix_credit_transactions_user_created missing"
        assert "user_id" in idx2.lower()
        assert "created_at" in idx2.lower()

        # CHECK constraint behavior — bogus kind is rejected.
        uid = await conn.fetchval(
            "INSERT INTO users (id, display_name) "
            "VALUES (gen_random_uuid(), 'mig014-ck-kind') RETURNING id"
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO credit_transactions "
                "  (user_id, kind, amount_cents) VALUES ($1, 'bogus', 100)",
                uid,
            )

        # UNIQUE partial index behavior — same (reference_id, reference_type)
        # raises on second insert; NULL reference_id is exempt.
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents, reference_id, reference_type) "
            "  VALUES ($1, 'debit', -100, 'usage_log_42', 'usage_log')",
            uid,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO credit_transactions "
                "  (user_id, kind, amount_cents, reference_id, reference_type) "
                "  VALUES ($1, 'debit', -100, 'usage_log_42', 'usage_log')",
                uid,
            )
        # NULL reference_id is exempt — multiple NULLs are allowed.
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents) VALUES ($1, 'topup', 500)",
            uid,
        )
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents) VALUES ($1, 'topup', 500)",
            uid,
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upgrade_creates_stripe_webhook_events_with_unique_event_id(
    migrated,
):
    """``stripe_webhook_events.stripe_event_id`` UNIQUE for idempotency."""
    conn = await _connect(migrated)
    try:
        tbl = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='stripe_webhook_events'"
        )
        assert tbl == 1

        uq = await conn.fetchval(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_stripe_webhook_events_event_id'"
        )
        assert uq == 1, "uq_stripe_webhook_events_event_id missing"

        # Behavior: second insert of same stripe_event_id raises.
        await conn.execute(
            "INSERT INTO stripe_webhook_events "
            "  (stripe_event_id, event_type, payload) "
            "  VALUES ('evt_test_dup', 'checkout.session.completed', '{}')"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO stripe_webhook_events "
                "  (stripe_event_id, event_type, payload) "
                "  VALUES ('evt_test_dup', 'checkout.session.completed', '{}')"
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upgrade_bumps_ap_multiplier_to_1_15_for_existing_rows(
    migrated,
):
    """D-08 data migration: every cost_weights row that was at 1.0 is now 1.15.

    Migration 010 seeds 6 baseline rows at ap_multiplier=1.0; after 014 they
    must all be at 1.15.
    """
    conn = await _connect(migrated)
    try:
        n_115 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15"
        )
        n_10 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.0"
        )
        # Baseline from migration 010 is 6 rows; after 014's data migration
        # all 6 must be at 1.15 and 0 at 1.0.
        assert n_115 >= 6, (
            f"D-08 data migration didn't fire — only {n_115} rows at 1.15"
        )
        assert n_10 == 0, (
            f"D-08 data migration left {n_10} rows at 1.0 (expected 0)"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_round_trip_downgrade_and_re_upgrade(pg):
    """``upgrade head → downgrade -1 → upgrade head`` preserves the
    additive surface (columns + tables + indexes + constraints).

    The cost_weights data migration is reversible by symmetry: 1.15 → 1.0
    on downgrade restores the baseline; 1.0 → 1.15 on re-upgrade flips
    them back.
    """
    # Ensure we're at head (the module fixture has run).
    _alembic(pg, "upgrade", "head")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID

        # Pre-downgrade snapshot — additive surface only.
        before_cols = await conn.fetch(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND ((table_name='users'
                    AND column_name IN ('tier','stripe_customer_id',
                                        'refund_writeoff_cents'))
                   OR table_name IN ('credit_balances','credit_transactions',
                                     'stripe_webhook_events'))
            ORDER BY table_name, column_name
            """
        )
        before_set = {(r["table_name"], r["column_name"]) for r in before_cols}
        assert before_set, "expected non-empty additive surface pre-downgrade"
    finally:
        await conn.close()

    # downgrade -1 → 013
    _alembic(pg, "downgrade", "-1")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == PRIOR_REVISION_ID, (
            f"post-downgrade head {head!r} != {PRIOR_REVISION_ID!r}"
        )
        # The 3 user columns must be GONE.
        for col in ("tier", "stripe_customer_id", "refund_writeoff_cents"):
            still = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='users' AND column_name=$1",
                col,
            )
            assert still is None, f"users.{col} still present after downgrade"
        # The 3 new tables must be GONE.
        for t in ("credit_balances", "credit_transactions",
                  "stripe_webhook_events"):
            still = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name=$1",
                t,
            )
            assert still is None, f"{t} still present after downgrade"
        # cost_weights reverted to 1.0 baseline.
        n_10 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.0"
        )
        n_115 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15"
        )
        assert n_10 >= 6, (
            f"cost_weights downgrade didn't reverse: {n_10} rows at 1.0"
        )
        assert n_115 == 0, (
            f"cost_weights downgrade left {n_115} rows at 1.15"
        )
    finally:
        await conn.close()

    # Re-upgrade → head; surface restored, ap_multiplier flipped again.
    _alembic(pg, "upgrade", "head")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID

        after_cols = await conn.fetch(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND ((table_name='users'
                    AND column_name IN ('tier','stripe_customer_id',
                                        'refund_writeoff_cents'))
                   OR table_name IN ('credit_balances','credit_transactions',
                                     'stripe_webhook_events'))
            ORDER BY table_name, column_name
            """
        )
        after_set = {(r["table_name"], r["column_name"]) for r in after_cols}
        # The set must match the pre-downgrade snapshot byte-identically.
        missing = before_set - after_set
        assert not missing, f"round-trip lost columns: {missing!r}"
        extra = after_set - before_set
        assert not extra, f"round-trip introduced unexpected columns: {extra!r}"

        n_115 = await conn.fetchval(
            "SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15"
        )
        assert n_115 >= 6, (
            f"re-upgrade ap_multiplier flip lost: {n_115} rows at 1.15"
        )
    finally:
        await conn.close()


# ----------------------------------------------------------------------
# Settings extension test (no DB) — Stripe field exposure + dev/prod modes
# ----------------------------------------------------------------------


def test_settings_exposes_8_stripe_fields_with_placeholders_in_dev(monkeypatch):
    """In ``AP_ENV=dev``, missing AP_STRIPE_* env vars resolve to deterministic
    placeholders + a single warning per field. Mirrors the ``oauth_X missing
    in dev`` discipline already used for OAuth credentials.
    """
    # Strip every AP_STRIPE_* env var to force the dev placeholder branch.
    for key in list(os.environ.keys()):
        if key.startswith("AP_STRIPE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    # Reload Settings — get_settings() is a fresh snapshot.
    from api_server.config import Settings, get_settings

    s = get_settings()
    assert isinstance(s, Settings)

    # The 8 fields exist + carry non-empty placeholder values.
    assert s.stripe_api_key
    assert "PLACEHOLDER" in s.stripe_api_key.upper()
    assert s.stripe_webhook_secret
    assert "PLACEHOLDER" in s.stripe_webhook_secret.upper()
    assert s.stripe_price_id_pro_monthly
    for pack_field in (
        "stripe_price_id_pack_5",
        "stripe_price_id_pack_10",
        "stripe_price_id_pack_25",
        "stripe_price_id_pack_50",
        "stripe_price_id_pack_100",
    ):
        v = getattr(s, pack_field)
        assert v, f"{pack_field} resolved empty in dev — placeholder missing"
        assert "PLACEHOLDER" in v.upper(), (
            f"{pack_field} = {v!r} — expected PLACEHOLDER substring in dev"
        )


def test_settings_fail_loud_in_prod_when_stripe_keys_missing(monkeypatch):
    """In ``AP_ENV=prod``, ``validate_stripe_config(settings)`` raises
    ``RuntimeError`` listing every missing AP_STRIPE_* env var.

    Settings instantiation itself stays optional (mirrors OAuth's
    ``_resolve_or_fail`` deferred-fail-loud discipline so unrelated tests
    that flip ``AP_ENV=prod`` for non-Stripe surfaces don't have to mint
    8 placeholders); the prod gate fires when a Phase B service
    (StripeClient lifespan, billing_packs) calls the validator at
    construction time.
    """
    for key in list(os.environ.keys()):
        if key.startswith("AP_STRIPE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    from api_server.config import get_settings, validate_stripe_config

    # Settings constructs cleanly in prod with empty Stripe values — the
    # fail-loud is deferred to validate_stripe_config() (mirrors OAuth).
    s = get_settings()
    assert s.stripe_api_key == ""

    with pytest.raises(RuntimeError) as exc:
        validate_stripe_config(s)
    msg = str(exc.value)
    assert "AP_STRIPE" in msg.upper()
    # The error lists every missing key.
    for alias in (
        "AP_STRIPE_API_KEY",
        "AP_STRIPE_WEBHOOK_SECRET",
        "AP_STRIPE_PRICE_ID_PRO_MONTHLY",
        "AP_STRIPE_PRICE_ID_PACK_5",
        "AP_STRIPE_PRICE_ID_PACK_10",
        "AP_STRIPE_PRICE_ID_PACK_25",
        "AP_STRIPE_PRICE_ID_PACK_50",
        "AP_STRIPE_PRICE_ID_PACK_100",
    ):
        assert alias in msg, f"{alias} missing from RuntimeError: {msg!r}"


def test_validate_stripe_config_noop_in_dev(monkeypatch):
    """In ``AP_ENV=dev``, ``validate_stripe_config`` is a no-op even when
    no AP_STRIPE_* env vars are set — the model validator's placeholder
    substitution kicks in and there's nothing to fail-loud about.
    """
    for key in list(os.environ.keys()):
        if key.startswith("AP_STRIPE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    from api_server.config import get_settings, validate_stripe_config

    s = get_settings()
    # Returns silently — no RuntimeError.
    validate_stripe_config(s)
    # Placeholder substitution fired.
    assert "PLACEHOLDER" in s.stripe_api_key.upper()
