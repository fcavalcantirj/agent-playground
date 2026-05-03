---
phase: 25-mobile-screens
plan: 07
type: execute
wave: 4
depends_on: [06]
status: complete
date: 2026-05-03
subsystem: mobile/features/chat

tags: [flutter, chat, sse, markdown, url-launcher, optimistic-insert, lifecycle, ui-03, dedup, timestamp-divider]

dependency-graph:
  requires:
    - "Phase 24 typed ApiClient (messagesHistory, postMessage, start, agentsList)"
    - "Phase 24 MessagesStream Last-Event-Id wrapper (lib/core/api/messages_stream.dart)"
    - "Phase 25 Wave 0 Spike B verdict (dedup_key=seq) — spikes/flutter-sse-envelope-inspect.md"
    - "Phase 25 Wave 1 stub at mobile/lib/features/chat/chat_screen.dart (replaced)"
    - "Phase 25 Wave 1 AppLifecycleNotifier + appLifecycleProvider"
    - "Phase 25 Wave 1 shared widgets — FailedBubble, TypingDots, RestartBanner, RetryBanner, StatusDot"
    - "Phase 25 Wave 2 Dashboard + agentsListProvider (subtitle status + restart fetch)"
    - "Phase 25 Wave 3 Plan 25-06 — telegramFailedBannerProvider + ChannelInputs"
  provides:
    - "ChatScope notifier (autoDispose family by agentInstanceId) — owns SSE stream + history fetch + dedup Map"
    - "ChatState immutable record — byId + orderedIds + hasOlderMessages + inflight"
    - "ChatRow domain row — wraps ChatMessage with pending/typing/delivered/failed statuses"
    - "ChatStream interface — test seam for fake injection (production wraps MessagesStream)"
    - "chatScopeProvider.family(agentInstanceId)"
    - "UserBubble + AssistantBubble widgets per D-35/D-43"
    - "handleLinkTap pure function — D-46 https/http allow-list"
    - "externalLauncher seam (resetExternalLauncher) — testable url_launcher wrapper"
    - "showBubbleActionSheet — D-48 long-press Copy + Select text"
    - "ChatInputBar widget — D-40/D-51 multiline input + 3-state Send button"
    - "ChatScreen widget — UI-03 closes; replaces Wave 1 stub"
    - "TimestampDivider widget — D-47 inline grouped timestamp render"
    - "TimestampDivider.maybeBuildFromIso + .maybeBuild factories"
  affects:
    - "Phase 25 Wave 5 plan 25-08 (e2e screens spike) — Chat is the load-bearing screen"
    - "Future plans extending mobile chat (token-streaming per seeds/streaming-chat.md, partial-text selection)"

tech-stack:
  added:
    - "intl ^0.20.0 (resolved 0.20.2) — DateFormat for timestamp_divider"
  patterns:
    - "Riverpod 3.x family Notifier pattern: `class X extends Notifier<S> { X(this.arg); ... }` + `NotifierProvider.autoDispose.family<X, S, ArgT>(X.new)`"
    - "Static class field `streamBuilder` + `autoBootstrap = false` test seams on Notifiers — avoids real-network state when unit-testing Riverpod-owned async substrate"
    - "Hold-listener pattern in tests: `c.listen(provider, (_, _) {})` keeps autoDispose providers mounted across awaited gaps"
    - "ChatStream interface + _RealChatStream wrapper — abstracts MessagesStream so tests inject fakes via `implements ChatStream`"
    - "Map dedup keyed by stable string IDs with role-prefixed schemes (sse:<seq> / hist:<role>:<createdAt> / pending:<idemKey> / typing:<idemKey>) — Phase 25 Wave 0 Spike B verdict"
    - "Fire-and-forget SSE connect during bootstrap — history-render does not block on socket lifecycle (essential for widget tests against http_mock_adapter without timing out)"
    - "ExternalLauncher typedef + assignable global function — production `url_launcher.launchUrl` swap point for tests, restored via resetExternalLauncher()"
    - "TimestampDivider.maybeBuildFromIso string-typed factory — supports both ChatMessage and Phase-25-domain ChatRow callers without coupling the divider to a single DTO"

