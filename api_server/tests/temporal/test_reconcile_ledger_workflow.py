"""Phase B Plan B-stripe-09 Task 2 — reconcile_ledger activity tests.

Real Postgres (testcontainers, alembic-migrated) + ``ActivityEnvironment``
per CLAUDE.md golden rule #1. The Sentry boundary is mocked out at the
``sentry_sdk.capture_message`` symbol because ``init_sentry`` is a no-op
when ``AP_SENTRY_DSN_API`` is unset (Phase 31 D-14).

Coverage matrix per PLAN.md ``<behavior>``:

  * test_reconcile_ledger_no_drift_no_sentry
  * test_reconcile_ledger_emits_sentry_capture_message_when_drift_detected
  * test_reconcile_ledger_repairs_cache_to_match_ledger_truth
"""
from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
import pytest
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.reconcile_ledger import (
    ReconcileLedgerActivities,
)


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(pool: asyncpg.Pool) -> UUID:
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, tier, display_name) "
            "VALUES ($1, 'ultra', $2)",
            user_id, f"reconcile-ledger-{uuid4().hex[:8]}",
        )
    return user_id


async def _seed_balance(
    pool: asyncpg.Pool, *, user_id: UUID, balance_cents: int,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, $2)",
            user_id, balance_cents,
        )


async def _seed_topup_ledger(
    pool: asyncpg.Pool, *, user_id: UUID, amount_cents: int,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO credit_transactions
              (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1, 'topup', $2, $3, 'stripe_checkout_session')
            """,
            user_id, amount_cents, f"cs-{uuid4().hex[:12]}",
        )


async def _read_balance(pool: asyncpg.Pool, user_id: UUID) -> int:
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    return int(v or 0)


# ---------------------------------------------------------------------------
# 1. No drift → drift_count=0 + no Sentry
# ---------------------------------------------------------------------------


async def test_reconcile_ledger_no_drift_no_sentry(
    db_pool: asyncpg.Pool, monkeypatch,
) -> None:
    """When cache_cents == ledger SUM, drift_count == 0 and no Sentry call."""
    user_id = await _seed_user(db_pool)
    await _seed_balance(db_pool, user_id=user_id, balance_cents=2500)
    await _seed_topup_ledger(db_pool, user_id=user_id, amount_cents=2500)

    captures: list[tuple] = []

    def _fake_capture_message(*args, **kwargs):
        captures.append((args, kwargs))

    # Patch the import used by the activity body.
    import api_server.temporal.activities.reconcile_ledger as mod
    monkeypatch.setattr(
        mod.sentry_sdk, "capture_message", _fake_capture_message,
    )

    acts = ReconcileLedgerActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    drift_count = await env.run(acts.reconcile)

    assert drift_count == 0, (
        f"matching cache+ledger MUST yield 0 drift; got {drift_count}"
    )
    assert captures == [], (
        f"no drift MUST mean no Sentry capture; got {captures}"
    )
    # Cache untouched.
    assert await _read_balance(db_pool, user_id) == 2500


# ---------------------------------------------------------------------------
# 2. Drift → Sentry capture_message at error level
# ---------------------------------------------------------------------------


async def test_reconcile_ledger_emits_sentry_capture_message_when_drift_detected(
    db_pool: asyncpg.Pool, monkeypatch,
) -> None:
    """cache=100, ledger SUM=50 → drift detected, Sentry message emitted."""
    user_id = await _seed_user(db_pool)
    await _seed_balance(db_pool, user_id=user_id, balance_cents=100)
    await _seed_topup_ledger(db_pool, user_id=user_id, amount_cents=50)

    captures: list[tuple] = []

    def _fake_capture_message(*args, **kwargs):
        captures.append((args, kwargs))

    import api_server.temporal.activities.reconcile_ledger as mod
    monkeypatch.setattr(
        mod.sentry_sdk, "capture_message", _fake_capture_message,
    )

    acts = ReconcileLedgerActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    drift_count = await env.run(acts.reconcile)

    assert drift_count == 1, f"expected 1 drift; got {drift_count}"
    assert len(captures) == 1, (
        f"expected exactly 1 Sentry capture; got {len(captures)}"
    )
    args, kwargs = captures[0]
    msg = args[0] if args else kwargs.get("message", "")
    assert "drift" in msg.lower()
    assert str(user_id) in msg
    # Phase 31 H6: capture at error level.
    assert kwargs.get("level") == "error", (
        f"Sentry level MUST be 'error'; got {kwargs.get('level')!r}"
    )


# ---------------------------------------------------------------------------
# 3. Repair-on-detect: cache moved to ledger truth
# ---------------------------------------------------------------------------


async def test_reconcile_ledger_repairs_cache_to_match_ledger_truth(
    db_pool: asyncpg.Pool, monkeypatch,
) -> None:
    """After reconcile, the drifting balance row matches ledger SUM."""
    user_id = await _seed_user(db_pool)
    await _seed_balance(db_pool, user_id=user_id, balance_cents=100)
    await _seed_topup_ledger(db_pool, user_id=user_id, amount_cents=50)

    # Silence Sentry — only assert the repair side-effect here.
    import api_server.temporal.activities.reconcile_ledger as mod
    monkeypatch.setattr(
        mod.sentry_sdk, "capture_message", lambda *a, **k: None,
    )

    acts = ReconcileLedgerActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    drift_count = await env.run(acts.reconcile)

    assert drift_count == 1
    # Cache repaired to ledger truth.
    assert await _read_balance(db_pool, user_id) == 50


# ---------------------------------------------------------------------------
# 4. Multiple users — only drifting rows surface; non-drifting untouched
# ---------------------------------------------------------------------------


async def test_reconcile_ledger_only_drifting_users_counted(
    db_pool: asyncpg.Pool, monkeypatch,
) -> None:
    """User A has correct cache; User B is drifting. Count = 1."""
    user_a = await _seed_user(db_pool)
    user_b = await _seed_user(db_pool)
    await _seed_balance(db_pool, user_id=user_a, balance_cents=300)
    await _seed_topup_ledger(db_pool, user_id=user_a, amount_cents=300)
    await _seed_balance(db_pool, user_id=user_b, balance_cents=999)
    await _seed_topup_ledger(db_pool, user_id=user_b, amount_cents=42)

    captures: list[tuple] = []

    def _fake_capture_message(*args, **kwargs):
        captures.append((args, kwargs))

    import api_server.temporal.activities.reconcile_ledger as mod
    monkeypatch.setattr(
        mod.sentry_sdk, "capture_message", _fake_capture_message,
    )

    acts = ReconcileLedgerActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    drift_count = await env.run(acts.reconcile)

    assert drift_count == 1
    assert len(captures) == 1
    msg = captures[0][0][0]
    assert str(user_b) in msg
    assert str(user_a) not in msg
    # Repair: B fixed to 42; A unchanged at 300.
    assert await _read_balance(db_pool, user_a) == 300
    assert await _read_balance(db_pool, user_b) == 42
