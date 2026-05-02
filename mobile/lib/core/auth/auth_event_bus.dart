// Phase 24 Plan 06 — CROSS-WAVE SHIM for Plan 24-04's AuthEventBus.
//
// Plan 24-04 owns this file's final implementation. This shim exists ONLY
// so Plan 24-06's providers tree compiles. The contract (event type
// `AuthRequired`, `events` Stream, `dispose()`) mirrors the surface Plan
// 24-04's RED tests already use; the wave-merge replaces this file when
// 24-04 lands.

import 'dart:async';

/// Emitted when a 401 is observed and the local session was cleared.
/// Phase 25 wires `MaterialApp.router.refreshListenable` to redirect to
/// the OAuth screen on this event; Phase 24 only needs the type to exist.
class AuthRequired {
  const AuthRequired();
}

class AuthEventBus {
  AuthEventBus() : _controller = StreamController<AuthRequired>.broadcast();

  final StreamController<AuthRequired> _controller;

  Stream<AuthRequired> get events => _controller.stream;

  void emit() {
    if (!_controller.isClosed) {
      _controller.add(const AuthRequired());
    }
  }

  Future<void> dispose() => _controller.close();
}
