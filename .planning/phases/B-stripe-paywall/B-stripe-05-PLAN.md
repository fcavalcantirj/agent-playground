---
phase: B-stripe
plan: 05
type: execute
wave: 3
depends_on: [B-stripe-03, B-stripe-04]
files_modified:
  - api_server/src/api_server/routes/billing.py
  - api_server/tests/routes/test_billing_checkout_routes.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-03 (both Stripe surfaces — subscription + credit Checkout)
  - D-06 (pack catalog backed by /v1/billing/packs)
  - D-11 (lazy customer create — uses services/stripe_client.lazy_create_or_fetch_customer)
  - D-21 (mobile receives session_url to open in webview)
  - D-24 (allow_promotion_codes=true on every Checkout)
  - AMD-04 (StripeClient instance via app.state.stripe_client)
  - BIL-01 (top-up via Stripe Checkout)
must_haves:
  truths:
    - "POST /v1/billing/checkout {pack_id} validates pack_id is in PACKS, returns {checkout_url} pointing at Stripe-hosted Checkout"
    - "POST /v1/billing/subscription returns {checkout_url} for the Pro monthly subscription"
    - "Both endpoints are auth-gated (require_user) and create the Stripe Customer lazily (race-safe via SELECT FOR UPDATE)"
    - "Both endpoints respect AMD-04 (StripeClient instance from app.state, NOT module-level)"
    - "Invalid pack_id returns 400 with INVALID_PACK_ID code"
    - "Tests can run against stripe-mock OR real Stripe TEST mode (per pytest mark)"
  artifacts:
    - path: "api_server/src/api_server/routes/billing.py"
      provides: "Adds POST /v1/billing/checkout and POST /v1/billing/subscription"
      contains: "@router.post(\"/billing/checkout\""
  key_links:
    - from: "routes/billing.py POST /billing/checkout"
      to: "services/stripe_client.py::create_pack_checkout_session"
      via: "function call passing app.state.stripe_client + asyncpg conn + pack_id + URLs"
      pattern: "create_pack_checkout_session"
---

<objective>
Outbound Stripe-API endpoints. Mobile (Wave 5) will POST {pack_id} to `/v1/billing/checkout` and POST {} to `/v1/billing/subscription`, then open the returned `checkout_url` in InAppWebView. Both endpoints lazy-create the Stripe Customer the first time the user touches Stripe.

Purpose: This is the user-initiated half of the Stripe contract. The other half is Wave 3's webhook handler (Plan 06).
Output: 2 new POST endpoints in routes/billing.py + tests against stripe-mock + (under phase_b_e2e mark) real Stripe TEST mode.
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
@.planning/phases/B-stripe-paywall/B-stripe-03-SUMMARY.md
@api_server/src/api_server/routes/billing.py
@api_server/src/api_server/services/stripe_client.py
@api_server/src/api_server/services/billing_packs.py
@api_server/src/api_server/config.py

<interfaces>
From api_server/src/api_server/services/stripe_client.py (Wave 1):
```python
async def create_pack_checkout_session(
    *, conn, user_id: UUID, pack_id: str,
    success_url: str, cancel_url: str, client: StripeClient,
) -> str:  # returns hosted Checkout URL

async def create_subscription_checkout_session(
    *, conn, user_id: UUID, success_url: str, cancel_url: str,
    client: StripeClient, settings: Settings,
) -> str:  # returns hosted Checkout URL
```

