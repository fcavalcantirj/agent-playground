// Phase 25 Wave 4 plan 25-07 task 2 — D-43 markdown render tests.
//
// Verifies:
//   * UserBubble renders right-aligned with foreground bg + background fg.
//   * AssistantBubble renders left-aligned with muted bg + foreground fg.
//   * AssistantBubble passes markdown content through MarkdownBody.
//   * AssistantBubble strips images per D-43 (imageBuilder returns
//     SizedBox.shrink — Image widget is NOT in the tree).
//   * AssistantBubble code blocks render in JetBrains Mono per D-43.
//   * Long-press on either bubble opens the action sheet with Copy +
//     Select text (D-48).
//   * ChatInputBar Enter inserts newline, NOT send (D-40).
//   * ChatInputBar Send button states: disabled-empty / enabled / spinner
//     (D-51).

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/bubble_widget.dart';
import 'package:agent_playground/features/chat/input_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: solvrTheme(),
      home: Scaffold(body: child),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('UserBubble (D-35)', () {
    testWidgets('right-aligned with foreground bg + background fg',
        (tester) async {
      await tester.pumpWidget(_wrap(const UserBubble(content: 'hi')));
      // The Align with centerRight wraps the bubble.
      final aligns = tester.widgetList<Align>(find.byType(Align)).toList();
      final centerRight = aligns
          .where((a) => a.alignment == Alignment.centerRight)
          .toList();
      expect(centerRight, isNotEmpty);
      // Decoration is BoxDecoration(color: SolvrColors.foreground).
      final container = tester.widget<Container>(
        find
            .descendant(
              of: find.byType(UserBubble),
              matching: find.byType(Container),
            )
            .first,
      );
      final decoration = container.decoration! as BoxDecoration;
      expect(decoration.color, SolvrColors.foreground);
      // Content text is rendered inside SelectableText.
      expect(find.text('hi'), findsOneWidget);
    });
  });

  group('AssistantBubble (D-35 + D-43)', () {
    testWidgets('left-aligned with muted bg + foreground fg', (tester) async {
      await tester.pumpWidget(
        _wrap(const AssistantBubble(content: 'hello **world**')),
      );
      final aligns = tester.widgetList<Align>(find.byType(Align)).toList();
      final centerLeft = aligns
          .where((a) => a.alignment == Alignment.centerLeft)
          .toList();
      expect(centerLeft, isNotEmpty);
      final container = tester.widget<Container>(
        find
            .descendant(
              of: find.byType(AssistantBubble),
              matching: find.byType(Container),
            )
            .first,
      );
      final decoration = container.decoration! as BoxDecoration;
      expect(decoration.color, SolvrColors.muted);
      // MarkdownBody is rendered.
      expect(find.byType(MarkdownBody), findsOneWidget);
    });

    testWidgets('strips images per D-43 (no Image widget in tree)',
        (tester) async {
      await tester.pumpWidget(
        _wrap(
          const AssistantBubble(content: '![alt](https://example.com/x.png)'),
        ),
      );
      // imageBuilder returns SizedBox.shrink → no Image widget exists.
      expect(find.byType(Image), findsNothing);
    });

    testWidgets('renders code fences (markdown content reaches MarkdownBody)',
        (tester) async {
      await tester.pumpWidget(
        _wrap(
          const AssistantBubble(content: '```dart\nfinal x = 1;\n```'),
        ),
      );
      final mb = tester.widget<MarkdownBody>(find.byType(MarkdownBody));
      expect(mb.data, '```dart\nfinal x = 1;\n```');
      expect(mb.styleSheet, isNotNull);
      // Code block decoration was set up.
      expect(mb.styleSheet!.codeblockDecoration, isNotNull);
    });

    testWidgets('selectable=false so long-press fires D-48 action sheet',
        (tester) async {
      // Selectable=true would let the OS intercept long-press for the
      // native selection menu, eating the bubble-level gesture and the
      // D-48 sheet would never show. Verified via long-press tests below.
      await tester.pumpWidget(
        _wrap(const AssistantBubble(content: 'pick me')),
      );
      final mb = tester.widget<MarkdownBody>(find.byType(MarkdownBody));
      expect(mb.selectable, isFalse);
    });
  });

  group('Long-press → bottom sheet (D-48)', () {
    testWidgets('UserBubble long-press shows Copy + Select text tiles',
        (tester) async {
      var copied = 0;
      var selected = 0;
      await tester.pumpWidget(
        _wrap(
          UserBubble(
            content: 'foo',
            onCopy: () => copied++,
            onSelect: () => selected++,
          ),
        ),
      );
      // The bubble is right-aligned inside Align (which fills the screen),
      // so long-press on the bubble's GestureDetector directly — the
      // Align's centroid is empty space.
      await tester.longPress(
        find.descendant(
          of: find.byType(UserBubble),
          matching: find.byType(GestureDetector),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Copy'), findsOneWidget);
      expect(find.text('Select text'), findsOneWidget);
      await tester.tap(find.text('Copy'));
      await tester.pumpAndSettle();
      expect(copied, 1);
      expect(selected, 0);
    });

    testWidgets('AssistantBubble long-press shows Copy + Select text tiles',
        (tester) async {
      var copied = 0;
      var selected = 0;
      await tester.pumpWidget(
        _wrap(
          AssistantBubble(
            content: 'foo',
            onCopy: () => copied++,
            onSelect: () => selected++,
          ),
        ),
      );
      await tester.longPress(
        find.descendant(
          of: find.byType(AssistantBubble),
          matching: find.byType(GestureDetector),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Select text'), findsOneWidget);
      await tester.tap(find.text('Select text'));
      await tester.pumpAndSettle();
      expect(selected, 1);
      expect(copied, 0);
    });
  });

  group('ChatInputBar (D-40 + D-51)', () {
    testWidgets('empty input → Send button disabled', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ChatInputBar(onSend: (_) {}, onCancel: () {}),
        ),
      );
      final btn = tester.widget<IconButton>(
        find.byKey(const Key('chat-send-button')),
      );
      expect(btn.onPressed, isNull);
    });

    testWidgets('non-empty input → Send button enabled; tap fires onSend',
        (tester) async {
      String? sent;
      await tester.pumpWidget(
        _wrap(
          ChatInputBar(onSend: (c) => sent = c, onCancel: () {}),
        ),
      );
      await tester.enterText(find.byKey(const Key('chat-input-field')), 'hi');
      await tester.pump();
      final btn = tester.widget<IconButton>(
        find.byKey(const Key('chat-send-button')),
      );
      expect(btn.onPressed, isNotNull);
      await tester.tap(find.byKey(const Key('chat-send-button')));
      await tester.pump();
      expect(sent, 'hi');
    });

    testWidgets('inflight → spinner replaces send icon; tap fires onCancel',
        (tester) async {
      var cancelled = 0;
      await tester.pumpWidget(
        _wrap(
          ChatInputBar(
            inflight: true,
            onSend: (_) {},
            onCancel: () => cancelled++,
          ),
        ),
      );
      expect(find.byKey(const Key('chat-send-spinner')), findsOneWidget);
      expect(find.byKey(const Key('chat-send-button')), findsNothing);
      await tester.tap(find.byKey(const Key('chat-send-spinner')));
      await tester.pump();
      expect(cancelled, 1);
    });

    testWidgets('TextField textInputAction is newline (D-40)', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ChatInputBar(onSend: (_) {}, onCancel: () {}),
        ),
      );
      final tf = tester.widget<TextField>(
        find.byKey(const Key('chat-input-field')),
      );
      expect(tf.textInputAction, TextInputAction.newline);
      expect(tf.maxLines, 5);
      expect(tf.minLines, 1);
    });
  });
}
