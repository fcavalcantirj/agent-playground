// Phase 25 Wave 1 D-66 — AuthService seam.
//
// Real impl uses google_sign_in 7.x + flutter_appauth 12.x (cannot be
// driven by WidgetTester). Test impl reads SESSION_ID via --dart-define
// (mirrors Phase 24 D-49 spike pattern). Riverpod overrides swap impls.
//
// Wave 0 Spike A PASS (2026-05-03) — iOS Simulator id_token round-trip
// confirmed; the production iOS path no longer depends on the test seam,
// but the seam still ships for unit-test parallelization.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';

abstract interface class AuthService {
  Future<Result<SessionUser>> signInWithGoogle();
  Future<Result<SessionUser>> signInWithGithub();

  /// Exchange a GitHub authorization code for a session, then persist
  /// the session_id. Used when the OAuth dance is driven outside this
  /// service (e.g. by `GithubOAuthWebViewScreen` on Android, where the
  /// Chrome-Custom-Tab → `solvrlabs://` dispatch is unreliable).
  Future<Result<SessionUser>> signInWithGithubCode({
    required String code,
    required String codeVerifier,
  });

  Future<void> signOut();
}
