// Phase 25 Wave 1 — Login screen (D-04..D-06).
//
// Layout: 64px top spacer → `>_ SOLVR_LABS` wordmark in JetBrains Mono w600
// at 28px → 48px gap → optional `Signed out · Sign in to continue` banner
// (D-03) → "Continue with Google" full-width 48dp ElevatedButton → 16px
// gap → "Continue with GitHub" → optional inline red error caption (D-06).
//
// Pending (D-05): tapped button replaces label with CircularProgressIndicator;
// other button is disabled (onPressed: null). Failures (D-06): inline red
// caption under buttons; cleared on next button tap.
//
// Navigation: on success the loginSuccessProvider is set; the router (or
// app shell) listens and replaces with /dashboard. The widget itself does
// not call go_router so it stays testable without a full router harness.

import 'dart:io' show Platform;

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class LoginScreen extends ConsumerWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pending = ref.watch(loginPendingProvider);
    final error = ref.watch(loginErrorProvider);
    final showBanner = ref.watch(showSignedOutBannerProvider);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 64),
              Center(
                child: Text(
                  '>_ SOLVR_LABS',
                  style: SolvrTextStyles.mono(
                    fontSize: 28,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(height: 48),
              if (showBanner) ...[
                const Text(
                  'Signed out · Sign in to continue',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    color: SolvrColors.mutedForeground,
                  ),
                ),
                const SizedBox(height: 24),
              ],
              _OAuthButton(
                provider: 'google',
                label: 'Continue with Google',
                glyph: 'G',
                pending: pending,
                onTap: () => _signIn(context, ref, 'google'),
              ),
              const SizedBox(height: 16),
              _OAuthButton(
                provider: 'github',
                label: 'Continue with GitHub',
                glyph: 'GH',
                pending: pending,
                onTap: () => _signIn(context, ref, 'github'),
              ),
              // 2026-05-12 — Sign in with Apple. iOS-only per Apple's
              // guidelines (the button is not allowed on Android).
              // kIsWeb guard so this still compiles for the web target
              // (where dart:io's Platform throws at boot).
              if (!kIsWeb && Platform.isIOS) ...[
                const SizedBox(height: 16),
                _OAuthButton(
                  provider: 'apple',
                  label: 'Continue with Apple',
                  glyph: '',
                  pending: pending,
                  onTap: () => _signIn(context, ref, 'apple'),
                ),
              ],
              const SizedBox(height: 16),
              _OAuthButton(
                provider: 'email',
                label: 'Continue with email',
                glyph: '@',
                pending: pending,
                onTap: () {
                  // Email path is multi-step (request code → enter code).
                  // The button itself only navigates; the email-request
                  // network call happens on the EmailLoginScreen so we
                  // can give the user a textbox first.
                  context.push('/login/email');
                },
              ),
              if (error != null) ...[
                const SizedBox(height: 16),
                Text(
                  error,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 12,
                    color: SolvrColors.destructive,
                  ),
                ),
              ],
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _signIn(
    BuildContext context,
    WidgetRef ref,
    String provider,
  ) async {
    // D-06 — clear error caption on next button tap, even if a request
    // ends up failing again (the user re-engaged, the previous failure
    // is no longer the active state).
    ref.read(loginErrorProvider.notifier).state = null;
    ref.read(loginPendingProvider.notifier).state = provider;

    final svc = ref.read(authServiceProvider);
    // 2026-05-11 — GitHub OAuth on Android via HTTPS App Link (RFC 8252):
    // flutter_appauth opens Chrome Custom Tab, GitHub redirects to
    // https://agents.solvr.dev/m/oauth/github?code=..., Android verifies
    // our SHA-256 via the server's .well-known/assetlinks.json and routes
    // the intent directly to RedirectUriReceiverActivity — no custom-scheme
    // dispatch (which fails on HyperOS), no webview (which GitHub blocks).
    // Same flutter_appauth code path for iOS (ASWebAuthenticationSession
    // handles HTTPS callbacks identically).
    final r = switch (provider) {
      'google' => await svc.signInWithGoogle(),
      'github' => await svc.signInWithGithub(),
      'apple' => await svc.signInWithApple(),
      _ => await svc.signInWithGoogle(),
    };

    // Always reset pending so the buttons re-enable.
    ref.read(loginPendingProvider.notifier).state = null;

    switch (r) {
      case Ok(:final value):
        ref.read(showSignedOutBannerProvider.notifier).state = false;
        ref.read(loginSuccessProvider.notifier).state = value;
      case Err(:final error):
        // 2026-05-12 — include request_id so a user reporting "I can't
        // sign in" gives us a grep-able id for prod logs/Sentry.
        // Format: <friendly headline>\n<server detail>\n(id: <reqid>)
        final reqId = error.requestId;
        final tail = reqId == null || reqId.isEmpty
            ? ''
            : '\n(id: $reqId)';
        ref.read(loginErrorProvider.notifier).state =
            "Couldn't sign in. ${_friendly(error)}\n"
            "${error.message}$tail".trim();
    }
  }

  String _friendly(ApiError e) {
    if (e.code == ErrorCode.network) return 'Check your connection.';
    if (e.code == ErrorCode.timeout) return 'The request timed out.';
    if (e.code == ErrorCode.unauthorized) {
      return "The server didn't accept the sign-in.";
    }
    return 'Try again.';
  }
}

class _OAuthButton extends StatelessWidget {
  const _OAuthButton({
    required this.provider,
    required this.label,
    required this.glyph,
    required this.pending,
    required this.onTap,
  });

  final String provider;
  final String label;
  final String glyph;
  final String? pending;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isThisPending = pending == provider;
    final isOtherPending = pending != null && !isThisPending;

    return SizedBox(
      height: 48,
      child: ElevatedButton(
        onPressed: (isThisPending || isOtherPending) ? null : onTap,
        child: isThisPending
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // TODO(v0.3-polish): swap glyph for brand SVGs.
                  Text(
                    glyph,
                    style: SolvrTextStyles.mono(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ).copyWith(color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    label,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
