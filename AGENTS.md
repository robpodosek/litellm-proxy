# AGENTS.md

## Project identity

Free Frontier is a local, OpenAI-compatible model-routing proxy.

Its job is to expose a stable logical model such as `free-frontier` and transparently select among configured free-tier provider/model routes.

Free Frontier is **not** an agent framework.

## Source of truth

Before changing implementation code, read in this order:

1. `docs/SPEC-v0.1.md`
2. `docs/ARCHITECTURE.md`
3. `docs/ROADMAP.md`
4. `README.md`

When documentation conflicts, `docs/SPEC-v0.1.md` is authoritative for v0.1 product behavior.

## Hard product boundary

Do not add functionality for:

- agent planning
- repository/task management
- prompt orchestration
- agent memory
- handoffs between agents
- Git automation
- tmux/session management
- coding workflows
- multi-agent coordination
- IDE-specific workflow logic

Hermes, Cline, Codex-based tools, Continue, Open WebUI, custom applications, and similar systems are consumers of Free Frontier. They are not components of Free Frontier.

The test for scope is:

> Does the proxy need this information or behavior to select and serve an LLM request?

If the answer is no, it probably does not belong in the core project.

## v0.1 public contract

Normal clients should be able to configure a stable OpenAI-compatible base URL and request the logical model:

```text
free-frontier
```

Physical provider/model identities are internal routing details and must not be required in normal consumer configuration.

The system must support transparent fallback among eligible routes.

## Free-only invariant

v0.1 is free-only.

The implementation must never knowingly select paid inference.

If all eligible free routes are unavailable, fail cleanly instead of selecting a paid route.

Do not add a paid fallback, automatic credit usage, or "temporary" paid escape hatch in v0.1.

Account-level billing remains outside Free Frontier's control. Documentation must not claim the software can override billing settings attached to user-supplied provider credentials.

## API keys

Users supply credentials for the providers they choose to enable.

Do not hard-code credentials.

Do not log credential values.

Do not require credentials for providers that the user has not enabled.

Keep provider credentials behind the proxy so clients do not need upstream provider keys.

## Routing ownership

Free Frontier should own:

- logical-model resolution
- route eligibility
- preference/priority policy
- health/cooldown state
- fallback decisions
- capability filtering
- free-only eligibility policy
- routing observability

Provider libraries such as LiteLLM may own transport and normalization details, but they must not become the source of truth for Free Frontier's product semantics when doing so would violate the specification.

## Failure and cooldown behavior

Temporary failures such as rate limits, capacity errors, and appropriate service failures should make a route temporarily ineligible according to policy.

While a route is cooling down, new requests should avoid it rather than repeatedly hammer it.

After the cooldown expires, the route becomes eligible again automatically unless another health condition prevents it.

Fallback must be transparent to the caller before response streaming has begun.

Do not attempt to splice together partially streamed responses from different upstream models in v0.1.

## Capability safety

Do not select an otherwise healthy route if it cannot satisfy the request.

Capability checks may include:

- streaming
- tools/function calling
- structured output
- context-window requirements
- modalities such as vision when supported

Unknown capability support should be treated conservatively rather than guessed.

## Observability boundary

Monitoring data belongs in the core. Monitoring presentation does not.

The core may emit structured events/state and expose read-only status/health information.

A future dashboard, CLI UI, or VS Code extension should consume that information as a client.

Never make routing correctness depend on a dashboard process, Rich terminal UI, VS Code extension, or other presentation layer.

## Implementation approach

Prefer small, explicit components with typed interfaces.

Initial implementation target:

- Python 3.12+
- `src/` package layout
- tests under `tests/`
- LiteLLM where it reduces provider-specific transport/normalization work

Do not build a generalized plugin system, daemon mesh, database-backed control plane, web dashboard, or workflow engine for v0.1.

## Phase discipline

Current implementation target: **Phase 2 — free-only routing, fallback, and cooldowns**.

Work only on the current phase unless the user explicitly expands scope.

`docs/ROADMAP.md` defines phase acceptance gates.

Do not implement later-phase features "while you're here" if they materially broaden the change.

Every phase should leave the repository testable and understandable.

## Testing expectations

Routing logic must be testable without consuming real provider quota.

Prefer fake/mock upstreams for deterministic tests of:

- route selection
- rate-limit fallback
- cooldown skipping
- cooldown expiry
- capability filtering
- all-routes-unavailable behavior
- free-only enforcement
- streaming behavior
- tool-call behavior

Real-provider smoke tests may exist separately and must not be required for the normal unit test suite.

## Configuration rules

Configuration must be validated at startup.

Reject invalid references such as fallbacks/routes that point to nonexistent route IDs.

Reject ambiguous or unsafe cost-policy configuration.

Do not silently ignore malformed routing configuration.

## Documentation rules

Do not hard-code claims about provider quotas, exact free-tier limits, or currently available model IDs unless those claims have been verified against current provider documentation.

Provider offerings change frequently. Prefer configuration and capability metadata over marketing copy embedded in code.

## Definition of done for a phase

Before declaring a phase complete:

1. run its automated tests
2. run formatting/linting configured for the repository
3. confirm the phase acceptance gate in `docs/ROADMAP.md`
4. summarize files changed and design decisions
5. list any spec requirement that remains intentionally unimplemented because it belongs to a later phase
