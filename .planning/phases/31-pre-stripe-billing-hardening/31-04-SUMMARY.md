---
phase: 31-pre-stripe-billing-hardening
plan: 04
subsystem: mobile/observability+chat-error-surfacing
tags: [mobile, sentry, riverpod, chat, sse, error-classification]
requirements: [H4, H6]
mitigates: [T-31-02-mobile-half, T-31-05-residual]
dependency-graph:
  requires:
    - "Phase 31 Plan 01: sentry_flutter ^9.20.0 pinned in mobile/pubspec.yaml"
  provides:
    - "initSentry({required Future<void> Function() runner}) wrap-runner helper at mobile/lib/core/instrumentation/sentry.dart"
    - "ChatStreamErrorClass enum + classifyChatStreamError(Object) at mobile/lib/features/chat/chat_stream_error_classifier.dart"
    - "StateProvider<ChatStreamErrorState?> chatStreamErrorProvider at mobile/lib/features/chat/chat_stream_error_banner_provider.dart"
    - "ChatScope.retryStreamConnect() — retry-CTA dispatch surface for Plan 05 widget tests"
    - "Inline RetryBanner sibling-block (Key('chat-stream-error-banner')) consuming chatStreamErrorProvider in chat_screen.dart"
    - "mobile/Makefile ios + android targets propagating SENTRY_DSN_MOBILE / SENTRY_RELEASE / SENTRY_ENVIRONMENT --dart-defines"
  affects:
    - "Plan 05 (Wave 2): widget + classifier-unit + Sentry transport-mock tests authored against the surfaces created here"
tech-stack:
  added: []
  patterns:
    - "wrap-runner pattern via SentryFlutter.init's appRunner argument (zone-bound error capture)"
    - "Riverpod StateProvider<T?> single-active banner — direct sibling of telegram_failed_banner_provider (Phase 25 D-50)"
    - "Pure top-level classifier function (no Riverpod, no I/O) — testable in isolation"
    - "Reuse of shared RetryBanner widget per AMD-01 — no parallel banner widget file"
key-files:
  created:
    - "mobile/lib/core/instrumentation/sentry.dart"
    - "mobile/lib/features/chat/chat_stream_error_classifier.dart"
    - "mobile/lib/features/chat/chat_stream_error_banner_provider.dart"
  modified:
    - "mobile/lib/main.dart (wrap main() body in await initSentry(runner: () async { ... }))"
    - "mobile/lib/features/chat/chat_providers.dart (line :387 silent-swallow → classifier; _onResumed catch → classifier; new retryStreamConnect)"
    - "mobile/lib/features/chat/chat_screen.dart (streamErr ref.watch + sibling RetryBanner block + _streamErrorCopy + _handleStreamErrorRetry helpers)"
    - "mobile/Makefile (ios + android targets gain three SENTRY_* dart-define lines)"
decisions:
  - "Renamed the `// ignore: discarded_futures` lint suppression at the SSE-connect site to `// ignore: unawaited_futures` — the analyzer's pre-existing message confirmed `discarded_futures` was not produced at that location and `unawaited_futures` was the correct rule for the catchError fire-and-forget chain."
  - "Added `retryStreamConnect()` method on ChatScope so the chat_screen RetryBanner onTap could call a real reconnect path (writing through the same classifier on failure per D-09) rather than just clearing the banner state. Plan explicitly authorized this when the codebase did not expose a Riverpod-friendly stream-connect handle."
  - "Auth-class CTA dispatch via context.go('/login') matches the project's go_router /login route (verified via existing /login navigation patterns in the codebase)."
metrics:
  duration: "~25 minutes"
  completed: "2026-05-08T15:19:34Z"
  tasks_completed: 2
  files_created: 3
  files_modified: 4
  commits:
    - "ab6ebae: feat(31-04): H6 mobile — initSentry helper + main.dart wrap-runner + Makefile dart-defines"
    - "a529e05: feat(31-04): H4 — chat-stream error classifier + banner state + inline RetryBanner"
---

