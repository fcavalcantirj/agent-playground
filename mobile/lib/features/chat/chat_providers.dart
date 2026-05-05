// Phase 25 Wave 4 plan 25-07 task 1 — Chat scope provider.
//
// Owns per-(agentInstanceId) Riverpod state for the Chat screen:
//   * MessagesStream (SSE, parallel-mounted with GET /messages per D-36)
//   * Map dedup of ChatRow keyed by stable string keys (D-36):
//       - SSE arrivals  -> 'sse:<seq>'
//       - history rows  -> 'hist:<role>:<created_at>'
//       - optimistic    -> 'pending:<idemKey>'  +  'typing:<idemKey>'
//   * Insertion order preserved for ListView render
//   * Optimistic insert + retry-with-NEW-uuid (D-41 + D-45)
//   * AppLifecycleState.resumed -> stream.disconnect()+connect() (D-52)
//   * Dispose hook: cancel CancelToken + close SSE subscription
//
// Wave 0 Spike B verdict (2026-05-03) — `spikes/flutter-sse-envelope-inspect.md`
// — overrode CONTEXT D-36's "dedup by inapp_message_id" wording. The SSE
// envelope on the wire is `{seq, kind, payload:{source, content, captured_at},
// correlation_id, ts}` with NO `inapp_message_id` field, so the dedup Map
// keys on `seq` for SSE rows. History rows carry `inapp_message_id`, but
// those are interaction-pair IDs (user + assistant share one id), so we
// key history rows by `(role, created_at)` instead. Cross-correlation
// between SSE and history is by content-equality on first-arrival; if a
// row is already present we DO NOT insert a duplicate.
//
// State invariants:
//   * `byId` and `orderedIds` are always in sync (every key in orderedIds
//     exists in byId; orderedIds has no duplicates).
//   * Optimistic placeholders use `pending:<idemKey>` (user) and
//     `typing:<idemKey>` (assistant typing indicator). They are removed
//     when the corresponding SSE event arrives (matched by content for
//     the user mirror; the assistant typing placeholder is removed when
//     ANY assistant SSE event with greater seq arrives after the post).
//   * `markFailed(idemKey)` flips the user `pending:<idemKey>` row's
//     status to 'failed' (rendered via FailedBubble). The placeholder
//     STAYS in history — D-44 says failed bubbles persist as durable
//     records.
//   * `retryFailed(failedKey, content)` generates a NEW Uuid().v4()
//     and appends a new pending pair below — the failed bubble is NOT
//     removed (D-45).

import 'dart:async';
import 'dart:convert';

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

/// Surface contract used by `ChatScope`. The real implementation is
/// `MessagesStream`; tests inject a fake via [ChatScope.streamBuilder].
abstract class ChatStream {
  Stream<SseEvent> get events;
  Future<void> connect();
  Future<void> disconnect();
  Future<void> dispose();
  String? get lastEventId;
}

class _RealChatStream implements ChatStream {
  _RealChatStream(this._inner);
  final MessagesStream _inner;
  @override
  Stream<SseEvent> get events => _inner.events;
  @override
  Future<void> connect() => _inner.connect();
  @override
  Future<void> disconnect() => _inner.disconnect();
  @override
  Future<void> dispose() => _inner.dispose();
  @override
  String? get lastEventId => _inner.lastEventId;
}

/// Domain row used by the Chat screen state. Wraps a `ChatMessage` with
/// the local statuses Phase 25 layers on top (`pending`, `typing`,
/// `delivered`, `failed`).
///
/// Status semantics:
///   * `delivered`  — the canonical "real message present" state.
///   * `pending`    — optimistic user bubble before POST /messages acks.
///   * `typing`     — assistant placeholder, replaced by an SSE event.
///   * `failed`     — POST failed; renders FailedBubble (D-44). Stays.
class ChatRow {
  const ChatRow({
    required this.id,
    required this.role,
    required this.content,
    required this.status,
    required this.createdAt,
    this.errorMessage,
  });

  factory ChatRow.fromHistory(ChatMessage m) => ChatRow(
        id: 'hist:${m.role}:${m.createdAt}',
        role: m.role,
        content: m.content,
        status: 'delivered',
        createdAt: m.createdAt,
      );