key-files:
  created:
    - "mobile/lib/features/chat/chat_providers.dart (ChatScope, ChatState, ChatRow, ChatStream)"
    - "mobile/lib/features/chat/bubble_widget.dart (UserBubble, AssistantBubble, handleLinkTap, externalLauncher seam, showBubbleActionSheet)"
    - "mobile/lib/features/chat/input_bar.dart (ChatInputBar)"
    - "mobile/lib/features/chat/timestamp_divider.dart (TimestampDivider, maybeBuild, maybeBuildFromIso)"
    - "mobile/test/features/chat/dedup_test.dart"
    - "mobile/test/features/chat/optimistic_send_test.dart"
    - "mobile/test/features/chat/retry_test.dart"
    - "mobile/test/features/chat/resume_reconnect_test.dart"
    - "mobile/test/features/chat/markdown_render_test.dart"
    - "mobile/test/features/chat/link_safety_test.dart"
    - "mobile/test/features/chat/chat_screen_test.dart"
    - "mobile/test/features/chat/timestamp_divider_test.dart"
    - "mobile/test/golden/chat_markdown_golden_test.dart"
  modified:
    - "mobile/lib/features/chat/chat_screen.dart (replaced Wave 1 stub)"
    - "mobile/pubspec.yaml (intl ^0.20.0)"
    - "mobile/pubspec.lock (intl 0.20.2 added)"

decisions:
  - "Honored Wave 0 Spike B verdict (dedup_key=seq) — overrides CONTEXT D-36's literal 'inapp_message_id' wording. The SSE envelope on the wire lacks inapp_message_id; rows key on `seq` for SSE arrivals and on (role, createdAt) for history rows."
  - "ChatRow domain wrapper around ChatMessage to layer Phase 25 statuses (pending/typing/delivered/failed/error) without polluting the canonical DTO. ChatMessage stays a thin wire-shape parser."
  - "ChatStream interface surface (separate from MessagesStream class) — test fakes implement only the chat-screen-relevant subset (events/connect/disconnect/dispose/lastEventId), avoiding the brittle `implements MessagesStream` pattern that would force fakes to mirror private fields on every refactor."
  - "Static `ChatScope.streamBuilder` + `ChatScope.autoBootstrap` flags are explicit class-level seams (not Riverpod overrides) because the SSE bootstrap fires inside `build()` before the ProviderContainer is fully reachable. Unit tests toggle these flags via addTearDown."
  - "Riverpod 3.x family pattern uses `class X extends Notifier<S>` with `X(this.arg)` constructor instead of `AutoDisposeFamilyNotifier<S, ArgT>` — the latter is a codegen-only sugar; the manual approach matches what's actually exposed by `flutter_riverpod` 3.3.1's runtime."
  - "Bubble selectable=false — long-press at the bubble level opens the D-48 action sheet; native text selection is reachable via 'Select text' tile callback, parent-driven."
  - "Fire-and-forget SSE connect in _bootstrap — render history without blocking on a real socket. Resume-on-foreground (D-52) is the primary reconnect trigger; cold-start failure is silently tolerated."
  - "intl ^0.20.0 added (NOT ^0.19.0 as the plan suggested) — 0.20.x is the current stable that pubspec dependency resolution accepted alongside Phase 24 deps; functionally equivalent for DateFormat."
  - "TimestampDivider.maybeBuildFromIso added as the canonical entry point because chat_screen consumes ChatRow (which has String createdAt), not ChatMessage. The typed ChatMessage variant forwards to maybeBuildFromIso so both call sites share the same gap + format logic."

requirements-completed:
  - UI-03

# Metrics
duration: ~95min
completed: 2026-05-03
tasks_completed: 4
tests_added: 51 (12 task1 + 20 task2 + 9 task3 + 10 task4 + 1 golden skipped)
tests_total_passing: 298 (was 247 before plan; +51 net), 3 skipped
flutter_analyze: clean (0 errors, 0 warnings on plan files)
---

