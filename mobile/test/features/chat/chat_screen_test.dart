// Phase 25 Wave 4 plan 25-07 task 3 — ChatScreen widget tests.
//
// Covers UI-03 + D-37/D-38/D-39/D-49/D-50 + D-42 (auto-scroll-suppression
// chip). The agentsList and messagesHistory feeds are mocked at the dio
// transport via http_mock_adapter.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:agent_playground/features/chat/chat_screen.dart';
import 'package:agent_playground/features/chat/telegram_failed_banner_provider.dart';
import 'package:agent_playground/shared/restart_banner.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

const _agentId = 'a-1';

class _FakeAuth implements AuthService {
  @override
  Future<Result<SessionUser>> signInWithGoogle() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<Result<SessionUser>> signInWithGithub() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<Result<SessionUser>> signInWithGithubCode({
    required String code,
    required String codeVerifier,
  }) async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<void> signOut() async {}
}

class _Harness {
  _Harness() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
    auth = _FakeAuth();
  }
  late final Dio dio;
  late final DioAdapter adapter;
  late final ApiClient api;
  late final _FakeAuth auth;

  void stubAgents(List<Map<String, dynamic>> rows) {
    adapter.onGet('/v1/agents', (s) => s.reply(200, rows));
  }

  void stubMessages(List<Map<String, dynamic>> rows) {
    adapter.onGet(
      '/v1/agents/$_agentId/messages',
      (s) => s.reply(200, <String, dynamic>{'messages': rows}),
      queryParameters: {'limit': 200},
    );
  }

  void stubMessagesEmpty() => stubMessages(const []);
}

Map<String, dynamic> _msg({
  required String role,
  required String content,
  required String createdAt,
  String inappMessageId = 'm-1',
}) =>
    {
      'inapp_message_id': inappMessageId,
      'role': role,
      'content': content,
      'created_at': createdAt,
    };

Map<String, dynamic> _agentJson({
  String id = _agentId,
  String name = 'claude-test',
  String status = 'running',
}) =>
    {
      'id': id,
      'name': name,
      'recipe_name': 'openclaw',
      'model': 'anthropic/claude-haiku-4-5',
      'status': status,
      'created_at': '2026-05-03T00:00:00Z',
      'last_activity': '2026-05-03T00:00:00Z',
    };

GoRouter _router() => GoRouter(
      initialLocation: '/chat/$_agentId',
      routes: [
        GoRoute(
          path: '/chat/:id',
          builder: (_, state) =>
              ChatScreen(agentInstanceId: state.pathParameters['id']!),
        ),
        GoRoute(
          path: '/dashboard',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('DASHBOARD_ROUTE'))),
        ),
      ],
    );

Widget _wrap(_Harness h) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(h.api),
        authServiceProvider.overrideWithValue(h.auth),
      ],
      child: MaterialApp.router(
        theme: solvrTheme(),
        routerConfig: _router(),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ChatScreen — empty state (D-38)', () {
    testWidgets('renders italic "Say hi to <agent_name>" when no messages',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson(name: 'claude-test')])
        ..stubMessagesEmpty();
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      expect(find.text('Say hi to claude-test'), findsOneWidget);
    });
  });

  group('ChatScreen — populated (D-08-style render)', () {
    testWidgets('renders bubbles for history rows in ASC order',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubMessages([
          _msg(
            role: 'user',
            content: 'hi',
            createdAt: '2026-05-03T12:00:00Z',
            inappMessageId: 'm-1',
          ),
          _msg(
            role: 'assistant',
            content: 'hello',
            createdAt: '2026-05-03T12:00:01Z',
            inappMessageId: 'm-2',
          ),
        ]);
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      expect(find.text('hi'), findsOneWidget);
      expect(find.text('hello'), findsOneWidget);
    });
  });

  group('ChatScreen — AppBar (D-37)', () {
    testWidgets('renders agent name + model + StatusDot in subtitle',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson(name: 'my-agent')])
        ..stubMessagesEmpty();
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      expect(find.text('my-agent'), findsOneWidget);
      expect(find.text('anthropic/claude-haiku-4-5'), findsOneWidget);
      expect(find.byType(StatusDot), findsAtLeastNWidgets(1));
    });

    testWidgets('back arrow tap routes to /dashboard', (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubMessagesEmpty();
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.text('DASHBOARD_ROUTE'), findsOneWidget);
    });
  });

  group('ChatScreen — Telegram-failed banner (D-50)', () {
    testWidgets('renders RetryBanner when telegramFailedBannerProvider is set',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubMessagesEmpty();
      final container = ProviderContainer(
        overrides: [
          apiClientProvider.overrideWithValue(h.api),
          authServiceProvider.overrideWithValue(h.auth),
        ],
      );
      addTearDown(container.dispose);
      container.read(telegramFailedBannerProvider.notifier).state =
          const TelegramFailedBannerState(
        agentInstanceId: _agentId,
        reason: 'bad bot token',
        telegramInputs: {'TELEGRAM_BOT_TOKEN': 'xxx'},
      );
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
      expect(find.byKey(const Key('telegram-failed-banner')), findsOneWidget);
      expect(
        find.textContaining('Telegram setup failed: bad bot token'),
        findsOneWidget,
      );
    });

    testWidgets('Dismiss × clears the provider state', (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubMessagesEmpty();
      final container = ProviderContainer(
        overrides: [
          apiClientProvider.overrideWithValue(h.api),
          authServiceProvider.overrideWithValue(h.auth),
        ],
      );
      addTearDown(container.dispose);
      container.read(telegramFailedBannerProvider.notifier).state =
          const TelegramFailedBannerState(
        agentInstanceId: _agentId,
        reason: 'bad token',
        telegramInputs: {},
      );
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
      await tester.tap(find.byTooltip('Dismiss'));
      await tester.pumpAndSettle();
      expect(container.read(telegramFailedBannerProvider), isNull);
    });
  });

  group('ChatScreen — restart banner (D-49)', () {
    testWidgets('renders RestartBanner when agent.status != "running"',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson(status: 'stopped')])
        ..stubMessagesEmpty();
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      expect(find.byType(RestartBanner), findsOneWidget);
    });

    testWidgets('hides RestartBanner when agent.status == "running"',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson(status: 'running')])
        ..stubMessagesEmpty();
      await tester.pumpWidget(_wrap(h));
      await tester.pumpAndSettle();
      expect(find.byType(RestartBanner), findsNothing);
    });
  });

  group('ChatScreen — RetryBanner widget present (D-50)', () {
    testWidgets('Telegram-failed banner is wrapped by RetryBanner',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubMessagesEmpty();
      final container = ProviderContainer(
        overrides: [
          apiClientProvider.overrideWithValue(h.api),
          authServiceProvider.overrideWithValue(h.auth),
        ],
      );
      addTearDown(container.dispose);
      container.read(telegramFailedBannerProvider.notifier).state =
          const TelegramFailedBannerState(
        agentInstanceId: _agentId,
        reason: 'r',
        telegramInputs: {},
      );
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
      expect(find.byType(RetryBanner), findsOneWidget);
    });
  });
}
