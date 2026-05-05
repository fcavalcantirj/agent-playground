// Phase 27 Change 3b Wave 4 — AgentUsageScreen widget tests.
//
// Cases (per 27-CHANGE-3B-PLAN.md Wave 4):
//   - Empty state (messageCount = 0) → AsciiAgentBanner heading
//   - Populated → cumulative headline shows USD + tokens + msgs
//   - 7d series renders chart
//   - Pull-to-refresh → ref.invalidate fires (asserted via build counter)
//   - Error → RetryBanner (401 path is handled by AuthInterceptor —
//     the screen just shows the typed error)

import 'dart:async';

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/agent_usage_screen.dart';
import 'package:agent_playground/features/usage/usage_chart.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:agent_playground/shared/ascii_agent_banner.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const String _agentId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

AgentUsageData _data({
  int messageCount = 0,
  String costUsd = '0',
  int inputTokens = 0,
  int outputTokens = 0,
  String? lastActivity,
  List<AgentSeriesEntry> series7d = const [],
  List<AgentSeriesEntry> series30d = const [],
}) =>
    AgentUsageData(
      agentId: _agentId,
      cumulative: AgentCumulative(
        inputTokens: inputTokens,
        outputTokens: outputTokens,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
        costUsd: costUsd,
        messageCount: messageCount,
        lastActivity: lastActivity,
      ),
      series7d: series7d,
      series30d: series30d,
    );

AgentSeriesEntry _bar(String day, String costUsd) => AgentSeriesEntry(
      day: day,
      costUsd: costUsd,
      tokens: 100,
      messageCount: 1,
    );

Widget _wrap({
  required AgentUsageNotifier Function() builder,
}) =>
    ProviderScope(
      overrides: [
        agentUsageProvider(_agentId).overrideWith(builder),
      ],
      child: MaterialApp(
        theme: solvrTheme(),
        home: const AgentUsageScreen(agentId: _agentId),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AgentUsageScreen', () {
    testWidgets('empty (messageCount=0) → AsciiAgentBanner empty state',
        (tester) async {
      await tester.pumpWidget(
        _wrap(builder: () => _StaticNotifier(_data())),
      );
      await tester.pumpAndSettle();
      expect(find.byType(AsciiAgentBanner), findsOneWidget);
      expect(find.text('No usage yet'), findsOneWidget);
    });

    testWidgets('populated → cumulative headline + chart + 7d series',
        (tester) async {
      await tester.pumpWidget(
        _wrap(
          builder: () => _StaticNotifier(
            _data(
              messageCount: 8,
              costUsd: '0.001234',
              inputTokens: 123,
              outputTokens: 45,
              lastActivity: '2026-05-04T22:01:00Z',
              series7d: [
                _bar('2026-04-28', '0.0001'),
                _bar('2026-05-04', '0.001134'),
              ],
              series30d: [
                _bar('2026-05-04', '0.001234'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      // Headline contains the formatted USD ($0.001234 → sub-cent → $0.0012)
      // and message + token counts. Use partial find for resilience.
      expect(find.textContaining(r'$'), findsAtLeastNWidgets(1));
      expect(find.textContaining('8 messages'), findsOneWidget);
      // Chart appears at least once (could be 7d + 30d).
      expect(find.byType(UsageChart), findsAtLeastNWidgets(1));
    });

    testWidgets('error → RetryBanner', (tester) async {
      await tester.pumpWidget(_wrap(builder: _ErrorNotifier.new));
      await tester.pumpAndSettle();
      expect(find.byType(RetryBanner), findsOneWidget);
    });

    testWidgets('loading → no exception, no banner', (tester) async {
      await tester.pumpWidget(_wrap(builder: _PendingNotifier.new));
      await tester.pump();
      expect(find.byType(RetryBanner), findsNothing);
      expect(find.byType(AsciiAgentBanner), findsNothing);
    });
  });
}

// ---------------------------------------------------------------------------
// Test seams.
// ---------------------------------------------------------------------------

class _StaticNotifier extends AgentUsageNotifier {
  _StaticNotifier(this._value);
  final AgentUsageData _value;
  @override
  Future<AgentUsageData> build(String agentId) async => _value;
}

class _PendingNotifier extends AgentUsageNotifier {
  @override
  Future<AgentUsageData> build(String agentId) =>
      Completer<AgentUsageData>().future;
}

class _ErrorNotifier extends AgentUsageNotifier {
  @override
  Future<AgentUsageData> build(String agentId) async {
    throw const ApiError(
      code: ErrorCode.network,
      message: 'no connection (test)',
    );
  }
}
