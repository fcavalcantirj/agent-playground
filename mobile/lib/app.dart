// Phase 24 Wave 1 — minimum viable root widget. Plan 02 wires solvrTheme;
// Plan 06 wires the go_router config + HealthzScreen route.
// For now we render a single placeholder Scaffold so analyze + smoke_test pass.

import 'package:flutter/material.dart';

class SolvrLabsApp extends StatelessWidget {
  const SolvrLabsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Solvr Labs',
      home: Scaffold(
        body: Center(child: Text('Solvr Labs — booting...')),
      ),
    );
  }
}
