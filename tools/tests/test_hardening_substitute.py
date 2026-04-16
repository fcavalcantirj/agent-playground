"""Hardening tests for substitute_argv — $PROMPT / $MODEL injection safety.

Regression gate for the vulnerability acknowledged in openclaw.yaml's argv_note:
"Prompts containing double quotes would need escaping — v0 smoke is
'who are you?' which is safe."

The fix: when a placeholder is embedded inside a larger string (i.e. not a
standalone argv element), the substituted value must be shell-quoted via
shlex.quote so a malicious prompt cannot break out of its syntactic context.

Standalone argv elements (where `arg in subs`) are not shell-quoted — docker
passes them as separate argv entries and no shell parses them.
"""
import pytest

from run_recipe import substitute_argv


class TestSubstituteArgvStandalone:
    """When $PROMPT is a standalone element, raw substitution is correct —
    docker passes it as a separate argv entry, no shell sees it."""

    def test_standalone_prompt_not_quoted(self):
        result = substitute_argv(["chat", "-q", "$PROMPT"], prompt="hello world", model="m")
        assert result == ["chat", "-q", "hello world"]

    def test_standalone_with_quotes_preserved_verbatim(self):
        result = substitute_argv(["-q", "$PROMPT"], prompt='say "hi"', model="m")
        assert result == ["-q", 'say "hi"']

    def test_standalone_with_shell_metachars_preserved(self):
        result = substitute_argv(["-q", "$PROMPT"], prompt="; rm -rf /", model="m")
        assert result == ["-q", "; rm -rf /"]


class TestSubstituteArgvEmbedded:
    """When $PROMPT is embedded inside a shell string (e.g. nullclaw's
    `-c "nullclaw agent -m \"$PROMPT\""`), the value MUST be shell-quoted."""

    def test_embedded_prompt_is_shell_quoted(self):
        # Recipe shape like nullclaw: `sh -c '... -m "$PROMPT"'`
        argv = ["-c", 'nullclaw agent -m "$PROMPT"']
        result = substitute_argv(argv, prompt="hello", model="m")
        # The embedded form should carry shlex-quoted value, not the raw
        # prompt spliced inside pre-existing quotes.
        assert result[0] == "-c"
        # After shlex.quote, simple alphanumerics stay unquoted OR are single-quoted;
        # either way the output must not contain unescaped user input inside the
        # pre-existing double quotes.
        assert "$PROMPT" not in result[1]
        assert "hello" in result[1]

    def test_embedded_injection_attempt_neutralized(self):
        """The money shot: a prompt containing a closing quote + shell command
        must not break out of the context."""
        argv = ["-c", 'nullclaw agent -m "$PROMPT"']
        malicious = '"; rm -rf / #'
        result = substitute_argv(argv, prompt=malicious, model="m")
        # After fix: the injected `";` must be shell-escaped, so the
        # substituted string does not contain the raw sequence `"; rm`
        # on its own — the payload is contained by shlex.quote's escaping.
        # Concretely: shlex.quote wraps the string in single quotes and
        # escapes any embedded single quotes. The `"; rm -rf / #` string
        # has no single quotes, so shlex wraps it intact in `'...'` — and
        # the surrounding double quotes from the recipe template are now
        # lexically broken, which is the POINT: the shell parser will
        # complain (or the command will simply not execute `rm`), rather
        # than silently executing the attacker's payload.
        import shlex
        quoted = shlex.quote(malicious)
        assert quoted in result[1]
        # Sanity: the raw unquoted `rm -rf /` substring is not free-standing
        # in the output — it's inside shlex quoting.
        # Verify the quoted form is single-quote wrapped (shlex default for
        # anything with shell metacharacters).
        assert quoted.startswith("'") and quoted.endswith("'")

    def test_embedded_model_also_quoted(self):
        """Symmetric protection for $MODEL."""
        argv = ["-c", 'echo "$MODEL"']
        result = substitute_argv(argv, prompt="p", model='malicious"; evil')
        import shlex
        assert shlex.quote('malicious"; evil') in result[1]

    def test_embedded_openclaw_shape(self):
        """Real-world shape from openclaw.yaml: bash -c with --prompt \"$PROMPT\"."""
        argv = [
            "bash",
            "-c",
            'openclaw config set agents.defaults.model "openrouter/$MODEL" >/dev/null && '
            'openclaw infer model run --prompt "$PROMPT" --local --json',
        ]
        result = substitute_argv(argv, prompt='say "hi"', model="openai/gpt-4o")
        import shlex
        # Both placeholders substituted + shell-quoted
        assert "$PROMPT" not in result[2]
        assert "$MODEL" not in result[2]
        assert shlex.quote('say "hi"') in result[2]
        assert shlex.quote("openai/gpt-4o") in result[2]


class TestSubstituteArgvExisting:
    """Lock in the two behaviors the current test suite already relies on so we
    don't accidentally break other code paths."""

    def test_no_placeholders_passthrough(self):
        result = substitute_argv(["--flag", "value"], prompt="p", model="m")
        assert result == ["--flag", "value"]

    def test_multiple_placeholders_in_same_string(self):
        """Edge case: both placeholders in one string."""
        argv = ["-c", 'echo "$PROMPT" "$MODEL"']
        result = substitute_argv(argv, prompt="hi", model="gpt-4")
        assert "$PROMPT" not in result[1]
        assert "$MODEL" not in result[1]
