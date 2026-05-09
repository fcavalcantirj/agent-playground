---
phase: B-stripe
plan: 10
subsystem: billing-paywall
tags: [wave-5, mobile, billing, riverpod, dio, dtos, dumb-client, flutter]
requires:
  - phase: B-stripe-03
    provides: "GET /v1/billing/{packs,balance,transactions} server contracts (PackEntry, BalanceResponse, TransactionsResponse) + billing rate-limit bucket + 4 ErrorCode constants"
  - phase: B-stripe-05
    provides: "POST /v1/billing/{checkout,subscription} server contracts (lazy customer create + race-defense + checkout_url response shape)"
provides:
  - "billing_models.dart — Pack, Balance, Transaction, TransactionsPage hand-written fromJson DTOs (D-34)"
  - "billing_api.* — 5 typed methods on ApiClient: billingPacks, billingBalance, billingTransactions, createPackCheckoutSession, createSubscriptionCheckoutSession (Result<T> envelopes)"
  - "billing_providers.dart — PacksNotifier + BalanceNotifier (with D-32 lifecycle resume) + TransactionsNotifier (with loadMore cursor pagination)"
  - "_stubs.dart PHASE_B_STUB markers — TopUpScreen / CheckoutWebViewScreen / TransactionsScreen placeholders for Plan 11 to replace atomically"
  - "/billing/{topup,checkout,transactions} GoRoute entries"
affects: [B-stripe-11, B-stripe-12]
tech-stack:
  added: []
  patterns:
    - "Riverpod hub mirroring usage_providers.dart shape: CancelToken concurrency guard + ref.listen(appLifecycleProvider) → invalidateSelf on resume"
    - "loadMore() cursor-pagination on AsyncNotifier: read state.value, no-op when nextBefore is null, manual state = AsyncValue.data assignment with merged list"
    - "PHASE_B_STUB convention for in-flight router scaffolding: routes register today against minimal Scaffold widgets; downstream plan replaces by searching the marker"
    - "Test pattern for autoDispose providers: typed _holdX(container) listener helpers + observe-via-listen for thrown-error cases (read.future races autoDispose)"
key-files:
  created:
    - mobile/lib/features/billing/billing_models.dart
    - mobile/lib/features/billing/billing_providers.dart
    - mobile/lib/features/billing/billing_providers.g.dart
    - mobile/lib/features/billing/_stubs.dart
    - mobile/test/features/billing/billing_models_test.dart
    - mobile/test/features/billing/billing_providers_test.dart
  modified:
    - mobile/lib/core/api/api_endpoints.dart
    - mobile/lib/core/api/api_client.dart
    - mobile/lib/core/router/app_router.dart
key-decisions:
  - "Methods added directly on `class ApiClient` (not via Dart extension) — matches the existing Phase 27 pattern at lines 407-440 (`usageSummary`, `agentUsage`). Extension would have required a separate import for callers; keeping all dio methods on one class preserves the existing call shape."
  - "Stubs co-located in `_stubs.dart` (NOT inlined in app_router.dart) — keeps app_router.dart focused on routing config, makes Plan 11's atomic replace step a single-file delete plus 3 new widget files. The PHASE_B_STUB grep marker survives in 5 places (3 doc strings + 2 file comments)."
  - "Test 'surfaces ApiError on AsyncValue when server returns 401' uses observe-via-listen instead of `expectLater(read.future, throwsA(isA<ApiError>()))` — Riverpod 3.x's `.future` semantics race autoDispose for unrescued throws, producing a spurious 'StateError: disposed during loading' on `read.future` even though the AsyncValue.error correctly carries the ApiError."
  - "TransactionsNotifier.loadMore swallows errors silently (state remains prior page) — Plan 11's screen will surface the explicit error UX via direct call to `api.billingTransactions(...)` since the screen owns the toast/SnackBar shape; the provider's role is canonical state, not error UX."
