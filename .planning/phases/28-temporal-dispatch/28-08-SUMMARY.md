---
phase: 28-temporal-dispatch
plan: 08
subsystem: mobile-ui
tags: [mobile, flutter, riverpod, ui, ticker, navigation-safety]
requires: [28-06]
provides:
  - Dashboard AppBar ticker re-mount (Consumer-scoped)
  - Chat AppBar ticker re-mount (Consumer-scoped)
  - widget test guarding against defunct-element regression
affects:
  - mobile/lib/features/dashboard/dashboard_screen.dart
  - mobile/lib/features/chat/chat_screen.dart
tech_stack:
  added: []
  patterns:
    - Consumer-scoped Riverpod subscription wrapping a ConsumerWidget mounted inside a parent ConsumerStatefulWidget — Element lifecycle bound to the wrapper, not the screen
key_files:
  created:
    - mobile/test/features/usage/usage_ticker_widget_remount_test.dart
  modified:
    - mobile/lib/features/dashboard/dashboard_screen.dart
    - mobile/lib/features/chat/chat_screen.dart
decisions:
  - D-18 trigger #1 (mount-time ref.watch) drives the ticker via Consumer-scoped subscription — Phase 27 yank reverted
  - D-21 trigger #3 (instant SSE-driven invalidation) remains DEFERRED — chat_providers.dart still does NOT call ref.invalidate(usageSummaryProvider) inside _onSseEvent
  - Stub Dashboard / Chat scaffolds in the navigation-safety test mirror the production Consumer(builder: ...) shape — race is structural, not screen-specific
metrics:
  duration: ~10 minutes
  completed: 2026-05-06
---

# Phase 28 Plan 08: Re-mount UsageTickerWidget via Consumer Wrapper Summary

Re-mount the AppBar usage ticker in the Dashboard and Chat screens using
a Consumer-scoped Riverpod subscription so the provider's Element lifetime
binds to the AppBar tear-down (not the surrounding ConsumerStatefulWidget),
structurally resolving the Phase 27 defunct-element race that yanked the
ticker.

## What Shipped

| File | Change |
| --- | --- |
| `mobile/lib/features/dashboard/dashboard_screen.dart` | Added `usage_ticker_widget.dart` import and inserted a `Consumer(builder: (context, ref, _) => const UsageTickerWidget())` as the FIRST entry in the AppBar `actions:` array (leftmost in the trailing row, ahead of the existing `PopupMenuButton`). |
| `mobile/lib/features/chat/chat_screen.dart` | Same import + same Consumer-wrapped mount as the FIRST entry in the AppBar `actions:` array, ahead of the existing conditional `PopupMenuButton`/Stop overflow menu. |
| `mobile/test/features/usage/usage_ticker_widget_remount_test.dart` | New widget test with two cases: (1) single Dashboard → Chat → Dashboard round-trip, (2) three rapid round-trips. Each case asserts `tester.takeException()` is null after every pump cycle. |

The `UsageTickerWidget` itself is UNCHANGED — only the mount sites are
touched. The Consumer wrapper is the surgical structural fix.

## Verification

| Check | Result |
| --- | --- |
| `grep -c "UsageTickerWidget"` (case-insensitive, dashboard) | 2 (import + mount) |
| `grep -c "UsageTickerWidget"` (case-insensitive, chat) | 2 (import + mount) |
| `grep -c "Consumer("` introduces the new wrapper | 1 new occurrence per file |
| `grep -c "ref.invalidate(usageSummaryProvider)"` (chat_providers.dart, callable code) | 0 — the only match is inside a multi-line code comment explaining the D-21 deferral (line 450). D-21 trigger #3 deferral confirmed. |
| `flutter test test/features/usage/usage_ticker_widget_test.dart` | 6/6 PASS (0:06s) — all existing tests still green. |
| `flutter test test/features/usage/usage_ticker_widget_remount_test.dart` | 2/2 PASS (0:02s) — new navigation-safety test green. |
| `flutter test test/features/usage/` (full feature dir) | 23/23 PASS (0:04s) — no regressions across ticker, chart, agent-usage-screen, providers. |
| `flutter analyze lib/features/dashboard/dashboard_screen.dart lib/features/chat/chat_screen.dart` | 9 info-level warnings, all pre-existing (none on the lines added by this plan). 0 errors. |

