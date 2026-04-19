---
phase: 22b
plan: 03
type: execute
wave: 1
depends_on: ["22b-01"]
files_modified:
  - api_server/src/api_server/services/watcher_service.py
  - api_server/tests/test_events_watcher_docker_logs.py
  - api_server/tests/test_events_watcher_exec_poll.py
  - api_server/tests/test_events_watcher_file_tail.py
  - api_server/tests/test_events_watcher_backpressure.py
  - api_server/tests/test_events_watcher_teardown.py
autonomous: true
requirements:
  - SC-03-GATE-B

must_haves:
  truths:
    - "watcher_service.py declares an EventSource Protocol and three concrete classes: DockerLogsStreamSource, DockerExecPollSource, FileTailInContainerSource (D-23 three source kinds)"
    - "_select_source(recipe, channel, container_id, chat_id_hint, stop_event) dispatches to the concrete class based on recipe.channels.<channel>.event_source_fallback.kind — default to DockerLogsStreamSource when no fallback declared"
    - "run_watcher producer enqueues only REGEX-MATCHED tuples into asyncio.Queue(maxsize=500); unmatched lines are discarded (D-03)"
    - "Consumer batches up to 100 matched rows OR 100ms window and calls insert_agent_events_batch from Plan 22b-02"
    - "Queue-full path drops oldest + coalesced WARN (first + once-per-100 drops) — spike-02 empirical shape"
    - "DockerLogsStreamSource iterator ends cleanly on docker rm -f within 2s; NO Task.cancel() required (spike-03)"
    - "_redact_creds is applied to any log line before it is bound into a _log.exception extra field (watcher never stores body, but error traces may contain tokens)"
    - "Payload field names forbid reply_text/body/message/content at build time — D-06 enforcement defense-in-depth behind Pydantic validation from Plan 22b-02"
  artifacts:
    - path: "api_server/src/api_server/services/watcher_service.py"
      provides: "Protocol + 3 source classes + run_watcher + _select_source + _get_poll_lock + _get_poll_signal"
      exports: ["EventSource","DockerLogsStreamSource","DockerExecPollSource","FileTailInContainerSource","run_watcher","_select_source","_get_poll_lock","_get_poll_signal","BATCH_SIZE","BATCH_WINDOW_MS"]
    - path: "api_server/tests/test_events_watcher_docker_logs.py"
      provides: "DockerLogsStreamSource integration test against live alpine container"
      contains: "DockerLogsStreamSource"
    - path: "api_server/tests/test_events_watcher_exec_poll.py"
      provides: "DockerExecPollSource integration test — JSON diff parser"
      contains: "DockerExecPollSource"
    - path: "api_server/tests/test_events_watcher_file_tail.py"
      provides: "FileTailInContainerSource integration test — sessions_manifest + tail -F"
      contains: "FileTailInContainerSource"
    - path: "api_server/tests/test_events_watcher_backpressure.py"
      provides: "Spike-02 reproducer — 20k-line flood, queue stays bounded, 0 FD leak"
      contains: "def test_watcher_backpressure"
    - path: "api_server/tests/test_events_watcher_teardown.py"
      provides: "Spike-03 reproducer — docker rm -f iterator end within 2s, 0 dangling tasks"
      contains: "def test_watcher_teardown"
  key_links:
    - from: "api_server/src/api_server/services/watcher_service.py"
      to: "api_server/src/api_server/services/event_store.py"
      via: "insert_agent_events_batch call inside consumer coroutine"
      pattern: "insert_agent_events_batch"
    - from: "api_server/src/api_server/services/watcher_service.py"
      to: "api_server/src/api_server/models/events.py"
      via: "KIND_TO_PAYLOAD validation before enqueue (D-08 defense-in-depth)"
      pattern: "KIND_TO_PAYLOAD"
    - from: "api_server/src/api_server/services/watcher_service.py::run_watcher"
      to: "app.state.event_poll_signals"
      via: "signal.set() after successful batch commit wakes long-poll handler"
      pattern: "event_poll_signals"
---

<objective>
Build the multi-source log-watcher service — the observation tier that converts container stdout / CLI-poll output / session-JSONL tail into typed `agent_events` rows.

**D-23 is the load-bearing architectural decision of this plan.** CONTEXT.md D-01 described docker-logs-scrape as THE ingest path; spikes 01c (nullclaw) and 01e (openclaw) empirically proved that 40% of the catalog needs an alternative source. This plan implements the `EventSource` Protocol abstraction with three concrete implementations and a dispatch function that selects the right one based on `recipe.channels.<channel>.event_source_fallback.kind` — with `docker_logs_stream` as the fall-through default.

Three source kinds per RESEARCH §Pattern 1 + §D-23:

| Kind | Recipes | Teardown semantics |
|------|---------|--------------------|
| `docker_logs_stream` (default) | hermes, picoclaw, nanobot | `docker.APIClient().logs(stream=True, follow=True)` bridged via `asyncio.to_thread(next, it, None)`. Iterator ends cleanly on `docker rm -f` in <270ms (spike-03); NO `Task.cancel()` required. |
| `docker_exec_poll` | nullclaw | Periodic `docker exec <cid> nullclaw history show <session_id> --json` at 500ms cadence; diff against prev snapshot; yield synthetic JSON lines for new messages. Loop exits on `stop_event.is_set()`. |
| `file_tail_in_container` | openclaw | `docker exec <cid> tail -n0 -F <session_log>` subprocess; stream stdout via `Popen.stdout.readline` wrapped in `asyncio.to_thread`. Session-id resolved at attach time from `sessions_manifest` (Pitfall 2 — re-resolve on tail exit). BusyBox `tail -F` line-buffering probed in Plan 22b-01. |

`run_watcher` is the single spawn entrypoint: it instantiates the right source, compiles recipe regexes, runs a producer coroutine (source.lines → matcher → queue) and a consumer coroutine (batcher → event_store). After each successful batch commit, `app.state.event_poll_signals[agent_id].set()` wakes any pending long-poll handler (Plan 22b-05). On `stop_event.set()`, the consumer drains its queue and the producer's source ends naturally.

**Parallelizable with Plan 22b-02** (no shared files — 22b-02 owns `services/event_store.py` + `models/events.py`; this plan owns `services/watcher_service.py`). 22b-02's exports (`insert_agent_events_batch`, `KIND_TO_PAYLOAD`, `VALID_KINDS`) are consumed by this plan; the merge order forces 22b-02's commits to land first, but the PLAN files may run in parallel execution waves.

This plan is intentionally monolithic — splitting it introduces cross-wave dependency on the `EventSource` Protocol that Task 3 consumes, and all three tasks share `watcher_service.py`; a split into (e.g.) 22b-03a + 22b-03b would require circular-import discipline and forbid parallel file writes. The extra size is accepted in exchange for a single atomic merge of the watcher substrate.

Purpose: SC-03 Gate B — for every running agent_container, produce a `reply_sent` row in `agent_events` within 10s of the bot's outbound Telegram delivery, correlatable by an embedded UUID.

Output: One service module, five integration test files seeded from spike-02/spike-03/spike-01a/spike-01c/spike-01e reproducers, all passing against real Docker daemon via the `docker_client` + `running_alpine_container` fixtures from Plan 22b-01.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-RESEARCH.md
@.planning/phases/22b-agent-event-stream/22b-PATTERNS.md
@.planning/phases/22b-agent-event-stream/22b-VALIDATION.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-02-docker-sdk-backpressure.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-03-watcher-teardown.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01a-hermes.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01b-picoclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01c-nullclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01d-nanobot.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md
@.planning/phases/22b-agent-event-stream/22b-01-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-02-SUMMARY.md
@api_server/src/api_server/services/runner_bridge.py
@api_server/src/api_server/routes/agent_lifecycle.py
@recipes/nullclaw.yaml
@recipes/openclaw.yaml

<interfaces>
<!-- Contracts this plan creates AND consumes. -->

From api_server/src/api_server/services/event_store.py (Plan 22b-02 — consumer of):
```python
async def insert_agent_events_batch(conn, agent_container_id: UUID,
                                     rows: list[tuple[str, dict, str | None]]) -> list[int]
```

From api_server/src/api_server/models/events.py (Plan 22b-02 — consumer of):
```python
VALID_KINDS: set[str] = {"reply_sent","reply_failed","agent_ready","agent_error"}
KIND_TO_PAYLOAD: dict[str, type[BaseModel]]      # kind → Pydantic class
```

