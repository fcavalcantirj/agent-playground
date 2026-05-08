# Phase B: Stripe Paywall — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents. Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** B-stripe-paywall
**Areas discussed:** Tier model & transition, Pricing knobs, Stripe substrate & error semantics, Gate posture & sequencing, Tier propagation, Webhook event matrix + downgrade/refund, Ledger truth boundary, Test strategy, Currency, Promo codes, Phase B exit gate, Migration default + audit log

---

## Tier Shape (locked early, before enum)

| Option | Description | Selected |
|--------|-------------|----------|
| Lock as-is | Three tiers; Pro=BYOK+sub, Ultra=platform-billed credits; Phase B implements BOTH Stripe surfaces. | ✓ |
| Lock, but Pro defers | Same shape but Pro subscription wiring deferred; Phase B = Ultra only. | |
| Refine the shape | Adjust — drop Pro / merge with Ultra / change unlocks. | |

**User's choice:** Lock as-is.
**Notes:** Confirmed by user note: "pro users are ones with BYOK and paying, so they pay fixed for the agents".

---

## Tier Co-existence

| Option | Description | Selected |
|--------|-------------|----------|
| Exclusive enum | Single `users.tier` column = `free` \| `pro` \| `team`. Mutually exclusive. | ✓ |
| Independent flags | Two columns: `pro_subscription_active`, `platform_billed`. User can be both. | |
| Defer to Phase C | Lock single enum for B; revisit hybrid mode if a real user surfaces the need. | |

**User's choice:** Exclusive enum.

---

## Tier Enum Values

| Option | Description | Selected |
|--------|-------------|----------|
| free / pro / team | Industry-standard naming (Cursor/Notion/Linear). | |
| free / pro / payg | "PAYG" descriptively accurate; less marketable. | |
| free / pro / credits | Names the unit of account directly; couples enum to implementation. | |
| free / pro / **ultra** | Marketable, future-proof; unit-of-account not baked in. | ✓ |

**User's choice:** Free text — `free / pro / ultra`. Reflected back and locked.

---

## Tier Transition Driver

| Option | Description | Selected |
|--------|-------------|----------|
| Stripe-event-driven | Webhook = sole writer of `users.tier`. | ✓ |
| User-elective + Stripe sync | User picks tier on Settings; Stripe flips column. | |
| Admin-only flag | Manual ops field for v1. | |

**User's choice:** Stripe-event-driven.

---

## Pro Entitlements

| Option | Description | Selected |
|--------|-------------|----------|
| 5 agents + 30d retention | Free=1/7d, Pro=5/30d, Ultra=∞/∞. Memory's anchor. | ✓ |
| Agent slots only (skip retention) | Retention unlimited for everyone in B; pruning is a separate phase. | |
| Defer entitlements to Phase C | Tier flag exists but enforces nothing; Pro = "support us" label. | |

**User's choice:** 5 agents + 30d retention.

---

## Credit-Pack Catalog

| Option | Description | Selected |
|--------|-------------|----------|
| 5 packs: $5 / $10 / $25 / $50 / $100 | Standard ladder; mirrors v0/Replit/Cursor. | ✓ |
| 3 packs: $10 / $25 / $100 | Fewer choices; less decision paralysis. | |
| 4 packs + bonus on largest | Skips $5; adds bonus credits on $100. | |

**User's choice:** 5 packs $5–$100, 1:1 USD→credit.

---

## ap_multiplier

| Option | Description | Selected |
|--------|-------------|----------|
| 1.20 (20%) | Industry-typical (Cursor/v0). | |
| 1.10 (10%) | Aggressive; barely covers Stripe + tiny margin. | |
| 1.30 (30%) | Conservative; healthy margin. | |
| Per-provider variation | Different multipliers per cost_weights row. | |
| **1.15 (15%)** | Mid-range with honest pricing math (after follow-up). | ✓ |

**User's choice:** Free text "15? 17? 12-18%?" → follow-up locked **1.15**. Net margin: ~1% on $5 packs, ~6% on $25, ~9% on $100.

---

## Stripe Account State