  /// Stable dedup key (one of the `<scheme>:...` forms documented above).
  final String id;
  final String role;
  final String content;
  final String status;
  final String createdAt;
  final String? errorMessage;

  ChatRow copyWith({
    String? content,
    String? status,
    String? errorMessage,
  }) =>
      ChatRow(
        id: id,
        role: role,
        content: content ?? this.content,
        status: status ?? this.status,
        createdAt: createdAt,
        errorMessage: errorMessage ?? this.errorMessage,
      );
}

/// Immutable state held by [ChatScope].
class ChatState {
  const ChatState({
    this.byId = const <String, ChatRow>{},
    this.orderedIds = const <String>[],
    this.hasOlderMessages = false,
    this.inflight = false,
  });

  final Map<String, ChatRow> byId;
  final List<String> orderedIds;
  final bool hasOlderMessages;
  final bool inflight;

  ChatState copyWith({
    Map<String, ChatRow>? byId,
    List<String>? orderedIds,
    bool? hasOlderMessages,
    bool? inflight,
  }) =>
      ChatState(
        byId: byId ?? this.byId,
        orderedIds: orderedIds ?? this.orderedIds,
        hasOlderMessages: hasOlderMessages ?? this.hasOlderMessages,
        inflight: inflight ?? this.inflight,
      );

  /// Insert a row if not present, else update status/content (D-36).
  /// Returns `this` unchanged when the upsert is a no-op (rare, but keeps
  /// the contract symmetric).
  ChatState upsertOne(ChatRow row) {
    if (byId.containsKey(row.id)) {
      // Map dedup — update fields per D-36 ("if id already present, update
      // status only"). Content + createdAt are immutable per id.
      final existing = byId[row.id]!;
      if (existing.status == row.status &&
          existing.errorMessage == row.errorMessage) {
        return this;
      }
      final next = Map<String, ChatRow>.of(byId);
      next[row.id] = existing.copyWith(
        status: row.status,
        errorMessage: row.errorMessage,
      );
      return copyWith(byId: next);
    }
    final next = Map<String, ChatRow>.of(byId)..[row.id] = row;
    final order = List<String>.of(orderedIds)..add(row.id);
    return copyWith(byId: next, orderedIds: order);
  }

  /// Bulk upsert — used by the history fetch (D-36 parallel-mount fold).
  /// Skips rows whose `(role, createdAt)` pair already collides with a
  /// non-history key (i.e. an SSE event that's already represented).
  ChatState upsertManyHistory(List<ChatMessage> messages) {
    var s = this;
    for (final m in messages) {
      // If a same-content row already exists (SSE arrived first), skip.
      final alreadyHasContent = s.byId.values.any((r) =>
          r.role == m.role &&
          r.content == m.content &&
          r.createdAt == m.createdAt);
      if (alreadyHasContent) continue;
      s = s.upsertOne(ChatRow.fromHistory(m));
    }
    return s;
  }

  /// D-41 — optimistic insert: append a 'user' pending bubble + an
  /// 'assistant' typing placeholder under the SAME idemKey scheme.
  ChatState insertOptimistic({
    required String idemKey,
    required String content,
    required DateTime now,
  }) {
    final user = ChatRow(
      id: 'pending:$idemKey',
      role: 'user',
      content: content,
      status: 'pending',
      createdAt: now.toUtc().toIso8601String(),
    );
    final typing = ChatRow(
      id: 'typing:$idemKey',
      role: 'assistant',
      content: '',
      status: 'typing',
      createdAt: now.toUtc().toIso8601String(),
    );
    return upsertOne(user).upsertOne(typing).copyWith(inflight: true);
  }

  /// D-44 — flip a pending row to 'failed'. Kept in history (D-45).
  ChatState markFailed({required String idemKey, required String error}) {
    final pendingId = 'pending:$idemKey';
    final typingId = 'typing:$idemKey';
    if (!byId.containsKey(pendingId)) return this;
    final next = Map<String, ChatRow>.of(byId);
    next[pendingId] = next[pendingId]!.copyWith(
      status: 'failed',
      errorMessage: error,
    );
    // Drop the typing placeholder — there will be no assistant reply.
    next.remove(typingId);
    final order = orderedIds.where((id) => id != typingId).toList();
    return copyWith(byId: next, orderedIds: order, inflight: false);
  }