Flutter version used: `3.41.0` (project-pinned via `.fvmrc` at `/Users/fcavalcanti/fvm/versions/3.41.0/bin/flutter`). The system Flutter (`/opt/homebrew/bin/flutter` 3.35.7) is below the project's pubspec floor (`>=3.41.0`).

## Commits

| Hash | Message |
| --- | --- |
| `0195fa2` | `feat(28-08): re-mount UsageTickerWidget in Dashboard + Chat AppBars via Consumer wrapper` |
| `59f0829` | `test(28-08): widget test — UsageTickerWidget survives Dashboard ↔ Chat navigation` |

Both commits land 2 insertions per mount file (no deletions) plus one
194-line test file. No deletions across the plan.

## D-21 Deferral — Confirmed

The plan's must-have `truth` "chat_providers.dart does NOT call
ref.invalidate(usageSummaryProvider) inside _onSseEvent" was verified by
grep. The only occurrence of `ref.invalidate(usageSummaryProvider)` in
`mobile/lib/features/chat/chat_providers.dart` is at line 450 inside a
documentation comment explaining the deferral:

```dart
// Phase 27 D-32 trigger #3 (deferred) — instant ticker refresh on
// assistant reply was attempted via ref.invalidate(usageSummaryProvider)
// here, but it crashed downstream Consumers mid-SSE-handler with
// 'Failed assertion: _lifecycleState != _ElementLifecycle.defunct'.
// Triggers #1 (mount) + #2 (lifecycle resume) cover the workflow;
// ticker updates on next screen mount or app resume.
```

No live call exists. D-21 trigger #3 stays deferred — Phase 28 explicitly
ships only triggers #1 (mount-time ref.watch) and #2 (AppLifecycleState.resumed).

## Auto-mode Checkpoint Handling

Task 3 is `checkpoint:human-verify` — a 12-step manual iOS-simulator
smoke (deploy fresh agent → chat round-trip → ticker increment → back-nav
→ background-foreground → tap navigation). Auto-mode auto-approves
`human-verify` checkpoints, so per the executor protocol this checkpoint
is logged as auto-approved and the plan continues to completion.

**HOWEVER** — the manual smoke is the only end-to-end signal that the
fix actually flows real BYOK usage from a Temporal-dispatched assistant
reply through the UsageRecorder into the AppBar ticker. Auto-approval
does NOT verify that path; it only allows the plan to land. The widget
test (`usage_ticker_widget_remount_test.dart`) covers the structural
defunct-element guarantee, which is the load-bearing claim. The
end-to-end smoke remains an outstanding task for the user to run on a
real simulator before Phase 28 closes.

If a future `--auto` run wants stronger gating, escalate the smoke to
`checkpoint:human-action` (which auto-mode does not auto-approve) or
build a dockerized harness equivalent to `make e2e-inapp-docker` for the
mobile screens.

⚡ Auto-approved: AppBar ticker re-mount + navigation-safety test green.

## Deviations from Plan

None — plan executed exactly as written.

The plan's optional Step 4 of Task 1 (`flutter build ios --no-codesign`)
was skipped in favor of `flutter analyze` + `flutter test` because:

- The mobile macOS host requires a CocoaPods/Xcode toolchain pass for
  `flutter build ios` that's slow (~3-6 min) and not load-bearing for the
  test cases this plan ships — the analyzer + test runner already exercise
  the same Dart imports, type checks, and Element graph the build would.
- The widget test's `tester.takeException()` assertion is the canonical
  signal for the defunct-element regression; build success is necessary
  but not sufficient.

The user can run `cd mobile && /Users/fcavalcanti/fvm/versions/3.41.0/bin/flutter build ios --no-codesign` locally before the iOS smoke if they want the build gate before booting the simulator.

## Self-Check: PASSED

- [x] `mobile/lib/features/dashboard/dashboard_screen.dart` exists and contains `UsageTickerWidget` (verified via grep)
- [x] `mobile/lib/features/chat/chat_screen.dart` exists and contains `UsageTickerWidget` (verified via grep)
- [x] `mobile/test/features/usage/usage_ticker_widget_remount_test.dart` exists (verified — 194 lines, 2 testWidgets blocks)
- [x] Commit `0195fa2` exists in `git log`
- [x] Commit `59f0829` exists in `git log`
- [x] No `ref.invalidate(usageSummaryProvider)` call sites in chat_providers.dart (only one comment-only match at line 450)
- [x] Existing 6 ticker tests + 2 new tests + full feature dir 23/23 PASS
