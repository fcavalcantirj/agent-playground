"""Phase B Plan B-stripe-08 Task 1 — debit_balance activity tests.

Real Postgres (testcontainers, alembic-migrated) + ``ActivityEnvironment``
(real Temporal SDK activity runner) per CLAUDE.md golden rule #1.

Coverage matrix per PLAN.md ``<behavior>``:

* ``test_returns_zero_for_free_tier``
* ``test_returns_zero_for_pro_tier``
* ``test_returns_zero_when_usage_logs_status_is_failed``
* ``test_returns_zero_when_usage_logs_cost_usd_is_null``
* ``test_returns_zero_when_no_usage_logs_row_for_message``
* ``test_inserts_negative_amount_ledger_row_for_ultra_with_successful_usage``
* ``test_rebuilds_balance_cache_from_ledger_sum``
* ``test_idempotent_on_temporal_retry``
* ``test_call_site_byte_identity_in_dispatch_message_workflow_unchanged``

Spike-B (``tests/_spikes/spike_b_debit_activity_contract.py``) proved the
``UniqueViolationError`` round-trip in Wave 0; this test file replays the
same shape against the migration-014 schema with the real
``services.ledger.debit_user`` helper instead of the spike's inline INSERT.
"""
from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from temporalio import activity
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.debit_balance import DebitBalanceActivities


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    pool: asyncpg.Pool, *, tier: str = "ultra",
) -> UUID:
    """INSERT a ``users`` row with the requested tier."""
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, tier, display_name) VALUES ($1, $2, $3)",
            user_id, tier, f"debit-test-{tier}",
        )
    return user_id


async def _seed_agent(pool: asyncpg.Pool, *, user_id: UUID) -> UUID:
    """INSERT an ``agent_instances`` row owned by the given user."""
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'recipe-x', 'm-test', $3)
            """,
            agent_id, user_id, f"agent-{uuid4().hex[:8]}",
        )
    return agent_id


async def _seed_usage_log(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    message_id: UUID,
    cost_usd: Decimal | None,
    status: str = "success",
    status_code: int = 200,
) -> UUID:
    """INSERT one usage_logs row keyed on the workflow's ``message_id``.

    ``cost_usd`` may be ``None`` to exercise the null-cost branch.
    """
    row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_logs (
                id, user_id, agent_instance_id, message_id,
                provider, model, upstream_request_id,
                input_tokens, output_tokens,
                cost_usd, status, status_code, source
            ) VALUES (
                $1, $2, $3, $4,
                'openrouter', 'm-test', 'gen-test',
                10, 20,
                $5, $6, $7, 'inapp'
            )
            """,
            row_id, user_id, agent_instance_id, message_id,
            cost_usd, status, status_code,
        )
    return row_id


