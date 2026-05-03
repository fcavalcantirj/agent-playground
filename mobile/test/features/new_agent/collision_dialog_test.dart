// Phase 25 Wave 3 plan 25-06 task 2 — D-28 collision dialog tests.
//
// Asserts pre-flight name-collision check on Deploy tap:
//   - GET /v1/agents lookup
//   - if duplicate name → ConfirmDialog "Name '{name}' already used" with
//     Cancel / Re-deploy / Rename
//   - Cancel → no orchestrator call
//   - Rename → name field focused, no orchestrator call
//   - Re-deploy → orchestrator runs

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/deploy_orchestrator.dart';
import 'package:agent_playground/features/new_agent/deploy_step.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

RecipeDetail _recipe() => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'nullclaw',
        'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
      },
    });

ApiClient _apiWithExisting() {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet(
    '/v1/agents',
    (s) => s.reply(200, <Map<String, dynamic>>[
      <String, dynamic>{
        'id': 'agent-existing',
        'name': 'foo',
        'recipe_name': 'openclaw',
        'model': 'anthropic/claude-haiku-4-5',
        'status': 'running',
        'created_at': '2026-05-01T00:00:00Z',
      },
    ]),
  );
  return ApiClient(dio);
}

void _populateScope(ProviderContainer c, String name) {
  c.read(wizardScopeProvider.notifier)
    ..setSelectedRecipe(_recipe())
    ..setSelectedModel(
      const OpenRouterModel(id: 'anthropic/claude-haiku-4-5', name: 'haiku'),
    )
    ..setByokKey('sk-or-test')
    ..setAgentName(name);
}

GoRouter _router() => GoRouter(
      initialLocation: '/new-agent/name-deploy',
      routes: [
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) => const DeployStep(),
        ),
        GoRoute(
          path: '/chat/:agentInstanceId',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('CHAT_ROUTE'))),
        ),
        GoRoute(
          path: '/dashboard',
          builder: (_, _) => const Scaffold(body: SizedBox.shrink()),
        ),
      ],
    );

Widget _harness(ProviderContainer c) => UncontrolledProviderScope(
      container: c,
      child: MaterialApp.router(theme: solvrTheme(), routerConfig: _router()),
    );

class _SpyOrchestrator extends DeployOrchestrator {
  _SpyOrchestrator(super.api);
  int deployCalls = 0;

  @override
  Future<DeployOutcome> deploy({
    required String recipeName,
    required String modelId,
    required String agentName,
    required String byokKey,
    required bool telegramEnabled,
    Map<String, String> telegramInputs = const {},
    CancelToken? cancelToken,
  }) async {
    deployCalls++;
    return const DeployOutcome.success(agentInstanceId: 'a-1');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    DeployStep.orchestratorBuilder = null;
  });
  tearDown(() {
    DeployStep.orchestratorBuilder = null;
  });

  testWidgets(
      'D-28: dup name on Deploy tap → ConfirmDialog with title + body + 3 '
      'buttons', (tester) async {
    final spy = _SpyOrchestrator(_apiWithExisting());
    DeployStep.orchestratorBuilder = (_) => spy;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithExisting())],
    );
    addTearDown(container.dispose);
    _populateScope(container, 'foo');
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();

    expect(find.text('Name "foo" already used'), findsOneWidget);
    expect(
      find.textContaining('Re-deploy replaces it; rename keeps both'),
      findsOneWidget,
    );
    expect(find.widgetWithText(TextButton, 'Cancel'), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Re-deploy'), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Rename'), findsOneWidget);

    expect(
      spy.deployCalls,
      0,
      reason: 'orchestrator must NOT run while dialog is open',
    );
  });

  testWidgets('D-28: Cancel → dialog dismisses, orchestrator never runs',
      (tester) async {
    final spy = _SpyOrchestrator(_apiWithExisting());
    DeployStep.orchestratorBuilder = (_) => spy;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithExisting())],
    );
    addTearDown(container.dispose);
    _populateScope(container, 'foo');
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Name "foo" already used'), findsNothing);
    expect(spy.deployCalls, 0);
  });

  testWidgets(
      'D-28: Rename → dialog dismisses, orchestrator never runs, name '
      'field still on screen', (tester) async {
    final spy = _SpyOrchestrator(_apiWithExisting());
    DeployStep.orchestratorBuilder = (_) => spy;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithExisting())],
    );
    addTearDown(container.dispose);
    _populateScope(container, 'foo');
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Rename'));
    await tester.pumpAndSettle();
    expect(find.text('Name "foo" already used'), findsNothing);
    expect(spy.deployCalls, 0);
    expect(find.byKey(const ValueKey('agent_name_field')), findsOneWidget);
  });

  testWidgets('D-28: Re-deploy → orchestrator runs', (tester) async {
    final spy = _SpyOrchestrator(_apiWithExisting());
    DeployStep.orchestratorBuilder = (_) => spy;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithExisting())],
    );
    addTearDown(container.dispose);
    _populateScope(container, 'foo');
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Re-deploy'));
    await tester.pumpAndSettle();
    expect(spy.deployCalls, 1);
  });

  testWidgets('no collision: orchestrator runs without dialog',
      (tester) async {
    final spy = _SpyOrchestrator(_apiWithExisting());
    DeployStep.orchestratorBuilder = (_) => spy;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiWithExisting())],
    );
    addTearDown(container.dispose);
    _populateScope(container, 'unique-name');
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    expect(find.textContaining('already used'), findsNothing);
    expect(spy.deployCalls, 1);
  });
}
