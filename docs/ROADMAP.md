# Free Frontier v0.1 Roadmap

This roadmap turns the specification into narrow implementation phases. Do not start a later phase until the current phase's acceptance gate passes.

Current implementation target: **Phase 2**. Phase 0 and Phase 1 acceptance gates have passed.

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
- safe counters and recent route outcomes
- health endpoint
- read-only route/status endpoint(s)
- cooldown expiry visibility
- selected-route/fallback visibility
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

### Acceptance gate

At least two OpenAI-compatible consumer applications can be configured with the same Free Frontier base URL and `free-frontier` logical model, and simulated/controlled provider failure causes transparent fallback without client reconfiguration.

---

# After v0.1

Potential follow-on work:

- small web dashboard
- VS Code extension
- richer route analytics
- additional logical routing profiles
- provider discovery/validation helpers

These should consume stable core interfaces instead of moving UI concerns into routing logic.
