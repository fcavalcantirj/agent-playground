// Phase 27 Change 3b Wave 4 — minimal CustomPainter bar chart for the
// per-agent breakdown screen. NO new dependency (D-31 — fl_chart isn't
// in pubspec). ~30 lines of paint logic.
//
// Each entry's `costUsd` (parsed) drives the bar height. Bars are
// monochrome (#1F1F1F) over a muted track (#EFEFEC). Empty input
// renders the track at zero height. No animations in v1.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:flutter/material.dart';

class UsageChart extends StatelessWidget {
  const UsageChart({required this.entries, super.key});

  final List<AgentSeriesEntry> entries;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.infinite,
      painter: _UsageChartPainter(entries),
    );
  }
}

class _UsageChartPainter extends CustomPainter {
  _UsageChartPainter(this.entries);

  final List<AgentSeriesEntry> entries;

  @override
  void paint(Canvas canvas, Size size) {
    final track = Paint()..color = SolvrColors.muted;
    canvas.drawRect(
      Rect.fromLTWH(0, size.height - 1, size.width, 1),
      track,
    );

    if (entries.isEmpty) return;

    final values = entries
        .map((e) => double.tryParse(e.costUsd) ?? 0)
        .toList(growable: false);
    final maxValue = values.fold<double>(0, (a, b) => a > b ? a : b);
    if (maxValue <= 0) return;

    final n = entries.length;
    final slotWidth = size.width / n;
    final barWidth = slotWidth * 0.7;
    final barPad = (slotWidth - barWidth) / 2;
    final bar = Paint()..color = SolvrColors.foreground;

    for (var i = 0; i < n; i++) {
      final h = (values[i] / maxValue) * size.height;
      final x = (slotWidth * i) + barPad;
      final y = size.height - h;
      canvas.drawRect(Rect.fromLTWH(x, y, barWidth, h), bar);
    }
  }

  @override
  bool shouldRepaint(covariant _UsageChartPainter old) =>
      !identical(old.entries, entries);
}
