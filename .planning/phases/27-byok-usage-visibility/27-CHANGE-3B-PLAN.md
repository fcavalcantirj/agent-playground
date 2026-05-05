# Phase 27 Change 3b — Mobile UI Plan (TDD, recon-confirmed)

**Locked:** 2026-05-04 evening, after 4 parallel Explore agents recon
**Methodology:** TDD (RED → GREEN per wave) — small atomic waves so we never break the suite
**Web:** deferred — separate phase with different brand/look (annotated in 27-CONTEXT.md state tracker)

---

## Recon synthesis (4 agents)

| Surface | Finding |
|---|---|
| **AppBar** | Per-screen (NOT shared). Dashboard `dashboard_screen.dart:94` is the prime mount; Chat `chat_screen.dart:158` is the secondary. Login + Wizard have no ticker |
| **Routing** | `go_router` everywhere. New route added in `mobile/lib/core/router/app_router.dart` |
| **Auth gating** | Implicit via router (router enforces `/login` on 401). No need for an `isSignedInProvider` check inside the ticker |
| **Per-agent screen** | Net-new (no existing detail screen) |
| **Riverpod** | `@riverpod` annotation + `riverpod_generator` codegen. AsyncNotifier + family pattern. Existing reference: `dashboard_providers.dart::AgentsList` |
| **ApiClient** | Dio + `Result<T>`-typed returns (never throws). Auth cookie auto-injected via `AuthInterceptor`. Pattern: `Future<Result<T>> methodName({CancelToken? cancelToken})` |
| **App-resume** | `appLifecycleProvider` already exists; `ref.listen(appLifecycleProvider, …)` is the established refresh trigger |
| **SSE** | `MessagesStream` (`mobile/lib/core/api/messages_stream.dart`) publishes `SseEvent(kind, data)` to a broadcast stream. Listen for `inapp_outbound` to refresh the ticker |
| **Pull-to-refresh** | `RefreshIndicator` + `ref.invalidate(p) → await ref.read(p.future)`. Reuse Dashboard's pattern |
| **Tests** | `http_mock_adapter` (NOT mocktail/mockito); `ProviderScope.overrides` for Riverpod. `_Harness` + `_wrap()` helper convention. `flutter test` runs everything |
| **Chart lib** | `fl_chart` NOT in pubspec. Use `CustomPainter` + `Path` (~30 lines) — no new dep |
| **Theme** | `#FAFAF7` bg / `#1F1F1F` fg / single green accent. Inter + JetBrains Mono. Border-radius zero (flat). `SolvrTextStyles.mono()` for ticker label |
| **Aesthetic — REUSE** | `AsciiAgentBanner`, `EmptyStateScaffold`, `SkeletonRow`, `RetryBanner` ALL exist and fit the breakdown screen |
| **Currency formatter** | NONE exists. Write `usd_formatter.dart` with auto-precision step (`$0.0034` / `$0.04` / `$1.23`). `intl` already in deps |
| **Snackbars** | Per-screen, text-only, 4-8s. Mirror existing pattern |

---

## File inventory (every change)

### NEW files

| Path | Purpose |
|---|---|
| `mobile/lib/core/format/usd_formatter.dart` | Pure function `formatUsd(double or Decimal-string) → String` with auto-precision step |
| `mobile/lib/features/usage/usage_models.dart` | Dart models for `UsageSummary`, `AgentBreakdownEntry`, `AgentUsageData`, `AgentCumulative`, `AgentSeriesEntry` (mirror 3a JSON; D-14 USD as String) |
| `mobile/lib/features/usage/usage_providers.dart` | `UsageSummary` notifier (`@riverpod`) + `AgentUsage` notifier family (`@riverpod` with arg) |
| `mobile/lib/features/usage/usage_ticker_widget.dart` | AppBar trailing widget — USD label + chevron + tap → push to breakdown |
| `mobile/lib/features/usage/agent_usage_screen.dart` | Per-agent breakdown — cumulative headline + 7d/30d charts + empty state via `AsciiAgentBanner` |
| `mobile/lib/features/usage/usage_chart.dart` | `CustomPainter` 7/30-day bar chart (no new dep) |
| `mobile/test/core/format/usd_formatter_test.dart` | Pure unit tests for the formatter |
| `mobile/test/features/usage/usage_providers_test.dart` | Provider tests with mocked Dio |
| `mobile/test/features/usage/usage_ticker_widget_test.dart` | Widget tests (loading / loaded / error / sub-cent vs cent vs dollar) |
| `mobile/test/features/usage/agent_usage_screen_test.dart` | Widget tests (empty / populated / 7d-30d series) |
| `mobile/test/features/usage/usage_chart_test.dart` | CustomPainter tests (7-day shape, scales correctly, empty input) |

### MODIFIED files (small, surgical)

