from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from free_frontier import __version__
from free_frontier.config import load_config
from free_frontier.models import AppConfig
from free_frontier.observability import ObservabilityState
from free_frontier.providers import CompletionTransport, LiteLLMTransport, TransportError
from free_frontier.routing import (
    AllRoutesUnavailable,
    NoCompatibleRoutes,
    Router,
    UnknownLogicalModel,
)


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat-completions request subset used by Free Frontier."""

    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False


def _error(
    status_code: int,
    message: str,
    *,
    error_type: str,
    code: str,
    param: str | None = None,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "message": message,
        "type": error_type,
        "param": param,
        "code": code,
    }
    headers: dict[str, str] = {}
    if retry_after_seconds is not None:
        error["retry_after_seconds"] = retry_after_seconds
        headers["Retry-After"] = str(retry_after_seconds)

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=headers,
    )


async def _sse_events(
    chunks: AsyncIterator[dict[str, Any]],
    observability: ObservabilityState,
) -> AsyncIterator[str]:
    try:
        async for chunk in chunks:
            yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
    except Exception:
        observability.record_request_failed("stream_interrupted")
        raise

    observability.record_request_succeeded()
    yield "data: [DONE]\n\n"


def create_app(
    config: AppConfig | None = None,
    transport: CompletionTransport | None = None,
    observability: ObservabilityState | None = None,
) -> FastAPI:
    resolved_config = config or load_config()
    resolved_transport = transport or LiteLLMTransport()
    resolved_observability = observability or ObservabilityState(resolved_config.routes)
    router = Router(
        resolved_config,
        resolved_transport,
        observability=resolved_observability,
    )

    app = FastAPI(
        title="Free Frontier",
        version=__version__,
        description="OpenAI-compatible free-tier LLM routing proxy.",
    )
    app.state.router = router
    app.state.observability = resolved_observability

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def model_row(model_id: str, *, created: int | None = None) -> dict[str, Any]:
        return {
            "id": model_id,
            "object": "model",
            "created": created if created is not None else int(time.time()),
            "owned_by": "free-frontier",
        }

    def route_rows() -> list[dict[str, Any]]:
        logical = resolved_config.logical_models["free-frontier"]
        rows: list[dict[str, Any]] = []

        for priority, route_id in enumerate(logical.routes, start=1):
            route = resolved_config.routes[route_id]
            remaining = router.cooldown_remaining(route_id)
            configured_eligible = route.enabled and route.free
            eligible_now = configured_eligible and remaining <= 0
            rows.append(
                {
                    "id": route_id,
                    "priority": priority,
                    "provider": route.provider,
                    "model": route.model,
                    "enabled": route.enabled,
                    "free": route.free,
                    "capabilities": sorted(
                        capability.value for capability in route.capabilities
                    ),
                    "incompatible_capability_combinations": [
                        sorted(capability.value for capability in combination)
                        for combination in route.incompatible_capability_combinations
                    ],
                    "eligible_now": eligible_now,
                    "cooldown": {
                        "active": remaining > 0,
                        "remaining_seconds": round(remaining, 3),
                    },
                    "metrics": resolved_observability.route_snapshot(route_id),
                }
            )

        return rows

    @app.get("/health")
    async def health() -> dict[str, Any]:
        routes = route_rows()
        ready = any(route["eligible_now"] for route in routes)
        return {
            "status": "ok" if ready else "degraded",
            "ready": ready,
            "version": __version__,
            "uptime_seconds": round(resolved_observability.uptime_seconds(), 3),
        }

    @app.get("/status")
    async def status() -> dict[str, Any]:
        routes = route_rows()
        eligible = sum(1 for route in routes if route["eligible_now"])
        cooling = sum(1 for route in routes if route["cooldown"]["active"])
        disabled = sum(1 for route in routes if not route["enabled"])
        paid_ineligible = sum(1 for route in routes if not route["free"])
        snapshot = resolved_observability.status_snapshot()

        return {
            "status": "ok" if eligible else "degraded",
            "version": __version__,
            "started_at": snapshot["started_at"],
            "uptime_seconds": snapshot["uptime_seconds"],
            "logical_model": "free-frontier",
            "last_selected_route": snapshot["last_selected_route"],
            "requests": snapshot["requests"],
            "routes": {
                "configured": len(routes),
                "eligible_now": eligible,
                "cooling_down": cooling,
                "disabled": disabled,
                "paid_ineligible": paid_ineligible,
            },
        }

    @app.get("/routes")
    async def routes() -> dict[str, Any]:
        return {
            "object": "list",
            "logical_model": "free-frontier",
            "data": route_rows(),
        }

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        now = int(time.time())
        return {
            "object": "list",
            "data": [model_row(model_id, created=now) for model_id in router.logical_models()],
        }

    @app.get("/v1/models/{model_id}", response_model=None)
    async def retrieve_model(model_id: str) -> dict[str, Any] | JSONResponse:
        if model_id not in router.logical_models():
            return _error(
                404,
                f"Unknown model '{model_id}'. Use a logical model returned by /v1/models.",
                error_type="invalid_request_error",
                code="model_not_found",
                param="model",
            )
        return model_row(model_id)

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(
        request: ChatCompletionRequest,
        http_request: Request,
    ) -> dict[str, Any] | JSONResponse | StreamingResponse:
        payload = request.model_dump(exclude={"model"}, exclude_none=True)
        payload["stream"] = request.stream
        request_id = http_request.state.request_id
        resolved_observability.record_request_started(streaming=request.stream)

        try:
            if request.stream:
                chunks = await router.stream(
                    request.model,
                    payload,
                    request_id=request_id,
                )
                return StreamingResponse(
                    _sse_events(chunks, resolved_observability),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )

            response = await router.complete(
                request.model,
                payload,
                request_id=request_id,
            )
            resolved_observability.record_request_succeeded()
            return response
        except UnknownLogicalModel:
            resolved_observability.record_request_failed("model_not_found")
            return _error(
                404,
                f"Unknown model '{request.model}'. Use a logical model returned by /v1/models.",
                error_type="invalid_request_error",
                code="model_not_found",
                param="model",
            )
        except NoCompatibleRoutes as exc:
            resolved_observability.record_request_failed("unsupported_capabilities")
            required = ", ".join(sorted(capability.value for capability in exc.required))
            return _error(
                400,
                f"No configured free route supports the request capabilities: {required}.",
                error_type="invalid_request_error",
                code="unsupported_capabilities",
            )
        except AllRoutesUnavailable as exc:
            resolved_observability.record_request_failed("all_routes_unavailable")
            return _error(
                503,
                "All eligible free routes are temporarily unavailable.",
                error_type="api_error",
                code="all_routes_unavailable",
                retry_after_seconds=exc.retry_after_seconds,
            )
        except TransportError:
            resolved_observability.record_request_failed("upstream_error")
            return _error(
                502,
                "An upstream route failed with a non-retryable error.",
                error_type="api_error",
                code="upstream_error",
            )

    return app
