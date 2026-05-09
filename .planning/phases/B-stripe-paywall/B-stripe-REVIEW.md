---
phase: B-stripe-paywall
status: warnings
depth: standard
created: 2026-05-09
files_reviewed: 41
findings:
  critical: 0
  high: 3
  medium: 6
  low: 5
  total: 14
---

# Code Review: Phase B-stripe-paywall

**Scope:** 41 production files (tests/spikes/generated/lock files excluded)
**Depth:** standard
**Status:** warnings — no CRITICAL findings; load-bearing security paths (webhook signature, atomic ledger, pre-flight 402, lazy customer create) are correctly implemented.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 6 |
| LOW | 5 |
| **Total** | **14** |

The phase delivers a coherent Stripe paywall substrate. Biggest real risks: (1) reconciliation poller not transactional vs the live webhook path, (2) webview `success_url` doesn't carry `{CHECKOUT_SESSION_ID}` substitution end-to-end, (3) inconsistent stored-payload format between webhook ingest and reconcile.

---

## HIGH

### HIGH-01 — `reconcile_stripe` activity stores Python-repr instead of JSON for `payload`

**File:** `api_server/src/api_server/temporal/activities/reconcile_stripe.py:124`
**Problem:** Webhook ingest stores `payload.decode()` (raw JSON bytes from Stripe). Reconcile stores `str(event)` — `stripe.StripeObject.__str__` returns a Python-repr-like view (single-quoted, `None` instead of `null`), NOT canonical JSON. Over time `stripe_webhook_events.payload` becomes mixed-format.
**Impact:** Audit/replay tooling that calls `json.loads(payload)` will fail intermittently on rows the reconcile path inserted.
**Fix:** `json.dumps(event.to_dict() if hasattr(event, "to_dict") else dict(event))`. Or share `_event_payload_to_json(event)` between routes/billing_webhook.py and the reconcile activity.

### HIGH-02 — Default `success_url` does NOT match the mobile webview interceptor; substitution placeholder unused

**Files:** `api_server/src/api_server/routes/billing.py:299-302` + `mobile/lib/features/billing/checkout_webview_screen.dart:62-72`
**Problem:** Server's `_DEFAULT_SUCCESS_URL` carries `?session_id={CHECKOUT_SESSION_ID}`. Stripe substitutes this. The webview matcher checks only host+path, ignores query — and **session_id is extracted nowhere on the mobile side**. `app_router.dart:113-118` shows a future-intent stub.
**Impact:** Mobile cannot validate redirect came from user's own Checkout session. Future post-Checkout reconciliation can't be wired without a refactor.
**Fix:** Either drop `{CHECKOUT_SESSION_ID}` substitution OR extract `uri.queryParameters['session_id']` in `classifyNavigationForResult` and surface on `PaymentResult.success`. Pick one; current state is "documented intent, no code".

### HIGH-03 — `record_tier_change` audit info loss (from_tier/to_tier accepted but not persisted)

**File:** `api_server/src/api_server/services/ledger.py:243-256`
**Problem:** Helper validates from_tier/to_tier early but the `kind='tier_change'` row only stores `stripe_event_id` in `reference_id`. NO column carries from_tier/to_tier. Forensic reconstruction requires Stripe API access (events expire after 30 days).
**Impact:** Audit information loss for tier history.
**Fix options:** (a) repurpose `reference_id` to `f"{stripe_event_id}:{from_tier}->{to_tier}"`, (b) follow-up migration adding metadata column, (c) document explicitly that audit relies on cached `stripe_webhook_events.payload` (and fix HIGH-01 first).

---

## MEDIUM

### MED-01 — Pre-flight 402 read uses default-isolation snapshot, races with concurrent debit

**File:** `api_server/src/api_server/routes/llm_proxy.py:320-338`
**Problem:** Pre-flight does fresh `pool.acquire()` outside any tx. Under READ COMMITTED, concurrent in-flight debit holding `SELECT FOR UPDATE` returns pre-debit balance. User with balance=1¢ + 2 concurrent calls: both pass gate, both debit, second drives negative.
**Impact:** Edge — user gets one "free" call beyond balance at very low balances during concurrent streams.
**Fix:** Accept this (D-12 floor=1¢ acknowledges post-hoc debit) and document, OR add `SELECT FOR SHARE` aligned with debit lock. Holding lock across 10-600s LLM stream is costly. Recommendation: leave as-is + add comment naming the race.

### MED-02 — Webhook handler 500 message leaks side-effect detail to Stripe ops UI

**File:** `api_server/src/api_server/routes/billing_webhook.py:191-194`
**Problem:** Returns `"webhook side-effect failed; rolled back for retry"`. Body lands in Stripe webhook delivery logs.
**Impact:** Minor info disclosure.
**Fix:** Generic body `"internal error"`; log details via `_log.exception` only.

### MED-03 — Worker constructs StripeClient without validate_stripe_config gate

**File:** `api_server/src/api_server/temporal/worker.py:216-218`
**Problem:** Worker calls `stripe.StripeClient(settings.stripe_api_key)` directly. With misconfigured prod env, fails on first scheduled call (~5min later) instead of at boot.
**Impact:** Slow-fail in prod misconfig; ops paged 5min late.
**Fix:** Add `validate_stripe_config(settings)` after `get_settings()` in `temporal/worker.py:main()` BEFORE constructing client.

### MED-04 — `prune_messages` activity holds connection across multiple auto-committed DELETEs

