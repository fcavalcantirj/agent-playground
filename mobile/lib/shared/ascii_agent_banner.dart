// Phase 25 Wave 1 D-17 + UI-SPEC §Component 3.
//
// Matrix-aesthetic cycling JetBrains Mono banner. The widget is "dumb" —
// the consumer (Wave 2 DashboardScreen) supplies a Stream<List<String>>
// keyed off `recipesProvider` which sources names from GET /v1/recipes.
// Recipe names are NEVER hardcoded here (Golden Rule #2 / UI-SPEC line 314).
// On empty/loading streams, falls back to a static ['solvr_labs'] for
// graceful degradation per UI-SPEC line 315.
//
// Cycles every `intervalMs` (default 2000ms) with a cross-fade through
// AnimatedSwitcher, easeInOut 300ms (resolves D-Discretion line 499).

import 'dart:async';

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class AsciiAgentBanner extends StatefulWidget {
  const AsciiAgentBanner({
    required this.namesStream,
    this.intervalMs = 2000,
    super.key,
  });

  final Stream<List<String>> namesStream;
  final int intervalMs;

  @override
  State<AsciiAgentBanner> createState() => _AsciiAgentBannerState();
}

class _AsciiAgentBannerState extends State<AsciiAgentBanner> {
  // Static fallback when the stream is empty/loading. Single name keeps
  // the banner visible; the consumer is responsible for supplying the
  // live recipe list once GET /v1/recipes resolves.
  static const List<String> _fallback = ['solvr_labs'];

  List<String> _names = _fallback;
  int _index = 0;
  Timer? _timer;
  StreamSubscription<List<String>>? _sub;

  @override
  void initState() {
    super.initState();
    _sub = widget.namesStream.listen((names) {
      if (!mounted) return;
      setState(() {
        _names = names.isEmpty ? _fallback : names;
        if (_names.isNotEmpty) {
          _index = _index % _names.length;
        }
      });
    });
    _timer = Timer.periodic(
      Duration(milliseconds: widget.intervalMs),
      (_) {
        if (!mounted || _names.isEmpty) return;
        setState(() => _index = (_index + 1) % _names.length);
      },
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    unawaited(_sub?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final name = _names.isEmpty ? _fallback.first : _names[_index];
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      switchInCurve: Curves.easeInOut,
      switchOutCurve: Curves.easeInOut,
      child: Text(
        name,
        key: ValueKey(name),
        textAlign: TextAlign.center,
        style: SolvrTextStyles.mono(
          fontSize: 28,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
