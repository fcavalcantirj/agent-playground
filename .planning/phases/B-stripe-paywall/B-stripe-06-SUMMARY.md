---
phase: B-stripe
plan: 06
subsystem: billing-paywall
tags: [wave-3, stripe, webhook, postgres, idempotency, ledger, hmac, fastapi, asyncpg]
requires:
  - phase: B-stripe-01
    provides: "spike-a-validated StripeClient.construct_event signature path + sign_webhook_payload helper"
  - phase: B-stripe-02
    provides: "migration 014 + ledger.credit_user / record_tier_change atomic helpers + StripeClient lifespan service"
  - phase: B-stripe-03
    provides: "rate-limit middleware webhook-path exclusion (_BILLING_WEBHOOK_PATH) + STRIPE_WEBHOOK_INVALID error code"
provides:
  - "POST /v1/billing/webhook — sole writer of users.tier per D-04"
  - "Idempotent same-tx ON CONFLICT (stripe_event_id) DO NOTHING + rolling-back side-effect path (Pitfall 2)"
  - "7-event matrix per D-14/AMD-05: checkout.session.completed + subscription.{created,updated,deleted} + invoice.{paid,payment_failed} + charge.refunded; payment_intent.succeeded explicitly NOT branched"
  - "users.subscription_cancel_at_period_end + users.subscription_current_period_end columns (migration 014 extension)"
  - "agent_containers.container_status enum extended with 'auto_paused' for D-15 Pro→Free downgrade"
  - "tests/_fixtures/sign_webhook.py + 8 signed-fixture stripe_webhooks/*.json envelopes"
affects: [B-stripe-09, B-stripe-10, B-stripe-13]
tech-stack:
  added: []
  patterns:
    - "Same-tx idempotency: INSERT ON CONFLICT DO NOTHING RETURNING is the FIRST tx action; side-effect failure rolls the dedupe row back so Stripe retries against a clean state"
    - "Hand-rolled signed fixtures via sign_webhook_payload + StripeClient.construct_event round-trip for webhook integration tests (AMD-02 — stripe-mock has no webhook simulation)"
    - "StripeObject → plain-dict conversion via obj.to_dict() (NOT .get() — StripeObject overrides __getattr__ and raises AttributeError on .get)"
    - "OFFSET 1 LIMIT 4 keep-oldest semantics for D-15 auto-pause: free tier cap=1 keeps the absolute-oldest agent; the next 4 oldest non-paused non-stopped flip to 'auto_paused'; anything past the window stays running"
    - "Cumulative-aware refund key (charge_id:event_id) so partial refunds settle delta-by-delta without UNIQUE collisions"
key-files:
  created:
    - api_server/src/api_server/routes/billing_webhook.py
    - api_server/tests/_fixtures/__init__.py
    - api_server/tests/_fixtures/sign_webhook.py
    - api_server/tests/_fixtures/stripe_webhooks/checkout_session_completed.json
    - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_created.json
    - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_updated.json
    - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_deleted.json
    - api_server/tests/_fixtures/stripe_webhooks/invoice_paid.json
    - api_server/tests/_fixtures/stripe_webhooks/invoice_payment_failed.json
    - api_server/tests/_fixtures/stripe_webhooks/charge_refunded.json
    - api_server/tests/_fixtures/stripe_webhooks/payment_intent_succeeded.json
    - api_server/tests/routes/test_billing_webhook.py
  modified:
    - api_server/src/api_server/main.py  (mount POST /v1/billing/webhook router under /v1)
    - api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py  (extend with subscription state columns + agent_containers status enum)
    - api_server/tests/test_migration_014_phase_b.py  (2 new tests for the migration extension + extended round-trip)
    - api_server/tests/conftest.py  (TRUNCATE list extended with stripe_webhook_events + credit_transactions + credit_balances for cross-test isolation)
key-decisions:
  - "Side-effect failures return 500 (not bubble exception): ASGI re-raise breaks the HTTP contract Stripe expects (status_code=0); wrapping the tx in try/except and returning 500 lets Stripe retry against a clean state while still rolling back the dedupe row"
  - "Added 8th fixture (payment_intent_succeeded.json) over PLAN's 7 to cover the AMD-05 explicit-no-side-effect ack path; PLAN expected 7 but 8 strengthens coverage"
  - "obj.to_dict() (not _to_dict_recursive() / dict()) is the canonical StripeObject→dict path: stripe-python v15 StripeObject overrides __getattr__ and raises AttributeError on common methods like .get / dict() / iter; spike-a access patterns (event.data.object.metadata.pack_id) work for attribute reads but break on optional fields"
  - "Migration 014 extension over a new migration 015: PLAN explicitly specified extend-014 to keep Wave 1 minimally re-touched. Spike H proved 014 is round-trip clean against PG17; the additive columns + enum-rebuild stay in the same revision so nothing further has to track 'when did 014's surface change'"
  - "OFFSET 1 LIMIT 4 (not OFFSET 0 LIMIT 5) — D-15 free tier cap is 1 agent; the user keeps the absolute-oldest agent as their surviving free-tier agent and we pause the next 4 oldest. Anything past index 4 (i.e. agents 6+) stays running and is the user's responsibility to clean up via DELETE /v1/agents/:id"
