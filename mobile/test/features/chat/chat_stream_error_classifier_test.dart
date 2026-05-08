// Phase 31 H4 — classifier unit tests (D-07 + AMD-02).
//
// Five canonical mapping cases plus the connection-error transport tier.
// Locked mapping per CONTEXT.md AMD-02:
//   SocketException                                    -> networkTransient
//   TimeoutException                                   -> networkTransient
//   DioException(connection*Timeout/connectionError)   -> networkTransient
//   DioException(response.statusCode == 401)           -> authExpired
//   DioException(response.statusCode >= 500)           -> serverError
//   DioException(response.statusCode 4xx, !=401)       -> serverError
//   Unknown Object                                     -> networkTransient
import 'dart:async';
import 'dart:io';

import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

RequestOptions _opts() => RequestOptions();

void main() {
  group('classifyChatStreamError', () {
    test('SocketException -> networkTransient', () {
      expect(
        classifyChatStreamError(const SocketException('host down')),
        ChatStreamErrorClass.networkTransient,
      );
    });

    test('TimeoutException -> networkTransient', () {
      expect(
        classifyChatStreamError(
          TimeoutException('boom', const Duration(seconds: 1)),
        ),
        ChatStreamErrorClass.networkTransient,
      );
    });

    test('DioException connectionError -> networkTransient', () {
      final dio = DioException(
        requestOptions: _opts(),
        type: DioExceptionType.connectionError,
      );
      expect(
        classifyChatStreamError(dio),
        ChatStreamErrorClass.networkTransient,
      );
    });

    test('DioException 401 -> authExpired', () {
      final dio = DioException(
        requestOptions: _opts(),
        response: Response(
          requestOptions: _opts(),
          statusCode: 401,
        ),
      );
      expect(classifyChatStreamError(dio), ChatStreamErrorClass.authExpired);
    });

    test('DioException 503 -> serverError (AMD-02)', () {
      final dio = DioException(
        requestOptions: _opts(),
        response: Response(
          requestOptions: _opts(),
          statusCode: 503,
        ),
      );
      expect(classifyChatStreamError(dio), ChatStreamErrorClass.serverError);
    });

    test('unknown Object -> networkTransient (D-07 fallback)', () {
      expect(
        classifyChatStreamError(Exception('weird wrapper')),
        ChatStreamErrorClass.networkTransient,
      );
    });
  });
}
