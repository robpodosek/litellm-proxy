# Free Frontier

**One endpoint. Free models. FrFr.**

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

## Project constitution

Free Frontier follows a deliberately strict architectural rule: **keep the core small, boring,
and focused on one job.** Install FrFr, add provider keys, point a client at it, and forget it
exists.

No speculative infrastructure belongs in the default runtime. Databases, sidecars, queues, UI
stacks, plugin systems, and new abstractions must solve a concrete current problem and beat a
simpler alternative before they are admitted. Monitoring data belongs in the core; dashboards,
VS Code extensions, and other presentation layers belong in separate projects that consume the
core APIs.

See [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) for the durable architectural rules.

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

## Capability-aware routing

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
Routes can also declare incompatible capability combinations. For example, a route may support
structured output and tools individually while rejecting a request that combines both. Unknown
support is treated conservatively.

### Streaming fallback boundary

For streaming requests, Free Frontier may transparently fall back **before the first upstream
chunk is emitted**.

Once the first chunk has committed the response to a physical route, Free Frontier never
splices the remainder of the answer from another model. A post-commit upstream stream failure
terminates that stream instead of mixing model outputs.

## Phase 4: headless observability

Free Frontier exposes read-only machine-readable status without requiring a terminal UI:

```text
GET /health
GET /status
GET /routes
```

`/health` reports process readiness and uptime.

`/status` reports aggregate request/fallback counters, the last selected route, and route-state
summaries.

`/routes` reports safe per-route details including priority, provider/model identity, declared
capabilities, current cooldown state, current eligibility, attempts, selections, successes,
failures, skips, recent failure status, and average observed latency.

These endpoints are intentionally read-only. They do not participate in route ordering,
eligibility, cooldowns, or fallback decisions. They also omit credential values and credential
environment-variable names.

Example:

```bash
curl -s http://127.0.0.1:4000/health | python -m json.tool
curl -s http://127.0.0.1:4000/status | python -m json.tool
curl -s http://127.0.0.1:4000/routes | python -m json.tool
```

A future dashboard or VS Code extension can consume these interfaces without becoming part of
the routing core.


## Phase 5 hardening

Real-client integration adds a few compatibility guarantees:

- every HTTP response includes an `X-Request-ID` correlation ID
- routing logs include that same request ID across attempts, skips, failures, and fallbacks
- final `503 all_routes_unavailable` responses include `Retry-After` when a known cooldown can
  tell the client when the next compatible free route may become eligible
- known top-level provider diagnostic fields are removed when safe, while metadata that may be required for tool/reasoning compatibility is preserved
- `GET /v1/models/{model}` supports OpenAI-compatible model-detail discovery

Some clients probe unrelated backend APIs such as Ollama endpoints while auto-detecting a
server. Free Frontier intentionally returns `404` for APIs it does not implement instead of
pretending to be another backend.

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
capabilities = ["streaming", "tools", "structured_output"]
incompatible_capability_combinations = [
  ["structured_output", "streaming"],
  ["structured_output", "tools"],
]

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

Retrieve one logical model:

```bash
curl -s http://127.0.0.1:4000/v1/models/free-frontier | python -m json.tool
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
filtering, and pre-stream fallback smoke tests. See
[`docs/PHASE4-SMOKE.md`](docs/PHASE4-SMOKE.md) for status, cooldown, and fallback-observability
smoke tests.

## Real clients

Phase 5 hardens the stable proxy contract against real consumers. The client-facing setup stays:

```text
Base URL: http://127.0.0.1:4000/v1
Model:    free-frontier
```

Integration guides:

- [`docs/integrations/HERMES.md`](docs/integrations/HERMES.md)
- [`docs/integrations/CLINE.md`](docs/integrations/CLINE.md)

Provider credentials remain in Free Frontier. A client that requires a non-empty API-key field
for an OpenAI-compatible endpoint may use a non-secret local placeholder while Free Frontier is
bound to loopback. Do not copy upstream provider keys into clients.

## Docker

Phase 5 restores container packaging around the new application entrypoint. Prepare `.env` and
`free-frontier.toml` exactly as for local development, then run:

```bash
docker compose build
docker compose up -d
```

The compose file publishes the proxy only on host loopback by default:

```text
127.0.0.1:4000 -> container:4000
```

Check it with:

```bash
curl -s http://127.0.0.1:4000/health | python -m json.tool
docker compose ps
```

Stop it with:

```bash
docker compose down
```

`.env` and the local `free-frontier.toml` are runtime inputs and are excluded from the image
build context. See [`docs/PHASE5-SMOKE.md`](docs/PHASE5-SMOKE.md) and
[`docs/RELEASE-CHECKLIST.md`](docs/RELEASE-CHECKLIST.md).

## Current provider notes

The checked-in sample routes are documented in [`docs/PROVIDERS.md`](docs/PROVIDERS.md). Provider
availability and free-tier terms can change, so re-check the upstream sources before releases.

## Development

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git --no-pager diff --check
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
