# Phase B: Stripe Paywall — Research

**Researched:** 2026-05-08
**Domain:** Stripe billing (subscription + one-time Checkout) on FastAPI + Temporal + asyncpg + Flutter
**Confidence:** HIGH on Stripe substrate (verified against PyPI/GitHub/docs); MEDIUM on a few mobile + stripe-mock gaps surfaced during research

## Summary

Phase B is a billing layer on top of an already-shipping FastAPI/Temporal/asyncpg/Flutter substrate. Most architectural decisions are **already locked** in CONTEXT.md (D-01..D-26). The research job is therefore to (1) verify the locked stack against current upstream reality, (2) close the empirical gray areas the planner will face, and (3) flag a small number of CONTEXT.md decisions that research has invalidated and need amendment **before** planning.

**Three findings change the plan shape:**

1. **Stripe Python SDK pin in CONTEXT.md is two majors stale.** CONTEXT says `stripe>=8.0,<9.0`. PyPI live as of 2026-05-08 is **15.1.0** (verified by direct PyPI JSON query — see Sources). v8 is the **legacy `stripe.Customer.create` static-method era**; v9+ introduced `StripeClient` instances and v15.x is the current line. Recommended pin: `stripe>=15.0,<16.0`.

2. **`stripe-mock` does NOT emit webhook events.** CONTEXT D-22 reads "Unit tests use stripe-mock... for fast feedback on route handlers, **webhook idempotency**, debit math." The webhook idempotency clause is wrong: stripe-mock is a request/response validator only; the project README says it "does not attempt to reproduce the *behavior* of the real Stripe API at all." Webhook event simulation must come from either (a) hand-rolled fixture payloads (signed with the test webhook secret) or (b) Stripe CLI `trigger` against real TEST mode. Mainline tests will use option (a); CI integration tests will use option (b).

3. **Stripe CLI on macOS + deploy stack network is the H7-equivalent split-brain trap.** Per the canonical macOS rule (`feedback_no_native_uvicorn_with_deploy_stack.md`), Phase B must rebuild the deploy api_server image when smoke-testing. The Stripe CLI's `stripe listen --forward-to http://localhost:8000/v1/billing/webhook` works cleanly with that flow IF the deploy stack publishes 8000 (it already does). No new container needed (CLI runs on the host).

**Primary recommendation:** Plan around current-major Stripe SDK (15.x with `StripeClient`) and explicitly drop "stripe-mock for webhook idempotency tests" — replace with a thin local fixture+signature helper. Everything else in CONTEXT.md is sound.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Tier Model:**
- **D-01:** `users.tier` is a TEXT column with three exclusive enum values: `free | pro | ultra`. Migration 014 backfills every existing user to `'free'`.
- **D-02:** Tier semantics: `free` (BYOK, 1 agent, 7d retention), `pro` (BYOK + paid Stripe subscription, 5 agents, 30d retention; LLM still BYOK), `ultra` (platform-billed, AP fronts LLM key, credit packs via Checkout, pre-flight 402 + atomic debit, unlimited agents/retention).
- **D-03:** Phase B implements BOTH Stripe surfaces (subscription product + credit Checkout). They share `stripe_webhook_events` idempotency table and `users.stripe_customer_id` linkage column; otherwise independent workflows.
- **D-04:** Tier transitions are Stripe-event-driven. Webhook handler is the **sole writer** of `users.tier`.
- **D-05:** Pro entitlements: active-agent slot count `free=1 / pro=5 / ultra=∞`; retention `free=7d / pro=30d / ultra=unlimited`. Enforced in API at `agent.create` and `messages.list`.

**Pricing Knobs:**
- **D-06:** Credit-pack catalog hardcoded in api_server (single SOT, NOT duplicated to mobile — mobile fetches via `GET /v1/billing/packs`). 5 packs at $5/$10/$25/$50/$100. Each pack: `{ id, label, usd_amount_cents, credit_cents, stripe_price_id }`.
- **D-07:** Top-up grants are 1:1 USD→credit (`credit_cents = usd_amount_cents`). Markup lives only in `cost_weights.ap_multiplier` on the **debit** side.
- **D-08:** Phase B default `ap_multiplier = 1.15` (15% markup). Admin-mutable per row in `cost_weights`.
- **D-09:** Daily Temporal scheduled workflow (`prune_messages_workflow`) hard-deletes `inapp_messages` rows older than `users.tier` retention window.

