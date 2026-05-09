"""Phase B Plan B-stripe-03 — read-side billing routes.

Three GET endpoints, all auth-gated, no Stripe outbound:

  GET /v1/billing/packs
    Single SOT for the 5-pack credit catalog (D-06). Mobile + web
    fetch via this route — clients NEVER mirror the catalog locally
    (per ``feedback_dumb_client_no_mocks.md`` + golden rule #2).

  GET /v1/billing/balance
    Tier + raw balance + display projection. Polled by mobile after
    Stripe Checkout return (D-21) until the webhook-driven top-up
    surfaces. Pitfall 6: ``display_balance_cents`` clamps the negative
    refund-driven case to 0 while ``is_negative`` flags the underlying
    ledger truth — the UI renders "$0 ⚠" until admin write-off.

  GET /v1/billing/transactions
    Paginated ledger history for the calling user. Cursor:
    ``created_at DESC, id DESC`` (id is the secondary key — same-second
    rows preserve a stable order). Page params: ``limit ∈ [1, 200]``
    (FastAPI Query rejects out-of-range with 422); ``before=<datetime>``
    is the cursor for next-page fetches; ``next_before`` is the cursor
    to feed back to the route. ``next_before=None`` signals last page.

Mirrors ``routes/usage.py`` shape verbatim — Pydantic response_model +
``require_user`` early-return + asyncpg pool from ``request.app.state.db``
+ ``_err`` helper. Pure DB reads + static catalog projection; no Stripe
SDK calls land here (those live in Wave 3 webhook + Wave 2 Checkout
routes).

Cross-tenant defense (T-B-XT): every SQL read carries
``WHERE user_id = $1`` from the ``request.state.user_id`` UUID resolved
by ``require_user``; the route never accepts a ``user_id`` from request
body or query string. T-B-PRC defense: ``stripe_price_id`` lives only on
the internal ``Pack`` dataclass — ``PackEntry`` (the response shape)
intentionally omits it.
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..services.billing_packs import PACKS, get_pack
from ..services.stripe_client import (
    create_pack_checkout_session,
    create_subscription_checkout_session,
)


_log = logging.getLogger("api_server.billing")
router = APIRouter()


def _err(status: int, code: str, msg: str) -> JSONResponse:
    """Mirror routes/usage.py::_err — single source of truth for the envelope."""
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, msg),
    )


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class PackEntry(BaseModel):
    """One row in /v1/billing/packs — internal stripe_price_id is OMITTED.

    T-B-PRC mitigation: the Stripe Price object id is operational metadata
    used only by Wave 2's Checkout creation route. Mobile + web don't
    need it (they call POST /v1/billing/checkout/pack with the pack id).
    """

    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int


class PackCatalogResponse(BaseModel):
    packs: list[PackEntry]


class BalanceResponse(BaseModel):
    """Body for /v1/billing/balance — tier + raw + display projections."""

    tier: str
    balance_cents: int
    display_balance_cents: int
    is_negative: bool


class TransactionEntry(BaseModel):
    """One row in /v1/billing/transactions.

    ``id`` is rendered as a string (UUID JSON contract, mirrors
    ``routes/usage.py::AgentBreakdownEntry.agent_id`` — UUID->str so
    mobile/web parsers stay language-agnostic).
    """

    id: str
    kind: str
    amount_cents: int
    reference_id: str | None
    reference_type: str | None
    created_at: datetime


class TransactionsResponse(BaseModel):
    transactions: list[TransactionEntry]
    # Cursor for the NEXT page; None when this is the final page.
    next_before: datetime | None = None


# ---------------------------------------------------------------------------
# GET /v1/billing/packs — D-06 single SOT projection
# ---------------------------------------------------------------------------


@router.get("/billing/packs", response_model=PackCatalogResponse)
async def list_packs(request: Request):
    """Return the 5-pack credit catalog. Auth-required."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    # user_id intentionally unused — packs are a static catalog, but the
    # auth gate stays on so anonymous browsers can't enumerate the
    # Stripe surface (and so the rate-limit "billing" bucket has a
    # stable per-user subject).
    return PackCatalogResponse(
        packs=[
            PackEntry(
                id=p.id,
                label=p.label,
                usd_amount_cents=p.usd_amount_cents,
                credit_cents=p.credit_cents,
            )
            for p in PACKS
        ],
    )


# ---------------------------------------------------------------------------
# GET /v1/billing/balance — D-21 polled by mobile post-Checkout
# ---------------------------------------------------------------------------


