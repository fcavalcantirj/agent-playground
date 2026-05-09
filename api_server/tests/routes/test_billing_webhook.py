"""Phase B Plan B-stripe-06 — TDD route tests for POST /v1/billing/webhook.

Tests-first per CLAUDE.md golden rule #5 + Phase B D-04 / D-14 / D-22:
the api_server is the **sole writer** of ``users.tier`` (D-04). Tier flips
arrive through this route, signed by Stripe, idempotent on
``stripe_webhook_events.stripe_event_id``. Same-transaction wraps the
idempotency-row INSERT and the side-effect (Pitfall 2) so a side-effect
failure rolls the dedupe row back and Stripe's retry sees a clean state.

Coverage matrix (15 tests per PLAN <behavior>):

  Signature & idempotency (5)
   * missing Stripe-Signature → 400 STRIPE_WEBHOOK_INVALID
   * bad signature → 400 STRIPE_WEBHOOK_INVALID
   * stale timestamp (>5 min) → 400 STRIPE_WEBHOOK_INVALID
   * duplicate event_id → second POST returns 200 + skips side-effect
   * side-effect raises → idempotency row rolled back (next retry can re-process)

  Event matrix (10)
   * checkout.session.completed → ledger 'topup' row + tier flip free→ultra
   * customer.subscription.created → tier='pro' + audit row
   * customer.subscription.updated cancel_at_period_end=true → state stored,
     tier UNCHANGED
   * customer.subscription.deleted → tier='free' + 4-oldest non-paused agents
     auto-paused (D-15); audit row written
   * customer.subscription.deleted with 3 agents → cap=1 keeps oldest,
     pauses 2 (no IndexError; OFFSET 1 LIMIT 4 handles short lists)
   * charge.refunded → kind='refund' negative ledger row; balance recomputes
   * invoice.paid → ack-only (no ledger / tier change)
   * invoice.payment_failed → ack-only (Smart Retries)
   * payment_intent.succeeded → AMD-05 ack-only, NO branch on this event
   * unknown event type → 200 ack

D-04 invariant: only this route mutates ``users.tier``. Webhook is the
sole writer.

D-22 invariant: hand-rolled signed fixtures via ``sign_webhook_payload``.
stripe-mock cannot synthesize webhook events; AMD-02 calls for real
HMAC-signed payloads against ``stripe.StripeClient.construct_event``.

Real Postgres testcontainer drives every assertion (golden rule #1
no mocks of core substrate).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time as _time
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from tests._fixtures.sign_webhook import sign_webhook_payload


pytestmark = pytest.mark.api_integration


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "_fixtures" / "stripe_webhooks"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _load_raw(name: str) -> bytes:
    """Read a fixture and return its raw bytes (no transforms)."""
    return (FIXTURES_DIR / f"{name}.json").read_bytes()


def _load_fixture(name: str, ap_user_id: str | None = None) -> bytes:
    """Load fixture JSON, substituting the ap_user_id placeholder.

    Stripe signs raw bytes; the signature is over EXACTLY the bytes that
    will be POSTed. We replace ``__AP_USER_ID__`` BEFORE signing so the
    HMAC matches the bytes the route receives.
    """
    raw = (FIXTURES_DIR / f"{name}.json").read_text()
    if ap_user_id is not None:
        raw = raw.replace("__AP_USER_ID__", ap_user_id)
    return raw.encode()


def _override_event_id(payload: bytes, new_event_id: str) -> bytes:
    """Re-render the JSON with a different ``id`` field. Used to mint
    multiple distinct event-id replays of the same fixture body in one
    test run (TRUNCATE between tests + a fresh evt_test_* id per case)."""
    obj = json.loads(payload.decode())
    obj["id"] = new_event_id
    return json.dumps(obj, separators=(",", ":")).encode()


async def _seed_user(
    pool: asyncpg.Pool,
    *,
    tier: str = "free",
    stripe_customer_id: str | None = None,
) -> UUID:
    """Insert a user row and return its UUID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO users (id, provider, sub, email, display_name, tier, "
            "stripe_customer_id) "
            "VALUES (gen_random_uuid(), 'google', $1, $2, 'Test', $3, $4) "
            "RETURNING id",
            f"sub-{uuid4().hex[:12]}",
            f"u{uuid4().hex[:8]}@example.com",
            tier,
            stripe_customer_id,
        )
    return row["id"]


async def _read_user_tier(pool: asyncpg.Pool, user_id: UUID) -> str:
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


async def _count_webhook_rows(pool: asyncpg.Pool, stripe_event_id: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM stripe_webhook_events "
            "WHERE stripe_event_id = $1",
            stripe_event_id,
        )


