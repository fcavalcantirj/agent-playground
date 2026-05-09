---
status: partial
phase: B-stripe-paywall
source: [B-stripe-VALIDATION.md, B-stripe-13-PLAN.md, STRIPE-TEST-CATALOG.md]
started: 2026-05-09T13:00:00Z
updated: 2026-05-09T13:00:00Z
---

# Phase B — HUMAN-UAT

> Manual gate per D-25. Run AFTER all automated tests are green and BEFORE
> flipping `.planning/PHASE-B-EXIT-GATE-PASSED` from "automated only" to
> "fully verified".

## Prerequisites

- [ ] Stripe TEST mode keys in `deploy/.env.prod` (or `.env`):
  - `AP_STRIPE_API_KEY=sk_test_...`
  - `AP_STRIPE_WEBHOOK_SECRET=whsec_...`  ← from `stripe listen` output
- [ ] 6 Stripe Products + Prices created in TEST mode dashboard:
  - 1× Pro Monthly subscription (lookup_key `ap_pro_monthly`, $12.00, recurring)
  - 5× one-time credit packs ($5, $10, $25, $50, $100) with lookup_keys
    `ap_pack_5usd`, `ap_pack_10usd`, `ap_pack_25usd`, `ap_pack_50usd`,
    `ap_pack_100usd`
  - All 6 price IDs are pasted into the env file under
    `AP_STRIPE_PRICE_ID_*` (see `deploy/.env.prod.example` for names)
  - See `.planning/phases/B-stripe-paywall/STRIPE-TEST-CATALOG.md` for
    the already-minted TEST account `acct_1Rbog8IXnB0o3aa1` catalog.
- [ ] Stripe CLI installed on host: `which stripe` returns a path
- [ ] `stripe login` completed (links the CLI to TEST account)
- [ ] Deploy stack running:
  `docker compose -f deploy/docker-compose.prod.yml ps` shows
  `api_server` + `temporal-worker` + `postgres` + `temporal` up
  (per CLAUDE.md macOS rule — NOT native uvicorn alongside the deploy
  stack; spike F evidence in B-stripe-01-SUMMARY.md proves this is the
  only valid path)
- [ ] Stripe CLI listener forwarding to deploy api_server:
  `stripe listen --forward-to http://localhost:8000/v1/billing/webhook`
  (in a separate terminal). Copy the printed `whsec_*` value into
  `deploy/.env.prod` as `AP_STRIPE_WEBHOOK_SECRET`, then restart the
  deploy api_server: `docker compose -f deploy/docker-compose.prod.yml
  restart api_server`.
- [ ] Mobile app installed on iOS/Android device or simulator + pointed
  at `http://localhost:8000` via
  `set -a; source .env; set +a; cd mobile && make ios DEVICE=<id>
   BASE_URL=http://localhost:8000`

**Stripe TEST cards used in this UAT:**

- `4242 4242 4242 4242` — succeeds (any future expiry, any 3-digit CVC, any 5-digit ZIP)
- `4000 0000 0000 9995` — declines (insufficient funds; UAT-2 sad-path optional)
- `4000 0027 6000 3184` — requires 3DS authentication (UAT-3 promo path optional)

