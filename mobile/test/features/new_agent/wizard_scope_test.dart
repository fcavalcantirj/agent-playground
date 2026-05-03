// Phase 25 Wave 3 plan 25-05 task 2 — wizardScopeProvider tests.
//
// Pitfall #10 Pattern A — single Notifier, manually invalidated on close
// (D-31). Tests cover default state, isDirty discrimination, all setters,
// and clear() reset.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

RecipeDetail _detail(String name) => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': name,
        'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
      },
    });

const _model = OpenRouterModel(
  id: 'anthropic/claude-haiku-4-5',
  name: 'Claude Haiku 4.5',
);

void main() {
  test('default state — all fields null/empty/false; isDirty false', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final state = container.read(wizardScopeProvider);
    expect(state.selectedRecipe, isNull);
    expect(state.selectedModel, isNull);
    expect(state.byokKey, '');
    expect(state.agentName, '');
    expect(state.telegramEnabled, isFalse);
    expect(state.telegramInputs, isEmpty);
    expect(state.isDirty, isFalse);
  });

  test('setSelectedRecipe makes state dirty + stores recipe', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(wizardScopeProvider.notifier);
    final detail = _detail('openclaw');
    notifier.setSelectedRecipe(detail);
    final s = container.read(wizardScopeProvider);
    expect(s.selectedRecipe?.name, 'openclaw');
    expect(s.isDirty, isTrue);
  });

  test('setSelectedModel + setByokKey + setAgentName each flip isDirty',
      () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(wizardScopeProvider.notifier)
      ..setSelectedModel(_model);
    expect(container.read(wizardScopeProvider).selectedModel?.id,
        'anthropic/claude-haiku-4-5');
    expect(container.read(wizardScopeProvider).isDirty, isTrue);

    notifier
      ..clear()
      ..setByokKey('sk-or-test');
    expect(container.read(wizardScopeProvider).byokKey, 'sk-or-test');
    expect(container.read(wizardScopeProvider).isDirty, isTrue);

    notifier
      ..clear()
      ..setAgentName('foo');
    expect(container.read(wizardScopeProvider).agentName, 'foo');
    expect(container.read(wizardScopeProvider).isDirty, isTrue);
  });

  test('setTelegramEnabled + setTelegramInput propagate', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(wizardScopeProvider.notifier)
      ..setTelegramEnabled(true);
    expect(container.read(wizardScopeProvider).telegramEnabled, isTrue);
    expect(container.read(wizardScopeProvider).isDirty, isTrue);

    notifier
      ..setTelegramInput('TELEGRAM_BOT_TOKEN', 'sek-1')
      ..setTelegramInput('TELEGRAM_ALLOWED_USER', '12345');
    final s = container.read(wizardScopeProvider);
    expect(s.telegramInputs['TELEGRAM_BOT_TOKEN'], 'sek-1');
    expect(s.telegramInputs['TELEGRAM_ALLOWED_USER'], '12345');
  });

  test('clear() resets to default + isDirty false', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    container.read(wizardScopeProvider.notifier)
      ..setSelectedRecipe(_detail('hermes'))
      ..setSelectedModel(_model)
      ..setByokKey('sk-or')
      ..setAgentName('bar')
      ..setTelegramEnabled(true)
      ..setTelegramInput('K', 'V');
    expect(container.read(wizardScopeProvider).isDirty, isTrue);

    container.read(wizardScopeProvider.notifier).clear();
    final s = container.read(wizardScopeProvider);
    expect(s.selectedRecipe, isNull);
    expect(s.selectedModel, isNull);
    expect(s.byokKey, '');
    expect(s.agentName, '');
    expect(s.telegramEnabled, isFalse);
    expect(s.telegramInputs, isEmpty);
    expect(s.isDirty, isFalse);
  });
}
