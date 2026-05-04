// Phase 25 Wave 3 plan 25-05 task 2 — wizard scope (D-21 + Pitfall #10
// Pattern A) + Wave 3 task 3 — modelsProvider (D-26 source).
//
// Pitfall #10 Pattern A: a single Notifier (not autoDispose) holding the
// entire wizard's transient state across steps 1/2/2.5/3 + push-route
// model picker. Manually `ref.invalidate(wizardScopeProvider)` on
// (a) cancel-X confirm (D-31) and (b) Deploy success (D-60). Pattern A
// over Pattern B (ProviderScope override + ShellRoute) per 25-RESEARCH
// Pitfall #10 — there is only one wizard at a time, so explicit
// invalidation is simpler than wiring a route-group ProviderScope.
//
// Authoring style: riverpod_annotation + riverpod_generator. Matches
// `core/api/providers.dart` shape (Phase 24 D-34 only forbids JSON
// codegen — riverpod_generator is independent).

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'wizard_providers.g.dart';

/// Transient wizard state. Persisted ONLY in memory — see D-50: per-deploy
/// Telegram bot tokens are NOT written to flutter_secure_storage. BYOK
/// keys live in flutter_secure_storage via `secureStorageProvider`
/// (D-33), not here.
class WizardScopeState {
  const WizardScopeState({
    this.selectedRecipe,
    this.selectedModel,
    this.byokKey = '',
    this.agentName = '',
    this.telegramEnabled = false,
    this.telegramInputs = const <String, String>{},
  });

  final RecipeDetail? selectedRecipe;
  final OpenRouterModel? selectedModel;
  final String byokKey;
  final String agentName;
  final bool telegramEnabled;
  final Map<String, String> telegramInputs;

  /// Drives D-31 cancel UX — X close skips the ConfirmDialog when no
  /// field has been touched.
  bool get isDirty =>
      selectedRecipe != null ||
      selectedModel != null ||
      byokKey.isNotEmpty ||
      agentName.isNotEmpty ||
      telegramEnabled ||
      telegramInputs.isNotEmpty;

  WizardScopeState copyWith({
    RecipeDetail? selectedRecipe,
    OpenRouterModel? selectedModel,
    String? byokKey,
    String? agentName,
    bool? telegramEnabled,
    Map<String, String>? telegramInputs,
  }) =>
      WizardScopeState(
        selectedRecipe: selectedRecipe ?? this.selectedRecipe,
        selectedModel: selectedModel ?? this.selectedModel,
        byokKey: byokKey ?? this.byokKey,
        agentName: agentName ?? this.agentName,
        telegramEnabled: telegramEnabled ?? this.telegramEnabled,
        telegramInputs: telegramInputs ?? this.telegramInputs,
      );
}

@Riverpod(keepAlive: true)
class WizardScope extends _$WizardScope {
  @override
  WizardScopeState build() => const WizardScopeState();

  void setSelectedRecipe(RecipeDetail r) =>
      state = state.copyWith(selectedRecipe: r);
  void setSelectedModel(OpenRouterModel m) =>
      state = state.copyWith(selectedModel: m);
  void setByokKey(String k) => state = state.copyWith(byokKey: k);
  void setAgentName(String n) => state = state.copyWith(agentName: n);
  // The single-bool toggle setter is symmetric with the other setters
  // (setSelectedRecipe / setSelectedModel / ...); a named-param wrapper
  // would only add ceremony at every callsite for one parameter.
  // ignore: avoid_positional_boolean_parameters
  void setTelegramEnabled(bool v) =>
      state = state.copyWith(telegramEnabled: v);
  void setTelegramInput(String env, String value) {
    final next = Map<String, String>.from(state.telegramInputs);
    next[env] = value;
    state = state.copyWith(telegramInputs: next);
  }

  /// Reset the wizard to its empty state. Called from:
  ///   - WizardShell._onClose after the Discard ConfirmDialog (D-31).
  ///   - DeployStep success path (Plan 25-06 — D-60 wizard exit).
  void clear() => state = const WizardScopeState();
}

/// Cached `GET /v1/models` for the model picker (D-26). Mirrors the shape
/// of `recipesProvider` in dashboard_providers.dart (Phase 25 Plan 25-04).
@Riverpod(keepAlive: true)
Future<List<OpenRouterModel>> models(Ref ref) async {
  final api = ref.watch(apiClientProvider);
  final r = await api.models();
  return switch (r) {
    Ok(:final value) => value,
    // ApiError is the typed envelope (Phase 24 D-32) — Riverpod surfaces
    // it as AsyncError to widget consumers.
    // ignore: only_throw_errors
    Err(:final error) => throw error,
  };
}

/// Provider-scoped catalog: same as [modelsProvider] but passes
/// `?provider=<arg>` to the server so the response is filtered to ids
/// matching the recipe's primary provider (`anthropic/...`,
/// `~anthropic/...`, etc. for openclaw; full catalog for openrouter
/// recipes). Bug fix 2026-05-04 (4-agent confirmation): the wizard's
/// model picker uses this when `selectedRecipe?.channelProviderCompat
/// ['inapp']?.supported.first` ≠ 'openrouter' so users only see
/// candidates the recipe can actually deploy with. `keepAlive: true`
/// keeps each per-provider catalog cached after the picker closes.
final recipeModelsProvider = FutureProvider.family<List<OpenRouterModel>, String>(
  (Ref ref, String provider) async {
    final api = ref.watch(apiClientProvider);
    // 'openrouter' is the unfiltered catalog — pass null so the server
    // hits the byte-passthrough hot path (no JSON re-serialize).
    final r = await api.models(
      provider: provider == 'openrouter' ? null : provider,
    );
    return switch (r) {
      Ok<List<OpenRouterModel>>(:final value) => value,
      // ignore: only_throw_errors
      Err<List<OpenRouterModel>>(:final error) => throw error,
    };
  },
);
