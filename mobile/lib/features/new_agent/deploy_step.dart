// Phase 25 Wave 3 plan 25-06 task 2 — Wizard Step 3: Name + Telegram +
// Deploy.
//
// Replaces the Wave 1 stub. Composes:
//   1. Name TextField with regex validation per D-27
//      (^[a-z0-9][a-z0-9_-]*$, length ≤ 64).
//   2. Telegram toggle row (visible ONLY when
//      recipe.channelsSupported includes 'telegram' per D-55).
//   3. Dynamic ChannelInputs widget when toggle is ON (D-54).
//   4. Deploy button — disabled until form is valid + (telegram OFF OR
//      all required Telegram inputs filled).
//
// On Deploy tap:
//   1. Pre-flight name-collision check (D-28) — agentsList() lookup +
//      ConfirmDialog with Cancel / Re-deploy / Rename.
//   2. Smoke loading UX (D-29) — replaces Deploy button with progress
//      card + 1s tick + Cancel via dio CancelToken.
//   3. DeployOrchestrator runs the 1×/runs + N×/start sequence (D-56).
//   4. Branch per outcome:
//        - success (D-60) → clear wizard scope + go('/chat/<id>') REPLACE
//        - partialSuccess (D-58) → set telegramFailedBannerProvider +
//          clear wizard scope + go('/chat/<id>')
//        - smokeFail / runsError (D-30) → red error card + Retry / Edit
//        - inappFail (D-57) → red error card with inapp title + Retry
//        - cancelled → reset to editing
//
// Web mirror: frontend/components/playground-form.tsx lines 316-360.
// Golden Rule #2: NEVER hardcode Telegram field labels. They come from
// recipe.channels.telegram.required_user_input via ChannelInputs.

import 'dart:async';

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/telegram_failed_banner_provider.dart';
import 'package:agent_playground/features/new_agent/channel_inputs.dart';
import 'package:agent_playground/features/new_agent/deploy_orchestrator.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_shell.dart';
import 'package:agent_playground/shared/confirm_dialog.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// D-27 — agent name regex (stricter than backend per PATTERNS line 723):
/// lowercase + digits + `_` + `-`, must start with letter/digit, no
/// spaces. Backend accepts the looser case-insensitive + space pattern;
/// the client's stricter regex gives a cleaner UX.
final RegExp kAgentNameRegex = RegExp(r'^[a-z0-9][a-z0-9_-]*$');

/// D-27 — backend cap (api_server/src/api_server/models/runs.py line 80).
const int kAgentNameMaxLength = 64;

class DeployStep extends ConsumerStatefulWidget {
  const DeployStep({super.key});

  /// D-29 / Plan 25-06 — orchestrator override seam for tests. Production
  /// uses `DeployOrchestrator(apiClient)`. Tests inject a fake to
  /// short-circuit the dio layer entirely. Reset to `null` between tests
  /// (setUp / tearDown).
  static DeployOrchestrator Function(ApiClient api)? orchestratorBuilder;

  @override
  ConsumerState<DeployStep> createState() => _DeployStepState();
}

enum _DeployStateKind { editing, smokeLoading, smokeFail, inappFail }

class _DeployStepState extends ConsumerState<DeployStep> {
  final _nameCtl = TextEditingController();
  final _nameFocus = FocusNode();

