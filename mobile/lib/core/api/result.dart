// Phase 24 Plan 03 — sealed Result<T> + typed ApiError mirroring the
// backend Stripe-shape envelope at api_server/src/api_server/models/errors.py.
//
// The 18 enum cases below mirror the SCREAMING_SNAKE constants from that
// file's `class ErrorCode:` block (lines 39-58), camelCased. The 3
// client-only cases (network, timeout, unknownServer) cover dio-side
// failures with no backend equivalent.

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Sealed result discriminated union — D-32.
///
/// Switch over `Result<T>` is exhaustive at compile time on `Ok<T>` and
/// `Err<T>`. No default arm is necessary; adding a third subclass would be
/// a compile error in every callsite, which is the contract we want.
sealed class Result<T> {
  const Result();
  const factory Result.ok(T value) = Ok<T>;
  const factory Result.err(ApiError error) = Err<T>;
}

final class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;
}

final class Err<T> extends Result<T> {
  const Err(this.error);
  final ApiError error;
}

/// Mirrors `api_server/src/api_server/models/errors.py::ErrorCode`.
/// Add a new value here when (and only when) the backend `ErrorCode`
/// class adds one — they must stay 1:1.
enum ErrorCode {
  // Backend-emitted (lines 39-58 of api_server/src/api_server/models/errors.py)
  invalidRequest,
  recipeNotFound,
  schemaNotFound,
  lintFail,
  payloadTooLarge,
  rateLimited,
  idempotencyBodyMismatch,
  unauthorized,
  internal,
  runnerTimeout,
  infraUnavailable,
  agentNotFound,
  agentNotRunning,
  agentAlreadyRunning,
  channelNotConfigured,
  channelInputsInvalid,
  concurrentPollLimit,
  eventStreamUnavailable,

  // Client-only (no backend equivalent — dio raised before/after wire).
  network,
  timeout,
  unknownServer,
}

/// Typed error model — D-38 / D-39.
///
/// Created via [ApiError.fromDioException] for transport-layer failures, or
/// directly with the const constructor for synthetic client-side errors.
class ApiError {
  const ApiError({
    required this.code,
    required this.message,
    this.param,
    this.requestId,
    this.statusCode,
  });
  final ErrorCode code;
  final String message;
  final String? param;
  final String? requestId;
  final int? statusCode;

  /// Parse a [DioException] into a typed [ApiError]. Recognises:
  ///
  /// - cancel        -> network/cancelled
  /// - any timeout   -> timeout
  /// - response==null -> network (with the dio message)
  /// - response.data has the Stripe-shape envelope -> backend code lookup
  /// - response with no/malformed envelope -> unknownServer
  // ignore: prefer_constructors_over_static_methods
  static ApiError fromDioException(DioException e) {
    if (CancelToken.isCancel(e)) {
      return const ApiError(code: ErrorCode.network, message: 'cancelled');
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout) {
      return ApiError(
        code: ErrorCode.timeout,
        message: e.message ?? 'timeout',
      );
    }
    final response = e.response;
    if (response == null) {
      return ApiError(
        code: ErrorCode.network,
        message: e.message ?? 'network error',
      );
    }
    // Wire JSON shape:
    // {"error": {"type": "...", "code": "...", "message": "...",
    //            "param": "...", "request_id": "..."}}
    // (api_server/src/api_server/models/errors.py:87-147)
    final body = response.data;
    if (body is Map<String, dynamic> &&
        body['error'] is Map<String, dynamic>) {
      final err = body['error'] as Map<String, dynamic>;
      return ApiError(
        code: _parseCode(err['code'] as String?),
        message: (err['message'] as String?) ?? 'unknown',
        param: err['param'] as String?,
        requestId: err['request_id'] as String?,
        statusCode: response.statusCode,
      );
    }
    return ApiError(
      code: ErrorCode.unknownServer,
      message: 'malformed error envelope',
      statusCode: response.statusCode,
    );
  }

  /// Convenience builder for client-side validation failures (e.g. an empty
  /// agent_name caught before the dio call ships).
  // ignore: prefer_constructors_over_static_methods
  static ApiError invalidArgument(String param, String message) => ApiError(
        code: ErrorCode.invalidRequest,
        message: message,
        param: param,
      );

  static ErrorCode _parseCode(String? code) => switch (code) {
        'INVALID_REQUEST' => ErrorCode.invalidRequest,
        'RECIPE_NOT_FOUND' => ErrorCode.recipeNotFound,
        'SCHEMA_NOT_FOUND' => ErrorCode.schemaNotFound,
        'LINT_FAIL' => ErrorCode.lintFail,
        'PAYLOAD_TOO_LARGE' => ErrorCode.payloadTooLarge,
        'RATE_LIMITED' => ErrorCode.rateLimited,
        'IDEMPOTENCY_BODY_MISMATCH' => ErrorCode.idempotencyBodyMismatch,
        'UNAUTHORIZED' => ErrorCode.unauthorized,
        'INTERNAL' => ErrorCode.internal,
        'RUNNER_TIMEOUT' => ErrorCode.runnerTimeout,
        'INFRA_UNAVAILABLE' => ErrorCode.infraUnavailable,
        'AGENT_NOT_FOUND' => ErrorCode.agentNotFound,
        'AGENT_NOT_RUNNING' => ErrorCode.agentNotRunning,
        'AGENT_ALREADY_RUNNING' => ErrorCode.agentAlreadyRunning,
        'CHANNEL_NOT_CONFIGURED' => ErrorCode.channelNotConfigured,
        'CHANNEL_INPUTS_INVALID' => ErrorCode.channelInputsInvalid,
        'CONCURRENT_POLL_LIMIT' => ErrorCode.concurrentPollLimit,
        'EVENT_STREAM_UNAVAILABLE' => ErrorCode.eventStreamUnavailable,
        _ => ErrorCode.unknownServer,
      };

  /// Test-only access to the private [_parseCode] switch.
  /// `very_good_analysis` warns on private-name access from tests; this
  /// `@visibleForTesting` shim is the canonical workaround.
  @visibleForTesting
  static ErrorCode parseCodeForTest(String? code) => _parseCode(code);
}
