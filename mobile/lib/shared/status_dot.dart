// Phase 25 Wave 1 D-14 + UI-SPEC §Component 1.
//
// Three-state status indicator on Dashboard rows + Chat AppBar subtitle.
// Color is a SIGNAL, never decoration: green = running, red = failed,
// hollow ring = stopped/exited. Size 8 px default. Wraps Semantics for
// screen readers per UI-SPEC line 273.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class StatusDot extends StatelessWidget {
  const StatusDot({required this.status, this.size = 8, super.key});

  final String status;
  final double size;

  @override
  Widget build(BuildContext context) {
    final spec = _spec(status);
    return Semantics(
      label: 'Agent status: $status',
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: spec.fill,
          border: spec.borderColor == null
              ? null
              : Border.all(color: spec.borderColor!),
        ),
      ),
    );
  }

  _DotSpec _spec(String s) {
    switch (s) {
      case 'running':
        return const _DotSpec(fill: SolvrColors.success);
      case 'stopped':
      case 'exited':
        return const _DotSpec(borderColor: SolvrColors.mutedForeground);
      case 'failed':
      case 'error':
        return const _DotSpec(fill: SolvrColors.destructive);
      default:
        return const _DotSpec(borderColor: SolvrColors.border);
    }
  }
}

class _DotSpec {
  const _DotSpec({this.fill = Colors.transparent, this.borderColor});
  final Color fill;
  final Color? borderColor;
}
