# Spike 10 — `docker exec <container> openclaw pairing approve <code>` latency

**Date:** 2026-04-18
**Plan affected:** 22-05 (POST /v1/agents/:id/channels/:cid/pair)
**Verdict:** MAJOR GOTCHA CAUGHT — plan revision required

## Probe

```bash
t0=$(date +%s.%N)
docker exec ap-probe-openclaw openclaw pairing approve telegram FAKECODE123
t1=$(date +%s.%N)
```

## Actual result

**Wall time: 59.8 seconds** (!)
Exit code: non-zero (expected — FAKECODE123 isn't a pending request)

## Verdict: MAJOR GOTCHA

Plan 22-05 Task 4 (`POST /channels/:cid/pair`) assumed a ~2s call. Actual measured latency: **60s**. This is because `openclaw` CLI itself takes ~10-20s to cold-boot per invocation, and `pairing approve` subcommand goes through the full boot path — config load, plugin registry init, auth profiles read — even when invoked as `docker exec`.

## Impact on Plan 22-05

The API endpoint `POST /v1/agents/:id/channels/:cid/pair` will block for ~60s on openclaw. Implications:

1. **Client timeout:** frontend PairingModal must allow ≥90s timeout, not the default 30s most HTTP clients use.
2. **Rate limit:** the `pair` endpoint should have a **low** rate limit (e.g., 3 req/min) specifically because each call is heavyweight.
3. **Idempotency:** if the API call times out client-side, the openclaw CLI inside the container may STILL be running — future pair calls for the same code could race.
4. **UX:** the pairing modal MUST show a "this takes ~60s on openclaw" disclosure and a spinner, or users will assume it hung.

## Plan delta required

Plan 22-05 Task 4:
- Timeout for `docker exec` → 90s (not 30s).
- Return `{status: "processing", retry_after_s: 60}` if the exec is still in progress.
- Add a note: "openclaw's pairing CLI is heavyweight; other agents using this endpoint may be faster."

Plan 22-06 Task 2 (PairingModal):
- UX disclosure: "Approval takes up to 60 seconds for openclaw. Please wait."
- Client timeout ≥90s.
- Disable retry button until the first request returns.

## Spike value

Had the plan shipped with a 30s timeout on both client and server sides, every openclaw pair attempt would time out, leading to the dashboard showing stale "pairing pending" cards. Exact scenario Rule #5 prevents.
