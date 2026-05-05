// Phase 27 Change 3b Wave 4 — per-agent BYOK usage breakdown screen.
//
// Pushed from UsageTickerWidget (and from the future direct agent-row
// affordance). Watches agentUsageProvider(id) — Riverpod auto-cancels
// the request on screen pop via CancelToken in usage_providers.dart.
//
// Layout (per UI plan §Wave 4):
//   AppBar — back button + screen title
//   Body:
//     loading → centered CircularProgressIndicator (small)
//     error   → RetryBanner (tap → ref.invalidate(agentUsageProvider(id)))
//     empty   → AsciiAgentBanner + "No usage yet" (REUSE EmptyStateScaffold)
//     loaded  → cumulative headline + "Last 7 days" chart + "Last 30 days"
//
// Pull-to-refresh wraps the loaded body — RefreshIndicator's onRefresh
// calls ref.invalidate(agentUsageProvider(id)) and awaits the new
// .future so the indicator dismisses on completion.

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/format/usd_formatter.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/usage/usage_chart.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:agent_playground/features/usage/usage_providers.dart';
import 'package:agent_playground/shared/ascii_agent_banner.dart';
import 'package:agent_playground/shared/empty_state_scaffold.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AgentUsageScreen extends ConsumerWidget {
  const AgentUsageScreen({required this.agentId, super.key});

  final String agentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(agentUsageProvider(agentId));

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Usage',
          style: SolvrTextStyles.mono(
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: async.when(
        data: (data) => _Body(agentId: agentId, data: data),
        loading: () => const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
        error: (err, _) => _ErrorView(agentId: agentId, error: err),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.agentId, required this.data});

  final String agentId;
  final AgentUsageData data;

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(agentUsageProvider(agentId));
    await ref.read(agentUsageProvider(agentId).future);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (data.cumulative.messageCount == 0) {
      return RefreshIndicator(
        onRefresh: () => _refresh(ref),
        child: ListView(
          // Tall enough so the indicator can be triggered on an
          // otherwise-empty screen.
          children: [
            SizedBox(
              height: MediaQuery.of(context).size.height * 0.7,
              child: EmptyStateScaffold(
                heading: 'No usage yet',
                body:
                    'Send a message to your agent to see costs here.',
                banner: AsciiAgentBanner(
                  namesStream: Stream<List<String>>.value(const [
                    'openclaw',
                    'hermes',
                    'nullclaw',
                    'picoclaw',
                    'nanobot',
                  ]),
                ),
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _refresh(ref),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Headline(cumulative: data.cumulative),
          const SizedBox(height: 24),
          _SeriesBlock(
            title: 'Last 7 days',
            entries: data.series7d,
          ),
          const SizedBox(height: 24),
          _SeriesBlock(
            title: 'Last 30 days',
            entries: data.series30d,
          ),
        ],
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({required this.cumulative});

  final AgentCumulative cumulative;

  @override
  Widget build(BuildContext context) {
    final usd = formatUsd(cumulative.costUsd);
    final tokens = cumulative.inputTokens + cumulative.outputTokens;
    final lastActivity = cumulative.lastActivity;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          usd,
          style: SolvrTextStyles.mono(
            fontSize: 28,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '$tokens tokens · ${cumulative.messageCount} messages'
          '${lastActivity != null ? ' · last $lastActivity' : ''}',
          style: const TextStyle(
            fontSize: 12,
            color: SolvrColors.mutedForeground,
          ),
        ),
      ],
    );
  }
}

class _SeriesBlock extends StatelessWidget {
  const _SeriesBlock({required this.title, required this.entries});

  final String title;
  final List<AgentSeriesEntry> entries;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: SolvrTextStyles.mono(
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: 80,
          child: UsageChart(entries: entries),
        ),
      ],
    );
  }
}

class _ErrorView extends ConsumerWidget {
  const _ErrorView({required this.agentId, required this.error});

  final String agentId;
  final Object error;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final message = error is ApiError
        ? (error as ApiError).message
        : 'Something went wrong';
    return Padding(
      padding: const EdgeInsets.all(16),
      child: RetryBanner(
        message: message,
        actionLabel: 'Retry',
        onTap: () => ref.invalidate(agentUsageProvider(agentId)),
      ),
    );
  }
}