From api_server/src/api_server/services/runner_bridge.py (existing — ANALOG):
```python
# _get_tag_lock pattern (lines 82-94) — we mirror for _get_poll_lock
async def _get_tag_lock(app_state, image_tag: str) -> asyncio.Lock: ...
# asyncio.to_thread bridge (lines 117-131) — we mirror in all 3 source classes
result = await asyncio.to_thread(run_cell, ...)
```

From api_server/src/api_server/routes/agent_lifecycle.py (existing — ANALOG for redaction):
```python
def _redact_creds(text: str, channel_inputs: dict[str, str]) -> str:  # lines 109-131
```

From api_server/tests/conftest.py (Plan 22b-01 — shared fixtures):
```python
@pytest.fixture(scope="session") def docker_client()                  # docker-py from-env
@pytest.fixture def running_alpine_container(docker_client)           # factory, auto-remove
@pytest.fixture(scope="session") def event_log_samples_dir() -> Path  # path to spike captures
```

New exports FROM this plan (consumed by Plan 22b-04 lifecycle integration):
```python
# watcher_service.py
class EventSource(Protocol):
    async def lines(self) -> AsyncIterator[str]: ...

class DockerLogsStreamSource: ...
class DockerExecPollSource:   ...
class FileTailInContainerSource: ...

async def run_watcher(app_state, *, container_row_id: UUID, container_id: str,
                      agent_id: UUID, recipe: dict, channel: str,
                      chat_id_hint: str | None) -> None
def _select_source(recipe, channel, container_id, chat_id_hint, stop_event) -> EventSource
async def _get_poll_lock(app_state, agent_id: UUID) -> asyncio.Lock
def _get_poll_signal(app_state, agent_id: UUID) -> asyncio.Event
BATCH_SIZE = 100
BATCH_WINDOW_MS = 100
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: EventSource Protocol + DockerLogsStreamSource + helper primitives</name>
  <files>api_server/src/api_server/services/watcher_service.py, api_server/tests/test_events_watcher_docker_logs.py</files>
  <read_first>
    - api_server/src/api_server/services/runner_bridge.py (ANALOG — module docstring lines 1-28, `_get_tag_lock` lines 82-94, `asyncio.to_thread` bridge lines 117-131)
    - api_server/src/api_server/services/__init__.py (confirm empty — each module is import-on-demand; no package-level re-exports)
    - 22b-PATTERNS.md §"api_server/src/api_server/services/watcher_service.py" (authoritative module docstring + logger naming + `_select_source` verbatim)
    - 22b-RESEARCH.md §"Pattern 1: Multi-source watcher via Protocol (D-23)" (authoritative class shapes)
    - 22b-SPIKES/spike-02-docker-sdk-backpressure.md (the docker.APIClient().logs(stream=True, follow=True) + asyncio.to_thread(next, it, None) pattern — PASS verdict + planner note 3 about the `None` sentinel)
    - 22b-SPIKES/spike-03-watcher-teardown.md (iterator ends cleanly on docker rm -f — NO Task.cancel needed; planner note 1)
    - 22b-CONTEXT.md D-02, D-10, D-12, D-23
  </read_first>
  <behavior>
    - `from api_server.services.watcher_service import EventSource, DockerLogsStreamSource, _get_poll_lock, _get_poll_signal, BATCH_SIZE, BATCH_WINDOW_MS` succeeds.
    - `DockerLogsStreamSource(container_id, stop_event).lines()` yields raw str lines (decoded utf-8 with errors='replace'); returns when iterator ends OR `stop_event.is_set()`.
    - Against a real alpine container running `for i in $(seq 1 100); do echo line-$i; done; sleep 30`, the source yields 100 lines in order within 2s.
    - When the test calls `container.remove(force=True)`, the source's `async for` loop terminates within 2s (spike-03 timing) without raising.
    - `_get_poll_lock(app_state, agent_id)` returns a stable `asyncio.Lock` keyed on agent_id — two calls in the same process return the SAME lock object (identity check).
    - `_get_poll_signal(app_state, agent_id)` returns a stable `asyncio.Event` keyed on agent_id.
  </behavior>
  <action>
**Part A — Create `api_server/src/api_server/services/watcher_service.py`** with the module docstring + imports + constants + `_get_poll_lock` + `_get_poll_signal` + `EventSource` Protocol + `DockerLogsStreamSource`. Copy the module docstring shape VERBATIM from 22b-PATTERNS.md §"api_server/src/api_server/services/watcher_service.py" (lines 250-278 of PATTERNS):

```python
"""Per-container log-watcher service — async bridge + source dispatch (Phase 22b-03).

Mirrors runner_bridge's Pattern 2 in reverse: instead of one-shot
``to_thread(run_cell)``, watchers are long-lived pump coroutines that
bridge a blocking iterator (docker-py logs, subprocess.Popen stdout,
or docker exec polls) into asyncio via ``asyncio.to_thread``.

Key primitives:
- ``app.state.log_watchers: dict[container_row_id, (Task, Event)]``
- ``app.state.event_poll_signals: dict[agent_id, asyncio.Event]`` — one per agent
- ``app.state.event_poll_locks: dict[agent_id, asyncio.Lock]`` — D-13 429 cap
- ``asyncio.Queue(maxsize=500)`` per watcher (NOT in app.state — watcher-local)

BYOK invariant: chat_id_hint is the ONLY channel-derived value the watcher
receives; it is a numeric user ID, not a secret. Bearer tokens never reach
the watcher. Any exception message that might contain creds passes through
_redact_creds before hitting a log handler (defense-in-depth — the watcher
does not have access to the Bearer; it only sees the chat_id_hint).
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator, Protocol
from uuid import UUID

import docker

_log = logging.getLogger("api_server.watcher")

# Tunables (D-12 + spike-02 verdict — 500 is a safety belt, not a routine-case bound).
BATCH_SIZE = 100
BATCH_WINDOW_MS = 100
QUEUE_MAXSIZE = 500


async def _get_poll_lock(app_state, agent_id: UUID) -> asyncio.Lock:
    """Return (creating if needed) the per-agent long-poll ``asyncio.Lock`` (D-13).

    Pitfall 1 safe — mirrors ``runner_bridge._get_tag_lock``. Mutations to
    the shared ``event_poll_locks`` dict happen under ``app_state.locks_mutex``
    so concurrent setdefault-races cannot leave two coroutines holding
    different Lock objects for the same agent_id.
    """
    async with app_state.locks_mutex:
        lock = app_state.event_poll_locks.get(agent_id)
        if lock is None:
            lock = asyncio.Lock()
            app_state.event_poll_locks[agent_id] = lock
    return lock


def _get_poll_signal(app_state, agent_id: UUID) -> asyncio.Event:
    """Return (creating if needed) the per-agent watcher→handler wake signal."""
    signal = app_state.event_poll_signals.get(agent_id)
    if signal is None:
        signal = asyncio.Event()
        app_state.event_poll_signals[agent_id] = signal
    return signal


class EventSource(Protocol):
    """Abstract source of raw event lines for one container.

    Every concrete source yields raw lines (bytes→str decoded) that the
    watcher's matcher runs through the recipe's event_log_regex dict. The
    source owns its own teardown (iterator-end OR poll-loop-break). The
    watcher never ``Task.cancel()``s the source; instead it signals via
    ``stop_event`` and awaits natural end (spike-03 PASS — iterator ends
    cleanly on docker rm -f in <270ms).
    """
    async def lines(self) -> AsyncIterator[str]:  # pragma: no cover (Protocol)
        ...


class DockerLogsStreamSource:
    """Source kind: ``docker_logs_stream`` (default — hermes, picoclaw, nanobot).

    Uses ``docker.APIClient().logs(stream=True, follow=True)`` bridged via
    ``asyncio.to_thread(next, it, None)``. The ``None`` sentinel (spike-02
    planner note 3) is non-obvious but critical — it returns ``None`` at
    StopIteration rather than raising across the thread boundary.

    Teardown: iterator ends cleanly on ``docker rm -f`` in <270ms (spike-03).
    No ``Task.cancel()`` required. ``tail=0`` so we do NOT re-read the
    historical buffer on attach (events emitted before attach are lost
    per D-11 — the correlation_id contract prevents false-PASS).
    """

    def __init__(self, container_id: str, stop_event: asyncio.Event):
        self.container_id = container_id
        self.stop_event = stop_event

    async def lines(self) -> AsyncIterator[str]:
        client = docker.APIClient()
        try:
            it = client.logs(
                container=self.container_id,
                stream=True,
                follow=True,
                stdout=True,
                stderr=True,
                tail=0,
            )
            while not self.stop_event.is_set():
                chunk = await asyncio.to_thread(next, it, None)
                if chunk is None:
                    return  # iterator ended (container reaped — spike-03 PASS)
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                for line in text.splitlines():
                    if line:
                        yield line
        finally:
            try:
                client.close()
            except Exception:
                pass
```

**Part B — Create `api_server/tests/test_events_watcher_docker_logs.py`** that exercises `DockerLogsStreamSource` against a real alpine container via the `running_alpine_container` fixture from Plan 22b-01. Test:

1. `test_docker_logs_source_yields_echoed_lines` — alpine runs `sh -c 'for i in $(seq 1 20); do echo line-$i; sleep 0.02; done; sleep 10'`, collect first 20 lines from the source, assert `["line-1", "line-2", ..., "line-20"] == collected`.

2. `test_docker_logs_source_terminates_on_remove_force` — alpine runs `sh -c 'echo hi; sleep 30'`, start consuming, call `container.remove(force=True)` from outside, assert source's generator completes within 2s (spike-03 budget).

3. `test_docker_logs_source_honours_stop_event` — alpine runs `sh -c 'while true; do echo x; sleep 0.1; done'`, start consuming, `stop_event.set()` from outside, assert generator exits within 1s.

4. `test_docker_logs_source_decodes_non_utf8_safely` — alpine runs `sh -c 'printf "valid\n"; printf "\xff\xfe\n"; printf "after\n"; sleep 10'`, assert the source yields 3 lines without raising (decode errors='replace' contract).

Test skeleton (stdlib + pytest-asyncio):

```python
"""Phase 22b-03 Task 1 — DockerLogsStreamSource integration tests.

