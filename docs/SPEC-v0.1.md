# Free Frontier v0.1 Specification

**Repository:** https://github.com/robpodosek/free-frontier
**Version:** 0.1
**Status:** Initial implementation specification

## 1. Purpose

Free Frontier is a local, OpenAI-compatible model proxy that provides a single stable interface to multiple user-configured free-tier LLM providers.

Its purpose is:

> Point a compatible AI client at Free Frontier instead of directly at an upstream provider, and Free Frontier transparently selects, switches, and falls back among eligible free model routes.

The calling application should not need to know:

- which provider is serving a request
- which physical model is serving a request
- which configured routes are currently rate-limited
- which routes are cooling down or temporarily unavailable
- which fallback should be attempted next
- which routes satisfy the request's capabilities
- how provider-specific API differences are normalized

Those concerns belong to Free Frontier.

Free Frontier is infrastructure below the agent/application layer. It does not implement agents.

## 2. Core external contract

A compatible client should be able to use a stable OpenAI-compatible endpoint and normally request one logical model:

```text
Base URL: http://localhost:4000/v1
Model:    free-frontier
```

The logical model name is an abstraction over a routing policy, not the name of a physical upstream LLM.

A typical request looks conceptually like:

```http
POST /v1/chat/completions
```

```json
{
  "model": "free-frontier",
  "messages": [
    {"role": "user", "content": "Implement this function."}
  ]
}
```

The caller does not participate in selecting the physical provider/model route.

## 3. Product boundary

Free Frontier deals with LLM inference routing.

It does not understand or manage:

- coding tasks
- repository state
- agent plans
- prompts beyond what is necessary to forward an inference request
- agent memory
- handoffs
- Git workflows
- terminal sessions
- IDE workflows
- multi-agent orchestration

Those responsibilities belong to consuming applications.

## 4. Logical models

Clients should normally request a logical model such as:

```text
free-frontier
```

Internally, that logical model resolves to a configured pool of physical routes:

```text
free-frontier
      │
      ├── Provider A / Model 1
      ├── Provider B / Model 2
      ├── Provider C / Model 3
      └── Optional local route
```

Changing the provider/model composition, ordering, or availability of that pool must not require normal consumers to change their model selection.

## 5. User-supplied provider credentials

Free Frontier does not supply third-party API access.

Users must provide credentials for the providers they want to enable.

The implementation must:

- allow users to configure only a subset of supported providers
- avoid requiring credentials for disabled providers
- keep upstream credentials on the Free Frontier side
- never log credential values
- never expose upstream credentials to clients

More configured eligible providers generally means a larger fallback pool.

## 6. Free-only cost policy

v0.1 is free-only by design.

A route is eligible only when its configuration marks it as allowed by the free-only policy and the implementation can treat it as a free route under that configuration.

Normative rule:

> **Free Frontier MUST NOT knowingly route a v0.1 request to paid inference.**

If every eligible free route is unavailable, incompatible, exhausted, or cooling down, Free Frontier must return a clean failure instead of selecting a paid route.

Paid fallback is out of scope for v0.1.

### 6.1 Upstream billing caveat

Free Frontier controls route selection. It cannot override billing behavior attached to a user-supplied provider account, project, or API key.

Documentation must clearly tell users that an upstream provider may charge an account if that account is configured for automatic paid overages or paid usage.

Users who require a strict zero-cost setup are responsible for configuring provider accounts/projects so paid usage is disabled or otherwise impossible where the provider supports such controls.

Free Frontier's free-only invariant describes the routes Free Frontier knowingly selects. It is not a claim that Free Frontier can override an upstream provider's account-level billing configuration.

## 7. Routing policy

Routing policy is server-side configuration.

A route is a provider + physical model + metadata required for eligibility and transport.

The router may consider:

- configured preference/priority
- availability
- cooldown state
- provider/model health
- request capability requirements
- context-window requirements
- streaming support
- tool/function-calling support
- structured-output support
- latency or recent failures when policy permits
- free-only cost eligibility

The exact scoring algorithm may evolve without changing the external logical-model contract.

## 8. Fallback behavior

Fallback must be transparent to the caller before response streaming begins.

For an ordered example:

```text
Route A
   │ temporary failure
   ▼
Route B
   │ temporary failure
   ▼
Route C
   │ success
   ▼
client receives response
```

The caller continues requesting `free-frontier` throughout.

The router must not require the client to retry with a different physical model name.

## 9. Rate limits and cooldowns

Temporary failures may make a route temporarily ineligible.

Examples include appropriate forms of:

- HTTP 429 / rate limiting
- temporary provider capacity exhaustion
- transient upstream service unavailability
- selected timeout/service errors according to policy

When a route enters cooldown:

1. the failure is recorded as structured routing state/event data
2. the route is skipped for new requests while the cooldown remains active
3. fallback proceeds to the next eligible route
4. after cooldown expiry, the route automatically becomes eligible for consideration again unless another condition prevents it

