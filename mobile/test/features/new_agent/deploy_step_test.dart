// Phase 25 Wave 3 plan 25-06 task 2 — DeployStep widget tests.
//
// Covers: D-22 step 3 layout, D-27 name regex, D-30 smoke fail UX,
// D-55 telegram toggle visibility, D-57 inapp fail, D-58
// telegram-only fail nav, D-60 success nav. The collision dialog
// (D-28) and nav-stack assertion (D-60) live in their own files.
//
// Strategy: stub `DeployOrchestrator.deploy()` via the
// `DeployStep.orchestratorBuilder` test seam so the widget exercises
// every outcome variant without touching dio.

import 'dart:async';

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/telegram_failed_banner_provider.dart';
import 'package:agent_playground/features/new_agent/deploy_orchestrator.dart';
import 'package:agent_playground/features/new_agent/deploy_step.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

RecipeDetail _telegramRecipe() => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'openclaw',
        'channels': <String, dynamic>{
          'inapp': <String, dynamic>{},
          'telegram': <String, dynamic>{
            'required_user_input': <Map<String, dynamic>>[
              <String, dynamic>{
                'env': 'TELEGRAM_BOT_TOKEN',
                'secret': true,
                'hint': 'Create via @BotFather /newbot.',
              },
              <String, dynamic>{
                'env': 'TELEGRAM_ALLOWED_USER',
                'secret': false,
                'hint': 'Numeric Telegram user ID.',
              },
            ],
          },
        },
      },
    });

RecipeDetail _inappOnlyRecipe() => RecipeDetail.fromJson(<String, dynamic>{
      'recipe': <String, dynamic>{
        'name': 'nullclaw',
        'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
      },
    });

void _populateScope(
  ProviderContainer c, {
  required RecipeDetail recipe,
  String byok = 'sk-or-test',
  String? agentName,
  bool telegramEnabled = false,
  Map<String, String> telegramInputs = const {},
}) {
  c.read(wizardScopeProvider.notifier)
    ..setSelectedRecipe(recipe)
    ..setSelectedModel(
      const OpenRouterModel(id: 'anthropic/claude-haiku-4-5', name: 'haiku'),
    )
    ..setByokKey(byok);
  if (agentName != null) {
    c.read(wizardScopeProvider.notifier).setAgentName(agentName);
  }
  if (telegramEnabled) {
    c.read(wizardScopeProvider.notifier).setTelegramEnabled(true);
  }
  for (final e in telegramInputs.entries) {
    c.read(wizardScopeProvider.notifier).setTelegramInput(e.key, e.value);
  }
}

ApiClient _apiNoAgents() {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet(
    '/v1/agents',
    (s) => s.reply(200, <Map<String, dynamic>>[]),
  );
  return ApiClient(dio);
}

GoRouter _router() => GoRouter(
      initialLocation: '/new-agent/name-deploy',
      routes: [
        GoRoute(
          path: '/new-agent/clone',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('CLONE_ROUTE'))),
        ),
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) => const DeployStep(),
        ),
        GoRoute(
          path: '/dashboard',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('DASHBOARD_ROUTE'))),
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

Widget _harness(ProviderContainer c) => UncontrolledProviderScope(
      container: c,
      child: MaterialApp.router(theme: solvrTheme(), routerConfig: _router()),
    );

