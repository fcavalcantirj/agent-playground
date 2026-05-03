// Phase 25 Wave 3 plan 25-06 task 1 — D-54 dynamic Telegram-input fields.
//
// Mirror of frontend/components/playground-form.tsx lines 638-689 — the
// canonical web playground render loop. Labels = recipe.channels.<id>.
// required_user_input[i].env verbatim. NEVER hardcode "Bot Token" /
// "User ID" / "TELEGRAM_BOT_TOKEN" — that turns the dumb-client into a
// catalog of channel fields, violating Golden Rule #2.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

class ChannelInputs extends ConsumerWidget {
  const ChannelInputs({required this.channelMeta, super.key});

  final RecipeChannelMeta channelMeta;

  /// D-46 https/http allow-list — `mailto:`, `javascript:`, custom URI
  /// schemes are stripped at the launcher boundary.
  Future<void> _openExternal(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final scheme = uri.scheme.toLowerCase();
    if (scheme != 'https' && scheme != 'http') return;
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inputs = channelMeta.allInputs;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final input in inputs)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Label = the `env` value verbatim (Golden Rule #2).
                Text(
                  input.env,
                  style: SolvrTextStyles.mono(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  key: ValueKey('channel_input_${input.env}'),
                  obscureText: input.secret,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: InputDecoration(
                    hintText: input.secret ? '••••••••' : '...',
                  ),
                  onChanged: (v) => ref
                      .read(wizardScopeProvider.notifier)
                      .setTelegramInput(input.env, v),
                ),
                if (input.hint != null && input.hint!.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: _HintCaption(
                      hint: input.hint!,
                      hintUrl: input.hintUrl,
                      onOpen: _openExternal,
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _HintCaption extends StatelessWidget {
  const _HintCaption({
    required this.hint,
    required this.onOpen,
    this.hintUrl,
  });

  final String hint;
  final String? hintUrl;
  final Future<void> Function(String) onOpen;

  @override
  Widget build(BuildContext context) {
    final captionStyle = Theme.of(context).textTheme.bodySmall?.copyWith(
          color: SolvrColors.mutedForeground,
        );
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(hint, style: captionStyle),
        if (hintUrl != null && hintUrl!.isNotEmpty)
          TextButton(
            onPressed: () => onOpen(hintUrl!),
            child: const Text('get one here'),
          ),
      ],
    );
  }
}