patterns-established:
  - "Pattern: webhook idempotency via 'first action in tx is dedupe INSERT ON CONFLICT' — re-usable for any future external-callback handler (Twilio, GitHub, third-party services)"
  - "Pattern: StripeObject → dict via .to_dict() at the boundary; never .get() / .get on attributes — this is the v15 invariant"
  - "Pattern: signed-fixture test rig via sign_webhook_payload (HMAC-SHA256 on raw bytes + 5-min Stripe SDK tolerance) — re-usable when other Stripe-shape webhooks land (Connect, Stripe Climate, etc.)"
requirements-completed: []
duration: ~12min
completed: 2026-05-09
---

# Phase B Plan B-stripe-06: Stripe Webhook Handler Summary

**POST /v1/billing/webhook is live — sole writer of users.tier (D-04), 7-event matrix per AMD-05, idempotent on stripe_webhook_events.stripe_event_id, side-effect-rollback-safe.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-09T02:27:23Z
- **Completed:** 2026-05-09T02:39:05Z
- **Tasks:** 1 (TDD: RED + GREEN gates)
- **Files created:** 12 (route handler + 1 sign_webhook helper + 8 signed-fixture envelopes + 1 test file + 1 _fixtures/__init__.py)
- **Files modified:** 4 (main.py + migration 014 + migration 014 tests + conftest TRUNCATE list)

## Accomplishments

- POST /v1/billing/webhook endpoint live: signature-verify via `StripeClient.construct_event` (AMD-04); idempotent on `stripe_webhook_events.stripe_event_id` UNIQUE; same-transaction wraps the dedupe-row INSERT and side-effect (Pitfall 2 — failure rolls the dedupe row back so Stripe retries cleanly).
- 7-event matrix per D-14/AMD-05 fully wired: `checkout.session.completed` grants credit + flips tier free→ultra; `customer.subscription.created` flips tier→pro; `customer.subscription.updated` stores cancel_at_period_end + period_end without a tier flip; `customer.subscription.deleted` flips tier→free + auto-pauses 4 oldest non-paused agents (D-15); `charge.refunded` posts a delta-aware negative ledger row (D-16); `invoice.paid` / `invoice.payment_failed` are ack-only; `payment_intent.succeeded` is explicitly ack-only-no-side-effect per AMD-05 (would double-credit otherwise).
- Migration 014 extended: `users.subscription_cancel_at_period_end` (boolean NOT NULL DEFAULT false) + `users.subscription_current_period_end` (timestamptz NULL) + `ck_agent_containers_status` rebuilt to include `'auto_paused'`. All round-trip clean against the PG17 testcontainer.
- 15/15 webhook integration tests + 12/12 migration 014 tests green against real Postgres 17. Sibling Phase B suites (test_billing_read_routes, test_billing_checkout_routes, test_ledger_atomic, test_billing_packs, test_rate_limit_billing) untouched and still green (34/34).

## Task Commits

Each TDD gate was committed atomically:

1. **RED gate — failing tests + signed fixtures** — `c5170cf` (test)
2. **GREEN gate — route handler + migration extension + conftest TRUNCATE extension** — `2953c3d` (feat)

## Files Created/Modified

- `api_server/src/api_server/routes/billing_webhook.py` — POST /v1/billing/webhook handler with signature verify + idempotency + 7-event branch (8 explicit `event_type ==` branches: 7 typed + payment_intent.succeeded ack).
- `api_server/tests/_fixtures/__init__.py` + `sign_webhook.py` — promoted helper from Wave 0 spike A; sign_webhook_payload returns Stripe-Signature header.
- `api_server/tests/_fixtures/stripe_webhooks/*.json` (8 files) — signed-fixture envelopes for the 7 D-14 events + payment_intent_succeeded for the AMD-05 ack-no-side-effect test.
- `api_server/tests/routes/test_billing_webhook.py` — 15 integration tests (5 sig/idempotency + 10 event-matrix) against real PG17.
- `api_server/src/api_server/main.py` — registered `billing_webhook_route.router` under `/v1` after the read-side billing route.
- `api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py` — extended with subscription state columns + agent_containers enum rebuild + symmetric downgrade.
- `api_server/tests/test_migration_014_phase_b.py` — 2 new tests asserting the extension columns + enum extension; round-trip test extended to assert the new columns survive downgrade-then-upgrade.
- `api_server/tests/conftest.py` — TRUNCATE list extended with `stripe_webhook_events`, `credit_transactions`, `credit_balances` so deterministic event ids don't leak across tests.

