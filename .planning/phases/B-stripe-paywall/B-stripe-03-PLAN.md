---
phase: B-stripe
plan: 03
type: execute
wave: 2
depends_on: [B-stripe-02]
files_modified:
  - api_server/src/api_server/routes/billing.py
  - api_server/src/api_server/main.py
  - api_server/src/api_server/middleware/rate_limit.py
  - api_server/src/api_server/models/errors.py
  - api_server/tests/routes/test_billing_read_routes.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-06 (GET /v1/billing/packs returns the single SOT)
  - D-21 (GET /v1/billing/balance polled by mobile post-Checkout)
  - BIL-05 (transaction history GET /v1/billing/transactions paginated)
  - BIL-06 (current balance + tier surface for dashboard)
must_haves:
  truths:
    - "GET /v1/billing/packs returns the 5 packs with correct pack ids and price metadata, auth-gated"
    - "GET /v1/billing/balance returns {tier, balance_cents, display_balance_cents, is_negative} for the calling user"
    - "GET /v1/billing/transactions returns the user's ledger rows ordered by created_at DESC, paginated by ?limit=N&before=<created_at>"
    - "All 3 routes are require_user-gated (no anonymous browsing) and return Stripe-shape error envelopes"
    - "Rate-limit middleware applies the new 'billing' bucket (30 calls / 60s per user) to /v1/billing/{packs,balance,transactions}"
    - "Rate-limit middleware does NOT apply the 'billing' bucket to /v1/billing/webhook (Wave 3 owns that path; Stripe must not be rate-limited)"
  artifacts:
    - path: "api_server/src/api_server/routes/billing.py"
      provides: "FastAPI router with packs/balance/transactions endpoints"
      exports: ["router"]
    - path: "api_server/src/api_server/middleware/rate_limit.py"
      provides: "Updated _LIMITS dict with 'billing' bucket and predicate excluding /v1/billing/webhook"
      contains: "_LIMITS[\"billing\"]"
  key_links:
    - from: "api_server/src/api_server/main.py"
      to: "api_server/src/api_server/routes/billing.py"
      via: "app.include_router(billing.router, prefix='/v1', tags=['billing'])"
      pattern: "billing\\.router"
    - from: "api_server/src/api_server/routes/billing.py"
      to: "api_server/src/api_server/services/billing_packs.py"
      via: "PACKS imported and projected into PackCatalogResponse"
      pattern: "from \\.\\.services\\.billing_packs import"
---

