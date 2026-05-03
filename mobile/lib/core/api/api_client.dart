// Phase 24 Plan 04 — typed dio client (D-31). One method per backend
// endpoint. Every method returns Future<Result<T>> and never throws
// (D-32 — surface DioException via ApiError.fromDioException). Every
// method accepts an optional CancelToken (D-41) so callers can cancel
// inflight requests on screen-pop / SSE-disconnect / route-change.
//
// BYOK contract (D-40): only `runs(byokOpenRouterKey)` and
// `start(byokOpenRouterKey)` accept the optional Authorization header.
// There is intentionally no global BYOK injector — that would risk
// leaking the key to e.g. /v1/messages or /v1/agents (T-24-04-04).
//
// Idempotency contract (D-36, Phase 23 D-09): postMessage's Dart
// signature REQUIRES `idempotencyKey`. The backend in
// api_server/src/api_server/middleware/idempotency.py:58-73 returns 400
// if Idempotency-Key is missing on POST /v1/agents/:id/messages, so the
// client must surface that requirement at the call shape, not at runtime.
//
// Pagination guard (D-42): messagesHistory clamps limit to [1, 1000]
// BEFORE issuing the dio call — invalid values short-circuit to
// Result.err(ErrorCode.invalidRequest, param: 'limit') so we save a
// round-trip and surface the error in the same shape as a server-side
// 400.

import 'package:agent_playground/core/api/api_endpoints.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:dio/dio.dart';

class ApiClient {
  ApiClient(this._dio);

  final Dio _dio;

  /// Exposed for test / spike seams (e.g. installing http_mock_adapter,
  /// adding the AuthInterceptor in the Riverpod DI graph).
  Dio get dio => _dio;

