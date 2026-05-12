// 2026-05-11 — GitHub OAuth via in-app webview (sidesteps Chrome
// Custom Tab → `solvrlabs://` intent failure on Android prod).
//
// flutter_appauth uses Chrome Custom Tab on Android. When GitHub's
// "Reauthorization required" interstitial (rate-limited high-volume
// client_id) POSTs the grant, the redirect to `solvrlabs://oauth/github`
// goes through GitHub's intermediate "Authorizing…" page (JS / meta-refresh)
// and Chrome's external-intent tightening silently drops the launch:
// AppAuth's authorize() Future never resolves, UI hangs forever.
//
// Empirically observed in prod on 2026-05-11. Desktop incognito with the
// same `client_id` + `redirect_uri` succeeded server-side (tab title
// "OAuth application authorized") — proving the GitHub side is healthy
// and the failure is the Chrome-Custom-Tab → custom-scheme dispatch.
//
// This screen runs the OAuth dance inside `flutter_inappwebview`
// instead — same pattern as CheckoutWebViewScreen for Stripe Checkout
// (D-19/D-20/D-21). The webview's `shouldOverrideUrlLoading` sees
// EVERY navigation request including the redirect to `solvrlabs://`,
// so we never need Android's intent system to dispatch a thing.
//
// Server-side `/v1/auth/github/mobile` contract is unchanged: it still
// takes {code, redirect_uri, code_verifier} and exchanges with GitHub.

import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

/// Output of a completed (or cancelled) flow.
class GithubOAuthResult {
  const GithubOAuthResult({this.code, this.codeVerifier, this.error});
  final String? code;
  final String? codeVerifier;
  final String? error;

  bool get isSuccess => code != null && codeVerifier != null;
}

/// Push this screen to drive the GitHub authorize flow. The returned
/// Future completes with a code+verifier on success, or an error/null
/// if the user cancelled or the redirect carried an `error=` param.
class GithubOAuthWebViewScreen extends StatefulWidget {
  const GithubOAuthWebViewScreen({
    required this.clientId,
    required this.redirectUri,
    this.authorizationEndpoint = 'https://github.com/login/oauth/authorize',
    this.scopes = const ['read:user', 'user:email'],
    super.key,
  });

  final String clientId;
  final String redirectUri;
  final String authorizationEndpoint;
  final List<String> scopes;

  @override
  State<GithubOAuthWebViewScreen> createState() =>
      _GithubOAuthWebViewScreenState();
}

class _GithubOAuthWebViewScreenState extends State<GithubOAuthWebViewScreen> {
  late final String _codeVerifier;
  late final String _codeChallenge;
  late final String _state;
  late final Uri _authorizeUrl;

  @override
  void initState() {
    super.initState();
    _codeVerifier = generatePkceVerifier();
    _codeChallenge = pkceChallengeFor(_codeVerifier);
    _state = generateOAuthState();
    _authorizeUrl = Uri.parse(widget.authorizationEndpoint).replace(
      queryParameters: <String, String>{
        'client_id': widget.clientId,
        'redirect_uri': widget.redirectUri,
        'scope': widget.scopes.join(' '),
        'state': _state,
        'response_type': 'code',
        'code_challenge': _codeChallenge,
        'code_challenge_method': 'S256',
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('GitHub sign-in'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () {
            if (mounted) {
              Navigator.of(context).pop(
                const GithubOAuthResult(error: 'cancelled'),
              );
            }
          },
        ),
      ),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri.uri(_authorizeUrl)),
        initialSettings: InAppWebViewSettings(
          useShouldOverrideUrlLoading: true,
          javaScriptEnabled: true,
        ),
        shouldOverrideUrlLoading: (controller, action) async =>
            classifyGithubRedirect(
          action.request.url,
          expectedRedirectUri: widget.redirectUri,
          expectedState: _state,
          codeVerifier: _codeVerifier,
          onMatch: (result) {
            if (mounted) Navigator.of(context).pop(result);
          },
        ),
      ),
    );
  }
}

// ---- Pure helpers (extracted for unit testing) -----------------------------

/// Inspects a navigation URL; if it's the GitHub auth-code redirect to our
/// scheme, calls `onMatch` with the extracted result and returns CANCEL.
/// Otherwise returns ALLOW.
NavigationActionPolicy classifyGithubRedirect(
  Uri? uri, {
  required String expectedRedirectUri,
  required String expectedState,
  required String codeVerifier,
  required void Function(GithubOAuthResult) onMatch,
}) {
  if (uri == null) return NavigationActionPolicy.ALLOW;
  final expected = Uri.parse(expectedRedirectUri);
  if (uri.scheme != expected.scheme) return NavigationActionPolicy.ALLOW;
  if (uri.host != expected.host) return NavigationActionPolicy.ALLOW;
  // Path can be empty (just `solvrlabs://oauth`) or `/github` — accept either
  // as long as the scheme+host matched the registered redirect.
  final params = uri.queryParameters;
  if (params.containsKey('error')) {
    onMatch(GithubOAuthResult(error: params['error']));
    return NavigationActionPolicy.CANCEL;
  }
  final code = params['code'];
  final state = params['state'];
  if (code == null || code.isEmpty) {
    onMatch(const GithubOAuthResult(error: 'missing_code'));
    return NavigationActionPolicy.CANCEL;
  }
  if (state != expectedState) {
    onMatch(const GithubOAuthResult(error: 'state_mismatch'));
    return NavigationActionPolicy.CANCEL;
  }
  onMatch(
    GithubOAuthResult(code: code, codeVerifier: codeVerifier),
  );
  return NavigationActionPolicy.CANCEL;
}

/// 32 bytes → base64url (43 chars, no padding) — meets RFC 7636 §4.1.
String generatePkceVerifier([Random? random]) {
  final r = random ?? Random.secure();
  final bytes = List<int>.generate(32, (_) => r.nextInt(256));
  return base64Url.encode(bytes).replaceAll('=', '');
}

/// S256 challenge per RFC 7636 §4.2 — sha256(verifier), base64url, no padding.
String pkceChallengeFor(String verifier) {
  final hash = sha256.convert(utf8.encode(verifier)).bytes;
  return base64Url.encode(hash).replaceAll('=', '');
}

/// 16 random bytes → base64url — CSRF state per OAuth 2.0 best practice.
String generateOAuthState([Random? random]) {
  final r = random ?? Random.secure();
  final bytes = List<int>.generate(16, (_) => r.nextInt(256));
  return base64Url.encode(bytes).replaceAll('=', '');
}
