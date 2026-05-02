"""SPIKE D-31 (Wave 0 BLOCKING) — GZipMiddleware × SSE compatibility.

Configure ``GZipMiddleware(minimum_size=1024)`` on a tiny FastAPI app, fire a
streaming/SSE response through it, assert chunks are delivered as emitted
(un-buffered), NOT batched at end-of-stream.

PASS criterion: at the ASGI ``http.response.body`` event level, the SSE
route emits MULTIPLE separate body events with ``more_body=True`` between
them, and the first body event arrives well before the last (i.e. the
events are interleaved with the generator's ``await asyncio.sleep(0.1)``,
not collected to a single end-of-stream blob).

FAIL → switch to a content-type-exclude config explicitly listing
``text/event-stream`` and re-spike. Per Starlette ≥0.46.0 release notes
``text/event-stream`` is in ``DEFAULT_EXCLUDED_CONTENT_TYPES`` so this spike
is regression-prevention only — but D-31 forbids the phase from sealing
without empirical proof.

Why ASGI-event-level inspection (not httpx.ASGITransport stream timing):
``httpx.ASGITransport`` runs the ASGI app to completion and buffers the
full body before surfacing a single response to the caller, so chunk
timing observed via ``client.stream(...).aiter_bytes()`` is meaningless
(the test would always see one chunk at end-of-stream regardless of
whether the middleware was buffering). At the ASGI ``send`` callable
itself, however, every ``http.response.body`` event corresponds to one
yield from the underlying generator — exactly what uvicorn flushes to
the wire over a real socket. Recording the events at that boundary gives
us a faithful proxy for production streaming behavior.

The spike constructs its OWN minimal FastAPI app inline and does NOT import
``api_server.main``. This keeps the spike resilient to future changes in
production middleware order or router structure: the only thing under test
is Starlette's GZipMiddleware behavior over an SSE-shaped streaming body.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.gzip import GZipMiddleware


def _build_spike_app() -> FastAPI:
    """Return an inline FastAPI app with GZipMiddleware(minimum_size=1024)
    plus two routes: ``/sse`` (text/event-stream streaming body) and
    ``/json`` (application/json body well above the 1024-byte threshold)."""
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.get("/sse")
    async def sse():  # noqa: D401
        async def gen():
            # 5 chunks, 100ms apart, each padded so the cumulative body
            # comfortably exceeds 1024 bytes (each chunk ~310 bytes).
            for i in range(5):
                payload = f"data: chunk-{i}\n\n".encode() + (b"x" * 300) + b"\n"
                yield payload
                await asyncio.sleep(0.1)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/json")
    async def big_json():  # noqa: D401
        # ~2KB JSON body — comfortably above minimum_size=1024 so GZip
        # is engaged when the client advertises Accept-Encoding: gzip.
        return JSONResponse({"data": "y" * 2048})

    return app


async def _drive_asgi(
    app, path: str, headers: dict[str, str]
) -> tuple[dict, list[tuple[float, dict]]]:
    """Drive the ASGI ``app`` with a synthetic GET request and capture
    every ``send`` event with a wall-clock timestamp.

    Returns ``(start_event, events)`` where ``start_event`` is the
    ``http.response.start`` dict (status + headers) and ``events`` is a
    list of ``(elapsed_ms, event_dict)`` for each subsequent
    ``http.response.body`` event.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("test", 0),
        "server": ("test", 80),
    }

    request_queue: asyncio.Queue = asyncio.Queue()
    await request_queue.put({"type": "http.request", "body": b"", "more_body": False})

    start_event: dict = {}
    body_events: list[tuple[float, dict]] = []
    t0 = time.monotonic()

    async def receive():
        return await request_queue.get()

    async def send(message):
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        if message["type"] == "http.response.start":
            start_event.update(message)
        elif message["type"] == "http.response.body":
            body_events.append((elapsed_ms, message))

    await app(scope, receive, send)
    return start_event, body_events


