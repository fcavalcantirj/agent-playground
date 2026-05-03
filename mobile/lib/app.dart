// Phase 25 Wave 1 — root MaterialApp.router.
//
// Threads `initialRoute` from main.dart's cold-start probe, primes the
// AppLifecycleNotifier (Mechanism §1) at boot, subscribes to AuthEventBus
// for D-03 mid-session 401 → /login redirect with the signed-out banner,
// and listens to loginSuccessProvider so a successful sign-in routes to
// /dashboard with router.go (replace, NOT push).

import 'dart:async';

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:agent_playground/core/router/app_router.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SolvrLabsApp extends ConsumerStatefulWidget {
  const SolvrLabsApp({super.key, this.initialRoute = '/login'});

  final String initialRoute;

  @override
  ConsumerState<SolvrLabsApp> createState() => _SolvrLabsAppState();
}

class _SolvrLabsAppState extends ConsumerState<SolvrLabsApp> {
  late final GoRouter _router = buildRouter(
    initialLocation: widget.initialRoute,
  );
  StreamSubscription<void>? _authSub;

  @override
  void initState() {
    super.initState();
    // D-03 — any 401 mid-session: clear session_id (AuthInterceptor already
    // does), set the signed-out banner, route to /login.
    _authSub = ref.read(authEventBusProvider).events.listen((_) {
      ref.read(showSignedOutBannerProvider.notifier).state = true;
      _router.go('/login');
    });
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
        ref
          ..read(loginSuccessProvider.notifier).state = null
          ..read(showSignedOutBannerProvider.notifier).state = false;
        _router.go('/dashboard');
      }
    });

    return MaterialApp.router(
      title: 'Solvr Labs',
      theme: solvrTheme(),
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}
