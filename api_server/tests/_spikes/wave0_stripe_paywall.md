# Phase B Wave 0 — Spike Evidence (Stripe Paywall)

**Status:** ALL 8 SPIKES PASSED
**Phase:** B-stripe (Stripe Paywall)
**Plan:** B-stripe-01
**Date:** 2026-05-08
**Commits:** `b61c028`, `46c6096`, `94ec8ff` + this aggregation

Per CLAUDE.md Golden Rule #5: every non-trivial mechanism in
`B-stripe-RESEARCH.md` was probed against real infra before Wave 1 sealed.
The 8 spikes cover the full grey-area surface — webhook signature
verification, debit activity contract, atomic ledger conservation,
Temporal schedule idempotency, mobile webview interception, Stripe CLI
deploy-stack delivery, lazy-customer race-defense, and migration round-trip.

## Spike matrix

| Spike | File | Verb | What it proved | PASS evidence |
|-------|------|------|----------------|---------------|
| **A** | `spike_a_webhook_signature.py` | `uv run python tests/_spikes/spike_a_webhook_signature.py` | Hand-rolled signed fixture (AMD-02) round-trips through `stripe.StripeClient.construct_event` (AMD-04); tampered payload + stale timestamp both raise `SignatureVerificationError` | `PASS spike-a` (committed `b61c028`) |
| **B** | `spike_b_debit_activity_contract.py` | `uv run python tests/_spikes/spike_b_debit_activity_contract.py` | `@activity.defn(name="debit_balance")` returns Decimal-as-string AND is idempotent on second invocation: `asyncpg.UniqueViolationError` on the `(reference_id, reference_type)` UNIQUE index → return originally-debited amount | `PASS spike-b` (committed `b61c028`) |
| **C** | `spike_c_atomic_ledger.py` | `uv run python tests/_spikes/spike_c_atomic_ledger.py` | INSERT credit_transactions + UPDATE credit_balances inside a single transaction is concurrent-safe under 8 parallel debits — final balance = initial − sum(deltas), no double-decrement, all 8 ledger rows present | `PASS spike-c` (committed `b61c028`) |
| **D** | `spike_d_temporal_schedule.py` | `AP_TEMPORAL_HOST=localhost:7233 uv run python tests/_spikes/spike_d_temporal_schedule.py` | `register_schedules` helper survives second-boot create attempt by catching typed `ScheduleAlreadyRunningError` (NOT a generic RPCError, as RESEARCH §Pattern 4 originally claimed) and falling back to `get_schedule_handle().update()`. Three sequential calls: created, updated, updated. | `PASS spike-d` (committed `46c6096`) |
| **E** | `mobile/integration_test/spike_e_inappwebview_intercept.dart` | `fvm flutter test integration_test/spike_e_inappwebview_intercept.dart -d <iOS sim>` | `flutter_inappwebview` 6.1.5 `shouldOverrideUrlLoading` callback fires on https-redirect; query-param extraction works; returning `NavigationActionPolicy.CANCEL` halts the page load. Tested on iPhone 17 Pro simulator (iOS 26.2). | `PASS spike-e` + `All tests passed!` (committed `94ec8ff`) |
| **F** | `spike_f_stripe_cli_deploy_stack.md` | manual: `stripe listen --forward-to http://localhost:8000/v1/billing/webhook --skip-verify` + `stripe trigger checkout.session.completed` + `docker compose -f deploy/docker-compose.prod.yml logs api_server` | Stripe CLI delivered 7 cascading events to `deploy-api_server-1` container (NOT a side-launched native uvicorn): source IP `172.18.0.1` = `deploy_default` bridge gateway; User-Agent `Stripe/1.0`; container ID `ee9d8d17b1...e073982`. | `PASS` marker in markdown evidence file |
| **G** | `spike_g_lazy_customer_create.py` | `uv run python tests/_spikes/spike_g_lazy_customer_create.py` | `SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE` serializes two concurrent first-clicks into 1 fake-Stripe-customer-create call (counter-example without `FOR UPDATE` recorded 2 calls — race confirmed real). Third call hits already-populated path with 0 fake calls. | `PASS spike-g` (committed `46c6096`) |
| **H** | `spike_h_migration_roundtrip.py` | `uv run python tests/_spikes/spike_h_migration_roundtrip.py` | Migration `014_phase_b_ledger_and_tier` (drafted in `_spikes/draft_014_migration.py`) round-trips: upgrade head → schema assertions PASS (users.tier, users.stripe_customer_id, users.refund_writeoff_cents, credit_balances, credit_transactions, stripe_webhook_events, ck/uq/ix constraints, `cost_weights.ap_multiplier 1.0→1.15`); downgrade -1 → all schema artefacts gone, ap_multiplier reverted; re-upgrade head → idempotent. Migration body lives in `_spikes/` only — Wave 1 will copy it to `alembic/versions/`. | `PASS spike-h` (committed `46c6096`) |