Every test uses the Plan 22b-01 `running_alpine_container` fixture to
spawn a real alpine container; NO MOCKS (Golden Rule 1). Wall time budgets
come from spike-03 (iterator-end <2s) and spike-02 (queue stays bounded).
"""
import asyncio
import pytest
from api_server.services.watcher_service import DockerLogsStreamSource

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_docker_logs_source_yields_echoed_lines(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(
        ["sh", "-c", "for i in $(seq 1 20); do echo line-$i; sleep 0.02; done; sleep 10"])
    source = DockerLogsStreamSource(container.id, stop_event)

    collected: list[str] = []
    async def _consume():
        async for line in source.lines():
            collected.append(line)
            if len(collected) >= 20:
                stop_event.set()
                return

    await asyncio.wait_for(_consume(), timeout=5.0)
    assert collected == [f"line-{i}" for i in range(1, 21)]


@pytest.mark.asyncio
async def test_docker_logs_source_terminates_on_remove_force(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
    source = DockerLogsStreamSource(container.id, stop_event)
    task = asyncio.create_task(_drain(source))
    await asyncio.sleep(0.5)   # let attach happen
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=3.0)   # spike-03 budget


async def _drain(source):
    async for _ in source.lines():
        pass


@pytest.mark.asyncio
async def test_docker_logs_source_honours_stop_event(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo x; sleep 0.1; done"])
    source = DockerLogsStreamSource(container.id, stop_event)
    task = asyncio.create_task(_drain(source))
    await asyncio.sleep(0.3)
    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_docker_logs_source_decodes_non_utf8_safely(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(
        ["sh", "-c", "printf 'valid\\n'; printf '\\xff\\xfe\\n'; printf 'after\\n'; sleep 10"])
    source = DockerLogsStreamSource(container.id, stop_event)
    collected: list[str] = []
    async def _consume():
        async for line in source.lines():
            collected.append(line)
            if len(collected) >= 3:
                stop_event.set()
                return
    await asyncio.wait_for(_consume(), timeout=5.0)
    assert len(collected) == 3
    assert "valid" in collected[0]
    assert "after" in collected[2]
```

**Note on `Task.cancel` discipline (spike-03):** `Task.cancel` is forbidden on the docker source iterator (iterator ends naturally on `docker rm -f` in <270ms per spike-03). A single `consumer_task.cancel()` fallback in the `run_watcher` `finally` block is permitted and is introduced in Task 3 — it does NOT cancel the docker source; it only cancels the local consumer coroutine if the 2s drain budget is exceeded. That is why Task 1's acceptance criterion allows `grep -c Task.cancel` to return `<= 1`.

**Verify:**
```bash
cd api_server && pytest -x tests/test_events_watcher_docker_logs.py -v 2>&1 | tail -20
```
All 4 tests green.
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.services.watcher_service import EventSource, DockerLogsStreamSource, _get_poll_lock, _get_poll_signal, BATCH_SIZE, BATCH_WINDOW_MS; assert BATCH_SIZE == 100 and BATCH_WINDOW_MS == 100" && pytest -x tests/test_events_watcher_docker_logs.py -v 2>&1 | grep -qE "4 passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class DockerLogsStreamSource" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "class EventSource(Protocol)" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "asyncio.to_thread(next, it, None)" api_server/src/api_server/services/watcher_service.py` returns `>=1` (spike-02 sentinel pattern)
    - `grep -c "tail=0" api_server/src/api_server/services/watcher_service.py` returns `>=1` (D-11: no re-read of historical buffer)
    - `grep -cE "def _get_poll_lock\b|def _get_poll_signal\b" api_server/src/api_server/services/watcher_service.py` returns exactly `2`
    - `grep -c "Task.cancel" api_server/src/api_server/services/watcher_service.py` returns `<= 1` (the single allowed match is the `consumer_task.cancel()` timeout fallback in `run_watcher`'s `finally` block, introduced in Task 3; the docker source iterator is NOT cancelled per spike-03)
    - `cd api_server && pytest -x tests/test_events_watcher_docker_logs.py -v 2>&1 | grep -cE "PASSED"` returns `>=4`
  </acceptance_criteria>
  <done>watcher_service.py module skeleton exists with EventSource Protocol + DockerLogsStreamSource + app-state helpers; 4 integration tests against live alpine green; no `Task.cancel` on the docker source iterator (spike-03 discipline — the single `consumer_task.cancel()` fallback is introduced in Task 3).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: DockerExecPollSource + FileTailInContainerSource + _select_source dispatch</name>
  <files>api_server/src/api_server/services/watcher_service.py, api_server/tests/test_events_watcher_exec_poll.py, api_server/tests/test_events_watcher_file_tail.py</files>
  <read_first>
    - api_server/src/api_server/services/watcher_service.py (the file being extended — read current shape from Task 1 to understand where to append)
    - 22b-RESEARCH.md §"Pattern 1: Multi-source watcher via Protocol (D-23)" — authoritative DockerExecPollSource + FileTailInContainerSource skeletons
    - 22b-RESEARCH.md §"D-23: Multi-Source Watcher Architecture" + "Dispatch (in watcher_service._select_source)" — VERBATIM dispatch function
    - 22b-SPIKES/spike-01c-nullclaw.md — DockerExecPollSource spec: `argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]`, `session_id_template: "agent:main:telegram:direct:{chat_id}"`, polling 500ms, JSON diff returns new `messages[]` entries
    - 22b-SPIKES/spike-01e-openclaw.md — FileTailInContainerSource spec: `sessions_manifest: /home/node/.openclaw/agents/main/sessions/sessions.json`, `session_log_template: "/home/node/.openclaw/agents/main/sessions/{session_id}.jsonl"`. Resolve session by `sessions.json` manifest → find origin.from matching `telegram:<chat_id>` → get sessionId → tail the JSONL
    - 22b-PATTERNS.md §"services/watcher_service.py" — `_select_source` dispatch verbatim (lines 339-350)
    - 22b-01-SUMMARY.md — whether BusyBox tail -F probe PASSED (determines if FileTailInContainerSource uses `tail -F` OR the `sh -c "while :; do cat; sleep 0.2; done"` fallback)
  </read_first>
  <behavior>
    - `DockerExecPollSource(container_id, argv_template=[...], session_id_template="...", chat_id_hint="123", poll_interval_s=0.2, stop_event)` yields one synthetic JSON line per new entry in `messages[]` from successive `docker exec` polls. When no chat_id_hint provided, the source uses a glob strategy over sessions_manifest (lifespan re-attach case — A6 degrade-gracefully).
    - `FileTailInContainerSource(container_id, sessions_manifest="/path/sessions.json", session_log_template="/path/{session_id}.jsonl", chat_id_hint="152099202", stop_event)` at start-up (a) execs `cat sessions.json` via `docker exec`, (b) parses JSON, (c) picks session whose `origin.from` matches `telegram:<chat_id_hint>`, (d) spawns `docker exec <cid> tail -n0 -F <resolved_path>` via `subprocess.Popen`, (e) yields each `readline()` output wrapped in `asyncio.to_thread`. On tail exit or stop_event, kills subprocess and returns.
    - `_select_source(recipe, channel, container_id, chat_id_hint, stop_event)` returns: `DockerLogsStreamSource` when `event_source_fallback` is absent (hermes/picoclaw/nanobot); `DockerExecPollSource` when kind=="docker_exec_poll" (nullclaw); `FileTailInContainerSource` when kind=="file_tail_in_container" (openclaw); raises `ValueError("unknown event_source_fallback.kind: ...")` otherwise.
  </behavior>
  <action>
**Part A — APPEND to `api_server/src/api_server/services/watcher_service.py`** (below the DockerLogsStreamSource class from Task 1):

```python
class DockerExecPollSource:
    """Source kind: ``docker_exec_poll`` (nullclaw).

    Evidence: spike-01c-nullclaw.md. Nullclaw's stdout is barren (9 lines
    total across a full session including boot). The authoritative activity
    log is ``nullclaw history show <session_id> --json`` which prints the
    entire conversation as a JSON document. This source polls that CLI at
    ``poll_interval_s`` cadence, diffs successive ``messages[]`` arrays,
    and yields one synthetic JSON line per NEW entry.

    Spec (from recipes/nullclaw.yaml event_source_fallback.spec):
        argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]
        session_id_template: "agent:main:telegram:direct:{chat_id}"

    Degrade-gracefully (A6 in RESEARCH §Open Questions): when chat_id_hint
    is ``None`` (lifespan re-attach path), we cannot compute session_id;
    the source emits a single _log.warning and returns immediately. The
    harness's Gate B can be re-run after a real DM triggers session
    creation on the next /start.
    """

    def __init__(
        self,
        container_id: str,
        spec: dict,
        chat_id_hint: str | None,
        stop_event: asyncio.Event,
        poll_interval_s: float = 0.5,
    ):
        self.container_id = container_id
        self.argv_template: list[str] = list(spec.get("argv_template") or [])
        self.session_id_template: str = spec.get("session_id_template") or ""
        self.chat_id_hint = chat_id_hint
        self.stop_event = stop_event
        self.poll_interval_s = poll_interval_s

    def _resolve_session_id(self) -> str | None:
        if not self.chat_id_hint or not self.session_id_template:
            return None
        return self.session_id_template.format(chat_id=self.chat_id_hint)

    async def lines(self) -> AsyncIterator[str]:
        session_id = self._resolve_session_id()
        if session_id is None:
            _log.warning(
                "docker_exec_poll source cannot resolve session_id "
                "(chat_id_hint=None) — Gate B deferred until next /start",
                extra={"container_id": self.container_id[:12]},
            )
            return

        argv = [a.format(session_id=session_id) for a in self.argv_template]
        prev_messages: list[dict] = []
        while not self.stop_event.is_set():
            try:
                out = await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "exec", self.container_id, *argv],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                _log.warning("docker exec poll timed out",
                             extra={"container_id": self.container_id[:12]})
                await asyncio.sleep(self.poll_interval_s)
                continue
            if out.returncode != 0:
                # Container likely gone; let caller's stop_event loop end us.
                _log.debug("docker exec poll returncode=%s stderr=%s",
                           out.returncode, out.stderr[:200])
                await asyncio.sleep(self.poll_interval_s)
                continue
            try:
                doc = json.loads(out.stdout)
            except json.JSONDecodeError:
                _log.warning("docker exec poll produced non-JSON output",
                             extra={"container_id": self.container_id[:12]})
                await asyncio.sleep(self.poll_interval_s)
                continue
            current = doc.get("messages") or []
            # Emit only the tail-extension (Pitfall 3 — lagging is fine; the
            # synthetic line carries role + content so the watcher matcher
            # does role-based extraction rather than regex).
            for msg in current[len(prev_messages):]:
                yield json.dumps(msg)
            prev_messages = current
            await asyncio.sleep(self.poll_interval_s)


class FileTailInContainerSource:
    """Source kind: ``file_tail_in_container`` (openclaw).

    Evidence: spike-01e-openclaw.md. Openclaw's docker logs are barren;
    the only authoritative record of per-message activity is the session
    JSONL at ``/home/node/.openclaw/agents/main/sessions/<session_id>.jsonl``.
    One JSON document per line; assistant replies carry the body in
    ``message.content[].text`` (type=='text' entry).

    Flow:
      1. ``docker exec <cid> cat <sessions_manifest>`` → parse JSON.
      2. Pick session whose ``origin.from`` matches ``telegram:<chat_id_hint>``.
      3. Resolve tail path from ``session_log_template.format(session_id=...)``.
      4. Spawn ``docker exec <cid> tail -n0 -F <path>`` via subprocess.Popen.
      5. Bridge ``proc.stdout.readline`` through ``asyncio.to_thread``.
      6. On stop_event OR tail subprocess exit, terminate cleanly.

    Pitfall 2 (session-id drift) — if the user creates a new chat with
    openclaw, a new session JSONL is spawned; this source is scoped to
    the session resolved at attach time. A second chat on the same
    container needs a second FileTailInContainerSource (post-MVP, not
    in 22b scope). The session resolution step emits a _log.warning
    when no match is found so ops can see the reason Gate B failed.

    BusyBox tail -F line-buffering: Plan 22b-01 probed assumption A3.
    If the probe PASSED (definitive), the default ``tail -F`` path is
    used. If the probe FAILED, plan 22b-01's SUMMARY must record this
    and this source MUST fall back to
    ``sh -c 'while :; do cat "$1"; sleep 0.2; done' -- <path>``.
    Executor: read Plan 22b-01 SUMMARY first; set _USE_TAIL_FALLBACK
    to True only if SUMMARY reports A3 FAILED.
    """

    _USE_TAIL_FALLBACK = False   # Plan 22b-01 SUMMARY verdict reader sets this

    def __init__(
        self,
        container_id: str,
        spec: dict,
        chat_id_hint: str | None,
        stop_event: asyncio.Event,
    ):
        self.container_id = container_id
        self.sessions_manifest: str = spec.get("sessions_manifest") or ""
        self.session_log_template: str = spec.get("session_log_template") or ""
        self.chat_id_hint = chat_id_hint
        self.stop_event = stop_event

    async def _resolve_session_path(self) -> str | None:
        if not self.sessions_manifest or not self.session_log_template:
            return None
        try:
            out = await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", self.container_id, "cat", self.sessions_manifest],
                capture_output=True, text=True, timeout=3.0, check=False,
            )
        except subprocess.TimeoutExpired:
            return None
        if out.returncode != 0:
            return None
        try:
            manifest = json.loads(out.stdout)
        except json.JSONDecodeError:
            return None
        # Manifest shape (spike-01e): {"agent:main:main": {"sessionId":"...","origin":{"from":"telegram:152099202",...}}}
        needle = f"telegram:{self.chat_id_hint}" if self.chat_id_hint else None
        for _key, entry in manifest.items():
            if not isinstance(entry, dict):
                continue
            origin = entry.get("origin") or {}
            if needle is None or origin.get("from") == needle:
                session_id = entry.get("sessionId")
                if session_id:
                    return self.session_log_template.format(session_id=session_id)
        _log.warning(
            "file_tail_in_container: no session matching chat_id_hint=%s "
            "found in manifest (file has %d entries)",
            self.chat_id_hint, len(manifest),
            extra={"container_id": self.container_id[:12]},
        )
        return None

    async def lines(self) -> AsyncIterator[str]:
        path = await self._resolve_session_path()
        if path is None:
            return
        if self._USE_TAIL_FALLBACK:
            argv = ["docker", "exec", self.container_id, "sh", "-c",
                    f"while :; do cat '{path}'; sleep 0.2; done"]
        else:
            argv = ["docker", "exec", self.container_id, "tail", "-n0", "-F", path]
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        try:
            while not self.stop_event.is_set():
                line = await asyncio.to_thread(proc.stdout.readline)
                if line == "":
                    return   # tail subprocess exited (file gone / container reaped)
                yield line.rstrip("\n")
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass


def _select_source(
    recipe: dict,
    channel: str,
    container_id: str,
    chat_id_hint: str | None,
    stop_event: asyncio.Event,
) -> EventSource:
    """Dispatch per D-23. Default (no event_source_fallback) = DockerLogsStreamSource.

    Verbatim shape from RESEARCH §D-23 Dispatch.
    """
    channel_spec = (recipe.get("channels") or {}).get(channel, {}) or {}
    fallback = channel_spec.get("event_source_fallback")
    if fallback is None:
        return DockerLogsStreamSource(container_id, stop_event)
    kind = fallback.get("kind")
    spec = fallback.get("spec", {}) or {}
    if kind == "docker_exec_poll":
        return DockerExecPollSource(container_id, spec, chat_id_hint, stop_event)
    if kind == "file_tail_in_container":
        return FileTailInContainerSource(container_id, spec, chat_id_hint, stop_event)
    raise ValueError(f"unknown event_source_fallback.kind: {kind!r}")
```

**Part B — Create `api_server/tests/test_events_watcher_exec_poll.py`:**

```python
"""Phase 22b-03 Task 2 — DockerExecPollSource integration tests.

