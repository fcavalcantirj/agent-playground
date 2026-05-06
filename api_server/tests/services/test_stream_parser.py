"""Phase 29 Plan 04 Task 2 — pure-function tests for StreamUsageParser.

Covers:

  Test 1  — OpenAI final-chunk last-wins on usage
  Test 2  — OpenAI post-DONE-edge: usage chunk arrives AFTER [DONE]
  Test 3  — OpenAI no usage → failed status
  Test 4  — Anthropic message_start captures input + cache fields
  Test 5  — AMD-07 CANONICAL: 3 message_delta events with output_tokens=5,12,17
            → finalize().output_tokens == 17 (NOT 34). Load-bearing test.
  Test 6  — Anthropic upstream_request_id from message_start.message.id
  Test 7  — Anthropic message_stop sets was_complete (success vs failed)
  Test 8  — chunked-byte boundary: line split across two feed() calls
  Test 9  — malformed JSON skipped silently
  Test 10 — Anthropic explicit zero-cache-hit case (input=42, cache_read=0,
            cache_creation=0, output=23)

No PG, no Docker, no upstream — pure-function unit tests.
"""
from __future__ import annotations

import json

from api_server.services.stream_parser import StreamUsageParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse_chunk(payload: dict | str) -> bytes:
    """Wrap a JSON dict (or a raw sentinel like ``"[DONE]"``) as an SSE line."""
    if isinstance(payload, str):
        return f"data: {payload}\n".encode()
    return f"data: {json.dumps(payload)}\n".encode()


# ===========================================================================
# OpenAI / OpenRouter format
# ===========================================================================


def test_openai_final_chunk_last_wins() -> None:
    """3 chunks; only the last carries usage. finalize captures it."""
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(_sse_chunk({"id": "gen-x", "choices": [{"delta": {"content": "hi"}}]}))
    parser.feed(_sse_chunk({"id": "gen-x", "choices": [{"delta": {"content": "!"}}]}))
    parser.feed(_sse_chunk({
        "id": "gen-x",
        "choices": [],
        "usage": {"prompt_tokens": 42, "completion_tokens": 17},
    }))
    parser.feed(_sse_chunk("[DONE]"))

    out = parser.finalize()
    assert out.input_tokens == 42
    assert out.output_tokens == 17
    assert out.upstream_request_id == "gen-x"
    assert out.status == "success"


def test_openai_post_done_edge_captures_trailing_usage() -> None:
    """OpenRouter quirk: usage chunk arrives AFTER [DONE]. Pitfall 2.

    The parser MUST NOT break on [DONE] — it sets the completion flag
    and continues scanning so a trailing usage chunk is captured.
    """
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(_sse_chunk({"id": "gen-y", "choices": [{"delta": {"content": "hi"}}]}))
    parser.feed(_sse_chunk("[DONE]"))
    # Usage arrives AFTER [DONE].
    parser.feed(_sse_chunk({
        "id": "gen-y",
        "choices": [],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }))

    out = parser.finalize()
    assert out.input_tokens == 11
    assert out.output_tokens == 22
    assert out.status == "success"


def test_openai_no_usage_marks_failed() -> None:
    """No usage chunk + no [DONE] → status='failed'."""
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(_sse_chunk({"id": "gen-z", "choices": [{"delta": {"content": "hi"}}]}))
    parser.feed(_sse_chunk({"id": "gen-z", "choices": [{"delta": {"content": "!"}}]}))

    out = parser.finalize()
    assert out.input_tokens == 0
    assert out.output_tokens == 0
    assert out.status == "failed"


# ===========================================================================
# Anthropic native format
# ===========================================================================


def test_anthropic_message_start_captures_input_and_cache_fields() -> None:
    """message_start usage block has FINAL input + cache fields."""
    parser = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    parser.feed(_sse_chunk({
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "usage": {
                "input_tokens": 42,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 5,
                "output_tokens": 1,
            },
        },
    }))

    out = parser.finalize()
    assert out.input_tokens == 42
    assert out.cache_creation_tokens == 100
    assert out.cache_read_tokens == 5


