# Failure behavior

This document describes the v0.1 client-visible failure behavior.

## Fallback-worthy upstream failures

Free Frontier currently treats these classes as eligible for transparent fallback before a
response is committed:

- HTTP 429 / rate limit
- selected temporary service failures such as 408, 425, 500, 502, 503, 504, and 529
- connection/time-out style temporary transport failures
- HTTP 404 / stale or unavailable physical model route

A fallback-worthy failure puts the failed route into cooldown before the next eligible route is
attempted.

## Non-retryable upstream failures

Other upstream failures are returned as a safe generic `502` with code `upstream_error`.
Provider exception text and credentials are not returned to clients.

A bad or expired provider credential is therefore currently treated as configuration that
should be fixed, not silently hidden by fallback.

## All routes unavailable

If every compatible free route is unavailable or cooling down, Free Frontier returns:

```text
HTTP 503
code: all_routes_unavailable
```

It does not knowingly escape to a paid route.

## Unsupported request capabilities

If enabled free routes exist but none supports the request's required capabilities, Free
Frontier returns:

```text
HTTP 400
code: unsupported_capabilities
```

No incompatible upstream request is attempted.

## Unknown logical model

Clients requesting a model other than a configured logical model receive:

```text
HTTP 404
code: model_not_found
```

Normal v0.1 consumers should use `free-frontier`.

## Streaming boundary

Transparent fallback is allowed only before the first upstream chunk is emitted. After the
first chunk commits the stream to a physical route, a later upstream failure terminates that
stream. Free Frontier never splices output from two physical models into one streamed answer.

## Debugging order

1. `GET /health`
2. `GET /status`
3. `GET /routes`
4. inspect Free Frontier route-decision logs
5. verify enabled provider credentials are present
6. verify provider model IDs and free-tier availability against current provider docs

Do not put API-key values into bug reports or logs.
