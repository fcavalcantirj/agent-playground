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
import 'package:agent_playground/features/billing/iap_offerings_provider.dart';
import 'package:agent_playground/features/billing/iap_service.dart';
import 'package:agent_playground/features/billing/pack_picker_widget.dart';
import 'package:agent_playground/features/billing/topup_inflight_widget.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
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
    // Capture baseline balance once — both Stripe and IAP paths poll
    // the same /v1/billing/balance endpoint until the webhook lands.
    final bal = ref.read(balanceProvider).value;
    _baselineBalanceCents = bal?.balanceCents ?? 0;

    if (kIsWeb) {
      await _onPackSelectedViaStripe(pack);
    } else {
      await _onPackSelectedViaIap(pack);
    }
  }

  Future<void> _onPackSelectedViaStripe(Pack pack) async {
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
          setState(() => _state = _TopUpState.picking);
        }
    }
  }

  Future<void> _onPackSelectedViaIap(Pack pack) async {
    setState(() => _state = _TopUpState.awaitingCheckout);
    final offerings = await ref.read(iapOfferingsProvider.future);
    if (!mounted) return;
    // Match by Pack.id ("pack_5") → RC Package.identifier ("pack_5").
    // The RC dashboard config is the source of truth; mobile catalog ids
    // mirror server-side billing_packs.Pack.id.
    final rcPackages = packPackagesFrom(offerings);
    final rcPackage = rcPackages.where((p) => p.identifier == pack.id).firstOrNull;
    if (rcPackage == null) {
      setState(() => _state = _TopUpState.picking);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text(
          "Credit packs aren't available right now. Try again later.",
        )),
      );
      return;
    }
    final status = await IapService.instance.purchase(rcPackage);
    if (!mounted) return;
    switch (status) {
      case IapPurchaseStatus.purchased:
        setState(() {
          _state = _TopUpState.awaitingWebhook;
          _cancelledByUser = false;
        });
        await _pollUntilTopupReflected();
      case IapPurchaseStatus.cancelled:
        setState(() => _state = _TopUpState.picking);
      case IapPurchaseStatus.error:
        setState(() => _state = _TopUpState.picking);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text(
            "Couldn't complete the purchase. Try again.",
          )),
        );
    }
  }

  Future<void> _pollUntilTopupReflected() async {
    // #14 fix: go through apiClient directly. The previous
    // ref.invalidate(balanceProvider) + ref.read(balanceProvider.future)
    // path silently no-op'd against the autoDispose AsyncNotifier's cached
    // future — every "refresh" resolved to the cached AsyncValue, no HTTP
    // hop, and the user always saw a 30s spinner regardless of webhook.
    final api = ref.read(apiClientProvider);
    final start = DateTime.now();
    while (mounted &&
        !_cancelledByUser &&
        DateTime.now().difference(start).inSeconds < 30) {
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted || _cancelledByUser) return;
      final r = await api.billingBalance();
      if (!mounted || _cancelledByUser) return;
      switch (r) {
        case Ok(:final value):
          if (value.balanceCents > (_baselineBalanceCents ?? 0)) {
            // Make sure widgets watching balanceProvider see the new value.
            ref.invalidate(balanceProvider);
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Top-up confirmed!')),
            );
            context.pop();
            return;
          }
        case Err():
          // Transient error — retry next tick. Do not surface.
          break;
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