def test_anthropic_message_delta_last_wins_on_output_tokens_amd07() -> None:
    """AMD-07 canonical: 3 message_delta events with output_tokens=5, 12, 17.

    The CUMULATIVE-not-delta property of Anthropic's
    ``message_delta.usage.output_tokens`` means the parser must
    OVERWRITE on each delta, never sum. langchain-js #10249 and
    agno-agi #6537 both shipped 30-50% over-count bugs by += here.

    Final value MUST be 17 (NOT 5+12+17=34). This is the Phase 29
    invariant the cumulative-bug reading group sees.
    """
    parser = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    parser.feed(_sse_chunk({
        "type": "message_start",
        "message": {
            "id": "msg_amd07",
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
    }))
    parser.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 5}}))
    parser.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 12}}))
    parser.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 17}}))
    parser.feed(_sse_chunk({"type": "message_stop"}))

    out = parser.finalize()
    # 5, 12, 17 → MUST be 17, NOT 34. Last-wins overwrite, NEVER sum.
    assert out.output_tokens == 17, (
        f"AMD-07 invariant broken: expected last-wins=17, got {out.output_tokens}. "
        "If this is 34, the parser is summing instead of overwriting (cumulative bug)."
    )
    assert out.input_tokens == 10
    assert out.status == "success"


def test_anthropic_upstream_request_id_from_message_start() -> None:
    """``message.id`` becomes ``upstream_request_id`` for the usage row."""
    parser = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    parser.feed(_sse_chunk({
        "type": "message_start",
        "message": {"id": "msg_abc", "usage": {"input_tokens": 1, "output_tokens": 1}},
    }))
    parser.feed(_sse_chunk({"type": "message_stop"}))

    out = parser.finalize()
    assert out.upstream_request_id == "msg_abc"


def test_anthropic_was_complete_via_message_stop() -> None:
    """No message_stop → status='failed'; with stop → status='success'."""
    # Without message_stop.
    p1 = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    p1.feed(_sse_chunk({
        "type": "message_start",
        "message": {"id": "m1", "usage": {"input_tokens": 1, "output_tokens": 1}},
    }))
    p1.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 5}}))
    out1 = p1.finalize()
    assert out1.status == "failed", "no message_stop → must be failed"

    # With message_stop.
    p2 = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    p2.feed(_sse_chunk({
        "type": "message_start",
        "message": {"id": "m2", "usage": {"input_tokens": 1, "output_tokens": 1}},
    }))
    p2.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 5}}))
    p2.feed(_sse_chunk({"type": "message_stop"}))
    out2 = p2.finalize()
    assert out2.status == "success"
    assert out2.output_tokens == 5


# ===========================================================================
# Cross-cutting parser invariants
# ===========================================================================


def test_chunked_byte_boundary_reassembles_lines() -> None:
    """A ``data: {...}\\n`` line split across two feed() calls is parsed."""
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    full = json.dumps({
        "id": "gen-split",
        "choices": [],
        "usage": {"prompt_tokens": 7, "completion_tokens": 8},
    })
    raw = f"data: {full}\n".encode()
    # Split mid-payload — first half no \n, second half completes the line.
    cut = len(raw) // 2
    parser.feed(raw[:cut])
    out_mid = parser.finalize()
    # Mid-stream finalize sees nothing yet; defensive — output_tokens=0.
    assert out_mid.output_tokens == 0
    # Now feed the rest. (In real life finalize is called once at end;
    # this test re-uses the parser only to prove the byte-boundary
    # buffering — see fresh_parser below for the canonical case.)
    fresh_parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    fresh_parser.feed(raw[:cut])
    fresh_parser.feed(raw[cut:])
    fresh_parser.feed(_sse_chunk("[DONE]"))
    out = fresh_parser.finalize()
    assert out.input_tokens == 7
    assert out.output_tokens == 8


def test_malformed_json_silently_skipped() -> None:
    """``data: notjson\\n`` does not raise; finalize reports no usage."""
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(b"data: notjson\n")
    parser.feed(b"data: {still bad\n")
    parser.feed(_sse_chunk({
        "id": "gen-after-bad",
        "choices": [],
        "usage": {"prompt_tokens": 9, "completion_tokens": 10},
    }))
    parser.feed(_sse_chunk("[DONE]"))

    out = parser.finalize()
    # Bad lines did not abort the parse; trailing usage chunk captured.
    assert out.input_tokens == 9
    assert out.output_tokens == 10
    assert out.status == "success"


def test_anthropic_explicit_no_cache_hit_case() -> None:
    """input=42, cache_read=0, cache_creation=0, final output=23."""
    parser = StreamUsageParser(provider="anthropic", sse_format="anthropic")
    parser.feed(_sse_chunk({
        "type": "message_start",
        "message": {
            "id": "msg_no_cache",
            "usage": {
                "input_tokens": 42,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 1,
            },
        },
    }))
    parser.feed(_sse_chunk({"type": "message_delta", "usage": {"output_tokens": 23}}))
    parser.feed(_sse_chunk({"type": "message_stop"}))

    out = parser.finalize()
    assert out.input_tokens == 42
    assert out.cache_read_tokens == 0
    assert out.cache_creation_tokens == 0
    assert out.output_tokens == 23
    assert out.status == "success"
