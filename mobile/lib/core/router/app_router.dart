// Phase 25 Wave 1 — go_router config (D-21 / D-26 / D-60).
//
// Replaces the Phase 24 single-route placeholder. Eight routes:
//   /login                     — D-04..D-06 Login
//   /retry-bootstrap           — D-02 cold-start retry
//   /dashboard                 — Wave 2 stub (D-08..D-20)
//   /new-agent/clone           — Wave 3 stub (D-21 step 1)
//   /new-agent/model           — Wave 3 stub (D-22 step 2)
//   /new-agent/model/picker    — Wave 3 stub (D-26 push-route picker)
//   /new-agent/name-deploy     — Wave 3 stub (D-22 step 3)
//   /chat/:agentInstanceId     — Wave 4 stub (D-35..D-53)
//
// `initialLocation` is resolved at boot by main.dart's resolveInitialRoute
// against GET /v1/users/me (D-01..D-02).

import 'package:agent_playground/features/chat/chat_screen.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/dashboard/dashboard_screen.dart';
import 'package:agent_playground/features/login/login_screen.dart';
import 'package:agent_playground/features/new_agent/clone_step.dart';
import 'package:agent_playground/features/new_agent/deploy_step.dart';
import 'package:agent_playground/features/new_agent/model_picker_screen.dart';
import 'package:agent_playground/features/new_agent/model_step.dart';
import 'package:agent_playground/features/retry_bootstrap/retry_bootstrap_screen.dart';
import 'package:agent_playground/features/usage/agent_usage_screen.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// Phase 25 Wave 5: invalidates `agentsListProvider` whenever any
/// route pops back to /dashboard. Catches every entry path (system
/// back gesture, X close, route.push pop, programmatic context.pop)
/// without per-screen plumbing — the previous attempt of invalidating
/// in ChatScreen.dispose / WizardShell._onClose missed the system
/// back-gesture path during the wizard's deploy step. Reading is
/// cheap because Riverpod caches; the network round-trip only fires
/// when the dashboard widget is actually visible.
class _DashboardRefreshObserver extends NavigatorObserver {
  _DashboardRefreshObserver(this._ref);

  final WidgetRef _ref;

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    // Cheap: ref.invalidate marks the cache stale. The actual GET
    // /v1/agents only fires if the dashboard widget is currently
    // subscribing (i.e. visible). Off-screen no network round-trip.
    _ref.invalidate(agentsListProvider);
  }
}

GoRouter buildRouter({String initialLocation = '/login', WidgetRef? ref}) =>
    GoRouter(
      initialLocation: initialLocation,
      observers: ref == null ? const [] : [_DashboardRefreshObserver(ref)],
      routes: [
        GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
        GoRoute(
          path: '/retry-bootstrap',
          builder: (_, _) => const RetryBootstrapScreen(),
        ),
        GoRoute(
          path: '/dashboard',
          builder: (_, _) => const DashboardScreen(),
        ),
        GoRoute(
          path: '/new-agent/clone',
          builder: (_, _) => const CloneStep(),
        ),
        GoRoute(
          path: '/new-agent/model',
          builder: (_, _) => const ModelStep(),
        ),
        GoRoute(
          path: '/new-agent/model/picker',
          builder: (_, _) => const ModelPickerScreen(),
        ),
        GoRoute(
          path: '/new-agent/name-deploy',
          builder: (_, _) => const DeployStep(),
        ),
        GoRoute(
          path: '/chat/:agentInstanceId',
          builder: (_, state) => ChatScreen(
            agentInstanceId: state.pathParameters['agentInstanceId']!,
          ),
        ),
        // Phase 27 Change 3b — per-agent BYOK usage breakdown.
        GoRoute(
          path: '/agents/:id/usage',
          builder: (_, state) => AgentUsageScreen(
            agentId: state.pathParameters['id']!,
          ),
        ),
      ],
    );
