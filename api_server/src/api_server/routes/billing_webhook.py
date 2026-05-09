"""Phase B Plan B-stripe-06 — POST /v1/billing/webhook (Stripe → AP).

The single most load-bearing surface in Phase B. Stripe → AP webhook
delivery + idempotency + tier mutation. **Sole writer of ``users.tier``**
(D-04). Same transaction wraps idempotency-row + side-effect (Pitfall 2).
7-event matrix per D-14-as-amended (AMD-05 drops ``payment_intent.succeeded``).

Auth: Stripe-Signature HMAC verified by ``stripe.StripeClient.construct_event``
(AMD-04). The route is publicly routable; the rate-limit middleware
EXCLUDES this path (``_BILLING_WEBHOOK_PATH``) so Stripe is never
throttled (T-B-DOS accept).

Idempotency: ``stripe_webhook_events.stripe_event_id UNIQUE`` (D-22 +
spike A). The dedupe-row INSERT is the FIRST action inside the
transaction; if the side-effect raises, the savepoint rolls back the
INSERT and Stripe's retry sees a clean state.

Event matrix (D-14 / AMD-05):

  checkout.session.completed       → ledger 'topup' + tier flip free→ultra
  customer.subscription.created    → tier='pro' + audit row
  customer.subscription.updated    → store cancel_at_period_end + period_end;
                                     tier UNCHANGED (D-04)
  customer.subscription.deleted    → tier='free' + auto-pause 4 oldest
                                     non-paused agents (D-15)
  charge.refunded                  → ledger 'refund' negative row (D-16)
  invoice.paid                     → ack only
  invoice.payment_failed           → ack only (Stripe Smart Retries)
  payment_intent.succeeded         → AMD-05 — ack only, NO side-effect
                                     (would double-credit alongside
                                     checkout.session.completed)
  unknown event types              → ack only

T-B-LK mitigation: only the first 20 chars of the signature header are
logged on failure; the payload body is never logged.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import stripe
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope
from ..services.ledger import credit_user, record_tier_change


_log = logging.getLogger("api_server.billing_webhook")
router = APIRouter()


def _err(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse(
        make_error_envelope(code, msg), status_code=status,
    )


# ---------------------------------------------------------------------------
# Helpers — best-effort attribute/dict access on StripeObject
# ---------------------------------------------------------------------------
#
# stripe-python v15 returns ``StripeObject`` instances from ``construct_event``
# which support BOTH attribute access (``obj.metadata.pack_id``) and dict
# access (``obj["metadata"]["pack_id"]``). The dict access is more
# defensive for fields that may legitimately be missing on some event
# variants — ``.get`` returns None instead of raising AttributeError.
# Every handler below uses dict access for required fields and treats
# absent keys as "warn + skip side-effect".


def _as_dict(obj) -> dict:
    """Return a fully-converted plain dict view of a StripeObject / dict.

    ``StripeObject.to_dict()`` recursively converts nested StripeObjects
    to dicts (verified against stripe-python v15). The fallback paths
    cover synthetic test inputs that pass plain dicts directly.

    Critical: do NOT rely on ``.get()`` against a raw StripeObject —
    StripeObject overrides ``__getattr__`` for sub-resource access and
    raises ``AttributeError`` on ``.get``. Always pass through ``_as_dict``
    so handler code can use the standard dict ``.get`` idiom.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    # Synthetic fallback — last-resort dict() for Mapping-like inputs.
    try:
        return dict(obj)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Route — POST /v1/billing/webhook