From routes/billing.py (Wave 2 — extending this file):
- router exists; PackCatalogResponse / BalanceResponse / TransactionsResponse models exist
- _err helper exists
- ErrorCode.INVALID_PACK_ID exists
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: POST /v1/billing/checkout + /v1/billing/subscription endpoints</name>
  <files>api_server/src/api_server/routes/billing.py, api_server/tests/routes/test_billing_checkout_routes.py</files>
  <read_first>
    - api_server/src/api_server/routes/billing.py (Wave 2 — current file shape after Plan 03)
    - api_server/src/api_server/services/stripe_client.py (Wave 1 — helper signatures)
    - api_server/src/api_server/services/billing_packs.py (Wave 1 — get_pack)
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (§Example C — full helper template + Pitfall 5 — race defense)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"services/stripe_client.py")
    - api_server/tests/conftest.py (stripe_client_test fixture from Wave 1)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_checkout_unauthenticated_returns_401
    - test_checkout_invalid_pack_id_returns_400_with_invalid_pack_id_code
    - test_checkout_valid_pack_id_returns_200_with_checkout_url
    - test_checkout_lazy_creates_customer_on_first_call_only (mock counter + 2 sequential calls)
    - test_checkout_returns_url_starting_with_https (or stripe-mock host)
    - test_subscription_unauthenticated_returns_401
    - test_subscription_returns_200_with_checkout_url
    - test_subscription_uses_pro_monthly_price_id_from_settings
    - test_phase_b_e2e_real_stripe_test_mode_creates_real_session (marked phase_b_e2e — skipped without AP_STRIPE_TEST_API_KEY)
  </behavior>
  <action>
**Modification — `api_server/src/api_server/routes/billing.py`:** Append two new endpoints to the file from Wave 2.

```python
from ..services.billing_packs import get_pack
from ..services.stripe_client import create_pack_checkout_session, create_subscription_checkout_session

class CheckoutRequest(BaseModel):
    pack_id: str = Field(..., description="One of pack_5/pack_10/pack_25/pack_50/pack_100")
    success_url: str | None = Field(default=None, description="Override success URL (defaults to canonical)")
    cancel_url: str | None = Field(default=None, description="Override cancel URL")

class CheckoutResponse(BaseModel):
    checkout_url: str

# Default redirect URLs for the InAppWebView interception (RESEARCH Open Q #2 — webview-internal sentinel).
_DEFAULT_SUCCESS_URL = "https://app.solvrlabs.com/billing/return-success?session_id={CHECKOUT_SESSION_ID}"
_DEFAULT_CANCEL_URL = "https://app.solvrlabs.com/billing/return-cancel"


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_pack_checkout(request: Request, body: CheckoutRequest):
    """Create a Stripe Checkout Session for one of the 5 credit packs (D-06)."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    if get_pack(body.pack_id) is None:
        return _err(400, ErrorCode.INVALID_PACK_ID, f"unknown pack_id: {body.pack_id}")

    client = request.app.state.stripe_client
    pool = request.app.state.db
    success_url = body.success_url or _DEFAULT_SUCCESS_URL
    cancel_url = body.cancel_url or _DEFAULT_CANCEL_URL

    try:
        async with pool.acquire() as conn:
            checkout_url = await create_pack_checkout_session(
                conn=conn, user_id=user_id, pack_id=body.pack_id,
                success_url=success_url, cancel_url=cancel_url, client=client,
            )
    except Exception as e:
        _log.exception("billing.checkout.create_failed user_id=%s pack_id=%s", user_id, body.pack_id)
        return _err(502, ErrorCode.INVALID_REQUEST, "failed to create checkout session")
    return CheckoutResponse(checkout_url=checkout_url)


class SubscriptionRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None

@router.post("/billing/subscription", response_model=CheckoutResponse)
async def create_subscription(request: Request, body: SubscriptionRequest):
    """Create a Stripe Checkout Session for the Pro monthly subscription (D-02)."""
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
                conn=conn, user_id=user_id, success_url=success_url, cancel_url=cancel_url,
                client=client, settings=settings,
            )
    except Exception:
        _log.exception("billing.subscription.create_failed user_id=%s", user_id)
        return _err(502, ErrorCode.INVALID_REQUEST, "failed to create subscription session")
    return CheckoutResponse(checkout_url=checkout_url)
```

**File — `api_server/tests/routes/test_billing_checkout_routes.py`:** Two test classes:

1. **stripe-mock tests** (default — fast, no network): Use the `stripe_client_test` fixture from Wave 1's conftest extension. stripe-mock returns a stub Checkout Session with a fake URL. Behaviors covered: 401, 400 invalid pack, 200 with URL, lazy customer create counter, settings-driven price ID for subscription.

