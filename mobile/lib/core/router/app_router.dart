// Phase 24 Plan 06 — go_router config. Single placeholder route in P24;
// Phase 25 fills /dashboard, /new-agent, /chat/:id.

import 'package:agent_playground/features/_placeholder/healthz_screen.dart';
import 'package:go_router/go_router.dart';

GoRouter buildRouter() => GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const HealthzScreen(),
        ),
      ],
    );
