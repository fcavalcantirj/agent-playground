---
phase: 25
plan: 06
subsystem: mobile/features/new_agent
tags: [flutter, new-agent, deploy, telegram, multi-channel, smoke, byok, ui-02-amended-amd-01]
requirements: [UI-02]
dependency_graph:
  requires:
    - 25-05  # wizard scaffolding (WizardShell, wizardScopeProvider, RecipeDetail DTOs)
    - 24-09  # ApiClient.runs / start / agentsList + Result<T> + ApiError
    - 23     # /v1/runs smoke gate + /v1/agents/:id/start contract
  provides:
    - mobile/lib/features/new_agent/deploy_step.dart (DeployStep — wizard step 3)
    - mobile/lib/features/new_agent/channel_inputs.dart (D-54 dynamic Telegram fields)
    - mobile/lib/features/new_agent/deploy_orchestrator.dart (D-56 multi-channel)
    - mobile/lib/features/chat/telegram_failed_banner_provider.dart (D-50 banner state)
  affects:
    - mobile/lib/core/router/app_router.dart (already routes /new-agent/name-deploy here)
tech-stack:
  added:
    - dart:io File (used by telegram_inputs_test.dart for file-content negation)
  patterns:
    - sealed class DeployOutcome (6 variants)
    - StateProvider<TelegramFailedBannerState?> (cross-feature memory-only state)
    - http_mock_adapter onPost(... data: Matchers.any) — required when route matcher must accept any non-null body
    - http_mock_adapter replyCallback / replyCallbackAsync — fires per-request, NOT at route registration
    - DeployStep.orchestratorBuilder static seam — tests inject _FakeOrchestrator subclass
    - DeployOrchestrator(ApiClient api) public-named positional ctor — required so test subclasses can extend via `super.api`
key-files:
  created:
    - mobile/lib/features/new_agent/deploy_orchestrator.dart
    - mobile/lib/features/new_agent/channel_inputs.dart
    - mobile/lib/features/chat/telegram_failed_banner_provider.dart
    - mobile/test/features/new_agent/deploy_step_test.dart
    - mobile/test/features/new_agent/collision_dialog_test.dart
    - mobile/test/features/new_agent/multi_channel_deploy_test.dart
    - mobile/test/features/new_agent/channel_inputs_test.dart
    - mobile/test/features/new_agent/telegram_inputs_test.dart
    - mobile/test/features/new_agent/deploy_nav_test.dart
  modified:
    - mobile/lib/features/new_agent/deploy_step.dart (replaced Wave 1 stub)
decisions:
  - DeployOrchestrator extracted as a pure-Dart class with no Flutter / Riverpod deps, so the 1×/runs + N×/start state machine can be exercised at unit-test granularity (7 outcome paths) without WidgetTester.
  - 6 DeployOutcome variants instead of a 4-variant Result<Outcome,Error> — the surface needs DeploySuccess / DeployPartialSuccess / DeploySmokeFail / DeployRunsError / DeployInappFail / DeployCancelled to map cleanly to D-30 / D-57 / D-58 / D-29 cancel without nested if-chains in DeployStep.
  - DeployStep.orchestratorBuilder is a STATIC field on the public widget class (not on the private state class) so tests can inject _FakeOrchestrator without exposing the state class.
  - `DeployOrchestrator(ApiClient api) : _api = api` uses a public-named positional parameter (the field stays private) so test subclasses can extend via `super.api`.
  - telegramFailedBannerProvider lives in `mobile/lib/features/chat/` (not new_agent/) because it's CONSUMED by Wave 4 Chat. The DeployStep is the WRITER; placing the provider next to the consumer keeps the cross-feature dependency direction explicit.
  - The state is memory-only (StateProvider<T?>), not persisted to flutter_secure_storage, per D-50: bot tokens are per-deploy and must not survive a Chat dispose / sign-out.
  - ChannelInputs renders fields with `Text(input.env)` as the label — the env-var name verbatim. Golden Rule #2 enforced at runtime (widget contract) AND at file-content (telegram_inputs_test grep negation) — comments in the source ARE allowed to mention 'Bot Token' / 'TELEGRAM_BOT_TOKEN' for human context, but string literals are forbidden. The grep test strips `//` comments before searching.
  - http_mock_adapter quirk: `onPost(route, callback)` invokes the callback AT REGISTRATION (to install the response handler on the matcher), so a `(s) { counter++; s.reply(...); }` lambda increments counter when the route is set up, NOT when a request fires. Tests that count actual hits MUST use `(s) => s.replyCallback(200, (_) { counter++; return body; })` so the counter lives inside replyCallback's per-request lambda. Five tests in multi_channel_deploy_test.dart were rewritten this way.
  - http_mock_adapter quirk: the default FullHttpRequestMatcher rejects non-null actual bodies when the matcher's expected body is null, even though the route paths match. All onPost calls therefore pass `data: Matchers.any` (`const _anyBody = Matchers.any`) so route matching is route-only.
  - The Telegram-on form scrolls below the 800x600 default test viewport (toggle row + 2 dynamic TextFields + Deploy button = ~620px). Three widget tests use `tester.ensureVisible(find.widgetWithText(ElevatedButton, 'Deploy'))` before tapping.
  - Comment-stripping in telegram_inputs_test (split on `\n`, drop everything from `//` onward) is intentionally simple — it does NOT handle `/* */` block comments. The test file invariant only matters for string literals, and the ChannelInputs source uses only `//` comments.
