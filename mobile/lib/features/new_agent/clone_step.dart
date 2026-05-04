// Phase 25 Wave 3 plan 25-05 task 3 — Step 1: Clone picker (D-25).
//
// UX rev 2026-05-04: switched from horizontal-scroll list to 2-column
// vertical grid. The horizontal layout stretched cards full-height
// (Expanded > horizontal ListView passes infinite height; the inner
// Container's height:160 wasn't honored). Grid is more scannable,
// shows multiple recipes without scrolling, and matches the recipe-
// emoji-prefixed dashboard rows visually. Each card:
//   - leading emoji (per-recipe, recipe-author controlled, falls back
//     to no glyph if recipe declares none)
//   - recipe name (mono w600 16)
//   - 3-4 line description, ellipsized
//   - border 2px in both states (color-only state change). A 1↔2px
//     border swap reflowed the description by 2px of inner width —
//     picoclaw/zeroclaw wrap points sat at the column edge.
//
// On card tap: fetch RecipeDetail (api.recipeDetail(name)) so
// downstream steps (BYOK label-swap D-32, Telegram dynamic fields
// D-54) have the channels.<id>.* metadata. Store in
// `wizardScopeProvider.selectedRecipe` so step 2 / 3 read from a
// single source of truth (Pitfall #10 Pattern A).
//
// Golden Rule #2: NO hardcoded recipe names. Every name comes from
// the API. The `_RecipeCard` widget receives a `Recipe` summary
// (name + description + emoji); description/emoji may be null when
// the recipe yaml omits them.

import 'dart:async';

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/dashboard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_shell.dart';
import 'package:agent_playground/shared/skeleton_row.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class CloneStep extends ConsumerWidget {
  const CloneStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recipes = ref.watch(recipesProvider);
    final scope = ref.watch(wizardScopeProvider);

    return WizardShell(
      title: 'Pick a clone',
      currentStep: 0,
      canGoBack: false,
      body: recipes.when(
        loading: () => const _LoadingCards(),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              "Couldn't load clones",
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ),
        data: (list) => Column(
          children: [
            Expanded(
              child: GridView.builder(
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 8,
                ),
                gridDelegate:
                    const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  mainAxisSpacing: 12,
                  crossAxisSpacing: 12,
                  mainAxisExtent: 160,
                ),
                itemCount: list.length,
                itemBuilder: (ctx, i) {
                  final r = list[i];
                  final isSelected = scope.selectedRecipe?.name == r.name;
                  return _RecipeCard(
                    recipe: r,
                    selected: isSelected,
                    onTap: () => _onSelect(ref, r.name),
                  );
                },
              ),
            ),
            const SizedBox(height: 32),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: scope.selectedRecipe == null
                      ? null
                      : () => context.push('/new-agent/model'),
                  child: const Text('Next'),
                ),
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Future<void> _onSelect(WidgetRef ref, String name) async {
    // Upgrade summary → detail so the wizard's downstream steps have
    // channels.<id>.* metadata. The api wraps DioException in Result.err
    // so this never throws.
    final detailRes =
        await ref.read(apiClientProvider).recipeDetail(name: name);
    if (detailRes case Ok(:final value)) {
      ref.read(wizardScopeProvider.notifier).setSelectedRecipe(value);
      // Fire-and-forget: pre-select the recipe's first verified model
      // so step 2 lands on a known-working pairing without forcing the
      // user through the full-screen picker. User can override via the
      // "Change" button. See _maybePreselectFirstVerified for guards.
      unawaited(_maybePreselectFirstVerified(ref, value));
    }
    // On Err the selection silently no-ops; the user retains their
    // prior state and can tap another card. Plan 25-06 will add inline
    // error UX if this becomes a UX problem.
  }

  /// Pre-select the recipe author's canonical model so the user lands
  /// on a known-working pairing without opening the picker. Silent
  /// no-op on any failure (empty verified list, model deprecated from
  /// catalog, catalog fetch error). recipeModelsProvider is keepAlive
  /// so the picker that opens later reuses the same future.
  Future<void> _maybePreselectFirstVerified(
    WidgetRef ref,
    RecipeDetail r,
  ) async {
    if (r.verifiedModels.isEmpty) return;
    final firstId = r.verifiedModels.first;
    final primaryProvider =
        r.channelProviderCompat['inapp']?.supported.firstOrNull ??
            'openrouter';
    try {
      final catalog =
          await ref.read(recipeModelsProvider(primaryProvider).future);
      final match = catalog.where((m) => m.id == firstId).firstOrNull;
      if (match == null) return;
      ref.read(wizardScopeProvider.notifier).setSelectedModel(match);
    } on Object catch (_) {
      // Catalog unavailable (ApiError or otherwise) — silent no-op so
      // the wizard still works in degraded mode; user picks manually.
    }
  }
}

class _RecipeCard extends StatelessWidget {
  const _RecipeCard({
    required this.recipe,
    required this.selected,
    required this.onTap,
  });

  final Recipe recipe;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: SolvrColors.card,
          border: Border.all(
            color: selected ? SolvrColors.foreground : SolvrColors.border,
            // Constant 2px in both states. `Border.all` insets the child by
            // `width` on every side, so a 1↔2 swap on selection reflowed
            // the description text by 2px of inner width — visible on
            // picoclaw/zeroclaw whose wrap point sat at the column edge.
            // Emphasis is now carried entirely by color contrast.
            width: 2,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (recipe.emoji != null) ...[
                  Text(
                    recipe.emoji!,
                    style: const TextStyle(fontSize: 18),
                  ),
                  const SizedBox(width: 6),
                ],
                Expanded(
                  child: Text(
                    recipe.name,
                    style: SolvrTextStyles.mono(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Text(
                recipe.description ?? '',
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: SolvrColors.mutedForeground,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 4 placeholder tiles while `recipesProvider` is loading. Matches the
/// 2-column grid the data state uses so the layout doesn't reflow when
/// recipes arrive.
class _LoadingCards extends StatelessWidget {
  const _LoadingCards();

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        mainAxisExtent: 160,
      ),
      itemCount: 4,
      itemBuilder: (_, _) => const SkeletonRow(),
    );
  }
}