patterns-established:
  - "Pattern: Riverpod 3.x autoDispose test with thrown errors — use `container.listen<AsyncValue<T>>(provider, ...)` and pump with sleep/check loop instead of awaiting `.future` (the latter races autoDispose). Re-usable for any AsyncNotifier whose build() can throw."
  - "Pattern: PHASE_X_STUB router scaffolding — single `_stubs.dart` with marker-tagged widgets co-located with the feature; downstream plan searches the marker, replaces, deletes the stub file. Keeps the green-build contract with downstream plans without prematurely owning their files."
  - "Pattern: typed _holdX helper per provider for autoDispose-mounting in tests — Riverpod 3.x's ProviderListenable type isn't exported through the test surface, so per-provider helpers (with concrete `AsyncValue<T>` type) are the cleanest workaround."
requirements-completed: []
duration: 17min
completed: 2026-05-09
---

# Phase B Plan B-stripe-10: Mobile Billing Dumb-Client Substrate Summary

**Mobile data plumbing for Phase B billing — DTOs + API client methods + Riverpod providers + router stubs land today; Plan 11 (Wave 5 mobile screens) now has a typed substrate to bind against. Pack catalog flows through `GET /v1/billing/packs` per dumb-client rule; mobile NEVER hardcodes the 5 packs.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-05-09T03:30:18Z
- **Completed:** 2026-05-09T03:47:58Z
- **Tasks:** 2 (Task 1 + Task 2, both TDD)
- **Files created:** 6
- **Files modified:** 3
- **Tests added:** 19 (11 model + 8 provider, all GREEN)

## Accomplishments

- **`billing_models.dart`** — Pack, Balance, Transaction, TransactionsPage with hand-written fromJson per D-34. Defensive defaults on missing fields (`(json['x'] as int?) ?? 0` style) — additive backend fields don't crash. Balance.fromJson handles the D-16 negative-balance case (raw `balance_cents=-250` while `display_balance_cents=0`, `is_negative=true`) so Plan 11's UI can render `$0 ⚠` while the underlying overdraft survives in the ledger truth.
- **`billing_api.*`** — 5 typed methods directly on ApiClient (matching Phase 27 pattern at lines 407-440). All return `Future<Result<T>>` and never throw. Cancel-token-aware. `billingTransactions(limit, before)` URL-encodes the cursor as ISO-8601-Z; server-side `created_at < $2` strict-less ensures stable pagination across same-second inserts. `createPackCheckoutSession({pack_id})` and `createSubscriptionCheckoutSession()` return the Stripe Checkout URL string for the InAppWebView host (Plan 11).
- **`billing_providers.dart`** — Three @riverpod AsyncNotifier classes mirroring `usage_providers.dart` discipline: CancelToken concurrency guard + `ref.listen<AppLifecycleState>(appLifecycleProvider)` → invalidateSelf on resume (BalanceNotifier carries the lifecycle hook because the AppBar ticker is what background-foreground transitions touch most). TransactionsNotifier exposes `loadMore()` for cursor-pagination — no-op when `nextBefore` is null, otherwise merges the next page into state.value via manual `state = AsyncValue.data(...)`.
- **`_stubs.dart`** — PHASE_B_STUB marker file with TopUpScreen / CheckoutWebViewScreen / TransactionsScreen placeholders. Plan 11's executor greps the marker to swap atomically. Co-located with feature so it's discoverable from billing/ directory.
- **app_router.dart** — 3 new GoRoute entries for `/billing/{topup,checkout,transactions}`. The `/billing/checkout` route reads `?url=` query param (webview-internal handshake per D-21) so the route is wired today and Plan 11 can switch to `state.extra` shape when the real CheckoutWebViewScreen lands.
- **api_endpoints.dart** — 5 new constants under `// Phase B — billing surface`. Single source of truth for the 5 endpoints; tests + ApiClient reference the same strings.
- **42/42 tests PASS** (8 new billing provider + 11 new billing model + 23 usage regression).

## Task Commits

Each task followed the TDD RED → GREEN cycle:

1. **Task 1 RED — billing DTOs failing tests** — `cb20c2e` (test)
2. **Task 1 GREEN — billing DTOs + 5 API methods** — `8b4ac6f` (feat)
3. **Task 2 RED — provider tests** — `0846e6a` (test)
4. **Task 2 GREEN — providers + router + stubs** — `20a3f99` (feat)

## Files Created/Modified

