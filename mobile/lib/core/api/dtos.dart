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
    this.verdict,
    this.category,
    this.detail,
    this.stderrTail,
  });

  factory RunResponse.fromJson(Map<String, dynamic> json) => RunResponse(
        agentInstanceId: json['agent_instance_id'] as String,
        // Server returns RunResponse.verdict ("PASS"/"FAIL") — no smoke_ok
        // boolean. Wave 5 spike caught the mocks-vs-prod divergence;
        // unit fixtures fed `smoke_ok: true` directly. Map verdict→bool here.
        smokeOk: (json['verdict'] as String?) == 'PASS' ||
            ((json['smoke_ok'] as bool?) ?? false),
        verdict: json['verdict'] as String?,
        category: json['category'] as String?,
        detail: json['detail'] as String?,
        stderrTail: json['stderr_tail'] as String?,
      );

  final String agentInstanceId;
  final bool smokeOk;
  // Server-side smoke diagnostics; surfaced on the deploy fail card per
  // D-30 ("red-bordered card with verdict.detail"). Null when /runs was
  // a transport-error fallthrough — orchestrator falls back to a generic
  // string in that case.
  final String? verdict;
  final String? category;
  final String? detail;
  final String? stderrTail;
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
        // status is null on the wire when the agent has no container yet
        // (initial deploy crash, manually stopped, etc). Default to
        // 'stopped' so the dashboard renders a grey dot rather than
        // crashing. Wave 5 manual-app run caught this on a list with
        // mixed running / null-status agents from prior test sweeps.
        status: (json['status'] as String?) ?? 'stopped',
        createdAt: (json['created_at'] as String?) ?? '',
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
///
/// Phase 25 Wave 2 (D-25 / UI-SPEC) — extended with `description` so the
/// Wave-3 wizard's recipe-card UX can render a 1-line caption without
/// re-touching this DTO. Dashboard (Wave 2) only needs `name`, but the
/// extension lands here to keep dtos.dart additive across waves.
class Recipe {
  const Recipe({
    required this.name,
    required this.channelsSupported,
    this.description,
  });

  factory Recipe.fromJson(Map<String, dynamic> json) => Recipe(
        name: json['name'] as String,
        channelsSupported:
            ((json['channels_supported'] as List<dynamic>?) ?? <dynamic>[])
                .map((e) => e as String)
                .toList(growable: false),
        description: json['description'] as String?,
      );

  final String name;
  final List<String> channelsSupported;
  final String? description;
}

/// Per-channel user-input descriptor from `GET /v1/recipes/{name}` —
/// `recipe.channels.<id>.required_user_input[i]` /
/// `recipe.channels.<id>.optional_user_input[i]`.
///
/// Mirrors the pydantic `ChannelUserInput` model from api_server (D-54).
/// Permissive parser per 25-RESEARCH Open Question #3 — every optional
/// field defaults defensively so additive recipe schema changes don't
/// crash the wizard.
class ChannelUserInput {
  const ChannelUserInput({
    required this.env,
    required this.secret,
    this.hint,
    this.hintUrl,
    this.kind,
  });

  factory ChannelUserInput.fromJson(Map<String, dynamic> json) =>
      ChannelUserInput(
        env: json['env'] as String,
        secret: (json['secret'] as bool?) ?? false,
        hint: json['hint'] as String?,
        hintUrl: json['hint_url'] as String?,
        kind: json['kind'] as String?,
      );

  /// Env-var name (e.g. `TELEGRAM_BOT_TOKEN`). Doubles as the form-field
  /// label per UI-SPEC line 589 — Golden Rule #2 (no Dart-side label
  /// catalogs).
  final String env;

  /// Whether the value is sensitive — drives `obscureText: true` per D-34.
  final bool secret;

  /// Per-recipe caption rendered below the field (UI-SPEC line 591).
  final String? hint;

  /// Optional `hint_url` — when present, mobile renders a "get one here"
  /// link via `url_launcher` (D-46 https/http allow-list applies).
  final String? hintUrl;

  /// Optional `kind` discriminator (e.g. `telegram_numeric_id`). Reserved
  /// for future client-side input-type hints; not used in MVP.
  final String? kind;
}

/// Channel metadata from `recipe.channels.<id>` map. Drives the wizard's
/// dynamic-field render loop per D-54 + UI-SPEC §Step 3.
class RecipeChannelMeta {
  const RecipeChannelMeta({
    required this.requiredUserInput,
    required this.optionalUserInput,
  });

  factory RecipeChannelMeta.fromJson(Map<String, dynamic> json) =>
      RecipeChannelMeta(
        requiredUserInput:
            ((json['required_user_input'] as List<dynamic>?) ?? <dynamic>[])
                .cast<Map<String, dynamic>>()
                .map(ChannelUserInput.fromJson)
                .toList(growable: false),
        optionalUserInput:
            ((json['optional_user_input'] as List<dynamic>?) ?? <dynamic>[])
                .cast<Map<String, dynamic>>()
                .map(ChannelUserInput.fromJson)
                .toList(growable: false),
      );

