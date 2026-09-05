# Free Frontier Architecture

This document describes the intended v0.1 component boundaries. It is subordinate to `SPEC-v0.1.md`.

## System position

```text
AI client / agent framework
          │
          │ OpenAI-compatible request
          ▼
┌──────────────────────────────┐
│        Free Frontier         │
│                              │
│  API                         │
│   ↓                          │
│  logical model resolution    │
│   ↓                          │
│  capability + cost filter    │
│   ↓                          │
│  routing policy              │
│   ↓                          │
│  cooldown / health state     │
│   ↓                          │
│  provider transport          │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
   Provider  Provider  Local
      A         B      model
```

Free Frontier sits below clients. It should not contain agent-specific behavior.

## Planned core components

The exact module names can evolve, but the responsibilities should stay separate.

### API layer

Responsibilities:

- expose OpenAI-compatible endpoints
- parse/validate incoming requests
- preserve the logical model abstraction
- stream normalized responses
- map terminal routing failures to clear API errors

Must not own provider priority or cooldown policy.

### Configuration

Responsibilities:

- load user configuration
- validate logical models and route definitions
- resolve enabled providers and required credentials
- expose immutable/typed configuration to the router

Configuration should fail early when references are invalid.

### Route registry

A route represents one concrete upstream provider/model target plus routing metadata.

Likely metadata includes:

- stable route ID
- provider identifier
- provider model identifier
- enabled state
- free-only eligibility declaration
- priority/preference
- capabilities
- provider-specific transport options

Physical route IDs are internal implementation details and are not the normal model names used by clients.

### Router / policy

Responsibilities:

- resolve a logical model to candidate routes
- filter candidates by free-only policy
- filter by request capabilities
- filter routes that are temporarily unavailable
- order/select candidates according to policy
- attempt transparent fallback before streaming begins

The router should be deterministic under test fixtures.

### Cooldown / health state

Responsibilities:

- classify temporary failures that should cool a route
- record cooldown start/expiry
- answer whether a route is currently eligible
- return expired routes to eligibility automatically

This state should be independent of any UI.

### Provider transport

Responsibilities:

- invoke upstream providers
- normalize request/response behavior
- provide streaming/tool-call compatibility where the upstream supports it

LiteLLM is the initial intended transport/normalization dependency unless implementation work reveals a concrete reason to replace or isolate parts of it.

Free Frontier should not duplicate provider-specific plumbing merely to avoid a dependency.

### Observability

Responsibilities:

- emit structured routing events
- expose safe read-only health/status data
- record enough information to explain routing decisions

Must never expose API secrets.

Must never be required for routing correctness.

## Planned source layout

Phase 0 establishes only a minimal importable package. Later phases may converge toward:

```text
src/free_frontier/
├── __init__.py
├── app.py
├── config.py
├── models.py
├── api/
│   ├── openai.py
│   └── status.py
├── routing/
│   ├── router.py
│   ├── policy.py
│   ├── capabilities.py
│   └── cooldowns.py
├── providers/
│   ├── base.py
│   ├── litellm.py
│   └── registry.py
└── observability/
    ├── events.py
    └── logging.py
```

Do not create all of these modules merely to match the diagram. Create them when the phase being implemented requires the responsibility.

## Future presentation layers

A later dashboard or VS Code extension should communicate with stable, read-only Free Frontier status/health interfaces.

```text
                    ┌── CLI/status client
                    │
Free Frontier Core ─┼── web dashboard
                    │
                    └── VS Code extension
```

Those presentation layers should remain replaceable. The router must operate correctly when none of them are running.
