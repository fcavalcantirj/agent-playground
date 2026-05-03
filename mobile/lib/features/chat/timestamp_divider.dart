// Phase 25 Wave 4 plan 25-07 task 4 — D-47 inline grouped timestamp divider.
//
// Rendered between bubbles ONLY when next.createdAt - prev.createdAt > 5
// minutes. Caption format:
//   same calendar day  -> 'HH:mm' (24h, e.g. '14:32')
//   different day      -> 'MMM dd HH:mm' (e.g. 'Apr 28 14:32')
// Color: SolvrColors.mutedForeground; size: 12; centered.
//
// Per D-47: NO timestamp on every bubble; NO long-press-to-reveal.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class TimestampDivider extends StatelessWidget {
  const TimestampDivider({required this.label, super.key});

  final String label;

  static const Duration _gapThreshold = Duration(minutes: 5);

  /// Returns a TimestampDivider widget if a divider is warranted between
  /// `prev` and `next`, otherwise null. Caller injects null whenever the
  /// returned widget is null (or wraps it in a conditional spread).
  ///
  /// `now` is a test seam — defaults to `DateTime.now()` so the same-day
  /// branch can be exercised deterministically. Tests pass a fixed value
  /// to assert the format choice.
  static Widget? maybeBuild({
    required ChatMessage? prev,
    required ChatMessage next,
    DateTime? now,
  }) =>
      maybeBuildFromIso(
        prevIso: prev?.createdAt,
        nextIso: next.createdAt,
        now: now,
      );

  /// String-typed counterpart for callers that work with `ChatRow`
  /// (Phase 25 chat scope state) whose `createdAt` is already an ISO-8601
  /// string. Same gap + format logic as [maybeBuild].
  static Widget? maybeBuildFromIso({
    required String? prevIso,
    required String nextIso,
    DateTime? now,
  }) {
    if (prevIso == null) return null; // no divider above first bubble.
    final p = DateTime.tryParse(prevIso);
    final n = DateTime.tryParse(nextIso);
    if (p == null || n == null) return null; // graceful degradation.
    if (n.difference(p) <= _gapThreshold) return null;
    final base = (now ?? DateTime.now()).toLocal();
    final nLocal = n.toLocal();
    final sameDay = nLocal.year == base.year &&
        nLocal.month == base.month &&
        nLocal.day == base.day;
    final fmt = sameDay ? DateFormat('HH:mm') : DateFormat('MMM dd HH:mm');
    return TimestampDivider(label: fmt.format(nLocal));
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        child: Center(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              color: SolvrColors.mutedForeground,
            ),
          ),
        ),
      );
}
