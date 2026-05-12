// Phase 25 Wave 1 D-66 real impl.
//
// google_sign_in 7.x (Pitfall #3): GoogleSignIn.instance.initialize() +
// attemptLightweightAuthentication() ?? authenticate(). Auth + authz are
// now separate steps — for OIDC we only need authentication's idToken.
// Wave 0 Spike A confirmed iOS path produces a non-null id_token
// (spikes/flutter-google-signin-7x.md verdict: PASS).
//
// flutter_appauth 12.x (Pitfall #4): Phase 24 D-15 already shipped the
// solvrlabs://oauth/github URL scheme registration on both iOS+Android.
//
// Client IDs come in via constructor so they can be injected from
// `--dart-define GOOGLE_IOS_CLIENT_ID=... GOOGLE_SERVER_CLIENT_ID=...
// GITHUB_CLIENT_ID=...` (see core/auth/providers.dart).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:google_sign_in/google_sign_in.dart';

class AuthServiceReal implements AuthService {
  AuthServiceReal({
    required this.apiClient,
    required this.storage,
    this.googleIosClientId,
    this.googleServerClientId,
    this.githubClientId,
    this.githubAuthEndpoint = 'https://github.com/login/oauth/authorize',
    this.githubTokenEndpoint = 'https://github.com/login/oauth/access_token',
    this.githubRedirectUrl = 'solvrlabs://oauth/github',
    FlutterAppAuth? appAuth,
  }) : _appAuth = appAuth ?? const FlutterAppAuth();

  final ApiClient apiClient;
  final SecureStorage storage;
  final String? googleIosClientId;
  final String? googleServerClientId;
  final String? githubClientId;
  final String githubAuthEndpoint;
  final String githubTokenEndpoint;
  final String githubRedirectUrl;
  final FlutterAppAuth _appAuth;

  bool _googleInitialized = false;

  Future<void> _ensureGoogleInit() async {
    if (_googleInitialized) return;
    await GoogleSignIn.instance.initialize(
      clientId: (googleIosClientId?.isEmpty ?? true) ? null : googleIosClientId,
      serverClientId: (googleServerClientId?.isEmpty ?? true)
          ? null
          : googleServerClientId,
    );
    _googleInitialized = true;
  }

  @override
  Future<Result<SessionUser>> signInWithGoogle() async {
    try {
      await _ensureGoogleInit();
      final account =
          await GoogleSignIn.instance.attemptLightweightAuthentication() ??
              await GoogleSignIn.instance.authenticate();
      final idToken = account.authentication.idToken;
      if (idToken == null) {
        return const Result.err(
          ApiError(
            code: ErrorCode.unknownServer,
            message: 'no id_token from Google',
          ),
        );
      }
      // Mobile auth has no cookie jar — backend returns
      // {session_id, user} in the body (Phase 23 D-23). Persist
      // session_id so AuthInterceptor can attach it as Cookie on
      // subsequent calls.
      final res = await apiClient.authGoogleMobile(idToken: idToken);
      if (res case Err(:final error)) {
        return Result<SessionUser>.err(error);
      }
      final ok = (res as Ok<MobileAuthResponse>).value;
      await storage.writeSessionId(ok.sessionId);
      return Result<SessionUser>.ok(ok.user);
    } on GoogleSignInException catch (e) {
      return Result.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'google sign-in failed: ${e.code.name}',
        ),
      );
    } on Exception catch (e) {
      return Result.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'google sign-in failed: $e',
        ),
      );
    }
  }

  @override
  Future<Result<SessionUser>> signInWithGithub() async {
    try {
      // Phase 25 Wave 5 (production-safe): client_secret-free flow.
      // authorize() returns the authorization code only; backend
      // exchanges with its stored secret (so it never lives on device).
      // This also sidesteps AppAuth-iOS's JSON-only token-response
      // parser hitting GitHub's default x-www-form-urlencoded body.
      final result = await _appAuth.authorize(
        AuthorizationRequest(
          githubClientId ?? '',
          githubRedirectUrl,
          serviceConfiguration: AuthorizationServiceConfiguration(
            authorizationEndpoint: githubAuthEndpoint,
            tokenEndpoint: githubTokenEndpoint,
          ),
          scopes: const ['read:user', 'user:email'],
        ),
      );
      final code = result.authorizationCode;
      if (code == null) {
        return const Result.err(
          ApiError(
            code: ErrorCode.unknownServer,
            message: 'no authorization code from GitHub',
          ),
        );
      }
      // flutter_appauth.authorize() generates a PKCE code_verifier and
      // sends its challenge to the authorize endpoint; the exchange
      // step at /login/oauth/access_token MUST include the same
      // verifier or GitHub returns invalid_grant.
      return _exchangeGithubCode(code: code, codeVerifier: result.codeVerifier);
    } on Exception catch (e) {
      return Result.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'github auth failed: $e',
        ),
      );
    }
  }

  @override
  Future<Result<SessionUser>> signInWithGithubCode({
    required String code,
    required String codeVerifier,
  }) async {
    // Caller (e.g. GithubOAuthWebViewScreen on Android) has already
    // driven the GitHub authorize step and captured {code, verifier};
    // we just exchange + persist.
    try {
      return await _exchangeGithubCode(code: code, codeVerifier: codeVerifier);
    } on Exception catch (e) {
      return Result.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'github auth failed: $e',
        ),
      );
    }
  }

  Future<Result<SessionUser>> _exchangeGithubCode({
    required String code,
    required String? codeVerifier,
  }) async {
    final res = await apiClient.authGithubMobile(
      code: code,
      redirectUri: githubRedirectUrl,
      codeVerifier: codeVerifier,
    );
    if (res case Err(:final error)) {
      return Result<SessionUser>.err(error);
    }
    final ok = (res as Ok<MobileAuthResponse>).value;
    await storage.writeSessionId(ok.sessionId);
    return Result<SessionUser>.ok(ok.user);
  }

  @override
  Future<void> signOut() async {
    try {
      await GoogleSignIn.instance.signOut();
    } on Object catch (_) {
      // Silent best-effort — google sign-out failure must not block
      // session_id wipe; user has already chosen to leave.
    }
    await storage.clearSessionId();
    // BYOK keys NOT cleared — D-25/D-33.
  }
}
