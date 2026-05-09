"""Phase B Plan B-stripe-09 Task 2 — reconcile_stripe activity tests.

Real Postgres (testcontainers, alembic-migrated) + ``ActivityEnvironment``
per CLAUDE.md golden rule #1. The Stripe network boundary is replaced
by a hand-rolled FakeStripeClient that returns canned events — the
activity's Stripe interaction is one method (``client.events.list``)
and exercising real Stripe in an integration test would gate the suite
on network availability + TEST keys for every contributor.

(The full Stripe round-trip is covered by Phase B's e2e CI matrix
against real TEST keys per D-22; this file scopes to the
already-working substrate of: "given a missed event, did we apply it
exactly once via the same handler the live route uses?")

Coverage matrix per PLAN.md ``<behavior>``:

  * test_reconcile_stripe_picks_up_missed_event_and_applies_via_handler
  * test_reconcile_stripe_skips_already_processed_events
  * test_reconcile_stripe_with_no_events_returns_zero
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.reconcile_stripe import (
    ReconcileStripeActivities,
)


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Fake Stripe client — minimal shape the activity touches
# ---------------------------------------------------------------------------


class _FakeEventDataObject(dict):
    """Dict subclass that ALSO supports attribute access for the inner
    ``event.data.object`` shape ``_handle_checkout_completed`` walks.

    The webhook handler calls ``_as_dict(event.data.object)`` which uses
    ``.to_dict()`` if available, falling back to ``dict()``. Pure dicts
    are the simplest input that satisfies that path.
    """


class _FakeEventData:
    def __init__(self, *, obj: dict) -> None:
        self.object = _FakeEventDataObject(obj)


class _FakeEvent:
    def __init__(
        self,
        *,
        event_id: str,
        event_type: str,
        ap_user_id: str,
        pack_id: str = "pack_25",
        credit_cents: int = 2500,
        session_id: str | None = None,
    ) -> None:
        self.id = event_id
        self.type = event_type
        self.data = _FakeEventData(obj={
            "id": session_id or f"cs_test_{event_id}",
            "object": "checkout.session",
            "amount_total": credit_cents,
            "currency": "usd",
            "customer": f"cus_test_{ap_user_id[:8]}",
            "metadata": {
                "ap_user_id": ap_user_id,
                "pack_id": pack_id,
                "credit_cents": str(credit_cents),
            },
            "mode": "payment",
            "payment_status": "paid",
            "status": "complete",
        })


class _FakeEventsListResult:
    def __init__(self, *, data: list[_FakeEvent]) -> None:
        self.data = data


class _FakeEventsResource:
    def __init__(self, *, results: list[_FakeEvent]) -> None:
        self._results = results
        self.last_params: dict | None = None

    def list(self, *, params: dict) -> _FakeEventsListResult:
        self.last_params = params
        return _FakeEventsListResult(data=self._results)


class FakeStripeClient:
    """Minimal stand-in for ``stripe.StripeClient``.

    The activity touches ONLY ``client.events.list(params=...)`` so the
    fake exposes that path and nothing else. Tests pre-load events into
    the fake before calling ``acts.reconcile``.
    """

    def __init__(self, *, events: list[_FakeEvent] | None = None) -> None:
        self.events = _FakeEventsResource(results=events or [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    pool: asyncpg.Pool, *, tier: str = "free",
) -> UUID:
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, tier, display_name) "
            "VALUES ($1, $2, $3)",
            user_id, tier, f"reconcile-test-{uuid4().hex[:8]}",
        )
    return user_id


async def _count_webhook_rows(
    pool: asyncpg.Pool, *, stripe_event_id: str,
) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*)::int FROM stripe_webhook_events "
            "WHERE stripe_event_id = $1",
            stripe_event_id,
        )


async def _count_topup_rows(pool: asyncpg.Pool, user_id: UUID) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*)::int FROM credit_transactions "
            "WHERE user_id = $1 AND kind = 'topup'",
            user_id,
        )


async def _read_tier(pool: asyncpg.Pool, user_id: UUID) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT tier FROM users WHERE id = $1", user_id,
        )


# ---------------------------------------------------------------------------
# 1. Missed event → applied via the same handler the route uses
# ---------------------------------------------------------------------------


async def test_reconcile_stripe_picks_up_missed_event_and_applies_via_handler(
    db_pool: asyncpg.Pool,
) -> None:
    """A `checkout.session.completed` not in stripe_webhook_events triggers
    the same `_handle_checkout_completed` path the live route uses:
    ledger 'topup' row + tier flip free→ultra + dedupe row INSERTed.
    """
    user_id = await _seed_user(db_pool, tier="free")
    event = _FakeEvent(
        event_id="evt_test_reconcile_001",
        event_type="checkout.session.completed",
        ap_user_id=str(user_id),
        credit_cents=2500,
    )
    fake_client = FakeStripeClient(events=[event])

    acts = ReconcileStripeActivities(
        db_pool=db_pool, stripe_client=fake_client,
    )
    env = ActivityEnvironment()
    applied = await env.run(acts.reconcile)

    assert applied == 1, f"expected 1 applied event; got {applied}"
    # Side-effects: ledger topup + tier flip.
    assert await _count_topup_rows(db_pool, user_id) == 1
    assert await _read_tier(db_pool, user_id) == "ultra"
    # Dedupe row landed.
    assert await _count_webhook_rows(
        db_pool, stripe_event_id="evt_test_reconcile_001",
    ) == 1


# ---------------------------------------------------------------------------
# 2. Already-processed event is skipped (no double-apply)
# ---------------------------------------------------------------------------


async def test_reconcile_stripe_skips_already_processed_events(
    db_pool: asyncpg.Pool,
) -> None:
    """Pre-seed a stripe_webhook_events row matching the event id; the
    reconcile must skip it (applied count == 0; no duplicate ledger row).
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    event_id = "evt_test_reconcile_already_002"

    # Seed the dedupe row + a prior topup as if the live webhook applied.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO stripe_webhook_events "
            "  (stripe_event_id, event_type, payload) "
            "VALUES ($1, 'checkout.session.completed', '{}')",
            event_id,
        )
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, 2500)",
            user_id,
        )
        await conn.execute(
            """
            INSERT INTO credit_transactions
              (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1, 'topup', 2500, $2, 'stripe_checkout_session')
            """,
            user_id, "cs_test_already",
        )

    event = _FakeEvent(
        event_id=event_id,
        event_type="checkout.session.completed",
        ap_user_id=str(user_id),
        credit_cents=2500,
    )
    fake_client = FakeStripeClient(events=[event])

    acts = ReconcileStripeActivities(
        db_pool=db_pool, stripe_client=fake_client,
    )
    env = ActivityEnvironment()
    applied = await env.run(acts.reconcile)

    assert applied == 0, (
        f"already-processed event MUST be skipped; applied={applied}"
    )
    # Still exactly one topup row (the prior one); no double-apply.
    assert await _count_topup_rows(db_pool, user_id) == 1
    # Still exactly one dedupe row.
    assert await _count_webhook_rows(
        db_pool, stripe_event_id=event_id,
    ) == 1


