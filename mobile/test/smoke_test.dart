// Phase 24 Plan 01 — smoke test. Proves the scaffold compiles and the root
// widget renders. Wave 2/3 plans add real theme + Result + interceptor tests.

import 'package:agent_playground/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('SolvrLabsApp renders without throwing', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolvrLabsApp()));
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsOneWidget);
  });
}
