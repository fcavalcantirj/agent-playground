// Track 2 (#18) — Billing hub.
//
// Replaces /billing/topup as the entry point from the AppBar tier
// chip and the dashboard / chat overflow menu. Surfaces:
//
//   1. Current tier badge + plain-English subtitle ("BYOK • for tinkerers"
//      vs "BYOK • for hobbyists" vs "Pay-as-you-go • for serious users").
//   2. Current balance — only meaningful for Ultra; Free/Pro see a one-line
//      explanation that LLM cost lives on their own provider key.
//   3. Top up tile — pushes /billing/topup (existing screen).
//   4. Transactions tile — pushes /billing/transactions.
//   5. Tier comparison panel — what each tier gets you, in plain English.
//      The user-visible names are still Free / Pro / Ultra; the row
//      subtitles carry the BYOK/PAYG framing.
//
// No tap to the current `/billing/topup` route from the chat 402 modal
// changes — the modal still pushes /topup directly so the friction is
// minimal in the "out of balance" recovery flow.
//
// Per-decision-doc D-25, the AppBar usage ticker stays — it lives on
// every screen and was not reorganized into the hub.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class BillingHubScreen extends ConsumerWidget {
  const BillingHubScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(usageSummaryProvider);
    final tier = summary.value?.tier ?? 'free';
    final balanceCents = summary.value?.displayBalanceCents ?? 0;
    final isNegative = summary.value?.isNegative ?? false;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Billing',
          style: SolvrTextStyles.mono(fontSize: 18, fontWeight: FontWeight.w600),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _CurrentPlanCard(
            tier: tier,
            balanceCents: balanceCents,
            isNegative: isNegative,
          ),
          const SizedBox(height: 16),
          _ActionTile(
            title: 'Top up',
            subtitle: tier == 'ultra'
                ? 'Add to your balance'
                : 'Switch to Ultra and prepay LLM cost',
            onTap: () => context.push('/billing/topup'),
          ),
          _ActionTile(
            title: 'Transactions',
            subtitle: 'Top-ups, debits, refunds',
            onTap: () => context.push('/billing/transactions'),
          ),
          const SizedBox(height: 24),
          Text(
            'Plans',
            style: SolvrTextStyles.mono(
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ).copyWith(letterSpacing: 0.6),
          ),
          const SizedBox(height: 8),
          _PlanRow(
            name: 'FREE',
            subtitle: 'BYOK • for tinkerers',
            entitlements: '1 active agent · 7-day chat history',
            current: tier == 'free',
          ),
          _PlanRow(
            name: 'PRO',
            subtitle: 'BYOK • for hobbyists',
            entitlements:
                r'5 active agents · 30-day history · fixed $/mo',
            current: tier == 'pro',
          ),
          _PlanRow(
            name: 'ULTRA',
            subtitle: 'Pay-as-you-go • for serious users',
            entitlements:
                'Unlimited agents · unlimited history · we pay LLM, you reload',
            current: tier == 'ultra',
          ),
        ],
      ),
    );
  }
}

class _CurrentPlanCard extends StatelessWidget {
  const _CurrentPlanCard({
    required this.tier,
    required this.balanceCents,
    required this.isNegative,
  });

  final String tier;
  final int balanceCents;
  final bool isNegative;

  @override
  Widget build(BuildContext context) {
    final isUltra = tier == 'ultra';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: SolvrColors.foreground),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Current plan',
            style: SolvrTextStyles.mono(fontSize: 11).copyWith(
              color: SolvrColors.mutedForeground,
              letterSpacing: 0.6,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            tier.toUpperCase(),
            style: SolvrTextStyles.mono(
              fontSize: 24,
              fontWeight: FontWeight.w700,
            ).copyWith(letterSpacing: 1.2),
          ),
          const SizedBox(height: 4),
          Text(
            switch (tier) {
              'pro' => 'BYOK • for hobbyists',
              'ultra' => 'Pay-as-you-go • for serious users',
              _ => 'BYOK • for tinkerers',
            },
            style: SolvrTextStyles.mono(fontSize: 12).copyWith(
              color: SolvrColors.mutedForeground,
            ),
          ),
          if (isUltra) ...[
            const SizedBox(height: 16),
            Text(
              'Balance',
              style: SolvrTextStyles.mono(fontSize: 11).copyWith(
                color: SolvrColors.mutedForeground,
                letterSpacing: 0.6,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              isNegative
                  ? r'$0.00 ⚠'
                  : '\$${(balanceCents / 100).toStringAsFixed(2)}',
              style: SolvrTextStyles.mono(
                fontSize: 28,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (isNegative) ...[
              const SizedBox(height: 4),
              Text(
                'Refund processed; balance is below zero. Top up to resume.',
                style: SolvrTextStyles.mono(fontSize: 11).copyWith(
                  color: SolvrColors.mutedForeground,
                ),
              ),
            ],
          ] else ...[
            const SizedBox(height: 8),
            Text(
              'You pay your LLM provider directly with your own key.',
              style: SolvrTextStyles.mono(fontSize: 12).copyWith(
                color: SolvrColors.mutedForeground,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.only(top: 8),
        decoration: BoxDecoration(
          border: Border.all(color: SolvrColors.border),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: SolvrTextStyles.mono(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: SolvrTextStyles.mono(fontSize: 11).copyWith(
                      color: SolvrColors.mutedForeground,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right,
              color: SolvrColors.mutedForeground,
            ),
          ],
        ),
      ),
    );
  }
}

class _PlanRow extends StatelessWidget {
  const _PlanRow({
    required this.name,
    required this.subtitle,
    required this.entitlements,
    required this.current,
  });

  final String name;
  final String subtitle;
  final String entitlements;
  final bool current;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(
          color: current ? SolvrColors.foreground : SolvrColors.border,
          width: current ? 2 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                name,
                style: SolvrTextStyles.mono(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ).copyWith(letterSpacing: 0.8),
              ),
              if (current) ...[
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: SolvrColors.foreground,
                  ),
                  child: Text(
                    'CURRENT',
                    style: SolvrTextStyles.mono(
                      fontSize: 9,
                      fontWeight: FontWeight.w700,
                    ).copyWith(
                      color: SolvrColors.background,
                      letterSpacing: 0.8,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: SolvrTextStyles.mono(fontSize: 11).copyWith(
              color: SolvrColors.mutedForeground,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            entitlements,
            style: SolvrTextStyles.mono(fontSize: 11),
          ),
        ],
      ),
    );
  }
}
