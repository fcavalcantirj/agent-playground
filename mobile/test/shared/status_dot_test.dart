// Phase 25 Wave 1 D-14 — StatusDot widget unit tests.
//
// Per UI-SPEC §Component 1 + plan 25-03 Task 1 behavior list:
// - running   → filled circle #22C55E
// - stopped   → hollow ring 1px #6B6B6B
// - failed    → filled circle #D9333A
// - exited    → same hollow ring as stopped
// - Semantics label per UI-SPEC line 273.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<BoxDecoration> _decorationOf(WidgetTester tester) async {
  final container = tester.widget<Container>(find.byType(Container));
  return container.decoration! as BoxDecoration;
}

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('running renders filled circle with success green',
      (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'running')));
    final dec = await _decorationOf(tester);
    expect(dec.shape, BoxShape.circle);
    expect(dec.color, SolvrColors.success);
    expect(dec.border, isNull);
  });

  testWidgets('stopped renders hollow ring with mutedForeground border',
      (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'stopped')));
    final dec = await _decorationOf(tester);
    // Hollow ring: fill is fully transparent (alpha 0).
    expect(dec.color, equals(const Color(0x00000000)));
    final border = dec.border! as Border;
    expect(border.top.color, SolvrColors.mutedForeground);
    expect(border.top.width, 1);
  });

  testWidgets('exited renders same hollow ring as stopped', (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'exited')));
    final dec = await _decorationOf(tester);
    expect(dec.color, equals(const Color(0x00000000)));
    final border = dec.border! as Border;
    expect(border.top.color, SolvrColors.mutedForeground);
  });

  testWidgets('failed renders filled circle with destructive red',
      (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'failed')));
    final dec = await _decorationOf(tester);
    expect(dec.shape, BoxShape.circle);
    expect(dec.color, SolvrColors.destructive);
  });

  testWidgets('error renders filled circle with destructive red (alias)',
      (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'error')));
    final dec = await _decorationOf(tester);
    expect(dec.color, SolvrColors.destructive);
  });

  testWidgets('Semantics label includes the status value', (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'running')));
    expect(
      find.bySemanticsLabel(RegExp('Agent status: running')),
      findsOneWidget,
    );
  });

  testWidgets('respects custom size', (tester) async {
    await tester.pumpWidget(
      wrap(const StatusDot(status: 'running', size: 16)),
    );
    final container = tester.widget<Container>(find.byType(Container));
    expect(container.constraints?.maxWidth ?? 16, 16);
  });

  testWidgets('unknown status falls back to neutral border', (tester) async {
    await tester.pumpWidget(wrap(const StatusDot(status: 'whatever')));
    final dec = await _decorationOf(tester);
    expect(dec.color, equals(const Color(0x00000000)));
    final border = dec.border! as Border;
    expect(border.top.color, SolvrColors.border);
  });
}
