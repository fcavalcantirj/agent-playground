// Phase 25 Wave 3 plan 25-06 task 1 — multi-channel deploy orchestrator.
//
// Pure-Dart class. No widgets, no Riverpod. Mirror of
// frontend/components/playground-form.tsx lines 316-360 — the canonical
// 1×/runs + N×/start sequence (D-56). Pulled out of the widget so unit
// tests can mock the ApiClient and assert call sequence + cancellation +
// branching exhaustively without WidgetTester.
//
// Outcome variants (D-30 / D-56 / D-57 / D-58):
//   - success           — full deploy (inapp [+ telegram if requested]) PASS
//   - partialSuccess    — inapp PASS, telegram /start failed (D-58)
//   - smokeFail         — verdict != PASS at /v1/runs (D-30)
//   - runsError         — transport-level error before reaching verdict
//   - inappFail         — inapp /start failed (D-57); telegram never tried
//   - cancelled         — caller cancelled the CancelToken mid-sequence

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:dio/dio.dart';

/// Sealed result of a multi-channel deploy.
sealed class DeployOutcome {
  const DeployOutcome();
  const factory DeployOutcome.success({required String agentInstanceId}) =
      DeploySuccess;
  const factory DeployOutcome.partialSuccess({
    required String agentInstanceId,
    required String telegramFailReason,
    required Map<String, String> telegramInputs,
  }) = DeployPartialSuccess;
  const factory DeployOutcome.smokeFail({
    required String agentInstanceId,
    required String reason,
    String? stderrTail,
  }) = DeploySmokeFail;
  const factory DeployOutcome.runsError({required ApiError error}) =
      DeployRunsError;
  const factory DeployOutcome.inappFail({required ApiError error}) =
      DeployInappFail;
  const factory DeployOutcome.cancelled() = DeployCancelled;
}

final class DeploySuccess extends DeployOutcome {
  const DeploySuccess({required this.agentInstanceId});
  final String agentInstanceId;
}

final class DeployPartialSuccess extends DeployOutcome {
  const DeployPartialSuccess({
    required this.agentInstanceId,
    required this.telegramFailReason,
    required this.telegramInputs,
  });
  final String agentInstanceId;
  final String telegramFailReason;
  final Map<String, String> telegramInputs;
}

final class DeploySmokeFail extends DeployOutcome {
  const DeploySmokeFail({
    required this.agentInstanceId,
    required this.reason,
    this.stderrTail,
  });
  final String agentInstanceId;
  final String reason;
  // Raw stderr_tail from the runs row — surfaced in the wizard's
  // "Show details" affordance so power users / support can copy the
  // docker-level error without losing the friendly top-line copy.
  final String? stderrTail;
}

final class DeployRunsError extends DeployOutcome {
  const DeployRunsError({required this.error});
  final ApiError error;
}

final class DeployInappFail extends DeployOutcome {
  const DeployInappFail({required this.error});
  final ApiError error;
}

final class DeployCancelled extends DeployOutcome {
  const DeployCancelled();
}

/// Multi-channel deploy orchestrator (D-56). Owns NO widget state; the
/// caller (DeployStep) owns the CancelToken + UI side effects.
class DeployOrchestrator {
  // Constructor uses a public positional name so test subclasses can
  // forward via `super.api`; the underlying field is private to keep
  // the runtime API surface narrow.
  const DeployOrchestrator(ApiClient api) : _api = api;

  final ApiClient _api;

  /// Run the deploy sequence:
  ///   1. POST /v1/runs (smoke gate per Phase 23 D-22).
  ///   2. If smoke PASS: POST /v1/agents/{id}/start with channel='inapp'.
  ///   3. If [telegramEnabled] AND step 2 succeeded: POST /start with
  ///      channel='telegram' and [telegramInputs].
  ///
  /// Errors short-circuit per D-30 / D-57 / D-58. CancelToken is checked
  /// between calls — if cancelled, returns [DeployCancelled].
  Future<DeployOutcome> deploy({
    required String recipeName,
    required String modelId,
    required String agentName,
    required String byokKey,
    required bool telegramEnabled,
    Map<String, String> telegramInputs = const {},
    CancelToken? cancelToken,
  }) async {
    // ---- Step 1: POST /v1/runs (smoke gate per Phase 23 D-22) ------------
    final runsRes = await _api.runs(
      body: RunRequest(
        recipeName: recipeName,
        model: modelId,
        agentName: agentName,
      ),
      byokOpenRouterKey: byokKey,
      cancelToken: cancelToken,
    );
    if (cancelToken?.isCancelled ?? false) {
      return const DeployOutcome.cancelled();
    }
    switch (runsRes) {
      case Err(:final error):
        return DeployOutcome.runsError(error: error);
      case Ok(:final value):
        if (!value.smokeOk) {
          // D-30: surface the server-side detail so the user sees the
          // actual failure cause (e.g. "Unable to find image locally")
          // instead of a generic "verdict != PASS". Falls back to the
          // category + verdict pair when detail is null.
          final reason = value.detail ??
              [
                if (value.verdict != null) 'verdict=${value.verdict}',
                if (value.category != null) 'category=${value.category}',
              ].join(', ');
          return DeployOutcome.smokeFail(
            agentInstanceId: value.agentInstanceId,
            reason: reason.isEmpty ? 'verdict != PASS' : reason,
            stderrTail: value.stderrTail,
          );
        }
        final agentId = value.agentInstanceId;

        // ---- Step 2: POST /start with channel='inapp' (D-56 always) ------
        final inappRes = await _api.start(
          agentId: agentId,
          byokOpenRouterKey: byokKey,
          cancelToken: cancelToken,
        );
        if (cancelToken?.isCancelled ?? false) {
          return const DeployOutcome.cancelled();
        }
        if (inappRes is Err<StartResponse>) {
          return DeployOutcome.inappFail(error: inappRes.error);
        }

        // ---- Step 3: optional Telegram (D-58 partial-success path) -------
        if (telegramEnabled) {
          final tgRes = await _api.start(
            agentId: agentId,
            body: StartRequest(
              channel: 'telegram',
              channelInputs: Map<String, dynamic>.from(telegramInputs),
            ),
            byokOpenRouterKey: byokKey,
            cancelToken: cancelToken,
          );
          if (cancelToken?.isCancelled ?? false) {
            return const DeployOutcome.cancelled();
          }
          if (tgRes is Err<StartResponse>) {
            return DeployOutcome.partialSuccess(
              agentInstanceId: agentId,
              telegramFailReason: tgRes.error.message,
              telegramInputs: Map<String, String>.from(telegramInputs),
            );
          }
        }
        return DeployOutcome.success(agentInstanceId: agentId);
    }
  }
}
