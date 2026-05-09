---
phase: B-stripe-paywall
plan: 08
subsystem: payments
tags: [temporal, stripe, ledger, asyncpg, fastapi, llm-proxy, idempotency]

# Dependency graph
requires:
  - phase: B-stripe-02
    provides: services/ledger.py atomic helpers (debit_user, credit_user) + migration 014 schema (users.tier, credit_balances, credit_transactions)
  - phase: B-stripe-04
    provides: tier projection on /v1/usage/summary (mobile reads tier from API)
  - phase: 28
    provides: dispatch_message workflow shape + D-22 debit_balance activity contract lock
  - phase: 29
    provides: llm_proxy section-numbered comment scaffold (section 1, 2, 3)
provides:
  - Real ledger debit on every Ultra-tier successful upstream LLM call (D-13)
  - Pre-flight 402 INSUFFICIENT_BALANCE gate at section 2.5 of llm_proxy (D-12)
  - Idempotent debit_balance Temporal activity (UNIQUE-violation safe under retry)
  - Class-bound DebitBalanceActivities with db_pool injection (mirrors RecordUsageActivities)
affects: [B-stripe-09, B-stripe-10, B-stripe-11, B-stripe-12, B-stripe-13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Class-bound Temporal activities + module-level alias (preserves Phase 28 D-22 import path while letting worker register class-bound bound method via shared activity-name registration)"
    - "Pre-flight 402 fresh-conn predicate (does NOT piggy-back on outer transactions; LEFT JOIN coalesces missing balance rows to 0)"

key-files:
  created:
    - api_server/tests/temporal/test_debit_balance_activity.py
    - api_server/tests/routes/test_llm_proxy_402.py
  modified:
    - api_server/src/api_server/temporal/activities/debit_balance.py
    - api_server/src/api_server/temporal/worker.py
    - api_server/src/api_server/routes/llm_proxy.py
    - .planning/phases/B-stripe-paywall/deferred-items.md

key-decisions:
  - "Module-level alias `debit_balance = DebitBalanceActivities.debit_balance` preserves the workflow's `debit_balance.debit_balance` import path while the worker registers the class-bound bound method — Temporal SDK dispatches by activity-name (`debit_balance`) so both reach the same registration"
  - "Pre-flight 402 uses fresh asyncpg conn (not piggy-back on any outer tx) because the predicate is short-lived and the existing handler has no active transaction at the section 2.5 insertion point"
  - "Test 4 (cost_usd null path) seeded explicit `Decimal('0')` instead of NULL — usage_logs.cost_usd is NOT NULL with default 0 from migration 011; the activity's `cost_cents <= 0` guard handles both equivalently"

patterns-established:
  - "Phase 28 D-22 contract preservation: workflow file is byte-unchanged across Phase B body replacement; activity-name registration on bound method + module-level callable alias keeps the import path stable"
  - "Pre-flight gate predicate `tier='ultra' AND balance < 1` covers BOTH zero AND negative balances (Pitfall 6) — single predicate, no special-case branch"

requirements-completed: []  # Plan frontmatter has no `requirements:` field — Phase B uses D-XX decisions, not REQUIREMENTS.md slugs

# Metrics
duration: 10min
completed: 2026-05-09
---

# Phase B-stripe-paywall Plan 08: Temporal debit_balance + LLM proxy pre-flight 402 Summary

**Closed the Phase B billing loop: every successful Ultra-tier LLM call now atomically debits the credit ledger (idempotent under Temporal retry), and balance ≤ 0 short-circuits at section 2.5 of llm_proxy with INSUFFICIENT_BALANCE 402 before any upstream forward.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-09T03:00:52Z
- **Completed:** 2026-05-09T03:10:21Z
- **Tasks:** 2 (both TDD; 4 commits across RED/GREEN gates)
- **Files modified:** 6 (3 source + 2 test + 1 deferred-items log)

## Accomplishments

- `DebitBalanceActivities` class with `db_pool` injection replaces the Phase 28 D-22 stub — the activity now reads `users.tier` + the latest `usage_logs` row and atomically inserts a debit ledger row + rebuilds the balance cache via `services.ledger.debit_user`
- Idempotent on UNIQUE(reference_id=usage_log.id, reference_type='usage_log') — Temporal retry produces no double-debit (Wave 0 spike-b's contract proven against migration 014 schema)
- Worker registers `debit_acts.debit_balance` (class-bound) instead of the standalone D-22 no-op; module-level alias preserves the workflow's `debit_balance.debit_balance` import path so the workflow file stays byte-unchanged (D-22 lock honored)
- Pre-flight 402 block at llm_proxy section 2.5 (between BYOK resolve and body mutation) returns INSUFFICIENT_BALANCE the moment `tier='ultra' AND balance_cents < 1` — the predicate catches both zero AND any negative balance (D-16 + Pitfall 6)
- BYOK tiers (free / pro) bypass the gate entirely — they pay the upstream provider directly per D-02

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1 RED — failing tests for debit_balance activity** — `eed8899` (test)
2. **Task 1 GREEN — debit_balance body + class-bound rewrite + worker registration** — `87c7093` (feat)
3. **Task 2 RED — failing tests for llm_proxy pre-flight 402** — `331a44f` (test)
4. **Task 2 GREEN — pre-flight 402 in llm_proxy section 2.5** — `6437297` (feat)

## Files Created/Modified

- **`api_server/src/api_server/temporal/activities/debit_balance.py`** — Replaced D-22 stub body with class-bound `DebitBalanceActivities`; reads tier + usage_log; calls `debit_user`; module-level alias preserves workflow import path
- **`api_server/src/api_server/temporal/worker.py`** — Switched import from standalone `debit_balance` to `DebitBalanceActivities`; instantiates `debit_acts` alongside `usage_acts`/`mark_acts`/etc.; activities= list now registers `debit_acts.debit_balance`
- **`api_server/src/api_server/routes/llm_proxy.py`** — New section 2.5 block between BYOK resolve and body mutation: LEFT JOIN `users` × `credit_balances`, predicate `tier='ultra' AND balance_cents < 1` → 402 INSUFFICIENT_BALANCE
- **`api_server/tests/temporal/test_debit_balance_activity.py`** — 9 tests (8 behavior + 1 byte-identity grep) covering Free/Pro short-circuit, status='failed'/cost=0/missing-row → "0", Ultra+success → ledger insert + cache rebuild, Temporal retry idempotency
- **`api_server/tests/routes/test_llm_proxy_402.py`** — 6 tests covering pass-through (free@0¢ / pro@0¢ / ultra@1¢) and 402 (ultra@0¢ / ultra@-50¢ / 402-skips-upstream)
- **`.planning/phases/B-stripe-paywall/deferred-items.md`** — Logged 3 pre-existing test_llm_proxy.py failures from Phase B-stripe-02's 1.15× ap_multiplier shift

## Decisions Made

- **Module-level alias for the activity** — The workflow imports `from ..activities import debit_balance` and references `debit_balance.debit_balance`. Class-bound activities lose that path; resolution: keep `debit_balance = DebitBalanceActivities.debit_balance` at module bottom. Temporal's name-based dispatch routes the workflow's call to the worker's registered bound method via the shared `@activity.defn(name="debit_balance")` registration.
- **Fresh asyncpg conn for the 402 predicate** — Section 2.5 acquires its own conn from the pool. The handler at this point has no outstanding transaction; piggy-backing would have required threading a conn through the IP-map / BYOK-cache lookups for no gain.
- **`balance_cents < 1` predicate** — Single condition catches `0` AND negative values; no special-case branch needed for D-16 refund-driven negatives (Pitfall 6 cross-checked in test #5).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test for null `cost_usd` re-shaped to `Decimal('0')`**
- **Found during:** Task 1 GREEN gate run (`test_returns_zero_when_usage_logs_cost_usd_is_null` failed with `NotNullViolationError`)
- **Issue:** PLAN.md's behavior list says "test_returns_zero_when_usage_logs_cost_usd_is_null" but `usage_logs.cost_usd` is NOT NULL (DEFAULT 0) per migration 011 — the literal NULL seed is impossible.
- **Fix:** Seeded `Decimal('0')` instead of NULL; the activity's `cost_cents <= 0` guard returns "0" for both equivalently. Test docstring documents the equivalence.
- **Files modified:** `api_server/tests/temporal/test_debit_balance_activity.py`
- **Verification:** Test passes; behavior intent preserved.
- **Committed in:** `87c7093` (Task 1 GREEN gate commit, alongside the implementation)

---

**Total deviations:** 1 auto-fixed (Rule 1 — test re-shape to honor NOT NULL schema; intent preserved)
**Impact on plan:** No scope creep; the activity's defensive `is None` branch is kept (dead code today; defense-in-depth if a future migration ever drops NOT NULL).

## Issues Encountered

- **3 pre-existing test failures in `tests/routes/test_llm_proxy.py`** — `test_d09_no_inline_falls_back_to_cost_weights`, `test_d09_anthropic_does_not_use_inline_path`, `test_d09_openai_direct_does_not_use_inline_path`. All assert against `Decimal('0.00004500')`-shaped values that pre-date migration 014's `cost_weights.ap_multiplier` 1.0 → 1.15 bump. Verified pre-existing via `git stash` + re-run on commit `331a44f` (BEFORE Plan 08's llm_proxy.py edit). Logged in `deferred-items.md`; out-of-scope per executor scope-boundary rule. Triage suggestion: a Phase B follow-up to audit + update every cost-derived test expectation in one batch.

## User Setup Required

None — no external service configuration required. The pre-flight 402 fires automatically once a user is on tier='ultra' with depleted balance; this state is reachable today via the existing Stripe webhook path (B-stripe-06) or admin write-off (D-16).

## Threat Model Audit

| Threat ID | Status | Evidence |
|-----------|--------|----------|
| T-B-IDP (Tampering — debit_balance idempotency) | mitigated | Test `test_idempotent_on_temporal_retry` runs the activity twice; 1 debit row inserted; balance unchanged on second call (UniqueViolation caught + Decimal returned) |
| T-B-NB (Tampering — pre-flight gate negative balance) | mitigated | Test `test_proxy_returns_402_for_ultra_tier_with_negative_balance` seeds `balance_cents=-50`; predicate fires; upstream call_count == 0 |
| T-B-CONTRACT (Tampering — D-22 lock) | mitigated | Test `test_call_site_byte_identity_in_dispatch_message_workflow_unchanged` grep-locks the call site; `git diff workflows/dispatch_message.py` produces zero lines of output |
| T-B-ZERO (Tampering — debit only on success) | mitigated | Tests `test_returns_zero_when_usage_logs_status_is_failed`, `test_returns_zero_when_usage_logs_cost_usd_is_null`, `test_returns_zero_when_no_usage_logs_row_for_message` all assert "0" return + zero ledger rows on the failure paths |

## Next Phase Readiness

- **Wave 4 partial.** Plan 09 (`prune_messages_workflow`) is the remaining Wave 4 plan. Plans 10-13 (Wave 5+ — Stripe schedules, mobile UI, e2e gate) follow.
- **Billing loop closed end-to-end on the api_server side.** An Ultra user with a top-up can now: (a) chat through the proxy → real cost recorded in `usage_logs` → real ledger debit via Temporal → balance cache rebuilt; (b) when balance hits 0 → next chat returns 402 INSUFFICIENT_BALANCE before upstream is called.
- **Mobile-side render of 402** is wave 5 work — the API surface is ready (existing `/v1/billing/balance` from Plan 03 + new 402 envelope shape).

## Self-Check: PASSED

**File existence:**
- `api_server/src/api_server/temporal/activities/debit_balance.py` — FOUND (modified)
- `api_server/src/api_server/temporal/worker.py` — FOUND (modified)
- `api_server/src/api_server/routes/llm_proxy.py` — FOUND (modified)
- `api_server/tests/temporal/test_debit_balance_activity.py` — FOUND (created)
- `api_server/tests/routes/test_llm_proxy_402.py` — FOUND (created)

**Commit existence:**
- `eed8899` — FOUND (Task 1 RED)
- `87c7093` — FOUND (Task 1 GREEN)
- `331a44f` — FOUND (Task 2 RED)
- `6437297` — FOUND (Task 2 GREEN)

**TDD gate compliance (plan_type=execute, tasks both `tdd="true"`):**
- Task 1 RED → GREEN sequence intact (test commit before feat commit) ✓
- Task 2 RED → GREEN sequence intact ✓

**Test results:**
- 9/9 `test_debit_balance_activity.py` PASS ✓
- 6/6 `test_llm_proxy_402.py` PASS ✓
- 7/7 `test_dispatch_message_workflow.py` regression PASS ✓
- 12/15 `test_llm_proxy.py` regression PASS (3 pre-existing failures deferred) ✓

**Acceptance gates:**
- `git diff api_server/src/api_server/temporal/workflows/dispatch_message.py` is empty ✓
- `grep -c '@activity.defn(name="debit_balance")'` exact-decorator-line count = 1 (line 60) ✓ (the file's full grep returns 3 because of two docstring mentions; the functional contract is the decorator itself)
- `grep -c 'class DebitBalanceActivities'` = 1 ✓
- `grep -c 'debit_acts = DebitBalanceActivities'` (worker.py) = 1 ✓
- `grep -c '# ---------- 2.5. Phase B pre-flight'` (llm_proxy.py) = 1 ✓
- `grep -c 'INSUFFICIENT_BALANCE'` (llm_proxy.py) = 1 ✓

---
*Phase: B-stripe-paywall*
*Plan: 08*
*Completed: 2026-05-09*
