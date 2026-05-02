// Phase 24 Plan 06 — CROSS-WAVE SHIM for Plan 24-04's AuthInterceptor.
//
// Plan 24-04 owns this file's final implementation (RED tests at
// mobile/test/api/auth_interceptor_test.dart on the parallel worktree
// already specify the contract). This shim exists ONLY so Plan 24-06's
// providers tree compiles + the placeholder /healthz call boots through
// a real Dio. When 24-04 lands its feat commit, this file is replaced at
// the wave-merge.
//
// Contract (mirrors Plan 24-04 RED tests):
//   - constructor(SecureStorage, AuthEventBus)
//   - onRequest: inject `Cookie: ap_session=<uuid>` if session present
//   - onError: on 401 → clear stored session + emit AuthRequired

import 'package:agent_playground/core/auth/auth_event_bus.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:dio/dio.dart';

class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage, this._bus);

  final SecureStorage _storage;
  final AuthEventBus _bus;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final sid = await _storage.readSessionId();
    if (sid != null && sid.isNotEmpty) {
      options.headers['Cookie'] = 'ap_session=$sid';
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
      _bus.emit();
    }
    handler.next(err);
  }
}
