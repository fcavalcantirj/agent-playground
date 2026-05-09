// Phase B Plan 11 — Stripe Checkout webview (D-19/D-20/D-21 + AMD-03).
//
// flutter_inappwebview 6.1.5 — Wave 0 spike-e proven the
// `shouldOverrideUrlLoading` callback signature works against AMD-03's
// recommended `https://app.solvrlabs.com/billing/return-{success,cancel}`
// sentinel URLs without AppLinks/UniversalLinks plumbing (RESEARCH Open
// Q #2 — webview-internal handshake).
//
// On a sentinel match the screen pops with PaymentResult.{success,
// cancelled}; the calling TopUpScreen consumes the result and either
// invalidates balanceProvider in a polling loop (success) or returns to
// the picker (cancelled).

import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

/// Outcome flag returned via Navigator.pop when the webview
/// intercepts the Stripe-hosted success_url or cancel_url.
enum PaymentResult { success, cancelled }

class CheckoutWebViewScreen extends StatefulWidget {
  const CheckoutWebViewScreen({required this.checkoutUrl, super.key});

  final String checkoutUrl;

  @override
  State<CheckoutWebViewScreen> createState() => _CheckoutWebViewScreenState();
}

class _CheckoutWebViewScreenState extends State<CheckoutWebViewScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Checkout')),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri(widget.checkoutUrl)),
        initialSettings: InAppWebViewSettings(
          // Force the navigation-delegate callback to fire on every
          // navigation including the initial load (matches spike-e
          // shape).
          useShouldOverrideUrlLoading: true,
        ),
        shouldOverrideUrlLoading: (controller, action) async =>
            classifyNavigationForResult(action.request.url, (result) {
          if (mounted) Navigator.of(context).pop(result);
        }),
      ),
    );
  }
}

/// Pure URL-classification function — extracted for unit testing
/// (the InAppWebView itself can't be exercised in `flutter test`,
/// but the host+path branching can). Calls `onIntercept(result)`
/// when the URL matches one of the sentinel paths AND returns
/// CANCEL; otherwise returns ALLOW.
NavigationActionPolicy classifyNavigationForResult(
  Uri? uri,
  void Function(PaymentResult) onIntercept,
) {
  if (uri == null) return NavigationActionPolicy.ALLOW;
  if (uri.host == kCheckoutSentinelHost &&
      uri.path == kCheckoutSentinelSuccessPath) {
    onIntercept(PaymentResult.success);
    return NavigationActionPolicy.CANCEL;
  }
  if (uri.host == kCheckoutSentinelHost &&
      uri.path == kCheckoutSentinelCancelPath) {
    onIntercept(PaymentResult.cancelled);
    return NavigationActionPolicy.CANCEL;
  }
  return NavigationActionPolicy.ALLOW;
}

/// Webview-internal sentinel host+paths (RESEARCH Open Q #2 — no
/// AppLinks/UniversalLinks needed; the webview's navigation delegate
/// catches these BEFORE the OS-level URL handler runs).
const String kCheckoutSentinelHost = 'app.solvrlabs.com';
const String kCheckoutSentinelSuccessPath = '/billing/return-success';
const String kCheckoutSentinelCancelPath = '/billing/return-cancel';