(All Stripe TEST card numbers: https://docs.stripe.com/testing#cards)

## Current Test

[awaiting human action]

## Tests

### UAT-1 — Free → Ultra via $5 credit pack (D-04, D-07, D-21)

**Goal:** prove the webhook flips tier free→ultra and seeds 500¢ in the
ledger end-to-end.

1. [ ] Sign up a fresh user (e.g. `phase-b-uat-1@yourdomain.com`) via
       Google or GitHub OAuth in the mobile app.
2. [ ] Confirm tier='free' and stripe_customer_id IS NULL in DB:
       `docker compose -f deploy/docker-compose.prod.yml exec postgres
        psql -U ap -d agent_playground_api -c
        "SELECT tier, stripe_customer_id FROM users
         WHERE email='phase-b-uat-1@yourdomain.com'"`
3. [ ] In the mobile app, navigate to the Top-Up screen (Plan 11).
4. [ ] Tap the "$5" pack tile.
5. [ ] EXPECT: `flutter_inappwebview` opens Stripe Checkout (real
       cs_test_* URL); the inflight UI is locked + spinner + mm:ss timer.
6. [ ] In the webview, enter test card `4242 4242 4242 4242`, expiry
       any future date, CVC any 3 digits, postal code any 5 digits.
7. [ ] Submit payment.
8. [ ] EXPECT: webview closes automatically (URL-intercept handshake);
       SnackBar shows "Top-up confirmed!" within 5–15s (webhook-driven
       via the active `stripe listen`).
9. [ ] Confirm tier flipped + balance seeded in DB:
       `SELECT tier, b.balance_cents
        FROM users u
        LEFT JOIN credit_balances b ON b.user_id = u.id
        WHERE email = 'phase-b-uat-1@yourdomain.com'`
       Expect `tier='ultra'` and `balance_cents=500`.
10. [ ] Confirm one ledger row landed:
       `SELECT kind, amount_cents FROM credit_transactions
        WHERE user_id = (SELECT id FROM users WHERE email='phase-b-uat-1@yourdomain.com')`
       Expect a single `kind='topup' amount_cents=500` row.

**expected:** tier flips free→ultra; balance seeds to 500¢; ledger has one topup row
**result:** [pending]

### UAT-2 — Send chat → debit → drained → 402 (D-12, D-13, D-21)

**Goal:** prove the pre-flight 402 gate trips when balance < 1¢ and the
mobile app surfaces the blocking modal.

1. [ ] With the UAT-1 user (now ultra, $5 balance), open chat to any
       agent.
2. [ ] Send a message; observe a real reply.
3. [ ] Confirm the upstream call ran end-to-end:
       `SELECT cost_usd, upstream_request_id FROM usage_logs
        WHERE user_id = ... ORDER BY created_at DESC LIMIT 1`
       — expect `cost_usd > 0` and `upstream_request_id` non-null.
4. [ ] Confirm a debit ledger row exists:
       `SELECT kind, amount_cents FROM credit_transactions
        WHERE user_id = ... AND kind = 'debit'
        ORDER BY created_at DESC LIMIT 1`
5. [ ] Drain the balance: send messages until `balance_cents < 1`. The
       first ~1¢ debit is sub-cent in real OpenRouter cost, so this
       can take many messages with a short prompt. As an
       admin-friendly accelerator, run a one-shot SQL drain (with
       explicit op-marker so the audit trail stays clean):
       `INSERT INTO credit_transactions (user_id, kind, amount_cents,
        reference_id, reference_type) VALUES (
          (SELECT id FROM users WHERE email='phase-b-uat-1@yourdomain.com'),
          'debit', -500,
          'phase-b-uat-2-drain', 'phase_b_uat_drain')`
       then `UPDATE credit_balances SET balance_cents = (
         SELECT COALESCE(SUM(amount_cents), 0)
         FROM credit_transactions WHERE user_id = ...) WHERE user_id = ...`
       (mirrors `services/ledger.py::_rebuild_balance_from_ledger`).
6. [ ] Send the next chat message.
7. [ ] EXPECT: a blocking modal "Out of credits" with primary "Top up"
       and secondary "Later" CTAs (Plan 12).
8. [ ] Tap "Top up" → EXPECT routing to the TopUp screen.

**expected:** 402 INSUFFICIENT_BALANCE → modal → tap-through to /topup
**result:** [pending]

### UAT-3 — Promo code applied to Checkout (D-24)

**Goal:** prove `allow_promotion_codes=true` works end-to-end.

1. [ ] In Stripe TEST dashboard → Products → Coupons → New, mint a
       promo code (e.g. 50%-off-once, code `UAT3PROMO`).
2. [ ] In the mobile app, tap a $10 pack tile.
3. [ ] In the Stripe Checkout webview, click "Have a promotion code?"
       (Stripe surfaces this when `allow_promotion_codes=true`) and
       enter `UAT3PROMO`.
4. [ ] EXPECT: the displayed total is $5.00 (50% off applied).
5. [ ] Submit (with TEST card `4242 4242 4242 4242`).
6. [ ] EXPECT: webhook fires (visible in the `stripe listen` terminal);
       webview closes; SnackBar shows top-up confirmed.
7. [ ] Confirm ledger row: per D-07 the credit_cents is 1000 (the
       FULL pack credit, not the discounted total). Stripe's webhook
       payload includes the discounted `amount_total` as a separate
       field; the route consumes `metadata.credit_cents` as the source
       of truth.
       `SELECT amount_cents FROM credit_transactions
        WHERE user_id = ... AND kind = 'topup'
        ORDER BY created_at DESC LIMIT 1`
       Expect `amount_cents=1000`.

**expected:** promo discount visible in Checkout; ledger top-up reflects FULL pack credit (D-07)
**result:** [pending]

### UAT-4 — Pro upgrade + cancel grace period + downgrade (D-15)

**Goal:** prove the Pro subscription lifecycle: upgrade flips tier→pro;
cancel-at-period-end keeps tier='pro' until period_end; period end
flips tier→free and auto-pauses the 4 oldest active agents.

1. [ ] Sign up a new user `phase-b-uat-4@yourdomain.com`.
2. [ ] (Optional setup) Create 5 active agents for this user (POST
       `/v1/agents` × 5 via curl with the session cookie or via the
       mobile dashboard if the surface supports it).
3. [ ] Drive Pro upgrade — Phase B has `POST /v1/billing/subscription`
       (Plan 05). The mobile surface for Pro is deferred to B.2; in
       this UAT, drive via curl with the session cookie:
       `curl -X POST -b "ap_session=<...>" -H "Content-Type: application/json"
        -d '{}' http://localhost:8000/v1/billing/subscription`
       — copy the returned `checkout_url` and open in a browser.
4. [ ] In Stripe Checkout, enter test card, submit.
5. [ ] EXPECT: webhook fires, tier flips free→pro:
       `SELECT tier FROM users WHERE email='phase-b-uat-4@yourdomain.com'`
6. [ ] In Stripe TEST dashboard → Subscriptions, find the new sub and
       set `cancel_at_period_end=true`.
7. [ ] EXPECT: tier remains 'pro' until period_end. DB column
       `subscription_cancel_at_period_end=true` and
       `subscription_current_period_end` is set.
8. [ ] In Stripe TEST dashboard, force-end the period — easiest path
       is `stripe trigger customer.subscription.deleted` from a
       terminal (the CLI mints a synthetic event for the test
       subscription).
9. [ ] EXPECT: tier flips pro→free; the 4 oldest active agents flip
       to `paused_at IS NOT NULL` (cap=1 keeps the oldest active per
       D-05); newest active agent is the one allowed slot.

**expected:** pro→free downgrade auto-pauses 4 oldest agents; cap=1 enforced
**result:** [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps

- Mobile Pro upgrade surface (UAT-4 step 3) is curl-driven for v0.3 —
  Phase B.2 (web frontend) and a follow-up mobile UI task can replace
  the curl with a tap-through.
- Live webhook delivery requires HTTPS; Phase B targets local
  (`stripe listen → http://localhost:8000`). Production rollout
  unblocks on H7 (Hetzner deploy).
