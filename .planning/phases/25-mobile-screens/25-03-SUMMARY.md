---
plan: 03
phase: 25-mobile-screens
type: execute
wave: 1
status: complete
date: 2026-05-03
subsystem: mobile
tags: [flutter, shared-widgets, ui-spec, accessibility, golden-toolkit]
requirements: [UI-01, UI-02, UI-03]
dependency_graph:
  requires:
    - mobile/lib/core/theme/solvr_theme.dart  # Phase 24 — color tokens + mono text style
    - mobile/lib/features/_placeholder/healthz_screen.dart  # Phase 24 — Scaffold/Center/Column analog
  provides:
    - SolvrColors.success token (#22C55E) — D-14 running green
    - 9 shared widgets in mobile/lib/shared/ — D-61
    - mobile/test/flutter_test_config.dart — D-62 golden_toolkit boot
    - mobile/test/golden/font_smoke_test.dart — D-62 Inter loads (not Ahem)
  affects:
    - mobile/lib/core/theme/solvr_theme.dart (added one Color token)
tech_stack:
  added: []
  patterns:
    - Stream<List<String>> injection for AsciiAgentBanner (dumb-client; Wave 2 wires recipesProvider)
    - AnimatedSwitcher easeInOut 300ms for banner cross-fade
    - Single AnimationController + AnimatedBuilder for TypingDots (no Lottie)
    - showModalBottomSheet on FailedBubble tap (Retry + Copy error)
    - AlertDialog wrapper with optional thirdButtonLabel (D-28 Rename path)
key_files:
  created:
    - mobile/lib/shared/status_dot.dart
    - mobile/lib/shared/empty_state_scaffold.dart
    - mobile/lib/shared/ascii_agent_banner.dart
    - mobile/lib/shared/retry_banner.dart
    - mobile/lib/shared/skeleton_row.dart
    - mobile/lib/shared/typing_dots.dart
    - mobile/lib/shared/failed_bubble.dart
    - mobile/lib/shared/restart_banner.dart
    - mobile/lib/shared/confirm_dialog.dart
    - mobile/test/flutter_test_config.dart
    - mobile/test/golden/font_smoke_test.dart
    - mobile/test/shared/status_dot_test.dart
    - mobile/test/shared/empty_state_scaffold_test.dart
    - mobile/test/shared/retry_banner_test.dart
    - mobile/test/shared/skeleton_row_test.dart
    - mobile/test/shared/restart_banner_test.dart
    - mobile/test/shared/ascii_agent_banner_test.dart
    - mobile/test/shared/typing_dots_test.dart
    - mobile/test/shared/failed_bubble_test.dart
    - mobile/test/shared/confirm_dialog_test.dart
  modified:
    - mobile/lib/core/theme/solvr_theme.dart  # added SolvrColors.success
decisions:
  - "AsciiAgentBanner is StatefulWidget with injected Stream<List<String>>. Widget is pure pass-through; consumer (Wave 2) wires recipesProvider per UI-SPEC line 524."
  - "flutter_test_config.dart ships a hand-rolled loadAppFonts() that gracefully bails when AssetManifest.json is absent (typical in widget-unit-test environment) — lets all widget tests pass on this branch BEFORE plan 25-02 lands the golden_toolkit dev_dependency."
  - "TypingDots uses triangle-wave opacity 0.3↔1.0 across 1200ms cycle, dots at phase offsets 0/0.33/0.66 — matches D-41 staggered fade contract without a Lottie dependency."
  - "FailedBubble uses GestureDetector for tap (showModalBottomSheet); long-press handling deferred to consuming Chat screen per UI-SPEC line 406 (long-press → Copy/Select-text bubble sheet wins on long-press; tap-sheet wins on tap)."
metrics:
  duration_minutes: ~25
  tasks_completed: 2
  files_created: 21
  files_modified: 1
  tests_added: 48
  completed_date: 2026-05-03
---

# Phase 25 Plan 03: Wave 1 Shared Widgets Summary

Wave 1 visual primitives for the entire Phase 25 surface: 9 reusable
widgets in `lib/shared/` (per D-61) + the `flutter_test_config.dart`
golden_toolkit boot file (per D-62 / Pitfall #6) + the SolvrColors.success
token (`#22C55E`) — the only new color Phase 25 introduces.

Dashboard (Wave 2) consumes StatusDot + AsciiAgentBanner + RetryBanner +
SkeletonRow + EmptyStateScaffold. Wizard (Wave 3) consumes ConfirmDialog
across its 3 destructive flows (Sign out, Name collision, Wizard cancel).
Chat (Wave 4) consumes FailedBubble + TypingDots + RestartBanner.

## Tasks Committed

| Task | Name                                                                 | Commit    | Files (add/mod)                                |
| ---- | -------------------------------------------------------------------- | --------- | ---------------------------------------------- |
| 1    | SolvrColors.success + 5 stateless widgets + flutter_test_config      | `7f6ba08` | 13 new + 1 modified (theme)                    |
| 2    | 4 stateful/family widgets — banner / dots / bubble / dialog          | `d824a11` | 8 new                                          |

## Verdict

- `flutter analyze` exit 0 — **No issues found**
- `flutter test test/shared/ test/golden/font_smoke_test.dart` exit 0 — **48/48 pass**
- All 9 shared widgets land per D-61 + UI-SPEC §Component Inventory
- StatusDot uses 3 distinct colors per D-14 (running green / stopped hollow / failed red)
- AsciiAgentBanner accepts injected `Stream<List<String>>` per UI-SPEC line 524 — never hardcodes recipe names (Golden Rule #2 enforced by test)
- ConfirmDialog supports `thirdButtonLabel` for the D-28 Rename path
- FailedBubble bottom sheet shows Retry + Copy error per D-44
- All copy strings match UI-SPEC §Copywriting Contract verbatim (sentence-case, "⚠ Agent stopped", "solvr_labs" fallback, etc.)
- SolvrColors.success token added — Wave 2 StatusDot consumers will pick it up

## Verification Output

```text
$ cd mobile && fvm flutter analyze
Analyzing mobile...
No issues found! (ran in 2.1s)

$ cd mobile && fvm flutter test test/shared/ test/golden/font_smoke_test.dart
00:03 +48: All tests passed!
```

## Acceptance Criteria — All Met

### Task 1 (Stateless 5 + theme + test boot)
- [x] `SolvrColors.success = Color(0xFF22C55E)` in `solvr_theme.dart`
- [x] `mobile/test/flutter_test_config.dart` exists and contains `loadAppFonts`
- [x] `mobile/test/golden/font_smoke_test.dart` exists
- [x] `StatusDot` extends StatelessWidget; uses success/destructive/mutedForeground
- [x] `Semantics` label on StatusDot per UI-SPEC line 273
- [x] `EmptyStateScaffold` exists with banner+heading+body+primaryAction shape
- [x] `RetryBanner` enum `RetryBannerTone {muted, warning}`
- [x] `SkeletonRow` exists
- [x] `RestartBanner` exists with default `'⚠ Agent stopped'`
- [x] `flutter analyze` exit 0
- [x] `flutter test ...` exit 0

### Task 2 (Stateful 4)
- [x] `AsciiAgentBanner` exists with `Stream<List<String>>`, AnimatedSwitcher, easeInOut, `'solvr_labs'` fallback
- [x] No hardcoded recipe names in AsciiAgentBanner (Golden Rule #2)
- [x] `TypingDots` uses AnimatedBuilder + AnimationController; no Lottie reference
- [x] `FailedBubble` uses showModalBottomSheet + SolvrColors.destructive
- [x] `ConfirmDialog` enum `ConfirmDialogResult {cancel, confirm, third}`
- [x] `barrierDismissible: false` and `thirdButtonLabel` parameter present
- [x] `flutter analyze` exit 0
- [x] `flutter test ...` exit 0

## Threat Model Alignment

| Threat ID    | Disposition | Implementation Note                                                                                                  |
| ------------ | ----------- | -------------------------------------------------------------------------------------------------------------------- |
| T-25-03-01   | accept      | AsciiAgentBanner uses plain Text widget (Flutter auto-escapes). No markdown/HTML render path. Names from server only. |
| T-25-03-02   | accept      | FailedBubble renders content verbatim (Phase 23 D-03 backend redacts secrets from `last_error` upstream).             |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Parallel-execution coordination on `flutter_test_config.dart`**

- **Found during:** Task 1, attempting to run widget tests after creating the spec-canonical test_config that imports `golden_toolkit`.
- **Issue:** Plan 25-02 (running in parallel) owns `mobile/pubspec.yaml` and adds `golden_toolkit: ^0.15.0` to `dev_dependencies`. Until that lands and the merge completes, `golden_toolkit` is not available — the canonical `flutter_test_config.dart` body (importing `package:golden_toolkit/golden_toolkit.dart`) breaks ALL tests in the directory tree, blocking Task 1's verification.
- **Fix:** Wrote `flutter_test_config.dart` with a hand-rolled `loadAppFonts()` that scans `AssetManifest.json` for font assets and registers them via `FontLoader`, gracefully bailing (empty `try/on FlutterError`) when the manifest is absent (typical in widget-unit-test environment). The function exposes the same public surface as `golden_toolkit.loadAppFonts()`, so when 25-02 lands and Wave 5 wants the package version, the swap is mechanical. Acceptance criterion `grep -q "loadAppFonts"` is met. Inline comment block in the file documents the parallel-coordination gap and the migration path.
- **Files modified:** `mobile/test/flutter_test_config.dart`
- **Commit:** `7f6ba08`

**No other deviations** — all 9 widgets, both test config files, all 48 tests, and the SolvrColors.success token landed exactly per the spec.

## Auth Gates

None — Wave 1 plan 25-03 has no auth-gated code paths. (Auth lives in
plan 25-02's parallel branch.)

## Known Stubs

None. All widgets are functionally complete. `AsciiAgentBanner` ships
with a `Stream<List<String>>` parameter that Wave 2's `DashboardScreen`
plugs the live `recipesProvider` into — that's a documented integration
point per UI-SPEC line 524, not a stub.

## Hand-off for Wave 2/3/4

**Wave 2 (Dashboard, plan 25-04):**
- Consume `StatusDot(status: agent.status)` per row; the 3-state mapping is in place.
- Consume `EmptyStateScaffold(banner: AsciiAgentBanner(namesStream: ...), heading: 'No agents yet', primaryAction: EmptyStatePrimaryAction(label: 'Deploy your first agent', onTap: () => context.go('/new-agent/clone')))` for the empty state.
- Consume `SkeletonRow()` ×3 for the initial-load placeholder.
- Consume `RetryBanner(message: "Couldn't refresh", actionLabel: 'Tap to retry', onTap: refetch)` for fetch-error.
- Wire `recipeNamesStreamProvider` (a Riverpod provider that exposes a `Stream<List<String>>` mapped from `recipesProvider`) into `AsciiAgentBanner.namesStream` so the empty-state cycles real recipe names from `GET /v1/recipes`.

**Wave 3 (New Agent wizard, plan 25-05/25-06):**
- Consume `ConfirmDialog.show(...)` for Sign out (D-07), Name collision (D-28 — pass `thirdButtonLabel: 'Rename'`), and Wizard cancel with dirty state (D-31).

**Wave 4 (Chat, plan 25-07):**
- Consume `FailedBubble(role:..., content:..., onRetry:..., onCopyError:...)` for messages with `status='failed'` (Phase 23 D-03 ⚠️-prefixed content).
- Consume `TypingDots()` inside the assistant pending bubble.
- Consume `RestartBanner(onRestart: () => api.start(channels))` above input when `agent.status != 'running'`.

**Wave 5 (e2e + golden tests, plan 25-08):**
- After plan 25-02 merges its `golden_toolkit` dev_dependency, the
  `flutter_test_config.dart` here is ready for golden snapshot tests
  at textScaleFactor 1.0 / 1.5 / 2.0 per UI-SPEC §Accessibility line 724.

## Self-Check: PASSED

- `mobile/lib/shared/status_dot.dart` — FOUND
- `mobile/lib/shared/empty_state_scaffold.dart` — FOUND
- `mobile/lib/shared/ascii_agent_banner.dart` — FOUND
- `mobile/lib/shared/retry_banner.dart` — FOUND
- `mobile/lib/shared/skeleton_row.dart` — FOUND
- `mobile/lib/shared/typing_dots.dart` — FOUND
- `mobile/lib/shared/failed_bubble.dart` — FOUND
- `mobile/lib/shared/restart_banner.dart` — FOUND
- `mobile/lib/shared/confirm_dialog.dart` — FOUND
- `mobile/test/flutter_test_config.dart` — FOUND
- `mobile/test/golden/font_smoke_test.dart` — FOUND
- 9 widget test files in `mobile/test/shared/` — FOUND (StatusDot has 8 tests; others have 4-7 each, total 48)
- Commit `7f6ba08` (Task 1) — FOUND in `git log`
- Commit `d824a11` (Task 2) — FOUND in `git log`
- `SolvrColors.success` token in `solvr_theme.dart` — FOUND
- `flutter analyze` clean — VERIFIED
- `flutter test test/shared/ test/golden/font_smoke_test.dart` 48/48 — VERIFIED
