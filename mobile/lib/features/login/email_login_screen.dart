// 2026-05-12 — magic-link email login (step 1 of 2).
//
// User enters email; tap "Send code" calls
// `AuthService.requestEmailCode(email)`; on success, push
// `/login/email/code?email=<>` which renders OtpInputScreen.
//
// Layout mirrors LoginScreen: 64px top spacer → wordmark → 48px gap →
// email input (autofocus, email keyboard, autofill hint) → "Send code"
// button with inflight spinner. Error caption under the field on
// failure (clear on next tap).

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class EmailLoginScreen extends ConsumerStatefulWidget {
  const EmailLoginScreen({super.key});

  @override
  ConsumerState<EmailLoginScreen> createState() => _EmailLoginScreenState();
}

class _EmailLoginScreenState extends ConsumerState<EmailLoginScreen> {
  final _controller = TextEditingController();
  bool _pending = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _looksLikeEmail {
    final v = _controller.text.trim();
    return v.contains('@') && v.contains('.') && v.length >= 5;
  }

  Future<void> _sendCode() async {
    if (_pending) return;
    final email = _controller.text.trim();
    if (!_looksLikeEmail) {
      setState(() => _error = 'Enter a valid email address.');
      return;
    }
    setState(() {
      _pending = true;
      _error = null;
    });

    final svc = ref.read(authServiceProvider);
    final r = await svc.requestEmailCode(email: email);

    if (!mounted) return;
    setState(() => _pending = false);

    switch (r) {
      case Ok():
        if (!mounted) return;
        context.push(Uri(
          path: '/login/email/code',
          queryParameters: {'email': email},
        ).toString());
      case Err(:final error):
        setState(() => _error = _friendly(error));
    }
  }

  String _friendly(ApiError e) {
    if (e.code == ErrorCode.network) return 'Check your connection.';
    if (e.code == ErrorCode.timeout) return 'The request timed out.';
    // Server's rate-limit / validation message is the most useful copy
    // we have; surface it verbatim ("please wait 47s..." / "invalid
    // email format").
    return e.message;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 32),
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
              const Text(
                "Enter your email and we'll send you a 6-digit code.",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  color: SolvrColors.mutedForeground,
                ),
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _controller,
                autofocus: true,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.go,
                autocorrect: false,
                enableSuggestions: false,
                autofillHints: const [AutofillHints.email],
                onSubmitted: (_) => _sendCode(),
                decoration: const InputDecoration(
                  labelText: 'Email',
                  hintText: 'you@example.com',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: 48,
                child: ElevatedButton(
                  onPressed: _pending ? null : _sendCode,
                  child: _pending
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          'Send code',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
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
}
