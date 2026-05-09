// #16 — Phase B post-UAT fix: ensure that go_router's context.go() between
// sibling top-level routes (e.g. /chat/:id → /dashboard) reliably nudges
// agentsListProvider to refetch.
//
// go_router fires NavigatorObserver.didReplace (NOT didPop) for sibling
// route swaps. The pre-fix observer only overrode didPop, so chat-back /
// wizard-close / deploy-success transitions silently leaked the stale
// agent status (icon stayed gray after a chat-side restart until the
// user re-entered + re-exited chat). This test gates the fix.
//
// Strategy: mount a minimal 2-route GoRouter wired with the production
// `DashboardRefreshObserver`, then navigate /a → /b via context.go and
// assert agentsListProvider.refetch fires (counter increments on the
// dio adapter).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/router/app_router.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'DashboardRefreshObserver.didReplace invalidates agentsListProvider '
    '(sibling-go path — flicker fix)',
    (tester) async {
      var agentsListHits = 0;

      final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
      // Use interceptor to count requests (http_mock_adapter's onGet
      // callback only fires once per registration in some versions —
      // an interceptor counts every wire hit deterministically).
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (opts, handler) {
            if (opts.path == '/v1/agents' && opts.method == 'GET') {
              agentsListHits += 1;
            }
            handler.next(opts);
          },
        ),
      );
      final adapter = DioAdapter(dio: dio);
      final api = ApiClient(dio);
      adapter.onGet(
        '/v1/agents',
        (s) => s.reply(200, {'agents': <Map<String, dynamic>>[]}),
      );

      final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)],
      );
      addTearDown(container.dispose);

      // Build a minimal 2-route GoRouter that wires the prod observer
      // by passing the test ref. Routes /a and /b are top-level
      // siblings — context.go() between them fires didReplace, the
      // exact event that's load-bearing for the fix.
      Widget app() => UncontrolledProviderScope(
            container: container,
            child: Consumer(
              builder: (context, ref, _) {
                final router = GoRouter(
                  initialLocation: '/a',
                  observers: [DashboardRefreshObserver(ref)],
                  routes: [
                    GoRoute(
                      path: '/a',
                      builder: (_, _) => Consumer(
                        builder: (ctx, r, _) {
                          // Subscribe — keepAlive prevents disposal,
                          // observer's invalidate triggers refetch on
                          // this active subscription.
                          r.watch(agentsListProvider);
                          return Scaffold(
                            body: Center(
                              child: ElevatedButton(
                                key: const Key('go-b'),
                                onPressed: () => ctx.go('/b'),
                                child: const Text('GO B'),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    GoRoute(
                      path: '/b',
                      builder: (_, _) => Consumer(
                        builder: (ctx, _, _) => Scaffold(
                          body: Center(
                            child: ElevatedButton(
                              key: const Key('go-a'),
                              onPressed: () => ctx.go('/a'),
                              child: const Text('BACK TO A'),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                );
                return MaterialApp.router(
                  theme: solvrTheme(),
                  routerConfig: router,
                );
              },
            ),
          );

      await tester.pumpWidget(app());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump();

      // Initial mount of /a fetched once (Consumer watches the provider).
      final hitsBeforeNav = agentsListHits;
      expect(
        hitsBeforeNav,
        greaterThan(0),
        reason: 'Initial /a mount must fetch /v1/agents (sanity check).',
      );

      // Sibling-go: /a → /b. Fires didReplace.
      await tester.tap(find.byKey(const Key('go-b')));
      await tester.pumpAndSettle();

      // Confirm we're on /b (sanity).
      expect(find.byKey(const Key('go-a')), findsOneWidget);

      // Sibling-go back: /b → /a. Fires didReplace AGAIN. With the fix,
      // the observer invalidates agentsListProvider, /a remounts and
      // its watcher triggers a fresh fetch.
      await tester.tap(find.byKey(const Key('go-a')));
      await tester.pumpAndSettle();

      expect(
        agentsListHits,
        greaterThan(hitsBeforeNav),
        reason:
            'GET /v1/agents must fire after sibling-go back to /a '
            '(didReplace observer hook). Pre-nav hits=$hitsBeforeNav, '
            'post-nav hits=$agentsListHits.',
      );
    },
  );
}
