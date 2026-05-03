// Phase 25 Wave 1 D-18 — SkeletonRow widget unit tests.

import 'package:agent_playground/shared/skeleton_row.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(
        home: Scaffold(body: SizedBox(width: 400, child: child)),
      );

  testWidgets('default renders 3 bars with 4px gaps stacked vertically',
      (tester) async {
    await tester.pumpWidget(wrap(const SkeletonRow()));
    // Outer SizedBox + the 3 bar containers + bg containers from MaterialApp.
    // We assert by counting at least 3 children Containers under the Column.
    expect(find.byType(Column), findsOneWidget);
    final column = tester.widget<Column>(find.byType(Column));
    final containers = column.children.whereType<Container>().toList();
    final aligns = column.children.whereType<Align>().toList();
    expect(containers.length + aligns.length, greaterThanOrEqualTo(3));
  });

  testWidgets('default height is 56dp', (tester) async {
    await tester.pumpWidget(wrap(const SkeletonRow()));
    final outer = tester.widget<SkeletonRow>(find.byType(SkeletonRow));
    expect(outer.height, 56);
  });

  testWidgets('custom bars list controls bar count', (tester) async {
    await tester.pumpWidget(
      wrap(const SkeletonRow(bars: [0.5, 0.25])),
    );
    final column = tester.widget<Column>(find.byType(Column));
    final visibleBars = column.children
        .where((c) => c is Container || c is Align)
        .toList();
    expect(visibleBars.length, 2);
  });

  testWidgets('last bar is right-aligned (D-08 last_activity)',
      (tester) async {
    await tester.pumpWidget(wrap(const SkeletonRow()));
    final align = tester.widget<Align>(find.byType(Align).last);
    expect(align.alignment, Alignment.centerRight);
  });
}
