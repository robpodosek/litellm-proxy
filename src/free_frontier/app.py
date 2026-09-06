from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from free_frontier.config import load_config
from free_frontier.models import AppConfig
from free_frontier.providers import CompletionTransport, LiteLLMTransport, TransportError
from free_frontier.routing import AllRoutesUnavailable, Router, UnknownLogicalModel


class ChatCompletionRequest(BaseModel):
    """Phase 2 subset of the OpenAI chat-completions request shape.

    Unknown OpenAI-compatible generation parameters are preserved and forwarded. Streaming
    is explicitly deferred to Phase 3 and rejected rather than silently mishandled.
    """

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
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": param,
                "code": code,
            }
        },
    )


def create_app(
    config: AppConfig | None = None,
    transport: CompletionTransport | None = None,
) -> FastAPI:
    resolved_config = config or load_config()
    resolved_transport = transport or LiteLLMTransport()
    router = Router(resolved_config, resolved_transport)

    app = FastAPI(
        title="Free Frontier",
        version="0.1.0a2",
        description="OpenAI-compatible free-tier LLM routing proxy.",
    )

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        now = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": now,
                    "owned_by": "free-frontier",
                }
                for model_id in router.logical_models()
            ],
        }

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any] | JSONResponse:
        if request.stream:
            return _error(
                400,
                "Streaming is not implemented until Phase 3; retry with stream=false.",
                error_type="invalid_request_error",
                code="unsupported_feature",
                param="stream",
            )

        try:
            payload = request.model_dump(exclude={"model"}, exclude_none=True)
            payload["stream"] = False
            return await router.complete(request.model, payload)
        except UnknownLogicalModel:
            return _error(
                404,
                f"Unknown model '{request.model}'. Use a logical model returned by /v1/models.",
                error_type="invalid_request_error",
                code="model_not_found",
                param="model",
            )
        except AllRoutesUnavailable:
            return _error(
                503,
                "All eligible free routes are temporarily unavailable.",
                error_type="api_error",
                code="all_routes_unavailable",
            )
        except TransportError:
            return _error(
                502,
                "An upstream route failed with a non-retryable error.",
                error_type="api_error",
                code="upstream_error",
            )

    return app
