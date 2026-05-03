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
    final filtered = _query.isEmpty
        ? list
        : list
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
        onTap: () => Navigator.of(context).pop(filtered[i]),
      ),
    );
  }
}

class _ModelRow extends StatelessWidget {
  const _ModelRow({required this.model, required this.onTap});

  final OpenRouterModel model;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
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
    );
  }
}
