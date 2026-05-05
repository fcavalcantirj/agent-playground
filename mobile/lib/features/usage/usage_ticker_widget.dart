// Phase 27 Change 3b Wave 3 — AppBar usage ticker.
//
// Always-visible USD running total in the AppBar's `actions:` array.
// Mounted on the Dashboard (lib/features/dashboard/dashboard_screen.dart)
// and the Chat screen (lib/features/chat/chat_screen.dart) per Wave 5.
//
// States:
//   loading → muted "$ —" (no spinner — too noisy in the AppBar)
//   loaded  → formatUsd(totalUsd) + chevron, JetBrainsMono w600 14sp
//   error   → muted "$ —" (still tappable; real error UX lives on the
//             per-agent breakdown screen via RetryBanner)
//
// Tap target (D-28-derived UX gap closure):
//   Dashboard / Chat ticker → push /agents/<byAgent.first.agentId>/usage
//   when by_agent has at least one entry. byAgent[0] is the most-recent
//   agent (server returns it ordered by last_activity DESC). Tap is a
//   no-op when by_agent is empty (no usage = nothing to drill into).
//
// Auto-refresh wiring lives in usage_providers.dart:
//   #1 mount via ref.watch
//   #2 lifecycle resumed via ref.listen(appLifecycleProvider)
//   #3 SSE inapp_outbound — wired in Wave 5 from chat_providers.dart.

import 'dart:async';

import 'package:agent_playground/core/format/usd_formatter.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class UsageTickerWidget extends ConsumerWidget {
  const UsageTickerWidget({super.key});

  static const String _placeholder = r'$ —';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(usageSummaryProvider);

    final label = summary.when(
      data: (s) => formatUsd(s.totalUsd),
      loading: () => _placeholder,
      error: (_, _) => _placeholder,
    );

    final isLoaded = summary.hasValue;

    return InkWell(
      onTap: () {
        final s = summary.value;
        if (s == null || s.byAgent.isEmpty) return;
        unawaited(context.push('/agents/${s.byAgent.first.agentId}/usage'));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: SolvrTextStyles.mono(
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ).copyWith(
                color: isLoaded
                    ? SolvrColors.foreground
                    : SolvrColors.mutedForeground,
              ),
            ),
            if (isLoaded) ...[
              const SizedBox(width: 4),
              const Icon(
                Icons.chevron_right,
                size: 16,
                color: SolvrColors.mutedForeground,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
