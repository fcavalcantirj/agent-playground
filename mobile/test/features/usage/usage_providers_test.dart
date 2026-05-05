// Phase 27 Change 3b Wave 2 — Models + ApiClient methods + Riverpod
// providers. Drives all three together via http_mock_adapter (transport
// seam — real Dio + real JSON encode/decode).
//
// Cases (per 27-CHANGE-3B-PLAN.md Wave 2):
//   - Happy path → UsageSummary populated (totals + by_agent rows)
//   - Empty state → total_usd "0", by_agent []
//   - 401 from server → Result.err(unauthorized) — AuthInterceptor's bus
//     emit is its own concern; here we only assert the typed error path
//   - 404 from per-agent → Result.err(agentNotFound)
//
// ApiClient is exercised directly (the providers wrap the same calls).
// Provider-level wiring (lifecycle resume → invalidateSelf) is verified
// in Wave 3's widget tests where the lifecycle harness lives.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

void main() {
  late Dio dio;
  late DioAdapter adapter;
  late ApiClient api;

  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
  });

  group('GET /v1/usage/summary', () {
    test('happy path → UsageSummary populated', () async {
      adapter.onGet(
        '/v1/usage/summary',
        (s) => s.reply(200, {
          'total_usd': '0.0034',
          'message_count': 12,
          'by_agent': [
            {
              'agent_id': '11111111-1111-1111-1111-111111111111',
              'agent_name': 'hermes-1',
              'recipe_name': 'hermes',
              'model': 'anthropic/claude-haiku-4-5',
              'cost_usd': '0.002',
              'message_count': 8,
              'last_activity': '2026-05-04T22:01:00Z',
            },
            {
              'agent_id': '22222222-2222-2222-2222-222222222222',
              'agent_name': 'openclaw-1',
              'recipe_name': 'openclaw',
              'model': 'claude-sonnet-4-5',
              'cost_usd': '0.0014',
              'message_count': 4,
              'last_activity': '2026-05-04T20:00:00Z',
            },
          ],
        }),
      );
      final r = await api.usageSummary();
      switch (r) {
        case Ok(:final value):
          expect(value.totalUsd, '0.0034');
          expect(value.messageCount, 12);
          expect(value.byAgent, hasLength(2));
          expect(value.byAgent.first.agentName, 'hermes-1');
          expect(value.byAgent.first.costUsd, '0.002');
          expect(value.byAgent.first.lastActivity, '2026-05-04T22:01:00Z');
          expect(value.byAgent[1].model, 'claude-sonnet-4-5');
        case Err(:final error):
          fail('expected Ok, got ${error.message}');
      }
    });

    test('empty state → total_usd "0", by_agent []', () async {
      adapter.onGet(
        '/v1/usage/summary',
        (s) => s.reply(200, {
          'total_usd': '0',
          'message_count': 0,
          'by_agent': <dynamic>[],
        }),
      );
      final r = await api.usageSummary();
      switch (r) {
        case Ok(:final value):
          expect(value.totalUsd, '0');
          expect(value.messageCount, 0);
          expect(value.byAgent, isEmpty);
        case Err(:final error):
          fail('expected Ok, got ${error.message}');
      }
    });

    test('401 from server → Result.err(unauthorized)', () async {
      adapter.onGet(
        '/v1/usage/summary',
        (s) => s.reply(401, {
          'error': {
            'type': 'unauthorized',
            'code': 'UNAUTHORIZED',
            'message': 'Authentication required',
            'param': 'ap_session',
            'request_id': 'req-401',
          },
        }),
      );
      final r = await api.usageSummary();
      switch (r) {
        case Ok():
          fail('expected Err on 401');
        case Err(:final error):
          expect(error.code, ErrorCode.unauthorized);
          expect(error.statusCode, 401);
      }
    });
  });

  group('GET /v1/agents/:id/usage', () {
    test('happy path → AgentUsageData populated', () async {
      const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
      adapter.onGet(
        '/v1/agents/$id/usage',
        (s) => s.reply(200, {
          'agent_id': id,
          'cumulative': {
            'input_tokens': 123,
            'output_tokens': 45,
            'cache_read_tokens': 0,
            'cache_creation_tokens': 0,
            'cost_usd': '0.001234',
            'message_count': 8,
            'last_activity': '2026-05-04T22:01:00Z',
          },
          'series_7d': [
            {
              'day': '2026-04-28',
              'cost_usd': '0.0001',
              'tokens': 50,
              'message_count': 1,
            },
            {
              'day': '2026-05-04',
              'cost_usd': '0.001134',
              'tokens': 118,
              'message_count': 7,
            },
          ],
          'series_30d': [
            {
              'day': '2026-05-04',
              'cost_usd': '0.001234',
              'tokens': 168,
              'message_count': 8,
            },
          ],
        }),
      );
      final r = await api.agentUsage(id);
      switch (r) {
        case Ok(:final value):
          expect(value.agentId, id);
          expect(value.cumulative.inputTokens, 123);
          expect(value.cumulative.costUsd, '0.001234');
          expect(value.cumulative.messageCount, 8);
          expect(value.series7d, hasLength(2));
          expect(value.series7d.first.day, '2026-04-28');
          expect(value.series7d[1].messageCount, 7);
          expect(value.series30d, hasLength(1));
        case Err(:final error):
          fail('expected Ok, got ${error.message}');
      }
    });

    test('404 from server → Result.err(agentNotFound)', () async {
      const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
      adapter.onGet(
        '/v1/agents/$id/usage',
        (s) => s.reply(404, {
          'error': {
            'type': 'not_found',
            'code': 'AGENT_NOT_FOUND',
            'message': 'agent $id not found',
            'param': 'agent_id',
            'request_id': 'req-404',
          },
        }),
      );
      final r = await api.agentUsage(id);
      switch (r) {
        case Ok():
          fail('expected Err on 404');
        case Err(:final error):
          expect(error.code, ErrorCode.agentNotFound);
          expect(error.statusCode, 404);
      }
    });
  });

  group('UsageSummary.fromJson defensive parsing', () {
    test('missing by_agent yields empty list', () {
      final s = UsageSummary.fromJson({
        'total_usd': '0',
        'message_count': 0,
      });
      expect(s.byAgent, isEmpty);
    });

    test('missing optional last_activity → null', () {
      final e = AgentBreakdownEntry.fromJson({
        'agent_id': 'x',
        'agent_name': 'x',
        'recipe_name': 'r',
        'model': 'm',
        'cost_usd': '0',
        'message_count': 0,
      });
      expect(e.lastActivity, isNull);
    });
  });
}
