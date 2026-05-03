// Phase 25 Wave 3 plan 25-05 task 3 — Step 1: Clone picker (D-25).
//
// UI-SPEC ### Step 1 (lines 561-565):
// - Horizontal scrolling row of recipe cards from `recipesProvider`
//   (Phase 25 Plan 25-04 — already shipped).
// - Card: 200×160 white bg; idle 1px #DEDEDA border; selected 2px #1F1F1F
//   border; recipe name JetBrains Mono w600 body 16; 1-line description
//   below.
// - Below: 32px gap then `Next` button (full-width 48dp), disabled until
//   any card has been tapped.
//
// On card tap: fetch RecipeDetail (api.recipeDetail(name)) so downstream
// steps (BYOK label-swap D-32, Telegram dynamic fields D-54) have the
// channels.<id>.* metadata. Store in `wizardScopeProvider.selectedRecipe`
// so step 2 / 3 read from a single source of truth (Pitfall #10 Pattern A).
//
// Golden Rule #2: NO hardcoded recipe names. Every name comes from the
// API. The `_RecipeCard` widget receives a `Recipe` summary (name +
// description); the description may be null when the recipe yaml omits
// it.

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
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 24),
                itemCount: list.length,
                separatorBuilder: (_, _) => const SizedBox(width: 8),
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
    }
    // On Err the selection silently no-ops; the user retains their
    // prior state and can tap another card. Plan 25-06 will add inline
    // error UX if this becomes a UX problem.
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
        width: 200,
        height: 160,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: SolvrColors.card,
          border: Border.all(
            color: selected ? SolvrColors.foreground : SolvrColors.border,
            width: selected ? 2 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              recipe.name,
              style: SolvrTextStyles.mono(
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
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

/// 3 placeholder cards while `recipesProvider` is loading. Mirrors the
/// dashboard's SkeletonRow vocabulary in horizontal layout. Uses a
/// horizontal ListView so the loading state is scrollable just like the
/// data state — three 200px cards exceed the typical 342px usable width
/// on phone-class screens.
class _LoadingCards extends StatelessWidget {
  const _LoadingCards();

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      itemCount: 3,
      separatorBuilder: (_, _) => const SizedBox(width: 8),
      itemBuilder: (_, _) => const SizedBox(
        width: 200,
        height: 160,
        child: SkeletonRow(),
      ),
    );
  }
}
