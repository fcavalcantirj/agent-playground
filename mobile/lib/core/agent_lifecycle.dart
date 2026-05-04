// Cross-screen restart helper.
//
// Pure async function — does the BYOK lookup + POST /v1/agents/:id/start
// dance once, called from BOTH the chat-screen RestartBanner (commit
// d3c8863) and the dashboard 3-dot menu's Restart entry (this commit).
// Mirrors the precedent set by `mobile/lib/features/new_agent/
// deploy_orchestrator.dart` — pure logic, sealed Outcome, no widget
// state. Each caller wraps it in its own setState/SnackBar shell since
// the inflight UX differs per surface (chat = full RestartBanner with
// elapsed counter; dashboard = small per-row spinner).
//
// Why centralised: the BYOK-lookup walks
// `recipeDetail.channelProviderCompat['inapp'].supported` and matches
// against `secureStorage.readByokKey(provider)`. That contract is tied
// to the api_server's recipes_loader synthesizer (commit 925a1bf) AND
// the wizard's `_byokConfig.storageProvider` (model_step.dart:55). Two
// callers means two drift surfaces — extract once and the next backend
// contract change touches one site.

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

/// Look up the BYOK key for [agent] from [storage], then call
/// [api].start(...) with it. Returns [RestartOk] / [RestartNoBYOK] /
/// [RestartFailed] — never throws.
///
/// Lookup precedence: walk `recipeDetail.channelProviderCompat['inapp']
/// .supported` (typically `['openrouter']` or `['anthropic']`); first
/// provider with a non-empty `byok_key_<provider>` value wins. Falls
/// back to a direct openrouter/anthropic probe when `provider_compat`
/// is missing (defense vs an old api_server that didn't yet ship the
/// recipes_loader synthesizer at commit 925a1bf).
Future<RestartOutcome> restartAgent({
  required AgentSummary agent,
  required ApiClient api,
  required SecureStorage storage,
}) async {
  String? byokKey;

  // 1. Pull recipe metadata to learn which providers count.
  final detailRes = await api.recipeDetail(name: agent.recipeName);
  if (detailRes case Ok<RecipeDetail>(value: final detail)) {
    final compat = detail.channelProviderCompat['inapp'];
    if (compat != null) {
      for (final provider in compat.supported) {
        final k = await storage.readByokKey(provider);
        if (k != null && k.isNotEmpty) {
          byokKey = k;
          break;
        }
      }
    }
  }

  // 2. Defensive fallback — try the two known providers if the recipe
  //    detail call failed OR the response had no provider_compat. Costs
  //    two keychain reads on the cold path; never on the hot path
  //    (post-925a1bf the synthesizer guarantees provider_compat).
  if (byokKey == null || byokKey.isEmpty) {
    for (final provider in const ['openrouter', 'anthropic']) {
      final k = await storage.readByokKey(provider);
      if (k != null && k.isNotEmpty) {
        byokKey = k;
        break;
      }
    }
  }

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
