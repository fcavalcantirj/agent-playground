// Phase 24 Plan 05 — MessagesStream Last-Event-Id state machine.
//
// RESEARCH §Pitfall #2 (load-bearing): flutter_client_sse 2.0.3 has no
// `lastEventId` parameter and no auto-reconnect. The wrapper owns the
// cursor, updates it on every received event, and re-injects it as a
// `Last-Event-Id` header on manual reconnect. These tests exercise that
// state machine via an in-process StreamController seam — no network IO.

import 'dart:async';

import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:flutter_client_sse/flutter_client_sse.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('MessagesStream — Last-Event-Id tracking (RESEARCH Pitfall #2)', () {
    test('starts with lastEventId == null', () {
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) =>
            const Stream<SSEModel>.empty(),
      );
      expect(s.lastEventId, isNull);
    });

    test('updates lastEventId on event with non-empty id', () async {
      final ctrl = StreamController<SSEModel>();
      Map<String, String>? capturedHeaders;
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) {
          capturedHeaders = headers;
          return ctrl.stream;
        },
      );
      await s.connect();
      ctrl.add(SSEModel(id: '7', event: 'inapp_outbound', data: 'hi'));
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(s.lastEventId, '7');
      // first connect: no cursor yet, so no Last-Event-Id header.
      expect(capturedHeaders!['Last-Event-Id'], isNull);
      await s.dispose();
      await ctrl.close();
    });

    test('does NOT update lastEventId on event with null id', () async {
      final ctrl = StreamController<SSEModel>();
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) => ctrl.stream,
      );
      await s.connect();
      ctrl.add(SSEModel(id: '3', event: 'inapp_outbound', data: 'first'));
      ctrl.add(SSEModel(event: 'inapp_outbound', data: 'no-id'));
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(s.lastEventId, '3');
      await s.dispose();
      await ctrl.close();
    });

    test('does NOT update lastEventId on event with empty id', () async {
      final ctrl = StreamController<SSEModel>();
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) => ctrl.stream,
      );
      await s.connect();
      ctrl.add(SSEModel(id: '5', event: 'inapp_outbound', data: '5'));
      ctrl.add(SSEModel(id: '', event: 'inapp_outbound', data: 'empty'));
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(s.lastEventId, '5');
      await s.dispose();
      await ctrl.close();
    });

    test('disconnect preserves lastEventId; reconnect re-passes it', () async {
      final firstHeaders = <String, String>{};
      final secondHeaders = <String, String>{};
      var call = 0;
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) {
          call++;
          if (call == 1) firstHeaders.addAll(headers);
          if (call == 2) secondHeaders.addAll(headers);
          final c = StreamController<SSEModel>();
          if (call == 1) {
            Future<void>.microtask(() {
              c.add(SSEModel(id: '11', event: 'inapp_outbound', data: 'a'));
            });
          }
          return c.stream;
        },
      );
      await s.connect();
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(s.lastEventId, '11');
      expect(firstHeaders.containsKey('Last-Event-Id'), isFalse);

      await s.disconnect();
      expect(s.lastEventId, '11', reason: 'disconnect must preserve cursor');

      await s.connect();
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(secondHeaders['Last-Event-Id'], '11');
      await s.dispose();
    });

    test('resetCursor clears lastEventId', () async {
      final ctrl = StreamController<SSEModel>();
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) => ctrl.stream,
      );
      await s.connect();
      ctrl.add(SSEModel(id: '99', event: 'inapp_outbound', data: ''));
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(s.lastEventId, '99');
      s.resetCursor();
      expect(s.lastEventId, isNull);
      await s.dispose();
      await ctrl.close();
    });

    test('connect injects Cookie when cookieProvider returns a value',
        () async {
      Map<String, String>? captured;
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => 'sess-abc',
        subscribe: ({required url, required headers}) {
          captured = headers;
          return const Stream<SSEModel>.empty();
        },
      );
      await s.connect();
      expect(captured!['Cookie'], 'ap_session=sess-abc');
      expect(captured!['Accept'], 'text/event-stream');
      expect(captured!['Cache-Control'], 'no-cache');
      await s.dispose();
    });

    test(
        'connect with no cookie + no cursor => only Accept + Cache-Control headers',
        () async {
      Map<String, String>? captured;
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-1',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) {
          captured = headers;
          return const Stream<SSEModel>.empty();
        },
      );
      await s.connect();
      expect(captured!.containsKey('Cookie'), isFalse);
      expect(captured!.containsKey('Last-Event-Id'), isFalse);
      expect(captured!['Accept'], 'text/event-stream');
      expect(captured!['Cache-Control'], 'no-cache');
      await s.dispose();
    });

    test('connect URL targets /v1/agents/<id>/messages/stream', () async {
      String? captured;
      final s = MessagesStream(
        baseUrl: Uri.parse('http://localhost:8000'),
        agentId: 'agent-xyz',
        cookieProvider: () async => null,
        subscribe: ({required url, required headers}) {
          captured = url;
          return const Stream<SSEModel>.empty();
        },
      );
      await s.connect();
      expect(
        captured,
        'http://localhost:8000/v1/agents/agent-xyz/messages/stream',
      );
      await s.dispose();
    });
  });
}