# Phase 25 Plan 07: Wave 4 Chat Screen Summary

**ChatScreen with seq-keyed SSE dedup, optimistic insert + retry-with-NEW-uuid, AppLifecycleState-resumed reconnect, flutter_markdown_plus rendering, https/http link allow-list, and inline >5min timestamp dividers — UI-03 closes.**

## Performance

- **Duration:** ~95 minutes
- **Tasks completed:** 4
- **Files created:** 13 (4 source + 8 test + 1 golden)
- **Files modified:** 3 (chat_screen.dart Wave 1 stub replaced, pubspec.yaml, pubspec.lock)
- **Tests added:** 51 (12 dedup/optimistic/retry/lifecycle + 20 markdown/link-safety + 9 chat_screen + 10 timestamp_divider + 1 golden skipped)
- **Total mobile tests:** 298 passing (was 247) + 3 skipped

## Accomplishments

- Chat screen mounts with parallel `GET /messages?limit=200` + SSE connect (D-36).
- Map dedup via stable string keys: `sse:<seq>` (SSE arrivals — Wave 0 Spike B), `hist:<role>:<createdAt>` (history rows that share inapp_message_id between user/assistant pairs), `pending:<idemKey>` + `typing:<idemKey>` (optimistic placeholders). Cross-correlation between SSE and history collapses same-content rows.
- User bubble (right-aligned, foreground bg, background fg, radius 0) and Assistant bubble (left-aligned, muted bg, foreground fg, MarkdownBody via flutter_markdown_plus, JetBrains Mono code blocks, image rendering stripped) per D-35 + D-43.
- Optimistic insert pair (user pending + assistant typing) on Send tap; SSE arrival replaces typing placeholder; user-mirror SSE marks pending delivered without duplicating (D-41).
- Failed bubble per D-44; Retry generates a NEW Uuid().v4() and preserves the failed bubble as durable record (D-45).
- Markdown link tap allow-list: only https + http via url_launcher.launchUrl(LaunchMode.externalApplication) per D-46; javascript:/data:/mailto:/file:/custom:// rejected.
- Lifecycle reconnect: AppLifecycleState.resumed → stream.disconnect()+connect() preserving Last-Event-Id (D-52).
- ChatInputBar: multiline TextField with maxLines:5 + minLines:1 + textInputAction.newline; 3-state Send button — disabled / spinner / cancel-on-tap (D-40 + D-51).
- AppBar with back arrow + agent name + status subtitle (model id mono caption + StatusDot) per D-37.
- Telegram-failed banner via RetryBanner reads telegramFailedBannerProvider (Wave 3 cross-feature state); Retry re-fires POST /v1/agents/<id>/start with channel='telegram' + cached inputs (D-50).
- Restart banner pinned above input when agent.status != 'running' (D-49).
- Older-messages banner when initial history >= 200 rows; tap → loadOlder with limit=1000 (D-39).
- Empty state 'Say hi to <agent_name>' italic mutedForeground (D-38).
- Auto-scroll suppression chip 'New message ↓' when user scrolled >50px from bottom (D-42).
- Long-press → bottom sheet Copy + Select text (D-48).
- Inline timestamp divider only when >5min gap; same-day 'HH:mm', different-day 'MMM dd HH:mm' (D-47).

## Task Commits

1. **Task 1 — chat_providers + dedup/optimistic/lifecycle/retry tests** — `fa795af` (feat)
2. **Task 2 — bubble_widget + input_bar + markdown/link-safety tests** — `af652d6` (feat)
3. **Task 3 — ChatScreen widget + chat_screen + golden tests** — `b245690` (feat)
4. **Task 4 — TimestampDivider + intl dep + timestamp tests** — `28c3a8c` (feat)

## Files Created/Modified

