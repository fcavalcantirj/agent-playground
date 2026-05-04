// Phase 25 Wave 1 D-66 test impl.
//
// Reads --dart-define SESSION_ID; writes via secureStorage; returns a
// synthesized SessionUser. Used by Wave 5 spike + widget tests so the
// native sheet is never touched in CI/automated runs. Mirrors Phase 24
// D-49 spike pattern.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';

class AuthServiceTestSeam implements AuthService {
  AuthServiceTestSeam({required this.storage, required this.sessionId});

  final SecureStorage storage;
  final String sessionId;

  @override
  Future<Result<SessionUser>> signInWithGoogle() => _stash('google');

  @override
  Future<Result<SessionUser>> signInWithGithub() => _stash('github');

  Future<Result<SessionUser>> _stash(String provider) async {
    await storage.writeSessionId(sessionId);
    return Result.ok(
      SessionUser(
        id: 'test-seam-$provider',
        email: 'spike@test',
        displayName: 'Spike',
        provider: provider,
        createdAt: DateTime.now().toUtc().toIso8601String(),
      ),
    );
  }

  @override
  Future<void> signOut() async {
    await storage.clearSessionId();
    // BYOK keys NOT cleared per D-25/D-33.
  }

  @override
  Future<Result<int>> signOutEverywhere() async {
    // Test seam — no real backend call. The integration test that drives
    // logout-all should override authServiceProvider with a custom seam
    // OR mock the api directly. Returning a stable Result.ok(0) keeps
    // unit tests deterministic.
    await storage.clearSessionId();
    return const Result.ok(0);
  }
}
