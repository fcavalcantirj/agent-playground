// Phase 25 Wave 4 plan 25-07 task 3 — Chat markdown golden snapshot.
//
// Skipped at run-time per the same Pitfall #6 / google_fonts handling as
// dashboard_empty_golden_test.dart. Capture command:
//
//   flutter test --update-goldens test/golden/chat_markdown_golden_test.dart
//
// The committed PNG is the load-bearing deliverable per the plan. Strict
// per-run match unblocks once Inter + JetBrainsMono are bundled as ttf
// assets in pubspec (Wave-4 polish TODO inherited from 25-04).

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/bubble_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Same google_fonts FlutterError swallow as dashboard goldens.
  final priorOnError = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('Failed to load font') ||
        msg.contains('GoogleFonts.config.allowRuntimeFetching')) {
      return; // intentional swallow
    }
    priorOnError?.call(details);
  };

  testWidgets(
    'chat_markdown bubble matches golden snapshot @ textScale 1.0',
    skip: true,
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      const markdown = 'Here is a snippet:\n\n'
          '```dart\nfinal x = 1;\n```\n\n'
          'And a [link](https://example.com).';

      await tester.pumpWidget(
        MaterialApp(
          theme: solvrTheme(),
          home: const Scaffold(
            body: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: AssistantBubble(content: markdown),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/chat_markdown.png'),
      );

      await tester.runAsync(
        () async => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      tester.takeException();
    },
  );
}