Evidence: spike-01c-nullclaw. We simulate nullclaw's `history show --json`
behavior with a tiny alpine shim script that writes progressively longer
JSON documents to /tmp/hist.json; the source polls `cat /tmp/hist.json`
via docker exec and yields one synthetic line per new messages[] entry.
No MOCKS — real docker daemon, real subprocess.
"""
import asyncio
import json
import pytest
from api_server.services.watcher_service import DockerExecPollSource, _select_source

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_exec_poll_yields_new_messages_only(running_alpine_container):
    # Boot an alpine with a small shell loop that appends messages every 300ms
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
    # argv: we fake the nullclaw CLI with `cat /tmp/hist.json` which produces the JSON doc
    source = DockerExecPollSource(
        container_id=container.id,
        spec={"argv_template": ["cat", "/tmp/hist.json"],
              "session_id_template": "ignored:{chat_id}"},
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
    await asyncio.wait_for(consume(), timeout=6.0)
    assert [m["role"] for m in collected] == ["user", "assistant", "user"]
    assert collected[1]["content"] == "ok-1"


@pytest.mark.asyncio
async def test_exec_poll_degrades_when_chat_id_missing(running_alpine_container):
    container = running_alpine_container(["sh", "-c", "sleep 10"])
    stop_event = asyncio.Event()
    source = DockerExecPollSource(
        container_id=container.id,
        spec={"argv_template": ["nullclaw", "history", "show", "{session_id}"],
              "session_id_template": "agent:main:telegram:direct:{chat_id}"},
        chat_id_hint=None,
        stop_event=stop_event,
        poll_interval_s=0.1,
    )
    collected: list[str] = []
    async for line in source.lines():
        collected.append(line)
    assert collected == []


def test_select_source_docker_logs_when_no_fallback():
    import asyncio
    recipe = {"channels": {"telegram": {}}}
    src = _select_source(recipe, "telegram", "cid123", None, asyncio.Event())
    from api_server.services.watcher_service import DockerLogsStreamSource
    assert isinstance(src, DockerLogsStreamSource)


def test_select_source_exec_poll_dispatch():
    import asyncio
    recipe = {"channels": {"telegram": {"event_source_fallback": {
        "kind": "docker_exec_poll",
        "spec": {"argv_template": ["a","b"], "session_id_template": "x:{chat_id}"}}}}}
    src = _select_source(recipe, "telegram", "cid", "123", asyncio.Event())
    assert src.__class__.__name__ == "DockerExecPollSource"


def test_select_source_file_tail_dispatch():
    import asyncio
    recipe = {"channels": {"telegram": {"event_source_fallback": {
        "kind": "file_tail_in_container",
        "spec": {"sessions_manifest": "/a/b", "session_log_template": "/c/{session_id}.jsonl"}}}}}
    src = _select_source(recipe, "telegram", "cid", "123", asyncio.Event())
    assert src.__class__.__name__ == "FileTailInContainerSource"


def test_select_source_unknown_kind_raises():
    import asyncio
    recipe = {"channels": {"telegram": {"event_source_fallback": {"kind": "mystery", "spec": {}}}}}
    with pytest.raises(ValueError, match="unknown event_source_fallback.kind"):
        _select_source(recipe, "telegram", "cid", None, asyncio.Event())
```

**Part C — Create `api_server/tests/test_events_watcher_file_tail.py`:**

```python
"""Phase 22b-03 Task 2 — FileTailInContainerSource integration tests.

