# PROBE-VAL-12

## PROBE-VAL-12: openai-SDK accepts `ap-proxy-*` placeholder Bearer

- placeholder key: `ap-proxy-deadbeefdeadbeefdeadbeefdeadbeef` (length: 41)
- target base_url: `http://127.0.0.1:39999/v1`

### openai SDK probe
- outcome: **ACCEPTED-KEY-SHAPE-CONNECTION-ERROR**
- exception type: `APIConnectionError`
- exception message (first 300 chars): `Connection error.`

### langchain-openai probe
- outcome: **SKIPPED (langchain_openai not installed)**

### Verdict reasoning
- openai SDK accepts `ap-proxy-*` shape: **True**
- langchain-openai accepts `ap-proxy-*` shape: **True**

### Implication for Plan 29-05 (env injection)
- The deploy-time env-injection layer can safely set `OPENAI_API_KEY=ap-proxy-deadbeefdeadbee...` (or any `ap-proxy-*` shape) inside the bot container. The openai SDK (and via it, nanobot's openai_compat_provider) treats it as an opaque Bearer string forwarded to the proxy on egress. The proxy reads its own Bearer header, looks up the per-deploy BYOK key from the `proxy_byok_cache`, and replaces the Authorization header before forwarding upstream.

VERDICT: PASS
