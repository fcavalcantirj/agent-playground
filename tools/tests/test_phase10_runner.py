"""Phase 10 Task 2: runner rewrite tests.

Covers the new contracts for ensure_image (-> Verdict | None),
run_cell (-> tuple[Verdict, dict]), run_with_timeout helper,
--global-timeout argparse option, and cidfile injection.

RED: these tests must fail before Task 2 implementation lands and pass
after. They test the refactored surface of ensure_image/run_cell/main
without needing a live Docker daemon (all subprocess calls are mocked).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRunWithTimeoutHelper:
    def test_success_returns_rc_zero_not_timed_out(self):
        from run_recipe import run_with_timeout

        rc, so, se, to = run_with_timeout(["true"], timeout_s=5)
        assert rc == 0
        assert to is False

    def test_nonzero_returns_rc_nonzero_not_timed_out(self):
        from run_recipe import run_with_timeout

        rc, so, se, to = run_with_timeout(["false"], timeout_s=5)
        assert rc != 0
        assert to is False

    def test_timeout_sets_timed_out_true(self, monkeypatch):
        from run_recipe import run_with_timeout

        def fake_run(cmd, **k):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1, stderr="timed")

        monkeypatch.setattr(subprocess, "run", fake_run)
        rc, so, se, to = run_with_timeout(["docker", "build", "x"], timeout_s=1)
        assert to is True
        assert rc == -1

    def test_timeout_bytes_stdout_decoded(self, monkeypatch):
        """Python 3.10 Pitfall 3: exc.stdout/stderr may be bytes."""
        from run_recipe import run_with_timeout

        def fake_run(cmd, **k):
            exc = subprocess.TimeoutExpired(cmd=cmd, timeout=1)
            exc.stdout = b"partial-out"
            exc.stderr = b"partial-err"
            raise exc

        monkeypatch.setattr(subprocess, "run", fake_run)
        rc, so, se, to = run_with_timeout(["x"], timeout_s=1)
        assert to is True
        assert so == "partial-out"
        assert se == "partial-err"


class TestEnsureImageReturnType:
    def test_ensure_image_signature_returns_verdict_or_none(self):
        import inspect
        from run_recipe import ensure_image

        sig = inspect.signature(ensure_image)
        anno = str(sig.return_annotation)
        assert anno.endswith("| None") or "Optional" in anno, (
            f"ensure_image must return Verdict | None, got {anno}"
        )


class TestRunCellSignatureAndCidfile:
    def test_run_cell_returns_tuple_verdict_dict(self, monkeypatch, minimal_valid_recipe):
        """run_cell must return (Verdict, dict)."""
        from run_recipe import Category, Verdict, run_cell

        captured_cmds: list = []

        def fake_run(cmd, **k):
            captured_cmds.append(cmd)
            # Non-docker-run calls (rm, kill, tag etc): succeed.
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="hello test-agent", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="TEST_KEY",
            api_key_val="secret",
            quiet=True,
        )
        assert isinstance(result, tuple), f"expected tuple, got {type(result)}"
        assert len(result) == 2
        verdict, details = result
        assert isinstance(verdict, Verdict)
        assert isinstance(details, dict)

    def test_run_cell_injects_cidfile_into_docker_run(
        self, monkeypatch, minimal_valid_recipe
    ):
        from run_recipe import run_cell

        captured_cmds: list = []

        def fake_run(cmd, **k):
            captured_cmds.append(list(cmd))
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="hello test-agent", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="TEST_KEY",
            api_key_val="secret",
            quiet=True,
        )

        docker_run_cmd = next(
            (c for c in captured_cmds if c[:2] == ["docker", "run"]), None
        )
        assert docker_run_cmd is not None
        cid_args = [a for a in docker_run_cmd if a.startswith("--cidfile=")]
        assert len(cid_args) == 1, (
            f"expected exactly one --cidfile arg, got {cid_args}"
        )


class TestRunCellCategories:
    def test_pass_category_on_pass_if_match(self, monkeypatch, minimal_valid_recipe):
        from run_recipe import Category, run_cell

        # recipe uses `exit_zero` pass_if — rc=0 → PASS
        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
        )
        assert verdict.category is Category.PASS
        assert verdict.verdict == "PASS"

    def test_invoke_fail_on_nonzero_exit(self, monkeypatch, minimal_valid_recipe):
        from run_recipe import Category, run_cell

        # Force non-zero exit from docker run
        minimal_valid_recipe["smoke"]["pass_if"] = "response_contains_name"

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=1,
                    stdout="",
                    stderr="docker: Error response from daemon",
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
        )
        assert verdict.category is Category.INVOKE_FAIL
        assert "exit 1" in verdict.detail
        assert verdict.verdict == "FAIL"

    def test_assert_fail_on_pass_if_fail(self, monkeypatch, minimal_valid_recipe):
        from run_recipe import Category, run_cell

        minimal_valid_recipe["smoke"]["pass_if"] = "response_contains_name"

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                # rc=0 but payload does NOT contain the recipe name -> ASSERT_FAIL
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="bye", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
        )
        assert verdict.category is Category.ASSERT_FAIL
        assert "pass_if evaluated FAIL" in verdict.detail

    def test_timeout_category_reaps_via_cidfile(
        self, monkeypatch, tmp_path, minimal_valid_recipe
    ):
        from run_recipe import Category, run_cell

        reap_calls: list = []

        # We need cidfile to exist and contain a fake CID when the kill path
        # reads it. We intercept Path.read_text / Path.exists / Path.stat only
        # for cidfiles in /tmp/ap-cid-*.
        real_subprocess_run = subprocess.run

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                # Simulate the CLI timeout — and drop a cidfile to /tmp
                # so the reap-via-cidfile path has something to read.
                cidarg = next(
                    (a for a in cmd if a.startswith("--cidfile=")), None
                )
                if cidarg:
                    cidpath = Path(cidarg.split("=", 1)[1])
                    cidpath.write_text("abc123fake-container-id")
                raise subprocess.TimeoutExpired(
                    cmd=cmd, timeout=1, output="", stderr=""
                )
            if cmd[:2] == ["docker", "kill"] or cmd[:3] == ["docker", "rm", "-f"]:
                reap_calls.append(tuple(cmd))
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            # rm -rf data_dir, etc.
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
            smoke_timeout_s=1,
        )
        assert verdict.category is Category.TIMEOUT
        assert "exceeded smoke.timeout_s=1s" in verdict.detail
        # The reap path fired docker kill and docker rm -f
        kills = [c for c in reap_calls if c[:2] == ("docker", "kill")]
        rms = [c for c in reap_calls if c[:3] == ("docker", "rm", "-f")]
        assert len(kills) == 1, f"expected 1 docker kill, got {kills}"
        assert len(rms) == 1, f"expected 1 docker rm -f, got {rms}"

    def test_invoke_fail_redacts_api_key_in_detail(
        self, monkeypatch, minimal_valid_recipe
    ):
        from run_recipe import Category, run_cell

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=2,
                    stdout="",
                    stderr=(
                        "Error: bad auth — with TEST_KEY=sk-supersecret-abc\n"
                        "more context line"
                    ),
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict, details = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="TEST_KEY",
            api_key_val="sk-supersecret-abc",
            quiet=True,
        )
        # Either the stderr tail hits the detail or just the exit-code summary
        # hits. In both cases, the raw secret MUST NOT appear anywhere.
        assert "sk-supersecret-abc" not in verdict.detail
        assert "sk-supersecret-abc" not in (details.get("stderr_tail") or "")
        assert verdict.category is Category.INVOKE_FAIL


class TestGlobalTimeoutArg:
    def test_global_timeout_parsed_as_int(self):
        from run_recipe import parse_args

        args = parse_args(["--global-timeout=10", "x.yaml"])
        assert args.global_timeout == 10

    def test_global_timeout_default_none(self):
        from run_recipe import parse_args

        args = parse_args(["x.yaml"])
        assert args.global_timeout is None


class TestMainLintShortCircuits:
    def test_lint_all_works_without_docker_preflight(self, monkeypatch, tmp_path):
        """--lint-all must short-circuit BEFORE preflight_docker()."""
        from run_recipe import main

        # Force preflight to fail — it should NOT be called for --lint-all.
        called = {"preflight": False}

        import run_recipe
        real_preflight = run_recipe.preflight_docker

        def tripwire():
            called["preflight"] = True
            return real_preflight()

        monkeypatch.setattr(run_recipe, "preflight_docker", tripwire)

        # Build a minimal recipes dir with no recipes so --lint-all returns 2
        # without touching docker; important: main must not have called preflight.
        recipes = tmp_path / "recipes"
        recipes.mkdir()
        monkeypatch.chdir(tmp_path)

        rc = main(["--lint-all"])
        assert called["preflight"] is False

    def test_lint_single_works_without_docker_preflight(self, monkeypatch, tmp_path):
        from run_recipe import main

        called = {"preflight": False}
        import run_recipe

        def tripwire():
            called["preflight"] = True
            return None

        monkeypatch.setattr(run_recipe, "preflight_docker", tripwire)

        fake = tmp_path / "nope.yaml"
        # Recipe doesn't exist → main returns 2 BEFORE calling preflight
        rc = main([str(fake), "--lint"])
        assert rc == 2
        assert called["preflight"] is False


class TestRunCellCidfileUnlink:
    """Regression test per Pitfall 2 + Open Q4: cidfile must be unlinked on every path."""

    def test_cidfile_unlinked_after_success(self, monkeypatch, minimal_valid_recipe):
        from run_recipe import run_cell

        created_cidfiles: list = []

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                cidarg = next(
                    (a for a in cmd if a.startswith("--cidfile=")), None
                )
                if cidarg:
                    cidpath = Path(cidarg.split("=", 1)[1])
                    cidpath.write_text("fake-cid-abc")
                    created_cidfiles.append(cidpath)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
        )
        assert created_cidfiles
        for p in created_cidfiles:
            assert not p.exists(), (
                f"cidfile not unlinked after success: {p}"
            )

    def test_cidfile_unlinked_after_invoke_fail(
        self, monkeypatch, minimal_valid_recipe
    ):
        from run_recipe import run_cell

        created_cidfiles: list = []

        def fake_run(cmd, **k):
            if cmd[:2] == ["docker", "run"]:
                cidarg = next(
                    (a for a in cmd if a.startswith("--cidfile=")), None
                )
                if cidarg:
                    cidpath = Path(cidarg.split("=", 1)[1])
                    cidpath.write_text("fake-cid-abc")
                    created_cidfiles.append(cidpath)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=2, stdout="", stderr="boom"
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="K",
            api_key_val="v",
            quiet=True,
        )
        assert created_cidfiles
        for p in created_cidfiles:
            assert not p.exists(), (
                f"cidfile not unlinked after invoke-fail: {p}"
            )
