"""Hardening tests for API key delivery via --env-file.

Regression gate: `docker run -e KEY=<actual-value>` leaks the key to the
kernel process listing (visible to any user on the host via `ps` or
/proc/*/cmdline). The fix passes the key through `--env-file <tmp>` with
the value written to a chmod-600 file that is unlinked after the run.
"""
import os
import subprocess
from pathlib import Path

import pytest

import run_recipe
from run_recipe import run_cell


@pytest.fixture
def openrouter_recipe():
    return {
        "name": "test",
        "runtime": {
            "volumes": [{"name": "d", "host": "per_session_tmpdir", "container": "/data"}],
        },
        "invoke": {
            "mode": "cli-passthrough",
            "spec": {"argv": ["echo", "hi"]},
        },
        "smoke": {"prompt": "hi", "pass_if": "exit_zero", "timeout_s": 5},
    }


class TestEnvFileKeyDelivery:
    def test_docker_cmd_does_not_contain_raw_key(
        self, monkeypatch, tmp_path, openrouter_recipe
    ):
        """The key value must never appear in the docker argv itself."""
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            # First call is `docker run` — record it.
            if "docker" in cmd[0] and "run" in cmd[1]:
                if "argv" not in captured:
                    captured["argv"] = list(cmd)
                    # Read the env-file that was written and stash its contents.
                    for i, tok in enumerate(cmd):
                        if tok == "--env-file" and i + 1 < len(cmd):
                            envpath = Path(cmd[i + 1])
                            captured["envfile"] = envpath
                            captured["envfile_contents"] = (
                                envpath.read_text() if envpath.exists() else None
                            )
                            try:
                                captured["envfile_mode"] = oct(envpath.stat().st_mode & 0o777)
                            except FileNotFoundError:
                                captured["envfile_mode"] = None
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        SECRET = "sk-or-supersecret-value-1234567890"
        run_cell(
            openrouter_recipe,
            image_tag="img:test",
            prompt="hi",
            model="m",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val=SECRET,
            quiet=True,
        )

        # The raw key must not appear anywhere in the docker argv.
        assert "argv" in captured
        for tok in captured["argv"]:
            assert SECRET not in tok, f"raw key leaked in docker argv: {tok}"

        # Env file should have carried the key (read during the fake_run above).
        assert captured.get("envfile_contents") is not None
        assert SECRET in captured["envfile_contents"]
        assert "OPENROUTER_API_KEY=" in captured["envfile_contents"]

        # Env file permissions: owner r/w only.
        assert captured.get("envfile_mode") == oct(0o600)

    def test_docker_cmd_has_env_file_flag(
        self, monkeypatch, tmp_path, openrouter_recipe
    ):
        captured = {}

        def fake_run(cmd, **kwargs):
            if "docker" in cmd[0] and "run" in cmd[1]:
                if "argv" not in captured:
                    captured["argv"] = list(cmd)
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            openrouter_recipe,
            image_tag="img:test",
            prompt="hi",
            model="m",
            api_key_var="ANTHROPIC_API_KEY",
            api_key_val="sk-ant-test",
            quiet=True,
        )

        argv = captured["argv"]
        assert "--env-file" in argv
        # Make sure the old `-e KEY=VAL` form is NOT present.
        joined = " ".join(argv)
        assert "ANTHROPIC_API_KEY=sk-ant-test" not in joined
        # `-e` followed by a `KEY=VAL` token is the anti-pattern we removed.
        for i, tok in enumerate(argv):
            if tok == "-e" and i + 1 < len(argv):
                assert "=" not in argv[i + 1] or not argv[i + 1].startswith(
                    "ANTHROPIC_API_KEY="
                )


class TestEnvFileCleanup:
    def test_env_file_unlinked_after_success(
        self, monkeypatch, tmp_path, openrouter_recipe
    ):
        captured_path: list[Path] = []

        def fake_run(cmd, **kwargs):
            if "docker" in cmd[0] and "run" in cmd[1]:
                for i, tok in enumerate(cmd):
                    if tok == "--env-file" and i + 1 < len(cmd):
                        captured_path.append(Path(cmd[i + 1]))
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            openrouter_recipe,
            image_tag="img:test",
            prompt="hi",
            model="m",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="sk-test",
            quiet=True,
        )

        assert captured_path, "no env-file path captured"
        # After run_cell returns, the env file must be gone.
        assert not captured_path[0].exists(), \
            f"env-file {captured_path[0]} leaked on disk after run_cell completed"

    def test_env_file_unlinked_after_timeout(
        self, monkeypatch, tmp_path, openrouter_recipe
    ):
        captured_path: list[Path] = []

        def fake_run(cmd, **kwargs):
            if "docker" in cmd[0] and "run" in cmd[1]:
                for i, tok in enumerate(cmd):
                    if tok == "--env-file" and i + 1 < len(cmd):
                        captured_path.append(Path(cmd[i + 1]))
                raise subprocess.TimeoutExpired(
                    cmd=cmd, timeout=1, output=b"", stderr=b""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            openrouter_recipe,
            image_tag="img:test",
            prompt="hi",
            model="m",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val="sk-test",
            quiet=True,
        )

        assert captured_path
        assert not captured_path[0].exists(), \
            "env-file leaked after timeout path"


class TestEnvFileContent:
    def test_env_file_single_line_key_only(
        self, monkeypatch, tmp_path, openrouter_recipe
    ):
        """The env file should contain exactly one KEY=VALUE line and nothing else."""
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            if "docker" in cmd[0] and "run" in cmd[1]:
                for i, tok in enumerate(cmd):
                    if tok == "--env-file" and i + 1 < len(cmd):
                        ep = Path(cmd[i + 1])
                        captured["lines"] = ep.read_text().splitlines()
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        run_cell(
            openrouter_recipe,
            image_tag="img:test",
            prompt="hi",
            model="m",
            api_key_var="TEST_KEY",
            api_key_val="s3cret",
            quiet=True,
        )

        lines = [l for l in captured["lines"] if l.strip()]
        assert lines == ["TEST_KEY=s3cret"]