metrics:
  duration: ~150 minutes
  completed: 2026-05-03
  task_count: 3
  test_count: 33  # 16 from task 1 + 17 from task 2 (incl. 5 collision) + 1 from task 3, includes 3 banner provider unit tests
  total_test_count_after_plan: 247  # +33 vs the 213 baseline (211 prior + 2 skipped)
  files_created: 8
  files_modified: 1
---

# Phase 25 Plan 06: Deploy Step — Multi-channel Orchestrator + Dynamic Telegram Fields + Failed-Banner Provider Summary

## One-liner

Wired Step 3 of the New-Agent wizard end-to-end: name-validation + collision dialog + smoke loading UX + 6-variant DeployOrchestrator multi-channel state machine + dynamic Telegram input fields rendered straight from `recipe.channels.telegram.required_user_input` + cross-feature TelegramFailedBannerProvider for the D-58 partial-success path; UI-02 (amended via AMD-01) closed.

## Commits

| Hash    | Type    | Subject                                                                  |
| ------- | ------- | ------------------------------------------------------------------------ |
| 6443a82 | feat    | DeployOrchestrator + ChannelInputs + telegramFailedBannerProvider (Task 1)|
| 7c125c7 | feat    | DeployStep widget — wizard step 3 (Task 2)                               |
| 02a0f1d | test    | nav-stack assertion (Task 3)                                             |

## What landed

### Task 1 — Orchestrator + ChannelInputs + Banner Provider

- **`mobile/lib/features/new_agent/deploy_orchestrator.dart`** — pure-Dart class encapsulating the canonical web playground deploy sequence (`frontend/components/playground-form.tsx` lines 316-360):
  1. `POST /v1/runs` (BYOK Bearer) → smoke gate
  2. If smoke PASS: `POST /v1/agents/<id>/start` with `channel='inapp'`
  3. If `telegramEnabled`: `POST /v1/agents/<id>/start` with `channel='telegram'` + the entered `channelInputs`
- 6 outcome variants: `DeploySuccess`, `DeployPartialSuccess`, `DeploySmokeFail`, `DeployRunsError`, `DeployInappFail`, `DeployCancelled`. CancelToken polled between calls.
- **`mobile/lib/features/new_agent/channel_inputs.dart`** — dynamic Telegram-field render loop (D-54). Mirrors web `playground-form.tsx` lines 638-689. Labels = `recipe.channels.telegram.required_user_input[i].env` verbatim. `secret` flag drives `obscureText`. `hint_url` taps go through `url_launcher` with the D-46 https/http allow-list.
- **`mobile/lib/features/chat/telegram_failed_banner_provider.dart`** — `StateProvider<TelegramFailedBannerState?>` holding `agentInstanceId + reason + telegramInputs`. Memory-only per D-50. DeployStep writes; Wave 4 Chat reads.

### Task 2 — DeployStep widget

