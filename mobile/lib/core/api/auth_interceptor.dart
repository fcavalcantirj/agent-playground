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
      // Only clear/emit if WE actually attached a session cookie to this
      // request. A 401 on a never-authenticated request means "you weren't
      // logged in" — not "your session got invalidated".
      //
      // Race fixed (2026-05-11, Android prod):
      //   1. AppBar usage ticker polls /v1/usage/summary while the user is
      //      on the login screen (anonymous; no Cookie attached). Server
      //      returns 401.
      //   2. User taps Google sign-in. AuthService writes session_id.
      //   3. The in-flight ticker request from step 1 lands AFTER step 2's
      //      write completes. Old code unconditionally cleared session_id
      //      on that stale 401, wiping the just-minted session and bouncing
      //      the user back to login.
      // Empirically confirmed via prod log probe + reproduced by the
      // `'on 401 WITHOUT cookie ...'` unit test.
      final cookie = err.requestOptions.headers['Cookie'];
      final sentSession = cookie is String && cookie.contains('ap_session=');
      if (sentSession) {
        await _storage.clearSessionId();
        _authEvents.emit();
      }
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
}