Evidence: spike-01e-openclaw. We simulate the openclaw session-JSONL
layout inside alpine: /tmp/sessions.json as the manifest pointing at
a session id; /tmp/sessions/<sid>.jsonl as the tailed file.
"""
import asyncio
import json
import pytest
from api_server.services.watcher_service import FileTailInContainerSource

pytestmark = pytest.mark.integration


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
        spec={"sessions_manifest": "/tmp/sessions.json",
              "session_log_template": "/tmp/sessions/{session_id}.jsonl"},
        chat_id_hint="152099202",
        stop_event=stop_event,
    )
    collected: list[dict] = []
    async def consume():
        async for line in source.lines():
            collected.append(json.loads(line))
            if len(collected) >= 3:
                stop_event.set()
                return
    await asyncio.wait_for(consume(), timeout=8.0)
    roles = [e["message"]["role"] for e in collected]
    assert roles == ["user", "assistant", "user"]
    assert collected[1]["message"]["content"][0]["text"] == "ok-test-01"


@pytest.mark.asyncio
async def test_file_tail_returns_when_session_not_found(running_alpine_container):
    setup = r"""
echo '{"agent:main:main":{"sessionId":"sess-xyz","origin":{"from":"telegram:OTHER","provider":"telegram"}}}' > /tmp/sessions.json
mkdir -p /tmp/sessions; touch /tmp/sessions/sess-xyz.jsonl
sleep 10
"""
    container = running_alpine_container(["sh", "-c", setup])
    stop_event = asyncio.Event()
    source = FileTailInContainerSource(
        container_id=container.id,
        spec={"sessions_manifest": "/tmp/sessions.json",
              "session_log_template": "/tmp/sessions/{session_id}.jsonl"},
        chat_id_hint="152099202",   # does NOT match `OTHER` in the manifest
        stop_event=stop_event,
    )
    collected: list[str] = []
    async for line in source.lines():
        collected.append(line)
    assert collected == []
```

**Verify:**
```bash
cd api_server && pytest -x tests/test_events_watcher_exec_poll.py tests/test_events_watcher_file_tail.py -v 2>&1 | tail -25
```
All tests green (5 from exec_poll + 2 from file_tail).
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.services.watcher_service import DockerExecPollSource, FileTailInContainerSource, _select_source" && pytest -x tests/test_events_watcher_exec_poll.py tests/test_events_watcher_file_tail.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 7 { exit 0 } { exit 1 }'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class DockerExecPollSource" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "class FileTailInContainerSource" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "def _select_source" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "docker_exec_poll" api_server/src/api_server/services/watcher_service.py` returns `>=1`
    - `grep -c "file_tail_in_container" api_server/src/api_server/services/watcher_service.py` returns `>=1`
    - `grep -c "tail\", \"-n0\", \"-F\"" api_server/src/api_server/services/watcher_service.py` returns `>=1` (OR the BusyBox fallback is present if Plan 22b-01 SUMMARY reports A3 FAILED)
    - `cd api_server && pytest -x tests/test_events_watcher_exec_poll.py tests/test_events_watcher_file_tail.py -v 2>&1 | grep -cE "PASSED"` returns `>=7` (5 exec_poll + 2 file_tail)
    - `python3 -c "from api_server.services.watcher_service import _select_source; import asyncio; _select_source({'channels':{'telegram':{'event_source_fallback':{'kind':'mystery','spec':{}}}}}, 'telegram', 'c', None, asyncio.Event())"` exits with nonzero (ValueError)
  </acceptance_criteria>
  <done>Three source classes landed; _select_source dispatches per D-23 with default/poll/file-tail branches + explicit ValueError on unknown kind; 7+ integration tests against live alpine green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: run_watcher producer/consumer + backpressure + teardown tests</name>
  <files>api_server/src/api_server/services/watcher_service.py, api_server/tests/test_events_watcher_backpressure.py, api_server/tests/test_events_watcher_teardown.py</files>
  <read_first>
    - api_server/src/api_server/services/watcher_service.py (the file being extended — read current shape from Tasks 1+2)
    - api_server/src/api_server/services/event_store.py (Plan 22b-02 output — signature of insert_agent_events_batch)
    - api_server/src/api_server/models/events.py (Plan 22b-02 output — VALID_KINDS, KIND_TO_PAYLOAD for defense-in-depth validation)
    - api_server/src/api_server/routes/agent_lifecycle.py lines 109-131 (_redact_creds helper — copy reference path, watcher imports it)
    - 22b-RESEARCH.md §"Example 1: Watcher spawn + matcher + batched insert (authoritative shape)" (lines 561-651 — copy run_watcher body + drop-coalesce + batch flow)
    - 22b-SPIKES/spike-02-docker-sdk-backpressure.md — thresholds: 20k lines in 8s, 17,470 drops recorded, 0 FD/RSS delta, coalesce WARN to first + once-per-100
    - 22b-SPIKES/spike-03-watcher-teardown.md — `docker rm -f` ends iterator <270ms; watcher task done within 2s after stop_event; 0 dangling tasks
    - 22b-CONTEXT.md D-03, D-06, D-08, D-12
    - 22b-VALIDATION.md §"Spike Evidence → Test Fixture Mapping" — backpressure test threshold, teardown test threshold
  </read_first>
  <behavior>
    - `run_watcher(app_state, container_row_id, container_id, agent_id, recipe, channel, chat_id_hint)` registers itself as `(current_task(), stop_event)` in `app_state.log_watchers[container_row_id]`, runs the producer+consumer, and on termination removes itself from the registry.
    - Producer: `async for line in source.lines(): for kind, pattern in regexes.items(): if m := pattern.search(line): build payload via _build_payload(kind, m, chat_id_hint); validate via KIND_TO_PAYLOAD[kind].model_validate(payload); enqueue.` Unknown kinds dropped with `_log.warning`.
    - Consumer: timed wait up to BATCH_WINDOW_MS; flush when len(pending) >= BATCH_SIZE OR elapsed >= BATCH_WINDOW_MS; `async with app_state.db.acquire() as conn: await insert_agent_events_batch(conn, agent_id, pending)`; then `_get_poll_signal(app_state, agent_id).set()`.
    - QueueFull: `queue.get_nowait()` (drop oldest) + `queue.put_nowait(new)` + `drops += 1` + coalesced WARN (first + once-per-100).
    - Backpressure test (spike-02 port): alpine container emits 20000 lines in <8s. Watcher queue stays bounded at 500. Post-teardown: 0 dangling asyncio tasks. 0 FD leak (optional measurement via `/proc/<pid>/fd`). Note: this test attaches a NO-OP consumer (or regex matching NOTHING, so matched-line rate = 0 → queue stays empty) to validate that backpressure is SAFE in the raw-line flood path.
    - Teardown test (spike-03 port): start alpine + watcher (matching regex that fires on every line), after 1s call `container.remove(force=True)`, assert watcher task transitions to `done` within 2s; `asyncio.all_tasks()` delta is 0.
  </behavior>
  <action>
**Part A — APPEND to `api_server/src/api_server/services/watcher_service.py`**:

```python
# ------------------ matcher + payload build ------------------


def _compile_regexes(recipe: dict, channel: str) -> dict[str, re.Pattern]:
    """Compile every non-null entry in channels.<channel>.event_log_regex.

    Unknown kinds (keys NOT in VALID_KINDS) are discarded at compile time
    with a WARN log; recipes SHOULD only declare the 4 canonical kinds.
    """
    from .. models.events import VALID_KINDS   # deferred import avoids cycle
    channel_spec = (recipe.get("channels") or {}).get(channel, {}) or {}
    regex_map = channel_spec.get("event_log_regex") or {}
    compiled: dict[str, re.Pattern] = {}
    for kind, pattern in regex_map.items():
        if not pattern:
            continue
        if kind not in VALID_KINDS:
            _log.warning("recipe declared non-canonical event_log_regex kind %r — discarding", kind)
            continue
        try:
            compiled[kind] = re.compile(pattern)
        except re.error as exc:
            _log.warning("recipe event_log_regex.%s failed to compile: %s", kind, exc)
    # ready_log_regex (D-14) contributes agent_ready if not already covered.
    ready_pattern = (channel_spec.get("ready_log_regex")
                     or (recipe.get("persistent") or {}).get("spec", {}).get("ready_log_regex"))
    if ready_pattern and "agent_ready" not in compiled:
        try:
            compiled["agent_ready"] = re.compile(ready_pattern)
        except re.error as exc:
            _log.warning("ready_log_regex failed to compile: %s", exc)
    return compiled


def _build_payload(kind: str, match: re.Match, chat_id_hint: str | None) -> dict:
    """Project a regex match into a typed-per-kind payload dict (D-08).

    D-06 privacy discipline: NEVER include reply_text/body/message/content
    fields. chat_id comes from the regex named group OR the chat_id_hint
    fallback. captured_at is always set server-side.
    """
    from datetime import datetime, timezone
    groups = match.groupdict()
    now = datetime.now(timezone.utc).isoformat()
    if kind == "reply_sent":
        reply_text = groups.get("reply_text") or ""
        chat_id = (groups.get("chat_id") or chat_id_hint or "").strip() or "unknown"
        return {"chat_id": chat_id,
                "length_chars": len(reply_text),
                "captured_at": now}
    if kind == "reply_failed":
        return {"chat_id": groups.get("chat_id") or chat_id_hint,
                "reason": (groups.get("reason") or "unknown")[:256],
                "captured_at": now}
    if kind == "agent_ready":
        ready = groups.get("ready_line") or (match.group(0)[:512])
        return {"ready_log_line": ready, "captured_at": now}
    if kind == "agent_error":
        severity = (groups.get("severity") or "ERROR").upper()
        if severity not in ("ERROR", "FATAL"):
            severity = "ERROR"
        detail = (groups.get("detail") or groups.get("message") or match.group(0))[:512]
        return {"severity": severity, "detail": detail, "captured_at": now}
    raise ValueError(f"unknown kind: {kind!r}")


def _extract_correlation(kind: str, raw_line: str, match: re.Match) -> str | None:
    """Named capture group `cid` OR None (D-07 fallback = timestamp-window match)."""
    groups = match.groupdict()
    return groups.get("cid") or groups.get("correlation_id")


# ------------------ run_watcher ------------------


async def run_watcher(
    app_state,
    *,
    container_row_id: UUID,
    container_id: str,
    agent_id: UUID,
    recipe: dict,
    channel: str,
    chat_id_hint: str | None,
) -> None:
    """Spawn point called from /start (Plan 22b-04) and lifespan re-attach.

    Registers ``app_state.log_watchers[container_row_id] = (current_task, stop_event)``.
    Runs producer (source → matcher → queue) and consumer (batcher → event_store)
    until ``stop_event.is_set() and queue.empty()``.

    On exit (natural source end OR stop_event + drain), removes the registry
    entry in the ``finally`` block.
    """
    # Deferred imports (avoid cycles at module load; Plan 22b-02 owns these).
    from ..models.events import VALID_KINDS, KIND_TO_PAYLOAD
    from ..services.event_store import insert_agent_events_batch
    from pydantic import ValidationError

    stop_event = asyncio.Event()
    app_state.log_watchers[container_row_id] = (asyncio.current_task(), stop_event)
    try:
        source = _select_source(recipe, channel, container_id, chat_id_hint, stop_event)
        regexes = _compile_regexes(recipe, channel)
        if not regexes:
            _log.warning(
                "no event_log_regex declared for recipe/channel — watcher idles",
                extra={"container_id": container_id[:12], "channel": channel},
            )
            return
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)

        async def consumer():
            pending: list[tuple[str, dict, str | None]] = []
            last_flush = time.monotonic()
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=BATCH_WINDOW_MS / 1000)
                except asyncio.TimeoutError:
                    item = None
                if item is not None:
                    pending.append(item)
                now = time.monotonic()
                should_flush = (
                    pending
                    and (len(pending) >= BATCH_SIZE
                         or (now - last_flush) * 1000 >= BATCH_WINDOW_MS)
                )
                if should_flush:
                    async with app_state.db.acquire() as conn:
                        try:
                            await insert_agent_events_batch(conn, agent_id, pending)
                        except Exception:
                            _log.exception(
                                "event_store batch insert failed; dropping %d rows",
                                len(pending),
                                extra={"agent_id": str(agent_id)})
                    signal = _get_poll_signal(app_state, agent_id)
                    signal.set()
                    pending = []
                    last_flush = now
                if stop_event.is_set() and queue.empty():
                    # Drain any remaining pending before exit
                    if pending:
                        async with app_state.db.acquire() as conn:
                            try:
                                await insert_agent_events_batch(conn, agent_id, pending)
                            except Exception:
                                _log.exception("final drain batch failed")
                        _get_poll_signal(app_state, agent_id).set()
                    return

        consumer_task = asyncio.create_task(consumer())

        drops = 0
        try:
            async for raw_line in source.lines():
                for kind, pattern in regexes.items():
                    m = pattern.search(raw_line)
                    if not m:
                        continue
                    try:
                        payload = _build_payload(kind, m, chat_id_hint)
                    except ValueError:
                        continue
                    # Defense-in-depth validate via Pydantic (D-08) — a matcher
                    # bug cannot sneak an invalid payload into the queue.
                    cls = KIND_TO_PAYLOAD.get(kind)
                    if cls is None:
                        continue
                    try:
                        cls.model_validate(payload)
                    except ValidationError:
                        _log.warning("payload failed pydantic validation — dropping",
                                     extra={"kind": kind})
                        continue
                    corr = _extract_correlation(kind, raw_line, m)
                    try:
                        queue.put_nowait((kind, payload, corr))
                    except asyncio.QueueFull:
                        try:
                            queue.get_nowait()     # drop oldest
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            queue.put_nowait((kind, payload, corr))
                        except asyncio.QueueFull:
                            pass
                        drops += 1
                        if drops == 1 or drops % 100 == 0:
                            _log.warning(
                                "watcher queue drop",
                                extra={"agent_id": str(agent_id), "drops": drops})
        finally:
            stop_event.set()
            try:
                await asyncio.wait_for(consumer_task, timeout=2.0)
            except asyncio.TimeoutError:
                consumer_task.cancel()
    finally:
        app_state.log_watchers.pop(container_row_id, None)


__all__ = [
    "EventSource",
    "DockerLogsStreamSource",
    "DockerExecPollSource",
    "FileTailInContainerSource",
    "run_watcher",
    "_select_source",
    "_compile_regexes",
    "_build_payload",
    "_extract_correlation",
    "_get_poll_lock",
    "_get_poll_signal",
    "BATCH_SIZE",
    "BATCH_WINDOW_MS",
    "QUEUE_MAXSIZE",
]
```

**Part B — Create `api_server/tests/test_events_watcher_backpressure.py`:**

```python
"""Phase 22b-03 Task 3 — spike-02 backpressure reproducer.

