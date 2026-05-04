// Phase 25 Wave 2 — Dashboard screen (D-07..D-20 + UI-01).
//
// Replaces the Wave 1 stub. Composes the four states from UI-SPEC §Screen
// Layouts ### Dashboard:
//
//   - LOADING (D-18): 3 SkeletonRow placeholders.
//   - EMPTY  (D-17): EmptyStateScaffold + AsciiAgentBanner cycling recipe
//                    names from GET /v1/recipes + black "Deploy your first
//                    agent" button → /new-agent/clone.
//   - POPULATED (D-08): RefreshIndicator-wrapped ListView.separated of
//                       AgentRow widgets (status dot + name + model id +
//                       relative time). Tap row → /chat/<id>.
//   - ERROR (D-19): cold-load failure → centered RetryBanner; post-load
//                   refresh failure → RetryBanner pinned above the
//                   last-known list (preserved per D-19).
//
// AppBar (D-09): >_ SOLVR_LABS wordmark + 3-dot overflow whose ONLY entry
// is "Sign out" (D-07) → ConfirmDialog → AuthService.signOut + go('/login').
//
// Bottom nav (D-10): Home / Browse / Profile — Browse + Profile are
// no-ops in MVP; visually greyed via ColoredIconTheme. NavigationBar's
// onDestinationSelected ignores indices != 0.
//
// FAB (D-11): square-cornered (radius 0 per Solvr theme) "+" button → push
// /new-agent/clone.
//
// Pull-to-refresh + AppLifecycleState.resumed share a single re-fetch
// path: ref.invalidate(agentsListProvider) → AgentsList.build re-runs with
// a fresh CancelToken (Pitfall #8 concurrency guard).

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/agent_row.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:agent_playground/shared/ascii_agent_banner.dart';
import 'package:agent_playground/shared/confirm_dialog.dart';
import 'package:agent_playground/shared/empty_state_scaffold.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:agent_playground/shared/skeleton_row.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  // Per-row inflight set for DELETE /v1/agents/:id. Mirrors the
  // _restartInflight pattern in chat_screen.dart (commit d3c8863) —
  // single-screen ephemeral state, no Riverpod StateNotifier needed.
  final Set<String> _deletingIds = <String>{};

  @override
  Widget build(BuildContext context) {
    final agents = ref.watch(agentsListProvider);
    final namesAsync = ref.watch(recipeNamesStreamProvider);
    // Bridge AsyncValue<List<String>> → Stream<List<String>> so the dumb
    // AsciiAgentBanner widget stays a pure stream consumer (UI-SPEC line
    // 314). Empty/error/loading states emit nothing — banner falls back to
    // its built-in static label.
    final namesStream = Stream<List<String>>.fromIterable(
      namesAsync.maybeWhen(
        data: (names) => [names],
        orElse: () => const <List<String>>[],
      ),
    );

    final body = _buildBody(context, agents, namesStream);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          '>_ SOLVR_LABS',
          style: SolvrTextStyles.mono(
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            tooltip: 'More',
            onSelected: (value) async {
              if (value == 'signout') {
                await _confirmSignOut(context);
              }
            },
            itemBuilder: (_) => const <PopupMenuEntry<String>>[
              PopupMenuItem<String>(
                value: 'signout',
                child: Text('Sign out'),
              ),
            ],
          ),
        ],
      ),
      body: body,
      floatingActionButton: FloatingActionButton(
        key: const Key('dashboard-fab'),
        onPressed: () => context.push('/new-agent/clone'),
        backgroundColor: SolvrColors.foreground,
        foregroundColor: SolvrColors.background,
        shape: const RoundedRectangleBorder(),
        child: const Icon(Icons.add),
      ),
      bottomNavigationBar: NavigationBar(
        // D-10 — Browse + Profile no-op in MVP.
        onDestinationSelected: (i) {
          if (i != 0) return;
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined, color: SolvrColors.foreground),
            selectedIcon: Icon(Icons.home, color: SolvrColors.foreground),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.search, color: SolvrColors.mutedForeground),
            label: 'Browse',
          ),
          NavigationDestination(
            icon: Icon(
              Icons.person_outline,
              color: SolvrColors.mutedForeground,
            ),
            label: 'Profile',
          ),
        ],
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    AsyncValue<List<AgentSummary>> agents,
    Stream<List<String>> namesStream,
  ) {
    final cached = agents.value;
    final isError = agents.hasError;
    final isLoading = agents.isLoading;

    // Riverpod 3 quirk: after a failing build, the state is
    // `AsyncLoading.copyWithPrevious(error)` until the next refetch — so
    // `hasError` AND `isLoading` are both true. Check the error path first
    // so a cold-load failure surfaces the retry banner instead of an
    // infinite skeleton.
    if (isError && cached == null) {
      return _ErrorState(
        onRetry: () => ref.invalidate(agentsListProvider),
      );
    }
    // Cold first load — no data available yet.
    if (isLoading && cached == null) {
      return const _LoadingState();
    }

    final list = cached ?? const <AgentSummary>[];
    if (list.isEmpty) {
      return _EmptyState(namesStream: namesStream);
    }
    return _PopulatedState(
      agents: list,
      hasFreshError: isError,
      deletingIds: _deletingIds,
      onDelete: (a) => _confirmDelete(context, a),
      onRefresh: () async {
        ref.invalidate(agentsListProvider);
        // Wait for the new fetch to settle so RefreshIndicator dismisses
        // its spinner only after the data lands.
        try {
          await ref.read(agentsListProvider.future);
        // RetryBanner above the list surfaces the error; no rethrow needed.
        // ignore: avoid_catches_without_on_clauses
        } catch (_) {
          // intentionally empty — error visible via RetryBanner above list.
        }
      },
    );
  }

  /// Confirm + execute DELETE /v1/agents/:id. Adds the agent id to
  /// `_deletingIds` while in flight so the row shows a spinner and is
  /// non-tappable. Always clears the inflight state in `finally`.
  /// SnackBar on success (4s) and on failure (8s, longer so the user can
  /// read the error). On success, invalidate `agentsListProvider` so the
  /// row disappears once the next fetch lands.
  Future<void> _confirmDelete(BuildContext ctx, AgentSummary a) async {
    final result = await ConfirmDialog.show(
      ctx,
      title: 'Delete ${a.name}?',
      body:
          'This will stop and remove the agent. This cannot be undone.',
      confirmLabel: 'Delete',
    );
    if (result != ConfirmDialogResult.confirm) return;
    if (!ctx.mounted) return;
    setState(() => _deletingIds.add(a.id));
    try {
      final res = await ref
          .read(apiClientProvider)
          .deleteAgent(agentId: a.id);
      if (!ctx.mounted) return;
      if (res case Err(:final error)) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          SnackBar(
            duration: const Duration(seconds: 8),
            content: Text('Delete failed: ${error.message}'),
          ),
        );
        return;
      }
      ScaffoldMessenger.of(ctx).showSnackBar(
        const SnackBar(
          content: Text('Agent deleted'),
        ),
      );
      ref.invalidate(agentsListProvider);
    } finally {
      if (mounted) setState(() => _deletingIds.remove(a.id));
    }
  }

  Future<void> _confirmSignOut(BuildContext context) async {
    final result = await ConfirmDialog.show(
      context,
      title: 'Sign out of Solvr Labs?',
      confirmLabel: 'Sign out',
    );
    if (result != ConfirmDialogResult.confirm) return;
    await ref.read(authServiceProvider).signOut();
    // Login screen banner is reset on every sign-out — clean slate.
    ref.read(showSignedOutBannerProvider.notifier).state = false;
    if (context.mounted) {
      context.go('/login');
    }
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) => const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SkeletonRow(),
          Divider(height: 1),
          SkeletonRow(),
          Divider(height: 1),
          SkeletonRow(),
        ],
      );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.namesStream});

  final Stream<List<String>> namesStream;

  @override
  Widget build(BuildContext context) => EmptyStateScaffold(
        banner: AsciiAgentBanner(namesStream: namesStream),
        heading: 'No agents yet',
        primaryAction: EmptyStatePrimaryAction(
          label: 'Deploy your first agent',
          onTap: () => GoRouter.of(context).push('/new-agent/clone'),
        ),
      );
}

class _PopulatedState extends StatelessWidget {
  const _PopulatedState({
    required this.agents,
    required this.hasFreshError,
    required this.deletingIds,
    required this.onDelete,
    required this.onRefresh,
  });

  final List<AgentSummary> agents;
  final bool hasFreshError;
  final Set<String> deletingIds;
  final void Function(AgentSummary) onDelete;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView.separated(
        key: const Key('dashboard-list'),
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: agents.length + (hasFreshError ? 1 : 0),
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (ctx, i) {
          if (hasFreshError && i == 0) {
            return RetryBanner(
              message: "Couldn't refresh",
              actionLabel: 'Tap to retry',
              onTap: onRefresh,
            );
          }
          final idx = hasFreshError ? i - 1 : i;
          final agent = agents[idx];
          return AgentRow(
            agent: agent,
            isDeleting: deletingIds.contains(agent.id),
            onTap: () => GoRouter.of(ctx).push('/chat/${agent.id}'),
            onDelete: () => onDelete(agent),
          );
        },
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: RetryBanner(
            message: "Couldn't load agents",
            actionLabel: 'Tap to retry',
            onTap: onRetry,
          ),
        ),
      );
}
