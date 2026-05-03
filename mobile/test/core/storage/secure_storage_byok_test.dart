// Phase 25 Wave 1 — D-25 + D-33 BYOK key persistence tests.
//
// Critical invariant: writeByokKey/readByokKey round-trip; clearSessionId()
// MUST NOT clear byok_key_<provider> entries (logout-does-not-clear-BYOK).
//
// Uses `FlutterSecureStorage.setMockInitialValues` (a `@visibleForTesting`
// helper that swaps in an in-memory `TestFlutterSecureStoragePlatform`)
// so the test does not need a platform channel.

import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('writeByokKey + readByokKey round-trips the value', () async {
    final s = SecureStorage();
    await s.writeByokKey('openrouter', 'sk-or-key');
    expect(await s.readByokKey('openrouter'), 'sk-or-key');
  });

  test('readByokKey for an unset provider returns null', () async {
    final s = SecureStorage();
    expect(await s.readByokKey('anthropic'), isNull);
  });

  test('clearSessionId does NOT clear byok_key_* entries (D-25/D-33)',
      () async {
    final s = SecureStorage();
    await s.writeSessionId('abc');
    await s.writeByokKey('openrouter', 'sk-or-key');
    await s.clearSessionId();
    expect(await s.readSessionId(), isNull);
    expect(
      await s.readByokKey('openrouter'),
      'sk-or-key',
      reason: 'BYOK keys must survive logout per D-25/D-33',
    );
  });

  test('clearByokKey removes the entry', () async {
    final s = SecureStorage();
    await s.writeByokKey('openrouter', 'sk-or-key');
    await s.clearByokKey('openrouter');
    expect(await s.readByokKey('openrouter'), isNull);
  });
}
