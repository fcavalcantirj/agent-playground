// Phase 25 Wave 1 D-49 — RestartBanner widget unit tests.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/restart_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('default message is "⚠ Agent stopped"', (tester) async {
    await tester.pumpWidget(wrap(RestartBanner(onRestart: () {})));
    expect(find.text('\u26A0 Agent stopped'), findsOneWidget);
  });

  testWidgets('renders Restart button and fires onRestart', (tester) async {
    var restarted = false;
    await tester.pumpWidget(
      wrap(RestartBanner(onRestart: () => restarted = true)),
    );
    await tester.tap(find.text('Restart'));
    await tester.pump();
    expect(restarted, isTrue);
  });

  testWidgets('background is muted with 1px top border #DEDEDA',
      (tester) async {
    await tester.pumpWidget(wrap(RestartBanner(onRestart: () {})));
    final container = tester.widget<Container>(find.byType(Container).first);
    final dec = container.decoration! as BoxDecoration;
    expect(dec.color, SolvrColors.muted);
    final border = dec.border! as Border;
    expect(border.top.color, SolvrColors.border);
    expect(border.top.width, 1);
  });

  testWidgets('custom message replaces default', (tester) async {
    await tester.pumpWidget(
      wrap(RestartBanner(onRestart: () {}, message: 'CUSTOM')),
    );
    expect(find.text('CUSTOM'), findsOneWidget);
    expect(find.text('\u26A0 Agent stopped'), findsNothing);
  });

  testWidgets('banner is full-width with 48dp min height', (tester) async {
    await tester.pumpWidget(wrap(RestartBanner(onRestart: () {})));
    final container = tester.widget<Container>(find.byType(Container).first);
    expect(container.constraints?.minHeight, 48);
  });
}
