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
    if (err.response?.statusCode == 401 && _isSessionAuthFailure(err)) {
      await _storage.clearSessionId();
      // Phase 26: forward the SESSION_REVOKED reason (if present) so the
      // login screen can render the "session ended elsewhere" banner
      // instead of the generic "Signed out" copy.
      _authEvents.emit(reason: _extractRevocationReason(err));
    }
    handler.next(err);
  }

  /// A 401 response means "auth failed", but auth on this API has TWO
  /// independent gates per Phase 23 D-22 / Phase 25 Wave 5:
  ///
  ///   * Session cookie (`ap_session`) — the user's identity. A 401 here
  ///     means the session is invalid / expired → log out.
  ///   * Bearer token (`Authorization: Bearer <byok>`) — the per-request
  ///     LLM provider key on `/v1/runs` and `/start`. A 401 here means
  ///     the BYOK key is empty / malformed — the user is still signed
  ///     in; clearing the session would force a needless re-login.
  ///
  /// Backend returns the failing field in `error.param`. Distinguish:
  ///
  ///   - `param == "ap_session"` → session failure → log out.
  ///   - `param == "Authorization"` → BYOK failure → keep session.
  ///   - other / missing → conservative; treat as session failure
  ///     (matches the prior unconditional behavior on routes that
  ///     don't carry a BYOK Bearer at all).
  bool _isSessionAuthFailure(DioException err) {
    final data = err.response?.data;
    if (data is! Map<String, dynamic>) return true;
    final error = data['error'];
    if (error is! Map<String, dynamic>) return true;
    final param = error['param'] as String?;
    return param != 'Authorization';
  }

  /// Phase 26: extract the revocation reason from the response body so the
  /// login screen can branch its banner copy. Returns ``'session_revoked'``
  /// when the api_server returned ``error.code == 'SESSION_REVOKED'``;
  /// ``null`` for any other 401 shape (generic UNAUTHORIZED / malformed
  /// body / no body at all).
  String? _extractRevocationReason(DioException err) {
    final data = err.response?.data;
    if (data is! Map<String, dynamic>) return null;
    final error = data['error'];
    if (error is! Map<String, dynamic>) return null;
    return error['code'] == 'SESSION_REVOKED' ? 'session_revoked' : null;
  }
}
