---
phase: B-stripe
plan: 04
subsystem: billing.tier-projection
tags: [tier-aware, dumb-client, projection, phase-a-regression-gate]
wave: 2
status: SHIPPED

dependency-graph:
  requires:
    - "B-stripe-02 (migration 014 — users.tier column + credit_balances table; D-17 ledger-as-truth)"
  provides:
    - "Tier-aware /v1/usage/summary projection — single endpoint, mobile branches render on summary.tier"
    - "Phase A regression gate — exact key-set assertion for free-tier consumers (T-B-LEAK)"
  affects:
    - "Mobile UsageTickerWidget (Wave 5 update — branches USD vs credit-balance display on summary.tier)"
    - "Web playground (Phase B.2 — same contract)"

tech-stack:
  added: []
  patterns:
    - "response_model_exclude_none=True — strips ultra-only None fields from wire response (Phase A consumers see byte-identical key-set)"
    - "LEFT JOIN credit_balances + COALESCE(balance,0) — sparse-row safe read"

key-files:
  created:
    - "api_server/tests/routes/test_usage_summary_tier_projection.py"
  modified:
    - "api_server/src/api_server/routes/usage.py"

decisions:
  - "Used FastAPI response_model_exclude_none=True (NOT model_dump(exclude_none=True) at handler) so the OpenAPI schema still documents the optional fields while the wire response strips them for free/pro"
  - "tier defaults to 'free' on the model so it's always projected (Phase A consumers see only one additive field, never absent)"
  - "Defensive 'tier_row is None' fallback to 'free' tier — surfaces Phase A shape rather than 500 if user row vanishes between auth and read"

metrics:
  duration: "~6 minutes"
  completed: "2026-05-09T01:59:49Z"
  tasks_completed: 1
  test_count: "6 new + 9 Phase A regression + 12 sibling billing read routes = 27/27 PASS"
  file_count: 2
---

# Phase B Plan B-stripe-04: Tier-aware /v1/usage/summary Projection Summary

