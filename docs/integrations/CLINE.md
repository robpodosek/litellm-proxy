# Cline integration

Verified against current Cline OpenAI Compatible provider documentation on 2026-09-06.

## Prerequisites

Start Free Frontier:

```bash
uv run free-frontier
```

Verify:

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

## VS Code configuration

Open Cline settings and use:

```text
API Provider: OpenAI Compatible
Base URL:     http://127.0.0.1:4000/v1
API Key:      free-frontier-local
Model ID:     free-frontier
```

`free-frontier-local` is only a placeholder for Cline's required API-key field. Free Frontier
v0.1 does not authenticate loopback clients and ignores the bearer value. Never paste Gemini,
Groq, NVIDIA, or OpenRouter provider credentials into Cline when Cline is using Free Frontier.

Recommended conservative model metadata for the current sample route pool:

```text
Context Window:    131072
Max Output Tokens: 32768
Image Support:     off
```

Cline exposes advanced model configuration fields for OpenAI-compatible providers. Keep image
support disabled until every route intended for vision requests is explicitly configured with
Free Frontier's `vision` capability.

## Verify

Use Cline's Verify action if available. Then give Cline a small task in a disposable or clean
repository, for example:

```text
Read README.md and tell me the project title. Do not modify files.
```

Free Frontier should show inference traffic while Cline remains configured only with
`free-frontier`.

For a tool-heavy smoke test, ask Cline to inspect a file and run a harmless project command.
The client should complete its normal tool loop while Free Frontier handles model tool calls.

## Transparent fallback test

1. Leave Cline configured with the same Base URL and Model ID.
2. Temporarily make Free Frontier's first physical route fail.
3. Keep the second free route valid and enabled.
4. Restart Free Frontier.
5. Repeat the same Cline task.
6. Confirm Cline succeeds without a provider/model change.
7. Inspect `/status` and `/routes` to verify the physical fallback.
8. Restore the first route afterward.

The client configuration must not change during the test.

## Current Cline reference

- https://docs.cline.bot/provider-config/openai-compatible
- https://github.com/cline/cline/blob/main/docs/provider-config/openai-compatible.mdx