# Phase 31 Plan 04: Mobile Sentry init + chat-stream error classifier + RetryBanner Summary

Combined H4 (mobile silently swallowing SSE-connect failures → user sees nothing) and H6 mobile (zero `sentry_flutter` references → webhook 500s/debit failures invisible to ops) into one Wave-1 plan because both surfaces share the chat-feature dir + main.dart + Makefile and no other plan touches them.

## What Was Built

### Task 1 — H6 mobile (commit `ab6ebae`)

Created `mobile/lib/core/instrumentation/sentry.dart` exporting:

```dart
Future<void> initSentry({required Future<void> Function() runner}) async
```

Behavior:
- Reads `SENTRY_DSN_MOBILE`, `SENTRY_ENVIRONMENT` (default `'dev'`), `SENTRY_RELEASE` from `String.fromEnvironment`
- DSN empty → `debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)')` + `await runner()` and return (D-14, SPEC AC15)
- DSN non-empty → `SentryFlutter.init(...)` with:
  - `tracesSampleRate = 0.0` (errors-only per SPEC AC15)
  - `appRunner: runner` (wrap-runner pattern for zone-bound error capture)
  - `beforeSend` filter: drops `DioException` with `response.statusCode != null && < 500` to protect Free-tier quota (D-12 mobile equivalent / T-31-02 mitigation)

`mobile/lib/main.dart`: existing `main()` body wrapped inside `await initSentry(runner: () async { ... })`. Logic preserved verbatim — only the wrap is new.

`mobile/Makefile`: appended three `--dart-define SENTRY_DSN_MOBILE=$(SENTRY_DSN_MOBILE)` / `SENTRY_RELEASE=$(GIT_SHA)` / `SENTRY_ENVIRONMENT=$(SENTRY_ENVIRONMENT)` lines to BOTH `ios:` and `android:` targets (D-15).

### Task 2 — H4 chat-stream error surfacing (commit `a529e05`)

Created `mobile/lib/features/chat/chat_stream_error_classifier.dart` — pure top-level enum + dispatch fn:

```dart
enum ChatStreamErrorClass { networkTransient, authExpired, serverError }
ChatStreamErrorClass classifyChatStreamError(Object e)
```

AMD-02 mapping (locked):
- `SocketException` | `TimeoutException` → `networkTransient`
- `DioException` of type `connectionError | connectionTimeout | sendTimeout | receiveTimeout` → `networkTransient`
- `DioException` `response.statusCode == 401` → `authExpired`
- `DioException` `response.statusCode >= 500` → `serverError` (AMD-02 reconciles SPEC AC11)
- `DioException` non-401 4xx (e.g. 403, 404, 422) → `serverError`
- Unknown `Object` → `networkTransient` (D-07 fallback)

Created `mobile/lib/features/chat/chat_stream_error_banner_provider.dart` — `StateProvider<ChatStreamErrorState?>` mirroring `telegram_failed_banner_provider.dart` shape (D-05). State holds `agentInstanceId`, `errorClass`, `lastFailedAction` (`'connect'` | `'reconnect_on_resume'`).

`mobile/lib/features/chat/chat_providers.dart`:
- Imports added for both new files
- Line `:387` silent-swallow `_stream.connect().catchError((_) {})` replaced with `catchError((Object e) { ref.read(...).state = ChatStreamErrorState(..., errorClass: classifyChatStreamError(e), lastFailedAction: 'connect') })`
- `_onResumed` rewritten with D-09 replace-not-stack contract: success → `state = null`; failure → new `ChatStreamErrorState(..., lastFailedAction: 'reconnect_on_resume')`
- New `retryStreamConnect()` method — disconnect + reconnect + classifier-driven banner update on failure; serves as the test seam for Plan 05 widget tests AND the chat_screen retry-CTA dispatch site

