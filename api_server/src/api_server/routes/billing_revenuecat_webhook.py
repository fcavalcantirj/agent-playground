"""POST /v1/billing/revenuecat/webhook — RevenueCat → AP IAP webhook.

Sibling to ``billing_webhook.py`` (Stripe). RevenueCat POSTs a JSON event
every time an iOS / Android user transitions through an In-App Purchase
state: initial purchase, renewal, cancellation, refund, etc. This route
verifies the shared-secret auth header, dedupes on the RC event id, and
dispatches to the existing ledger primitives.

Auth: ``Authorization: Bearer $AP_REVENUECAT_WEBHOOK_SECRET`` — RC's
documented scheme. The secret is shared between RC's dashboard and
``deploy/.env.prod``; a mismatch → 401 + log the prefix only.

Idempotency: ``revenuecat_webhook_events.rc_event_id UNIQUE`` (migration
020). The dedupe-row INSERT is the FIRST action inside the transaction;
if the side-effect raises, the savepoint rolls back the INSERT and RC's
retry sees a clean state. Same Pitfall-2 discipline as the Stripe webhook.

Event matrix (RC v1 webhook payload):

  INITIAL_PURCHASE        → pack: credit_user('topup'); sub: tier free→pro
  NON_RENEWING_PURCHASE   → pack: credit_user('topup') (consumable)
  RENEWAL                 → sub: tier free→pro (idempotent if already pro)
  CANCELLATION            → ack only — user marked cancel-at-period-end on RC's
                            side, the EXPIRATION event later flips tier
  EXPIRATION              → sub: tier pro→free
  REFUND                  → pack: credit_user('refund', -amount); sub: tier→free
  TRANSFER / PRODUCT_CHANGE → ack only (we don't handle plan switching yet)
  unknown event types     → ack only

The product_id → Pack mapping flows through ``get_pack_by_apple_product``
or ``get_pack_by_google_product`` in ``services/billing_packs.py``; the
``store`` field on the event tells us which side to look up. Unknown
product ids → warn + ack-only (better to drop one event than 5xx a retry
storm that's actually a recipe-config mismatch on our side).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope
from ..services.billing_packs import (
    get_pack_by_apple_product,
    get_pack_by_google_product,
)
from ..services.ledger import credit_user, record_tier_change


_log = logging.getLogger("api_server.billing_revenuecat_webhook")
router = APIRouter()


# Product id for the Pro monthly subscription is sourced from Settings —
# we recognize both Apple and Google variants via the same check at
# dispatch time. Looked up in the request scope (not import scope) so
# tests that override Settings don't need to re-import the module.


def _err(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse(
        make_error_envelope(code, msg), status_code=status,
    )


@router.post("/billing/revenuecat/webhook")
async def revenuecat_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Public route. Auth via RC-shared-secret Bearer header (NOT session)."""
    settings = request.app.state.settings
    secret = settings.revenuecat_webhook_secret
    if not secret:
        # The route exists but RC isn't configured yet. 400 + log so a
        # misconfigured webhook URL is loud.
        _log.warning("revenuecat_webhook.secret_unset — refusing request")
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "RevenueCat webhook secret not configured on this deploy",
        )
    expected = f"Bearer {secret}"
    if authorization != expected:
        # Log only the prefix — never log the full header (T-B-LK).
        _log.warning(
            "revenuecat_webhook.auth_failed prefix=%s",
            (authorization or "")[:20],
        )
        return _err(400, ErrorCode.UNAUTHORIZED, "bad webhook auth")

    try:
        payload_bytes = await request.body()
        body = await request.json()
    except Exception:
        _log.exception("revenuecat_webhook.body_parse_failed")
        return _err(400, ErrorCode.INVALID_REQUEST, "body must be JSON")

    event = body.get("event") if isinstance(body, dict) else None
    if not isinstance(event, dict):
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "payload missing top-level 'event' object",
        )
    event_id = event.get("id")
    event_type = event.get("type")
    app_user_id = event.get("app_user_id")
    if not (event_id and event_type and app_user_id):
        _log.warning(
            "revenuecat_webhook.missing_required_fields event_id=%s type=%s",
            event_id, event_type,
        )
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "event missing id / type / app_user_id",
        )

    pool = request.app.state.db
    duplicate = False
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Dedupe-row INSERT is the FIRST action in the tx (Pitfall 2).
                inserted = await conn.fetchval(
                    """
                    INSERT INTO revenuecat_webhook_events
                      (rc_event_id, event_type, payload)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (rc_event_id) DO NOTHING
                    RETURNING rc_event_id
                    """,
                    event_id, event_type, payload_bytes.decode(),
                )
                if inserted is None:
                    duplicate = True
                else:
                    await _dispatch_event(conn, settings, event)
    except Exception:
        # Side-effect raised. Tx rolled back; dedupe row never committed;
        # RC's retry will hit a clean state.
        _log.exception(
            "revenuecat_webhook.side_effect_failed event_id=%s type=%s",
            event_id, event_type,
        )
        return _err(
            500, ErrorCode.INTERNAL,
            "webhook side-effect failed; rolled back for retry",
        )

    if duplicate:
        _log.info(
            "revenuecat_webhook.duplicate_event id=%s type=%s",
            event_id, event_type,
        )
    return JSONResponse({"received": True}, status_code=200)


