"""OpenAI-compatible /v1 API Gateway.

Exposes Mission Control's provider-router as a standard OpenAI-compatible
endpoint so any CLI tool (Claude Code, Codex, Cursor, Cline, OpenCode …)
can point to it::

    export OPENAI_BASE_URL=http://localhost:8000/v1
    export OPENAI_API_KEY=sk-agentic-os

Endpoints
---------
- GET  /v1/models             — list available models & providers
- POST /v1/chat/completions   — chat completion (supports streaming via SSE)
- POST /v1/completions        — text completion (lightweight wrapper)
- POST /v1/embeddings         — embedding generation (when available)

Architecture
------------
The Gateway is an APIRouter that mounts on the FastAPI app. It:

1. Accepts OpenAI-format requests
2. Resolves the model name to a provider via the ProviderManager
3. For ``openai_compatible`` providers → transparent proxy to the provider's
   own /v1/chat/completions (full message passthrough + streaming passthrough)
4. For all other providers → adapts through the ProviderAdapter.execute()
5. Returns OpenAI-format responses
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from agentic_os.core.providers.manager import ProviderManagerImpl
from agentic_os.domain.agent import Agent, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("gateway")

# ──────────────────────────────────────────────────────────────────────────────
# OpenAI-compatible request / response models
# ──────────────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str = "user"  # system | user | assistant
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage] = []
    temperature: float | None = 0.7
    top_p: float | None = 1.0
    max_tokens: int | None = None
    stream: bool = False
    stop: str | list[str] | None = None
    frequency_penalty: float | None = 0.0
    presence_penalty: float | None = 0.0


class CompletionRequest(BaseModel):
    model: str = ""
    prompt: str = ""
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False


class EmbeddingRequest(BaseModel):
    model: str = ""
    input: str | list[str] = ""


# ──────────────────────────────────────────────────────────────────────────────
# Model resolution
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_provider(
    model: str,
    provider_mgr: ProviderManagerImpl,
) -> tuple[Any, str] | None:
    """Find a provider capable of serving *model*.

    Resolution order:
    1. Exact model match (provider has a model with this ID)
    2. Provider default model matches
    3. Any available provider (first healthy one)

    Returns ``(provider_adapter, model_name)`` or ``None``.
    """
    if model:
        # Try exact model match across all providers
        for p in provider_mgr.list_providers():
            adapter = provider_mgr.get(p.name)
            if adapter is None:
                continue
            for m in provider_mgr.list_models(p.name):
                if m.id == model or m.id.endswith(f"/{model}"):
                    log.info("gateway.model_match", provider=p.name, model=model)
                    return adapter, m.id
            # Check if the provider's default model matches
            cfg = provider_mgr.get_config(p.name)
            if cfg and cfg.default_model == model:
                return adapter, model

    # Pick the first healthy provider as fallback
    for p in provider_mgr.list_providers():
        adapter = provider_mgr.get(p.name)
        if adapter is None:
            continue
        cfg = provider_mgr.get_config(p.name)
        fallback_model = cfg.default_model if cfg and cfg.default_model else model or "default"
        if fallback_model:
            log.info("gateway.fallback_match", provider=p.name, model=fallback_model)
            return adapter, fallback_model
        # Even without a configured model, try the first available
        models = provider_mgr.list_models(p.name)
        if models:
            m = models[0]
            return adapter, m.id
        # Last resort: use the provider directly
        return adapter, model or "default"

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Provider invocation
# ──────────────────────────────────────────────────────────────────────────────


def _is_proxyable(adapter: Any) -> bool:
    """Check if we can directly proxy to the provider's own OpenAI endpoint."""
    kind = getattr(adapter, "info", None)
    if kind is None:
        return False
    # Check type name or kind attribute
    type_name = type(adapter).__name__.lower()
    if "openai" in type_name or "compatible" in type_name:
        return True
    return False