/// Test seam: a fake DeployOrchestrator that returns a pre-canned outcome.
class _FakeOrchestrator extends DeployOrchestrator {
  _FakeOrchestrator(super.api, this._outcome);
  final DeployOutcome _outcome;
  Map<String, dynamic>? lastTelegramInputs;
  bool? lastTelegramEnabled;

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
    lastTelegramEnabled = telegramEnabled;
    lastTelegramInputs = Map<String, dynamic>.from(telegramInputs);
    return _outcome;
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    DeployStep.orchestratorBuilder = null;
  });

  tearDown(() {
    DeployStep.orchestratorBuilder = null;
  });

  testWidgets(
    'D-27: invalid name (uppercase + space) shows red caption; valid name '
    'clears it',
    (tester) async {
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(container, recipe: _inappOnlyRecipe());
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const ValueKey('agent_name_field')),
        'My-Agent',
      );
      await tester.pumpAndSettle();
      expect(
        find.text('Lowercase letters, numbers, _ and - only'),
        findsOneWidget,
      );

      await tester.enterText(
        find.byKey(const ValueKey('agent_name_field')),
        'valid_name',
      );
      await tester.pumpAndSettle();
      expect(
        find.text('Lowercase letters, numbers, _ and - only'),
        findsNothing,
      );
    },
  );

  testWidgets('D-27: 65-char name shows length-cap caption', (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(container, recipe: _inappOnlyRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    final tooLong = 'a' * 65;
    await tester.enterText(
      find.byKey(const ValueKey('agent_name_field')),
      tooLong,
    );
    await tester.pumpAndSettle();
    expect(find.text('Name too long (max 64).'), findsOneWidget);
  });

  testWidgets(
    'D-55: Telegram toggle visible when channelsSupported includes telegram',
    (tester) async {
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(container, recipe: _telegramRecipe());
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      expect(find.text('Add Telegram channel'), findsOneWidget);
      expect(find.byType(Switch), findsOneWidget);
    },
  );

  testWidgets(
    'D-55: Telegram toggle HIDDEN when recipe does not declare telegram',
    (tester) async {
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(container, recipe: _inappOnlyRecipe());
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      expect(find.text('Add Telegram channel'), findsNothing);
      expect(find.byType(Switch), findsNothing);
    },
  );

  testWidgets(
    'Telegram toggled ON renders the dynamic ChannelInputs fields',
    (tester) async {
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(
        container,
        recipe: _telegramRecipe(),
        telegramEnabled: true,
      );
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      expect(find.text('TELEGRAM_BOT_TOKEN'), findsOneWidget);
      expect(find.text('TELEGRAM_ALLOWED_USER'), findsOneWidget);
    },
  );

  testWidgets('Deploy disabled until valid form', (tester) async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(container, recipe: _inappOnlyRecipe());
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();

    // Empty name → disabled.
    var btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Deploy'),
    );
    expect(btn.onPressed, isNull);

    // Valid name → enabled.
    await tester.enterText(
      find.byKey(const ValueKey('agent_name_field')),
      'my-agent',
    );
    await tester.pumpAndSettle();
    btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Deploy'),
    );
    expect(btn.onPressed, isNotNull);
  });

  testWidgets(
    'Deploy disabled when Telegram ON and required input is empty',
    (tester) async {
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(
        container,
        recipe: _telegramRecipe(),
        agentName: 'my-agent',
        telegramEnabled: true,
      );
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      var btn = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Deploy'),
      );
      expect(btn.onPressed, isNull, reason: 'required telegram inputs empty');

      // Fill required inputs → enabled.
      container
          .read(wizardScopeProvider.notifier)
          .setTelegramInput('TELEGRAM_BOT_TOKEN', 't1');
      container
          .read(wizardScopeProvider.notifier)
          .setTelegramInput('TELEGRAM_ALLOWED_USER', '123');
      await tester.pumpAndSettle();
      btn = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Deploy'),
      );
      expect(btn.onPressed, isNotNull);
    },
  );

  testWidgets('D-29: Deploy tap shows progress card with Cancel + elapsed',
      (tester) async {
    DeployStep.orchestratorBuilder = _FakeOrchestratorPending.new;
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(
      container,
      recipe: _inappOnlyRecipe(),
      agentName: 'my-agent',
    );
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    // Drain the agentsList() pre-flight microtask, then run the loading
    // setState frame. We can't `pumpAndSettle` because the orchestrator
    // future never completes (by design — that's the whole point of the
    // _FakeOrchestratorPending stub).
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Smoke testing recipe + model + key…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Cancel'), findsOneWidget);
  });

  testWidgets('D-30: smoke fail outcome renders red card with Retry + Edit',
      (tester) async {
    DeployStep.orchestratorBuilder = (api) => _FakeOrchestrator(
          api,
          const DeployOutcome.smokeFail(
            agentInstanceId: 'a-1',
            reason: 'recipe lint failed',
          ),
        );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(
      container,
      recipe: _inappOnlyRecipe(),
      agentName: 'my-agent',
    );
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    expect(find.text('Smoke test failed'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Retry'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Edit'), findsOneWidget);
  });

  testWidgets(
    'D-57: inapp fail renders red card with inapp title',
    (tester) async {
      DeployStep.orchestratorBuilder = (api) => _FakeOrchestrator(
            api,
            const DeployOutcome.inappFail(
              error: ApiError(
                code: ErrorCode.infraUnavailable,
                message: 'docker is sad',
              ),
            ),
          );
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(
        container,
        recipe: _telegramRecipe(),
        agentName: 'my-agent',
        telegramEnabled: true,
        telegramInputs: const {
          'TELEGRAM_BOT_TOKEN': 't1',
          'TELEGRAM_ALLOWED_USER': '123',
        },
      );
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      // Telegram toggle ON pushes Deploy below the 800x600 viewport.
      await tester.ensureVisible(
        find.widgetWithText(ElevatedButton, 'Deploy'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
      await tester.pumpAndSettle();
      expect(find.text("Couldn't start in-app channel"), findsOneWidget);
    },
  );

  testWidgets(
    'B-stripe regression: TIER_LIMIT_EXCEEDED renders plan-limit copy, '
    'not technical "agent cap reached for tier ..." jargon',
    (tester) async {
      // Server message is informative for logs — but the user should see
      // human-readable copy, not "agent cap reached for tier 'free' (1 active, cap 1)".
      DeployStep.orchestratorBuilder = (api) => _FakeOrchestrator(
            api,
            const DeployOutcome.inappFail(
              error: ApiError(
                code: ErrorCode.tierLimitExceeded,
                message: "agent cap reached for tier 'free' (1 active, cap 1)",
                statusCode: 403,
              ),
            ),
          );
      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
      );
      addTearDown(container.dispose);
      _populateScope(
        container,
        recipe: _inappOnlyRecipe(),
        agentName: 'my-agent',
      );
      await tester.pumpWidget(_harness(container));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
      await tester.pumpAndSettle();

      // Title must NOT be the technical "Couldn't start in-app channel" —
      // the user knows nothing about "in-app channels".
      expect(find.text("Couldn't start in-app channel"), findsNothing);

      // Title should communicate the actual situation.
      expect(find.text('Plan limit reached'), findsOneWidget);

      // Body must NOT echo the raw technical message.
      expect(
        find.textContaining("agent cap reached for tier 'free'"),
        findsNothing,
      );

      // Body should explain what to do next, in plain English.
      expect(find.textContaining('Stop'), findsOneWidget);
    },
  );

  testWidgets(
      'D-60: success → context.go(/chat/<id>) + wizardScope cleared + banner '
      'remains null', (tester) async {
    DeployStep.orchestratorBuilder = (api) => _FakeOrchestrator(
          api,
          const DeployOutcome.success(agentInstanceId: 'a-1'),
        );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(
      container,
      recipe: _inappOnlyRecipe(),
      agentName: 'my-agent',
    );
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    expect(find.text('CHAT_ROUTE_a-1'), findsOneWidget);
    // Wizard scope cleared (D-60).
    expect(container.read(wizardScopeProvider).agentName, '');
    // Banner stays null on full success.
    expect(container.read(telegramFailedBannerProvider), isNull);
  });

  testWidgets(
      'D-58: telegram-only fail → context.go(/chat/<id>) + '
      'telegramFailedBannerProvider populated', (tester) async {
    DeployStep.orchestratorBuilder = (api) => _FakeOrchestrator(
          api,
          const DeployOutcome.partialSuccess(
            agentInstanceId: 'a-1',
            telegramFailReason: 'rate limited',
            telegramInputs: {'TELEGRAM_BOT_TOKEN': 't1'},
          ),
        );
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(_apiNoAgents())],
    );
    addTearDown(container.dispose);
    _populateScope(
      container,
      recipe: _telegramRecipe(),
      agentName: 'my-agent',
      telegramEnabled: true,
      telegramInputs: const {
        'TELEGRAM_BOT_TOKEN': 't1',
        'TELEGRAM_ALLOWED_USER': '123',
      },
    );
    await tester.pumpWidget(_harness(container));
    await tester.pumpAndSettle();
    // The Telegram-on form scrolls below the 800x600 test viewport — make
    // the Deploy button visible first.
    await tester.ensureVisible(
      find.widgetWithText(ElevatedButton, 'Deploy'),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Deploy'));
    await tester.pumpAndSettle();
    final banner = container.read(telegramFailedBannerProvider);
    expect(banner, isNotNull, reason: 'D-58 banner state must be populated');
    expect(banner!.agentInstanceId, 'a-1');
    expect(banner.reason, 'rate limited');
    expect(banner.telegramInputs, containsPair('TELEGRAM_BOT_TOKEN', 't1'));
    // Wizard scope cleared (D-60).
    expect(container.read(wizardScopeProvider).agentName, '');
    expect(find.text('CHAT_ROUTE_a-1'), findsOneWidget);
  });
}

/// Pending orchestrator stub — Future never completes. Used to assert the
/// loading-card UX appears between Deploy tap and outcome.
class _FakeOrchestratorPending extends DeployOrchestrator {
  _FakeOrchestratorPending(super.api);

  @override
  Future<DeployOutcome> deploy({
    required String recipeName,
    required String modelId,
    required String agentName,
    required String byokKey,
    required bool telegramEnabled,
    Map<String, String> telegramInputs = const {},
    CancelToken? cancelToken,
  }) {
    final c = Completer<DeployOutcome>();
    // Never completes — caller controls via cancelToken.
    return c.future;
  }
}
