---
phase: 24-flutter-foundation
plan: 06
subsystem: mobile-foundation
tags: [flutter, riverpod, riverpod_generator, go_router, dio, dart_define, app_env, healthz, portrait_lock, system_ui_overlay]

# Dependency graph
requires:
  - phase: 24-01
    provides: mobile/ scaffold + minimum main.dart/app.dart + smoke test
  - phase: 24-02
    provides: solvrTheme() ThemeData factory + SolvrTextStyles.mono
  - phase: 24-03
    provides: sealed Result<T> + ApiError + ErrorCode + DTOs (HealthOk) + ApiEndpoints
  - phase: 24-04
    provides: ApiClient + AuthInterceptor + SecureStorage + AuthEventBus + RedactingLogInterceptor
provides:
  - AppEnv.fromEnvironment() + fromValue() — fail-loud BASE_URL boot validation (D-43)
  - mobile/build.yaml — riverpod_generator opt-in (D-34 carve-out: codegen for providers, NOT JSON)
  - Riverpod provider tree — appEnv → secureStorage → authEventBus → dio → apiClient
  - go_router config — single placeholder route '/' → HealthzScreen
  - HealthzScreen — calls ref.read(apiClientProvider).healthz() + renders Ok/Err via SolvrTextStyles.mono
  - Final main.dart boot sequence — AppEnv validation + portrait lock + SystemUiOverlayStyle.dark + ProviderScope
  - app.dart — MaterialApp.router(theme: solvrTheme(), routerConfig: GoRouter)
  - features/{dashboard,new_agent,chat}/.gitkeep + shared/.gitkeep — D-26 folder layout placeholders
affects: [24-08, 24-09, 25, mobile-launch]

# Tech tracking
tech-stack:
  added:
    - "@riverpod annotation + riverpod_generator code generation (D-34 carve-out)"
    - "go_router configuration (existing dep wired for the first time)"
  patterns:
    - "Boot-time fail-loud env validation — AppEnv.fromEnvironment crashes on empty/malformed BASE_URL before any dio call"
    - "Riverpod codegen provider tree with keepAlive + ref.onDispose for resource cleanup"
    - "Defense-in-depth portrait lock — SystemChrome.setPreferredOrientations alongside Plan 07 native config"
    - "Test seam pattern — fromValue(String) split out of fromEnvironment() so unit tests cover validation paths without compile-time const games"

key-files:
  created:
    - mobile/lib/core/env/app_env.dart
    - mobile/lib/core/api/providers.dart
    - mobile/lib/core/api/providers.g.dart
    - mobile/lib/core/router/app_router.dart
    - mobile/lib/features/_placeholder/healthz_screen.dart
    - mobile/lib/features/dashboard/.gitkeep
    - mobile/lib/features/new_agent/.gitkeep
    - mobile/lib/features/chat/.gitkeep
    - mobile/lib/shared/.gitkeep
    - mobile/build.yaml
    - mobile/test/env/app_env_test.dart
  modified:
    - mobile/lib/main.dart
    - mobile/lib/app.dart
    - mobile/test/smoke_test.dart
  cross_wave_shims:
    - mobile/lib/core/api/api_client.dart
    - mobile/lib/core/api/auth_interceptor.dart
    - mobile/lib/core/api/log_interceptor.dart
    - mobile/lib/core/auth/auth_event_bus.dart
    - mobile/lib/core/storage/secure_storage.dart

key-decisions:
  - "Cross-wave shims for Plan 24-04 outputs — minimal placeholder implementations created in this worktree so providers.dart compiles, HealthzScreen boots, and tests pass. Replaced at wave-merge when Plan 24-04 lands its real impl."
  - "Smoke test rewritten to override dioProvider — HealthzScreen.initState fires a real /healthz call, which would hang pumpAndSettle or leave a 10s timer pending; injecting a Dio with a rejecting HttpClientAdapter keeps the widget tree timer-free without violating Golden Rule #1 (the production /healthz path is exercised against real infra by Plan 24-09 spike)."
  - "Lint-clean as a hard gate — all very_good_analysis info-level lints (always_use_package_imports, directives_ordering, prefer_constructors_over_static_methods, document_ignores, unintended_html_in_doc_comment) cleaned to make `flutter analyze` exit 0."

