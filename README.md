# Free Frontier

**One endpoint. Multiple free LLM providers. Automatic fallback. No paid inference without explicit opt-in.**

Free Frontier is a local, OpenAI-compatible model proxy that gives AI clients one stable
endpoint while transparently routing requests across the free-tier model providers you
configure.

Clients only need to know:

```text
Base URL: http://localhost:4000/v1
Model:    free-frontier
```

Hermes, Cline, Continue, Open WebUI, custom applications, and other OpenAI-compatible clients
sit above Free Frontier. They do not need to know which provider or physical model actually
serves a request.

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
      ┌──────┼──────┐
      ▼      ▼      ▼
   Route A Route B Route C
```

## What Free Frontier owns

Free Frontier owns the model-selection details that would otherwise leak into every client
configuration:

- which provider/model is preferred
- which configured routes are enabled and free-only eligible
- which routes are rate-limited or cooling down
- which fallback should be attempted next
- how provider-specific APIs are normalized

The caller keeps using `free-frontier` throughout.

## You provide the API keys

Free Frontier does **not** provide third-party API access. You provide API keys for the
providers whose free tiers you want to use.

You do not have to configure every supported provider. A route can remain disabled until you
have configured its credential. Enabled free routes that declare an API-key environment
variable must have that credential available at startup.

Provider credentials stay behind Free Frontier. The client does not need upstream provider
keys.

## What happens when a route hits a limit?

Phase 2 implements ordered free-only fallback and cooldowns.

Given:

```text
Route A
   ↓
Route B
   ↓
Route C
```

Free Frontier tries Route A first. If A fails with a fallback-worthy route failure such as a
rate limit or temporary upstream outage, Free Frontier:

1. places A into cooldown
2. attempts the next eligible free route
3. returns the successful response through the same `free-frontier` model
4. skips A on new requests while A is cooling down
5. automatically makes A eligible again after its cooldown expires

The caller never switches physical model names.

The router also treats an upstream model-not-found response as a route-unavailable failure so
a stale physical model can fall back instead of breaking the logical model immediately.

## Zero-cost policy

For v0.1, Free Frontier is **free-only by design**.

> If all eligible free routes are unavailable, Free Frontier fails instead of knowingly selecting paid inference.

A route with `free = false` is never selected by the v0.1 router even if it appears in a
logical model's ordered route list.

### Important account-level billing caveat

Free Frontier controls the routes it selects. It cannot override the billing policy attached
to an API account you provide.

If a provider account automatically bills after a free allowance is exhausted, the provider
may still charge that account. For strict zero-cost operation, configure provider accounts so
paid overages are disabled or otherwise impossible where supported.

The Free Frontier guarantee is:

> **Free Frontier will not knowingly route a request to paid inference in v0.1.**

## Phase 2: resilient free-only routing

Phase 2 currently implements:

- typed TOML configuration
- one public logical model: `free-frontier`
- multiple ordered physical routes
- explicit `enabled` and `free` route eligibility
- configurable global cooldown duration
- optional per-route cooldown duration
- rate-limit fallback
- fallback for selected temporary 5xx/timeout failures
- fallback for upstream model-not-found / route-unavailable failures
- provider `Retry-After` support when it extends the configured cooldown
- automatic cooldown expiry and route re-eligibility
- clean `503 all_routes_unavailable` behavior
- strict skipping of paid/ineligible routes
- LiteLLM as the provider-normalization transport
- non-streaming `POST /v1/chat/completions`
- `GET /v1/models`
- deterministic fake-upstream tests that consume no provider quota

Still intentionally deferred:

- capability-aware route filtering, streaming, and tools (Phase 3)
- read-only status/observability API (Phase 4)
- Hermes/Cline integration hardening and packaging (Phase 5)

## Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/robpodosek/free-frontier.git
cd free-frontier
uv sync
```

Create local runtime files:

```bash
cp free-frontier.toml.example free-frontier.toml
cp .env.example .env
```

The checked-in example starts with Gemini enabled and Groq present but disabled:

```toml
[routing]
default_cooldown_seconds = 60

[routes."gemini-flash"]
provider = "gemini"
model = "gemini/gemini-3.6-flash"
enabled = true
free = true
api_key_env = "GEMINI_API_KEY"

[routes."groq-gpt-oss"]
provider = "groq"
model = "groq/openai/gpt-oss-120b"
enabled = false
free = true
api_key_env = "GROQ_API_KEY"

[logical_models."free-frontier"]
routes = ["gemini-flash", "groq-gpt-oss"]
```

To use the Groq fallback, add `GROQ_API_KEY` to `.env` and set its route to `enabled = true`.

Provider model availability and free-tier terms can change. Verify configured routes against
current provider documentation and your own account billing settings.

## Run

```bash
uv run free-frontier
```

Default listener:

```text
http://127.0.0.1:4000
```

List public logical models:

```bash
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

Send a non-streaming request:

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "free-frontier",
    "messages": [{"role": "user", "content": "Say hello from Free Frontier."}],
    "stream": false
  }' | python -m json.tool
```

See [`docs/PHASE2-SMOKE.md`](docs/PHASE2-SMOKE.md) for a controlled real-provider fallback
smoke test.

## Development

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git diff --check
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