async def _dispatch_event(conn, settings, event: dict) -> None:
    """Dispatch by event.type to the right handler. Caller owns the tx."""
    event_type = event.get("type")
    if event_type in ("INITIAL_PURCHASE", "NON_RENEWING_PURCHASE", "RENEWAL"):
        await _handle_purchase_or_renewal(conn, settings, event)
    elif event_type in ("CANCELLATION",):
        # No-op: user clicked cancel but is still entitled until period
        # end. EXPIRATION fires when the entitlement actually ends.
        _log.info(
            "revenuecat_webhook.cancellation_ack event_id=%s",
            event.get("id"),
        )
    elif event_type == "EXPIRATION":
        await _handle_subscription_expiration(conn, event)
    elif event_type == "REFUND":
        await _handle_refund(conn, settings, event)
    else:
        # Unknown / out-of-scope event (TRANSFER, PRODUCT_CHANGE,
        # SUBSCRIBER_ALIAS, etc.). Ack-only — RC sends a long-tail of
        # event types we don't act on in v1.
        _log.info(
            "revenuecat_webhook.event_ack_only event_id=%s type=%s",
            event.get("id"), event_type,
        )


def _resolve_pack(settings, event: dict):
    """Return (Pack | None) for the product_id in this event."""
    product_id = event.get("product_id")
    store = (event.get("store") or "").upper()
    if not product_id:
        return None
    if store == "APP_STORE":
        return get_pack_by_apple_product(product_id)
    if store == "PLAY_STORE":
        return get_pack_by_google_product(product_id)
    # Fall back: try both — RC sometimes omits `store` on test events.
    return (
        get_pack_by_apple_product(product_id)
        or get_pack_by_google_product(product_id)
    )


def _is_pro_subscription(settings, event: dict) -> bool:
    """True if this event is for the Pro monthly subscription product."""
    product_id = event.get("product_id")
    if not product_id:
        return False
    apple_pro = getattr(settings, "apple_product_id_pro_monthly", "") or ""
    google_pro = getattr(settings, "google_product_id_pro_monthly", "") or ""
    return product_id in (apple_pro, google_pro)


