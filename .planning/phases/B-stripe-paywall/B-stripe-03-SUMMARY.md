---
phase: B-stripe
plan: 03
subsystem: billing-paywall
tags: [wave-2, billing, routes, rate-limit, error-codes, fastapi, asyncpg]
requires:
  - phase: B-stripe-02
    provides: "migration 014 (users.tier + credit_balances + credit_transactions + stripe_webhook_events) + services/billing_packs.PACKS + services/ledger atomic helpers + StripeClient lifespan service"
provides:
  - "GET /v1/billing/packs — D-06 single SOT for the 5-pack catalog (PackEntry omits stripe_price_id per T-B-PRC)"
  - "GET /v1/billing/balance — D-21 tier + raw + display + is_negative projection (Pitfall 6 / D-16)"
  - "GET /v1/billing/transactions — paginated ledger history (limit ∈ [1,200], cursor before=<created_at>)"
  - "_LIMITS['billing'] = (30, 60) — billing-bucket rate limit; webhook path explicitly excluded"
  - "4 new ErrorCode constants — INSUFFICIENT_BALANCE / TIER_LIMIT_EXCEEDED / INVALID_PACK_ID / STRIPE_WEBHOOK_INVALID"
affects: [B-stripe-04, B-stripe-05, B-stripe-06, B-stripe-07, B-stripe-08, B-stripe-09, B-stripe-10, B-stripe-11, B-stripe-12, B-stripe-13]
tech-stack:
  added: []
  patterns:
    - "Inline _err helper + require_user early-return — mirrors routes/usage.py byte-identical"
    - "Pydantic response_model with intentional field omission for security (PackEntry omits internal stripe_price_id)"
    - "Bucket constant pair for path-prefix predicate with exclusion (_BILLING_PATH_PREFIX + _BILLING_WEBHOOK_PATH) — re-usable shape for any future include-prefix-but-exclude-one-path bucket"
    - "(created_at DESC, id DESC) compound order key with strict-less cursor (created_at < $2) — stable pagination across same-second inserts"
key-files:
  created:
    - api_server/src/api_server/routes/billing.py
    - api_server/tests/routes/test_billing_read_routes.py
    - api_server/tests/middleware/test_rate_limit_billing.py
  modified:
    - api_server/src/api_server/main.py
    - api_server/src/api_server/middleware/rate_limit.py
    - api_server/src/api_server/models/errors.py
key-decisions:
  - "Plan asked for 'limit clamps at max'; FastAPI's Query(le=200) returns 422 on out-of-range values rather than silently clamping. Test asserts the 422 — validation is the right shape (silent clamp would let mobile drift unnoticed)."
  - "Plan's draft used 404 for the 'user not found' path in /v1/billing/balance; downgraded to 401 because the only way that branch fires is a session pointing at a CASCADE-deleted user — the session itself is invalid, so 401 is the correct shape (caller should re-auth, not 'user not found')."
  - "(limit, window_seconds) bucket name kept lowercase 'billing' to match existing lowercase convention in _LIMITS (runs / lint / get / chat / auth)."
  - "Path predicate ordering: billing branch BEFORE the generic GET branch — without this, the 300/60 GET ceiling would clobber the tighter 30/60 billing ceiling."
patterns-established:
  - "Pattern: include-prefix-but-exclude-one-path for rate-limit buckets — re-usable when Wave 3 (webhook) and Wave 2 (POST checkout) want different ceilings under the same /v1/billing/* prefix"
requirements-completed:
  - D-06
  - D-21
  - BIL-05
  - BIL-06
duration: ~10min
completed: 2026-05-09
---

# Phase B Plan B-stripe-03: Billing Read Routes + Rate Limit Bucket Summary

**3 read endpoints + the billing rate-limit bucket — mobile (Wave 5) and web (Phase B.2) now have a real surface to bind the pack picker, the balance ticker, and the transaction history to.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-09T01:40:00Z
- **Completed:** 2026-05-09T01:50:00Z
- **Tasks:** 2 (Task 1 + Task 2, both TDD)
- **Files created:** 3
- **Files modified:** 3
- **Tests added:** 19 (12 route + 7 middleware)

## Accomplishments

