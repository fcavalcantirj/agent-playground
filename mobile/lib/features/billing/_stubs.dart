// Phase B Plan 10 — billing screen stubs.
//
// PHASE_B_STUB
// Plan 11 (Wave 5 mobile UI screens) replaces these classes with the real
// TopUpScreen / CheckoutWebViewScreen / TransactionsScreen widgets. The
// stubs exist only so that Plan 10 ships a green build — the router
// registers the three /billing/* routes today (so deep-links resolve and
// Plan 11's executor can swap implementations atomically), but the bodies
// are placeholder Scaffolds until Plan 11 lands.
//
// Plan 11 executor: search for `// PHASE_B_STUB` and replace these
// classes with the real screens (typically extracted into their own
// files: topup_screen.dart, checkout_webview_screen.dart,
// transactions_screen.dart per the pattern map). Delete this file when
// the real screens land.

import 'package:flutter/material.dart';

/// PHASE_B_STUB — Plan 11 replaces with real `TopUpScreen` (pack picker
/// + tier-aware copy + onTap → POST /v1/billing/checkout via
/// `createPackCheckoutSession`).
class TopUpScreen extends StatelessWidget {
  const TopUpScreen({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Center(child: Text('TopUp (Plan 11 stub)')),
      );
}

/// PHASE_B_STUB — Plan 11 replaces with real `CheckoutWebViewScreen`
/// (`flutter_inappwebview` + `shouldOverrideUrlLoading` interception of
/// the Stripe-hosted success/cancel URLs per AMD-03 / D-21).
class CheckoutWebViewScreen extends StatelessWidget {
  const CheckoutWebViewScreen({required this.checkoutUrl, super.key});

  final String checkoutUrl;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(child: Text('Checkout (Plan 11 stub): $checkoutUrl')),
      );
}

/// PHASE_B_STUB — Plan 11 replaces with real `TransactionsScreen`
/// (paginated list backed by `transactionsProvider` + RefreshIndicator
/// + `loadMore()` infinite-scroll trigger).
class TransactionsScreen extends StatelessWidget {
  const TransactionsScreen({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Center(child: Text('Transactions (Plan 11 stub)')),
      );
}
