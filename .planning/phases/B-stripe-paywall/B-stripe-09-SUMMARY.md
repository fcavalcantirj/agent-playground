---
phase: B-stripe
plan: 09
subsystem: billing-paywall
tags: [wave-4, temporal, schedules, cron, retention, reconcile, sentry, prune, ledger]
requires:
  - phase: B-stripe-02
    provides: "services.ledger.{debit_user,credit_user,record_tier_change} + migration 014 schema (credit_balances, credit_transactions, stripe_webhook_events, users.tier)"
  - phase: B-stripe-06
    provides: "routes.billing_webhook._handle_checkout_completed — re-used verbatim by reconcile_stripe activity"
  - phase: B-stripe-07
    provides: "services.tier_enforcement.retention_window_days — single source of truth for prune_messages cutoffs"
  - phase: B-stripe-01
    provides: "Wave 0 spike-D template — typed ScheduleAlreadyRunningError + RPCError fallback shape, verified against deploy stack at localhost:7233"
  - phase: 28
    provides: "Temporal substrate (worker.py, RetryPolicy, sandbox-passthrough imports, ActivityEnvironment test harness)"
  - phase: 31
    provides: "instrumentation.sentry.init_sentry + before_send filter — H6 wiring; capture_message routes to ops alerting at error level"
provides:
  - "PruneMessagesActivities + PruneMessagesWorkflow: daily 03:00 UTC retention pruner enforcing D-09"
  - "ReconcileStripeActivities + ReconcileStripeWorkflow: 5-min poller backstopping missed Stripe webhooks via the same handler the live route uses (Pitfall 2)"
  - "ReconcileLedgerActivities + ReconcileLedgerWorkflow: nightly 04:30 UTC drift detector + repair-on-detect + Sentry alert at error level"
  - "temporal/schedules.py register_schedules helper — idempotent across boots via typed ScheduleAlreadyRunningError (spike-d corrected RESEARCH §Pattern 4)"
  - "Worker.py registers 3 workflows + 3 activities + calls register_schedules at boot"
  - "main.py lifespan calls register_schedules redundantly so schedules exist regardless of worker/api_server boot ordering"
affects:
  - "Phase B Wave 5 mobile (D-21 polling backstop now covered: 5-min reconcile catches missed webhooks)"
  - "Phase B exit gate D-25 — automated CI e2e + manual UAT both indirectly depend on the cron substrate being live"
  - "Future deploy stack — ops can introspect via tctl schedule describe / Temporal Web UI on the 3 schedule IDs"

tech-stack:
  added: []
  patterns:
    - "Class-bound activity + module-level fail-loud alias — third instance of the Phase 28 record_usage shape pattern (now applied to prune_messages, reconcile_stripe, reconcile_ledger)"
    - "Cron schedule registration helper with typed-exception-first idempotency (RPCError substring fallback as defense-in-depth)"
    - "Reconcile-via-same-handler discipline — reconcile_stripe activity calls billing_webhook._handle_checkout_completed verbatim so missed-webhook recovery shares the live route's tx + idempotency invariants byte-for-byte"
    - "Repair-on-detect for cache drift — D-17 ledger-as-truth means UPDATE the cache to ledger SUM, do NOT 'log + leave broken'"

key-files:
  created:
    - api_server/src/api_server/temporal/activities/prune_messages.py
    - api_server/src/api_server/temporal/activities/reconcile_stripe.py
    - api_server/src/api_server/temporal/activities/reconcile_ledger.py
    - api_server/src/api_server/temporal/workflows/prune_messages.py
    - api_server/src/api_server/temporal/workflows/reconcile_stripe.py
    - api_server/src/api_server/temporal/workflows/reconcile_ledger.py
    - api_server/src/api_server/temporal/schedules.py
    - api_server/tests/temporal/test_prune_messages_workflow.py
    - api_server/tests/temporal/test_reconcile_stripe_workflow.py
    - api_server/tests/temporal/test_reconcile_ledger_workflow.py
    - api_server/tests/temporal/test_schedules_idempotent.py
  modified:
    - api_server/src/api_server/temporal/worker.py
    - api_server/src/api_server/main.py