  /// Mark a pending optimistic row as 'delivered' (POST acked, but the
  /// SSE user-mirror has not yet arrived). Subsequent SSE arrivals will
  /// upsert separate rows; the pending one remains visible until the
  /// chat is rebuilt — that's by design (D-41: same-content collision
  /// handled at upsertManyHistory and in the SSE merge below).
  ChatState markPendingDelivered({required String idemKey}) {
    final pendingId = 'pending:$idemKey';
    if (!byId.containsKey(pendingId)) return this;
    final next = Map<String, ChatRow>.of(byId);
    next[pendingId] = next[pendingId]!.copyWith(status: 'delivered');
    return copyWith(byId: next, inflight: false);
  }

  /// SSE arrival for an assistant message — replaces ANY 'typing:*'
  /// placeholder before inserting the new row (D-41 typing-replaces).
  /// Returns the state with typing placeholders cleared if the role is
  /// 'assistant' AND the new row's content is non-empty.
  ChatState clearTypingPlaceholders() {
    final keepIds =
        orderedIds.where((id) => !id.startsWith('typing:')).toList();
    if (keepIds.length == orderedIds.length) return this;
    final next = Map<String, ChatRow>.of(byId)
      ..removeWhere((k, _) => k.startsWith('typing:'));
    return copyWith(byId: next, orderedIds: keepIds, inflight: false);
  }
}

/// Family-scoped Chat state holder.
///
/// Riverpod 3.x AutoDisposeFamilyNotifier — reaches a fresh provider per
/// `agentInstanceId` so scrolling between chats spawns a new SSE stream
/// each time. `keepAlive: false` (the default for autoDispose) ensures
/// the SSE socket closes when the user pops the Chat route.
class ChatScope extends Notifier<ChatState> {
  ChatScope(this.agentInstanceId);

  /// The family arg surfaced as a regular constructor parameter — Riverpod
  /// 3.x family Notifiers don't expose an `arg` getter on the base class
  /// (codegen-only sugar), so we capture it here at construction.
  final String agentInstanceId;

  late ChatStream _stream;
  CancelToken? _historyToken;
  CancelToken? _sendToken;
  StreamSubscription<SseEvent>? _sseSub;
  ProviderSubscription<AppLifecycleState>? _lifeSub;

  /// Test seam — overridden in unit tests to inject a fake stream.
  /// Production code uses the default factory which wraps a real
  /// `MessagesStream`.
  static ChatStream Function({
    required Uri baseUrl,
    required String agentId,
    required Future<String?> Function() cookieProvider,
  }) streamBuilder = ({
    required baseUrl,
    required agentId,
    required cookieProvider,
  }) =>
      _RealChatStream(
        MessagesStream(
          baseUrl: baseUrl,
          agentId: agentId,
          cookieProvider: cookieProvider,
        ),
      );

  /// Test seam — gates whether `_bootstrap()` is invoked from build().
  /// Tests that exercise dedup / optimistic-insert / retry directly drive
  /// the notifier methods without spinning up a stream subscription.
  static bool autoBootstrap = true;

  @override
  ChatState build() {
    final env = ref.read(appEnvProvider);
    final storage = ref.read(secureStorageProvider);
    _stream = streamBuilder(
      baseUrl: env.baseUrl,
      agentId: agentInstanceId,
      cookieProvider: storage.readSessionId,
    );
    if (autoBootstrap) {
      // Schedule bootstrap microtask so build() can return synchronously.
      // ignore: discarded_futures
      Future<void>.microtask(_bootstrap);
    }

    // D-52 lifecycle hook — disconnect/connect on resume.
    _lifeSub = ref.listen<AppLifecycleState>(
      appLifecycleProvider,
      (prev, next) {
        if (prev != next && next == AppLifecycleState.resumed) {
          // _onResumed reconnects in the background; we don't need to
          // await it inside the lifecycle callback.
          // ignore: discarded_futures
          _onResumed();
        }
      },
    );

    ref.onDispose(() {
      _historyToken?.cancel('ChatScope disposed');
      _sendToken?.cancel('ChatScope disposed');
      // Fire-and-forget cleanup at dispose — Riverpod onDispose is sync.
      // ignore: discarded_futures
      _sseSub?.cancel();
      // ignore: discarded_futures
      _stream.dispose();
      _lifeSub?.close();
    });

    return const ChatState();
  }