# ---------------------------------------------------------------------------
# 3. No events → applied count == 0 (steady state)
# ---------------------------------------------------------------------------


async def test_reconcile_stripe_with_no_events_returns_zero(
    db_pool: asyncpg.Pool,
) -> None:
    """Empty Stripe page → zero applied; no DB mutations."""
    fake_client = FakeStripeClient(events=[])
    acts = ReconcileStripeActivities(
        db_pool=db_pool, stripe_client=fake_client,
    )
    env = ActivityEnvironment()
    applied = await env.run(acts.reconcile)
    assert applied == 0


# ---------------------------------------------------------------------------
# 4. Query window — last 15 minutes (3× cron period)
# ---------------------------------------------------------------------------


async def test_reconcile_stripe_queries_with_15_minute_window(
    db_pool: asyncpg.Pool,
) -> None:
    """Activity passes ``created.gte = now - 15min`` to events.list."""
    fake_client = FakeStripeClient(events=[])
    acts = ReconcileStripeActivities(
        db_pool=db_pool, stripe_client=fake_client,
    )
    env = ActivityEnvironment()
    await env.run(acts.reconcile)

    params: dict[str, Any] = fake_client.events.last_params or {}
    assert params.get("type") == "checkout.session.completed"
    assert params.get("limit") == 100
    created = params.get("created") or {}
    assert "gte" in created
    # 15 min = 900s; allow some slack since the test uses real wall time.
    from time import time as _time
    expected_gte = int(_time()) - 900
    assert abs(int(created["gte"]) - expected_gte) <= 5
