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

import 'package:agent_playground/core/agent_lifecycle.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/agent_row.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:agent_playground/features/usage/usage_ticker_widget.dart';
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
  // Per-row inflight sets. Mirrors the _restartInflight pattern in
  // chat_screen.dart (commit d3c8863) — single-screen ephemeral state,
  // no Riverpod StateNotifier needed. Two parallel sets (not one
  // unified _busyIds) so the AgentRow can render delete and restart
  // with different visuals — restart spinner without dimming, delete
  // spinner WITH dimming (Agent 4 nit: dimming reads as "going away"
  // which fits delete but not restart).
  final Set<String> _deletingIds = <String>{};
  final Set<String> _restartingIds = <String>{};
  final Set<String> _stoppingIds = <String>{};

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
          const UsageTickerWidget(),
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
    // Recipe-emoji lookup map. Built from `recipesProvider` (already
    // cached at dashboard mount). Null entries fall back to text-only
    // rendering on the row. Computed inline (no Riverpod codegen
    // dance) to keep this commit non-invasive.
    final recipesAsync = ref.watch(recipesProvider);
    final recipeList = recipesAsync.maybeWhen(
      data: (l) => l,
      orElse: () => const <Recipe>[],
    );
    final recipeEmojiByName = <String, String?>{
      for (final r in recipeList) r.name: r.emoji,
    };

    return _PopulatedState(
      agents: list,
      hasFreshError: isError,
      deletingIds: _deletingIds,
      restartingIds: _restartingIds,
      stoppingIds: _stoppingIds,
      recipeEmojiByName: recipeEmojiByName,
      onDelete: (a) => _confirmDelete(context, a),
      onRestart: (a) => _restartAgent(context, a),
      onStop: (a) => _stopAgent(context, a),
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

  /// Restart an agent from the dashboard. No ConfirmDialog — restart
  /// is non-destructive (idempotent on the backend; rapid double-taps
  /// would hit the per-tag asyncio.Lock). Adds the agent id to
  /// `_restartingIds` SYNCHRONOUSLY before any await — Agent 4 nit:
  /// the BYOK lookup itself is a network call (~200-800ms on
  /// recipeDetail miss), and a "menu closed but no spinner yet"
  /// window would let a fast second tap re-fire from the popup. Setting
  /// the busy flag first ensures the next render swaps the menu for
  /// the spinner before the user can tap again.
  ///
  /// Result mapping (4-agent design, edge-case agent):
  /// - RestartOk → 'Agent restarted' SnackBar (4s) + invalidate.
  /// - RestartNoBYOK → 'No BYOK key stored…' SnackBar (8s, parallels
  ///   chat-screen wording).
  /// - RestartFailed with code AGENT_ALREADY_RUNNING → soft 'Agent is
  ///   already running' SnackBar (4s) + invalidate (the local cache
  ///   was stale; the next fetch will resolve to status='running').
  /// - Any other RestartFailed → 'Restart failed: <message>' (8s).
  Future<void> _restartAgent(BuildContext ctx, AgentSummary a) async {
    if (_restartingIds.contains(a.id)) return; // re-entrancy guard
    setState(() => _restartingIds.add(a.id));
    try {
      final outcome = await restartAgent(
        agent: a,
        api: ref.read(apiClientProvider),
        storage: ref.read(secureStorageProvider),
      );
      if (!ctx.mounted) return;
      switch (outcome) {
        case RestartOk():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(
              content: Text('Agent restarted'),
            ),
          );
          ref.invalidate(agentsListProvider);
        case RestartNoBYOK():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(
              duration: Duration(seconds: 8),
              content: Text(
                'No BYOK key stored for this agent — re-deploy via the '
                'wizard to enter your API key.',
              ),
            ),
          );
        case RestartFailed(:final error):
          // 409 Conflict surfaces from a stale local cache (the agent
          // already came up between fetch and tap). Soft-message + let
          // the next agentsList fetch correct the status.
          if (error.code == ErrorCode.agentAlreadyRunning) {
            ScaffoldMessenger.of(ctx).showSnackBar(
              const SnackBar(
                content: Text('Agent is already running'),
              ),
            );
            ref.invalidate(agentsListProvider);
          } else {
            ScaffoldMessenger.of(ctx).showSnackBar(
              SnackBar(
                duration: const Duration(seconds: 8),
                content: Text('Restart failed: ${error.message}'),
              ),
            );
          }
      }
    } finally {
      if (mounted) setState(() => _restartingIds.remove(a.id));
    }
  }

  /// Gracefully stop a running agent. No ConfirmDialog — stop is
  /// non-destructive (the user can restart immediately) so the
  /// ceremony would be friction. Re-entrancy guard via _stoppingIds.
  ///
  /// Result mapping:
  /// - StopOk → 'Agent stopped' (4s) + invalidate provider (status →
  ///   'stopped' so the menu re-renders with Restart + Delete).
  /// - StopAlreadyStopped → soft 'Agent already stopped' (4s) +
  ///   invalidate (the local cache was stale).
  /// - StopFailed → 'Stop failed: <message>' (8s).
  Future<void> _stopAgent(BuildContext ctx, AgentSummary a) async {
    if (_stoppingIds.contains(a.id)) return; // re-entrancy guard
    setState(() => _stoppingIds.add(a.id));
    try {
      final outcome = await stopAgent(
        agent: a,
        api: ref.read(apiClientProvider),
        storage: ref.read(secureStorageProvider),
      );
      if (!ctx.mounted) return;
      switch (outcome) {
        case StopOk():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(
              content: Text('Agent stopped'),
            ),
          );
          ref.invalidate(agentsListProvider);
        case StopAlreadyStopped():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(
              content: Text('Agent already stopped'),
            ),
          );
          ref.invalidate(agentsListProvider);
        case StopFailed(:final error):
          ScaffoldMessenger.of(ctx).showSnackBar(
            SnackBar(
              duration: const Duration(seconds: 8),
              content: Text('Stop failed: ${error.message}'),
            ),
          );
      }
    } finally {
      if (mounted) setState(() => _stoppingIds.remove(a.id));
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
    required this.restartingIds,
    required this.stoppingIds,
    required this.recipeEmojiByName,
    required this.onDelete,
    required this.onRestart,
    required this.onStop,
    required this.onRefresh,
  });

  final List<AgentSummary> agents;
  final bool hasFreshError;
  final Set<String> deletingIds;
  final Set<String> restartingIds;
  final Set<String> stoppingIds;
  final Map<String, String?> recipeEmojiByName;
  final void Function(AgentSummary) onDelete;
  final void Function(AgentSummary) onRestart;
  final void Function(AgentSummary) onStop;
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
          // Restart is offered only when the server-derived status
          // permits it. running/starting/stopping would 409 against
          // the per-agent partial unique index OR overlap with an
          // existing in-flight start (Agent 2 verified). Empty/null
          // status defaults to 'stopped' per AgentSummary.fromJson.
          final canRestart = agent.status != 'running' &&
              agent.status != 'starting' &&
              agent.status != 'stopping';
          // Stop is offered only when the agent is currently running.
          // Any other status would 409 AGENT_NOT_RUNNING server-side
          // (no live container row for fetch_running_container_for_
          // agent to find). Mutually exclusive with canRestart.
          final canStop = agent.status == 'running';
          return AgentRow(
            agent: agent,
            recipeEmoji: recipeEmojiByName[agent.recipeName],
            isDeleting: deletingIds.contains(agent.id),
            isRestarting: restartingIds.contains(agent.id),
            isStopping: stoppingIds.contains(agent.id),
            onTap: () => GoRouter.of(ctx).push('/chat/${agent.id}'),
            onDelete: () => onDelete(agent),
            onRestart: canRestart ? () => onRestart(agent) : null,
            onStop: canStop ? () => onStop(agent) : null,
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
