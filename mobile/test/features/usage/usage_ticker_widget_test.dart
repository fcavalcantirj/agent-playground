// Phase 27 Change 3b Wave 3 — UsageTickerWidget tests.
//
// Cases (per 27-CHANGE-3B-PLAN.md Wave 3):
//   - Loading state → renders the muted "$ —" placeholder
//   - Loaded $0.0034 (sub-cent) → mono font + chevron
//   - Loaded $1.23 (dollar)
//   - Error → muted "$ —" fallback (still tappable, but the breakdown
//     screen handles real error UX)
//   - Tap → navigates (verified via a mocked GoRouter that records the
//     last `push` target)
//
// Mock at the provider boundary: usageSummaryProvider.overrideWith.
// Mocking via http_mock_adapter would also work but pumping the
// AsyncNotifier through a real Dio for a widget test is needless
// indirection — Wave 2's transport tests already cover the wire layer.

import 'dart:async';

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:agent_playground/features/usage/usage_ticker_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

UsageSummary _summary({
  required String totalUsd,
  List<AgentBreakdownEntry> byAgent = const [],
}) =>
    UsageSummary(totalUsd: totalUsd, messageCount: 0, byAgent: byAgent);

AgentBreakdownEntry _entry(String id) => AgentBreakdownEntry(
      agentId: id,
      agentName: 'agent-$id',
      recipeName: 'hermes',
      model: 'anthropic/claude-haiku-4-5',
      costUsd: '0.001',
      messageCount: 1,
    );

Widget _wrap({
  required ProviderScope scope,
}) =>
    MaterialApp(theme: solvrTheme(), home: scope);

GoRouter _captureRouter({required ValueChanged<String> onPush}) => GoRouter(
      initialLocation: '/host',
      routes: [
        GoRoute(
          path: '/host',
          builder: (context, _) => Scaffold(
            appBar: AppBar(actions: const [UsageTickerWidget()]),
            body: const SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '/agents/:id/usage',
          builder: (context, state) {
            // Record the push target so the test can assert on it.
            onPush(state.uri.toString());
            return const Scaffold(body: Text('breakdown-target'));
          },
        ),
      ],
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('UsageTickerWidget', () {
    testWidgets('loading → muted "\$ —" placeholder', (tester) async {
      await tester.pumpWidget(
        _wrap(
          scope: ProviderScope(
            overrides: [
              usageSummaryProvider.overrideWith(_NeverResolveNotifier.new),
            ],
            child: MaterialApp(
              theme: solvrTheme(),
              home: Scaffold(
                appBar: AppBar(actions: const [UsageTickerWidget()]),
              ),
            ),
          ),
        ),
      );
      // Don't pumpAndSettle — the AsyncNotifier never resolves.
      await tester.pump();
      expect(find.text(r'$ —'), findsOneWidget);
    });

    testWidgets('loaded sub-cent → "\$0.0034" + chevron', (tester) async {
      await tester.pumpWidget(
        _wrap(
          scope: ProviderScope(
            overrides: [
              usageSummaryProvider
                  .overrideWith(() => _StaticNotifier(_summary(totalUsd: '0.0034'))),
            ],
            child: MaterialApp(
              theme: solvrTheme(),
              home: Scaffold(
                appBar: AppBar(actions: const [UsageTickerWidget()]),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$0.0034'), findsOneWidget);
      expect(find.byIcon(Icons.chevron_right), findsOneWidget);
    });

    testWidgets('loaded dollar value → "\$1.23"', (tester) async {
      await tester.pumpWidget(
        _wrap(
          scope: ProviderScope(
            overrides: [
              usageSummaryProvider
                  .overrideWith(() => _StaticNotifier(_summary(totalUsd: '1.23'))),
            ],
            child: MaterialApp(
              theme: solvrTheme(),
              home: Scaffold(
                appBar: AppBar(actions: const [UsageTickerWidget()]),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$1.23'), findsOneWidget);
    });

    testWidgets('error → muted "\$ —" fallback', (tester) async {
      await tester.pumpWidget(
        _wrap(
          scope: ProviderScope(
            overrides: [
              usageSummaryProvider.overrideWith(_ErrorNotifier.new),
            ],
            child: MaterialApp(
              theme: solvrTheme(),
              home: Scaffold(
                appBar: AppBar(actions: const [UsageTickerWidget()]),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$ —'), findsOneWidget);
    });

    testWidgets(
        'tap → pushes /agents/:id/usage when byAgent has at least one row',
        (tester) async {
      String? lastPush;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(
                _summary(
                  totalUsd: '0.05',
                  byAgent: [_entry('11111111-1111-1111-1111-111111111111')],
                ),
              ),
            ),
          ],
          child: MaterialApp.router(
            theme: solvrTheme(),
            routerConfig: _captureRouter(onPush: (target) => lastPush = target),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(UsageTickerWidget));
      await tester.pumpAndSettle();
      expect(
        lastPush,
        '/agents/11111111-1111-1111-1111-111111111111/usage',
      );
    });

    testWidgets('tap is a no-op when byAgent is empty', (tester) async {
      String? lastPush;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(_summary(totalUsd: '0')),
            ),
          ],
          child: MaterialApp.router(
            theme: solvrTheme(),
            routerConfig: _captureRouter(onPush: (target) => lastPush = target),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(UsageTickerWidget));
      await tester.pumpAndSettle();
      expect(lastPush, isNull, reason: 'no agents → tap must not navigate');
    });
  });
}

// ---------------------------------------------------------------------------
// Test seams — concrete notifier overrides for ProviderScope.
// ---------------------------------------------------------------------------

class _StaticNotifier extends UsageSummaryNotifier {
  _StaticNotifier(this._value);
  final UsageSummary _value;
  @override
  Future<UsageSummary> build() async => _value;
}

class _NeverResolveNotifier extends UsageSummaryNotifier {
  @override
  Future<UsageSummary> build() {
    // Forever-pending future — exercises the loading state.
    return Completer<UsageSummary>().future;
  }
}

class _ErrorNotifier extends UsageSummaryNotifier {
  @override
  Future<UsageSummary> build() async {
    throw const ApiError(
      code: ErrorCode.network,
      message: 'no connection (test)',
    );
  }
}
