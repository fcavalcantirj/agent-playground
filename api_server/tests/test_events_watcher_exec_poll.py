"""Phase 22b-03 Task 2 — DockerExecPollSource integration tests.

Evidence: spike-01c-nullclaw. We simulate nullclaw's `history show --json`
behavior with a tiny shell loop inside an alpine container that writes
progressively longer JSON documents to /tmp/hist.json; the source polls
``cat /tmp/hist.json`` via docker exec and yields one synthetic line per
new ``messages[]`` entry. NO MOCKS — real docker daemon, real subprocess.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from api_server.services.watcher_service import (
    DockerExecPollSource,
    DockerLogsStreamSource,
    _select_source,
)

pytestmark = pytest.mark.api_integration


@pytest.mark.asyncio
async def test_exec_poll_yields_new_messages_only(running_alpine_container):
    # Boot an alpine with a small shell loop that appends messages every 300ms.
    script = r"""
echo '{"session_id":"test","messages":[]}' > /tmp/hist.json
sleep 0.5
echo '{"session_id":"test","messages":[{"role":"user","content":"hi"}]}' > /tmp/hist.json
sleep 0.5
echo '{"session_id":"test","messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"ok-1"}]}' > /tmp/hist.json
sleep 0.5
echo '{"session_id":"test","messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"ok-1"},{"role":"user","content":"hi2"}]}' > /tmp/hist.json
sleep 10
"""
    container = running_alpine_container(["sh", "-c", script])
    stop_event = asyncio.Event()
    # argv: we fake the nullclaw CLI with `cat /tmp/hist.json` which produces the JSON doc.
    source = DockerExecPollSource(
        container_id=container.id,
        spec={
            "argv_template": ["cat", "/tmp/hist.json"],
            "session_id_template": "ignored:{chat_id}",
        },
        chat_id_hint="152099202",
        stop_event=stop_event,
        poll_interval_s=0.15,
    )
    collected: list[dict] = []

    async def consume():
        async for line in source.lines():
            collected.append(json.loads(line))
            if len(collected) >= 3:
                stop_event.set()
                return

    await asyncio.wait_for(consume(), timeout=8.0)
    assert [m["role"] for m in collected] == ["user", "assistant", "user"]
    assert collected[1]["content"] == "ok-1"


@pytest.mark.asyncio
async def test_exec_poll_degrades_when_chat_id_missing(running_alpine_container):
    container = running_alpine_container(["sh", "-c", "sleep 10"])
    stop_event = asyncio.Event()
    source = DockerExecPollSource(
        container_id=container.id,
        spec={
            "argv_template": ["nullclaw", "history", "show", "{session_id}"],
            "session_id_template": "agent:main:telegram:direct:{chat_id}",
        },
        chat_id_hint=None,
        stop_event=stop_event,
        poll_interval_s=0.1,
    )
    collected: list[str] = []
    async for line in source.lines():
        collected.append(line)
    assert collected == []


def test_select_source_docker_logs_when_no_fallback():
    recipe = {"channels": {"telegram": {}}}
    src = _select_source(recipe, "telegram", "cid123", None, asyncio.Event())
    assert isinstance(src, DockerLogsStreamSource)


def test_select_source_exec_poll_dispatch():
    recipe = {
        "channels": {
            "telegram": {
                "event_source_fallback": {
                    "kind": "docker_exec_poll",
                    "spec": {
                        "argv_template": ["a", "b"],
                        "session_id_template": "x:{chat_id}",
                    },
                }
            }
        }
    }
    src = _select_source(recipe, "telegram", "cid", "123", asyncio.Event())
    assert src.__class__.__name__ == "DockerExecPollSource"


def test_select_source_file_tail_dispatch():
    recipe = {
        "channels": {
            "telegram": {
                "event_source_fallback": {
                    "kind": "file_tail_in_container",
                    "spec": {
                        "sessions_manifest": "/a/b",
                        "session_log_template": "/c/{session_id}.jsonl",
                    },
                }
            }
        }
    }
    src = _select_source(recipe, "telegram", "cid", "123", asyncio.Event())
    assert src.__class__.__name__ == "FileTailInContainerSource"


def test_select_source_unknown_kind_raises():
    recipe = {
        "channels": {
            "telegram": {"event_source_fallback": {"kind": "mystery", "spec": {}}}
        }
    }
    with pytest.raises(ValueError, match="unknown event_source_fallback.kind"):
        _select_source(recipe, "telegram", "cid", None, asyncio.Event())
