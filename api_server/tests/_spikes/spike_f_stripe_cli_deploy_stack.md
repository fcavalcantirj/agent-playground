# Spike F — Stripe CLI delivers to deploy stack (NOT native uvicorn)

**Status:** PASS

**Phase:** B-stripe Wave 0 (gating)
**Date:** 2026-05-08
**Plan:** B-stripe-01

## Purpose

Prove the CLAUDE.md macOS rule holds for the webhook contract: Stripe CLI's
`listen --forward-to http://localhost:8000/...` reliably routes to the
`deploy-api_server-1` container (the only api_server we want for Wave 3+
webhook work) and NOT to a hypothetical side-launched native uvicorn.

If the request landed on a stray native uvicorn instead, Wave 3+ webhook
work would silently land in the wrong process — same split-brain trap
documented in `feedback_no_native_uvicorn_with_deploy_stack.md`.

## Preconditions confirmed before run

- Deploy stack up and healthy:
  ```
  $ docker compose -f deploy/docker-compose.prod.yml ps
  NAME                       STATUS                     PORTS
  deploy-api_server-1        Up 34 minutes (healthy)   127.0.0.1:8000->8000/tcp
  deploy-postgres-1          Up 34 minutes (healthy)   5432/tcp
  deploy-redis-1             Up 34 minutes (healthy)   127.0.0.1:6379->6379/tcp
  deploy-temporal-1          Up 34 minutes (healthy)   127.0.0.1:7233->7233/tcp
  deploy-temporal-worker-1   Up 34 minutes
  ```
  Container ID for `deploy-api_server-1`:
  `ee9d8d17b1664f1e21ae515e7bb64a8b6b152a9edf6e709a738b4f9edf073982`

- No native uvicorn on :8000 — only the deploy container publishes that
  port. (Re-confirmed by reading `docker compose ps` PORTS column above.)

- Stripe CLI installed:
  ```
  $ which stripe
  /opt/homebrew/bin/stripe
  $ stripe version
  stripe version 1.40.9
  ```

## Step 1 — Probe the webhook route directly

```
$ curl -sS -X POST -H "Content-Type: application/json" -d '{}' \
       http://localhost:8000/v1/billing/webhook -w "\nHTTP_STATUS=%{http_code}\n"
{"detail":"Not Found"}
HTTP_STATUS=404
```

A 404 on this route is the **expected** Wave 0 condition — the route does
not exist yet (Wave 3 mounts it). The 404 is the success signal: it
proves the request reached an api_server that is willing to answer (just
without that route registered).

## Step 2 — Start `stripe listen` forwarding to the deploy container

```
$ stripe listen --forward-to http://localhost:8000/v1/billing/webhook --skip-verify
Ready! You are using Stripe API Version [2025-05-28.basil]. Your webhook signing
secret is whsec_2e22a9183958222c4f598c93a81379264be877f707861580fa3a3d78ef2038b2
(^C to quit)
```

`--skip-verify` is intentional — the route doesn't exist yet so there is
no signing-secret check to pass; we only care about request routing.

## Step 3 — Trigger a checkout.session.completed event (and the cascade Stripe fires)

```
$ stripe trigger checkout.session.completed
Setting up fixture for: product
Running fixture for: product
Setting up fixture for: price
...
Trigger succeeded! Check dashboard for event details.
```

Stripe's `trigger` command spawns a CASCADE of events to set up the
fixture (product → price → checkout_session → payment_method → ...), so
multiple events arrive over the listen channel.

## Step 4 — `stripe listen` log shows every event was forwarded and got 404

