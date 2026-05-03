// Phase 25 Wave 1 — D-02 cold-start retry screen.
//
// Shown when GET /v1/users/me fails with 5xx / network error / timeout
// at boot. Single Retry button re-fires usersMe and routes the user to
// /dashboard or /login or stays on this screen depending on the result.
// No auto-retry, no exponential backoff (D-02).

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/boot/resolve_initial_route.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class RetryBootstrapScreen extends ConsumerStatefulWidget {
  const RetryBootstrapScreen({super.key});

  @override
  ConsumerState<RetryBootstrapScreen> createState() =>
      _RetryBootstrapScreenState();
}

class _RetryBootstrapScreenState extends ConsumerState<RetryBootstrapScreen> {
  bool _retrying = false;

  Future<void> _retry() async {
    if (_retrying) return;
    setState(() => _retrying = true);
    final api = ref.read(apiClientProvider);
    final route = await resolveInitialRoute(api);
    if (!mounted) return;
    setState(() => _retrying = false);
    if (route != '/retry-bootstrap') {
      context.go(route);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Text(
                  '>_ SOLVR_LABS',
                  style: SolvrTextStyles.mono(
                    fontSize: 28,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(height: 32),
              const Text(
                "Couldn't reach server",
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              const Text(
                'Check your connection and try again.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  color: SolvrColors.mutedForeground,
                ),
              ),
              const SizedBox(height: 32),
              SizedBox(
                height: 48,
                child: ElevatedButton(
                  onPressed: _retrying ? null : _retry,
                  child: _retrying
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          'Retry',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
