// Phase 25 Wave 1 D-66 — AuthService seam.
//
// Real impl uses google_sign_in 7.x + flutter_appauth 12.x +
// flutter_web_auth_2 5.x + sign_in_with_apple 6.x. Test impl reads
// SESSION_ID via --dart-define. Riverpod overrides swap impls.

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

  /// 2026-05-12 — Sign in with Apple. iOS only; on Android the login
  /// screen does not render the Apple button.
  Future<Result<SessionUser>> signInWithApple();

  /// 2026-05-12 — magic-link OTP: request the code be sent to `email`.
  /// On success, the response payload contains a cooldown the UI uses
  /// to gate the "resend" button.
  Future<Result<int>> requestEmailCode({required String email});

  /// 2026-05-12 — magic-link OTP: verify the 6-digit `code` for `email`,
  /// mint a session, persist session_id.
  Future<Result<SessionUser>> verifyEmailCode({
    required String email,
    required String code,
  });

  Future<void> signOut();
}
