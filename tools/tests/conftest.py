import json
import subprocess
import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

# Add tools/ to sys.path so tests can import run_recipe
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_recipe import load_recipe, lint_recipe, evaluate_pass_if


@pytest.fixture
def yaml_rt():
    """Pre-configured ruamel YAML instance matching runner's config."""
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)

    def _represent_none(dumper, _data):
        return dumper.represent_scalar("tag:yaml.org,2002:null", "null")

    y.representer.add_representer(type(None), _represent_none)
    return y


@pytest.fixture
def schema():
    """Load the JSON Schema for recipe validation."""
    schema_path = Path(__file__).parent.parent / "ap.recipe.schema.json"
    return json.loads(schema_path.read_text())


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Factory: configure subprocess.run to return canned output."""

    def _configure(stdout="", returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=returncode,
                stdout=stdout if kwargs.get("capture_output") else None,
                stderr=stderr if kwargs.get("capture_output") else None,
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

    return _configure


@pytest.fixture
def mock_subprocess_timeout(monkeypatch):
    """Factory: configure subprocess.run to raise TimeoutExpired on docker run,
    return success on cleanup calls (docker kill, docker rm, rm -rf).

    Optionally records every non-docker-run invocation so tests can assert the
    cleanup path (docker kill / docker rm -f) fired. Per Phase 10 RESEARCH.md
    §Pitfall 5 — TimeoutExpired injection is what drives the TIMEOUT category
    code path; the recorded invocations list is what lets W5's
    `test_docker_kill_invoked_on_timeout` assert the load-bearing D-03 promise
    that `docker kill <cid>` + `docker rm -f <cid>` actually fire on timeout.
    """

    recorded: list[list[str]] = []

    def _configure(timeout_s: int = 1, *, record: bool = False):
        def fake_run(cmd, **kwargs):
            if len(cmd) >= 2 and list(cmd[:2]) == ["docker", "run"]:
                raise subprocess.TimeoutExpired(
                    cmd=cmd, timeout=timeout_s, output="", stderr=""
                )
            if record:
                recorded.append(list(cmd))
            # docker kill, docker rm -f, rm -rf (cleanup), docker version (preflight) etc.
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="" if kwargs.get("capture_output") else None,
                stderr="" if kwargs.get("capture_output") else None,
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        return recorded

    return _configure


@pytest.fixture
def mock_subprocess_dispatch(monkeypatch):
    """Factory: per-command return code dispatcher.

    Usage:
        mock_subprocess_dispatch({
            ("git", "clone"): (0, "", ""),
            ("docker", "build"): (125, "", "error response"),
            ("docker", "image", "inspect"): (1, "", ""),
        }, default=(0, "", ""))

    Dispatches by argv prefix — first matching tuple wins. The default tuple
    handles any command not explicitly mapped. Used by Phase 10 category tests
    to drive BUILD_FAIL / PULL_FAIL / CLONE_FAIL / INVOKE_FAIL paths by giving
    each shelled-out tool a distinct return code.
    """

    def _configure(rules: dict, *, default=(0, "", "")):
        def fake_run(cmd, **kwargs):
            for prefix, (rc, so, se) in rules.items():
                if len(cmd) >= len(prefix) and tuple(cmd[: len(prefix)]) == prefix:
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=rc,
                        stdout=so if kwargs.get("capture_output") else None,
                        stderr=se if kwargs.get("capture_output") else None,
                    )
            rc, so, se = default
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=rc,
                stdout=so if kwargs.get("capture_output") else None,
                stderr=se if kwargs.get("capture_output") else None,
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

    return _configure


@pytest.fixture
def fake_cidfile(monkeypatch, tmp_path):
    """Factory: pre-populate a cidfile on disk with a known container ID.

    Writes the cid text to a real file under `tmp_path` and patches
    `run_recipe.Path` so any construction of `/tmp/ap-cid-*.cid` inside
    `run_cell` resolves to that populated file. The point of this fixture is
    W5's D-03 maturity test: when `run_cell` hits TimeoutExpired, it reads
    the cidfile, extracts the CID, and calls `docker kill <cid>` + `docker
    rm -f <cid>`. Pre-populating the cidfile is what lets the test assert
    the exact CID made it into those calls.

    Usage:
        cid = "fake-cid-abc123"
        cidfile_path = fake_cidfile(cid=cid)
        # Now run_cell's Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")
        # construction is redirected to cidfile_path; the kill/rm reap path
        # reads the pre-populated content and targets the known CID.

    Returns: Path to the on-disk cidfile (already populated with cid text).
    """

    def _configure(*, cid: str = "fake-cid-abc123") -> Path:
        cidfile_path = tmp_path / "cidfile.cid"
        cidfile_path.write_text(cid)

        # Intercept Path construction in run_recipe for the specific cidfile
        # pattern. run_cell does `cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")`,
        # so we patch run_recipe.Path (the namespace run_cell uses, since run_recipe
        # imports Path via `from pathlib import Path`) — NOT pathlib.Path globally,
        # which would break every other code path.
        import run_recipe as _rr
        original_path = _rr.Path

        def _path_ctor(arg, *rest, **kwargs):
            if isinstance(arg, str) and arg.startswith("/tmp/ap-cid-"):
                return cidfile_path
            return original_path(arg, *rest, **kwargs)

        monkeypatch.setattr(_rr, "Path", _path_ctor)

        return cidfile_path

    return _configure


@pytest.fixture
def minimal_valid_recipe():
    """A minimal recipe dict that passes lint."""
    return {
        "apiVersion": "ap.recipe/v0.1",
        "name": "test-agent",
        "display_name": "Test Agent",
        "description": "A test recipe for unit testing.",
        "source": {
            "repo": "https://github.com/test/test",
            "ref": "abc123def456789012345678901234567890abcd",
        },
        "build": {
            "mode": "upstream_dockerfile",
        },
        "runtime": {
            "provider": "openrouter",
            "process_env": {
                "api_key": "OPENROUTER_API_KEY",
                "base_url": None,
                "model": None,
            },
            "volumes": [
                {
                    "name": "test_vol",
                    "host": "per_session_tmpdir",
                    "container": "/data",
                }
            ],
        },
        "invoke": {
            "mode": "cli-passthrough",
            "spec": {
                "argv": ["echo", "$PROMPT"],
            },
        },
        "smoke": {
            "prompt": "hello",
            "pass_if": "exit_zero",
            "verified_cells": [
                {
                    "model": "test/model",
                    "verdict": "PASS",
                    "category": "PASS",
                    "detail": "",
                },
            ],
        },
        "metadata": {
            "recon_date": "2026-04-15",
            "recon_by": "test",
            "source_citations": ["test"],
        },
    }


@pytest.fixture
def broken_recipes_dir():
    """Path to the broken_recipes directory."""
    return Path(__file__).parent / "broken_recipes"


@pytest.fixture
def real_recipes():
    """Paths to the 5 committed recipes — used by TestLintRealRecipes regression guard.

    Returns a list of (name, Path) tuples. Adding a new recipe to recipes/
    means adding it here too — explicit list keeps the test deterministic
    and surfaces the addition in code review.
    """
    repo_root = Path(__file__).resolve().parents[2]
    return [
        ("hermes",   repo_root / "recipes" / "hermes.yaml"),
        ("picoclaw", repo_root / "recipes" / "picoclaw.yaml"),
        ("nullclaw", repo_root / "recipes" / "nullclaw.yaml"),
        ("nanobot",  repo_root / "recipes" / "nanobot.yaml"),
        ("openclaw", repo_root / "recipes" / "openclaw.yaml"),
    ]
