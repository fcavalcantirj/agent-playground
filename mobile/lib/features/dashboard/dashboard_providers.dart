// Phase 25 Wave 2 — Dashboard providers (D-12 / D-13 / D-17).
//
// Three providers:
//   - agentsListProvider: AsyncNotifier fetch of GET /v1/agents. Re-fetched
//     on (a) mount, (b) AppLifecycleState.resumed (D-12), and (c) explicit
//     invalidation from the pull-to-refresh gesture (D-12). Sorted
//     last_activity desc per D-13. Uses a CancelToken concurrency guard per
//     Pitfall #8 in 25-RESEARCH.md so a lifecycle re-entry while a
//     pull-to-refresh fetch is inflight cancels the older request rather
//     than letting two responses race for the UI.
//
//   - recipesProvider: cached AsyncValue of GET /v1/recipes. Source for the
//     AsciiAgentBanner names stream on the Dashboard empty-state (D-17).
//     Wave 3 wizard refetches per open; for Wave 2 the cached value is
//     sufficient.
//
//   - recipeNamesStreamProvider: Stream<List<String>> derived from
//     recipesProvider so AsciiAgentBanner stays a pure widget that consumes
//     a stream (UI-SPEC §Component 3 line 314).
//
// Authoring style: riverpod_generator (matches `core/api/providers.dart`
// shape). The test that drives this file overrides `apiClientProvider` so
// the generated AgentsList can be exercised against http_mock_adapter
// without touching codegen output.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'dashboard_providers.g.dart';

// #16 — keepAlive prevents the autoDispose disposal race when navigating
// /chat/:id → /dashboard via context.go (sibling-route swap). Without this,
// chat tear-down drops the only listener, autoDispose schedules the
// provider for disposal, and the dashboard's first frame after remount
// can flicker stale state via AsyncLoading.copyWithPrevious(stopped).
// Memory cost is trivial (a list of agent summaries — same data the
// dashboard already holds in widget state). Matches the precedent set
// by `recipesProvider` two declarations below.
@Riverpod(keepAlive: true)
class AgentsList extends _$AgentsList {
  CancelToken? _cancel;

  @override
  Future<List<AgentSummary>> build() async {
    // Pitfall #8 — cancel any inflight request from a prior build cycle so a
    // mid-fetch lifecycle resume + pull-to-refresh do not race.
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('AgentsList disposed');
      }
    });

    // D-12 — refetch on AppLifecycleState.resumed. ref.listen survives
    // across build() runs (registered fresh each build per Riverpod
    // semantics).
    // ignore: cascade_invocations
    ref.listen<AppLifecycleState>(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.agentsList(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => _sortByLastActivityDesc(value),
      // ApiError is the typed envelope (Phase 24 D-32); Riverpod's AsyncValue
      // turns it into AsyncError so widget-level Result.match analogs work.
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }

  /// D-13 — most recent first. Null `lastActivity` falls to bottom.
  static List<AgentSummary> _sortByLastActivityDesc(List<AgentSummary> list) {
    return List<AgentSummary>.of(list)
      ..sort((a, b) {
        final aa = a.lastActivity ?? '';
        final bb = b.lastActivity ?? '';
        return bb.compareTo(aa);
      });
  }
}

/// Cached `GET /v1/recipes`. Drives AsciiAgentBanner names per D-17.
@Riverpod(keepAlive: true)
Future<List<Recipe>> recipes(Ref ref) async {
  final api = ref.watch(apiClientProvider);
  final r = await api.recipes();
  return switch (r) {
    Ok(:final value) => value,
    // ApiError is the typed envelope (Phase 24 D-32) — see AgentsList.build.
    // ignore: only_throw_errors
    Err(:final error) => throw error,
  };
}

/// `Stream<List<String>>` projection of recipe names — AsciiAgentBanner
/// consumes a Stream so the widget stays pure (UI-SPEC line 314).
///
/// Single-emit by design — recipesProvider invalidation re-runs this
/// builder.
@riverpod
Stream<List<String>> recipeNamesStream(Ref ref) async* {
  final list = await ref.watch(recipesProvider.future);
  yield list.map((r) => r.name).toList(growable: false);
}
