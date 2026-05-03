// Phase 25 Wave 3 plan 25-06 task 1 — ChannelInputs widget tests.
//
// Covers D-54 (dynamic field render loop) — labels = env value verbatim,
// secret flag drives obscureText, hint_url renders a "get one here" link.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/channel_inputs.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

RecipeChannelMeta _meta() => const RecipeChannelMeta(
      requiredUserInput: [
        ChannelUserInput(
          env: 'TELEGRAM_BOT_TOKEN',
          secret: true,
          hint: 'Create via @BotFather /newbot.',
        ),
        ChannelUserInput(
          env: 'TELEGRAM_ALLOWED_USER',
          secret: false,
          hint: 'Numeric Telegram user ID.',
          hintUrl: 'https://t.me/userinfobot',
        ),
      ],
      optionalUserInput: [],
    );

Widget _harness({
  required RecipeChannelMeta meta,
  ProviderContainer? container,
}) {
  final c = container ?? ProviderContainer();
  return UncontrolledProviderScope(
    container: c,
    child: MaterialApp(
      theme: solvrTheme(),
      home: Scaffold(body: ChannelInputs(channelMeta: meta)),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders one TextField per ChannelUserInput with env as label',
      (tester) async {
    await tester.pumpWidget(_harness(meta: _meta()));
    await tester.pumpAndSettle();
    // Labels = env values, verbatim.
    expect(find.text('TELEGRAM_BOT_TOKEN'), findsOneWidget);
    expect(find.text('TELEGRAM_ALLOWED_USER'), findsOneWidget);
    // 2 TextFields (one per input).
    expect(find.byType(TextField), findsNWidgets(2));
  });

  testWidgets('typing into a field updates wizardScope.telegramInputs',
      (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(_harness(meta: _meta(), container: container));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('channel_input_TELEGRAM_BOT_TOKEN')),
      'tg-secret-1',
    );
    await tester.pumpAndSettle();
    expect(
      container.read(wizardScopeProvider).telegramInputs,
      containsPair('TELEGRAM_BOT_TOKEN', 'tg-secret-1'),
    );
  });

  testWidgets('secret=true input has obscureText: true; secret=false does not',
      (tester) async {
    await tester.pumpWidget(_harness(meta: _meta()));
    await tester.pumpAndSettle();
    final secretTf = tester.widget<TextField>(
      find.byKey(const ValueKey('channel_input_TELEGRAM_BOT_TOKEN')),
    );
    final plainTf = tester.widget<TextField>(
      find.byKey(const ValueKey('channel_input_TELEGRAM_ALLOWED_USER')),
    );
    expect(secretTf.obscureText, isTrue);
    expect(plainTf.obscureText, isFalse);
    // Both disable autocorrect + suggestions per secret-input hygiene.
    expect(secretTf.autocorrect, isFalse);
    expect(secretTf.enableSuggestions, isFalse);
    expect(plainTf.autocorrect, isFalse);
    expect(plainTf.enableSuggestions, isFalse);
  });

  testWidgets('input with hint renders the hint caption', (tester) async {
    await tester.pumpWidget(_harness(meta: _meta()));
    await tester.pumpAndSettle();
    expect(find.text('Create via @BotFather /newbot.'), findsOneWidget);
    expect(find.text('Numeric Telegram user ID.'), findsOneWidget);
  });

  testWidgets('input with hint_url renders a "get one here" link button',
      (tester) async {
    await tester.pumpWidget(_harness(meta: _meta()));
    await tester.pumpAndSettle();
    // The TELEGRAM_ALLOWED_USER input has a hint_url; the BOT_TOKEN does not.
    // Exactly one "get one here" button is rendered.
    expect(find.text('get one here'), findsOneWidget);
  });

  testWidgets('empty inputs (no required, no optional) renders no TextFields',
      (tester) async {
    await tester.pumpWidget(_harness(
      meta: const RecipeChannelMeta(
        requiredUserInput: [],
        optionalUserInput: [],
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNothing);
  });
}
