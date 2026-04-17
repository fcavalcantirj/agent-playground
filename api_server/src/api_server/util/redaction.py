"""String redaction helpers for server-side logging + error envelope building.

Mirrors the posture of ``tools/run_recipe.py::_redact_api_key`` but for the
server side, where the raw runner stderr may have already been processed
before reaching code that emits it downstream. Use as defense-in-depth; the
PRIMARY redaction mechanism is the log-allowlist in ``log_redact.py``.

Plan 19-06 artifact. Phase 19 CONTEXT.md D-02 and RESEARCH.md §Security
Domain V7/V8 both call for defense-in-depth here: even if a future code
path accidentally logs stderr or an exception message, this helper should
be called first so known BYOK patterns are masked.
"""
from __future__ import annotations

import re

# Common BYOK/OAuth token shapes observed across providers.
#   - ``Bearer <token>`` from Authorization headers (OAuth2, OpenRouter, Anthropic)
#   - ``sk-...`` / ``sk-ant-...`` from OpenAI / Anthropic direct
#   - ``or-...`` from OpenRouter's provisioning / admin API tokens
_BEARER_RE = re.compile(r"Bearer [A-Za-z0-9\-_\.]{20,}")
_SK_RE = re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9\-_]{16,}")
_OR_RE = re.compile(r"\bor-[A-Za-z0-9\-_]{16,}")


def mask_known_prefixes(text: str, *, api_key_val: str | None = None) -> str:
    """Return ``text`` with BYOK-looking substrings replaced by ``<REDACTED>``.

    Mask order:

    1. Literal ``api_key_val`` (only when supplied and ≥8 chars — avoids
       accidentally masking common short substrings such as ``"abc"``).
    2. ``Bearer <token>`` patterns. The ``Bearer `` prefix is preserved for
       log clarity; only the opaque token body is redacted.
    3. Provider-specific prefixes ``sk-``, ``sk-ant-``, and ``or-`` followed
       by ≥16 URL-safe characters.

    Returns an empty string when ``text`` is falsy.
    """
    if not text:
        return ""
    out = text
    if api_key_val and len(api_key_val) >= 8:
        out = out.replace(api_key_val, "<REDACTED>")
    out = _BEARER_RE.sub("Bearer <REDACTED>", out)
    out = _SK_RE.sub("<REDACTED>", out)
    out = _OR_RE.sub("<REDACTED>", out)
    return out