## Discoveries / Course corrections

The spike pass surfaced corrections that Wave 1 must honor — these were
NOT in the original RESEARCH.md / PATTERNS.md; they were discovered at
the spike layer and are documented inside the spike scripts.

1. **Spike D — typed exception, not RPCError-with-substring (PATTERNS.md
   wrong).** Temporal SDK 1.27.x raises `temporalio.client.ScheduleAlreadyRunningError`
   when `create_schedule` collides with an existing schedule, NOT a
   generic `RPCError("already exists")`. The Wave 1 helper catches the
   typed exception first and keeps the substring fallback as
   defense-in-depth. See spike_d_temporal_schedule.py docstring +
   `_create_or_update`.

2. **Spike H — revision IDs ≤ 32 chars.** Initial draft used revision
   `014_phase_b_credit_ledger_and_tier` (33 chars), which exceeds
   alembic_version's `character varying(32)`. Shortened to
   `014_phase_b_ledger_and_tier` (27 chars) before the spike could pass.
   Wave 1 must use this exact string.

3. **Spike H — Postgres 12+ removed `pg_constraint.consrc`.** The
   schema-shape assertion originally read from `consrc`; replaced with
   `pg_get_constraintdef(oid)`. Future migration tests should follow
   the same pattern.

4. **Spike H — cost_weights data-migration assertion uses migration-010
   seed.** Migration 010 already seeds 6 baseline rows at
   `ap_multiplier=1.0`; the spike asserts that all 6 flip to 1.15
   post-upgrade and back to 1.0 post-downgrade. (Original draft
   incorrectly asserted a `provider='spike-h'` row that was never
   seeded.)

5. **Spike F — confirmed NO native uvicorn anti-pattern.** No
   side-launched uvicorn was running during the run. The deploy stack's
   `docker compose ps` shows the deploy container as the sole owner
   of `127.0.0.1:8000`, and the request's source IP `172.18.0.1` (the
   `deploy_default` bridge gateway) confirms it traversed the Docker
   port publish, not a host-local process. This is the exact
   architectural assertion the CLAUDE.md macOS rule demands.

## How to re-run end-to-end

```bash
# Python spikes (A, B, C, D, G, H) — D needs deploy Temporal up
cd api_server
for s in tests/_spikes/spike_a_webhook_signature.py \
         tests/_spikes/spike_b_debit_activity_contract.py \
         tests/_spikes/spike_c_atomic_ledger.py \
         tests/_spikes/spike_g_lazy_customer_create.py \
         tests/_spikes/spike_h_migration_roundtrip.py; do
  echo "=== $s ==="
  uv run python "$s"
done
AP_TEMPORAL_HOST=localhost:7233 uv run python tests/_spikes/spike_d_temporal_schedule.py

# Mobile spike (E) — needs booted iOS simulator
cd ../mobile
fvm flutter test integration_test/spike_e_inappwebview_intercept.dart -d <booted-sim-id>

# Manual spike (F) — see spike_f_stripe_cli_deploy_stack.md
```

## Wave 1 release condition

**Every spike PASSED.** Wave 1 is unblocked. The migration draft in
`tests/_spikes/draft_014_migration.py` is ready to copy verbatim into
`api_server/alembic/versions/014_phase_b_ledger_and_tier.py`.
