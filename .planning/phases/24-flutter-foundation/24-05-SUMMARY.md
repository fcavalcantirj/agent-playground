---
phase: 24-flutter-foundation
plan: 05
subsystem: mobile/api
tags: [mobile, flutter, sse, messages, last-event-id, dart, tdd]
type: execute
wave: 3
requirements: [APP-03]
dependency-graph:
  requires:
    - 24-01 (Flutter scaffold + flutter_client_sse pinned in pubspec.lock)
    - 24-03 (api_endpoints.dart, dtos.dart, result.dart)
  provides:
    - mobile/lib/core/api/messages_stream.dart (MessagesStream + SseEvent + SseSubscribe seam)
  affects:
    - 24-09 spike step 8 (D-46 Last-Event-Id no-duplicate resume) consumes this wrapper
    - Phase 25 Chat screen will own a MessagesStream instance per agent
tech-stack:
  added:
    - flutter_client_sse 2.0.3 (already in pubspec.lock; first usage lands here)
  patterns:
    - Test seam typedef (SseSubscribe) for in-process StreamController-based unit testing
    - Manual cursor state machine workaround for SSE library lacking W3C auto-resume
key-files:
  created:
    - mobile/lib/core/api/messages_stream.dart
    - mobile/test/api/messages_stream_test.dart
  modified: []
decisions:
  - D-33 (carry-forward Phase 23): SSE library = flutter_client_sse — used here verbatim
  - D-13 (carry-forward Phase 23): Last-Event-ID resume on reconnect — implemented via _lastEventId
  - D-17 (carry-forward Phase 23): Sessions ride Cookie: ap_session=<uuid> — injected in connect()
  - RESEARCH Pitfall #2: confirmed empirically against package source — no lastEventId param, no autoReconnect
metrics:
  duration: ~10m
  completed: 2026-05-02T21:52Z
  tasks_completed: 1/1
  tests_added: 9
  tests_passing: 9
  files_created: 2
  files_modified: 0
  lines_added: ~330
---

# Phase 24 Plan 05: MessagesStream Last-Event-Id Wrapper Summary

**One-liner:** `MessagesStream` wrapper around `flutter_client_sse` 2.0.3 that owns `_lastEventId`, re-injects it as a `Last-Event-Id` header on manual reconnect, and preserves the cursor across `disconnect()` — closing RESEARCH Pitfall #2.

## What Shipped

A unit-tested SSE wrapper class at `mobile/lib/core/api/messages_stream.dart` that fixes the load-bearing flaw in `flutter_client_sse` 2.0.3: the package does NOT auto-track or auto-resume `Last-Event-Id` (no `lastEventId` parameter on `subscribeToSSE`, no `autoReconnect`, no `ReconnectConfig` — verified directly against the pub-cache source at `~/.pub-cache/hosted/pub.dev/flutter_client_sse-2.0.3/lib/flutter_client_sse.dart`).

The wrapper:

- Holds `_lastEventId: String?` as private state.
- On every received `SSEModel`, persists `m.id` to `_lastEventId` only if non-null and non-empty.
- `connect()` builds the headers map with `Accept: text/event-stream`, `Cache-Control: no-cache`, then conditionally `Cookie: ap_session=<uuid>` (when `cookieProvider()` returns a non-empty value) and `Last-Event-Id: <cursor>` (when `_lastEventId` is set). Targets `<baseUrl>/v1/agents/<agentId>/messages/stream`.
- `disconnect()` cancels the listener but does NOT clear the cursor — next `connect()` resumes.
- `resetCursor()` clears `_lastEventId` for a future "fresh load" UX (out of Phase 24 scope).
- `dispose()` cleans up the listener + closes the broadcast `_events` controller.

A test-only seam (`SseSubscribe` typedef) lets unit tests inject an in-process `StreamController<SSEModel>` so the cursor state machine and outbound header map can be asserted without network IO. The default seam delegates to `SSEClient.subscribeToSSE`.

## Tasks

| # | Name                                                        | Status | Commit  |
|---|-------------------------------------------------------------|--------|---------|
| 1 | Task 1: messages_stream.dart — Last-Event-Id-tracking SSE wrapper | DONE | f9d3ca9 (RED) + 275ad33 (GREEN) |

## Tests

`mobile/test/api/messages_stream_test.dart` — 9 unit tests, all green:

1. `starts with lastEventId == null`
2. `updates lastEventId on event with non-empty id`
3. `does NOT update lastEventId on event with null id`
4. `does NOT update lastEventId on event with empty id`
5. `disconnect preserves lastEventId; reconnect re-passes it`  *(load-bearing — Spike step 8)*
6. `resetCursor clears lastEventId`
7. `connect injects Cookie when cookieProvider returns a value`
8. `connect with no cookie + no cursor: minimal headers only`
9. `connect URL targets /v1/agents/<id>/messages/stream`

Run output:
```
00:04 +9: All tests passed!
```

`fvm flutter analyze lib/core/api/messages_stream.dart test/api/messages_stream_test.dart` → `No issues found!`

## must_haves Truths

| Truth | Verification |
|-------|--------------|
| MessagesStream tracks _lastEventId from event.id on every received SSE event | Tests 2/3/4 cover update + ignore-null + ignore-empty branches |
| connect() injects Last-Event-Id header from _lastEventId when set | Test 5 asserts `secondHeaders['Last-Event-Id']` == `'11'` after reconnect |
| disconnect() preserves _lastEventId so reconnect resumes from same cursor | Test 5 asserts `s.lastEventId` still `'11'` after `disconnect()` |
| resetCursor() clears _lastEventId for fresh-load UX | Test 6 asserts `s.lastEventId` is null after `resetCursor()` |
| Cookie: ap_session=<uuid> included in connect headers when cookieProvider returns a value | Test 7 asserts `captured!['Cookie'] == 'ap_session=sess-abc'` |

