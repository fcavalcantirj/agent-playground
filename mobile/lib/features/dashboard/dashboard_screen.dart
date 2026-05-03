// Phase 25 Wave 1 stub — replaced by Wave 2 plan 25-04 (Dashboard).
//
// The router needs a buildable widget so main.dart can compile and the
// /dashboard route resolves at boot. Wave 2 swaps the body for the real
// agent list (D-08..D-20).

import 'package:flutter/material.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('>_ SOLVR_LABS')),
      body: const Center(child: Text('Dashboard — coming Wave 2')),
    );
  }
}