  _DeployStateKind _state = _DeployStateKind.editing;
  String? _errorTitle;
  String? _errorBody;
  CancelToken? _cancel;
  Stopwatch? _elapsed;
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    final initial = ref.read(wizardScopeProvider).agentName;
    _nameCtl.text = initial;
  }

  @override
  void dispose() {
    _nameCtl.dispose();
    _nameFocus.dispose();
    _tick?.cancel();
    _cancel?.cancel('DeployStep disposed');
    super.dispose();
  }

  // ------------------------------------------------------------------
  // Name validation (D-27).
  // ------------------------------------------------------------------
  String? _nameValidationError(String v) {
    final trimmed = v.trim();
    if (trimmed.isEmpty) return null;
    if (trimmed.length > kAgentNameMaxLength) return 'Name too long (max 64).';
    if (!kAgentNameRegex.hasMatch(trimmed)) {
      return 'Lowercase letters, numbers, _ and - only';
    }
    return null;
  }

  bool _telegramSupported(WizardScopeState scope) =>
      scope.selectedRecipe?.channelsSupported.contains('telegram') ?? false;

  bool _telegramRequiredFilled(WizardScopeState scope) {
    if (!scope.telegramEnabled) return true;
    final tg = scope.selectedRecipe?.channels['telegram'];
    if (tg == null) return true;
    for (final input in tg.requiredUserInput) {
      final v = scope.telegramInputs[input.env];
      if (v == null || v.trim().isEmpty) return false;
    }
    return true;
  }

  bool _formValid(WizardScopeState scope) {
    final name = scope.agentName.trim();
    if (name.isEmpty) return false;
    if (_nameValidationError(name) != null) return false;
    if (scope.selectedRecipe == null) return false;
    if (scope.selectedModel == null) return false;
    if (scope.byokKey.isEmpty) return false;
    if (!_telegramRequiredFilled(scope)) return false;
    return true;
  }

  // ------------------------------------------------------------------
  // Deploy entrypoint.
  // ------------------------------------------------------------------
  Future<void> _onDeploy() async {
    final scope = ref.read(wizardScopeProvider);
    if (!_formValid(scope)) return;
    final name = scope.agentName.trim();

    // D-28 — pre-flight name-collision check.
    final api = ref.read(apiClientProvider);
    final agentsRes = await api.agentsList();
    if (!mounted) return;
    if (agentsRes case Ok(:final value)) {
      AgentSummary? existing;
      for (final a in value) {
        if (a.name == name) {
          existing = a;
          break;
        }
      }
      if (existing != null) {
        final r = await ConfirmDialog.show(
          context,
          title: 'Name "$name" already used',
          body: 'Existing agent: ${existing.recipeName} + ${existing.model}. '
              'Re-deploy replaces it; rename keeps both.',
          confirmLabel: 'Re-deploy',
          thirdButtonLabel: 'Rename',
        );
        if (!mounted) return;
        switch (r) {
          case ConfirmDialogResult.cancel:
            return;
          case ConfirmDialogResult.third:
            _nameFocus.requestFocus();
            return;
          case ConfirmDialogResult.confirm:
            // Proceed to deploy.
            break;
        }
      }
    }

    // D-29 — smoke loading UX.
    setState(() {
      _state = _DeployStateKind.smokeLoading;
      _elapsed = Stopwatch()..start();
      _errorTitle = null;
      _errorBody = null;
    });
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    _cancel = CancelToken();

    final orchestrator =
        (DeployStep.orchestratorBuilder ?? DeployOrchestrator.new)(api);
    final outcome = await orchestrator.deploy(
      recipeName: scope.selectedRecipe!.name,
      modelId: scope.selectedModel!.id,
      agentName: name,
      byokKey: scope.byokKey,
      telegramEnabled: scope.telegramEnabled && _telegramSupported(scope),
      telegramInputs:
          Map<String, String>.from(scope.telegramInputs),
      cancelToken: _cancel,
    );
    _tick?.cancel();
    _tick = null;
    if (!mounted) return;

    switch (outcome) {
      case DeploySuccess(:final agentInstanceId):
        ref.read(telegramFailedBannerProvider.notifier).state = null;
        ref.read(wizardScopeProvider.notifier).clear();
        if (!mounted) return;
        context.go('/chat/$agentInstanceId');
        return;
      case DeployPartialSuccess(
          :final agentInstanceId,
          :final telegramFailReason,
          :final telegramInputs,
        ):
        ref.read(telegramFailedBannerProvider.notifier).state =
            TelegramFailedBannerState(
          agentInstanceId: agentInstanceId,
          reason: telegramFailReason,
          telegramInputs: telegramInputs,
        );
        ref.read(wizardScopeProvider.notifier).clear();
        if (!mounted) return;
        context.go('/chat/$agentInstanceId');
        return;
      case DeploySmokeFail(:final reason):
        setState(() {
          _state = _DeployStateKind.smokeFail;
          _errorTitle = 'Smoke test failed';
          _errorBody = reason;
        });
        return;
      case DeployRunsError(:final error):
        setState(() {
          _state = _DeployStateKind.smokeFail;
          _errorTitle = 'Smoke test failed';
          _errorBody = error.message;
        });
        return;
      case DeployInappFail(:final error):
        setState(() {
          _state = _DeployStateKind.inappFail;
          if (error.code == ErrorCode.tierLimitExceeded) {
            // B-stripe regression fix: don't leak "agent cap reached for
            // tier 'free' (1 active, cap 1)" jargon. Map to plain English.
            _errorTitle = 'Plan limit reached';
            _errorBody =
                "You've used your free plan's only agent slot. Stop "
                'an existing agent to deploy a new one, or upgrade to '
                'Pro for 5 active agents.';
          } else {
            _errorTitle = "Couldn't start in-app channel";
            _errorBody = error.message;
          }
        });
        return;
      case DeployCancelled():
        setState(() => _state = _DeployStateKind.editing);
        return;
    }
  }

  void _onCancelInflight() {
    _cancel?.cancel('user cancelled smoke');
    _tick?.cancel();
    _tick = null;
    setState(() => _state = _DeployStateKind.editing);
  }

  // ------------------------------------------------------------------
  // Build.
  // ------------------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final scope = ref.watch(wizardScopeProvider);
    final telegramVisible = _telegramSupported(scope);
    final nameError = _nameValidationError(_nameCtl.text);

    return WizardShell(
      title: 'Name + Deploy',
      currentStep: 2,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const ValueKey('agent_name_field'),
              controller: _nameCtl,
              focusNode: _nameFocus,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: 'Agent name',
                errorText: nameError,
              ),
              onChanged: (v) {
                ref.read(wizardScopeProvider.notifier).setAgentName(v);
              },
            ),
            if (telegramVisible) ...[
              const SizedBox(height: 24),
              _TelegramToggleRow(
                value: scope.telegramEnabled,
                onChanged: (v) => ref
                    .read(wizardScopeProvider.notifier)
                    .setTelegramEnabled(v),
              ),
              if (scope.telegramEnabled &&
                  scope.selectedRecipe?.channels['telegram'] != null)
                ChannelInputs(
                  channelMeta: scope.selectedRecipe!.channels['telegram']!,
                ),
            ],
            const SizedBox(height: 32),
            _DeployFooter(
              state: _state,
              elapsed: _elapsed,
              errorTitle: _errorTitle,
              errorBody: _errorBody,
              canDeploy: _formValid(scope),
              onDeploy: _onDeploy,
              onCancel: _onCancelInflight,
              onRetry: _onDeploy,
              onEdit: () {
                setState(() => _state = _DeployStateKind.editing);
                context.go('/new-agent/clone');
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _TelegramToggleRow extends StatelessWidget {
  const _TelegramToggleRow({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Switch(value: value, onChanged: onChanged),
            const SizedBox(width: 8),
            const Expanded(child: Text('Add Telegram channel')),
          ],
        ),
        Padding(
          padding: const EdgeInsets.only(left: 8, top: 4),
          child: Text(
            'Send messages to this agent from Telegram too.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: SolvrColors.mutedForeground,
                ),
          ),
        ),
      ],
    );
  }
}

