// Phase 25 Wave 3 plan 25-05 task 2 — common wizard chrome.
//
// Renders the shared AppBar (back arrow on steps 2/3 + X close on every
// step per D-31), the step indicator (D-23 — three dots + caption labels),
// and a body slot for per-step content. Cancel UX (D-31): X tap reads
// wizardScope.isDirty; if dirty → ConfirmDialog "Discard changes?",
// otherwise pop straight to /dashboard. Discard confirms → clear() the
// wizard scope + go('/dashboard'). Back arrow taps `Navigator.pop` so
// per-step state is preserved across the wizard session per D-24.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:agent_playground/shared/confirm_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// Shared AppBar + stepper + body slot for the 3 wizard steps.
class WizardShell extends ConsumerWidget {
  const WizardShell({
    required this.title,
    required this.currentStep,
    required this.body,
    this.canGoBack = true,
    super.key,
  });

  /// AppBar title (e.g. "Pick a clone", "Pick a model + key", "Name + Deploy").
  final String title;

  /// 0-indexed step number (0 = Clone, 1 = Model + Key, 2 = Name + Deploy).
  /// Drives the filled stepper dot per D-23.
  final int currentStep;

  /// Per-step body. WizardShell does NOT scroll the body — leave that to
  /// the caller (some steps need horizontal scrolling, others vertical).
  final Widget body;

  /// Step 1 has only X (no prior step); steps 2/3 also have ←. Defaults
  /// to true — callers explicitly pass `false` on step 1.
  final bool canGoBack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        leading: canGoBack
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                tooltip: 'Back',
                onPressed: () => Navigator.of(context).pop(),
              )
            : null,
        title: Text(title),
        actions: [
          IconButton(
            icon: const Icon(Icons.close),
            tooltip: 'Close',
            onPressed: () => _onClose(context, ref),
          ),
        ],
      ),
      body: Column(
        children: [
          _Stepper(currentStep: currentStep),
          const SizedBox(height: 8),
          Expanded(child: body),
        ],
      ),
    );
  }

  Future<void> _onClose(BuildContext context, WidgetRef ref) async {
    final isDirty = ref.read(wizardScopeProvider).isDirty;
    if (!isDirty) {
      ref.read(wizardScopeProvider.notifier).clear();
      // A long-running deploy may have completed in the background even
      // though the wizard surfaced a smoke-fail (mobile timeout) — refresh
      // the dashboard so the new agent shows up without pull-to-refresh.
      ref.invalidate(agentsListProvider);
      if (context.mounted) {
        context.go('/dashboard');
      }
      return;
    }
    final result = await ConfirmDialog.show(
      context,
      title: 'Discard changes?',
      confirmLabel: 'Discard',
    );
    if (result != ConfirmDialogResult.confirm) return;
    ref.read(wizardScopeProvider.notifier).clear();
    ref.invalidate(agentsListProvider);
    if (context.mounted) {
      context.go('/dashboard');
    }
  }
}

class _Stepper extends StatelessWidget {
  const _Stepper({required this.currentStep});

  final int currentStep;

  static const _labels = ['Clone', 'Model + Key', 'Name + Deploy'];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (var i = 0; i < 3; i++) ...[
                _Dot(filled: i == currentStep),
                if (i < 2)
                  Container(
                    width: 32,
                    height: 1,
                    margin: const EdgeInsets.symmetric(horizontal: 8),
                    color: SolvrColors.border,
                  ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: List.generate(
              3,
              (i) => Expanded(
                child: Text(
                  _labels[i],
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: SolvrColors.mutedForeground,
                      ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.filled});

  final bool filled;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 16,
      height: 16,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: filled ? SolvrColors.foreground : null,
        border: filled
            ? null
            : Border.all(color: SolvrColors.border),
      ),
    );
  }
}