# ---------------------------------------------------------------------------


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    """Public route. Auth via Stripe-Signature HMAC, NOT session cookie.

    Sole writer of ``users.tier`` (D-04). 7-event matrix per D-14 / AMD-05.
    Same-transaction wraps idempotency-row INSERT + side-effect (Pitfall 2).
    """
    # MUST be raw bytes — never await request.json() first (Pitfall 1).
    payload = await request.body()
    if not stripe_signature:
        return _err(
            400, ErrorCode.STRIPE_WEBHOOK_INVALID, "missing signature",
        )

    settings = request.app.state.settings
    client: stripe.StripeClient = request.app.state.stripe_client

    try:
        event = client.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        # Log only the prefix — never log the full sig (T-B-LK).
        _log.warning(
            "billing_webhook.signature_failed sig_prefix=%s",
            (stripe_signature or "")[:20],
        )
        return _err(
            400, ErrorCode.STRIPE_WEBHOOK_INVALID, "bad signature",
        )
    except Exception:
        _log.exception("billing_webhook.construct_event_unexpected_error")
        return _err(
            400, ErrorCode.STRIPE_WEBHOOK_INVALID, "could not parse event",
        )

    pool = request.app.state.db
    duplicate = False
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # The dedupe-row INSERT is the FIRST action in the tx so
                # a side-effect failure rolls it back (Pitfall 2).
                # RETURNING NULL on conflict + DO NOTHING short-circuits
                # the rest of the handler.
                inserted = await conn.fetchval(
                    """
                    INSERT INTO stripe_webhook_events
                      (stripe_event_id, event_type, payload)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (stripe_event_id) DO NOTHING
                    RETURNING stripe_event_id
                    """,
                    event.id, event.type, payload.decode(),
                )
                if inserted is None:
                    duplicate = True
                else:
                    # Branch on event type. Side-effect runs in SAME
                    # transaction (Pitfall 2 — keeps the dedupe row +
                    # side-effect atomic). On exception, conn.transaction
                    # rolls back and the dedupe row never commits, so
                    # Stripe's retry sees a clean state.
                    await _dispatch_event(conn, event)
    except stripe.SignatureVerificationError:
        # Defense in depth — should already be handled above.
        return _err(
            400, ErrorCode.STRIPE_WEBHOOK_INVALID, "bad signature",
        )
    except Exception:
        # Side-effect raised. The transaction is already rolled back by
        # the conn.transaction() context manager unwinding; the dedupe
        # row was NOT committed. We return 5xx so Stripe retries (the
        # retry will hit a clean state — no idempotency row in the way).
        _log.exception(
            "billing_webhook.side_effect_failed event_id=%s type=%s",
            event.id, event.type,
        )
        return _err(
            500, ErrorCode.INTERNAL,
            "webhook side-effect failed; rolled back for retry",
        )

    if duplicate:
        _log.info(
            "billing_webhook.duplicate_event id=%s type=%s",
            event.id, event.type,
        )
    return JSONResponse({"received": True}, status_code=200)


async def _dispatch_event(conn, event) -> None:
    """Dispatch by ``event.type`` to the right handler. Caller owns the tx."""
    event_type = event.type
    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(conn, event)
    elif event_type == "customer.subscription.created":
        await _handle_subscription_created(conn, event)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(conn, event)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(conn, event)
    elif event_type == "charge.refunded":
        await _handle_charge_refunded(conn, event)
    elif event_type == "invoice.paid":
        # ack-only; subscription renewals don't grant credit.
        _log.info(
            "billing_webhook.invoice_paid_ack id=%s", event.id,
        )
    elif event_type == "invoice.payment_failed":
        # ack-only; Stripe Smart Retries handles the dunning loop.
        _log.info(
            "billing_webhook.invoice_payment_failed_ack id=%s",
            event.id,
        )
    elif event_type == "payment_intent.succeeded":
        # AMD-05: redundant with checkout.session.completed; ack only.
        # Subscribing to BOTH would double-credit pack purchases (paid
        # via Checkout → also fires PaymentIntent).
        _log.info(
            "billing_webhook.payment_intent_ack_no_side_effect id=%s",
            event.id,
        )
    else:
        _log.info(
            "billing_webhook.unknown_event_ack id=%s type=%s",
            event.id, event_type,
        )


# ---------------------------------------------------------------------------
# Event handlers — each runs inside the caller's transaction
# ---------------------------------------------------------------------------


async def _user_id_for_customer(
    conn, customer_id: str | None,
) -> UUID | None:
    """Resolve users.id by stripe_customer_id; return None if not found."""
    if not customer_id:
        return None
    return await conn.fetchval(
        "SELECT id FROM users WHERE stripe_customer_id = $1",
        customer_id,
    )


async def _handle_checkout_completed(conn, event) -> None:
    """checkout.session.completed → grant credits + tier free→ultra (first time)."""
    obj = _as_dict(event.data.object)
    metadata = obj.get("metadata") or {}
    ap_user_id = metadata.get("ap_user_id")
    pack_id = metadata.get("pack_id")
    credit_cents_str = metadata.get("credit_cents")
    if not (ap_user_id and pack_id and credit_cents_str):
        _log.warning(
            "billing_webhook.checkout_missing_metadata event_id=%s",
            event.id,
        )
        return
    try:
        user_id = UUID(ap_user_id)
        credit_cents = int(credit_cents_str)
    except (ValueError, TypeError):
        _log.warning(
            "billing_webhook.checkout_bad_metadata event_id=%s "
            "ap_user_id=%r credit_cents=%r",
            event.id, ap_user_id, credit_cents_str,
        )
        return

    # 1. Credit the ledger (idempotent on (reference_id, reference_type)
    #    where reference_id = checkout session id).
    session_id = obj.get("id")
    await credit_user(
        conn,
        user_id=user_id,
        kind="topup",
        amount_cents=credit_cents,
        reference_id=session_id,
        reference_type="stripe_checkout_session",
    )

    # 2. Tier flip free→ultra (D-04 + D-26). Idempotent: on retry the
    #    SELECT-FOR-UPDATE returns 'ultra' and the IF gate skips the
    #    UPDATE; ``record_tier_change`` is idempotent on stripe_event_id.
    current_tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
    )
    if current_tier == "free":
        await conn.execute(
            "UPDATE users SET tier = 'ultra' WHERE id = $1", user_id,
        )
        await record_tier_change(
            conn,
            user_id=user_id,
            from_tier=current_tier,
            to_tier="ultra",
            stripe_event_id=event.id,
        )


