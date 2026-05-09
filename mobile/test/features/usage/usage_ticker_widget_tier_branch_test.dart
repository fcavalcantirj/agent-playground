// Phase B Plan 12 Task 1 — UsageTickerWidget tier-branched render tests.
//
// Cases (per B-stripe-12-PLAN.md must_haves.truths):
//   - tier='free'  → "$X.YZ" (existing Phase 27 USD path; no balance)
//   - tier='pro'   → "$X.YZ" (same USD path; balance fields absent)
//   - tier='ultra' → "<displayBalanceCents> credits"
//   - tier='ultra' AND isNegative=true → "$0.00 ⚠" + tap-to-explain dialog
//   - UsageSummary.fromJson with NO balance fields (free) → defaults
//   - UsageSummary.fromJson WITH balance fields (ultra) → fields present
//
// Mock at the provider boundary: usageSummaryProvider.overrideWith.
// Phase A regression coverage stays in usage_ticker_widget_test.dart.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:agent_playground/features/usage/usage_ticker_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

UsageSummary _summary({
  required String totalUsd,
  String tier = 'free',
  int? balanceCents,
  int? displayBalanceCents,
  bool? isNegative,
}) =>
    UsageSummary(
      totalUsd: totalUsd,
      messageCount: 0,
      byAgent: const [],
      tier: tier,
      balanceCents: balanceCents,
      displayBalanceCents: displayBalanceCents,
      isNegative: isNegative,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('UsageTickerWidget tier branch', () {
    testWidgets('tier="free" → renders USD ticker (existing path)',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(_summary(totalUsd: '0.42')),
            ),
          ],
          child: MaterialApp(
            theme: solvrTheme(),
            home: Scaffold(
              appBar: AppBar(actions: const [UsageTickerWidget()]),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$0.42'), findsOneWidget);
      expect(find.textContaining('credits'), findsNothing);
    });

    testWidgets('tier="pro" → renders USD ticker (existing path)',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(
                _summary(totalUsd: '12.34', tier: 'pro'),
              ),
            ),
          ],
          child: MaterialApp(
            theme: solvrTheme(),
            home: Scaffold(
              appBar: AppBar(actions: const [UsageTickerWidget()]),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$12.34'), findsOneWidget);
      expect(find.textContaining('credits'), findsNothing);
    });

    testWidgets('tier="ultra" → renders "<displayBalanceCents> credits"',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(
                _summary(
                  totalUsd: '0.0',
                  tier: 'ultra',
                  balanceCents: 1234,
                  displayBalanceCents: 1234,
                  isNegative: false,
                ),
              ),
            ),
          ],
          child: MaterialApp(
            theme: solvrTheme(),
            home: Scaffold(
              appBar: AppBar(actions: const [UsageTickerWidget()]),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('1234 credits'), findsOneWidget);
      expect(find.text(r'$0.0'), findsNothing);
    });

    testWidgets(
        'tier="ultra" AND isNegative=true → "\$0.00 ⚠" + tap opens dialog',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(
                _summary(
                  totalUsd: '0.0',
                  tier: 'ultra',
                  balanceCents: -250,
                  displayBalanceCents: 0,
                  isNegative: true,
                ),
              ),
            ),
          ],
          child: MaterialApp(
            theme: solvrTheme(),
            home: Scaffold(
              appBar: AppBar(actions: const [UsageTickerWidget()]),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(r'$0.00 ⚠'), findsOneWidget);
      // Tap surfaces the explainer dialog.
      await tester.tap(find.byType(UsageTickerWidget));
      await tester.pumpAndSettle();
      expect(find.text('Negative balance'), findsOneWidget);
      // Close the dialog so the test teardown is clean.
      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
    });

    testWidgets(
        'tier="ultra" with balance=0 (not negative) → "0 credits"',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            usageSummaryProvider.overrideWith(
              () => _StaticNotifier(
                _summary(
                  totalUsd: '0.0',
                  tier: 'ultra',
                  balanceCents: 0,
                  displayBalanceCents: 0,
                  isNegative: false,
                ),
              ),
            ),
          ],
          child: MaterialApp(
            theme: solvrTheme(),
            home: Scaffold(
              appBar: AppBar(actions: const [UsageTickerWidget()]),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('0 credits'), findsOneWidget);
    });
  });

  group('UsageSummary.fromJson tier projection', () {
    test('free user — no balance fields → tier="free", null balances', () {
      final s = UsageSummary.fromJson({
        'total_usd': '1.23',
        'message_count': 4,
        'by_agent': const <dynamic>[],
        'tier': 'free',
      });
      expect(s.tier, 'free');
      expect(s.balanceCents, isNull);
      expect(s.displayBalanceCents, isNull);
      expect(s.isNegative, isNull);
    });

    test('ultra user — balance fields present → projected', () {
      final s = UsageSummary.fromJson({
        'total_usd': '0',
        'message_count': 0,
        'by_agent': const <dynamic>[],
        'tier': 'ultra',
        'balance_cents': 1234,
        'display_balance_cents': 1234,
        'is_negative': false,
      });
      expect(s.tier, 'ultra');
      expect(s.balanceCents, 1234);
      expect(s.displayBalanceCents, 1234);
      expect(s.isNegative, isFalse);
    });

    test('legacy payload without tier → defaults to "free"', () {
      // Phase A regression: the existing Phase 27 contract must still
      // hydrate when the server is rolled back to a pre-Phase-B build.
      final s = UsageSummary.fromJson({
        'total_usd': '0.5',
        'message_count': 1,
        'by_agent': const <dynamic>[],
      });
      expect(s.tier, 'free');
      expect(s.balanceCents, isNull);
      expect(s.totalUsd, '0.5');
    });
  });
}

// ---------------------------------------------------------------------------
// Test seam — concrete notifier override for ProviderScope.
// ---------------------------------------------------------------------------

class _StaticNotifier extends UsageSummaryNotifier {
  _StaticNotifier(this._value);
  final UsageSummary _value;
  @override
  Future<UsageSummary> build() async => _value;
}
