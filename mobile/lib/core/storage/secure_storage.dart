// Phase 24 Plan 04 — flutter_secure_storage wrapper for session_id (D-35).
//
// The cached value avoids hitting the platform channel on every dio
// request (RESEARCH Anti-Pattern line 843). Re-read happens only after
// a clearSessionId() call (or after process death — the cache is
// process-scoped). The constructor accepts an optional `backend`
// override so unit tests can inject a fake without touching Keychain
// / EncryptedSharedPreferences (which are unavailable in `flutter
// test`).

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  SecureStorage([FlutterSecureStorage? backend])
      : _backend = backend ?? const FlutterSecureStorage();

  static const String _kSessionId = 'session_id';

  final FlutterSecureStorage _backend;
  String? _cached;
  bool _hydrated = false;

  Future<String?> readSessionId() async {
    if (_hydrated) return _cached;
    _cached = await _backend.read(key: _kSessionId);
    _hydrated = true;
    return _cached;
  }

  Future<void> writeSessionId(String id) async {
    await _backend.write(key: _kSessionId, value: id);
    _cached = id;
    _hydrated = true;
  }

  Future<void> clearSessionId() async {
    await _backend.delete(key: _kSessionId);
    _cached = null;
    _hydrated = true;
  }
}
