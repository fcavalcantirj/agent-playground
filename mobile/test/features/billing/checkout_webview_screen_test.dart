// Phase B Plan 11 Task 2 — CheckoutWebViewScreen unit tests.
//
// `flutter test` cannot drive a real InAppWebView (the platform channels
// expect a host page). The integration smoke (Task 3 / Plan 11 manual UAT)
// covers the full webview navigation. Here we unit-test:
//
//   - test_checkout_webview_loads_url_on_init           — widget builds
//   - test_checkout_webview_intercepts_success_url_pops_with_success_result
//   - test_checkout_webview_intercepts_cancel_url_pops_with_cancelled_result
//   - test_checkout_webview_allows_navigation_to_other_urls
//
// The 3 navigation tests target the pure `classifyNavigationForResult`
// helper extracted from the screen so the URL-classification branching
// can be exercised without driving the platform channel.

import 'package:agent_playground/features/billing/checkout_webview_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CheckoutWebViewScreen', () {
    testWidgets('mounts with the supplied url (widget tree assembles)',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: CheckoutWebViewScreen(
            checkoutUrl: 'https://checkout.stripe.com/c/pay/cs_test_x',
          ),
        ),
      );
      // First frame is enough — InAppWebView's platform channel will
      // not fire in the test harness (MissingPluginException is
      // expected). The smoke is that CheckoutWebViewScreen is in the
      // tree and the checkoutUrl reaches the widget unchanged.
      await tester.pump();
      // Drain platform-channel exceptions so they don't fail the test;
      // the integration smoke (Task 3 manual UAT) is what verifies
      // real navigation.
      tester.takeException();
      final w = tester.widget<CheckoutWebViewScreen>(
        find.byType(CheckoutWebViewScreen),
      );
      expect(w.checkoutUrl, 'https://checkout.stripe.com/c/pay/cs_test_x');
    });
  });

  group('classifyNavigationForResult', () {
    test('intercepts success url -> CANCEL + PaymentResult.success', () {
      PaymentResult? captured;
      final policy = classifyNavigationForResult(
        Uri.parse(
          'https://app.solvrlabs.com/billing/return-success'
          '?session_id=cs_test_abc',
        ),
        (r) => captured = r,
      );
      expect(policy, NavigationActionPolicy.CANCEL);
      expect(captured, PaymentResult.success);
    });

    test('intercepts cancel url -> CANCEL + PaymentResult.cancelled', () {
      PaymentResult? captured;
      final policy = classifyNavigationForResult(
        Uri.parse('https://app.solvrlabs.com/billing/return-cancel'),
        (r) => captured = r,
      );
      expect(policy, NavigationActionPolicy.CANCEL);
      expect(captured, PaymentResult.cancelled);
    });

    test('allows navigation to other Stripe URLs', () {
      PaymentResult? captured;
      final policy = classifyNavigationForResult(
        Uri.parse('https://checkout.stripe.com/c/pay/cs_test_xyz'),
        (r) => captured = r,
      );
      expect(policy, NavigationActionPolicy.ALLOW);
      expect(captured, isNull);
    });

    test('allows null URI without throwing', () {
      PaymentResult? captured;
      final policy = classifyNavigationForResult(null, (r) => captured = r);
      expect(policy, NavigationActionPolicy.ALLOW);
      expect(captured, isNull);
    });

    test('does not intercept when host matches but path does not', () {
      PaymentResult? captured;
      final policy = classifyNavigationForResult(
        Uri.parse('https://app.solvrlabs.com/some-other-path'),
        (r) => captured = r,
      );
      expect(policy, NavigationActionPolicy.ALLOW);
      expect(captured, isNull);
    });
  });
}
