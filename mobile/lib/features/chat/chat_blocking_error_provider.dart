// Phase B Plan 12 Task 2 (D-21) — chat blocking-error signal.
//
// Surfaces 402 INSUFFICIENT_BALANCE from the chat send / retry path so
// chat_screen.dart can `ref.listen(...)` and dispatch
// `showInsufficientCreditsModal(context)` when the value flips. The
// modal owns the user-facing UX; the provider is purely the bridge
// between the headless ChatScope notifier and the widget tree (which
// owns the BuildContext required by showDialog).
//
// EXPLICITLY NOT a RetryBanner / chatStreamErrorProvider — those
// classify Phase 31 H4 transient SSE/HTTP errors. The 402 path is a
// blocking paywall surface (D-21).
//
// Lifecycle:
//   * `null`                     — idle (no blocking error pending).
//   * `insufficientCredits`      — chat layer wants the modal shown.
//   * the chat-screen listener flips it back to `null` after the modal
//     is presented (so a future 402 re-arms the trigger; without the
//     reset Riverpod's listener would not fire on a same-value update).
//
// Memory-only StateProvider mirroring `telegram_failed_banner_provider.dart`.
import 'package:flutter_riverpod/legacy.dart';

/// Discriminator for the modal-owning blocking-error surfaces. Today
/// only one shape (insufficient credits / 402); future 4xx surfaces
/// that warrant a blocking modal extend this enum (e.g. an explicit
/// `tierLimitReached` if D-05 entitlement gates ever surface in chat).
enum ChatBlockingError {
  /// 402 INSUFFICIENT_BALANCE on `POST /v1/agents/:id/messages` —
  /// route to `showInsufficientCreditsModal(context)` per D-21.
  insufficientCredits,
}

final StateProvider<ChatBlockingError?> chatBlockingErrorProvider =
    StateProvider<ChatBlockingError?>((_) => null);
