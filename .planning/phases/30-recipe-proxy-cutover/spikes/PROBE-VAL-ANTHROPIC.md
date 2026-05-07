# PROBE-VAL-ANTHROPIC

## PROBE-VAL-ANTHROPIC: Anthropic SSE through proxy

- model: `claude-haiku-4-5`
- max_tokens: 50
- BYOK key: `<REDACTED-AN-KEY>`
- transport: httpx ASGITransport → in-process FastAPI app
- upstream: real api.anthropic.com (no respx — this is the spike)

### (1) cost_weights pre-check
- input_per_1m_usd: 1.000000 | output_per_1m_usd: 5.000000 | ap_multiplier: 1.0000

### (2) DB fixtures seeded
- user_id: `5794686f-0cb5-4111-8c13-8c6a29ebeb40`
- agent_instance_id: `f9afc8ad-ea23-42c1-86e1-b06dd6d482d3`
- bridge_ip: `172.18.0.42`
- agent_containers.upstream_provider: `anthropic`
- agent_containers.provider_key_enc: 64 bytes (non-NULL)

### (3) Real-money POST through proxy
- URL: `/v1/llm/forward/v1/messages` (proxy rewrites to `https://api.anthropic.com/v1/messages`)
- request body: `{"model": "claude-haiku-4-5", "max_tokens": 50, "stream": true, "messages": [{"role": "user", "content": "Reply with exactly: ok-30-01"}]}`

- proxy response status: 200

### (4) usage_logs row
```json
{
  "status": "success",
  "input_tokens": "16",
  "output_tokens": "8",
  "cost_usd": "0.00005600",
  "provider": "anthropic",
  "model": "claude-haiku-4-5",
  "upstream_request_id": "req_011CanP5hXRKVAH6pjWkkq5g",
  "status_code": "200"
}
```

### (5) AMD-07 + Pitfall 1 invariants
- output_tokens=8 (< 50 — cumulative last-wins applied)
- cost_weights computation: (16 * 1.000000 + 8 * 5.000000) / 1M * 1.0000 = 0.0000560000
- usage_logs.cost_usd: 0.00005600
- delta: 0E-10

### (6) BYOK custody (D-12)
- agent_containers.upstream_provider: `anthropic`
- agent_containers.provider_key_enc IS NOT NULL: `True`


VERDICT: PASS