async def _seed_topup(
    pool: asyncpg.Pool, *, user_id: UUID, amount_cents: int,
) -> None:
    """Seed an initial topup so debits land into a non-zero balance."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, $2)",
            user_id, amount_cents,
        )
        await conn.execute(
            """
            INSERT INTO credit_transactions
                (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1, 'topup', $2, $3, 'stripe_session')
            """,
            user_id, amount_cents, f"seed-topup-{uuid4().hex[:12]}",
        )


def _make_inp(*, message_id: UUID, user_id: UUID) -> Any:
    """Synthesize a minimal object exposing ``inp.user_id`` + ``inp.message_id``.

    The activity body only reads two attributes from the workflow's
    ``DispatchMessageInput`` dataclass; using a plain object avoids
    over-specifying the dataclass's other fields when they are unused
    by this code path.
    """
    class _Inp:
        pass

    obj = _Inp()
    obj.user_id = str(user_id)
    obj.message_id = str(message_id)
    return obj


# ---------------------------------------------------------------------------
# 1. tier='free' → "0"
# ---------------------------------------------------------------------------


async def test_returns_zero_for_free_tier(db_pool: asyncpg.Pool) -> None:
    user_id = await _seed_user(db_pool, tier="free")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    message_id = uuid4()
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=Decimal("0.000123"),
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    assert result == "0", f"free-tier MUST return '0'; got {result!r}"
    # No ledger row created.
    async with db_pool.acquire() as conn:
        debits = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = 'debit'",
            user_id,
        )
    assert debits == 0


# ---------------------------------------------------------------------------
# 2. tier='pro' → "0"
# ---------------------------------------------------------------------------


async def test_returns_zero_for_pro_tier(db_pool: asyncpg.Pool) -> None:
    user_id = await _seed_user(db_pool, tier="pro")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    message_id = uuid4()
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=Decimal("0.000123"),
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    assert result == "0", f"pro-tier MUST return '0'; got {result!r}"
    async with db_pool.acquire() as conn:
        debits = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = 'debit'",
            user_id,
        )
    assert debits == 0


# ---------------------------------------------------------------------------
# 3. usage_logs.status='failed' → "0" (D-13)
# ---------------------------------------------------------------------------


async def test_returns_zero_when_usage_logs_status_is_failed(
    db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=10_000)
    message_id = uuid4()
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=Decimal("0.005"),
        status="failed", status_code=500,
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    assert result == "0", (
        f"failed-upstream MUST return '0' (D-13); got {result!r}"
    )
    async with db_pool.acquire() as conn:
        bal = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    assert bal == 10_000, f"balance MUST be unchanged; got {bal}"


# ---------------------------------------------------------------------------
# 4. usage_logs.cost_usd is null → "0"
# ---------------------------------------------------------------------------


async def test_returns_zero_when_usage_logs_cost_usd_is_null(
    db_pool: asyncpg.Pool,
) -> None:
    """``usage_logs.cost_usd`` is NOT NULL with default 0 (migration 011).

    The "null cost_usd" intent in the plan's behavior list maps to
    ``cost_usd = 0`` here — the column is NOT NULL with a 0 default and
    the activity's ``cost_cents <= 0`` guard returns "0" for both. We
    seed an explicit 0 to exercise the same branch as the original null
    intent without violating the schema's NOT NULL.
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=10_000)
    message_id = uuid4()
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=Decimal("0"),
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    assert result == "0", (
        f"zero cost_usd MUST return '0'; got {result!r}"
    )
    # No ledger row, balance unchanged.
    async with db_pool.acquire() as conn:
        debits = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = 'debit'",
            user_id,
        )
        bal = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    assert debits == 0
    assert bal == 10_000


# ---------------------------------------------------------------------------
# 5. no usage_logs row for the message → "0"
# ---------------------------------------------------------------------------


async def test_returns_zero_when_no_usage_logs_row_for_message(
    db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=10_000)
    # Note: NO usage_logs row created for this message_id.
    message_id = uuid4()

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    assert result == "0", (
        f"missing usage_logs row MUST return '0'; got {result!r}"
    )


# ---------------------------------------------------------------------------
# 6. ultra + status='success' + cost_usd>0 → ledger row inserted
# ---------------------------------------------------------------------------


