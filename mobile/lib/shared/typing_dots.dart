// Phase 25 Wave 1 D-41 + UI-SPEC §Component 6.
//
// 3 dots, 6px diameter, 4px gap, staggered fade 0.3 → 1.0 → 0.3,
// 1200ms total cycle, offsets 0/400/800ms (≈0.0/0.33/0.66 of period).
// Single AnimationController + AnimatedBuilder per UI-SPEC line 382 —
// no extra animation runtime / no third-party motion package dep
// (D-Discretion resolution line 502).

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class TypingDots extends StatefulWidget {
  const TypingDots({this.color, super.key});

  final Color? color;

  @override
  State<TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctl = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  // Triangle wave 0.3 → 1.0 → 0.3 with the given phase offset (0..1 of
  // the 1200ms cycle).
  double _opacityAt(double offsetSeconds) {
    final t = (_ctl.value - offsetSeconds) % 1.0;
    if (t < 0.5) return 0.3 + 0.7 * (t * 2);
    return 1.0 - 0.7 * ((t - 0.5) * 2);
  }

  Widget _dot(double offset) => AnimatedBuilder(
        animation: _ctl,
        builder: (_, child) => Opacity(
          opacity: _opacityAt(offset),
          child: Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: widget.color ?? SolvrColors.mutedForeground,
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _dot(0),
        const SizedBox(width: 4),
        _dot(0.33),
        const SizedBox(width: 4),
        _dot(0.66),
      ],
    );
  }
}
