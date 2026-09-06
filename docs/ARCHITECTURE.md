# Free Frontier architecture

## Architectural position

Free Frontier sits below agent frameworks and other AI clients.

```text
Hermes / Cline / OpenAI-compatible client
                  │
                  ▼
           Free Frontier API
                  │
                  ▼
          logical model router
                  │
         ┌────────┼────────┐
         ▼        ▼        ▼
      Route A  Route B  Route C
         │        │        │
         └────────┼────────┘
                  ▼
             LiteLLM
                  │
                  ▼
        upstream providers
```

Free Frontier does not understand agent plans, repositories, coding tasks, or workflow state.
Its responsibility is inference routing behind a stable logical model interface.

## Phase 2 component boundaries

### API layer: `app.py`

Responsibilities:

- expose OpenAI-compatible endpoints
- accept the public `free-frontier` logical model
- preserve unknown compatible request parameters
- reject streaming until Phase 3
- map terminal routing failures to safe API errors

It does not choose provider order or cooldown durations.

### Configuration: `config.py` + `models.py`

Responsibilities:

- load TOML and `.env`
- validate route references
- preserve ordered route preference
- validate `enabled` and `free` eligibility metadata
- load configurable cooldown policy
- require credentials only for enabled free routes that may be selected
- keep credential values out of typed configuration objects

Invalid route references fail at startup.

### Router: `routing.py`

Responsibilities:

- resolve a logical model to its ordered candidate routes
- enforce the v0.1 free-only invariant
- skip disabled and cooling routes
- attempt fallback after normalized fallback-worthy failures
- return the first successful normalized response
- keep physical model identity hidden from normal clients
- return a terminal all-routes-unavailable condition when no eligible route succeeds

Route order in the logical model definition is deterministic preference order.

### Cooldown state: `cooldowns.py`

Responsibilities:

- record per-route cooldown expiry using a monotonic clock
- answer whether a route is currently cooling down
- make expired routes eligible automatically

The tracker is intentionally headless and in-memory in Phase 2. It exposes no dashboard or
status API. Phase 4 will add read-only observability around routing state without making UI
code part of the routing path.

### Provider transport: `providers/`

Responsibilities:

- invoke upstream providers through LiteLLM
- keep API-key values behind the proxy
- normalize provider failures into safe `TransportError` categories
- preserve provider `Retry-After` hints when available
- normalize provider responses into OpenAI-style data structures

LiteLLM handles provider-specific API differences. Free Frontier owns routing policy.

### Failure classification

Phase 2 distinguishes:

- `rate_limit`: fallback-worthy; enters cooldown
- `temporary`: selected timeouts/5xx/capacity failures; fallback-worthy; enters cooldown
- `route_unavailable`: upstream model-not-found/route-unavailable failures; fallback-worthy;
  enters cooldown
- `non_retryable`: terminal for the request; does not silently fall back

Capability-specific incompatibility is intentionally deferred to Phase 3.

## Free-only invariant

A route is eligible only when:

```text
enabled == true
AND
free == true
AND
not cooling down
```

A configured route with `free = false` is never selected in v0.1. If no eligible free route
succeeds, the router fails rather than selecting paid inference.

This software cannot override billing rules attached to the provider account behind an API
key, so strict zero-cost users must also configure their provider accounts appropriately.

## Cooldown policy

Global default:

```toml
[routing]
default_cooldown_seconds = 60
```

A route may override it:

```toml
[routes."some-route"]
cooldown_seconds = 120
```

If an upstream error supplies a numeric `Retry-After`, Phase 2 uses the longer of the
configured cooldown and the provider hint. This avoids retrying earlier than either policy
allows.

## Current source layout

```text
src/free_frontier/
├── __init__.py
├── __main__.py
├── app.py
├── cli.py
├── config.py
├── cooldowns.py
├── models.py
├── routing.py
└── providers/
    ├── __init__.py
    ├── base.py
    └── litellm.py
```

Do not split these responsibilities into more modules merely to match a future diagram.
Create new boundaries when later phases actually require them.

## Later phases

Phase 3 adds capability-aware selection, streaming, and tools.

Phase 4 adds headless observability and read-only status APIs.

Phase 5 hardens real consumer/provider integration and packaging.

A future dashboard or VS Code extension should consume stable status interfaces as a client:

```text
                    ┌── CLI/status client
                    │
Free Frontier Core ─┼── web dashboard
                    │
                    └── VS Code extension
```

Routing correctness must not depend on any presentation layer being present.
