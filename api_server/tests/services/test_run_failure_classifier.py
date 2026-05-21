"""Unit tests for run_failure_classifier.

Pure-function tests — no Postgres, no Docker, no HTTP. Each fixture is a
real or near-real stderr_tail captured from an actual failing recipe run.
The Pedro case (2026-05-21) is the gold-standard fixture.
"""
from __future__ import annotations

import pytest

from api_server.services.run_failure_classifier import (
    RunFailureClass,
    classify_invoke_fail,
)


# Gold-standard fixture — exact stderr from runs row 01KS484QJVQDDHHQT2670BTV5P
# (user pedroggf@gmail.com, hermes + google/gemini-3.5-flash, 2026-05-21).
PEDRO_STDERR = (
    "docker run exit 1 [stderr]: 03:09:31 - root - ERROR [20260521_030929_6c3f53] "
    "- Non-retryable client error: Error code: 401 - "
    "{'error': {'message': 'Missing Authentication header', 'code': 401}}"
)


class TestProviderInference:
    """``_provider_for(model)`` via the public entry — confirmed indirectly
    via the chain ordering. We pick fixtures whose pattern only one provider
    matches, so a misorder would surface as the wrong code."""

    def test_openrouter_default_when_model_unset(self):
        cls = classify_invoke_fail(PEDRO_STDERR, None)
        assert cls is not None
        assert cls.code == "upstream_auth_missing"

    def test_openrouter_for_provider_slash_model(self):
        cls = classify_invoke_fail(PEDRO_STDERR, "google/gemini-3.5-flash")
        assert cls is not None
        assert cls.code == "upstream_auth_missing"

    def test_anthropic_for_claude_prefix(self):
        cls = classify_invoke_fail(
            "ERROR: anthropic.APIError: authentication_error: invalid x-api-key",
            "claude-3-5-sonnet-20241022",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"

    def test_openai_for_gpt_prefix(self):
        cls = classify_invoke_fail(
            "openai.AuthenticationError: invalid_api_key: incorrect api key",
            "gpt-4o-mini",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"


class TestOpenRouter:
    def test_pedro_missing_authentication_header(self):
        cls = classify_invoke_fail(PEDRO_STDERR, "google/gemini-3.5-flash")
        assert cls == RunFailureClass(
            code="upstream_auth_missing",
            detail="No OpenRouter API key was sent with the request.",
            hint=(
                "Tap Edit, go to Model + Key, and paste your "
                "`sk-or-v1-…` key from https://openrouter.ai/keys."
            ),
        )

    def test_no_auth_credentials_found(self):
        cls = classify_invoke_fail(
            "Error code: 401 - {'error': {'message': 'No auth credentials found'}}",
            "anthropic/claude-3.5-sonnet",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"

    def test_user_not_found(self):
        cls = classify_invoke_fail(
            "Error code: 401 - {'error': {'message': 'User not found'}}",
            "google/gemini-3.5-flash",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"

    def test_402_credits(self):
        cls = classify_invoke_fail(
            "Error code: 402 - {'error': {'message': 'You have run out of credits'}}",
            "google/gemini-3.5-flash",
        )
        assert cls is not None
        assert cls.code == "upstream_credit_low"

    def test_model_not_found(self):
        cls = classify_invoke_fail(
            "Error code: 400 - {'error': {'message': 'model_not_found: foo/bar'}}",
            "foo/bar",
        )
        assert cls is not None
        assert cls.code == "upstream_model_unknown"

    def test_rate_limit_429(self):
        cls = classify_invoke_fail(
            "Error code: 429 - {'error': {'message': 'Rate limit exceeded'}}",
            "google/gemini-3.5-flash",
        )
        assert cls is not None
        assert cls.code == "upstream_rate_limited"


class TestAnthropic:
    def test_authentication_error(self):
        cls = classify_invoke_fail(
            "anthropic.APIError: authentication_error: invalid x-api-key",
            "claude-3-5-sonnet-20241022",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"

    def test_credit_balance_too_low(self):
        cls = classify_invoke_fail(
            "anthropic.BadRequestError: credit_balance_too_low",
            "claude-3-5-sonnet-20241022",
        )
        assert cls is not None
        assert cls.code == "upstream_credit_low"

    def test_overloaded_error(self):
        cls = classify_invoke_fail(
            "anthropic.APIError: overloaded_error: Overloaded",
            "claude-3-5-sonnet-20241022",
        )
        assert cls is not None
        assert cls.code == "upstream_overloaded"

    def test_rate_limit_error(self):
        cls = classify_invoke_fail(
            "anthropic.RateLimitError: rate_limit_error",
            "claude-3-5-sonnet-20241022",
        )
        assert cls is not None
        assert cls.code == "upstream_rate_limited"


class TestOpenAI:
    def test_invalid_api_key(self):
        cls = classify_invoke_fail(
            "openai.AuthenticationError: invalid_api_key: incorrect api key",
            "gpt-4o-mini",
        )
        assert cls is not None
        assert cls.code == "upstream_auth_invalid"

    def test_insufficient_quota(self):
        cls = classify_invoke_fail(
            "openai.RateLimitError: insufficient_quota: You exceeded your quota",
            "gpt-4o-mini",
        )
        assert cls is not None
        assert cls.code == "upstream_credit_low"

    def test_rate_limit_exceeded(self):
        cls = classify_invoke_fail(
            "openai.RateLimitError: rate_limit_exceeded",
            "gpt-4o-mini",
        )
        assert cls is not None
        assert cls.code == "upstream_rate_limited"


class TestUnclassified:
    def test_unknown_stderr_returns_none(self):
        cls = classify_invoke_fail(
            "docker run exit 1 [stderr]: Bus error (core dumped)",
            "google/gemini-3.5-flash",
        )
        assert cls is None

    def test_empty_stderr_returns_none(self):
        assert classify_invoke_fail("", "google/gemini-3.5-flash") is None
        assert classify_invoke_fail(None, "google/gemini-3.5-flash") is None


class TestShape:
    def test_detail_ends_with_period(self):
        cls = classify_invoke_fail(PEDRO_STDERR, "google/gemini-3.5-flash")
        assert cls is not None
        assert cls.detail.endswith(".")

    def test_hint_is_one_line(self):
        cls = classify_invoke_fail(PEDRO_STDERR, "google/gemini-3.5-flash")
        assert cls is not None
        assert cls.hint is not None
        assert "\n" not in cls.hint
