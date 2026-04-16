"""Hardening tests for clone cache keyed on source.ref.

Previously: /tmp/ap-recipe-<name>-clone — keyed on recipe name only. Changing
source.ref silently pinned users to the old clone because the path already
existed. The fix: include a 12-char hash of source.ref in the clone path, so
any ref change creates a fresh clone dir. Old dirs become orphaned (harmless
disk occupation; --no-cache wipes all ap-recipe-<name>-*-clone dirs).
"""
import hashlib
from pathlib import Path

import pytest

from run_recipe import _clone_dir_for


def _short(ref: str) -> str:
    return hashlib.sha256(ref.encode()).hexdigest()[:12]


class TestCloneDirPath:
    def test_path_includes_ref_hash(self):
        p = _clone_dir_for("agent-x", "v1.0.0")
        assert _short("v1.0.0") in str(p)
        assert "agent-x" in str(p)

    def test_different_refs_yield_different_paths(self):
        p1 = _clone_dir_for("agent-x", "v1.0.0")
        p2 = _clone_dir_for("agent-x", "v2.0.0")
        assert p1 != p2

    def test_same_ref_yields_stable_path(self):
        p1 = _clone_dir_for("agent-x", "abc123def")
        p2 = _clone_dir_for("agent-x", "abc123def")
        assert p1 == p2

    def test_different_names_with_same_ref_differ(self):
        p1 = _clone_dir_for("agent-a", "same-ref")
        p2 = _clone_dir_for("agent-b", "same-ref")
        assert p1 != p2

    def test_none_ref_still_produces_deterministic_path(self):
        """When source.ref is absent, still produce a deterministic path —
        using a distinct sentinel hash so it cannot alias with a real ref."""
        p1 = _clone_dir_for("agent-x", None)
        p2 = _clone_dir_for("agent-x", None)
        assert p1 == p2

    def test_path_under_tmp(self):
        p = _clone_dir_for("agent-x", "v1")
        assert str(p).startswith("/tmp/ap-recipe-")
        assert str(p).endswith("-clone")
