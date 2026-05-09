// SPIKE (Phase B Wave 0 — spike E) — flutter_inappwebview shouldOverrideUrlLoading.
//
// Proves AMD-03 / RESEARCH §Example D: the navigation-delegate API surface
// flutter_inappwebview gives us is exactly what Wave 6 (mobile checkout
// webview) needs — i.e. when the in-page redirect lands on
// `https://app.solvrlabs.com/billing/return-success?session_id=cs_*`, our
// Dart callback fires BEFORE the page is fetched, lets us extract the
// session_id, and returns NavigationActionPolicy.CANCEL to stop the
// webview from loading the (fake-app-domain) URL.
//
// The test loads a tiny inline `data:text/html,...` page with one anchor
// pointing at the success URL. Tapping the anchor (synthesized via
// `evaluateJavascript("document.getElementById('go').click()")`) triggers
// shouldOverrideUrlLoading. The callback inspects the navigation request,
// extracts `session_id`, and signals a Completer.
//
// No real Stripe Checkout, no real network — the data: URL renders
// entirely in the webview. This isolates the navigation-delegate API
// from any Stripe-side flakiness.
//
// PASS criterion: print "PASS spike-e" + completer fires within 10s with
// the expected session_id.
//
// Run via:
//   cd mobile && fvm flutter test integration_test/spike_e_inappwebview_intercept.dart
//
// Requires: a booted simulator/emulator (integration_test driver). On
// macOS the iOS simulator is the canonical path (matches Phase 24 / 25
// pattern).

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

const _successOrigin = 'https://app.solvrlabs.com';
const _successPath = '/billing/return-success';
const _expectedSessionId = 'cs_spike_dummy';

const _inlineHtml = '''
<html><body>
<h1>spike-e</h1>
<a id="go" href="$_successOrigin$_successPath?session_id=$_expectedSessionId">click</a>
<script>setTimeout(function(){document.getElementById('go').click();}, 250);</script>
</body></html>
''';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('shouldOverrideUrlLoading intercepts success URL', (tester) async {
    final completer = Completer<Uri>();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InAppWebView(
            initialData: InAppWebViewInitialData(data: _inlineHtml),
            initialSettings: InAppWebViewSettings(
              // shouldOverrideUrlLoading is not called for the very first
              // page load by default; this flag forces the callback to
              // run on every navigation including the initial load.
              useShouldOverrideUrlLoading: true,
              javaScriptEnabled: true,
            ),
            shouldOverrideUrlLoading: (controller, navigationAction) async {
              final uri = navigationAction.request.url;
              if (uri == null) {
                return NavigationActionPolicy.ALLOW;
              }
              // The data: URL itself triggers a callback first; ignore it
              // and let it through. Only the click-driven HTTPS navigation
              // is the assertion target.
              if (uri.scheme != 'https') {
                return NavigationActionPolicy.ALLOW;
              }
              if (uri.host == 'app.solvrlabs.com' &&
                  uri.path == _successPath &&
                  uri.queryParameters['session_id'] == _expectedSessionId &&
                  !completer.isCompleted) {
                completer.complete(uri);
              }
              // CANCEL prevents the webview from actually fetching the
              // (non-existent) success URL — Wave 6 will route to the
              // app's billing-result screen here.
              return NavigationActionPolicy.CANCEL;
            },
          ),
        ),
      ),
    );

    // Pump frames until the in-page setTimeout fires the click + the
    // navigation-delegate completes. 10s budget mirrors Wave 6's worst-case
    // Checkout-redirect timing.
    final deadline = DateTime.now().add(const Duration(seconds: 10));
    while (!completer.isCompleted && DateTime.now().isBefore(deadline)) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(completer.isCompleted, isTrue,
        reason: 'shouldOverrideUrlLoading did not fire within 10s — '
            'flutter_inappwebview navigation-delegate API surface is NOT '
            'what AMD-03 promises');
    final hit = await completer.future;
    expect(hit.host, 'app.solvrlabs.com');
    expect(hit.path, _successPath);
    expect(hit.queryParameters['session_id'], _expectedSessionId);

    // ignore: avoid_print
    print('PASS spike-e');
  });
}