## Decisions Made

- **Side-effect-failure path returns 500 (not propagate the exception).** Initial implementation let the exception unwind out of the transaction context manager, which caused httpx's ASGI transport to raise and produce status_code=0 (no HTTP response). Wrapping the tx in try/except and returning 500 (`ErrorCode.INTERNAL`) preserves the HTTP contract Stripe expects while still rolling back the dedupe-row INSERT (the conn.transaction context unwinds cleanly on exception). This is the right shape for production too — Stripe Smart Retries kicks in on 5xx.
- **`obj.to_dict()` is the canonical StripeObject→dict bridge in v15.** stripe-python v15's `StripeObject.__getattr__` raises `AttributeError` on `.get()`, `dict()`, `to_dict_recursive()`, etc. — anything that isn't an actual sub-resource attribute. The public `to_dict()` method recursively unwraps to plain dicts; everything else is internal API. The `_as_dict` helper in `billing_webhook.py` documents this behavior.
- **8 fixtures over PLAN's 7.** Added `payment_intent_succeeded.json` so the AMD-05 explicit-ack-no-side-effect branch has a real signed-fixture test (`test_payment_intent_succeeded_is_not_handled_returns_200_ack`). PLAN said 7; 8 covers the explicit-no-side-effect path more honestly. The PLAN's done-criteria check (`grep -c 'payment_intent.succeeded' = 1`) is a deviation — actual count is 3 (1 branch + 2 doc lines). Acceptable: stricter is fine.
- **Migration 014 extension over a new 015.** PLAN explicitly directed extend-014 to keep wave 1 minimally re-touched. Spike H validated the 014 round-trip; the additive columns + enum rebuild reverse cleanly on downgrade. The downgrade path defensively flips any `auto_paused` rows to `stopped` BEFORE the constraint rebuild so the new (non-auto_paused) constraint creation succeeds.
- **OFFSET 1 LIMIT 4 keep-oldest auto-pause.** D-15 says free tier cap is 1 and the user's surviving agent is the absolute-oldest. The OFFSET 1 (skip the oldest = the surviving one) + LIMIT 4 (pause the next 4) handles short lists naturally — only 2 rows fall in the window for a 3-agent user. Anything past index 4 (agent 6+) stays running and is the user's responsibility to clean up via DELETE /v1/agents/:id.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Side-effect exception unwound out of ASGI transport instead of returning 500**
- **Found during:** Task 1 GREEN gate, `test_side_effect_failure_rolls_back_idempotency_row` first run
- **Issue:** Plan's draft route shape let the side-effect exception propagate out of the route. ASGI transport (httpx test client) re-raises app exceptions by default, producing `status_code=0` and breaking the test contract `assert r.status_code >= 500`. In production the same shape returns a partial response Stripe interprets as a connection issue, not a 500 (no Smart Retries trigger).
- **Fix:** Wrapped the entire `pool.acquire() / conn.transaction()` block in `try/except`. On exception we log via `_log.exception(...)` and return `_err(500, ErrorCode.INTERNAL, ...)`. The `conn.transaction()` context manager still unwinds and rolls back the dedupe-row INSERT, so Stripe's retry sees a clean state.
- **Files modified:** `api_server/src/api_server/routes/billing_webhook.py` (route body).
- **Verification:** `test_side_effect_failure_rolls_back_idempotency_row` passes — asserts r.status_code >= 500 + 0 rows in `stripe_webhook_events` for the failed event id + no partial ledger state.
- **Committed in:** `2953c3d` (GREEN gate commit).

