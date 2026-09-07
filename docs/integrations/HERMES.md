# Hermes Agent integration

Verified against current Hermes Agent documentation on 2026-09-06.

Free Frontier should look like one custom OpenAI-compatible model to Hermes. Hermes should not
contain Gemini/Groq provider fallback logic when Free Frontier is being tested as the model
router; Free Frontier owns that layer.

## Prerequisites

Start Free Frontier first:

```bash
uv run free-frontier
```

Verify the logical model is visible:

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

The model list should contain `free-frontier`.

## Interactive configuration

Run:

```bash
hermes model
```

Choose the custom OpenAI-compatible endpoint flow and use:

```text
API base URL: http://127.0.0.1:4000/v1
API key:      leave blank if Hermes allows it; otherwise use a local placeholder
Model name:   free-frontier
Context:      131072
```

`131072` is the conservative common context size for the current sample route pool because
Groq GPT-OSS 120B is documented at 131,072 tokens. If the enabled route set changes, use a
context size that every eligible route can safely satisfy until Free Frontier gains
context-window-aware routing.

## Direct config

The equivalent `~/.hermes/config.yaml` model block is:

```yaml
model:
  default: free-frontier
  provider: custom
  base_url: http://127.0.0.1:4000/v1
  context_length: 131072
```

Free Frontier does not require a client API key while bound to loopback in v0.1. If Hermes
requires a non-empty key for a custom endpoint, use a non-secret placeholder such as
`free-frontier-local`. Do not put provider credentials such as `GEMINI_API_KEY` or
`GROQ_API_KEY` into Hermes.

## Smoke test

Run a one-shot query:

```bash
hermes chat --oneshot -q "Reply with exactly: HERMES FREE FRONTIER OK"
```

Then inspect Free Frontier:

```bash
curl -s http://127.0.0.1:4000/status | python -m json.tool
curl -s http://127.0.0.1:4000/routes | python -m json.tool
```

Hermes should continue to know only `free-frontier`; `/status` and `/routes` may reveal the
physical route for observability.

## Tool-call smoke test

Hermes requires a large context window for tool use. With the custom model configured above,
run:

```bash
hermes chat --oneshot --toolsets terminal -q \
  "Use the terminal tool to run pwd once, then report only the resulting path."
```

A successful run proves that Hermes can execute its normal agent loop while the model traffic
passes through Free Frontier's OpenAI-compatible tool-call path.

## Transparent fallback test

To prove the abstraction rather than Hermes' own fallback feature:

1. Make sure Hermes has no separate fallback provider configured for this test.
2. Temporarily make the first Free Frontier route fail in `free-frontier.toml`.
3. Keep a second free route enabled and valid.
4. Restart Free Frontier.
5. Run the same Hermes one-shot query.
6. Confirm the query succeeds without changing Hermes configuration.
7. Confirm `/status` reports `fallbacks` increased and `last_selected_route` is the fallback.
8. Restore the real first route and restart Free Frontier.

Hermes configuration must remain:

```text
base URL: http://127.0.0.1:4000/v1
model:    free-frontier
```

## Current Hermes references

- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md
