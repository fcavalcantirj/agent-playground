// Phase 25 Wave 4 plan 25-07 task 3 — Chat screen (UI-03).
//
// Replaces the Wave 1 stub. Composes:
//
//   * AppBar (D-37) — back arrow + agent name + status subtitle row
//     (model-id mono caption + StatusDot).
//   * Telegram-failed banner (D-50) — RetryBanner pinned below AppBar
//     when telegramFailedBannerProvider is set; Retry re-fires
//     POST /v1/agents/<id>/start with channel='telegram' + cached inputs.
//   * Older-messages banner (D-39) — when initial history returned >=200
//     rows, pinned above the list; tap loads up to 1000 more.
//   * Message list — ListView of bubbles with auto-scroll suppression
//     chip (D-42) — "New message ↓" appears when user scrolled up >50px.
//   * Empty state (D-38) — "Say hi to <agent_name>" when zero rows.
//   * Restart banner (D-49) — pinned above ChatInputBar when agent.status
//     != 'running'.
//   * ChatInputBar — multiline expanding input + Send button (D-40 / D-51).
//
// Back nav goes to /dashboard always per UI-SPEC §Routing — no overflow
// menu (D-37 says agent lifecycle is reachable only via D-49 banner).

import 'package:agent_playground/core/agent_lifecycle.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/bubble_widget.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:agent_playground/features/chat/input_bar.dart';
import 'package:agent_playground/features/chat/telegram_failed_banner_provider.dart';
import 'package:agent_playground/features/chat/timestamp_divider.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/usage/usage_ticker_widget.dart';
import 'package:agent_playground/shared/failed_bubble.dart';
import 'package:agent_playground/shared/restart_banner.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:agent_playground/shared/typing_dots.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({required this.agentInstanceId, super.key});

  final String agentInstanceId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final ScrollController _scrollCtl = ScrollController();
  bool _userScrolledUp = false;

  // Restart inflight state — shows spinner + elapsed timer in the
  // RestartBanner instead of the click-spammable "Restart" button.
  // /v1/agents/:id/start can take 30-90s on a cold cache; without this
  // feedback the user thinks nothing happened and rapidly fires more
  // /start calls that all queue behind the tag_lock and 409 (debug
  // session 2026-05-04 found 12 click-spammed /start attempts in 3min,
  // 11 returned 409 Conflict).
  bool _restartInflight = false;
  Stopwatch? _restartElapsed;
  Timer? _restartTick;

  // Stop inflight guard. AppBar overflow menu replaces 'Stop' with
  // 'Stopping…' + spinner while in flight. Stop is fast (5-15s docker
  // SIGTERM + rm), so no Stopwatch/Timer needed — the post-success
  // status flip + RestartBanner reveal is its own visual confirmation.
  bool _stopInflight = false;

  @override
  void initState() {
    super.initState();
    _scrollCtl.addListener(_onScroll);
    // Bug fix 2026-05-04: invalidate agentsListProvider on chat mount
    // so we always render against the freshest agent.status, not whatever
    // the dashboard cached before /v1/agents/:id/start completed. After
    // a successful deploy the wizard navigates to /chat/<id> while
    // /v1/agents may still report status='starting' from a fetch
    // captured during the wizard. Without this invalidate the chat
    // shows the RestartBanner ("Agent stopped") for the running agent
    // until the user pulls-to-refresh — confusing UX. The dispose-side
    // invalidate (added Phase 25 Wave 5) handles the dashboard direction
    // but mounted-chat-with-stale-data needed its own refresh.
    // ignore: discarded_futures
    Future<void>.microtask(() {
      if (mounted) ref.invalidate(agentsListProvider);
    });
  }

  @override
  void dispose() {
    _scrollCtl.removeListener(_onScroll);
    _scrollCtl.dispose();
    _restartTick?.cancel();
    // Phase 25 Wave 5: when the user pops back from chat to dashboard,
    // refresh the agents list so newly-deployed agents and updated
    // last_activity timestamps land without requiring a pull-to-refresh.
    // (D-12 lifecycle resume fires only on cold-start; route-pop is
    // a different signal.)
    ref.invalidate(agentsListProvider);
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollCtl.hasClients) return;
    final pos = _scrollCtl.position;
    // D-42 — "scrolled up" = > 50px from bottom edge.
    final fromBottom = pos.maxScrollExtent - pos.pixels;
    final scrolledUp = fromBottom > 50;
    if (scrolledUp != _userScrolledUp) {
      setState(() => _userScrolledUp = scrolledUp);
    }
  }

  AgentSummary? _currentAgent(AsyncValue<List<AgentSummary>> agentsAsync) {
    final list = agentsAsync.value ?? const <AgentSummary>[];
    for (final a in list) {
      if (a.id == widget.agentInstanceId) return a;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final scope = ref.watch(chatScopeProvider(widget.agentInstanceId));
    final scopeNotifier =
        ref.read(chatScopeProvider(widget.agentInstanceId).notifier);
    final agentsAsync = ref.watch(agentsListProvider);
    final agent = _currentAgent(agentsAsync);
    final tgBanner = ref.watch(telegramFailedBannerProvider);
    final isStopped =
        agent != null && agent.status != 'running' && agent.status.isNotEmpty;

    // The AppBar overflow menu only renders when there's at least one
    // valid action — currently only 'Stop' when the agent is running.
    // (Restart already has its own RestartBanner pinned above the
    // input when stopped, and Delete intentionally requires the
    // dashboard friction so the user can't nuke a chat mid-conversation
    // by accident.)
    final showStopMenu = agent != null && agent.status == 'running';

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () => context.go('/dashboard'),
        ),
        title: _ChatAppBarTitle(
          agent: agent,
          fallbackId: widget.agentInstanceId,
        ),
        actions: [
          const UsageTickerWidget(),
          if (showStopMenu)
            PopupMenuButton<String>(
              key: const Key('chat-overflow-menu'),
              icon: const Icon(Icons.more_vert),
              tooltip: 'Agent actions',
              enabled: !_stopInflight,
              onSelected: (v) {
                if (v == 'stop') _stopAgent(context, agent);
              },
              itemBuilder: (_) => [
                PopupMenuItem<String>(
                  value: 'stop',
                  enabled: !_stopInflight,
                  child: _stopInflight
                      ? const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            SizedBox(width: 8),
                            Text('Stopping…'),
                          ],
                        )
                      : const Text('Stop'),
                ),
              ],
            ),
        ],
      ),
      body: Column(
        children: [
          if (tgBanner != null)
            RetryBanner(
              key: const Key('telegram-failed-banner'),
              message: 'Telegram setup failed: ${tgBanner.reason}',
              actionLabel: 'Retry',
              tone: RetryBannerTone.warning,
              dismissible: true,
              onDismiss: () => ref
                  .read(telegramFailedBannerProvider.notifier)
                  .state = null,
              onTap: () => _retryTelegram(context, tgBanner),
            ),
          if (scope.hasOlderMessages)
            _OlderMessagesBanner(onTap: scopeNotifier.loadOlder),
          Expanded(
            child: scope.orderedIds.isEmpty
                ? _EmptyChatState(agentName: agent?.name)
                : _MessageList(
                    state: scope,
                    scrollCtl: _scrollCtl,
                    agentInstanceId: widget.agentInstanceId,
                    notifier: scopeNotifier,
                    showJumpChip: _userScrolledUp,
                  ),
          ),
          if (isStopped)
            RestartBanner(
              onRestart: () => _restartAgent(context),
              inflight: _restartInflight,
              elapsed: _restartElapsed,
            ),
          ChatInputBar(
            enabled: !isStopped,
            inflight: scope.inflight,
            onSend: scopeNotifier.sendMessage,
            onCancel: scopeNotifier.cancelInflight,
          ),
        ],
      ),
    );
  }

  Future<void> _retryTelegram(
    BuildContext context,
    TelegramFailedBannerState s,
  ) async {
    final api = ref.read(apiClientProvider);
    final r = await api.start(
      agentId: s.agentInstanceId,
      body: StartRequest(
        channel: 'telegram',
        channelInputs: s.telegramInputs,
      ),
    );
    if (r is Ok<StartResponse>) {
      ref.read(telegramFailedBannerProvider.notifier).state = null;
    }
  }

  Future<void> _restartAgent(BuildContext context) async {
    // Re-entrancy guard — `/v1/agents/:id/start` can take 30-90s on a cold
    // cache (debug session 2026-05-04 measured 53s for poolprobe4). Without
    // this, click-spamming the Restart button fires N parallel /start
    // requests that all queue behind the per-tag asyncio.Lock; the first
    // wins, the rest 409 Conflict.
    if (_restartInflight) return;

    final agent = ref.read(agentsListProvider).asData?.value
        .where((a) => a.id == widget.agentInstanceId)
        .firstOrNull;
    if (agent == null) {
      // No agent loaded — can't lookup recipe. Should never happen
      // because the banner only renders when agent != null, but defensive.
      return;
    }

    // Inflight state — disables the button + shows spinner + elapsed
    // counter in the RestartBanner. Tick every 1s so the user sees the
    // counter advance and knows the request is alive.
    setState(() {
      _restartInflight = true;
      _restartElapsed = Stopwatch()..start();
    });
    _restartTick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });

    RestartOutcome? outcome;
    try {
      outcome = await restartAgent(
        agent: agent,
        api: ref.read(apiClientProvider),
        storage: ref.read(secureStorageProvider),
      );
    } catch (e) {
      // Defensive — restartAgent wraps dio errors in RestartFailed but a
      // non-dio throw (parse error, etc.) would otherwise vanish into
      // an unhandled Future.
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            duration: const Duration(seconds: 8),
            content: Text('Restart failed: $e'),
          ),
        );
      }
    } finally {
      _restartTick?.cancel();
      _restartTick = null;
      if (mounted) {
        setState(() {
          _restartInflight = false;
          _restartElapsed = null;
        });
      }
    }
    if (!context.mounted || outcome == null) return;
    switch (outcome) {
      case RestartOk():
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            duration: Duration(seconds: 4),
            content: Text('Agent restarted'),
          ),
        );
      case RestartNoBYOK():
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            duration: Duration(seconds: 8),
            content: Text(
              'No BYOK key stored for this agent — re-deploy via the wizard '
              'to enter your API key.',
            ),
          ),
        );
      case RestartFailed(:final error):
        if (error.code == ErrorCode.agentAlreadyRunning) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Agent is already running'),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              duration: const Duration(seconds: 8),
              content: Text('Restart failed: ${error.message}'),
            ),
          );
        }
    }
    ref.invalidate(agentsListProvider);
  }

  /// Gracefully stop the running agent via POST /v1/agents/:id/stop.
  /// Mirrors the dashboard `_stopAgent` flow but lives here so the
  /// AppBar overflow menu can swap to a 'Stopping…' label + spinner
  /// while in flight (re-entrancy guard via `_stopInflight`).
  Future<void> _stopAgent(BuildContext ctx, AgentSummary agent) async {
    if (_stopInflight) return;
    setState(() => _stopInflight = true);
    try {
      final outcome = await stopAgent(
        agent: agent,
        api: ref.read(apiClientProvider),
        storage: ref.read(secureStorageProvider),
      );
      if (!ctx.mounted) return;
      switch (outcome) {
        case StopOk():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(content: Text('Agent stopped')),
          );
        case StopAlreadyStopped():
          ScaffoldMessenger.of(ctx).showSnackBar(
            const SnackBar(content: Text('Agent already stopped')),
          );
        case StopFailed(:final error):
          ScaffoldMessenger.of(ctx).showSnackBar(
            SnackBar(
              duration: const Duration(seconds: 8),
              content: Text('Stop failed: ${error.message}'),
            ),
          );
      }
      // Invalidate on success + already-stopped (cache-correction);
      // skip on hard failures so the row keeps its current state.
      if (outcome is StopOk || outcome is StopAlreadyStopped) {
        ref.invalidate(agentsListProvider);
      }
    } finally {
      if (mounted) setState(() => _stopInflight = false);
    }
  }
}

