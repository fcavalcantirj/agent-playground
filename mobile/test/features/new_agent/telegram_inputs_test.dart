// Phase 25 Wave 3 plan 25-06 task 1 — Golden Rule #2 enforcement (D-54).
//
// File-content negation: channel_inputs.dart MUST NOT contain hardcoded
// Telegram field labels as string literals. Labels come from server
// metadata (recipe.channels.telegram.required_user_input[i].env).
//
// This test exists because a "small refactor" can silently re-introduce
// a hardcoded "Bot Token" label in the future, sliding the dumb-client
// back into a catalog. The test is intentionally rigid.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('channel_inputs.dart has no hardcoded Telegram field labels',
      () async {
    // Try `lib/...` (test runs from `mobile/`) and the absolute path as
    // a fallback for IDE runners that set a different cwd.
    final relative =
        File('lib/features/new_agent/channel_inputs.dart');
    final raw = await (relative.existsSync()
            ? relative
            : File('mobile/lib/features/new_agent/channel_inputs.dart'))
        .readAsString();

    // Strip `//`-style comments line-by-line — comments may legitimately
    // mention forbidden tokens (e.g. "NEVER hardcode 'Bot Token' here")
    // without that being a Golden Rule #2 violation. The negation only
    // cares about NON-comment string literals in the rendered code.
    final src = raw
        .split('\n')
        .map((line) {
          final idx = line.indexOf('//');
          return idx < 0 ? line : line.substring(0, idx);
        })
        .join('\n');

    // String literals (single + double quoted) for any of these labels
    // would be a Golden Rule #2 violation — labels MUST come from data.
    const forbidden = <String>[
      '"Bot Token"',
      "'Bot Token'",
      '"User ID"',
      "'User ID'",
      '"TELEGRAM_BOT_TOKEN"',
      "'TELEGRAM_BOT_TOKEN'",
      '"TELEGRAM_ALLOWED_USER"',
      "'TELEGRAM_ALLOWED_USER'",
      '"TELEGRAM_ALLOWED_USERS"',
      "'TELEGRAM_ALLOWED_USERS'",
    ];
    for (final f in forbidden) {
      expect(
        src.contains(f),
        isFalse,
        reason: 'forbidden label literal "$f" found in channel_inputs.dart '
            '(Golden Rule #2 — labels must come from recipe metadata)',
      );
    }
  });
}