The implementation should not repeatedly hammer a route known to be cooling down.

Cooldown policy must be configurable or otherwise explicit and testable.

## 10. Capability-aware routing

A healthy route is not necessarily a valid route for every request.

Free Frontier must avoid selecting routes known to be incompatible with the request.

Capability metadata/checks may include:

- streaming
- tool/function calling
- structured output / JSON modes
- context-window capacity
- vision or other modalities

Unknown support should be handled conservatively. The router should not guess that a route supports a required capability.

## 11. OpenAI-compatible API

The primary external interface is OpenAI-compatible.

At minimum, v0.1 should support the endpoints and request behavior necessary for target clients to use:

```text
/v1/chat/completions
/v1/models
```

Where supported by eligible upstream routes, v0.1 should preserve compatible behavior for:

- streaming
- system messages
- tool/function calling
- common generation parameters
- structured output parameters used by target clients

Provider-specific differences should be normalized behind the proxy rather than exposed as normal client configuration.

## 12. Streaming

If a client requests streaming and an eligible route supports it, Free Frontier should return an OpenAI-compatible streamed response.

Fallback before upstream response streaming begins should be transparent.

Once meaningful response streaming from an upstream route has begun, v0.1 is not required to reconstruct or splice the partial response using another model.

## 13. Operational routing state

Free Frontier may maintain only the operational state required to route and observe inference requests, including:

- route health
- cooldown start/expiry
- recent failures/successes
- latency observations
- request/fallback counters
- safe usage metadata

Free Frontier does not maintain conversation memory, agent memory, task state, repository state, or agent handoffs.

## 14. Observability

Monitoring is part of the core; monitoring presentation is not.

The core should emit structured events and/or expose read-only status information sufficient to answer questions such as:

- which route served the last request?
- why was the preferred route skipped?
- which routes are cooling down?
- when does a cooldown expire?
- what fallback attempts occurred?
- which routes are currently eligible?

Observability must not require a terminal UI.

A future dashboard, CLI view, or VS Code extension should consume the same routing state without participating in routing decisions.

Normative architecture rule:

> **Observability interfaces consume routing state; they do not own or control routing state.**

## 15. Provider abstraction

The implementation should avoid reimplementing provider-specific HTTP/streaming/tool-call normalization when a maintained library such as LiteLLM can provide it reliably.

Free Frontier still owns its product semantics:

- logical models
- route eligibility
- priority policy
- free-only enforcement
- capability policy
- cooldown/fallback behavior
- routing observability

Transport/provider libraries are implementation dependencies, not the public product contract.

## 16. Configuration requirements

v0.1 configuration must be validated before serving requests.

Invalid configuration must fail clearly rather than being silently ignored.

Validation must eventually cover at least:

- unique route IDs
- logical models referencing existing routes
- valid provider/model configuration
- explicit cost-policy eligibility
- capability metadata shape
- cooldown/routing policy shape
- credentials required only for enabled routes

Stale references to nonexistent fallback targets must be rejected.

## 17. Security and secrets

Free Frontier must not:

- hard-code API keys
- print API key values in normal logs
- include credential values in status endpoints
- expose provider credentials to callers

A proxy-level authentication mechanism may be supported independently of upstream provider credentials.

## 18. v0.1 required behavior

v0.1 succeeds only when the following behaviors are proven:

1. a client can request the stable logical model `free-frontier`
2. at least two configured free routes can participate in routing
3. a successful preferred route serves normally
4. a temporary/rate-limit failure on the preferred route transparently falls back
5. a route in cooldown is skipped on subsequent requests
6. an expired cooldown makes that route eligible again automatically
7. an incompatible route is skipped when the request requires unsupported capabilities
8. streaming works through the logical model for compatible routes
9. tool/function calling works through the logical model for compatible routes
10. all eligible free routes unavailable results in a clean failure, not paid inference
11. configuration cannot silently reference nonexistent routes
12. routing behavior is observable without a dedicated monitoring UI

## 19. Explicitly out of scope for v0.1

Do not build:

- an agent framework
- a coding agent
- an agent orchestrator
- a workflow engine
- an MCP replacement
- an IDE
- a task manager
- a Git manager
- an agent-memory/handoff system
- multi-agent swarms
- a web dashboard
- a VS Code extension
- a hosted control plane
- distributed execution
- a generalized provider/plugin marketplace
- paid fallback

A dashboard and VS Code extension are valid future consumers of Free Frontier's observability/status interfaces, but they are not part of v0.1 core routing.

## 20. Guiding rule

Whenever a proposed feature requires Free Frontier to understand what an agent or application is doing beyond what is present in the inference request, ask:

> Does the proxy actually need this to select and serve an eligible LLM route?

If the answer is no, it does not belong in the Free Frontier core.
