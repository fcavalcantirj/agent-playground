// Phase 25 Wave 3 plan 25-05 task 3 — BYOK label-swap (D-32) tests.
//
// Critical Golden Rule #2 invariant: the label MUST come from
// `recipe.channelProviderCompat['inapp'].supported` — NEVER from a Dart
// `if recipe == 'hermes'` branch. Bug fix 2026-05-04: the original
// implementation switched on `deferred.contains('openrouter')`, which
// silently broke openclaw inapp (synthesized as
// `{supported:[anthropic], deferred:[]}`). The label-swap now switches
// on `supported.first`; this fixture asserts every supported branch.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/model_step.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

ApiClient _api({Map<String, dynamic>? modelsBody}) {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet(
    '/v1/models',
    (s) => s.reply(200, modelsBody ?? <Map<String, dynamic>>[]),
  );
  return ApiClient(dio);
}

GoRouter _router() => GoRouter(
      initialLocation: '/new-agent/model',
      routes: [
        GoRoute(
          path: '/new-agent/model',
          builder: (_, _) => const ModelStep(),
        ),
        GoRoute(
          path: '/new-agent/model/picker',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('PICKER'))),
        ),
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('NAME_DEPLOY'))),
        ),
      ],
    );

Widget _harnessForRecipe(RecipeDetail recipe, {ProviderContainer? c}) {
  final container = c ??
      ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_api())],
      );
  // Pre-populate the wizard with the recipe so ModelStep reads it.
  container.read(wizardScopeProvider.notifier).setSelectedRecipe(recipe);
  return UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(theme: solvrTheme(), routerConfig: _router()),
  );
}

RecipeDetail _recipeWithCompat({
  required List<String> supported,
  List<String> deferred = const <String>[],
}) =>
    RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'fixture',
        'channels': <String, dynamic>{
          'inapp': <String, dynamic>{
            'provider_compat': <String, dynamic>{
              'supported': supported,
              'deferred': deferred,
            },
          },
        },
      },
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets(
      "label = 'OpenRouter API Key' when supported=[openrouter] "
      '(nullclaw / hermes / picoclaw / nanobot / zeroclaw inapp)',
      (tester) async {
    final recipe = _recipeWithCompat(supported: const ['openrouter']);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_api())],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(_harnessForRecipe(recipe, c: container));
    await tester.pumpAndSettle();
    expect(find.text('OpenRouter API Key'), findsOneWidget);
    expect(find.text('Anthropic API Key'), findsNothing);
  });

  testWidgets(
      "label = 'Anthropic API Key' when supported=[anthropic] "
      '(openclaw inapp)', (tester) async {
    final recipe = _recipeWithCompat(supported: const ['anthropic']);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_api())],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(_harnessForRecipe(recipe, c: container));
    await tester.pumpAndSettle();
    expect(find.text('Anthropic API Key'), findsOneWidget);
    expect(find.text('OpenRouter API Key'), findsNothing);
  });

  testWidgets(
      "label = 'OpenAI API Key' when supported=[openai] "
      '(future recipe)', (tester) async {
    final recipe = _recipeWithCompat(supported: const ['openai']);
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_api())],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(_harnessForRecipe(recipe, c: container));
    await tester.pumpAndSettle();
    expect(find.text('OpenAI API Key'), findsOneWidget);
  });

  testWidgets('no recipe selected (defensive) — defaults to OpenRouter label',
      (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_api())],
    );
    addTearDown(container.dispose);
    // DON'T set a recipe.
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: _router(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('OpenRouter API Key'), findsOneWidget);
  });
}
