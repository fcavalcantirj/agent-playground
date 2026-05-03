// Phase 25 Wave 1 D-17 + UI-SPEC §Component 2.
//
// Centered empty-state body with optional banner widget + heading + body
// + primary action button. Spacing per UI-SPEC line 294:
// 32 px → banner → 32 px → heading → 16 px → body → 32 px → primary action.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class EmptyStatePrimaryAction {
  const EmptyStatePrimaryAction({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;
}

class EmptyStateScaffold extends StatelessWidget {
  const EmptyStateScaffold({
    required this.heading,
    this.banner,
    this.body,
    this.primaryAction,
    super.key,
  });

  final String heading;
  final Widget? banner;
  final String? body;
  final EmptyStatePrimaryAction? primaryAction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final children = <Widget>[];

    if (banner != null) {
      children
        ..add(banner!)
        ..add(const SizedBox(height: 32));
    }

    children.add(
      Text(
        heading,
        textAlign: TextAlign.center,
        style: theme.textTheme.headlineSmall?.copyWith(
          fontSize: 28,
          fontWeight: FontWeight.w600,
          color: SolvrColors.foreground,
        ),
      ),
    );

    if (body != null) {
      children
        ..add(const SizedBox(height: 16))
        ..add(
          Text(
            body!,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyLarge?.copyWith(
              fontSize: 16,
              color: SolvrColors.mutedForeground,
            ),
          ),
        );
    }

    if (primaryAction != null) {
      children
        ..add(const SizedBox(height: 32))
        ..add(
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton(
              onPressed: primaryAction!.onTap,
              style: ElevatedButton.styleFrom(
                backgroundColor: SolvrColors.foreground,
                foregroundColor: SolvrColors.background,
                shape: const RoundedRectangleBorder(),
                textStyle: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              child: Text(primaryAction!.label),
            ),
          ),
        );
    }

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: children,
        ),
      ),
    );
  }
}