async def _proxy_chat_completion(
    adapter: Any,
    model: str,
    body: ChatCompletionRequest,
) -> dict | AsyncGenerator[dict, None]:
    """Proxy a chat completion request to an openai_compatible provider.

    Supports streaming passthrough.
    """
    base_url: str = getattr(adapter, "_base_url", "")
    api_key: str = getattr(adapter, "_api_key", "")
    timeout: float = getattr(adapter, "_timeout", 120.0)

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [m.model_dump() for m in body.messages],
        "stream": body.stream,
    }
    if body.temperature is not None:
        payload["temperature"] = body.temperature
    if body.max_tokens is not None:
        payload["max_tokens"] = body.max_tokens
    if body.top_p is not None:
        payload["top_p"] = body.top_p
    if body.stop is not None:
        payload["stop"] = body.stop

    client = httpx.AsyncClient(timeout=timeout)

    if not body.stream:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data
        finally:
            await client.aclose()
    else:

        async def _stream() -> AsyncGenerator[bytes, None]:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    async for raw in resp.aiter_bytes():
                        yield raw
            except Exception as exc:
                log.error("gateway.proxy_stream_error", error=str(exc))
                yield b'data: {"error": "stream failed"}\n\n'
                yield b"data: [DONE]\n"

        return _stream()  # ty:ignore[invalid-return-type]


async def _adapter_chat_completion(
    adapter: Any,
    model: str,
    body: ChatCompletionRequest,
) -> dict:
    """Execute a chat completion through a non-OpenAI-compatible provider adapter.

    Converts the OpenAI-style request to an Agent+Task and calls
    ``adapter.execute()``.
    """
    # Build a prompt from messages
    prompt_parts: list[str] = []
    for msg in body.messages:
        role = msg.role.upper()
        prompt_parts.append(f"<{role}>\n{msg.content}\n</{role}>")
    prompt = "\n\n".join(prompt_parts)

    agent = Agent(
        id="gateway",
        name="Gateway",
        role="assistant",
        provider=getattr(adapter, "_name", "unknown"),
        model=model,
    )
    task = Task(
        id=uuid.uuid4().hex,
        title=prompt[:80],
        role="user",
        description=prompt,
    )

    try:
        result = await adapter.execute(agent, task)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────


