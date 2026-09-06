# Phase 4 Smoke Tests

Phase 4 adds read-only observability. These tests use the same running proxy and provider routes
already proven in Phases 1 through 3.

## 1. Start Free Frontier

```bash
uv run free-frontier
```

## 2. Check initial status surfaces

```bash
curl -s http://127.0.0.1:4000/health | python -m json.tool
curl -s http://127.0.0.1:4000/status | python -m json.tool
curl -s http://127.0.0.1:4000/routes | python -m json.tool
```

Expected:

- `/health` returns `status`, `ready`, `version`, and `uptime_seconds`
- `/status` reports request counters and `last_selected_route`
- `/routes` reports route priority, provider/model, capabilities, cooldown state, eligibility,
  and metrics
- no credential values or credential environment-variable names appear

## 3. Record one successful request

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Reply with exactly: STATUS OK"}],
    "stream": false
  }' | python -m json.tool
```

Then inspect:

```bash
curl -s http://127.0.0.1:4000/status | python -m json.tool
curl -s http://127.0.0.1:4000/routes | python -m json.tool
```

Expected:

- request `total` and `successes` increment
- `last_selected_route` identifies the physical route selected internally
- the selected route shows an attempt, selection, and success
- its average observed latency is populated

## 4. Explain a real fallback

This requires two enabled real free routes. With Gemini first and Groq second, temporarily change
the Gemini physical model in local `free-frontier.toml` to a nonexistent model while leaving its
capabilities intact.

Restart Free Frontier, then send:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Reply with exactly: OBSERVABLE FALLBACK OK"}],
    "stream": false
  }' | python -m json.tool
```

Inspect status immediately:

```bash
curl -s http://127.0.0.1:4000/status | python -m json.tool
curl -s http://127.0.0.1:4000/routes | python -m json.tool
```

Expected:

- Gemini shows a recent route-unavailable failure
- Gemini is cooling down and `eligible_now` is false
- the aggregate fallback counter increments
- Groq is the `last_selected_route`
- Groq shows a successful attempt

Send the same completion again during the cooldown, then inspect `/routes` again. Gemini should
show a `cooldown` skip without another upstream attempt.

Restore the real Gemini model after this test.

## 5. Read-only invariant

Calling these endpoints repeatedly:

```bash
curl -s http://127.0.0.1:4000/health >/dev/null
curl -s http://127.0.0.1:4000/status >/dev/null
curl -s http://127.0.0.1:4000/routes >/dev/null
```

must not increment inference request totals or route attempts and must not change later route
selection.
