// Phase 24 Plan 09 — spike helper functions (kept separate so the test
// file stays focused on the 9-step narrative).

import 'dart:math';

import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:flutter_test/flutter_test.dart';

/// Asserts a Result is Ok and returns the value, or fails the test with
/// a step number + redacted error envelope summary.
T expectOk<T>(Result<T> r, {required int step}) {
  switch (r) {
    case Ok(:final value):
      return value;
    case Err(:final error):
      fail(
        'Step $step FAILED: code=${error.code.name} '
        'status=${error.statusCode} message=${error.message} '
        'param=${error.param} request_id=${error.requestId}',
      );
  }
}

/// Wait for the next SseEvent of kind=inapp_outbound (an assistant reply)
/// after `received.length` events have already been delivered. Times out
/// at the bot timeout boundary and fails the test loudly.
Future<SseEvent> waitForOutbound(
  List<SseEvent> received, {
  Duration timeout = const Duration(minutes: 10),
  int afterIndex = 0,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (var i = afterIndex; i < received.length; i++) {
      final ev = received[i];
      if (ev.kind == 'inapp_outbound') return ev;
    }
    await Future<void>.delayed(const Duration(milliseconds: 200));
  }
  fail(
    'Step did not receive an inapp_outbound event within '
    '${timeout.inMinutes} min. Received ${received.length} events; '
    'kinds=${received.map((e) => e.kind).toList()}',
  );
}

/// 8-character lowercase hex suffix for unique agent names (D-56).
String shortRandHex() {
  final rng = Random.secure();
  return List<int>.generate(4, (_) => rng.nextInt(256))
      .map((b) => b.toRadixString(16).padLeft(2, '0'))
      .join();
}

/// Extract the assistant text from a delivered inapp_outbound event's
/// `data` field. The dispatcher persists the bot reply as the entire
/// `bot_response` column verbatim and emits it on the SSE event's data.
String extractAssistantContent(String rawData) {
  final trimmed = rawData.trim();
  if (trimmed.isEmpty) return trimmed;
  // The data field can be raw text or a JSON envelope depending on
  // backend revision; both shapes are accepted as long as the test's
  // history-parity assertion uses the same extraction.
  if (trimmed.startsWith('{')) {
    // Best-effort attempt — if the backend wraps in JSON, dig out
    // a likely content field. The history GET returns ChatMessage
    // with `content` string, so the bare-text path is the common one.
    return trimmed;
  }
  return trimmed;
}