  /// D-36 — GET /messages?limit=200 then SSE connect.
  ///
  /// Bug 3 follow-up (2026-05-04): history is now AWAITED FIRST and the
  /// SSE subscription only starts on Ok. flutter_client_sse 2.0.3 has a
  /// hardcoded 5-second retry on ANY non-2xx response (package source
  /// flutter_client_sse-2.0.3/lib/flutter_client_sse.dart:27 +
  /// switch-default at 119-130 — it never inspects HTTP status), so a
  /// 404 from the server (genuine ownership mismatch) used to flood the
  /// api_server with one /messages/stream request every 5s forever.
  /// Pre-flighting via the history call (same auth + ownership gate as
  /// the SSE endpoint) catches the 4xx path before SSE ever fires.
  /// 5xx during an active SSE stream still triggers the package's retry
  /// loop — accepted for now (transient/server-side).
  ///
  /// Cost of sequencing vs the prior parallel D-36: ~50-100ms added to
  /// initial render in the happy path. Acceptable trade for eliminating
  /// the retry storm.
  Future<void> _bootstrap() async {
    _historyToken = CancelToken();
    final api = ref.read(apiClientProvider);
    final res = await api.messagesHistory(
      agentId: agentInstanceId,
      limit: 200,
      cancelToken: _historyToken,
    );
    if (res case Ok(:final value)) {
      // D-39 — banner if exactly 200 returned (more may exist).
      final has200 = value.messages.length >= 200;
      state = state.upsertManyHistory(value.messages).copyWith(
            hasOlderMessages: has200,
          );
      // Ownership + auth proven by the successful history fetch — safe
      // to subscribe to the SSE stream without risking a retry storm.
      _sseSub = _stream.events.listen(_onSseEvent);
      // Fire-and-forget SSE connect; failures are silently tolerated
      // (next resume triggers a reconnect via D-52).
      // ignore: discarded_futures
      _stream.connect().catchError((_) {});
    }
    // On Err we leave the SSE unstarted. The chat shows whatever state
    // existed (likely empty); the user can pull-to-refresh or back out.
  }

  Future<void> _onResumed() async {
    await _stream.disconnect();
    try {
      await _stream.connect();
    // ignore: avoid_catches_without_on_clauses
    } catch (_) {
      // intentionally empty — keep prior state visible on reconnect failure.
    }
  }

  /// Test seam — drives the SSE handler directly from unit tests.
  @visibleForTesting
  void debugOnSse(SseEvent ev) => _onSseEvent(ev);

  /// Test seam — exposes the failed-marker for retry tests.
  @visibleForTesting
  void debugMarkFailed(String idemKey, String error) {
    state = state.markFailed(idemKey: idemKey, error: error);
  }