| Path | Change |
|---|---|
| `mobile/lib/core/api/api_client.dart` | + `Future<Result<UsageSummary>> usageSummary({CancelToken? cancelToken})` + `Future<Result<AgentUsageData>> agentUsage(String agentId, {CancelToken? cancelToken})` |
| `mobile/lib/core/router/app_router.dart` | + `GoRoute(path: '/agents/:id/usage', builder: …)` |
| `mobile/lib/features/dashboard/dashboard_screen.dart` | Insert `UsageTickerWidget()` before `PopupMenuButton` in `actions:` (line ~94) |
| `mobile/lib/features/chat/chat_screen.dart` | Same — insert ticker in chat AppBar actions (line ~158) |

**That's it. ~11 new files + 4 surgical edits. Web untouched.**

---

## TDD wave plan (atomic — never break the suite)

### Wave 1 — USD formatter (pure logic, fastest loop)
1. **RED**: write `usd_formatter_test.dart` with these cases:
   - `formatUsd("0")` → `"$0"`
   - `formatUsd("0.0034")` → `"$0.0034"` (sub-cent — 4 decimals)
   - `formatUsd("0.04")` → `"$0.04"` (cent-range — 2 decimals)
   - `formatUsd("1.23")` → `"$1.23"`
   - `formatUsd("1234.56")` → `"$1,234.56"` (commas via `intl`)
   - Boundary: `formatUsd("0.009999")` rounds to `"$0.01"` or stays `"$0.0100"`? **Decision: stays at sub-cent precision until value crosses 0.01 exactly** — pin in test
2. **GREEN**: implement `usd_formatter.dart` (single function, ~20 lines)
3. Run `flutter test test/core/format/` → all green
4. Commit atomically

### Wave 2 — Models + ApiClient methods + Riverpod providers
1. **RED**: write `usage_providers_test.dart` against mocked `/v1/usage/summary` + `/v1/agents/:id/usage` JSON. Cover:
   - Happy path → `UsageSummary` populated
   - Empty state → `total_usd = "0"`, `by_agent = []`
   - 401 from server → emits the AuthRequired error path
   - 404 from server → `Result.err` with `agentNotFound`
2. **GREEN** in this order (so tests turn green incrementally):
   - `usage_models.dart` (pure data classes with `fromJson`)
   - `api_client.dart` extension (`usageSummary` + `agentUsage` methods)
   - `usage_providers.dart` (`UsageSummary` notifier + `AgentUsage(id)` notifier family)
3. Run `flutter test test/features/usage/usage_providers_test.dart` → all green
4. Run `flutter test` (full suite) → no regression
5. Commit atomically

### Wave 3 — Ticker widget
1. **RED**: write `usage_ticker_widget_test.dart`:
   - Loading state → renders skeleton placeholder (small width)
   - Loaded ($0.0034) → renders `$0.0034` with mono font + chevron
   - Loaded ($1.23) → renders `$1.23`
   - Error state → renders muted `$ —` (or similar minimal fallback)
   - Tap → triggers navigation (verified via mocked `GoRouter`)
2. **GREEN**: implement `usage_ticker_widget.dart` (`Consumer` widget, ~50 lines)
3. Run widget tests → green
4. Run full mobile suite → no regression
5. Commit atomically

### Wave 4 — Per-agent breakdown screen + chart
1. **RED**: write `agent_usage_screen_test.dart` + `usage_chart_test.dart`:
   - Empty state → renders `EmptyStateScaffold` + `AsciiAgentBanner`
   - Populated → cumulative headline shows USD + tokens + msg count + last activity
   - 7d series → 7 bar widths proportional to data
   - 30d series → 30 entries (or fewer if days have no rows — server omits empty)
   - Pull-to-refresh → `ref.invalidate(agentUsageProvider(id))` fires
   - 401 from API → AuthRequired path (router redirects to login)
2. **GREEN**: implement `agent_usage_screen.dart` + `usage_chart.dart`
3. Run all tests → green
4. Commit atomically

### Wave 5 — Wire into AppBar + router (smallest, surgical)
1. Add `GoRoute('/agents/:id/usage')` in `app_router.dart`
2. Add `UsageTickerWidget()` to Dashboard AppBar `actions:` array
3. Add `UsageTickerWidget()` to Chat AppBar `actions:` array
4. Run full mobile suite (including dashboard + chat tests) → no regression
5. Commit atomically

### Wave 6 — Live verification (manual, on iOS simulator)
1. Boot the stack per `CLAUDE.md` Local Dev section:
   - `docker compose -f docker-compose.dev.yml up -d postgresql`
   - `set -a; source .env; set +a; AP_ENV=dev DATABASE_URL=… AP_REDIS_URL=… AP_RECIPES_DIR=./recipes api_server/.venv/bin/uvicorn …`
   - `set -a; source .env; set +a; cd mobile && PATH="$HOME/.pub-cache/bin:$PATH" GOOGLE_IOS_CLIENT_ID="$GOOGLE_IOS_CLIENT_ID" AP_OAUTH_GOOGLE_CLIENT_ID="$AP_OAUTH_GOOGLE_CLIENT_ID" AP_OAUTH_GITHUB_MOBILE_CLIENT_ID="$AP_OAUTH_GITHUB_MOBILE_CLIENT_ID" make ios DEVICE=27F84DB8-FC2B-4657-9C0D-029AF11B6DDA BASE_URL=http://localhost:8000`
