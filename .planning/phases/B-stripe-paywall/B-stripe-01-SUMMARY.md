---
phase: B-stripe
plan: 01
subsystem: billing-paywall
tags: [wave-0, spikes, stripe, temporal, postgres, alembic, mobile, flutter_inappwebview, deploy-stack]
requires:
  - "deploy stack up (api_server + temporal + postgres + redis)"
  - "Stripe TEST keys in deploy/.env.prod (sk_test_*, whsec_*)"
  - "Stripe CLI (brew tap stripe/stripe-cli) + stripe login"
  - "FVM Flutter 3.41.0 + iPhone simulator booted"
provides:
  - "validated grey-area mechanisms for Phase B Wave 1+ implementation"
  - "draft migration body for 014_phase_b_ledger_and_tier (in _spikes/, NOT yet alembic/versions/)"
  - "register_schedules helper template (typed ScheduleAlreadyRunningError + RPCError fallback)"
  - "atomic ledger pattern proven concurrent-safe at 8-way parallelism"
  - "lazy stripe_customer_id create proven race-free under SELECT FOR UPDATE"
  - "mobile checkout-webview navigation-delegate API confirmed (flutter_inappwebview ^6.1.5)"
  - "deploy-stack webhook routing confirmed (NO native-uvicorn split-brain)"
affects: []
tech-stack:
  added:
    - "stripe (Python SDK) >=15.0,<16.0  — already pinned in api_server/pyproject.toml"
    - "flutter_inappwebview ^6.1.5  — added to mobile/pubspec.yaml (AMD-03)"
  patterns:
    - "Hand-rolled signed-fixture helper via HMAC-SHA256 → StripeClient.construct_event round-trip"
    - "Postgres testcontainer + alembic upgrade/downgrade/upgrade idempotency assertion shape"
    - "asyncpg pool + asyncio.gather race-defense pattern (FOR UPDATE serialization proof)"
    - "Temporal schedule register-or-update template (typed exception first, RPCError substring fallback)"
    - "Flutter integration_test driving InAppWebView with inline data: URL + auto-clicking anchor"
key-files:
  created:
    - api_server/tests/_spikes/sign_webhook.py
    - api_server/tests/_spikes/spike_a_webhook_signature.py
    - api_server/tests/_spikes/spike_b_debit_activity_contract.py
    - api_server/tests/_spikes/spike_c_atomic_ledger.py
    - api_server/tests/_spikes/spike_d_temporal_schedule.py
    - api_server/tests/_spikes/spike_g_lazy_customer_create.py
    - api_server/tests/_spikes/spike_h_migration_roundtrip.py
    - api_server/tests/_spikes/draft_014_migration.py
    - api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md
    - api_server/tests/_spikes/wave0_stripe_paywall.md
    - mobile/integration_test/spike_e_inappwebview_intercept.dart
  modified:
    - mobile/pubspec.yaml  (add flutter_inappwebview ^6.1.5)
    - mobile/pubspec.lock  (resolved transitives)
decisions:
  - "Catch typed ScheduleAlreadyRunningError FIRST, then RPCError substring fallback — RESEARCH §Pattern 4 was wrong; spike D proved the typed exception is what 1.27.x raises"
  - "Migration revision ID 014_phase_b_ledger_and_tier (27 chars) — alembic_version is varchar(32); do NOT use 014_phase_b_credit_ledger_and_tier (33 chars)"
  - "cost_weights data migration asserted across all migration-010 seed rows (≥6) — do NOT seed a synthetic spike row in the spike body; the migration touches everything at ap_multiplier=1.0"
  - "Spike F established the deploy-stack-only webhook delivery convention as the canonical Wave 3+ pattern (rejecting any future native-uvicorn-alongside-deploy attempts)"
metrics:
  duration: "~50min (D+G+H+E+F + evidence aggregation; A+B+C done in prior session)"
  completed: 2026-05-08
---

# Phase B Plan 01: Wave 0 Spike Gate (Stripe Paywall) Summary

Wave 0 BLOCKING gate. Probed all 8 grey-area mechanisms identified in
`B-stripe-RESEARCH.md` against real infra BEFORE Wave 1 sealed any
implementation work. Per CLAUDE.md Golden Rule #5: every non-trivial
mechanism gets spiked and the result captured as evidence; the plan's
own assumptions hit real infra too.

All 8 spikes PASS. Wave 1 is unblocked.

## Spike-by-spike results