**Stripe Substrate:**
- **D-10:** TEST-mode keys assumed available before Wave 0 spike. Live-mode arrives at H7.
- **D-11:** Stripe **Customer** record created **lazily** on first Stripe-affecting interaction. `users.stripe_customer_id` stays NULL for Free users. Customer metadata `{ ap_user_id: <uuid> }`.
- **D-12:** **Pre-flight 402 floor of 1¢.** If `tier='ultra' AND balance_cents < 1` → return 402 immediately, do not forward to upstream. Real cost debited post-hoc.
- **D-13:** Debit only on success. Non-2xx OR no `usage` block → debit_amount = 0. Mid-stream failures with partial tokens debit 0 in v1.
- **D-14:** Webhook event matrix: `checkout.session.completed`, `customer.subscription.{created,updated,deleted}`, `payment_intent.{succeeded,payment_failed}`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded`.
- **D-15:** Pro → Free downgrade: `cancel_at_period_end=true` (existing 5 agents continue until period end); at period end (`subscription.deleted`), tier flips to `free`, 4 oldest active agents auto-paused (not deleted), new `agent.create` blocked.
- **D-16:** Refund/chargeback: insert `credit_transactions` row with `kind='refund'`, `amount_cents = -original_amount`. Negative balance triggers 402. `users.refund_writeoff_cents BIGINT DEFAULT 0` for admin write-off.

**Architecture:**
- **D-17:** Ledger-as-truth. `credit_transactions` is sole source of truth; `credit_balances.balance_cents` is denormalized cache rebuilt by every debit/credit transaction in the same DB transaction. Mirrors MSV `web_user_repo.go:562` + `poken_service.go:180`. Nightly Temporal cron re-derives cache from ledger and logs drift.
- **D-18:** Tier propagation across sessions = lazy re-read. `get_current_user` reads `users.tier` fresh on every authenticated request. H2 NOT revived.

**Sequencing & Scope:**
- **D-19:** Phase B starts now (local substrate). Live webhook delivery requires HTTPS/H7 (Hetzner deploy). Phase 31 manual UAT items don't block.
- **D-20:** Phase B scope = api_server + mobile only. Web frontend = Phase B.2.

**Mobile UX:**
- **D-21:** 402 mobile UX: blocking modal "Out of credits" with "Top up" CTA → pack picker → Stripe Checkout webview → on return, mobile polls `GET /v1/billing/balance`. Inflight UI lock pattern from `feedback_inflight_ui_for_long_awaits.md`.

**Test Strategy:**
- **D-22:** Two-tier substrate: (a) **Unit** tests use `stripe-mock`; (b) **Integration + e2e** use real Stripe TEST mode + Stripe CLI webhook forwarding. CI runs against TEST keys (`AP_STRIPE_TEST_API_KEY`, `AP_STRIPE_TEST_WEBHOOK_SECRET`). Mirror Phase 31 H8 shape. **`respx` for HTTP isolation in unit tests.** *(Research note: see Recommended Amendments below — D-22 contains a load-bearing inaccuracy about stripe-mock's webhook capabilities.)*

**Scope Locks:**
- **D-23:** USD only. No currency column.
- **D-24:** Stripe promo codes enabled (`allow_promotion_codes=true`).
- **D-25:** Phase B exit gate: `PHASE-B-EXIT-GATE-PASSED` requires (1) automated CI e2e (Free → Ultra Checkout → message → `usage_logs` row → ledger debit → fourth call drains balance → fifth returns 402); (2) manual UAT in `B-HUMAN-UAT.md`.
- **D-26:** Migration 014 backfills `users.tier='free'`. Tier-change audit reuses `credit_transactions` with `kind='tier_change'`.

### Claude's Discretion

- **Env var naming:** `AP_STRIPE_API_KEY`, `AP_STRIPE_WEBHOOK_SECRET`, `AP_STRIPE_PRICE_ID_PRO_MONTHLY`, plus one `AP_STRIPE_PRICE_ID_*` per credit pack.
- **SDK pin:** `stripe>=8.0,<9.0` *(SUPERSEDED — see Recommended Amendments)*
- **Reconciliation poller:** 5-min Temporal scheduled workflow (`reconcile_stripe_workflow`).
- **Webhook idempotency:** `stripe_webhook_events.stripe_event_id` UNIQUE constraint; on duplicate event id, return 200 immediately. Same DB transaction as side-effect.
- **Decimal contract:** `debit_balance` activity preserves the Decimal-to-string return contract from Phase 28 D-22.
- **Tax computation:** Stripe Tax auto-handles VAT/sales-tax. AP doesn't compute tax.
- **Receipts:** Stripe's auto-emails are the v1 receipt path.
- **Webhook handler placement:** `api_server/src/api_server/routes/billing_webhook.py`. Public route, no auth dependency, signature-verified.

### Deferred Ideas (OUT OF SCOPE)

- **Phase B.2 (web frontend parity)** — top-up flow + balance display + 402 modal + transaction history.
- **Phase B.1 / hardening pass** — pro-rata partial-stream debit, branded receipts, multi-currency, admin write-off UI, token-count pre-flight estimation, multiple paid tiers, yearly subscription, invoice/PDF history, H2 revival.
- **H7 (Hetzner deploy)** — production prereq for live Stripe webhooks.
- **Future tier propagation upgrades** if lazy-reread latency becomes a UX problem.
- **Phase C** — analytics/reporting (per-tier MRR, usage projections, BYOK-vs-Ultra comparison).

</user_constraints>

## Recommended Amendments to CONTEXT.md (pre-planning)

Per `feedback_amend_context_post_research.md`, surface these to the user before `/gsd-plan-phase` so the locked-decisions doc remains the single source of truth.

| AMD | Section | Change | Rationale |
|-----|---------|--------|-----------|
| **AMD-01** | Claude's Discretion → SDK pin | Replace `stripe>=8.0,<9.0` with `stripe>=15.0,<16.0`. | [VERIFIED: PyPI 2026-05-08] Latest stable is 15.1.0; v8 is the **legacy module-level static-method API** (`stripe.Customer.create()`); v9+ introduced `StripeClient` instances. Pinning v8 commits us to a deprecation-track API surface and misses three years of upstream fixes. The "Billing Credit Balance + Meter Events APIs" rationale CONTEXT cites is preserved (those APIs landed in v8 and remain in v15). |
| **AMD-02** | D-22 Test Strategy | Strike "webhook idempotency" from the stripe-mock bullet; add: "Webhook handler signature-verify + idempotency tests use **hand-rolled signed fixtures** (raw JSON payload + `Stripe-Signature` header computed via `t=<unix>,v1=hmac_sha256(secret, f'{t}.{payload}')`). stripe-mock has no webhook event simulation per upstream docs and Issue #16." | [VERIFIED: github.com/stripe/stripe-mock README, Issue #16 (open since 2017)] stripe-mock validates request shapes; it does NOT emit events. Without this amendment, a Wave 0 spike will fail and the planner won't know why. |
| **AMD-03** | Mobile UX (D-21) | Pin webview package: `flutter_inappwebview` (NOT `webview_flutter`). | [VERIFIED: pubspec.yaml shows neither installed yet] flutter_inappwebview has documented `navigationDelegate` URL interception and is widely used for Stripe Checkout in 2026 community examples; webview_flutter's HTTPS handling has open issues with redirect interception (flutter/flutter#70284). Mobile must intercept `success_url`/`cancel_url` redirects to close the webview without server round-trip — that's the canonical pattern. |
| **AMD-04** | New decision | Webhook handler must use the **service-based SDK pattern** (`StripeClient.construct_event(payload, signature, secret)`), NOT the legacy module-level (`stripe.Webhook.construct_event(...)`). Both ship in v15.x; the latter is documented as deprecated. | [CITED: github.com/stripe/stripe-python/wiki/Migration-guide-for-v8-(StripeClient)] Future-proofs the call site — new endpoints land only on the StripeClient pattern. |
| **AMD-05** | New decision | Listen to **`checkout.session.completed` only** for credit-pack top-ups, not `payment_intent.succeeded`. Reason: `checkout.session.completed` carries the session-level `metadata` (where `pack_id` lives); `payment_intent.succeeded` does not unless metadata is double-attached. Listening to both creates a double-credit risk that must be defended against in idempotency code. | [VERIFIED: docs.stripe.com/metadata + github.com/stripe/stripe-go#1771] CONTEXT D-14 lists both events; clarification: `payment_intent.payment_failed` IS still needed (failure UX), but `payment_intent.succeeded` is redundant with `checkout.session.completed` for one-time payments and should be ignored or acknowledged-without-side-effect. |

These five amendments are the only research-revealed corrections. Everything else in the locked decisions is sound and survives current-day verification.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stripe Customer create (lazy) | API / Backend | — | D-11; secret keys never leave api_server |
| Stripe Checkout Session create (one-time pack) | API / Backend | — | Mobile receives `session_url` to open in webview; api_server signs the request |
| Stripe Subscription create (Pro upgrade) | API / Backend | — | Same as Checkout — secret keys server-side only |
| Webhook signature verification + idempotency | API / Backend | — | Stripe → AP HTTPS POST; only api_server has `AP_STRIPE_WEBHOOK_SECRET` |
| `users.tier` flip | API / Backend (webhook handler ONLY) | — | D-04 sole-writer rule |
| Pre-flight 402 balance check | API / Backend (proxy route) | — | D-12; happens before upstream forward in `llm_proxy.py` |
| Atomic debit on success | API / Backend (Temporal activity) | — | D-13 + D-17; in-DB transaction in `debit_balance` activity body |
| Daily message prune | Temporal worker | API / Backend (schema) | D-09; scheduled workflow + activity |
| 5-min Stripe reconcile | Temporal worker | — | Discretion; backstops missed webhooks |
| Nightly ledger reconciliation | Temporal worker | API / Backend (Sentry alert) | D-17; cache vs ledger drift detection |
| Pro slot/retention enforcement | API / Backend (route handlers) | — | D-05; `agent.create` + `messages.list` query gate |
| Credit-pack catalog read | API / Backend (`GET /v1/billing/packs`) | Mobile (display only) | D-06; dumb-client rule |
| Balance display | API / Backend (`/v1/billing/balance`) | Mobile (`UsageTickerWidget` extension) | D-21; ticker rendering branched on tier |
| Stripe Checkout webview | Mobile | API / Backend (creates session URL) | D-21; mobile opens URL, intercepts success/cancel redirect |
| 402 modal + Top-up flow | Mobile | API / Backend (404 propagation) | D-21; mobile owns blocking modal UX |
| Transaction history | API / Backend (`/v1/billing/transactions`) | Mobile (paginated list) | Phase 27 pattern reuse |

## Standard Stack

### Core (additions Phase B introduces)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **stripe** | **>=15.0,<16.0** | Stripe Python SDK | [VERIFIED: PyPI 2026-05-08, latest=15.1.0]. Current major. Carries `StripeClient` (D-AMD-04), Billing Credit Balance, Meter Events. v8 (CONTEXT current pin) is two majors stale and uses deprecated module-level static methods. |
| **stripe-cli** | **latest** (host install via `brew install stripe/stripe-cli/stripe`) | Local webhook forwarding for dev | [VERIFIED: docs.stripe.com/cli] Standard tool. Runs on host (NOT in deploy compose) and forwards to `http://localhost:8000/v1/billing/webhook`. Returns webhook signing secret on first `listen` invocation — pipe into `.env` as `AP_STRIPE_WEBHOOK_SECRET` for dev. |

