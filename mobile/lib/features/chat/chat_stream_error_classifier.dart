// Phase 31 H4 (D-06, D-07, AMD-02) — three-class chat-stream error taxonomy.
//
// Pure top-level dispatch fn. No Riverpod, no I/O, no async. Reusable from
// BOTH chat_providers.dart:387 (initial connect) AND chat_providers.dart's
// _onResumed reconnect site (~line 398).
//
// AMD-02 supersedes the original D-07 wording — locked mapping below.
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';

/// Three-class user-facing taxonomy. Maps to the three SPEC-locked copy
/// strings in chat_screen.dart (`_streamErrorCopy`).
enum ChatStreamErrorClass {
  /// SocketException, TimeoutException, transport-tier DioException.
  /// Banner copy: "Connection lost — tap to retry".
  networkTransient,

  /// HTTP 401. Banner copy: "Session expired — sign in again".
  authExpired,

  /// HTTP 5xx and non-401 4xx. Banner copy: "Server error — try again later".
  serverError,
}

/// Classify any caught Object thrown by the SSE-connect / history-fetch
/// path into a `ChatStreamErrorClass`. Unknown errors fall back to
/// `networkTransient` (D-07) — the original error should be logged to a
/// Sentry breadcrumb at the call site for debugging.
ChatStreamErrorClass classifyChatStreamError(Object e) {
  // Network-layer errors → transient.
  if (e is SocketException) return ChatStreamErrorClass.networkTransient;
  if (e is TimeoutException) return ChatStreamErrorClass.networkTransient;

  // Dio surface (history-fetch retries, defensive coverage of any dio path
  // that bubbles up to the SSE-connect callback).
  if (e is DioException) {
    final status = e.response?.statusCode;
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return ChatStreamErrorClass.networkTransient;
    }
    if (status == 401) return ChatStreamErrorClass.authExpired;
    // AMD-02: 5xx → serverError (NOT networkTransient — required by SPEC AC11).
    if (status != null && status >= 500) {
      return ChatStreamErrorClass.serverError;
    }
    // Non-401 4xx (e.g. 403, 404, 422) → serverError surface.
    return ChatStreamErrorClass.serverError;
  }

  // Unknown Object (raw Exception, String, flutter_client_sse 2.0.3 wrap,
  // etc.) → fallback per D-07. Caller should log the original to a
  // Sentry breadcrumb.
  return ChatStreamErrorClass.networkTransient;
}
