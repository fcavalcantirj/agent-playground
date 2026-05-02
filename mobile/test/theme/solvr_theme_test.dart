// Phase 24 Plan 02 — APP-02 invariants.
//
// All tests are `testWidgets` (not plain `test`) so the WidgetTester binding
// can flush google_fonts' fire-and-forget `loadFontIfNecessary` future via
// `tester.pumpAndSettle()` before each test completes — otherwise the
// runtime-fetch failure (no network in unit tests) lands as
// "test failed after it had already completed". Pitfall #6 in
// `.planning/phases/24-flutter-foundation/24-RESEARCH.md`.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<ThemeData> _bootTheme(WidgetTester tester) async {
  final theme = solvrTheme();
  await tester.pumpWidget(
    MaterialApp(theme: theme, home: const SizedBox()),
  );
  await tester.pumpAndSettle();
  return theme;
}

void main() {
  group('solvrTheme — APP-02', () {
    testWidgets('scaffold background is #FAFAF7 (CONTEXT line 139)',
        (tester) async {
      final theme = await _bootTheme(tester);
      expect(theme.scaffoldBackgroundColor, const Color(0xFFFAFAF7));
    });

    testWidgets('primary is #1F1F1F (CONTEXT line 139)', (tester) async {
      final theme = await _bootTheme(tester);
      expect(theme.colorScheme.primary, const Color(0xFF1F1F1F));
      expect(theme.colorScheme.onPrimary, const Color(0xFFFAFAF7));
    });

    testWidgets('card shape is BorderRadius.zero', (tester) async {
      final theme = await _bootTheme(tester);
      final shape = theme.cardTheme.shape! as RoundedRectangleBorder;
      expect(shape.borderRadius, BorderRadius.zero);
    });

    testWidgets('elevated button shape is BorderRadius.zero', (tester) async {
      final theme = await _bootTheme(tester);
      final style = theme.elevatedButtonTheme.style!;
      final shape =
          style.shape!.resolve(<WidgetState>{})! as RoundedRectangleBorder;
      expect(shape.borderRadius, BorderRadius.zero);
    });

    testWidgets('outlined button shape is BorderRadius.zero', (tester) async {
      final theme = await _bootTheme(tester);
      final style = theme.outlinedButtonTheme.style!;
      final shape =
          style.shape!.resolve(<WidgetState>{})! as RoundedRectangleBorder;
      expect(shape.borderRadius, BorderRadius.zero);
    });

    testWidgets(
      'SolvrTextStyles.mono returns a TextStyle wired to JetBrainsMono',
      (tester) async {
        // pumpWidget first so the binding is ready before
        // SolvrTextStyles.mono calls GoogleFonts.jetBrainsMono.
        await tester.pumpWidget(const MaterialApp(home: SizedBox()));
        final style = SolvrTextStyles.mono(fontSize: 14);
        await tester.pumpAndSettle();
        expect(style.fontFamily, isNotNull);
        // google_fonts prefixes the fontFamily with the family name; matches
        // both bundled-asset and runtime-fetch paths.
        expect(style.fontFamily, contains('JetBrainsMono'));
      },
    );

    testWidgets('Card rendered through theme has zero corner radius',
        (tester) async {
      final theme = solvrTheme();
      await tester.pumpWidget(
        MaterialApp(
          theme: theme,
          home: const Scaffold(
            body: Card(child: Text('flat')),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('flat'), findsOneWidget);
      final card = tester.widget<Card>(find.byType(Card));
      // Card.shape is null when ThemeData provides it — read via theme:
      final shape =
          (card.shape ?? theme.cardTheme.shape!) as RoundedRectangleBorder;
      expect(shape.borderRadius, BorderRadius.zero);
    });
  });
}
