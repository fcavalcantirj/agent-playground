"""Phase B Plan B-stripe-04 — TDD route tests for tier-aware /v1/usage/summary.

Tests-first per CLAUDE.md golden rule #2 (dumb client) + Phase B D-02/D-21:
the api_server projects ``tier`` (always) and ``balance_cents`` /
``display_balance_cents`` / ``is_negative`` (only for ``tier='ultra'``).

Mobile's ``UsageTickerWidget`` (Wave 5 update) reads this single endpoint
and branches its render on tier — USD ticker for free/pro, credit balance
for ultra. Single-endpoint approach keeps mobile from having to choose
between ``/v1/usage/summary`` and ``/v1/billing/balance`` (dumb-client rule).

Coverage matrix (6 behaviors per PLAN <behavior>):

  * test_summary_for_free_tier_returns_tier_field_but_NOT_balance_cents
  * test_summary_for_pro_tier_returns_tier_field_but_NOT_balance_cents
  * test_summary_for_ultra_tier_returns_tier_AND_balance_cents_AND_display_balance_AND_is_negative
  * test_summary_for_ultra_with_zero_balance_returns_balance_cents_zero_is_negative_false
  * test_summary_for_ultra_with_negative_balance_returns_negative_is_negative_true_display_zero
  * test_summary_existing_phase_a_fields_unchanged_for_free_user

Backward-compatibility invariant (T-B-LEAK mitigation): Free/Pro responses
must NOT carry ``balance_cents``, ``display_balance_cents``, or
``is_negative`` keys at all — Phase A consumers see byte-identical shape.

Mirrors ``tests/routes/test_billing_read_routes.py`` shape verbatim:
``async_client`` + ``authenticated_cookie`` from the top-level conftest;
direct asyncpg seeds for ``users.tier`` + ``credit_balances``.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg
import httpx
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _set_user_tier(
    pool: asyncpg.Pool, *, user_id: UUID, tier: str,
) -> None:
    """Update users.tier for the calling user (D-04 webhook is normally the
    sole writer; tests bypass via direct UPDATE so we don't have to drive
    Stripe events to set up state)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET tier = $1 WHERE id = $2", tier, user_id,
        )


async def _seed_balance(
    pool: asyncpg.Pool, *, user_id: UUID, balance_cents: int,
) -> None:
    """Upsert a credit_balances row at the given balance.

    Negative values are valid (D-16 refund/chargeback path) — the table
    column is BIGINT NOT NULL with no CHECK constraint disallowing
    negatives, by design.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET balance_cents = $2",
            user_id, balance_cents,
        )


# ---------------------------------------------------------------------------
# Tier projection — 6 tests
# ---------------------------------------------------------------------------


async def test_summary_for_free_tier_returns_tier_field_but_NOT_balance_cents(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Free user (default tier) → tier='free' present; ultra-only fields ABSENT.

    The user is seeded by the ``authenticated_cookie`` fixture with the
    schema default ``tier='free'``; no balance row exists. Phase A
    consumers must see byte-identical shape — assert ultra-only keys are
    NOT present at all (not just None).
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    # No tier change — fixture-seeded user is tier='free' by schema default.
    # No credit_balances row — Free users don't have one (Wave 1 Plan 02 D-17).

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # tier always present (defaults projected for every user)
    assert body["tier"] == "free"

    # T-B-LEAK invariant — ultra-only keys are ABSENT for free tier.
    assert "balance_cents" not in body, body
    assert "display_balance_cents" not in body, body
    assert "is_negative" not in body, body

    # Phase A regression — existing keys still present + correct shape.
    assert isinstance(body["total_usd"], str)
    assert "message_count" in body
    assert "by_agent" in body
    assert isinstance(body["by_agent"], list)


async def test_summary_for_pro_tier_returns_tier_field_but_NOT_balance_cents(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Pro user → tier='pro' present; ultra-only fields ABSENT.

    Pro is BYOK + Stripe subscription — D-02 says Pro users keep the same
    USD-cost visibility shape as Free (no platform-billed metering).
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    await _set_user_tier(db_pool, user_id=user_id, tier="pro")

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tier"] == "pro"
    # T-B-LEAK — Pro users don't get a credit balance shape leak either.
    assert "balance_cents" not in body, body
    assert "display_balance_cents" not in body, body
    assert "is_negative" not in body, body


async def test_summary_for_ultra_tier_returns_tier_AND_balance_cents_AND_display_balance_AND_is_negative(  # noqa: E501
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Ultra user with positive balance → all 4 fields present + correct values."""
    user_id = UUID(authenticated_cookie["_user_id"])
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=1234)

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tier"] == "ultra"
    assert body["balance_cents"] == 1234
    assert body["display_balance_cents"] == 1234
    assert body["is_negative"] is False


async def test_summary_for_ultra_with_zero_balance_returns_balance_cents_zero_is_negative_false(  # noqa: E501
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Ultra user with NO credit_balances row OR balance=0 → 0/0/false.

    D-12 pre-flight 402 condition is ``balance_cents < 1`` so 0 is the
    boundary; mobile's modal triggers off ``is_negative=False`` and
    ``balance_cents == 0`` to differentiate "out of credits" from
    "owes money after refund".
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    # No _seed_balance call → COALESCE(balance,0) path covers the LEFT JOIN miss.

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tier"] == "ultra"
    assert body["balance_cents"] == 0
    assert body["display_balance_cents"] == 0
    assert body["is_negative"] is False


async def test_summary_for_ultra_with_negative_balance_returns_negative_is_negative_true_display_zero(  # noqa: E501
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Ultra user with negative balance (D-16 refund path) → display=0, is_negative=true.

    Pitfall 6: clamping display to >= 0 keeps the UI from showing a
    negative dollar amount; ``is_negative`` flag triggers the
    "you owe credits — top up to clear write-off" UX in mobile.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=-500)

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tier"] == "ultra"
    assert body["balance_cents"] == -500
    assert body["display_balance_cents"] == 0  # clamped >= 0 (Pitfall 6)
    assert body["is_negative"] is True


async def test_summary_existing_phase_a_fields_unchanged_for_free_user(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Phase A regression gate — free user's response carries every existing
    Phase A field byte-identical: total_usd (string), message_count (int),
    by_agent (list), and the per-agent entry shape.

    This is the load-bearing must_haves.truths[2]: 'Existing
    /v1/usage/summary contract stays byte-identical for the fields Phase A
    clients already consume'. Phase A tests in test_usage_endpoints.py
    cover the full shape; this test pins the no-regression invariant
    inline at the tier-projection layer so a future refactor of the
    handler can't silently shift Phase A keys.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    # No tier change — default 'free'.

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Phase A fields — exact set of keys for empty-state free user.
    assert set(body.keys()) == {"total_usd", "message_count", "by_agent", "tier"}, body
    assert isinstance(body["total_usd"], str)
    assert Decimal(body["total_usd"]) == Decimal("0")
    assert body["message_count"] == 0
    assert body["by_agent"] == []
    # tier is the only addition Phase A consumers see — a forward-compat
    # additive field; existing clients ignore it.
    assert body["tier"] == "free"
