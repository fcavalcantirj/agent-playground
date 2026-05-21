"""Classify INVOKE_FAIL stderr_tail into a friendly (code, detail, hint) tuple.

When a recipe's smoke run fails because the upstream LLM provider rejected
the request, the raw stderr is something like::

    docker run exit 1 [stderr]: ... Non-retryable client error: Error code: 401
    - {'error': {'message': 'Missing Authentication header', 'code': 401}}

The user can't act on that. But the error envelope is a stable, documented
shape from each provider, so we can pattern-match the few canonical cases
and emit a one-line friendly message + an action hint.

Coverage (2026-05-21):
  * OpenRouter — auth missing / auth invalid / credits low / model unknown / rate-limited
  * Anthropic — authentication_error / permission_error / not_found_error /
    rate_limit_error / overloaded_error / credit_balance_too_low
  * OpenAI — invalid_api_key / insufficient_quota / model_not_found / rate_limit_exceeded

Provider is inferred from the model slug — matches what hermes_cli's
runtime_provider does internally:
  * starts with ``claude-`` → anthropic direct
  * starts with ``gpt-`` / ``o1-`` → openai direct
  * everything else (incl. ``google/gemini-*``, ``meta/llama-*``,
    ``provider/model``-shaped slugs) → openrouter

Unmatched stderr returns None — the caller still writes the raw stderr to
``runs.stderr_tail`` and tags the Sentry event ``classified=unclassified``
so we discover new patterns in the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunFailureClass:
    """Classification result for an upstream INVOKE_FAIL.

    Attributes:
      code: Stable machine code for the failure family (e.g. ``upstream_auth_missing``).
            Same string is used as Sentry tag ``classified`` and as a future
            i18n-key root.
      detail: 1-line user-facing message ending in a period.
      hint: 1-line actionable next step (URL allowed), or None for "no clear hint".
    """

    code: str
    detail: str
    hint: str | None


# --- Provider inference ----------------------------------------------------

def _provider_for(model: str | None) -> str:
    """Return ``openrouter`` | ``anthropic`` | ``openai`` for a model slug.

    Defaults to ``openrouter`` when ``model`` is None or empty, matching the
    fact that all current recipes route through OpenRouter unless the model
    slug screams Anthropic/OpenAI directly.
    """
    if not model:
        return "openrouter"
    m = model.lower()
    if m.startswith("claude-"):
        return "anthropic"
    if m.startswith("gpt-") or m.startswith("o1-") or m.startswith("o3-"):
        return "openai"
    return "openrouter"


# --- OpenRouter -----------------------------------------------------------

def _classify_openrouter(stderr_lower: str) -> RunFailureClass | None:
    # Order matters — more-specific matches first.
    if "missing authentication header" in stderr_lower:
        return RunFailureClass(
            code="upstream_auth_missing",
            detail="No OpenRouter API key was sent with the request.",
            hint=(
                "Tap Edit, go to Model + Key, and paste your "
                "`sk-or-v1-…` key from https://openrouter.ai/keys."
            ),
        )
    if "no auth credentials found" in stderr_lower:
        return RunFailureClass(
            code="upstream_auth_invalid",
            detail="OpenRouter rejected your API key.",
            hint=(
                "Generate a fresh key at https://openrouter.ai/keys and "
                "re-paste it on the Model + Key step."
            ),
        )
    if "user not found" in stderr_lower or (
        "invalid api key" in stderr_lower and "openrouter" in stderr_lower
    ):
        return RunFailureClass(
            code="upstream_auth_invalid",
            detail="Your OpenRouter API key isn't valid.",
            hint=(
                "Generate a fresh key at https://openrouter.ai/keys and "
                "re-paste it on the Model + Key step."
            ),
        )
    if "402" in stderr_lower and "credits" in stderr_lower:
        return RunFailureClass(
            code="upstream_credit_low",
            detail="Your OpenRouter account has no credits left.",
            hint="Top up at https://openrouter.ai/credits and tap Retry.",
        )
    if "insufficient_quota" in stderr_lower:
        return RunFailureClass(
            code="upstream_credit_low",
            detail="OpenRouter says your account is out of quota.",
            hint="Top up at https://openrouter.ai/credits and tap Retry.",
        )
    if "model_not_found" in stderr_lower or "is not a valid model id" in stderr_lower:
        return RunFailureClass(
            code="upstream_model_unknown",
            detail="That model isn't available on OpenRouter right now.",
            hint="Tap Edit and pick a different model on the Model step.",
        )
    if (
        "rate_limit" in stderr_lower
        or "rate limit" in stderr_lower
        or "error code: 429" in stderr_lower
    ):
        return RunFailureClass(
            code="upstream_rate_limited",
            detail="OpenRouter rate-limited the request.",
            hint="Wait a minute and tap Retry.",
        )
    return None


# --- Anthropic direct -----------------------------------------------------

def _classify_anthropic(stderr_lower: str) -> RunFailureClass | None:
    if "authentication_error" in stderr_lower or "invalid x-api-key" in stderr_lower:
        return RunFailureClass(
            code="upstream_auth_invalid",
            detail="Anthropic rejected your API key.",
            hint=(
                "Generate a fresh key at https://console.anthropic.com/settings/keys "
                "and re-paste it on the Model + Key step."
            ),
        )
    if "permission_error" in stderr_lower:
        return RunFailureClass(
            code="upstream_permission",
            detail="Your Anthropic key isn't permitted for this model.",
            hint=(
                "Check the key's allowed models at "
                "https://console.anthropic.com/settings/keys."
            ),
        )
    if "credit_balance_too_low" in stderr_lower:
        return RunFailureClass(
            code="upstream_credit_low",
            detail="Your Anthropic account is out of credit.",
            hint="Top up at https://console.anthropic.com/billing and tap Retry.",
        )
    if "not_found_error" in stderr_lower:
        return RunFailureClass(
            code="upstream_model_unknown",
            detail="That Claude model isn't available right now.",
            hint="Tap Edit and pick a different model.",
        )
    if "rate_limit_error" in stderr_lower:
        return RunFailureClass(
            code="upstream_rate_limited",
            detail="Anthropic rate-limited the request.",
            hint="Wait a minute and tap Retry.",
        )
    if "overloaded_error" in stderr_lower:
        return RunFailureClass(
            code="upstream_overloaded",
            detail="Anthropic is overloaded right now.",
            hint="Wait a minute and tap Retry.",
        )
    return None


# --- OpenAI direct --------------------------------------------------------

def _classify_openai(stderr_lower: str) -> RunFailureClass | None:
    if "invalid_api_key" in stderr_lower or "incorrect api key" in stderr_lower:
        return RunFailureClass(
            code="upstream_auth_invalid",
            detail="OpenAI rejected your API key.",
            hint=(
                "Generate a fresh key at https://platform.openai.com/api-keys "
                "and re-paste it on the Model + Key step."
            ),
        )
    if "insufficient_quota" in stderr_lower:
        return RunFailureClass(
            code="upstream_credit_low",
            detail="Your OpenAI account is out of quota.",
            hint="Top up at https://platform.openai.com/account/billing and tap Retry.",
        )
    if "model_not_found" in stderr_lower:
        return RunFailureClass(
            code="upstream_model_unknown",
            detail="That OpenAI model isn't available to your key.",
            hint="Tap Edit and pick a different model.",
        )
    if "rate_limit_exceeded" in stderr_lower:
        return RunFailureClass(
            code="upstream_rate_limited",
            detail="OpenAI rate-limited the request.",
            hint="Wait a minute and tap Retry.",
        )
    return None


# --- Public entry ---------------------------------------------------------

def classify_invoke_fail(
    stderr_tail: str | None,
    model: str | None,
) -> RunFailureClass | None:
    """Pattern-match ``stderr_tail`` into a known upstream failure family.

    Returns None when the stderr doesn't match any known pattern — caller
    keeps the raw stderr in the response (truncated) and tags the Sentry
    event ``classified=unclassified``.
    """
    if not stderr_tail:
        return None
    sl = stderr_tail.lower()
    provider = _provider_for(model)

    # Try the inferred provider first; fall through to others so a
    # mis-inferred provider doesn't lose the match (e.g. user picked an
    # OpenRouter-routed claude-3.5-sonnet — we'd infer anthropic but the
    # error envelope is OpenRouter's).
    chain = {
        "openrouter": (_classify_openrouter, _classify_anthropic, _classify_openai),
        "anthropic": (_classify_anthropic, _classify_openrouter, _classify_openai),
        "openai": (_classify_openai, _classify_openrouter, _classify_anthropic),
    }[provider]
    for fn in chain:
        result = fn(sl)
        if result is not None:
            return result
    return None
