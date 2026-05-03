// Phase 25 Wave 2 plan 25-04 task 2 — DashboardScreen widget tests.
//
// Covers UI-01 + D-07 / D-08 / D-10 / D-11 / D-17 / D-18 / D-19. The
// agentsList feed is mocked at the dio transport via http_mock_adapter
// (Phase 24 dev_dependency) — apiClientProvider is overridden with a real
// ApiClient bound to a stubbed Dio. recipesProvider is also exercised so
// the empty-state banner has a names stream.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/agent_row.dart';
import 'package:agent_playground/features/dashboard/dashboard_screen.dart';
import 'package:agent_playground/shared/ascii_agent_banner.dart';
import 'package:agent_playground/shared/empty_state_scaffold.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:agent_playground/shared/skeleton_row.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

class _FakeAuth implements AuthService {
  int signOutCalls = 0;
  @override
  Future<Result<SessionUser>> signInWithGoogle() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<Result<SessionUser>> signInWithGithub() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
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

  void stubAgents(List<Map<String, dynamic>> rows, {int status = 200}) {
    adapter.onGet('/v1/agents', (s) => s.reply(status, rows));
  }

  void stubAgentsError() {
    adapter.onGet(
      '/v1/agents',
      (s) => s.reply(500, <String, dynamic>{
        'error': {
          'type': 'api_error',
          'code': 'INTERNAL',
          'message': 'boom',
        },
      }),
    );
  }

  void stubRecipes(List<Map<String, dynamic>> rows) {
    adapter.onGet('/v1/recipes', (s) => s.reply(200, {'recipes': rows}));
  }
}

Map<String, dynamic> _agentJson({
  String id = 'a-1',
  String name = 'claude-test-1',
  String model = 'anthropic/claude-haiku-4-5',
  String status = 'running',
  String? lastActivity,
}) =>
    {
      'id': id,
      'name': name,
      'recipe_name': 'openclaw',
      'model': model,
      'status': status,
      'created_at': '2026-05-03T00:00:00Z',
      if (lastActivity != null) 'last_activity': lastActivity,
    };

GoRouter _router(Widget Function() dashboard, {String initial = '/'}) {
  return GoRouter(
    initialLocation: initial,
    routes: [
      GoRoute(path: '/', builder: (_, _) => dashboard()),
      GoRoute(
        path: '/login',
        builder: (_, _) =>
            const Scaffold(body: Center(child: Text('LOGIN_ROUTE'))),
      ),
      GoRoute(
        path: '/new-agent/clone',
        builder: (_, _) =>
            const Scaffold(body: Center(child: Text('NEW_AGENT_CLONE'))),
      ),
      GoRoute(
        path: '/chat/:id',
        builder: (_, state) => Scaffold(
          body:
              Center(child: Text('CHAT_ROUTE_${state.pathParameters['id']}')),
        ),
      ),
    ],
  );
}