class _DeployFooter extends StatelessWidget {
  const _DeployFooter({
    required this.state,
    required this.elapsed,
    required this.errorTitle,
    required this.errorBody,
    required this.canDeploy,
    required this.onDeploy,
    required this.onCancel,
    required this.onRetry,
    required this.onEdit,
  });

  final _DeployStateKind state;
  final Stopwatch? elapsed;
  final String? errorTitle;
  final String? errorBody;
  final bool canDeploy;
  final VoidCallback onDeploy;
  final VoidCallback onCancel;
  final VoidCallback onRetry;
  final VoidCallback onEdit;

  String _formatElapsed(Stopwatch? s) {
    final secs = s?.elapsed.inSeconds ?? 0;
    final mm = (secs ~/ 60).toString().padLeft(2, '0');
    final ss = (secs % 60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case _DeployStateKind.editing:
        return SizedBox(
          height: 48,
          child: ElevatedButton(
            onPressed: canDeploy ? onDeploy : null,
            child: const Text('Deploy'),
          ),
        );
      case _DeployStateKind.smokeLoading:
        return Container(
          padding: const EdgeInsets.all(16),
          decoration:
              BoxDecoration(border: Border.all(color: SolvrColors.border)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text('Smoke testing recipe + model + key…'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    _formatElapsed(elapsed),
                    style: SolvrTextStyles.mono(fontSize: 12).copyWith(
                      color: SolvrColors.mutedForeground,
                    ),
                  ),
                  TextButton(
                    onPressed: onCancel,
                    child: const Text('Cancel'),
                  ),
                ],
              ),
            ],
          ),
        );
      case _DeployStateKind.smokeFail:
      case _DeployStateKind.inappFail:
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            border: Border.all(color: SolvrColors.destructive),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                errorTitle ?? '',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: SolvrColors.destructive,
                      fontWeight: FontWeight.w600,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                errorBody ?? '',
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 48,
                      child: ElevatedButton(
                        onPressed: onRetry,
                        child: const Text('Retry'),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: SizedBox(
                      height: 48,
                      child: ElevatedButton(
                        onPressed: onEdit,
                        child: const Text('Edit'),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
    }
  }
}
