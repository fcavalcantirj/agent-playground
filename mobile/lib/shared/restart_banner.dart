// Phase 25 Wave 1 D-49 + UI-SPEC §Component 8.
//
// Pinned-above-input banner when agent.status != 'running'. Default
// message "⚠ Agent stopped" + Restart text button. 1 px top border to
// separate from the chat scroll area; bg muted #EFEFEC. Banner clears
// only when status flips back to running (refetched after /start succeeds).

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class RestartBanner extends StatelessWidget {
  const RestartBanner({
    required this.onRestart,
    this.message = '\u26A0 Agent stopped',
    super.key,
  });

  final VoidCallback onRestart;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$message. Restart agent to resume sending.',
      child: Container(
        width: double.infinity,
        constraints: const BoxConstraints(minHeight: 48),
        decoration: const BoxDecoration(
          color: SolvrColors.muted,
          border: Border(
            top: BorderSide(color: SolvrColors.border),
          ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  fontSize: 12,
                  color: SolvrColors.mutedForeground,
                ),
              ),
            ),
            TextButton(
              onPressed: onRestart,
              style: TextButton.styleFrom(
                foregroundColor: SolvrColors.foreground,
                textStyle: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              child: const Text('Restart'),
            ),
          ],
        ),
      ),
    );
  }
}
