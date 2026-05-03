// Phase 25 Wave 3 plan 25-05 task 3 — ModelStep widget tests.
//
// Covers D-26 (Pick a model push), D-32 (BYOK label-swap covered by
// dedicated byok_label_test.dart), D-33 (auto-fill from secureStorage),
// D-34 (obscureText + eye-toggle + autocorrect/enableSuggestions = false),
// Next disabled until both selectedModel + byokKey present.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
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

ApiClient _apiWithModels() {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet(
    '/v1/models',
    (s) => s.reply(200, <Map<String, dynamic>>[
      {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
    ]),
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
              const Scaffold(body: Center(child: Text('PICKER_ROUTE'))),
        ),
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('NAME_DEPLOY_ROUTE'))),
        ),
      ],
    );

Widget _harness(ProviderContainer container) {
  return UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(theme: solvrTheme(), routerConfig: _router()),
  );
}

RecipeDetail _openrouterRecipe() => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'nullclaw',
        'channels': <String, dynamic>{
          'inapp': <String, dynamic>{},
        },
      },
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets(
      'no selectedModel → "Pick a model" button visible; tap pushes picker',
      (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithModels())],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    expect(find.text('Pick a model'), findsOneWidget);
    await tester.tap(find.text('Pick a model'));
    await tester.pumpAndSettle();
    expect(find.text('PICKER_ROUTE'), findsOneWidget);
  });

  testWidgets(
      'with selectedModel → renders model id + Change text button',
      (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithModels())],
    );
    addTearDown(container.dispose);
    container.read(wizardScopeProvider.notifier)
      ..setSelectedRecipe(_openrouterRecipe())
      ..setSelectedModel(const OpenRouterModel(
        id: 'anthropic/claude-haiku-4-5',
        name: 'Claude Haiku 4.5',
      ));
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    expect(find.text('anthropic/claude-haiku-4-5'), findsOneWidget);
    expect(find.text('Change'), findsOneWidget);
  });

  testWidgets(
      'BYOK TextField is obscureText:true + autocorrect/enableSuggestions '
      'false (D-34)', (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithModels())],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    final tf = tester.widget<TextField>(
      find.widgetWithText(TextField, 'OpenRouter API Key'),
    );
    expect(tf.obscureText, isTrue);
    expect(tf.autocorrect, isFalse);
    expect(tf.enableSuggestions, isFalse);
  });

  testWidgets('eye-toggle flips obscureText (D-34)', (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithModels())],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.visibility), findsOneWidget);
    expect(find.byIcon(Icons.visibility_off), findsNothing);
    await tester.tap(find.byIcon(Icons.visibility));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.visibility_off), findsOneWidget);
  });

  testWidgets(
      'BYOK auto-fills from secureStorage on mount (D-33)',
      (tester) async {
    FlutterSecureStorage.setMockInitialValues({
      'byok_key_openrouter': 'sk-or-stored-key',
    });
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(_apiWithModels()),
        secureStorageProvider.overrideWithValue(SecureStorage()),
      ],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    final scope = container.read(wizardScopeProvider);
    expect(scope.byokKey, 'sk-or-stored-key');
  });

  testWidgets(
      'BYOK onChanged → secureStorage.writeByokKey + wizardScope.byokKey '
      'updates', (tester) async {
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(_apiWithModels()),
        secureStorageProvider.overrideWithValue(SecureStorage()),
      ],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'OpenRouter API Key'),
      'sk-or-typed-key',
    );
    await tester.pumpAndSettle();
    expect(
      container.read(wizardScopeProvider).byokKey,
      'sk-or-typed-key',
    );
    final stored =
        await container.read(secureStorageProvider).readByokKey('openrouter');
    expect(stored, 'sk-or-typed-key');
  });

  testWidgets(
      'Next disabled until selectedModel != null AND byokKey not empty',
      (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithModels())],
    );
    addTearDown(container.dispose);
    container
        .read(wizardScopeProvider.notifier)
        .setSelectedRecipe(_openrouterRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();

    // No model + no key → disabled.
    var btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Next'),
    );
    expect(btn.onPressed, isNull);

    // Set model only → still disabled.
    container.read(wizardScopeProvider.notifier).setSelectedModel(
          const OpenRouterModel(id: 'a/b', name: 'b'),
        );
    await tester.pumpAndSettle();
    btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Next'),
    );
    expect(btn.onPressed, isNull);

    // Set byokKey → enabled.
    container.read(wizardScopeProvider.notifier).setByokKey('sk-or-1');
    await tester.pumpAndSettle();
    btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Next'),
    );
    expect(btn.onPressed, isNotNull);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await tester.pumpAndSettle();
    expect(find.text('NAME_DEPLOY_ROUTE'), findsOneWidget);
  });
}