@router.get("/billing/balance", response_model=BalanceResponse)
async def get_balance(request: Request):
    """Return user's tier + raw balance + display projection (Pitfall 6)."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.tier,
                COALESCE(b.balance_cents, 0)::BIGINT AS balance_cents
            FROM users u
            LEFT JOIN credit_balances b ON b.user_id = u.id
            WHERE u.id = $1
            """,
            user_id,
        )
    if row is None:
        # The session pointed to a user_id that no longer exists in the
        # users table (cascade-deleted while the session was live). 401
        # is the right shape — the session is no longer valid.
        return _err(401, ErrorCode.UNAUTHORIZED, "user not found")
    raw_balance = int(row["balance_cents"])
    return BalanceResponse(
        tier=row["tier"],
        balance_cents=raw_balance,
        display_balance_cents=max(raw_balance, 0),
        is_negative=raw_balance < 0,
    )


# ---------------------------------------------------------------------------
# GET /v1/billing/transactions — paginated ledger history
# ---------------------------------------------------------------------------


@router.get("/billing/transactions", response_model=TransactionsResponse)
async def list_transactions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None),
):
    """Return user's ledger rows, ordered by created_at DESC, paginated.

    The composite (created_at DESC, id DESC) order is stable across
    same-second inserts — concurrent debits at the same instant won't
    interleave the page boundary unpredictably.

    Cursor protocol:
      * First page — caller omits ``before``; receives ``next_before``
        (the oldest item's created_at) when a full ``limit`` rows came
        back; receives ``None`` otherwise.
      * Next page — caller passes ``before=<next_before>``; the SQL
        filter is strict (``< $2``) so the cursor item is NOT
        re-rendered on the next page.
    """
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        if before is None:
            rows = await conn.fetch(
                """
                SELECT id, kind, amount_cents,
                       reference_id, reference_type, created_at
                FROM credit_transactions
                WHERE user_id = $1
                ORDER BY created_at DESC, id DESC
                LIMIT $2
                """,
                user_id, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, kind, amount_cents,
                       reference_id, reference_type, created_at
                FROM credit_transactions
                WHERE user_id = $1 AND created_at < $2
                ORDER BY created_at DESC, id DESC
                LIMIT $3
                """,
                user_id, before, limit,
            )
    txs = [
        TransactionEntry(
            id=str(r["id"]),
            kind=r["kind"],
            amount_cents=int(r["amount_cents"]),
            reference_id=r["reference_id"],
            reference_type=r["reference_type"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    next_before = txs[-1].created_at if len(txs) == limit else None
    return TransactionsResponse(transactions=txs, next_before=next_before)


# ===========================================================================
# Phase B Plan B-stripe-05 — POST /v1/billing/checkout + /v1/billing/subscription
# ===========================================================================
#
# Outbound Stripe-Checkout endpoints. Mobile (Wave 5) POSTs ``{pack_id}`` to
# ``/v1/billing/checkout`` and ``{}`` to ``/v1/billing/subscription``, then
# opens the returned ``checkout_url`` inside ``flutter_inappwebview``. Both
# endpoints lazy-create the Stripe Customer the first time the user touches
# Stripe (D-11) — race-defended via ``SELECT ... FOR UPDATE`` inside the
# Wave 1 ``services/stripe_client.lazy_create_or_fetch_customer`` helper
# (spike_g_lazy_customer_create.py case (b) proved 1 customer per 2-way
# concurrent first-click).
#
# Both routes share these invariants:
#   * auth-gated via ``require_user`` (UNAUTHORIZED 401 envelope on miss)
#   * StripeClient instance read from ``request.app.state.stripe_client``
#     (AMD-04 — never the deprecated module-level static methods)
#   * Settings read from ``request.app.state.settings`` (subscription path
#     uses ``stripe_price_id_pro_monthly``)
#   * ``allow_promotion_codes=true`` on every Checkout session (D-24 —
#     marketing mints codes Stripe-side; AP carries no per-code state)
#   * ``automatic_tax: {enabled: true}`` (Stripe Tax handles VAT/sales-tax)
#   * Default success_url embeds the literal string ``{CHECKOUT_SESSION_ID}``
#     — Stripe substitutes the real session id at redirect time so the
#     mobile webview's nav delegate (D-21) can read it off the URL.
#
# Failure handling:
#   * Unknown pack_id → 400 INVALID_PACK_ID (T-B-PCK allow-list defense)
#   * Stripe SDK raises (network, auth, validation) → 502 INVALID_REQUEST
#     with a generic message; the underlying exception is logged via
#     ``_log.exception`` (sanitized through Phase 29 _redact_creds — T-B-LK
#     mitigation, no Stripe error details leak to the client).
#
# The webhook half of the contract lives in Wave 3 (Plan B-stripe-06) —
# this plan only covers the user-initiated POST half.


_DEFAULT_SUCCESS_URL = (
    "https://app.solvrlabs.com/billing/return-success"
    "?session_id={CHECKOUT_SESSION_ID}"
)
_DEFAULT_CANCEL_URL = "https://app.solvrlabs.com/billing/return-cancel"


class CheckoutRequest(BaseModel):
    """Body for POST /v1/billing/checkout.

    ``pack_id`` is the canonical id from ``services.billing_packs.PACKS``
    (e.g. ``pack_5``..``pack_100``); validated against the allow-list at
    request time. ``success_url`` / ``cancel_url`` are optional overrides
    — the defaults point at the canonical solvrlabs.com return-handshake
    URLs the mobile webview intercepts.
    """

    pack_id: str = Field(
        ..., description="One of pack_5/pack_10/pack_25/pack_50/pack_100",
    )
    success_url: str | None = Field(
        default=None,
        description="Override success URL (defaults to canonical handshake URL).",
    )
    cancel_url: str | None = Field(
        default=None,
        description="Override cancel URL (defaults to canonical handshake URL).",
    )


class CheckoutResponse(BaseModel):
    """Stripe-hosted Checkout URL — mobile loads this in InAppWebView."""

    checkout_url: str


class SubscriptionRequest(BaseModel):
    """Body for POST /v1/billing/subscription. Body is optional; both URL
    fields default to the canonical handshake URLs."""

    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_pack_checkout(request: Request, body: CheckoutRequest):
    """Create a Stripe Checkout session for one of the 5 credit packs (D-06).

    Returns ``{checkout_url}`` for the mobile webview. Lazy-creates the
    Stripe Customer if this is the user's first Stripe-affecting click;
    second sequential click reuses the persisted ``stripe_customer_id``.
    Concurrent first-clicks for the SAME user produce EXACTLY ONE Stripe
    Customer (Wave 1 spike-g proof; ``SELECT ... FOR UPDATE`` lock).
    """
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    # T-B-PCK: validate pack_id against the in-memory PACKS allow-list.
    if get_pack(body.pack_id) is None:
        return _err(
            400, ErrorCode.INVALID_PACK_ID,
            f"unknown pack_id: {body.pack_id}",
        )

    client = request.app.state.stripe_client
    pool = request.app.state.db
    success_url = body.success_url or _DEFAULT_SUCCESS_URL
    cancel_url = body.cancel_url or _DEFAULT_CANCEL_URL

    settings = request.app.state.settings
    try:
        async with pool.acquire() as conn:
            checkout_url = await create_pack_checkout_session(
                conn=conn,
                user_id=user_id,
                pack_id=body.pack_id,
                success_url=success_url,
                cancel_url=cancel_url,
                client=client,
                settings=settings,
            )
    except Exception:
        # T-B-LK: log full exception (sanitized) but return generic
        # 502 — never leak Stripe error details to the mobile client.
        _log.exception(
            "billing.checkout.create_failed user_id=%s pack_id=%s",
            user_id, body.pack_id,
        )
        return _err(
            502, ErrorCode.INVALID_REQUEST,
            "failed to create checkout session",
        )
    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/billing/subscription", response_model=CheckoutResponse)
async def create_subscription(request: Request, body: SubscriptionRequest):
    """Create a Stripe Checkout session for the Pro monthly subscription (D-02).

    The Pro tier price id lives in Settings (``stripe_price_id_pro_monthly``);
    the actual Pro tier flip happens in Wave 3's webhook handler when
    ``customer.subscription.created`` lands (D-04 sole-writer rule).
    """
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    settings = request.app.state.settings
    client = request.app.state.stripe_client
    pool = request.app.state.db
    success_url = body.success_url or _DEFAULT_SUCCESS_URL
    cancel_url = body.cancel_url or _DEFAULT_CANCEL_URL

    try:
        async with pool.acquire() as conn:
            checkout_url = await create_subscription_checkout_session(
                conn=conn,
                user_id=user_id,
                success_url=success_url,
                cancel_url=cancel_url,
                client=client,
                settings=settings,
            )
    except Exception:
        _log.exception(
            "billing.subscription.create_failed user_id=%s", user_id,
        )
        return _err(
            502, ErrorCode.INVALID_REQUEST,
            "failed to create subscription session",
        )
    return CheckoutResponse(checkout_url=checkout_url)


__all__ = ["router"]
