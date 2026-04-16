"""Unit tests for all 5 pass_if verbs in evaluate_pass_if.

Pillar 1 (D-11a, D-12): each verb has at least one PASS and one FAIL test.
No Docker, no network — pure function tests against canned payloads.
"""
import pytest
from run_recipe import evaluate_pass_if


class TestResponseContainsName:
    def test_pass_when_name_present(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am hermes, an AI assistant.",
            name="hermes",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_fail_when_name_absent(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am an AI assistant.",
            name="hermes",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"

    def test_case_insensitive(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am HERMES.",
            name="hermes",
            exit_code=0,
            smoke={"case_insensitive": True},
        )
        assert result == "PASS"

    def test_case_sensitive_default(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am HERMES.",
            name="hermes",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"


class TestResponseContainsString:
    def test_pass_when_needle_found(self):
        result = evaluate_pass_if(
            "response_contains_string",
            payload="OpenClaw is an AI framework.",
            name="test",
            exit_code=0,
            smoke={"needle": "OpenClaw"},
        )
        assert result == "PASS"

    def test_fail_when_needle_absent(self):
        result = evaluate_pass_if(
            "response_contains_string",
            payload="I am an AI assistant.",
            name="test",
            exit_code=0,
            smoke={"needle": "OpenClaw"},
        )
        assert result == "FAIL"

    def test_error_when_needle_missing(self):
        result = evaluate_pass_if(
            "response_contains_string",
            payload="anything",
            name="test",
            exit_code=0,
            smoke={},
        )
        assert result == "ERROR(missing smoke.needle)"

    def test_case_insensitive_needle(self):
        result = evaluate_pass_if(
            "response_contains_string",
            payload="OPENCLAW is great.",
            name="test",
            exit_code=0,
            smoke={"needle": "openclaw", "case_insensitive": True},
        )
        assert result == "PASS"


class TestResponseNotContains:
    def test_pass_when_needle_absent(self):
        result = evaluate_pass_if(
            "response_not_contains",
            payload="I am an AI assistant.",
            name="test",
            exit_code=0,
            smoke={"needle": "error"},
        )
        assert result == "PASS"

    def test_fail_when_needle_present(self):
        result = evaluate_pass_if(
            "response_not_contains",
            payload="An error occurred.",
            name="test",
            exit_code=0,
            smoke={"needle": "error"},
        )
        assert result == "FAIL"

    def test_error_when_needle_missing(self):
        result = evaluate_pass_if(
            "response_not_contains",
            payload="anything",
            name="test",
            exit_code=0,
            smoke={},
        )
        assert result == "ERROR(missing smoke.needle)"


class TestResponseRegex:
    def test_pass_when_regex_matches(self):
        result = evaluate_pass_if(
            "response_regex",
            payload="Version 2.3.1 is installed.",
            name="test",
            exit_code=0,
            smoke={"regex": r"Version \d+\.\d+\.\d+"},
        )
        assert result == "PASS"

    def test_fail_when_regex_no_match(self):
        result = evaluate_pass_if(
            "response_regex",
            payload="No version info here.",
            name="test",
            exit_code=0,
            smoke={"regex": r"Version \d+\.\d+\.\d+"},
        )
        assert result == "FAIL"

    def test_error_when_regex_missing(self):
        result = evaluate_pass_if(
            "response_regex",
            payload="anything",
            name="test",
            exit_code=0,
            smoke={},
        )
        assert result == "ERROR(missing smoke.regex)"

    def test_case_insensitive_regex(self):
        result = evaluate_pass_if(
            "response_regex",
            payload="HERMES agent ready.",
            name="test",
            exit_code=0,
            smoke={"regex": r"hermes", "case_insensitive": True},
        )
        assert result == "PASS"


class TestExitZero:
    def test_pass_on_zero(self):
        result = evaluate_pass_if(
            "exit_zero",
            payload="",
            name="test",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_fail_on_nonzero(self):
        result = evaluate_pass_if(
            "exit_zero",
            payload="",
            name="test",
            exit_code=1,
            smoke={},
        )
        assert result == "FAIL"


class TestUnknownVerb:
    def test_unknown_verb_returns_unknown(self):
        result = evaluate_pass_if(
            "nonexistent_verb",
            payload="",
            name="test",
            exit_code=0,
            smoke={},
        )
        assert result.startswith("UNKNOWN(")