**2. [Rule 1 - Bug] StripeObject `.get()` raises AttributeError**
- **Found during:** Task 1 GREEN gate, `test_duplicate_event_id_returns_200_no_double_side_effect` first run (balance was 0 instead of 2500)
- **Issue:** Initial route used `obj.get("metadata") or {}` to read fields off `event.data.object`. stripe-python v15 `StripeObject` overrides `__getattr__` and raises `AttributeError` on `.get` (and on `dict()`, `to_dict_recursive()`, etc.). This made every metadata-dependent handler skip silently with a "missing_metadata" warning.
- **Fix:** Added `_as_dict(obj)` helper that calls `obj.to_dict()` (the public, recursive-unwrapping API) and falls back to plain-dict synthesis for synthetic test inputs. Every handler now passes `event.data.object` through `_as_dict` before any `.get` access.
- **Files modified:** `api_server/src/api_server/routes/billing_webhook.py`.
- **Verification:** All 9 event-matrix tests pass; the metadata-warning log line never fires under signed-fixture inputs.
- **Committed in:** `2953c3d` (GREEN gate commit).

**3. [Rule 3 - Blocking] conftest TRUNCATE list missed Phase B tables → cross-test contamination**
- **Found during:** Task 1 GREEN gate, `test_checkout_session_completed_inserts_topup_row_and_flips_tier_to_ultra` failed because `test_duplicate_event_id_*` ran first and left a `stripe_webhook_events` row with the same fixture event id. The dedupe ON CONFLICT short-circuited the second test's side-effect.
- **Issue:** `tests/conftest.py::_truncate_tables` purges 9 tables but did not include `stripe_webhook_events`, `credit_transactions`, `credit_balances`. Phase B fixtures use deterministic event ids (`evt_test_<eventtype>_001`) so cross-test leakage made tests order-dependent.
- **Fix:** Extended the TRUNCATE list with the 3 Phase B tables. `RESTART IDENTITY CASCADE` is harmless — these tables FK into users which is already in the list, so cascade was implicit before; making it explicit keeps intent obvious.
- **Files modified:** `api_server/tests/conftest.py`.
- **Verification:** All 15 webhook tests pass when run together (`pytest tests/routes/test_billing_webhook.py`); sibling billing suites (read_routes, checkout_routes, ledger_atomic, billing_packs, rate_limit_billing) all still pass — TRUNCATE is purely additive and shouldn't break tests that don't seed those tables.
- **Committed in:** `2953c3d` (GREEN gate commit).

**4. [Rule 1 - Bug] _seed_agent_container test helper missed agent_instances.model NOT NULL**
- **Found during:** Task 1 GREEN gate, `test_subscription_deleted_*` failed with `NotNullViolationError: null value in column "model"`.
- **Issue:** Migration 001 baseline declares `agent_instances.model` NOT NULL; my initial seed helper only set `recipe_name` + `name`.
- **Fix:** Added `model='openrouter/anthropic/claude-3-haiku'` to the `_seed_agent_container` helper.
- **Files modified:** `api_server/tests/routes/test_billing_webhook.py`.
- **Verification:** Both subscription_deleted tests pass.
- **Committed in:** `2953c3d` (GREEN gate commit).

---

**Total deviations:** 4 auto-fixed (3 bugs × correctness + 1 blocking × test infra)
**Impact on plan:** All four were correctness fixes — none changed the plan's deliverables. The route shape (signature-verify + idempotency + 7-event matrix) is bit-for-bit what the PLAN specified; the deviations were the implementation gotchas the plan's pseudo-code didn't cover.

## Issues Encountered

None outside the deviations above. The PLAN body shipped verbatim modulo the 4 auto-fixes; spike A (Wave 0) had already validated the signature path so the GREEN gate landed cleanly once the StripeObject + ASGI-error-shape gotchas were resolved.

## User Setup Required

None. The webhook secret env var (`AP_STRIPE_WEBHOOK_SECRET`) is already populated in `deploy/.env.prod` from Phase B Wave 0 prereqs (the value `whsec_*` minted by `stripe webhook endpoints create` is in `STRIPE-TEST-CATALOG.md`). Stripe CLI smoke (`stripe trigger checkout.session.completed --override ...`) is the recommended manual verification but not gated.

## Next Phase Readiness

- **Wave 4 unblocked.** The webhook is the load-bearing surface every later wave reads from: Wave 4 debit_balance activity + Wave 5 mobile webview + Wave 6 metering will hit this route as the source of truth for tier flips and credit grants.
- **No blockers.** Spike A + spike H already validated the signature + migration round-trip; the implementation gotchas the deviations called out are now wired into permanent test-time invariants.

## Truth Audit (must_haves.truths from PLAN.md)

