"""StreamUsageParser — byte-level SSE parser for the proxy hot path.

The proxy router (Plan 04, ``routes/llm_proxy.py``) tees the upstream
streaming response: each chunk is forwarded to the bot AND fed into
this parser. After the stream closes, :meth:`finalize` returns a
:class:`ParsedUsage` (reused from ``services/usage_recorder.py``) that
the proxy persists to ``usage_logs``.

Two SSE shapes are supported, dispatched by ``sse_format``:

  - ``"openai"`` (OpenAI, OpenRouter): scan all ``data: {...}\\n`` lines
    for a ``usage`` field at the top level. **Last-wins** — the final
    chunk carries the canonical numbers (``include_usage=true`` is
    injected by the proxy at the body-mutation step). The parser does
    NOT break on ``[DONE]`` because some providers (notably OpenRouter)
    emit the usage chunk AFTER the ``[DONE]`` sentinel — RESEARCH.md
    Pitfall 2.

  - ``"anthropic"`` (Anthropic native): consume ``message_start`` once
    (carries ``input_tokens`` + cache fields, FINAL at first event) and
    each ``message_delta`` for ``output_tokens`` — **AMD-07 last-wins
    overwrite, NEVER sum**. Anthropic's ``message_delta.usage.output_
    tokens`` is **cumulative**, not a delta; summing across deltas
    overcounts (langchain-js #10249, agno-agi #6537). PROBE-VAL-13
    confirmed empirically that claude-haiku-4-5 emits exactly one
    ``message_delta`` per response with the full cumulative total —
    last-wins gives the right answer in both the multi-delta and
    single-delta cases.

Status determination:

  - OpenAI: ``status='success'`` when usage was captured AND the
    ``[DONE]`` sentinel arrived; ``status='failed'`` otherwise.
  - Anthropic: ``status='success'`` when ``message_stop`` event was
    seen; ``status='failed'`` otherwise.

Chunked-byte boundaries: ``feed()`` accepts arbitrary byte chunks and
buffers across newline-incomplete boundaries; complete lines are
extracted via ``partition(b'\\n')`` so a JSON payload split across two
``feed()`` calls is parsed correctly when the second half arrives.

Malformed JSON is silently skipped — a single garbled line cannot
abort the parse of the rest of the stream (the bot still receives
every byte; only our own usage capture is best-effort).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from dataclasses import replace

from .usage_recorder import (
    ParsedUsage,
    _parse_anthropic_native,
    _parse_openai_compat,
)

_log = logging.getLogger("api_server.stream_parser")


class StreamUsageParser:
    """Byte-level SSE parser. Feed chunks; finalize at stream close.

    Per-instance: do NOT share across requests. The internal buffer +
    last-wins state is request-scoped.
    """

    __slots__ = (
        "_provider",
        "_sse_format",
        "_buf",
        "_upstream_request_id",
        # OpenAI / OpenRouter state
        "_final_usage",
        # Anthropic state (AMD-07)
        "_anthropic_input",
        "_anthropic_cache_read",
        "_anthropic_cache_creation",
        "_anthropic_output",
        # Completion sentinel
        "_was_complete",
        # Phase 29 hotfix — non-streaming JSON fallback
        "_saw_sse_line",
        "_raw_body",
    )

    def __init__(self, provider: str, sse_format: str) -> None:
        self._provider = provider
        self._sse_format = sse_format
        self._buf = bytearray()
        self._upstream_request_id: str | None = None
        # OpenAI/OpenRouter: assembled usage dict from the last chunk
        # that carried one. Last-wins.
        self._final_usage: dict[str, Any] | None = None
        # Anthropic native: input + cache fields are FINAL on
        # message_start; output_tokens is OVERWRITTEN on each
        # message_delta (AMD-07 last-wins).
        self._anthropic_input: int = 0
        self._anthropic_cache_read: int = 0
        self._anthropic_cache_creation: int = 0
        self._anthropic_output: int = 0
        # True when [DONE] (OpenAI) or message_stop (Anthropic) was seen.
        self._was_complete: bool = False
        # Phase 29 hotfix — non-streaming JSON fallback. ``_saw_sse_line``
        # flips True the first time a ``data: ...`` line is encountered.
        # ``_raw_body`` accumulates EVERY chunk so finalize() can parse
        # the complete body as a single JSON object when no SSE was seen.
        self._saw_sse_line: bool = False
        self._raw_body = bytearray()

    def feed(self, chunk: bytes) -> None:
        """Append + scan complete ``\\n``-terminated lines.

        Buffers across chunk boundaries: a line split across two
        ``feed()`` calls is reassembled from the trailing buffer
        contents on the second call.
        """
        if not chunk:
            return
        self._buf.extend(chunk)
        # Phase 29: also accumulate the raw body for the non-streaming
        # JSON fallback in finalize(). Bounded by upstream Content-Length;
        # a chat-completion body is < 50 KB in practice.
        self._raw_body.extend(chunk)
        # Drain every complete line out of the buffer; whatever remains
        # after the last \n stays for the next feed.
        while b"\n" in self._buf:
            line, _, rest = self._buf.partition(b"\n")
            self._buf = bytearray(rest)
            self._scan_line(bytes(line).strip())

    def _scan_line(self, line: bytes) -> None:
        """Inspect one ``data: ...`` line, dispatch on ``sse_format``."""
        if not line.startswith(b"data: "):
            return
        # Phase 29: any ``data: `` line confirms an SSE stream — disables
        # the non-streaming JSON fallback in finalize().
        self._saw_sse_line = True
        payload = line[6:].strip()
        if payload == b"[DONE]":
            # OpenAI / OpenRouter completion sentinel. Do NOT break the
            # outer loop — OpenRouter emits the usage chunk AFTER [DONE]
            # in some configurations (RESEARCH.md Pitfall 2).
            self._was_complete = True
            return
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            # Garbage line — skip silently. The bot still receives the
            # raw bytes; our usage capture is best-effort.
            return
        if not isinstance(event, dict):
            return

        if self._sse_format == "openai":
            self._scan_openai(event)
        elif self._sse_format == "anthropic":
            self._scan_anthropic(event)
        # Unknown sse_format → silently no-op; finalize() returns failed.

    def _scan_openai(self, event: dict[str, Any]) -> None:
        """OpenAI / OpenRouter event extraction. Last-wins on usage."""
        usage = event.get("usage")
        if isinstance(usage, dict):
            self._final_usage = usage
        rid = event.get("id")
        if rid:
            self._upstream_request_id = str(rid)

    def _scan_anthropic(self, event: dict[str, Any]) -> None:
        """Anthropic native event extraction. AMD-07 last-wins on output_tokens."""
        etype = event.get("type")
        if etype == "message_start":
            msg = event.get("message") or {}
            u = msg.get("usage") or {}
            # message_start carries the FINAL input + cache numbers
            # (Anthropic emits totals once at start). Capture once.
            self._anthropic_input = int(u.get("input_tokens") or 0)
            self._anthropic_cache_creation = int(
                u.get("cache_creation_input_tokens") or 0
            )
            self._anthropic_cache_read = int(
                u.get("cache_read_input_tokens") or 0
            )
            # message_start.usage.output_tokens is typically 1 (a
            # priming token) — capture so finalize() returns a sane
            # default if no message_delta arrives.
            start_out = u.get("output_tokens")
            if start_out is not None:
                self._anthropic_output = int(start_out)
            mid = msg.get("id")
            if mid:
                self._upstream_request_id = str(mid)
        elif etype == "message_delta":
            u = event.get("usage") or {}
            ot = u.get("output_tokens")
            if ot is not None:
                # AMD-07 — output_tokens is CUMULATIVE; OVERWRITE,
                # NEVER sum. langchain-js #10249 / agno-agi #6537
                # both shipped 30-50% over-count bugs by += here.
                self._anthropic_output = int(ot)
        elif etype == "message_stop":
            self._was_complete = True

    def finalize(self) -> ParsedUsage:
        """Return the captured ParsedUsage. No more feed() calls after this."""
        # Phase 29 hotfix — when no ``data: `` lines were ever observed,
        # the upstream returned a non-streaming single JSON body (e.g.
        # nanobot's openai_compat_provider posts ``stream=false`` to
        # OpenRouter / OpenAI; or any future Anthropic non-streaming
        # ``POST /v1/messages`` call). aiter_raw() yielded the body as
        # one or more chunks; ``_raw_body`` accumulated all of them.
        # Parse it as a single JSON object and dispatch to the
        # provider-specific dict-mode helper.
        if not self._saw_sse_line and self._raw_body:
            try:
                body = json.loads(bytes(self._raw_body))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Either malformed JSON OR upstream returned non-UTF-8
                # bytes (e.g. gzip-magic 1f 8b — defensive: the proxy
                # forces Accept-Encoding: identity outbound, but if
                # upstream ignores that we must NOT crash here).
                body = None
            if isinstance(body, dict):
                if self._sse_format == "anthropic":
                    return _parse_anthropic_native(body)
                if self._sse_format == "openai":
                    parsed = _parse_openai_compat(body, self._provider)
                    # Map legacy ``unknown`` (bot stripped usage) to Phase
                    # 29 widened-enum ``failed`` per D-15 — the proxy's
                    # cost-capture path should treat both as the same
                    # signal: capture failed, no tokens recorded.
                    if parsed.status == "unknown":
                        parsed = replace(parsed, status="failed")
                    return parsed
        if self._sse_format == "openai":
            usage = self._final_usage
            if usage is None:
                # Nothing to report — failed capture (no usage AND/OR
                # incomplete stream).
                return ParsedUsage(
                    upstream_request_id=self._upstream_request_id,
                    status="failed",
                )
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            if cache_read == 0:
                details = usage.get("prompt_tokens_details") or {}
                if isinstance(details, dict):
                    cache_read = int(details.get("cached_tokens") or 0)
            cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
            return ParsedUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_creation,
                upstream_request_id=self._upstream_request_id,
                status="success" if self._was_complete else "failed",
            )
        if self._sse_format == "anthropic":
            return ParsedUsage(
                input_tokens=self._anthropic_input,
                output_tokens=self._anthropic_output,
                cache_read_tokens=self._anthropic_cache_read,
                cache_creation_tokens=self._anthropic_cache_creation,
                upstream_request_id=self._upstream_request_id,
                status="success" if self._was_complete else "failed",
            )
        return ParsedUsage(status="failed")


__all__ = ["StreamUsageParser"]