`mobile/lib/features/chat/chat_screen.dart`:
- Imports added for both new files
- `final streamErr = ref.watch(chatStreamErrorProvider);` next to existing `tgBanner` watch
- Inline `RetryBanner(key: const Key('chat-stream-error-banner'), ...)` block as sibling of telegram banner (AMD-01 — reuses shared RetryBanner; no new banner widget file)
- `_streamErrorCopy(ChatStreamErrorClass)` helper returns the SPEC-locked copy strings AC5/AC6/AC7
- `_handleStreamErrorRetry(BuildContext, ChatStreamErrorState)` — auth-class navigates to `/login`; other classes call `retryStreamConnect()`
- `actionLabel` is `'Sign in'` for auth-class, `'Retry'` for the others (D-08)

## Empirical Verification (`must_haves.truths`)

All 11 truths from the plan frontmatter were grep-verified against the committed source. Selected highlights:

- `mobile main() runs inside SentryFlutter.init's appRunner zone when SENTRY_DSN_MOBILE is set` — `appRunner: runner` present in `sentry.dart`; `main.dart` body wrapped in `initSentry(runner: ...)`
- `mobile main() runs without Sentry init when SENTRY_DSN_MOBILE is empty` — `if (dsn.isEmpty)` branch in `sentry.dart` calls `debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)')` then `await runner()` (SPEC AC15)
- AMD-02 classifier mapping verified (5 conditional branches present in classifier source)
- `Both _stream.connect() at chat_providers.dart:387 AND _onResumed catch route through the SAME classifyChatStreamError` — 3 hits of `classifyChatStreamError` in chat_providers.dart (initial connect, _onResumed, retryStreamConnect)
- `On _onResumed success the banner state is REPLACED with null; on failure REPLACED with new classification (D-09 — NOT stacked)` — `state = null` on success; `state = ChatStreamErrorState(...)` on failure (no append/stack)
- `chat_screen.dart renders an inline RetryBanner sibling-block` — `Key('chat-stream-error-banner')` present, sibling to `Key('telegram-failed-banner')` in same Column
- Three SPEC copy strings byte-exact: `'Connection lost — tap to retry'` / `'Session expired — sign in again'` / `'Server error — try again later'`
- Auth-class banner button label is `'Sign in'`; other classes use `'Retry'` — verified via grep
- Mobile Makefile ios + android targets propagate three SENTRY_* dart-defines — `grep -c` returns 2 for each of `SENTRY_DSN_MOBILE=`, `SENTRY_RELEASE=`, `SENTRY_ENVIRONMENT=`

## flutter analyze

`fvm flutter analyze lib/core/instrumentation/sentry.dart lib/main.dart` — **0 issues**.

`fvm flutter analyze lib/features/chat/` — 15 info-level issues, ALL pre-existing in baseline (17 issues before my edits). My edits NET removed 2 lints (`unnecessary_ignore: discarded_futures` and `unawaited_futures` at the prior line 387) and introduced ZERO new lints. Per CLAUDE.md SCOPE BOUNDARY rule, pre-existing info-level lints in unrelated files are out of scope.

## flutter test

- `test/main_boot_test.dart` (4 tests) + `test/smoke_test.dart` (1 test) — all PASS (regression check on main.dart wrap)
- `test/features/chat/dedup_test.dart`, `optimistic_send_test.dart`, `resume_reconnect_test.dart`, `retry_test.dart` — 12/12 PASS (regression check on chat_providers edits)
- `test/features/chat/chat_screen_test.dart` has 6 pre-existing failures (timer-leak `!timersPending` assertion errors) — verified by running on baseline pre-my-edits; same 6 failures predate this plan. Out of scope per SCOPE BOUNDARY rule.

Plan 05 (Wave 2) will author the new classifier-unit + widget + Sentry transport-mock tests against the surfaces created here.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Lint-suppression label corrected at SSE-connect site**
- **Found during:** Task 2, after `flutter analyze` flagged `unnecessary_ignore: discarded_futures` on the freshly-replaced line
- **Issue:** The plan's `<action>` body specified `// ignore: discarded_futures` for the catchError chain, but the analyzer reported `discarded_futures` was not actually produced at that location while `unawaited_futures` WAS firing
- **Fix:** Renamed the ignore label to `// ignore: unawaited_futures` — the lint that the analyzer actually emits for `_stream.connect().catchError(...)` outside an `async` body
- **Files modified:** `mobile/lib/features/chat/chat_providers.dart`
- **Commit:** `a529e05`

