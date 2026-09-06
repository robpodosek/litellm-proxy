# Phase 3 Smoke Tests

These checks consume real provider quota. Run deterministic tests first:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git diff --check
```

Start Free Frontier in one terminal:

```bash
uv run free-frontier
```

All client requests below continue to use only:

```text
model = free-frontier
```

## 1. Streaming through the logical model

```bash
curl -N http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [
      {"role": "user", "content": "Reply with the words ONE TWO THREE, one word at a time."}
    ],
    "stream": true
  }'
```

Expected:

- HTTP 200
- `text/event-stream`
- multiple `data:` events
- streamed chunks report `"model":"free-frontier"`
- final event is `data: [DONE]`

## 2. Tool calling

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [
      {"role": "user", "content": "Use the get_weather tool for Seattle."}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get weather for a city.",
          "parameters": {
            "type": "object",
            "properties": {
              "city": {"type": "string"}
            },
            "required": ["city"]
          }
        }
      }
    ],
    "tool_choice": "required",
    "stream": false
  }' | python -m json.tool
```

Expected:

- HTTP 200
- response still reports `"model": "free-frontier"`
- assistant message contains OpenAI-compatible `tool_calls`
- the client never names the physical provider/model

## 3. Capability filtering

Temporarily remove `tools` from the preferred route's `capabilities` in
`free-frontier.toml`, while leaving a later enabled free route with `tools` support.

Repeat the tool request.

Expected server log shape:

```text
route=<preferred> event=skipped reason=capability missing=tools
route=<fallback> event=attempt mode=completion
route=<fallback> event=success mode=completion
```

The client should still receive a normal `free-frontier` response.

## 4. Streaming pre-commit fallback

Enable two routes with `streaming` capability. Temporarily make the preferred physical model
invalid, as in the Phase 2 stale-model fallback test.

Send the streaming request from test 1.

Expected server log shape:

```text
route=<preferred> event=attempt mode=stream
route=<preferred> event=failed ... fallback=true ...
route=<fallback> event=attempt mode=stream
route=<fallback> event=success mode=stream committed=true
```

The stream should come entirely from the fallback route while the client still sees
`free-frontier`.

Restore the preferred model immediately after the test.

## 5. No post-commit stream splicing

This behavior is covered deterministically in `tests/test_phase3_acceptance.py` rather than by
intentionally killing a real provider mid-response.

The invariant is:

> After the first upstream chunk commits a stream, Free Frontier never switches physical models for that response.
