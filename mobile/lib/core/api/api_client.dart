// Phase 24 Plan 06 — CROSS-WAVE SHIM for Plan 24-04's ApiClient.
//
// Plan 24-04 owns this file's final implementation (per 24-PATTERNS.md
// Group 4 — full surface for /v1/runs, /v1/agents/:id/start, /v1/agents/:id/messages,
// /v1/recipes, /v1/models, /v1/users/me). Phase 24 Wave 3 only needs the
// /healthz path so the placeholder boot screen turns Ok/Err. When Plan
// 24-04 lands, the wave-merge replaces this file.
//
// The healthz() return shape (Result<HealthOk>) is the same as Plan 24-04
// will produce; only the other endpoints are missing.

import 'package:agent_playground/core/api/api_endpoints.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:dio/dio.dart';

class ApiClient {
  ApiClient(this._dio);

  final Dio _dio;

  /// `GET /healthz` — backend liveness probe (Phase 19-03).
  /// Plan 24-04 will mirror this same wrap-in-Result pattern across the
  /// full endpoint surface.
  Future<Result<HealthOk>> healthz() async {
    try {
      final res = await _dio.get<dynamic>(ApiEndpoints.healthz);
      final body = res.data;
      if (body is Map<String, dynamic>) {
        return Result<HealthOk>.ok(HealthOk.fromJson(body));
      }
      return const Result<HealthOk>.err(
        ApiError(
          code: ErrorCode.unknownServer,
          message: 'malformed /healthz body',
        ),
      );
    } on DioException catch (e) {
      return Result<HealthOk>.err(ApiError.fromDioException(e));
    }
  }
}