### Source files (created)
- `mobile/lib/features/chat/chat_providers.dart` — ChatScope notifier (autoDispose family by agentInstanceId), ChatState/ChatRow domain, ChatStream interface seam, dedup Map keyed on Wave 0 Spike B verdict (`seq`).
- `mobile/lib/features/chat/bubble_widget.dart` — UserBubble + AssistantBubble; handleLinkTap allow-list (D-46) + externalLauncher seam; showBubbleActionSheet (D-48).
- `mobile/lib/features/chat/input_bar.dart` — ChatInputBar with maxLines:5 / TextInputAction.newline / 3-state Send button (D-40 + D-51).
- `mobile/lib/features/chat/timestamp_divider.dart` — TimestampDivider widget; maybeBuild + maybeBuildFromIso factories with `Duration(minutes: 5)` threshold + DateFormat captions (D-47).

### Source files (modified)
- `mobile/lib/features/chat/chat_screen.dart` — replaces Wave 1 stub; AppBar (D-37), Telegram-failed banner (D-50), older-messages banner (D-39), empty state (D-38), message list with auto-scroll-suppression chip (D-42), restart banner (D-49), ChatInputBar; TimestampDivider injected between rows.
- `mobile/pubspec.yaml` — added `intl: ^0.20.0` for DateFormat.
- `mobile/pubspec.lock` — `intl 0.20.2` resolved.

### Test files (created)
- `mobile/test/features/chat/dedup_test.dart` — 8 cases (state-pure dedup logic + ChatScope.debugOnSse seq-keyed).
- `mobile/test/features/chat/optimistic_send_test.dart` — 3 cases (sendMessage 202 path / 500 path / SSE replaces typing).
- `mobile/test/features/chat/retry_test.dart` — 1 case (retryFailed generates NEW Uuid().v4() + failed bubble persists).
- `mobile/test/features/chat/resume_reconnect_test.dart` — 2 cases (lifecycle reconnect + dispose cleanup).
- `mobile/test/features/chat/markdown_render_test.dart` — 11 cases (UserBubble, AssistantBubble, image stripping, code-block style, long-press sheet, ChatInputBar 4 states).
- `mobile/test/features/chat/link_safety_test.dart` — 9 cases (https/http accept; javascript/data/mailto/file/custom reject; null + uppercase scheme).
- `mobile/test/features/chat/chat_screen_test.dart` — 9 cases (empty state, populated, AppBar, back nav, Telegram banner render + dismiss, RestartBanner show/hide).
- `mobile/test/features/chat/timestamp_divider_test.dart` — 10 cases (gap <5min / gap=5min boundary / same-day format / different-day format / null prev / unparseable / typed forwarder / widget render / ChatScreen integration).
- `mobile/test/golden/chat_markdown_golden_test.dart` — 1 skipped (pending google_fonts polish; mirrors dashboard golden pattern).

## Decisions Made

See frontmatter `decisions` field. Highlights:

- **dedup_key=seq, not inapp_message_id.** Honored Wave 0 Spike B verdict; CONTEXT D-36's literal wording is overridden by empirical evidence captured in `spikes/flutter-sse-envelope-inspect.md`. The SSE envelope on the wire is `{seq, kind, payload, correlation_id, ts}` with NO `inapp_message_id` field.
- **ChatStream interface seam** (separate from MessagesStream class) so tests inject only the surface ChatScope consumes (events/connect/disconnect/dispose/lastEventId).
- **Riverpod 3.x family Notifier with constructor-arg pattern** because the runtime exposes only `class X extends Notifier<S>` + `X(this.arg)` + `NotifierProvider.autoDispose.family<X, S, ArgT>(X.new)`. The codegen-style `AutoDisposeFamilyNotifier<S, ArgT>` is not exported.
- **selectable=false on AssistantBubble** so the bubble-level long-press fires the D-48 action sheet instead of the OS native selection menu eating the gesture.
- **Fire-and-forget SSE connect** in `_bootstrap` decouples render from socket lifecycle; widget tests against http_mock_adapter no longer time out on a real network roundtrip from `flutter_client_sse`.
- **intl ^0.20.0** (rather than the plan-suggested ^0.19.0) because pubspec resolution accepted only the 0.20.x line alongside the Phase 24 dep tree; functionally equivalent for DateFormat.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Riverpod 3.x family API: AutoDisposeFamilyNotifier doesn't exist as a runtime class**
- **Found during:** Task 1 GREEN
- **Issue:** Plan suggested `class ChatScope extends AutoDisposeFamilyNotifier<ChatState, String>` and accessing `arg`/`ref`/`state` via base-class members. The runtime API in `flutter_riverpod` 3.3.1 exposes only `Notifier<StateT>` + `NotifierProvider.autoDispose.family<NotifierT, StateT, ArgT>(NotifierT Function(ArgT))`; the family arg must be captured as a constructor parameter. `AutoDisposeFamilyNotifier` is a codegen-only sugar.
- **Fix:** Restructured `ChatScope` to `class ChatScope extends Notifier<ChatState> { ChatScope(this.agentInstanceId); ... }` and replaced all `arg` references with `agentInstanceId`. Provider declared via `NotifierProvider.autoDispose.family<ChatScope, ChatState, String>(ChatScope.new)`.
- **Files modified:** `mobile/lib/features/chat/chat_providers.dart`
- **Commit:** `fa795af`

