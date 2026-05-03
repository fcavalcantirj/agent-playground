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
import 'package:agent_playground/shared/failed_bubble.dart';
import 'package:agent_playground/shared/restart_banner.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:agent_playground/shared/typing_dots.dart';
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

  @override
  void initState() {
    super.initState();
    _scrollCtl.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollCtl.removeListener(_onScroll);
    _scrollCtl.dispose();
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
    // D-49 — multi-channel restart needs the channel set; the extended
    // /v1/agents response is not yet wired here, so mobile defaults to
    // inapp. Surfaced as a planner-deferred TODO in CONTEXT.
    //
    // Phase 25 Wave 5: /v1/agents/:id/start REQUIRES a Bearer BYOK key
    // (api_server/src/api_server/routes/agent_lifecycle.py:236-242).
    // Look up the recipe's provider from the agent's recipe name + read
    // the stored byok_key_<provider>. If we don't have one cached, the
    // restart silently 401s. Surface a SnackBar so the user knows why.
    final api = ref.read(apiClientProvider);
    final storage = ref.read(secureStorageProvider);
    final agent = ref.read(agentsListProvider).asData?.value
        .where((a) => a.id == widget.agentInstanceId)
        .firstOrNull;
    String? byokKey;
    if (agent != null) {
      final detailRes = await api.recipeDetail(name: agent.recipeName);
      if (detailRes case Ok<RecipeDetail>(value: final detail)) {
        // The recipe's inapp channel declares which providers are
        // supported; we stored the BYOK under byok_key_<provider> when
        // the user typed it during the wizard. Use the first supported
        // provider that has a key — covers the common single-provider
        // recipes (zeroclaw → openrouter, openclaw → anthropic, ...).
        final compat = detail.channelProviderCompat['inapp'];
        if (compat != null) {
          for (final provider in compat.supported) {
            final k = await storage.readByokKey(provider);
            if (k != null && k.isNotEmpty) {
              byokKey = k;
              break;
            }
          }
        }
      }
    }
    if (byokKey == null || byokKey.isEmpty) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No BYOK key stored for this agent — re-deploy via the wizard '
              'to enter your API key.',
            ),
          ),
        );
      }
      return;
    }
    final res = await api.start(
      agentId: widget.agentInstanceId,
      byokOpenRouterKey: byokKey,
    );
    if (res is Err<StartResponse> && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Restart failed: ${res.error.message}')),
      );
    }
    ref.invalidate(agentsListProvider);
  }
}

class _ChatAppBarTitle extends StatelessWidget {
  const _ChatAppBarTitle({required this.agent, required this.fallbackId});

  final AgentSummary? agent;
  final String fallbackId;

  @override
  Widget build(BuildContext context) {
    final title = agent?.name ?? fallbackId;
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
              Flexible(
                child: Text(
                  agent!.model,
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
