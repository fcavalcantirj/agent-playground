// Phase 25 Wave 3 plan 25-06 task 3 — D-60 / RESEARCH §Open Question Q5.
//
// Asserts at runtime that Deploy success uses go_router.go(/chat/<id>) —
// REPLACING the wizard stack — so that back from Chat returns to
// Dashboard, NOT the wizard. The load-bearing check is
// `Navigator.canPop()` returning `false` after the route swap, which
// would not happen if DeployStep mistakenly used `context.push`.

import 'dart:async';

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

ApiClient _api() {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet(
    '/v1/agents',
    (s) => s.reply(200, <Map<String, dynamic>>[]),
  );
  return ApiClient(dio);
}

RecipeDetail _recipe() => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'nullclaw',
        'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
      },
    });

class _FakeOrchestrator extends DeployOrchestrator {
  _FakeOrchestrator(super.api);

  @override
  Future<DeployOutcome> deploy({
    required String recipeName,
    required String modelId,
    required String agentName,
    required String byokKey,
    required bool telegramEnabled,
    Map<String, String> telegramInputs = const {},
    CancelToken? cancelToken,
  }) async => const DeployOutcome.success(agentInstanceId: 'a-1');
}

GoRouter _router() => GoRouter(
      initialLocation: '/dashboard',
      routes: [
        GoRoute(
          path: '/dashboard',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('DASHBOARD_ROUTE'))),
        ),
        GoRoute(
          path: '/new-agent/clone',
          builder: (_, _) => const Scaffold(body: SizedBox.shrink()),
        ),
        GoRoute(
          path: '/new-agent/model',
          builder: (_, _) => const Scaffold(body: SizedBox.shrink()),
        ),
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) => const DeployStep(),
        ),
        GoRoute(
          path: '/chat/:agentInstanceId',
          builder: (ctx, state) => Scaffold(
            body: Center(
              child: Text(
                'CHAT_ROUTE_${state.pathParameters['agentInstanceId']}',
              ),
            ),
          ),
        ),
      ],
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    DeployStep.orchestratorBuilder = null;
  });
  tearDown(() {
    DeployStep.orchestratorBuilder = null;
  });

  testWidgets(
      'D-60 / RESEARCH Q5: Deploy success → /chat/<id> with empty back stack',
      (tester) async {
    DeployStep.orchestratorBuilder = _FakeOrchestrator.new;
    final router = _router();
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_api())],
    );
    addTearDown(container.dispose);

    // Pre-populate the wizard scope so DeployStep finds a valid form.
    container.read(wizardScopeProvider.notifier)
      ..setSelectedRecipe(_recipe())
      ..setSelectedModel(
        const OpenRouterModel(id: 'anthropic/claude-haiku-4-5', name: 'h'),
      )
      ..setByokKey('sk-or-test')
      ..setAgentName('my-agent');

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Walk the wizard stack via push() to mimic the user's nav path —
    // each push adds an entry to the route stack. After Deploy success,
    // go_router.go() should REPLACE the entire stack with /chat/<id>.
    unawaited(router.push<Object?>('/new-agent/clone'));
    await tester.pumpAndSettle();
    unawaited(router.push<Object?>('/new-agent/model'));
    await tester.pumpAndSettle();
    unawaited(router.push<Object?>('/new-agent/name-deploy'));
    await tester.pumpAndSettle();

    // Sanity: we are on the deploy step.
    expect(find.byKey(const ValueKey('agent_name_field')), findsOneWidget);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();

    // Route landed on /chat/<id>.
    expect(find.text('CHAT_ROUTE_a-1'), findsOneWidget);

    // Load-bearing assertion — Navigator.canPop() must be false. If the
    // orchestrator success branch mistakenly used context.push instead
    // of context.go, the wizard stack would still be poppable.
    final ctx = tester.element(find.text('CHAT_ROUTE_a-1'));
    // Wizard stack must be torn down after Deploy success — back goes to
    // Dashboard, not wizard (D-60 + RESEARCH Q5).
    expect(Navigator.of(ctx).canPop(), isFalse);

    // Belt-and-suspenders: go_router's own match list confirms it.
    final cfg = router.routerDelegate.currentConfiguration;
    expect(
      cfg.matches.length,
      1,
      reason: 'go_router stack must contain exactly /chat/:id after '
          'Deploy success',
    );
    // Route path startsWith('/chat/') is the textual mirror of the
    // route-stack assertion above.
    final activePath = cfg.uri.path;
    expect(activePath, startsWith('/chat/'));
  });
}