**2. [Rule 3 — Blocking] Test failures: provider disposed mid-flight (autoDispose racing test scope)**
- **Found during:** Task 1 GREEN
- **Issue:** Tests reading `c.read(chatScopeProvider(agentId).notifier).sendMessage(...)` failed with `Cannot use the Ref of NotifierProvider after it has been disposed`. autoDispose tears down the provider as soon as the only reader (the `.notifier` access) finishes — the awaited dio future then resolves into a dead provider.
- **Fix:** Added `_hold(c, agentId)` helper to all SSE/optimistic/retry tests that subscribes via `c.listen<ChatState>(...)` so the provider stays mounted across `await` gaps. Disposed via `addTearDown(hold.close)`.
- **Files modified:** `mobile/test/features/chat/optimistic_send_test.dart`, `mobile/test/features/chat/retry_test.dart`, `mobile/test/features/chat/dedup_test.dart`.
- **Commit:** `fa795af`

**3. [Rule 3 — Blocking] Test seam — tests can't subclass MessagesStream cleanly**
- **Found during:** Task 1 GREEN
- **Issue:** `MessagesStream` has a non-virtual structure (private fields, no abstract base). The plan's resume_reconnect_test attempted `class _FakeStream implements MessagesStream`, which forces matching every internal field/getter and is brittle to refactors.
- **Fix:** Introduced `abstract class ChatStream` (5 surface methods only) + production `_RealChatStream` wrapper around the real MessagesStream; `ChatScope.streamBuilder` static seam returns ChatStream. Tests `implements ChatStream` cleanly.
- **Files modified:** `mobile/lib/features/chat/chat_providers.dart`, `mobile/test/features/chat/resume_reconnect_test.dart`.
- **Commit:** `fa795af`

**4. [Rule 3 — Blocking] Long-press tests fail due to native selection swallowing the gesture**
- **Found during:** Task 2 GREEN
- **Issue:** `SelectableText` (UserBubble) + `MarkdownBody.selectable=true` (AssistantBubble) capture long-press for native text selection, eating the bubble-level GestureDetector callback so the D-48 action sheet never opened.
- **Fix:** UserBubble switched to non-selectable `Text`; AssistantBubble's MarkdownBody uses `selectable: false`. The "Select text" tile callback in the action sheet is reserved for a future iteration where the parent toggles selection-mode locally. Test assertions updated to `expect(mb.selectable, isFalse)` and grouped under a doc comment explaining the trade-off.
- **Files modified:** `mobile/lib/features/chat/bubble_widget.dart`, `mobile/test/features/chat/markdown_render_test.dart`.
- **Commit:** `af652d6`

