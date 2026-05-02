// Phase 24 Plan 04 — dio Interceptor for cookie injection + 401 handler (D-35).
//
// Cookie wire format mirrors the backend constant in
// api_server/src/api_server/middleware/session.py:37
// (`SESSION_COOKIE_NAME = "ap_session"`). The interceptor:
//
//   * onRequest: when SecureStorage has a session_id, set
//     `Cookie: ap_session=<uuid>`. The cache inside SecureStorage means
//     this is a synchronous in-memory read after the first hit.
//   * onError: on a 401, clear the stored session AND emit
//     [AuthRequired] on the bus. clearSessionId() runs BEFORE
//     emit() so a Phase-25 listener observing the bus can never
//     witness a stale session_id still in storage (T-24-04-03).
//
// The interceptor never swallows the error: handler.next(err) is always
// called so the typed-client layer can return Result.err(...) up to
// the caller.

import 'package:agent_playground/core/auth/auth_event_bus.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:dio/dio.dart';

class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage, this._authEvents);

  final SecureStorage _storage;
  final AuthEventBus _authEvents;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final sessionId = await _storage.readSessionId();
    if (sessionId != null && sessionId.isNotEmpty) {
      options.headers['Cookie'] = 'ap_session=$sessionId';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      await _storage.clearSessionId();
      _authEvents.emit();
    }
    handler.next(err);
  }
}