key-decisions:
  - "Catch typed ScheduleAlreadyRunningError FIRST, then RPCError substring fallback — Wave 0 spike D corrected RESEARCH §Pattern 4 + PATTERNS.md (which both said RPCError-only). The string-match path never fires against temporalio==1.27.x; keeping it as defense-in-depth covers SDK version churn."
  - "Schedule cadences: prune-messages cron 0 3 * * * (03:00 UTC daily), reconcile-stripe interval 5 min, reconcile-ledger cron 30 4 * * * (04:30 UTC nightly, after the prune so the diagnostic narrative in Temporal UI reads top-down)."
  - "Reconcile-stripe re-uses billing_webhook._handle_checkout_completed verbatim — same-tx dedupe-row INSERT + side-effect, same idempotency key (stripe_webhook_events.stripe_event_id UNIQUE). One handler shape, two callers (live route + reconcile cron)."
  - "Reconcile-stripe query window = 15 min (3× the cron period) — gives 2 missed-cron-tick redundancy. Matches CONTEXT D-Discretion notes."
  - "Reconcile-ledger emits Sentry capture_message at error level (Phase 31 H6 routes to ops alerts) AND repairs the cache via UPDATE in the same loop. D-17 invariant: ledger is canonical; the cache being wrong is the bug, never the inverse."
  - "register_schedules called from BOTH worker.py (fail-loud) and main.py (best-effort try/except). The redundancy ensures schedules exist regardless of which container boots first; the helper's idempotency makes the redundancy free of side effects."
  - "Worker.py uses fail-loud register_schedules call — schedule registration is part of the worker's contract, not best-effort. main.py uses try/except because api_server's route surface should stay available even if Temporal hiccups."

patterns-established:
  - "Three Phase B cron-driven workflows registered idempotently across worker + api_server boots — pattern any future Phase B sub-phase can replicate by adding a new schedule ID + handler to schedules.py."
  - "Reconcile-via-same-handler — reconcile activities should call into the live route's handler functions, not duplicate the side-effect logic. Saves invariants (idempotency key, transaction shape, error log format) from drifting between the two callers."
  - "ActivityEnvironment + real Postgres testcontainer + monkeypatched Sentry — sufficient for activity body coverage without booting a full Temporal cluster per test. Phase 28 D-22 ActivityEnvironment shape extended cleanly to all 3 new activities."

requirements-completed:
  - "D-09 (daily prune_messages_workflow — retention enforcement)"
  - "D-17 (nightly reconcile_ledger_workflow — drift detection + Sentry alert)"
  - "D-Discretion (reconcile_stripe_workflow — 5-min poller backstops missed webhooks)"

duration: ~45min
completed: 2026-05-09
---

# Phase B Plan B-stripe-09: Three Temporal Scheduled Workflows + Idempotent Registration Helper Summary

**Daily prune (D-09 retention), 5-min reconcile (D-Discretion missed-webhook backstop), nightly ledger drift check (D-17), all wired through one idempotent register_schedules helper that survives worker re-boots via the spike-d-corrected typed ScheduleAlreadyRunningError path.**

Wave 4 of Phase B is complete. The three cron substrates the rest of
Phase B's correctness story leans on are now live, idempotent across
boots, and exercised by 13/13 integration tests against real Postgres
testcontainer + ActivityEnvironment + the live deploy-stack Temporal
cluster at `localhost:7233`.

## Plan tasks executed

| Task | Description                                                                  | Commit    |
| ---- | ---------------------------------------------------------------------------- | --------- |
| 1    | 3 activities + 3 workflows + schedules.py (idempotent register helper)       | `82d0991` |
| 2a   | TDD tests — 13 cases covering prune, reconcile_stripe, reconcile_ledger, schedules idempotency | `894e947` |
| 2b   | Worker + lifespan wiring — Worker constructor + register_schedules at both boot paths | `f646bc5` |

## Truth audit (4/4 must_haves.truths satisfied)