async def _handle_purchase_or_renewal(conn, settings, event: dict) -> None:
    """INITIAL_PURCHASE / NON_RENEWING_PURCHASE / RENEWAL.

    Pack product → credit the ledger ('topup').
    Pro subscription product → tier free→pro (idempotent if already pro).
    Anything else → warn + skip (likely a stale RC config or a product we
    haven't catalogued yet; better to drop the side-effect than 5xx
    retry-storm).
    """
    event_id = event.get("id")
    app_user_id = event.get("app_user_id")
    transaction_id = event.get("transaction_id")
    try:
        user_id = UUID(app_user_id)
    except (ValueError, TypeError):
        _log.warning(
            "revenuecat_webhook.bad_app_user_id event_id=%s app_user_id=%r",
            event_id, app_user_id,
        )
        return

    if _is_pro_subscription(settings, event):
        current_tier = await conn.fetchval(
            "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
        )
        if current_tier is None:
            _log.warning(
                "revenuecat_webhook.user_not_found event_id=%s user_id=%s",
                event_id, user_id,
            )
            return
        if current_tier != "pro":
            await conn.execute(
                "UPDATE users SET tier = 'pro' WHERE id = $1", user_id,
            )
            await record_tier_change(
                conn,
                user_id=user_id,
                from_tier=current_tier,
                to_tier="pro",
                revenuecat_event_id=event_id,
            )
        return

    pack = _resolve_pack(settings, event)
    if pack is None:
        _log.warning(
            "revenuecat_webhook.unknown_product event_id=%s product_id=%r store=%r",
            event_id, event.get("product_id"), event.get("store"),
        )
        return
    if not transaction_id:
        _log.warning(
            "revenuecat_webhook.missing_transaction_id event_id=%s",
            event_id,
        )
        return
    await credit_user(
        conn,
        user_id=user_id,
        kind="topup",
        amount_cents=pack.credit_cents,
        reference_id=transaction_id,
        reference_type="revenuecat_transaction",
    )


async def _handle_subscription_expiration(conn, event: dict) -> None:
    """EXPIRATION → tier pro→free. Symmetric with Stripe's subscription.deleted."""
    event_id = event.get("id")
    app_user_id = event.get("app_user_id")
    try:
        user_id = UUID(app_user_id)
    except (ValueError, TypeError):
        return
    current_tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
    )
    if current_tier in (None, "free"):
        return  # already free — idempotent retry
    await conn.execute(
        "UPDATE users SET tier = 'free' WHERE id = $1", user_id,
    )
    await record_tier_change(
        conn,
        user_id=user_id,
        from_tier=current_tier,
        to_tier="free",
        revenuecat_event_id=event_id,
    )
    # NOTE: D-15 auto-pause on Pro→Free isn't replicated here yet — see
    # billing_webhook.py::_handle_subscription_deleted for the canonical
    # implementation. When the first IAP Pro user actually expires we'll
    # port that block. Until then: free tier cap enforcement at
    # services/tier_enforcement.py blocks new agent starts but the
    # existing fleet keeps running.


async def _handle_refund(conn, settings, event: dict) -> None:
    """REFUND → pack: credit_user(kind='refund', -amount). Sub: tier→free.

    For Pro sub refunds, we also flip tier free since the user is no
    longer paid up. EXPIRATION may or may not fire depending on the
    store / refund timing, so handle the tier here defensively (the
    tier UPDATE is idempotent via SELECT-FOR-UPDATE).
    """
    event_id = event.get("id")
    app_user_id = event.get("app_user_id")
    transaction_id = event.get("transaction_id")
    try:
        user_id = UUID(app_user_id)
    except (ValueError, TypeError):
        return

    if _is_pro_subscription(settings, event):
        current_tier = await conn.fetchval(
            "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
        )
        if current_tier in (None, "free"):
            return
        await conn.execute(
            "UPDATE users SET tier = 'free' WHERE id = $1", user_id,
        )
        await record_tier_change(
            conn,
            user_id=user_id,
            from_tier=current_tier,
            to_tier="free",
            revenuecat_event_id=event_id,
        )
        return

    pack = _resolve_pack(settings, event)
    if pack is None or not transaction_id:
        return
    # Refund: insert a kind='refund' row with the NEGATIVE amount —
    # mirrors the Stripe path (services/billing_webhook.py::_handle_charge_refunded).
    # The reference_id is the original transaction_id + '_refund' so the
    # original topup row and the refund row don't collide on UNIQUE.
    await credit_user(
        conn,
        user_id=user_id,
        kind="refund",
        amount_cents=-pack.credit_cents,
        reference_id=f"{transaction_id}_refund",
        reference_type="revenuecat_transaction",
    )
