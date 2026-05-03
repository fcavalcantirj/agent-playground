// Phase 25 Wave 4 plan 25-07 task 1 — D-36 dedup tests.
//
// Targets the `ChatState` upsert + `ChatScope.debugOnSse` paths. Per Wave 0
// Spike B verdict, dedup keys on `seq` for SSE arrivals; history rows key
// on `(role, created_at)`. Same content arriving via both SSE and history
// must NOT produce a duplicate bubble.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const _agentId = 'a-1';

ProviderContainer _container({Dio? dio}) {
  ChatScope.autoBootstrap = false;
  addTearDown(() => ChatScope.autoBootstrap = true);
  final theDio = dio ?? Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  final api = ApiClient(theDio);
  final c = ProviderContainer(
    overrides: [apiClientProvider.overrideWithValue(api)],
  );
  addTearDown(c.dispose);
  return c;
}

ProviderSubscription<ChatState> _hold(ProviderContainer c) {
  return c.listen<ChatState>(
    chatScopeProvider(_agentId),
    (_, _) {},
    fireImmediately: true,
  );
}

void main() {
  group('ChatState pure dedup logic', () {
    test('History upsertMany dedupes when SSE-content already present', () {
      // Construct a state that already has an SSE-shaped row.
      final pre = const ChatState().upsertOne(
        const ChatRow(
          id: 'sse:1',
          role: 'assistant',
          content: 'reply',
          status: 'delivered',
          createdAt: '2026-05-03T12:00:00Z',
        ),
      );
      // Same content, same createdAt arrives via history.
      final after = pre.upsertManyHistory([
        const ChatMessage(
          inappMessageId: 'msg-1',
          role: 'assistant',
          content: 'reply',
          createdAt: '2026-05-03T12:00:00Z',
        ),
      ]);
      expect(
        after.orderedIds.length,
        1,
        reason: 'same content via SSE + history must collapse to one row',
      );
    });

    test('Empty history insert yields a single delivered row', () {
      final s = const ChatState().upsertManyHistory([
        const ChatMessage(
          inappMessageId: 'm1',
          role: 'user',
          content: 'hi there',
          createdAt: '2026-05-03T12:00:00Z',
        ),
      ]);
      expect(s.orderedIds.length, 1);
      expect(s.byId.values.first.status, 'delivered');
      expect(s.byId.values.first.role, 'user');
    });

    test('upsertOne updates status when key already present (D-36)', () {
      final pre = const ChatState().upsertOne(
        const ChatRow(
          id: 'sse:7',
          role: 'assistant',
          content: 'hello',
          status: 'queued',
          createdAt: '2026-05-03T12:00:00Z',
        ),
      );
      final after = pre.upsertOne(
        const ChatRow(
          id: 'sse:7',
          role: 'assistant',
          content: 'hello',
          status: 'delivered',
          createdAt: '2026-05-03T12:00:00Z',
        ),
      );
      // Map dedup -> still one row, but status flipped.
      expect(after.orderedIds.length, 1);
      expect(after.byId['sse:7']!.status, 'delivered');
    });
  });

  group('ChatScope.debugOnSse — Wave 0 Spike B dedup_key=seq', () {
    test('SSE event keyed on seq is inserted once even on duplicate seq', () {
      final c = _container();
      final hold = _hold(c);
      addTearDown(hold.close);
      final notifier = c.read(chatScopeProvider(_agentId).notifier);
      const ev = SseEvent(
        id: '7',
        kind: 'inapp_outbound',
        data: '{"seq":7,"kind":"inapp_outbound","payload":{"source":"agent",'
            '"content":"hi","captured_at":"2026-05-03T12:00:00Z"},'
            '"correlation_id":null,"ts":"2026-05-03T12:00:00.001Z"}',
      );
      notifier
        ..debugOnSse(ev)
        ..debugOnSse(ev);
      final s = c.read(chatScopeProvider(_agentId));
      expect(s.byId.keys.where((k) => k.startsWith('sse:')).length, 1);
      expect(s.orderedIds.length, 1);
      expect(s.byId['sse:7']!.content, 'hi');
      expect(s.byId['sse:7']!.role, 'assistant');
      expect(s.byId['sse:7']!.status, 'delivered');
    });

    test('Non-inapp_outbound SSE event is ignored', () {
      final c = _container();
      final hold = _hold(c);
      addTearDown(hold.close);
      final notifier = c.read(chatScopeProvider(_agentId).notifier);
      const ev = SseEvent(
        id: '99',
        kind: 'heartbeat',
        data: '{"seq":99}',
      );
      notifier.debugOnSse(ev);
      expect(c.read(chatScopeProvider(_agentId)).byId, isEmpty);
    });

    test('Malformed SSE payload is ignored (no crash)', () {
      final c = _container();
      final hold = _hold(c);
      addTearDown(hold.close);
      final notifier = c.read(chatScopeProvider(_agentId).notifier);
      notifier.debugOnSse(const SseEvent(
        id: '1',
        kind: 'inapp_outbound',
        data: 'not-json',
      ));
      notifier.debugOnSse(const SseEvent(
        id: '2',
        kind: 'inapp_outbound',
        data: '{"seq":"not-an-int"}',
      ));
      expect(c.read(chatScopeProvider(_agentId)).byId, isEmpty);
    });
  });
}
