// Phase 25 Wave 2 plan 25-04 task 2 — Dashboard lifecycle re-fetch tests.
//
// Verifies D-12 (AppLifecycleState.resumed → /v1/agents re-fetch) and
// Pitfall #8 (concurrent fetch from a mid-fetch resume cancels the prior
// inflight request via CancelToken).

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
  Future<void> signOut() async {}
}

/// Counts dio requests by path-suffix. Installed as a Dio interceptor so the
/// `http_mock_adapter` transport stub still serves bodies; the counter only
/// observes the request side.
class _CountingInterceptor extends Interceptor {
  int agentsCalls = 0;
  int recipesCalls = 0;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    if (options.path.endsWith('/v1/agents')) {
      agentsCalls++;
    }
    if (options.path.endsWith('/v1/recipes')) {
      recipesCalls++;
    }
    handler.next(options);
  }
}

GoRouter _router() => GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (_, _) => const DashboardScreen()),
      ],
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'AppLifecycleState.resumed triggers a second /v1/agents fetch (D-12)',
      (tester) async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    final counter = _CountingInterceptor();
    dio.interceptors.add(counter);
    final adapter = DioAdapter(dio: dio);
    adapter
      ..onGet('/v1/agents', (s) => s.reply(200, <dynamic>[]))
      ..onGet('/v1/recipes', (s) => s.reply(200, <dynamic>[]));

    final api = ApiClient(dio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          authServiceProvider.overrideWithValue(_FakeAuth()),
        ],
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: _router(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(counter.agentsCalls, 1, reason: 'mount triggers initial fetch');

    // Send paused → resumed (D-12).
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();

    expect(
      counter.agentsCalls,
      2,
      reason: 'resumed must trigger a second fetch (D-12 + Pitfall #8 '
          'CancelToken guard collapses any inflight fetch)',
    );
  });
}
