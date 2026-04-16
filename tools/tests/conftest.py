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
