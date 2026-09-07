# AGENTS.md

## Project identity

Free Frontier is a local, OpenAI-compatible model-routing proxy.

Its job is to expose a stable logical model such as `free-frontier` and transparently select
among configured free-tier provider/model routes.

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

Hermes, Cline, Continue, Open WebUI, custom applications, and similar systems are consumers of
Free Frontier. They are not components of Free Frontier.

The scope test is:

> Does the proxy need this information or behavior to select and serve an LLM request?

If the answer is no, it probably does not belong in the core project.

## v0.1 public contract

Normal clients configure one OpenAI-compatible base URL and request:

```text
free-frontier
```

Physical provider/model identities are internal routing details. Clients must not be required
to select them.

## Free-only invariant

v0.1 is free-only.

The implementation must never knowingly select paid inference. If all eligible free routes
are unavailable or incompatible, fail cleanly instead of selecting a paid route.

Do not add a paid fallback, automatic credit usage, or temporary paid escape hatch in v0.1.

Account-level billing remains outside Free Frontier's control. Documentation must not claim
that Free Frontier can override billing settings attached to user-supplied credentials.

## API keys

Users supply credentials for providers they choose to enable.

Do not:

- hard-code credentials
- log credential values
- expose provider credentials through API responses
- require credentials for disabled routes

## Routing ownership

Free Frontier owns:

- logical-model resolution
- route eligibility and ordering
- free-only enforcement
- cooldown state
- fallback decisions
- request capability extraction
- capability filtering
- the streaming commit boundary
- routing observability

LiteLLM owns provider transport/normalization details where useful, but it does not define Free
Frontier's product semantics.

## Capability policy

Route capabilities are explicit configuration metadata.

Unknown support is unsupported until configured otherwise.

A request must never be sent to a route missing a capability the request requires. Current
Phase 3 capability names are:

- `streaming`
- `tools`
- `structured_output`
- `vision`

Capability declarations should be conservative. If a provider supports a feature only under
certain combinations or modes, do not claim broader support than Free Frontier can safely
route today.

## Streaming invariant

Transparent fallback is allowed only before the first upstream stream chunk commits the
response.

After the first upstream chunk has been accepted:

- keep the request bound to that route
- never splice remaining output from a fallback model
- terminate the stream if the committed upstream fails
- record the post-commit failure in logs without attempting fallback

## Failure and cooldown behavior

Fallback-worthy failures include configured temporary failures such as rate limits, selected
service errors, timeouts, and stale model/route-not-found responses.

While a route is cooling down, new requests should skip it. After cooldown expiry, the route
must automatically become eligible again unless another rule prevents selection.

Non-retryable failures must not be silently converted into fallback.

## Observability boundary

Monitoring data belongs in the core; monitoring presentation does not.

Routing behavior must be inspectable, but presentation is not part of routing correctness.

Keep route decision logs safe and credential-free. A future dashboard or VS Code extension
must consume status/observability interfaces rather than own routing decisions.

## Current phase

Phase 0 through Phase 4 acceptance gates have passed.

Current implementation target: **Phase 5 - integration hardening and v0.1 release.**

Phase 5 may add packaging, integration documentation, compatibility fixes, and release checks.
Do not move Hermes/Cline workflow logic into Free Frontier. Client-specific setup belongs in
documentation or compatibility boundaries, not in routing policy.

Do not build the dashboard or VS Code extension in Phase 5. Those remain post-v0.1 consumers
of the stable observability API.

## Testing requirements

Before considering a change complete, run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git diff --check
```

Tests should use fake transports whenever possible so normal test runs consume no provider
quota.

Phase 5 must prove at minimum:

1. Hermes can use `http://127.0.0.1:4000/v1` + `free-frontier`
2. Cline can use the same endpoint + logical model through OpenAI Compatible mode
3. both consumers can complete tool-using workflows through Free Frontier
4. controlled provider failure remains transparent to both consumers
5. Docker packaging runs the same application entrypoint and binds host loopback by default
6. provider examples are checked against current provider documentation
7. failure behavior and release steps are documented
8. all Phase 0 through Phase 4 behavior remains unchanged

## Code style

- Python 3.12+
- keep dependencies minimal
- prefer typed, explicit data models
- keep provider-specific behavior behind transport interfaces
- keep policy in Free Frontier routing code
- keep errors actionable without leaking secrets
- do not leave trailing whitespace
- always run `git diff --check` before handoff


## Phase 5 hardening invariants

- Preserve `X-Request-ID` correlation from HTTP response through every route-decision log line.
- Do not implement fake Ollama or other provider-specific discovery endpoints.
- Treat incompatible capability combinations as pre-routing policy, not as errors to discover by
  consuming upstream inference.
- Keep `Retry-After` derived only from known route cooldown state.
- Normalize known provider-only response metadata without stripping OpenAI-compatible tool,
  streaming, usage, or structured-output fields.
