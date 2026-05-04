// Phase 25 Wave 1 D-49 + UI-SPEC §Component 8.
//
// Pinned-above-input banner when agent.status != 'running'. Default
// message "⚠ Agent stopped" + Restart text button. 1 px top border to
// separate from the chat scroll area; bg muted #EFEFEC. Banner clears
// only when status flips back to running (refetched after /start succeeds).
//
// Phase 25 Wave 5 follow-up (debug session 2026-05-04): inflight + elapsed
// surface a spinner + mm:ss counter in place of the Restart button while
// /v1/agents/:id/start is in flight. Without this the user thinks the
// click did nothing (a cold cache /start can take 30-90s) and rapid-fire
// clicks pile parallel /start requests behind the per-tag asyncio.Lock —
// debug session counted 12 click-spammed /start attempts in 3min, 11
// returned 409 Conflict.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class RestartBanner extends StatelessWidget {
  const RestartBanner({
    required this.onRestart,
    this.message = '\u26A0 Agent stopped',
    this.inflight = false,
    this.elapsed,
    super.key,
  });

  final VoidCallback onRestart;
  final String message;

  /// True while /v1/agents/:id/start is in flight. Disables the Restart
  /// button + swaps it for a spinner + mm:ss counter so the user has
  /// visible feedback during the multi-second await.
  final bool inflight;

  /// Stopwatch started when inflight flipped true. Read each frame so
  /// the counter advances; the chat screen ticks the parent setState
  /// every 1s.
  final Stopwatch? elapsed;

  String _formatElapsed(Stopwatch? s) {
    final secs = s?.elapsed.inSeconds ?? 0;
    final mm = (secs ~/ 60).toString().padLeft(2, '0');
    final ss = (secs % 60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  @override
  Widget build(BuildContext context) {
    final label = inflight
        ? 'Restarting agent. Please wait.'
        : '$message. Restart agent to resume sending.';
    return Semantics(
      label: label,
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
                inflight ? 'Restarting agent…' : message,
                style: const TextStyle(
                  fontSize: 12,
                  color: SolvrColors.mutedForeground,
                ),
              ),
            ),
            if (inflight) ...[
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: const AlwaysStoppedAnimation<Color>(
                    SolvrColors.foreground,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                _formatElapsed(elapsed),
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: SolvrColors.mutedForeground,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(width: 8),
            ] else
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
