---
date: 2026-05-03
git_sha: a9f8393
phase: 25-mobile-screens
spike: sse-envelope-inspect
dedup_key: seq
verdict: PASS
---

# Phase 25 Wave 0 Spike B — SSE envelope inspection

Closes 25-RESEARCH.md Open Question #1 + Pitfall #9.

Empirically confirmed against the live local `api_server` running in
`deploy-api_server-1` (Docker stack at /healthz=ok, /readyz=ok,
schema_version=`ap.recipe/v0.1`, recipes_count=6) on 2026-05-03 by
hitting `GET /v1/agents/{agent_id}/messages/stream` with a real session
cookie and posting a fresh message via `POST /v1/agents/{agent_id}/messages`.

## SSE event sample (kind=inapp_outbound, replayed)

Captured verbatim from the live SSE stream (`tee /tmp/spike-b-25-01/sse.log`):

```
id: 1
event: inapp_outbound
data: {"seq": 1, "kind": "inapp_outbound", "payload": {"source": "agent", "content": "I'll check the current workspace and help you with a spike roundtrip...", "captured_at": "2026-05-03T00:20:35.165249+00:00"}, "correlation_id": null, "ts": "2026-05-03T00:20:35.165598+00:00"}

id: 2
event: inapp_outbound
data: {"seq": 2, "kind": "inapp_outbound", "payload": {"source": "agent", "content": "I'm ready to assist you. What would you like me to help with?", "captured_at": "2026-05-03T00:20:39.563582+00:00"}, "correlation_id": null, "ts": "2026-05-03T00:20:39.563968+00:00"}
```

## SSE event sample (kind=inapp_outbound, fresh live arrival)

After `POST /v1/agents/{agent_id}/messages` body `{"content":"phase 25 spike B"}`:

```
id: 3
event: inapp_outbound
data: {"seq": 3, "kind": "inapp_outbound", "payload": {"source": "agent", "content": "I see you've referenced \"phase 25 spike B\" from memory context...", "captured_at": "2026-05-03T15:59:46.470484+00:00"}, "correlation_id": null, "ts": "2026-05-03T15:59:46.470951+00:00"}
```

`POST /v1/agents/{agent_id}/messages` returned:

```json
{ "message_id": "6521b00e-0e09-4fc4-83de-0119329e3480",
  "status": "pending",
  "queued_at": "2026-05-03T15:59:42.654552+00:00" }
```

## Corresponding /v1/agents/{id}/messages history rows

```json
{ "role": "assistant",
  "kind": "message",
  "content": "I'll check the current workspace and help you with a spike roundtrip...",
  "created_at": "2026-05-03T00:20:26.417558+00:00",
  "inapp_message_id": "017373c2-c33e-44a5-b616-56695f0e16b5" }
```

## Decision

**`dedup_key: seq`** because the SSE outbound envelope on the wire
explicitly lacks `inapp_message_id`. The envelope is exactly:

```
{seq:int, kind:str, payload:{source, content, captured_at}, correlation_id:str|null, ts:str}
```

The history endpoint (`GET /v1/agents/{id}/messages`) DOES carry
`inapp_message_id` per row, so the chat screen will cross-reference
SSE arrivals → history rows via `seq` (the SSE identifier-of-record)
rather than a shared message UUID.

This realizes Pitfall #9 in 25-RESEARCH.md verbatim — the contingency
that was already flagged with mitigation. Wave 4 plan (25-07) MUST amend
D-36 from "dedup by inapp_message_id" to "dedup by seq" before sealing
the chat dedup Map.

## Side notes (not load-bearing for the verdict, but useful for Wave 4)

- The POST response `message_id` (e.g. `6521b00e-0e09-4fc4-83de-0119329e3480`)
  matches NEITHER the SSE `seq` NOR the history-row `inapp_message_id`.
  It appears to be an internal queue ID. Wave 4 should not rely on it
  for cross-correlation.
- History rows return user+assistant pairs sharing the SAME
  `inapp_message_id` (e.g. user "spike roundtrip" and assistant reply
  both carry `017373c2-c33e-44a5-b616-56695f0e16b5`). This is a
  backend interaction-pair model, not a message-level identifier.
  Wave 4 must NOT assume `inapp_message_id` is unique per message —
  prefer `(role, seq)` or `(role, created_at)` as the chat row key.
- `correlation_id` in the SSE envelope is `null` for outbound replies
  in this empirical sample. Don't depend on it for dedup.

## Repro

```bash
# Pre-req: deploy-api_server-1 healthy on localhost:8000, deploy-postgres-1 up
SESSION=57313217-0a8a-4059-a230-ebc1669b66f6   # active sessions row
AGENT=0059f03a-0191-4969-9821-c02855e4e7fb     # zeroclaw, container_status=running, channel=inapp

# Open SSE
curl -N -H "Cookie: ap_session=$SESSION" \
  "http://localhost:8000/v1/agents/$AGENT/messages/stream" | tee /tmp/spike-b-25-01/sse.log

# In second terminal, post message
curl -X POST -H "Cookie: ap_session=$SESSION" \
  -H "Idempotency-Key: $(uuidgen)" -H "Content-Type: application/json" \
  -d '{"content":"phase 25 spike B"}' \
  "http://localhost:8000/v1/agents/$AGENT/messages"

# Inspect history shape
curl -fsS -H "Cookie: ap_session=$SESSION" \
  "http://localhost:8000/v1/agents/$AGENT/messages?limit=5" | python3 -m json.tool
```

## Verdict rationale

The SSE envelope is sufficient to drive a correct chat dedup Map with
**`seq`** as the key — `seq` is monotonically increasing per
`agent_instance_id` (Phase 22c.3 D-09 / D-34 envelope guarantee) and
arrives on EVERY outbound event. No fallback heuristic needed. The
amended D-36 in 25-RESEARCH.md and 25-CONTEXT.md should read
"Map<int, ChatMessage> keyed by `seq`" rather than
"Map<String, ChatMessage> keyed by `inappMessageId`".
