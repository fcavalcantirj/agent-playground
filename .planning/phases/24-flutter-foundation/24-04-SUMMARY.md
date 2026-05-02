---
phase: 24-flutter-foundation
plan: 04
subsystem: mobile/core/api + mobile/core/auth + mobile/core/storage
tags: [flutter, dio, secure_storage, auth, http-client]
requires: [24-01, 24-03]
provides:
  - mobile/core/api/api_client.dart (typed Future<Result<T>> facade over 13 endpoints)
  - mobile/core/api/auth_interceptor.dart (Cookie injection + 401 handler)
  - mobile/core/api/log_interceptor.dart (dev redacting logger)
  - mobile/core/storage/secure_storage.dart (cached session_id wrapper)
  - mobile/core/auth/auth_event_bus.dart (broadcast Stream<AuthRequired>)
affects: []
tech-stack:
  added:
    - http_mock_adapter ^0.6.1 (dev_dependency — in-process dio transport seam for tests)
  patterns:
    - "Result<T> over try/catch — every public method returns Future<Result<T>>"
    - "Read SecureStorage cache on every dio request, hydrate-once-per-process"
    - "Stripe-shape error envelope parsing via ApiError.fromDioException"
    - "Plan-driven 80-char wrap; very_good_analysis baseline"
key-files:
  created:
    - mobile/lib/core/api/api_client.dart (294 lines)
    - mobile/lib/core/api/auth_interceptor.dart (52 lines)
    - mobile/lib/core/api/log_interceptor.dart (69 lines)
    - mobile/lib/core/storage/secure_storage.dart (41 lines)
    - mobile/lib/core/auth/auth_event_bus.dart (27 lines)
    - mobile/test/api/auth_interceptor_test.dart (236 lines)
    - mobile/test/api/api_client_test.dart (228 lines)
  modified:
    - mobile/pubspec.yaml (added http_mock_adapter ^0.6.1 dev_dependency)
    - mobile/pubspec.lock (regenerated)
decisions:
  - "Used flutter_secure_storage v10's unified AppleOptions in test fake"
  - "Switched all relative imports to package: imports per very_good_analysis"
  - "Emit AuthRequired AFTER clearSessionId() to mitigate T-24-04-03 stale-storage race"
  - "redactHeader() lifted to top-level (not a method) so unit tests can drive redaction without dio"
metrics:
  tasks_completed: 2
  tasks_planned: 2
  files_created: 7
  files_modified: 2
  tests_added: 11 + 12 (Task 1 + Task 2)
  total_tests_passing: 61
  duration_minutes: ~25
  completed_date: 2026-05-02
---

# Phase 24 Plan 04: Typed dio ApiClient + AuthInterceptor + SecureStorage + AuthEventBus + RedactingLogInterceptor Summary

One-liner: Hand-written typed dio facade over 13 backend endpoints (`Future<Result<T>>` per call, no exceptions surface), plus Cookie injection / 401 → AuthRequired plumbing and a dev-only redacting logger — APP-03 closed; Wave 4 (Plan 09 spike) can now `import 'package:agent_playground/core/api/api_client.dart'` and drive the full 9-step round-trip.

## Tasks Executed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| RED 1 | failing tests for SecureStorage + AuthInterceptor + redactHeader | 957534a | mobile/test/api/auth_interceptor_test.dart |
| GREEN 1 | SecureStorage + AuthEventBus + AuthInterceptor + RedactingLogInterceptor | 72f1f62 | mobile/lib/core/storage/secure_storage.dart, mobile/lib/core/auth/auth_event_bus.dart, mobile/lib/core/api/auth_interceptor.dart, mobile/lib/core/api/log_interceptor.dart |
| RED 2 | failing ApiClient tests + http_mock_adapter dev dep | c7919f1 | mobile/pubspec.yaml, mobile/pubspec.lock, mobile/test/api/api_client_test.dart |
| GREEN 2 | typed dio ApiClient over 13 endpoints | 5750bb9 | mobile/lib/core/api/api_client.dart |

## Test Results

```
fvm flutter analyze lib/ test/  →  No issues found!
fvm flutter test                →  +61 tests, all passing
   - test/api/auth_interceptor_test.dart       11/11
   - test/api/api_client_test.dart             12/12
   - test/api/api_error_test.dart (Plan 03)    13/13
   - test/api/result_test.dart (Plan 03)        4/4
   - test/theme/solvr_theme_test.dart (24-02)  20/20
   - test/smoke_test.dart (24-01)               1/1
```

## Plan Truths Verified

- [x] ApiClient exposes one Future<Result<T>> method per endpoint (13 methods: healthz, runs, start, stop, postMessage, messagesHistory, agentsList, recipes, models, usersMe, authGoogleMobile, authGithubMobile)
- [x] AuthInterceptor injects `Cookie: ap_session=<uuid>` on every request when sessionId present
- [x] AuthInterceptor on 401 clears stored session AND emits AuthRequired on the event bus
- [x] BYOK `Authorization: Bearer <key>` only on runs() and start() — never on other methods
- [x] Idempotency-Key header REQUIRED on postMessage — call signature enforces it (`required String idempotencyKey`)
- [x] Every method accepts an optional CancelToken (D-41)
- [x] RedactingLogInterceptor truncates Cookie + Authorization to last 8 chars in dev logs
- [x] All min_lines satisfied (api_client 294 ≥ 200, auth_interceptor 52 ≥ 30, secure_storage 41 ≥ 25, auth_event_bus 27 ≥ 15, log_interceptor 69 ≥ 30)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] flutter_secure_storage v10 API drift in test fake**
- **Found during:** Task 1 first analyze run
- **Issue:** Plan's verbatim `_FakeBackend` skeleton declared `IOSOptions? iOptions` and `MacOsOptions? mOptions` — flutter_secure_storage v10 (already pinned in mobile/pubspec.yaml at `^10.0.0`) collapsed both into a unified `AppleOptions`. Three `invalid_override` errors blocked the test compile.
- **Fix:** Renamed both parameter types to `AppleOptions?` in the fake's `read`/`write`/`delete` overrides. Production code (the real `flutter_secure_storage` plugin) is unaffected.
- **Files modified:** mobile/test/api/auth_interceptor_test.dart
- **Commit:** 72f1f62 (rolled into the GREEN commit since the fix landed before initial test pass)

