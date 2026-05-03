// Phase 25 Wave 5 D-65 — widget-level helpers for the screens e2e driver.
//
// Kept separate from `spike_helpers.dart` (Phase 24) so the unit-level
// helpers (`expectOk`, `waitForOutbound`, `shortRandHex`,
// `extractAssistantContent`) stay reusable, and the widget-level helpers
// (which need a `WidgetTester`) live next to the only file that uses
// them. The pumpAndSettle vs pump+timeout distinction matters here: any
// helper that drives the wizard / chat MUST tolerate
// in-flight network calls and SSE deliveries, so plain pumpAndSettle is
// not always the right tool (it never settles when a stream is open).
//
// Helpers:
//   * tapAndSettle      — tap a finder, then pumpAndSettle (with cap).
//   * waitForFinder     — poll-pump until a finder matches, with timeout.
//   * waitForChatBubble — wait for a bubble whose content equals/contains
//                         the given text (assistant or user side).
//   * pumpUntilSettled  — bounded pump loop; mirrors the Phase 24 spike's
//                         "pump up to N times" pattern for streams that
//                         never quiesce.

import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// Tap [finder] and pumpAndSettle for up to [timeout]. Defaults to a
/// generous 30s ceiling so a recipe-detail fetch on tap doesn't time out
/// the helper itself.
Future<void> tapAndSettle(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  await tester.tap(finder);
  // Phase 25 — short pumpAndSettle window so a single tap dispatches the
  // gesture without waiting for stream-driven animation timers.
  // ignore: avoid_redundant_argument_values
  await tester.pumpAndSettle(const Duration(milliseconds: 100));
  await pumpUntilSettled(tester, timeout: timeout);
}

/// Pump in 200ms increments until the widget tree quiesces, capped at
/// [timeout]. Unlike `pumpAndSettle`, this does not throw when there are
/// pending timers (e.g. an SSE keepalive); it just stops pumping.
Future<void> pumpUntilSettled(
  WidgetTester tester, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (!tester.binding.hasScheduledFrame) return;
  }
}

/// Poll-pump until [finder] matches at least one widget, or [timeout]
/// elapses. Fails the test loudly with the matched-widget count and the
/// elapsed time when timeout hits. Used for any wait that depends on a
/// network round-trip (Login → Dashboard, Deploy → Chat, SSE arrival).
Future<void> waitForFinder(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(minutes: 2),
  String? reason,
}) async {
  final start = DateTime.now();
  final deadline = start.add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) return;
  }
  final elapsed = DateTime.now().difference(start);
  fail(
    'waitForFinder timed out after ${elapsed.inSeconds}s waiting for '
    '$finder${reason == null ? '' : ' ($reason)'}',
  );
}

/// Wait for a chat bubble whose visible text equals [content]. Both
/// `UserBubble` (right-aligned Text) and `AssistantBubble`
/// (`MarkdownBody`) render the content as plain Text on the
/// happy-path "hi" / short-reply case, so a Text-finder is sufficient.
Future<void> waitForChatBubble(
  WidgetTester tester,
  String content, {
  Duration timeout = const Duration(minutes: 2),
}) async {
  await waitForFinder(
    tester,
    find.text(content),
    timeout: timeout,
    reason: 'chat bubble with content "$content"',
  );
}

/// Wait for a chat bubble whose visible text *contains* [substring]. Used
/// when the assistant reply is dynamic (e.g. greetings vary) — caller
/// only knows the leading characters or a known marker substring.
Future<void> waitForChatBubbleContaining(
  WidgetTester tester,
  String substring, {
  Duration timeout = const Duration(minutes: 2),
}) async {
  final start = DateTime.now();
  final deadline = start.add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    final found = find
        .byWidgetPredicate(
          (w) => w is Text && (w.data ?? '').contains(substring),
        )
        .evaluate();
    if (found.isNotEmpty) return;
  }
  final elapsed = DateTime.now().difference(start);
  fail(
    'waitForChatBubbleContaining timed out after ${elapsed.inSeconds}s '
    'waiting for any Text containing "$substring"',
  );
}

/// Seed the secureStorage's session_id slot before the app boots. Used by
/// the Wave 5 driver in Step 9 (kill+relaunch): the relaunch must NOT
/// re-trigger the AuthService sheet, so the session has to already be
/// persisted.
Future<void> seedSecureStorage(SecureStorage storage, String sessionId) async {
  await storage.writeSessionId(sessionId);
}
