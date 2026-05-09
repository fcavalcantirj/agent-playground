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
from pydantic import BaseModel

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..services.billing_packs import PACKS


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


__all__ = ["router"]
