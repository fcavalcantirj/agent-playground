// Phase 27 Change 3b Wave 2 — Riverpod providers for the BYOK ticker.
//
// Two providers:
//
//   - usageSummaryProvider: AsyncNotifier fetching GET /v1/usage/summary.
//     Auto-refreshes on (a) mount via ref.watch, (b) AppLifecycleState.resumed
//     (D-32 trigger #2). Trigger #3 (SSE inapp_outbound → invalidateSelf)
//     wires in during Wave 5 from chat_providers.dart.
//
//   - agentUsageProvider(agentId): family AsyncNotifier fetching
//     GET /v1/agents/:id/usage. Powers the per-agent breakdown screen.
//     Pull-to-refresh on the screen calls ref.invalidate(provider(id)).
//
// CancelToken concurrency guard mirrors AgentsList in
// dashboard_providers.dart (Pitfall #8): a build()-cycle cancel
// supersedes any inflight request when the user resumes mid-fetch.
//
// Throws ApiError on Err so AsyncValue carries it; widget code uses
// .when / .maybeWhen patterns. The tap-target ticker on cold load
// renders a neutral muted "$ —"; real error UX lives on the
// breakdown screen via RetryBanner.

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:agent_playground/features/usage/usage_models.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'usage_providers.g.dart';

@riverpod
class UsageSummaryNotifier extends _$UsageSummaryNotifier {
  CancelToken? _cancel;

  @override
  Future<UsageSummary> build() async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('UsageSummaryNotifier disposed');
      }
    });

    // Trigger #2 — refetch on app resume (D-32). ref.listen registers
    // fresh per build() per Riverpod semantics.
    // ignore: cascade_invocations
    ref.listen<AppLifecycleState>(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.usageSummary(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ApiError is the typed envelope (Phase 24 D-32); Riverpod's
      // AsyncValue turns it into AsyncError so .when/.maybeWhen can
      // surface it widget-side.
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }
}

@riverpod
class AgentUsageNotifier extends _$AgentUsageNotifier {
  CancelToken? _cancel;

  @override
  Future<AgentUsageData> build(String agentId) async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('AgentUsageNotifier disposed');
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.agentUsage(agentId, cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ApiError is the typed envelope — see UsageSummaryNotifier.build.
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }
}
