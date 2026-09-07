# Free Frontier v0.1 Roadmap

This roadmap turns the specification into narrow implementation phases. Do not start a later phase until the current phase's acceptance gate passes.

Current implementation target: **Phase 5**. Phase 0 through Phase 4 acceptance gates have passed.

## Phase 0 — Reset and contract

**Goal:** remove the experimental architecture and establish the v0.1 source of truth.

Deliverables:

- corrected `README.md`
- normative `docs/SPEC-v0.1.md`
- architecture boundaries in `docs/ARCHITECTURE.md`
- coding-agent instructions in `AGENTS.md`
- clean Python `src/` package skeleton
- cleaned environment template and ignore rules
- old terminal monitoring UI removed
- old launcher/callback/stats implementation removed
- stale routing config removed
- old Docker launcher removed until a real application entrypoint exists
- stale dependency lockfile removed

### Acceptance gate

- repository contains no legacy `main.py`, `monitor.py`, or `proxy_callbacks.py`
- repository contains no old `config.yaml` claiming to be the v0.1 routing contract
- docs consistently describe Free Frontier as a model proxy, not an agent framework
- `python -m compileall src` succeeds
- Phase 0 contract tests pass

**Phase 0 is intentionally not a runnable proxy.**

---

## Phase 1 — Stable API + configuration foundation

**Goal:** serve the `free-frontier` logical model through a clean application/configuration layer using one upstream route. No multi-provider fallback yet.

Deliverables:

- application entrypoint
- typed configuration schema
- logical-model and physical-route data model
- startup configuration validation
- one enabled provider transport through LiteLLM
- `GET /v1/models` exposing `free-frontier`
- `POST /v1/chat/completions` accepting `model: free-frontier`
- non-streaming request/response path
- secrets loaded from environment without leaking to logs
- unit tests using fake/mocked transport
- minimal real-provider smoke test documentation

Do not add cooldown/fallback logic beyond interfaces needed by Phase 2.

### Acceptance gate

A client can send a non-streaming chat-completion request to `free-frontier`, the request is resolved to one configured physical route, and the response returns through the OpenAI-compatible API without the client naming that physical route.

---

## Phase 2 — Free-only routing, fallback, and cooldowns

**Goal:** make multiple free routes behave like one resilient logical model.

Deliverables:

- multiple route definitions under `free-frontier`
- explicit free-only eligibility metadata/policy
- deterministic route ordering/preference
- failure classification for fallback-worthy temporary failures
- cooldown state with configurable duration/policy
- skip routes while cooling down
- automatic re-eligibility after cooldown expiry
- transparent pre-stream fallback
- clean all-routes-unavailable error
- validation that logical models cannot reference nonexistent routes
- tests proving no paid/ineligible route can be selected

### Required deterministic tests

1. preferred route succeeds
2. preferred route returns a rate-limit failure and fallback succeeds
3. next request during cooldown skips the preferred route
4. expired cooldown makes the preferred route eligible again
5. all eligible free routes unavailable returns a clean failure
6. a route not eligible under the free-only policy is never selected
7. invalid route references fail configuration validation

### Acceptance gate

With fake upstreams, one request can transparently fail from Route A to Route B, subsequent requests skip A during cooldown, and A automatically returns to eligibility after cooldown expiry. No paid/ineligible route is ever selected.

---

## Phase 3 — Capability-aware routing, streaming, and tools

**Goal:** make fallback safe for real agent frameworks rather than merely available.

Deliverables:

- capability metadata for routes
- request capability extraction
- capability filtering before route selection
- OpenAI-compatible streaming through the logical model
- compatible tool/function-call forwarding and responses
- structured-output handling needed by target clients
- explicit behavior for failure before vs. after streaming begins
- tests for capability filtering, streaming, and tools

### Required tests

- tools request skips a route without tool support
- streaming request skips a route without streaming support
- compatible route streams successfully
- pre-stream upstream failure can fall back transparently
- no attempt is made to splice a partial streamed answer from another model
- tool calls remain OpenAI-compatible through the proxy abstraction

### Acceptance gate

Hermes/Cline-style requests using streaming and tools can target only `free-frontier`; the router selects only compatible routes and can still fall back safely before streaming begins.

---

## Phase 4 — Headless observability and status API

**Goal:** make routing explainable without coupling correctness to a UI.

Deliverables:

- structured routing events/logs
- safe in-memory request and route counters
- `GET /health` liveness/readiness endpoint
- `GET /status` aggregate status endpoint
- `GET /routes` read-only per-route status endpoint
- cooldown expiry visibility
- selected-route/fallback visibility
- route attempt/success/failure/skip metrics
- safe latency observations
- secret redaction tests

### Acceptance gate

An external client can determine which routes are eligible/cooling down and explain a recent fallback using read-only status data, while the router behaves identically if nobody consumes that data.

---

## Phase 5 — Integration hardening and v0.1 release

**Goal:** prove the abstraction against real consumers and package it cleanly.

Deliverables:

- Hermes smoke test/integration guide
- Cline smoke test/integration guide
- at least two real provider configurations verified against current provider docs
- container packaging restored around the new application entrypoint
- local development workflow
- configuration examples
- failure/error documentation
- release checklist

### Phase 5 hardening discovered during real Hermes integration

Before calling v0.1 complete, incorporate the compatibility issues exposed by the first real Hermes run:

