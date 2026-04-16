"""Unit tests for Phase 10 error taxonomy (D-01 + D-02 + D-03).

Each live category has >=1 fixture exercising the code path that emits it.
No live Docker — all subprocess calls mocked via conftest fixtures
(mock_subprocess_dispatch / mock_subprocess_timeout / fake_cidfile).

Plan 10-05 exit gate: every branch in the 9-live-category taxonomy produces
a Verdict in a test under 5 seconds total wall time.
"""
from __future__ import annotations

import dataclasses
import io
import shutil
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from run_recipe import (
    Category,
    Verdict,
    _redact_api_key,
    emit_verdict_line,
    ensure_image,
    lint_recipe,
    preflight_docker,
    run_cell,
)


# ---------- enum + dataclass primitives ----------


class TestCategoryEnum:
    def test_enum_has_11_values(self):
        assert len(list(Category)) == 11

    def test_enum_ordering(self):
        values = [c.value for c in Category]
        assert values == [
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

    def test_reserved_values_present(self):
        assert Category.STOCHASTIC.value == "STOCHASTIC"
        assert Category.SKIP.value == "SKIP"

    def test_live_values_covered(self):
        live = {
            "PASS",
            "ASSERT_FAIL",
            "INVOKE_FAIL",
            "BUILD_FAIL",
            "PULL_FAIL",
            "CLONE_FAIL",
            "TIMEOUT",
            "LINT_FAIL",
            "INFRA_FAIL",
        }
        assert live <= {c.value for c in Category}


class TestVerdictShape:
    def test_pass_verdict_derives_pass(self):
        assert Verdict(Category.PASS).verdict == "PASS"

    def test_non_pass_verdict_derives_fail(self):
        for cat in (
            Category.ASSERT_FAIL,
            Category.TIMEOUT,
            Category.INVOKE_FAIL,
            Category.BUILD_FAIL,
            Category.PULL_FAIL,
            Category.CLONE_FAIL,
            Category.LINT_FAIL,
            Category.INFRA_FAIL,
        ):
            assert Verdict(cat).verdict == "FAIL", cat

    def test_default_detail_is_empty_string(self):
        assert Verdict(Category.PASS).detail == ""

    def test_to_cell_dict_shape(self):
        d = Verdict(Category.PASS, "msg").to_cell_dict()
        assert set(d.keys()) == {"category", "detail", "verdict"}
        assert d["category"] == "PASS"
        assert d["detail"] == "msg"
        assert d["verdict"] == "PASS"

    def test_verdict_is_frozen(self):
        v = Verdict(Category.PASS)
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.detail = "mutated"  # type: ignore[misc]


# ---------- category emission tests ----------
# (one class per LIVE category per D-01; 9 classes)


class TestPassCategory:
    def test_pass_when_pass_if_true(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        # Patch image_exists so ensure_image is bypassed from the test's POV.
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        # Dispatch: docker run returns rc=0 with recipe name in stdout
        mock_subprocess_dispatch(
            {
                ("docker", "run"): (0, "I am test-agent here.", ""),
            }
        )
        # Set pass_if to match the stdout
        minimal_valid_recipe["smoke"]["pass_if"] = "response_contains_name"
        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
        )
        assert verdict.category is Category.PASS
        assert verdict.detail == ""
        assert verdict.verdict == "PASS"
        assert details["category"] == "PASS"


class TestAssertFailCategory:
    def test_assert_fail_when_pass_if_false(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        mock_subprocess_dispatch(
            {
                ("docker", "run"): (0, "I am a different agent.", ""),
            }
        )
        minimal_valid_recipe["smoke"]["pass_if"] = "response_contains_name"
        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
        )
        assert verdict.category is Category.ASSERT_FAIL
        assert "pass_if" in verdict.detail.lower()
        assert verdict.verdict == "FAIL"


class TestInvokeFailCategory:
    def test_invoke_fail_when_rc_nonzero(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        mock_subprocess_dispatch(
            {
                ("docker", "run"): (125, "", "error: something broke"),
            }
        )
        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
        )
        assert verdict.category is Category.INVOKE_FAIL
        assert "exit 125" in verdict.detail

    def test_invoke_fail_redacts_api_key(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        leaky_stderr = "err: OPENROUTER_API_KEY=sk-secret-abc123 invalid"
        mock_subprocess_dispatch(
            {
                ("docker", "run"): (1, "", leaky_stderr),
            }
        )
        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="sk-secret-abc123",
            quiet=True,
        )
        assert verdict.category is Category.INVOKE_FAIL
        # The raw secret must not appear anywhere surface-facing.
        assert "sk-secret-abc123" not in verdict.detail
        assert "sk-secret-abc123" not in (details.get("stderr_tail") or "")


class TestBuildFailCategory:
    def test_build_fail_when_docker_build_rc_nonzero(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        # ensure_image: force image_exists=False so it proceeds to clone+build;
        # short-circuit clone by ensuring clone_dir "exists"
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: False)
        monkeypatch.setattr(
            "run_recipe.enforce_disk_guard", lambda *, skip, quiet: None
        )
        # Make the clone_dir appear to exist (bypass git clone).
        fake_clone = Path(f"/tmp/ap-recipe-{minimal_valid_recipe['name']}-clone")
        fake_clone.mkdir(parents=True, exist_ok=True)
        try:
            mock_subprocess_dispatch(
                {
                    ("docker", "build"): (125, "", "build error"),
                }
            )
            result = ensure_image(
                minimal_valid_recipe,
                image_tag="ap-recipe-test",
                no_cache=False,
                no_disk_check=True,
                quiet=True,
            )
            assert result is not None
            assert result.category is Category.BUILD_FAIL
            assert "125" in result.detail
        finally:
            shutil.rmtree(fake_clone, ignore_errors=True)


class TestPullFailCategory:
    def test_pull_fail_when_docker_pull_rc_nonzero(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        # Switch recipe to image_pull mode
        minimal_valid_recipe["build"]["mode"] = "image_pull"
        minimal_valid_recipe["build"]["image"] = "alpine:3.20"
        # Remove source to match image_pull mode's schema
        minimal_valid_recipe.pop("source", None)
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: False)
        monkeypatch.setattr(
            "run_recipe.enforce_disk_guard", lambda *, skip, quiet: None
        )
        mock_subprocess_dispatch(
            {
                ("docker", "pull"): (1, "", "pull error"),
            }
        )
        result = ensure_image(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            no_cache=False,
            no_disk_check=True,
            quiet=True,
        )
        assert result is not None
        assert result.category is Category.PULL_FAIL


class TestCloneFailCategory:
    def test_clone_fail_when_git_clone_rc_nonzero(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: False)
        monkeypatch.setattr(
            "run_recipe.enforce_disk_guard", lambda *, skip, quiet: None
        )
        # Ensure clone_dir does NOT exist so git clone is attempted.
        fake_clone = Path(f"/tmp/ap-recipe-{minimal_valid_recipe['name']}-clone")
        shutil.rmtree(fake_clone, ignore_errors=True)
        mock_subprocess_dispatch(
            {
                ("git", "clone"): (128, "", "fatal: not found"),
            }
        )
        result = ensure_image(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            no_cache=False,
            no_disk_check=True,
            quiet=True,
        )
        assert result is not None
        assert result.category is Category.CLONE_FAIL


class TestTimeoutCategory:
    def test_timeout_produces_TIMEOUT_verdict(
        self, monkeypatch, mock_subprocess_timeout, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        mock_subprocess_timeout(timeout_s=1)
        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
            smoke_timeout_s=1,
        )
        assert verdict.category is Category.TIMEOUT
        assert "timeout" in verdict.detail.lower()
        assert verdict.verdict == "FAIL"


class TestLintFailCategory:
    def test_lint_fail_on_invalid_recipe(self, minimal_valid_recipe):
        # Drop a required field to trigger lint errors
        del minimal_valid_recipe["name"]
        errors = lint_recipe(minimal_valid_recipe)
        assert len(errors) > 0
        # LINT_FAIL category value is in the enum as source-of-truth
        assert Category.LINT_FAIL.value == "LINT_FAIL"


class TestInfraFailCategory:
    def test_infra_fail_when_docker_version_fails(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="Cannot connect to the Docker daemon",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        v = preflight_docker()
        assert v is not None
        assert v.category is Category.INFRA_FAIL
        assert "docker version exit 1" in v.detail

    def test_infra_fail_when_docker_version_times_out(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        v = preflight_docker()
        assert v is not None
        assert v.category is Category.INFRA_FAIL
        assert "unresponsive" in v.detail

    def test_infra_fail_when_docker_cli_missing(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("No such file")

        monkeypatch.setattr(subprocess, "run", fake_run)
        v = preflight_docker()
        assert v is not None
        assert v.category is Category.INFRA_FAIL
        assert "not in PATH" in v.detail

    def test_no_verdict_when_docker_version_ok(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="27.0.3\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert preflight_docker() is None


# ---------- cidfile lifecycle (regression gate for Pitfall 2 + W5 D-03 maturity) ----------


class TestCidfileLifecycle:
    def test_cidfile_unlinked_on_timeout(
        self, monkeypatch, mock_subprocess_timeout, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        unlinked: list[Path] = []
        original_unlink = Path.unlink

        def tracking_unlink(self, missing_ok=False):
            unlinked.append(self)
            try:
                original_unlink(self, missing_ok=missing_ok)
            except OSError:
                pass

        monkeypatch.setattr(Path, "unlink", tracking_unlink)
        mock_subprocess_timeout(timeout_s=1)
        run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
            smoke_timeout_s=1,
        )
        # At least one unlinked path should be a cidfile under /tmp/ap-cid-
        cidfile_unlinks = [p for p in unlinked if str(p).startswith("/tmp/ap-cid-")]
        assert cidfile_unlinks, f"cidfile never unlinked; unlinks={unlinked}"

    def test_no_stale_cidfiles_after_success(
        self, monkeypatch, mock_subprocess_dispatch, minimal_valid_recipe
    ):
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)
        mock_subprocess_dispatch(
            {
                ("docker", "run"): (0, "I am test-agent.", ""),
            }
        )
        minimal_valid_recipe["smoke"]["pass_if"] = "response_contains_name"
        # Snapshot /tmp before & after run_cell to check no cidfile leakage
        before = set(Path("/tmp").glob("ap-cid-*.cid"))
        run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
        )
        after = set(Path("/tmp").glob("ap-cid-*.cid"))
        # after ⊆ before (run_cell's own cidfile must be unlinked)
        leaked = after - before
        assert not leaked, f"cidfile leaked: {leaked}"

    def test_docker_kill_invoked_on_timeout(
        self,
        monkeypatch,
        mock_subprocess_timeout,
        fake_cidfile,
        minimal_valid_recipe,
    ):
        """W5 load-bearing test for D-03: when TIMEOUT fires AND the cidfile
        on disk contains a real container ID, `docker kill <cid>` and
        `docker rm -f <cid>` MUST actually be invoked. Without this test,
        a regression where the TIMEOUT classification fires but the kill
        path is skipped would pass CI silently — breaking D-03's core
        promise to 'actually kill runaway containers'.
        """
        monkeypatch.setattr("run_recipe.image_exists", lambda tag: True)

        # Pre-populate the cidfile on disk with a known CID + steer run_cell's
        # Path(/tmp/ap-cid-*) construction to this populated file.
        cid = "fake-cid-abc123"
        cidfile_path = fake_cidfile(cid=cid)
        assert cidfile_path.exists()
        assert cidfile_path.read_text() == cid

        # Install the timeout mock with recording enabled so we can verify
        # the kill/rm invocations landed.
        recorded = mock_subprocess_timeout(timeout_s=1, record=True)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="fake-key",
            quiet=True,
            smoke_timeout_s=1,
        )

        # Verdict shape: TIMEOUT + FAIL
        assert verdict.category is Category.TIMEOUT, f"got {verdict.category}"
        assert verdict.verdict == "FAIL"

        # The load-bearing assertion: docker kill + docker rm -f fired
        # with the exact CID that was in the cidfile.
        kill_calls = [c for c in recorded if c[:2] == ["docker", "kill"]]
        rm_calls = [c for c in recorded if c[:3] == ["docker", "rm", "-f"]]
        assert kill_calls, f"docker kill never invoked; recorded={recorded}"
        assert rm_calls, f"docker rm -f never invoked; recorded={recorded}"
        assert cid in kill_calls[0], (
            f"docker kill did not target {cid}: {kill_calls[0]}"
        )
        assert cid in rm_calls[0], (
            f"docker rm -f did not target {cid}: {rm_calls[0]}"
        )

        # Cidfile cleanup still happens (existing behavior gate).
        assert not cidfile_path.exists(), (
            "cidfile should be unlinked in run_cell's finally block"
        )


# ---------- emit_verdict_line format ----------


class TestEmitFormat:
    def test_emit_pass_is_green(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.PASS),
                recipe="hermes",
                model="anthropic/haiku",
                wall_s=0.12,
            )
        out = buf.getvalue()
        assert "\033[32m" in out  # _GREEN
        assert "PASS" in out
        assert "hermes" in out
        assert "(anthropic/haiku)" in out
        assert "0.12s" in out

    def test_emit_non_pass_is_red(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.TIMEOUT, "exceeded smoke.timeout_s=180s"),
                recipe="hermes",
                model="openai/gpt-4o-mini",
                wall_s=180.00,
            )
        out = buf.getvalue()
        assert "\033[31m" in out  # _RED
        assert "TIMEOUT" in out
        assert "— exceeded smoke.timeout_s=180s" in out

    def test_emit_no_detail_when_empty(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            emit_verdict_line(
                Verdict(Category.PASS), recipe="x", model="y", wall_s=0.0
            )
        out = buf.getvalue()
        assert " — " not in out  # no detail separator when detail=""


# ---------- redaction helper ----------


class TestRedaction:
    def test_redacts_exact_var(self):
        assert _redact_api_key("FOO=secret bar", "FOO") == "FOO=<REDACTED> bar"

    def test_empty_input(self):
        assert _redact_api_key("", "FOO") == ""

    def test_no_match(self):
        assert (
            _redact_api_key("nothing to redact here", "FOO")
            == "nothing to redact here"
        )

    def test_multiple_instances(self):
        out = _redact_api_key("FOO=abc and later FOO=def", "FOO")
        assert "abc" not in out
        assert "def" not in out
        assert out.count("<REDACTED>") == 2
