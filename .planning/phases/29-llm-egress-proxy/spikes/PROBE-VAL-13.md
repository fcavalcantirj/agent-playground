# PROBE-VAL-13

## PROBE-VAL-13: Anthropic SSE — output_tokens is cumulative

- model: `claude-haiku-4-5`
- prompt: 'List 12 different fruits. For each fruit, write one sentence describing its taste, then a second sentence describing where it grows. Number them 1-12.'
- max_tokens: 600

### message_start.message.usage
```json
{
  "input_tokens": 41,
  "cache_creation_input_tokens": 0,
  "cache_read_input_tokens": 0,
  "cache_creation": {
    "ephemeral_5m_input_tokens": 0,
    "ephemeral_1h_input_tokens": 0
  },
  "output_tokens": 1,
  "service_tier": "standard",
  "inference_geo": "not_available"
}
```

### message_delta.usage events (full list)
```json
[
  {
    "input_tokens": 41,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "output_tokens": 600
  }
]
```

### output_tokens sequence (in order of emission)
- count: 1
- values: [600]

### Raw SSE (first 4KB)
```
event: message_start
data: {"type":"message_start","message":{"model":"claude-haiku-4-5-20251001","id":"msg_01UmHuUbjMReFq8wLxp1jJGx","type":"message","role":"assistant","content":[],"stop_reason":null,"stop_sequence":null,"stop_details":null,"usage":{"input_tokens":41,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":0},"output_tokens":1,"service_tier":"standard","inference_geo":"not_available"}}              }

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}           }

event: ping
data: {"type": "ping"}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"#"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" 12 Fruits: Taste and Origin\n\n1. **Apple** - Apples have"}           }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" a crisp, sweet-to-tart flavor that varies by variety, from the sweet"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ness of Gala to the tartness of Granny Smith. They grow in temperate regions worldwide, with major"}        }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" production in China, the United States, and Europe.\n\n2. **Banana** - Bananas offer a creamy, mild sweetness with a soft texture"}       }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" that becomes more pronounced as they ripen. They thrive in tropical and subtropical climates, particularly in countries like India, China"}     }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":", and the Philippines.\n\n3. **Mango** - Mangoes have a rich, juicy sweetness with subtle fl"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"oral notes and a smooth texture often described as buttery. They grow in warm tropical regions, with India, China, and Thailand"}             }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" being the largest producers.\n\n4. **Strawberry** - Strawberries deliver a bright, fresh sweetness with a slightly tart undertone and a ju"} }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"icy texture. They are cultivated in temperate climates worldwide, with major production in China, the United States, and Mexico.\n\n5. **Blueberry** - Blueber"}            }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ries have a sweet-tart flavor with subtle earthy notes and a delicate, slightly firm texture. They grow in coo"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ler climates, particularly in North America, Northern Europe, and parts of Asia.\n\n6. **Orange** - Oranges provide a refreshing cit"}  }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"rus sweetness with a bright acidity and juicy flesh. They grow in subtropical and tropical regions, with major cultivation in Brazil, China, and Florida.\n\n7"}   }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":". **Pineapple** - Pineapples offer a tropical sweetness with a tangy acidity and a firm, fib"}               }

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"rous texture. They are grown in tropical regions, particularly in Costa Rica, the Philippines, and Brazil.\n
```

### Verdict reasoning
- message_start.usage.input_tokens > 0: **True**
- message_start.usage carries cache_*_input_tokens fields: **True**
- at least one message_delta event observed: **True** (observed count: 1)
- output_tokens monotonic non-decreasing: **True**

### Cumulative-not-delta empirical evidence
- message_start.usage.output_tokens = 1 (nonzero -> NOT delta-mode)
- last message_delta.usage.output_tokens = 600 (full message total)
- summing would yield 601 (double-counts by 1 — proves cumulative-not-delta)
- cumulative-not-delta empirically confirmed (AMD-07): **True**

### Surprise — protocol shape vs research assumption
- 29-RESEARCH.md §Streaming Capture Strategy assumed multiple `message_delta` events (one per content_block_stop). Empirical reality (2026-05-06): claude-haiku-4-5 emits **exactly one `message_delta`** at the end of the message, with `usage.output_tokens` carrying the full cumulative total. The parser spec (last-wins overwrite) still works correctly under this protocol — the 'last' delta IS the only delta — but the **spike-acceptance criterion** baked into the plan ('≥2 message_delta events') was wrong about the protocol shape.

### Proposed AMD-08+ amendment (deviation surfaced for human review)
- 29-RESEARCH.md §Streaming Capture Strategy currently shows multi-`message_delta` examples implying ≥2 events per response. Update the doc to clarify: Anthropic emits **exactly one `message_delta`** per `message_stop`, with `usage.output_tokens` carrying the full cumulative total. The parser spec in 29-PATTERNS.md is unaffected (last-wins still picks the only delta), but the doc should accurately describe protocol shape.
- Cumulative-not-delta is still empirically confirmed via the message_start.output_tokens=1 vs message_delta.output_tokens=N comparison: summing would double-count by `start_output`.

### Parser implication (29-PATTERNS.md StreamUsageParser, lines 410-465)
- The parser MUST use `self._anthropic_output = int(u.get('output_tokens') or self._anthropic_output)` (last-wins overwrite), NOT `+= int(...)` (sum). The empirical sequence above proves this directly: the LAST (and in practice ONLY) message_delta value IS the canonical total; summing message_start.output_tokens + message_delta.output_tokens would overcount by 1.

VERDICT: PASS
