# Free Frontier

**One endpoint. Multiple free LLM providers. Automatic fallback. No paid inference without explicit opt-in.**

Free Frontier is a local, OpenAI-compatible model proxy that gives AI clients one stable
endpoint while transparently routing requests across the free-tier model providers you
configure.

The client should only need to know:

```text
Base URL: http://localhost:4000/v1
Model:    free-frontier
```

Hermes, Cline, Continue, Open WebUI, custom applications, and other OpenAI-compatible clients
can sit above Free Frontier. They do not need to know which provider or physical model
actually serves a request.

```text
Hermes / Cline / other client
            │
            ▼
     ┌───────────────┐
     │ Free Frontier │
     │               │
     │ free-frontier │
     └───────┬───────┘
             │
      routing + fallback
             │
      ┌──────┼──────┬──────────┐
      ▼      ▼      ▼          ▼
   Provider Provider Provider  Local
      A        B       C       model
```

## What Free Frontier does

Free Frontier owns the model-selection details that would otherwise leak into every client
configuration:

- which provider/model is preferred
- which configured routes are currently healthy
- which routes are rate-limited or cooling down
- which fallback should be tried next
- whether a route can satisfy the request's capabilities
- how provider-specific APIs are normalized
- whether a route is eligible under the configured cost policy

The calling application keeps using the logical model name `free-frontier` throughout.

## You provide the API keys

Free Frontier does **not** provide third-party API access. You provide API keys for the
providers whose free tiers you want to use.

You do not have to configure every supported provider. Configuring more eligible providers
will give Free Frontier a larger fallback pool as multi-route routing is implemented.

Provider credentials stay on the Free Frontier side. The client talks only to Free Frontier.

## What happens when a free-tier limit is reached?

The v0.1 target behavior is automatic free-tier fallback. Assume a configured preference
order of Provider A, then B, then C. If A reaches a free-tier inference limit, Free Frontier
will eventually cool that route down and transparently try the next eligible free route.
When the cooldown expires, the preferred route becomes eligible again.

The client still requests:

```text
model = free-frontier
```

It does not change providers, models, credentials, or configuration.

**Current implementation note:** Phase 1 intentionally has one physical route. Automatic
fallback/cooldown behavior is implemented in Phase 2.

## Zero-cost policy

For v0.1, Free Frontier is **free-only by design**.

> If all eligible free routes are unavailable, Free Frontier fails instead of knowingly selecting paid inference.

Free Frontier must never silently convert a free-routing failure into a paid request.

### Important account-level billing caveat

Free Frontier controls the routes it selects. It cannot override the billing policy attached
to an API account you provide.

If you supply a key for an account or project configured to automatically bill after a free
allowance is exhausted, the upstream provider may charge that account even though Free
Frontier intended to use a free-tier route.

If you want a strict zero-cost setup, configure each provider account/project so paid
overages are disabled or otherwise impossible, where the provider supports that option.

The Free Frontier guarantee is:

> **Free Frontier will not knowingly route a request to paid inference in v0.1.**

It is not a guarantee against billing settings controlled by an upstream provider account.

## Phase 1: runnable single-route proxy

Phase 1 implements the first runnable slice of the v0.1 architecture:

```text
OpenAI-compatible client
        │
        │ model = free-frontier
        ▼
   Free Frontier
        │
        ▼
one configured free physical route
        │
        ▼
normalized response
```

Implemented now:

- typed TOML configuration
- startup validation
- free-only validation for the active route
- provider credentials loaded from environment variables
- LiteLLM Python SDK as the provider-normalization transport
- `GET /v1/models`
- non-streaming `POST /v1/chat/completions`
- physical provider/model identity hidden behind `free-frontier`
- deterministic fake-transport tests that consume no real API quota

Not implemented yet:

- multiple routes / fallback / cooldowns (Phase 2)
- capability-aware selection, streaming, and tools (Phase 3)
- status/observability API (Phase 4)
- Hermes/Cline hardening and packaging (Phase 5)

## Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/robpodosek/free-frontier.git
cd free-frontier
uv sync
```

Create your local runtime files:

```bash
cp free-frontier.toml.example free-frontier.toml
cp .env.example .env
```

Add the API key for the configured route to `.env`.

The example Phase 1 route uses Gemini through LiteLLM:

```toml
[routes."gemini-flash"]
provider = "gemini"
model = "gemini/gemini-3.6-flash"
enabled = true
free = true
api_key_env = "GEMINI_API_KEY"

[logical_models."free-frontier"]
routes = ["gemini-flash"]
```

Provider models and free-tier terms can change. Verify the currently configured route against
the provider's current documentation and your own account billing settings.

## Run

```bash
uv run free-frontier
```

The default listener is:

```text
http://127.0.0.1:4000
```

List the public logical models:

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

Send a Phase 1 non-streaming request:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Say hello from Free Frontier."}],
    "stream": false
  }' | python -m json.tool
```

The client requests only `free-frontier`. The configured physical model is an internal route.

See [`docs/PHASE1-SMOKE.md`](docs/PHASE1-SMOKE.md) for the real-provider acceptance smoke test.

## Development

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
```

Normal automated tests use fake transports and do not consume provider quota.

## Architecture and roadmap

- [`docs/SPEC-v0.1.md`](docs/SPEC-v0.1.md) is the normative product contract.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) defines component boundaries.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) defines implementation phases and acceptance gates.
- [`AGENTS.md`](AGENTS.md) defines instructions for coding agents modifying this repository.

## Repository

Canonical repository: https://github.com/robpodosek/free-frontier

## License

MIT. See [`LICENSE`](LICENSE).
