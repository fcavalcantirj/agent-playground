---
phase: 24-flutter-foundation
plan: 09
subsystem: testing
tags: [flutter, integration_test, sse, idempotency, last-event-id, byok, openrouter, dio, spike]

# Dependency graph
requires:
  - phase: 24-flutter-foundation
    provides: ApiClient (Plan 04) + MessagesStream (Plan 05) + RedactingLogInterceptor (Plan 04) + Makefile spike target (Plan 08)
  - phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
    provides: POST /v1/runs + /agents/:id/start + /agents/:id/messages (block-and-fast-ack) + SSE stream + history GET + Idempotency-Key replay (D-09) + cookie session middleware (D-17)
  - phase: 22c.3-inapp-chat-channel
    provides: inapp dispatcher + outbox + SSE id:<seq> per event (D-09/D-34)
  - phase: 22c-oauth-google
    provides: browser OAuth flow that mints the ap_session cookie used by the spike via cookie-paste (D-49)
provides:
  - 9-step integration_test spike covering deploy → start → SSE connect → post → reply → history parity → idem replay → Last-Event-Id resume → stop
  - reusable spike helpers (expectOk + waitForOutbound + shortRandHex + extractAssistantContent) to seed Phase 25 chat-screen integration tests
affects: [25-flutter-screens, exit-gate-verifier, ci-mobile-workflow]

# Tech tracking
tech-stack:
  added: [integration_test (already in pubspec; first usage)]
  patterns:
    - "9-step end-to-end spike against REAL infra — Golden Rule #1 + #5 enforcement at the foundation layer"
    - "spike as regression test post-execution (lives at integration_test/, runs via make spike)"
    - "test-side --dart-define for BASE_URL / SESSION_ID / OPENROUTER_KEY (D-49/D-50/D-51) — env-config outside the app"
    - "step-numbered failure capture via expectOk (redacted error envelope, no Cookie/Authorization values)"

key-files:
  created:
    - mobile/integration_test/spike_api_roundtrip_test.dart
    - mobile/integration_test/spike_helpers.dart
  modified: []

key-decisions:
  - "Helpers are public (no underscore prefix) so they can be shared with Phase 25 chat-screen integration tests later"
  - "Single inline lint suppression on BaseOptions.baseUrl (avoid_redundant_argument_values) with documented rationale: const-evaluation sees fromEnvironment as '' at static-analysis time, runtime expect() guards non-empty"
  - "RedactingLogInterceptor attached on the spike dio (D-52) — same redaction policy as production; mitigates T-24-09-01"
  - "Bot-timeout ceiling at 10 min (waitForOutbound) matches dispatcher 600s timeout (Phase 22c.3 D-40); test-level Timeout at 15 min for the whole 9-step run (D-55 half-day max)"
  - "Step 8 cursor-survival assertion added on top of spec: after disconnect(), expect stream.lastEventId unchanged before reconnect (Plan 05 contract regression guard)"

patterns-established:
  - "Integration test as exit-gate artifact: D-53 makes spike PASS a HARD precondition for Phase 25's plan-checker; spike file stays in tree as a regression test"
  - "Single testWidgets block, sequential 9 steps with === Step N === comment banners — narrative test layout"
  - "Step-numbered fail() messages include code/status/message/param/request_id from the typed ApiError envelope, redacting nothing in the envelope itself but never logging Cookie/Authorization values"

requirements-completed: [APP-05]

# Metrics
duration: ~12min
completed: 2026-05-02
---

# Phase 24 Plan 09: Live API Round-trip Spike Summary

**Two integration_test files (259 + 72 LOC) drive ApiClient + MessagesStream through the full 9-step D-46 round-trip — deploy / start / SSE / send / reply / history-parity / idem-replay / Last-Event-Id-resume / stop — against a live local api_server + Docker + OpenRouter.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-02T22:14:00Z (approximate — start of executor)
- **Completed:** 2026-05-02T22:27:01Z
- **Tasks committed:** 1 (Task 1; Task 0 + Task 2 are checkpoint:human gates handled by the orchestrator)
- **Files modified:** 2 created