class _ChatAppBarTitle extends ConsumerWidget {
  const _ChatAppBarTitle({required this.agent, required this.fallbackId});

  final AgentSummary? agent;
  final String fallbackId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // If the agentsListProvider hasn't surfaced this agent yet (cold-mount
    // race after a fresh deploy), show 'Loading…' rather than the raw
    // agent_instance UUID. The provider invalidates on chat dispose +
    // wizard close so this branch is short-lived.
    final title = agent?.name ?? 'Loading…';

    // Resolve the per-recipe emoji for the agent (parity with the
    // dashboard AgentRow). Falls back to no glyph when the recipe
    // declares none or recipesProvider hasn't loaded yet.
    String? emoji;
    if (agent != null) {
      final recipesAsync = ref.watch(recipesProvider);
      emoji = recipesAsync
          .maybeWhen(data: (l) => l, orElse: () => const <Recipe>[])
          .where((r) => r.name == agent!.recipeName)
          .map((r) => r.emoji)
          .firstOrNull;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: SolvrColors.foreground,
          ),
        ),
        if (agent != null)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (emoji != null && emoji.isNotEmpty) ...[
                ExcludeSemantics(
                  child: Text(
                    emoji,
                    style: const TextStyle(fontSize: 12, height: 1.0),
                  ),
                ),
                const SizedBox(width: 4),
              ],
              Flexible(
                child: Text(
                  // recipe · model — gives the user immediate context
                  // about what kind of agent they're chatting with.
                  '${agent!.recipeName} · ${agent!.model}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: SolvrTextStyles.mono(fontSize: 12).copyWith(
                    color: SolvrColors.mutedForeground,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              StatusDot(status: agent!.status, size: 6),
            ],
          ),
      ],
    );
  }
}

