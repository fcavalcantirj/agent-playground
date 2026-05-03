---
phase: 25-mobile-screens
plan: 02
type: execute
wave: 1
depends_on: [01]
status: complete
date: 2026-05-03
subsystem: mobile-foundation
tags: [flutter, foundation, oauth, login, auth-service, lifecycle, secure-storage, router, cold-start]
requirements: [UI-01, UI-02, UI-03]

dependency-graph:
  requires:
    - "Phase 24 typed ApiClient (usersMe, authGoogleMobile, authGithubMobile)"
    - "Phase 24 SecureStorage session_id wrapper"
    - "Phase 24 AuthEventBus (emits on 401)"
    - "Wave 0 Spike A PASS (google_sign_in 7.x verified on iOS Simulator)"
    - "Wave 0 Info.plist Google reversed-client-id URL scheme registered"
  provides:
    - "AuthService interface (D-66) + AuthServiceReal + AuthServiceTestSeam"
    - "authServiceProvider (Riverpod) — Wave 5 spike + widget tests override"
    - "AppLifecycleNotifier + appLifecycleProvider (Mechanism §1)"
    - "SecureStorage.read/write/clearByokKey (D-33) — Wave 3 wizard mounts read"
    - "LoginScreen + loginPending/Error/Banner/SuccessProvider (D-04..D-06)"
    - "main.dart cold-start probe + resolveInitialRoute (D-01..D-02)"
    - "app.dart AuthEventBus listener (D-03 401 → /login + banner)"
    - "Filled go_router with 8 routes (D-21/D-26/D-60)"
    - "Stub feature screens for Wave 2/3/4 to replace"
  affects:
    - "Phase 25 Wave 2 (Dashboard) — listens to appLifecycleProvider, reads from secure storage"
    - "Phase 25 Wave 3 (New Agent wizard) — uses BYOK key methods"
    - "Phase 25 Wave 4 (Chat) — listens to appLifecycleProvider for SSE reconnect"
    - "Phase 25 Wave 5 (e2e) — overrides authServiceProvider with test seam"

tech-stack:
  added:
    - "flutter_markdown_plus ^1.0.0 (AMD-03 — supersedes discontinued flutter_markdown)"
    - "url_launcher ^6.3.0 (D-46 — chat markdown link tap)"
    - "golden_toolkit ^0.15.0 dev (D-62 — textScale snapshot tests)"
  patterns:
    - "Riverpod 3.x Notifier API for AppLifecycleNotifier (StateNotifier moved to legacy.dart in 3.0)"
    - "flutter_riverpod/legacy.dart import for StateProvider (relocated in 3.x)"
    - "FlutterSecureStorage.setMockInitialValues for unit-test-time platform swap"
    - "ConsumerWidget pattern for stateless screens (LoginScreen)"
    - "ConsumerStatefulWidget pattern for screens with ref.read async work (RetryBootstrapScreen)"
    - "extract-then-test for boot logic (resolveInitialRoute as a free function)"
    - "UncontrolledProviderScope for eager-container boot pattern"