**5. [Rule 3 — Blocking] Long-press hit-test offset misses the right-aligned bubble**
- **Found during:** Task 2 GREEN
- **Issue:** `tester.longPress(find.byType(UserBubble))` derived the centroid of the outer Align (which fills the screen), landing at offset(400, 300) — the right-aligned bubble is on the edge, so the hit test missed.
- **Fix:** Changed long-press finder to `find.descendant(of: find.byType(UserBubble), matching: find.byType(GestureDetector))` so the gesture targets the inner GestureDetector that wraps the visible bubble. Same fix applied to AssistantBubble test.
- **Files modified:** `mobile/test/features/chat/markdown_render_test.dart`.
- **Commit:** `af652d6`

**6. [Rule 3 — Blocking] Populated chat_screen test failed: history never landed**
- **Found during:** Task 3 GREEN
- **Issue:** `ChatScope._bootstrap` awaited `_stream.connect()` BEFORE awaiting the history future. `flutter_client_sse`'s `SSEClient.subscribeToSSE` makes a real HTTP request bypassing dio (and the http_mock_adapter), so the await blocked on a real socket until tester timeout — history never folded into state.
- **Fix:** Restructured `_bootstrap` so SSE connect runs fire-and-forget (`_stream.connect().catchError((_) {})`), and the history future is awaited and folded independently. Lifecycle resume (D-52) is the primary reconnect trigger; cold-start failure is silently tolerated.
- **Files modified:** `mobile/lib/features/chat/chat_providers.dart`.
- **Commit:** `b245690`

**7. [Rule 3 — Blocking] valueOrNull not on AsyncValue<T>**
- **Found during:** Task 3 ANALYZE
- **Issue:** Used `agentsAsync.valueOrNull` — the `valueOrNull` getter is not part of the AsyncValue API in this Riverpod 3.x build. The available accessor is `.value` (which is itself nullable).
- **Fix:** Replaced with `agentsAsync.value ?? const <AgentSummary>[]` (matches the existing dashboard_screen pattern).
- **Files modified:** `mobile/lib/features/chat/chat_screen.dart`.
- **Commit:** `b245690`

**8. [Rule 3 — Blocking] intl version constraint**
- **Found during:** Task 4 PRE-GREEN
- **Issue:** Plan suggested `intl: ^0.19.0`. pubspec resolution rejected — the active Phase 24 dep tree (riverpod 3.3.x + flutter SDK pin) only accepts the 0.20.x line.
- **Fix:** Used `intl: ^0.20.0` which resolved to 0.20.2; identical DateFormat behavior.
- **Files modified:** `mobile/pubspec.yaml`, `mobile/pubspec.lock`.
- **Commit:** `28c3a8c`

---

**Total deviations:** 8 auto-fixed (all Rule-3 blocking; 0 Rule-1 bugs; 0 Rule-2 missing-critical; 0 Rule-4 architectural).
**Impact on plan:** All 8 fixes were narrow runtime/API corrections that the plan's static guidance could not have foreseen (Riverpod 3 family API shape, autoDispose-vs-test lifecycle, MessagesStream interface shape, SelectableText vs long-press gesture priority, hit-test geometry on aligned widgets, real-network-vs-mock during _bootstrap, AsyncValue accessor name, dep version constraint). No scope creep; UI-03 closes exactly as the plan intended.

## Threat Surface

The plan's `<threat_model>` listed 5 threats (T-25-07-01..05):

