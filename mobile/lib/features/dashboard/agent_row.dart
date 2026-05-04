// Phase 25 Wave 2 — single Dashboard row (D-08, D-14, D-15, D-16, D-20).
//
// Layout per UI-SPEC §Screen Layouts ### Dashboard (lines 510-534):
//   16 px horizontal pad → StatusDot 8 → 12 px gap → name body 16 w600
//   over model-id JetBrains Mono caption 12 muted (each ellipsized to a
//   single line per D-20) → flex spacer → 8 px → relative-time caption 12
//   muted right-aligned.
//
// Tap handler is wired from the parent (DashboardScreen) so the row stays
// agnostic of GoRouter — easier widget-testing without a router harness.
//
// Bug 2 follow-up: trailing PopupMenuButton with a single 'Delete' entry
// next to the relative-time label. While `isDeleting` is true, the menu
// is replaced with a small spinner and the row's onTap is disabled —
// mirrors the inflight pattern from RestartBanner (commit d3c8863).

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:flutter/material.dart';

class AgentRow extends StatelessWidget {
  const AgentRow({
    required this.agent,
    required this.onTap,
    this.onDelete,
    this.onRestart,
    this.onStop,
    this.isDeleting = false,
    this.isRestarting = false,
    this.isStopping = false,
    @visibleForTesting this.now,
    super.key,
  });

  final AgentSummary agent;
  final VoidCallback onTap;

  /// Optional delete trigger. When null, the 'Delete' menu entry is
  /// suppressed (test fixtures + future read-only contexts).
  final VoidCallback? onDelete;

  /// Optional restart trigger. When null, the 'Restart' menu entry is
  /// suppressed — the dashboard passes null when `agent.status` is
  /// `running` / `starting` / `stopping` (would 409 server-side
  /// against the partial-unique index `ix_agent_containers_agent_in
  /// stance_running` per migration 003:88). For any other status
  /// (`stopped`, `start_failed`, `crashed`, empty/null-coerced-to-
  /// `'stopped'`), pass the callback so the user can recover.
  final VoidCallback? onRestart;

  /// Optional stop trigger. When null, the 'Stop' menu entry is
  /// suppressed — the dashboard passes null UNLESS `agent.status ==
  /// 'running'` (the only state where the server has a live container
  /// to SIGTERM; any other status would 409 AGENT_NOT_RUNNING).
  final VoidCallback? onStop;

  /// True while a DELETE /v1/agents/:id is in flight for this row.
  /// Disables onTap, replaces the trailing menu with a small spinner,
  /// AND dims the whole row to 50% opacity (delete = "going away").
  final bool isDeleting;

  /// True while a POST /v1/agents/:id/start is in flight for this
  /// row. Disables onTap + replaces the menu with a spinner, but does
  /// NOT dim the row — restart isn't destructive, so the visual
  /// shouldn't read as "vanishing". 4-agent design 2026-05-04 nit.
  final bool isRestarting;

  /// True while a POST /v1/agents/:id/stop is in flight for this row.
  /// Same visual treatment as [isRestarting] — spinner, no dimming
  /// (stop is "transitioning" not "going away"; the agent comes back
  /// with status='stopped' and the user can restart it).
  final bool isStopping;

  /// Test seam — defaults to DateTime.now() at render time. Allows the unit
  /// tests for `_relativeTime` to assert deterministic output without
  /// freezing the wall clock.
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final body = Theme.of(context).textTheme.bodyLarge;
    final caption = Theme.of(context).textTheme.bodySmall;
    final isBusy = isDeleting || isRestarting || isStopping;
    final core = InkWell(
      onTap: isBusy ? null : onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: SizedBox(
          height: 56,
          child: Row(
            children: [
              StatusDot(status: agent.status),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      agent.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: body?.copyWith(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: SolvrColors.foreground,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      agent.model,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: SolvrTextStyles.mono(
                        fontSize: 12,
                      ).copyWith(color: SolvrColors.mutedForeground),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                relativeTime(agent.lastActivity, now: now),
                style: caption?.copyWith(
                  fontSize: 12,
                  color: SolvrColors.mutedForeground,
                ),
              ),
              if (isBusy)
                const Padding(
                  padding: EdgeInsets.only(left: 8, right: 4),
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else if (onDelete != null || onRestart != null || onStop != null)
                PopupMenuButton<String>(
                  key: ValueKey('agent-row-menu-${agent.id}'),
                  icon: const Icon(Icons.more_vert, size: 20),
                  tooltip: 'Agent actions',
                  onSelected: (v) {
                    if (v == 'stop' && onStop != null) onStop!();
                    if (v == 'restart' && onRestart != null) onRestart!();
                    if (v == 'delete' && onDelete != null) onDelete!();
                  },
                  itemBuilder: (_) => <PopupMenuEntry<String>>[
                    if (onStop != null)
                      const PopupMenuItem<String>(
                        value: 'stop',
                        child: Text('Stop'),
                      ),
                    if (onRestart != null)
                      const PopupMenuItem<String>(
                        value: 'restart',
                        child: Text('Restart'),
                      ),
                    if (onDelete != null)
                      const PopupMenuItem<String>(
                        value: 'delete',
                        child: Text(
                          'Delete',
                          style: TextStyle(color: SolvrColors.destructive),
                        ),
                      ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
    // Dim only on delete — restart isn't "going away" (Agent 4 nit).
    return Opacity(opacity: isDeleting ? 0.5 : 1.0, child: core);
  }

  /// D-15 — relative time renderer.
  ///
  /// Returns: `''` if iso null/unparseable; `'now'` (<1m); `'<N>m'` (<60m);
  /// `'<N>h'` (<24h); `'yesterday'` (<48h); `'<N>d'` (<7d); ISO date prefix
  /// `YYYY-MM-DD` for older.
  @visibleForTesting
  static String relativeTime(String? iso, {DateTime? now}) {
    if (iso == null || iso.isEmpty) return '';
    final ts = DateTime.tryParse(iso);
    if (ts == null) return '';
    final base = now ?? DateTime.now();
    final delta = base.difference(ts);
    if (delta.isNegative) return 'now';
    if (delta.inMinutes < 1) return 'now';
    if (delta.inMinutes < 60) return '${delta.inMinutes}m';
    if (delta.inHours < 24) return '${delta.inHours}h';
    if (delta.inDays < 2) return 'yesterday';
    if (delta.inDays < 7) return '${delta.inDays}d';
    // Older — short ISO date keeps the slot deterministic and locale-free.
    return ts.toIso8601String().substring(0, 10);
  }
}
