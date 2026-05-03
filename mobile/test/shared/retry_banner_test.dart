// Phase 25 Wave 1 D-19/D-50 — RetryBanner widget unit tests.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('muted tone has muted bg and no warning glyph', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      wrap(
        RetryBanner(
          message: "Couldn't refresh",
          actionLabel: 'Tap to retry',
          onTap: () => tapped = true,
        ),
      ),
    );
    final container = tester.widget<Container>(find.byType(Container).first);
    expect(container.color, SolvrColors.muted);
    expect(find.text('\u26A0'), findsNothing);

    await tester.tap(find.text('Tap to retry'));
    await tester.pump();
    expect(tapped, isTrue);
  });

  testWidgets('warning tone shows ⚠ glyph prefix on muted bg',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        RetryBanner(
          message: 'Telegram setup failed',
          actionLabel: 'Retry',
          onTap: () {},
          tone: RetryBannerTone.warning,
        ),
      ),
    );
    expect(find.text('\u26A0'), findsOneWidget);
    final container = tester.widget<Container>(find.byType(Container).first);
    expect(container.color, SolvrColors.muted);
  });

  testWidgets('dismissible renders × icon and fires onDismiss',
      (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      wrap(
        RetryBanner(
          message: 'm',
          actionLabel: 'Retry',
          onTap: () {},
          dismissible: true,
          onDismiss: () => dismissed = true,
        ),
      ),
    );
    expect(find.byIcon(Icons.close), findsOneWidget);
    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();
    expect(dismissed, isTrue);
  });

  testWidgets('non-dismissible omits the × icon', (tester) async {
    await tester.pumpWidget(
      wrap(
        RetryBanner(
          message: 'm',
          actionLabel: 'Retry',
          onTap: () {},
        ),
      ),
    );
    expect(find.byIcon(Icons.close), findsNothing);
  });

  testWidgets('banner is full-width with min 48dp height', (tester) async {
    await tester.pumpWidget(
      wrap(
        RetryBanner(
          message: 'm',
          actionLabel: 'Retry',
          onTap: () {},
        ),
      ),
    );
    final container = tester.widget<Container>(find.byType(Container).first);
    expect(container.constraints?.minHeight, 48);
  });
}
