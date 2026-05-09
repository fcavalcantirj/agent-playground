"""Phase B Plan B-stripe-03 Task 1 — TDD route tests for /v1/billing/{packs,balance,transactions}.

Tests-first per CLAUDE.md golden rule #2 (dumb client) + Phase B D-06/D-21:
the api_server returns ready-to-render JSON. Mobile fetches the 5-pack
catalog via ``GET /v1/billing/packs`` (no client-side mirror, per
``feedback_dumb_client_no_mocks.md``); polls ``GET /v1/billing/balance``
post-Checkout for tier-aware UI; renders history via
``GET /v1/billing/transactions`` paginated by created_at-DESC cursor.

Coverage matrix (12 behaviors per PLAN <behavior>):

  GET /v1/billing/packs
   * 401 without cookie → Stripe envelope, code=UNAUTHORIZED
   * 200 returns 5 packs in order pack_5..pack_100
   * Response intentionally OMITS internal stripe_price_id (T-B-PRC)

  GET /v1/billing/balance
   * 401 without cookie
   * 200 with no credit_balances row → balance_cents=0, tier='free',
     display_balance_cents=0, is_negative=False
   * Negative balance → display_balance_cents=0 + is_negative=True
     (Pitfall 6 — D-16 refund/chargeback path)
   * Tier value reflects the row's value (free/pro/ultra)

  GET /v1/billing/transactions
   * 401 without cookie
   * 200 returns user's ledger rows ORDER BY created_at DESC
   * limit param clamps at upper bound (200) when ?limit > 200
   * before=<ts> filters to rows strictly older than the cursor
   * Cross-tenant defense — only the calling user's rows surface

Mirrors ``tests/routes/test_usage_endpoints.py`` shape verbatim:
``async_client`` + ``authenticated_cookie`` + ``second_authenticated_cookie``
fixtures from the top-level conftest; direct asyncpg seeds for
``credit_balances`` + ``credit_transactions``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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
    """Update users.tier for the calling user."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET tier = $1 WHERE id = $2", tier, user_id,
        )


async def _seed_balance(
    pool: asyncpg.Pool, *, user_id: UUID, balance_cents: int,
) -> None:
    """Upsert a credit_balances row at the given balance."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET balance_cents = $2",
            user_id, balance_cents,
        )


async def _seed_transaction(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    kind: str = "topup",
    amount_cents: int = 500,
    reference_id: str | None = None,
    reference_type: str | None = None,
    created_at: datetime | None = None,
) -> UUID:
    tx_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO credit_transactions
              (id, user_id, kind, amount_cents,
               reference_id, reference_type, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, NOW()))
            """,
            tx_id, user_id, kind, amount_cents,
            reference_id, reference_type, created_at,
        )
    return tx_id


# ---------------------------------------------------------------------------
# /v1/billing/packs — 3 tests
# ---------------------------------------------------------------------------


async def test_packs_unauthenticated_returns_401(
    async_client: httpx.AsyncClient,
) -> None:
    """No cookie → 401 + Stripe envelope code=UNAUTHORIZED."""
    r = await async_client.get("/v1/billing/packs")
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert body["error"]["param"] == "ap_session"