  void _onSseEvent(SseEvent ev) {
    // The SSE envelope on the wire (Wave 0 Spike B):
    //   { seq:int, kind:str, payload:{source, content, captured_at}, ... }
    // Dedup Map keys on `seq` (Wave 0 Spike B verdict).
    if (ev.kind != 'inapp_outbound') return;
    final Map<String, dynamic> json;
    try {
      json = jsonDecode(ev.data) as Map<String, dynamic>;
    // ignore: avoid_catches_without_on_clauses
    } catch (_) {
      return;
    }
    final seq = json['seq'];
    final payload = json['payload'];
    if (seq is! int || payload is! Map<String, dynamic>) return;
    final source = payload['source'] as String?;
    final content = payload['content'] as String?;
    final capturedAt = payload['captured_at'] as String?;
    if (content == null || capturedAt == null) return;

    // D-36 — `source: 'agent'` is the assistant reply; `source: 'user'`
    // is the user mirror replay. Map source -> chat role.
    final role = source == 'agent' ? 'assistant' : 'user';

    final row = ChatRow(
      id: 'sse:$seq',
      role: role,
      content: content,
      status: 'delivered',
      createdAt: capturedAt,
    );

    // If an assistant typing placeholder is in flight, clear it before
    // upserting the real row so the bubble visually replaces (D-41).
    if (role == 'assistant') {
      state = state.clearTypingPlaceholders().upsertOne(row);
      // Phase 27 D-32 trigger #3 (deferred) — instant ticker refresh on
      // assistant reply was attempted via ref.invalidate(usageSummaryProvider)
      // here, but it crashed downstream Consumers mid-SSE-handler with
      // 'Failed assertion: _lifecycleState != _ElementLifecycle.defunct'.
      // Triggers #1 (mount) + #2 (lifecycle resume) cover the workflow;
      // ticker updates on next screen mount or app resume.
    } else {
      // For user mirrors, keep the optimistic 'pending:<idemKey>' rows in
      // place — they have a different id (pending vs sse) so the upsert
      // is additive. We still avoid double-rendering by using the
      // history-style content collision check.
      final dup = state.byId.values.any((r) =>
          r.role == 'user' &&
          r.content == content &&
          r.status == 'pending');
      if (dup) {
        // Mark the pending one as delivered; do NOT add a second user row.
        // Find which idemKey it corresponds to.
        for (final entry in state.byId.entries) {
          if (entry.key.startsWith('pending:') &&
              entry.value.role == 'user' &&
              entry.value.content == content) {
            state = state.markPendingDelivered(
              idemKey: entry.key.substring('pending:'.length),
            );
            break;
          }
        }
      } else {
        state = state.upsertOne(row);
      }
    }
  }

  /// D-41 — Send: optimistic insert + POST /messages.
  Future<void> sendMessage(String content) async {
    final idemKey = const Uuid().v4();
    state = state.insertOptimistic(
      idemKey: idemKey,
      content: content,
      now: DateTime.now(),
    );
    _sendToken = CancelToken();
    final api = ref.read(apiClientProvider);
    final r = await api.postMessage(
      agentId: agentInstanceId,
      content: content,
      idempotencyKey: idemKey,
      cancelToken: _sendToken,
    );
    switch (r) {
      case Ok():
        state = state.markPendingDelivered(idemKey: idemKey);
      case Err(:final error):
        state = state.markFailed(idemKey: idemKey, error: error.message);
    }
  }

  /// Cancel the in-flight POST (D-51 — cancel-on-spinner-tap).
  void cancelInflight() {
    _sendToken?.cancel('user-cancelled');
  }

  /// D-45 — retry generates a NEW Uuid().v4(); failed bubble stays.
  Future<void> retryFailed({
    required String failedKey,
    required String content,
  }) async {
    final newKey = const Uuid().v4();
    state = state.insertOptimistic(
      idemKey: newKey,
      content: content,
      now: DateTime.now(),
    );
    final api = ref.read(apiClientProvider);
    final r = await api.postMessage(
      agentId: agentInstanceId,
      content: content,
      idempotencyKey: newKey,
    );
    switch (r) {
      case Ok():
        state = state.markPendingDelivered(idemKey: newKey);
      case Err(:final error):
        state = state.markFailed(idemKey: newKey, error: error.message);
    }
  }

  /// D-39 — load up to 1000 older messages.
  Future<void> loadOlder() async {
    _historyToken?.cancel('superseded by loadOlder');
    _historyToken = CancelToken();
    final api = ref.read(apiClientProvider);
    final res = await api.messagesHistory(
      agentId: agentInstanceId,
      limit: 1000,
      cancelToken: _historyToken,
    );
    if (res case Ok(:final value)) {
      state = state.upsertManyHistory(value.messages).copyWith(
            hasOlderMessages: false,
          );
    }
  }
}

/// Family-scoped chat state. Use `ref.watch(chatScopeProvider(agentId))`.
final chatScopeProvider =
    NotifierProvider.autoDispose.family<ChatScope, ChatState, String>(
  ChatScope.new,
);
