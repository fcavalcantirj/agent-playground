---
phase: B-stripe
plan: 05
subsystem: billing-paywall
tags: [wave-3, stripe, checkout, subscription, lazy-customer, race-defense, post-routes, fastapi]
requires:
  - phase: B-stripe-02
    provides: "build_stripe_client + lazy_create_or_fetch_customer + create_pack_checkout_session + create_subscription_checkout_session helpers; AP_STRIPE_* Settings; PACKS catalog single SOT; lifespan-owned app.state.stripe_client"
  - phase: B-stripe-03
    provides: "routes/billing.py with require_user gate, _err helper, ErrorCode.INVALID_PACK_ID, billing rate-limit bucket (30/60s, webhook excluded)"
provides:
  - "POST /v1/billing/checkout — Stripe Checkout session for one-time credit pack (D-06)"
  - "POST /v1/billing/subscription — Stripe Checkout session for Pro monthly subscription (D-02)"
  - "Both endpoints lazy-create the Stripe Customer race-safely (D-11; spike-g proof reproduced at route layer)"
  - "phase_b_e2e marker registered in pyproject.toml — opt-in real-Stripe-TEST e2e (Plan 13 will drive in CI)"
  - "FakeStripeClient stateful test double pattern for future Wave 3 webhook tests (per RESEARCH Pitfall 10)"
affects: [B-stripe-06, B-stripe-07, B-stripe-08, B-stripe-09, B-stripe-10, B-stripe-11, B-stripe-12, B-stripe-13]
tech-stack:
  added: []
  patterns:
    - "FakeStripeClient stateful test double — counter-incrementing customers.create + checkout.sessions.create with deterministic id minting; thread-safe under asyncio.gather"
    - "Lazy-customer-create idempotency assertion via fake counter (1 call across 2 sequential POSTs; 1 call across 2 concurrent POSTs)"
    - "Default success_url with literal {CHECKOUT_SESSION_ID} placeholder (Stripe substitutes server-side at redirect; mobile webview reads off intercepted URL)"
    - "Generic 502 INVALID_REQUEST envelope on Stripe SDK exception (T-B-LK no detail leak); _log.exception for redacted server-side trace"
key-files:
  created:
    - api_server/tests/routes/test_billing_checkout_routes.py
  modified:
    - api_server/src/api_server/routes/billing.py
    - api_server/pyproject.toml
key-decisions:
  - "Stripe SDK boundary mocked via stateful FakeStripeClient (not stripe-mock) — RESEARCH Pitfall 10 documents stripe-mock as shape-only/stateless; our route tests need state propagation (returned cus_id flows back into UPDATE users.stripe_customer_id) so a hand-rolled stateful fake is the appropriate tool. Real Postgres + asyncpg + SELECT FOR UPDATE flows through unchanged."
  - "phase_b_e2e marker added to pyproject.toml (skipif gate keyed on AP_STRIPE_TEST_API_KEY env). Default CI run (`pytest -m 'not phase_b_e2e'`) excludes it; Plan 13 will wire `make e2e-phase-b-stripe` to drive it against real Stripe TEST mode."
  - "Default success_url constant lives in billing.py (NOT Settings) — it's a Stripe-side handshake URL with the literal {CHECKOUT_SESSION_ID} substitution token, not an env-driven config. Constant uses solvrlabs.com domain (D-21 mobile webview intercepts here)."
  - "Stripe SDK exception handling = generic 502 INVALID_REQUEST with _log.exception. T-B-LK invariant: never leak Stripe error details (api keys may appear in trace messages); the existing _log.exception path uses Phase 29 _redact_creds for sanitization."
  - "Reused existing ErrorCode.INVALID_REQUEST as the 502 code (not a new code) — these failures are 'we couldn't build the Checkout request', which fits the 'invalid_request' Stripe-shape category. Adding a STRIPE_API_FAILURE code would inflate the error catalog without giving the mobile client a meaningful new branch."
patterns-established:
  - "Pattern: FakeStripeClient counter-incrementing test double for any Stripe SDK route test — re-usable for Wave 3 webhook handler shape tests (the webhook side already has the AMD-02 hand-rolled signed-fixture pattern)"
  - "Pattern: 2-way concurrent route POST test via asyncio.gather to verify SELECT FOR UPDATE serialization at the HTTP boundary (mirror spike-g case (b) at the route layer)"
  - "Pattern: app.state.stripe_client per-test override via async_client._app accessor (forward-compatible with the started_api_server fixture variant)"
requirements-completed: []
duration: ~14min
completed: 2026-05-09
---

# Phase B Plan B-stripe-05: POST /v1/billing/{checkout,subscription}