**Created:**

- `mobile/lib/features/billing/billing_models.dart` — Pack/Balance/Transaction/TransactionsPage DTOs with hand-written fromJson per D-34.
- `mobile/lib/features/billing/billing_providers.dart` — PacksNotifier/BalanceNotifier/TransactionsNotifier with CancelToken guards + lifecycle resume (BalanceNotifier).
- `mobile/lib/features/billing/billing_providers.g.dart` — riverpod_generator output.
- `mobile/lib/features/billing/_stubs.dart` — PHASE_B_STUB widgets for Plan 11 to replace.
- `mobile/test/features/billing/billing_models_test.dart` — 11 unit tests covering complete + missing-field paths for all 4 DTOs.
- `mobile/test/features/billing/billing_providers_test.dart` — 8 integration tests via ProviderContainer + http_mock_adapter, with `_holdX` helpers for autoDispose mounting.

**Modified:**

- `mobile/lib/core/api/api_endpoints.dart` — added `billingPacks`/`billingBalance`/`billingTransactions`/`billingCheckout`/`billingSubscription` constants.
- `mobile/lib/core/api/api_client.dart` — added 5 new methods returning `Future<Result<T>>` envelopes.
- `mobile/lib/core/router/app_router.dart` — 3 new GoRoute entries + import of stubs.

## Decisions Made

See `key-decisions` in frontmatter (4 logged decisions covering: extension-vs-class for ApiClient methods, stubs file location, error-test pattern, loadMore error-swallow).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Riverpod 3.x autoDispose races `read.future` for thrown errors**
- **Found during:** Task 2 (provider test infrastructure)
- **Issue:** `await container.read(packsProvider.future)` for the 401 case raised `StateError: disposed during loading state` instead of the expected `ApiError`. Investigation showed the AsyncValue did carry the ApiError on `.error`, but the `.future` getter's autoDispose interaction in Riverpod 3.x prevents the error from surfacing through that path before dispose runs.
- **Fix:** Added `_holdPacks` / `_holdBalance` / `_holdTransactions` test helpers using `container.listen<AsyncValue<T>>(provider, ..., fireImmediately: true)` to pin autoDispose mounted across the awaited gap. For the 401 test specifically, switched to observe-via-listen + pump-loop to read `next.error` directly off the AsyncValue.
- **Files modified:** `mobile/test/features/billing/billing_providers_test.dart`
- **Verification:** All 8 provider tests + 23 usage regression tests GREEN.
- **Committed in:** `20a3f99` (part of Task 2 GREEN commit)

**2. [Rule 1 - Bug] Provider names from riverpod_generator strip the `Notifier` suffix**
- **Found during:** Task 2 (initial test compile)
- **Issue:** Plan body referenced `packsNotifierProvider` / `balanceNotifierProvider` / `transactionsNotifierProvider`. The riverpod_generator output exposes `packsProvider` / `balanceProvider` / `transactionsProvider` (the `Notifier` suffix is stripped from the variable name; only the class name retains it).
- **Fix:** Renamed all 3 references in test file (replace_all). Plan body's example was illustrative; generator naming is authoritative.
- **Files modified:** `mobile/test/features/billing/billing_providers_test.dart`
- **Verification:** Compilation succeeded; all tests GREEN.
- **Committed in:** `20a3f99` (part of Task 2 GREEN commit)

## Threat Model Audit

| Threat ID | Disposition | Mitigation Verified |
|-----------|-------------|---------------------|
| T-B-LK    | mitigate    | DTOs do NOT include `stripe_price_id` (PackEntry server-side already omits it; mobile model has no such field). Verified: `grep stripe_price_id mobile/lib/features/billing/` returns 0 hits. |
| T-B-XT    | mitigate    | All billing API methods route through Dio's existing AuthInterceptor (session cookie / Bearer); no new bypass added. Server-side cross-tenant defense per Plan 03. |
| T-B-LOG   | mitigate    | DioException flows through `ApiError.fromDioException` (existing Phase 24 D-32 path); no new logging added in this plan. Phase 31 H6 Sentry redaction inherited unchanged. |

## Truth Audit

5/5 must_haves.truths from PLAN.md satisfied:

1. ✅ `billing_models.dart` exposes Pack, Balance, Transaction DTOs with hand-written fromJson per D-34 — verified `grep -c 'factory.*fromJson' billing_models.dart = 4` (Pack + Balance + Transaction + TransactionsPage).
2. ✅ `billing_api.*` adds 5 new typed methods (billingPacks + billingBalance + createPackCheckoutSession + createSubscriptionCheckoutSession + billingTransactions) — verified by grep on `Future<Result<...>>` return signatures = 5 new methods at api_client.dart lines 442-545.
3. ✅ `billing_providers.dart` Riverpod hub mirrors usage_providers.dart shape (CancelToken + appLifecycleProvider listen) — verified: `grep -c '@riverpod' billing_providers.dart = 3`; `grep -c 'CancelToken' billing_providers.dart = 6`; appLifecycleProvider listen present in BalanceNotifier.
4. ✅ app_router adds 3 new routes — verified: `grep -c '/billing/' app_router.dart = 6` (the 3 GoRoute paths each appear in path + builder ref). Three new GoRoute entries for `/billing/topup`, `/billing/checkout`, `/billing/transactions`.
5. ✅ Mobile NEVER hardcodes pack data — verified: `grep -E 'pack_5|pack_10|pack_25|pack_50|pack_100' mobile/lib/` returns ONLY a documentation comment in billing_models.dart explaining the `id` field. No hardcoded pack array, no hardcoded prices. Every render path goes through `GET /v1/billing/packs` per D-06.

## Key Links Verification

- `mobile/lib/features/billing/billing_api.*` → `GET /v1/billing/packs` via `Dio client + ApiEndpoints.billingPacks` ✅ (api_client.dart `billingPacks()` method @ line ~448 invokes `_dio.get(ApiEndpoints.billingPacks, ...)`).
- `mobile/lib/core/router/app_router.dart` → billing screens (Plan 11) via GoRoute entries ✅ (3 routes: `/billing/topup`, `/billing/checkout`, `/billing/transactions`; bodies are PHASE_B_STUB widgets pending Plan 11 swap).

## Deferred Issues (out of scope per `<deviation_rules>` SCOPE BOUNDARY)

- `lib/core/api/api_client.dart:390:11` `use_null_aware_elements` info-level lint (pre-existing — `git blame` confirms 7b59f226 from 2026-05-03 Phase 25 Wave 5). Logged but NOT fixed.
- 5 info-level lints in `billing_providers.dart` (4× `document_ignores` + 1× `avoid_redundant_argument_values`) — match the same pre-existing-style ignore-comment pattern used in `usage_providers.dart`. Re-classified as project-style consistency, not actionable.
- 103 total info-level lints from `flutter analyze` repo-wide — none in files modified by this plan; all pre-existing.

## Next Phase

**Plan 11 (Wave 5 mobile UI screens — TopUpScreen + PackPickerWidget + CheckoutWebViewScreen + InsufficientCreditsModal + TopupInflightWidget + TransactionsScreen).** Replaces the 3 PHASE_B_STUB widgets in `_stubs.dart` with real screens. Search marker: `// PHASE_B_STUB`. The TransactionsScreen consumes `transactionsProvider` + `loadMore()` from this plan. The TopUpScreen consumes `packsProvider` for the catalog. The CheckoutWebViewScreen consumes `createPackCheckoutSession` + `createSubscriptionCheckoutSession` to mint the Stripe Checkout URL.

**Plan 12 (mobile AppBar ticker tier-branching).** Wires `balanceProvider` into `dashboard_providers.dart` for the AppBar's tier-aware projection (ultra → `formatCredits(balanceCents)`, free/pro → fall back to existing BYOK USD ticker). NOT touched in this plan (per critical_rules: do not touch `dashboard_providers.dart`).

## Self-Check: PASSED

All 7 created/modified file paths verified on disk. All 4 commit hashes verified in `git log`:
- `cb20c2e` test (Task 1 RED)
- `8b4ac6f` feat (Task 1 GREEN)
- `0846e6a` test (Task 2 RED)
- `20a3f99` feat (Task 2 GREEN)

