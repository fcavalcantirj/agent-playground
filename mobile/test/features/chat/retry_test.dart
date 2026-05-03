// Phase 25 Wave 4 plan 25-07 task 1 — D-44 + D-45 retry tests.
//
// Verifies:
//   * Retry generates a NEW Uuid().v4() (different idempotency key)
//   * Failed bubble persists across Retry (durable record per D-44)
//   * Retry path inserts a fresh pending pair below the failed row

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

const _agentId = 'a-1';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
      'Retry generates a NEW Idempotency-Key (D-45) and preserves '
      'failed bubble (D-44)', () async {
    ChatScope.autoBootstrap = false;
    addTearDown(() => ChatScope.autoBootstrap = true);

    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    final adapter = DioAdapter(dio: dio);
    final seenIdemKeys = <String>[];

    // First call fails with 500; subsequent calls succeed with 202.
    adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.replyCallback(500, (req) {
        final key = (req.headers['Idempotency-Key'] ??
                req.headers['idempotency-key'] ??
                '') as String;
        seenIdemKeys.add(key);
        return <String, dynamic>{
          'error': {
            'type': 'api_error',
            'code': 'INTERNAL',
            'message': 'boom',
          },
        };
      }),
      data: Matchers.any,
    );

    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(ApiClient(dio))],
    );
    addTearDown(c.dispose);
    final hold = c.listen<ChatState>(
      chatScopeProvider(_agentId),
      (_, _) {},
      fireImmediately: true,
    );
    addTearDown(hold.close);
    final n = c.read(chatScopeProvider(_agentId).notifier);

    await n.sendMessage('hello');
    expect(seenIdemKeys.length, 1);
    final firstKey = seenIdemKeys.first;
    final afterFail = c.read(chatScopeProvider(_agentId));
    final failedEntry = afterFail.byId.entries.firstWhere(
      (e) => e.value.status == 'failed',
    );
    expect(failedEntry.value.role, 'user');
    expect(failedEntry.value.errorMessage, contains('boom'));

    // Reconfigure the adapter to succeed for the retry attempt.
    adapter.reset();
    adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.replyCallback(202, (req) {
        final key = (req.headers['Idempotency-Key'] ??
                req.headers['idempotency-key'] ??
                '') as String;
        seenIdemKeys.add(key);
        return <String, dynamic>{
          'message_id': 'q-2',
          'status': 'queued',
          'queued_at': '2026-05-03T12:00:01Z',
        };
      }),
      data: Matchers.any,
    );

    await n.retryFailed(failedKey: failedEntry.key, content: 'hello');
    expect(seenIdemKeys.length, 2);
    final secondKey = seenIdemKeys[1];
    expect(
      secondKey,
      isNot(firstKey),
      reason: 'D-45 — retry generates a NEW Uuid().v4()',
    );

    // Failed bubble must still be present (D-44 — durable record).
    final after = c.read(chatScopeProvider(_agentId));
    expect(
      after.byId.containsKey(failedEntry.key),
      isTrue,
      reason: 'D-44 — failed bubble persists as durable record',
    );
    // A new pending row was added and flipped to delivered.
    final newPending = after.byId.entries
        .where((e) =>
            e.key.startsWith('pending:') &&
            e.value.status == 'delivered' &&
            e.value.content == 'hello' &&
            e.key != failedEntry.key)
        .toList();
    expect(newPending, isNotEmpty);
  });
}
