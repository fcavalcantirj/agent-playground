"""Idempotency middleware (Plan 19-05).

Replaces the Plan 19-02 pass-through stub. Implements Stripe-style
idempotency for ``POST /v1/runs`` ONLY (CONTEXT.md §D-01 / §D-07):

- Request has no ``Idempotency-Key`` header → pass through.
- Cache hit (same ``(user_id, key)`` + same body hash, not expired)
  → replay the cached verdict verbatim, status 200, no downstream run.
- Cache mismatch (same ``(user_id, key)`` + different body hash)
  → 422 IDEMPOTENCY_BODY_MISMATCH (Pitfall 6). The client tried to
  reuse a key for a different payload, which is almost always a bug.
- Cache miss → pass through to the route handler, capture the
  response body, and (if the response is 200) write the verdict to
  ``idempotency_keys`` for future replay.

Cross-user isolation is enforced in the service layer: every query
filters on ``user_id`` and the advisory lock key mixes ``user_id`` in.
Phase 19 has a single anonymous user so this is proven by schema
invariants rather than runtime separation. Phase 21+ swaps
``ANONYMOUS_USER_ID`` for a session-resolved user id; no middleware
change needed.

**Fail-open on backend error:** a Postgres outage causes the
middleware to log and pass through (uncached) rather than fail the
request. A cached replay losing its cache is preferable to a site-wide
outage.

**Response caching safety:** we only cache status=200 responses. 4xx
and 5xx are transient (or legitimately reproducible) and caching them
would lock in an error state for 24 hours. This also avoids caching
the middleware's own 429/422 responses.

Class name + ``__init__`` signature unchanged from Plan 19-02 so
``main.py`` stays wired (Wave 3 file-ownership contract).
"""
from __future__ import annotations

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..constants import ANONYMOUS_USER_ID
from ..models.errors import ErrorCode, make_error_envelope
from ..services.idempotency import check_or_reserve, hash_body, write_idempotency

_log = logging.getLogger("api_server.idempotency")


def _get_header(scope: Scope, name_lower: bytes) -> bytes | None:
    """Return the first header value matching ``name_lower`` (bytes, lc)."""
    for n, v in scope.get("headers", []):
        if n == name_lower:
            return v
    return None


async def _read_body(receive: Receive) -> bytes:
    """Drain all ``http.request`` messages into one byte buffer.

    ASGI body is delivered chunked (``more_body=True`` until the final
    chunk). We must consume every chunk so the downstream handler can
    use a fresh ``receive`` callable that replays the captured bytes.
    Non-``http.request`` messages (e.g. ``http.disconnect``) are
    skipped; the disconnect case is handled by the downstream handler
    after we hand off.
    """
    chunks: list[bytes] = []
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            # http.disconnect or some transport-level event; we have no
            # body yet, stop draining and let the downstream path see it
            # through the replay receive's next call.
            continue
        if msg.get("body"):
            chunks.append(msg["body"])
        if not msg.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_receive(body: bytes) -> Receive:
    """Build a ``receive`` callable that serves ``body`` once then disconnects.

    After the single ``http.request`` message, further calls return
    ``http.disconnect`` — matches ASGI semantics when a client has
    finished sending the body.
    """
    sent = {"done": False}

    async def _receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return _receive


async def _send_json(send: Send, status: int, payload: dict) -> None:
    """Emit a single-shot JSON response via the ASGI ``send`` callable."""
    body = json.dumps(payload).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class IdempotencyMiddleware:
    """ASGI middleware implementing Stripe-style idempotency on ``POST /v1/runs``.

    Class name + signature match the Plan 19-02 stub exactly so the
    existing ``app.add_middleware(IdempotencyMiddleware)`` wiring in
    ``main.create_app()`` works unchanged.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        # Only applies to POST /v1/runs. Everything else (lifespan,
        # other routes, GET /v1/runs/{id}, OPTIONS, etc.) passes
        # through unmodified.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method")
        path = scope.get("path")
        if not (method == "POST" and path == "/v1/runs"):
            await self.app(scope, receive, send)
            return

        # Idempotency-Key header is optional. When absent, we pass
        # through and the endpoint runs exactly once per request with
        # no caching — the default Stripe semantic.
        key_bytes = _get_header(scope, b"idempotency-key")
        if key_bytes is None:
            await self.app(scope, receive, send)
            return
        key = key_bytes.decode(errors="ignore").strip()
        if not key:
            await self.app(scope, receive, send)
            return

        # Drain + hash the request body. The body hash uses raw bytes
        # (not re-serialized JSON) so semantically-equal payloads that
        # serialize differently still count as different requests —
        # matches Stripe's behavior and keeps the mismatch check sharp.
        body = await _read_body(receive)
        body_hash = hash_body(body)
        user_id = ANONYMOUS_USER_ID  # Phase 19 — Phase 21+ resolves real user

        app = scope["app"]
        try:
            async with app.state.db.acquire() as conn:
                tag, cached = await check_or_reserve(
                    conn, user_id, key, body_hash,
                )
        except Exception:
            # Fail-open: idempotency backend down → pass through
            # uncached. Better than 500-ing every /v1/runs request.
            _log.exception("idempotency backend error; failing open (not cached)")
            await self.app(scope, _replay_receive(body), send)
            return

        if tag == "hit":
            # Replay the cached verdict verbatim. HTTP 200 regardless
            # of whether the original run was a PASS or FAIL — the
            # failure semantics live in the body's `verdict` field.
            await _send_json(send, 200, cached or {})
            return

        if tag == "mismatch":
            # Same key + different body → client bug. 422 is the
            # canonical Stripe-style response (IDEMPOTENCY_BODY_MISMATCH).
            await _send_json(
                send,
                422,
                make_error_envelope(
                    ErrorCode.IDEMPOTENCY_BODY_MISMATCH,
                    "Idempotency-Key was used with a different request body",
                    param="Idempotency-Key",
                ),
            )
            return

        # Cache miss: run the endpoint normally, but wrap ``send`` so
        # we can capture the response body + status. After the handler
        # finishes, if status==200 we write the cache row. 4xx/5xx are
        # not cached (see module docstring).
        response_status = {"code": 0}
        response_body_chunks: list[bytes] = []

        async def send_wrapper(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                response_status["code"] = int(msg.get("status", 0))
            elif msg["type"] == "http.response.body" and msg.get("body"):
                response_body_chunks.append(msg["body"])
            await send(msg)

        await self.app(scope, _replay_receive(body), send_wrapper)

        if response_status["code"] == 200:
            try:
                resp_body = b"".join(response_body_chunks)
                verdict_json = json.loads(resp_body)
                # Only cache entries that correspond to a real run — the
                # route handler always includes ``run_id`` on success.
                # Without it the cache entry is useless for replay.
                run_id = verdict_json.get("run_id")
                if run_id:
                    async with app.state.db.acquire() as conn:
                        await write_idempotency(
                            conn, user_id, key, body_hash,
                            run_id, verdict_json,
                        )
            except Exception:
                # Non-fatal: the user's request already succeeded; a
                # failed cache-write just means the next retry will
                # re-run. Don't turn a 200 into an error.
                _log.exception("idempotency write failed (non-fatal)")