def create_gateway_router(provider_mgr: ProviderManagerImpl) -> APIRouter:
    """Build the OpenAI-compatible /v1 router.

    Call from ``create_app()`` and mount via ``app.include_router()``.
    """
    router = APIRouter(prefix="")

    # ── GET /v1/models ────────────────────────────────────────────────────
    @router.get("/v1/models")
    async def list_models():
        """Return all models known to the ProviderManager in OpenAI format."""
        all_models = provider_mgr.list_models()
        data = []
        seen: set[str] = set()
        for m in all_models:
            mid = m.id
            if mid not in seen:
                seen.add(mid)
                data.append(
                    {
                        "id": mid,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": m.provider,
                    }
                )
        # Also add provider-level entries for easy discovery
        for p in provider_mgr.list_providers():
            pid = f"{p.name}/default"
            if pid not in seen:
                seen.add(pid)
                data.append(
                    {
                        "id": pid,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": p.name,
                    }
                )
        return {"object": "list", "data": data}

    # ── POST /v1/chat/completions ──────────────────────────────────────────
    @router.post("/v1/chat/completions")
    async def chat_completions(body: ChatCompletionRequest, request: Request):
        """OpenAI-compatible chat completion endpoint.

        Supports streaming via ``stream: true`` in the request body.
        """
        resolved = _resolve_provider(body.model, provider_mgr)
        if resolved is None:
            # Return a helpful error listing available models
            all_models = provider_mgr.list_models()
            available = [m.id for m in all_models]
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "message": f"Model '{body.model}' not found. Available: {available[:20]}",
                        "type": "model_not_found",
                        "param": "model",
                        "code": "model_not_found",
                    }
                },
            )

        adapter, resolved_model = resolved
        log.info(
            "gateway.chat",
            model=body.model,
            resolved_model=resolved_model,
            provider=type(adapter).__name__,
            stream=body.stream,
        )

        # For OpenAI-compatible providers → transparent proxy
        if _is_proxyable(adapter):
            result = await _proxy_chat_completion(adapter, resolved_model, body)
            if body.stream:
                # StreamingResponse with the proxy's byte stream
                return StreamingResponse(
                    result,  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            # Non-streaming: wrap the proxy response in OpenAI format
            data = result  # type: ignore[assignment]
            # Ensure the id/model fields are populated
            if "id" not in data:  # ty:ignore[unsupported-operator]
                data["id"] = f"chatcmpl-{uuid.uuid4().hex}"  # ty:ignore[invalid-assignment]
            if "model" not in data or not data["model"]:  # ty:ignore[not-subscriptable, unsupported-operator]
                data["model"] = resolved_model  # ty:ignore[invalid-assignment]
            if "object" not in data:  # ty:ignore[unsupported-operator]
                data["object"] = "chat.completion"  # ty:ignore[invalid-assignment]
            return JSONResponse(content=data)

        # For non-OpenAI-compatible providers → adapt through execute()
        result = await _adapter_chat_completion(adapter, resolved_model, body)
        return JSONResponse(content=result)

    # ── POST /v1/completions ───────────────────────────────────────────────
    @router.post("/v1/completions")
    async def completions(body: CompletionRequest):
        """Text completion endpoint (lightweight wrapper around chat)."""
        chat_body = ChatCompletionRequest(
            model=body.model,
            messages=[ChatMessage(role="user", content=body.prompt)],
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            stream=body.stream,
        )
        resolved = _resolve_provider(body.model, provider_mgr)
        if resolved is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "message": f"Model '{body.model}' not found",
                        "type": "model_not_found",
                        "code": "model_not_found",
                    }
                },
            )
        adapter, resolved_model = resolved
        if _is_proxyable(adapter):
            result = await _proxy_chat_completion(adapter, resolved_model, chat_body)
            if body.stream:
                return StreamingResponse(
                    result,  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                    media_type="text/event-stream",
                )
            data = result  # type: ignore[assignment]
            # Transform chat response to completion format
            text = ""
            for choice in data.get("choices", []):  # ty:ignore[unresolved-attribute]
                msg = choice.get("message", {})
                text += msg.get("content", "")
            resp = {
                "id": f"cmpl-{uuid.uuid4().hex}",
                "object": "text_completion",
                "created": int(time.time()),
                "model": resolved_model,
                "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
                "usage": data.get(  # ty:ignore[unresolved-attribute]
                    "usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                ),
            }
            return JSONResponse(content=resp)

        result = await _adapter_chat_completion(adapter, resolved_model, chat_body)
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return JSONResponse(
            content={
                "id": f"cmpl-{uuid.uuid4().hex}",
                "object": "text_completion",
                "created": int(time.time()),
                "model": resolved_model,
                "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
                "usage": result.get(
                    "usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                ),
            }
        )

    # ── POST /v1/embeddings ────────────────────────────────────────────────
    @router.post("/v1/embeddings")
    async def embeddings(body: EmbeddingRequest):
        """Embedding endpoint.

        Tries each provider's ``/v1/embeddings`` in order.  Returns a stub
        for now until embedding-aware providers are registered.
        """
        # Try each provider for embeddings support
        for p in provider_mgr.list_providers():
            adapter = provider_mgr.get(p.name)
            if adapter is None:
                continue
            if not _is_proxyable(adapter):
                continue
            base_url: str = getattr(adapter, "_base_url", "")
            api_key: str = getattr(adapter, "_api_key", "")
            url = f"{base_url.rstrip('/')}/v1/embeddings"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        url,
                        json={"model": body.model or "text-embedding-ada-002", "input": body.input},
                        headers=headers,
                    )
                    if resp.status_code < 500:
                        data = resp.json()
                        data["model"] = body.model or "text-embedding-ada-002"
                        return JSONResponse(content=data)
            except Exception:
                continue

        # No embedding provider found
        raise HTTPException(
            status_code=501,
            detail={
                "error": {
                    "message": "Embeddings not available — "
                    "no embedding-capable provider registered",
                    "type": "not_implemented",
                    "code": "not_implemented",
                }
            },
        )

    return router
