// Phase 24 Plan 04 — ApiClient happy-path + early-validation coverage.
//
// Drives the typed client via dio's `http_mock_adapter` — an in-process
// transport seam (NOT a service mock per Golden Rule #1: real dio, real
// JSON encode/decode, real interceptor chain; only the network socket
// is short-circuited). Plan 09's spike instead drives ApiClient against
// a live api_server in a Docker network.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
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

  test('healthz returns Ok(HealthOk(true))', () async {
    adapter.onGet('/healthz', (server) => server.reply(200, {'ok': true}));
    final r = await api.healthz();
    switch (r) {
      case Ok(:final value):
        expect(value.ok, isTrue);
      case Err():
        fail('expected Ok');
    }
  });

  test('runs sends Authorization: Bearer when byokOpenRouterKey set',
      () async {
    adapter.onPost(
      '/v1/runs',
      (server) => server.reply(
        200,
        {'agent_instance_id': 'agent-1', 'smoke_ok': true},
      ),
      data: {
        'recipe_name': 'nullclaw',
        'model': 'anthropic/claude-haiku-4-5',
        'agent_name': 'spike-1',
      },
      headers: {
        'Authorization': 'Bearer sk-test',
        'content-type': Headers.jsonContentType,
      },
    );
    final r = await api.runs(
      body: const RunRequest(
        recipeName: 'nullclaw',
        model: 'anthropic/claude-haiku-4-5',
        agentName: 'spike-1',
      ),
      byokOpenRouterKey: 'sk-test',
    );
    switch (r) {
      case Ok(:final value):
        expect(value.agentInstanceId, 'agent-1');
        expect(value.smokeOk, isTrue);
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('start sends Authorization: Bearer when byokOpenRouterKey set',
      () async {
    adapter.onPost(
      '/v1/agents/agent-1/start',
      (server) => server.reply(
        200,
        {'container_id': 'ctr-1', 'status': 'running'},
      ),
      data: {'channel': 'inapp', 'channel_inputs': <String, dynamic>{}},
      headers: {
        'Authorization': 'Bearer sk-test',
        'content-type': Headers.jsonContentType,
      },
    );
    final r = await api.start(
      agentId: 'agent-1',
      byokOpenRouterKey: 'sk-test',
    );
    switch (r) {
      case Ok(:final value):
        expect(value.containerId, 'ctr-1');
        expect(value.status, 'running');
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('postMessage sends Idempotency-Key header (D-09 enforcement)',
      () async {
    adapter.onPost(
      '/v1/agents/agent-1/messages',
      (server) => server.reply(202, {
        'message_id': 'msg-99',
        'status': 'queued',
        'queued_at': '2026-05-02T00:00:00Z',
      }),
      data: {'content': 'hello'},
      headers: {
        'Idempotency-Key': 'idem-1',
        'content-type': Headers.jsonContentType,
      },
    );
    final r = await api.postMessage(
      agentId: 'agent-1',
      content: 'hello',
      idempotencyKey: 'idem-1',
    );
    switch (r) {
      case Ok(:final value):
        expect(value.messageId, 'msg-99');
        expect(value.status, 'queued');
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('messagesHistory rejects limit=0 without hitting dio', () async {
    // No adapter response wired — proves the early-return guard fires.
    final r = await api.messagesHistory(agentId: 'agent-1', limit: 0);
    switch (r) {
      case Err(:final error):
        expect(error.code, ErrorCode.invalidRequest);
        expect(error.param, 'limit');
      case Ok():
        fail('expected Err for limit=0');
    }
  });

  test('messagesHistory rejects limit=1001 without hitting dio', () async {
    final r = await api.messagesHistory(agentId: 'agent-1', limit: 1001);
    switch (r) {
      case Err(:final error):
        expect(error.code, ErrorCode.invalidRequest);
        expect(error.param, 'limit');
      case Ok():
        fail('expected Err for limit=1001');
    }
  });

  test('messagesHistory limit=200 hits backend', () async {
    adapter.onGet(
      '/v1/agents/agent-1/messages',
      (server) => server.reply(200, {'messages': <dynamic>[]}),
      queryParameters: {'limit': 200},
    );
    final r = await api.messagesHistory(agentId: 'agent-1');
    switch (r) {
      case Ok(:final value):
        expect(value.messages, isEmpty);
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('agentsList parses an empty array', () async {
    adapter.onGet('/v1/agents', (server) => server.reply(200, <dynamic>[]));
    final r = await api.agentsList();
    switch (r) {
      case Ok(:final value):
        expect(value, isEmpty);
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('models parses OpenRouter top-level array', () async {
    adapter.onGet(
      '/v1/models',
      (server) => server.reply(200, [
        {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
      ]),
    );
    final r = await api.models();
    switch (r) {
      case Ok(:final value):
        expect(value.length, 1);
        expect(value.first.id, 'anthropic/claude-haiku-4-5');
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('models parses OpenRouter {data: [...]} envelope', () async {
    adapter.onGet(
      '/v1/models',
      (server) => server.reply(200, {
        'data': [
          {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
        ],
      }),
    );
    final r = await api.models();
    switch (r) {
      case Ok(:final value):
        expect(value.length, 1);
      case Err():
        fail('expected Ok');
    }
  });

  test('stop POSTs with Bearer + returns Ok(null)', () async {
    var sawBearer = false;
    adapter.onPost(
      '/v1/agents/agent-1/stop',
      (server) => server.reply(200, {'ok': true}),
    );
    // Verify Bearer header is present on the outbound request.
    api.dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (opts, h) {
          if (opts.headers['Authorization'] == 'Bearer test-key') {
            sawBearer = true;
          }
          return h.next(opts);
        },
      ),
    );
    final r = await api.stop(agentId: 'agent-1', byokOpenRouterKey: 'test-key');
    expect(r, isA<Ok<void>>());
    expect(sawBearer, isTrue, reason: 'stop must send Authorization: Bearer');
  });

  test('400 with envelope surfaces ApiError with correct code', () async {
    adapter.onGet(
      '/healthz',
      (server) => server.reply(400, {
        'error': {
          'type': 'invalid_request',
          'code': 'INVALID_REQUEST',
          'message': 'bad',
          'request_id': 'r1',
        },
      }),
    );
    final r = await api.healthz();
    switch (r) {
      case Err(:final error):
        expect(error.code, ErrorCode.invalidRequest);
        expect(error.statusCode, 400);
        expect(error.requestId, 'r1');
      case Ok():
        fail('expected Err');
    }
  });
}