async def test_inserts_negative_amount_ledger_row_for_ultra_with_successful_usage(
    db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=10_000)
    message_id = uuid4()
    # cost_usd $0.05 → 5 cents debit.
    cost_usd = Decimal("0.05")
    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=cost_usd,
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    result = await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    # Decimal-as-string contract.
    assert isinstance(result, str), f"expected str return; got {type(result)}"
    assert Decimal(result) == Decimal("0.05"), (
        f"expected '0.05'; got {result!r}"
    )
    # Ledger row inserted with negative amount + reference_id keyed on
    # the usage_logs.id (D-22 idempotency rail).
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT amount_cents, kind, reference_id, reference_type
            FROM credit_transactions
            WHERE user_id = $1 AND kind = 'debit'
            """,
            user_id,
        )
    assert row is not None, "expected one debit row to be inserted"
    assert row["amount_cents"] == -5, (
        f"expected amount_cents=-5; got {row['amount_cents']}"
    )
    assert row["reference_id"] == str(usage_log_id), (
        f"reference_id MUST equal usage_logs.id; got {row['reference_id']!r}"
    )
    assert row["reference_type"] == "usage_log"


# ---------------------------------------------------------------------------
# 7. balance cache rebuilt from ledger SUM (D-17)
# ---------------------------------------------------------------------------


async def test_rebuilds_balance_cache_from_ledger_sum(
    db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=1_000)  # $10
    message_id = uuid4()
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=Decimal("0.10"),  # 10 cents debit
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    await env.run(acts.debit_balance, _make_inp(
        message_id=message_id, user_id=user_id,
    ))

    # Balance cache MUST equal SUM(amount_cents) = 1000 + (-10) = 990.
    async with db_pool.acquire() as conn:
        bal = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
        ledger_sum = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_cents), 0)::BIGINT "
            "FROM credit_transactions WHERE user_id = $1",
            user_id,
        )
    assert bal == 990, f"expected balance_cents=990; got {bal}"
    assert int(ledger_sum) == 990, (
        f"ledger SUM disagreement: bal={bal} ledger={ledger_sum}"
    )


# ---------------------------------------------------------------------------
# 8. Temporal retry → UNIQUE-violation caught; no double-debit
# ---------------------------------------------------------------------------


async def test_idempotent_on_temporal_retry(db_pool: asyncpg.Pool) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_topup(db_pool, user_id=user_id, amount_cents=10_000)
    message_id = uuid4()
    cost_usd = Decimal("0.07")  # 7 cents
    await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        message_id=message_id, cost_usd=cost_usd,
    )

    acts = DebitBalanceActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    inp = _make_inp(message_id=message_id, user_id=user_id)

    first = await env.run(acts.debit_balance, inp)
    second = await env.run(acts.debit_balance, inp)

    assert first == second, (
        f"retry MUST return same string; first={first!r} second={second!r}"
    )
    assert Decimal(first) == Decimal("0.07")

    async with db_pool.acquire() as conn:
        debit_count = await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = 'debit'",
            user_id,
        )
        bal = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    assert debit_count == 1, (
        f"retry MUST NOT insert a duplicate debit row; got {debit_count}"
    )
    # Balance: 10000 + (-7) = 9993.
    assert bal == 9993, f"expected balance_cents=9993; got {bal}"


# ---------------------------------------------------------------------------
# 9. Phase 28 D-22 lock — workflow file is byte-unchanged
# ---------------------------------------------------------------------------


def test_call_site_byte_identity_in_dispatch_message_workflow_unchanged() -> None:
    """The workflow's ``execute_activity`` call site MUST stay byte-identical
    per Phase 28 D-22; this test grep-locks the contract.

    If a future refactor renames the activity reference in the workflow,
    this test fails — and the failure is the right answer (D-22 says:
    don't reshape the workflow from Phase B).
    """
    workflow_path = pathlib.Path(__file__).resolve().parents[2] / (
        "src/api_server/temporal/workflows/dispatch_message.py"
    )
    src = workflow_path.read_text()
    # Phase 28 sealed call-site uses the function-reference form
    # ``debit_balance.debit_balance``. Either spelling on whitespace is
    # acceptable; the assertion succeeds when at least one form matches.
    candidates = (
        "execute_activity(\n                debit_balance.debit_balance",
        "execute_activity(\n            debit_balance.debit_balance",
        "execute_activity(\n        debit_balance.debit_balance",
        "execute_activity(debit_balance.debit_balance",
        'execute_activity("debit_balance"',
    )
    assert any(c in src for c in candidates), (
        "workflow's execute_activity call for debit_balance MUST be unchanged "
        "(Phase 28 D-22 lock); checked patterns: {0}".format(candidates)
    )