async def _count_ledger_rows(pool: asyncpg.Pool, user_id: UUID, kind: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM credit_transactions "
            "WHERE user_id = $1 AND kind = $2",
            user_id, kind,
        )


async def _seed_agent_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    container_status: str = "running",
    created_at: datetime | None = None,
) -> UUID:
    """Insert an ``agent_containers`` row (ties to a fresh agent_instance)."""
    async with pool.acquire() as conn:
        # agent_instances FK is NOT NULL; mint a row to point at.
        ai_id = await conn.fetchval(
            "INSERT INTO agent_instances (id, user_id, recipe_name, name) "
            "VALUES (gen_random_uuid(), $1, 'hermes', $2) RETURNING id",
            user_id, f"agent-{uuid4().hex[:8]}",
        )
        row_id = await conn.fetchval(
            "INSERT INTO agent_containers "
            "  (id, user_id, agent_instance_id, recipe_name, deploy_mode, "
            "   container_status, created_at) "
            "VALUES (gen_random_uuid(), $1, $2, 'hermes', 'persistent', $3, "
            "        COALESCE($4, NOW())) "
            "RETURNING id",
            user_id, ai_id, container_status, created_at,
        )
    return row_id


def _set_app_settings_webhook_secret(
    async_client: httpx.AsyncClient, secret: str,
) -> None:
    """Ensure the app's runtime settings expose ``stripe_webhook_secret``.

    Tests sign with the value we set; if the dev placeholder differs from
    our test-known secret the signature won't verify. Mutating the
    Settings object directly is the simplest path — the Settings field
    isn't immutable and all downstream code reads it via
    ``request.app.state.settings.stripe_webhook_secret``.
    """
    app = async_client._app  # type: ignore[attr-defined]
    app.state.settings.stripe_webhook_secret = secret


WEBHOOK_SECRET = "whsec_test_b_stripe_06"


# ---------------------------------------------------------------------------
# Signature & idempotency (5)
# ---------------------------------------------------------------------------


async def test_missing_signature_returns_400(
    async_client: httpx.AsyncClient,
) -> None:
    """No Stripe-Signature header → 400 STRIPE_WEBHOOK_INVALID."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "STRIPE_WEBHOOK_INVALID"


async def test_bad_signature_returns_400_with_stripe_webhook_invalid_code(
    async_client: httpx.AsyncClient,
) -> None:
    """Garbage signature header → 400 STRIPE_WEBHOOK_INVALID."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=b'{"id":"evt_garbage","type":"unknown"}',
        headers={
            "Stripe-Signature": "t=12345,v1=deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "STRIPE_WEBHOOK_INVALID"


async def test_stale_timestamp_returns_400(
    async_client: httpx.AsyncClient,
) -> None:
    """Timestamp 10 minutes old → SDK enforces 5-min tolerance → 400."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    payload = b'{"id":"evt_stale","type":"unknown.event","data":{"object":{}}}'
    stale_sig = sign_webhook_payload(
        payload, WEBHOOK_SECRET, ts=int(_time()) - 600,
    )
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": stale_sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "STRIPE_WEBHOOK_INVALID"


async def test_duplicate_event_id_returns_200_no_double_side_effect(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """Second POST with same event_id is short-circuited by ON CONFLICT."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(db_pool, tier="free")
    payload = _load_fixture("checkout_session_completed", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)

    # 1st POST — should fire the side-effect.
    r1 = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json() == {"received": True}
    assert await _read_balance(db_pool, user_id) == 2500
    assert await _read_user_tier(db_pool, user_id) == "ultra"

    # 2nd POST identical → ON CONFLICT short-circuits; no double-credit.
    r2 = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"received": True}
    # Balance unchanged, only one ledger 'topup' row exists.
    assert await _read_balance(db_pool, user_id) == 2500
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 1
    # Only one stripe_webhook_events row landed.
    assert await _count_webhook_rows(
        db_pool, "evt_test_checkout_session_completed_001",
    ) == 1