<objective>
Read-side billing routes (no Stripe API calls; pure DB reads + static catalog projection) plus the rate-limit middleware extension. This is the smallest meaningful surface mobile + web can consume from /v1/billing/*.

Purpose: Mobile (Wave 5) needs `/v1/billing/packs` to render the pack picker, `/v1/billing/balance` for the AppBar ticker tier projection, and `/v1/billing/transactions` for history. None of these touch Stripe outbound — pure DB reads.
Output: routes/billing.py with 3 GET endpoints, rate-limit extension, ErrorCode additions, integration tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/B-stripe-paywall/CONTEXT.md
@.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md
@.planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md
@.planning/phases/B-stripe-paywall/B-stripe-02-SUMMARY.md
@api_server/src/api_server/routes/usage.py
@api_server/src/api_server/middleware/rate_limit.py
@api_server/src/api_server/models/errors.py
@api_server/src/api_server/auth/deps.py

<interfaces>
From api_server/src/api_server/auth/deps.py:
```python
def require_user(request: Request) -> JSONResponse | UUID:
    # Returns JSONResponse(401) on missing/invalid session, else the UUID
```

From api_server/src/api_server/services/billing_packs.py (Wave 1):
```python
@dataclass(frozen=True)
class Pack:
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int
    stripe_price_id: str  # internal — DO NOT project externally

PACKS: tuple[Pack, ...]  # 5 packs
def get_pack(pack_id: str) -> Pack | None
```

From api_server/src/api_server/middleware/rate_limit.py (current shape):
```python
_LIMITS: dict[str, tuple[int, int]] = {  # bucket → (max, window_seconds)
    "auth": (5, 60),
    # ...others
}
def _bucket_for(scope) -> str | None: ...  # returns bucket key or None
```

From api_server/src/api_server/models/errors.py:
```python
class ErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    # add: INSUFFICIENT_BALANCE, TIER_LIMIT_EXCEEDED, INVALID_PACK_ID, STRIPE_WEBHOOK_INVALID
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: routes/billing.py read-only endpoints + ErrorCode additions</name>
  <files>api_server/src/api_server/routes/billing.py, api_server/src/api_server/models/errors.py, api_server/src/api_server/main.py, api_server/tests/routes/test_billing_read_routes.py</files>
  <read_first>
    - api_server/src/api_server/routes/usage.py (FULL — Pydantic response_model + require_user + asyncpg pool + _err helper)
    - api_server/src/api_server/services/billing_packs.py (PACKS frozen tuple)
    - api_server/src/api_server/main.py (`app.include_router` ordering)
    - api_server/src/api_server/models/errors.py (ErrorCode enum + make_error_envelope)
    - api_server/tests/routes/test_usage_endpoints.py (testcontainer + async_client + _seed_user pattern)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_packs_unauthenticated_returns_401
    - test_packs_authenticated_returns_5_packs_in_order
    - test_packs_response_omits_internal_stripe_price_id_field
    - test_balance_unauthenticated_returns_401
    - test_balance_no_balance_row_returns_zero_for_free_tier
    - test_balance_with_negative_balance_returns_is_negative_true_and_display_zero
    - test_balance_returns_user_tier_value
    - test_transactions_unauthenticated_returns_401
    - test_transactions_returns_user_rows_ordered_desc
    - test_transactions_pagination_limit_param_clamps_at_max
    - test_transactions_pagination_before_filter_works
    - test_transactions_filters_to_calling_user_only (cross-tenant defense)
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/models/errors.py` extension:** Add 4 new ErrorCode enum values:

```python
class ErrorCode(str, Enum):
    # ...existing values...
    INSUFFICIENT_BALANCE = "insufficient_balance"   # 402 — pre-flight gate or post-debit drain
    TIER_LIMIT_EXCEEDED = "tier_limit_exceeded"     # 403 — agent.create cap, retention filter
    INVALID_PACK_ID = "invalid_pack_id"             # 400 — client sent pack_id not in PACKS
    STRIPE_WEBHOOK_INVALID = "stripe_webhook_invalid"  # 400 — signature failure
```

**File 2 — `api_server/src/api_server/routes/billing.py`:** New file. Mirror `routes/usage.py` shape exactly.

```python
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..services.billing_packs import PACKS

_log = logging.getLogger("api_server.billing")
router = APIRouter()

def _err(status: int, code: ErrorCode, msg: str) -> JSONResponse:
    return JSONResponse(make_error_envelope(code, msg), status_code=status)


class PackEntry(BaseModel):
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int


class PackCatalogResponse(BaseModel):
    packs: list[PackEntry]


class BalanceResponse(BaseModel):
    tier: str
    balance_cents: int
    display_balance_cents: int
    is_negative: bool


class TransactionEntry(BaseModel):
    id: str
    kind: str
    amount_cents: int
    reference_id: Optional[str]
    reference_type: Optional[str]
    created_at: datetime


class TransactionsResponse(BaseModel):
    transactions: list[TransactionEntry]
    next_before: Optional[datetime] = None  # cursor for next page


@router.get("/billing/packs", response_model=PackCatalogResponse)
async def list_packs(request: Request):
    """Single SOT for the 5-pack catalog (D-06). Auth required."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
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


@router.get("/billing/balance", response_model=BalanceResponse)
async def get_balance(request: Request):
    """Return user's tier + raw balance + display projection (D-21 + Pitfall 6)."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.tier, COALESCE(b.balance_cents, 0)::BIGINT AS balance_cents
            FROM users u
            LEFT JOIN credit_balances b ON b.user_id = u.id
            WHERE u.id = $1
            """,
            user_id,
        )
    if row is None:
        return _err(404, ErrorCode.UNAUTHORIZED, "user not found")
    return BalanceResponse(
        tier=row["tier"],
        balance_cents=int(row["balance_cents"]),
        display_balance_cents=max(int(row["balance_cents"]), 0),
        is_negative=int(row["balance_cents"]) < 0,
    )


@router.get("/billing/transactions", response_model=TransactionsResponse)
async def list_transactions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[datetime] = Query(default=None),
):
    """Paginated ledger history for the calling user. Cursor: created_at DESC."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        if before is None:
            rows = await conn.fetch(
                """
                SELECT id, kind, amount_cents, reference_id, reference_type, created_at
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
                SELECT id, kind, amount_cents, reference_id, reference_type, created_at
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
```

**File 3 — `api_server/src/api_server/main.py`:** Register the billing router after the usage router. Locate the existing `app.include_router(usage_route.router, prefix="/v1", tags=["usage"])` line and add immediately after:

```python
from .routes import billing as billing_route  # type: ignore[import-not-found]
app.include_router(billing_route.router, prefix="/v1", tags=["billing"])
```

**File 4 — `api_server/tests/routes/test_billing_read_routes.py`:** Mirror `tests/routes/test_usage_endpoints.py`. Use the existing `async_client` + Postgres testcontainer fixtures. Seed users + balance rows + transaction rows directly via asyncpg. Cover the 12 behaviors listed in `<behavior>`. Use `pytest.mark.api_integration` per the existing convention.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/routes/test_billing_read_routes.py -x</automated>
  </verify>
  <done>
- 12 read-route tests green.
- `grep -c '@router.get(\"/billing/' api_server/src/api_server/routes/billing.py` outputs `3`.
- `grep -c 'INSUFFICIENT_BALANCE\|TIER_LIMIT_EXCEEDED\|INVALID_PACK_ID\|STRIPE_WEBHOOK_INVALID' api_server/src/api_server/models/errors.py` outputs `4`.
- `grep -c 'billing_route.router' api_server/src/api_server/main.py` outputs `1`.
- The `stripe_price_id` field of Pack is NOT projected into PackEntry response (security — the Stripe price IDs are internal and we don't need to leak them).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rate-limit middleware extension — billing bucket</name>
  <files>api_server/src/api_server/middleware/rate_limit.py, api_server/tests/middleware/test_rate_limit_billing.py</files>
  <read_first>
    - api_server/src/api_server/middleware/rate_limit.py (FULL — current `_LIMITS` + `_AUTH_ROUTE_KEYS` + `_bucket_for` discipline)
    - api_server/tests/middleware/ (look for existing rate-limit tests; mirror their fixture style)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (Shared Patterns → Rate limiting)
    - api_server/src/api_server/routes/billing.py (Task 1 — to confirm path prefixes)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_billing_packs_path_routes_to_billing_bucket
    - test_billing_balance_path_routes_to_billing_bucket
    - test_billing_transactions_path_routes_to_billing_bucket
    - test_billing_webhook_path_does_NOT_route_to_billing_bucket
    - test_billing_bucket_30_in_60s_then_429
    - test_billing_bucket_resets_after_window
  </behavior>
  <action>
**Modification — `api_server/src/api_server/middleware/rate_limit.py`:**

Locate the existing `_LIMITS` dict and add:

```python
_LIMITS["billing"] = (30, 60)   # 30 calls per 60s per (user, billing) — billing reads/writes EXCEPT webhook
```

Locate the existing `_bucket_for(scope)` function and add a branch that maps `/v1/billing/*` (excluding the webhook path) to the `billing` bucket. Mirror the existing `_AUTH_ROUTE_KEYS` style — use a stable predicate, not a string-prefix match alone:

```python
_BILLING_PATH_PREFIX = "/v1/billing/"
_BILLING_WEBHOOK_PATH = "/v1/billing/webhook"

def _bucket_for(scope) -> str | None:
    path = scope.get("path") or ""
    # ...existing branches first (auth bucket, etc.)...
    if path.startswith(_BILLING_PATH_PREFIX) and path != _BILLING_WEBHOOK_PATH:
        return "billing"
    # ...existing fall-through logic...
```

**Why webhook is excluded:** Stripe is the sole caller; rate-limiting Stripe causes its retry storm to escalate. Wave 3 will land the webhook route; it relies on Stripe-Signature HMAC + the `stripe_webhook_events.stripe_event_id` UNIQUE constraint as its abuse-prevention surface — NOT rate limiting.

**File — `api_server/tests/middleware/test_rate_limit_billing.py`:** Mirror existing rate-limit middleware tests. Key tests:
- Burst 31 calls in <60s to `/v1/billing/balance` → 31st returns 429.
- Wait the window → next call succeeds.
- 31 calls to `/v1/billing/webhook` → all 31 succeed (or fail on signature — never on rate limit).
- 31 calls to `/v1/usage/summary` → none routed to `billing` bucket; existing limits apply.

If the existing rate-limit middleware tests mock the clock via a `_now` injection helper, reuse that. Otherwise use `freezegun` (verify it's already in dev deps).
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/middleware/test_rate_limit_billing.py -x</automated>
  </verify>
  <done>
- 6 rate-limit tests green.
- `grep -c 'billing' api_server/src/api_server/middleware/rate_limit.py` ≥ 2 (one in _LIMITS, one in the path predicate).
- The webhook path is explicitly excluded — confirmed by a test that hits the route 31× and gets no 429.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile/web client → /v1/billing/{packs,balance,transactions} | session-cookie-authenticated; rate-limited per (user, "billing") bucket |
| Stripe API → /v1/billing/webhook | webhook authentication via Stripe-Signature HMAC (Wave 3 owns); MUST NOT be rate-limited |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-XT | InfoDisclosure | routes/billing.py::list_transactions + get_balance | mitigate | every SQL query carries WHERE user_id = $1 from request.state.user_id; never accept user_id from request body or query |
| T-B-PRC | InfoDisclosure | routes/billing.py::list_packs PackEntry response | mitigate | PackEntry intentionally omits stripe_price_id; only id/label/cents are projected |
| T-B-RL | DoS | middleware/rate_limit.py | mitigate | 30/60s billing bucket caps abusive polling; webhook path explicitly excluded so Stripe is not throttled |
| T-B-NEG | InfoDisclosure | routes/billing.py::get_balance | accept | negative balance is intentionally surfaced via display_balance_cents=0 + is_negative=true (Pitfall 6); user sees "$0 ⚠" until admin write-off |
</threat_model>

<verification>
- All 12 read-route tests pass.
- All 6 rate-limit tests pass.
- Webhook path confirmed excluded from billing bucket.
- API responds with proper auth gating (401 unauthenticated; 200 authenticated).
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/routes/test_billing_read_routes.py tests/middleware/test_rate_limit_billing.py -x` all green.
- Manual smoke (executor): `curl -i http://localhost:8000/v1/billing/packs` returns 401 without cookie; with cookie returns 200 + 5-pack JSON.
- `grep -A2 '_BILLING_PATH_PREFIX' api_server/src/api_server/middleware/rate_limit.py` shows the webhook exclusion.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-03-SUMMARY.md` listing the 3 read endpoints + the rate-limit bucket + ErrorCode additions.
</output>
