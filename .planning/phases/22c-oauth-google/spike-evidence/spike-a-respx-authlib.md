# Spike A — respx x authlib 1.6.11 interop

**Run date:** 2026-04-19T23:09:37Z
**Command:** `docker exec deploy-api_server-1 sh -c "cd /tmp && python -m pytest spikes/test_respx_authlib.py -x -v"`
**Result:** **PASS** (after Rule 3 deviation on respx pin — see below)

## Rationale

RESEARCH §Open Question 5 flagged that historical versions of authlib + respx + httpx had an interop bug (respx issue #46 through authlib 0.15.0). Modern versions (authlib 1.6.11 + respx 0.21 + httpx 0.27) were EXPECTED to work but had not been empirically verified in this repo. Per golden rule 5, spike it before downstream plans commit to the pattern.

## Version pins verified

- authlib: **1.6.11**
- respx: **0.23.1** (upgraded from the RESEARCH-pinned 0.21 — see deviation below)
- httpx: **0.28.1** (transitively pulled in by authlib 1.6.11)
- itsdangerous: **2.2.0**
- python: 3.11.15
- pytest: 9.0.3
- pytest-asyncio: 1.3.0
- respx-pytest plugin: 0.23.1

## Deviation — Rule 3 (blocking issue): respx pin bumped from `>=0.21,<0.22` to `>=0.22,<0.24`

**Discovery:** The spike ran twice.

**First run (respx 0.21.1 — the RESEARCH-specified pin):** FAILED with
```
respx.models.AllMockedAssertionError: RESPX: <Request(b'POST', 'https://oauth2.googleapis.com/token')> not mocked!
```
The route was registered in the router (`router.routes` showed the correct `POST /token` pattern); respx's `amock` interceptor fired (trace showed `respx/mocks.py:190` in the call chain); but `resolver()` returned `route=None` and therefore `AllMockedAssertionError`. The same failure reproduced with BOTH `@respx.mock` decorator AND `async with respx.mock():` context-manager styles, and with BOTH a bare `httpx.AsyncClient.post(...)` AND authlib's `oauth.google.fetch_access_token(...)` — i.e. the root cause was respx 0.21 vs httpx 0.28, not authlib.

**Root cause:** respx 0.21 was released against an earlier httpx; httpx 0.28 changed internal request-object shape enough that respx 0.21's matcher can see the route but cannot match it. respx 0.22+ fixed this (respx 0.22.0 was the compatibility bump for httpx 0.28).

**Fix:** Bumped the pin in `api_server/pyproject.toml` to `respx>=0.22,<0.24` and upgraded the container-installed version to respx 0.23.1 (current latest).

**Re-run:** PASS, as shown below.

## Test output (captured)

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python
cachedir: .pytest_cache
rootdir: /tmp
plugins: asyncio-1.3.0, respx-0.23.1, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

spikes/test_respx_authlib.py::test_respx_intercepts_authlib_token_exchange PASSED [100%]

============================== 1 passed in 0.07s ===============================
```

## What the test proved

1. `respx.post("https://oauth2.googleapis.com/token").mock(...)` correctly intercepts the httpx POST that authlib's `StarletteOAuth2App.fetch_access_token(redirect_uri=..., code=...)` makes internally (via `authlib.integrations.httpx_client.AsyncOAuth2Client`).
2. `token_route.called` is True after the call; `token_route.call_count == 1`.
3. authlib parses the canned JSON payload (`access_token`, `token_type`, `expires_in`, `scope`) into a Python dict without dispatching any real network request.
4. No DNS / outbound traffic escapes — `@respx.mock` is configured with `assert_all_mocked=True` by default and would raise on any unmatched request.

## Decision

- **PASS → AMD-05 stands.** All downstream OAuth integration tests MUST use `@respx.mock` (or `async with respx.mock():`) to stub Google's `oauth2.googleapis.com/token` + `openidconnect.googleapis.com/v1/userinfo` and GitHub's `github.com/login/oauth/access_token` + `api.github.com/user` + `api.github.com/user/emails`.
- The respx pin in `api_server/pyproject.toml` is now `>=0.22,<0.24` (bumped from the RESEARCH-specified `>=0.21,<0.22`). Downstream plans (especially 22c-05 which authors the full OAuth route integration tests) should cite this evidence file if the pin is questioned.
- Wave 0 Spike A hard gate: CLEARED.

## Execution note

The running `deploy-api_server-1` container has `/app/api_server/` baked into the image (no bind-mount for source), so the spike test file was `docker cp`'d into `/tmp/spikes/` inside the container and run from there with `cd /tmp && python -m pytest spikes/test_respx_authlib.py`. The authoritative copy of the test lives at `api_server/tests/spikes/test_respx_authlib.py` on the host filesystem; downstream waves that rebuild the image will bake it into `/app/api_server/tests/spikes/`.
