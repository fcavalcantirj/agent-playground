// Phase 25 Wave 3 plan 25-06 task 1 — D-50 / D-58.
//
// Cross-feature Riverpod state used by Wave 3 DeployStep (writer) +
// Wave 4 ChatScreen (reader). When a multi-channel deploy succeeds at
// inapp but fails at telegram (D-58), DeployStep stores the fail-reason
// + entered telegramInputs here, then routes to /chat/<id> — Wave 4 Chat
// reads this and renders the sticky failed-banner per D-50, with Retry
// re-firing /v1/agents/<id>/start (channel='telegram') using the cached
// inputs.
//
// Held in MEMORY ONLY per D-50 — bot tokens are per-deploy and MUST NOT
// land in flutter_secure_storage. Banner clears when:
//   - User × dismisses the banner (Wave 4 Chat sets state = null).
//   - Retry succeeds (Wave 4 Chat sets state = null).
//   - User signs out (provider cleared via Riverpod container teardown).

import 'package:flutter_riverpod/legacy.dart';

class TelegramFailedBannerState {
  const TelegramFailedBannerState({
    required this.agentInstanceId,
    required this.reason,
    required this.telegramInputs,
  });

  /// The agent the banner belongs to (Wave 4 Chat scopes by `agentId`).
  final String agentInstanceId;

  /// `ApiError.message` from the telegram /start failure.
  final String reason;

  /// Cached `channel_inputs` map keyed by env-var name. Used by Retry to
  /// re-fire /start without forcing the user to re-enter the bot token.
  final Map<String, String> telegramInputs;
}

/// Memory-only state (D-50). Single-active-banner — at most one
/// telegram-failed deploy can be in-flight at a time per user.
final StateProvider<TelegramFailedBannerState?> telegramFailedBannerProvider =
    StateProvider<TelegramFailedBannerState?>((_) => null);
