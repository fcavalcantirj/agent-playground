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

import 'package:agent_playground/features/billing/billing_hub_screen.dart';
import 'package:agent_playground/features/billing/checkout_webview_screen.dart';
import 'package:agent_playground/features/billing/topup_screen.dart';
import 'package:agent_playground/features/billing/transactions_screen.dart';
import 'package:agent_playground/features/chat/chat_screen.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/dashboard/dashboard_screen.dart';
import 'package:agent_playground/features/login/email_login_screen.dart';
import 'package:agent_playground/features/login/login_screen.dart';
import 'package:agent_playground/features/login/otp_input_screen.dart';
import 'package:agent_playground/features/new_agent/clone_step.dart';
import 'package:agent_playground/features/new_agent/deploy_step.dart';
import 'package:agent_playground/features/new_agent/model_picker_screen.dart';
import 'package:agent_playground/features/new_agent/model_step.dart';
import 'package:agent_playground/features/retry_bootstrap/retry_bootstrap_screen.dart';
import 'package:agent_playground/features/settings/settings_screen.dart';
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
class DashboardRefreshObserver extends NavigatorObserver {
  DashboardRefreshObserver(this._ref);

  final WidgetRef _ref;

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    // Cheap: ref.invalidate marks the cache stale. The actual GET
    // /v1/agents only fires if the dashboard widget is currently
    // subscribing (i.e. visible). Off-screen no network round-trip.
    _ref.invalidate(agentsListProvider);
  }

  // #16 — Phase B post-UAT fix: go_router's context.go() between sibling
  // top-level routes (e.g. /chat/:id → /dashboard, /new-agent/* →
  // /dashboard, /new-agent/name-deploy → /chat/:id) fires didReplace,
  // NOT didPop. Without this override, every chat-back / wizard-close /
  // deploy-success transition fails to refresh the dashboard's agent
  // list. Symptom: status icon stayed stale after a chat-side restart
  // until the user re-entered + re-exited the chat. Same handler as
  // didPop — invalidate, the watching dashboard refetches, off-screen
  // no-op.
  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    _ref.invalidate(agentsListProvider);
  }

  // go_router fires didPush (NOT didReplace) for sibling-route swaps
  // when both routes are top-level peers (verified by Phase B post-UAT
  // tracing: /a → /b → /a fires didPush twice, didReplace zero times).
  // Skip the very first push (initial route mount) — there's nothing
  // stale on first paint and we want to avoid an unnecessary fetch.
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    if (previousRoute == null) return;
    _ref.invalidate(agentsListProvider);
  }
}

GoRouter buildRouter({String initialLocation = '/login', WidgetRef? ref}) =>
    GoRouter(
      initialLocation: initialLocation,
      observers: ref == null ? const [] : [DashboardRefreshObserver(ref)],
      routes: [
        GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
        // 2026-05-12 — magic-link OTP login (step 1: enter email).
        GoRoute(
          path: '/login/email',
          builder: (_, _) => const EmailLoginScreen(),
        ),
        // 2026-05-12 — magic-link OTP login (step 2: enter 6-digit code).
        GoRoute(
          path: '/login/email/code',
          builder: (_, state) => OtpInputScreen(
            email: state.uri.queryParameters['email'] ?? '',
          ),
        ),
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
        // Track 2 (#18) — billing hub. Entry point from the AppBar
        // tier badge + dashboard/chat overflow menu. Surfaces tier
        // status, balance (Ultra), top-up CTA, transactions tile.
        GoRoute(
          path: '/billing',
          builder: (_, _) => const BillingHubScreen(),
        ),
        // Phase B Plan 11 — billing surface routes.
        // TopUpScreen + CheckoutWebViewScreen + TransactionsScreen are
        // all real screens; the Plan 10 _stubs.dart file has been
        // deleted.
        GoRoute(
          path: '/billing/topup',
          builder: (_, _) => const TopUpScreen(),
        ),
        GoRoute(
          path: '/billing/checkout',
          builder: (_, state) {
            // success_url returns /billing/checkout?session_id=<cs>
            // (D-21 webview-internal sentinel) — the URL itself is read
            // here when the screen builds. Plan 11's CheckoutWebViewScreen
            // takes the Stripe-hosted URL as a constructor arg via
            // `state.extra`; the stub takes the query param so the route
            // is wired today and Plan 11 can switch on either shape.
            final url = state.uri.queryParameters['url'] ?? '';
            return CheckoutWebViewScreen(checkoutUrl: url);
          },
        ),
        GoRoute(
          path: '/billing/transactions',
          builder: (_, _) => const TransactionsScreen(),
        ),
        // App Store Guideline 5.1.1(v) — in-app account deletion lives
        // here, alongside Privacy/Terms/Support links + Sign out.
        GoRoute(
          path: '/settings',
          builder: (_, _) => const SettingsScreen(),
        ),
      ],
    );