2. **`phase_b_e2e` marked tests** (real Stripe TEST mode): Skip if `AP_STRIPE_TEST_API_KEY` is unset. Build a real StripeClient with the env-provided key. Create a real test user (with email like `phase-b-e2e-{uuid}@example.com`). Hit the route. Assert the returned URL starts with `https://checkout.stripe.com/c/pay/cs_test_`. Inspect Stripe's API to confirm the Customer was lazy-created with `metadata.ap_user_id == str(user_id)` (cleanup the test customer at the end).

For the lazy-create-counter test: instrument `services/stripe_client.lazy_create_or_fetch_customer` via monkeypatch — wrap `client.customers.create` with a counter; call the route TWICE in sequence; assert the counter increments to 1 (not 2 — the second call reads the cached `stripe_customer_id`).

For race-defense: spawn 2 concurrent POSTs from the same user_id (using `asyncio.gather`); assert exactly 1 customer was created (mirror spike-g pattern).
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/routes/test_billing_checkout_routes.py -m 'not phase_b_e2e' -x</automated>
  </verify>
  <done>
- All non-`phase_b_e2e` tests pass against stripe-mock.
- `grep -c '@router.post(\"/billing/' api_server/src/api_server/routes/billing.py` outputs `2` (checkout + subscription).
- The `_DEFAULT_SUCCESS_URL` constant uses the `{CHECKOUT_SESSION_ID}` placeholder (Stripe replaces this with the actual session id at redirect time).
- Lazy-create-counter test proves `lazy_create_or_fetch_customer` is called twice but `client.customers.create` only fires once.
- Race-defense test mirrors spike-g (2 concurrent POSTs → 1 customer).
- The `phase_b_e2e`-marked test exists and is skipped without the env var present.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile → POST /v1/billing/{checkout,subscription} | session-cookie-authenticated; rate-limited per "billing" bucket from Plan 03 |
| api_server → Stripe API (outbound) | StripeClient (with secret API key) creates Customer + Checkout Session |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-LR | Tampering | routes/billing.py + services/stripe_client.lazy_create_or_fetch_customer | mitigate | SELECT ... FOR UPDATE serializes concurrent first-clicks; race-defense test asserts single customer create under 2-way concurrency |
| T-B-PCK | Tampering | routes/billing.py POST /billing/checkout | mitigate | pack_id is validated against PACKS allow-list; 400 INVALID_PACK_ID for unknown pack |
| T-B-LK | InfoDisclosure | routes/billing.py error envelopes | mitigate | exception handler logs the exception via _log.exception (sanitized via Phase 29 _redact_creds) but returns generic 502 to client; no Stripe error detail leaks |
| T-B-RUN | Tampering | success_url / cancel_url client overrides | mitigate | even if the client overrides, the only side-effect of an evil URL is the user's own webview bouncing to it; Stripe Customer creation already happened. Future hardening: validate URL scheme is https + host is an allowlist |
| T-B-IDP | Tampering | Stripe outbound API call | accept | the Stripe SDK auto-generates idempotency keys for create operations; SDK retry safe |
</threat_model>

<verification>
- 8 stripe-mock tests + 1 marked-skipped real-Stripe test exist.
- 2-way concurrent POST race test asserts single customer create.
- `make e2e-phase-b-stripe` (Plan 13) will run the marked-skipped test against real Stripe TEST mode.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/routes/test_billing_checkout_routes.py -m 'not phase_b_e2e' -x` green.
- Manual smoke: with deploy stack up + valid env, `curl -X POST -b "ap_session=..." -H "Content-Type: application/json" -d '{"pack_id":"pack_25"}' http://localhost:8000/v1/billing/checkout` returns `{"checkout_url":"https://checkout.stripe.com/c/pay/cs_test_..."}`.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-05-SUMMARY.md` listing the 2 endpoints + the lazy-customer-race-defense pattern.
</output>
