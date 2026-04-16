"""Hardening tests for two smaller gaps:
- Silent git checkout failure (logged symmetrically with fetch failures).
- Awk subprocess with no timeout (now capped at 30s, fail-open to raw).
"""
import subprocess

import pytest

import run_recipe
from run_recipe import apply_stdout_filter


class TestAwkTimeout:
    def test_awk_timeout_falls_back_to_raw(self, monkeypatch):
        """A runaway awk program should not wedge the runner.

        Fail-open to raw payload so pass_if still has something to evaluate —
        an empty return would mask all downstream verdicts.
        """
        def raise_timeout(cmd, **kwargs):
            assert cmd[0] == "awk"
            assert "timeout" in kwargs, "awk subprocess must be called with timeout"
            assert kwargs["timeout"] > 0
            raise subprocess.TimeoutExpired(
                cmd=cmd, timeout=kwargs["timeout"], output=b"", stderr=b""
            )

        monkeypatch.setattr(subprocess, "run", raise_timeout)

        raw = "some payload text\nwith lines"
        result = apply_stdout_filter(
            raw, {"engine": "awk", "program": "BEGIN{while(1){}}"}
        )
        # Fail-open: return raw so downstream can still classify.
        assert result == raw

    def test_awk_timeout_value_is_bounded(self, monkeypatch):
        captured_timeout: list[int] = []

        def fake_run(cmd, **kwargs):
            captured_timeout.append(kwargs.get("timeout"))
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="ok", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        apply_stdout_filter("x", {"engine": "awk", "program": "NR==1"})
        assert captured_timeout[0] is not None
        # Not pathologically large — should be a small-double-digit bound.
        assert 1 <= captured_timeout[0] <= 120


class TestAwkNoFilter:
    """Existing passthrough behavior must survive the timeout addition."""

    def test_no_spec_returns_raw(self):
        assert apply_stdout_filter("abc", None) == "abc"

    def test_engine_none_returns_raw(self):
        assert apply_stdout_filter("abc", {"engine": None}) == "abc"

    def test_unsupported_engine_raises(self):
        with pytest.raises(SystemExit):
            apply_stdout_filter("x", {"engine": "sed", "program": "s/a/b/"})


class TestCheckoutFailureLogged:
    """When `git checkout FETCH_HEAD` fails, the runner must log it
    symmetrically with the fetch-failure branch instead of silently
    falling through to shallow HEAD."""

    def test_checkout_failure_emits_warning(self, monkeypatch, tmp_path, capsys):
        # Stage: clone OK, fetch OK, checkout NON-zero rc.
        def fake_run_with_timeout(cmd, *, timeout_s, capture=True):
            if cmd[:2] == ["git", "clone"]:
                # simulate successful clone (dir created)
                dest = cmd[-1]
                from pathlib import Path as _P
                _P(dest).mkdir(parents=True, exist_ok=True)
                return 0, "", "", False
            if "fetch" in cmd:
                return 0, "", "", False
            if "checkout" in cmd:
                return 128, "", "fatal: reference is not a tree", False
            if cmd[:2] == ["docker", "build"]:
                return 0, "", "", False
            return 0, "", "", False

        def fake_image_exists(tag):
            return False

        # Disable disk guard for this unit test.
        monkeypatch.setattr(run_recipe, "run_with_timeout", fake_run_with_timeout)
        monkeypatch.setattr(run_recipe, "image_exists", fake_image_exists)
        monkeypatch.setattr(run_recipe, "enforce_disk_guard", lambda **kw: None)

        recipe = {
            "name": "testagent",
            "build": {"mode": "upstream_dockerfile", "dockerfile": "Dockerfile"},
            "source": {
                "repo": "https://example.com/x.git",
                "ref": "abc123def456",
            },
        }

        verdict = run_recipe.ensure_image(
            recipe,
            image_tag="img:t",
            no_cache=True,  # force fresh clone path
            no_disk_check=True,
            quiet=False,
        )

        captured = capsys.readouterr()
        # Failure path must surface a WARN line naming checkout.
        assert "WARN" in captured.out
        assert "checkout" in captured.out.lower()
