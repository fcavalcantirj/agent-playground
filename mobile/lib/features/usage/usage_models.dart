// Phase 27 Change 3b Wave 2 — Dart DTOs for the BYOK usage endpoints.
//
// Mirrors the FastAPI response models in
// api_server/src/api_server/routes/usage.py. USD values are
// **strings** (D-14): the server returns NUMERIC(14,8) coerced to JSON
// string, so the client never deserializes USD into a double (precision
// loss across language boundaries — Dart's double, JS Number).
//
// Hand-written fromJson per Phase 24 D-34 (codegen restricted to
// riverpod_generator only — no json_serializable / build_runner JSON
// codegen). Defensive on additive backend fields: missing keys yield
// sane defaults (0 / "0" / null) rather than crashing.

class UsageSummary {
  const UsageSummary({
    required this.totalUsd,
    required this.messageCount,
    required this.byAgent,
  });

  factory UsageSummary.fromJson(Map<String, dynamic> json) => UsageSummary(
        totalUsd: (json['total_usd'] as String?) ?? '0',
        messageCount: (json['message_count'] as int?) ?? 0,
        byAgent: ((json['by_agent'] as List<dynamic>?) ?? const <dynamic>[])
            .map((e) => AgentBreakdownEntry.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
      );

  final String totalUsd;
  final int messageCount;
  final List<AgentBreakdownEntry> byAgent;
}

class AgentBreakdownEntry {
  const AgentBreakdownEntry({
    required this.agentId,
    required this.agentName,
    required this.recipeName,
    required this.model,
    required this.costUsd,
    required this.messageCount,
    this.lastActivity,
  });

  factory AgentBreakdownEntry.fromJson(Map<String, dynamic> json) =>
      AgentBreakdownEntry(
        agentId: json['agent_id'] as String,
        agentName: json['agent_name'] as String,
        recipeName: json['recipe_name'] as String,
        model: json['model'] as String,
        costUsd: (json['cost_usd'] as String?) ?? '0',
        messageCount: (json['message_count'] as int?) ?? 0,
        lastActivity: json['last_activity'] as String?,
      );

  final String agentId;
  final String agentName;
  final String recipeName;
  final String model;
  final String costUsd;
  final int messageCount;

  /// ISO-8601 UTC string from the server, or null when the agent has
  /// no recorded activity yet.
  final String? lastActivity;
}

class AgentCumulative {
  const AgentCumulative({
    required this.inputTokens,
    required this.outputTokens,
    required this.cacheReadTokens,
    required this.cacheCreationTokens,
    required this.costUsd,
    required this.messageCount,
    this.lastActivity,
  });

  factory AgentCumulative.fromJson(Map<String, dynamic> json) =>
      AgentCumulative(
        inputTokens: (json['input_tokens'] as int?) ?? 0,
        outputTokens: (json['output_tokens'] as int?) ?? 0,
        cacheReadTokens: (json['cache_read_tokens'] as int?) ?? 0,
        cacheCreationTokens: (json['cache_creation_tokens'] as int?) ?? 0,
        costUsd: (json['cost_usd'] as String?) ?? '0',
        messageCount: (json['message_count'] as int?) ?? 0,
        lastActivity: json['last_activity'] as String?,
      );

  final int inputTokens;
  final int outputTokens;
  final int cacheReadTokens;
  final int cacheCreationTokens;
  final String costUsd;
  final int messageCount;
  final String? lastActivity;
}

class AgentSeriesEntry {
  const AgentSeriesEntry({
    required this.day,
    required this.costUsd,
    required this.tokens,
    required this.messageCount,
  });

  factory AgentSeriesEntry.fromJson(Map<String, dynamic> json) =>
      AgentSeriesEntry(
        // Server returns ISO date "YYYY-MM-DD" — keep as string here so
        // the chart layer can pick its own DateTime parsing strategy.
        day: json['day'] as String,
        costUsd: (json['cost_usd'] as String?) ?? '0',
        tokens: (json['tokens'] as int?) ?? 0,
        messageCount: (json['message_count'] as int?) ?? 0,
      );

  final String day;
  final String costUsd;
  final int tokens;
  final int messageCount;
}

class AgentUsageData {
  const AgentUsageData({
    required this.agentId,
    required this.cumulative,
    required this.series7d,
    required this.series30d,
  });

  factory AgentUsageData.fromJson(Map<String, dynamic> json) => AgentUsageData(
        agentId: json['agent_id'] as String,
        cumulative: AgentCumulative.fromJson(
          json['cumulative'] as Map<String, dynamic>,
        ),
        series7d:
            ((json['series_7d'] as List<dynamic>?) ?? const <dynamic>[])
                .map(
                  (e) => AgentSeriesEntry.fromJson(e as Map<String, dynamic>),
                )
                .toList(growable: false),
        series30d:
            ((json['series_30d'] as List<dynamic>?) ?? const <dynamic>[])
                .map(
                  (e) => AgentSeriesEntry.fromJson(e as Map<String, dynamic>),
                )
                .toList(growable: false),
      );

  final String agentId;
  final AgentCumulative cumulative;
  final List<AgentSeriesEntry> series7d;
  final List<AgentSeriesEntry> series30d;
}
