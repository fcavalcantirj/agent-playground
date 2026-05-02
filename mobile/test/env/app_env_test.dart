// Phase 24 Plan 06 — AppEnv fail-loud boot validation (D-43).

import 'package:agent_playground/core/env/app_env.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppEnv.fromValue — D-43 fail-loud', () {
    test('parses http://localhost:8000', () {
      final env = AppEnv.fromValue('http://localhost:8000');
      expect(env.baseUrl.toString(), 'http://localhost:8000');
      expect(env.baseUrl.host, 'localhost');
      expect(env.baseUrl.port, 8000);
    });

    test('parses Android emulator http://10.0.2.2:8000', () {
      final env = AppEnv.fromValue('http://10.0.2.2:8000');
      expect(env.baseUrl.host, '10.0.2.2');
    });

    test('parses ngrok https URL', () {
      final env = AppEnv.fromValue('https://abc.ngrok-free.app');
      expect(env.baseUrl.scheme, 'https');
      expect(env.baseUrl.host, 'abc.ngrok-free.app');
    });

    test('empty throws StateError', () {
      expect(
        () => AppEnv.fromValue(''),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            startsWith('BASE_URL is empty'),
          ),
        ),
      );
    });

    test('non-URL throws StateError', () {
      expect(
        () => AppEnv.fromValue('not-a-url'),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('malformed'),
          ),
        ),
      );
    });

    test('non-http scheme throws StateError', () {
      expect(
        () => AppEnv.fromValue('ftp://example.com'),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('malformed'),
          ),
        ),
      );
    });
  });
}