| Option | Description | Selected |
|--------|-------------|----------|
| Account exists / I'll set up parallel | Stripe account out-of-band; plan-phase assumes TEST keys exist. | ✓ |
| Account creation is part of Phase B | Phase B includes a setup-checklist plan. | |
| Defer — TEST mode only | Live-mode rollout is a separate ops phase coupled with H7. | |

**User's choice:** Account exists / I'll set up parallel.

---

## Stripe Customer Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy on first Stripe interaction | `users.stripe_customer_id` NULL for Free; created on first Pro-subscribe or top-up. | ✓ |
| Eager on signup | Every signup creates a Stripe Customer immediately. | |
| Eager on tier change to Pro/Ultra | Sub-step of Checkout flow; functionally equivalent to Lazy. | |

**User's choice:** Lazy.

---

## Pre-flight 402 Estimation

| Option | Description | Selected |
|--------|-------------|----------|
| Floor estimate (1¢) | Reserve flat 1¢; real cost debited post-hoc. | ✓ |
| Token-count estimate | Tokenize prompt; multiply by cost_weights × ap_multiplier. | |
| Hybrid: floor + post-hoc cap | 1¢ pre-flight + `overdrawn_cents` column on user. | |

**User's choice:** Floor estimate.

---

## Refund / Error Semantics (LLM call failure)

| Option | Description | Selected |
|--------|-------------|----------|
| Debit only on success | Non-2xx or no `usage` block → debit=0. | ✓ |
| Pro-rata debit on partial success | Debit per partial token count from interrupted SSE. | |
| Debit upstream-actual + refund job | Always debit; refund queue on no-`usage`. | |

**User's choice:** Debit only on success.

---

## Phase B Sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Start now — local substrate, webhook awaits H7 | Migrations + endpoints + activity + mobile vs Stripe TEST + `stripe listen`. | ✓ |
| Wait for the 4 manual UAT gates | OpenRouter cap + GH secret + baseline PR + regression PR clear first. | |
| Wait for H7 too | No code starts until live HTTPS webhooks receivable. | |

**User's choice:** Start now.

---

## Phase B Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Mobile-only Phase B; web is B.2 | api_server + mobile. Web later. | ✓ |
| Mobile + web together | Both clients in Phase B. | |
| API-only Phase B; clients later | Just api_server billing substrate. | |

**User's choice:** Mobile-only.

---

## Retention Pruning

| Option | Description | Selected |
|--------|-------------|----------|
| Daily Temporal cron — hard delete | Scheduled workflow deletes per-tier retention window. | ✓ |
| Soft-delete: query-time filter | Filter at read time; never delete. | |
| Defer retention enforcement | Pro's "30d" is marketing claim only. | |

**User's choice:** Daily Temporal cron — hard delete.

---

## 402 Mobile UX

| Option | Description | Selected |
|--------|-------------|----------|
| Modal: "Out of credits" + Top-Up CTA | Blocking modal → pack picker → Checkout webview → poll balance. | ✓ |
| Banner + send-blocked | Persistent banner; send button disabled. | |
| Inline error bubble | 402 surfaces as system message in chat thread. | |

**User's choice:** Modal.

---

## Ledger Truth Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Ledger-as-truth, scalar is cache | Reads SUM `credit_transactions`; cache rebuilt every tx. | ✓ |
| Scalar-as-truth, ledger is audit | `balance_cents` is sole truth; ledger for audit only. | |
| Both — reconciled on every read | Read scalar + concurrent SUM check. | |

**User's choice:** Ledger-as-truth.

---

## Webhook Event Matrix

| Option | Description | Selected |
|--------|-------------|----------|
| Full set | checkout.session.completed + payment_intent.* + subscription.* + invoice.* + charge.refunded | ✓ |
| Minimum viable set | checkout + subscription.deleted + charge.refunded only | |
| Iterative — ship MVP, add later | checkout + subscription.created/deleted only | |

**User's choice:** Full set.

---

## Pro→Free Downgrade

| Option | Description | Selected |
|--------|-------------|----------|
| Soft cap with grace + immediate-stop new | `cancel_at_period_end=true`; period-end flip; auto-pause 4 oldest. | ✓ |
| Hard cap immediately | Tier flips on cancel; 4 agents instantly paused. | |
| Allow over-cap forever after Pro | Once Pro, keep 5 agents even after downgrade. | |

**User's choice:** Soft cap with grace.

