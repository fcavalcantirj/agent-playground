"""Phase 22b-03 Task 1 — DockerLogsStreamSource integration tests.

Every test uses the Plan 22b-01 ``running_alpine_container`` fixture to
spawn a real alpine container; NO MOCKS (Golden Rule 1). Wall-time budgets
come from spike-03 (iterator-end <2s) and spike-02 (queue stays bounded).

Marked ``api_integration`` because they require a live Docker daemon. The
default pytest invocation (no ``-m`` flag) STILL collects + runs them; the
marker exists so a CI lane that disables Docker can opt out via
``-m "not api_integration"``.
"""
from __future__ import annotations

import asyncio

import pytest

from api_server.services.watcher_service import DockerLogsStreamSource

pytestmark = pytest.mark.api_integration


async def _drain(source) -> None:
    async for _ in source.lines():
        pass


@pytest.mark.asyncio
async def test_docker_logs_source_yields_echoed_lines(running_alpine_container):
    stop_event = asyncio.Event()
    # Initial sleep gives the test code a window to attach BEFORE the lines
    # start flowing. tail=0 means "no historical buffer" so any lines emitted
    # before our `client.logs(follow=True)` call returns are missed by design
    # (D-11). We compensate by spacing emissions across ~1.5s while the
    # consumer is already attached.
    container = running_alpine_container(
        ["sh", "-c", "sleep 0.5; for i in $(seq 1 20); do echo line-$i; sleep 0.05; done; sleep 10"]
    )
    source = DockerLogsStreamSource(container.id, stop_event)

    collected: list[str] = []

    async def _consume():
        async for line in source.lines():
            collected.append(line)
            if len(collected) >= 20:
                stop_event.set()
                return

    await asyncio.wait_for(_consume(), timeout=8.0)
    assert collected == [f"line-{i}" for i in range(1, 21)]


@pytest.mark.asyncio
async def test_docker_logs_source_terminates_on_remove_force(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
    source = DockerLogsStreamSource(container.id, stop_event)
    task = asyncio.create_task(_drain(source))
    await asyncio.sleep(0.5)  # let attach happen
    container.remove(force=True)
    # spike-03 budget = 2s; allow 3s for CI jitter and asyncio.to_thread wake.
    await asyncio.wait_for(task, timeout=3.0)


@pytest.mark.asyncio
async def test_docker_logs_source_honours_stop_event(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo x; sleep 0.1; done"]
    )
    source = DockerLogsStreamSource(container.id, stop_event)
    task = asyncio.create_task(_drain(source))
    await asyncio.sleep(0.3)
    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_docker_logs_source_decodes_non_utf8_safely(running_alpine_container):
    stop_event = asyncio.Event()
    container = running_alpine_container(
        ["sh", "-c", "sleep 0.5; printf 'valid\\n'; printf '\\xff\\xfe\\n'; printf 'after\\n'; sleep 10"]
    )
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