async def test_side_effect_failure_rolls_back_idempotency_row(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    monkeypatch,
) -> None:
    """If credit_user raises, the stripe_webhook_events INSERT rolls back.

    Pitfall 2: the dedupe row + side-effect run in the SAME transaction
    so a 5xx on the side-effect leaves Stripe with a clean retry path.
    """
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(db_pool, tier="free")

    # Patch credit_user inside the route module so the route's import
    # binding flips to a function that raises.
    from api_server.routes import billing_webhook as bw_module

    async def _raise_credit_user(*args, **kwargs):
        raise RuntimeError("synthetic failure for rollback test")

    monkeypatch.setattr(bw_module, "credit_user", _raise_credit_user)

    payload = _load_fixture("checkout_session_completed", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    # FastAPI surfaces the exception as 500. The exact status is less
    # important than the rollback assertion below.
    assert r.status_code >= 500, r.text
    # The idempotency row was rolled back — Stripe can retry cleanly.
    assert await _count_webhook_rows(
        db_pool, "evt_test_checkout_session_completed_001",
    ) == 0
    # No partial ledger state.
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 0
    assert await _read_user_tier(db_pool, user_id) == "free"


# ---------------------------------------------------------------------------
# checkout.session.completed (1)
# ---------------------------------------------------------------------------


async def test_checkout_session_completed_inserts_topup_row_and_flips_tier_to_ultra(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """First successful pack purchase grants credit + flips tier to ultra (D-04 + D-26)."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(db_pool, tier="free")

    payload = _load_fixture("checkout_session_completed", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _read_user_tier(db_pool, user_id) == "ultra"
    assert await _read_balance(db_pool, user_id) == 2500
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 1
    # Tier-change audit row also landed (D-26).
    assert await _count_ledger_rows(db_pool, user_id, "tier_change") == 1


# ---------------------------------------------------------------------------
# customer.subscription.created (1)
# ---------------------------------------------------------------------------


async def test_subscription_created_flips_tier_to_pro(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """customer.subscription.created → tier='pro' + audit row."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="free", stripe_customer_id="cus_test_user_a",
    )

    payload = _load_fixture("customer_subscription_created", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _read_user_tier(db_pool, user_id) == "pro"
    assert await _count_ledger_rows(db_pool, user_id, "tier_change") == 1


# ---------------------------------------------------------------------------
# customer.subscription.updated (1)
# ---------------------------------------------------------------------------


async def test_subscription_updated_with_cancel_at_period_end_does_not_flip_tier(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """cancel_at_period_end=true is stored; tier stays 'pro' until deleted."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="pro", stripe_customer_id="cus_test_user_a",
    )

    payload = _load_fixture("customer_subscription_updated", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    # Tier UNCHANGED — D-04 says only deletion flips tier off.
    assert await _read_user_tier(db_pool, user_id) == "pro"
    # Subscription state columns reflect the update.
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_cancel_at_period_end, "
            "       subscription_current_period_end "
            "FROM users WHERE id = $1",
            user_id,
        )
    assert row["subscription_cancel_at_period_end"] is True
    assert row["subscription_current_period_end"] is not None


# ---------------------------------------------------------------------------
# customer.subscription.deleted (2)
# ---------------------------------------------------------------------------


async def test_subscription_deleted_flips_tier_to_free_and_pauses_4_oldest_agents(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """6 agents pre-state → 1 oldest stays running, next 4 auto_paused, 1 newest stays running.

    D-15: free tier cap = 1 agent; the migration extension lets the
    handler pause the 4 oldest non-paused, non-stopped agents OFFSET 1
    LIMIT 4 (keep-oldest semantics — the user's surviving agent is the
    one with the lowest created_at). Anything past the offset window
    stays running and is the user's responsibility to clean up.
    """
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="pro", stripe_customer_id="cus_test_user_a",
    )

    # Seed 6 running containers with monotonic created_at so the ASC
    # ordering is deterministic.
    base = datetime.now(timezone.utc) - timedelta(hours=6)
    container_ids: list[UUID] = []
    for i in range(6):
        cid = await _seed_agent_container(
            db_pool,
            user_id=user_id,
            container_status="running",
            created_at=base + timedelta(minutes=i),
        )
        container_ids.append(cid)

    payload = _load_fixture("customer_subscription_deleted", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _read_user_tier(db_pool, user_id) == "free"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, container_status FROM agent_containers "
            "WHERE user_id = $1 ORDER BY created_at ASC",
            user_id,
        )
    statuses = [r["container_status"] for r in rows]
    # First (oldest) stays running; next 4 auto_paused; last stays running
    # (only OFFSET 1 LIMIT 4 are paused).
    assert statuses[0] == "running", f"oldest should stay running: {statuses}"
    assert statuses[1:5] == ["auto_paused"] * 4, f"4 oldest after head: {statuses}"
    assert statuses[5] == "running", f"newest should stay running: {statuses}"


async def test_subscription_deleted_with_3_agents_pauses_only_2(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """3 agents pre-state → oldest 1 stays running, the next 2 auto_paused.

    The OFFSET 1 LIMIT 4 SQL handles short lists naturally — only 2 rows
    fall in the offset window when the list is 3 long. No IndexError, no
    over-pausing. This is the boundary case D-15 protects against.
    """
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="pro", stripe_customer_id="cus_test_user_a",
    )

    base = datetime.now(timezone.utc) - timedelta(hours=3)
    for i in range(3):
        await _seed_agent_container(
            db_pool,
            user_id=user_id,
            container_status="running",
            created_at=base + timedelta(minutes=i),
        )

    payload = _load_fixture("customer_subscription_deleted", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _read_user_tier(db_pool, user_id) == "free"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT container_status FROM agent_containers "
            "WHERE user_id = $1 ORDER BY created_at ASC",
            user_id,
        )
    statuses = [r["container_status"] for r in rows]
    assert statuses == ["running", "auto_paused", "auto_paused"], statuses


# ---------------------------------------------------------------------------
# charge.refunded (1)
# ---------------------------------------------------------------------------


async def test_charge_refunded_inserts_negative_ledger_row(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """charge.refunded → ledger row kind='refund', amount_cents = -2500."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="ultra", stripe_customer_id="cus_test_user_a",
    )
    # Seed a prior topup so the balance starts non-zero.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, 2500)",
            user_id,
        )
        await conn.execute(
            "INSERT INTO credit_transactions "
            "  (user_id, kind, amount_cents, reference_id, reference_type) "
            "VALUES ($1, 'topup', 2500, 'cs_seed_001', 'stripe_checkout_session')",
            user_id,
        )

    payload = _load_fixture("charge_refunded", str(user_id))
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    # One refund row landed.
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT amount_cents, reference_id, reference_type "
            "FROM credit_transactions WHERE user_id = $1 AND kind = 'refund'",
            user_id,
        )
    assert len(rows) == 1, rows
    assert rows[0]["amount_cents"] == -2500
    assert rows[0]["reference_type"] == "stripe_refund"
    # Balance recomputes to 0 (2500 topup - 2500 refund).
    assert await _read_balance(db_pool, user_id) == 0


