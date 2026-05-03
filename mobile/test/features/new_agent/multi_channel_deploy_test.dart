// Phase 25 Wave 3 plan 25-06 task 1 — DeployOrchestrator unit tests.
//
// Covers D-30 / D-56 / D-57 / D-58 + cancellation. Uses http_mock_adapter
// to stub the dio responses and assert the call sequence end-to-end
// without WidgetTester. The orchestrator is a pure-Dart class so these
// are straight unit tests.
//
// Note on `data: _anyBody`: http_mock_adapter's default
// FullHttpRequestMatcher checks the request body against the matcher's
// expected body. Without `data:` the matcher's expected body defaults to
// null and the matcher rejects every actual non-null POST body. Passing
// `Matchers.any` makes the matcher accept any body, so we match by
// route alone.

import 'dart:async';

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/features/chat/telegram_failed_banner_provider.dart';
import 'package:agent_playground/features/new_agent/deploy_orchestrator.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

const _byok = 'sk-or-test';
const _agentId = 'agent_inst_a-1';
// http_mock_adapter exposes Matchers.any as a const AnyMatcher; the type
// itself isn't part of the package's public exports, so we type the
// helper as `Object` to satisfy `specify_nonobvious_property_types`
// without naming the private class. The matcher contract is exercised
// at runtime by every onPost() call below.
// ignore: specify_nonobvious_property_types
const _anyBody = Matchers.any;

({ApiClient api, DioAdapter adapter}) _apiAndAdapter() {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  final adapter = DioAdapter(dio: dio);
  return (api: ApiClient(dio), adapter: adapter);
}

Map<String, dynamic> _runsBody({required bool smokeOk}) => <String, dynamic>{
      'agent_instance_id': _agentId,
      'smoke_ok': smokeOk,
    };

Map<String, dynamic> _startBody() => <String, dynamic>{
      'container_id': 'cid-1',
      'status': 'running',
    };

