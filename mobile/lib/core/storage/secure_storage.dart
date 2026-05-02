// Phase 24 Plan 06 — CROSS-WAVE SHIM for Plan 24-04's SecureStorage.
//
// Plan 24-04 owns this file's final implementation (RED tests at
// mobile/test/api/auth_interceptor_test.dart on the parallel worktree).
// This shim exists ONLY so Plan 24-06's providers tree + HealthzScreen
// compile + boot through the real route. When Plan 24-04 lands, its feat
// commit replaces this file at the wave-merge.
//
// The constructor + method names mirror the contract Plan 24-04's RED tests
// declared (`SecureStorage(FlutterSecureStorage backend)`,
// `readSessionId()`, `writeSessionId()`, `clearSessionId()`) so the shim
// surface and the final surface stay in lockstep.

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  SecureStorage([FlutterSecureStorage? backend])
      : _backend = backend ?? const FlutterSecureStorage();

  static const String _sessionKey = 'session_id';

  final FlutterSecureStorage _backend;
  String? _cached;
  bool _hydrated = false;

  Future<String?> readSessionId() async {
    if (!_hydrated) {
      _cached = await _backend.read(key: _sessionKey);
      _hydrated = true;
    }
    return _cached;
  }

  Future<void> writeSessionId(String value) async {
    await _backend.write(key: _sessionKey, value: value);
    _cached = value;
    _hydrated = true;
  }

  Future<void> clearSessionId() async {
    await _backend.delete(key: _sessionKey);
    _cached = null;
    _hydrated = true;
  }
}