## Artifacts

| Path | Provides | Lines | Required Strings |
|------|----------|------:|------------------|
| `mobile/lib/core/api/messages_stream.dart` | Last-Event-Id wrapper around flutter_client_sse | 129 | `_lastEventId`, `Last-Event-Id`, `ap_session=`, `void resetCursor` — all present |
| `mobile/test/api/messages_stream_test.dart` | Unit tests covering Last-Event-Id state machine | 201 | n/a |

## Key Links

- `MessagesStream.connect` → `flutter_client_sse SSEClient.subscribeToSSE` via `header: { 'Last-Event-Id': _lastEventId }` when set, through the production seam `_defaultSubscribe`.
- The default seam imports `SSERequestType` from `package:flutter_client_sse/constants/sse_request_type_enum.dart` (re-export not provided by the package's main library file — verified empirically by an analyzer error in the first GREEN compile).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `SSERequestType` not exported by `package:flutter_client_sse/flutter_client_sse.dart`**
- **Found during:** Task 1 GREEN — first analyzer pass after writing the implementation.
- **Issue:** Plan code sample imports only `package:flutter_client_sse/flutter_client_sse.dart` and references `SSERequestType.GET`. That symbol lives in `package:flutter_client_sse/constants/sse_request_type_enum.dart` and is not re-exported by the main library file (the library uses `import` not `export` for it). Compile-time error: `Undefined name 'SSERequestType'`.
- **Fix:** Added a second import line:
  ```dart
  import 'package:flutter_client_sse/constants/sse_request_type_enum.dart';
  ```
- **Files modified:** `mobile/lib/core/api/messages_stream.dart`
- **Commit:** 275ad33

**2. [Rule 1 - Bug] Plan's test sample passed `id: null` to `SSEModel` constructor (kw-only positional)**
- **Found during:** Task 1 RED authoring — plan source listed `SSEModel(id: null, event: 'inapp_outbound', data: 'no-id')`. The package's constructor is `SSEModel({this.data, this.id, this.event})` which accepts that, but the very_good_analysis lint rule `avoid_redundant_argument_values` would flag `id: null` as the default. Wrote `SSEModel(event: 'inapp_outbound', data: 'no-id')` instead (no `id` passed → field stays at its default `''`).
- **Note:** This actually exercises the empty-id branch via the same default; Test 4 separately covers the explicit `id: ''` case to be exhaustive. Both tests pass.
- **Files modified:** `mobile/test/api/messages_stream_test.dart`
- **Commit:** f9d3ca9

**3. [Rule 1 - Lint] Several lint touch-ups under very_good_analysis 10.0.0**
- `avoid_types_on_closure_parameters`: removed `(SSEModel m)` annotation in `stream.listen((m) {...})`.
- `unnecessary_lambdas`: replaced `(Object e, StackTrace s) => _events.addError(e, s)` with a tearoff `_events.addError`.
- `unintended_html_in_doc_comment`: backticked `id:<seq>` → `` `id:<seq>` `` in docstring.
- `cascade_invocations` (×2 in test): combined consecutive `ctrl.add(...)` calls into cascade form.
- `discarded_futures` (test): added a documented `// ignore: discarded_futures` for the intentional fire-and-forget microtask in the reconnect-resumes test (the goal is to deliver one event before the test's `await Future.delayed`).
- `lines_longer_than_80_chars`: shortened the test name string to fit `dart format` width 80.
- **Why auto-fixed:** Project pins `very_good_analysis: ^10.0.0` per Phase 24 D-23 — analyzer-clean is a correctness requirement (Rule 2). Final analyzer output: `No issues found!`.

### Manual / Architectural Changes

None. The plan's `<action>` block was followed structurally; only minimal corrections above were needed to make the code compile under the project's pinned package set + lint suite.

## Self-Check

```bash
[ -f mobile/lib/core/api/messages_stream.dart ] → FOUND
[ -f mobile/test/api/messages_stream_test.dart ] → FOUND
git log --oneline | grep f9d3ca9 → FOUND (test commit)
git log --oneline | grep 275ad33 → FOUND (feat commit)
fvm flutter analyze ... → "No issues found!"
fvm flutter test ... → "+9: All tests passed!"
```

## Self-Check: PASSED

## TDD Gate Compliance

- RED gate: `f9d3ca9` — `test(24-05): add failing tests ...` — confirmed failing pre-implementation (compile error: `Method not found: 'MessagesStream'`).
- GREEN gate: `275ad33` — `feat(24-05): implement MessagesStream ...` — 9/9 tests pass after implementation lands.
- REFACTOR: not needed; the implementation that passed RED→GREEN was already minimal and readable.

## Open Items / Follow-ups

- Plan 24-09's spike (`mobile/integration_test/spike_api_roundtrip_test.dart`) step 8 (D-46) is the live-fire end-to-end verification of this wrapper. Plan 09 will instantiate a `MessagesStream` against a real local `api_server`, drive `connect()` → mid-stream `disconnect()` → `connect()` again, and assert subsequent events arrive without duplicates. The unit tests here exercise the cursor state machine; the spike exercises the wire contract.
- Phase 25's Chat screen will own a `MessagesStream` per agent route. The current API (`events` Stream getter, `connect/disconnect/resetCursor/dispose` methods) is the surface Phase 25 consumes.
- The wrapper does NOT auto-reconnect on transport errors — `flutter_client_sse` itself attempts a 5s retry internally (per source review). That behaviour is preserved as-is; Phase 24 does not opt into custom reconnect policy (D-39 carry-forward — no auto-retry in dio; mobile/SSE side defers reconnect UX to Phase 25 foreground-handling).
