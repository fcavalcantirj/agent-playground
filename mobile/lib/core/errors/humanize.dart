// Mobile-side fallback for run_failure_classifier.py.
//
// The api_server's classify_invoke_fail() already populates the friendly
// detail (+ hint) on every smoke FAIL it recognizes. This Dart twin is
// defense-in-depth: if a future api_server build hasn't shipped yet, or
// the user is talking to an older deploy, the wizard still shows the
// friendly copy instead of a raw docker stderr blob.
//
// Match shape mirrors run_failure_classifier.py exactly so any new pattern
// added there can be ported here with a one-to-one edit.

class HumanizedFailure {
  const HumanizedFailure({
    required this.code,
    required this.detail,
    this.hint,
  });

  /// Stable family tag (`upstream_auth_missing`, `upstream_credit_low`, …).
  /// Also used as the Sentry `classified` tag.
  final String code;

  /// 1-line user-facing message ending in a period.
  final String detail;

  /// 1-line actionable next step (URL allowed) or null.
  final String? hint;
}

/// Pattern-match an upstream failure stderr into a friendly message.
///
/// Returns null when no pattern matches. Caller should fall back to
/// showing the raw stderr (truncated, with a "Show details" affordance).
HumanizedFailure? humanizeStderr(String? stderrTail, String? modelSlug) {
  if (stderrTail == null || stderrTail.isEmpty) return null;
  final sl = stderrTail.toLowerCase();
  final provider = _providerFor(modelSlug);
  final chain = switch (provider) {
    'anthropic' => const [_classifyAnthropic, _classifyOpenRouter, _classifyOpenAI],
    'openai' => const [_classifyOpenAI, _classifyOpenRouter, _classifyAnthropic],
    _ => const [_classifyOpenRouter, _classifyAnthropic, _classifyOpenAI],
  };
  for (final fn in chain) {
    final result = fn(sl);
    if (result != null) return result;
  }
  return null;
}

String _providerFor(String? model) {
  if (model == null || model.isEmpty) return 'openrouter';
  final m = model.toLowerCase();
  if (m.startsWith('claude-')) return 'anthropic';
  if (m.startsWith('gpt-') || m.startsWith('o1-') || m.startsWith('o3-')) {
    return 'openai';
  }
  return 'openrouter';
}

HumanizedFailure? _classifyOpenRouter(String sl) {
  if (sl.contains('missing authentication header')) {
    return const HumanizedFailure(
      code: 'upstream_auth_missing',
      detail: 'No OpenRouter API key was sent with the request.',
      hint: 'Tap Edit, go to Model + Key, and paste your `sk-or-v1-…` key '
          'from https://openrouter.ai/keys.',
    );
  }
  if (sl.contains('no auth credentials found')) {
    return const HumanizedFailure(
      code: 'upstream_auth_invalid',
      detail: 'OpenRouter rejected your API key.',
      hint: 'Generate a fresh key at https://openrouter.ai/keys and re-paste '
          'it on the Model + Key step.',
    );
  }
  if (sl.contains('user not found') ||
      (sl.contains('invalid api key') && sl.contains('openrouter'))) {
    return const HumanizedFailure(
      code: 'upstream_auth_invalid',
      detail: "Your OpenRouter API key isn't valid.",
      hint: 'Generate a fresh key at https://openrouter.ai/keys and re-paste '
          'it on the Model + Key step.',
    );
  }
  if (sl.contains('402') && sl.contains('credits')) {
    return const HumanizedFailure(
      code: 'upstream_credit_low',
      detail: 'Your OpenRouter account has no credits left.',
      hint: 'Top up at https://openrouter.ai/credits and tap Retry.',
    );
  }
  if (sl.contains('insufficient_quota')) {
    return const HumanizedFailure(
      code: 'upstream_credit_low',
      detail: 'OpenRouter says your account is out of quota.',
      hint: 'Top up at https://openrouter.ai/credits and tap Retry.',
    );
  }
  if (sl.contains('model_not_found') ||
      sl.contains('is not a valid model id')) {
    return const HumanizedFailure(
      code: 'upstream_model_unknown',
      detail: "That model isn't available on OpenRouter right now.",
      hint: 'Tap Edit and pick a different model on the Model step.',
    );
  }
  if (sl.contains('rate_limit') ||
      sl.contains('rate limit') ||
      sl.contains('error code: 429')) {
    return const HumanizedFailure(
      code: 'upstream_rate_limited',
      detail: 'OpenRouter rate-limited the request.',
      hint: 'Wait a minute and tap Retry.',
    );
  }
  return null;
}

HumanizedFailure? _classifyAnthropic(String sl) {
  if (sl.contains('authentication_error') || sl.contains('invalid x-api-key')) {
    return const HumanizedFailure(
      code: 'upstream_auth_invalid',
      detail: 'Anthropic rejected your API key.',
      hint: 'Generate a fresh key at https://console.anthropic.com/settings/keys '
          'and re-paste it on the Model + Key step.',
    );
  }
  if (sl.contains('permission_error')) {
    return const HumanizedFailure(
      code: 'upstream_permission',
      detail: "Your Anthropic key isn't permitted for this model.",
      hint: "Check the key's allowed models at "
          'https://console.anthropic.com/settings/keys.',
    );
  }
  if (sl.contains('credit_balance_too_low')) {
    return const HumanizedFailure(
      code: 'upstream_credit_low',
      detail: 'Your Anthropic account is out of credit.',
      hint: 'Top up at https://console.anthropic.com/billing and tap Retry.',
    );
  }
  if (sl.contains('not_found_error')) {
    return const HumanizedFailure(
      code: 'upstream_model_unknown',
      detail: "That Claude model isn't available right now.",
      hint: 'Tap Edit and pick a different model.',
    );
  }
  if (sl.contains('rate_limit_error')) {
    return const HumanizedFailure(
      code: 'upstream_rate_limited',
      detail: 'Anthropic rate-limited the request.',
      hint: 'Wait a minute and tap Retry.',
    );
  }
  if (sl.contains('overloaded_error')) {
    return const HumanizedFailure(
      code: 'upstream_overloaded',
      detail: 'Anthropic is overloaded right now.',
      hint: 'Wait a minute and tap Retry.',
    );
  }
  return null;
}

HumanizedFailure? _classifyOpenAI(String sl) {
  if (sl.contains('invalid_api_key') || sl.contains('incorrect api key')) {
    return const HumanizedFailure(
      code: 'upstream_auth_invalid',
      detail: 'OpenAI rejected your API key.',
      hint: 'Generate a fresh key at https://platform.openai.com/api-keys '
          'and re-paste it on the Model + Key step.',
    );
  }
  if (sl.contains('insufficient_quota')) {
    return const HumanizedFailure(
      code: 'upstream_credit_low',
      detail: 'Your OpenAI account is out of quota.',
      hint: 'Top up at https://platform.openai.com/account/billing '
          'and tap Retry.',
    );
  }
  if (sl.contains('model_not_found')) {
    return const HumanizedFailure(
      code: 'upstream_model_unknown',
      detail: "That OpenAI model isn't available to your key.",
      hint: 'Tap Edit and pick a different model.',
    );
  }
  if (sl.contains('rate_limit_exceeded')) {
    return const HumanizedFailure(
      code: 'upstream_rate_limited',
      detail: 'OpenAI rate-limited the request.',
      hint: 'Wait a minute and tap Retry.',
    );
  }
  return null;
}
