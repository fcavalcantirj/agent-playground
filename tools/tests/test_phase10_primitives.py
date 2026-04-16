"""Phase 10 Task 1: primitives tests.

Covers Category enum shape, Verdict dataclass behavior, preflight_docker
wiring, _redact_api_key redaction, and emit_verdict_line output format.

RED: these tests must fail before Task 1 implementation lands and pass
after. They exercise the additive module-level additions only — no
changes to ensure_image/run_cell/main().
"""
from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCategoryEnum:
    def test_category_has_exactly_11_values(self):
        from run_recipe import Category

        assert len(list(Category)) == 11

    def test_category_order_and_values(self):
        from run_recipe import Category

        expected = [
            "PASS",
            "ASSERT_FAIL",
            "INVOKE_FAIL",
            "BUILD_FAIL",
            "PULL_FAIL",
            "CLONE_FAIL",
            "TIMEOUT",
            "LINT_FAIL",
            "INFRA_FAIL",
            "STOCHASTIC",
            "SKIP",
        ]
        assert [c.value for c in Category] == expected

    def test_category_values_equal_names(self):
        from run_recipe import Category

        assert Category.PASS.value == "PASS"
        assert Category.TIMEOUT.value == "TIMEOUT"
        assert Category.INFRA_FAIL.value == "INFRA_FAIL"

    def test_category_is_str_subclass(self):
        from run_recipe import Category

        # Python 3.10 compat: `class Category(str, Enum)` — members ARE strings.
        assert isinstance(Category.PASS, str)


class TestVerdictDataclass:
    def test_pass_verdict_derives_verdict_pass(self):
        from run_recipe import Category, Verdict

        v = Verdict(Category.PASS)
        assert v.verdict == "PASS"
        assert v.detail == ""

    def test_non_pass_verdict_derives_verdict_fail(self):
        from run_recipe import Category, Verdict

        assert Verdict(Category.TIMEOUT).verdict == "FAIL"
        assert Verdict(Category.ASSERT_FAIL, "bad").verdict == "FAIL"
        assert Verdict(Category.INFRA_FAIL).verdict == "FAIL"

    def test_detail_preserved(self):
        from run_recipe import Category, Verdict

        assert Verdict(Category.ASSERT_FAIL, "bad").detail == "bad"

    def test_verdict_is_frozen(self):
        from run_recipe import Category, Verdict
        import dataclasses

        v = Verdict(Category.PASS)
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.category = Category.TIMEOUT  # type: ignore[misc]

    def test_to_cell_dict_pass(self):
        from run_recipe import Category, Verdict

        d = Verdict(Category.PASS).to_cell_dict()
        assert d == {"category": "PASS", "detail": "", "verdict": "PASS"}

    def test_to_cell_dict_timeout(self):
        from run_recipe import Category, Verdict

        d = Verdict(Category.TIMEOUT, "exceeded 180s").to_cell_dict()
        assert d == {
            "category": "TIMEOUT",
            "detail": "exceeded 180s",
            "verdict": "FAIL",
        }


class TestRedactApiKey:
    def test_redacts_simple_assignment(self):
        from run_recipe import _redact_api_key

        assert _redact_api_key("FOO=secret bar", "FOO") == "FOO=<REDACTED> bar"

    def test_empty_input_returns_empty(self):
        from run_recipe import _redact_api_key

        assert _redact_api_key("", "FOO") == ""

    def test_no_match_passes_through(self):
        from run_recipe import _redact_api_key

        assert _redact_api_key("no key here", "FOO") == "no key here"

    def test_redacts_real_api_key_pattern(self):
        from run_recipe import _redact_api_key

        out = _redact_api_key(
            "error: OPENROUTER_API_KEY=sk-or-v1-abc123xyz failed", "OPENROUTER_API_KEY"
        )
        assert out == "error: OPENROUTER_API_KEY=<REDACTED> failed"

    def test_redacts_multiple_occurrences(self):
        from run_recipe import _redact_api_key

        out = _redact_api_key("K=a K=b", "K")
        assert out == "K=<REDACTED> K=<REDACTED>"


class TestPreflightDocker:
    def test_returns_none_or_infra_fail(self):
        """preflight returns either None (docker OK) or a Verdict with
        INFRA_FAIL category. Either is acceptable for a unit test — both
        are on the live code path."""
        from run_recipe import Category, Verdict, preflight_docker

        result = preflight_docker()
        assert result is None or (
            isinstance(result, Verdict) and result.category is Category.INFRA_FAIL
        )

    def test_missing_docker_binary_returns_infra_fail(self, monkeypatch):
        from run_recipe import Category, Verdict, preflight_docker

        def raise_fnf(*a, **k):
            raise FileNotFoundError("no docker")

        monkeypatch.setattr(subprocess, "run", raise_fnf)
        result = preflight_docker()
        assert isinstance(result, Verdict)
        assert result.category is Category.INFRA_FAIL
        assert "docker CLI not in PATH" in result.detail

    def test_daemon_down_returns_infra_fail(self, monkeypatch):
        from run_recipe import Category, Verdict, preflight_docker

        def fake_run(cmd, **k):
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="Cannot connect to daemon"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = preflight_docker()
        assert isinstance(result, Verdict)
        assert result.category is Category.INFRA_FAIL
        assert "docker version exit 1" in result.detail

    def test_daemon_timeout_returns_infra_fail(self, monkeypatch):
        from run_recipe import Category, Verdict, preflight_docker

        def fake_run(cmd, **k):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = preflight_docker()
        assert isinstance(result, Verdict)
        assert result.category is Category.INFRA_FAIL
        assert "unresponsive" in result.detail


class TestEmitVerdictLine:
    def test_pass_line_green_with_expected_fields(self):
        from run_recipe import Category, Verdict, emit_verdict_line

        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.PASS), recipe="x", model="y", wall_s=1.23
            )
        out = buf.getvalue()
        assert "PASS" in out
        assert "x" in out
        assert "(y)" in out
        assert "1.23s" in out
        # Green ANSI colour for PASS
        assert "\033[32m" in out

    def test_timeout_line_red_with_detail(self):
        from run_recipe import Category, Verdict, emit_verdict_line

        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.TIMEOUT, "exceeded 180s"),
                recipe="hermes",
                model="openai/gpt-4o-mini",
                wall_s=180.00,
            )
        out = buf.getvalue()
        assert "TIMEOUT" in out
        # Red ANSI colour for non-PASS
        assert "\033[31m" in out
        # Ends with " — <detail>" before the newline
        assert out.rstrip().endswith(" — exceeded 180s")

    def test_pass_line_omits_detail_dash(self):
        from run_recipe import Category, Verdict, emit_verdict_line

        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.PASS), recipe="x", model="y", wall_s=0.5
            )
        # No trailing em-dash detail section when detail is empty
        assert " — " not in buf.getvalue()


class TestExistingApiStillImportable:
    """Guard-rail: Task 1 is additive. Existing importable API must still work."""

    def test_existing_functions_still_importable(self):
        from run_recipe import (
            evaluate_pass_if,
            lint_recipe,
            load_recipe,
        )

        # Basic sanity: evaluate_pass_if still works
        assert (
            evaluate_pass_if(
                "exit_zero", payload="", name="n", exit_code=0, smoke={}
            )
            == "PASS"
        )
