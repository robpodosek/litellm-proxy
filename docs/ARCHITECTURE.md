# Free Frontier Architecture

## Product boundary

Free Frontier sits between OpenAI-compatible clients and upstream LLM providers.

```text
Hermes / Cline / other client
            |
            v
     OpenAI-compatible API
            |
            v
      Free Frontier router
        |     |      |
        v     v      v
      route route  route
            |
            v
          LiteLLM
            |
            v
     upstream providers
```

The core does not understand agent tasks, repositories, memory, handoffs, or IDE workflows.

## Public abstraction

Clients request logical models. v0.1 exposes:

```text
free-frontier
```

Physical provider/model identities are internal route configuration.

## Main components

### `app.py`

Owns the external OpenAI-compatible HTTP surface:

- `GET /v1/models`
- `POST /v1/chat/completions`
- JSON error envelopes
- server-sent event framing for streamed chat completions

It does not select providers itself.

### `config.py` and `models.py`

Own validated runtime configuration:

- server settings
- logical models
- physical routes
- free-only metadata
- route capability metadata
- cooldown settings
- credential environment-variable names

Secrets stay in environment variables rather than typed config state.

### `capabilities.py`

Extracts request requirements from OpenAI-compatible request fields.

Current capability signals include:

- `stream=true` -> `streaming`
- tools/function fields -> `tools`
- JSON/JSON-schema `response_format` -> `structured_output`
- image content parts -> `vision`

Unknown route support is treated conservatively.

### `routing.py`

Owns Free Frontier policy:

1. resolve logical model
2. enforce enabled + free-only eligibility
3. filter routes by request capabilities
4. skip routes in cooldown
5. attempt routes in configured order
6. classify fallback behavior through normalized transport errors
7. rewrite returned model identity to the logical model

For non-streaming requests, fallback may continue until a compatible free route succeeds or all
eligible routes are exhausted.

For streaming requests, the router prefetches the first upstream chunk before committing the
HTTP stream. A fallback-worthy failure before that chunk can fall back transparently.

After the first chunk, the route is committed. A later stream failure terminates the stream and
never splices content from another model.

### `cooldowns.py`

Owns in-memory route cooldown timing. Cooldown state affects selection but is independent of
any UI.

### `providers/`

Owns transport normalization.

`LiteLLMTransport` translates Free Frontier's internal `PhysicalRoute` plus normalized payload
into LiteLLM calls for both normal and streaming completion paths. It normalizes provider
exceptions into safe routing failure categories.

Provider transports do not decide cost eligibility, route order, capability policy, or
fallback semantics.

## Capability-aware selection

For a request requiring:

```text
streaming + tools
```

this route is eligible:

```text
capabilities = [streaming, tools]
```

while this route is skipped before transport:

```text
capabilities = [streaming]
```

Capability metadata should describe what Free Frontier can safely use, not every feature a
provider advertises in isolation.

## Streaming commit boundary

```text
request stream=true
       |
       v
Route A start
       |
       +-- fails before first chunk --> cooldown/fallback to Route B
       |
       v
first chunk received
       |
       +-- response committed to Route A
       |
       +-- later failure --> terminate stream, no fallback splice
```

This boundary keeps transparent fallback from producing one response assembled from multiple
models.

## Observability

Routing logs report decisions such as:

- route skipped because ineligible
- route skipped because capability missing
- route skipped because cooldown active
- route attempt
- route failure and cooldown
- route success
- stream failure after commit

Phase 4 may add read-only status APIs and counters. Those interfaces must consume routing state
rather than participate in routing decisions.

## Future presentation layers

A future dashboard or VS Code extension should sit outside the routing core:

```text
                 +-> CLI/status client
Free Frontier ---+-> web dashboard
                 +-> VS Code extension
```

The proxy must remain fully functional without any of them.