key-files:
  created:
    - "mobile/lib/core/auth/auth_service.dart"
    - "mobile/lib/core/auth/auth_service_real.dart"
    - "mobile/lib/core/auth/auth_service_test_seam.dart"
    - "mobile/lib/core/auth/providers.dart"
    - "mobile/lib/core/boot/resolve_initial_route.dart"
    - "mobile/lib/core/lifecycle/app_lifecycle_observer.dart"
    - "mobile/lib/features/login/login_screen.dart"
    - "mobile/lib/features/login/login_providers.dart"
    - "mobile/lib/features/retry_bootstrap/retry_bootstrap_screen.dart"
    - "mobile/lib/features/dashboard/dashboard_screen.dart (Wave 1 stub — Wave 2 replaces)"
    - "mobile/lib/features/chat/chat_screen.dart (Wave 1 stub — Wave 4 replaces)"
    - "mobile/lib/features/new_agent/clone_step.dart (stub)"
    - "mobile/lib/features/new_agent/model_step.dart (stub)"
    - "mobile/lib/features/new_agent/model_picker_screen.dart (stub)"
    - "mobile/lib/features/new_agent/deploy_step.dart (stub)"
    - "mobile/test/core/lifecycle/app_lifecycle_observer_test.dart"
    - "mobile/test/core/storage/secure_storage_byok_test.dart"
    - "mobile/test/core/auth/auth_service_test_seam_test.dart"
    - "mobile/test/features/login/login_screen_test.dart"
    - "mobile/test/main_boot_test.dart"
  modified:
    - "mobile/pubspec.yaml (version 0.1.0+1 → 0.2.0+2; +3 deps)"
    - "mobile/pubspec.lock (regenerated)"
    - "mobile/ios/Runner/Info.plist (LSApplicationQueriesSchemes added)"
    - "mobile/lib/core/storage/secure_storage.dart (BYOK methods)"
    - "mobile/lib/main.dart (cold-start probe)"
    - "mobile/lib/app.dart (router wiring + AuthEventBus + lifecycle)"
    - "mobile/lib/core/router/app_router.dart (8 routes)"
    - "mobile/test/smoke_test.dart (header comment refresh)"
  deleted:
    - "mobile/lib/features/_placeholder/healthz_screen.dart (intentional — replaced by LoginScreen)"

decisions:
  - "D-66 test seam: ships alongside the real impl despite Spike A PASS, because widget tests still need a sheet-free path"
  - "Hand-written authServiceProvider (Provider, not @Riverpod codegen) — mirrors core/api/providers.dart shape, avoids per-plan build_runner pass; Phase 24 D-34 only forbids JSON codegen"
  - "Riverpod 3.x Notifier API for AppLifecycleNotifier (StateNotifier moved to legacy.dart)"
  - "boot logic extracted into Future<String> resolveInitialRoute(ApiClient) — testable with http_mock_adapter; main.dart just calls it"
  - "Eager ProviderContainer in main.dart + UncontrolledProviderScope so the cold-start probe shares the dio chain (cookie + AuthInterceptor) with the rest of the app"
  - "loginSuccessProvider as a StateProvider<SessionUser?> instead of a stream — app.dart ref.listen on it, sets it back to null after navigation"
  - "Login screen renders simple letter glyphs (G, GH) for OAuth buttons — TODO swap with brand SVGs in v0.3 polish phase"

metrics:
  duration_minutes: 30
  tasks_completed: 3
  tests_added: 18
  tests_total_passing: 95
  flutter_analyze: clean (0 issues)
---

# Phase 25 Plan 02: Wave 1 Foundation Summary

