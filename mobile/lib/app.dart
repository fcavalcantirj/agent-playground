// Phase 25 Wave 1 — root MaterialApp.router.
//
// Threads `initialRoute` from main.dart's cold-start probe, primes the
// AppLifecycleNotifier (Mechanism §1) at boot, subscribes to AuthEventBus
// for D-03 mid-session 401 → /login redirect with the signed-out banner,
// and listens to loginSuccessProvider so a successful sign-in routes to
// /dashboard with router.go (replace, NOT push).

import 'dart:async';

import 'package:agent_playground/core/api/dtos.dart' show SessionUser;
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:agent_playground/core/router/app_router.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/billing/iap_service.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

class SolvrLabsApp extends ConsumerStatefulWidget {
  const SolvrLabsApp({super.key, this.initialRoute = '/login'});

  final String initialRoute;

  @override
  ConsumerState<SolvrLabsApp> createState() => _SolvrLabsAppState();
}

class _SolvrLabsAppState extends ConsumerState<SolvrLabsApp> {
  late final GoRouter _router = buildRouter(
    initialLocation: widget.initialRoute,
    ref: ref,
  );
  StreamSubscription<void>? _authSub;

  @override
  void initState() {
    super.initState();
    // D-03 — any 401 mid-session: clear session_id (AuthInterceptor already
    // does), set the signed-out banner, route to /login.
    _authSub = ref.read(authEventBusProvider).events.listen((_) {
      ref.read(showSignedOutBannerProvider.notifier).state = true;
      // D-16 / WR-01 — drop the Sentry user-context tag on sign-out so any
      // subsequent unauthenticated capture doesn't carry the stale user id.
      Sentry.configureScope((scope) => scope.setUser(null));
      // Also log the RC SDK out so a subsequent anonymous purchase doesn't
      // get attributed to the prior user. No-op on web / un-configured.
      unawaited(IapService.instance.logout());
      _router.go('/login');
    });
    // On cold-start with an existing session, the route resolver routes
    // straight to /dashboard without firing loginSuccessProvider. Probe
    // /v1/users/me once at startup; if it returns a SessionUser, bind
    // both Sentry user-context AND IapService.appUserID. This lets a
    // returning Pro user upgrade-to-purchase without first signing out
    // and back in.
    unawaited(_bindSessionUserOnStart());
  }

  Future<void> _bindSessionUserOnStart() async {
    final r = await ref.read(apiClientProvider).usersMe();
    if (!mounted) return;
    if (r is Ok<SessionUser>) {
      Sentry.configureScope(
        (scope) => scope.setUser(SentryUser(id: r.value.id)),
      );
      await IapService.instance.identify(r.value.id);
    }
  }

  @override
  void dispose() {
    unawaited(_authSub?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Prime the lifecycle notifier so the WidgetsBindingObserver registers
    // from boot. Wave 2 Dashboard + Wave 4 Chat ref.listen this.
    ref.watch(appLifecycleProvider);

    // D-04..D-06 success path — a successful sign-in publishes the
    // SessionUser via loginSuccessProvider; the router replaces with
    // /dashboard (NOT push — back from Dashboard does not return to Login).
    // ignore: cascade_invocations
    ref.listen(loginSuccessProvider, (prev, next) {
      if (next != null) {
        // D-16 / WR-01 — tag Sentry events with the authenticated user id
        // (ID-only, no PII) so mobile crashes get the same user-context
        // bridge as the api_server's session middleware.
        //
        // Phase B Plan 12 (AMD-04) — also seed `tier='free'` as the
        // initial scope tag. The usageSummaryProvider listener below
        // refines it to the authoritative tier once the first
        // /v1/usage/summary call lands (5-15s after sign-in typically).
        // setTag (NOT setExtra/setContexts) so the tier is searchable
        // in Sentry's issue list — the planning truth's `setData` is
        // a typo; Sentry Scope's actual surface is setTag/setExtra/
        // setContexts (sentry-flutter 9.20.0). setTag fits the
        // low-cardinality enum (free|pro|ultra) shape best.
        Sentry.configureScope((scope) {
          scope
            ..setUser(SentryUser(id: next.id))
            ..setTag('tier', 'free');
        });
        // RevenueCat IAP — bind our user_id to RC's appUserID so the
        // /v1/billing/revenuecat/webhook handler can resolve purchases
        // back to the right users row. No-op when the RC SDK key isn't
        // configured for this platform (web, or dart-define unset in dev).
        unawaited(IapService.instance.identify(next.id));
        ref
          ..read(loginSuccessProvider.notifier).state = null
          ..read(showSignedOutBannerProvider.notifier).state = false;
        _router.go('/dashboard');
      }
    });

    // Phase B Plan 12 (AMD-04) — refresh Sentry user-context tier on
    // every usage summary fetch. UsageSummaryProvider polls
    // /v1/usage/summary on mount + AppLifecycleState.resumed, so a tier
    // flip (D-04 — Stripe webhook → users.tier mutation) is reflected
    // in Sentry within the latency of the next foreground refresh
    // (5-15s typical, backstopped by the dashboard ticker's poll
    // cadence). Tier is one of `free | pro | ultra` per D-01 — not
    // PII, safe to surface in crash reports per the threat model
    // T-B-LK disposition.
    // ignore: cascade_invocations
    ref.listen<AsyncValue<UsageSummary>>(usageSummaryProvider, (prev, next) {
      next.whenData((summary) {
        Sentry.configureScope(
          (scope) => scope.setTag('tier', summary.tier),
        );
      });
    });

    return MaterialApp.router(
      title: 'Solvr Labs',
      theme: solvrTheme(),
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}
