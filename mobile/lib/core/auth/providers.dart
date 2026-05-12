// Phase 25 Wave 1 — Auth-related Riverpod providers.
//
// Hand-written `Provider`s (mirrors `core/api/providers.dart` shape; the
// riverpod_generator is allowed by Phase 24 D-34 but adds a build_runner
// pass — for a single 3-line provider it is not worth the codegen step).
//
// `authServiceProvider` returns the real impl by default; tests override
// with `authServiceProvider.overrideWithValue(fakeImpl)`. Wave 5 spike
// overrides with `AuthServiceTestSeam(...)` driven by --dart-define
// SESSION_ID per D-66.

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/auth_service_real.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const String _kGoogleIosClientId =
    String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
const String _kGoogleServerClientId =
    String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');
const String _kGithubClientId = String.fromEnvironment('GITHUB_CLIENT_ID');

final authServiceProvider = Provider<AuthService>(
  (ref) => AuthServiceReal(
    apiClient: ref.watch(apiClientProvider),
    storage: ref.watch(secureStorageProvider),
    googleIosClientId: _kGoogleIosClientId.isEmpty ? null : _kGoogleIosClientId,
    googleServerClientId:
        _kGoogleServerClientId.isEmpty ? null : _kGoogleServerClientId,
    githubClientId: _kGithubClientId.isEmpty ? null : _kGithubClientId,
  ),
);

/// Exposed for the Android webview-driven GitHub OAuth path
/// (`LoginScreen` → `GithubOAuthWebViewScreen`). Mirrors the same
/// `--dart-define GITHUB_CLIENT_ID=...` value `authServiceProvider`
/// already consumes.
final githubClientIdProvider = Provider<String?>(
  (ref) => _kGithubClientId.isEmpty ? null : _kGithubClientId,
);
