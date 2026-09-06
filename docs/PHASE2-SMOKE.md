# Phase 2 smoke test

Phase 2's automated acceptance tests use fake upstreams so normal development does not consume
provider quota. This smoke test exercises a real two-provider fallback path.

## Prerequisites

You need API keys for two enabled free-tier routes. The checked-in example is prepared for:

- Gemini via `GEMINI_API_KEY`
- Groq via `GROQ_API_KEY`

Review each provider account's billing settings before testing. Free Frontier cannot override
account-level paid-overage settings.

## 1. Enable both routes

Copy the templates if you have not already:

```bash
cp free-frontier.toml.example free-frontier.toml
cp .env.example .env
```

Add both keys to `.env` and set the Groq route in `free-frontier.toml` to:

```toml
enabled = true
```

Keep the logical route order as:

```toml
[logical_models."free-frontier"]
routes = ["gemini-flash", "groq-gpt-oss"]
```

## 2. Prove the preferred route works

Start Free Frontier:

```bash
uv run free-frontier
```

In another terminal:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Reply exactly: PHASE 2 NORMAL OK"}],
    "stream": false
  }' | python -m json.tool
```

The response should remain branded as `model: free-frontier`.

## 3. Force a safe fallback

Stop Free Frontier and temporarily change only the preferred physical model in your local,
git-ignored `free-frontier.toml`:

```toml
[routes."gemini-flash"]
model = "gemini/definitely-not-a-real-model"
```

Do not change the public logical model or route order.

Restart Free Frontier and send:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Reply exactly: PHASE 2 FALLBACK OK"}],
    "stream": false
  }' | python -m json.tool
```

A successful response proves that the invalid preferred route failed and the second enabled
free route served the request without client reconfiguration.

## 4. Restore the preferred model

Restore:

```toml
model = "gemini/gemini-3.6-flash"
```

Restart the process after editing configuration. Phase 2 does not hot-reload configuration.

## Automated acceptance gate

Always run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git diff --check
```

The deterministic suite proves fallback, cooldown skipping, cooldown expiry, free-only
selection, invalid-reference rejection, and all-routes-unavailable behavior without relying
on live quota exhaustion.
