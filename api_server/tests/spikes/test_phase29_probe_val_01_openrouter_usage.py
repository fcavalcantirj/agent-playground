"""PROBE-VAL-01 — OpenRouter inline usage chunk on streaming + non-streaming.

Empirically validates 29-RESEARCH §Streaming Capture Strategy + AMD-07
assumption: OpenRouter `/v1/chat/completions` returns a `usage` block on
both `stream=true` (in a final SSE chunk) and `stream=false` (in the
JSON body), and the relative position of the usage chunk vs `[DONE]`
is recorded so the parser strategy in 29-PATTERNS.md handles every
observed shape.

Cost ceiling: anthropic/claude-haiku-4-5 via OpenRouter, max_tokens=50,
2 calls (stream + non-stream) — total spend ~$0.0001 USD.

Run manually:

    set -a && source /Users/fcavalcanti/dev/agent-playground/.env && set +a
    cd api_server && uv run pytest \
        tests/spikes/test_phase29_probe_val_01_openrouter_usage.py \
        -v -m spike --tb=short
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
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-01.md"
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = "anthropic/claude-haiku-4-5"


def _redact_creds(text: str, key: str) -> str:
    """Remove the BYOK key from any logged transcript."""
    if not key:
        return text
    return text.replace(key, "<REDACTED-OR-KEY>")


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def test_openrouter_usage_inline_on_stream_and_nonstream() -> None:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY required (source .env first)")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 50,
    }
    artifact_lines: list[str] = []
    artifact_lines.append("## PROBE-VAL-01: OpenRouter inline usage chunk")
    artifact_lines.append("")
    artifact_lines.append(f"- model: `{MODEL}`")
    artifact_lines.append(f"- max_tokens: 50")
    artifact_lines.append("- BYOK key: `<REDACTED-OR-KEY>`")
    artifact_lines.append("")

    # ---- Variant A: stream=true with stream_options.include_usage ----
    stream_body = {
        **body,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    raw_lines: list[str] = []
    usage_chunk_index: int | None = None
    done_index: int | None = None
    found_usage: dict | None = None

    with httpx.Client(timeout=30.0) as client:
        with client.stream(
            "POST",
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json=stream_body,
        ) as resp:
            assert resp.status_code == 200, (
                f"OR stream returned {resp.status_code}: {resp.read()!r}"
            )
            for idx, line in enumerate(resp.iter_lines()):
                raw_lines.append(line)
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                payload = stripped[5:].strip()
                if payload == "[DONE]":
                    done_index = idx
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(event.get("usage"), dict):
                    usage_chunk_index = idx
                    found_usage = event["usage"]

    artifact_lines.append("### Variant A — stream=true")
    artifact_lines.append("")
    artifact_lines.append(f"- raw line count: {len(raw_lines)}")
    artifact_lines.append(f"- usage chunk line index: {usage_chunk_index}")
    artifact_lines.append(f"- [DONE] line index: {done_index}")
    artifact_lines.append("")
    if found_usage is not None:
        artifact_lines.append("```json")
        artifact_lines.append(json.dumps(found_usage, indent=2))
        artifact_lines.append("```")
        artifact_lines.append("")
    # Record the FIRST 4KB and LAST 1KB of the raw stream for downstream
    # plan reference.
    raw_concat = "\n".join(raw_lines)
    head = raw_concat[:4096]
    tail = raw_concat[-1024:] if len(raw_concat) > 4096 else ""
    artifact_lines.append("#### Raw stream (first 4KB)")
    artifact_lines.append("```")
    artifact_lines.append(_redact_creds(head, key))
    artifact_lines.append("```")
    if tail:
        artifact_lines.append("#### Raw stream (last 1KB)")
        artifact_lines.append("```")
        artifact_lines.append(_redact_creds(tail, key))
        artifact_lines.append("```")
    artifact_lines.append("")

    # Position note
    if usage_chunk_index is not None and done_index is not None:
        if usage_chunk_index < done_index:
            position = "usage BEFORE [DONE]"
        else:
            position = "usage AFTER [DONE] (post-DONE edge case — last-wins required)"
    elif usage_chunk_index is not None:
        position = "usage present, NO [DONE] sentinel observed"
    else:
        position = "NO usage chunk observed"
    artifact_lines.append(f"- ordering: **{position}**")
    artifact_lines.append("")

    stream_pass = (
        found_usage is not None
        and int(found_usage.get("prompt_tokens", 0)) > 0
        and int(found_usage.get("completion_tokens", 0)) > 0
    )

    # ---- Variant B: stream=false ----
    nonstream_body = {**body, "stream": False}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json=nonstream_body,
        )
    artifact_lines.append("### Variant B — stream=false")
    artifact_lines.append("")
    artifact_lines.append(f"- HTTP status: {resp.status_code}")
    nonstream_usage: dict | None = None
    if resp.status_code == 200:
        body_json = resp.json()
        nonstream_usage = body_json.get("usage")
        artifact_lines.append("```json")
        artifact_lines.append(
            json.dumps(
                {"id": body_json.get("id"), "usage": nonstream_usage},
                indent=2,
            )
        )
        artifact_lines.append("```")
    artifact_lines.append("")
    nonstream_pass = (
        nonstream_usage is not None
        and int(nonstream_usage.get("prompt_tokens", 0)) > 0
        and int(nonstream_usage.get("completion_tokens", 0)) > 0
    )

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- stream=true carries usage: **{stream_pass}**")
    artifact_lines.append(
        f"- stream=false carries usage: **{nonstream_pass}**"
    )
    artifact_lines.append("")

    verdict = "PASS" if (stream_pass and nonstream_pass) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"PROBE-VAL-01 expected both stream + nonstream to carry usage; "
        f"stream_pass={stream_pass} nonstream_pass={nonstream_pass}"
    )
