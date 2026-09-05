# Free Frontier

**One endpoint. Multiple free LLM providers. Automatic fallback. No paid inference without explicit opt-in.**

Free Frontier is a local, OpenAI-compatible model proxy that gives AI clients one stable endpoint while transparently routing requests across the free-tier model providers you configure.

The client should only need to know:

```text
Base URL: http://localhost:4000/v1
Model:    free-frontier
```

Hermes, Cline, Continue, Open WebUI, custom applications, and other OpenAI-compatible clients can sit above Free Frontier. They do not need to know which provider or physical model actually serves a request.

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

Free Frontier owns the model-selection details that would otherwise leak into every client configuration:

- which provider/model is preferred
- which configured routes are currently healthy
- which routes are rate-limited or cooling down
- which fallback should be tried next
- whether a route can satisfy the request's capabilities
- how provider-specific APIs are normalized
- whether a route is eligible under the configured cost policy

The calling application keeps using the logical model name `free-frontier` throughout.

## You provide the API keys

Free Frontier does **not** provide third-party API access. You provide API keys for the providers whose free tiers you want to use.

You do not have to configure every supported provider. Configuring more eligible providers gives Free Frontier a larger fallback pool.

Provider credentials stay on the Free Frontier side. The client talks only to Free Frontier.

A future release may support more providers, but the initial provider targets include services such as Google AI Studio, Groq, NVIDIA NIM, and OpenRouter, plus optional local inference.

## What happens when a free-tier limit is reached?

Assume the configured preference order is:

```text
Provider A
    ↓
Provider B
    ↓
Provider C
```

Free Frontier sends requests to Provider A while that route is eligible and available.

If Provider A reaches a free-tier inference limit and responds with a rate-limit or temporary-capacity failure, Free Frontier should:

1. mark that route as temporarily unavailable or cooling down
2. retry the request against the next eligible free route
3. return the successful response through the same OpenAI-compatible interface
4. keep skipping the cooling route until it becomes eligible again
5. automatically allow the preferred route back into consideration after its cooldown expires

The client still requests:

```text
model = free-frontier
```

It does not change providers, models, credentials, or configuration.

## Zero-cost policy

For v0.1, Free Frontier is **free-only by design**.

> If all eligible free routes are unavailable, Free Frontier fails instead of knowingly selecting paid inference.

Free Frontier must never silently convert a free-routing failure into a paid request.

### Important account-level billing caveat

Free Frontier controls the routes it selects. It cannot override the billing policy attached to an API account you provide.

If you supply a key for an account or project configured to automatically bill after a free allowance is exhausted, the upstream provider may charge that account even though Free Frontier intended to use a free-tier route.

If you want a strict zero-cost setup, configure each provider account/project so paid overages are disabled or otherwise impossible, where the provider supports that option.

The Free Frontier guarantee is:

> **Free Frontier will not knowingly route a request to paid inference in v0.1.**

It is not a guarantee against billing settings controlled by an upstream provider account.

## Logical model abstraction

Clients normally request one logical model:

```text
free-frontier
```

That is not a physical LLM. It represents Free Frontier's routing policy.

Internally it may resolve to different provider/model combinations over time:

```text
free-frontier
      │
      ├── Provider A / Model 1
      ├── Provider B / Model 2
      ├── Provider C / Model 3
      └── Local fallback
```

Routes can be added, removed, reordered, cooled down, or replaced without forcing consumers to reconfigure their model selection.

## Capability-aware fallback

A healthy model is not automatically a valid fallback.

Routing must be able to account for request requirements such as:

- tool/function calling
- streaming
- context-window requirements
- structured output
- vision or other modalities when supported

A fallback route must be both available **and compatible** with the request.

## Monitoring without a monitoring UI

Free Frontier still needs observability, but routing must not depend on a terminal dashboard or other presentation layer.

The core should produce structured routing state and events such as:

- route selected
- fallback attempted
- rate limit encountered
- cooldown entered/exited
- request succeeded/failed
- latency and basic usage metadata

That state can later power a web dashboard, CLI view, or VS Code extension without putting presentation code in the routing path.

## Current repository state: Phase 0

The project is currently in a clean v0.1 rebuild.

**Phase 0 intentionally contains the product contract, architecture boundaries, development instructions, and Python package skeleton, but not a runnable proxy.** The previous experimental launcher, terminal health-monitor UI, resilience callback, stale routing configuration, Docker launcher, and dependency lockfile have been removed so the new implementation can be built directly against the v0.1 specification.

See:

- [`docs/SPEC-v0.1.md`](docs/SPEC-v0.1.md) for the normative product contract
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the intended component boundaries
- [`docs/ROADMAP.md`](docs/ROADMAP.md) for the implementation phases and acceptance gates
- [`AGENTS.md`](AGENTS.md) for instructions to coding agents working on this repository

## Repository

Canonical repository: https://github.com/robpodosek/free-frontier

## License

MIT. See [`LICENSE`](LICENSE).