Threshold (spike-02): 20k lines in <=8s, queue stays bounded at 500,
drop path fires cleanly, 0 FD leak post-teardown, 0 dangling tasks.

This test uses a regex that matches NOTHING so the queue stays empty
(matched-line rate is the critical rate, not raw rate — D-03). The
real-world flood case is "loud container + permissive regex" which
this test does NOT exercise (that would be a fuzz test). Spike-02's
verdict covers the load-test scenario empirically.

A secondary sub-test DOES attach a permissive regex; it measures
how many drops occur when the queue saturates.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from api_server.services.watcher_service import run_watcher

pytestmark = pytest.mark.integration


class _FakeAppState:
    def __init__(self, db_pool):
        self.db = db_pool
        self.log_watchers = {}
        self.event_poll_signals = {}
        self.event_poll_locks = {}
        self.locks_mutex = asyncio.Lock()


@pytest.mark.asyncio
async def test_watcher_backpressure_raw_flood_unmatched(running_alpine_container, real_db_pool, seed_agent_container):
    # 20k-line flood against a no-match regex: queue should never fill,
    # consumer never called, matcher discards everything.
    container = running_alpine_container(
        ["sh", "-c", "for i in $(seq 1 20000); do echo line-$i; done; sleep 3"])
    recipe = {"channels": {"telegram": {"event_log_regex": {
        "reply_sent": r"THIS_WILL_NEVER_MATCH_\d{99}"}}}}
    state = _FakeAppState(real_db_pool)
    task = asyncio.create_task(run_watcher(
        state,
        container_row_id=uuid4(),
        container_id=container.id,
        agent_id=seed_agent_container,
        recipe=recipe,
        channel="telegram",
        chat_id_hint="152099202",
    ))
    await asyncio.sleep(5.0)   # let flood complete
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=3.0)
    # No events should have been written (no regex match).
    async with real_db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            seed_agent_container)
    assert count == 0
    # Watcher registry cleaned
    assert len(state.log_watchers) == 0


