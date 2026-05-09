// Phase B Plan 11 Task 1 — InsufficientCreditsModal widget tests.
//
// Cases (per PLAN <behavior>):
//   - test_insufficient_credits_modal_is_barrier_dismissible_false
//   - test_insufficient_credits_modal_top_up_cta_pushes_to_billing_topup_route
//   - test_insufficient_credits_modal_later_cta_dismisses
//
// We host a tiny GoRouter with two routes — `/` carries a button
// that fires `showInsufficientCreditsModal`, `/billing/topup` is a
// plain Scaffold with a known label so we can assert the navigation
// landed there.

import 'package:agent_playground/features/billing/insufficient_credits_modal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

GoRouter _router() => GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => const _Host(),
        ),
        GoRoute(
          path: '/billing/topup',
          builder: (_, _) => const Scaffold(
            body: Text('TOP_UP_LANDED'),
          ),
        ),
      ],
    );

class _Host extends StatelessWidget {
  const _Host();
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Builder(
          builder: (ctx) => ElevatedButton(
            onPressed: () => showInsufficientCreditsModal(ctx),
            child: const Text('TRIGGER'),
          ),
        ),
      ),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('showInsufficientCreditsModal', () {
    testWidgets('is barrierDismissible: false (tap outside does not dismiss)',
        (tester) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('TRIGGER'));
      await tester.pumpAndSettle();

      expect(find.text('Out of balance'), findsOneWidget);

      // Tap the barrier (top-left corner, far from the dialog content).
      await tester.tapAt(const Offset(10, 10));
      await tester.pumpAndSettle();

      // Modal still present.
      expect(find.text('Out of balance'), findsOneWidget);
    });

    testWidgets('Top up CTA pushes to /billing/topup', (tester) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('TRIGGER'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Top up'));
      await tester.pumpAndSettle();

      // Landed on the topup stub route.
      expect(find.text('TOP_UP_LANDED'), findsOneWidget);
      expect(find.text('Out of balance'), findsNothing);
    });

    testWidgets('Later CTA dismisses', (tester) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('TRIGGER'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Later'));
      await tester.pumpAndSettle();

      expect(find.text('Out of balance'), findsNothing);
      // Still on the host route (TRIGGER button visible again).
      expect(find.text('TRIGGER'), findsOneWidget);
    });
  });
}
