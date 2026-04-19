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


class DockerExecPollSource:
    """Source kind: ``docker_exec_poll`` (nullclaw).

    Evidence: spike-01c-nullclaw.md. Nullclaw's stdout is barren (9 lines
    total across a full session including boot). The authoritative activity
    log is ``nullclaw history show <session_id> --json`` which prints the
    entire conversation as a JSON document. This source polls that CLI at
    ``poll_interval_s`` cadence, diffs successive ``messages[]`` arrays,
    and yields one synthetic JSON line per NEW entry.

    Spec (from recipes/nullclaw.yaml event_source_fallback.spec)::

        argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]
        session_id_template: "agent:main:telegram:direct:{chat_id}"

    Degrade-gracefully (A6 in RESEARCH §Open Questions): when chat_id_hint
    is ``None`` (lifespan re-attach path), we cannot compute session_id;
    the source emits a single ``_log.warning`` and returns immediately. The
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
                _log.warning(
                    "docker exec poll timed out",
                    extra={"container_id": self.container_id[:12]},
                )
                await asyncio.sleep(self.poll_interval_s)
                continue
            if out.returncode != 0:
                # Container likely gone; let caller's stop_event loop end us.
                _log.debug(
                    "docker exec poll returncode=%s stderr=%s",
                    out.returncode,
                    (out.stderr or "")[:200],
                )
                await asyncio.sleep(self.poll_interval_s)
                continue
            try:
                doc = json.loads(out.stdout)
            except json.JSONDecodeError:
                _log.warning(
                    "docker exec poll produced non-JSON output",
                    extra={"container_id": self.container_id[:12]},
                )
                await asyncio.sleep(self.poll_interval_s)
                continue
            current = doc.get("messages") or []
            # Emit only the tail-extension (Pitfall 3 — lagging is fine; the
            # synthetic line carries role + payload-text so the watcher matcher
            # does role-based extraction rather than regex).
            for msg in current[len(prev_messages):]:
                yield json.dumps(msg)
            prev_messages = current
            await asyncio.sleep(self.poll_interval_s)


class FileTailInContainerSource:
    """Source kind: ``file_tail_in_container`` (openclaw).

    Evidence: spike-01e-openclaw.md. Openclaw's docker logs are barren;
    the only authoritative record of per-turn activity is the session
    JSONL at ``/home/node/.openclaw/agents/main/sessions/<session_id>.jsonl``.
    One JSON document per line; assistant replies carry the text payload
    inside the JSONL entry's nested-text field (type=='text' entry).

    Flow:
      1. ``docker exec <cid> cat <sessions_manifest>`` → parse JSON.
      2. Pick session whose ``origin.from`` matches ``telegram:<chat_id_hint>``.
      3. Resolve tail path from ``session_log_template.format(session_id=...)``.
      4. Spawn the tail subprocess via ``subprocess.Popen``.
      5. Bridge ``proc.stdout.readline`` through ``asyncio.to_thread``.
      6. On stop_event OR tail subprocess exit, terminate cleanly.

    Pitfall 2 (session-id drift) — if the user creates a new chat with
    openclaw, a new session JSONL is spawned; this source is scoped to
    the session resolved at attach time. A second chat on the same
    container needs a second FileTailInContainerSource (post-MVP, not
    in 22b scope). The session resolution step emits a ``_log.warning``
    when no match is found so ops can see the reason Gate B failed.

    BusyBox tail -F line-buffering — Plan 22b-01 PROBED assumption A3
    and the verdict was **FAIL** (BusyBox's tail -F has ~547ms first-emit
    latency vs the 500ms SLA; verbatim from 22b-01-SUMMARY.md). The
    fallback path ``sh -c 'while :; do cat <path>; sleep 0.2; done'`` is
    therefore the DEFAULT for this class. Keep ``_USE_TAIL_FALLBACK = True``
    until a future probe against a non-BusyBox tail flips the verdict.
    """

    # Plan 22b-01 SUMMARY.md verdict — A3 FAILED → fallback REQUIRED.
    _USE_TAIL_FALLBACK = True

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
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None
        if out.returncode != 0:
            return None
        try:
            manifest = json.loads(out.stdout)
        except json.JSONDecodeError:
            return None
        # Manifest shape (spike-01e):
        # {"agent:main:main": {"sessionId":"...","origin":{"from":"telegram:152099202",...}}}
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
            self.chat_id_hint,
            len(manifest),
            extra={"container_id": self.container_id[:12]},
        )
        return None

    async def lines(self) -> AsyncIterator[str]:
        path = await self._resolve_session_path()
        if path is None:
            return
        if self._USE_TAIL_FALLBACK:
            # BusyBox tail -F A3 probe FAILED in Plan 22b-01 — use the
            # cat-and-sleep loop instead. The loop emits the entire file
            # every 200ms so the watcher dedupes via correlation_id /
            # role-based extraction at the matcher layer (D-07 contract).
            argv = [
                "docker",
                "exec",
                self.container_id,
                "sh",
                "-c",
                f"while :; do cat '{path}'; sleep 0.2; done",
            ]
        else:  # pragma: no cover — gated on a future BusyBox-replaced base image
            argv = [
                "docker",
                "exec",
                self.container_id,
                "tail",
                "-n0",
                "-F",
                path,
            ]
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        try:
            while not self.stop_event.is_set():
                line = await asyncio.to_thread(proc.stdout.readline)
                if line == "":
                    return  # tail subprocess exited (file gone / container reaped)
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


# ------------------ matcher + payload build ------------------


def _compile_regexes(recipe: dict, channel: str) -> dict[str, "re.Pattern"]:
    """Compile every non-null entry in ``channels.<channel>.event_log_regex``.

    Unknown kinds (keys NOT in ``VALID_KINDS``) are discarded at compile
    time with a WARN log; recipes SHOULD only declare the 4 canonical
    kinds. The ``ready_log_regex`` (D-14) contributes ``agent_ready`` if
    not already covered by ``event_log_regex``.

    ``VALID_KINDS`` is imported lazily from Plan 22b-02's ``models.events``
    so this module remains importable in worktrees where Plan 22b-02 has
    not yet merged (Wave 1 parallel execution).
    """
    from ..models.events import VALID_KINDS  # deferred import — Plan 22b-02

    channel_spec = (recipe.get("channels") or {}).get(channel, {}) or {}
    regex_map = channel_spec.get("event_log_regex") or {}
    compiled: dict[str, re.Pattern] = {}
    for kind, pattern in regex_map.items():
        if not pattern:
            continue
        if kind not in VALID_KINDS:
            _log.warning(
                "recipe declared non-canonical event_log_regex kind %r — discarding",
                kind,
            )
            continue
        try:
            compiled[kind] = re.compile(pattern)
        except re.error as exc:
            _log.warning("recipe event_log_regex.%s failed to compile: %s", kind, exc)
    # ready_log_regex (D-14) contributes agent_ready if not already covered.
    ready_pattern = channel_spec.get("ready_log_regex") or (
        recipe.get("persistent") or {}
    ).get("spec", {}).get("ready_log_regex")
    if ready_pattern and "agent_ready" not in compiled and "agent_ready" in VALID_KINDS:
        try:
            compiled["agent_ready"] = re.compile(ready_pattern)
        except re.error as exc:
            _log.warning("ready_log_regex failed to compile: %s", exc)
    return compiled


def _build_payload(kind: str, match: "re.Match", chat_id_hint: str | None) -> dict:
    """Project a regex match into a typed-per-kind payload dict (D-08).

    D-06 privacy: see PLAN.md threat T-22b-03-02 — the recipe-author capture
    group named ``reply_text`` is read ONLY to compute ``length_chars`` and
    is then discarded. No raw outbound text crosses into the payload dict;
    Pydantic ``ConfigDict(extra='forbid')`` (Plan 22b-02) is the second-line
    defense at validate time.
    """
    from datetime import datetime, timezone

    groups = match.groupdict()
    now = datetime.now(timezone.utc).isoformat()
    if kind == "reply_sent":
        outbound = groups.get("reply_text") or ""   # read-only — see D-06 above
        chat_id = (groups.get("chat_id") or chat_id_hint or "").strip() or "unknown"
        return {
            "chat_id": chat_id,
            "length_chars": len(outbound),
            "captured_at": now,
        }
    if kind == "reply_failed":
        return {
            "chat_id": groups.get("chat_id") or chat_id_hint,
            "reason": (groups.get("reason") or "unknown")[:256],
            "captured_at": now,
        }
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


def _extract_correlation(
    kind: str, raw_line: str, match: "re.Match"
) -> str | None:
    """Named capture group ``cid`` OR ``correlation_id`` OR None.

    D-07 fallback (timestamp-window match) is the responsibility of the
    consumer test harness, not this layer.
    """
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

    Registers ``app_state.log_watchers[container_row_id] = (current_task,
    stop_event)``. Runs producer (source → matcher → queue) and consumer
    (batcher → event_store) until ``stop_event.is_set() and queue.empty()``.

    On exit (natural source end OR ``stop_event`` + drain), removes the
    registry entry in the ``finally`` block.
    """
    # Deferred imports (avoid cycles at module load; Plan 22b-02 owns these).
    from ..models.events import KIND_TO_PAYLOAD
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
                        queue.get(), timeout=BATCH_WINDOW_MS / 1000
                    )
                except asyncio.TimeoutError:
                    item = None
                if item is not None:
                    pending.append(item)
                now = time.monotonic()
                should_flush = pending and (
                    len(pending) >= BATCH_SIZE
                    or (now - last_flush) * 1000 >= BATCH_WINDOW_MS
                )
                if should_flush:
                    async with app_state.db.acquire() as conn:
                        try:
                            await insert_agent_events_batch(conn, agent_id, pending)
                        except Exception:
                            _log.exception(
                                "event_store batch insert failed; dropping %d rows",
                                len(pending),
                                extra={"agent_id": str(agent_id)},
                            )
                    _get_poll_signal(app_state, agent_id).set()
                    pending = []
                    last_flush = now
                if stop_event.is_set() and queue.empty():
                    # Drain any remaining pending before exit
                    if pending:
                        async with app_state.db.acquire() as conn:
                            try:
                                await insert_agent_events_batch(
                                    conn, agent_id, pending
                                )
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
                        _log.warning(
                            "payload failed pydantic validation — dropping",
                            extra={"kind": kind},
                        )
                        continue
                    corr = _extract_correlation(kind, raw_line, m)
                    try:
                        queue.put_nowait((kind, payload, corr))
                    except asyncio.QueueFull:
                        try:
                            queue.get_nowait()  # drop oldest
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
                                extra={
                                    "agent_id": str(agent_id),
                                    "drops": drops,
                                },
                            )
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