patterns-established:
  - "Boot-time fail-loud — main.dart calls AppEnv.fromEnvironment() before any other init; misconfigured BASE_URL throws StateError instead of surfacing as 502 on first request."
  - "Riverpod codegen carve-out from D-34 — `riverpod_generator` runs via build_runner but is INDEPENDENT from `json_serializable`; providers.g.dart is committed, JSON DTOs remain hand-rolled."
  - "Defense-in-depth orientation lock — main.dart calls SystemChrome.setPreferredOrientations programmatically as backup for Plan 07's Info.plist + AndroidManifest config (some Android OEM skins ignore the manifest hint)."
  - "Test seam for compile-time-const env — split fromEnvironment() (which uses `const String.fromEnvironment`) and fromValue(String) (test-driven) so unit tests can drive validation paths."

requirements-completed: [APP-04, APP-01]

# Metrics
duration: 12min
completed: 2026-05-02
---

# Phase 24 Plan 06: AppEnv + Riverpod Providers + go_router + HealthzScreen + Boot Wiring Summary

**Final boot sequence wiring — `flutter run --dart-define BASE_URL=...` validates env, locks portrait, sets dark status-bar icons, and routes through MaterialApp.router → HealthzScreen which renders /healthz Ok/Err via the real theme.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-02T21:48:27Z
- **Completed:** 2026-05-02T22:00:30Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN; Task 2: full boot wiring)
- **Files created:** 16 (incl. 5 cross-wave shims + 1 generated providers.g.dart)
- **Files modified:** 3 (main.dart, app.dart, smoke_test.dart)

## Accomplishments

- **Fail-loud boot validation lands** — `AppEnv.fromEnvironment` reads `--dart-define BASE_URL=...` (default `http://localhost:8000`), validates non-empty + http(s) scheme + non-empty host, and throws StateError on every other input. 6/6 unit tests cover the matrix.
- **Riverpod provider tree assembled** — `appEnv → secureStorage → authEventBus → dio → apiClient`, all keepAlive, all with `ref.onDispose` cleanup; codegen via `@Riverpod` annotation + `riverpod_generator` (D-34 carve-out — independent runner from json_serializable).
- **go_router wired with single placeholder route** — `/ → HealthzScreen` consumes `apiClientProvider`, calls `/healthz`, and renders `OK` / `NOT OK` / `ERROR: <code> — <message>` via `SolvrTextStyles.mono` against the real `solvrTheme()` ThemeData.
- **Final boot sequence shipped** — `main.dart` ensures binding init → AppEnv validation → portrait lock (`SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp])`) → `SystemUiOverlayStyle.dark` → `runApp(ProviderScope(child: SolvrLabsApp()))`.
- **D-26 feature folder layout planted** — `lib/features/{dashboard, new_agent, chat}` + `lib/shared/` carry `.gitkeep` so the folder tree commits ahead of Phase 25 work.
- **Lint gate green** — `flutter analyze` exits 0 with no warnings/info; all 44 unit tests pass.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED — failing AppEnv tests** — `34ffa93` (test)
2. **Task 1 GREEN — AppEnv.fromEnvironment + fromValue** — `4e97f8d` (feat)
3. **Task 2 — providers tree + router + HealthzScreen + main/app boot wiring** — `cf76fbc` (feat)

## Files Created/Modified

### Created
- `mobile/lib/core/env/app_env.dart` — boot-time BASE_URL validation; `fromEnvironment` reads `--dart-define`, `fromValue(String)` is the test seam
- `mobile/lib/core/api/providers.dart` — `@Riverpod(keepAlive: true)` declarations for appEnv, secureStorage, authEventBus, dio, apiClient
- `mobile/lib/core/api/providers.g.dart` — riverpod_generator output (committed; D-34 carve-out)
- `mobile/lib/core/router/app_router.dart` — `buildRouter()` returning a GoRouter with the single placeholder route
- `mobile/lib/features/_placeholder/healthz_screen.dart` — the only Phase 24 screen; calls `api.healthz()` and switches over `Result<HealthOk>`
- `mobile/build.yaml` — opt-in for `riverpod_generator` only (no json_serializable)
- `mobile/test/env/app_env_test.dart` — 6 unit tests (3 happy paths, 3 fail-loud paths)
- `mobile/lib/features/{dashboard,new_agent,chat}/.gitkeep`, `mobile/lib/shared/.gitkeep` — D-26 folder layout

### Modified
- `mobile/lib/main.dart` — full boot sequence (was Plan 24-01 minimum stub)
- `mobile/lib/app.dart` — `MaterialApp.router(theme: solvrTheme(), routerConfig: ...)` (was Plan 24-01 placeholder Scaffold)
- `mobile/test/smoke_test.dart` — overrides `dioProvider` so HealthzScreen.initState's /healthz call doesn't leak a 10s timer

