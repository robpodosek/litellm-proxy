# Verified provider notes

Provider/model availability, free-tier terms, rate limits, and capabilities change over time.
This file records the v0.1 sample routes that were checked against provider documentation on
2026-09-06. Re-check these sources when changing routes or preparing a release.

## Google Gemini 3.6 Flash

Free Frontier route:

```toml
[routes."gemini-flash"]
provider = "gemini"
model = "gemini/gemini-3.6-flash"
enabled = true
free = true
api_key_env = "GEMINI_API_KEY"
capabilities = ["streaming", "tools", "structured_output"]
```

Google's Gemini Developer API pricing page currently lists `gemini-3.6-flash` with free-tier
input and output pricing as free of charge. Google's deprecation page currently lists Gemini
3.6 Flash with no announced shutdown date.

Free Frontier also live-smoke-tested non-streaming completions, streaming, and function/tool
calling through this route on 2026-09-06.

Sources:

- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/deprecations

## Groq GPT-OSS 120B

Free Frontier route:

```toml
[routes."groq-gpt-oss"]
provider = "groq"
model = "groq/openai/gpt-oss-120b"
enabled = false
free = true
api_key_env = "GROQ_API_KEY"
capabilities = ["streaming", "tools", "structured_output"]
incompatible_capability_combinations = [
  ["structured_output", "streaming"],
  ["structured_output", "tools"],
]
```

Groq's Free Plan limits currently include `openai/gpt-oss-120b` at 30 requests/minute,
1,000 requests/day, 8,000 tokens/minute, and 200,000 tokens/day. Groq documents tool use,
JSON Object Mode, and JSON Schema Mode for the model.

Free Frontier declares structured output as an individual capability but explicitly blocks
known unsupported combinations with streaming and tool use. Free Frontier live-smoke-tested
normal completion, streaming fallback, and tool-call handling through this route on 2026-09-06.

Sources:

- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/model/openai/gpt-oss-120b

## Billing warning

A provider being available on a free plan does not let Free Frontier override the billing
settings of the API account attached to a key. For strict zero-cost operation, configure the
upstream account so paid overages or automatic paid conversion are disabled where possible.

Free Frontier's v0.1 invariant is narrower and enforceable: it never knowingly selects a route
whose own configuration has `free = false`.