- **`mobile/lib/features/new_agent/deploy_step.dart`** — replaces the Wave 1 stub.
  - `WizardShell(currentStep: 2)` chrome.
  - `TextField(key: ValueKey('agent_name_field'))` — D-27 regex `^[a-z0-9][a-z0-9_-]*$` + 64-char cap, red error caption.
  - Telegram toggle row — visible ONLY when `recipe.channelsSupported.contains('telegram')` per D-55.
  - `ChannelInputs` widget rendered when toggle is ON (D-54).
  - `Deploy` button gated on `_formValid` — name valid + recipe + model + byok + (telegramEnabled → all required inputs filled).
  - On Deploy tap:
    - **D-28 collision check**: `agentsList()` lookup → if dup, `ConfirmDialog` "Name '{name}' already used" with `Cancel` / `Re-deploy` (destructive) / `Rename` (third button focuses the name field).
    - **D-29 loading UX**: progress card with `CircularProgressIndicator(strokeWidth: 2)` + "Smoke testing recipe + model + key…" + 1s `Stopwatch`-driven elapsed text + Cancel button (cancels via `dio CancelToken`).
    - **D-30 / D-57 fail UX**: red-bordered card with title (`Smoke test failed` or `Couldn't start in-app channel`) + body (verdict.detail or ApiError.message) + Retry / Edit buttons. Edit pops to `/new-agent/clone` (state preserved per D-24).
    - **D-58 partial success**: write `telegramFailedBannerProvider` state + `wizardScopeProvider.notifier.clear()` + `context.go('/chat/<id>')` (REPLACE).
    - **D-60 full success**: clear banner + clear scope + `context.go('/chat/<id>')` (REPLACE).
- Static `DeployStep.orchestratorBuilder` test seam — tests inject `_FakeOrchestrator` subclass to drive each outcome path without dio.

### Task 3 — Nav-stack assertion

- **`mobile/test/features/new_agent/deploy_nav_test.dart`** — runtime widget test that pumps the production `go_router` through three `push()` calls (clone → model → name-deploy), taps Deploy with a fake-success orchestrator, and asserts:
  - `find.text('CHAT_ROUTE_a-1')` present (route swapped to `/chat/<id>`)
  - `Navigator.of(ctx).canPop() == false` (load-bearing — would be `true` if `context.push` had regressed)
  - `router.routerDelegate.currentConfiguration.matches.length == 1`
  - `currentConfiguration.uri.path.startsWith('/chat/')`
- Closes RESEARCH §Open Question Q5.

## Test results

| File                                             | Tests | Pass |
| ------------------------------------------------ | ----- | ---- |
| `multi_channel_deploy_test.dart`                 | 9     | 9    |
| `channel_inputs_test.dart`                       | 6     | 6    |
| `telegram_inputs_test.dart`                      | 1     | 1    |
| `deploy_step_test.dart`                          | 12    | 12   |
| `collision_dialog_test.dart`                     | 5     | 5    |
| `deploy_nav_test.dart`                           | 1     | 1    |
| **Total new in plan 25-06**                      | **34**| **34** |

`flutter test` — `+247 ~2: All tests passed` (213 baseline + 34 new = 247).
`flutter analyze` — no errors or warnings on new / modified files (12 pre-existing info-only lints in unrelated dashboard/golden files).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] DeployOrchestrator constructor signature for test subclassing**
- **Found during:** Task 2 (deploy_step_test.dart authoring)
- **Issue:** Original constructor `const DeployOrchestrator(this._api)` made the parameter privately-named, so test subclasses could not extend via `super.api`.
- **Fix:** Changed to `const DeployOrchestrator(ApiClient api) : _api = api;` — public positional name, private field. Test subclasses now extend cleanly via `super.api`.
- **Files modified:** `mobile/lib/features/new_agent/deploy_orchestrator.dart`
- **Commit:** `7c125c7`

**2. [Rule 3 - Blocking] http_mock_adapter route matcher rejects non-null bodies when expected is null**
- **Found during:** Task 1 (multi_channel_deploy_test authoring)
- **Issue:** Default `FullHttpRequestMatcher` checks the request body against the matcher's expected body. Without `data:` the matcher's expected body defaults to null and rejects every actual non-null POST body — every orchestrator test failed at the matching step.
- **Fix:** All `onPost(...)` calls now pass `data: Matchers.any` (`const _anyBody = Matchers.any;`) so route matching is route-only.
- **Files modified:** `mobile/test/features/new_agent/multi_channel_deploy_test.dart`
- **Commit:** `6443a82`

