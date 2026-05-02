// Phase 24 Plan 06 — root MaterialApp.router.

import 'package:agent_playground/core/router/app_router.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SolvrLabsApp extends ConsumerStatefulWidget {
  const SolvrLabsApp({super.key});

  @override
  ConsumerState<SolvrLabsApp> createState() => _SolvrLabsAppState();
}

class _SolvrLabsAppState extends ConsumerState<SolvrLabsApp> {
  late final GoRouter _router = buildRouter();

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Solvr Labs',
      theme: solvrTheme(),
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}