@pytest.mark.asyncio
async def test_watcher_drops_coalesce_warn_on_saturation(running_alpine_container, real_db_pool, seed_agent_container, caplog):
    # Permissive regex that matches every line — queue will saturate
    # because the consumer hits real-PG and can't keep up at 2500 lines/s.
    container = running_alpine_container(
        ["sh", "-c", "for i in $(seq 1 20000); do echo 'reply-x '$i; done; sleep 3"])
    recipe = {"channels": {"telegram": {"event_log_regex": {
        "reply_sent": r"reply-x (?P<chat_id>\d+)"}}}}
    state = _FakeAppState(real_db_pool)
    import logging; caplog.set_level(logging.WARNING, logger="api_server.watcher")
    task = asyncio.create_task(run_watcher(
        state,
        container_row_id=uuid4(),
        container_id=container.id,
        agent_id=seed_agent_container,
        recipe=recipe,
        channel="telegram",
        chat_id_hint="0",
    ))
    await asyncio.sleep(6.0)
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=3.0)
    # WARN logs should have fired (first + once-per-100), but NOT once per drop.
    warn_msgs = [r.message for r in caplog.records if "queue drop" in r.message]
    # Coalescing means the number of WARNs is << number of drops.
    assert len(warn_msgs) < 500, f"WARN spam: {len(warn_msgs)}"
```

**Part C — Create `api_server/tests/test_events_watcher_teardown.py`:**

```python
"""Phase 22b-03 Task 3 — spike-03 teardown reproducer.

Threshold (spike-03): docker rm -f ends iterator <270ms; watcher task
transitions to done within 2s; asyncio.all_tasks() delta == 0.
"""
import asyncio
import pytest
from uuid import uuid4
from api_server.services.watcher_service import run_watcher

pytestmark = pytest.mark.integration


class _FakeAppState:
    def __init__(self, db_pool):
        self.db = db_pool
        self.log_watchers = {}
        self.event_poll_signals = {}
        self.event_poll_locks = {}
        self.locks_mutex = asyncio.Lock()


@pytest.mark.asyncio
async def test_watcher_teardown_on_remove_force(running_alpine_container, real_db_pool, seed_agent_container):
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
    recipe = {"channels": {"telegram": {"event_log_regex": {
        "reply_sent": r"reply (?P<chat_id>\d+)"}}}}
    state = _FakeAppState(real_db_pool)
    tasks_before = set(asyncio.all_tasks())
    watcher_task = asyncio.create_task(run_watcher(
        state, container_row_id=uuid4(), container_id=container.id,
        agent_id=seed_agent_container, recipe=recipe, channel="telegram",
        chat_id_hint="0"))
    await asyncio.sleep(0.5)
    container.remove(force=True)
    # Watcher must complete within 3s (spike-03 budget + 1s slack for consumer drain)
    await asyncio.wait_for(watcher_task, timeout=3.0)
    # Registry must be empty
    assert len(state.log_watchers) == 0
    # No dangling tasks introduced by this test (besides the set we started with)
    tasks_after = set(asyncio.all_tasks()) - tasks_before - {asyncio.current_task()}
    # Filter out tasks that just haven't been awaited yet
    still_alive = [t for t in tasks_after if not t.done()]
    assert still_alive == [], f"dangling tasks: {still_alive}"