### Cross-Wave Shims (will be replaced at wave-merge by Plan 24-04 outputs)
- `mobile/lib/core/api/api_client.dart` — minimal `ApiClient.healthz()` only; Plan 24-04 will own the full /v1/* surface
- `mobile/lib/core/api/auth_interceptor.dart` — Cookie injection on request + 401-clear-and-emit on error (matches Plan 24-04's RED test contract)
- `mobile/lib/core/api/log_interceptor.dart` — `redactHeader()` truncate-to-last-8 (matches D-52) + pass-through `RedactingLogInterceptor`
- `mobile/lib/core/auth/auth_event_bus.dart` — broadcast Stream<AuthRequired> + dispose
- `mobile/lib/core/storage/secure_storage.dart` — read/write/clear with in-memory cache; matches Plan 24-04's RED test contract

## Decisions Made

- **Cross-wave shim strategy** — the executor prompt explicitly anticipated Plan 24-04 running in a parallel worktree and instructed to "ship a placeholder provider that the Plan 24-06 file structure expects". Implemented as five small files matching the contract Plan 24-04's already-committed RED tests (commit `957534a`) declared. Each file is headered with a `CROSS-WAVE SHIM` notice. When Plan 24-04 lands its feat commit, the wave-merge will conflict on these files — the merging orchestrator should keep Plan 24-04's version (which is the file's primary owner).
- **Smoke test override pattern** — keeping `pumpAndSettle()` in the smoke test required preventing the in-flight /healthz call from leaving a pending timer. Chose a custom `HttpClientAdapter` that throws `DioException(connectionError)` immediately, injected via `dioProvider.overrideWith(...)`. This is NOT a violation of Golden Rule #1 — the production /healthz path runs against real infra in Plan 24-09's spike; the smoke test is purely "did the widget tree mount".
- **Lint-clean is a hard gate** — chose to fix all 29 info-level lints (mostly `always_use_package_imports` from the relative imports the plan's verbatim code blocks used) rather than relax the analysis configuration. The verify gate said "must exit 0".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Smoke test pumpAndSettle hangs on real /healthz call**
- **Found during:** Task 2 verification (`flutter test`)
- **Issue:** Plan 24-01's smoke test used `pumpAndSettle()`. After Plan 24-06 wired `HealthzScreen` (which fires `api.healthz()` on initState through a real Dio with 10s timeout), pumpAndSettle either timed out or — when shortened to single `pump()` — left a pending Timer that crashed the test framework's invariant check.
- **Fix:** Wrapped the smoke widget in a `ProviderScope` with `dioProvider.overrideWith(...)` injecting a Dio whose `httpClientAdapter` throws `DioException(connectionError)` immediately. The /healthz call returns synchronously, no timer leaks.
- **Files modified:** `mobile/test/smoke_test.dart`
- **Verification:** `flutter test` 44/44 green; smoke test runs in 2 sec.
- **Committed in:** `cf76fbc`

**2. [Rule 2 — Critical] CROSS-WAVE SHIM files for Plan 24-04 outputs**
- **Found during:** Task 2 (cannot satisfy Plan 24-06's must_haves without Plan 24-04's exports)
- **Issue:** Plan 24-06 must_haves require `apiClientProvider`, `SecureStorage`, `AuthEventBus`, `AuthInterceptor`, `RedactingLogInterceptor` to exist; their owner Plan 24-04 is running in a parallel worktree and only RED tests have been committed (no `lib/` files yet on main). The executor prompt anticipates this and says "ship a placeholder provider that the Plan 24-06 file structure expects".
- **Fix:** Created 5 minimal-but-functional placeholder files; each header explicitly marks it as a `CROSS-WAVE SHIM` and points to Plan 24-04 as the owner. Contracts (constructor signatures, method names, event types) match Plan 24-04's already-committed RED test specs (commit `957534a`) to minimize merge friction.
- **Files modified:** `mobile/lib/core/api/api_client.dart`, `mobile/lib/core/api/auth_interceptor.dart`, `mobile/lib/core/api/log_interceptor.dart`, `mobile/lib/core/auth/auth_event_bus.dart`, `mobile/lib/core/storage/secure_storage.dart`
- **Verification:** `flutter analyze` exits 0; 44/44 tests pass.
- **Committed in:** `cf76fbc`
- **Note for wave-merge:** When Plan 24-04 lands its feat commit, these files will conflict. The merging orchestrator should keep Plan 24-04's version (its file ownership). Cross-checked by reading the RED test contracts at `git show 957534a:mobile/test/api/auth_interceptor_test.dart` so the shim API surface aligns.

**3. [Rule 1 — Bug] flutter analyze info-level lints failed exit-code gate**
- **Found during:** Task 2 verification
- **Issue:** Plan's verbatim code blocks used relative imports (`'../auth/auth_event_bus.dart'`, `'core/router/app_router.dart'`), which `very_good_analysis` flags as `always_use_package_imports` (info-level but treated as failure by the project's lint config). 29 issues reported; `flutter analyze` exited 1.
- **Fix:** Converted all internal imports to `package:agent_playground/...` style; sorted directives alphabetically; added doc-comment ignore comments where needed (`prefer_constructors_over_static_methods` on `AppEnv.fromValue`); rewrapped one long line in `log_interceptor.dart`; replaced angle brackets in dartdoc with backticks to silence `unintended_html_in_doc_comment`.
- **Files modified:** `mobile/lib/app.dart`, `mobile/lib/main.dart`, `mobile/lib/core/api/providers.dart`, `mobile/lib/core/api/api_client.dart`, `mobile/lib/core/api/auth_interceptor.dart`, `mobile/lib/core/api/log_interceptor.dart`, `mobile/lib/core/router/app_router.dart`, `mobile/lib/features/_placeholder/healthz_screen.dart`, `mobile/lib/core/env/app_env.dart`
- **Verification:** `flutter analyze --no-pub` → "No issues found! (ran in 2.1s)" — exit 0.
- **Committed in:** `cf76fbc`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 critical add, 1 lint-gate fix)
**Impact on plan:** All deviations were necessary for the plan's own verify gates to pass. No scope creep: cross-wave shims are owned by Plan 24-04 and clearly marked for replacement; smoke-test override is testing-only; lint fixes are purely stylistic. Plan 24-06's intended functionality landed exactly as specified.

## Issues Encountered

- **Riverpod codegen flag deprecated** — `--delete-conflicting-outputs` triggered a "These options have been removed and were ignored" warning from build_runner; the build still succeeded. Not a blocker for Phase 24 but worth noting for future codegen runs (use plain `dart run build_runner build`).

## User Setup Required

None. The `flutter run --dart-define BASE_URL=...` workflow is fully self-service per D-44; no in-app pickers, no env switchers, no debug menus. Per-target switching happens at the `flutter run` invocation, not at runtime.

## Next Phase Readiness

- **Plan 24-09 (spike) unblocked-pending-merge** — once Plan 24-04 lands real `ApiClient` + `MessagesStream` and the wave-merge happens, the spike can run `flutter test integration_test/spike_api_roundtrip_test.dart` against the live api_server via the same providers wired here.
- **Plan 24-08 (env config docs)** — README + `.env.example` should document the four BASE_URL targets (Simulator, emulator, LAN, ngrok) that `AppEnv` accepts.
- **Phase 25 ready** — feature folders (`features/dashboard`, `features/new_agent`, `features/chat`) exist with .gitkeep so Phase 25 can `cd mobile/lib/features/dashboard && touch dashboard_screen.dart` and start filling in.
- **Wave-merge note** — Plan 24-04's feat commit (still pending in `worktree-agent-a5cecac1`) will conflict with the 5 shim files in this plan. Resolution: take Plan 24-04's version. Both worktrees branched from the same wave-2 merge HEAD (`3fd2cd4`), so the merge graph is clean.

## Self-Check: PASSED

Verified via `[ -f path ] && echo FOUND` and `git log --all --oneline | grep -q <hash>`:

| Item | Status |
|---|---|
| `mobile/lib/core/env/app_env.dart` | FOUND |
| `mobile/lib/core/api/providers.dart` | FOUND |
| `mobile/lib/core/api/providers.g.dart` | FOUND |
| `mobile/lib/core/router/app_router.dart` | FOUND |
| `mobile/lib/features/_placeholder/healthz_screen.dart` | FOUND |
| `mobile/lib/features/dashboard/.gitkeep` | FOUND |
| `mobile/lib/features/new_agent/.gitkeep` | FOUND |
| `mobile/lib/features/chat/.gitkeep` | FOUND |
| `mobile/lib/shared/.gitkeep` | FOUND |
| `mobile/build.yaml` | FOUND |
| `mobile/test/env/app_env_test.dart` | FOUND |
| Commit `34ffa93` (test RED) | FOUND |
| Commit `4e97f8d` (feat GREEN) | FOUND |
| Commit `cf76fbc` (feat Task 2) | FOUND |
| `flutter analyze` exit 0 | PASS |
| `flutter test` — 44/44 green | PASS |
| D-44 grep gate (no DebugMenu/EnvSwitcher/EnvBanner/showDebug/debug_overlay in lib/) | PASS |

---
*Phase: 24-flutter-foundation*
*Plan: 06*
*Completed: 2026-05-02*