**3. [Rule 3 - Blocking] http_mock_adapter callback fires AT REGISTRATION, not per request**
- **Found during:** Task 1 (multi_channel_deploy test debugging)
- **Issue:** `onPost(route, (s) { counter++; s.reply(...); })` increments the counter when the route is registered, NOT when a request fires. Five tests measured `startCalls` and saw 1 (registration) instead of 0 / actual call count.
- **Fix:** Rewrote affected tests to use `(s) => s.replyCallback(200, (_) { counter++; return body; })` — `replyCallback` fires per-request.
- **Files modified:** `mobile/test/features/new_agent/multi_channel_deploy_test.dart`
- **Commit:** `6443a82`

**4. [Rule 3 - Blocking] Telegram-on form exceeds 800x600 test viewport**
- **Found during:** Task 2 (D-57 + D-58 widget tests)
- **Issue:** Telegram toggle ON + 2 dynamic ChannelInputs + Deploy button measure ~620px. The Deploy button's hit center landed at `Offset(400, 604)` — outside the 800x600 viewport — and `tester.tap` missed.
- **Fix:** Three tests use `tester.ensureVisible(find.widgetWithText(ElevatedButton, 'Deploy'))` before tapping.
- **Files modified:** `mobile/test/features/new_agent/deploy_step_test.dart`
- **Commit:** `7c125c7`

**5. [Rule 3 - Blocking] Comment vs string literal in `telegram_inputs_test.dart` grep negation**
- **Found during:** Task 1 (Golden Rule #2 enforcement test)
- **Issue:** The negation test searched for `"Bot Token"` (string with quotes) in `channel_inputs.dart`. The source legitimately mentions `"Bot Token"` in a `// NEVER hardcode "Bot Token"` comment, which the test counted as a violation — false positive.
- **Fix:** The test now strips line-ending `//` comments before searching. The invariant still holds for actual string literals.
- **Files modified:** `mobile/test/features/new_agent/telegram_inputs_test.dart`
- **Commit:** `6443a82`

### Architectural changes

None — all 5 deviations were Rule-3 unblockers, no Rule-4 triggers.

## Threat surface follow-up

The plan's threat register listed:
- T-25-06-01: Bot token leak via UI (mitigated by `obscureText: input.secret` per recipe metadata in `channel_inputs.dart`).
- T-25-06-02: Bot token persisted in banner provider (mitigated — `telegram_failed_banner_provider.dart` uses `StateProvider`, NOT `flutter_secure_storage`; the file has no `flutter_secure_storage` import — verified by grep).
- T-25-06-03: Recipe name path-traversal (mitigated by D-27 client regex).
- T-25-06-04: `url_launcher` hint_url scheme injection (mitigated by `_openExternal` https/http allow-list in `channel_inputs.dart`).

No new threat surfaces introduced.

## TDD Gate Compliance

Plan was `type: execute` (not `type: tdd`), but each task internally followed RED/GREEN: source file + tests landed together in a `feat()` commit (Task 1, Task 2) or a `test()` commit (Task 3 — pure regression test against already-shipped widget).

## Self-Check: PASSED

- `[ -f mobile/lib/features/new_agent/deploy_orchestrator.dart ]` → FOUND
- `[ -f mobile/lib/features/new_agent/channel_inputs.dart ]` → FOUND
- `[ -f mobile/lib/features/chat/telegram_failed_banner_provider.dart ]` → FOUND
- `[ -f mobile/lib/features/new_agent/deploy_step.dart ]` → FOUND (replaced stub, verified `class DeployStep` + `DeployOrchestrator` references)
- `[ -f mobile/test/features/new_agent/multi_channel_deploy_test.dart ]` → FOUND
- `[ -f mobile/test/features/new_agent/channel_inputs_test.dart ]` → FOUND
- `[ -f mobile/test/features/new_agent/telegram_inputs_test.dart ]` → FOUND
- `[ -f mobile/test/features/new_agent/deploy_step_test.dart ]` → FOUND
- `[ -f mobile/test/features/new_agent/collision_dialog_test.dart ]` → FOUND
- `[ -f mobile/test/features/new_agent/deploy_nav_test.dart ]` → FOUND
- Commit `6443a82` reachable in `git log` → FOUND
- Commit `7c125c7` reachable in `git log` → FOUND
- Commit `02a0f1d` reachable in `git log` → FOUND
- `flutter test` exit 0 with `+247 ~2: All tests passed` → CONFIRMED
- `flutter analyze` exit 0 (only pre-existing info lints in unrelated files) → CONFIRMED
