"""Phase B Plan B-stripe-02 — StripeClient lifespan service + Checkout helpers.

Per AMD-04: Phase B uses the v15.x **StripeClient** service pattern, NOT
the legacy module-level static methods (``stripe.api_key = ...``). The
client is constructed once per process by ``main.py`` lifespan and
stashed on ``app.state.stripe_client`` (mirrors the
``proxy_byok_cache`` / ``proxy_ip_map`` lifespan-owned-resource
discipline).

Three async helpers in this module:

  * ``build_stripe_client(settings)`` — factory called from the lifespan.
    Calls ``validate_stripe_config(settings)`` so prod fails loud at boot
    rather than at first Stripe-affecting request.
  * ``lazy_create_or_fetch_customer`` — D-11. ``SELECT FOR UPDATE`` on
    the user row serializes concurrent first-clicks (Wave 0 spike-g
    proved this race; without the row lock, two clicks would create two
    Stripe Customers).
  * ``create_pack_checkout_session`` — D-06 + D-24 (allow_promotion_codes).
    Returns the Stripe-hosted Checkout URL.
  * ``create_subscription_checkout_session`` — D-02 / D-04 Pro tier
    monthly subscription.

T-B-LK mitigation (BYOK key never logged): the lifespan logs only
``api_key_prefix=settings.stripe_api_key[:7]`` (e.g. ``sk_test_``);
never the full key. The full key never enters a log record from this
module.
"""
from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
import stripe

from ..config import Settings, validate_stripe_config
from .billing_packs import get_pack

_log = logging.getLogger("api_server.stripe_client")


def build_stripe_client(settings: Settings) -> stripe.StripeClient:
    """Construct a process-wide StripeClient. Called once from lifespan.

    Calls ``validate_stripe_config(settings)`` so prod fails loud at
    boot if any AP_STRIPE_* env var is missing. In dev the placeholder
    values fill in via ``Settings._substitute_stripe_dev_placeholders``;
    the resulting client can be constructed but its outbound calls will
    fail with Stripe auth errors (intentional — dev should target
    Stripe TEST keys via ``deploy/.env.prod``).

    The returned client is thread-safe; one instance per process is
    sufficient for all Phase B Stripe traffic.
    """
    validate_stripe_config(settings)
    client = stripe.StripeClient(settings.stripe_api_key)
    return client


async def lazy_create_or_fetch_customer(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    client: stripe.StripeClient,
) -> str:
    """D-11: lazy Stripe Customer create on first Stripe-affecting click.

    Caller MUST be inside ``conn.transaction()``. The transaction shape:

        SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE
        if stripe_customer_id is NULL:
            customer = client.customers.create(...)
            UPDATE users SET stripe_customer_id = customer.id WHERE id = $1
        return stripe_customer_id

    The ``FOR UPDATE`` clause is the load-bearing one — Wave 0 spike-g
    proved that without it, two concurrent first-clicks both observe
    ``stripe_customer_id IS NULL`` at READ COMMITTED and both call
    ``client.customers.create``, producing two Stripe Customer records
    for one AP user.

    Customer metadata carries ``ap_user_id`` so Stripe-side ops can
    cross-reference back to the AP database.
    """
    row = await conn.fetchrow(
        "SELECT email, stripe_customer_id FROM users "
        "WHERE id = $1 FOR UPDATE",
        user_id,
    )
    if row is None:
        raise ValueError(f"user {user_id} not found")
    if row["stripe_customer_id"] is not None:
        return row["stripe_customer_id"]
    # Create a Customer; the AMD-04 service pattern uses
    # ``client.customers.create(params={...})`` (NOT the legacy module
    # form ``stripe.Customer.create(...)``).
    customer = client.customers.create(
        params={
            "email": row["email"] or "",
            "metadata": {"ap_user_id": str(user_id)},
        }
    )
    await conn.execute(
        "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
        customer.id, user_id,
    )
    return customer.id


async def create_pack_checkout_session(
    *,
    conn: asyncpg.Connection,
    user_id: UUID,
    pack_id: str,
    success_url: str,
    cancel_url: str,
    client: stripe.StripeClient,
) -> str:
    """Create a Stripe Checkout session for a one-time credit pack purchase.

    D-06 (catalog SOT) + D-24 (promo codes enabled) + AMD-05 (one-time
    mode). The session metadata carries ``pack_id`` and ``credit_cents``
    so the ``checkout.session.completed`` webhook handler (Wave 3) can
    grant the right amount of credit to the right user.

    ``automatic_tax`` is enabled — Stripe Tax handles VAT/sales-tax
    out-of-band per CONTEXT D-24 / Claude's Discretion section.

    The Customer is created lazily inside its OWN transaction so the
    Checkout session creation (HTTP call to Stripe) does not hold a
    Postgres lock for the duration. This is intentional: HTTP-call-while-
    holding-DB-lock is an anti-pattern (the lock blocks every other
    request for the user during a 500-1500ms upstream hop).

    Returns the Stripe-hosted Checkout URL (session.url).
    """
    pack = get_pack(pack_id)
    if pack is None:
        raise ValueError(f"unknown pack_id: {pack_id!r}")
    # First, materialize the Stripe Customer in its own DB transaction.
    # Caller may pass a fresh connection (no outer tx) — wrap our own.
    async with conn.transaction():
        customer_id = await lazy_create_or_fetch_customer(
            conn, user_id=user_id, client=client,
        )
    # The Stripe Checkout call is OUTSIDE any DB transaction.
    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "mode": "payment",
            "line_items": [
                {"price": pack.stripe_price_id, "quantity": 1},
            ],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,                      # D-24
            "metadata": {
                "ap_user_id": str(user_id),
                "pack_id": pack.id,
                "credit_cents": str(pack.credit_cents),
            },
            "automatic_tax": {"enabled": True},                 # Stripe Tax
        }
    )
    return session.url


async def create_subscription_checkout_session(
    *,
    conn: asyncpg.Connection,
    user_id: UUID,
    success_url: str,
    cancel_url: str,
    client: stripe.StripeClient,
    settings: Settings,
) -> str:
    """Create a Stripe Checkout session for the Pro tier monthly sub.

    D-02 / D-04: subscription mode; ``customer.subscription.{created,
    updated,deleted}`` webhook handlers (Wave 3) flip ``users.tier``.
    The Pro $/mo amount lives in Stripe-side config (Settings carries
    only the price id).

    Same lazy Customer pattern as ``create_pack_checkout_session``;
    same allow_promotion_codes + automatic_tax discipline.
    """
    async with conn.transaction():
        customer_id = await lazy_create_or_fetch_customer(
            conn, user_id=user_id, client=client,
        )
    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "mode": "subscription",
            "line_items": [
                {
                    "price": settings.stripe_price_id_pro_monthly,
                    "quantity": 1,
                },
            ],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,                      # D-24
            "metadata": {"ap_user_id": str(user_id)},
            "automatic_tax": {"enabled": True},
        }
    )
    return session.url