**File:** `api_server/src/api_server/temporal/activities/prune_messages.py:57-78`
**Problem:** Single connection, three serial DELETEs each auto-commits. Worker crash mid-prune leaves partial deletion.
**Impact:** LOW — retention is best-effort cron; partial completion recoverable.
**Fix (optional):** Wrap loop in `conn.transaction()` so worker crash = full rollback. Not strictly required.

### MED-05 — `reconcile_ledger` UPDATE without transaction; concurrent debit can race repair

**File:** `api_server/src/api_server/temporal/activities/reconcile_ledger.py:110-116`
**Problem:** After detecting drift, runs `UPDATE credit_balances SET balance_cents = $1` with no transaction or `SELECT FOR UPDATE`. Debit landing between SELECT (line 68) and this UPDATE causes stale value to overwrite fresh debit — re-introducing drift the next reconcile detects.
**Impact:** Reconcile loop oscillates `cache_cents` night after night without root-cause visible.
**Fix:** `async with conn.transaction(): SELECT 1 FROM credit_balances WHERE user_id=$1 FOR UPDATE; UPDATE ...` with re-read of SUM under lock. Or call `_rebuild_balance_from_ledger` from services/ledger.py directly.

### MED-06 — `_handle_subscription_updated` has no out-of-order event guard

**File:** `api_server/src/api_server/routes/billing_webhook.py:342-370`
**Problem:** Webhook dedupes by stripe_event_id. Stripe can emit multiple subscription.updated events with different ids — not delivery-ordered. Older event's `cancel_at_period_end` overwrites newer.
**Impact:** Mobile UI shows stale "cancels on <date>" briefly. Tier flip itself unaffected.
**Fix:** Compare `obj.get("created")` against new `users.subscription_updated_at` column; skip stale. Defer to v1.1 — document as known caveat.

---

## LOW

### LOW-01 — Webhook signature-prefix logging logs first 20 chars (could be 12)

**File:** `api_server/src/api_server/routes/billing_webhook.py:138`
**Problem:** Logs `(stripe_signature or "")[:20]` — covers `t=<unix>,v1=<sha256_hex>` first 20 chars; harmless against 64-char HMAC.
**Fix:** Drop to `[:13]` for conservatism. Current state acceptable.

### LOW-02 — `users.refund_writeoff_cents` column added but unused

**File:** `api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py:84-91`
**Problem:** NOT NULL DEFAULT 0; no production code references. D-16 admin write-off path deferred. Schema-only column carries zero risk.
**Fix:** None required. Reuse when admin tooling lands.

### LOW-03 — `tier_enforcement.check_can_create_agent` unknown-tier silently defaults to free cap

**File:** `api_server/src/api_server/services/tier_enforcement.py:79-87`
**Problem:** `agent_cap_for_tier(tier)` falls back to free's cap=1 silently. Future `'team'` tier forgetting to update map = silent downgrade with no log.
**Fix:** `_log.warning("tier_enforcement.unknown_tier tier=%s", tier)` on fallback.

### LOW-04 — Refund delta SUM relies on LIKE prefix; reference_type filter would future-proof

**File:** `api_server/src/api_server/routes/billing_webhook.py:447-452`
**Problem:** SUM filter is `kind='refund' AND reference_id LIKE $charge_id:%`. Today the kind filter prevents collision; LIKE is fragile if a future kind/event scheme uses same prefix.
**Fix:** Add `AND reference_type='stripe_refund'` to SUM. One-line future-proofing.

### LOW-05 — Mobile transactions_screen displays `tx.kind` raw (topup/debit/tier_change) to user

**File:** `mobile/lib/features/billing/transactions_screen.dart:91`
**Problem:** End users see "tier_change" — opaque enum value.
**Fix:** Add `_kindLabel(String kind)` formatter — "Top up" / "Usage" / "Refund" / "Plan change" / "Adjustment". Out-of-scope for this review; flag for Phase B.1.

---

## Verified Correct (No Findings)

- **D-04 invariant:** `users.tier` UPDATE only in routes/billing_webhook.py.
- **Stripe signature:** raw `await request.body()` BEFORE JSON parse; AMD-04 `client.construct_event`. No HMAC bypass.
- **Atomic debit:** SELECT FOR UPDATE before INSERT + cache rebuild (D-17, spike-c). Idempotent on UniqueViolationError.
- **Lazy customer create:** SELECT FOR UPDATE on user row serializes concurrent first-clicks (D-11, spike-G).
- **Webhook idempotency:** stripe_webhook_events.stripe_event_id UNIQUE; INSERT-first, side-effect-second, same tx.
- **Pre-flight 402:** Only fires for tier='ultra' AND balance<1; BYOK bypass correct.
- **Stripe API key handling:** Logs only `[:7]` prefix.
- **Mobile dumb client:** Pack catalog from `GET /v1/billing/packs`; no hardcoded list.
- **Decimal-as-string contract:** `temporal/activities/debit_balance.py:128` returns `str(charged)` per D-22.
- **ErrorCode parity:** Mobile result.dart mirrors api_server INSUFFICIENT_BALANCE; server-only codes intentionally not in mobile.
- **Migration 014 revertibility:** downgrade reverses schema; defensive UPDATE on enum addition.

---

## Out of Scope

- Wave 0 spike files in `api_server/tests/_spikes/` (one-shot evidence)
- `*-SUMMARY.md` plan artifacts
- Generated `.g.dart` / lock files / config files

## Recommended Next Steps

Run `/gsd-code-review-fix B-stripe-paywall` to auto-fix HIGH and MEDIUM findings, OR address HIGH-01/02/03 manually before staging deploy.
