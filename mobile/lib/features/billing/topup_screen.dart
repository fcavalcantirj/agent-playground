// Phase B Plan 11 Task 1 — Top-up screen (Wave 5 mobile UI, D-21).
//
// State machine (single screen, three states):
//   - picking          : pack catalog visible, tap fires Checkout flow.
//   - awaitingCheckout : POST /v1/billing/checkout in flight; on success
//                        push CheckoutWebViewScreen + await pop.
//   - awaitingWebhook  : webview popped with PaymentResult.success;
//                        polling balanceProvider every 2s for ≤30s
//                        until balance reflects the top-up. Cancel
//                        flips state back to picking; webhook still
//                        runs server-side regardless.
//
// Caller flow:
//   /billing/topup → tap a pack → Checkout webview → success URL
//   intercepted → screen pops → polling kicks → SnackBar + ctx.pop
//   when balance > baseline.
//
// Per Plan 11's must_haves.truths line 31: the calling screen polls
// BalanceNotifier until balance reflects the top-up (or 30s timeout).
// Webhook latency is 5-15s typical; the 30s budget catches the long
// tail without blocking the user UX indefinitely.

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:agent_playground/features/billing/billing_providers.dart';
import 'package:agent_playground/features/billing/checkout_webview_screen.dart';
import 'package:agent_playground/features/billing/pack_picker_widget.dart';
import 'package:agent_playground/features/billing/topup_inflight_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class TopUpScreen extends ConsumerStatefulWidget {
  const TopUpScreen({super.key});

  @override
  ConsumerState<TopUpScreen> createState() => _TopUpScreenState();
}

enum _TopUpState { picking, awaitingCheckout, awaitingWebhook }

class _TopUpScreenState extends ConsumerState<TopUpScreen> {
  _TopUpState _state = _TopUpState.picking;
  int? _baselineBalanceCents;
  bool _cancelledByUser = false;

  Future<void> _onPackSelected(Pack pack) async {
    setState(() => _state = _TopUpState.awaitingCheckout);
    final api = ref.read(apiClientProvider);
    final r = await api.createPackCheckoutSession(packId: pack.id);
    if (!mounted) return;
    switch (r) {
      case Err(:final error):
        setState(() => _state = _TopUpState.picking);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to start checkout: ${error.message}')),
        );
        return;
      case Ok(:final value):
        // Capture baseline balance for polling. AsyncValue.value can be
        // null if balanceProvider has not loaded yet; treat as 0.
        final bal = ref.read(balanceProvider).value;
        _baselineBalanceCents = bal?.balanceCents ?? 0;

        final result = await Navigator.of(context).push<PaymentResult>(
          MaterialPageRoute<PaymentResult>(
            builder: (_) => CheckoutWebViewScreen(checkoutUrl: value),
          ),
        );
        if (!mounted) return;
        if (result == PaymentResult.success) {
          setState(() {
            _state = _TopUpState.awaitingWebhook;
            _cancelledByUser = false;
          });
          await _pollUntilTopupReflected();
        } else {
          // cancelled or webview popped without a result.
          setState(() => _state = _TopUpState.picking);
        }
    }
  }

  Future<void> _pollUntilTopupReflected() async {
    final start = DateTime.now();
    while (mounted &&
        !_cancelledByUser &&
        DateTime.now().difference(start).inSeconds < 30) {
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted || _cancelledByUser) return;
      ref.invalidate(balanceProvider);
      try {
        final fresh = await ref.read(balanceProvider.future);
        if (fresh.balanceCents > (_baselineBalanceCents ?? 0)) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Top-up confirmed!')),
          );
          context.pop();
          return;
        }
      } on Object catch (_) {
        // Ignore transient errors and retry on the next tick.
      }
    }
    if (!mounted) return;
    if (!_cancelledByUser) {
      setState(() => _state = _TopUpState.picking);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Top-up is taking longer than expected. Pull to refresh later.',
          ),
        ),
      );
    }
  }

  void _onCancelInflight() {
    setState(() {
      _cancelledByUser = true;
      _state = _TopUpState.picking;
    });
  }

  @override
  Widget build(BuildContext context) {
    final packs = ref.watch(packsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Top up')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: switch (_state) {
          _TopUpState.awaitingWebhook => TopUpInflightWidget(
              onCancel: _onCancelInflight,
            ),
          _ => packs.when(
              data: (list) => PackPickerWidget(
                packs: list,
                onSelect: _state == _TopUpState.picking
                    ? _onPackSelected
                    : (_) {},
              ),
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) {
                final msg = e is ApiError ? e.message : '$e';
                return Center(child: Text('Failed to load packs: $msg'));
              },
            ),
        },
      ),
    );
  }
}
