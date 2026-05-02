// Phase 24 Plan 06 — placeholder screen.
//
// The ONLY Phase 24 screen. Calls /healthz through the real theme + real
// interceptor chain + real router. NO debug menu, NO env banner, NO
// developer-only chrome (CONTEXT line 19-22, D-44).

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class HealthzScreen extends ConsumerStatefulWidget {
  const HealthzScreen({super.key});

  @override
  ConsumerState<HealthzScreen> createState() => _HealthzScreenState();
}

class _HealthzScreenState extends ConsumerState<HealthzScreen> {
  Result<HealthOk>? _result;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  Future<void> _refresh() async {
    if (_loading) return;
    setState(() => _loading = true);
    final api = ref.read(apiClientProvider);
    final r = await api.healthz();
    if (!mounted) return;
    setState(() {
      _result = r;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = _result;
    Widget body;
    if (_loading || state == null) {
      body = const CircularProgressIndicator();
    } else {
      body = switch (state) {
        Ok(:final value) => Text(
            value.ok ? 'OK' : 'NOT OK',
            style: SolvrTextStyles.mono(fontSize: 24),
          ),
        Err(:final error) => Text(
            'ERROR: ${error.code.name} — ${error.message}',
            style: SolvrTextStyles.mono(fontSize: 16),
          ),
      };
    }

    return Scaffold(
      appBar: AppBar(title: const Text('>_ SOLVR_LABS')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              body,
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: _loading ? null : _refresh,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
