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
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class UsageTickerWidget extends ConsumerWidget {
  const UsageTickerWidget({super.key});

  static const String _placeholder = r'$ —';

  /// Phase B Plan 12 (D-25) — tier-aware label projection. Free/Pro
  /// keep the existing Phase 27 USD ticker shape; Ultra renders
  /// `<displayBalanceCents> credits` (or `$0.00 ⚠` when the ledger
  /// row is negative — Pitfall 6).
  static String labelForSummary(UsageSummary s) {
    if (s.tier == 'ultra') {
      if (s.isNegative ?? false) {
        return r'$0.00 ⚠';
      }
      final display = s.displayBalanceCents ?? 0;
      return '$display credits';
    }
    return formatUsd(s.totalUsd);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(usageSummaryProvider);

    final label = summary.when(
      data: labelForSummary,
      loading: () => _placeholder,
      error: (_, _) => _placeholder,
    );

    final isLoaded = summary.hasValue;
    final s = summary.value;
    final isUltraNegative =
        s != null && s.tier == 'ultra' && (s.isNegative ?? false);

    return InkWell(
      onTap: () {
        if (s == null) return;
        if (isUltraNegative) {
          // Pitfall 6 / D-16 — surface the negative-balance explainer.
          unawaited(_showNegativeBalanceDialog(context));
          return;
        }
        if (s.byAgent.isEmpty) return;
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
            // Hide the chevron when rendering a credits/negative balance
            // surface — the tap target on `$0.00 ⚠` opens an explainer
            // dialog, not a drilldown screen, so the chevron would
            // mislead the user about destination.
            if (isLoaded && !isUltraNegative) ...[
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

/// Pitfall 6 / D-16 — explainer surfaced when the ultra balance is
/// negative. Top-level so the test harness can trigger the modal via
/// a plain `tester.tap(find.byType(UsageTickerWidget))` without
/// having to thread a custom callback through the widget API.
Future<void> _showNegativeBalanceDialog(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Negative balance'),
      content: const Text(
        'A refund was processed and your balance is currently negative. '
        'Top up to resume usage, or contact support for write-off review.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Close'),
        ),
      ],
    ),
  );
}
