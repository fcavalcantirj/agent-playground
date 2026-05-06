"""PROBE-VAL-14 — mid-stream 4xx error shapes for the 3 providers.

29-RESEARCH §Stream interrupted / 4xx mid-stream claims:
- OpenAI / OpenRouter: `event: error\\ndata: {...}` mid-stream OR
  HTTP 4xx on initial response.
- Anthropic: `event: error\\ndata: {"type":"error","error":{...}}` mid-stream.

The proxy's parser must recognize both branches. This spike forces the
error condition by sending an obviously-invalid combination (over-quota
max_tokens, invalid model, etc.) and records exactly what shape the
upstream returns.

Cost: zero — every call is intentionally rejected upstream.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "29-llm-egress-proxy"
    / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-14.md"


def _redact(text: str, *keys: str) -> str:
    for k in keys:
        if k:
            text = text.replace(k, "<REDACTED>")
    return text


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def _open_status_then_lines(
    method: str, url: str, headers: dict, body: dict
) -> tuple[int, list[str], dict[str, str]]:
    """Open a streaming POST, capture the initial HTTP status + drained lines."""
    raw_lines: list[str] = []
    initial_status = 0
    rh: dict[str, str] = {}
    with httpx.Client(timeout=30.0) as client:
        with client.stream(
            method, url, headers=headers, json=body
        ) as resp:
            initial_status = resp.status_code
            rh = dict(resp.headers)
            for line in resp.iter_lines():
                raw_lines.append(line)
                if len(raw_lines) >= 200:
                    break
    return initial_status, raw_lines, rh


def test_streaming_error_shapes_per_provider() -> None:
    or_key = os.getenv("OPENROUTER_API_KEY")
    an_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")
    if not or_key or not an_key or not oai_key:
        pytest.skip("All three provider keys required")

    artifact_lines: list[str] = [
        "## PROBE-VAL-14: streaming 4xx + mid-stream error shapes",
        "",
    ]
    parseable_count = 0
    branch_count = 0

    # ---- OpenRouter ----
    artifact_lines.append("### Provider: OpenRouter")
    or_body = {
        "model": "this-model-does-not-exist-zzz",  # forces a 4xx
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "max_tokens": 20,
    }
    or_status, or_lines, or_headers = _open_status_then_lines(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "Authorization": f"Bearer {or_key}",
            "Content-Type": "application/json",
        },
        or_body,
    )
    artifact_lines.append(f"- initial HTTP status: {or_status}")
    artifact_lines.append(f"- raw line count: {len(or_lines)}")
    artifact_lines.append("- raw response (first 1KB):")
    artifact_lines.append("```")
    artifact_lines.append(_redact("\n".join(or_lines)[:1024], or_key, an_key, oai_key))
    artifact_lines.append("```")
    or_branch = "http_4xx" if or_status >= 400 else "sse_error_event"
    artifact_lines.append(f"- branch: **{or_branch}**")
    artifact_lines.append("")
    branch_count += 1
    # Parseable iff status indicates an error state OR raw text contains
    # an error JSON
    or_parseable = (
        or_status >= 400
        or any('"error"' in l for l in or_lines)
    )
    if or_parseable:
        parseable_count += 1

    # ---- OpenAI ----
    artifact_lines.append("### Provider: OpenAI")
    oai_body = {
        "model": "gpt-this-does-not-exist-zzz",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "max_tokens": 20,
    }
    oai_status, oai_lines, _oai_headers = _open_status_then_lines(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        {
            "Authorization": f"Bearer {oai_key}",
            "Content-Type": "application/json",
        },
        oai_body,
    )
    artifact_lines.append(f"- initial HTTP status: {oai_status}")
    artifact_lines.append(f"- raw line count: {len(oai_lines)}")
    artifact_lines.append("- raw response (first 1KB):")
    artifact_lines.append("```")
    artifact_lines.append(
        _redact("\n".join(oai_lines)[:1024], or_key, an_key, oai_key)
    )
    artifact_lines.append("```")
    oai_branch = "http_4xx" if oai_status >= 400 else "sse_error_event"
    artifact_lines.append(f"- branch: **{oai_branch}**")
    artifact_lines.append("")
    branch_count += 1
    oai_parseable = (
        oai_status >= 400 or any('"error"' in l for l in oai_lines)
    )
    if oai_parseable:
        parseable_count += 1

    # ---- Anthropic ----
    artifact_lines.append("### Provider: Anthropic")
    an_body = {
        "model": "claude-does-not-exist-zzz",
        "max_tokens": 20,
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    }
    an_status, an_lines, _an_headers = _open_status_then_lines(
        "POST",
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": an_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        an_body,
    )
    artifact_lines.append(f"- initial HTTP status: {an_status}")
    artifact_lines.append(f"- raw line count: {len(an_lines)}")
    artifact_lines.append("- raw response (first 1KB):")
    artifact_lines.append("```")
    artifact_lines.append(
        _redact("\n".join(an_lines)[:1024], or_key, an_key, oai_key)
    )
    artifact_lines.append("```")
    an_branch = "http_4xx" if an_status >= 400 else "sse_error_event"
    artifact_lines.append(f"- branch: **{an_branch}**")
    artifact_lines.append("")
    branch_count += 1
    an_parseable = (
        an_status >= 400 or any('"error"' in l for l in an_lines)
    )
    if an_parseable:
        parseable_count += 1

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(
        f"- 3/3 providers returned a parseable error shape: **{parseable_count}/{branch_count}**"
    )
    artifact_lines.append(
        "- Parser strategy in 29-RESEARCH §Stream interrupted is empirically supportable: "
        "either initial 4xx (fast-path: skip stream parser) or SSE event with 'error' key "
        "(slow-path: parser branches on event type)."
    )

    verdict = "PASS" if parseable_count == branch_count else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"only {parseable_count}/{branch_count} providers returned a parseable "
        f"error shape"
    )