Added `tier` (always) + `balance_cents` / `display_balance_cents` (clamped >= 0) / `is_negative` (only for `tier='ultra'`) to `/v1/usage/summary`. Mobile branches render on `summary.tier` — single endpoint, no client-side aggregation (dumb-client rule, golden rule #2).

## Objective Recap

Phase B Wave 2 sibling plan to `B-stripe-03` (read-side billing routes). Where 03 added a *new* `/v1/billing/balance` route, Plan 04 *extends* the existing Phase A `/v1/usage/summary` with the same tier+balance projection — so mobile's `UsageTickerWidget` (Wave 5 update) reads ONE endpoint and branches on tier (USD ticker for free/pro, credit balance for ultra). The single-endpoint approach keeps mobile from having to choose between two endpoints, which is the dumb-client rule.

## Commits

- **`7033932` — test(B-stripe-04): add failing tier-projection tests for /v1/usage/summary** (RED gate)
  - 6 tests covering tier='free'/'pro'/'ultra' projection contract
  - Free/Pro: tier field present, ultra-only keys ABSENT
  - Ultra: balance_cents + display_balance_cents (clamped >= 0) + is_negative
  - Pitfall 6 / D-16 negative-balance UX projection
  - Phase A regression gate — exact key-set assertion for free user
- **`2d92b61` — feat(B-stripe-04): tier-aware projection for /v1/usage/summary** (GREEN gate)
  - `UsageSummaryResponse` extended with 4 new fields (tier always present; balance_cents/display_balance_cents/is_negative optional)
  - LEFT JOIN credit_balances read with `COALESCE(balance,0)::BIGINT`
  - `response_model_exclude_none=True` strips ultra-only None fields from wire response
  - Defensive `tier_row is None` fallback to 'free' tier

## Files Created / Modified

### Created

- `api_server/tests/routes/test_usage_summary_tier_projection.py` — 6 TDD tests (real Postgres testcontainer; same `async_client` + `authenticated_cookie` fixtures as `test_billing_read_routes.py`)

### Modified

- `api_server/src/api_server/routes/usage.py` — extended `UsageSummaryResponse` model + extended `get_usage_summary` handler with tier/balance projection. ~74 lines added/changed; existing Phase A keys + types byte-identical.

## Verification

- **6/6** new tier-projection tests PASS (tests/routes/test_usage_summary_tier_projection.py)
- **9/9** Phase A regression tests PASS (tests/routes/test_usage_endpoints.py)
- **12/12** sibling billing read-route tests PASS (tests/routes/test_billing_read_routes.py — Plan 03 Wave 2)
- **27/27 total tests PASS** under real Postgres testcontainer (Golden Rule #1 satisfied)
- `grep -c "balance_cents" api_server/src/api_server/routes/usage.py` = 9 (>= 2 threshold)
- Free/Pro JSON response keys do NOT include `balance_cents`, `display_balance_cents`, `is_negative` — verified by `assert "balance_cents" not in body` in test_summary_for_free_tier_returns_tier_field_but_NOT_balance_cents (and same for Pro)
- Free user's full key-set is exactly `{total_usd, message_count, by_agent, tier}` — verified by `assert set(body.keys()) == {...}`

## Truth Audit (must_haves.truths from PLAN)

1. **"GET /v1/usage/summary projects tier and balance_cents fields when calling user has tier='ultra'"** — SATISFIED. `test_summary_for_ultra_tier_returns_tier_AND_balance_cents_AND_display_balance_AND_is_negative` asserts `body["tier"] == "ultra"`, `body["balance_cents"] == 1234`, `body["display_balance_cents"] == 1234`, `body["is_negative"] is False` against a real Postgres testcontainer with seeded `users.tier='ultra'` + `credit_balances` row.

2. **"Free + Pro users continue to see the existing USD-cost projection (no balance_cents leaked)"** — SATISFIED. `test_summary_for_free_tier_returns_tier_field_but_NOT_balance_cents` and `test_summary_for_pro_tier_returns_tier_field_but_NOT_balance_cents` assert `"balance_cents" not in body`, `"display_balance_cents" not in body`, `"is_negative" not in body` for both tiers. Achieved via `response_model_exclude_none=True` on the route decorator (T-B-LEAK mitigation).

3. **"Existing /v1/usage/summary contract stays byte-identical for the fields Phase A clients already consume"** — SATISFIED. `test_summary_existing_phase_a_fields_unchanged_for_free_user` asserts `set(body.keys()) == {"total_usd", "message_count", "by_agent", "tier"}` for an empty-state free user, plus all 9 Phase A regression tests in `test_usage_endpoints.py` continue passing without modification.

## Key Links Audit

- **`api_server/src/api_server/routes/usage.py` → `credit_balances` table via `LEFT JOIN credit_balances + WHERE u.id = $1 + tier branch`** — VERIFIED. Lines 197-208 of usage.py:
  ```python
  tier_row = await conn.fetchrow(
      """
      SELECT u.tier,
             COALESCE(b.balance_cents, 0)::BIGINT AS balance_cents
      FROM users u
      LEFT JOIN credit_balances b ON b.user_id = u.id
      WHERE u.id = $1
      """,
      user_id,
  )
  ```
  Pattern `credit_balances` matches PLAN's required `via:` and `pattern:` clauses byte-identical.

## Threat Model Audit

| Threat ID | Mitigation Applied? |
|-----------|--------------------|
| T-B-XT (cross-tenant InfoDisclosure on `routes/usage.py`) | YES — `WHERE u.id = $1` predicate sources user_id from `require_user(request)` (cookie-validated session), never from request body. |
| T-B-LEAK (UsageSummaryResponse leaks balance to free/pro) | YES — `response_model_exclude_none=True` strips ultra-only None fields; tests assert keys ABSENT (not just None) for free/pro. |
| T-B-NEG (negative-balance UX disclosure — accepted) | INTENTIONAL — `display_balance_cents=max(balance,0)` + `is_negative=true` is the planned UX (Pitfall 6). Test `test_summary_for_ultra_with_negative_balance_returns_negative_is_negative_true_display_zero` pins the expected projection. |

## Deviations from Plan

None. Plan executed exactly as written. The handler implementation is byte-identical to the action block: model extension, LEFT JOIN COALESCE read, conditional ultra-only field assignment, `response_model_exclude_none=True` for the wire-response stripping.

## Pre-existing Failures Outside Plan Scope (NOT introduced by Plan 04)

- `tests/routes/test_agent_lifecycle_inapp.py::test_inapp_substitutions_threaded_to_runner` — fails on the prior commit (`fc3bb8d`) too. Verified by checking out the file from `fc3bb8d` and re-running — same `assert 'ap-proxy-...' == 'sk-or-v1-...'` mismatch + Docker `containers/fakecid.../json: Not Found` error. Pre-existing; deferred per scope-boundary rule.
- `mobile/lib/features/dashboard/dashboard_providers.dart` — pre-existing dirty file flagged in PLAN's `<critical_rules>`. NOT touched.

## CLAUDE.md Compliance

- **Golden rule #1 (no mocks/stubs):** Real Postgres testcontainer used for all 6 new tests. asyncpg pool against migrated session-scoped Postgres 17 container.
- **Golden rule #2 (dumb client):** Server returns ready-to-render JSON. `tier` is the discriminator; mobile reads one endpoint and branches render. No client-side aggregation, no hardcoded tier table on mobile.
- **Golden rule #4 (root cause first):** No fix-to-pass — the `response_model_exclude_none=True` is the principled solution to the "Phase A consumers must see byte-identical keys" requirement. Pydantic's None-vs-missing distinction is the root mechanism; Optional fields + the decorator flag is the single canonical pattern.

## Self-Check: PASSED

- File `api_server/src/api_server/routes/usage.py` exists at HEAD (modified) — VERIFIED via `grep -c "balance_cents" ... = 9`.
- File `api_server/tests/routes/test_usage_summary_tier_projection.py` exists at HEAD (created) — VERIFIED via `git log --oneline -- ...`.
- Commit `7033932` exists in `git log --oneline --all` — RED gate.
- Commit `2d92b61` exists in `git log --oneline --all` — GREEN gate.

## TDD Gate Compliance

Plan was a single-task TDD plan (tdd="true"); RED + GREEN gate commits both present. No REFACTOR commit needed — implementation is minimal and clean.

- RED: `7033932 test(B-stripe-04): add failing tier-projection tests for /v1/usage/summary`
- GREEN: `2d92b61 feat(B-stripe-04): tier-aware projection for /v1/usage/summary`

## Next Plan

**B-stripe-05** (Wave 2 — POST checkout endpoints + StripeClient service plumbing).

Phase B Wave 2 of the sibling-pair (Plans 03 + 04) is now complete:
- Plan 03 → 3 GET billing routes + rate-limit billing bucket
- Plan 04 → tier-aware projection of the existing /v1/usage/summary

Wave 3 (POST `/v1/billing/checkout/{pack,subscribe}`) is unblocked.
