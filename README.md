# Free Frontier

**One endpoint. Multiple free LLM providers. Automatic fallback. No paid inference without explicit opt-in.**

Free Frontier is a local, OpenAI-compatible model proxy that gives AI clients one stable
endpoint while transparently routing requests across the free-tier provider/model routes you
configure.

Clients only need to know:

```text
Base URL: http://localhost:4000/v1
Model:    free-frontier
```

Hermes, Cline, Continue, Open WebUI, custom applications, and other OpenAI-compatible clients
sit above Free Frontier. They do not need to select the physical provider/model themselves.

## What Free Frontier owns

Free Frontier owns:

- logical-model resolution
- ordered free-only route selection
- rate-limit/service-failure fallback
- cooldown and automatic re-eligibility
- request capability detection
- capability-aware route filtering
- pre-stream fallback
- provider normalization through LiteLLM

The caller keeps requesting `free-frontier` throughout.

## You provide the API keys

Free Frontier does **not** provide third-party API access. You supply API keys for the
providers whose free tiers you want to use.

You do not have to configure every provider. Disabled routes do not require credentials.
Enabled free routes that declare an API-key environment variable require that credential at
startup.

Provider credentials stay behind Free Frontier. Clients only need the Free Frontier endpoint.

## Zero-cost policy

v0.1 is **free-only by design**.

> If all eligible free routes are unavailable or incompatible, Free Frontier fails instead of knowingly selecting paid inference.

A route with `free = false` is never selected by the v0.1 router.

### Important account-level billing caveat

Free Frontier controls which routes it selects. It cannot override the billing policy attached
to a provider account or API key you supply. If an upstream account automatically converts
free-tier exhaustion into billable usage, the upstream provider may still charge that account.

For strict zero-cost operation, configure provider accounts/projects so paid overages are
disabled or otherwise impossible where the provider supports that option.

## Phase 3: agent-compatible routing

Phase 3 adds capability-aware routing and OpenAI-compatible streaming/tool behavior on top of
Phase 2 fallback and cooldowns.

Each route explicitly declares capabilities such as:

```toml
capabilities = ["streaming", "tools", "structured_output"]
```

Free Frontier infers requirements from each request. For example:

- `stream = true` requires `streaming`
- `tools`, `tool_choice`, legacy `functions`, or `function_call` require `tools`
- JSON/JSON-schema `response_format` requires `structured_output`
- OpenAI-style image content requires `vision`

A route missing any required capability is skipped before an upstream request is attempted.
Unknown support is treated conservatively.

### Streaming fallback boundary

For streaming requests, Free Frontier may transparently fall back **before the first upstream
chunk is emitted**.

Once the first chunk has committed the response to a physical route, Free Frontier never
splices the remainder of the answer from another model. A post-commit upstream stream failure
terminates that stream instead of mixing model outputs.

## Setup

```bash
git clone https://github.com/robpodosek/free-frontier.git
cd free-frontier
uv sync
cp free-frontier.toml.example free-frontier.toml
cp .env.example .env
```

The checked-in example starts with Gemini enabled and Groq present but disabled:

```toml
[routes."gemini-flash"]
provider = "gemini"
model = "gemini/gemini-3.6-flash"
enabled = true
free = true
api_key_env = "GEMINI_API_KEY"
capabilities = ["streaming", "tools", "structured_output"]

[routes."groq-gpt-oss"]
provider = "groq"
model = "groq/openai/gpt-oss-120b"
enabled = false
free = true
api_key_env = "GROQ_API_KEY"
capabilities = ["streaming", "tools"]

[logical_models."free-frontier"]
routes = ["gemini-flash", "groq-gpt-oss"]
```

Provider capabilities, model availability, rate limits, and free-tier terms can change. Keep
route metadata aligned with current provider behavior and your own account billing settings.

## Run

```bash
uv run free-frontier
```

Default listener:

```text
http://127.0.0.1:4000
```

List logical models:

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

Non-streaming completion:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Say hello from Free Frontier."}],
    "stream": false
  }' | python -m json.tool
```

Streaming completion:

```bash
curl -N http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Count from one to five."}],
    "stream": true
  }'
```

See [`docs/PHASE3-SMOKE.md`](docs/PHASE3-SMOKE.md) for streaming, tool-calling, capability
filtering, and pre-stream fallback smoke tests.

## Development

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git diff --check
```

The deterministic test suite uses fake transports and consumes no provider quota.

## Architecture and roadmap

- [`docs/SPEC-v0.1.md`](docs/SPEC-v0.1.md) is the normative product contract.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) defines component boundaries.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) defines implementation phases and acceptance gates.
- [`AGENTS.md`](AGENTS.md) defines instructions for coding agents modifying this repository.

## Repository

Canonical repository: https://github.com/robpodosek/free-frontier

## License

MIT. See [`LICENSE`](LICENSE).
