// Phase 25 Wave 1 — D-66 AuthService test-seam contract tests.
//
// AuthServiceTestSeam reads `String.fromEnvironment('SESSION_ID')` and
// stashes it via SecureStorage, never touching the native OAuth sheet.
// Used by Wave 5 spike + widget tests so CI stays deterministic.
// D-25 invariant: signOut clears session_id, NOT byok_key_<provider>.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service_test_seam.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('signInWithGoogle stashes session_id and returns Ok provider=google',
      () async {
    final storage = SecureStorage();
    final svc = AuthServiceTestSeam(storage: storage, sessionId: 'abc');
    final r = await svc.signInWithGoogle();
    expect(r, isA<Ok<SessionUser>>());
    expect((r as Ok<SessionUser>).value.provider, 'google');
    expect(await storage.readSessionId(), 'abc');
  });

  test('signInWithGithub stashes session_id and returns Ok provider=github',
      () async {
    final storage = SecureStorage();
    final svc = AuthServiceTestSeam(storage: storage, sessionId: 'gh-sess');
    final r = await svc.signInWithGithub();
    expect(r, isA<Ok<SessionUser>>());
    expect((r as Ok<SessionUser>).value.provider, 'github');
    expect(await storage.readSessionId(), 'gh-sess');
  });

  test('signOut clears session_id but leaves byok_key_<provider> intact',
      () async {
    final storage = SecureStorage();
    await storage.writeByokKey('openrouter', 'sk-or-key');
    final svc = AuthServiceTestSeam(storage: storage, sessionId: 'abc');
    await svc.signInWithGoogle();
    expect(await storage.readSessionId(), 'abc');
    await svc.signOut();
    expect(await storage.readSessionId(), isNull);
    expect(
      await storage.readByokKey('openrouter'),
      'sk-or-key',
      reason: 'BYOK keys must survive sign-out per D-25',
    );
  });
}
