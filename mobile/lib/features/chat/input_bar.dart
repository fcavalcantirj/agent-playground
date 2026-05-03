// Phase 25 Wave 4 plan 25-07 task 2 — D-40 + D-51.
//
// Multi-line expanding TextField + Send button with three states.
//
//   - Empty / whitespace-only text  -> Send button DISABLED (D-51)
//   - Text + not in-flight         -> Send button ENABLED, tap fires onSend
//   - inflight=true                -> Send button shows CircularProgressIndicator;
//                                     tap fires onCancel (D-51 cancel-on-spinner-tap)
//
// `maxLines: 5` per D-40 — internal scroll once exceeded. `minLines: 1`
// keeps the bar tight on first render. `textInputAction:
// TextInputAction.newline` per D-40 — Enter inserts a newline, NOT
// commit, so hardware keyboard users don't accidentally send half-typed
// messages. Send is the only commit affordance.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';

class ChatInputBar extends StatefulWidget {
  const ChatInputBar({
    required this.onSend,
    required this.onCancel,
    this.inflight = false,
    this.enabled = true,
    super.key,
  });

  /// Tapped when text is non-empty and `inflight` is false.
  final void Function(String content) onSend;

  /// Tapped when `inflight` is true (Send button shows spinner).
  final VoidCallback onCancel;

  /// Whether a POST is in flight; drives the spinner state (D-51).
  final bool inflight;

  /// Disables the entire input row when the agent is stopped (D-49 — the
  /// RestartBanner is rendered above the input by the parent screen).
  final bool enabled;

  @override
  State<ChatInputBar> createState() => _ChatInputBarState();
}

class _ChatInputBarState extends State<ChatInputBar> {
  final TextEditingController _ctl = TextEditingController();
  String _text = '';

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  void _onSendPressed() {
    final content = _ctl.text;
    if (content.trim().isEmpty) return;
    widget.onSend(content);
    _ctl.clear();
    setState(() => _text = '');
  }

  @override
  Widget build(BuildContext context) {
    final canSend =
        widget.enabled && _text.trim().isNotEmpty && !widget.inflight;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                key: const Key('chat-input-field'),
                controller: _ctl,
                enabled: widget.enabled,
                // D-40 — internal scroll after ~5 lines.
                maxLines: 5,
                minLines: 1,
                // D-40 — Enter inserts a newline; Send is the only commit.
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  hintText: widget.enabled
                      ? 'Type a message...'
                      : 'Restart agent to send messages',
                  hintStyle: const TextStyle(
                    color: SolvrColors.mutedForeground,
                  ),
                ),
                onChanged: (v) => setState(() => _text = v),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 48,
              height: 48,
              child: widget.inflight
                  ? IconButton(
                      key: const Key('chat-send-spinner'),
                      icon: const Padding(
                        padding: EdgeInsets.all(8),
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: SolvrColors.foreground,
                        ),
                      ),
                      tooltip: 'Cancel',
                      onPressed: widget.onCancel,
                    )
                  : IconButton(
                      key: const Key('chat-send-button'),
                      icon: const Icon(Icons.send),
                      color: SolvrColors.foreground,
                      tooltip: 'Send',
                      onPressed: canSend ? _onSendPressed : null,
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
