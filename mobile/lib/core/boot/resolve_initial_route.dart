// Phase 25 Wave 1 — cold-start route resolution (D-01..D-02).
//
// Extracted as a free function so it is testable against an
// http_mock_adapter Dio without booting the entire app. main.dart
// invokes this with a real ApiClient + 6s timeout before runApp().
//
// Contract:
//   - Ok(SessionUser)            → '/dashboard'
//   - Err(unauthorized)          → '/login'
//   - Err(any other code)        → '/retry-bootstrap'
//   - timeout / unexpected throw → '/retry-bootstrap'

import 'dart:async';

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/result.dart';

const Duration kBootProbeTimeout = Duration(seconds: 6);

Future<String> resolveInitialRoute(
  ApiClient client, {
  Duration timeout = kBootProbeTimeout,
}) async {
  try {
    final r = await client.usersMe().timeout(timeout);
    return switch (r) {
      Ok() => '/dashboard',
      Err(:final error) when error.code == ErrorCode.unauthorized => '/login',
      Err() => '/retry-bootstrap',
    };
  } on TimeoutException {
    return '/retry-bootstrap';
  } on Object {
    return '/retry-bootstrap';
  }
}