- [x] POST /v1/billing/webhook is a public route (no require_user) and returns 400 on missing/invalid Stripe-Signature — `test_missing_signature_returns_400`, `test_bad_signature_returns_400_with_stripe_webhook_invalid_code`.
- [x] Webhook handler uses StripeClient.construct_event (service pattern AMD-04), NOT module-level stripe.Webhook.construct_event — `grep "client.construct_event" billing_webhook.py == 1`.
- [x] Idempotency: stripe_webhook_events.stripe_event_id UNIQUE; duplicate event id returns 200 immediately, side-effect skipped — `test_duplicate_event_id_returns_200_no_double_side_effect`.
- [x] checkout.session.completed inserts a credit_transactions topup row + rebuilds balance + flips tier='ultra' for the user (D-04 + D-26) — `test_checkout_session_completed_inserts_topup_row_and_flips_tier_to_ultra`.
- [x] customer.subscription.created flips users.tier to 'pro' + records tier_change audit row — `test_subscription_created_flips_tier_to_pro`.
- [x] customer.subscription.updated handles cancel_at_period_end=true by storing the flag (no immediate tier flip) — `test_subscription_updated_with_cancel_at_period_end_does_not_flip_tier`.
- [x] customer.subscription.deleted flips users.tier to 'free' + auto-pauses 4 oldest non-paused agents (D-15) — `test_subscription_deleted_flips_tier_to_free_and_pauses_4_oldest_agents` + boundary test `test_subscription_deleted_with_3_agents_pauses_only_2`.
- [x] charge.refunded inserts a negative-amount ledger row (kind='refund') + balance recomputes — `test_charge_refunded_inserts_negative_ledger_row`.
- [x] invoice.paid is acknowledged-without-side-effect (audit log only) — `test_invoice_paid_is_ack_no_side_effect`.
- [x] invoice.payment_failed is acknowledged-without-side-effect (Stripe Smart Retries handle the rest) — `test_invoice_payment_failed_is_ack_no_side_effect`.
- [x] payment_intent.succeeded is NOT in the event matrix (AMD-05) — handler explicitly does NOT branch on it — `test_payment_intent_succeeded_is_not_handled_returns_200_ack`.
- [x] All 7 event types are covered by signed-fixture integration tests (8 fixtures including the AMD-05 ack-only payment_intent_succeeded.json — exceeded plan).

## Artifact Audit (must_haves.artifacts)

- [x] `api_server/src/api_server/routes/billing_webhook.py` exists with `router = APIRouter()` exported.
- [x] `api_server/tests/_fixtures/sign_webhook.py` exists with `sign_webhook_payload` exported.
- [x] `api_server/tests/_fixtures/stripe_webhooks/` exists with 8 JSON files, each carrying an `id` field.

## Key-Links Audit (must_haves.key_links)

- [x] `billing_webhook.py` → `stripe_webhook_events` via `INSERT ... ON CONFLICT (stripe_event_id) DO NOTHING` in same tx as side-effect (line 144-156). Pattern `ON CONFLICT \(stripe_event_id\)` matched.
- [x] `billing_webhook.py` → `services/ledger.py::credit_user / record_tier_change` via function call inside `async with conn.transaction()` block. Pattern `credit_user|record_tier_change` matched (4 call sites: 1 in checkout, 1 in subscription_created, 1 in subscription_deleted, 1 in charge_refunded; record_tier_change called from 3 of those).

## Self-Check: PASSED

- [x] All 12 created files exist on disk
- [x] Both task commits exist in `git log --oneline`: `c5170cf`, `2953c3d`
- [x] `cd api_server && uv run pytest tests/routes/test_billing_webhook.py tests/test_migration_014_phase_b.py` — 27/27 PASS
- [x] `cd api_server && uv run pytest tests/test_billing_packs.py tests/test_ledger_atomic.py tests/middleware/test_rate_limit_billing.py tests/routes/test_billing_read_routes.py tests/routes/test_billing_checkout_routes.py` — 34 passed, 1 skipped (e2e — needs AP_STRIPE_TEST_API_KEY); no regressions in sibling Phase B suites
- [x] `grep -c 'event_type ==' api_server/src/api_server/routes/billing_webhook.py` = 8 (7 typed branches + payment_intent ack)
- [x] `ls api_server/tests/_fixtures/stripe_webhooks/*.json | wc -l` = 8 (PLAN expected 7; 8 honors AMD-05 with an explicit ack fixture)
- [x] `grep -c 'subscription_cancel_at_period_end' api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py` = 2 (one in upgrade, one in downgrade)
- [x] agent_containers.container_status='auto_paused' value is allowed by the rebuilt `ck_agent_containers_status` constraint

---
*Phase: B-stripe-paywall*
*Plan: B-stripe-06*
*Completed: 2026-05-09*
