// Phase 24 Plan 03 — backend endpoint paths.
//
// Centralized so tests + ApiClient (Plan 04) both reference the same strings.
// Mapping table: see 24-PATTERNS.md Group 4 lines 306-320.
//
// All paths under /v1 use the prefix already mounted by api_server. /healthz
// stays prefix-less (Phase 19-03: liveness check pre-router).

abstract final class ApiEndpoints {
  ApiEndpoints._();

  static const String healthz = '/healthz';

  static const String runs = '/v1/runs';

  static String agentStart(String agentId) => '/v1/agents/$agentId/start';
  static String agentStop(String agentId) => '/v1/agents/$agentId/stop';
  static String agentMessages(String agentId) =>
      '/v1/agents/$agentId/messages';
  static String agentMessagesStream(String agentId) =>
      '/v1/agents/$agentId/messages/stream';

  static const String agentsList = '/v1/agents';
  static const String recipes = '/v1/recipes';
  static const String models = '/v1/models';
  static const String usersMe = '/v1/users/me';
  static const String authGoogleMobile = '/v1/auth/google/mobile';
  static const String authGithubMobile = '/v1/auth/github/mobile';
}
