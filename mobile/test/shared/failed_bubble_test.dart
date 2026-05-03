// Phase 25 Wave 1 D-44 — FailedBubble widget unit tests.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/failed_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(
        home: Scaffold(body: SizedBox(width: 400, child: child)),
      );

  testWidgets('assistant role aligns left', (tester) async {
    await tester.pumpWidget(
      wrap(
        FailedBubble(
          role: 'assistant',
          content: 'oops',
          onRetry: () {},
          onCopyError: () {},
        ),
      ),
    );
    final align = tester.widget<Align>(find.byType(Align).first);
    expect(align.alignment, Alignment.centerLeft);
  });

  testWidgets('user role aligns right', (tester) async {
    await tester.pumpWidget(
      wrap(
        FailedBubble(
          role: 'user',
          content: 'oops',
          onRetry: () {},
          onCopyError: () {},
        ),
      ),
    );
    final align = tester.widget<Align>(find.byType(Align).first);
    expect(align.alignment, Alignment.centerRight);
  });

  testWidgets('renders 2px destructive border + ⚠ icon + content',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        FailedBubble(
          role: 'assistant',
          content: 'oops error',
          onRetry: () {},
          onCopyError: () {},
        ),
      ),
    );
    final bubble = tester.widget<Container>(find.byType(Container).first);
    final dec = bubble.decoration! as BoxDecoration;
    final border = dec.border! as Border;
    expect(border.top.width, 2);
    expect(border.top.color, SolvrColors.destructive);
    expect(find.byIcon(Icons.warning_rounded), findsOneWidget);
    expect(find.text('oops error'), findsOneWidget);
  });

  testWidgets('tap → modal sheet with Retry + Copy error', (tester) async {
    var retried = false;
    var copied = false;
    await tester.pumpWidget(
      wrap(
        FailedBubble(
          role: 'assistant',
          content: 'oops',
          onRetry: () => retried = true,
          onCopyError: () => copied = true,
        ),
      ),
    );

    await tester.tap(find.byType(GestureDetector));
    await tester.pumpAndSettle();
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Copy error'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(retried, isTrue);
    expect(copied, isFalse);
  });

  testWidgets('Copy error tile fires onCopyError', (tester) async {
    var copied = false;
    await tester.pumpWidget(
      wrap(
        FailedBubble(
          role: 'assistant',
          content: 'oops',
          onRetry: () {},
          onCopyError: () => copied = true,
        ),
      ),
    );
    await tester.tap(find.byType(GestureDetector));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Copy error'));
    await tester.pumpAndSettle();
    expect(copied, isTrue);
  });
}