- add a request/correlation ID to routing logs so concurrent client probes, retries, and inference calls can be traced as one request path
- add `GET /v1/models/{model}` for OpenAI-compatible model-detail discovery
- document harmless client backend-detection probes that Free Frontier intentionally does not implement
- do not fake Ollama or unrelated backend endpoints such as `/api/tags` or `/api/show` merely to silence probe 404s
- evolve route capabilities from independent yes/no flags into compatibility constraints for combinations such as structured output + streaming or structured output + tools
- expose useful retry timing in terminal errors/final `503` responses when an upstream `Retry-After` or known cooldown is available
- normalize/sanitize provider-specific response fields where practical so clients do not need to understand Gemini/Groq-specific metadata
- expand the live fallback pool beyond two upstreams when current provider policies permit a verifiably zero-cost route
- add deterministic tests that reproduce the real Hermes integration failure sequence: preferred route temporarily unavailable, fallback route rate-limited, routes cooling down, and client retries

### Acceptance gate

At least two OpenAI-compatible consumer applications can be configured with the same Free Frontier base URL and `free-frontier` logical model, and simulated/controlled provider failure causes transparent fallback without client reconfiguration. Real-client logs must be traceable by request ID, and compatibility probing must not require pretending to implement unrelated provider APIs.

---

# After v0.1

Post-v0.1 work should preserve the core rule: consumers see one stable OpenAI-compatible endpoint while provider selection, eligibility, cost policy, and fallback remain internal to Free Frontier.

## Provider expansion and qualification

Evaluate every provider at implementation time. A credential or model enters the normal FrFr routing pool only when there is a verifiable free-tier or other zero-marginal-cost path with a hard boundary against accidental paid fallback.

Candidate credentials already available for evaluation:

- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`
- `GEMINI_API_KEY`
- `GITHUB_TOKEN`
- `GOOGLE_API_KEY`
- `GROK_API_KEY`
- `GROQ_API_KEY`
- `NVIDIA_NIM_API_KEY`
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`

For each candidate, record:

- whether a real free tier currently exists
- whether the account can automatically spill into paid usage
- whether Free Frontier can enforce a hard no-paid boundary
- rate limits and cooldown semantics
- supported context size and request capabilities
- capability-combination restrictions
- provider/model deprecation or availability risks

Initial expansion targets include NVIDIA NIM, OpenRouter free routes, and other independently-backed providers that satisfy the zero-cost rule. Local Ollama models should also be supported as a zero-marginal-cost fallback option.

`OPENAI_API_KEY` must not enter the normal free pool merely because the user also has ChatGPT Plus or promotional credits. API-key billing and subscription billing are separate concerns. Any future paid route mode must be explicit opt-in and must never become an automatic fallback from the free pool.

## Subscription-backed OAuth routes

Investigate zero-marginal-cost routes backed by subscriptions the user already pays for, beginning with OpenAI Codex/ChatGPT subscription OAuth.

Requirements:

- authenticate through a first-class Free Frontier integration rather than copying or borrowing another client's stored OAuth credentials
- treat subscription usage limits separately from API-key billing
- expose subscription route availability/cooldown through the same routing and observability abstractions
- preserve the rule that a subscription-backed route cannot silently fall through to paid API usage

This broadens the practical meaning of "free" in Free Frontier to inference with no additional per-request charge to the user.

## Client compatibility

Harden compatibility with real OpenAI-compatible consumers such as Hermes and Cline.

Potential work:

- maintain a documented compatibility matrix
- support standard model-detail discovery such as `GET /v1/models/{model}`
- record which harmless discovery probes clients perform
- add request IDs/correlation IDs across HTTP requests, routing events, retries, and fallbacks
- add regression tests based on real client behavior
- avoid implementing fake compatibility endpoints that could misidentify Free Frontier as Ollama or another backend

## Response normalization

Reduce unnecessary leakage of provider-specific response details while preserving information required for OpenAI-compatible behavior.

Potential work:

- sanitize provider-specific metadata in streaming chunks
- normalize usage fields where providers differ
- preserve tool calls, structured output, and reasoning metadata only when needed by the client contract
- make provider identity available through explicit observability/debug interfaces rather than accidental response fields

## Capability policy evolution

Replace simple capability sets with richer constraints where required.

Examples:

- supports streaming
- supports tools
- supports structured output
- supports structured output only when not streaming
- supports structured output only when tools are absent
- supports vision or multimodal input
- context-window requirements

The router should reject incompatible capability combinations before consuming provider inference whenever the restriction is known.

## Observability and user interfaces

Build presentation layers as consumers of the existing headless status APIs. They must never become part of the routing critical path.

Potential work:

- small local web dashboard
- VS Code extension
- CLI status/routes commands
- richer route analytics and history
- request/fallback timelines using correlation IDs
- provider quota/cooldown visualization

## Routing intelligence

Potential follow-on routing work:

- additional logical routing profiles
- latency-aware ordering within an eligible free pool
- context-window-aware selection
- capability-preference policies
- provider health history
- provider discovery/validation helpers
- automated checks for model deprecation and free-tier policy drift

None of these may weaken the hard cost boundary. A faster or smarter route is never worth silently spending money.

## Branding and developer experience

Keep **Free Frontier** as the formal project name and use **FrFr** as the shorthand/brand where it fits.

Tagline:

> **One endpoint. Free models. FrFr.**

Potential future CLI naming can use `frfr` while the repository/package names remain `free-frontier` / `free_frontier` for compatibility.

---

All follow-on dashboards, extensions, CLIs, subscription integrations, and provider adapters should consume stable core interfaces instead of moving UI, client, or billing concerns into routing logic.
