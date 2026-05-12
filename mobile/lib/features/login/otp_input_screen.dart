// 2026-05-12 — magic-link email login (step 2 of 2).
//
// Shows the email under the wordmark + a single 6-digit field. When the
// user enters the 6th digit, auto-submits via
// `AuthService.verifyEmailCode(email, code)`. On success, publishes the
// SessionUser via `loginSuccessProvider` (same plumbing as Google /
// GitHub / Apple) and the app shell routes to /dashboard.
//
// "Resend code" link below the field; gated by a server-supplied
// cooldown countdown (typically 60s).

import 'dart:async';

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class OtpInputScreen extends ConsumerStatefulWidget {
  const OtpInputScreen({super.key, required this.email});

  final String email;

  @override
  ConsumerState<OtpInputScreen> createState() => _OtpInputScreenState();
}

class _OtpInputScreenState extends ConsumerState<OtpInputScreen> {
  final _codeController = TextEditingController();
  final _focusNode = FocusNode();
  bool _verifying = false;
  bool _resending = false;
  String? _error;
  int _cooldown = 60;
  Timer? _cooldownTimer;

  @override
  void initState() {
    super.initState();
    _startCooldown(60);
    // Autofocus the field after first frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _codeController.dispose();
    _focusNode.dispose();
    _cooldownTimer?.cancel();
    super.dispose();
  }

  void _startCooldown(int seconds) {
    _cooldownTimer?.cancel();
    setState(() => _cooldown = seconds);
    _cooldownTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) {
        t.cancel();
        return;
      }
      if (_cooldown <= 1) {
        t.cancel();
        setState(() => _cooldown = 0);
      } else {
        setState(() => _cooldown -= 1);
      }
    });
  }

  Future<void> _verify(String code) async {
    if (_verifying) return;
    setState(() {
      _verifying = true;
      _error = null;
    });
    final svc = ref.read(authServiceProvider);
    final r = await svc.verifyEmailCode(email: widget.email, code: code);
    if (!mounted) return;
    setState(() => _verifying = false);
    switch (r) {
      case Ok(:final value):
        ref.read(loginSuccessProvider.notifier).state = value;
        ref.read(showSignedOutBannerProvider.notifier).state = false;
        // App shell listens loginSuccessProvider and routes to /dashboard.
      case Err(:final error):
        setState(() {
          _error = _friendly(error);
          _codeController.clear();
        });
        _focusNode.requestFocus();
    }
  }

  Future<void> _resend() async {
    if (_resending || _cooldown > 0) return;
    setState(() {
      _resending = true;
      _error = null;
    });
    final svc = ref.read(authServiceProvider);
    final r = await svc.requestEmailCode(email: widget.email);
    if (!mounted) return;
    setState(() => _resending = false);
    switch (r) {
      case Ok(:final value):
        _startCooldown(value);
      case Err(:final error):
        setState(() => _error = _friendly(error));
    }
  }

  String _friendly(ApiError e) {
    if (e.code == ErrorCode.network) return 'Check your connection.';
    if (e.code == ErrorCode.timeout) return 'The request timed out.';
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
                "We sent a 6-digit code to",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  color: SolvrColors.mutedForeground,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                widget.email,
                textAlign: TextAlign.center,
                style: SolvrTextStyles.mono(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 32),
              TextField(
                controller: _codeController,
                focusNode: _focusNode,
                keyboardType: TextInputType.number,
                textAlign: TextAlign.center,
                maxLength: 6,
                enabled: !_verifying,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                ],
                autofillHints: const [AutofillHints.oneTimeCode],
                style: SolvrTextStyles.mono(
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                ),
                decoration: const InputDecoration(
                  counterText: '',
                  hintText: '••••••',
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) {
                  if (v.length == 6) {
                    _verify(v);
                  }
                },
              ),
              const SizedBox(height: 16),
              if (_verifying)
                const Center(
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else
                TextButton(
                  onPressed: (_cooldown > 0 || _resending) ? null : _resend,
                  child: Text(
                    _cooldown > 0
                        ? "Resend in ${_cooldown}s"
                        : (_resending ? "Sending..." : "Resend code"),
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
