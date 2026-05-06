# PROBE-VAL-11

## PROBE-VAL-11: OpenRouter /v1/key reliability

5 valid + 5 invalid calls, sequential.

- valid statuses: [200, 200, 200, 200, 200]
- invalid statuses: [401, 401, 401, 401, 401]

### data field shape
```json
{
  "label": "str",
  "is_management_key": "bool",
  "is_provisioning_key": "bool",
  "limit": "NoneType",
  "limit_reset": "NoneType",
  "limit_remaining": "NoneType",
  "include_byok_in_limit": "bool",
  "usage": "float",
  "usage_daily": "float",
  "usage_weekly": "float",
  "usage_monthly": "float",
  "byok_usage": "int",
  "byok_usage_daily": "int",
  "byok_usage_weekly": "int",
  "byok_usage_monthly": "int",
  "is_free_tier": "bool",
  "expires_at": "NoneType",
  "creator_user_id": "str",
  "rate_limit": "dict"
}
```

### Sample numeric fields (verbatim)
```json
{
  "usage": 4.05156104,
  "limit": null
}
```

- data.label present: True
- data.usage present: True

### Verdict reasoning
- 5/5 valid -> 200: **True**
- 5/5 invalid -> 401: **True**
- data.* shape captured: **True**

VERDICT: PASS
