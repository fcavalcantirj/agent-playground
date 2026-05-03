// Phase 25 Wave 1 D-17 — EmptyStateScaffold widget unit tests.

import 'package:agent_playground/shared/empty_state_scaffold.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('renders banner + heading + body + primaryAction in order',
      (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      wrap(
        EmptyStateScaffold(
          banner: const Text('BANNER', key: ValueKey('banner')),
          heading: 'No agents yet',
          body: 'Deploy your first agent to get started.',
          primaryAction: EmptyStatePrimaryAction(
            label: 'Deploy your first agent',
            onTap: () => tapped = true,
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('banner')), findsOneWidget);
    expect(find.text('No agents yet'), findsOneWidget);
    expect(
      find.text('Deploy your first agent to get started.'),
      findsOneWidget,
    );
    expect(find.text('Deploy your first agent'), findsOneWidget);

    await tester.tap(find.byType(ElevatedButton));
    await tester.pump();
    expect(tapped, isTrue);
  });

  testWidgets('without primaryAction does not render the button',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        const EmptyStateScaffold(
          heading: 'No agents yet',
          body: 'Deploy your first agent to get started.',
        ),
      ),
    );

    expect(find.text('No agents yet'), findsOneWidget);
    expect(find.byType(ElevatedButton), findsNothing);
  });

  testWidgets('renders heading-only when banner and body absent',
      (tester) async {
    await tester.pumpWidget(
      wrap(const EmptyStateScaffold(heading: 'Just a heading')),
    );
    expect(find.text('Just a heading'), findsOneWidget);
    expect(find.byType(ElevatedButton), findsNothing);
  });

  testWidgets('primary action button is full-width 48dp tall',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        EmptyStateScaffold(
          heading: 'h',
          primaryAction: EmptyStatePrimaryAction(
            label: 'Go',
            onTap: () {},
          ),
        ),
      ),
    );
    final sized = tester.widget<SizedBox>(
      find.ancestor(
        of: find.byType(ElevatedButton),
        matching: find.byType(SizedBox),
      ).first,
    );
    expect(sized.height, 48);
    expect(sized.width, double.infinity);
  });
}
