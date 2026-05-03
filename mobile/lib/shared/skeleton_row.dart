// Phase 25 Wave 1 D-18 + UI-SPEC §Component 5.
//
// Loading-state placeholder. 56 dp tall (matches Dashboard row geometry).
// 3 grey bars stacked vertically with 4 px gap. Last bar right-aligned to
// mirror `last_activity` placement. No animation in MVP.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class SkeletonRow extends StatelessWidget {
  const SkeletonRow({
    this.height = 56,
    this.bars = const [0.6, 0.4, 0.15],
    super.key,
  });

  final double height;
  final List<double> bars;

  static const List<double> _barHeights = [12, 10, 8];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final available = constraints.maxWidth;
            final children = <Widget>[];
            for (var i = 0; i < bars.length; i++) {
              final barHeight =
                  i < _barHeights.length ? _barHeights[i] : 8.0;
              final isLast = i == bars.length - 1;
              final bar = Container(
                width: available * bars[i],
                height: barHeight,
                color: SolvrColors.muted,
              );
              children.add(
                isLast
                    ? Align(alignment: Alignment.centerRight, child: bar)
                    : bar,
              );
              if (i < bars.length - 1) {
                children.add(const SizedBox(height: 4));
              }
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: children,
            );
          },
        ),
      ),
    );
  }
}