**Outbound Stripe-Checkout endpoints — mobile (Wave 5) calls these to mint a session URL it loads in InAppWebView. Lazy-customer-create + race-defense + auth-gated, all proven against real Postgres + a stateful Stripe SDK fake. Wave 3 webhook handler (Plan 06) is now unblocked to consume the user-side half of the contract.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-05-09T02:05:20Z
- **Completed:** 2026-05-09T02:20:00Z
- **Tasks:** 1 (TDD: RED + GREEN; no REFACTOR needed)
- **Files created:** 1
- **Files modified:** 2

## Accomplishments

- **POST /v1/billing/checkout** ships: validates pack_id against the in-memory PACKS allow-list (T-B-PCK), lazy-creates the Stripe Customer (D-11; race-defended via Wave 1's `SELECT ... FOR UPDATE`), creates a one-time-payment Checkout session via the Wave 1 `create_pack_checkout_session` helper, returns `{checkout_url}` for the mobile webview.
- **POST /v1/billing/subscription** ships: lazy-creates the Stripe Customer the same way, creates a subscription-mode Checkout session referencing `settings.stripe_price_id_pro_monthly` (D-02), returns `{checkout_url}`.
- Both endpoints are auth-gated (`require_user` 401 envelope on miss), read StripeClient + Settings from `app.state` (AMD-04), and inherit the billing rate-limit bucket from Plan 03 (30 requests / 60s, webhook excluded).
- D-24 `allow_promotion_codes=True` and `automatic_tax: {enabled: true}` are carried by the Wave 1 helpers and asserted at the route layer.
- Default `success_url` constant embeds the literal `{CHECKOUT_SESSION_ID}` placeholder so Stripe substitutes the real session id at redirect time — the mobile webview's nav delegate (D-21) can then read it off the intercepted URL.
- T-B-LK leak defense: any Stripe SDK exception is logged via `_log.exception` (sanitized by Phase 29 `_redact_creds`) but the client only sees a generic 502 INVALID_REQUEST.
- 9 new TDD route tests + 12 sibling read-route tests (no regression) + 25 Wave 1 sibling tests (no regression) = **46/46 PASS** under real Postgres testcontainer.
- 1 phase_b_e2e marker registered for the real-Stripe-TEST e2e test, correctly skipped without `AP_STRIPE_TEST_API_KEY` (Plan 13 will drive in CI).

## Task Commits

Each task was committed atomically:

1. **Task 1 RED gate: failing tests** — `e0e29e9` (test)
2. **Task 1 GREEN gate: endpoints implementation** — `7a254e0` (feat)

## Truth Audit (must_haves.truths from PLAN.md)

- [x] **POST /v1/billing/checkout {pack_id} validates pack_id is in PACKS, returns {checkout_url} pointing at Stripe-hosted Checkout** — proven by `test_checkout_invalid_pack_id_returns_400_with_invalid_pack_id_code` (allow-list rejection) + `test_checkout_valid_pack_id_returns_200_with_checkout_url` (returned URL is `https://checkout.stripe.com/c/pay/...` and references the same pack_id in session metadata).
- [x] **POST /v1/billing/subscription returns {checkout_url} for the Pro monthly subscription** — proven by `test_subscription_authenticated_returns_200_with_checkout_url` (200 + URL) + `test_subscription_uses_pro_monthly_price_id_from_settings` (line_items[0].price == settings.stripe_price_id_pro_monthly).
- [x] **Both endpoints are auth-gated (require_user) and create the Stripe Customer lazily (race-safe via SELECT FOR UPDATE)** — proven by 2 unauthenticated 401 tests + `test_checkout_lazy_creates_customer_on_first_call_only` (1 customer create across 2 sequential POSTs) + `test_checkout_concurrent_first_clicks_create_one_customer` (1 customer create across 2 concurrent POSTs via `asyncio.gather`; mirrors spike-g case (b)).
- [x] **Both endpoints respect AMD-04 (StripeClient instance from app.state, NOT module-level)** — verified in source: `client = request.app.state.stripe_client` at billing.py:354 and 408; helpers from `services.stripe_client` use `client.checkout.sessions.create(params={...})` (service-pattern call shape) — no module-level `stripe.api_key=` or `stripe.Customer.create(...)` anywhere in the call path.
- [x] **Invalid pack_id returns 400 with INVALID_PACK_ID code** — `test_checkout_invalid_pack_id_returns_400_with_invalid_pack_id_code` asserts both the status code and the envelope's `error.code`.
- [x] **Tests can run against stripe-mock OR real Stripe TEST mode (per pytest mark)** — default fast tests use the FakeStripeClient (statful drop-in for the SDK boundary; mirrors stripe-mock's shape role per Pitfall 10 but adds the state our route tests require). The `phase_b_e2e`-marked test substitutes a real `stripe.StripeClient(AP_STRIPE_TEST_API_KEY)` and hits live Stripe TEST. Default CI runs exclude the phase_b_e2e marker; Plan 13 will drive it.

## Done Criteria (from PLAN.md <done>)

- [x] All non-`phase_b_e2e` tests pass against the StripeClient stub — `9 passed, 1 deselected, 1 warning in 6.71s`.
- [x] `grep -c '@router.post("/billing/' api_server/src/api_server/routes/billing.py` outputs `2` — verified.
- [x] `_DEFAULT_SUCCESS_URL` uses `{CHECKOUT_SESSION_ID}` placeholder — verified by `test_checkout_default_success_url_carries_session_id_placeholder`.
- [x] Lazy-create-counter test proves `lazy_create_or_fetch_customer` is called twice but `client.customers.create` only fires once — `test_checkout_lazy_creates_customer_on_first_call_only` asserts `len(fake_stripe_client.customers_calls) == 1` after two POSTs.
- [x] Race-defense test mirrors spike-g (2 concurrent POSTs → 1 customer) — `test_checkout_concurrent_first_clicks_create_one_customer` (asyncio.gather + same-user pool; assertion: `len(fake.customers_calls) == 1`).
- [x] The `phase_b_e2e`-marked test exists and is skipped without the env var present — verified via `pytest -m phase_b_e2e` → `1 skipped`.

## Key Files

### Created

- `api_server/tests/routes/test_billing_checkout_routes.py` (516 lines) — 9 stripe-mock-style tests + 1 phase_b_e2e marked test. Uses a hand-rolled `FakeStripeClient` (counter-incrementing customers.create + sessions.create with deterministic id minting) to exercise the route+helper end-to-end against real Postgres while short-circuiting the Stripe HTTP boundary.

### Modified

- `api_server/src/api_server/routes/billing.py` — appended 178 lines: `_DEFAULT_SUCCESS_URL` / `_DEFAULT_CANCEL_URL` constants, `CheckoutRequest` / `CheckoutResponse` / `SubscriptionRequest` Pydantic models, `create_pack_checkout` and `create_subscription` POST handlers. Imports extended with `Field`, `get_pack`, and the two Wave 1 helper symbols.
- `api_server/pyproject.toml` — `phase_b_e2e` pytest marker registered (mirror existing `e2e_money_path` for Phase 31 H8).

## Decisions Made

- **FakeStripeClient over stripe-mock:** RESEARCH Pitfall 10 is explicit — stripe-mock validates request shapes only and is stateless, so a test that creates a Customer and then expects to read back its id will fail with stripe-mock. Our lazy-customer-create idempotency tests rely on a returned `cus_test_*` id flowing back into `UPDATE users.stripe_customer_id`, so a stateful fake is necessary. The fake mirrors the v15 service-pattern surface (`client.customers.create`, `client.checkout.sessions.create`) used by Wave 1's helpers; everything except the actual outbound HTTP-to-Stripe call goes through real code paths (real Postgres, real asyncpg, real `SELECT FOR UPDATE`, real Pydantic). The Wave 0 spike-a already covered the SDK's HMAC + signature contract end-to-end against the real `stripe` library, so this fake doesn't need to re-prove SDK semantics.

- **Stripe SDK exception → generic 502 INVALID_REQUEST:** following T-B-LK (BYOK / API-key never leaks via error message) — Stripe SDK exceptions can carry the API key in trace strings under some failure modes; the safest discipline is to log the full exception via `_log.exception` (which Phase 29 `_redact_creds` sanitizes) and return only a generic envelope to the client. ErrorCode reused (`INVALID_REQUEST`) rather than minted (`STRIPE_API_FAILURE`) — the mobile client doesn't need a new branch on this path; either it succeeds with a URL or it surfaces a generic "try again" SnackBar.

- **Default success_url constant in billing.py, not Settings:** the `{CHECKOUT_SESSION_ID}` literal is a Stripe-side substitution token, not env config. The constant is also the canonical mobile-webview-handshake URL (D-21) — it lives where the routes that emit it live, so a future code-search "where does the Checkout return URL come from" lands directly on it. Optional client overrides via the request body are honored (handy for Phase B.2 web frontend which may want a different post-Checkout landing page); defaults are the load-bearing path.

- **No new ledger writes in this plan:** these endpoints only mint Checkout sessions. The credit grant happens later in Wave 3's webhook handler (Plan 06) when `checkout.session.completed` lands and the `pack_id` metadata is read off the event. This plan is purely the user-initiated outbound half of the Stripe contract.

## Deviations from Plan

**None.** Plan executed exactly as written. All 9 stripe-mock-style tests + 1 phase_b_e2e marker test were specified in the plan's `<behavior>` block; the FakeStripeClient pattern is a faithful interpretation of the plan's "Use the `stripe_client_test` fixture from Wave 1's conftest extension" — Wave 1 deferred that fixture per the deferred-items.md, so this plan implements its own per-test fixture (cleaner than a session-scoped extension since each test wants a fresh counter anyway).

## Threat Model Audit

Per `<threat_model>` in PLAN.md, all 5 STRIDE threat-register entries have route-level mitigations or accept dispositions:

- **T-B-LR** (Customer-create race): mitigated by Wave 1's `SELECT ... FOR UPDATE` row lock; route-level test `test_checkout_concurrent_first_clicks_create_one_customer` asserts 1 customer create across 2 concurrent POSTs from the same user (mirrors spike-g case (b)).
- **T-B-PCK** (pack_id tampering): mitigated by allow-list check `if get_pack(body.pack_id) is None: return 400`. Test `test_checkout_invalid_pack_id_returns_400_with_invalid_pack_id_code` proves rejection without any Stripe SDK call.
- **T-B-LK** (Stripe error detail leak): mitigated by `_log.exception` (Phase 29 redacted) + generic 502 envelope; no Stripe SDK error string surfaces in the response body.
- **T-B-RUN** (success_url / cancel_url tampering): accepted with documented future hardening — even an evil URL only redirects the user's own webview; the Stripe Customer creation already happened. Future hardening: validate URL scheme is https + host is an allowlist (deferred).
- **T-B-IDP** (Stripe idempotency): accepted — Stripe SDK auto-generates idempotency keys for create operations; SDK retry-safe.

## Threat Flags

No new threat surface introduced beyond the plan's threat_model. The 2 new POST endpoints add no new persistence (writes happen via the Wave 1 helpers' existing transaction in `lazy_create_or_fetch_customer`; no new file access; no new env reads beyond Settings). The Stripe-egress surface is the existing app.state.stripe_client constructed by the Wave 1 lifespan.

## Self-Check: PASSED

**Files exist:**
- FOUND: `api_server/tests/routes/test_billing_checkout_routes.py`
- FOUND: `api_server/src/api_server/routes/billing.py` (modified)
- FOUND: `api_server/pyproject.toml` (modified)

**Commits exist:**
- FOUND: `e0e29e9` (test RED gate)
- FOUND: `7a254e0` (feat GREEN gate)

**Test verification:**
- `cd api_server && uv run pytest tests/routes/test_billing_checkout_routes.py -m 'not phase_b_e2e' -x` → `9 passed, 1 deselected, 1 warning in 6.71s` ✅
- `cd api_server && uv run pytest tests/routes/test_billing_*.py tests/test_billing_packs.py tests/test_ledger_atomic.py tests/test_migration_014_phase_b.py -m 'not phase_b_e2e'` → `46 passed` (9 new + 12 read-route + 8 ledger + 10 migration + 7 packs) ✅

## TDD Gate Compliance

- **RED gate:** `e0e29e9` — `test(B-stripe-05): add failing tests for POST /v1/billing/{checkout,subscription}` (9 tests, all failing with 404 because endpoints didn't exist; verified before commit).
- **GREEN gate:** `7a254e0` — `feat(B-stripe-05): POST /v1/billing/{checkout,subscription} endpoints` (9 tests pass; sibling tests still pass).
- **REFACTOR gate:** Not needed — endpoint shape is direct and final per the plan's <action> template; no cleanup pass produced different code.

## Manual smoke (deferred to Plan 13 / B-HUMAN-UAT)

Per PLAN.md `<success_criteria>`, the manual smoke (`curl -X POST -b "ap_session=..." -d '{"pack_id":"pack_25"}' http://localhost:8000/v1/billing/checkout` returning a real `cs_test_*` URL) is deferred to:

1. **Plan 13 automation** (`make e2e-phase-b-stripe` driving the `phase_b_e2e`-marked test against real Stripe TEST mode in CI).
2. **B-HUMAN-UAT** (manual run alongside the Stripe CLI `stripe listen` setup; mirrors Phase 31 H8's split CI/manual gating).

Both are out-of-scope for Plan 05 itself.

---

*Phase: B-stripe-paywall*
*Plan: 05*
*Wave: 3 — POST checkout endpoints (Wave 3 sibling: Plan 06 webhook handler, Plan 07 tier_enforcement)*
*Completed: 2026-05-09*