## Accomplishments

- **9-step round-trip test wired** — every D-46 step has a section banner + assertion. `flutter analyze` shows 0 issues across the whole project.
- **All 6 must-have grep checks pass** (`IntegrationTestWidgetsFlutterBinding`, `POST /v1/runs`, all 9 `// Step N` comments, `stream.lastEventId`, `expect(replayAck.messageId, messageId`, `expect(duplicates, isEmpty`, `RedactingLogInterceptor`).
- **Helpers extracted to spike_helpers.dart** (72 LOC) so Phase 25 chat tests can re-use `expectOk` / `waitForOutbound` without duplication.
- **D-50 fail-loud env-var contract honored** at the top of `main()` — `BASE_URL` / `SESSION_ID` / `OPENROUTER_KEY` are checked with `expect(..., isNotEmpty)` before any HTTP call.
- **D-52 redaction guarantee preserved** — `RedactingLogInterceptor` sits in front of the per-spike Cookie-injecting interceptor on the same dio, so any developer.log path goes through redaction.

## Task Commits

Each task was committed atomically:

1. **Task 1: spike_helpers.dart + spike_api_roundtrip_test.dart — 9-step round-trip** — `025b854` (test)

**Plan metadata commit:** Pending — orchestrator commits SUMMARY.md after Task 2 (live `make spike`) returns PASS.