2. Sign in
3. Deploy a Hermes agent (BYOK OpenRouter) — confirm ticker shows `$0` initially
4. Send "hi" → assert ticker increments within 5s of assistant reply rendering
5. Tap ticker → breakdown screen opens, shows cumulative + 7d series with the 1 day-bucket
6. Send 2 more messages → ticker keeps incrementing
7. Force-quit + relaunch app → ticker shows persisted total
8. Repeat with an Anthropic-direct agent (openclaw) — confirm same behavior

**Live test passes = Change 3b ships. Live test failure = root-cause first per golden rule #4.**

---

## Refresh strategy (locked)

The ticker refreshes via three triggers:

1. **Screen mount** — every screen with `UsageTickerWidget()` in its AppBar fetches on first build via `ref.watch(usageSummaryProvider)`. Riverpod auto-deduplicates if multiple screens mount in succession.
2. **App resume** — `appLifecycleProvider` listener inside the `UsageSummary` notifier fires `ref.invalidateSelf()` on `AppLifecycleState.resumed`.
3. **SSE `inapp_outbound`** — the new `UsageSummary` notifier subscribes to `MessagesStream`'s broadcast and invalidates self when a chat reply lands. Mirror the chat-providers pattern.

NO polling timer. NO manual refresh button on Dashboard. (Pull-to-refresh exists ONLY on the breakdown screen, since the ticker auto-refreshes via the 3 triggers above.)

---

## Aesthetic decisions (locked, reuses existing widgets)

- **Ticker label**: `JetBrains Mono` font, 14sp, bold; auto-precision USD prefix `$`; chevron `Icons.chevron_right` (16sp, muted)
- **Loading state of ticker**: pulsing `$ —` (no spinner — too noisy in the AppBar)
- **Error state of ticker**: subtle `$ —` muted; tap still navigates to breakdown screen which shows the real error there
- **Per-agent breakdown screen header**: `AppBar(title: Text(agent.name))` with back button
- **Cumulative headline**: 28sp w600 USD value, JetBrains Mono; secondary line shows `<n> tokens · <m> messages · <last activity>`
- **Charts**: `CustomPainter` bars, monochrome (`#1F1F1F` fill, `#EFEFEC` track), no animations in v1, week labels via JetBrains Mono day-of-week 2-letter abbrev
- **Empty state**: `EmptyStateScaffold(banner: AsciiAgentBanner(...), heading: 'No usage yet', body: 'Send a message to your agent to see costs here')` — REUSE existing widgets
- **Pull-to-refresh on breakdown screen**: standard Material `RefreshIndicator`
- **Errors on breakdown screen**: `RetryBanner` (existing widget) above the chart area

---

## Test budget (every wave's gate)

After each wave:
```bash
cd mobile && flutter test
# Expect: ALL existing tests pass + new wave's tests pass
```

After Wave 5 (full landed):
```bash
cd mobile && flutter test
# Expect: 100% pass
cd ../api_server && set -a; source ../.env; set +a; .venv/bin/python -m pytest tests/routes/ tests/services/ -q
# Expect: 113+ passes — backend should not be touched
```

---

## Out of scope (deferred)

- Web UI — separate phase with different brand/look
- Phase B credits UI — different unit-of-account, gated on Stripe + paywall arch
- Sparkline inside the ticker itself — defer to v2 polish
- 7d/30d empty-day padding — server omits, client renders gaps as zero-height bars (chart auto-handles)
- Polling fallback if SSE drops — defer; app-resume covers reconnect
- Dark mode — Phase 24 carry-forward; Solvr theme is light-only today

---

## Resume protocol (if `/clear` mid-implementation)

1. Read `memory/MEMORY.md` (auto-loaded)
2. Read `.planning/phases/27-byok-usage-visibility/27-CONTEXT.md` (state tracker)
3. Read this file (`27-CHANGE-3B-PLAN.md`)
4. `git log --oneline -10` — find which wave's commit is most recent; resume next wave
5. `cd mobile && flutter test` — confirm green before continuing

---

## Decisions added to phase D-log

- **D-28** — Mobile-only Phase 27 UI (web deferred to its own brand-aligned phase)
- **D-29** — TDD with 6 atomic waves; commit after each green wave
- **D-30** — Reuse existing `AsciiAgentBanner` / `EmptyStateScaffold` / `SkeletonRow` / `RetryBanner` widgets — don't reinvent
- **D-31** — `CustomPainter` for charts (no new dep); ~30 lines; revisit `fl_chart` only if design grows
- **D-32** — Ticker refresh = 3 triggers (mount + resume + SSE `inapp_outbound`). No polling timer
- **D-33** — Auth gating implicit via router (no `isSignedInProvider`); ticker only renders on signed-in screens because router only mounts those screens to authenticated users
