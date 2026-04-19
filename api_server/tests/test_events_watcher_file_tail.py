"""Phase 22b-03 Task 2 — FileTailInContainerSource integration tests.

Evidence: spike-01e-openclaw. We simulate the openclaw session-JSONL
layout inside alpine: ``/tmp/sessions.json`` as the manifest pointing
at a session id; ``/tmp/sessions/<sid>.jsonl`` as the tailed file.

Per Plan 22b-01 SUMMARY (BusyBox tail -F A3 probe FAILED with
~547ms first-emit latency vs 500ms SLA), the source class uses the
``sh -c 'while :; do cat; sleep 0.2; done'`` fallback rather than
direct ``tail -F`` against BusyBox.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from api_server.services.watcher_service import FileTailInContainerSource

pytestmark = pytest.mark.api_integration


@pytest.mark.asyncio
async def test_file_tail_yields_appended_lines(running_alpine_container):
    setup = r"""
mkdir -p /tmp/sessions
echo '{"agent:main:main":{"sessionId":"sess-abc","origin":{"from":"telegram:152099202","provider":"telegram"}}}' > /tmp/sessions.json
touch /tmp/sessions/sess-abc.jsonl
( sleep 0.4
  echo '{"type":"message","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}' >> /tmp/sessions/sess-abc.jsonl
  sleep 0.3
  echo '{"type":"message","message":{"role":"assistant","content":[{"type":"text","text":"ok-test-01"}]}}' >> /tmp/sessions/sess-abc.jsonl
  sleep 0.3
  echo '{"type":"message","message":{"role":"user","content":[{"type":"text","text":"thanks"}]}}' >> /tmp/sessions/sess-abc.jsonl
) &
sleep 30
"""
    container = running_alpine_container(["sh", "-c", setup])
    stop_event = asyncio.Event()
    source = FileTailInContainerSource(
        container_id=container.id,
        spec={
            "sessions_manifest": "/tmp/sessions.json",
            "session_log_template": "/tmp/sessions/{session_id}.jsonl",
        },
        chat_id_hint="152099202",
        stop_event=stop_event,
    )

    # The cat-and-sleep fallback emits the ENTIRE file each cycle (BusyBox
    # tail -F A3 FAILED in Plan 22b-01). Production-side, the watcher's
    # matcher dedupes via correlation_id (D-07). For this test we dedupe
    # by raw line content so we can assert the order of FIRST-SEEN entries.
    seen_lines: set[str] = set()
    unique_entries: list[dict] = []

    async def consume():
        async for line in source.lines():
            if line in seen_lines:
                continue
            seen_lines.add(line)
            try:
                unique_entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(unique_entries) >= 3:
                stop_event.set()
                return

    await asyncio.wait_for(consume(), timeout=10.0)
    roles = [e["message"]["role"] for e in unique_entries]
    assert roles == ["user", "assistant", "user"]
    assert unique_entries[1]["message"]["content"][0]["text"] == "ok-test-01"


@pytest.mark.asyncio
async def test_file_tail_returns_when_session_not_found(running_alpine_container):
    setup = r"""
echo '{"agent:main:main":{"sessionId":"sess-xyz","origin":{"from":"telegram:OTHER","provider":"telegram"}}}' > /tmp/sessions.json
mkdir -p /tmp/sessions
touch /tmp/sessions/sess-xyz.jsonl
sleep 10
"""
    container = running_alpine_container(["sh", "-c", setup])
    stop_event = asyncio.Event()
    source = FileTailInContainerSource(
        container_id=container.id,
        spec={
            "sessions_manifest": "/tmp/sessions.json",
            "session_log_template": "/tmp/sessions/{session_id}.jsonl",
        },
        # Does NOT match the manifest entry's `OTHER` chat id.
        chat_id_hint="152099202",
        stop_event=stop_event,
    )
    collected: list[str] = []
    async for line in source.lines():
        collected.append(line)
    assert collected == []
