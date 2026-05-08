// Phase 31 H4 (D-05, D-09) — chat-stream error banner state.
//
// Memory-only StateProvider mirroring Phase 25 D-50
// `telegram_failed_banner_provider.dart`. Single-active per chat;
// cleared on retry-success / dismiss / sign-out / Riverpod teardown.
import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:flutter_riverpod/legacy.dart';

class ChatStreamErrorState {
  const ChatStreamErrorState({
    required this.agentInstanceId,
    required this.errorClass,
    required this.lastFailedAction,
  });

  /// The chat thread that produced the error (lets the banner refuse to
  /// render if the user has navigated to a different agent's chat).
  final String agentInstanceId;

  /// One of three user-facing classes. See `chat_stream_error_classifier.dart`.
  final ChatStreamErrorClass errorClass;

  /// 'connect' for the initial-mount path, 'reconnect_on_resume' for
  /// the foreground-resume path. Drives retry-CTA dispatch.
  final String lastFailedAction;
}

final StateProvider<ChatStreamErrorState?> chatStreamErrorProvider =
    StateProvider<ChatStreamErrorState?>((_) => null);
