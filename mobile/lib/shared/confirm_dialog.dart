// Phase 25 Wave 1 D-07 + D-28 + D-31 + UI-SPEC §Component 9.
//
// Single shape for all destructive confirmations. Wraps Material
// AlertDialog. barrierDismissible: false (tap-outside does NOT cancel;
// back-button = Cancel). Confirm button text uses destructive red when
// destructive=true. Optional thirdButtonLabel supports the D-28 "Rename"
// path on the wizard name-collision dialog.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

enum ConfirmDialogResult { cancel, confirm, third }

abstract final class ConfirmDialog {
  ConfirmDialog._();

  static Future<ConfirmDialogResult> show(
    BuildContext context, {
    required String title,
    required String confirmLabel,
    String? body,
    String cancelLabel = 'Cancel',
    bool destructive = true,
    String? thirdButtonLabel,
  }) async {
    final result = await showDialog<ConfirmDialogResult>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        shape: const RoundedRectangleBorder(),
        title: Text(
          title,
          style: Theme.of(ctx).textTheme.titleMedium?.copyWith(
                fontSize: 20,
                fontWeight: FontWeight.w600,
                color: SolvrColors.foreground,
              ),
        ),
        content: body == null
            ? null
            : Text(
                body,
                style: const TextStyle(
                  fontSize: 16,
                  color: SolvrColors.mutedForeground,
                  height: 1.5,
                ),
              ),
        actions: [
          TextButton(
            onPressed: () =>
                Navigator.of(ctx).pop(ConfirmDialogResult.cancel),
            style: TextButton.styleFrom(
              foregroundColor: SolvrColors.foreground,
            ),
            child: Text(cancelLabel),
          ),
          if (thirdButtonLabel != null)
            TextButton(
              onPressed: () =>
                  Navigator.of(ctx).pop(ConfirmDialogResult.third),
              style: TextButton.styleFrom(
                foregroundColor: SolvrColors.foreground,
              ),
              child: Text(thirdButtonLabel),
            ),
          TextButton(
            onPressed: () =>
                Navigator.of(ctx).pop(ConfirmDialogResult.confirm),
            style: TextButton.styleFrom(
              foregroundColor: destructive
                  ? SolvrColors.destructive
                  : SolvrColors.foreground,
            ),
            child: Text(confirmLabel),
          ),
        ],
      ),
    );
    return result ?? ConfirmDialogResult.cancel;
  }
}
