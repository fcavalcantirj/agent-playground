// Phase 25 Wave 1 — main.dart cold-start logic tests (D-01..D-02).
//
// `resolveInitialRoute(ApiClient)` is a small extracted function that
// mirrors the boot-time switch in main.dart. We exercise it against an
// http_mock_adapter-driven Dio so the test stays pure (no platform
// channel, no flutter_secure_storage hot-path).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/api_endpoints.dart';
import 'package:agent_playground/core/boot/resolve_initial_route.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('resolveInitialRoute', () {
    late Dio dio;
    late DioAdapter adapter;
    late ApiClient client;

    setUp(() {
      dio = Dio(BaseOptions(baseUrl: 'http://test.invalid'));
      adapter = DioAdapter(dio: dio);
      client = ApiClient(dio);
    });

    test('200 → /dashboard', () async {
      adapter.onGet(
        ApiEndpoints.usersMe,
        (server) => server.reply(200, {
          'id': 'u1',
          'email': 'a@b',
          'display_name': 'A',
          'provider': 'google',
          'created_at': '2026-05-03T00:00:00Z',
        }),
      );
      expect(await resolveInitialRoute(client), '/dashboard');
    });

    test('401 → /login', () async {
      adapter.onGet(
        ApiEndpoints.usersMe,
        (server) => server.reply(401, {
          'error': {
            'type': 'unauthorized',
            'code': 'UNAUTHORIZED',
            'message': 'no session',
          },
        }),
      );
      expect(await resolveInitialRoute(client), '/login');
    });

    test('500 → /retry-bootstrap', () async {
      adapter.onGet(
        ApiEndpoints.usersMe,
        (server) => server.reply(500, {
          'error': {
            'type': 'internal',
            'code': 'INTERNAL',
            'message': 'boom',
          },
        }),
      );
      expect(await resolveInitialRoute(client), '/retry-bootstrap');
    });

    test('connection error → /retry-bootstrap', () async {
      adapter.onGet(
        ApiEndpoints.usersMe,
        (server) => server.throws(
          0,
          DioException.connectionError(
            requestOptions: RequestOptions(path: ApiEndpoints.usersMe),
            reason: 'unreachable',
          ),
        ),
      );
      expect(await resolveInitialRoute(client), '/retry-bootstrap');
    });
  });
}
