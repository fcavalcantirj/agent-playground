// Phase 25 Wave 3 plan 25-05 task 3 — Step 2.5: Model picker (D-26).
//
// UI-SPEC ### Step 2.5 (lines 574-580):
// - Full-screen scaffold pushed over step 2 — uses MaterialPageRoute (NOT
//   go_router push) so a `Navigator.pop(picked)` returns the OpenRouterModel
//   to the awaiting `context.push<OpenRouterModel>()` in ModelStep.
// - AppBar with ← back + title 'Pick a model'.
// - Top: TextField with Icons.search + 'Search models…' placeholder.
// - Body: ListView.builder (virtualized — catalog has 300+ entries).
// - Empty filter result → centered 'No models match "<query>"' caption.
// - Tap row → Navigator.pop(model).

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class ModelPickerScreen extends ConsumerStatefulWidget {
  const ModelPickerScreen({super.key});

  @override
  ConsumerState<ModelPickerScreen> createState() =>
      _ModelPickerScreenState();
}

class _ModelPickerScreenState extends ConsumerState<ModelPickerScreen> {
  final _searchCtl = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final modelsAsync = ref.watch(modelsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Pick a model')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _searchCtl,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search models…',
              ),
              onChanged: (v) => setState(() => _query = v.toLowerCase()),
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: modelsAsync.when(
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    "Couldn't load models",
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              ),
              data: (list) => _buildList(context, list),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildList(BuildContext context, List<OpenRouterModel> list) {
    // Pin the recipe's smoke-verified models to the top so the user
    // lands on a known-working combo first. Reorder happens BEFORE
    // the search filter so verified rows stay pinned even when the
    // user types. Empty `verifiedModels` (recipe never smoke-tested
    // any model) → no reorder, picker is identical to before.
    final verified = ref
            .watch(wizardScopeProvider)
            .selectedRecipe
            ?.verifiedModels ??
        const <String>[];
    final reordered = _reorder(list, verified);
    final verifiedSet = verified.toSet();

    final filtered = _query.isEmpty
        ? reordered
        : reordered
            .where(
              (m) =>
                  m.id.toLowerCase().contains(_query) ||
                  m.name.toLowerCase().contains(_query),
            )
            .toList(growable: false);
    if (filtered.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'No models match "${_searchCtl.text}"',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: SolvrColors.mutedForeground,
                ),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return ListView.builder(
      itemCount: filtered.length,
      itemBuilder: (ctx, i) => _ModelRow(
        model: filtered[i],
        verified: verifiedSet.contains(filtered[i].id),
        onTap: () => Navigator.of(context).pop(filtered[i]),
      ),
    );
  }

  /// Pin verified ids in declared order at the top, preserve server
  /// order for the rest. Verified ids not present in `all` (deprecated
  /// or removed from /v1/models) are silently skipped — no placeholder
  /// row, no error toast.
  static List<OpenRouterModel> _reorder(
    List<OpenRouterModel> all,
    List<String> verified,
  ) {
    if (verified.isEmpty) return all;
    final byId = {for (final m in all) m.id: m};
    final pinned = <OpenRouterModel>[
      for (final id in verified)
        if (byId.containsKey(id)) byId[id]!,
    ];
    final pinnedIds = pinned.map((m) => m.id).toSet();
    final rest = all.where((m) => !pinnedIds.contains(m.id));
    return [...pinned, ...rest];
  }
}

class _ModelRow extends StatelessWidget {
  const _ModelRow({
    required this.model,
    required this.onTap,
    this.verified = false,
  });

  final OpenRouterModel model;
  final VoidCallback onTap;

  /// True when this model's id appears in the selected recipe's
  /// `verifiedModels` list. Surfaces a small `✓ verified` chip on
  /// the right edge of the row.
  final bool verified;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    model.id,
                    style: SolvrTextStyles.mono(fontSize: 12),
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (model.name != model.id) ...[
                    const SizedBox(height: 2),
                    Text(
                      model.name,
                      style: Theme.of(context).textTheme.bodyMedium,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
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
                  color: SolvrColors.muted,
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
                      'verified',
                      style: SolvrTextStyles.mono(fontSize: 10).copyWith(
                        color: SolvrColors.mutedForeground,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
