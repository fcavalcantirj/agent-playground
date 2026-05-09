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

import 'dart:async';

import 'package:flutter/material.dart';

class TopUpInflightWidget extends StatefulWidget {
  const TopUpInflightWidget({required this.onCancel, super.key});

  final VoidCallback onCancel;

  @override
  State<TopUpInflightWidget> createState() => _TopUpInflightWidgetState();
}

class _TopUpInflightWidgetState extends State<TopUpInflightWidget> {
  Stopwatch? _elapsed;
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _elapsed = Stopwatch()..start();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
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
      decoration: BoxDecoration(border: Border.all(color: Colors.grey)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(width: 8),
              Expanded(child: Text('Confirming top-up…')),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                _formatElapsed(),
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12,
                ),
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
