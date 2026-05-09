// Phase B Plan 11 Task 1 — post-Checkout inflight UX (D-21).
//
// Lifted from mobile/lib/features/new_agent/deploy_step.dart:387-444
// (the Stopwatch + Timer.periodic + mm:ss + Cancel triplet) per
// memory feedback_inflight_ui_for_long_awaits.md. Shown after the
// CheckoutWebViewScreen pops with PaymentResult.success while
// TopUpScreen polls balanceProvider until the webhook lands and the
// balance reflects the top-up (5-15s typical, 30s budget per PLAN).
//
// Cancel is a soft cancel — TopUpScreen flips the state machine
// back to picking and shows a "still processing, refresh later"
// SnackBar. The Stripe webhook is in-flight server-side regardless.
//
// #15 visual refresh — Matrix-style cycling clawclones agent name
// instead of a dead spinner. Per memory feedback_solvr_matrix_aesthetic.md.

import 'dart:async';
import 'dart:math';

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

const List<String> _agentClones = <String>[
  'openclaw',
  'hermes',
  'nullclaw',
  'picoclaw',
  'nanobot',
  'qwenpaw',
];

class TopUpInflightWidget extends StatefulWidget {
  const TopUpInflightWidget({required this.onCancel, super.key});

  final VoidCallback onCancel;

  @override
  State<TopUpInflightWidget> createState() => _TopUpInflightWidgetState();
}

class _TopUpInflightWidgetState extends State<TopUpInflightWidget> {
  Stopwatch? _elapsed;
  Timer? _tick;
  Timer? _flicker;
  String _agent = _agentClones[0];
  final Random _rng = Random();

  @override
  void initState() {
    super.initState();
    _elapsed = Stopwatch()..start();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    // Flicker the agent name every ~250ms — fast enough to feel alive,
    // slow enough to read.
    _flicker = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (!mounted) return;
      setState(() {
        _agent = _agentClones[_rng.nextInt(_agentClones.length)];
      });
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _flicker?.cancel();
    _elapsed?.stop();
    super.dispose();
  }

  String _formatElapsed() {
    final secs = _elapsed?.elapsed.inSeconds ?? 0;
    final mm = (secs ~/ 60).toString().padLeft(2, '0');
    final ss = (secs % 60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: SolvrColors.border),
        color: SolvrColors.background,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 120),
                  transitionBuilder: (child, anim) =>
                      FadeTransition(opacity: anim, child: child),
                  child: Text(
                    '> ${_agent.padRight(10)}_  CONFIRMING',
                    key: ValueKey<String>(_agent),
                    style: SolvrTextStyles.mono(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ).copyWith(
                      color: SolvrColors.foreground,
                      letterSpacing: 0.6,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Stripe → webhook → ledger',
            style: SolvrTextStyles.mono(
              fontSize: 11,
            ).copyWith(color: SolvrColors.mutedForeground),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                _formatElapsed(),
                style: SolvrTextStyles.mono(
                  fontSize: 12,
                ).copyWith(color: SolvrColors.mutedForeground),
              ),
              TextButton(
                onPressed: widget.onCancel,
                child: const Text('Cancel'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
