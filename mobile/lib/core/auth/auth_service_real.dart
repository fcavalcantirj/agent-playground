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
import 'package:agent_playground/features/login/github_oauth_webview_screen.dart'
    show generatePkceVerifier, pkceChallengeFor, generateOAuthState;
import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
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
    // 2026-05-12 — Reverted to custom scheme for the morning hand-off. The
    // HTTPS App Link path (full server-side assetlinks.json deployed, Android
    // verifies the SHA-256) hits a HyperOS-specific task-isolation bug:
    // RedirectUriReceiverActivity fires in a NEW task per
    // FLAG_ACTIVITY_NEW_TASK on verified link intents → flutter_appauth's
    // same-task PendingIntent coordination fails → User cancelled flow
    // BEFORE Chrome opens. Custom scheme at least gets Chrome to open and
    // shows the authorize page; the last-leg redirect dispatch is still
    // flaky on HyperOS but we're back at the prior known state, not worse.
    // Pick this up by either (a) migrating to flutter_web_auth_2, or (b)
    // moving the App Link intent filter to MainActivity + handling in
    // onNewIntent + forwarding via MethodChannel.
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
    // 2026-05-12 — flutter_web_auth_2 instead of flutter_appauth.
    // flutter_appauth's PendingIntent same-task assumption breaks on
    // HyperOS where the redirect intent always lands in a new task
    // (FLAG_ACTIVITY_NEW_TASK). flutter_web_auth_2 uses a much simpler
    // CallbackActivity model — caller blocks on authenticate(), the
    // callback activity captures the URL via intent, Dart resumes with
    // the full callback string. No same-task coordination required.
    // PKCE handled client-side (helpers in github_oauth_webview_screen).
    final clientId = githubClientId ?? '';
    if (clientId.isEmpty) {
      return const Result.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'github client_id missing',
        ),
      );
    }
    final codeVerifier = generatePkceVerifier();
    final codeChallenge = pkceChallengeFor(codeVerifier);
    final state = generateOAuthState();
    final authorizeUrl = Uri.parse(githubAuthEndpoint).replace(
      queryParameters: <String, String>{
        'client_id': clientId,
        'redirect_uri': githubRedirectUrl,
        'scope': 'read:user user:email',
        'state': state,
        'response_type': 'code',
        'code_challenge': codeChallenge,
        'code_challenge_method': 'S256',
      },
    );

    try {
      final callback = await FlutterWebAuth2.authenticate(
        url: authorizeUrl.toString(),
        callbackUrlScheme: 'solvrlabs',
      );
      final callbackUri = Uri.parse(callback);
      final code = callbackUri.queryParameters['code'];
      final returnedState = callbackUri.queryParameters['state'];
      if (code == null || code.isEmpty) {
        return const Result.err(
          ApiError(
            code: ErrorCode.unknownServer,
            message: 'no authorization code from GitHub',
          ),
        );
      }
      if (returnedState != state) {
        return const Result.err(
          ApiError(
            code: ErrorCode.unknownServer,
            message: 'github state mismatch (csrf protection)',
          ),
        );
      }
      return _exchangeGithubCode(code: code, codeVerifier: codeVerifier);
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