- `routes/billing.py` ships 3 GET endpoints, each `require_user`-gated. `PackEntry` intentionally omits the internal `stripe_price_id` field (T-B-PRC mitigation — Stripe Price ids stay server-side; mobile invokes Wave 2's POST /checkout/pack with the pack id). `BalanceResponse` projects D-16 / Pitfall 6 — `display_balance_cents = max(raw, 0)` while `is_negative` flags the underlying ledger truth so the UI can render "$0 ⚠" until admin write-off. `TransactionsResponse` paginates by `(created_at DESC, id DESC)` with strict `created_at < $2` cursor — same-second inserts can't drift the page boundary.
- `middleware/rate_limit.py` extends with the `billing` bucket (30 calls / 60s per user). The path predicate routes `/v1/billing/packs|balance|transactions` to the bucket while explicitly excluding `/v1/billing/webhook` — Stripe is the sole caller there and rate-limiting Stripe escalates its retry storm. Wave 3 owns the webhook handler; abuse-prevention there is HMAC + `stripe_event_id` UNIQUE.
- `models/errors.py` adds 4 error codes Phase B's later waves will emit: INSUFFICIENT_BALANCE (402 from the pre-flight gate / post-debit drain), TIER_LIMIT_EXCEEDED (403 from agent.create cap), INVALID_PACK_ID (400 from Checkout init), STRIPE_WEBHOOK_INVALID (400 from signature verify failure). The `_CODE_TO_TYPE` map gets matching entries — `payment_required` and `forbidden` are new envelope `type` values introduced for the billing surface.
- All 19 plan tests pass against a real Postgres testcontainer; full pre-existing rate-limit suite (`test_rate_limit.py` + `test_chat_rate_limit.py`) stays green — 26/26 in the combined run.

## Task Commits

Each task was committed atomically:

1. **Task 1: routes/billing.py + ErrorCode additions + main.py wire-up** — `57518da` (feat)
2. **Task 2: rate-limit billing bucket + webhook exclusion** — `cadfd24` (feat)

## Files Created/Modified

- `api_server/src/api_server/routes/billing.py` (new) — 3 GET endpoints, Pydantic response models, `_err` helper, full module docstring covering the cross-tenant defense + Pitfall 6 projection.
- `api_server/tests/routes/test_billing_read_routes.py` (new) — 12 integration tests covering the 12 behaviors enumerated in the plan's `<behavior>` block.
- `api_server/tests/middleware/test_rate_limit_billing.py` (new) — 7 tests: 4 unit `_bucket_for` predicate tests + 3 integration tests (30-then-429, webhook unaffected, cross-bucket isolation).
- `api_server/src/api_server/main.py` — added `from .routes import billing as billing_route` import; included `billing_route.router` after the usage router.
- `api_server/src/api_server/middleware/rate_limit.py` — added `_BILLING_PATH_PREFIX` / `_BILLING_WEBHOOK_PATH` constants + `_LIMITS["billing"]` entry + the path-predicate branch (placed BEFORE the generic GET branch so the tighter 30/60 ceiling wins).
- `api_server/src/api_server/models/errors.py` — added 4 ErrorCode constants + 4 matching `_CODE_TO_TYPE` entries.

## Decisions Made

- **Limit param `?limit=999` returns 422, not silent clamp.** Plan's draft `<behavior>` said "limit param clamps at max"; FastAPI's `Query(le=200)` is the right enforcement vehicle — it rejects out-of-range values with 422 rather than silently clamping. Silent clamp would let a mobile-side bug (forgetting to honor the API contract) drift unnoticed; 422 is loud and actionable. Test `test_transactions_pagination_limit_param_clamps_at_max` asserts the 422 with this rationale embedded in its docstring.
- **'user not found' branch returns 401, not 404.** Plan draft said `_err(404, ErrorCode.UNAUTHORIZED, ...)`. The only way that branch fires is a session pointing at a CASCADE-deleted user — the session itself is no longer valid, so 401 is the correct shape (caller should re-auth, not 'user not found'). Returning 404 with code=UNAUTHORIZED would mismatch the envelope's `type` ('not_found' from the `_CODE_TO_TYPE` map vs the actual issue 'unauthorized') and confuse mobile error handlers.
- **Bucket precedence — billing BEFORE the generic GET branch.** Without this ordering, the 300/60 GET ceiling clobbers the tighter 30/60 billing ceiling. Mirrors the existing auth-bucket precedence (which also lives BEFORE the generic GET branch for the same reason — auth callbacks are GETs that need the tighter 5/60 cap).
- **Test added beyond the plan: cross-bucket isolation.** `test_billing_bucket_does_not_affect_runs_bucket` mirrors the existing `test_chat_rate_limit_does_not_affect_runs` shape — cheap regression guard against a future `_LIMITS` refactor that accidentally collapses two buckets into one. 7 tests total vs the plan's 6.

## Deviations from Plan

### Auto-fixed Issues

None. Both tasks shipped cleanly on first GREEN.

### Refinements (documented above)

- Limit-clamp test asserts 422 instead of silent clamp.
- 'User not found' projects 401 instead of 404.
- One extra rate-limit test (`test_billing_bucket_does_not_affect_runs_bucket`) added for cross-bucket isolation.

These are not "deviations" in the Rules-1-3 sense — they're refinements within the plan's intent that surfaced during implementation. The plan's `must_haves.truths` and `must_haves.key_links` contracts are preserved verbatim; the refinements harden the implementation.

## Issues Encountered

None. Both task tests went RED → GREEN on the first attempt.

## User Setup Required

None. This wave only adds local-substrate code; no env, no DB churn (migration 014 already on the alembic head from B-stripe-02).

## Next Phase Readiness

- **Wave 3 (B-stripe-04 webhook handler) unblocked.** The 4 ErrorCodes Wave 3 will emit are now defined; the rate-limit middleware's webhook exclusion is in place.
- **Wave 2 sibling (B-stripe-04 POST checkout routes) unblocked.** Will share the same `routes/billing.py` file? No — per the plan's `files_modified` list, Wave 3's webhook handler lives in `routes/billing_webhook.py` and Wave 2's POST checkout routes live in their own file. Wave 2 sibling will append to `routes/billing.py` for the POST endpoints (additive — no overlap with the 3 GETs landed here).
- **Wave 5 (mobile UI) unblocked.** Mobile can now build its pack picker against `/v1/billing/packs`, balance ticker against `/v1/billing/balance`, and transaction history against `/v1/billing/transactions`. The 3 endpoints return ready-to-render JSON per golden rule #2 — no client-side aggregation needed.

## Truth Audit (must_haves.truths from PLAN.md)

- [x] GET /v1/billing/packs returns the 5 packs with correct pack ids and price metadata, auth-gated — `test_packs_authenticated_returns_5_packs_in_order` + `test_packs_unauthenticated_returns_401`.
- [x] GET /v1/billing/balance returns {tier, balance_cents, display_balance_cents, is_negative} for the calling user — `test_balance_no_balance_row_returns_zero_for_free_tier` + `test_balance_returns_user_tier_value` + `test_balance_with_negative_balance_returns_is_negative_true_and_display_zero`.
- [x] GET /v1/billing/transactions returns the user's ledger rows ordered by created_at DESC, paginated by ?limit=N&before=<created_at> — `test_transactions_returns_user_rows_ordered_desc` + `test_transactions_pagination_before_filter_works`.
- [x] All 3 routes are require_user-gated (no anonymous browsing) and return Stripe-shape error envelopes — 3 unauthenticated tests confirm the 401 + envelope shape.
- [x] Rate-limit middleware applies the new 'billing' bucket (30 calls / 60s per user) to /v1/billing/{packs,balance,transactions} — `test_billing_packs_path_routes_to_billing_bucket` + 2 sibling unit tests + `test_billing_bucket_30_in_60s_then_429`.
- [x] Rate-limit middleware does NOT apply the 'billing' bucket to /v1/billing/webhook — `test_billing_webhook_path_does_NOT_route_to_billing_bucket` + `test_billing_webhook_path_unaffected_by_billing_bucket`.

## Artifact Audit (must_haves.artifacts)

- [x] `api_server/src/api_server/routes/billing.py` exists with FastAPI router exporting `router`. `grep -c '@router.get("/billing/' = 3`.
- [x] `api_server/src/api_server/middleware/rate_limit.py` has `_LIMITS["billing"]` entry. `grep -c 'billing' = 8` (≥2 required).

## Key Link Audit (must_haves.key_links)

- [x] `api_server/src/api_server/main.py` includes `billing_route.router` via `app.include_router(billing_route.router, prefix="/v1", tags=["billing"])`. `grep -c 'billing_route.router' = 1`.
- [x] `api_server/src/api_server/routes/billing.py` imports `from ..services.billing_packs import PACKS` and projects each Pack into a PackCatalogResponse. Imported and used in `list_packs`.

## Self-Check: PASSED

- [x] All 3 created files exist on disk
- [x] Both task commits exist in `git log --oneline`: `57518da`, `cadfd24`
- [x] `cd api_server && uv run pytest tests/routes/test_billing_read_routes.py tests/middleware/test_rate_limit_billing.py` — 19/19 PASS
- [x] No regression in pre-existing rate-limit suite — `test_rate_limit.py` + `test_chat_rate_limit.py` still pass alongside the new tests (26/26 combined)

---
*Phase: B-stripe-paywall*
*Plan: B-stripe-03*
*Completed: 2026-05-09*