### Supporting (already in stack — Phase B reuses)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `temporalio` | >=1.27.0,<1.28 | Already in pyproject.toml | Phase B adds 3 new workflows: `prune_messages_workflow` (D-09 daily cron), `reconcile_stripe_workflow` (5-min cron), `reconcile_ledger_workflow` (nightly cron); plus replaces body of existing `debit_balance` activity. |
| `asyncpg` | >=0.31.0,<0.32 | Already in pyproject.toml | Atomic ledger transactions (D-17) use `async with conn.transaction()`. |
| `sqlalchemy` | >=2.0.49,<2.1 | Already in pyproject.toml | NOT used for runtime queries (asyncpg direct); used only for alembic migrations. Phase B's migration 014 follows the existing 013 shape. |
| `respx` | >=0.22,<0.24 | Already in pyproject dev deps | HTTP isolation in unit tests against the Stripe SDK's underlying HTTP client. The Stripe Python SDK uses `requests` (legacy module mode) or `httpx` (new client) — both are mockable via respx (httpx) or the SDK's own `client` injection (requests path). |
| `sentry-sdk[fastapi]` | >=2.20,<3.0 | Already in pyproject.toml (Phase 31 H6) | New billing errors flow into Sentry without new wiring. D-17 reconciliation drift becomes a natural Sentry event. |
| `flutter_inappwebview` | latest stable on pub.dev | Mobile webview for Stripe Checkout | NOT YET in pubspec.yaml — Phase B introduces. AMD-03 documents why this over `webview_flutter`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| **stripe v15.x SDK** | stripe v8.x (CONTEXT current pin) | v8 is deprecation-track; new endpoints (Billing Credit Grant API, Meter Events post-2025) only available on the StripeClient pattern. v8 still works for our happy path but commits us to migration debt. |
| **`StripeClient.construct_event`** (AMD-04) | `stripe.Webhook.construct_event` (legacy module path) | Both work in v15. Legacy will be deprecated; service pattern is upstream-recommended. |
| **`flutter_inappwebview`** (AMD-03) | `webview_flutter` (Google-maintained) | webview_flutter has open HTTPS-redirect interception issues (flutter/flutter#70284); flutter_inappwebview's `navigationDelegate` is the widely-used 2026 community pattern for Stripe Checkout. Tradeoff: third-party vs Google-blessed; net win for navigation delegate clarity. |
| **External browser via `url_launcher` (AP already has it)** | Built-in browser tab | Per the 2026 article on Stripe Flutter crashes (Anab Khan, Apr 2026), the WebView teardown path is unstable on some Android devices. External browser is more stable. Tradeoff: loses smooth UX (user leaves the app, comes back via deep link). **For v1, stick with in-app webview per D-21**; flag external browser as a Phase B.1 fallback if iOS/Android in-app issues surface. |
| **Stripe-mock for webhook idempotency tests** (CONTEXT D-22 wording) | Hand-rolled signed fixtures (AMD-02) | stripe-mock has no webhook simulation. Hand-rolled is the only path. |
| **Single-row UPDATE atomic** (MSV `web_user_repo.go:562` shape) | Optimistic version column | Single-row UPDATE with WHERE clause guards (`WHERE balance_cents = old`) gives atomicity AND drift detection in one statement. MSV does not use a version column for poken_balances either (relies on `balance >= amount` predicate). Both work; recommend single-row UPDATE per MSV precedent. |
| **Daily Temporal cron (D-09)** | pg_cron / OS cron | Temporal already in stack; pg_cron means new Postgres extension + ops surface; OS cron has no observability. Temporal cron + activity gives retry, observability via Temporal UI, and same-runtime as the rest. |

**Installation (api_server):**

```bash
# Add to api_server/pyproject.toml under [project.dependencies]:
"stripe>=15.0,<16.0",
# Then:
cd api_server && uv lock
```

**Installation (mobile):**

```bash
# Add to mobile/pubspec.yaml under dependencies:
flutter_inappwebview: ^6.1.5  # verify latest at planning-time
# Then:
cd mobile && flutter pub get
```

**Installation (host):**

```bash
brew install stripe/stripe-cli/stripe   # macOS dev
stripe login   # opens browser for OAuth pairing with Stripe TEST mode
```

**Version verification (planner runs at plan-time):**

```bash
# Stripe Python SDK
python3 -c "import urllib.request, json; print(json.loads(urllib.request.urlopen('https://pypi.org/pypi/stripe/json').read())['info']['version'])"
# As of 2026-05-08: 15.1.0

# stripe-mock (image)
docker pull stripe/stripe-mock:latest && docker inspect stripe/stripe-mock:latest --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
# As of 2026-05-08: 0.199.0 (released May 7, 2026)

# flutter_inappwebview
curl -s https://pub.dev/api/packages/flutter_inappwebview | python3 -c "import sys, json; print(json.load(sys.stdin)['latest']['version'])"
```

## Architecture Patterns

### System Architecture Diagram

```
                  Browser (Stripe Checkout, hosted page)
                              ↑   redirect on success_url/cancel_url
                              ↓
+--------+    /v1/billing/checkout    +--------------+    create Customer/Session   +-----------+
| Mobile | ──────────────────────────▶|  api_server  |──────────────────────────────▶|  Stripe   |
| Flutter|◀──── { session_url } ──────|  (FastAPI)   |◀────── 200 + session.id ──────|   API     |
+--------+    open in InAppWebView    +--------------+                                +-----------+
    │                                       │  ▲                                          │
    │  POST chat → llm_proxy.py             │  │ writes users.tier,                       │ webhook
    │       (D-12 pre-flight 402 if         │  │ credit_balances,                         │ POST
    │        tier=ultra && balance<1¢)      │  │ credit_transactions                      │ /v1/billing/webhook
    │                                       │  │                                          ↓
    ▼                                       │  │  +------------------+                    │
+----------------+    forward upstream LLM   │  │  | billing_webhook  |◀───────────────────┘
| llm_proxy.py   |───────────────────────────┘  │  | (verify, dedup,  |
| (existing)     |       writes usage_logs      │  | branch on type,  |
+----------------+──────────────────────────────┼──| same-tx side-fx) |
        │                                       │  +------------------+
        │ start workflow                        │           │
        ▼                                       │           │
+--------------------+                          │           │
| Temporal           |                          │           │
| DispatchMessageWF  |                          │           │  Phase B writes
+--------------------+                          │           │  ┌──────────────────┐
        │                                       │           ▼  │ users (tier)     │
        │ debit_balance activity                │     ┌──────────────────────────┐
        │ (Phase B replaces body)               ▼     │ credit_balances (cache)  │
        ▼                                ┌──────────────────────────────────────┐
+----------------+   read cost_usd       │ credit_transactions (ledger truth)   │
| usage_logs row |◀───────────────────── │ stripe_webhook_events (idempotency)  │
| (cost_cents =  │   write ledger row    │ cost_weights (existing, ap_multiplier│
|  cost_usd*100  │   + UPDATE balance    │   bumps to 1.15)                     │
|  *ap_mult)     │   in same tx          │                                       │
+----------------+                       └──────────────────────────────────────┘

Three Temporal scheduled workflows (run on existing temporal-worker):
  prune_messages_workflow      (daily — D-09 retention)
  reconcile_stripe_workflow    (5min — backstop missed webhooks)
  reconcile_ledger_workflow    (nightly — drift detection, Sentry alert)
```

### Recommended Project Structure

```
api_server/src/api_server/
├── routes/
│   ├── billing_webhook.py         # NEW — public, signature-verified, sole writer of users.tier
│   ├── billing.py                 # NEW — /v1/billing/{packs,balance,transactions,checkout,subscription}
│   ├── llm_proxy.py               # MODIFY — D-12 pre-flight 402 insertion (no other change)
│   └── usage.py                   # MODIFY — /v1/usage/summary adds balance_cents field for ultra tier
├── services/
│   ├── stripe_client.py           # NEW — process-wide StripeClient instance + helpers (lazy customer create, session create)
│   ├── billing_packs.py           # NEW — single SOT for D-06 5-pack catalog (id, label, cents, stripe_price_id)
│   ├── ledger.py                  # NEW — atomic debit_user / credit_user / record_tier_change helpers (D-17 same-tx pattern)
│   └── tier_enforcement.py        # NEW — agent.create cap check, messages.list retention filter
├── temporal/
│   ├── activities/
│   │   ├── debit_balance.py       # MODIFY — body replaced (D-22 contract preserved)
│   │   ├── prune_messages.py      # NEW
│   │   ├── reconcile_stripe.py    # NEW
│   │   └── reconcile_ledger.py    # NEW
│   ├── workflows/
│   │   ├── prune_messages.py      # NEW (cron — daily)
│   │   ├── reconcile_stripe.py    # NEW (cron — 5min)
│   │   └── reconcile_ledger.py    # NEW (cron — nightly)
│   ├── schedules.py               # NEW — registers the 3 schedules at worker boot (idempotent on re-create)
│   └── worker.py                  # MODIFY — register 3 new workflows + activities + invoke schedules.py
└── alembic/versions/
    └── 014_phase_b_credit_ledger_and_tier.py   # NEW

mobile/lib/features/
├── usage/
│   ├── usage_models.dart          # MODIFY — add tier field, balance_cents field
│   ├── usage_providers.dart       # MODIFY — branch projection on tier
│   └── usage_ticker_widget.dart   # MODIFY — render credits OR USD per tier
├── billing/                       # NEW directory
│   ├── billing_models.dart
│   ├── billing_providers.dart
│   ├── packs_screen.dart          # 5-pack picker
│   ├── checkout_webview_screen.dart  # InAppWebView with navigation delegate
│   ├── topup_inflight_widget.dart # mm:ss timer + Snack pattern (mirrors deploy_step.dart)
│   ├── transactions_screen.dart   # paginated history
│   └── insufficient_credits_modal.dart  # 402 modal — D-21
├── chat/
│   └── chat_providers.dart        # MODIFY — 402 handler shows InsufficientCreditsModal
└── core/api/
    └── api_client.dart            # MODIFY — add billing endpoint methods + 402 handling
```

### Pattern 1: Stripe webhook handler (FastAPI + StripeClient)

**What:** Public route receives signed webhook POST, verifies signature using v15 SDK, dedupes via DB unique constraint, branches on event type, runs side-effects in same DB transaction, returns 200.

**When to use:** The single endpoint at `POST /v1/billing/webhook`. Public route — no `require_user`.

**Example (verified pattern, v15 SDK):**

```python
# Source: https://docs.stripe.com/webhooks + https://github.com/stripe/stripe-python/blob/master/examples/webhooks.py
# Adapted to FastAPI v0.136 + asyncpg pattern shipping in api_server/routes/llm_proxy.py

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
import stripe  # v15.x

router = APIRouter()

@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    # 1. Raw body — MUST be the unmodified bytes Stripe sent.
    payload = await request.body()
    if stripe_signature is None:
        return JSONResponse({"error": "missing signature"}, status_code=400)

    settings = request.app.state.settings
    client = request.app.state.stripe_client  # StripeClient instance (D-AMD-04)

    # 2. Signature verify + 5-min timestamp tolerance (SDK default).
    try:
        event = client.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        return JSONResponse({"error": "bad signature"}, status_code=400)

    # 3. Idempotency: insert into stripe_webhook_events with UNIQUE on
    #    (stripe_event_id). Duplicate → 200 immediately.
    pool = request.app.state.db
    async with pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """
                INSERT INTO stripe_webhook_events (stripe_event_id, event_type, payload)
                VALUES ($1, $2, $3)
                ON CONFLICT (stripe_event_id) DO NOTHING
                RETURNING stripe_event_id
                """,
                event.id, event.type, payload.decode(),
            )
            if inserted is None:
                # Already processed.
                return JSONResponse({"received": True}, status_code=200)

            # 4. Branch on event type — side-effect in SAME transaction.
            if event.type == "checkout.session.completed":
                await _handle_checkout_completed(conn, event.data.object)
            elif event.type == "customer.subscription.created":
                await _handle_sub_created(conn, event.data.object)
            elif event.type == "customer.subscription.updated":
                await _handle_sub_updated(conn, event.data.object)
            elif event.type == "customer.subscription.deleted":
                await _handle_sub_deleted(conn, event.data.object)
            elif event.type == "invoice.payment_failed":
                await _handle_invoice_failed(conn, event.data.object)
            elif event.type == "charge.refunded":
                await _handle_refund(conn, event.data.object)
            # invoice.paid, payment_intent.succeeded → ack-only (no side effect; covered by other events)

    return JSONResponse({"received": True}, status_code=200)
```

### Pattern 2: Atomic ledger debit (MSV-style same-DB-tx)

**What:** Insert ledger row + UPDATE balance cache in one transaction. Idempotent on `usage_logs.upstream_request_id` via UNIQUE constraint on `credit_transactions.reference_id`.

**When to use:** `debit_balance` activity body (Phase 28-locked contract).

**Example (verified MSV shape):**

```python
# Source: ported from /Users/fcavalcanti/dev/meusecretariovirtual/api/internal/repository/web_user_repo.go:562
#         + /Users/fcavalcanti/dev/meusecretariovirtual/api/internal/service/poken_service.go:180
# AP version uses USD-cents (not Pokens) and a separate ledger table (D-17 ledger-as-truth).

@activity.defn(name="debit_balance")
async def debit_balance(inp: DispatchMessageInput) -> str:
    """Phase B body. Returns Decimal-as-string per Phase 28 D-22 contract."""
    pool = activity.info().workflow_run_id and _get_pool() or None  # via service registry
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Bail if user is not platform-billed.
            tier = await conn.fetchval(
                "SELECT tier FROM users WHERE id = $1", inp.user_id,
            )
            if tier != "ultra":
                return "0"  # BYOK tiers don't debit (D-02).

            # 2. Find the usage_logs row created by llm_proxy.py for this message.
            row = await conn.fetchrow(
                """
                SELECT id, cost_usd, upstream_request_id, status
                FROM usage_logs
                WHERE message_id = $1 AND user_id = $2
                ORDER BY created_at DESC LIMIT 1
                """,
                inp.message_id, inp.user_id,
            )
            if row is None or row["status"] != "success" or not row["cost_usd"]:
                return "0"  # D-13 — no debit on failure / missing usage.

            # 3. Apply ap_multiplier via cost_weights (per-provider tunable).
            #    cost_usd has already had ap_multiplier applied at proxy
            #    time (see llm_proxy.py:178-203). Defensive: re-read the
            #    multiplier here and confirm it matches; flag drift to
            #    Sentry. For Phase B v1, trust the proxy-side math.
            cost_cents = int((row["cost_usd"] * Decimal(100)).quantize(Decimal("1")))
            if cost_cents <= 0:
                return "0"

            # 4. Insert ledger row — UNIQUE on reference_id makes retries safe.
            try:
                await conn.execute(
                    """
                    INSERT INTO credit_transactions
                        (user_id, kind, amount_cents, reference_id, reference_type)
                    VALUES ($1, 'debit', $2, $3, 'usage_log')
                    """,
                    inp.user_id, -cost_cents, str(row["id"]),
                )
            except asyncpg.UniqueViolationError:
                # Idempotent retry — the original transaction already debited.
                return str(Decimal(cost_cents) / Decimal(100))

            # 5. Rebuild cache from ledger SUM (D-17 ledger-as-truth).
            await conn.execute(
                """
                UPDATE credit_balances
                   SET balance_cents = (
                       SELECT COALESCE(SUM(amount_cents), 0)
                       FROM credit_transactions
                       WHERE user_id = $1
                   ),
                   updated_at = NOW()
                 WHERE user_id = $1
                """,
                inp.user_id,
            )

            return str(Decimal(cost_cents) / Decimal(100))
```

### Pattern 3: Pre-flight 402 in `llm_proxy.py`

**What:** Before forwarding to upstream LLM, check `tier='ultra' AND balance_cents < 1` → return 402 immediately.

**When to use:** Single insertion after BYOK cache resolves provider/key, before body mutation in `routes/llm_proxy.py`. The "tier='ultra'" predicate makes this a no-op for Free + Pro users.

**Example:**

```python
# Source: extends api_server/src/api_server/routes/llm_proxy.py:296 (after BYOK cache lookup)

# ---------- 2.5. Phase B pre-flight 402 (D-12) ----------
async with request.app.state.db.acquire() as conn:
    row = await conn.fetchrow(
        """
        SELECT u.tier, COALESCE(b.balance_cents, 0) AS balance_cents
        FROM users u
        LEFT JOIN credit_balances b ON b.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
if row and row["tier"] == "ultra" and row["balance_cents"] < 1:
    return _err(402, ErrorCode.INSUFFICIENT_BALANCE,
                "Out of credits. Top up to continue.")
```

### Pattern 4: Temporal schedule registration (idempotent at boot)

**What:** Worker boot registers 3 schedules. `create_schedule` with same ID is NOT automatically idempotent in Python SDK 1.27 (returns error if exists). Use `update_schedule` if exists or wrap in try/except.

**When to use:** `temporal/schedules.py` invoked from `worker.py` after `Worker` constructed but before `worker.run()`.

**Example:**

```python
# Source: docs.temporal.io/develop/python/schedules + Wave 0 spike candidate

from temporalio.client import (
    Schedule, ScheduleSpec, ScheduleIntervalSpec, ScheduleActionStartWorkflow,
)
from temporalio.exceptions import RPCError
from datetime import timedelta

async def register_schedules(client, task_queue: str) -> None:
    # 1. Daily message prune at 03:00 UTC.
    await _create_or_update(
        client,
        schedule_id="phase-b-prune-messages-daily",
        schedule=Schedule(
            action=ScheduleActionStartWorkflow(
                PruneMessagesWorkflow.run,
                id="prune-messages",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(cron_expressions=["0 3 * * *"]),
        ),
    )

    # 2. Stripe reconcile every 5 min.
    await _create_or_update(
        client,
        schedule_id="phase-b-reconcile-stripe-5min",
        schedule=Schedule(
            action=ScheduleActionStartWorkflow(
                ReconcileStripeWorkflow.run,
                id="reconcile-stripe",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))]),
        ),
    )

    # 3. Nightly ledger drift reconcile.
    await _create_or_update(
        client,
        schedule_id="phase-b-reconcile-ledger-nightly",
        schedule=Schedule(
            action=ScheduleActionStartWorkflow(
                ReconcileLedgerWorkflow.run,
                id="reconcile-ledger",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(cron_expressions=["30 4 * * *"]),
        ),
    )

async def _create_or_update(client, *, schedule_id: str, schedule):
    try:
        await client.create_schedule(schedule_id, schedule)
    except RPCError as e:
        if "already exists" in str(e).lower():
            handle = client.get_schedule_handle(schedule_id)
            await handle.update(lambda input: schedule)
        else:
            raise
```

### Anti-Patterns to Avoid

- **`stripe.Customer.create(...)` (legacy module-level static method).** v15 still ships it; deprecation track. Use `client.customers.create(params={"metadata": {...}})`.
- **Listening to `payment_intent.succeeded` for credit-pack top-ups.** AMD-05; use `checkout.session.completed`. Listening to both creates double-credit risk.
- **Hand-rolling HMAC signature verification.** D-AMD-04; use `client.construct_event(...)` — it does constant-time comparison + timestamp tolerance + header parsing.
- **Reading the parsed JSON body for signature verify.** Stripe signs the **raw bytes**. Reading `await request.json()` first and passing the dict to construct_event will fail. Always `await request.body()` first.
- **Side-effects outside the dedupe transaction.** Insert into `stripe_webhook_events` AND apply the side-effect in the same `async with conn.transaction()` block. Otherwise: dedupe-then-crash-before-side-effect leaves a stuck event id.
- **Mounting `webview_flutter` for Stripe Checkout (instead of flutter_inappwebview).** Open issues with HTTPS redirect interception (flutter/flutter#70284) make the success_url handshake fragile.
- **Web flutter `stripe_checkout` package (pub.dev/packages/stripe_checkout).** Web-only; we're shipping mobile (D-20). Pub.dev currently shows it as Web-platform only.
- **Updating `users.tier` from any endpoint other than `billing_webhook.py`.** D-04 sole-writer rule. Even an admin route should INSERT a `credit_transactions` row with `kind='tier_change'`; a separate Temporal workflow could re-read the ledger and apply tier changes if admin overrides arrive.
- **Native uvicorn alongside deploy stack on macOS** (CLAUDE.md split-brain trap). Phase B local smoke MUST rebuild the deploy api_server image. Stripe CLI runs on the host pointed at the deploy stack's published port 8000.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Webhook signature verification | Custom HMAC-SHA256 + timestamp tolerance + constant-time comparison | `StripeClient.construct_event(payload, signature, secret)` | Stripe's SDK does all four correctly. Hand-rolled is 100% the bug surface area Stripe deliberately abstracts. |
| Webhook event idempotency | Per-event-type custom dedup | `stripe_webhook_events.stripe_event_id UNIQUE` constraint | One UNIQUE index covers every event type. Constraint violation on INSERT = idempotent return-200. |
| Stripe API request retries | Custom backoff loop | SDK's built-in retry (StripeClient default) + Idempotency-Key header | The SDK auto-retries with exponential backoff and auto-generates idempotency keys for mutating operations. |
| Per-event credit/debit math | Manual ledger-and-cache update | Single DB transaction with INSERT into ledger + UPDATE balance from `SELECT SUM` | Mirrors MSV `web_user_repo.go:562` proven pattern. Catches drift naturally. |
| Subscription renewal failure handling | Custom poll + retry | Stripe Smart Retries + listen for `customer.subscription.deleted` (which fires after final retry) | Stripe handles 1-2 month retry windows automatically; deletion event signals terminal failure. |
| Tax computation | Multi-jurisdiction VAT/sales-tax | Stripe Tax (auto-attaches to Checkout sessions) | D-Discretion locks this. Stripe Tax is a config flag, not code. |
| Receipt rendering | Custom email/PDF | Stripe auto-receipt emails | D-Discretion locks this. |
| Promo code redemption | Custom discount logic | `allow_promotion_codes=true` on Checkout session | D-24. Marketing mints in dashboard; payload reflects discount. |
| Webhook secret rotation | Custom rotation | Stripe's "endpoint secret" rotation flow (one secret per endpoint) | When rotating, support both old + new secret in the env briefly. |
| Currency conversion | Multi-currency | USD only (D-23) | Out of scope. |
| Mobile webview cookie/session juggling | Custom cookie store | Just open Stripe Checkout fresh; no AP session needed (Stripe owns the session) | Stripe Checkout is hosted; no AP-side auth state lives in the webview. Mobile only watches the redirect URL. |

**Key insight:** Stripe-shaped problems have Stripe-shaped tooling. The 90% solution is "use the SDK; trust the documentation." The 10% remaining (atomic ledger, Temporal scheduling, mobile webview redirect interception) are projects we own.

## Runtime State Inventory

> Phase B is a feature-add (not a rename/refactor) but multiple categories matter because Phase B introduces external-system state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | New schema only — `users.tier`, `users.stripe_customer_id`, `users.refund_writeoff_cents`, `credit_balances`, `credit_transactions`, `stripe_webhook_events`. None pre-exist. Migration 014 backfills `users.tier='free'` for all existing rows (D-26). `cost_weights.ap_multiplier` data-migration: bump every row from 1.0 to 1.15 (D-08). | Migration 014 — code + data migration combined. |
| **Live service config** | **Stripe Dashboard:** Pro subscription product + price (`AP_STRIPE_PRICE_ID_PRO_MONTHLY`); 5 credit-pack products + prices; webhook endpoint URL (TEST: tunneled via Stripe CLI; LIVE at H7); promo codes (D-24); Stripe Tax enabled flag. **None are exported to git.** Each is dashboard-side configuration the user creates manually before Wave 0 spike. | Out-of-band by user before Wave 0; documented in `B-HUMAN-UAT.md`. Each Stripe price ID lands in `.env` / `deploy/.env.prod`. |
| **OS-registered state** | None. Stripe runs entirely in Stripe's cloud; AP carries no OS-level Stripe registration (no launchd, no Task Scheduler, no pm2 named processes for Stripe). | None. |
| **Secrets and env vars** | `AP_STRIPE_API_KEY` (TEST starts with `sk_test_`, LIVE with `sk_live_`); `AP_STRIPE_WEBHOOK_SECRET` (starts with `whsec_`); 6× `AP_STRIPE_PRICE_ID_*` (one for Pro monthly + one per pack). All NEW. The dev pattern mirrors Phase 22c-OAuth: pydantic Settings reads from `.env`; placeholders in dev mode emit a warning log if missing. | Add to `.env.example`, document in `B-HUMAN-UAT.md`. CI gets `AP_STRIPE_TEST_API_KEY` + `AP_STRIPE_TEST_WEBHOOK_SECRET` as GH Actions secrets. |
| **Build artifacts / installed packages** | `api_server/uv.lock` will gain stripe transitive deps. `mobile/pubspec.lock` will gain `flutter_inappwebview`. Neither requires manual cleanup. | Re-lock after dep add: `cd api_server && uv lock`; `cd mobile && flutter pub get`. |

## Common Pitfalls

### Pitfall 1: Reading parsed JSON before signature verify
**What goes wrong:** `event = client.construct_event(await request.json(), ...)` — signature fails because Stripe signs raw bytes, not re-serialized JSON.
**Why it happens:** FastAPI's idiom is `await request.json()`; we're trained to parse first.
**How to avoid:** ALWAYS `payload = await request.body()` (raw bytes). Pass to construct_event verbatim.
**Warning signs:** `SignatureVerificationError` on every webhook in dev. Red herring: "the signing secret is wrong" — usually it's parsed-JSON.

### Pitfall 2: Side-effect outside the dedupe transaction
**What goes wrong:** Insert into `stripe_webhook_events` returns success → Python crashes → side-effect (ledger insert, tier flip) never happens. Stripe retries the webhook → dedupe says "already processed" → state stuck.
**Why it happens:** Splitting "did I already process this event?" from "do the work" feels natural.
**How to avoid:** Both INSERT and the side-effect are inside one `async with conn.transaction():` block. If the side-effect raises, the transaction rolls back; the dedupe row is gone; Stripe retries; we get a clean retry.
**Warning signs:** "Webhook event id X processed but balance not updated" in Sentry. The reconciliation poller (5-min cron) catches this naturally.

### Pitfall 3: Listening to both `checkout.session.completed` AND `payment_intent.succeeded` for credit packs
**What goes wrong:** Both events fire on a successful one-time payment. Both reach the handler. The session-side has the `pack_id` metadata (so it can grant credits); the PI side might be coded to "also grant credits because the payment succeeded" → double credit.
**Why it happens:** CONTEXT.md D-14 lists both events. Without AMD-05, a junior implementer might branch on both and grant credits twice.
**How to avoid:** Per AMD-05: handle `checkout.session.completed` only for credit grants. `payment_intent.succeeded` is acked-without-side-effect for one-time payments. `payment_intent.payment_failed` IS still handled (UX feedback for failed top-up).
**Warning signs:** Reconciliation poller catches drift between `SUM(amount_cents) WHERE kind='topup'` and the Stripe Customer's lifetime spend. Sentry alert.

### Pitfall 4: Ledger row UNIQUE constraint missing or wrong
**What goes wrong:** `debit_balance` activity gets retried by Temporal → second insert succeeds → balance double-debited.
**Why it happens:** Temporal retry is the default — the workflow is the cron, the activity is the unit of work, retries are expected.
**How to avoid:** `UNIQUE(reference_id, reference_type)` on `credit_transactions` so a second INSERT for the same `usage_log_id` raises `UniqueViolationError`. Activity catches that and returns the originally-debited amount.
**Warning signs:** Total credits debited > messages × max-cost-per-message. Reconciliation poller (or simple aggregate query) flags it.

### Pitfall 5: Stripe Customer create races on first interaction
**What goes wrong:** User clicks "Subscribe to Pro" twice → two requests reach api_server → two `stripe.customers.create({metadata: {ap_user_id}})` calls succeed → two Stripe Customers exist with the same `ap_user_id` metadata → `users.stripe_customer_id` only stores one.
**Why it happens:** D-11 says "lazy creation"; without server-side serialization, double-clicks race.
**How to avoid:** Wrap the create-or-fetch in `SELECT ... FOR UPDATE` on the user row. If `stripe_customer_id IS NULL`, create the Stripe Customer + UPDATE the user row in the same transaction. Second concurrent request blocks on the row lock; reads the populated value.
**Warning signs:** Stripe dashboard shows duplicate customers for the same `ap_user_id`. Pre-deploy: cover with a concurrent-request unit test.

### Pitfall 6: Negative balance UX surface
**What goes wrong:** Refund fires. `credit_transactions` gets `kind='refund', amount_cents=-X`. SUM goes negative. Mobile shows "$-3.42 credits". User confused.
**Why it happens:** D-16 explicitly says negative balance is allowed (sticky `refund_writeoff_cents` for admin override).
**How to avoid:** Mobile renders `max(balance, 0)` for display PLUS a "negative balance" banner with explanation when balance < 0. The API's `/v1/billing/balance` returns `balance_cents` (raw, can be negative) AND `display_balance_cents` (clamped to 0) and `is_negative` flag. Dumb-client rule: API decides display.
**Warning signs:** Support tickets about "where did my credits go" when refund happens.

### Pitfall 7: macOS dev — Stripe CLI listen + deploy stack network
**What goes wrong:** Developer runs `stripe listen --forward-to http://localhost:8000/v1/billing/webhook` while ALSO running native uvicorn on side port 8001 (for "fast iteration"). Webhooks land at 8000 (deploy api_server). The new code under test is at 8001. Webhooks bypass the new code entirely.
**Why it happens:** The split-brain trap from `feedback_no_native_uvicorn_with_deploy_stack.md` extends to webhook testing.
**How to avoid:** Per CLAUDE.md canonical macOS workflow: rebuild the deploy api_server image (`docker compose -f deploy/docker-compose.prod.yml build api_server && up -d api_server`). Stripe CLI on host forwards to deploy 8000 (already published). Mobile keeps pointing at 8000. One stack, no split-brain.
**Warning signs:** "Webhook fires but my new handler code never executes" — check `docker compose logs deploy-api_server-1` to see if THAT container received the request.

### Pitfall 8: Schedule re-creation on worker restart
**What goes wrong:** Worker boot calls `client.create_schedule(...)` which raises `Already exists` after first boot. Worker boot fails. Container crash-loops.
**Why it happens:** Temporal's `create_schedule` is NOT idempotent; behavior is "create once, error on duplicate."
**How to avoid:** Try-create, fall back to `get_schedule_handle(...).update(...)` (Pattern 4 example above). Wave 0 spike confirms the exact error string for the `RPCError` branch.
**Warning signs:** Worker container restart-loops with `RPCError: schedule already exists`.

### Pitfall 9: cancel_at_period_end UX gap
**What goes wrong:** User clicks "Cancel Pro" → Stripe sets `cancel_at_period_end=true` → no immediate webhook → `customer.subscription.updated` fires but `users.tier` stays `pro`. User expects immediate cancel; sees no UI change.
**Why it happens:** D-15 specifies "soft-cap with grace" — cancel doesn't take effect until period end. UX needs to communicate this.
**How to avoid:** Mobile shows "Pro until <renewal_date>" badge after cancel. The `customer.subscription.updated` handler stores `cancel_at_period_end` flag and `current_period_end` so the API can return it. Mobile UI consumes those fields.
**Warning signs:** Support tickets "I canceled but it still says Pro."

### Pitfall 10: stripe-mock test "false positives"
**What goes wrong:** Unit tests pass against stripe-mock. CI fails against real Stripe TEST. Reason: stripe-mock is stateless ("data sent in requests is validated but ignored; not stored or reflected in future responses"). A test that creates a Customer then queries it gets stripe-mock's hardcoded response, not the data sent.
**Why it happens:** [VERIFIED: github.com/stripe/stripe-mock README]. Stripe-mock validates request shapes only.
**How to avoid:** Use stripe-mock for shape tests (does our code make the right HTTP request to Stripe?). Use respx + signed fixtures for webhook tests. Use real Stripe TEST mode for any test that depends on subsequent reads of created resources.
**Warning signs:** Unit tests green, integration tests red on basic CRUD.

## Code Examples

### Example A: GET /v1/billing/packs (catalog read — dumb-client rule)

```python
# Source: api_server/src/api_server/routes/billing.py (NEW)
# Pattern from: api_server/src/api_server/routes/usage.py:162 (response_model + require_user)

@router.get("/billing/packs", response_model=PackCatalogResponse)
async def list_packs(request: Request):
    """Return the 5-pack credit catalog. Auth required (no anonymous browsing).

    Single source of truth: services.billing_packs.PACKS. Mobile fetches; never
    hardcodes. Dumb-client rule.
    """
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    return PackCatalogResponse(packs=[
        PackEntry(
            id=p.id,
            label=p.label,
            usd_amount_cents=p.usd_amount_cents,
            credit_cents=p.credit_cents,  # 1:1 per D-07
        )
        for p in PACKS
    ])
```

### Example B: GET /v1/billing/balance

```python
# Source: api_server/src/api_server/routes/billing.py (NEW)

@router.get("/billing/balance", response_model=BalanceResponse)
async def get_balance(request: Request):
    """Return user's current balance + tier. Polled by mobile post-Checkout."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.tier, COALESCE(b.balance_cents, 0) AS balance_cents
            FROM users u
            LEFT JOIN credit_balances b ON b.user_id = u.id
            WHERE u.id = $1
            """,
            user_id,
        )
    return BalanceResponse(
        tier=row["tier"],
        balance_cents=row["balance_cents"],
        display_balance_cents=max(row["balance_cents"], 0),
        is_negative=row["balance_cents"] < 0,
    )
```

### Example C: Create Stripe Checkout Session (one-time pack)

```python
# Source: api_server/src/api_server/services/stripe_client.py (NEW)
# Pattern from: github.com/stripe/stripe-python/wiki/Migration-guide-for-v8-(StripeClient)

async def create_pack_checkout_session(
    *, conn, user_id: UUID, pack_id: str, success_url: str, cancel_url: str,
    client: StripeClient,
) -> str:
    """Lazy-create Customer if needed, then create one-time Checkout Session.

    Returns the hosted Checkout URL the mobile app loads in InAppWebView.
    """
    # 1. Lazy customer create (D-11) under SELECT FOR UPDATE (Pitfall 5).
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        customer_id = row["stripe_customer_id"]
        if customer_id is None:
            customer = client.customers.create(params={
                "email": row["email"],
                "metadata": {"ap_user_id": str(user_id)},
            })
            customer_id = customer.id
            await conn.execute(
                "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
                customer_id, user_id,
            )

    # 2. Lookup pack catalog (single SOT in api_server).
    pack = next(p for p in PACKS if p.id == pack_id)

    # 3. Create Checkout Session.
    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "mode": "payment",
            "line_items": [{"price": pack.stripe_price_id, "quantity": 1}],
            "success_url": success_url,  # e.g. solvrlabs://billing/success?session_id={CHECKOUT_SESSION_ID}
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,  # D-24
            "metadata": {
                "ap_user_id": str(user_id),
                "pack_id": pack.id,
                "credit_cents": str(pack.credit_cents),
            },
            "automatic_tax": {"enabled": True},  # Stripe Tax (D-Discretion)
        },
    )
    return session.url  # https://checkout.stripe.com/c/pay/cs_test_...
```

### Example D: Mobile InAppWebView with redirect interception

```dart
// Source: mobile/lib/features/billing/checkout_webview_screen.dart (NEW)
// Pattern: navigationDelegate-style interception. AMD-03 picks flutter_inappwebview.
// Adapt to flutter_inappwebview's actual onLoadStart / shouldOverrideUrlLoading API
// at planning-time (Wave 0 spike confirms exact callback shape).

class CheckoutWebViewScreen extends ConsumerStatefulWidget {
  final String checkoutUrl;
  const CheckoutWebViewScreen({required this.checkoutUrl, super.key});
  @override
  ConsumerState<CheckoutWebViewScreen> createState() => _State();
}

class _State extends ConsumerState<CheckoutWebViewScreen> {
  static const String _successHost = 'solvrlabs';   // deep-link scheme
  static const String _successPath = '/billing/success';
  static const String _cancelPath = '/billing/cancel';

  @override
  Widget build(BuildContext context) {
    return InAppWebView(
      initialUrlRequest: URLRequest(url: WebUri(widget.checkoutUrl)),
      shouldOverrideUrlLoading: (controller, action) async {
        final uri = action.request.url;
        if (uri == null) return NavigationActionPolicy.ALLOW;
        if (uri.scheme == _successHost && uri.path == _successPath) {
          // Pop screen; trigger balance polling (D-21 inflight UI lock).
          if (context.mounted) Navigator.of(context).pop(_PaymentResult.success);
          return NavigationActionPolicy.CANCEL;
        }
        if (uri.scheme == _successHost && uri.path == _cancelPath) {
          if (context.mounted) Navigator.of(context).pop(_PaymentResult.cancelled);
          return NavigationActionPolicy.CANCEL;
        }
        return NavigationActionPolicy.ALLOW;
      },
    );
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `stripe.Customer.create(...)` (module-level static) | `client.customers.create(params={...})` (StripeClient instance) | v8.0.0 (2024); v15.x is current as of May 2026 | Multi-client support, easier mocking, isolated config |
| `stripe.Webhook.construct_event(payload, sig, secret)` | `client.construct_event(payload, sig, secret)` | v8.0.0; both still work in v15 | Service-pattern consistency |
| Cron expressions in Temporal | `ScheduleSpec` (cron + intervals + skips + jitter) | Temporal Schedules GA in 2023 | Pause/resume, retroactive trigger, observability via UI |
| `webview_flutter` | `flutter_inappwebview` for redirect-heavy flows | Community shift 2024+ | Cleaner navigationDelegate API |
| stripe-mock for everything | Three-tier: stripe-mock (shape) + signed fixtures (webhook idempotency) + Stripe TEST mode (e2e) | Stable; matches 2026 community guides | Right tool per concern |
| `stripemock/stripe-mock` Docker image | `stripe/stripe-mock` (canonical) | Old image deprecated; new image is canonical 2025+ | docker compose service path change |

**Deprecated/outdated:**
- `stripe-python v8.x` — still works, no longer receiving features. Pin AMD-01 says use v15.
- `stripe.Webhook.construct_event` (legacy) — works in v15 but documented as deprecation-track.
- `stripemock/stripe-mock` Docker image — use `stripe/stripe-mock`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Stripe Python SDK v15.1.0 is stable for production use | Standard Stack | Low — directly verified via PyPI; falls back to v15.0.x if a regression appears mid-Wave-0 |
| A2 | `flutter_inappwebview` ^6.x is current and maintained | Standard Stack | Medium — verify exact version at planning-time via pub.dev API; package has been actively maintained per AMD-03 sources |
| A3 | Stripe Tax auto-handles VAT for our jurisdictions | D-Discretion (CONTEXT) | Low for v1 (TEST mode); Medium for live launch. User confirms enabled in Dashboard before live cutover |
| A4 | `cost_weights.ap_multiplier` is already applied at proxy time (read llm_proxy.py:178-203) | Pattern 2 example | LOW — verified by reading current code; debit activity reads cost_usd which already includes multiplier |
| A5 | Existing Phase 28 Temporal worker pattern (worker.py) supports adding 3 more workflows + activities without restructuring | Architecture | Low — existing worker.py already has 2 workflows + 7+ activities; adding 3 more follows the same shape |
| A6 | Stripe CLI works on host pointed at deploy stack's published port 8000 (no Docker network gymnastics) | Pitfall 7 | Low — Stripe CLI is a host-installed Go binary; port 8000 is already published in deploy/docker-compose.prod.yml |
| A7 | `flutter_appauth` and the existing OAuth flow do not conflict with `flutter_inappwebview` | Mobile additions | Low — different packages, different purposes; flutter_appauth uses ASWebAuthenticationSession (iOS) and Custom Tabs (Android) separate from in-app WebView. Wave 0 mobile spike confirms |
| A8 | The recommended `stripe>=15.0,<16.0` ceiling tracks the current major; v16 hasn't released as of May 8, 2026 | AMD-01 | Low — PyPI shows 15.x latest; v16 release would be a planning-time check |

## Open Questions

These are items the planner must surface for user confirmation OR the Wave 0 spike must answer empirically before plans seal.

1. **Pro tier price.**
   - What we know: D-Discretion says "$/mo deferred — Stripe-side config". CONTEXT pricing strategy memory anchors $9-$15.
   - What's unclear: The exact dollar amount.
   - Recommendation: User decides at Stripe-dashboard time. Plan refers to it as `AP_STRIPE_PRICE_ID_PRO_MONTHLY` only; no code constant.

2. **Mobile deep-link scheme for Checkout return.**
   - What we know: AP already uses `solvrlabs://oauth/github` (per CLAUDE.md). A new path under the same scheme is consistent.
   - What's unclear: Should we use `solvrlabs://billing/success?session_id={CHECKOUT_SESSION_ID}` (deep link, AppLinks/UniversalLinks) OR a webview-internal sentinel URL like `https://app.solvrlabs.com/billing/success` that the InAppWebView intercepts in shouldOverrideUrlLoading?
   - Recommendation: **Webview-internal sentinel URL** is simpler — no platform-specific manifest config, no AppLinks/UniversalLinks plumbing. The `success_url` passed to Stripe is `https://app.solvrlabs.com/billing/return-success?session_id={CHECKOUT_SESSION_ID}`; the InAppWebView's `shouldOverrideUrlLoading` callback intercepts the redirect before the page loads, pops the screen with a Result. This is the canonical 2026 community pattern. Wave 0 mobile spike confirms.

3. **`reconcile_stripe_workflow` query window.**
   - What we know: 5-min interval (D-Discretion).
   - What's unclear: Does each invocation query ALL `payment_intents` since now-5min, or since last successful run? Latter requires state.
   - Recommendation: Query `now-15min` window (3× redundancy on the schedule period); idempotency via `stripe_webhook_events` UNIQUE makes re-processing safe. No state needed.

4. **Negative-balance display on mobile.**
   - What we know: D-16 allows negative balance until admin write-off.
   - What's unclear: What does the AppBar ticker show for `balance_cents = -342`?
   - Recommendation: Server returns `display_balance_cents=0` AND `is_negative=true`. Mobile shows "$ 0.00 ⚠" with tap → modal explaining "Refund processed; please top up to resume" + "Contact support for write-off review".

5. **Pro downgrade auto-pause: which 4 agents?**
   - What we know: D-15 says "4 oldest active agents are auto-paused".
   - What's unclear: "Oldest" by `created_at`? `last_activity`? Random? What status enum?
   - Recommendation: Order by `agent_instances.created_at ASC`; LIMIT 4. Status enum: introduce `'auto_paused'` value (additive to whatever current values exist). Wave 0 schema spike confirms current `agent_instances.status` enum values. The user can manually unpause one or delete some after downgrade.

6. **Refund event payload — partial vs full?**
   - What we know: `charge.refunded` (D-14, D-16).
   - What's unclear: Stripe supports partial refunds. Does D-16's "credit revocation" mean full refund only, or do we negate the partial amount?
   - Recommendation: Read `charge.amount_refunded` (cumulative) — minus prior refund ledger rows for this charge — gives the delta to negate. UNIQUE on `(reference_id, reference_type='stripe_refund', refund_event_id)` keeps partials idempotent.

7. **Tax-on-credit-pack vs tax-on-LLM-cost.**
   - What we know: Stripe Tax handles tax on the Checkout transaction (D-Discretion).
   - What's unclear: When the user's $25 pack delivers $25 of credits, is the user taxed on the $25 OR is the $25 tax-inclusive (so they get $22 of credits)? Affects D-07 1:1 grant.
   - Recommendation: Stripe Tax adds tax on TOP of the line-item amount by default (not inclusive). The user pays $25 + tax; gets 25 credit_cents. D-07's 1:1 invariant holds for the line-item amount, not the post-tax total. Document in `B-HUMAN-UAT.md` so manual UAT verifies.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Stripe (test-mode) | Wave 0 spike + integration tests | Pending user action (D-10) | TEST mode | None — blocks Wave 0 if absent |
| Stripe CLI | Local webhook forwarding | Probably absent on dev box (`brew install stripe/stripe-cli/stripe`) | latest | None — required for D-22 integration shape |
| Docker Engine | Already running deploy stack | ✓ (deploy stack ships) | 24+ | — |
| `stripe/stripe-mock` Docker image | Unit tests (shape only) | Pull at first test run | 0.199.0 | Hand-rolled fixtures (D-22 requires anyway) |
| Postgres 17 | Already running deploy stack | ✓ | 17.x | — |
| Temporal cluster | Already running deploy stack | ✓ | 1.27.x SDK | — |
| `temporalio` Python | Already in pyproject | ✓ | 1.27.0 | — |
| `flutter_inappwebview` | Mobile billing flow | NOT in pubspec.yaml | latest | `webview_flutter` (acceptable but lower-quality redirect interception per AMD-03) |
| `stripe` Python SDK | All api_server billing code | NOT in pyproject.toml | 15.1.0 | None — required |
| OpenRouter | Phase 31 e2e regression | ✓ (already wired) | — | — |

**Missing dependencies with no fallback:**
- Stripe TEST keys + Webhook secret (user-side; D-10 explicit)
- `stripe` Python SDK (Phase B introduces)
- Stripe CLI on host (`brew install`)
- `flutter_inappwebview` (Phase B introduces)

**Missing dependencies with fallback:**
- `webview_flutter` over `flutter_inappwebview` (AMD-03 documents the trade)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (api_server) | pytest 8.x + pytest-asyncio + testcontainers (Postgres) + respx + Temporal `WorkflowEnvironment` (Phase 28 fixture) |
| Framework (mobile) | flutter_test + http_mock_adapter (existing) + `golden_toolkit` (existing) |
| Config file (api_server) | `api_server/pyproject.toml` `[tool.pytest.ini_options]` |
| Config file (mobile) | `mobile/test/` + `mobile/integration_test/` |
| Quick run command | `cd api_server && uv run pytest tests/test_billing_*.py -x` |
| Full suite command (api_server) | `cd api_server && uv run pytest -m 'not e2e_money_path'` |
| Full suite command (mobile) | `cd mobile && flutter test` |
| Phase B e2e gate | `make e2e-phase-b-stripe` (NEW Make target — runs against real Stripe TEST mode + signed-fixture webhooks) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | `users.tier` enum + backfill | unit (alembic round-trip) | `pytest tests/test_migration_014_phase_b.py -x` | ❌ Wave 0 |
| D-04 | Webhook handler is sole tier writer | integration (Stripe TEST event triggers tier flip; non-webhook routes can't flip tier) | `pytest tests/test_billing_webhook.py::test_subscription_created_flips_tier -x` | ❌ Wave 0 |
| D-05 | Pro slot cap (5) at agent.create | unit (mock pool, return tier='pro' + count(active)=5 → 403) | `pytest tests/test_tier_enforcement.py::test_pro_caps_at_5 -x` | ❌ Wave 0 |
| D-05 | Pro retention 30d filter on messages.list | unit (insert old + new rows; tier='pro'; assert old filtered) | `pytest tests/test_messages_list.py::test_retention_window_pro -x` | ❌ Wave 0 |
| D-09 | prune_messages workflow deletes >7d for free / >30d for pro | integration (Temporal WorkflowEnvironment + Postgres testcontainer) | `pytest tests/test_prune_messages_workflow.py -x` | ❌ Wave 0 |
| D-12 | Pre-flight 402 when tier='ultra' AND balance < 1 | integration (testcontainers Postgres + respx mocking upstream) | `pytest tests/test_llm_proxy_402.py -x` | ❌ Wave 0 |
| D-13 | Debit only on success | integration (Temporal WorkflowEnvironment; assert ledger row absent on failed forward) | `pytest tests/test_debit_balance_activity.py::test_no_debit_on_failure -x` | ❌ Wave 0 |
| D-14 | All 8 webhook events handled idempotently | integration (signed fixtures fire same event twice; assert exactly one side-effect) | `pytest tests/test_billing_webhook.py::test_idempotent_redelivery -x` | ❌ Wave 0 |
| D-15 | cancel_at_period_end → grace, then auto-pause 4 oldest | integration (subscription.deleted fixture + assert agent statuses) | `pytest tests/test_pro_downgrade.py -x` | ❌ Wave 0 |
| D-17 | Atomic ledger debit+balance update in same tx | unit + integration (Postgres testcontainer; concurrent debits) | `pytest tests/test_ledger_atomic.py -x` | ❌ Wave 0 |
| D-17 | Reconcile drift detection | integration (corrupt cache; run nightly reconcile workflow; assert Sentry event emitted) | `pytest tests/test_reconcile_ledger_workflow.py -x` | ❌ Wave 0 |
| D-21 | Mobile 402 modal flow | widget test (mock 402 response → assert modal shown) | `flutter test test/features/billing/insufficient_credits_modal_test.dart` | ❌ Wave 0 |
| D-21 | Mobile webview redirect interception | manual + integration_test (Stripe TEST webview manual UAT) | `flutter test integration_test/billing_webview_test.dart` | ❌ Wave 0 — manual primary |
| D-22 | Webhook signature verification | unit (signed fixtures; bad sig → 400) | `pytest tests/test_billing_webhook.py::test_signature_required -x` | ❌ Wave 0 |
| D-25 (exit gate) | Free → Ultra → message → debit → drained → 402 | e2e (`make e2e-phase-b-stripe`) | `make e2e-phase-b-stripe` | ❌ Wave 5 |

### Sampling Rate
- **Per task commit:** `cd api_server && uv run pytest tests/test_billing_*.py -x` (api_server) + `cd mobile && flutter test test/features/billing/ test/features/usage/` (mobile)
- **Per wave merge:** Full suite (`uv run pytest -m 'not e2e_money_path' && flutter test`)
- **Phase gate:** `make e2e-phase-b-stripe` GREEN against real Stripe TEST mode AND `make e2e-money-path` (Phase 31 H8) GREEN (regression gate — Phase B must not break Phase 31's money path)

### Wave 0 Gaps

These artifacts must exist before Wave 1 starts coding:

- [ ] `tests/conftest.py` extension — `stripe_client_test` fixture (StripeClient pointed at stripe-mock OR real TEST per pytest mark)
- [ ] `tests/_fixtures/stripe_webhooks/` directory — signed fixture files for each event in D-14
- [ ] `tests/_fixtures/sign_webhook.py` — helper that produces `Stripe-Signature` header from raw payload + secret
- [ ] `api_server/Makefile` target `e2e-phase-b-stripe` (mirrors `e2e-money-path` from Phase 31)
- [ ] `pytest.ini` marker `phase_b_e2e` (so `pytest -m 'not phase_b_e2e'` excludes the real-Stripe runs from default suite)
- [ ] CI workflow `.github/workflows/e2e-phase-b.yml` running `make e2e-phase-b-stripe` against `secrets.AP_STRIPE_TEST_API_KEY`
- [ ] Webhook URL exposure for CI: GH Actions runs the deploy api_server container locally, uses `stripe trigger` to fire events at `localhost:8000/v1/billing/webhook`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing `require_user` dep on all `/v1/billing/*` except `/v1/billing/webhook`. Webhook authentication is via Stripe signature, not user session. |
| V3 Session Management | inherited | Phase B does not change session handling. D-18 lazy tier read piggy-backs on existing `get_current_user`. |
| V4 Access Control | yes | `users.stripe_customer_id` lookups are scoped to `request.state.user_id`. Cross-tenant probe defense via WHERE-clause user filter (not 404 vs 200 distinction). |
| V5 Input Validation | yes | All new request bodies use Pydantic models. `pack_id` validated against `PACKS` allow-list. Webhook payload bytes are signature-verified BEFORE parse. |
| V6 Cryptography | yes | NEVER hand-roll HMAC; use `client.construct_event`. NEVER store Stripe API keys in DB or logs (they live only in env-loaded Settings). Webhook secrets follow same handling as `AP_OAUTH_*`. |
| V7 Error Handling | yes | Stripe API errors classified per Phase 22c error envelope shape (`make_error_envelope(...)`); details NEVER leak to client. |
| V8 Data Protection | yes | `stripe_customer_id` is not PII alone; combined with email it is. Masked in logs. Refund ledger rows must NOT include card last4 — Stripe webhook payload includes some card info; do NOT persist beyond what's needed (amount + ID). |
| V13 API and Web Service | yes | Webhook endpoint is public-internet (per H7); rate-limited (already covered by middleware/rate_limit.py — add `/v1/billing/webhook` to a new bucket OR exclude since Stripe-only — confirm with planner). |

### Known Threat Patterns for FastAPI + Stripe

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Webhook replay | Tampering | `stripe_webhook_events.stripe_event_id` UNIQUE constraint + 5-min timestamp tolerance from SDK |
| Webhook signature forgery | Spoofing | `client.construct_event` verifies HMAC-SHA256 in constant time |
| Cross-tenant balance read | Information disclosure | `WHERE user_id = $1` on every billing read; never accept user_id from request body |
| Race on lazy customer create | Tampering | `SELECT ... FOR UPDATE` on `users` row before customer creation |
| Negative balance to bypass paywall | Tampering | The 402 gate predicate `balance_cents < 1` (D-12) catches negatives too — `<1` is true for any value below 1 including negatives. Cross-checked. |
| Promo code abuse | Tampering | Stripe-side limits (max redemptions, expiry, customer-specific coupons) — D-24 leaves enforcement to Stripe |
| Idempotency key reuse with different params | Tampering | Stripe's own idempotency cache rejects mismatched bodies; SDK auto-retries with same key |
| Logged BYOK / Stripe key leak | Information disclosure | Inherit Phase 29 `_redact_creds(...)` pattern; extend to redact `sk_live_*` / `sk_test_*` / `whsec_*` if any code path could log them |
| Webhook handler latency exceeds Stripe's tolerance | DoS | Webhook handler does signature + dedupe + side-effect synchronously; if a side-effect risks >10s, defer it to a Temporal workflow and return 200 immediately. (Current scope: all side-effects are sub-second — UPDATE + INSERT statements.) |

## Sources

### Primary (HIGH confidence)
- [Stripe Python SDK on PyPI (live JSON query 2026-05-08)](https://pypi.org/pypi/stripe/json) — confirmed latest: `15.1.0`, requires Python `>=3.9`
- [stripe-python releases on GitHub](https://github.com/stripe/stripe-python/releases) — confirmed v15.x is current line; v8 is multiple majors stale
- [Migration guide for v8 (StripeClient)](https://github.com/stripe/stripe-python/wiki/Migration-guide-for-v8-(StripeClient)) — confirmed StripeClient pattern + `client.construct_event` signature
- [Stripe webhooks documentation](https://docs.stripe.com/webhooks) — confirmed raw-bytes requirement, 5-min timestamp tolerance, header `Stripe-Signature`
- [Stripe CLI listen reference](https://docs.stripe.com/cli/listen) — confirmed `--forward-to` semantics + signing secret returned on first listen
- [stripe-mock GitHub README](https://github.com/stripe/stripe-mock) — confirmed: validates request shapes only; no webhook simulation; latest 0.199.0 (May 7, 2026)
- [stripe-mock Issue #16](https://github.com/stripe/stripe-mock/issues/16) — confirms webhook support is a long-open feature request, not current functionality
- [Temporal Python schedules docs](https://docs.temporal.io/develop/python/schedules) — confirmed `Schedule + ScheduleSpec + ScheduleActionStartWorkflow` API
- [Stripe idempotent requests reference](https://docs.stripe.com/api/idempotent_requests) — confirmed Idempotency-Key behavior (24h cache; SDK auto-generates)
- [stripe-go Issue #1771 (metadata propagation)](https://github.com/stripe/stripe-go/issues/1771) — confirmed AMD-05 finding: metadata only on the event whose object carries it
- MSV reference: `/Users/fcavalcanti/dev/meusecretariovirtual/api/internal/repository/web_user_repo.go:562` — atomic credit pattern direct read
- MSV reference: `/Users/fcavalcanti/dev/meusecretariovirtual/api/internal/service/poken_service.go:180` — atomic debit pattern direct read
- MSV reference: `/Users/fcavalcanti/dev/meusecretariovirtual/api/internal/service/payment_poller.go:1-120` — payment poller shape (Phase B uses Temporal cron equivalent)
- AP local code: `api_server/src/api_server/routes/llm_proxy.py:172-203` — confirms `cost_usd` already includes ap_multiplier at proxy time
- AP local code: `api_server/src/api_server/temporal/workflows/dispatch_message.py:190-205` — Phase 28 D-22 contract for debit_balance call
- AP local code: `api_server/src/api_server/temporal/activities/debit_balance.py` — current "0" stub Phase B replaces
- AP local code: `api_server/src/api_server/temporal/worker.py` — pattern for adding workflows + activities + (new) schedule registration
- AP local code: `api_server/alembic/versions/013_phase29_proxy_columns.py` — migration shape for 014
- AP local code: `api_server/alembic/versions/010_usage_logs_cost_weights.py` — confirms `cost_weights.ap_multiplier` exists; data migration only (no schema change)
- AP local code: `mobile/lib/features/usage/usage_ticker_widget.dart` — extension point for tier-aware ticker

### Secondary (MEDIUM confidence)
- [Stripe Webhooks complete guide 2026 (Hooklistener)](https://www.hooklistener.com/learn/stripe-webhooks-implementation) — implementation guide, FastAPI-shaped patterns, 2026-current
- [Webhook signature verification 2026 (HookRay)](https://hookray.com/blog/webhook-signature-verification-2026) — confirms Stripe's HMAC pattern
- [Practical FastAPI webhook receiver guide](https://blog.greeden.me/en/2026/04/07/a-practical-guide-to-safely-implementing-webhook-receiver-apis-in-fastapi-from-signature-verification-and-retry-handling-to-idempotency-and-asynchronous-processing/) — FastAPI-specific webhook patterns + ack-fast-then-process advice
- [Stripe CLI + Docker Compose blog (2025)](https://martinbean.dev/blog/2025/08/15/using-the-stripe-cli-with-docker-compose/) — community pattern; confirms host-tunnel approach
- [Stripe Checkout in Flutter mobile (Fidev)](https://fidev.io/stripe-in-flutter-mobile/) — confirms WebView + navigationDelegate redirect interception pattern
- [InAppWebView feature comparison vs webview_flutter (Codemagic)](https://blog.codemagic.io/inappwebview-the-real-power-of-webviews-in-flutter/) — confirms AMD-03 rationale
- [Stripe Smart Retries documentation](https://docs.stripe.com/billing/revenue-recovery/smart-retries) — confirms automatic retry-then-deletion failure flow

### Tertiary (LOW confidence)
- Stripe Flutter crash article (Anab Khan, Apr 2026) — flagged for Open Question: external-browser-vs-webview tradeoff. Not blocking; D-21 explicitly picks webview.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified directly against PyPI; AMD-01 corrects an outdated CONTEXT pin
- Architecture (webhook + ledger + Temporal cron): HIGH — patterns are MSV-proven, AP-current, and Stripe-documented
- Mobile webview: MEDIUM — `flutter_inappwebview` redirect interception is community-validated for 2026 but exact callback API is package-specific; Wave 0 mobile spike confirms
- stripe-mock capabilities (D-22 inaccuracy): HIGH — multiple primary sources confirm webhook simulation absence
- Pitfalls: HIGH — Pitfalls 1, 2, 3, 7 are direct AP-context applications; Pitfalls 4, 5, 8 are MSV-precedent-shaped
- Open questions: MEDIUM — most have a clear default recommendation; user confirmation on dollar amounts and deep-link scheme

**Research date:** 2026-05-08
**Valid until:** 2026-06-08 (30 days for stable Stripe substrate). The mobile webview package and SDK majors should be re-checked at planning-time if the gap exceeds this window.

## RESEARCH COMPLETE

Key files written:
- **`.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md`** (this file)

Critical findings for orchestrator:
1. **AMD-01..AMD-05** in CONTEXT.md need amendment before `/gsd-plan-phase`. The five amendments are listed near the top of RESEARCH.md and copy verbatim into CONTEXT.md when the user accepts.
2. **`stripe-mock` cannot test webhooks** — D-22 wording requires correction (AMD-02). Tests use signed fixtures + Stripe TEST mode.
3. **Stripe Python SDK pin is two majors stale** — bump to `stripe>=15.0,<16.0` (AMD-01).
4. **8 Wave 0 spike candidates identified** in Validation Architecture; the planner converts these into the Wave 0 plan.
5. **macOS dev workflow is unchanged from Phase 31** — Stripe CLI on host, deploy stack rebuild, no native uvicorn.

Confidence: HIGH overall. The phase is well-bounded, has clear MSV precedents, and most decisions are already locked. The 5 amendments are research-revealed corrections, not philosophical reframes.
