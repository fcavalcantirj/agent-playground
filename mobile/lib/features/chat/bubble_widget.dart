// Phase 25 Wave 4 plan 25-07 task 2 — D-35 + D-43 + D-46 + D-48.
//
// User and Assistant chat bubbles.
//
//   UserBubble       — right-aligned, bg #1F1F1F (foreground), fg #FAFAF7
//                      (background), corner radius 0, 16/12 padding,
//                      max-width 80% of viewport, SelectableText.
//   AssistantBubble  — left-aligned, bg #EFEFEC (muted), fg #1F1F1F
//                      (foreground), corner radius 0, markdown rendering
//                      via `flutter_markdown_plus` (AMD-03 — supersedes
//                      discontinued `flutter_markdown`). Code blocks
//                      render in JetBrains Mono per D-43; image rendering
//                      is stripped (D-43 security guard).
//
// Markdown link tap (D-46): `_onTapLink` parses `href`, lower-cases the
// scheme, and ONLY allows `https` / `http` through `url_launcher`. Any
// other scheme (`javascript:`, `data:`, `file:`, `mailto:`, custom URI
// schemes) is silently dropped. Pitfall #2 honored — mode is
// `LaunchMode.externalApplication`.
//
// Long-press (D-48): both bubbles open a bottom sheet with two ListTile
// entries — "Copy" and "Select text". Sheet shape is the Solvr default
// (no rounded corners). Callbacks are passed in by the parent.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart' as ul;

/// Test seam: production wraps `url_launcher.launchUrl(uri, mode:
/// LaunchMode.externalApplication)`. Tests overwrite to capture the
/// would-be-launched URI without touching the real platform channel.
typedef ExternalLauncher = Future<bool> Function(Uri uri);

Future<bool> _defaultLauncher(Uri uri) =>
    ul.launchUrl(uri, mode: ul.LaunchMode.externalApplication);

ExternalLauncher externalLauncher = _defaultLauncher;

/// Reset the launcher to the production default. Tests call this from
/// `addTearDown` to keep state hermetic.
void resetExternalLauncher() {
  externalLauncher = _defaultLauncher;
}

/// D-46 link-tap policy. Returns `true` if the link was launched, `false`
/// if dropped by the allow-list or `launchUrl` returned false. Exposed
/// for direct testing without spinning up a widget tree.
Future<bool> handleLinkTap(String? href) async {
  if (href == null) return false;
  final uri = Uri.tryParse(href);
  if (uri == null) return false;
  final scheme = uri.scheme.toLowerCase();
  // D-46 allow-list: scheme != 'https' && scheme != 'http' -> drop.
  if (scheme != 'https' && scheme != 'http') return false;
  return externalLauncher(uri);
}

/// D-48 long-press bottom sheet — Copy + Select text.
Future<void> showBubbleActionSheet(
  BuildContext context, {
  required VoidCallback onCopy,
  required VoidCallback onSelect,
}) {
  return showModalBottomSheet<void>(
    context: context,
    shape: const RoundedRectangleBorder(),
    backgroundColor: SolvrColors.background,
    builder: (sheetCtx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.copy, color: SolvrColors.foreground),
            title: const Text('Copy'),
            onTap: () {
              Navigator.of(sheetCtx).pop();
              onCopy();
            },
          ),
          ListTile(
            leading:
                const Icon(Icons.text_fields, color: SolvrColors.foreground),
            title: const Text('Select text'),
            onTap: () {
              Navigator.of(sheetCtx).pop();
              onSelect();
            },
          ),
        ],
      ),
    ),
  );
}

/// D-35 — right-aligned, black bg, white fg, radius 0.
///
/// Uses non-selectable [Text] by default so the bubble-level long-press
/// gesture fires the D-48 action sheet instead of the OS native selection
/// menu. The "Select text" entry in the sheet is the path users take when
/// they want partial selection (parent wires that callback by re-rendering
/// the bubble with `selectable: true` if needed in a future iteration).
class UserBubble extends StatelessWidget {
  const UserBubble({
    required this.content,
    this.onCopy,
    this.onSelect,
    super.key,
  });

  final String content;
  final VoidCallback? onCopy;
  final VoidCallback? onSelect;

  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.centerRight,
        child: GestureDetector(
          onLongPress: () => showBubbleActionSheet(
            context,
            onCopy: () => onCopy?.call(),
            onSelect: () => onSelect?.call(),
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.8,
            ),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: const BoxDecoration(color: SolvrColors.foreground),
              child: Text(
                content,
                style: const TextStyle(
                  fontSize: 16,
                  color: SolvrColors.background,
                  height: 1.5,
                ),
              ),
            ),
          ),
        ),
      );
}

/// D-35 + D-43 — left-aligned, light grey bg, black fg, radius 0; markdown
/// rendered via `flutter_markdown_plus` with JetBrains Mono code blocks
/// + image rendering stripped per D-43.
class AssistantBubble extends StatelessWidget {
  const AssistantBubble({
    required this.content,
    this.onCopy,
    this.onSelect,
    super.key,
  });

  final String content;
  final VoidCallback? onCopy;
  final VoidCallback? onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final styleSheet = MarkdownStyleSheet.fromTheme(theme).copyWith(
      // D-43 — code blocks render in JetBrains Mono.
      code: GoogleFonts.jetBrainsMono(
        fontSize: 12,
        color: SolvrColors.foreground,
        backgroundColor: SolvrColors.card,
      ),
      codeblockDecoration: const BoxDecoration(
        color: SolvrColors.card,
        border: Border.fromBorderSide(
          BorderSide(color: SolvrColors.border),
        ),
      ),
      codeblockPadding: const EdgeInsets.all(8),
      p: const TextStyle(
        fontSize: 16,
        color: SolvrColors.foreground,
        height: 1.5,
      ),
    );

    return Align(
      alignment: Alignment.centerLeft,
      child: GestureDetector(
        onLongPress: () => showBubbleActionSheet(
          context,
          onCopy: () => onCopy?.call(),
          onSelect: () => onSelect?.call(),
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.8,
          ),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: const BoxDecoration(color: SolvrColors.muted),
            child: MarkdownBody(
              data: content,
              // selectable=false so the bubble-level long-press fires the
              // D-48 action sheet rather than the OS native selection menu.
              // "Select text" in the sheet drives the parent to re-render
              // with selection mode in a future iteration.
              onTapLink: (text, href, title) {
                // ignore: discarded_futures
                handleLinkTap(href);
              },
              // D-43 — image rendering stripped.
              imageBuilder: (uri, title, alt) => const SizedBox.shrink(),
              styleSheet: styleSheet,
            ),
          ),
        ),
      ),
    );
  }
}