async def _handle_subscription_created(conn, event) -> None:
    """customer.subscription.created → tier='pro' for the user (D-02)."""
    obj = _as_dict(event.data.object)
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        _log.warning(
            "billing_webhook.sub_created_user_not_found customer=%s",
            customer_id,
        )
        return
    current_tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
    )
    if current_tier != "pro":
        await conn.execute(
            "UPDATE users SET tier = 'pro' WHERE id = $1", user_id,
        )
        await record_tier_change(
            conn,
            user_id=user_id,
            from_tier=current_tier,
            to_tier="pro",
            stripe_event_id=event.id,
        )


async def _handle_subscription_updated(conn, event) -> None:
    """customer.subscription.updated → store cancel_at_period_end + period_end.

    Tier is NOT touched here — D-04 says only deletion flips tier to
    'free'. Until that fires the user keeps Pro access through the paid
    period; the UI surfaces "Cancels on <date>" using the cached
    subscription_current_period_end column.
    """
    obj = _as_dict(event.data.object)
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    period_end_unix = obj.get("current_period_end")
    period_end: datetime | None = None
    if period_end_unix is not None:
        try:
            period_end = datetime.fromtimestamp(
                int(period_end_unix), tz=timezone.utc,
            )
        except (ValueError, TypeError, OSError):
            period_end = None
    await conn.execute(
        "UPDATE users SET subscription_cancel_at_period_end = $1, "
        "                 subscription_current_period_end = $2 "
        "WHERE id = $3",
        cancel_at_period_end, period_end, user_id,
    )


async def _handle_subscription_deleted(conn, event) -> None:
    """customer.subscription.deleted → tier='free' + auto-pause D-15.

    Free tier cap = 1 agent. The user keeps the absolute-oldest agent as
    their surviving free-tier slot; the next 4 oldest non-paused
    non-stopped agents flip to 'auto_paused'. Anything past the
    OFFSET 1 LIMIT 4 window stays running and is the user's
    responsibility to clean up via the regular agents API.
    """
    obj = _as_dict(event.data.object)
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    current_tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
    )
    if current_tier == "free":
        return  # already free — idempotent retry
    await conn.execute(
        "UPDATE users SET tier = 'free' WHERE id = $1", user_id,
    )
    await record_tier_change(
        conn,
        user_id=user_id,
        from_tier=current_tier,
        to_tier="free",
        stripe_event_id=event.id,
    )
    # Auto-pause the 4 oldest non-paused, non-stopped agents per D-15.
    # The OFFSET 1 keeps the absolute-oldest agent as the surviving
    # free-tier agent (cap=1). LIMIT 4 caps the pause radius — anything
    # past index 4 stays running. The IN (SELECT ... ORDER BY OFFSET LIMIT)
    # shape works on Postgres because each subquery row produces a
    # distinct id.
    await conn.execute(
        """
        UPDATE agent_containers
           SET container_status = 'auto_paused'
         WHERE id IN (
           SELECT id FROM agent_containers
            WHERE user_id = $1
              AND container_status NOT IN ('stopped', 'crashed',
                                            'start_failed', 'auto_paused')
            ORDER BY created_at ASC
            OFFSET 1 LIMIT 4
         )
        """,
        user_id,
    )


async def _handle_charge_refunded(conn, event) -> None:
    """charge.refunded → ledger row kind='refund', amount = -delta (D-16).

    Stripe sends the cumulative refunded amount on every charge.refunded
    event; partial refunds emit multiple events. We compute the DELTA
    against any prior 'refund' rows for the same charge so a 2nd partial
    refund posts only its own delta. The reference_id key carries the
    event id alongside the charge id so the UNIQUE(reference_id,
    reference_type) idempotency rail does NOT collapse distinct partial
    refunds for the same charge into one row.
    """
    obj = _as_dict(event.data.object)
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    amount_refunded = int(obj.get("amount_refunded") or 0)
    if amount_refunded <= 0:
        return
    charge_id = obj.get("id")
    # Sum prior refund rows for this charge — note the SUM is over
    # negative cents, so we negate to get the prior cumulative refund.
    prior_refunded_neg = await conn.fetchval(
        "SELECT COALESCE(SUM(amount_cents), 0)::BIGINT "
        "FROM credit_transactions "
        "WHERE user_id = $1 AND kind = 'refund' AND reference_id LIKE $2",
        user_id, f"{charge_id}:%",
    )
    prior_refunded = -int(prior_refunded_neg or 0)
    delta = amount_refunded - prior_refunded
    if delta <= 0:
        return
    await credit_user(
        conn,
        user_id=user_id,
        kind="refund",
        amount_cents=-delta,
        reference_id=f"{charge_id}:{event.id}",
        reference_type="stripe_refund",
    )


__all__ = ["router"]
