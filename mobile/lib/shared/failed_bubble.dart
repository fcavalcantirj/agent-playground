// Phase 25 Wave 1 D-44 + UI-SPEC §Component 7.
//
// Distinct failed-message bubble. 2 px destructive red border + ⚠ glyph
// prefix + content text. Tap → bottom sheet with Retry + Copy error
// (per D-44). Role aligns left (assistant) or right (user) per D-35.
// Sheet uses scaffold theme, no rounded corners.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class FailedBubble extends StatelessWidget {
  const FailedBubble({
    required this.role,
    required this.content,
    required this.onRetry,
    required this.onCopyError,
    super.key,
  });

  /// 'user' or 'assistant'. Anything else aligns left like assistant.
  final String role;
  final String content;
  final VoidCallback onRetry;
  final VoidCallback onCopyError;

  bool get _isUser => role == 'user';

  Future<void> _showActionSheet(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      shape: const RoundedRectangleBorder(),
      backgroundColor: SolvrColors.background,
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(
                Icons.refresh,
                color: SolvrColors.foreground,
              ),
              title: const Text('Retry'),
              onTap: () {
                Navigator.of(sheetCtx).pop();
                onRetry();
              },
            ),
            ListTile(
              leading: const Icon(
                Icons.copy_outlined,
                color: SolvrColors.foreground,
              ),
              title: const Text('Copy error'),
              onTap: () {
                Navigator.of(sheetCtx).pop();
                onCopyError();
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bubble = GestureDetector(
      onTap: () => _showActionSheet(context),
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.8,
        ),
        decoration: BoxDecoration(
          color: SolvrColors.muted,
          border: Border.all(color: SolvrColors.destructive, width: 2),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.warning_rounded,
              size: 16,
              color: SolvrColors.destructive,
            ),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                content,
                style: const TextStyle(
                  fontSize: 16,
                  color: SolvrColors.foreground,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );

    return Align(
      alignment: _isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: bubble,
    );
  }
}
