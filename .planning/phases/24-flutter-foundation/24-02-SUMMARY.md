---
phase: 24-flutter-foundation
plan: 02
subsystem: mobile-theme
tags: [flutter, theme, app-02, solvr-labs]
requires:
  - 24-01-PLAN.md (mobile/ scaffold + pubspec deps + main.dart + app.dart)
provides:
  - "solvrTheme() ThemeData factory at mobile/lib/core/theme/solvr_theme.dart"
  - "SolvrColors locked-token palette (#FAFAF7 background / #1F1F1F foreground)"
  - "SolvrTextStyles.bodyTextTheme + SolvrTextStyles.mono"
  - "BorderRadius.zero invariant enforced via test gate"
affects:
  - 24-06-PLAN.md (will consume solvrTheme() in MaterialApp.router)
tech-stack:
  added:
    - "google_fonts: ^8.1.0 — Inter (body) + JetBrains Mono (mono)"
  patterns:
    - "Material 3 CardThemeData (replaces deprecated CardTheme)"
    - "testWidgets + pumpAndSettle to flush google_fonts late-async work"
    - "Strict very_good_analysis lint posture (0 issues)"
key-files:
  created:
    - "mobile/lib/core/theme/solvr_theme.dart (132 lines)"
    - "mobile/test/theme/solvr_theme_test.dart (94 lines)"
  modified: []
decisions:
  - "BorderRadius.zero kept explicit at flatShape declaration despite avoid_redundant_argument_values lint — APP-02 invariant should be self-documenting at call site (suppressed via documented // ignore)"
  - "Dropped useMaterial3: true — it is the default in Flutter 3.41.0 (avoid_redundant_argument_values)"
  - "All theme tests are testWidgets (not plain test) so WidgetTester binding can absorb google_fonts' fire-and-forget loadFontIfNecessary future via pumpAndSettle — avoids 'test failed after it had already completed' on no-network unit-test runs (RESEARCH §Pitfall #6)"
metrics:
  duration: "~6m"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
  tests_added: 7
  tests_passing: "7/7 in plan + 8/8 full suite"
  completed: 2026-05-02
---

# Phase 24 Plan 02: Solvr Labs Theme — Summary

