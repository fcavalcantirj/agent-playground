// Phase 24 Plan 04 — auth-required event stream (D-35).
//
// AuthInterceptor emits an [AuthRequired] sentinel on a 401. Phase 25
// listens on `events` and routes to OAuth (Phase 23 D-26). Phase 24
// only wires the bus; the placeholder screen (Plan 06) does not listen.
//
// Broadcast stream — multiple listeners (Phase 25 may attach a router
// listener AND a logger).

import 'dart:async';

class AuthRequired {
  const AuthRequired();
}

class AuthEventBus {
  AuthEventBus()
      : _controller = StreamController<AuthRequired>.broadcast();

  final StreamController<AuthRequired> _controller;

  Stream<AuthRequired> get events => _controller.stream;

  void emit() => _controller.add(const AuthRequired());

  Future<void> dispose() => _controller.close();
}