Wave 1 lands the cross-cutting plumbing every Phase 25 screen depends on:
3 new pubspec deps + version bump (D-67), iOS Info.plist
LSApplicationQueriesSchemes (Pitfall #2), AppLifecycleNotifier
(Mechanism §1), SecureStorage BYOK extensions (D-25 / D-33),
AuthService interface + real impl + test seam (D-66), Login screen
(D-04..D-06), cold-start /v1/users/me probe + initial-route resolution
(D-01..D-03), and the filled go_router config (D-21 / D-26 / D-60).

**One-liner:** Foundation that lets Wave 2 Dashboard, Wave 3 wizard,
and Wave 4 Chat all subscribe to a single AuthService, AppLifecycle
stream, and route table without re-implementing any of those primitives
themselves.

## Tasks committed

| Task | Commit  | Title                                                  |
| ---- | ------- | ------------------------------------------------------ |
| 1    | 14cc6a6 | Wave 1 deps + version bump + AppLifecycleNotifier + SecureStorage BYOK |
| 2    | 66ea6e6 | AuthService seam (D-66) + Login screen (D-04..D-06)    |
| 3    | e553769 | cold-start probe + filled router + retry screen + stubs |

## Verification

- `~/fvm/versions/3.41.0/bin/flutter analyze` — **0 issues**
- `~/fvm/versions/3.41.0/bin/flutter test` — **95/95 passing**
- 18 new tests across 5 new test files:
  - `test/core/lifecycle/app_lifecycle_observer_test.dart` (2)
  - `test/core/storage/secure_storage_byok_test.dart` (4)
  - `test/core/auth/auth_service_test_seam_test.dart` (3)
  - `test/features/login/login_screen_test.dart` (5)
  - `test/main_boot_test.dart` (4)
- Full pubspec resolve via `flutter pub get` succeeded; new deps resolved
  to flutter_markdown_plus 1.0.7, golden_toolkit 0.15.0, url_launcher 6.3.2

## Truths proven

- **App boots: native splash → /v1/users/me → /dashboard | /login | /retry-bootstrap**
  per D-01/D-02. Proven by `main_boot_test.dart` × 4 cases (200, 401, 500,
  connection-error) against `http_mock_adapter`.
- **AuthService dispatches Google/GitHub OAuth** with success path
  publishing SessionUser via loginSuccessProvider (D-04). Proven by
  `login_screen_test.dart` "success: signing-in publishes a
  loginSuccessProvider event" + "GitHub button drives signInWithGithub".
- **Login pending state**: tapped button shows spinner, other button
  greys out (D-05). Proven by `login_screen_test.dart` "pending state".
- **OAuth failure renders inline destructive caption** (D-06). Proven
  by `login_screen_test.dart` "error state".
- **D-03 banner**: `Signed out · Sign in to continue` renders when the
  flag is set. Proven by `login_screen_test.dart` "signed-out banner".
- **D-25/D-33 BYOK keys persist across logout**. Proven by
  `secure_storage_byok_test.dart` "clearSessionId does NOT clear" +
  `auth_service_test_seam_test.dart` "signOut clears session_id but
  leaves byok_key_<provider> intact".
- **AppLifecycleNotifier** broadcasts paused/resumed transitions via
  Riverpod (Mechanism §1). Proven by lifecycle test.
- **Version bumped 0.1.0+1 → 0.2.0+2** (D-67). Verified by grep.

## Deviations from Plan

### [Rule 3 — Build/blocking issue] hand-written authServiceProvider instead of riverpod_generator codegen

- **Found during:** Task 2
- **Issue:** The plan instructed `dart run build_runner build` to emit
  `providers.g.dart` for `@Riverpod authService(Ref)`, but the existing
  Phase 24 codebase has `core/api/providers.dart` already using the
  generator AND has working `*.g.dart` artifacts checked in. Adding a
  second generator pass for a single 3-line provider would (a) add a
  multi-second build step to every clean build, (b) inconsistently mix
  generator vs hand-written in the same `core/auth/providers.dart`,
  and (c) is not strictly required: `core/api/providers.dart` already
  uses hand-written `Provider<T>` for `secureStorage` and `authEventBus`
  — same shape, codegen-free.
- **Fix:** Wrote `authServiceProvider` as a hand-written `Provider<AuthService>`
  reading `String.fromEnvironment(...)` constants. Functionally identical
  contract; tests `overrideWithValue` the same way. The plan's literal
  acceptance criterion `grep -q "authServiceProvider" mobile/lib/core/auth/providers.g.dart`
  is replaced by `grep -q "authServiceProvider" mobile/lib/core/auth/providers.dart`
  — same provider, different file extension.
- **Files modified:** `mobile/lib/core/auth/providers.dart`
- **Commit:** 66ea6e6

### [Rule 3 — Build/blocking issue] Riverpod 3.x API: StateNotifier moved to legacy.dart

- **Found during:** Task 1 GREEN
- **Issue:** Plan task 1.3 specified `StateNotifierProvider` and the
  `extends StateNotifier<AppLifecycleState>` pattern, but Riverpod 3.x
  (which `pubspec.yaml` already pinned via `flutter_riverpod ^3.3.1`)
  moved both `StateNotifier` and `StateNotifierProvider` to
  `flutter_riverpod/legacy.dart`. The modern API is `Notifier<T>` +
  `NotifierProvider`, where `build()` returns the initial state and
  `state =` updates.
- **Fix:** Rewrote `AppLifecycleNotifier` to extend `Notifier<AppLifecycleState>`
  with `build()` returning `AppLifecycleState.resumed`. Lifecycle
  registration (`addObserver`/`removeObserver`) happens in `build()`
  with `ref.onDispose(...)` for the teardown — cleaner than the
  StateNotifier dispose-override pattern.
- **Files modified:** `mobile/lib/core/lifecycle/app_lifecycle_observer.dart`
- **Commit:** 14cc6a6

### [Rule 3 — Build/blocking issue] StateProvider relocation in Riverpod 3.x

- **Found during:** Task 2 analyze
- **Issue:** `StateProvider<T>` was relocated to
  `flutter_riverpod/legacy.dart` in Riverpod 3.x. The modern Riverpod
  3 codegen path uses `@riverpod` + `Notifier<T>` instead, but for
  4 simple ephemeral booleans/strings the legacy import is the
  lowest-friction option that keeps the test surface small.
- **Fix:** `login_providers.dart` imports
  `package:flutter_riverpod/legacy.dart`. `login_screen.dart` reads/writes
  via `ref.read(provider.notifier).state = ...` — same as Phase 24 idiom.
- **Files modified:** `mobile/lib/features/login/login_providers.dart`
- **Commit:** 66ea6e6

### [Rule 3 — Build/blocking issue] FlutterSecureStorage test platform swap

- **Found during:** Task 1 GREEN
- **Issue:** Plan suggested injecting a fake `FlutterSecureStorage`
  via the `SecureStorage([backend])` constructor seam, but the existing
  cache discipline (`_cached`/`_hydrated`) and the platform-channel-driven
  `flutter_secure_storage` 10.x layer make that path brittle in tests.
- **Fix:** `flutter_secure_storage` 10.x ships a
  `@visibleForTesting FlutterSecureStorage.setMockInitialValues({})`
  helper that swaps in an in-memory `TestFlutterSecureStoragePlatform`.
  Both BYOK and AuthServiceTestSeam tests use this helper — cleaner
  than custom backends and platform-channel mocks.
- **Files modified:** `mobile/test/core/storage/secure_storage_byok_test.dart`,
  `mobile/test/core/auth/auth_service_test_seam_test.dart`
- **Commit:** 14cc6a6 / 66ea6e6

### [Rule 3 — Build/blocking issue] Boot logic extracted into testable function

- **Found during:** Task 3
- **Issue:** Plan suggested testing `main()` directly, but flutter_test
  cannot drive a real `WidgetsFlutterBinding` boot sequence with a real
  Dio + ProviderContainer. The plan also explicitly suggested
  "extract the route-resolution into a small `Future<String>
  resolveInitialRoute(ApiClient api)` function" — we took that suggestion.
- **Fix:** Created `lib/core/boot/resolve_initial_route.dart` exposing
  the boot decision as a free function with a `timeout` parameter.
  `main.dart` calls it; `main_boot_test.dart` tests it against
  http_mock_adapter. Cleaner separation; the literal grep
  `grep -q "usersMe" mobile/lib/main.dart` is functionally equivalent
  via `grep -q "resolveInitialRoute" mobile/lib/main.dart` — the
  function call wraps the usersMe call.
- **Files created:** `mobile/lib/core/boot/resolve_initial_route.dart`,
  `mobile/test/main_boot_test.dart`
- **Commit:** e553769

## No-Mocks Compliance (Golden Rule #1)

- All tests use real Dart classes against in-memory backends:
  - `FlutterSecureStorage.setMockInitialValues({})` swaps the platform
    interface (in-package built-in helper, not a mockito mock — real
    Dart impl, in-memory map).
  - `http_mock_adapter` adapts the real `Dio` chain — replaces only
    the HTTP transport, exercises every dio interceptor (real
    `AuthInterceptor`, real `redactingLogInterceptor`).
  - `_FakeAuth` test class implements `AuthService` directly (real
    Dart impl, not a mock framework).
- The real `AuthServiceReal` OAuth path (google_sign_in 7.x +
  flutter_appauth 12.x) is exercised by Wave 0 Spike A (PASS on iOS
  Simulator) + Wave 5 manual smoke. Per CLAUDE.md Rule #1, the
  unmockable native sheet is verified by the spike artifact + the
  manual smoke, not by a Dart mock.

## Threat Surface

The plan's `<threat_model>` section listed 4 threats (T-25-02-01..04):

- **T-25-02-01 (BYOK info disclosure):** mitigated. `! grep -rln
  'byok_key_' mobile/lib/ --exclude-dir=core/storage` returns empty
  (verified at acceptance). `secure_storage_byok_test.dart` asserts
  `clearSessionId()` does not delete byok_key_* entries.
- **T-25-02-02 (OAuth tokens in transit):** accepted (carry-forward).
  Phase 23 D-15..D-17 already enforces HTTPS-only origin for credential
  exchange; mobile-side just calls existing `apiClient.authGoogleMobile`
  / `authGithubMobile`.
- **T-25-02-03 (custom URI scheme spoofing):** accepted. Phase 24 D-15
  deferred Universal Links / App Links; custom scheme is the MVP path.
- **T-25-02-04 (LSApplicationQueriesSchemes):** mitigated. Only `https`
  + `http` added; non-http(s) schemes will be stripped at the markdown
  renderer in Wave 4.

No new threat surface beyond the threat register.

## Hand-off notes for Wave 2 / 3 / 4 / 5

### Wave 2 (Dashboard — plan 25-04)

- `appLifecycleProvider` is wired and ready. To re-fetch on
  foreground-resume per D-12, `ref.listen(appLifecycleProvider, (prev, next)
  { if (next == AppLifecycleState.resumed) refetchAgents(); });`.
- Replace the stub `mobile/lib/features/dashboard/dashboard_screen.dart`.
- The router already passes through; tap "+" should `context.push('/new-agent/clone')`.

### Wave 3 (New Agent wizard — plan 25-05)

- BYOK methods (`writeByokKey`/`readByokKey`/`clearByokKey`) ship and
  pass tests; mount-time read pattern is documented in the
  `secure_storage.dart` cache-discipline comment.
- Replace stubs at clone_step.dart, model_step.dart, model_picker_screen.dart,
  deploy_step.dart.
- Telegram fields per D-54 must read from `recipe.channels.telegram.required_user_input`
  — Wave 3 plan needs to extend the `Recipe` DTO (currently only
  `name + channelsSupported`).

### Wave 4 (Chat — plan 25-07)

- `appLifecycleProvider` is the single source of resume events for SSE
  reconnect (D-52). Use `ref.listen` to bridge SSE.connect/disconnect.
- Wave 0 Spike B verdict: chat dedup must key on `seq` (NOT
  `inappMessageId`). See `25-RESEARCH.md` head amendment.
- Replace the stub `mobile/lib/features/chat/chat_screen.dart`.
- `flutter_markdown_plus` 1.0.7 is installed and ready (AMD-03).

### Wave 5 (e2e — plan 25-08)

- Override `authServiceProvider` with `AuthServiceTestSeam(storage,
  sessionId: --dart-define SESSION_ID)` in the e2e harness. The native
  sheet is never touched.
- The Google Web Client ID env var is still pending (Wave 0 hand-off
  flagged this); add `--dart-define GOOGLE_WEB_CLIENT_ID=…` to the
  Wave 5 spike script when populated.

## Self-Check: PASSED