@pytest.mark.asyncio
async def test_watcher_teardown_on_stop_event(running_alpine_container, real_db_pool, seed_agent_container):
    """stop_event.set() from registry also terminates cleanly."""
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo reply 123; sleep 0.05; done"])
    recipe = {"channels": {"telegram": {"event_log_regex": {
        "reply_sent": r"reply (?P<chat_id>\d+)"}}}}
    state = _FakeAppState(real_db_pool)
    crid = uuid4()
    task = asyncio.create_task(run_watcher(
        state, container_row_id=crid, container_id=container.id,
        agent_id=seed_agent_container, recipe=recipe, channel="telegram",
        chat_id_hint="0"))
    await asyncio.sleep(0.5)
    # Signal stop via registry
    _task, stop_event = state.log_watchers[crid]
    stop_event.set()
    # Also remove the container so the source iterator can end (the flood
    # consumer will keep pulling lines otherwise — stop_event handles the
    # producer loop but the inner source.lines() loop honors stop_event
    # between yields).
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=3.0)
```

**Verify:**
```bash
cd api_server && pytest -x tests/test_events_watcher_backpressure.py tests/test_events_watcher_teardown.py -v 2>&1 | tail -15
```
All green.
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.services.watcher_service import run_watcher, _compile_regexes, _build_payload, _extract_correlation" && pytest -x tests/test_events_watcher_backpressure.py tests/test_events_watcher_teardown.py -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 4 { exit 0 } { exit 1 }'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "async def run_watcher" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "def _compile_regexes" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -c "def _build_payload" api_server/src/api_server/services/watcher_service.py` returns exactly `1`
    - `grep -cE "reply_text|content|body|message_body" api_server/src/api_server/services/watcher_service.py | awk '$1 <= 2 { exit 0 } { exit 1 }'` passes (D-06 — reply_text only referenced as an INPUT groupdict key that we compute length from; no reply_text field flows to the payload output)
    - `grep -c "insert_agent_events_batch" api_server/src/api_server/services/watcher_service.py` returns `>=1`
    - `grep -c "_get_poll_signal(.*).set()" api_server/src/api_server/services/watcher_service.py` returns `>=1` (watcher wakes long-poll after batch commit)
    - `grep -c "QueueFull" api_server/src/api_server/services/watcher_service.py` returns `>=1`
    - `grep -c "drops % 100 == 0\|drops == 1" api_server/src/api_server/services/watcher_service.py` returns `>=1` (coalesced WARN per spike-02)
    - `grep -c "KIND_TO_PAYLOAD" api_server/src/api_server/services/watcher_service.py` returns `>=1` (defense-in-depth validation before enqueue)
    - `cd api_server && pytest -x tests/test_events_watcher_backpressure.py tests/test_events_watcher_teardown.py -v 2>&1 | grep -cE "PASSED"` returns `>=4`
    - `cd api_server && pytest -x tests/test_events_watcher_*.py -v 2>&1 | grep -cE "PASSED"` returns `>=11` (4 docker_logs + 5 exec_poll + 2 file_tail + 2 backpressure + 2 teardown)
  </acceptance_criteria>
  <done>run_watcher producer/consumer coordinates queue + batch + signal + drop-coalesce; spike-02 and spike-03 reproducers green against real alpine + real PG; KIND_TO_PAYLOAD validation before enqueue is defense-in-depth for D-06/D-08.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Docker daemon → watcher | Untrusted container stdout crosses here. Every raw line is regex-matched; unmatched lines discarded without entering memory beyond the source's chunk buffer. |
| regex match → payload build | Untrusted capture groups (chat_id, reply_text, severity, detail) become payload dict fields. Pydantic `KIND_TO_PAYLOAD` validation BEFORE enqueue rejects invalid shapes. |
| watcher → event_store batch INSERT | Payload dicts cross into Postgres. CHECK constraint (Plan 22b-02) backstops the kind enum; ConfigDict(extra="forbid") backstops field whitelist. |
| watcher registry (`app.state.log_watchers`) | In-process only; no external access. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-03-01 | Denial of Service | DockerLogsStreamSource iterator vs. flood | mitigate | Spike-02 empirically validated: 20k-line flood produces 17,470 drops, queue bounded at 500, 0 FD/RSS delta. test_watcher_backpressure_raw_flood_unmatched + test_watcher_drops_coalesce_warn_on_saturation are the regression guards |
| T-22b-03-02 | Information Disclosure | `_build_payload(reply_sent)` | mitigate | `reply_text` capture group is read ONLY to compute `length_chars`; NEVER copied into the payload dict. D-06 enforcement is defense-in-depth: Pydantic `ReplySentPayload.model_config = ConfigDict(extra="forbid")` (Plan 22b-02) rejects any payload with a reply_text field at `model_validate` time. `grep -c "reply_text" api_server/src/api_server/services/watcher_service.py` is ≤2 and only appears in `_build_payload` as a read-only input |
| T-22b-03-03 | Denial of Service | regex ReDoS via user-authored event_log_regex | mitigate | `re.compile` is called at watcher start; malformed regexes surface as a WARN log and are skipped (defense-in-depth — recipes ship regexes, not end-users). A synthetic long-line test-case would live in a separate `test_regex_safety.py` (RESEARCH §Known Threat Patterns) — out of scope for this plan but added to Plan 22b-06's recipe review |
| T-22b-03-04 | Tampering | run_watcher batch INSERT ordering vs. concurrent writers | accept | Single-writer-per-container-row invariant enforced by `app.state.log_watchers` registry keyed on `container_row_id`; Plan 22b-02's advisory-lock + UNIQUE backstop catches any pathological duplicate spawns |
| T-22b-03-05 | Information Disclosure | `_log.warning(..., extra={"container_id": ...})` | mitigate | Only first 12 chars of container_id are bound into the `extra` (`container_id[:12]`); bearer tokens never reach this layer; chat_id_hint is numeric so not a secret; exception strings that might contain tokens flow through `_log.exception` which writes the traceback verbatim — chat_id_hint is 6-10 digit numeric, not subject to cred-redaction rule (8-char threshold) |
| T-22b-03-06 | Elevation of Privilege | FileTailInContainerSource arbitrary path traversal | mitigate | `sessions_manifest` and `session_log_template` come from the recipe YAML (authorial ground truth, loaded via the recipes_loader); user input (`chat_id_hint`) is only interpolated via `.format(session_id=...)` where `session_id` is read out of the manifest's typed `sessionId` field. A malicious manifest could in principle include a traversal path but the manifest itself is inside the container and the `docker exec tail -F` runs with the container's user — no host-filesystem access |
| T-22b-03-07 | Denial of Service | unknown event_source_fallback.kind in recipe | mitigate | `_select_source` raises ValueError explicitly; caller (Plan 22b-04 lifecycle) catches, logs, and skips watcher spawn without failing the `/start` handler (events are observability, not correctness per 22b scope) |
</threat_model>

<verification>
- `cd api_server && pytest -x tests/test_events_watcher_docker_logs.py tests/test_events_watcher_exec_poll.py tests/test_events_watcher_file_tail.py tests/test_events_watcher_backpressure.py tests/test_events_watcher_teardown.py -v 2>&1 | tail -10` shows all PASSED
- `python3 -c "from api_server.services.watcher_service import (EventSource, DockerLogsStreamSource, DockerExecPollSource, FileTailInContainerSource, run_watcher, _select_source, _get_poll_lock, _get_poll_signal, BATCH_SIZE, BATCH_WINDOW_MS)"` exits 0
- `grep -cE "^class (DockerLogsStreamSource|DockerExecPollSource|FileTailInContainerSource|EventSource)" api_server/src/api_server/services/watcher_service.py` returns exactly `4`
- `grep -c "Task.cancel" api_server/src/api_server/services/watcher_service.py | awk '$1 <= 1 { exit 0 } { exit 1 }'` passes (one acceptable fallback in consumer timeout; NO cancellation of the watcher itself per spike-03)
- No existing test regresses: `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no red
</verification>

<success_criteria>
1. `watcher_service.py` declares `EventSource` Protocol + 3 concrete source classes + `run_watcher` + `_select_source` + `_get_poll_lock` + `_get_poll_signal` with all exports listed in `__all__`
2. D-23 dispatch is verbatim per RESEARCH §D-23 — default to DockerLogsStreamSource, dispatch on `event_source_fallback.kind`, raise ValueError on unknown kind
3. Consumer acquires a pool connection ONLY during `insert_agent_events_batch` call (connection-per-scope); signal `.set()` fires after successful batch commit
4. Drop path (QueueFull) uses coalesced WARN: first + once-per-100 (not every drop) — spike-02 discipline
5. Spike-02 reproducer: 20k-line flood test with no-match regex → 0 events written, 0 dangling tasks post-teardown
6. Spike-03 reproducer: docker rm -f → watcher task done within 3s, log_watchers registry empty
7. All 11+ integration tests (4 docker_logs + 5 exec_poll + 2 file_tail + 2 backpressure + 2 teardown) pass on real docker daemon + real PG via testcontainers
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-03-SUMMARY.md` with:
- The 3 EventSource implementations' resolved shape (argv / paths / poll cadence actually used)
- The `_select_source` dispatch table (recipe kind → class)
- Spike-02 reproducer measurements: flood rate, drop count, queue high-water mark
- Spike-03 reproducer measurements: teardown wall time
- Any deviations from RESEARCH §Example 1 authoritative shape
- BusyBox tail -F verdict (inherited from Plan 22b-01 SUMMARY): default `tail -F` or BusyBox fallback
</output>
