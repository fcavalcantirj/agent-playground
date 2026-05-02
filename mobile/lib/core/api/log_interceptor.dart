// Phase 24 Plan 06 — CROSS-WAVE SHIM for Plan 24-04's RedactingLogInterceptor.
//
// Plan 24-04 owns this file. The redactHeader truncate-to-last-8 contract
// is fully specified by Plan 24-04's RED tests; this shim implements only
// what Plan 24-06's debug-mode boot path requires. The wave-merge replaces
// this when 24-04 lands.

import 'package:dio/dio.dart';

/// D-52: redact secret-like header values to their last 8 characters so
/// debug logs don't leak full tokens.
///
/// - null            -> `<empty>`
/// - empty           -> `<empty>`
/// - up to 8 chars   -> `<short>`
/// - more than 8     -> `...<last8>`
String redactHeader(String? value) {
  if (value == null || value.isEmpty) {
    return '<empty>';
  }
  if (value.length <= 8) {
    return '<short>';
  }
  return '...${value.substring(value.length - 8)}';
}

class RedactingLogInterceptor extends Interceptor {
  const RedactingLogInterceptor();

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    // Plan 24-04 will own the structured-log emission. The shim just passes
    // through so debug builds don't crash on first request.
    handler.next(options);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    handler.next(err);
  }
}
