// Phase 24 Plan 05 — SSE wrapper that tracks Last-Event-Id manually.
//
// RESEARCH §Pitfall #2 (load-bearing): flutter_client_sse 2.0.3 has no
// `lastEventId` parameter and no auto-reconnect. The caller MUST track
// event.id and re-pass `Last-Event-Id` on reconnect. This wrapper owns
// that state machine; the spike (Plan 09) step 8 verifies the cursor
// delivers no-duplicate resume against a live backend.
//
// Carry-forward contracts:
// - Phase 23 D-13: Last-Event-ID resume on reconnect.
// - Phase 23 D-17: Sessions ride `Cookie: ap_session=<uuid>`.
// - Phase 22c.3 D-09/D-34: backend emits `id:<seq>` on every event.

import 'dart:async';

import 'package:flutter_client_sse/constants/sse_request_type_enum.dart';
import 'package:flutter_client_sse/flutter_client_sse.dart';

/// One delivered event surfaced to the consumer (single source of truth
/// for the message bubble + cursor in Phase 25's Chat screen).
class SseEvent {
  const SseEvent({
    required this.id,
    required this.kind,
    required this.data,
  });

  final String? id;
  final String kind;
  final String data;
}

/// Test seam: a function that, given a URL + headers, returns a
/// `Stream` of `SSEModel`. In production we delegate to
/// `SSEClient.subscribeToSSE`. Tests pass an in-process StreamController
/// so we can assert on the headers without going through the real network.
typedef SseSubscribe = Stream<SSEModel> Function({
  required String url,
  required Map<String, String> headers,
});

Stream<SSEModel> _defaultSubscribe({
  required String url,
  required Map<String, String> headers,
}) =>
    SSEClient.subscribeToSSE(
      method: SSERequestType.GET,
      url: url,
      header: headers,
    );

/// Last-Event-Id-tracking SSE wrapper around `flutter_client_sse`.
///
/// The wrapper owns `_lastEventId`; updates it on every received event
/// with a non-empty id; preserves it across `disconnect()` so the next
/// `connect()` re-injects it as `Last-Event-Id`. `resetCursor()` clears
/// the cursor for a fresh-load UX (out of Phase 24 scope).
class MessagesStream {
  MessagesStream({
    required Uri baseUrl,
    required this.agentId,
    required this.cookieProvider,
    SseSubscribe? subscribe,
  })  : _baseUrl = baseUrl,
        _subscribe = subscribe ?? _defaultSubscribe;

  final Uri _baseUrl;
  final String agentId;
  final Future<String?> Function() cookieProvider;
  final SseSubscribe _subscribe;

  String? _lastEventId;
  StreamSubscription<SSEModel>? _sub;
  final StreamController<SseEvent> _events =
      StreamController<SseEvent>.broadcast();

  Stream<SseEvent> get events => _events.stream;

  String? get lastEventId => _lastEventId;

  Future<void> connect() async {
    final cookie = await cookieProvider();
    final headers = <String, String>{
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      if (cookie != null && cookie.isNotEmpty) 'Cookie': 'ap_session=$cookie',
      if (_lastEventId != null && _lastEventId!.isNotEmpty)
        'Last-Event-Id': _lastEventId!,
    };
    final url = _baseUrl
        .resolve('/v1/agents/$agentId/messages/stream')
        .toString();
    final stream = _subscribe(url: url, headers: headers);
    _sub = stream.listen(
      (m) {
        if (m.id != null && m.id!.isNotEmpty) {
          _lastEventId = m.id;
        }
        _events.add(
          SseEvent(
            id: m.id,
            kind: m.event ?? 'unknown',
            data: m.data ?? '',
          ),
        );
      },
      onError: _events.addError,
    );
  }

  /// Disconnect WITHOUT clearing `_lastEventId`. The next `connect()` will
  /// re-pass `Last-Event-Id` and the backend will replay events strictly
  /// AFTER the cursor (Phase 22c.3 D-09/D-34 — `id:<seq>` per event).
  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
  }

  /// Reset cursor — used by future "load fresh" UX. Phase 24 does not
  /// expose this in the placeholder screen.
  void resetCursor() {
    _lastEventId = null;
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _events.close();
  }
}
