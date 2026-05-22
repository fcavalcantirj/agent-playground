"""Tests for POST /v1/billing/revenuecat/webhook.

Sibling to test_billing_webhook.py (Stripe). Coverage matrix:

  Auth + payload validation (4)
   * missing Authorization header → 400
   * wrong shared secret → 400
   * empty webhook_secret on deploy → 400 ("not configured")
   * malformed JSON → 400

  Idempotency (1)
   * duplicate rc_event_id → second POST 200, no double-credit

  Event matrix (7)
   * INITIAL_PURCHASE for pack → topup ledger row + balance += credit_cents
   * INITIAL_PURCHASE for Pro sub → tier free→pro + audit row
   * NON_RENEWING_PURCHASE for pack → same as INITIAL_PURCHASE
   * RENEWAL for Pro sub when tier=pro → idempotent ack (no second audit)
   * CANCELLATION → ack-only (tier unchanged)
   * EXPIRATION for Pro sub → tier pro→free
   * REFUND for pack → kind='refund', negative ledger row
"""
from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest


pytestmark = pytest.mark.api_integration




_TEST_RC_SECRET = "rc_test_webhook_secret_abc123"
_TEST_APPLE_PRO = "com.solvrlabs.agentplayground.pro_monthly"
_TEST_APPLE_PACK_5 = "com.solvrlabs.agentplayground.pack_5"
_TEST_GOOGLE_PACK_5 = "com.solvrlabs.agentplayground.pack_5"  # same id, diff store


def _build_event(
    *,
    event_id: str | None = None,
    event_type: str = "INITIAL_PURCHASE",
    app_user_id: str,
    product_id: str = _TEST_APPLE_PACK_5,
    store: str = "APP_STORE",
    transaction_id: str | None = None,
) -> dict:
    """Build a minimal RC webhook payload mirroring real shape."""
    return {
        "api_version": "1.0",
        "event": {
            "id": event_id or f"evt_{uuid4().hex[:16]}",
            "type": event_type,
            "app_user_id": app_user_id,
            "product_id": product_id,
            "store": store,
            "transaction_id": transaction_id or f"tx_{uuid4().hex[:16]}",
        },
    }


async def _seed_user(
    pool: asyncpg.Pool, *, tier: str = "free",
) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO users (id, provider, sub, email, display_name, tier) "
            "VALUES (gen_random_uuid(), 'google', $1, $2, 'Test', $3) "
            "RETURNING id",
            f"sub-{uuid4().hex[:12]}",
            f"u{uuid4().hex[:8]}@example.com",
            tier,
        )
    return row["id"]


async def _read_tier(pool: asyncpg.Pool, user_id: UUID) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT tier FROM users WHERE id = $1", user_id,
        )


async def _read_balance(pool: asyncpg.Pool, user_id: UUID) -> int:
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    return int(v or 0)


async def _count_rc_rows(pool: asyncpg.Pool, rc_event_id: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM revenuecat_webhook_events "
            "WHERE rc_event_id = $1",
            rc_event_id,
        )


async def _count_ledger(pool: asyncpg.Pool, user_id: UUID, kind: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = $2",
            user_id, kind,
        )


def _set_rc_settings(
    async_client: httpx.AsyncClient,
    secret: str = _TEST_RC_SECRET,
    apple_pro: str = _TEST_APPLE_PRO,
    apple_pack_5: str = _TEST_APPLE_PACK_5,
    google_pack_5: str = _TEST_GOOGLE_PACK_5,
) -> None:
    """Patch the app's settings + force re-build of billing_packs PACKS.

    Two-layer patching:
      1. app.state.settings — the webhook route reads
         settings.revenuecat_webhook_secret directly off the app state.
      2. os.environ + _build_packs() — billing_packs.PACKS is built at
         module import from a fresh ``Settings()`` (via
         ``config.get_settings()``), not from app.state.settings. So
         IAP product ids have to land in env BEFORE we re-run
         ``_build_packs()`` for the reverse-lookup helpers to see them.
    """
    app = async_client._transport.app  # type: ignore[attr-defined]
    s = app.state.settings
    object.__setattr__(s, "revenuecat_webhook_secret", secret)
    object.__setattr__(s, "apple_product_id_pro_monthly", apple_pro)
    object.__setattr__(s, "apple_product_id_pack_5", apple_pack_5)
    object.__setattr__(s, "google_product_id_pack_5", google_pack_5)
    # Env-level injection so _build_packs() picks them up.
    os.environ["AP_APPLE_PRODUCT_ID_PRO_MONTHLY"] = apple_pro
    os.environ["AP_APPLE_PRODUCT_ID_PACK_5"] = apple_pack_5
    os.environ["AP_GOOGLE_PRODUCT_ID_PACK_5"] = google_pack_5
    from api_server.services import billing_packs as bp
    bp.PACKS = bp._build_packs()


def _auth(secret: str = _TEST_RC_SECRET) -> dict:
    return {"Authorization": f"Bearer {secret}"}


