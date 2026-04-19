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

    Every concrete source yields raw lines (bytes->str decoded) that the
    watcher's matcher runs through the recipe's event_log_regex dict. The
    source owns its own teardown (iterator-end OR poll-loop-break). The
    watcher does NOT cancel the source coroutine; instead it signals via
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
    No coroutine cancellation required. ``tail=0`` so we do NOT re-read the
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
                if isinstance(chunk, (bytes, bytearray)):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = str(chunk)
                for line in text.splitlines():
                    if line:
                        yield line
        finally:
            try:
                client.close()
            except Exception:
                pass


__all__ = [
    "EventSource",
    "DockerLogsStreamSource",
    "_get_poll_lock",
    "_get_poll_signal",
    "BATCH_SIZE",
    "BATCH_WINDOW_MS",
    "QUEUE_MAXSIZE",
]
