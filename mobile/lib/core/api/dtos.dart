// Phase 24 Plan 03 — hand-written DTOs.
//
// Per Phase 24 D-34 the codegen path (build_runner / json codegen) is NOT
// used here: each class has a hand-rolled fromJson(Map<String, dynamic>) +
// (where applicable) toJson() => Map<String, dynamic>. Backend uses
// snake_case JSON keys; Dart classes expose camelCase fields. fromJson
// factories handle nullable backend fields defensively so additive backend
// changes don't crash the client.

/// `GET /healthz` response body.
/// Backend: api_server/src/api_server/routes/health.py returns `{"ok": true}`.
class HealthOk {
  const HealthOk({required this.ok});

  factory HealthOk.fromJson(Map<String, dynamic> json) =>
      HealthOk(ok: json['ok'] as bool);

  final bool ok;

  Map<String, dynamic> toJson() => {'ok': ok};
}

/// `POST /v1/runs` request body.
class RunRequest {
  const RunRequest({
    required this.recipeName,
    required this.model,
    required this.agentName,
  });

  final String recipeName;
  final String model;
  final String agentName;

  Map<String, dynamic> toJson() => {
        'recipe_name': recipeName,
        'model': model,
        'agent_name': agentName,
      };
}

/// `POST /v1/runs` response body.
class RunResponse {
  const RunResponse({
    required this.agentInstanceId,
    required this.smokeOk,
  });

  factory RunResponse.fromJson(Map<String, dynamic> json) => RunResponse(
        agentInstanceId: json['agent_instance_id'] as String,
        smokeOk: (json['smoke_ok'] as bool?) ?? false,
      );

  final String agentInstanceId;
  final bool smokeOk;
}

/// `POST /v1/agents/:id/start` request body.
/// Mobile always sends channel='inapp' per Phase 23 D-28.
class StartRequest {
  const StartRequest({
    this.channel = 'inapp',
    this.channelInputs = const <String, dynamic>{},
  });

  final String channel;
  final Map<String, dynamic> channelInputs;

  Map<String, dynamic> toJson() => {
        'channel': channel,
        'channel_inputs': channelInputs,
      };
}

/// `POST /v1/agents/:id/start` response body.
class StartResponse {
  const StartResponse({required this.containerId, required this.status});

  factory StartResponse.fromJson(Map<String, dynamic> json) => StartResponse(
        containerId: (json['container_id'] as String?) ?? '',
        status: (json['status'] as String?) ?? 'unknown',
      );

  final String containerId;
  final String status;
}

/// `POST /v1/agents/:id/messages` 202 response body (Phase 23 D-09).
class MessagePostAck {
  const MessagePostAck({
    required this.messageId,
    required this.status,
    required this.queuedAt,
  });

  factory MessagePostAck.fromJson(Map<String, dynamic> json) => MessagePostAck(
        messageId: json['message_id'] as String,
        status: (json['status'] as String?) ?? 'queued',
        queuedAt: (json['queued_at'] as String?) ?? '',
      );

  final String messageId;
  final String status;
  final String queuedAt;
}

/// One row of `GET /v1/agents/:id/messages` history (Phase 23 D-03/D-04).
///
/// Phase 22c.3 returns `inapp_message_id` (one inapp_messages row produces
/// both the user + assistant ChatMessage rows; both share the same id).
/// `kind` is currently always `"message"` and is forwarded for forward-compat.
class ChatMessage {
  const ChatMessage({
    required this.inappMessageId,
    required this.role,
    required this.content,
    required this.createdAt,
    this.kind,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        inappMessageId: json['inapp_message_id'] as String,
        role: json['role'] as String,
        content: json['content'] as String,
        createdAt: json['created_at'] as String,
        kind: json['kind'] as String?,
      );

  final String inappMessageId;
  final String role; // 'user' | 'assistant'
  final String content;
  final String createdAt;
  final String? kind;
}

/// `GET /v1/agents/:id/messages?limit=N` response body.
class MessagesPage {
  const MessagesPage({required this.messages});

  factory MessagesPage.fromJson(Map<String, dynamic> json) {
    final raw = (json['messages'] as List<dynamic>? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return MessagesPage(
      messages: raw.map(ChatMessage.fromJson).toList(growable: false),
    );
  }

  final List<ChatMessage> messages;
}

/// `GET /v1/agents` row.
class AgentSummary {
  const AgentSummary({
    required this.id,
    required this.name,
    required this.recipeName,
    required this.model,
    required this.status,
    required this.createdAt,
    this.lastActivity,
  });

  factory AgentSummary.fromJson(Map<String, dynamic> json) => AgentSummary(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? '',
        recipeName: json['recipe_name'] as String,
        model: (json['model'] as String?) ?? '',
        status: json['status'] as String,
        createdAt: json['created_at'] as String,
        lastActivity: json['last_activity'] as String?,
      );

  final String id;
  final String name;
  final String recipeName;
  final String model;
  final String status;
  final String createdAt;
  final String? lastActivity;
}

/// `GET /v1/recipes` row.
class Recipe {
  const Recipe({
    required this.name,
    required this.channelsSupported,
  });

  factory Recipe.fromJson(Map<String, dynamic> json) => Recipe(
        name: json['name'] as String,
        channelsSupported:
            ((json['channels_supported'] as List<dynamic>?) ?? <dynamic>[])
                .map((e) => e as String)
                .toList(growable: false),
      );

  final String name;
  final List<String> channelsSupported;
}

/// `GET /v1/models` row (OpenRouter passthrough).
class OpenRouterModel {
  const OpenRouterModel({required this.id, required this.name});

  factory OpenRouterModel.fromJson(Map<String, dynamic> json) =>
      OpenRouterModel(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? json['id'] as String,
      );

  final String id;
  final String name;
}

/// `GET /v1/users/me` (Phase 22c-05).
class SessionUser {
  const SessionUser({
    required this.id,
    required this.email,
    required this.displayName,
    required this.provider,
    required this.createdAt,
    this.avatarUrl,
  });

  factory SessionUser.fromJson(Map<String, dynamic> json) => SessionUser(
        id: json['id'] as String,
        email: (json['email'] as String?) ?? '',
        displayName: (json['display_name'] as String?) ?? '',
        avatarUrl: json['avatar_url'] as String?,
        provider: (json['provider'] as String?) ?? '',
        createdAt: (json['created_at'] as String?) ?? '',
      );

  final String id;
  final String email;
  final String displayName;
  final String? avatarUrl;
  final String provider;
  final String createdAt;
}
