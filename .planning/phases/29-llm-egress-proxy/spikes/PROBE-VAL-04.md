# PROBE-VAL-04

## PROBE-VAL-04: auth-header swap per provider

### Sub-probe (a) — OpenRouter /v1/key
- valid:   HTTP 200
- invalid: HTTP 401
```json
{"error":{"message":"Missing Authentication header","code":401}}
```

### Sub-probe (b) — Anthropic /v1/messages
- valid x-api-key + version: HTTP 200
- omit anthropic-version:    HTTP 400
  ```json
  {"type":"error","error":{"type":"invalid_request_error","message":"anthropic-version: header is required"},"request_id":"req_011Camde2yisBqPGigxyg9xK"}
  ```
- Bearer instead of x-api-key: HTTP 401
  ```json
  {"type":"error","error":{"type":"authentication_error","message":"Invalid bearer token"},"request_id":"req_011Camde44i4RqJ3LTivw6Ee"}
  ```

### Sub-probe (c) — OpenAI /v1/models
- valid:   HTTP 200
- invalid: HTTP 401
```json
{
  "error": {
    "message": "Incorrect API key provided: invalid. You can find your API key at https://platform.openai.com/account/api-keys.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_api_key"
  }
}
```

### Status code matrix
```json
{
  "or": {
    "valid": 200,
    "invalid": 401
  },
  "an": {
    "valid": 200,
    "no_version": 400,
    "bearer": 401
  },
  "oai": {
    "valid": 200,
    "invalid": 401
  }
}
```

### Verdict reasoning
- OpenRouter Bearer-auth shape OK: **True**
- Anthropic x-api-key+version shape OK: **True**
- OpenAI Bearer-auth shape OK: **True**

VERDICT: PASS
