// Phase 25 Wave 3 plan 25-05 task 3 — Step 2: Model + BYOK (D-26 + D-32 +
// D-33 + D-34).
//
// UI-SPEC ### Step 2 (lines 567-572):
// - "Pick a model" button (D-26) → push `/new-agent/model/picker`. After
//   selection: greyed card with model id + Change text button.
// - BYOK TextField with DYNAMIC label per D-32:
//     label = 'OpenRouter API Key' by default;
//     label = 'Anthropic API Key' when
//       `recipe.channelProviderCompat['inapp']?.deferred` contains
//       'openrouter' (e.g. hermes; openclaw + telegram).
//   The label-swap reads server metadata (Golden Rule #2 — NEVER a Dart
//   `if recipe == 'hermes'` branch). storageProvider key flips with the
//   label so each provider has its own keychain entry.
// - obscureText: true + eye-toggle suffix (D-34); autocorrect/enableSuggestions
//   false.
// - Auto-fill from `secureStorage.readByokKey(provider)` on mount (D-33).
// - On change: persist via `secureStorage.writeByokKey(provider, value)`
//   AND mirror into `wizardScope.byokKey` so step 3 can read it.
// - Next disabled until `selectedModel != null && byokKey.isNotEmpty`.

import 'dart:async';

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class ModelStep extends ConsumerStatefulWidget {
  const ModelStep({super.key});

  @override
  ConsumerState<ModelStep> createState() => _ModelStepState();
}

class _ModelStepState extends ConsumerState<ModelStep> {
  final _byokCtl = TextEditingController();
  bool _obscured = true;
  String? _hydratedFor; // provider key the controller was hydrated for

  @override
  void dispose() {
    _byokCtl.dispose();
    super.dispose();
  }

  /// D-32 BYOK label-swap. Reads server-supplied
  /// `channel_provider_compat[inapp].supported` (canonical "primary
  /// provider" of the recipe). Bug fix 2026-05-04: previously this
  /// switched on `deferred.contains('openrouter')` — a heuristic that
  /// was correct for openclaw.telegram (`{supported:[anthropic],
  /// deferred:[openrouter]}`) but wrong for openclaw.inapp where the
  /// synthesizer (api_server commit 925a1bf) produces
  /// `{supported:[anthropic], deferred:[]}` (no deferral; Anthropic is
  /// just THE provider). Switching on `supported` directly is correct
  /// for all 6 v0.2 recipes — the synthesizer guarantees the field is
  /// populated. Defaults to OpenRouter when no recipe is selected
  /// (defensive — first-render before selectedRecipe lands).
  ({String label, String storageProvider}) _byokConfig(
    RecipeDetail? recipe,
  ) {
    final supported = recipe?.channelProviderCompat['inapp']?.supported ??
        const <String>['openrouter'];
    final primary = supported.firstWhere(
      (p) => p == 'anthropic' || p == 'openrouter' || p == 'openai',
      orElse: () => 'openrouter',
    );
    return switch (primary) {
      'anthropic' => (
          label: 'Anthropic API Key',
          storageProvider: 'anthropic',
        ),
      'openai' => (
          label: 'OpenAI API Key',
          storageProvider: 'openai',
        ),
      _ => (
          label: 'OpenRouter API Key',
          storageProvider: 'openrouter',
        ),
    };
  }

  /// D-33 auto-fill from secureStorage.readByokKey() on first build (or
  /// when the provider key changes — e.g. user goes back to step 1 and
  /// picks a hermes recipe after openclaw).
  Future<void> _hydrateFromStorage(String provider) async {
    if (_hydratedFor == provider) return;
    _hydratedFor = provider;
    final stored =
        await ref.read(secureStorageProvider).readByokKey(provider);
    if (!mounted) return;
    if (stored != null && stored.isNotEmpty) {
      _byokCtl.text = stored;
      ref.read(wizardScopeProvider.notifier).setByokKey(stored);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scope = ref.watch(wizardScopeProvider);
    final cfg = _byokConfig(scope.selectedRecipe);

    // Schedule the hydrate after the frame so the WidgetRef.read calls
    // don't trip the "ref.read during build" Riverpod assertion. The
    // future is fire-and-forget — _hydrateFromStorage owns its own
    // mounted-check + setBYOK-once-per-provider guard.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_hydrateFromStorage(cfg.storageProvider));
    });

    return WizardShell(
      title: 'Pick a model + key',
      currentStep: 1,
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (scope.selectedModel == null)
              SizedBox(
                height: 48,
                child: ElevatedButton(
                  onPressed: () => _openPicker(context),
                  child: const Text('Pick a model'),
                ),
              )
            else
              _SelectedModelCard(
                model: scope.selectedModel!,
                verified: scope.selectedRecipe?.verifiedModels
                        .contains(scope.selectedModel!.id) ??
                    false,
                onChange: () => _openPicker(context),
              ),
            const SizedBox(height: 24),
            TextField(
              controller: _byokCtl,
              obscureText: _obscured,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: cfg.label,
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscured ? Icons.visibility : Icons.visibility_off,
                  ),
                  tooltip: _obscured ? 'Show key' : 'Hide key',
                  onPressed: () => setState(() => _obscured = !_obscured),
                ),
              ),
              onChanged: (v) async {
                ref.read(wizardScopeProvider.notifier).setByokKey(v);
                await ref
                    .read(secureStorageProvider)
                    .writeByokKey(cfg.storageProvider, v);
              },
            ),
            const SizedBox(height: 32),
            SizedBox(
              height: 48,
              child: ElevatedButton(
                onPressed: (scope.selectedModel != null &&
                        scope.byokKey.isNotEmpty)
                    ? () => context.push('/new-agent/name-deploy')
                    : null,
                child: const Text('Next'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openPicker(BuildContext context) async {
    final picked = await context.push<OpenRouterModel>(
      '/new-agent/model/picker',
    );
    if (picked != null && mounted) {
      ref.read(wizardScopeProvider.notifier).setSelectedModel(picked);
    }
  }
}

class _SelectedModelCard extends StatelessWidget {
  const _SelectedModelCard({
    required this.model,
    required this.onChange,
    this.verified = false,
  });

  final OpenRouterModel model;
  final VoidCallback onChange;

  /// True when `model.id` is in the selected recipe's `verifiedModels`
  /// list — surfaces a "✓ verified pairing" chip so the user knows the
  /// preselection / current choice is a recipe-author-tested combo.
  /// Mirrors the chip vocabulary used by `model_picker_screen._ModelRow`.
  final bool verified;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: SolvrColors.muted,
        border: Border.all(color: SolvrColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        model.id,
                        style: SolvrTextStyles.mono(fontSize: 14),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (verified) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: SolvrColors.card,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.check,
                              size: 12,
                              color: SolvrColors.foreground,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'verified pairing',
                              style: SolvrTextStyles.mono(fontSize: 10)
                                  .copyWith(
                                color: SolvrColors.mutedForeground,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
                if (model.name != model.id) ...[
                  const SizedBox(height: 2),
                  Text(
                    model.name,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: SolvrColors.mutedForeground,
                        ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
          TextButton(onPressed: onChange, child: const Text('Change')),
        ],
      ),
    );
  }
}
