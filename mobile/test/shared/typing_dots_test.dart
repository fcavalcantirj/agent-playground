// Phase 25 Wave 1 D-41 — TypingDots widget unit tests.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/typing_dots.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('renders 3 dots inside a Row with min-size', (tester) async {
    await tester.pumpWidget(wrap(const TypingDots()));
    final containers = tester.widgetList<Container>(find.byType(Container));
    final dotContainers = containers.where((c) {
      final dec = c.decoration;
      return dec is BoxDecoration && dec.shape == BoxShape.circle;
    }).toList();
    expect(dotContainers.length, 3);
    final row = tester.widget<Row>(find.byType(Row));
    expect(row.mainAxisSize, MainAxisSize.min);
    // Dispose animation cleanly.
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('default color is mutedForeground', (tester) async {
    await tester.pumpWidget(wrap(const TypingDots()));
    final containers = tester.widgetList<Container>(find.byType(Container));
    final dotDeco = containers
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .firstWhere((d) => d.shape == BoxShape.circle);
    expect(dotDeco.color, SolvrColors.mutedForeground);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('custom color overrides default', (tester) async {
    await tester.pumpWidget(
      wrap(const TypingDots(color: Colors.red)),
    );
    final containers = tester.widgetList<Container>(find.byType(Container));
    final dotDeco = containers
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .firstWhere((d) => d.shape == BoxShape.circle);
    expect(dotDeco.color, Colors.red);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('animation runs (opacity changes between frames)',
      (tester) async {
    await tester.pumpWidget(wrap(const TypingDots()));
    final initialOpacity = tester
        .widgetList<Opacity>(find.byType(Opacity))
        .first
        .opacity;
    await tester.pump(const Duration(milliseconds: 600));
    final laterOpacity = tester
        .widgetList<Opacity>(find.byType(Opacity))
        .first
        .opacity;
    expect(laterOpacity, isNot(equals(initialOpacity)));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('each dot is 6×6', (tester) async {
    await tester.pumpWidget(wrap(const TypingDots()));
    final containers = tester
        .widgetList<Container>(find.byType(Container))
        .where(
          (c) {
            final dec = c.decoration;
            return dec is BoxDecoration && dec.shape == BoxShape.circle;
          },
        )
        .toList();
    for (final c in containers) {
      expect(c.constraints?.maxWidth, 6);
      expect(c.constraints?.maxHeight, 6);
    }
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