@pytest.mark.asyncio
async def test_sse_chunks_arrive_unbatched_under_gzip_middleware():
    """Drive the SSE route at the ASGI protocol level and capture every
    ``http.response.body`` send event. The body must arrive in MULTIPLE
    events spaced by the generator's ``await asyncio.sleep(0.1)``, with
    the first body event landing well before the last — proving
    GZipMiddleware does NOT buffer text/event-stream to end-of-stream.
    """
    app = _build_spike_app()
    start_event, body_events = await _drive_asgi(
        app, "/sse", {"accept-encoding": "gzip"}
    )

    assert start_event.get("status") == 200, start_event

    # Decode response headers (list of (bytes, bytes) tuples) into a dict.
    response_headers = {
        k.decode().lower(): v.decode()
        for k, v in start_event.get("headers", [])
    }

    # CRITICAL: text/event-stream MUST NOT be gzipped. If this assertion
    # fails, GZipMiddleware is compressing SSE responses and the phase
    # needs to switch to a content-type-exclude config that explicitly
    # lists text/event-stream.
    content_encoding = response_headers.get("content-encoding")
    assert content_encoding != "gzip", (
        f"REGRESSION: text/event-stream IS being compressed "
        f"(content-encoding={content_encoding!r}). Switch to explicit "
        f"content-type-exclude config that lists text/event-stream."
    )

    assert response_headers.get("content-type", "").startswith(
        "text/event-stream"
    ), response_headers

    # Body events from the generator: 5 yields → 5 body events with
    # more_body=True, plus a final empty body event with more_body=False
    # (Starlette's StreamingResponse contract). GZip-buffering would
    # collapse these into a single event with the whole payload at
    # end-of-stream.
    body_only_events = [
        (t, e) for t, e in body_events if e.get("body", b"") != b""
    ]

    assert len(body_only_events) >= 2, (
        f"REGRESSION: GZipMiddleware appears to be buffering SSE chunks. "
        f"Expected >= 2 separate http.response.body events with payload, "
        f"got {len(body_only_events)}. All events: {body_events!r}"
    )

    first_body_ms = body_only_events[0][0]
    last_body_ms = body_only_events[-1][0]

    # The first body event should land WELL before the total stream
    # duration (5 * 100ms = ~500ms). 250ms is a generous bound that
    # still flags any end-of-stream batching regression.
    assert first_body_ms <= 250.0, (
        f"REGRESSION: first SSE body event arrived at {first_body_ms:.1f}ms "
        f"(threshold 250ms). Last body event at {last_body_ms:.1f}ms. "
        f"All body event timings: "
        f"{[round(t, 1) for t, _ in body_only_events]!r}. "
        f"GZipMiddleware appears to be buffering text/event-stream."
    )

    # Sanity: chunks really are spaced apart in time, not all flushed
    # at t=0 by some test-harness artifact.
    assert last_body_ms > first_body_ms, (
        f"all body events arrived at the same instant — likely a test "
        f"harness timing artifact, not real streaming. Timings: "
        f"{[round(t, 1) for t, _ in body_only_events]!r}"
    )


@pytest.mark.asyncio
async def test_non_sse_response_is_actually_gzipped():
    """Companion control: confirm GZipMiddleware DOES compress a non-SSE
    response when the body exceeds ``minimum_size`` and the client
    advertises ``Accept-Encoding: gzip``. This proves the middleware is
    actually engaged in this app and the SSE-no-gzip result above is
    NOT just because the middleware is silently a no-op.
    """
    app = _build_spike_app()
    start_event, _body_events = await _drive_asgi(
        app, "/json", {"accept-encoding": "gzip"}
    )

    assert start_event.get("status") == 200, start_event

    response_headers = {
        k.decode().lower(): v.decode()
        for k, v in start_event.get("headers", [])
    }

    assert response_headers.get("content-encoding") == "gzip", (
        f"GZipMiddleware did NOT compress a 2KB JSON response with "
        f"Accept-Encoding: gzip — middleware appears inert. "
        f"content-encoding={response_headers.get('content-encoding')!r}; "
        f"all response headers: {response_headers!r}"
    )
