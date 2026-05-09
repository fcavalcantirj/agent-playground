// Track 2 (#18) — AppBar tier badge.
//
// Tiny mono-font chip rendered IMMEDIATELY LEFT of the
// UsageTickerWidget on Dashboard + Chat AppBars. Tap → push /billing
// (the new hub) so the user can read what their tier means and
// upgrade / top up.
//
// Tiers are rendered in plain English, all caps, mono — Solvr matrix
// aesthetic. Free is muted; Pro and Ultra are foreground-colored so
// paying users feel acknowledged. Loading + error → muted dash so
// the AppBar doesn't reflow when usageSummaryProvider transitions.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class TierBadgeWidget extends ConsumerWidget {
  const TierBadgeWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(usageSummaryProvider);
    final label = summary.when(
      data: (s) => s.tier.toUpperCase(),
      loading: () => '—',
      error: (_, _) => '—',
    );
    final isPaid = summary.value?.tier == 'pro' || summary.value?.tier == 'ultra';

    return InkWell(
      onTap: () => context.push('/billing'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            border: Border.all(
              color: isPaid
                  ? SolvrColors.foreground
                  : SolvrColors.mutedForeground,
            ),
            borderRadius: BorderRadius.circular(2),
          ),
          child: Text(
            label,
            style: SolvrTextStyles.mono(
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ).copyWith(
              color: isPaid
                  ? SolvrColors.foreground
                  : SolvrColors.mutedForeground,
              letterSpacing: 0.8,
            ),
          ),
        ),
      ),
    );
  }
}