_Note: Task 0 (`checkpoint:human-action`) was a pre-flight gate handled before the executor wrote code. Task 2 (`checkpoint:human-verify`) is the live-spike invocation — handled by the orchestrator, not this executor (sequential-executor scope per orchestrator's `<execution_context>`)._

## Files Created/Modified

- `mobile/integration_test/spike_api_roundtrip_test.dart` (259 LOC) — single testWidgets block; 9 `// Step N` banners; assertions on `runResp.agentInstanceId` non-empty, `firstReplyText` non-empty, `stream.lastEventId` non-null, history-vs-SSE byte equality, `replayAck.messageId == messageId`, `duplicates.isEmpty` after Last-Event-Id resume; cleanup at end (sseSub.cancel + stream.dispose + dio.close); 15-min hard timeout
- `mobile/integration_test/spike_helpers.dart` (72 LOC) — `expectOk<T>` (Result→T or fail with redacted code/status/message/param/request_id), `waitForOutbound` (10-min ceiling poll loop; `afterIndex` parameter for the resume case), `shortRandHex` (8-char Random.secure suffix for D-56 unique agent names), `extractAssistantContent` (best-effort body extractor that the parity assertion uses on both sides of the comparison)

## Decisions Made

- **Public helpers (no `_` prefix):** the spike file imports them from `spike_helpers.dart`, and Phase 25's chat-screen integration tests will reuse them without copy/paste. Private helpers would force duplication.
- **Single inline lint suppression on `BaseOptions(baseUrl: _baseUrl)`:** `_baseUrl` is `String.fromEnvironment('BASE_URL')` which the analyzer evaluates at static-analysis time as `''`, matching `BaseOptions.baseUrl`'s default. The runtime `expect(_baseUrl, isNotEmpty)` four lines above guards against the empty case. A `// ignore: avoid_redundant_argument_values` directive with an explanatory comment block was the cleanest fix vs. a setter / a dummy non-empty default.
- **Step 8 cursor-survival assertion:** plan only required no-duplicate after resume, but I added an extra `expect(stream.lastEventId, lastSeenId)` between disconnect() and connect() — this guards against a Plan 05 regression where disconnect() accidentally clears the cursor. Cheap insurance.
- **`waitForOutbound` 10-minute ceiling:** matches the dispatcher 600s timeout (Phase 22c.3 D-40). Test-level `Timeout(Duration(minutes: 15))` covers the entire 9-step run with 5 min slack for setup/teardown — under the D-55 half-day cap.

## Deviations from Plan

[Rule 1 - Bug] **Lint compliance — `directives_ordering` + `lines_longer_than_80_chars` + `avoid_redundant_argument_values` + `document_ignores`**

- **Found during:** Task 1, after first `fvm flutter analyze` run
- **Issue:** First-pass code copied from the plan's <action> Step 1 + Step 2 code blocks tripped 9 info-level lints under `very_good_analysis` — non-alphabetical import groups, three lines >80 chars (incl. step-7 banner comment, agent-name template, step-8 fail reason), redundant `defaultValue: ''` on three `String.fromEnvironment` calls + one `BaseOptions.baseUrl`, and a missing rationale comment on the inline ignore directive.
- **Fix:** (a) merged the two import groups into a single alphabetized block; (b) split the agent-name into `final ts = ...; agentName = 'spike-roundtrip-$ts-${shortRandHex()}'`; (c) shortened the step-7/step-8 banner comments and the long fail-reason strings; (d) dropped `defaultValue: ''` on the three top-level fromEnvironment consts (empty string IS the default); (e) added a doc-block above the BaseOptions ignore directive explaining the const-evaluation gotcha.
- **Files modified:** `mobile/integration_test/spike_api_roundtrip_test.dart`, `mobile/integration_test/spike_helpers.dart`
- **Verification:** `fvm flutter analyze` → "No issues found! (ran in 2.0s)"
- **Committed in:** `025b854` (Task 1 commit — these were applied before the first commit, not a follow-up)

---

**Total deviations:** 1 auto-fixed (1 lint-compliance pass)
**Impact on plan:** None — all the plan's required asserts + the 9-step narrative + the must-have grep tokens are intact. Behavior unchanged; only formatting + redundant-defaults removed.

## Issues Encountered

None. The plan's <action> Step 1 + Step 2 code blocks compile cleanly against the existing Plan 04/05 substrate after lint cleanup.

## User Setup Required

None — the spike requires `BASE_URL` / `SESSION_ID` / `OPENROUTER_KEY` env vars at `make spike` invocation time, but that's the orchestrator's Task 2 checkpoint (D-49/D-50/D-51), not a configuration step for this executor's deliverable.

## Next Phase Readiness

- **Code is staged for the live spike run.** The orchestrator's next step is to collect `SESSION_ID` (browser-cookie paste) + `OPENROUTER_KEY` from the user, then run `cd mobile && make spike BASE_URL=http://localhost:8000 SESSION_ID=... OPENROUTER_KEY=...` against the booted iPhone 16e simulator (3D61926B-A0F6-443E-AF7E-A2E674E74DDF). On PASS the orchestrator records the live-run results in `spikes/flutter-api-roundtrip.md` (Plan 10) — that artifact closes the Phase 24 exit gate (D-53) for Phase 25's plan-checker.
- **No blockers** — substrate from Plans 04/05/06/08 is unchanged; this plan only adds two new files under `integration_test/`.
- **STATE.md / ROADMAP.md untouched** per the orchestrator's `<sequential_execution>` directive.

## Self-Check

Verifying claims:

- File `mobile/integration_test/spike_api_roundtrip_test.dart`: FOUND (259 LOC, ≥ 120 min)
- File `mobile/integration_test/spike_helpers.dart`: FOUND (72 LOC, ≥ 30 min)
- Commit `025b854`: FOUND
- `fvm flutter analyze` exit 0: VERIFIED ("No issues found!")
- All 6 must-have grep checks: PASSED (binding / POST /v1/runs / 9 steps / stream.lastEventId / replay-message-id / duplicates-empty / RedactingLogInterceptor)

## Self-Check: PASSED

---
*Phase: 24-flutter-foundation*
*Completed: 2026-05-02*
