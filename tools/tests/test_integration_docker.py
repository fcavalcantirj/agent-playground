"""Real-Docker integration tests.

These tests spawn actual containers against the live Docker daemon and verify
the cidfile + docker kill reap path does what it claims under mocks. The W5
gate in the unit tests proves "we CALL the right commands"; these tests prove
"the container actually dies."

Run explicitly:  pytest -m integration
Default run skips these (no `-m integration` flag), so CI without Docker
remains fast.

Each test skips gracefully if:
- Docker CLI is not on PATH
- Docker daemon is unreachable
- alpine:latest pull fails (no network, or Docker Hub throttle)
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            timeout=5,
            capture_output=True,
            text=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _ensure_alpine() -> bool:
    """Pull alpine:latest if not cached. Returns True if image is available."""
    r = subprocess.run(
        ["docker", "image", "inspect", "alpine:latest"],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return True
    r = subprocess.run(
        ["docker", "pull", "alpine:latest"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.returncode == 0


@pytest.fixture(scope="module")
def docker_ready():
    if not _docker_available():
        pytest.skip("Docker daemon unreachable — skipping real-Docker tests")
    if not _ensure_alpine():
        pytest.skip("alpine:latest not available — skipping")
    yield


def _container_exists(cid: str) -> bool:
    """Return True if a container with this CID (short or long) still exists."""
    r = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", cid],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


class TestRealDockerCidfileReap:
    """The load-bearing integration test: start a container that will
    outlive its timeout, let run_cell's TimeoutExpired handler fire, and
    verify the container is actually gone from the host afterward."""

    def test_cidfile_kill_reaps_long_running_container(self, docker_ready, tmp_path):
        # Drive run_cell directly with an alpine sleep recipe.
        # smoke.timeout_s is 3s; container sleeps 120s — so the timeout will fire.
        import run_recipe

        recipe = {
            "name": "int-reap-test",
            "runtime": {
                "volumes": [
                    {
                        "name": "data",
                        "host": "per_session_tmpdir",
                        "container": "/tmp/data",
                    }
                ],
            },
            "invoke": {
                "mode": "cli-passthrough",
                "spec": {
                    "entrypoint": "sleep",
                    "argv": ["120"],
                },
            },
            "smoke": {
                "prompt": "unused",
                "pass_if": "exit_zero",
                "timeout_s": 3,
            },
        }

        verdict, details = run_recipe.run_cell(
            recipe,
            image_tag="alpine:latest",
            prompt="unused",
            model="none",
            api_key_var="NO_KEY",
            api_key_val="x",
            quiet=True,
            smoke_timeout_s=3,
        )

        # The timeout should classify as TIMEOUT.
        assert verdict.category.value == "TIMEOUT", (
            f"expected TIMEOUT, got {verdict.category.value}: {verdict.detail}"
        )

        # No container named/matching our ephemeral UUID should be running.
        # Since we used --rm and --cidfile, after the kill + rm -f the
        # container should be gone; a broad check: no containers in state
        # "running" with alpine:latest image from the last 30s.
        r = subprocess.run(
            [
                "docker", "ps",
                "--filter", "ancestor=alpine:latest",
                "--filter", "status=running",
                "--format", "{{.ID}} {{.Command}}",
            ],
            capture_output=True,
            text=True,
        )
        # It's fine if there are OTHER alpine containers running (from other
        # things on the host) — but none of them should be running `sleep 120`
        # from our cell invocation.
        lines = [l for l in r.stdout.splitlines() if "sleep" in l and "120" in l]
        assert lines == [], (
            f"container with `sleep 120` still running after timeout reap: {lines}"
        )


class TestRealDockerHappyPath:
    """Also prove the happy path works end-to-end: a fast exit-zero container
    classifies as PASS and cleans up its cidfile / env-file."""

    def test_happy_path_exit_zero(self, docker_ready):
        import run_recipe

        recipe = {
            "name": "int-happy-test",
            "runtime": {
                "volumes": [
                    {
                        "name": "data",
                        "host": "per_session_tmpdir",
                        "container": "/tmp/data",
                    }
                ],
            },
            "invoke": {
                "mode": "cli-passthrough",
                "spec": {
                    "entrypoint": "echo",
                    "argv": ["hello from alpine"],
                },
            },
            "smoke": {
                "prompt": "unused",
                "pass_if": "exit_zero",
                "timeout_s": 30,
            },
        }

        verdict, details = run_recipe.run_cell(
            recipe,
            image_tag="alpine:latest",
            prompt="unused",
            model="none",
            api_key_var="NO_KEY",
            api_key_val="dummy",
            quiet=True,
            smoke_timeout_s=30,
        )

        assert verdict.category.value == "PASS", (
            f"expected PASS, got {verdict.category.value}: {verdict.detail}"
        )
        assert "hello from alpine" in details["filtered_payload"]

        # No /tmp/ap-cid-*.cid files should leak.
        leaked_cids = list(Path("/tmp").glob("ap-cid-*.cid"))
        assert not leaked_cids, f"cidfile leaked: {leaked_cids}"

        # No /tmp/ap-env-* files should leak either.
        leaked_envs = list(Path("/tmp").glob("ap-env-*"))
        assert not leaked_envs, f"env-file leaked: {leaked_envs}"
