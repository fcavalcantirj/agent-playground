# PROBE-VAL-01

## PROBE-VAL-01: OpenRouter inline usage chunk

- model: `anthropic/claude-haiku-4-5`
- max_tokens: 50
- BYOK key: `<REDACTED-OR-KEY>`

### Variant A — stream=true

- raw line count: 28
- usage chunk line index: 24
- [DONE] line index: 26

```json
{
  "prompt_tokens": 8,
  "completion_tokens": 24,
  "total_tokens": 32,
  "cost": 0.000128,
  "is_byok": false,
  "prompt_tokens_details": {
    "cached_tokens": 0,
    "cache_write_tokens": 0,
    "audio_tokens": 0,
    "video_tokens": 0
  },
  "cost_details": {
    "upstream_inference_cost": 0.000128,
    "upstream_inference_prompt_cost": 8e-06,
    "upstream_inference_completions_cost": 0.00012
  },
  "completion_tokens_details": {
    "reasoning_tokens": 0,
    "image_tokens": 0,
    "audio_tokens": 0
  }
}
```

#### Raw stream (first 4KB)
```
: OPENROUTER PROCESSING

: OPENROUTER PROCESSING

: OPENROUTER PROCESSING

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":"#","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":" Hey","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":" there! ","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":"👋\n\nHow","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":"'s","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":" it","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":" going? What can","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":" I help you with today?","role":"assistant"},"finish_reason":null,"native_finish_reason":null}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":"","role":"assistant"},"finish_reason":"stop","native_finish_reason":"end_turn"}]}

data: {"id":"gen-1778084973-hMXUx2DWmurqwHonRCcn","object":"chat.completion.chunk","created":1778084973,"model":"anthropic/claude-4.5-haiku-20251001","provider":"Amazon Bedrock","choices":[{"index":0,"delta":{"content":"","role":"assistant"},"finish_reason":"stop","native_finish_reason":"end_turn"}],"usage":{"prompt_tokens":8,"completion_tokens":24,"total_tokens":32,"cost":0.000128,"is_byok":false,"prompt_tokens_details":{"cached_tokens":0,"cache_write_tokens":0,"audio_tokens":0,"video_tokens":0},"cost_details":{"upstream_inference_cost":0.000128,"upstream_inference_prompt_cost":0.000008,"upstream_inference_completions_cost":0.00012},"completion_tokens_details":{"reasoning_tokens":0,"image_tokens":0,"audio_tokens":0}}}

data: [DONE]

```

- ordering: **usage BEFORE [DONE]**

### Variant B — stream=false

- HTTP status: 200
```json
{
  "id": "gen-1778084975-X3l4wuVCARmnQoFSgLL7",
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 24,
    "total_tokens": 32,
    "cost": 0.000128,
    "is_byok": false,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "cache_write_tokens": 0,
      "audio_tokens": 0,
      "video_tokens": 0
    },
    "cost_details": {
      "upstream_inference_cost": 0.000128,
      "upstream_inference_prompt_cost": 8e-06,
      "upstream_inference_completions_cost": 0.00012
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "image_tokens": 0,
      "audio_tokens": 0
    }
  }
}
```

### Verdict reasoning
- stream=true carries usage: **True**
- stream=false carries usage: **True**


VERDICT: PASS
