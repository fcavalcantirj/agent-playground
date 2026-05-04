// Cross-screen agent-lifecycle helpers.
//
// Pure async functions — do the BYOK lookup + POST /v1/agents/:id/{start,
// stop} dance once, called from BOTH the chat-screen banners + the
// dashboard 3-dot menu. Mirrors the precedent set by
// `mobile/lib/features/new_agent/deploy_orchestrator.dart` — pure logic,
// sealed Outcome, no widget state. Each caller wraps it in its own
// setState/SnackBar shell since the inflight UX differs per surface
// (chat = full RestartBanner with elapsed counter; dashboard = small
// per-row spinner).
//
// Why centralised: the BYOK-lookup walks
// `recipeDetail.channelProviderCompat['inapp'].supported` and matches
// against `secureStorage.readByokKey(provider)`. That contract is tied
// to the api_server's recipes_loader synthesizer (commit 925a1bf) AND
// the wizard's `_byokConfig.storageProvider` (model_step.dart:55). Two+
// callers means two+ drift surfaces — extract once and the next backend
// contract change touches one site.
//
// Why /stop also takes the BYOK key: api_server's stop_agent
// (api_server/src/api_server/routes/agent_lifecycle.py:614) requires
// the `Authorization: Bearer ...` prefix even though it never reads the
// value (Phase 21 placeholder for session-ownership). We send the same
// key the user typed during the wizard so a future Phase 21 contract
// change doesn't silently break (Agent 1 4-agent confirmation
// 2026-05-04).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';

/// Sealed result of a restart attempt. Callers `switch` on this to
/// pick the right SnackBar copy / state transition.
sealed class RestartOutcome {
  const RestartOutcome();
}

/// `/v1/agents/:id/start` returned 200 — the new container is up (or
/// at least the runner declared it ready). Caller should invalidate
/// `agentsListProvider` so the agent's `status` flips to `running`.
final class RestartOk extends RestartOutcome {
  const RestartOk();
}

/// No BYOK key found in secure storage for any provider declared in
/// the recipe's `channels.inapp.provider_compat.supported` list. The
/// user typed a key during the wizard — but on a fresh install (or
/// for a recipe deployed by a different account) the keychain is
/// empty. Caller should SnackBar pointing the user to re-deploy.
final class RestartNoBYOK extends RestartOutcome {
  const RestartNoBYOK();
}

/// `/v1/agents/:id/start` returned an error envelope (or transport
/// failed). [error] carries the server-side message; caller surfaces it
/// in the SnackBar verbatim.
final class RestartFailed extends RestartOutcome {
  const RestartFailed(this.error);
  final ApiError error;
}

/// Sealed result of a stop attempt. Callers `switch` on this to pick
/// the right SnackBar copy / state transition.
sealed class StopOutcome {
  const StopOutcome();
}

/// `/v1/agents/:id/stop` returned 200 — the container was gracefully
/// shut down (or force-killed within the per-recipe budget). Caller
/// should invalidate `agentsListProvider` so the agent's `status`
/// flips to `stopped`.
final class StopOk extends StopOutcome {
  const StopOk();
}

/// `/v1/agents/:id/stop` returned 409 AGENT_NOT_RUNNING — the local
/// `agent.status` cache was stale; the container was already stopped
/// (or never started). Caller should soft-message + invalidate the
/// list so the row re-renders with status='stopped'.
final class StopAlreadyStopped extends StopOutcome {
  const StopAlreadyStopped();
}

/// Anything else: 401 (no Bearer / no BYOK), 404 (unowned), 502
/// (runner failure), or transport errors. Caller surfaces
/// [error.message] in the SnackBar verbatim — the synthetic NO_BYOK
/// case (no key in keychain) is folded in here with a hardcoded
/// message so the sealed type stays at 3 cases (Agent 2 nit).
final class StopFailed extends StopOutcome {
  const StopFailed(this.error);
  final ApiError error;
}

/// Internal: walk the BYOK-lookup chain shared by [restartAgent] and
/// [stopAgent]. Returns the first non-empty `byok_key_<provider>` value
/// — `recipeDetail.channelProviderCompat['inapp'].supported` first
/// (post-925a1bf synthesizer guarantees this is populated), falling
/// back to a direct openrouter/anthropic probe (defense vs an old
/// api_server). Returns null if no key is found.
Future<String?> _resolveByokKey({
  required AgentSummary agent,
  required ApiClient api,
  required SecureStorage storage,
}) async {
  // 1. Pull recipe metadata to learn which providers count.
  final detailRes = await api.recipeDetail(name: agent.recipeName);
  if (detailRes case Ok<RecipeDetail>(value: final detail)) {
    final compat = detail.channelProviderCompat['inapp'];
    if (compat != null) {
      for (final provider in compat.supported) {
        final k = await storage.readByokKey(provider);
        if (k != null && k.isNotEmpty) {
          return k;
        }
      }
    }
  }

  // 2. Defensive fallback — try the two known providers if the recipe
  //    detail call failed OR the response had no provider_compat.
  for (final provider in const ['openrouter', 'anthropic']) {
    final k = await storage.readByokKey(provider);
    if (k != null && k.isNotEmpty) {
      return k;
    }
  }

  return null;
}

/// Look up the BYOK key for [agent] from [storage], then call
/// [api].start(...) with it. Returns [RestartOk] / [RestartNoBYOK] /
/// [RestartFailed] — never throws.
Future<RestartOutcome> restartAgent({
  required AgentSummary agent,
  required ApiClient api,
  required SecureStorage storage,
}) async {
  final byokKey =
      await _resolveByokKey(agent: agent, api: api, storage: storage);
  if (byokKey == null || byokKey.isEmpty) {
    return const RestartNoBYOK();
  }
  final res = await api.start(
    agentId: agent.id,
    byokOpenRouterKey: byokKey,
  );
  return switch (res) {
    Ok<StartResponse>() => const RestartOk(),
    Err<StartResponse>(:final error) => RestartFailed(error),
  };
}

/// Look up the BYOK key for [agent] from [storage], then call
/// [api].stop(...) with it. Returns [StopOk] / [StopAlreadyStopped] /
/// [StopFailed] — never throws.
///
/// Server-side stop_agent ignores the Bearer value but requires the
/// header (Phase 21 placeholder). We pass the same key the user typed
/// at deploy time so a future Phase 21 contract change doesn't break
/// silently. If the keychain is empty (e.g. fresh install), surface
/// as [StopFailed] with a synthetic 'No BYOK key stored…' ApiError so
/// the caller can render the same 'Stop failed: <message>' SnackBar
/// for both real-error and missing-key cases.
Future<StopOutcome> stopAgent({
  required AgentSummary agent,
  required ApiClient api,
  required SecureStorage storage,
}) async {
  final byokKey =
      await _resolveByokKey(agent: agent, api: api, storage: storage);
  if (byokKey == null || byokKey.isEmpty) {
    return const StopFailed(
      ApiError(
        code: ErrorCode.unauthorized,
        message: 'No BYOK key stored for this agent — re-deploy via the '
            'wizard to enter your API key.',
      ),
    );
  }
  final res = await api.stop(
    agentId: agent.id,
    byokOpenRouterKey: byokKey,
  );
  return switch (res) {
    Ok<void>() => const StopOk(),
    Err<void>(:final error) =>
      error.code == ErrorCode.agentNotRunning
          ? const StopAlreadyStopped()
          : StopFailed(error),
  };
}