**2. [Rule 2 - Missing functionality] Added `retryStreamConnect()` test-seam method on ChatScope**
- **Found during:** Task 2, while writing `_handleStreamErrorRetry` in chat_screen.dart
- **Issue:** chat_screen's retry-CTA needed a real reconnect path (not just `state = null`). Plan explicitly authorized this addition: "If the codebase does not yet expose a stream-connect method, executor adds a thin helper to chat_providers in this same task"
- **Fix:** Added `Future<void> retryStreamConnect()` to ChatScope — disconnect + reconnect + classifier-driven banner update on failure (D-09 contract honored). chat_screen `_handleStreamErrorRetry` now calls it
- **Files modified:** `mobile/lib/features/chat/chat_providers.dart`, `mobile/lib/features/chat/chat_screen.dart`
- **Commit:** `a529e05`

**3. [Rule 3 - Blocking] Cascade refactor in initSentry to clear `cascade_invocations` lints**
- **Found during:** Task 1, after `flutter analyze` flagged two `cascade_invocations` info-level lints inside the `SentryFlutter.init` callback
- **Issue:** Sequential `options.X = …` assignments triggered `cascade_invocations` lint
- **Fix:** Restructured to `options ..dsn = … ..environment = … ..tracesSampleRate = … ..beforeSend = …;` cascade form. The conditional `if (release.isNotEmpty) options.release = release;` stays as a separate statement (since cascade with `if` would change semantics)
- **Files modified:** `mobile/lib/core/instrumentation/sentry.dart`
- **Commit:** `ab6ebae`

**4. [Rule 3 - Blocking] Use package import in chat_stream_error_banner_provider.dart**
- **Found during:** Task 2, after `flutter analyze` flagged `always_use_package_imports` on the relative import of the classifier
- **Issue:** Plan-supplied source used `import 'chat_stream_error_classifier.dart';` (relative) which `very_good_analysis` rejects
- **Fix:** Changed to `import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';`
- **Files modified:** `mobile/lib/features/chat/chat_stream_error_banner_provider.dart`
- **Commit:** `a529e05`

### Authentication Gates

None encountered.

## Known Stubs

None. All four new/modified surfaces wire real data:
- `initSentry` is invoked by main.dart and either runs the runner directly (DSN empty) or initializes the SDK
- The classifier is called by chat_providers at three sites (initial connect, _onResumed, retryStreamConnect)
- The banner provider is read by chat_screen and written by chat_providers
- The RetryBanner action calls `retryStreamConnect()` (real disconnect+connect) for non-auth classes and `context.go('/login')` for auth class

## Threat Flags

None. The plan's `<threat_model>` lists T-31-02 mitigation (DioException<500 beforeSend filter) and T-31-05 residual (mobile `set_user` deferred to a future plan). No new security-relevant surface introduced beyond what the plan already covers.

## Self-Check: PASSED

- File `mobile/lib/core/instrumentation/sentry.dart` — FOUND
- File `mobile/lib/features/chat/chat_stream_error_classifier.dart` — FOUND
- File `mobile/lib/features/chat/chat_stream_error_banner_provider.dart` — FOUND
- File `mobile/lib/main.dart` (modified) — FOUND
- File `mobile/lib/features/chat/chat_providers.dart` (modified) — FOUND
- File `mobile/lib/features/chat/chat_screen.dart` (modified) — FOUND
- File `mobile/Makefile` (modified) — FOUND
- Commit `ab6ebae` — FOUND
- Commit `a529e05` — FOUND
- All 11 `must_haves.truths` empirically grep-verified
- `flutter analyze` clean on Task 1 files; net-improved on Task 2 files (pre-existing-only remaining)
- Existing chat unit tests all pass (12/12); pre-existing chat_screen widget-test failures are out of scope
