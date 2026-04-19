"""Phase 22b-01 Task 3 — A3 assumption probe.

BusyBox (alpine) ``tail -F`` must line-buffer reliably for Wave 1's
``FileTailInContainerSource`` (openclaw session JSONL tail) to work. This
probe writes a known line into a file inside a running alpine container,
spawns ``docker exec <cid> tail -n0 -F <path>``, and asserts the line
surfaces on :attr:`subprocess.Popen.stdout` within 500ms.

**PASS verdict** = A3 validated; Wave 1 uses the direct
``tail -F`` path in ``FileTailInContainerSource``.

**FAIL verdict** = BusyBox does NOT line-buffer under ``tail -F``; Wave 1
MUST adopt the documented fallback pattern
``sh -c 'while :; do cat; sleep 0.2; done'`` inside the
``FileTailInContainerSource`` implementation.

This test is a definitive PASS/FAIL oracle — it is NOT marked xfail.
The Wave 1 planner reads this verdict to pick the implementation branch.
"""
from __future__ import annotations

import selectors
import subprocess
import time

import pytest


@pytest.mark.api_integration
def test_busybox_tail_line_buffer(running_alpine_container):
    """Definitive probe for A3 — BusyBox ``tail -F`` line-buffering.

    Sequence:

    1. Spawn an alpine:3.19 container with ``touch /tmp/probe.log; tail -f /dev/null``
       so the container lives long enough to exec into.
    2. Give tail 300ms to attach.
    3. Run ``docker exec <cid> tail -n0 -F /tmp/probe.log`` via subprocess.
    4. Write the sentinel line into the file inside the container.
    5. Select on the Popen's stdout with a 500ms timeout.
    6. Assert the sentinel appears within the window.
    """
    container = running_alpine_container(
        ["sh", "-c", "touch /tmp/probe.log; tail -f /dev/null"]
    )
    try:
        # Give the container's own `tail -f /dev/null` time to boot so the
        # subsequent `docker exec tail -F` lands on a running container.
        time.sleep(0.3)

        # Launch tail -F on the probe file via docker exec. Line-buffered
        # pipe (bufsize=1) so Python's buffer doesn't mask a successful
        # BusyBox line-flush.
        proc = subprocess.Popen(
            [
                "docker", "exec", container.id,
                "tail", "-n0", "-F", "/tmp/probe.log",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            # Let `tail -F` attach to the file inside the container.
            time.sleep(0.3)

            # Write a sentinel line into the file inside the container.
            subprocess.run(
                [
                    "docker", "exec", container.id,
                    "sh", "-c", "echo probe-line-a3-xyz >> /tmp/probe.log",
                ],
                check=True,
                capture_output=True,
            )

            # Wait up to 500ms for the sentinel to surface on tail's stdout.
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            events = sel.select(timeout=0.5)

            assert events, (
                "BusyBox tail -F did NOT line-buffer within 500ms — "
                "Wave 1 must use the sh/cat/sleep fallback in "
                "FileTailInContainerSource"
            )

            line = proc.stdout.readline().strip()
            assert "probe-line-a3-xyz" in line, (
                f"Expected correlation sentinel in tail output, got: {line!r}"
            )
        finally:
            proc.kill()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
    finally:
        # Container cleanup is handled by the running_alpine_container
        # factory's teardown, but force-remove here so tail -F's docker
        # exec doesn't hold the container alive beyond the test boundary.
        try:
            container.remove(force=True)
        except Exception:
            pass
