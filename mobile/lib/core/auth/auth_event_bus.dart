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
  const AuthRequired({this.reason});

  /// Optional revocation reason carried from the api_server's 401 envelope.
  /// Phase 26: when the api returns `error.code == 'SESSION_REVOKED'`, the
  /// AuthInterceptor extracts it and forwards as `reason: 'session_revoked'`
  /// so the login screen can render a "session ended elsewhere" banner.
  /// Null on the existing generic-401 path (cookie expired / never signed
  /// in / self-logout) — login shows the standard "Signed out" copy.
  final String? reason;
}

class AuthEventBus {
  AuthEventBus()
      : _controller = StreamController<AuthRequired>.broadcast();

  final StreamController<AuthRequired> _controller;

  Stream<AuthRequired> get events => _controller.stream;

  void emit({String? reason}) =>
      _controller.add(AuthRequired(reason: reason));

  Future<void> dispose() => _controller.close();
}