Widget _wrap(_Harness h, GoRouter router) {
  return ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(h.api),
      authServiceProvider.overrideWithValue(h.auth),
    ],
    child: MaterialApp.router(
      theme: solvrTheme(),
      routerConfig: router,
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DashboardScreen — visual states', () {
    testWidgets('LOADING: renders 3 SkeletonRow widgets while fetch is inflight',
        (tester) async {
      final h = _Harness();
      // Never resolve the agents call so loading state persists.
      h.adapter.onGet(
        '/v1/agents',
        (s) async {
          await Future<void>.delayed(const Duration(seconds: 5));
          return s.reply(200, <dynamic>[]);
        },
      );
      h.stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      // Pump a single frame — provider future not yet resolved.
      await tester.pump();
      expect(find.byType(SkeletonRow), findsNWidgets(3));
      // Drain pending future before tearing down to avoid "timer pending".
      await tester.pump(const Duration(seconds: 6));
      await tester.pumpAndSettle();
    });

    testWidgets('EMPTY: renders EmptyStateScaffold + AsciiAgentBanner + '
        '"Deploy your first agent" button (D-17)', (tester) async {
      final h = _Harness()
        ..stubAgents(const [])
        ..stubRecipes(const [
          {'name': 'openclaw', 'channels_supported': ['inapp']},
          {'name': 'hermes', 'channels_supported': ['inapp']},
        ]);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      expect(find.byType(EmptyStateScaffold), findsOneWidget);
      expect(find.byType(AsciiAgentBanner), findsOneWidget);
      expect(find.text('No agents yet'), findsOneWidget);
      expect(find.text('Deploy your first agent'), findsOneWidget);
    });

    testWidgets('EMPTY → tap "Deploy your first agent" navigates to '
        '/new-agent/clone (D-11/D-17)', (tester) async {
      final h = _Harness()
        ..stubAgents(const [])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Deploy your first agent'));
      await tester.pumpAndSettle();
      expect(find.text('NEW_AGENT_CLONE'), findsOneWidget);
    });

    testWidgets('POPULATED: renders 3 AgentRow widgets in last_activity desc '
        'order (D-08/D-13)', (tester) async {
      final h = _Harness()
        ..stubAgents([
          _agentJson(
            id: 'a-old',
            name: 'old-agent',
            lastActivity: '2026-05-01T00:00:00Z',
          ),
          _agentJson(
            id: 'a-new',
            name: 'new-agent',
            lastActivity: '2026-05-03T00:00:00Z',
          ),
          _agentJson(
            id: 'a-mid',
            name: 'mid-agent',
            lastActivity: '2026-05-02T00:00:00Z',
            status: 'failed',
          ),
        ])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      expect(find.byType(AgentRow), findsNWidgets(3));
      // Order: new (2026-05-03) → mid → old.
      final names = tester
          .widgetList<AgentRow>(find.byType(AgentRow))
          .map((r) => r.agent.name)
          .toList();
      expect(names, ['new-agent', 'mid-agent', 'old-agent']);
    });

    testWidgets('POPULATED → tap row pushes /chat/<agent.id> (D-08)',
        (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson(id: 'a-1', name: 'claude-test-1')])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(AgentRow));
      await tester.pumpAndSettle();
      expect(find.text('CHAT_ROUTE_a-1'), findsOneWidget);
    });

    testWidgets('FAB: tap FloatingActionButton routes to /new-agent/clone '
        '(D-11)', (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('dashboard-fab')));
      await tester.pumpAndSettle();
      expect(find.text('NEW_AGENT_CLONE'), findsOneWidget);
    });
  });

  group('DashboardScreen — bottom nav (D-10)', () {
    testWidgets('renders Home/Browse/Profile destinations', (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Browse'), findsOneWidget);
      expect(find.text('Profile'), findsOneWidget);
    });

    testWidgets('Browse + Profile taps are no-ops (D-10)', (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson(id: 'a-1', name: 'foo')])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Browse'));
      await tester.pumpAndSettle();
      // Still on Dashboard — agent row visible (no route change occurred).
      expect(find.byType(AgentRow), findsOneWidget);
      await tester.tap(find.text('Profile'));
      await tester.pumpAndSettle();
      expect(find.byType(AgentRow), findsOneWidget);
    });
  });

  group('DashboardScreen — sign out (D-07)', () {
    testWidgets('overflow → "Sign out" → ConfirmDialog → confirm calls '
        'signOut + navigates to /login', (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('More'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sign out').last);
      await tester.pumpAndSettle();
      expect(find.text('Sign out of Solvr Labs?'), findsOneWidget);
      // Confirm.
      await tester.tap(find.widgetWithText(TextButton, 'Sign out'));
      await tester.pumpAndSettle();
      expect(h.auth.signOutCalls, 1);
      expect(find.text('LOGIN_ROUTE'), findsOneWidget);
    });

    testWidgets('overflow → "Sign out" → Cancel: no signOut, no nav',
        (tester) async {
      final h = _Harness()
        ..stubAgents([_agentJson()])
        ..stubRecipes(const []);
      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('More'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sign out').last);
      await tester.pumpAndSettle();
      expect(find.text('Sign out of Solvr Labs?'), findsOneWidget);
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();
      expect(h.auth.signOutCalls, 0);
      // Still on Dashboard (agent row visible).
      expect(find.byType(AgentRow), findsOneWidget);
    });
  });

  group('DashboardScreen — fetch error post-load (D-19)', () {
    testWidgets('cold-load failure → centered RetryBanner, no AgentRow',
        (tester) async {
      final h = _Harness()
        ..stubAgentsError()
        ..stubRecipes(const []);
      // Capture FlutterErrors emitted by Riverpod's uncaught AsyncNotifier
      // rejection — without this hook the test framework treats them as a
      // failed test even though the widget surfaces the failure correctly.
      final captured = <FlutterErrorDetails>[];
      final priorOnError = FlutterError.onError;
      FlutterError.onError = captured.add;
      addTearDown(() => FlutterError.onError = priorOnError);

      await tester.pumpWidget(_wrap(h, _router(DashboardScreen.new)));
      // Walk the AsyncValue<List<AgentSummary>> through:
      //   pump1: provider build started → loading
      //   pump2: dio rejected → AsyncError → DashboardScreen rebuild
      //   pump3: ListView/Center settles
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.byType(RetryBanner), findsOneWidget);
      expect(find.byType(AgentRow), findsNothing);
    });
  });
}