async def test_packs_authenticated_returns_5_packs_in_order(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
) -> None:
    """5 packs returned in pack_5 → pack_100 order with correct cents."""
    r = await async_client.get(
        "/v1/billing/packs",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    packs = body["packs"]
    assert len(packs) == 5
    expected_ids = ["pack_5", "pack_10", "pack_25", "pack_50", "pack_100"]
    assert [p["id"] for p in packs] == expected_ids
    expected_cents = [500, 1000, 2500, 5000, 10000]
    for pack, cents in zip(packs, expected_cents):
        assert pack["usd_amount_cents"] == cents
        # D-07 invariant: 1:1 USD→credit
        assert pack["credit_cents"] == cents
    # Labels are display strings ($5..$100)
    assert [p["label"] for p in packs] == ["$5", "$10", "$25", "$50", "$100"]


async def test_packs_response_omits_internal_stripe_price_id_field(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
) -> None:
    """T-B-PRC mitigation — stripe_price_id is internal, never projected."""
    r = await async_client.get(
        "/v1/billing/packs",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for pack in body["packs"]:
        assert "stripe_price_id" not in pack, (
            f"Internal stripe_price_id leaked in PackEntry: {pack}"
        )


# ---------------------------------------------------------------------------
# /v1/billing/balance — 4 tests
# ---------------------------------------------------------------------------


async def test_balance_unauthenticated_returns_401(
    async_client: httpx.AsyncClient,
) -> None:
    r = await async_client.get("/v1/billing/balance")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_balance_no_balance_row_returns_zero_for_free_tier(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
) -> None:
    """Free user with no credit_balances row → 0/free/0/False."""
    r = await async_client.get(
        "/v1/billing/balance",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "free"
    assert body["balance_cents"] == 0
    assert body["display_balance_cents"] == 0
    assert body["is_negative"] is False


async def test_balance_with_negative_balance_returns_is_negative_true_and_display_zero(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Pitfall 6 / D-16 — refund-driven negative balance projects display=0."""
    user_id = UUID(authenticated_cookie["_user_id"])
    await _seed_balance(db_pool, user_id=user_id, balance_cents=-150)
    r = await async_client.get(
        "/v1/billing/balance",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance_cents"] == -150
    assert body["display_balance_cents"] == 0
    assert body["is_negative"] is True


async def test_balance_returns_user_tier_value(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """tier='ultra' on the row surfaces verbatim in the response."""
    user_id = UUID(authenticated_cookie["_user_id"])
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=2500)
    r = await async_client.get(
        "/v1/billing/balance",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "ultra"
    assert body["balance_cents"] == 2500
    assert body["display_balance_cents"] == 2500
    assert body["is_negative"] is False


# ---------------------------------------------------------------------------
# /v1/billing/transactions — 5 tests
# ---------------------------------------------------------------------------


async def test_transactions_unauthenticated_returns_401(
    async_client: httpx.AsyncClient,
) -> None:
    r = await async_client.get("/v1/billing/transactions")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_transactions_returns_user_rows_ordered_desc(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """3 seeded rows surface in created_at DESC order with full payload."""
    user_id = UUID(authenticated_cookie["_user_id"])
    now = datetime.now(timezone.utc)
    await _seed_transaction(
        db_pool, user_id=user_id, kind="topup", amount_cents=500,
        reference_id="evt_oldest", reference_type="stripe_event",
        created_at=now - timedelta(hours=2),
    )
    await _seed_transaction(
        db_pool, user_id=user_id, kind="debit", amount_cents=-50,
        reference_id="usage_log_mid", reference_type="usage_log",
        created_at=now - timedelta(hours=1),
    )
    await _seed_transaction(
        db_pool, user_id=user_id, kind="topup", amount_cents=1000,
        reference_id="evt_newest", reference_type="stripe_event",
        created_at=now,
    )

    r = await async_client.get(
        "/v1/billing/transactions",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    txs = body["transactions"]
    assert len(txs) == 3
    # DESC by created_at: newest topup, then debit, then oldest topup.
    assert txs[0]["kind"] == "topup"
    assert txs[0]["amount_cents"] == 1000
    assert txs[0]["reference_id"] == "evt_newest"
    assert txs[1]["kind"] == "debit"
    assert txs[1]["amount_cents"] == -50
    assert txs[2]["amount_cents"] == 500
    # All entries carry the full descriptor shape.
    for tx in txs:
        assert "id" in tx and isinstance(tx["id"], str)
        assert "kind" in tx
        assert "amount_cents" in tx
        assert "reference_id" in tx
        assert "reference_type" in tx
        assert "created_at" in tx


async def test_transactions_pagination_limit_param_clamps_at_max(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """?limit=999 → FastAPI Query(le=200) returns 422 (validation)."""
    user_id = UUID(authenticated_cookie["_user_id"])
    # Seed a single row so the route is hit; we want validation behavior.
    await _seed_transaction(db_pool, user_id=user_id)
    r = await async_client.get(
        "/v1/billing/transactions?limit=999",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    # FastAPI validation rejects out-of-bound query params with 422.
    assert r.status_code == 422, r.text


async def test_transactions_pagination_before_filter_works(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """?before=<cursor> filters to rows strictly older than the cursor."""
    user_id = UUID(authenticated_cookie["_user_id"])
    now = datetime.now(timezone.utc)
    older = now - timedelta(hours=2)
    middle = now - timedelta(hours=1)
    await _seed_transaction(
        db_pool, user_id=user_id, kind="topup", amount_cents=100,
        reference_id="ref_old", reference_type="stripe_event",
        created_at=older,
    )
    await _seed_transaction(
        db_pool, user_id=user_id, kind="topup", amount_cents=200,
        reference_id="ref_mid", reference_type="stripe_event",
        created_at=middle,
    )
    await _seed_transaction(
        db_pool, user_id=user_id, kind="topup", amount_cents=300,
        reference_id="ref_new", reference_type="stripe_event",
        created_at=now,
    )

    # First page, no cursor — newest 2 rows.
    r = await async_client.get(
        "/v1/billing/transactions?limit=2",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["transactions"]) == 2
    assert body["transactions"][0]["amount_cents"] == 300
    assert body["transactions"][1]["amount_cents"] == 200
    # next_before reflects the oldest item shown (= middle row's ts).
    assert body["next_before"] is not None

    # Second page using the cursor — only the older row appears.
    cursor = body["next_before"]
    r2 = await async_client.get(
        f"/v1/billing/transactions?limit=2&before={cursor}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert len(body2["transactions"]) == 1
    assert body2["transactions"][0]["amount_cents"] == 100
    # Last page → no further cursor.
    assert body2["next_before"] is None


async def test_transactions_filters_to_calling_user_only(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
    second_authenticated_cookie: dict,
) -> None:
    """T-B-XT — User A's call returns ZERO rows from User B's ledger."""
    user_a = UUID(authenticated_cookie["_user_id"])
    user_b = UUID(second_authenticated_cookie["_user_id"])

    await _seed_transaction(
        db_pool, user_id=user_a, kind="topup", amount_cents=500,
        reference_id="user_a_topup", reference_type="stripe_event",
    )
    await _seed_transaction(
        db_pool, user_id=user_b, kind="topup", amount_cents=10000,
        reference_id="user_b_topup", reference_type="stripe_event",
    )

    # User A's view — only their row.
    r = await async_client.get(
        "/v1/billing/transactions",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    txs = r.json()["transactions"]
    assert len(txs) == 1
    assert txs[0]["amount_cents"] == 500
    assert txs[0]["reference_id"] == "user_a_topup"
