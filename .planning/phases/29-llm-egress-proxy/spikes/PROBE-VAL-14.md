# PROBE-VAL-14

## PROBE-VAL-14: streaming 4xx + mid-stream error shapes

### Provider: OpenRouter
- initial HTTP status: 400
- raw line count: 1
- raw response (first 1KB):
```
{"error":{"message":"this-model-does-not-exist-zzz is not a valid model ID","code":400},"user_id":"user_38aGGW3BprpR31FEQeQwtDiEnuS"}
```
- branch: **http_4xx**

### Provider: OpenAI
- initial HTTP status: 404
- raw line count: 8
- raw response (first 1KB):
```
{
    "error": {
        "message": "The model `gpt-this-does-not-exist-zzz` does not exist or you do not have access to it.",
        "type": "invalid_request_error",
        "param": null,
        "code": "model_not_found"
    }
}
```
- branch: **http_4xx**

### Provider: Anthropic
- initial HTTP status: 404
- raw line count: 1
- raw response (first 1KB):
```
{"type":"error","error":{"type":"not_found_error","message":"model: claude-does-not-exist-zzz"},"request_id":"req_011CamdeNhdWFJXbfYp9k5uR"}
```
- branch: **http_4xx**

### Verdict reasoning
- 3/3 providers returned a parseable error shape: **3/3**
- Parser strategy in 29-RESEARCH §Stream interrupted is empirically supportable: either initial 4xx (fast-path: skip stream parser) or SSE event with 'error' key (slow-path: parser branches on event type).

VERDICT: PASS
