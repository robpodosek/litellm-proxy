# Phase 1 real-provider smoke test

Phase 1 proves one stable logical model (`free-frontier`) against one configured physical
route. The default example uses Google Gemini through LiteLLM.

This is a manual smoke test. It is intentionally separate from the deterministic unit tests
so normal test runs never consume provider quota.

## 1. Create local configuration

```bash
cp free-frontier.toml.example free-frontier.toml
cp .env.example .env
```

`free-frontier.toml` is local runtime configuration and should not contain API keys.

The example route currently uses:

```toml
model = "gemini/gemini-3.6-flash"
```

Before relying on it for strict zero-cost use, verify the model is still eligible for the
provider's free tier and verify your Google project/account billing configuration. Provider
model availability and billing rules can change independently of Free Frontier.

## 2. Set your provider credential

Put your Google AI Studio API key in `.env`:

```dotenv
GEMINI_API_KEY=your-key-here
```

Free Frontier loads the credential from the environment. The key value is not stored in the
TOML route definition and should never appear in normal logs or API responses.

## 3. Start Free Frontier

```bash
uv sync
uv run free-frontier
```

Expected listener:

```text
http://127.0.0.1:4000
```

## 4. Confirm the logical model

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

The model list should expose `free-frontier`, not the configured physical route name.

## 5. Send a non-streaming completion

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [
      {"role": "user", "content": "Reply with exactly: FREE FRONTIER PHASE 1 OK"}
    ],
    "stream": false
  }' | python -m json.tool
```

Success criteria:

- HTTP 200
- response is OpenAI chat-completion shaped
- response `model` is `free-frontier`
- client request never names the physical provider/model
- provider API key never appears in the response

## Phase boundary

Phase 1 has exactly one route. A rate limit or provider failure therefore returns an upstream
error. Automatic fallback and cooldowns are Phase 2.

Streaming is intentionally rejected in Phase 1 and is implemented in Phase 3.

## Reference documentation

The sample route was checked against current documentation when Phase 1 was built:

- LiteLLM: https://docs.litellm.ai/ and the LiteLLM project configuration examples
- Gemini model catalog: https://ai.google.dev/gemini-api/docs/models
- Gemini pricing/free tier: https://ai.google.dev/gemini-api/docs/pricing
- Gemini billing tiers: https://ai.google.dev/gemini-api/docs/billing

Always re-check these before relying on a provider/model as free because upstream offerings can change.