`solvrTheme()` ThemeData factory ships at `mobile/lib/core/theme/solvr_theme.dart` with the locked APP-02 tokens (#FAFAF7 background / #1F1F1F foreground), `BorderRadius.zero` enforced on every shape, and `Inter` + `JetBrains Mono` wired through `google_fonts`. Seven widget tests gate the four APP-02 invariants and a real `Card` rendered through `MaterialApp(theme:)` proves the wiring end-to-end.

## What Shipped

### Implementation (`mobile/lib/core/theme/solvr_theme.dart`, 132 lines)

- **`SolvrColors`** — final `abstract` class holding the locked palette:
  - `background = #FAFAF7` (LOCKED, CONTEXT line 139)
  - `foreground = #1F1F1F` (LOCKED, CONTEXT line 139)
  - `card`, `muted`, `mutedForeground`, `border`, `destructive` as best-effort sRGB conversions of `solvr/frontend/app/globals.css:7-31` OKLCH tokens.
- **`SolvrTextStyles`** — `bodyTextTheme(TextTheme base)` returns `GoogleFonts.interTextTheme` with foreground-color override; `mono({fontSize, fontWeight})` returns a `GoogleFonts.jetBrainsMono` TextStyle for the `>_ SOLVR_LABS` mark and status text.
- **`solvrTheme()`** — builds `ThemeData.light()` with the locked colors, `useMaterial3` defaulted (true in Flutter 3.41.0), `BorderRadius.zero` on `cardTheme`, `elevatedButtonTheme`, `outlinedButtonTheme`, `inputDecorationTheme`, `appBarTheme`, plus a `dividerTheme` aligned to the border token.

### Tests (`mobile/test/theme/solvr_theme_test.dart`, 94 lines)

Seven `testWidgets` cases, all green:

1. `scaffoldBackgroundColor == #FAFAF7`
2. `colorScheme.primary == #1F1F1F` and `onPrimary == #FAFAF7`
3. `cardTheme.shape` is `BorderRadius.zero`
4. `elevatedButtonTheme.style.shape` is `BorderRadius.zero`
5. `outlinedButtonTheme.style.shape` is `BorderRadius.zero`
6. `SolvrTextStyles.mono(...)` returns a `TextStyle` whose `fontFamily` contains `JetBrainsMono`
7. A real `Card` rendered through `MaterialApp(theme: solvrTheme())` has zero-radius corners

A `_bootTheme(WidgetTester)` helper builds the theme inside a `MaterialApp` + pumps + settles, deduping the boot-the-binding-then-build-theme dance across the first 5 tests.

## Verification (full plan `<verification>` block)

| Gate | Result |
|------|--------|
| `fvm flutter analyze lib/core/theme/solvr_theme.dart` | 0 issues |
| `fvm flutter analyze test/theme/solvr_theme_test.dart` | 0 issues |
| `fvm flutter test test/theme/solvr_theme_test.dart` | 7/7 PASS |
| `fvm flutter test` (full suite, regression check) | 8/8 PASS (1 smoke + 7 theme) |
| `grep "BorderRadius.circular" lib/core/theme/solvr_theme.dart` | 0 hits (only `BorderRadius.zero`) |
| `grep "BorderRadius.zero" lib/core/theme/solvr_theme.dart` | present (used 6× across flatShape + inputDecorationTheme) |
| `grep "0xFFFAFAF7"` | present (background) |
| `grep "0xFF1F1F1F"` | present (foreground) |
| `grep "GoogleFonts.interTextTheme"` | present |
| `grep "GoogleFonts.jetBrainsMono"` | present |

## Must-Haves (from PLAN frontmatter)

- [x] **Truth 1** — ThemeData exposes scaffoldBackgroundColor #FAFAF7 and primary #1F1F1F (test 1 + test 2)
- [x] **Truth 2** — All RoundedRectangleBorder shapes use BorderRadius.zero (tests 3 + 4 + 5 + 7 cover card/elevated/outlined/rendered-card; appBar + input border use the same flatShape; visual confirmation in source via grep)
- [x] **Truth 3** — Inter font applies to body text via google_fonts (`SolvrTextStyles.bodyTextTheme` returns `GoogleFonts.interTextTheme(base).apply(...)`; wired into `textTheme:`)
- [x] **Truth 4** — JetBrains Mono font available via `SolvrTextStyles.mono` (test 6)
- [x] **Artifact 1** — `mobile/lib/core/theme/solvr_theme.dart` exists, 132 lines (>= 60 min), contains `BorderRadius.zero`
- [x] **Artifact 2** — `mobile/test/theme/solvr_theme_test.dart` exists, 94 lines (>= 30 min), covers APP-02 invariants
- [x] **Key-link 1** — Plan 06 will be able to `import 'package:agent_playground/core/theme/solvr_theme.dart'` and pass `solvrTheme()` to `MaterialApp.router(theme:)`

## Commits

| Task | Type | Hash | Message |
|------|------|------|---------|
| 1 | feat | `ca4e698` | feat(24-02): add Solvr Labs ThemeData factory with locked tokens |
| 2 | test | `80cd687` | test(24-02): add APP-02 invariant tests for solvrTheme |

(SUMMARY.md commit added below.)

## Deviations from Plan

### Auto-fixed Issues (no user permission needed)

**1. [Rule 3 — Blocking] Removed `useMaterial3: true`**
- **Found during:** Task 1, after first analyze run
- **Issue:** `very_good_analysis` flagged `avoid_redundant_argument_values` because `useMaterial3` is `true` by default in Flutter 3.41.0; the strict lint set treats info-level findings as fail signals during local diff hygiene.
- **Fix:** Dropped the explicit `useMaterial3: true` argument; `ThemeData.light()` already opts in.
- **Files modified:** `mobile/lib/core/theme/solvr_theme.dart`
- **Commit:** rolled into `ca4e698`

**2. [Rule 3 — Blocking] Suppressed `avoid_redundant_argument_values` at flatShape**
- **Found during:** Task 1, second analyze run
- **Issue:** Same lint, this time at `RoundedRectangleBorder(borderRadius: BorderRadius.zero)` — `BorderRadius.zero` is the constructor default. The plan deliberately keeps the argument explicit so APP-02's "zero corners everywhere" invariant is self-documenting at every flat-shape callsite.
- **Fix:** Added a documented `// ignore: avoid_redundant_argument_values` directly above the `borderRadius:` line, with a multi-line `//` comment explaining why (also satisfies the `document_ignores` lint).
- **Files modified:** `mobile/lib/core/theme/solvr_theme.dart`
- **Commit:** rolled into `ca4e698`

**3. [Rule 1 — Bug] Test binding not initialized for google_fonts**
- **Found during:** Task 2, first `flutter test` run
- **Issue:** Plan-template tests called `solvrTheme()` at the top of the `group(...)` block (outside any `test()`), which invokes `GoogleFonts.interTextTheme` → `AssetManifest.loadFromAssetBundle` → throws "Binding has not yet been initialized." All 7 tests failed.
- **Fix attempt 1:** Moved `solvrTheme()` inside each test body and added `TestWidgetsFlutterBinding.ensureInitialized()` at the top of `main()`. Resolved the binding error but uncovered the next bug.
- **Files modified:** `mobile/test/theme/solvr_theme_test.dart`
- **Commit:** rolled into `80cd687`

**4. [Rule 1 — Bug] google_fonts late-async failure ("test failed after it had already completed")**
- **Found during:** Task 2, second `flutter test` run
- **Issue:** `GoogleFonts.interTextTheme` and `GoogleFonts.jetBrainsMono` kick off a fire-and-forget `loadFontIfNecessary` future that fetches font binaries from `fonts.gstatic.com`. Unit tests have no network — the fetch fails AFTER the test's synchronous body completes, and `flutter_test` reports "This test failed after it had already completed" even though every expectation passed. RESEARCH §Pitfall #6 documents this exact case.
- **Fix attempts:**
  - Attempt A: `GoogleFonts.config.allowRuntimeFetching = false` — short-circuited the network fetch but `loadFontIfNecessary` then threw the asset-miss exception synchronously inside the unawaited future. Same late-async failure.
  - Attempt B: `flutter_test_config.dart` with `runZonedGuarded` + `FlutterError.onError` filter for the asset-miss message — failed because each `test()` runs in its own zone created by `flutter_test`, so the outer zone handler doesn't catch.
  - **Final fix:** Converted every `test()` in the suite to `testWidgets()` and added `tester.pumpAndSettle()` after each theme/style construction. The `WidgetTester` binding's microtask pump absorbs google_fonts' pending future before the test completes. 7/7 PASS, full suite 8/8 PASS, no late-async noise. Removed the abandoned `flutter_test_config.dart`.
- **Files modified:** `mobile/test/theme/solvr_theme_test.dart`
- **Files removed:** `mobile/test/flutter_test_config.dart` (intermediate workaround, no longer needed)
- **Commit:** rolled into `80cd687`

**5. [Rule 3 — Blocking] Test imports needed alphabetical sort**
- **Found during:** Task 2 analyze
- **Issue:** `directives_ordering` lint required `package:agent_playground/...` before `package:flutter/...` alphabetically.
- **Fix:** Reordered imports.
- **Files modified:** `mobile/test/theme/solvr_theme_test.dart`
- **Commit:** rolled into `80cd687`

**6. [Rule 3 — Blocking] Long test lines exceeded 80-char limit**
- **Found during:** Task 2 analyze (after testWidgets conversion)
- **Issue:** `lines_longer_than_80_chars` lint flagged 6 lines that came from `await tester.pumpWidget(MaterialApp(theme: theme, home: const SizedBox()));` repeated across 5 tests + the long testWidgets description for the mono-font test.
- **Fix:** Factored `_bootTheme(WidgetTester)` helper that builds + pumps + settles, deduping the lines and dropping the suite under the 80-char ceiling.
- **Files modified:** `mobile/test/theme/solvr_theme_test.dart`
- **Commit:** rolled into `80cd687`

### Plan-template literal deviations

The plan supplied a verbatim test template using plain `test()` for cases 1-6 and `testWidgets` only for the rendered-Card case. After the late-async failure was diagnosed (deviation #4 above), all 7 cases were converted to `testWidgets` with `pumpAndSettle`. Behavior coverage is identical — every original assertion is preserved. The plan's `<behavior>` block (lines 76-82, 235-241) is satisfied.

## Self-Check

- [x] `mobile/lib/core/theme/solvr_theme.dart` — FOUND
- [x] `mobile/test/theme/solvr_theme_test.dart` — FOUND
- [x] Commit `ca4e698` — FOUND in `git log`
- [x] Commit `80cd687` — FOUND in `git log`
- [x] `fvm flutter analyze` clean across both files
- [x] `fvm flutter test` 8/8 PASS (1 smoke + 7 theme)
- [x] No `BorderRadius.circular` in `solvr_theme.dart`
- [x] All authoritative hex values present (`#FAFAF7`, `#1F1F1F`)
- [x] Both `GoogleFonts.interTextTheme` and `GoogleFonts.jetBrainsMono` referenced

## Self-Check: PASSED
