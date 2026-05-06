// Phase 28 Plan 08 — UsageTickerWidget navigation-safety test.
//
// Reproduces the Phase 27 defunct-element scenario that yanked the
// AppBar ticker:
//
//   1. Mount a Dashboard-shaped Scaffold with the ticker in the AppBar's
//      actions array (Consumer-wrapped, mirroring Plan 08 Task 1).
//   2. Push a Chat-shaped Scaffold that ALSO mounts the ticker.
//   3. Pop back to Dashboard.
//
// The expected outcome with the Consumer-scoped subscription pattern is
// `tester.takeException()` returning null after each pump cycle —
// the Consumer's Element gets disposed cleanly when the AppBar tears
// down so the provider subscription's lifetime is bound to that
// Consumer (not the surrounding ConsumerStatefulWidget). If the test
// regressed to the Phase 27 direct-mount pattern, the framework would
// surface a `Failed assertion: _lifecycleState != _ElementLifecycle.defunct`
// from the Element tree during the second pump.
//
// We don't mount the real DashboardScreen / ChatScreen — they pull in
// agentsListProvider, recipesProvider, auth, secure storage, GoRouter,
// SSE, etc., which would require a wide ProviderScope override surface
// not relevant to what this test is trying to prove. Stub screens with
// the same AppBar shape are sufficient: the race is structural in the
// Consumer-scoped pattern, not in any DashboardScreen / ChatScreen
// business logic.

import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:agent_playground/features/usage/usage_ticker_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'UsageTickerWidget survives Dashboard → Chat → Dashboard navigation '
    'without defunct-element exception',
    (tester) async {
      const summary = UsageSummary(
        totalUsd: '0.05',
        messageCount: 1,
        byAgent: <AgentBreakdownEntry>[],
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(() => _StaticNotifier(summary)),
          ],
          child: const MaterialApp(
            home: _DashboardStub(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Sanity — the ticker is mounted in the Dashboard AppBar.
      expect(find.byType(UsageTickerWidget), findsOneWidget);
      expect(tester.takeException(), isNull);

      // Push the Chat stub.
      await tester.tap(find.text('Open Chat'));
      await tester.pumpAndSettle();
      // Now the Chat AppBar is on top; its ticker is the visible one.
      expect(find.byType(UsageTickerWidget), findsOneWidget);
      expect(tester.takeException(), isNull);

      // Pop back to Dashboard via the back button.
      final BuildContext ctx = tester.element(find.byType(UsageTickerWidget));
      Navigator.of(ctx).pop();
      await tester.pumpAndSettle();
      expect(find.byType(UsageTickerWidget), findsOneWidget);

      // Critical assertion — if the Consumer-scoped pattern regressed to
      // a direct ConsumerWidget mount, the provider subscription's
      // Element would still be referenced after the AppBar tear-down
      // and Flutter would surface
      //   `Failed assertion: _lifecycleState != _ElementLifecycle.defunct`
      // here. With the Consumer wrapper there is no such exception.
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'rapid back-and-forth Dashboard ↔ Chat does not surface a '
    'defunct-element exception',
    (tester) async {
      const summary = UsageSummary(
        totalUsd: '0.05',
        messageCount: 1,
        byAgent: <AgentBreakdownEntry>[],
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(() => _StaticNotifier(summary)),
          ],
          child: const MaterialApp(
            home: _DashboardStub(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Three round-trips simulating a user bouncing between screens.
      for (var i = 0; i < 3; i++) {
        await tester.tap(find.text('Open Chat'));
        await tester.pumpAndSettle();
        final BuildContext ctx =
            tester.element(find.byType(UsageTickerWidget));
        Navigator.of(ctx).pop();
        await tester.pumpAndSettle();
        expect(
          tester.takeException(),
          isNull,
          reason:
              'iteration $i — Consumer-scoped subscription must not '
              'leak past AppBar tear-down',
        );
      }
    },
  );
}

// ---------------------------------------------------------------------------
// Stub screens — mirror the Consumer-wrapped mount pattern from Plan 08
// Task 1 in dashboard_screen.dart and chat_screen.dart so the test
// exercises the same Element graph shape that ships in production.
// ---------------------------------------------------------------------------

class _DashboardStub extends StatelessWidget {
  const _DashboardStub();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          // Same Consumer wrapper as dashboard_screen.dart.
          Consumer(
            builder: (context, ref, _) => const UsageTickerWidget(),
          ),
        ],
      ),
      body: Center(
        child: ElevatedButton(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute<void>(builder: (_) => const _ChatStub()),
          ),
          child: const Text('Open Chat'),
        ),
      ),
    );
  }
}

class _ChatStub extends StatelessWidget {
  const _ChatStub();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat'),
        actions: [
          // Same Consumer wrapper as chat_screen.dart.
          Consumer(
            builder: (context, ref, _) => const UsageTickerWidget(),
          ),
        ],
      ),
      body: const Center(child: Text('chat body')),
    );
  }
}

// ---------------------------------------------------------------------------
// Test seam — synchronous override for usageSummaryProvider, mirroring
// the pattern in usage_ticker_widget_test.dart.
// ---------------------------------------------------------------------------

class _StaticNotifier extends UsageSummaryNotifier {
  _StaticNotifier(this._value);
  final UsageSummary _value;

  @override
  Future<UsageSummary> build() async => _value;
}
