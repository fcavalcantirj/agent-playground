// Phase 24 Plan 04 — dev-only redacting log interceptor (D-52).
//
// Mirrors api_server/src/api_server/middleware/log_redact.py policy:
// Cookie + Authorization headers are truncated to last 8 chars before
// reaching `developer.log`. Mitigates T-24-04-01 (Information
// Disclosure via dev logs).
//
// The function lives at top-level (not a method) so unit tests can
// drive the redaction logic in isolation without spinning up dio.

import 'dart:developer' as developer;

import 'package:dio/dio.dart';

/// Truncate a header value to its last 8 chars, prefixed with `...`.
///
/// `null` and empty values become `<empty>`. Any value that is not
/// strictly longer than 8 chars becomes `<short>` — short header
/// values are still potentially identifying, so we refuse to log
/// even a partial fragment of them.
String redactHeader(Object? raw) {
  final s = raw?.toString() ?? '';
  if (s.isEmpty) return '<empty>';
  if (s.length <= 8) return '<short>';
  return '...${s.substring(s.length - 8)}';
}

class RedactingLogInterceptor extends Interceptor {
  const RedactingLogInterceptor();

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    final cookie = redactHeader(options.headers['Cookie']);
    final authz = redactHeader(options.headers['Authorization']);
    developer.log(
      '> ${options.method} ${options.path} cookie=$cookie authz=$authz',
      name: 'http',
    );
    handler.next(options);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    developer.log(
      '< ${response.statusCode} ${response.requestOptions.path}',
      name: 'http',
    );
    handler.next(response);
  }

  @override
  void onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) {
    final code = err.response?.statusCode ?? '-';
    developer.log(
      '! $code ${err.requestOptions.path} ${err.type}',
      name: 'http',
    );
    handler.next(err);
  }
}
