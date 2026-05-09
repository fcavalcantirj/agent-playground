// Phase B Plan 12 Task 2 — chat 402 → InsufficientCreditsModal dispatch.
//
// D-21 — when api_server returns 402 INSUFFICIENT_BALANCE on POST
// /v1/agents/<id>/messages, the chat layer must NOT route through the
// existing classifyChatStreamError → RetryBanner path (Phase 31 H4 —
// transient SSE errors). Instead, it must trigger a blocking modal:
//   `showInsufficientCreditsModal(context)` from Plan 11.
//
// Mechanism — `chat_providers.dart`:
//   1. Inspect `ApiError.code == ErrorCode.insufficientBalance` (the new
//      enum value mirroring the api_server `INSUFFICIENT_BALANCE` code).
//   2. On match: flip `chatBlockingErrorProvider` to
//      `ChatBlockingError.insufficientCredits`. Do NOT call `markFailed`
//      (keeps the optimistic pending row out of the FailedBubble path —
//      the modal owns the UX).
//   3. On any other error: existing `markFailed` path stays intact
//      (FailedBubble + retry CTA per D-44 / D-45).
//
// The chat screen has a `ref.listen(chatBlockingErrorProvider)` that
// invokes `showInsufficientCreditsModal(context)` when the provider
// flips and clears the provider state on dismiss. That widget-level
// wiring is exercised through the existing widget-test harness; here we
// drive the notifier-level contract directly.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/features/chat/chat_blocking_error_provider.dart';
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

ProviderSubscription<ChatState> _hold(ProviderContainer c, String agentId) {
  return c.listen<ChatState>(
    chatScopeProvider(agentId),
    (_, _) {},
    fireImmediately: true,
  );
}

ProviderSubscription<ChatBlockingError?> _holdBlocking(ProviderContainer c) {
  return c.listen<ChatBlockingError?>(
    chatBlockingErrorProvider,
    (_, _) {},
    fireImmediately: true,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
      'sendMessage on 402 INSUFFICIENT_BALANCE flips chatBlockingErrorProvider '
      'and does NOT mark pending as failed', () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(402, <String, dynamic>{
        'error': {
          'type': 'payment_required',
          'code': 'INSUFFICIENT_BALANCE',
          'message': 'top up to continue',
        },
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final blockingHold = _holdBlocking(c);
    addTearDown(blockingHold.close);

    // Pre-condition — blocking provider starts null.
    expect(c.read(chatBlockingErrorProvider), isNull);

    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    await notifier.sendMessage('hi');

    // Blocking provider flipped — chat screen will surface the modal.
    expect(
      c.read(chatBlockingErrorProvider),
      ChatBlockingError.insufficientCredits,
    );

    // Pending row was NOT flipped to failed — modal owns the UX.
    final after = c.read(chatScopeProvider(_agentId));
    final pending =
        after.byId.entries.firstWhere((e) => e.key.startsWith('pending:'));
    expect(
      pending.value.status,
      isNot('failed'),
      reason: '402 must NOT route through markFailed (modal owns the UX)',
    );
    // inflight is cleared so the input bar regains its idle state.
    expect(after.inflight, isFalse);
  });

  test(
      'sendMessage on 500 INTERNAL stays on the existing markFailed path '
      '(blockingProvider untouched)', () async {
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
    final blockingHold = _holdBlocking(c);
    addTearDown(blockingHold.close);

    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    await notifier.sendMessage('still works');

    // Blocking provider must remain null — 500 is the FailedBubble path.
    expect(c.read(chatBlockingErrorProvider), isNull);

    final after = c.read(chatScopeProvider(_agentId));
    final pending =
        after.byId.entries.firstWhere((e) => e.key.startsWith('pending:'));
    expect(pending.value.status, 'failed');
    expect(pending.value.errorMessage, contains('boom'));
  });

  test(
      'sendMessage on 401 UNAUTHORIZED stays on the existing markFailed path '
      '(blockingProvider untouched; auth banner is the AuthEventBus path)',
      () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(401, <String, dynamic>{
        'error': {
          'type': 'unauthorized',
          'code': 'UNAUTHORIZED',
          'message': 'please sign in',
        },
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final blockingHold = _holdBlocking(c);
    addTearDown(blockingHold.close);

    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    await notifier.sendMessage('expired session');

    expect(c.read(chatBlockingErrorProvider), isNull);
    final after = c.read(chatScopeProvider(_agentId));
    final pending =
        after.byId.entries.firstWhere((e) => e.key.startsWith('pending:'));
    expect(pending.value.status, 'failed');
  });

  test(
      'retryFailed on 402 also flips chatBlockingErrorProvider and avoids '
      'a second failed bubble', () async {
    final h = _Harness();
    h.adapter.onPost(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(402, <String, dynamic>{
        'error': {
          'type': 'payment_required',
          'code': 'INSUFFICIENT_BALANCE',
          'message': 'top up',
        },
      }),
      data: Matchers.any,
    );
    final c = _container(h);
    final hold = _hold(c, _agentId);
    addTearDown(hold.close);
    final blockingHold = _holdBlocking(c);
    addTearDown(blockingHold.close);

    final notifier = c.read(chatScopeProvider(_agentId).notifier);
    // Seed a prior failed bubble (D-44/D-45 contract).
    notifier.debugMarkFailed('prior-key', 'previous network error');
    expect(c.read(chatBlockingErrorProvider), isNull);

    await notifier.retryFailed(failedKey: 'prior-key', content: 'retry me');

    expect(
      c.read(chatBlockingErrorProvider),
      ChatBlockingError.insufficientCredits,
    );
    // The new pending row added by retryFailed should NOT have flipped to
    // failed (the original failed bubble stays per D-45).
    final after = c.read(chatScopeProvider(_agentId));
    final newPendings = after.byId.entries
        .where((e) => e.key.startsWith('pending:'))
        .toList();
    expect(newPendings.length, 1, reason: 'retry inserts ONE new pending');
    expect(newPendings.single.value.status, isNot('failed'));
  });
}