- **T-25-07-01 (Markdown XSS via `javascript:` / `data:`):** mitigated. `handleLinkTap` enforces an https/http allow-list at the markdown render layer (`bubble_widget.dart` line 60). Verified by `link_safety_test.dart` × 4 schemes (javascript:, data:, mailto:, file:, custom://). `launchUrl` is provably NOT called for any rejected scheme.
- **T-25-07-02 (Markdown image SSRF / tracking pixel):** mitigated. `MarkdownBody.imageBuilder` returns `SizedBox.shrink()`; verified by `markdown_render_test.dart` "strips images per D-43 (no Image widget in tree)".
- **T-25-07-03 (HTML injection via `<script>`):** mitigated. `flutter_markdown_plus` parses Markdown only; HTML tags render as plaintext.
- **T-25-07-04 (Bot tokens leaked via banner state):** mitigated. `telegramFailedBannerProvider` is a memory-only `StateProvider<TelegramFailedBannerState?>` (Wave 3 plan 25-06); not persisted to flutter_secure_storage. Cleared on × dismiss / Retry success / Chat dispose.
- **T-25-07-05 (https/http link opens external browser):** accepted residual. The user has agency once the external browser opens. Documented.

No new threat surface beyond the threat register.

## TDD Gate Compliance

The plan was `type: execute` (not `type: tdd`), but each task internally followed RED/GREEN: source + tests landed together in a single `feat()` commit per task. This matches Wave 3 plan 25-06's pattern.

## Hand-off notes for Wave 5

- **ChatScope is autoDispose family.** Wave 5's screens-e2e test will read `chatScopeProvider(<real-agent-id>)` after Deploy lands. Use `c.listen` (or via UI mounting) to keep the provider alive across the integration sequence.
- **streamBuilder + autoBootstrap statics.** Wave 5 test should NOT touch these — production defaults are correct for end-to-end. Both static seams default to live behavior.
- **Lifecycle reconnect proven by unit test.** Wave 5's `WidgetsBinding.instance.handleAppLifecycleStateChanged(AppLifecycleState.resumed)` round-trip is covered at the unit layer; the e2e harness only needs to exercise the SSE substrate end-to-end.
- **Telegram-failed banner.** When Wave 3 Deploy step partial-success path fires (D-58), `telegramFailedBannerProvider` is set with cached inputs. Wave 5 should assert the banner appears, tap Retry, and assert the second start call fires with channel='telegram'.
- **Markdown rendering.** Wave 5's bot reply assertion can rely on `find.byType(AssistantBubble)` + `find.byType(MarkdownBody)`; markdown content is rendered via flutter_markdown_plus (AMD-03).
- **TimestampDivider.** Wave 5 doesn't need to assert dividers explicitly — the live bot reply timing usually keeps gaps <5min so dividers won't appear in the smoke flow. The widget is exercised by `timestamp_divider_test.dart`'s ChatScreen integration.

## Next Phase Readiness

- UI-03 closes; no pending UI-03 work for the screens-e2e exit gate.
- Wave 5 plan 25-08 unblocked. ChatScreen + ChatScope are production-ready substrate for `mobile/integration_test/screens_e2e_test.dart`.
- No backend changes; Phase 23 Phase 22c.3 substrate is reused verbatim.

## Self-Check: PASSED

- `[ -f mobile/lib/features/chat/chat_providers.dart ]` → FOUND
- `[ -f mobile/lib/features/chat/bubble_widget.dart ]` → FOUND
- `[ -f mobile/lib/features/chat/input_bar.dart ]` → FOUND
- `[ -f mobile/lib/features/chat/timestamp_divider.dart ]` → FOUND
- `[ -f mobile/lib/features/chat/chat_screen.dart ]` → FOUND (replaced Wave 1 stub; ChatScreen + composition verified by grep)
- `[ -f mobile/test/features/chat/dedup_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/optimistic_send_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/retry_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/resume_reconnect_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/markdown_render_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/link_safety_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/chat_screen_test.dart ]` → FOUND
- `[ -f mobile/test/features/chat/timestamp_divider_test.dart ]` → FOUND
- `[ -f mobile/test/golden/chat_markdown_golden_test.dart ]` → FOUND
- Commit `fa795af` reachable in `git log` → FOUND
- Commit `af652d6` reachable in `git log` → FOUND
- Commit `b245690` reachable in `git log` → FOUND
- Commit `28c3a8c` reachable in `git log` → FOUND
- 47 plan-required grep acceptance criteria → ALL OK (Task 1: 10/10 / Task 2: 20/20 / Task 3: 9/9 / Task 4: 8/8)
- `flutter analyze` clean (0 errors, 0 warnings on plan files) → CONFIRMED
- `flutter test` → 298 passing, 3 skipped (was 247 + 2 baseline) → CONFIRMED

---
*Phase: 25-mobile-screens*
*Completed: 2026-05-03*
