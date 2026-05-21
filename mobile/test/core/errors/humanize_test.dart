// Mirror test of api_server/tests/services/test_run_failure_classifier.py.
// Same fixtures, same expected codes — if the two ever diverge, that's a
// bug in one of the two pattern tables.

import 'package:agent_playground/core/errors/humanize.dart';
import 'package:flutter_test/flutter_test.dart';

const _pedroStderr =
    "docker run exit 1 [stderr]: 03:09:31 - root - ERROR [20260521_030929_6c3f53] "
    '- Non-retryable client error: Error code: 401 - '
    "{'error': {'message': 'Missing Authentication header', 'code': 401}}";

void main() {
  group('Provider inference (indirect via chain ordering)', () {
    test('OpenRouter is default when model is null', () {
      final r = humanizeStderr(_pedroStderr, null);
      expect(r, isNotNull);
      expect(r!.code, 'upstream_auth_missing');
    });

    test('provider/model slug routes to OpenRouter', () {
      final r = humanizeStderr(_pedroStderr, 'google/gemini-3.5-flash');
      expect(r!.code, 'upstream_auth_missing');
    });

    test('claude- prefix routes to Anthropic', () {
      final r = humanizeStderr(
        'anthropic.APIError: authentication_error: invalid x-api-key',
        'claude-3-5-sonnet-20241022',
      );
      expect(r!.code, 'upstream_auth_invalid');
    });

    test('gpt- prefix routes to OpenAI', () {
      final r = humanizeStderr(
        'openai.AuthenticationError: invalid_api_key: incorrect api key',
        'gpt-4o-mini',
      );
      expect(r!.code, 'upstream_auth_invalid');
    });
  });

  group('OpenRouter patterns', () {
    test("Pedro's exact stderr → upstream_auth_missing", () {
      final r = humanizeStderr(_pedroStderr, 'google/gemini-3.5-flash');
      expect(r, isNotNull);
      expect(r!.code, 'upstream_auth_missing');
      expect(r.detail, contains('No OpenRouter API key'));
      expect(r.hint, contains('openrouter.ai/keys'));
    });

    test('No auth credentials found → upstream_auth_invalid', () {
      final r = humanizeStderr(
        "Error code: 401 - {'error': {'message': 'No auth credentials found'}}",
        'anthropic/claude-3.5-sonnet',
      );
      expect(r!.code, 'upstream_auth_invalid');
    });

    test('User not found → upstream_auth_invalid', () {
      final r = humanizeStderr(
        "Error code: 401 - {'error': {'message': 'User not found'}}",
        'google/gemini-3.5-flash',
      );
      expect(r!.code, 'upstream_auth_invalid');
    });

    test('402 credits → upstream_credit_low', () {
      final r = humanizeStderr(
        "Error code: 402 - {'error': {'message': 'You have run out of credits'}}",
        'google/gemini-3.5-flash',
      );
      expect(r!.code, 'upstream_credit_low');
    });

    test('model_not_found → upstream_model_unknown', () {
      final r = humanizeStderr(
        "Error code: 400 - {'error': {'message': 'model_not_found: foo/bar'}}",
        'foo/bar',
      );
      expect(r!.code, 'upstream_model_unknown');
    });

    test('429 rate limit → upstream_rate_limited', () {
      final r = humanizeStderr(
        "Error code: 429 - {'error': {'message': 'Rate limit exceeded'}}",
        'google/gemini-3.5-flash',
      );
      expect(r!.code, 'upstream_rate_limited');
    });
  });

  group('Anthropic patterns', () {
    test('credit_balance_too_low → upstream_credit_low', () {
      final r = humanizeStderr(
        'anthropic.BadRequestError: credit_balance_too_low',
        'claude-3-5-sonnet-20241022',
      );
      expect(r!.code, 'upstream_credit_low');
    });

    test('overloaded_error → upstream_overloaded', () {
      final r = humanizeStderr(
        'anthropic.APIError: overloaded_error: Overloaded',
        'claude-3-5-sonnet-20241022',
      );
      expect(r!.code, 'upstream_overloaded');
    });
  });

  group('Unclassified', () {
    test('unknown stderr returns null', () {
      final r = humanizeStderr(
        'docker run exit 1 [stderr]: Bus error (core dumped)',
        'google/gemini-3.5-flash',
      );
      expect(r, isNull);
    });

    test('empty + null stderr returns null', () {
      expect(humanizeStderr('', 'google/gemini-3.5-flash'), isNull);
      expect(humanizeStderr(null, 'google/gemini-3.5-flash'), isNull);
    });
  });

  group('Shape', () {
    test('detail ends with period', () {
      final r = humanizeStderr(_pedroStderr, 'google/gemini-3.5-flash');
      expect(r!.detail.endsWith('.'), isTrue);
    });

    test('hint is single line', () {
      final r = humanizeStderr(_pedroStderr, 'google/gemini-3.5-flash');
      expect(r!.hint, isNotNull);
      expect(r.hint!.contains('\n'), isFalse);
    });
  });
}
