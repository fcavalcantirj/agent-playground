# PROBE-VAL-02

## PROBE-VAL-02: OpenRouter X-Generation-Id presence

- model: `anthropic/claude-haiku-4-5`

### Variant A — nonstream + valid key
- HTTP status: 200
```json
{
  "x-generation-id": "gen-1778084978-4YvhEmABKojNLXzu3Dkl",
  "x-request-id": "",
  "openrouter-request-id": ""
}
```
- All response header keys:
```
access-control-allow-origin, access-control-expose-headers, cf-ray, connection, content-encoding, content-type, date, permissions-policy, referrer-policy, server, transfer-encoding, x-content-type-options, x-generation-id
```

### Variant B — stream=true + valid key
- HTTP status: 200
```json
{
  "x-generation-id": "gen-1778084979-Mx8utZxNydZ8KMty2Y4b",
  "x-request-id": "",
  "openrouter-request-id": ""
}
```
- All response header keys:
```
access-control-allow-origin, access-control-expose-headers, cache-control, cf-ray, connection, content-type, date, permissions-policy, referrer-policy, server, transfer-encoding, x-content-type-options, x-generation-id
```

### Variant C — nonstream + invalid key
- HTTP status: 401
```json
{
  "x-generation-id": "",
  "x-request-id": "",
  "openrouter-request-id": ""
}
```

### Header-name shape
- canonical id-header names observed: ['x-generation-id']
- regex-matchable shape: `[a-f0-9-]{20,40}` (uuid-like or short hex)

### Verdict reasoning
- success-nonstream has id: **True**
- success-stream has id: **True**
- invalid-key has id: False (informational; not a gate)

VERDICT: PASS
