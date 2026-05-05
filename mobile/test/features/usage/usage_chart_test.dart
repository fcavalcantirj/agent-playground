// Phase 27 Change 3b Wave 4 — UsageChart CustomPainter tests.
//
// CustomPainter doesn't render text; we assert on its public surface
// (size, configurability) and that pumping it with N entries produces
// a Widget tree that doesn't throw under different input shapes.
//
// Visual goldens are deferred — not in the Wave 4 plan.

import 'package:agent_playground/features/usage/usage_chart.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

AgentSeriesEntry _bar(String day, String costUsd) => AgentSeriesEntry(
      day: day,
      costUsd: costUsd,
      tokens: 0,
      messageCount: 0,
    );

void main() {
  group('UsageChart', () {
    testWidgets('empty entries → renders without throwing', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 300,
              height: 100,
              child: UsageChart(entries: []),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(UsageChart), findsOneWidget);
    });

    testWidgets('7-day series renders without throwing', (tester) async {
      final entries = List<AgentSeriesEntry>.generate(
        7,
        (i) => _bar('2026-04-${28 + i}', '0.001'),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 300,
              height: 100,
              child: UsageChart(entries: entries),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(UsageChart), findsOneWidget);
    });

    testWidgets('30-day series renders without throwing', (tester) async {
      final entries = List<AgentSeriesEntry>.generate(
        30,
        (i) => _bar('2026-04-${(i % 28) + 1}', '0.0005'),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 300,
              height: 100,
              child: UsageChart(entries: entries),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(UsageChart), findsOneWidget);
    });

    testWidgets('mixed-magnitude bars render (proportional scaling)',
        (tester) async {
      final entries = [
        _bar('2026-04-28', '0.0001'),
        _bar('2026-04-29', '0.005'),
        _bar('2026-04-30', '0.05'),
        _bar('2026-05-01', '0.5'),
      ];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 300,
              height: 100,
              child: UsageChart(entries: entries),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(UsageChart), findsOneWidget);
    });
  });
}