# ---------------------------------------------------------------------------
# invoice.paid / invoice.payment_failed (2)
# ---------------------------------------------------------------------------


async def test_invoice_paid_is_ack_no_side_effect(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """invoice.paid lands the dedupe row but DOES NOT mutate ledger / tier."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="pro", stripe_customer_id="cus_test_user_a",
    )

    payload = _load_fixture("invoice_paid")
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    # Dedupe row landed.
    assert await _count_webhook_rows(
        db_pool, "evt_test_invoice_paid_001",
    ) == 1
    # Tier untouched, no ledger row.
    assert await _read_user_tier(db_pool, user_id) == "pro"
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 0
    assert await _count_ledger_rows(db_pool, user_id, "tier_change") == 0


async def test_invoice_payment_failed_is_ack_no_side_effect(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """invoice.payment_failed → ack only; Smart Retries handles the rest."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="pro", stripe_customer_id="cus_test_user_a",
    )

    payload = _load_fixture("invoice_payment_failed")
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _count_webhook_rows(
        db_pool, "evt_test_invoice_payment_failed_001",
    ) == 1
    assert await _read_user_tier(db_pool, user_id) == "pro"
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 0


# ---------------------------------------------------------------------------
# payment_intent.succeeded — AMD-05 (1)
# ---------------------------------------------------------------------------


async def test_payment_intent_succeeded_is_not_handled_returns_200_ack(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """AMD-05: payment_intent.succeeded is acked but NEVER triggers a side-effect.

    The handler explicitly does NOT branch on this event because the
    credit grant is wired to checkout.session.completed; subscribing to
    both would double-credit. We still register the dedupe row so a
    re-delivery doesn't loop.
    """
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)
    user_id = await _seed_user(
        db_pool, tier="free", stripe_customer_id="cus_test_user_a",
    )

    payload = _load_fixture("payment_intent_succeeded")
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    # No tier flip, no credit grant.
    assert await _read_user_tier(db_pool, user_id) == "free"
    assert await _count_ledger_rows(db_pool, user_id, "topup") == 0
    # Dedupe row landed (so retry is short-circuited).
    assert await _count_webhook_rows(
        db_pool, "evt_test_payment_intent_succeeded_001",
    ) == 1


# ---------------------------------------------------------------------------
# Unknown event type (1)
# ---------------------------------------------------------------------------


async def test_unknown_event_type_returns_200_ack(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """Unknown event types are acked + dedupe-rowed; future versions add
    branches without breaking compatibility."""
    _set_app_settings_webhook_secret(async_client, WEBHOOK_SECRET)

    payload = (
        b'{"id":"evt_test_unknown_001","object":"event","api_version":'
        b'"2025-03-31.basil","created":1746998400,"type":"customer.created",'
        b'"livemode":false,"data":{"object":{"id":"cus_test_unknown",'
        b'"object":"customer"}}}'
    )
    sig = sign_webhook_payload(payload, WEBHOOK_SECRET)
    r = await async_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    assert await _count_webhook_rows(db_pool, "evt_test_unknown_001") == 1
