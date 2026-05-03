// Phase 25 Wave 4 plan 25-07 task 1 — D-41 optimistic insert + send tests.
//
// Drives `chatScopeProvider.sendMessage` through http_mock_adapter and
// asserts:
//   * The optimistic user `pending:<idemKey>` + assistant `typing:<idemKey>`
//     pair appear immediately (before the dio future resolves).
//   * On 202 success, the pending row flips to 'delivered'; the typing
//     placeholder is later cleared by an SSE arrival (driven manually here).
//   * On dio error, the pending row flips to 'failed' and the typing row
//     is removed.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

const _agentId = 'a-1';

class _Harness {
  _Harness() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
  }
  late final Dio dio;
  late final DioAdapter adapter;
  late final ApiClient api;
}

ProviderContainer _container(_Harness h) {
  ChatScope.autoBootstrap = false;
  addTearDown(() => ChatScope.autoBootstrap = true);
  final c = ProviderContainer(
    overrides: [apiClientProvider.overrideWithValue(h.api)],
  );
  addTearDown(c.dispose);
  return c;
}

/// Holds a listener so the autoDispose family provider stays mounted
/// across awaited gaps in the test body.
ProviderSubscription<ChatState> _hold(ProviderContainer c, String agentId) {
  return c.listen<ChatState>(
    chatScopeProvider(agentId),
    (_, _) {},
    fireImmediately: true,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('sendMessage inserts optimistic pending+typing pair (D-41)', () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(202, <String, dynamic>{
        'message_id': 'q-1',
        'status': 'queued',
        'queued_at': '2026-05-03T12:00:00Z',
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    final fut = notifier.sendMessage('hello world');
    // Pre-await: state must already have 2 rows.
    final mid = c.read(chatScopeProvider(_agentId));
    expect(mid.orderedIds.length, 2);
    expect(
      mid.orderedIds.where((id) => id.startsWith('pending:')).length,
      1,
    );
    expect(
      mid.orderedIds.where((id) => id.startsWith('typing:')).length,
      1,
    );
    expect(mid.inflight, isTrue);
    await fut;
    final after = c.read(chatScopeProvider(_agentId));
    // After ack, pending -> delivered; typing remains until SSE clears it.
    final pendingEntry =
        after.byId.entries.firstWhere((e) => e.key.startsWith('pending:'));
    expect(pendingEntry.value.status, 'delivered');
    expect(after.inflight, isFalse);
  });

  test('sendMessage on dio error flips pending -> failed; typing dropped',
      () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(500, <String, dynamic>{
        'error': {
          'type': 'api_error',
          'code': 'INTERNAL',
          'message': 'boom',
        },
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    await notifier.sendMessage('oops');
    final after = c.read(chatScopeProvider(_agentId));
    final pending =
        after.byId.entries.firstWhere((e) => e.key.startsWith('pending:'));
    expect(pending.value.status, 'failed');
    expect(pending.value.errorMessage, contains('boom'));
    expect(
      after.orderedIds.where((id) => id.startsWith('typing:')).length,
      0,
    );
    expect(after.inflight, isFalse);
  });

  test('Assistant SSE arrival replaces typing placeholder (D-41)', () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(202, <String, dynamic>{
        'message_id': 'q-1',
        'status': 'queued',
        'queued_at': '2026-05-03T12:00:00Z',
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    await notifier.sendMessage('hi');
    expect(
      c
          .read(chatScopeProvider(_agentId))
          .orderedIds
          .where((id) => id.startsWith('typing:'))
          .length,
      1,
      reason: 'before SSE arrival, typing placeholder is present',
    );
    notifier.debugOnSse(const SseEvent(
      id: '5',
      kind: 'inapp_outbound',
      data: '{"seq":5,"kind":"inapp_outbound","payload":{"source":"agent",'
          '"content":"hello back","captured_at":"2026-05-03T12:00:01Z"},'
          '"correlation_id":null,"ts":"2026-05-03T12:00:01.001Z"}',
    ));
    final after = c.read(chatScopeProvider(_agentId));
    expect(
      after.orderedIds.where((id) => id.startsWith('typing:')).length,
      0,
    );
    expect(after.byId['sse:5']!.content, 'hello back');
    expect(after.byId['sse:5']!.role, 'assistant');
  });
}
