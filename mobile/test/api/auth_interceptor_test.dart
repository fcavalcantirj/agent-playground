// Phase 24 Plan 04 — AuthInterceptor + SecureStorage + AuthEventBus tests.
//
// These tests use a `_FakeBackend` standing in for `flutter_secure_storage`'s
// platform-channel-only plugin. The fake is NOT a service mock per Golden
// Rule #1 — `flutter test` runs in the Dart VM with no Keychain /
// EncryptedSharedPreferences. The integration spike (Plan 09) bypasses
// secure_storage entirely via `--dart-define SESSION_ID` (D-49); the
// production path is exercised on a real device by Phase 25 work.

import 'dart:async';
import 'package:agent_playground/core/api/auth_interceptor.dart';
import 'package:agent_playground/core/api/log_interceptor.dart';
import 'package:agent_playground/core/auth/auth_event_bus.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeBackend implements FlutterSecureStorage {
  final Map<String, String> _store = {};

  @override
  Future<String?> read({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      _store[key];

  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      _store.remove(key);
    } else {
      _store[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    _store.remove(key);
  }

  // Any other FlutterSecureStorage method that drifts into use must fail
  // loud — SecureStorage only calls read/write/delete.
  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError(
        'fake backend: ${invocation.memberName} not implemented',
      );
}

class _CapturingHandler extends RequestInterceptorHandler {
  RequestOptions? captured;
  @override
  void next(RequestOptions options) {
    captured = options;
  }
}

class _CapturingErrorHandler extends ErrorInterceptorHandler {
  DioException? captured;
  @override
  void next(DioException err) {
    captured = err;
  }
}

void main() {
  group('SecureStorage', () {
    test('caches after first read', () async {
      final backend = _FakeBackend();
      await backend.write(key: 'session_id', value: 'abc-123');
      final storage = SecureStorage(backend);
      expect(await storage.readSessionId(), 'abc-123');
      // Mutate underlying store; cached read should not see it.
      await backend.write(key: 'session_id', value: 'xyz-999');
      expect(await storage.readSessionId(), 'abc-123');
    });

    test('clearSessionId invalidates cache', () async {
      final backend = _FakeBackend();
      await backend.write(key: 'session_id', value: 'abc-123');
      final storage = SecureStorage(backend);
      await storage.readSessionId(); // hydrate cache
      await storage.clearSessionId();
      expect(await storage.readSessionId(), isNull);
    });

    test('writeSessionId updates cache + backend', () async {
      final backend = _FakeBackend();
      final storage = SecureStorage(backend);
      await storage.writeSessionId('new-uuid');
      expect(await storage.readSessionId(), 'new-uuid');
      expect(await backend.read(key: 'session_id'), 'new-uuid');
    });
  });

  group('AuthInterceptor', () {
    test('injects Cookie: ap_session=<uuid> when session present', () async {
      final backend = _FakeBackend();
      await backend.write(key: 'session_id', value: 'aaa-bbb-ccc');
      final storage = SecureStorage(backend);
      final bus = AuthEventBus();
      final interceptor = AuthInterceptor(storage, bus);

      final opts = RequestOptions(path: '/healthz');
      final handler = _CapturingHandler();
      await interceptor.onRequest(opts, handler);

      expect(handler.captured!.headers['Cookie'], 'ap_session=aaa-bbb-ccc');
      await bus.dispose();
    });

    test('does NOT inject Cookie when session absent', () async {
      final storage = SecureStorage(_FakeBackend());
      final bus = AuthEventBus();
      final interceptor = AuthInterceptor(storage, bus);

      final opts = RequestOptions(path: '/healthz');
      final handler = _CapturingHandler();
      await interceptor.onRequest(opts, handler);

      expect(handler.captured!.headers.containsKey('Cookie'), isFalse);
      await bus.dispose();
    });

    test('on 401 WITH cookie clears stored session AND emits AuthRequired',
        () async {
      final backend = _FakeBackend();
      await backend.write(key: 'session_id', value: 'will-be-cleared');
      final storage = SecureStorage(backend);
      final bus = AuthEventBus();
      final emitted = Completer<AuthRequired>();
      final sub = bus.events.listen(emitted.complete);
      final interceptor = AuthInterceptor(storage, bus);

      final reqOpts = RequestOptions(
        path: '/v1/users/me',
        headers: <String, dynamic>{'Cookie': 'ap_session=will-be-cleared'},
      );
      final err = DioException(
        requestOptions: reqOpts,
        response: Response<dynamic>(
          requestOptions: reqOpts,
          statusCode: 401,
        ),
        type: DioExceptionType.badResponse,
      );
      final handler = _CapturingErrorHandler();
      await interceptor.onError(err, handler);

      expect(handler.captured, same(err));
      expect(
        await emitted.future.timeout(const Duration(seconds: 1)),
        isA<AuthRequired>(),
      );
      expect(await storage.readSessionId(), isNull);
      await sub.cancel();
      await bus.dispose();
    });

    // RED test — reproduces the Android prod bug observed 2026-05-11:
    // The AppBar's usage ticker polls /v1/usage/summary on the login screen.
    // An in-flight pre-auth ticker request (no Cookie header) returns 401
    // AFTER the user has just signed in and the session_id was written.
    // The old onError unconditionally cleared session_id on any 401 — wiping
    // the just-minted session and bouncing the user back to login.
    // Fix: only clear/emit when WE actually attached a Cookie. A 401 on a
    // request that didn't carry a session is "you weren't logged in", not
    // "your session got invalidated".
    test(
      'on 401 WITHOUT cookie leaves storage untouched + does NOT emit',
      () async {
        final backend = _FakeBackend();
        await backend.write(key: 'session_id', value: 'fresh-session');
        final storage = SecureStorage(backend);
        final bus = AuthEventBus();
        final events = <AuthRequired>[];
        final sub = bus.events.listen(events.add);
        final interceptor = AuthInterceptor(storage, bus);

        // Simulates an in-flight pre-auth request whose response lands
        // after a fresh login completed: no Cookie was attached at send
        // time, but session_id is now populated in storage.
        final reqOpts = RequestOptions(path: '/v1/usage/summary');
        final err = DioException(
          requestOptions: reqOpts,
          response: Response<dynamic>(
            requestOptions: reqOpts,
            statusCode: 401,
          ),
          type: DioExceptionType.badResponse,
        );
        final handler = _CapturingErrorHandler();
        await interceptor.onError(err, handler);

        // Drain microtasks.
        await Future<void>.delayed(const Duration(milliseconds: 10));
        expect(events, isEmpty, reason: 'must not emit AuthRequired');
        expect(
          await storage.readSessionId(),
          'fresh-session',
          reason: 'just-minted session_id must survive a cookieless 401',
        );
        await sub.cancel();
        await bus.dispose();
      },
    );

    test('on non-401 errors leaves storage + bus untouched', () async {
      final backend = _FakeBackend();
      await backend.write(key: 'session_id', value: 'kept');
      final storage = SecureStorage(backend);
      final bus = AuthEventBus();
      final events = <AuthRequired>[];
      final sub = bus.events.listen(events.add);
      final interceptor = AuthInterceptor(storage, bus);

      final err = DioException(
        requestOptions: RequestOptions(path: '/v1/runs'),
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/v1/runs'),
          statusCode: 500,
        ),
        type: DioExceptionType.badResponse,
      );
      final handler = _CapturingErrorHandler();
      await interceptor.onError(err, handler);

      // Drain microtasks
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(events, isEmpty);
      expect(await storage.readSessionId(), 'kept');
      await sub.cancel();
      await bus.dispose();
    });
  });

  group('redactHeader', () {
    test('null becomes <empty>', () {
      expect(redactHeader(null), '<empty>');
    });

    test('empty string becomes <empty>', () {
      expect(redactHeader(''), '<empty>');
    });

    test('short value becomes <short>', () {
      expect(redactHeader('abc'), '<short>');
      expect(redactHeader('12345678'), '<short>');
    });

    test('long value truncated to last 8 chars', () {
      expect(
        redactHeader('ap_session=aaaaaaaa-bbbb-cccc-dddd-12345678'),
        '...12345678',
      );
      expect(
        redactHeader('Bearer sk-abcdefghijklmnopqrstuvwxyz12345678'),
        '...12345678',
      );
    });
  });
}