# ---------------------------------------------------------------------------
# Auth + payload validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_authorization_header_400(async_client):
    _set_rc_settings(async_client)
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        json={"event": {"id": "evt_x", "type": "INITIAL_PURCHASE",
                        "app_user_id": "x"}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_wrong_secret_400(async_client):
    _set_rc_settings(async_client)
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth("wrong_secret"),
        json={"event": {"id": "evt_x", "type": "INITIAL_PURCHASE",
                        "app_user_id": "x"}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_secret_unset_on_deploy_400(async_client):
    _set_rc_settings(async_client, secret="")  # webhook NOT configured
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth("anything"),
        json={"event": {"id": "evt_x", "type": "INITIAL_PURCHASE",
                        "app_user_id": "x"}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_malformed_json_body_400(async_client):
    _set_rc_settings(async_client)
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers={**_auth(), "Content-Type": "application/json"},
        content=b"not json",
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_missing_event_fields_400(async_client):
    _set_rc_settings(async_client)
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(),
        json={"event": {"id": "evt_x"}},  # missing type, app_user_id
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_event_id_no_double_credit(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool)
    event = _build_event(
        event_type="INITIAL_PURCHASE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PACK_5,
        store="APP_STORE",
    )
    # First call — credits the ledger.
    r1 = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r1.status_code == 200
    # Second call — same event id — must NOT double-credit.
    r2 = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r2.status_code == 200
    # Exactly one ledger row, exactly one webhook row.
    assert await _count_ledger(db_pool, user_id, "topup") == 1
    assert await _count_rc_rows(db_pool, event["event"]["id"]) == 1
    assert await _read_balance(db_pool, user_id) == 500


# ---------------------------------------------------------------------------
# Event matrix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initial_purchase_pack_credits_ledger(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool)
    event = _build_event(
        event_type="INITIAL_PURCHASE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PACK_5,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    assert await _read_balance(db_pool, user_id) == 500  # pack_5 = 500 cents
    assert await _count_ledger(db_pool, user_id, "topup") == 1


@pytest.mark.asyncio
async def test_non_renewing_purchase_pack_credits_ledger(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool)
    event = _build_event(
        event_type="NON_RENEWING_PURCHASE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PACK_5,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    assert await _read_balance(db_pool, user_id) == 500


@pytest.mark.asyncio
async def test_initial_purchase_pro_sub_flips_tier_to_pro(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool, tier="free")
    event = _build_event(
        event_type="INITIAL_PURCHASE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PRO,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    assert await _read_tier(db_pool, user_id) == "pro"
    # An audit row should exist (kind='tier_change', amount_cents=0).
    assert await _count_ledger(db_pool, user_id, "tier_change") == 1


@pytest.mark.asyncio
async def test_renewal_when_already_pro_is_idempotent(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool, tier="pro")
    event = _build_event(
        event_type="RENEWAL",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PRO,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    assert await _read_tier(db_pool, user_id) == "pro"
    # Tier unchanged → no audit row written
    assert await _count_ledger(db_pool, user_id, "tier_change") == 0


@pytest.mark.asyncio
async def test_cancellation_is_ack_only(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool, tier="pro")
    event = _build_event(
        event_type="CANCELLATION",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PRO,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    # Tier UNCHANGED (still pro until EXPIRATION fires later)
    assert await _read_tier(db_pool, user_id) == "pro"


@pytest.mark.asyncio
async def test_expiration_flips_tier_to_free(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool, tier="pro")
    event = _build_event(
        event_type="EXPIRATION",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PRO,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    assert await _read_tier(db_pool, user_id) == "free"
    assert await _count_ledger(db_pool, user_id, "tier_change") == 1


@pytest.mark.asyncio
async def test_refund_for_pack_writes_negative_ledger_row(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool)
    # First, the original purchase
    purchase = _build_event(
        event_type="INITIAL_PURCHASE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PACK_5,
        store="APP_STORE",
        transaction_id="tx_orig_001",
    )
    await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=purchase,
    )
    assert await _read_balance(db_pool, user_id) == 500
    # Then the refund (different event id, same transaction_id)
    refund = _build_event(
        event_type="REFUND",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PACK_5,
        store="APP_STORE",
        transaction_id="tx_orig_001",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=refund,
    )
    assert r.status_code == 200
    assert await _count_ledger(db_pool, user_id, "refund") == 1
    assert await _read_balance(db_pool, user_id) == 0


@pytest.mark.asyncio
async def test_unknown_event_type_is_ack_only(async_client, db_pool):
    _set_rc_settings(async_client)
    user_id = await _seed_user(db_pool, tier="pro")
    event = _build_event(
        event_type="PRODUCT_CHANGE",
        app_user_id=str(user_id),
        product_id=_TEST_APPLE_PRO,
        store="APP_STORE",
    )
    r = await async_client.post(
        "/v1/billing/revenuecat/webhook",
        headers=_auth(), json=event,
    )
    assert r.status_code == 200
    # Tier untouched
    assert await _read_tier(db_pool, user_id) == "pro"
    # Webhook row inserted (for dedupe) but no ledger row
    assert await _count_ledger(db_pool, user_id, "tier_change") == 0