| # | Truth                                                                                                                                                  | Evidence |
|---|--------------------------------------------------------------------------------------------------------------------------------------------------------|----------|
| 1 | PruneMessagesWorkflow runs daily, deletes inapp_messages older than the user's tier retention window (free=7d, pro=30d, ultra=never)                   | `test_prune_messages_deletes_messages_older_than_tier_retention` PASS — free deletes 4 (8/31/100/365d), pro deletes 3 (31/100/365d), ultra keeps 6. `test_prune_messages_keeps_ultra_user_messages_at_one_year` PASS. |
| 2 | ReconcileStripeWorkflow runs every 5 min, queries Stripe for checkout.session.completed events in the last 15 min that aren't in stripe_webhook_events, and processes them via the same handler logic as the webhook | `test_reconcile_stripe_picks_up_missed_event_and_applies_via_handler` PASS — applied count = 1, ledger topup row written, tier flipped free→ultra, dedupe row landed. `test_reconcile_stripe_queries_with_15_minute_window` PASS — `created.gte = now-900s`. |
| 3 | ReconcileLedgerWorkflow runs nightly, recomputes credit_balances.balance_cents from credit_transactions SUM, logs Sentry on any drift > $0.01         | `test_reconcile_ledger_emits_sentry_capture_message_when_drift_detected` PASS — 1 capture_message at level=error containing `user_id` + `drift`. `test_reconcile_ledger_repairs_cache_to_match_ledger_truth` PASS — cache repaired from 100 to ledger SUM 50. |
| 4 | register_schedules helper is idempotent — first call creates, second call updates without error (Pitfall 8 mitigated)                                   | `test_register_schedules_first_call_creates_all_three` PASS, `test_register_schedules_second_call_updates_without_error` PASS — 3rd call also succeeds, all 3 schedules still resolve via `get_schedule_handle().describe()`. Tests run against the live `deploy-temporal-1` cluster. |
| 5 | schedules registered ONCE per worker boot in worker.py main                                                                                              | `grep -c 'register_schedules' worker.py` = 2 (import + call); `grep -c 'PruneMessagesWorkflow\|ReconcileStripeWorkflow\|ReconcileLedgerWorkflow' worker.py` = 6 (3 imports + 3 in workflows= list). |

## Key links satisfied

| From                                | To                                                | Via                                              | Pattern               | Status |
|-------------------------------------|---------------------------------------------------|--------------------------------------------------|-----------------------|--------|
| `temporal/worker.py`                | `temporal/schedules.py::register_schedules`       | called once after Temporal client connect, before `worker.run()` | `register_schedules`  | ✅    |
| `temporal/activities/reconcile_stripe.py` | `routes/billing_webhook._handle_checkout_completed` | direct import inside activity body — same handler the live webhook uses | reconcile-via-same-handler | ✅    |
| `temporal/activities/reconcile_ledger.py` | `instrumentation/sentry.init_sentry` (Phase 31 H6) | `sentry_sdk.capture_message(..., level="error")`  | drift → ops alert via H6 | ✅    |
| `temporal/activities/prune_messages.py` | `services/tier_enforcement.retention_window_days` | direct call — D-05 single source of truth         | per-tier retention enforcement | ✅    |
| `main.py` lifespan                   | `temporal/schedules.py::register_schedules`       | redundant best-effort call after Temporal client connect | `register_schedules` | ✅    |

## Test results

```
tests/temporal/test_prune_messages_workflow.py ...                       [3 pass]
tests/temporal/test_reconcile_stripe_workflow.py ....                    [4 pass]
tests/temporal/test_reconcile_ledger_workflow.py ....                    [4 pass]
tests/temporal/test_schedules_idempotent.py ..                           [2 pass]

============================== 13 passed in 3.69s ==============================
```

Regression sweeps:

- `tests/temporal/` — **49 / 49 PASS** (8.83s) — no breakage of Phase 28 / 29 substrate.
- `tests/temporal/test_dispatch_message_workflow.py` — **7 / 7 PASS** (51.33s) — D-22 contract preserved (workflow file byte-unchanged).
- `tests/routes/test_billing_webhook.py` — **15 / 15 PASS** (8.82s) — billing_webhook handler still works (the activity imports it at runtime; no circular-import damage).

## Threat model audit

All 5 STRIDE entries from PLAN.md threat_model carried through:

| Threat ID  | Category       | Component                                | Disposition | Resolution                                                                                       |
|------------|----------------|------------------------------------------|-------------|--------------------------------------------------------------------------------------------------|
| T-B-DRIFT  | Tampering      | activities/reconcile_ledger.py           | mitigate    | Nightly recompute + Sentry alert + auto-repair-to-truth — all three implemented + test-asserted. |
| T-B-MISS   | Repudiation    | activities/reconcile_stripe.py           | mitigate    | 5-min poller queries Stripe directly; idempotency via stripe_webhook_events UNIQUE same-tx dedupe-row INSERT (Pitfall 2 inheritance from billing_webhook handler). |
| T-B-SCH    | DoS            | temporal/schedules.py                    | mitigate    | Typed `ScheduleAlreadyRunningError` first + RPCError substring fallback — Pitfall 8 mitigated; spike-d-proven against the live deploy cluster. |
| T-B-PRUNE  | Tampering      | activities/prune_messages.py             | mitigate    | DELETE filtered by tier-and-cutoff via JOIN on users.tier; user_id stays scoped to each tier's owners; ultra users never lose data (`days is None` skip). |
| T-B-LK     | InfoDisclosure | reconcile_stripe payload column          | mitigate    | `str(event)` is captured into `stripe_webhook_events.payload` for audit; for v1 the events listened to (per D-14) carry no PAN data — defense-in-depth note for future Stripe events that might add card details. |

## Deviations from Plan

### None — plan executed exactly as written.

The plan body's example code in Task 1 used `RPCError("already exists")` as the catch shape but `<read_first>` referenced spike-D explicitly, and the PLAN frontmatter `must_haves.artifacts` specifies "try/RPCError/update fallback". The objective + the `<critical_rules>` in the executor prompt + the spike-d source itself all ratify the typed-exception-first + RPCError-fallback pattern. The implementation matches the spike-d source verbatim — typed `ScheduleAlreadyRunningError` first, then RPCError substring fallback as defense-in-depth.

No Rule 1/2/3 auto-fixes were needed during implementation. No Rule 4 architectural decisions surfaced.

## Auth gates

None. The schedules idempotency test connects to `localhost:7233` (deploy stack) and self-skips if unreachable; in this session the deploy stack was up so the tests ran live and PASSed all 3 paths (create, update on 2nd call, update on 3rd call).

## Self-Check: PASSED

- [x] All 11 created files exist on disk (3 activities + 3 workflows + 1 schedules.py + 4 test files):
  - `api_server/src/api_server/temporal/activities/prune_messages.py`
  - `api_server/src/api_server/temporal/activities/reconcile_stripe.py`
  - `api_server/src/api_server/temporal/activities/reconcile_ledger.py`
  - `api_server/src/api_server/temporal/workflows/prune_messages.py`
  - `api_server/src/api_server/temporal/workflows/reconcile_stripe.py`
  - `api_server/src/api_server/temporal/workflows/reconcile_ledger.py`
  - `api_server/src/api_server/temporal/schedules.py`
  - `api_server/tests/temporal/test_prune_messages_workflow.py`
  - `api_server/tests/temporal/test_reconcile_stripe_workflow.py`
  - `api_server/tests/temporal/test_reconcile_ledger_workflow.py`
  - `api_server/tests/temporal/test_schedules_idempotent.py`
- [x] All 3 commits exist in `git log --oneline`:
  - `82d0991` — feat(B-stripe-09): 3 scheduled-workflow activities + schedules helper
  - `894e947` — test(B-stripe-09): activity + schedules idempotency tests
  - `f646bc5` — feat(B-stripe-09): register Phase B workflows + schedules in worker + lifespan
- [x] Worker constructor registers 3 new workflows + 3 new bound-method activities; `register_schedules` is called at line 289 (post-Worker, pre-`worker.run()`)
- [x] main.py lifespan calls register_schedules in a try/except after the Temporal client connect block (line 257-270)
- [x] Done criteria met: `grep -c 'register_schedules' worker.py` ≥ 1 (=2); `grep -c '<3 workflow names>' worker.py` = 6 (3 imports + 3 list entries); `grep -c 'register_schedules' main.py` ≥ 1 (=4)
- [x] No file in `api_server/alembic/versions/` was added or modified — Plan 09 is pure orchestration

Wave 4 complete. Phase B is now in Wave 5 (mobile UI surfaces — Plan 10+).