  // ---------------------------------------------------------------------------
  // GET /healthz
  // ---------------------------------------------------------------------------
  Future<Result<HealthOk>> healthz({CancelToken? cancelToken}) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.healthz,
        cancelToken: cancelToken,
      );
      return Result.ok(HealthOk.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/runs   (D-40 BYOK allowed)
  // ---------------------------------------------------------------------------
  Future<Result<RunResponse>> runs({
    required RunRequest body,
    String? byokOpenRouterKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.runs,
        data: body.toJson(),
        cancelToken: cancelToken,
        options: Options(
          headers: byokOpenRouterKey == null
              ? null
              : <String, String>{'Authorization': 'Bearer $byokOpenRouterKey'},
        ),
      );
      return Result.ok(RunResponse.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/agents/:id/start   (D-40 BYOK allowed)
  // ---------------------------------------------------------------------------
  Future<Result<StartResponse>> start({
    required String agentId,
    StartRequest body = const StartRequest(),
    String? byokOpenRouterKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.agentStart(agentId),
        data: body.toJson(),
        cancelToken: cancelToken,
        options: Options(
          headers: byokOpenRouterKey == null
              ? null
              : <String, String>{'Authorization': 'Bearer $byokOpenRouterKey'},
        ),
      );
      return Result.ok(StartResponse.fromJson(res.data ?? const {}));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/agents/:id/stop
  // ---------------------------------------------------------------------------
  /// Gracefully stop a persistent container.
  ///
  /// `byokOpenRouterKey` is REQUIRED by the API for consistency across the
  /// /v1/agents/:id/* family (Phase 21 will reuse it as the session-ownership
  /// gate). The api_server parses the Bearer header but does NOT forward the
  /// value to the runner — `/stop` is purely docker-lifecycle. Pass the same
  /// key the user supplied to `runs()` / `start()`.
  Future<Result<void>> stop({
    required String agentId,
    required String byokOpenRouterKey,
    CancelToken? cancelToken,
  }) async {
    try {
      await _dio.post<dynamic>(
        ApiEndpoints.agentStop(agentId),
        cancelToken: cancelToken,
        options: Options(
          headers: {'Authorization': 'Bearer $byokOpenRouterKey'},
        ),
      );
      return const Result.ok(null);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/agents/:id/messages   (D-36 / Phase 23 D-09: Idempotency-Key)
  // ---------------------------------------------------------------------------
  Future<Result<MessagePostAck>> postMessage({
    required String agentId,
    required String content,
    required String idempotencyKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.agentMessages(agentId),
        data: {'content': content},
        options: Options(
          headers: <String, String>{'Idempotency-Key': idempotencyKey},
        ),
        cancelToken: cancelToken,
      );
      return Result.ok(MessagePostAck.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/agents/:id/messages?limit=N   (D-42 pagination guard)
  // ---------------------------------------------------------------------------
  Future<Result<MessagesPage>> messagesHistory({
    required String agentId,
    int limit = 200,
    CancelToken? cancelToken,
  }) async {
    if (limit < 1 || limit > 1000) {
      return Result.err(
        ApiError.invalidArgument('limit', 'must be 1..1000'),
      );
    }
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.agentMessages(agentId),
        queryParameters: {'limit': limit},
        cancelToken: cancelToken,
      );
      return Result.ok(MessagesPage.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/agents
  // ---------------------------------------------------------------------------
  Future<Result<List<AgentSummary>>> agentsList({
    CancelToken? cancelToken,
  }) async {
    try {
      // Server returns AgentListResponse → `{"agents":[...]}`. Same
      // envelope shape as /v1/recipes; same mocks-vs-prod divergence
      // (Wave 5 manual app run — Phase 25 dashboard showed
      // "Couldn't load agents" while api_server returned 200 OK).
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.agentsList,
        cancelToken: cancelToken,
      );
      final raw = (res.data?['agents'] as List<dynamic>?) ??
          const <dynamic>[];
      final rows = raw
          .cast<Map<String, dynamic>>()
          .map(AgentSummary.fromJson)
          .toList(growable: false);
      return Result.ok(rows);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/recipes
  // ---------------------------------------------------------------------------
  Future<Result<List<Recipe>>> recipes({CancelToken? cancelToken}) async {
    try {
      // Server returns RecipeListResponse → `{"recipes":[...]}`. Unit
      // tests previously passed because http_mock_adapter fixtures
      // returned a top-level array — Wave 5 spike caught the divergence
      // (Golden Rule #1). Match the recipeDetail() envelope-aware shape.
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.recipes,
        cancelToken: cancelToken,
      );
      final raw = (res.data?['recipes'] as List<dynamic>?) ??
          const <dynamic>[];
      final rows = raw
          .cast<Map<String, dynamic>>()
          .map(Recipe.fromJson)
          .toList(growable: false);
      return Result.ok(rows);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/recipes/{name}   (Wave 3 — D-54 RecipeDetail source)
  // ---------------------------------------------------------------------------
  Future<Result<RecipeDetail>> recipeDetail({
    required String name,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.recipeDetail(name),
        cancelToken: cancelToken,
      );
      // RecipeDetail.fromJson unwraps the `{"recipe": ...}` envelope
      // (RecipeDetailResponse.model_dump() shape) — no client-side
      // unwrap needed here.
      return Result.ok(RecipeDetail.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/models   (OpenRouter passthrough — accepts both wire shapes)
  // ---------------------------------------------------------------------------
  Future<Result<List<OpenRouterModel>>> models({
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.get<dynamic>(
        ApiEndpoints.models,
        cancelToken: cancelToken,
      );
      final data = res.data;
      final List<dynamic> rows;
      if (data is List<dynamic>) {
        rows = data;
      } else if (data is Map<String, dynamic> &&
          data['data'] is List<dynamic>) {
        rows = data['data'] as List<dynamic>;
      } else {
        rows = const <dynamic>[];
      }
      final parsed = rows
          .cast<Map<String, dynamic>>()
          .map(OpenRouterModel.fromJson)
          .toList(growable: false);
      return Result.ok(parsed);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // GET /v1/users/me
  // ---------------------------------------------------------------------------
  Future<Result<SessionUser>> usersMe({CancelToken? cancelToken}) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.usersMe,
        cancelToken: cancelToken,
      );
      return Result.ok(SessionUser.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/auth/google/mobile
  // ---------------------------------------------------------------------------
  Future<Result<MobileAuthResponse>> authGoogleMobile({
    required String idToken,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.authGoogleMobile,
        data: {'id_token': idToken},
        cancelToken: cancelToken,
      );
      // Server returns {session_id, expires_at, user:{...}} per Phase 23
      // D-23 — mobile has no cookie jar, so the body carries session_id
      // and the caller must persist it before the next call.
      return Result.ok(MobileAuthResponse.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  // ---------------------------------------------------------------------------
  // POST /v1/auth/github/mobile
  // ---------------------------------------------------------------------------
  Future<Result<MobileAuthResponse>> authGithubMobile({
    required String accessToken,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.authGithubMobile,
        data: {'access_token': accessToken},
        cancelToken: cancelToken,
      );
      return Result.ok(MobileAuthResponse.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }
}
