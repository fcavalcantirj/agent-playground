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
  const UsageChart({
    required this.entries,
    this.slots = 7,
    super.key,
  });

  final List<AgentSeriesEntry> entries;

  /// Fixed slot count — the chart pads missing days so a single-day
  /// dataset doesn't render as one full-width slab.
  final int slots;

  @override
  Widget build(BuildContext context) {
    final padded = _padToSlots(entries, slots);
    final hasAny = padded.any((v) => v > 0);
    if (!hasAny) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          'No activity in last $slots days',
          style: const TextStyle(
            fontSize: 12,
            color: SolvrColors.mutedForeground,
          ),
        ),
      );
    }
    return CustomPaint(
      size: Size.infinite,
      painter: _UsageChartPainter(padded),
    );
  }
}

List<double> _padToSlots(List<AgentSeriesEntry> entries, int slots) {
  // Index by day string for O(1) lookup; server returns ISO YYYY-MM-DD.
  final byDay = <String, double>{
    for (final e in entries) e.day: double.tryParse(e.costUsd) ?? 0,
  };
  final today = DateTime.now();
  final todayDay = DateTime(today.year, today.month, today.day);
  final out = List<double>.filled(slots, 0);
  for (var i = 0; i < slots; i++) {
    final d = todayDay.subtract(Duration(days: slots - 1 - i));
    final key =
        '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    out[i] = byDay[key] ?? 0;
  }
  return out;
}

class _UsageChartPainter extends CustomPainter {
  _UsageChartPainter(this.values);

  final List<double> values;

  @override
  void paint(Canvas canvas, Size size) {
    final track = Paint()..color = SolvrColors.muted;
    canvas.drawRect(
      Rect.fromLTWH(0, size.height - 1, size.width, 1),
      track,
    );

    if (values.isEmpty) return;

    final maxValue = values.fold<double>(0, (a, b) => a > b ? a : b);
    if (maxValue <= 0) return;

    final n = values.length;
    final slotWidth = size.width / n;
    final barWidth = slotWidth * 0.7;
    final barPad = (slotWidth - barWidth) / 2;
    final bar = Paint()..color = SolvrColors.foreground;

    for (var i = 0; i < n; i++) {
      if (values[i] <= 0) continue;
      final h = (values[i] / maxValue) * size.height;
      final x = (slotWidth * i) + barPad;
      final y = size.height - h;
      canvas.drawRect(Rect.fromLTWH(x, y, barWidth, h), bar);
    }
  }

  @override
  bool shouldRepaint(covariant _UsageChartPainter old) =>
      !identical(old.values, values);
}
