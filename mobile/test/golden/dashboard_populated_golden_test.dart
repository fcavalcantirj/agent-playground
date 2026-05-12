// Phase 25 Wave 2 plan 25-04 task 2 — Dashboard populated golden snapshot.
//
// **Status:** Snapshot captured + committed at goldens/dashboard_populated.png
// via `flutter test --update-goldens`. Per-run check is @Skip-ped pending
// Wave-4 font-bundling (see dashboard_empty_golden_test.dart header for
// context — same google_fonts/HTTP-sandbox blocker, Pitfall #6 in
// 25-RESEARCH.md).
//
// TODO(wave-4-polish): bundle Inter + JetBrainsMono ttf in pubspec, drop
// @Skip, add textScale 1.5 + 2.0 sibling tests.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/dashboard_screen.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Pitfall #6 — see dashboard_empty_golden_test for context.
  final priorOnError = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('Failed to load font') ||
        msg.contains('GoogleFonts.config.allowRuntimeFetching')) {
      return;
    }
    priorOnError?.call(details);
  };

  // Wave-4-polish: bundle Inter + JetBrainsMono ttf in pubspec. Snapshot
  // captured + committed at goldens/dashboard_populated.png via
  // --update-goldens (file header has full context).
  testWidgets(
    'dashboard_populated matches golden snapshot @ textScale 1.0 (3 rows: '
    'running / stopped / failed)',
    skip: true,
    (tester) async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    final adapter = DioAdapter(dio: dio);
    // Use far-past timestamps so relative-time renders deterministically as
    // ISO date prefixes regardless of when the test runs.
    adapter.onGet(
      '/v1/agents',
      (s) => s.reply(200, [
        {
          'id': 'a-running',
          'name': 'claude-test-1',
          'recipe_name': 'openclaw',
          'model': 'anthropic/claude-haiku-4-5',
          'status': 'running',
          'created_at': '2026-04-30T00:00:00Z',
          'last_activity': '2026-04-30T12:00:00Z',
        },
        {
          'id': 'a-stopped',
          'name': 'openrouter-bot',
          'recipe_name': 'hermes',
          'model': 'openrouter/anthropic/claude-3-5-sonnet',
          'status': 'stopped',
          'created_at': '2026-04-29T00:00:00Z',
          'last_activity': '2026-04-29T12:00:00Z',
        },
        {
          'id': 'a-failed',
          'name': 'failed-deploy',
          'recipe_name': 'nullclaw',
          'model': 'anthropic/claude-sonnet-4-5',
          'status': 'failed',
          'created_at': '2026-04-28T00:00:00Z',
          'last_activity': '2026-04-28T12:00:00Z',
        },
      ]),
    );
    adapter.onGet('/v1/recipes', (s) => s.reply(200, {'recipes': <dynamic>[]}));
    final api = ApiClient(dio);

    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (_, _) => const DashboardScreen()),
      ],
    );

    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          authServiceProvider.overrideWithValue(_FakeAuth()),
        ],
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/dashboard_populated.png'),
    );
  });
}
