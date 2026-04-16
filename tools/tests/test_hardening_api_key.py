"""Hardening tests for resolve_api_key — cross-provider key bleed.

Regression gate for the vulnerability the function's own docstring names as
the anti-pattern: "Mixing those two concerns causes cross-provider key bleed
(e.g. an OpenAI direct key in the host env being injected as an OpenRouter
key)." — and then does exactly that via a hardcoded alias list.

The fix: canonical var ONLY. If the recipe declares
`runtime.process_env.api_key = ANTHROPIC_API_KEY`, the runner looks up
ANTHROPIC_API_KEY — not OPENROUTER_API_KEY.
"""
import pytest

from run_recipe import resolve_api_key


def _recipe(canonical_var: str) -> dict:
    return {
        "runtime": {
            "process_env": {
                "api_key": canonical_var,
            },
        },
    }


class TestResolveApiKeyCanonicalOnly:
    def test_finds_canonical_var_in_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        var, val = resolve_api_key(_recipe("ANTHROPIC_API_KEY"), tmp_path)
        assert var == "ANTHROPIC_API_KEY"
        assert val == "sk-ant-test"

    def test_finds_canonical_var_in_repo_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        (tmp_path / ".env").write_text('ANTHROPIC_API_KEY="sk-ant-fromfile"\n')
        var, val = resolve_api_key(_recipe("ANTHROPIC_API_KEY"), tmp_path)
        assert var == "ANTHROPIC_API_KEY"
        assert val == "sk-ant-fromfile"

    def test_process_env_beats_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "from-process")
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-file\n")
        _, val = resolve_api_key(_recipe("ANTHROPIC_API_KEY"), tmp_path)
        assert val == "from-process"


class TestResolveApiKeyNoBleed:
    """The load-bearing hardening: keys declared for one provider must not be
    silently substituted from another provider's env var."""

    def test_anthropic_recipe_does_not_leak_openrouter_key(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-leak")
        with pytest.raises(SystemExit) as exc:
            resolve_api_key(_recipe("ANTHROPIC_API_KEY"), tmp_path)
        msg = str(exc.value)
        assert "ANTHROPIC_API_KEY" in msg
        # The error should NOT tell the user the missing key was satisfied
        # by a sibling provider's var.
        assert "sk-or-leak" not in msg

    def test_openai_recipe_does_not_leak_openrouter_key(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-leak")
        with pytest.raises(SystemExit):
            resolve_api_key(_recipe("OPENAI_API_KEY"), tmp_path)

    def test_error_message_names_only_canonical_var(self, monkeypatch, tmp_path):
        """Error should not suggest the user set OPENROUTER_API_KEY as a
        fallback for an Anthropic recipe."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            resolve_api_key(_recipe("ANTHROPIC_API_KEY"), tmp_path)
        msg = str(exc.value)
        assert "ANTHROPIC_API_KEY" in msg
        # Must not tell the user to set OPEN_ROUTER_API_TOKEN as a fallback.
        assert "OPEN_ROUTER_API_TOKEN" not in msg


class TestResolveApiKeyOpenRouter:
    """The existing 5 recipes all declare api_key: OPENROUTER_API_KEY. This
    verifies the canonical lookup still works for them unchanged."""

    def test_openrouter_recipe_still_works(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        var, val = resolve_api_key(_recipe("OPENROUTER_API_KEY"), tmp_path)
        assert var == "OPENROUTER_API_KEY"
        assert val == "sk-or-test"

    def test_openrouter_recipe_reads_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        (tmp_path / ".env").write_text("OPENROUTER_API_KEY=from-file\n")
        _, val = resolve_api_key(_recipe("OPENROUTER_API_KEY"), tmp_path)
        assert val == "from-file"