void main() {
  group('DeployOrchestrator', () {
    test('happy path inapp-only → DeploySuccess', () async {
      final (:api, :adapter) = _apiAndAdapter();
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(200, _runsBody(smokeOk: true)),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.reply(200, _startBody()),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'anthropic/claude-haiku-4-5',
        agentName: 'my-agent',
        byokKey: _byok,
        telegramEnabled: false,
      );

      expect(outcome, isA<DeploySuccess>());
      expect((outcome as DeploySuccess).agentInstanceId, _agentId);
    });

    test('happy path inapp+telegram → DeploySuccess; both /start fired',
        () async {
      final (:api, :adapter) = _apiAndAdapter();
      final inputsSeen = <Map<String, dynamic>>[];
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(200, _runsBody(smokeOk: true)),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallback(200, (ro) {
            inputsSeen.add(ro.data as Map<String, dynamic>);
            return _startBody();
          }),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'anthropic/claude-haiku-4-5',
        agentName: 'my-agent',
        byokKey: _byok,
        telegramEnabled: true,
        telegramInputs: const {
          'TELEGRAM_BOT_TOKEN': 't1',
          'TELEGRAM_ALLOWED_USER': '123456',
        },
      );

      expect(outcome, isA<DeploySuccess>());
      expect(inputsSeen.length, 2);
      expect(inputsSeen[0]['channel'], 'inapp');
      expect(inputsSeen[1]['channel'], 'telegram');
      expect(
        inputsSeen[1]['channel_inputs'] as Map<String, dynamic>,
        containsPair('TELEGRAM_BOT_TOKEN', 't1'),
      );
    });

    test('verdict != PASS → DeploySmokeFail; /start NEVER called', () async {
      final (:api, :adapter) = _apiAndAdapter();
      var startCalls = 0;
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(200, _runsBody(smokeOk: false)),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallback(200, (_) {
            // replyCallback fires PER REQUEST, not at route-registration
            // (that's what onPost(... (s) => s.reply(...)) does — the
            // outer fn runs at register-time).
            startCalls++;
            return _startBody();
          }),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'm',
        agentName: 'n',
        byokKey: _byok,
        telegramEnabled: true,
      );

      expect(outcome, isA<DeploySmokeFail>());
      expect(startCalls, 0);
    });

    test('runs() Err (server 500) → DeployRunsError; /start NEVER called',
        () async {
      final (:api, :adapter) = _apiAndAdapter();
      var startCalls = 0;
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(500, <String, dynamic>{
            'error': <String, dynamic>{
              'type': 'server_error',
              'code': 'INTERNAL',
              'message': 'boom',
            },
          }),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallback(200, (_) {
            startCalls++;
            return _startBody();
          }),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'm',
        agentName: 'n',
        byokKey: _byok,
        telegramEnabled: false,
      );

      expect(outcome, isA<DeployRunsError>());
      expect(startCalls, 0);
    });

    test('inapp /start fail (D-57) → DeployInappFail; telegram NEVER called',
        () async {
      final (:api, :adapter) = _apiAndAdapter();
      var startCalls = 0;
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(200, _runsBody(smokeOk: true)),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallbackAsync(200, (ro) async {
            startCalls++;
            // Synthesize a 503 by throwing the DioException.
            throw DioException(
              requestOptions: ro,
              response: Response<Map<String, dynamic>>(
                requestOptions: ro,
                statusCode: 503,
                data: <String, dynamic>{
                  'error': <String, dynamic>{
                    'type': 'service_unavailable',
                    'code': 'INFRA_UNAVAILABLE',
                    'message': 'docker is sad',
                  },
                },
              ),
              type: DioExceptionType.badResponse,
            );
          }),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'm',
        agentName: 'n',
        byokKey: _byok,
        telegramEnabled: true,
        telegramInputs: const {'TELEGRAM_BOT_TOKEN': 't1'},
      );

      expect(outcome, isA<DeployInappFail>());
      expect(startCalls, 1, reason: 'only inapp; telegram never tried');
    });

    test('telegram /start fail when inapp succeeded (D-58) → '
        'DeployPartialSuccess', () async {
      final (:api, :adapter) = _apiAndAdapter();
      var startCalls = 0;
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(200, _runsBody(smokeOk: true)),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallbackAsync(
            200,
            (ro) async {
              startCalls++;
              final body = ro.data as Map<String, dynamic>;
              if (body['channel'] == 'inapp') {
                return _startBody();
              }
              // telegram fail — synthesize a DioException via 400 path.
              throw DioException(
                requestOptions: ro,
                response: Response<Map<String, dynamic>>(
                  requestOptions: ro,
                  statusCode: 400,
                  data: <String, dynamic>{
                    'error': <String, dynamic>{
                      'type': 'invalid_request',
                      'code': 'CHANNEL_INPUTS_INVALID',
                      'message': 'bot token rejected by Telegram',
                    },
                  },
                ),
                type: DioExceptionType.badResponse,
              );
            },
          ),
          data: _anyBody,
        );

      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'm',
        agentName: 'n',
        byokKey: _byok,
        telegramEnabled: true,
        telegramInputs: const {
          'TELEGRAM_BOT_TOKEN': 't1',
          'TELEGRAM_ALLOWED_USER': '123',
        },
      );

      expect(outcome, isA<DeployPartialSuccess>());
      final ps = outcome as DeployPartialSuccess;
      expect(ps.agentInstanceId, _agentId);
      expect(ps.telegramFailReason, contains('bot token'));
      expect(ps.telegramInputs, containsPair('TELEGRAM_BOT_TOKEN', 't1'));
      expect(startCalls, 2);
    });

    test('CancelToken cancelled before runs() returns → /start NEVER called',
        () async {
      final (:api, :adapter) = _apiAndAdapter();
      var startCalls = 0;
      adapter
        ..onPost(
          '/v1/runs',
          (s) => s.reply(
            200,
            _runsBody(smokeOk: true),
            delay: const Duration(milliseconds: 200),
          ),
          data: _anyBody,
        )
        ..onPost(
          '/v1/agents/$_agentId/start',
          (s) => s.replyCallback(200, (_) {
            startCalls++;
            return _startBody();
          }),
          data: _anyBody,
        );

      final cancel = CancelToken();
      Timer(const Duration(milliseconds: 20), () => cancel.cancel('user'));
      final outcome = await DeployOrchestrator(api).deploy(
        recipeName: 'openclaw',
        modelId: 'm',
        agentName: 'n',
        byokKey: _byok,
        telegramEnabled: false,
        cancelToken: cancel,
      );

      // dio surfaces cancel as DioException → ApiError(code: network,
      // message: 'cancelled'); orchestrator either short-circuits via
      // cancelToken (Cancelled) or surfaces the runs Err (RunsError with
      // code: network). EITHER outcome MUST guarantee /start was never
      // called — that's the load-bearing invariant of cancellation.
      expect(
        outcome,
        anyOf(isA<DeployCancelled>(), isA<DeployRunsError>()),
      );
      expect(startCalls, 0);
    });
  });

  group('telegramFailedBannerProvider', () {
    test('initial state is null', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      expect(container.read(telegramFailedBannerProvider), isNull);
    });

    test('set holds the agentId + reason + inputs; setting null clears',
        () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      container.read(telegramFailedBannerProvider.notifier).state =
          const TelegramFailedBannerState(
        agentInstanceId: 'a-1',
        reason: 'rate limited',
        telegramInputs: {'TELEGRAM_BOT_TOKEN': 't1'},
      );
      final s = container.read(telegramFailedBannerProvider);
      expect(s, isNotNull);
      expect(s!.agentInstanceId, 'a-1');
      expect(s.reason, 'rate limited');
      expect(s.telegramInputs, containsPair('TELEGRAM_BOT_TOKEN', 't1'));

      container.read(telegramFailedBannerProvider.notifier).state = null;
      expect(container.read(telegramFailedBannerProvider), isNull);
    });
  });
}