**2. [Rule 2 — Lint correctness] relative imports in lib/**
- **Found during:** Task 1 analyze, Task 2 analyze
- **Issue:** very_good_analysis enforces `always_use_package_imports` for files under `lib/`. The plan's verbatim sample used relative imports (`'../auth/auth_event_bus.dart'`, `'api_endpoints.dart'`, etc.) which would have failed the analyze gate.
- **Fix:** Switched to `package:agent_playground/...` imports in `auth_interceptor.dart` and `api_client.dart`. Conformed to existing project convention (Plan 03 sources also use package imports).
- **Files modified:** mobile/lib/core/api/auth_interceptor.dart, mobile/lib/core/api/api_client.dart

**3. [Rule 1 — Lint correctness] >80 char line in log_interceptor onError**
- **Found during:** Task 1 analyze
- **Issue:** `'! ${err.response?.statusCode ?? "—"} ${err.requestOptions.path} ${err.type}'` exceeded the 80-char limit (em-dash + interpolation pushed it to 84 cols).
- **Fix:** Hoisted `final code = err.response?.statusCode ?? '-';` (ASCII dash) and used `'! $code ${err.requestOptions.path} ${err.type}'`. Same observable behavior, fits under 80.
- **Files modified:** mobile/lib/core/api/log_interceptor.dart

**4. [Rule 3 — Test ergonomics] writeSessionId test added**
- **Found during:** Task 1 RED authoring
- **Issue:** Plan only specified read+clear test cases for SecureStorage; `writeSessionId` was reachable but untested, leaving a coverage hole that Phase 25 (which writes session_id post-OAuth) would have to discover.
- **Fix:** Added a third SecureStorage test case asserting writeSessionId both updates the in-memory cache AND persists to the backend.
- **Files modified:** mobile/test/api/auth_interceptor_test.dart
- **Net test count:** Plan estimated 5+ tests for Task 1; actual 11 (3 SecureStorage + 4 AuthInterceptor + 4 redactHeader).

No architectural deviations. No checkpoint hits.

## Threat Mitigations Implemented

| Threat ID | Status | Evidence |
| --------- | ------ | -------- |
| T-24-04-01 (Info Disclosure via dev logs) | Mitigated | RedactingLogInterceptor + redactHeader top-level fn (truncated at last 8 chars); 4 redactHeader unit tests cover null/empty/short/long inputs |
| T-24-04-02 (SecureStorage cache scope) | Accepted | Cache is process-scoped; documented in source header comment; survives only until process death |
| T-24-04-03 (Stale storage on 401) | Mitigated | `clearSessionId()` awaited BEFORE `_authEvents.emit()` in AuthInterceptor.onError; verified by the "401 clears stored session AND emits" test (storage.readSessionId() returns null when bus listener fires) |
| T-24-04-04 (BYOK on wrong endpoint) | Mitigated | BYOK only parameterized on `runs()` and `start()`; no global injector exists; grep `byokOpenRouterKey` returns exactly 8 occurrences (4 per method × 2 methods) and zero hits in postMessage / stop / messagesHistory / etc. |

## Hand-off Notes for Plan 24-06 (Wave 3)

- The Riverpod provider that constructs `Dio` should attach interceptors in this order: `AuthInterceptor`, then `RedactingLogInterceptor` (so the redacting logger sees the injected Cookie post-injection but pre-network).
- Construct `SecureStorage()` and `AuthEventBus()` once at the provider's top scope and inject both into `AuthInterceptor`.
- The constructor `ApiClient(Dio dio)` accepts the configured dio; expose `apiClientProvider` for downstream screens.
- Plan 09's spike will use `ApiClient` directly (no Riverpod) per the spike harness convention.

## Self-Check: PASSED

Verified via `git log --oneline 3fd2cd4..HEAD`:
- 957534a (RED 1) — FOUND
- 72f1f62 (GREEN 1) — FOUND
- c7919f1 (RED 2) — FOUND
- 5750bb9 (GREEN 2) — FOUND

Verified via `ls`:
- mobile/lib/core/api/api_client.dart — FOUND
- mobile/lib/core/api/auth_interceptor.dart — FOUND
- mobile/lib/core/api/log_interceptor.dart — FOUND
- mobile/lib/core/storage/secure_storage.dart — FOUND
- mobile/lib/core/auth/auth_event_bus.dart — FOUND
- mobile/test/api/auth_interceptor_test.dart — FOUND
- mobile/test/api/api_client_test.dart — FOUND

Verified via final `flutter analyze lib/ test/` — `No issues found!` (0 errors, 0 warnings, 0 info).
Verified via final `flutter test` — 61/61 tests passing.

## TDD Gate Compliance

- Plan type is `execute` with `tdd="true"` per task. Both tasks followed RED → GREEN.
- Task 1: RED commit 957534a (test failed: source files absent), GREEN commit 72f1f62 (11/11 pass)
- Task 2: RED commit c7919f1 (test failed: ApiClient class absent), GREEN commit 5750bb9 (12/12 pass)
- No REFACTOR commits needed — both GREEN commits met the line-length and import-style standards on first analyze.
