// Phase 25 Wave 1 D-19 + D-50 base + UI-SPEC §Component 4.
//
// Inline retry banner. tone=muted is the default Dashboard fetch-error
// banner; tone=warning prefixes a ⚠ glyph and is reused by D-50 for the
// Telegram-deploy-failed banner. Background stays #EFEFEC for both tones —
// red as a banner background is forbidden per UI-SPEC line 160-161.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

enum RetryBannerTone { muted, warning }

class RetryBanner extends StatelessWidget {
  const RetryBanner({
    required this.message,
    required this.actionLabel,
    required this.onTap,
    this.dismissible = false,
    this.onDismiss,
    this.tone = RetryBannerTone.muted,
    super.key,
  });

  final String message;
  final String actionLabel;
  final VoidCallback onTap;
  final bool dismissible;
  final VoidCallback? onDismiss;
  final RetryBannerTone tone;

  @override
  Widget build(BuildContext context) {
    final isWarning = tone == RetryBannerTone.warning;
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 48),
      color: SolvrColors.muted,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          if (isWarning) ...[
            const Text(
              '\u26A0',
              style: TextStyle(
                fontSize: 16,
                color: SolvrColors.foreground,
              ),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                fontSize: 12,
                color: SolvrColors.foreground,
              ),
            ),
          ),
          TextButton(
            onPressed: onTap,
            style: TextButton.styleFrom(
              foregroundColor: SolvrColors.foreground,
              textStyle: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            child: Text(actionLabel),
          ),
          if (dismissible)
            IconButton(
              icon: const Icon(Icons.close, size: 20),
              color: SolvrColors.foreground,
              tooltip: 'Dismiss',
              onPressed: onDismiss,
            ),
        ],
      ),
    );
  }
}