| Spike | Verb (one-liner) | Outcome |
|-------|------------------|---------|
| **A — webhook signature** | StripeClient.construct_event round-trips a hand-rolled signed fixture; tampered + stale rejected | PASS — `b61c028` |
| **B — debit activity contract** | `@activity.defn(name="debit_balance")` returns Decimal-as-string + idempotent on UNIQUE-violation retry | PASS — `b61c028` |
| **C — atomic ledger** | INSERT credit_transactions + UPDATE credit_balances same-tx is concurrent-safe at 8-way parallelism | PASS — `b61c028` |
| **D — Temporal schedule** | `register_schedules` helper idempotent across two boots (typed ScheduleAlreadyRunningError fallback) | PASS — `46c6096` |
| **E — mobile webview** | flutter_inappwebview shouldOverrideUrlLoading intercepts redirect URL with query-param extraction, returns NavigationActionPolicy.CANCEL | PASS — `94ec8ff` |
| **F — Stripe CLI deploy stack** | `stripe listen --forward-to http://localhost:8000/v1/billing/webhook` delivered to `deploy-api_server-1` (NOT a side-launched uvicorn) | PASS — `ecc4c06` |
| **G — lazy customer create** | `SELECT FOR UPDATE` serializes 2 concurrent first-clicks into 1 fake-Stripe call (counter-example without FOR UPDATE recorded 2 calls — race confirmed real) | PASS — `46c6096` |
| **H — migration round-trip** | Migration `014_phase_b_ledger_and_tier` upgrade → downgrade → re-upgrade is idempotent against PG17 testcontainer; ap_multiplier 1.0↔1.15 swap reverses cleanly | PASS — `46c6096` |

## Deviations from RESEARCH.md predictions

These are the corrections the spike pass surfaced. Each is a Wave 1
input, NOT a defect — the spike's job is exactly to find these.

### 1. Spike D — typed `ScheduleAlreadyRunningError`, not `RPCError("already exists")`

**RESEARCH §Pattern 4 / PATTERNS.md** said: catch `RPCError` and string-match
`"already exists"` to detect a colliding schedule.

**Reality (spike D):** Temporal SDK 1.27.x raises a typed
`temporalio.client.ScheduleAlreadyRunningError`. The string-match path
never fires. Wave 1's `register_schedules` helper now catches the typed
exception first and keeps the substring match as defense-in-depth in
case future SDK versions change the surface.

### 2. Spike H — alembic_version is `varchar(32)`

Initial draft revision `014_phase_b_credit_ledger_and_tier` is 33 chars
and gets truncated. Shortened to `014_phase_b_ledger_and_tier` (27 chars).
Wave 1 must use the shortened name verbatim.

### 3. Spike H — Postgres 12+ removed `pg_constraint.consrc`

Schema-shape assertions cannot use `consrc`; replaced with
`pg_get_constraintdef(oid)`. Future migration-test code follows this.

### 4. Spike H — cost_weights baseline is migration-010's 6 seeded rows

Initial draft asserted a synthetic `provider='spike-h'` row that was
never seeded. Replaced with COUNT-based assertions across the
migration-010 baseline (≥6 rows flip 1.0 → 1.15 on upgrade and back
on downgrade). This matches the production data shape.

### 5. Spike F — confirmed deploy-stack-only routing convention

The spike confirmed (with three independent signals — container ID,
source IP `172.18.0.1` = `deploy_default` bridge gateway, User-Agent
`Stripe/1.0`) that Stripe CLI delivery lands on `deploy-api_server-1`
when no native uvicorn is running. No new bug; this is the canonical
working pattern Wave 3+ webhook work depends on.

## Auth gates

None. All spikes ran against real infra without manual intervention
beyond the deploy stack already being up and Stripe TEST keys already
present in `deploy/.env.prod` (those are documented preconditions, not
gates).

## Self-Check: PASSED

- [x] All 11 created files exist on disk (8 spike scripts + 1 helper +
      1 draft migration + 1 evidence aggregation)
- [x] All 4 commits exist in `git log --oneline`:
  - `b61c028` — spikes A+B+C (prior session)
  - `46c6096` — spikes D+G+H
  - `94ec8ff` — spike E + mobile pubspec
  - `ecc4c06` — spike F + wave0 aggregation
- [x] `stripe>=15.0,<16.0` present in `api_server/pyproject.toml`
- [x] `flutter_inappwebview ^6.1.5` present in `mobile/pubspec.yaml`
- [x] No file in `api_server/alembic/versions/` was added or modified
      (the draft lives in `_spikes/` only — Wave 1 will copy it)
- [x] All 8 PASS markers documented in `wave0_stripe_paywall.md`

## Wave 1 release condition

Met. Wave 1 may proceed.