  final List<ChannelUserInput> requiredUserInput;
  final List<ChannelUserInput> optionalUserInput;

  /// Render order = required first, then optional (UI-SPEC line 588).
  List<ChannelUserInput> get allInputs => [
        ...requiredUserInput,
        ...optionalUserInput,
      ];
}

/// Per-channel provider compatibility synthesized from
/// `recipe.channels.<id>.provider_compat` (api_server.services.recipes_loader
/// lines 128-143). Drives BYOK label-swap (D-32) — mobile checks
/// `deferred.contains('openrouter')` to flip the field label from
/// "OpenRouter API Key" to "Anthropic API Key".
class ChannelProviderCompat {
  const ChannelProviderCompat({
    required this.supported,
    required this.deferred,
  });

  factory ChannelProviderCompat.fromJson(Map<String, dynamic> json) =>
      ChannelProviderCompat(
        supported: ((json['supported'] as List<dynamic>?) ?? <dynamic>[])
            .map((e) => e as String)
            .toList(growable: false),
        deferred: ((json['deferred'] as List<dynamic>?) ?? <dynamic>[])
            .map((e) => e as String)
            .toList(growable: false),
      );

  final List<String> supported;
  final List<String> deferred;
}

/// `GET /v1/recipes/{name}` response body — full recipe YAML dict
/// (api_server.routes.recipes.RecipeDetailResponse passthrough).
///
/// Wire shape: `{"recipe": {...full yaml dict...}}`. The wrapper is
/// unwrapped here so callers receive a flat DTO. Tests may also pass the
/// already-unwrapped recipe dict directly.
///
/// `channelsSupported` is derived from `channels.keys()` for parity with
/// the list-endpoint summary (recipes_loader.py:124).
/// `channelProviderCompat` is synthesized by walking
/// `channels.<id>.provider_compat` (recipes_loader.py:128-143) so the
/// wizard's BYOK label-swap (D-32) and Telegram dynamic-fields (D-54) can
/// share the same DTO. Subclassing `Recipe` makes RecipeDetail a drop-in
/// replacement anywhere a `Recipe` is expected (e.g. wizard scope after
/// upgrading from list-summary).
class RecipeDetail extends Recipe {
  const RecipeDetail({
    required super.name,
    required super.channelsSupported,
    required this.channels,
    required this.channelProviderCompat,
    super.description,
  });

  factory RecipeDetail.fromJson(Map<String, dynamic> json) {
    // Unwrap `{"recipe": {...}}` envelope per
    // RecipeDetailResponse.model_dump(); fall back to the bare dict when
    // tests pass the inner shape directly.
    final r = (json['recipe'] is Map<String, dynamic>)
        ? json['recipe'] as Map<String, dynamic>
        : json;

    final channelsRaw =
        (r['channels'] as Map<String, dynamic>?) ?? const <String, dynamic>{};
    final channels = <String, RecipeChannelMeta>{};
    final compat = <String, ChannelProviderCompat>{};
    channelsRaw.forEach((cid, cinfoRaw) {
      final cinfo = cinfoRaw is Map<String, dynamic>
          ? cinfoRaw
          : const <String, dynamic>{};
      channels[cid] = RecipeChannelMeta.fromJson(cinfo);
      final pc = cinfo['provider_compat'];
      if (pc is Map<String, dynamic>) {
        compat[cid] = ChannelProviderCompat.fromJson(pc);
      }
    });

    return RecipeDetail(
      name: r['name'] as String,
      // Mirror recipes_loader.py:124 — channels_supported == channels.keys.
      channelsSupported: channels.keys.toList(growable: false),
      description: r['description'] as String?,
      channels: channels,
      channelProviderCompat: compat,
    );
  }

  /// `recipe.channels.<id>` map — drives the wizard's dynamic Telegram
  /// fields (D-54).
  final Map<String, RecipeChannelMeta> channels;

  /// Synthesized from `channels.<id>.provider_compat` (recipes_loader.py
  /// lines 128-143). Drives the BYOK label-swap (D-32). Channels with no
  /// `provider_compat` block are absent from this map.
  final Map<String, ChannelProviderCompat> channelProviderCompat;
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

/// `POST /v1/auth/{google,github}/mobile` response envelope —
/// `{session_id, expires_at, user: {...}}`. Mobile has no cookie jar
/// (Phase 23 D-23) so the session_id arrives in the body and must be
/// persisted to SecureStorage by the caller before the next API call.
class MobileAuthResponse {
  const MobileAuthResponse({
    required this.sessionId,
    required this.user,
    this.expiresAt,
  });

  factory MobileAuthResponse.fromJson(Map<String, dynamic> json) =>
      MobileAuthResponse(
        sessionId: json['session_id'] as String,
        expiresAt: json['expires_at'] as String?,
        user: SessionUser.fromJson(json['user'] as Map<String, dynamic>),
      );

  final String sessionId;
  final String? expiresAt;
  final SessionUser user;
}