---

## Refund / Chargeback

| Option | Description | Selected |
|--------|-------------|----------|
| Revoke remaining; allow negative if spent | Refund row of full -$amount; balance can go negative; admin can write-off. | ✓ |
| Revoke only unspent portion | Refund capped at remaining balance. | |
| Defer to manual ops | Webhook logs refund; no automatic mutation. | |

**User's choice:** Revoke remaining; allow negative if spent.

---

## Tier Propagation Across Sessions

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy: re-read on next API request | `get_current_user` reads `users.tier` fresh; no caching. | ✓ |
| Reintroduce H2-style pub/sub | NOTIFY/LISTEN or Redis pub/sub keyed on user_id. | |
| Hybrid: lazy default + push on critical events | Push only `subscription.deleted` and `payment_intent.succeeded`. | |

**User's choice:** Lazy.

---

## Test Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Unit: stripe-mock; Integration+e2e: Stripe TEST mode | Two-tier substrate; respx for HTTP isolation. | ✓ |
| Stripe TEST mode everywhere | All tests hit real TEST mode (free, slower). | |
| stripe-mock everywhere; manual TEST UAT | Automated mock-only; human signoff against real TEST. | |

**User's choice:** Unit: stripe-mock; Integration+e2e: Stripe TEST mode.

---

## Currency

| Option | Description | Selected |
|--------|-------------|----------|
| USD only | Hardcoded USD; multi-currency is a future phase. | ✓ |
| USD only + currency column for future | Schema includes column; code path stays USD-only. | |
| Multi-currency from day 1 | USD + EUR + BRL; per-currency cost_weights. | |

**User's choice:** USD only.

---

## Promo Codes

| Option | Description | Selected |
|--------|-------------|----------|
| Enable Stripe promo codes | `allow_promotion_codes=true` for sub + credit packs. | ✓ |
| No coupons in v1 | Defer marketing flexibility. | |
| Pro coupons yes, credit-pack coupons no | Avoid arbitrage on top-ups. | |

**User's choice:** Enable Stripe promo codes.

---

## Phase B Exit Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Live TEST-mode e2e + manual UAT | CI e2e (stripe-mock + Stripe TEST) + B-HUMAN-UAT.md (real TEST + Stripe CLI). | ✓ |
| Automated only | Just CI e2e. | |
| Manual UAT only | Lock manual signoff; CI gate deferred to B.1. | |

**User's choice:** Live TEST-mode e2e + manual UAT.

---

## Migration Default + Audit

| Option | Description | Selected |
|--------|-------------|----------|
| Backfill `tier='free'` + reuse credit_transactions for tier flips | One ledger; new `kind='tier_change'` value. | ✓ |
| Backfill + separate `audit_log` table | Cleaner separation, more tables. | |
| Backfill only — no explicit audit | Audit implicit in Stripe event log. | |

**User's choice:** Reuse credit_transactions with `kind='tier_change'`.

---

## Claude's Discretion (no user input requested)

- Env var naming: `AP_STRIPE_API_KEY`, `AP_STRIPE_WEBHOOK_SECRET`, `AP_STRIPE_PRICE_ID_*` (per `AP_*` convention)
- Python SDK pin: `stripe>=8.0,<9.0`
- 5-min reconciliation as Temporal cron (no new scheduler)
- Webhook idempotency: `stripe_webhook_events.stripe_event_id` UNIQUE
- Decimal-as-string return for `debit_balance` (Phase 28 D-22 lock)
- Tax: defer to Stripe Tax (auto-handle)
- Receipts: rely on Stripe's auto-emails (no AP-side branded receipts in v1)
- Webhook handler placement: `routes/billing_webhook.py` (new file)

## Deferred Ideas

- Phase B.2 — web parity (top-up flow, balance, 402 modal, history)
- Pro-rata partial-stream debit (B.1 hardening)
- Branded receipts / invoicing
- Multi-currency
- Admin write-off UI
- Token-count pre-flight estimation
- Multiple paid sub tiers above Pro
- Yearly subscription discount
- B2B invoice/PDF history
- H2 logout-everywhere revival
- H7 Hetzner deploy (the actual production gate for live webhooks)
- Phase C — analytics / per-tier MRR / cost-comparison calculator