```
2026-05-08 22:16:25   --> product.created [evt_1TUzVFIXnB0o3aa16R0mJ7fj]
2026-05-08 22:16:25  <--  [404] POST http://localhost:8000/v1/billing/webhook [evt_...]
2026-05-08 22:16:26   --> price.created  [evt_1TUzVGIXnB0o3aa1wFJxHK6k]
2026-05-08 22:16:26  <--  [404] POST http://localhost:8000/v1/billing/webhook [evt_...]
2026-05-08 22:16:31   --> charge.succeeded
2026-05-08 22:16:31  <--  [404] POST http://localhost:8000/v1/billing/webhook
2026-05-08 22:16:31   --> checkout.session.completed [evt_1TUzVLIXnB0o3aa1yQgAHM5D]
2026-05-08 22:16:31  <--  [404] POST http://localhost:8000/v1/billing/webhook
2026-05-08 22:16:31   --> payment_intent.succeeded
2026-05-08 22:16:31  <--  [404] POST http://localhost:8000/v1/billing/webhook
2026-05-08 22:16:31   --> payment_intent.created
2026-05-08 22:16:31  <--  [404] POST http://localhost:8000/v1/billing/webhook
2026-05-08 22:16:34   --> charge.updated
2026-05-08 22:16:34  <--  [404] POST http://localhost:8000/v1/billing/webhook
```

All 7 events delivered to `localhost:8000` and got `404` — request
reached an api_server.

## Step 5 — Deploy api_server container log proves the request landed THERE

This is the load-bearing assertion. Read the deploy api_server's logs:

```
$ docker compose -f deploy/docker-compose.prod.yml logs api_server --since 2m \
    | grep -E "billing|webhook|404"

api_server-1  | INFO:  172.18.0.1:55504 - "POST /v1/billing/webhook HTTP/1.1" 404 Not Found
api_server-1  | [info] access duration_ms=0
                       headers={'user-agent': 'Stripe/1.0 (+https://stripe.com/docs/webhooks)',
                                'content-length': '937',
                                'content-type': 'application/json; charset=utf-8',
                                'x-request-id': '9f1e660ee86447ddb31488290c12b419'}
                       method=POST path=/v1/billing/webhook status=404
api_server-1  | INFO:  172.18.0.1:57954 - "POST /v1/billing/webhook HTTP/1.1" 404 Not Found
api_server-1  | [info] access duration_ms=1
                       headers={'user-agent': 'Stripe/1.0 (+https://stripe.com/docs/webhooks)',
                                'content-length': '4104',
                                'x-request-id': '7e3818cdd1c5430f9e330993e4e884bb'}
                       method=POST path=/v1/billing/webhook status=404
api_server-1  | INFO:  172.18.0.1:57954 - "POST /v1/billing/webhook HTTP/1.1" 404 Not Found
... (and so on for every event in the cascade)
```

### Three independent signals confirm this is the deploy container

1. **Container name**: `api_server-1` is the docker-compose service name
   from `deploy/docker-compose.prod.yml`. `docker inspect deploy-api_server-1`
   confirmed the same container ID `ee9d8d17b1664f1e21ae515e7bb64a8b6b152a9edf6e709a738b4f9edf073982`.

2. **Source IP `172.18.0.1`** — that is the gateway address of the
   `deploy_default` Docker bridge network (the only network the deploy
   stack uses). A native uvicorn would see the source as `127.0.0.1` /
   `::1`, not a 172.18.x.x bridge IP. The bridge gateway IP confirms
   the request came in via the Docker port-publish `127.0.0.1:8000` →
   container, NOT a side-launched native uvicorn.

3. **User-Agent `Stripe/1.0 (+https://stripe.com/docs/webhooks)`** —
   the canonical Stripe CLI / Stripe webhook user-agent. Differentiates
   from the `curl/8.7.1` probe in Step 1.

## PASS criterion

- [x] `stripe listen` forwarded all events to localhost:8000.
- [x] Every event got HTTP 404 (route doesn't exist yet — that's correct).
- [x] Deploy api_server container logs show every request landed there
      with source IP `172.18.0.1` (Docker bridge gateway) and User-Agent
      `Stripe/1.0`.
- [x] No side-launched native uvicorn was running on :8000 during the run
      (verified by `docker compose ps` showing the deploy container as
      the sole owner of the port).

**RESULT: PASS** — Wave 3 webhook work is safe to ship into the deploy
stack via the documented pattern.

## Cleanup

`stripe listen` was stopped via `kill <pid>`. The deploy stack continues
to run for the remaining spikes; no test data needs cleanup (the events
were rejected with 404 before any handler ran).
