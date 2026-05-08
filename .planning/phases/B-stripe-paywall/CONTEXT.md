# Phase B: Stripe Paywall — Context

**Gathered:** 2026-05-08
**Status:** Ready for planning
**Supersedes:** the 2026-05-07 kick-start CONTEXT.md (pre-discuss handoff). Phase 31 SHIPPED 2026-05-08, materially changing the gate picture; locked decisions below replace the kick-start's "5 open decisions + GATE choice" section.

<domain>
## Phase Boundary

Phase B adds a **platform-billed credit tier** (called `ultra`) and a **paid BYOK subscription tier** (called `pro`) on top of the existing AP substrate. **BYOK Free + Pro tiers stay entirely free of LLM-call money flow** — Phase A's USD ticker remains canonical for them. Phase B carries TWO Stripe surfaces:

1. **Subscription product** for `pro` (fixed $/mo; unlocks 5 active agents + 30d retention; LLM still paid via the user's own provider key — sub does NOT gate LLM calls)
2. **Credit Checkout** for `ultra` (one-time top-up packs; AP fronts the LLM key; pre-flight 402 + atomic debit gates every call)

**Out of scope (deferred):**
- Web frontend surfaces — Phase B.2
- Multi-currency (USD-only for Phase B)
- Live webhook delivery / production rollout — gated on H7 (Hetzner deploy)
- Branded receipts / invoicing UI (Stripe's auto-receipts cover v1)
- Multiple paid subscription tiers beyond Pro (schema accommodates; product surface defers)
- New marketing dollar amounts for Pro $/mo (Stripe-side config; not a code constant)

</domain>

<decisions>
## Implementation Decisions

### Tier Model

- **D-01:** `users.tier` is a TEXT column with three exclusive enum values: `free | pro | ultra`. Migration 014 backfills every existing user to `'free'`.
- **D-02:** Tier semantics:
  - `free` — BYOK, no money flow, 1 active agent, 7d message retention
  - `pro` — BYOK + paid Stripe **subscription** (fixed $/mo); 5 active agents, 30d retention; LLM calls still bill against the user's own provider key (visibility-only metering, like Free)
  - `ultra` — Platform-billed; AP fronts the LLM provider key; Stripe Checkout one-time **credit packs**; pre-flight 402 + atomic debit-on-success gates every LLM call; unlimited agents + unlimited retention
- **D-03:** Phase B implements BOTH Stripe surfaces (subscription product + credit Checkout). They share the `stripe_webhook_events` idempotency table and `users.stripe_customer_id` linkage column, but otherwise their workflows are independent.
- **D-04:** Tier transitions are **Stripe-event-driven**. The webhook handler is the **sole writer** of `users.tier`. Mechanism: `customer.subscription.{created,updated,deleted}` + `invoice.paid`/`invoice.payment_failed` flip pro↔free; `checkout.session.completed` for a credit pack flips free→ultra (and is also the trigger for the first balance top-up). `users.tier` is never set by an end-user-facing endpoint.
- **D-05:** Pro entitlements (enforced in API at `agent.create` and `messages.list`):
  - Active-agent slot count: `free=1 / pro=5 / ultra=∞`
  - Message retention window: `free=7d / pro=30d / ultra=unlimited`

### Pricing Knobs

- **D-06:** Credit-pack catalog (hardcoded code-side; single SOT in api_server, NOT duplicated to mobile — mobile fetches via `GET /v1/billing/packs`):
  - 5 packs: $5, $10, $25, $50, $100
  - Each pack: `{ id: str, label: str, usd_amount_cents: int, credit_cents: int, stripe_price_id: str }`
- **D-07:** Top-up grants are **1:1 USD→credit** (`credit_cents = usd_amount_cents`). The markup lives only in `cost_weights.ap_multiplier` on the **debit** side, never on the credit-grant side. (Avoids the MSV "75% post-facto discount hybrid" anti-pattern.)
- **D-08:** Phase B default `ap_multiplier` = **1.15** (15% markup; covers Stripe ~3% + OpenRouter ~5% + ~7% margin headroom). Admin-mutable per row in `cost_weights` table; per-provider tuning is supported by the existing column without code changes.
- **D-09:** Daily Temporal scheduled workflow (`prune_messages_workflow`) hard-deletes `inapp_messages` rows older than `users.tier` retention window. One Temporal schedule + one activity. Reuses existing Temporal substrate from Phase 28.

### Stripe Substrate

- **D-10:** Solvr Labs Stripe account exists or will be created out-of-band by the user. Plan-phase assumes Stripe **TEST**-mode keys are available before Wave 0 spike. Live-mode keys arrive when Phase B exits to staging (gated on H7).
- **D-11:** Stripe **Customer** record is created **lazily** on first Stripe-affecting interaction (Pro Checkout click OR Ultra credit-pack click). `users.stripe_customer_id` stays NULL for Free users. Customer has metadata `{ ap_user_id: <uuid> }` for cross-reference.
- **D-12:** **Pre-flight 402 estimation**: a flat **floor** of 1¢. If `tier='ultra' AND balance_cents < 1` → return 402 immediately, do not forward to upstream. Real cost is debited post-hoc from the upstream `usage` block. (Token-count tokenizer adds 50–200ms with no proven win for v1.)
- **D-13:** **Debit only on success.** If upstream returns non-2xx OR no `usage` block was captured, debit_amount = 0. Mid-stream failures with partial tokens still debit 0 in v1 (pro-rata is deferred to Phase B.1 if it surfaces real complaints).
- **D-14:** Webhook event matrix (full set Phase B handles):
  - `checkout.session.completed` — terminal state for one-time credit pack
  - `customer.subscription.created` / `customer.subscription.updated` / `customer.subscription.deleted` — Pro tier flips
  - `payment_intent.succeeded` / `payment_intent.payment_failed` — top-up payment lifecycle (succeeded backs the credit grant; failed informs UX)
  - `invoice.paid` — Pro renewal succeeded (no DB change required; logged for audit)
  - `invoice.payment_failed` — Pro renewal failed (Stripe retries automatically; if final retry fails Stripe emits `subscription.deleted` which downgrades)
  - `charge.refunded` — credit revocation (see D-16) or Pro-period refund
- **D-15:** Pro → Free **downgrade** behavior:
  - Stripe default `cancel_at_period_end=true` — existing 5 agents continue running until end of billing period
  - At period end (`subscription.deleted` webhook) — `users.tier` flips to `'free'`
  - The 4 oldest active agents are **auto-paused** (not deleted; user can resubscribe to restore them, or delete them down to 1)
  - New `agent.create` is blocked at the moment tier flips (cap=1)
- **D-16:** **Refund / chargeback** (`charge.refunded`):
  - Insert a `credit_transactions` row with `kind='refund'`, `amount_cents = -original_amount`, `reference_id = stripe_charge_id`, `reference_type = 'stripe_refund'`
  - Balance cache rebuilds from SUM; if user already spent some credits, balance goes negative
  - Negative balance triggers 402 on every subsequent call until balance ≥ 1¢
  - `users` gets a sticky `refund_writeoff_cents BIGINT DEFAULT 0` column; admin tooling can flip a write-off (adds a positive ledger row of `kind='admin_writeoff'`) if a dispute is decided in user's favor

### Architecture

- **D-17:** **Ledger-as-truth.** `credit_transactions` is the only source of truth for balance. `credit_balances.balance_cents` is a denormalized cache for fast reads, rebuilt by every debit/credit transaction in the same DB transaction (`UPDATE credit_balances SET balance_cents = (SELECT COALESCE(SUM(amount_cents),0) FROM credit_transactions WHERE user_id=...) WHERE user_id=...`). Mirrors MSV `web_user_repo.go:562` + `poken_service.go:180`. A nightly reconciliation Temporal cron re-derives the cache from the ledger and logs drift; mismatches become Sentry alerts (Phase 31 H6 already wired).
- **D-18:** **Tier propagation across sessions = lazy re-read.** `get_current_user` reads `users.tier` fresh on every authenticated request (no caching, no pub/sub). Tier change reflected within the latency of the next API call. H2 (logout-everywhere) is **not** revived for Phase B. Mobile UI's existing UsageTickerWidget polls `/v1/usage/summary` periodically — that path picks up tier changes for free.

### Sequencing & Scope

- **D-19:** Phase B **starts now** (local substrate). Migrations + endpoints + activity body + mobile UI land against Stripe **TEST** mode + local webhook (`stripe listen → http://localhost:8000/v1/billing/webhook`). **Live webhook delivery requires HTTPS/H7** (Hetzner deploy) — that's the production gate, not a code gate. The 4 manual UAT items from Phase 31 (`31-HUMAN-UAT.md`) clear in parallel and don't block Phase B.
- **D-20:** Phase B scope = **api_server + mobile only**. Web frontend gets the same surfaces in **Phase B.2**. v0.3 milestone (Solvr Labs Mobile MVP) keeps its mobile-first focus.

### Mobile UX

- **D-21:** **402 mobile UX**: blocking modal "Out of credits" with primary "Top up" CTA → opens pack picker → Stripe Checkout webview → on return, mobile polls `GET /v1/billing/balance` until `balance_cents` reflects the top-up (5–15s typical via webhook; backstopped by 5-min poller). Inflight UI: lock the trigger + spinner + mm:ss timer + success/failure SnackBar (mirror `deploy_step.dart` pattern; lesson from `feedback_inflight_ui_for_long_awaits.md`).

### Test Strategy

- **D-22:** Two-tier test substrate:
  - **Unit** tests use `stripe-mock` (Stripe-blessed in-memory mock; deterministic; speaks HTTP). Used for fast feedback on route handlers, webhook idempotency, debit math.
  - **Integration + e2e** use **real Stripe TEST mode** (free, public, identical API surface to live). CI runs against TEST keys via a GH Actions secret (`AP_STRIPE_TEST_API_KEY`, `AP_STRIPE_TEST_WEBHOOK_SECRET`). Mirrors the Phase 31 H8 "real OpenRouter in CI" shape.
  - `respx` for HTTP isolation in unit tests (already in stack from Phase 22c spike).

### Scope Locks

- **D-23:** **USD only.** No currency column on `credit_transactions`/`cost_weights`. Multi-currency is a future phase.
- **D-24:** **Stripe promo codes enabled** (`allow_promotion_codes=true` on every Checkout session). Marketing mints codes in the Stripe dashboard with zero AP-side code. Promo redemption is reflected in webhook payload; ledger captures the discounted amount.
- **D-25:** **Phase B exit gate** = `PHASE-B-EXIT-GATE-PASSED` marker requires BOTH:
  1. Automated CI e2e (stripe-mock + real Stripe TEST in the GH workflow): Free user signs up → upgrades to Ultra via Checkout → sends a chat message → `usage_logs` row appears with non-zero `cost_usd` → ledger debit row with `cost_usd * 100 * ap_multiplier` cents → fourth call drains balance → fifth call returns 402
  2. Manual UAT in `B-HUMAN-UAT.md` walking the same flow against real Stripe TEST mode + Stripe CLI webhook forwarding. Mirrors Phase 31's split-gate shape.
- **D-26:** Migration 014 backfills `users.tier='free'`. Tier-change audit reuses `credit_transactions` with a new `kind='tier_change'` value (`amount_cents=0`, `reference_id=stripe_event_id`, `reference_type='stripe_event'`). One ledger covers all billing-relevant audit; no separate `audit_log` table.

### Claude's Discretion

These are mechanical conventions; flagged here so downstream agents don't churn on them but no user input was needed:

- **Env var naming** (matches existing `AP_*` convention, MSV-shaped): `AP_STRIPE_API_KEY`, `AP_STRIPE_WEBHOOK_SECRET`, `AP_STRIPE_PRICE_ID_PRO_MONTHLY` (and one `AP_STRIPE_PRICE_ID_*` per credit pack). Loaded via existing pydantic Settings; placeholder fallback in dev mirrors the `oauth_X missing in dev; using placeholder` pattern.
- **SDK pin**: `stripe>=15.0,<16.0` Python SDK in `api_server/pyproject.toml` (see AMD-01 below — research verified PyPI latest=15.1.0 on 2026-05-08; v8 was 2 majors stale). Lockfile via `uv` (consistent with Phase 31 `sentry-sdk` and Phase 28 `temporalio` pins). v15 carries the StripeClient service pattern + Billing Credit Balance + Meter Events APIs.
- **Reconciliation poller**: 5-min Temporal scheduled workflow (`reconcile_stripe_workflow`); polls Stripe for `payment_intent.succeeded` events older than 5min not yet in `stripe_webhook_events`. Backstops missed webhooks. Mirrors MSV `payment_poller.go` shape but as a Temporal cron rather than a separate scheduler.
- **Webhook idempotency**: `stripe_webhook_events.stripe_event_id` UNIQUE constraint; on duplicate event id, return 200 immediately (Stripe will stop retrying). Same DB transaction as the side-effect (subscription state flip, ledger insert).
- **Decimal contract**: `debit_balance` activity preserves the Decimal-to-string return contract from Phase 28 D-22 (Temporal JSON serializer can't handle `Decimal`; stringified-decimal recovers losslessly via `Decimal(str)`).
- **Tax computation**: Stripe Tax auto-handles VAT/sales-tax. AP doesn't compute tax. Stripe-side config; out-of-band of code.
- **Receipts**: Stripe's auto-emails are the v1 receipt path. No AP-side branded receipt rendering. Future phase if customers ask.
- **Webhook handler placement**: `api_server/src/api_server/routes/billing_webhook.py` (new file). Public route, no auth dependency, signature-verified via the StripeClient service pattern (see AMD-04).

### Amendments (post-research, 2026-05-08)

Per `feedback_amend_context_post_research.md`, research surfaced 5 corrections to the locked decisions before plan-phase consumes this file. Treat each AMD as load-bearing as the original decision.

- **AMD-01 (supersedes "SDK pin" line above):** Pin `stripe>=15.0,<16.0`, NOT `>=8.0,<9.0`. PyPI verified 2026-05-08: latest stable = 15.1.0 (released 2026-04-24). v8 is the legacy module-level static-method API; v9+ introduced the `StripeClient` service pattern. Pinning v8 commits to a deprecation-track surface and misses three years of upstream fixes. The Billing Credit Balance + Meter Events APIs cited in the original line all remain available in v15.
- **AMD-02 (refines D-22):** Strike "webhook idempotency" from the stripe-mock bullet. stripe-mock validates request shapes only — it does NOT emit webhook events (verified via stripe-mock README + Issue #16, open since 2017). Webhook handler signature-verify + idempotency tests use **hand-rolled signed fixtures**: build a raw JSON payload, compute `Stripe-Signature` header as `t=<unix>,v1=<hmac_sha256(secret, f"{t}.{payload}")>`, POST to the route. stripe-mock keeps the role of validating outbound Stripe SDK calls (Customer/Checkout/Subscription create); it has no part in inbound-webhook tests.
- **AMD-03 (binds D-21 to a concrete package):** Mobile webview package = **`flutter_inappwebview`** (NOT `webview_flutter`). flutter_inappwebview's `navigationDelegate` URL interception is the documented 2026 community pattern for Stripe Checkout return-URL handshake; webview_flutter has open HTTPS-redirect interception issues (flutter/flutter#70284). Verified neither is in `mobile/pubspec.yaml` today — Phase B introduces. Pin: `flutter_inappwebview: ^6.1.5` (verify latest at planning-time).
- **AMD-04 (new decision):** Webhook handler MUST use the **service-based SDK pattern** — `StripeClient(api_key).webhooks.construct_event(payload, signature, secret)` — NOT the legacy module-level `stripe.Webhook.construct_event(...)`. Both ship in v15.x; the latter is documented as deprecated. Future-proofs the call site for new endpoints that land only on the StripeClient pattern.
- **AMD-05 (refines D-14):** For credit-pack top-ups, listen to **`checkout.session.completed` ONLY**, NOT also `payment_intent.succeeded`. Reason: `checkout.session.completed` carries the session-level `metadata` (where `pack_id` lives); `payment_intent.succeeded` does not unless metadata is double-attached. Listening to both creates a double-credit risk that must be defended against in idempotency code. `payment_intent.payment_failed` IS still in the matrix (for failure UX); `payment_intent.succeeded` is acknowledged-without-side-effect or dropped.

**D-14 webhook matrix as amended:**
- `checkout.session.completed` — credit pack one-time top-up succeeded (sole writer of credit grants)
- `payment_intent.payment_failed` — top-up failed (UX surface only; no DB mutation)
- `customer.subscription.created` / `customer.subscription.updated` / `customer.subscription.deleted` — Pro tier flips (D-04)
- `invoice.paid` — Pro renewal succeeded (logged for audit; no DB mutation needed)
- `invoice.payment_failed` — Pro renewal failed (Stripe smart-retries; final failure → `subscription.deleted`)
- `charge.refunded` — credit revocation (D-16)
- ~~`payment_intent.succeeded`~~ — DROPPED per AMD-05 (redundant with `checkout.session.completed`; double-credit risk)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project memory (load in this order)

- `memory/MEMORY.md` — auto-memory index
- `memory/project_pricing_strategy.md` — locked bimodal model + 2026 industry comparison + user's exact pushback
- `memory/project_phase_27_constraints.md` — Phase A locked constraints + Phase B carry-overs (provider-agnostic UsageRecorder, cost_weights table, AppBar USD ticker)
- `memory/project_phase_31_shipped.md` — gate status (H3/H4/H6/H8 ✅; 4 manual UAT pending; H7 still scripts-only)
- `memory/feedback_ap_proxy_is_not_msv_proxy.md` — why AP's proxy isn't MSV's; OpenRouter `/api/v1/generation` post-hoc + `cost_weights.ap_multiplier`
- `memory/feedback_dumb_client_no_mocks.md` — endpoint design corollary (server returns ready-to-render JSON; mobile fetches packs via API, no hardcoded catalog mirror)
- `memory/feedback_no_mocks_no_stubs.md` — Golden Rule #1 (real Stripe TEST in integration tests)
- `memory/feedback_test_everything_before_planning.md` — Golden Rule #5 (Wave 0 spike: stripe-mock + Stripe CLI listen + webhook signature verify, all hit real infra)
- `memory/feedback_no_native_uvicorn_with_deploy_stack.md` — split-brain trap; rebuild deploy api_server image, don't side-launch native uvicorn
- `memory/feedback_inflight_ui_for_long_awaits.md` — mobile inflight UI lock pattern for the Stripe Checkout return-and-poll flow
- `memory/project_solidity_audit_2026_05_04.md` — H1–H8 framing + MSV reference points (recorder.go:313-430, anthropicproxy/proxy.go, web_user_repo.go:562, payment.go:576-725, payment_poller.go, transactions-page-content.tsx)

### Existing AP code (Phase B drop-in points)

- `api_server/src/api_server/routes/llm_proxy.py` — pre-flight 402 check inserts here, after BYOK cache resolves the user's tier
- `api_server/src/api_server/services/proxy_dispatcher.py` — `PROVIDERS` table; cost-capture writes `usage_logs` rows already
- `api_server/src/api_server/routes/usage.py` — Phase A read API; `/v1/usage/summary` adds `balance_cents` field branched on tier
- `api_server/src/api_server/temporal/activities/debit_balance.py` — current `"0"` stub; Phase B replaces the body, keeps the activity name + signature byte-identical
- `api_server/src/api_server/temporal/workflows/dispatch_message.py` — call site for `debit_balance` (do NOT modify; Phase 28 D-22 lock)
- `api_server/src/api_server/middleware/rate_limit.py` — Phase 31 H3 buckets; `/v1/billing/*` routes get a new bucket here
- `api_server/src/api_server/instrumentation/sentry.py` — Phase 31 H6 wiring; new billing errors flow here automatically
- `api_server/alembic/versions/010_usage_logs_cost_weights.py` — `cost_weights.ap_multiplier` column already exists (defaults to 1.0)
- `api_server/alembic/versions/013_phase29_proxy_columns.py` — last migration; Phase B adds **014_credit_balances_and_ledger.py** (credit_balances + credit_transactions + stripe_webhook_events + users.tier + users.stripe_customer_id + users.refund_writeoff_cents)
- `api_server/src/api_server/auth/deps.py` — `get_current_user`; D-18 lazy tier read happens here
- `api_server/src/api_server/routes/auth.py` — Phase 31 buckets; mobile auth path used by tier-aware tests
- `api_server/pyproject.toml` — add `stripe>=15.0,<16.0` (per AMD-01)

### Existing AP mobile (Phase B UI extension points)

- `mobile/lib/features/usage/` — Phase A surface; balance display + transaction history + 402 modal extend this directory
- `mobile/lib/features/dashboard/dashboard_providers.dart` — current Riverpod hub; tier-aware projection for the AppBar usage ticker
- `mobile/lib/features/chat/chat_providers.dart` — 402 handler hooks here; Phase 31 H4 RetryBanner pattern is the inspiration shape (don't add a banner — show modal per D-21)
- `mobile/lib/main.dart` + `app.dart` — Phase 31 H6 Sentry user-tag wiring; tier change updates the Sentry user context too

### MSV reference points (proven patterns to inherit)

All paths in `/Users/fcavalcanti/dev/meusecretariovirtual/`:

- `recorder.go:313-430` — token parser; mirror cost-extraction shape for direct providers (already used by Phase 29)
- `anthropicproxy/proxy.go` — egress choke pattern; Phase B's pre-flight 402 check goes in our `llm_proxy.py`, same architectural role
- `web_user_repo.go:562` + `poken_service.go:180` — atomic credit/debit via DB transaction + optimistic version column (D-17 ledger-as-truth)
- `payment.go:576-725` — webhook handler shape (HMAC verify + idempotency lookup + branch on event_type)
- `payment_poller.go` — 5-min reconciliation poller; AP version is a Temporal cron, not a separate scheduler
- `transactions-page-content.tsx` — history UI shape for Phase B.2 web; mobile equivalent in `mobile/lib/features/usage/`

### MSV anti-patterns (DO NOT REPLICATE)

- Proprietary "Pokens" unit — Phase B uses **USD-cents**.
- Hardcoded catalog in 2 places (Go + frontend `lib/config.ts`) — Phase B keeps a **single SOT** in api_server (`GET /v1/billing/packs`); mobile fetches it. Per `feedback_dumb_client_no_mocks.md`.
- 75% BYOK post-facto discount hybrid — Phase B keeps a clean split: **BYOK is full visibility (no money flow), Ultra is full metering**.
- Pre-DONE SSE chunk fragility for cost capture — Phase B uses post-hoc OpenRouter `/api/v1/generation` (already what Phase 29/30 ship).

### External docs (verify SDK conventions)

- Stripe Python SDK v8 docs (https://stripe.com/docs/api?lang=python) — Customer + Checkout + Subscription + Webhook signature verification reference
- Stripe Tax auto-config (https://stripe.com/docs/tax) — D-24 promo codes + tax handling defer to Stripe-side config
- Stripe testing (https://stripe.com/docs/testing) — TEST card numbers + webhook simulation patterns for D-22

### Existing artifact

- `/Users/fcavalcanti/.claude/plans/indexed-tickling-beacon.md` (approved 2026-05-04) — original Phase A + Phase B 2-track plan; Phase A is shipped; Phase B portion is now this CONTEXT.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`cost_weights.ap_multiplier`** (migration 010) — column already exists, defaults to 1.0 across all rows. Phase B's only schema mutation here is a data-migration to set it to 1.15. Not a column add.
- **`debit_balance.debit_balance` activity + workflow call site** — Phase 28 D-22 locked the shape. The activity name, signature, return-as-string contract, and the `dispatch_message.py` `execute_activity(...)` call are all in place. Phase B only replaces the body of `activities/debit_balance.py`.
- **`/v1/usage/summary` route** — Phase A's read surface. Phase B adds a `balance_cents` field to its response when `users.tier='ultra'`. Same route, branched projection.
- **Temporal cron substrate** — Phase 28 wired the worker; Phase B adds two scheduled workflows (`prune_messages_workflow` for D-09 retention; `reconcile_stripe_workflow` for the 5-min poller).
- **Sentry instrumentation** — Phase 31 H6 wired both runtimes; billing errors flow into Sentry without new wiring. D-16 admin-writeoff and D-17 reconciliation drift become natural Sentry events.
- **Phase 31 rate-limit buckets** — `middleware/rate_limit.py` is ready for new buckets on `/v1/billing/*`.
- **Stripe customer linkage** — `users.stripe_customer_id TEXT NULL` is the only new user-table column besides `tier` and `refund_writeoff_cents`.

### Established Patterns

- **Migration shape** — `api_server/alembic/versions/013_phase29_proxy_columns.py` is the latest; Phase B's 014 follows the same alembic structure (revision/down_revision + `upgrade()` with idempotent guards + `downgrade()`).
- **Workflow + activity split** — Phase 28 patterns (deterministic workflow, side-effects in activities, retry policy `maximum_attempts=1` for best-effort like the current debit stub).
- **Webhook ingestion** — currently no webhooks land in api_server. Pattern to mirror: a single route module `routes/billing_webhook.py` mirroring MSV `payment.go`'s flow (signature verify → idempotency check → switch on event_type → side-effect in same DB tx → 200).
- **Test infra** — `api_server/tests/` already has Postgres testcontainers + respx + Temporal `WorkflowEnvironment` from Phase 28; stripe-mock + real-TEST-mode harnesses extend this.
- **Mobile inflight UI** — `mobile/lib/features/.../deploy_step.dart` lock-trigger + spinner + mm:ss + Snack pattern for any >2s backend await (Stripe Checkout return polling fits this).
- **Mobile error-classifier + RetryBanner** (Phase 31 H4) — pattern reference for the 402 path, but D-21 specifies modal not banner.

### Integration Points

- **Migration sequence** — 014 lands after 013 (last shipped). No conflicts.
- **Workflow sequence** — `dispatch_message.py` already calls `debit_balance.debit_balance` after `record_usage_activity`. Phase B's body replacement keeps this order.
- **Mobile route surface** — top-up flow is a new Flutter route (`/billing/topup`); transaction history is `/billing/history`; both reachable from the AppBar usage ticker tap (already exists in Phase A).
- **Worker process** — existing Temporal worker boots `dispatch_message_workflow`; Phase B adds two new workflows (retention prune + Stripe reconcile) registered alongside.
- **Deploy stack** — `deploy/docker-compose.prod.yml` already has Postgres + Redis + Temporal + temporal-worker + api_server + mobile; Phase B adds **no new container**. Stripe is an external API.

</code_context>

<specifics>
## Specific Ideas

- **No proprietary unit** — keep USD-cents end-to-end. The user has explicitly rejected MSV-style "Pokens" units twice across pricing-strategy and Phase B discussions.
- **Catalog lives in api_server** — frontend (mobile or web) fetches packs via `GET /v1/billing/packs`. Mobile MUST NOT mirror the catalog locally. Per `feedback_dumb_client_no_mocks.md`.
- **Bimodal display** — BYOK Free/Pro users see USD upstream cost; Ultra users see credits. Same `usage_logs` schema; only the `/v1/usage/summary` projection differs by tier. The pricing-strategy memory pattern.
- **Pro = subscription, Ultra = credits** — these are independent Stripe surfaces. A user is one or the other (D-01 exclusive enum). No hybrid mode in v1.
- **Modal not banner** for 402 — user picked the blocking modal explicitly; the RetryBanner pattern from Phase 31 H4 is for transient SSE errors, not for paywall. Different UX intent.
- **Stripe-event-driven** — webhook is the sole writer of `users.tier` and `credit_balances`/`credit_transactions`. No endpoint allows a logged-in user to flip their own tier directly. Audit trail is the ledger.
- **Soft-cap with grace** for Pro→Free downgrade — explicit user pick. Existing 5 agents stay alive until period end; 4 oldest auto-pause at flip; user can resub or delete down. Not "hard cap immediately".

</specifics>

<deferred>
## Deferred Ideas

These came up in discussion or memory but belong outside Phase B:

### Phase B.2 (web frontend parity)
- Web top-up flow + balance display + 402 modal + transaction history. Same API contract as mobile; different client.

### Phase B.1 (or hardening pass after exit)
- Pro-rata partial-stream debit (D-13 today bills 0 on mid-stream failure)
- Branded receipts / invoicing UI (Stripe auto-receipts cover v1)
- Multi-currency support (D-23 USD-only for v1)
- Admin write-off UI (the column lands in 014; UI ships when first dispute arrives)
- Token-count pre-flight estimation (D-12 floor estimate is sufficient for v1)
- Multiple paid subscription tiers above Pro (Pro+, Team, Enterprise)
- Yearly subscription discount tier
- Invoice/PDF history endpoint for B2B Pro accounts
- H2 (logout-everywhere) revival — D-18 chose lazy re-read; H2 is a session-correctness phase, separate from billing

### H7 (Hetzner deploy) — actual prereq for live Stripe webhooks
Phase B local-substrate work lands first (D-19); H7 is the production gate (live HTTPS endpoint required for Stripe to deliver real webhooks). Phase B exits to staging via Stripe TEST mode + Stripe CLI; live launch defers.

### Future tier propagation upgrades
If the lazy-reread latency (D-18) becomes a UX problem, revisit H2-style pub/sub OR the "Hybrid: lazy + push on critical events" option (push only on `subscription.deleted` and `payment_intent.succeeded`).

### Phase C — analytics / reporting
- Per-tier MRR / ARR dashboard
- User-facing usage projections ("at current rate, your $25 will last 6 days")
- Cost-comparison: BYOK vs Ultra cost calculator on the upgrade screen

</deferred>

---

*Phase: B-stripe-paywall*
*Context gathered: 2026-05-08*