class _OlderMessagesBanner extends StatelessWidget {
  const _OlderMessagesBanner({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        child: Container(
          width: double.infinity,
          color: SolvrColors.muted,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: const Text(
            'Older messages not shown · Tap to load up to 1000 more',
            style: TextStyle(
              fontSize: 12,
              color: SolvrColors.mutedForeground,
            ),
          ),
        ),
      );
}

class _EmptyChatState extends StatelessWidget {
  const _EmptyChatState({this.agentName});
  final String? agentName;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'Say hi to ${agentName ?? 'your agent'}',
            style: const TextStyle(
              fontSize: 16,
              fontStyle: FontStyle.italic,
              color: SolvrColors.mutedForeground,
            ),
          ),
        ),
      );
}

class _MessageList extends StatelessWidget {
  const _MessageList({
    required this.state,
    required this.scrollCtl,
    required this.agentInstanceId,
    required this.notifier,
    required this.showJumpChip,
  });

  final ChatState state;
  final ScrollController scrollCtl;
  final String agentInstanceId;
  final ChatScope notifier;
  final bool showJumpChip;

  @override
  Widget build(BuildContext context) => Stack(
        children: [
          ListView.builder(
            key: const Key('chat-message-list'),
            controller: scrollCtl,
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: state.orderedIds.length,
            itemBuilder: (ctx, i) {
              final row = state.byId[state.orderedIds[i]]!;
              final prev = i == 0
                  ? null
                  : state.byId[state.orderedIds[i - 1]];
              final divider = TimestampDivider.maybeBuildFromIso(
                prevIso: prev?.createdAt,
                nextIso: row.createdAt,
              );
              final bubble = _ChatRowWidget(row: row, notifier: notifier);
              if (divider == null) return bubble;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [divider, bubble],
              );
            },
          ),
          if (showJumpChip)
            Positioned(
              bottom: 12,
              right: 12,
              child: ActionChip(
                key: const Key('chat-jump-chip'),
                label: const Text('New message ↓'),
                onPressed: () {
                  scrollCtl.animateTo(
                    scrollCtl.position.maxScrollExtent,
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeOut,
                  );
                },
              ),
            ),
        ],
      );
}

class _ChatRowWidget extends StatelessWidget {
  const _ChatRowWidget({required this.row, required this.notifier});

  final ChatRow row;
  final ChatScope notifier;

  @override
  Widget build(BuildContext context) {
    if (row.status == 'failed') {
      return FailedBubble(
        role: row.role,
        content: row.content.isEmpty
            ? (row.errorMessage ?? 'Send failed')
            : row.content,
        onRetry: () => notifier.retryFailed(
          failedKey: row.id,
          content: row.content,
        ),
        onCopyError: () =>
            Clipboard.setData(ClipboardData(text: row.errorMessage ?? '')),
      );
    }
    if (row.status == 'typing') {
      return const Align(
        alignment: Alignment.centerLeft,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: TypingDots(),
        ),
      );
    }
    if (row.role == 'user') {
      return UserBubble(
        content: row.content,
        onCopy: () => Clipboard.setData(ClipboardData(text: row.content)),
      );
    }
    return AssistantBubble(
      content: row.content,
      onCopy: () => Clipboard.setData(ClipboardData(text: row.content)),
    );
  }
}
