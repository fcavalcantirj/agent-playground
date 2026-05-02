// Phase 24 Plan 03 — ApiError + ErrorCode wire-shape mirror.

import 'package:agent_playground/core/api/result.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ApiError._parseCode — 18 backend codes (errors.py:39-58)', () {
    const cases = <(String, ErrorCode)>{
      ('INVALID_REQUEST', ErrorCode.invalidRequest),
      ('RECIPE_NOT_FOUND', ErrorCode.recipeNotFound),
      ('SCHEMA_NOT_FOUND', ErrorCode.schemaNotFound),
      ('LINT_FAIL', ErrorCode.lintFail),
      ('PAYLOAD_TOO_LARGE', ErrorCode.payloadTooLarge),
      ('RATE_LIMITED', ErrorCode.rateLimited),
      ('IDEMPOTENCY_BODY_MISMATCH', ErrorCode.idempotencyBodyMismatch),
      ('UNAUTHORIZED', ErrorCode.unauthorized),
      ('INTERNAL', ErrorCode.internal),
      ('RUNNER_TIMEOUT', ErrorCode.runnerTimeout),
      ('INFRA_UNAVAILABLE', ErrorCode.infraUnavailable),
      ('AGENT_NOT_FOUND', ErrorCode.agentNotFound),
      ('AGENT_NOT_RUNNING', ErrorCode.agentNotRunning),
      ('AGENT_ALREADY_RUNNING', ErrorCode.agentAlreadyRunning),
      ('CHANNEL_NOT_CONFIGURED', ErrorCode.channelNotConfigured),
      ('CHANNEL_INPUTS_INVALID', ErrorCode.channelInputsInvalid),
      ('CONCURRENT_POLL_LIMIT', ErrorCode.concurrentPollLimit),
      ('EVENT_STREAM_UNAVAILABLE', ErrorCode.eventStreamUnavailable),
    };
    for (final (wire, expected) in cases) {
      test('$wire -> $expected', () {
        expect(ApiError.parseCodeForTest(wire), expected);
      });
    }

    test('null -> unknownServer', () {
      expect(ApiError.parseCodeForTest(null), ErrorCode.unknownServer);
    });
    test('UNKNOWN_GIBBERISH -> unknownServer', () {
      expect(
        ApiError.parseCodeForTest('UNKNOWN_GIBBERISH'),
        ErrorCode.unknownServer,
      );
    });
  });

  group('ApiError.fromDioException', () {
    DioException makeException({
      DioExceptionType type = DioExceptionType.unknown,
      Response<dynamic>? response,
      String? message,
    }) =>
        DioException(
          requestOptions: RequestOptions(path: '/healthz'),
          type: type,
          response: response,
          message: message,
        );

    test('cancellation maps to network/cancelled', () {
      final e = DioException(
        requestOptions: RequestOptions(path: '/healthz'),
        type: DioExceptionType.cancel,
      );
      final err = ApiError.fromDioException(e);
      expect(err.code, ErrorCode.network);
      expect(err.message, 'cancelled');
    });

    test('connectionTimeout -> ErrorCode.timeout', () {
      final e = makeException(
        type: DioExceptionType.connectionTimeout,
        message: 'connect timeout',
      );
      expect(ApiError.fromDioException(e).code, ErrorCode.timeout);
    });

    test('receiveTimeout -> ErrorCode.timeout', () {
      final e = makeException(
        type: DioExceptionType.receiveTimeout,
        message: 'receive timeout',
      );
      expect(ApiError.fromDioException(e).code, ErrorCode.timeout);
    });

    test('sendTimeout -> ErrorCode.timeout', () {
      final e = makeException(
        type: DioExceptionType.sendTimeout,
        message: 'send timeout',
      );
      expect(ApiError.fromDioException(e).code, ErrorCode.timeout);
    });

    test('null response -> ErrorCode.network', () {
      final e = makeException(message: 'connection reset');
      expect(ApiError.fromDioException(e).code, ErrorCode.network);
    });

    test('parses Stripe-shape envelope on 404 RECIPE_NOT_FOUND', () {
      final response = Response<dynamic>(
        requestOptions: RequestOptions(path: '/v1/recipes'),
        statusCode: 404,
        data: <String, dynamic>{
          'error': <String, dynamic>{
            'type': 'not_found',
            'code': 'RECIPE_NOT_FOUND',
            'message': 'no such recipe',
            'param': 'recipe_name',
            'request_id': 'abc123',
          },
        },
      );
      final e = makeException(response: response);
      final err = ApiError.fromDioException(e);
      expect(err.code, ErrorCode.recipeNotFound);
      expect(err.message, 'no such recipe');
      expect(err.param, 'recipe_name');
      expect(err.requestId, 'abc123');
      expect(err.statusCode, 404);
    });

    test('500 with no envelope -> unknownServer', () {
      final response = Response<dynamic>(
        requestOptions: RequestOptions(path: '/v1/runs'),
        statusCode: 500,
        data: 'plain string error',
      );
      final e = makeException(response: response);
      final err = ApiError.fromDioException(e);
      expect(err.code, ErrorCode.unknownServer);
      expect(err.statusCode, 500);
    });
  });
}
