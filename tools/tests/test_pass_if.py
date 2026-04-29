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

    # Phase 22c.1: pass_if response_contains_name now accepts an optional
    # ``agent_name`` (the user's chosen identity at deploy time) and PASSes
    # if EITHER recipe name OR agent_name appears in the reply.

    def test_pass_when_only_agent_name_present(self):
        """Recipe name absent, agent_name present → PASS (the new behavior)."""
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am browww-2, here to help.",
            name="nullclaw",
            agent_name="browww-2",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_pass_when_only_recipe_name_present_with_agent_name_set(self):
        """Recipe name present, agent_name absent from reply → PASS (backward compat)."""
        result = evaluate_pass_if(
            "response_contains_name",
            payload="hermes here, ready to gateway.",
            name="hermes",
            agent_name="my-bot",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_fail_when_neither_name_present(self):
        """Both names absent → FAIL."""
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I'm Claude, an AI assistant.",
            name="nullclaw",
            agent_name="browww-2",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"

    def test_agent_name_case_insensitive(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="hello, this is BROWWW-2 speaking.",
            name="nullclaw",
            agent_name="browww-2",
            exit_code=0,
            smoke={"case_insensitive": True},
        )
        assert result == "PASS"

    def test_agent_name_none_falls_back_to_recipe_name(self):
        """agent_name=None (default) → existing recipe-name-only behavior."""
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am hermes.",
            name="hermes",
            agent_name=None,
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_empty_agent_name_does_not_match_empty_substring(self):
        """Empty agent_name must NOT trivially PASS (empty string is in any string)."""
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I'm Claude.",
            name="nullclaw",
            agent_name="",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"


class TestRepliedOk:
    """Phase 22c.1 looser pass_if: exit_zero + non-empty reply."""

    def test_pass_when_exit_zero_and_reply_non_empty(self):
        result = evaluate_pass_if(
            "replied_ok",
            payload="I'm in a fresh setup, no IDENTITY.md yet — but here's my critique:",
            name="nullclaw",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"

    def test_fail_when_reply_empty(self):
        result = evaluate_pass_if(
            "replied_ok",
            payload="",
            name="nullclaw",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"

    def test_fail_when_reply_only_whitespace(self):
        result = evaluate_pass_if(
            "replied_ok",
            payload="   \n\t  ",
            name="nullclaw",
            exit_code=0,
            smoke={},
        )
        assert result == "FAIL"

    def test_fail_when_exit_nonzero(self):
        result = evaluate_pass_if(
            "replied_ok",
            payload="this reply was produced but the exit was bad",
            name="nullclaw",
            exit_code=1,
            smoke={},
        )
        assert result == "FAIL"

    def test_does_not_second_guess_content(self):
        """The whole point: any non-trivial reply + clean exit = PASS."""
        result = evaluate_pass_if(
            "replied_ok",
            payload="The capital of France is Paris.",
            name="some-recipe",
            agent_name="my-bot",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"


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
