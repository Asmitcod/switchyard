import hashlib
import os
import time
from pathlib import Path
from statistics import quantiles

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    DashboardResponse,
    RouteRequest,
    RouteResponse,
)
from .router import route_prompt


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
load_dotenv(ROOT / ".env")

from .database import dashboard_rows, initialize_database, log_request
from .providers import ProviderError, complete, fallback_order, provider_config, stream_complete
from .security import authenticate_and_rate_limit


initialize_database()

app = FastAPI(title="RouteWise API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness() -> dict:
    providers = {
        tier: provider_config(tier) is not None
        for tier in ("cheap", "strong")
    }
    return {
        "status": "ready" if all(providers.values()) else "degraded",
        "providers": providers,
    }


@app.get("/api/status")
def status(_: str = Depends(authenticate_and_rate_limit)) -> dict:
    providers = {
        tier: provider_config(tier) is not None
        for tier in ("cheap", "strong")
    }
    return {
        "service": "switchyard",
        "providers": providers,
        "storage": "configured" if os.getenv("DATABASE_URL") else "local",
        "trained_router": os.getenv("ROUTEWISE_USE_TRAINED_MODEL", "false").lower() == "true",
    }


@app.get("/v1/models")
def models() -> dict:
    available = []
    for tier in ("cheap", "strong"):
        config = provider_config(tier)
        if config:
            available.append(
                {
                    "id": config.model,
                    "object": "model",
                    "owned_by": "routewise",
                }
            )
    return {
        "object": "list",
        "data": [
            {
                "id": "routewise",
                "object": "model",
                "owned_by": "routewise",
                "capabilities": {"chat_completions": True, "streaming": True},
                "tiers": available,
            }
        ],
    }


@app.post("/api/route", response_model=RouteResponse)
def route(request: RouteRequest, _: str = Depends(authenticate_and_rate_limit)) -> RouteResponse:
    result = RouteResponse(**route_prompt(request.prompt, request.threshold))
    log_request(result.model_dump(), request.prompt)
    return result


@app.post("/v1/chat/completions", response_model=None)
def chat_completion(
    request: ChatCompletionRequest,
    _: str = Depends(authenticate_and_rate_limit),
) -> ChatCompletionResponse | StreamingResponse:
    prompt = next((message.content for message in reversed(request.messages) if message.role == "user"), None)
    if not prompt:
        raise HTTPException(status_code=422, detail="At least one user message is required")
    routing = route_prompt(prompt, request.threshold)
    messages = [message.model_dump() for message in request.messages]
    if request.stream:
        return stream_chat_completion(request, prompt, routing, messages)
    failures: list[str] = []
    fallback_used = False
    started = time.perf_counter()
    for tier in fallback_order(routing["cheap"]):
        config = provider_config(tier)
        if config is None:
            failures.append(f"{tier} provider is not configured")
            continue
        try:
            upstream = complete(config, messages, request.temperature, request.max_tokens)
            choice = upstream["choices"][0]
            result = ChatCompletionResponse(
                id=upstream.get("id", f"routewise-{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"),
                created=upstream.get("created", int(time.time())),
                model=config.model,
                choices=[choice],
                usage=upstream.get("usage", {}),
            )
            routing["chosen_model"] = tier
            routing["cheap"] = tier == "cheap"
            routing["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            usage = result.usage
            log_request(
                routing,
                prompt,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                fallback_used=fallback_used,
            )
            return result
        except ProviderError as error:
            failures.append(str(error))
            fallback_used = True
    raise HTTPException(status_code=503, detail={"message": "All configured providers failed", "failures": failures})


def stream_chat_completion(
    request: ChatCompletionRequest,
    prompt: str,
    routing: dict,
    messages: list[dict],
) -> StreamingResponse:
    for tier in fallback_order(routing["cheap"]):
        config = provider_config(tier)
        if config is None:
            continue
        try:
            chunks = stream_complete(config, messages, request.temperature, request.max_tokens)
            first_chunk = next(chunks)
        except (ProviderError, StopIteration):
            continue

        def events():
            started = time.perf_counter()
            yield first_chunk + "\n\n"
            for chunk in chunks:
                yield chunk + "\n\n"
            routing["chosen_model"] = tier
            routing["cheap"] = tier == "cheap"
            routing["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            log_request(routing, prompt)
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")
    raise HTTPException(status_code=503, detail="All configured providers failed to start streaming")


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(_: str = Depends(authenticate_and_rate_limit)) -> DashboardResponse:
    stored_rows = dashboard_rows()
    rows = [RouteResponse(**row, explanation="Persisted request metadata") for row in stored_rows]
    scores = [row.score for row in rows]
    cheap_count = sum(row.cheap for row in rows)
    cheap_share = cheap_count / len(rows) if rows else 0.0
    savings = cheap_share * (1 - 0.05 / 0.60)
    router_times = sorted(row.router_latency_ms for row in rows)
    p95 = quantiles(router_times, n=20)[18] if len(router_times) >= 2 else (router_times[0] if router_times else 0.0)
    return DashboardResponse(
        requests_routed=len(rows),
        cheap_share=round(cheap_share, 4),
        estimated_savings=round(savings, 4),
        router_p95_ms=round(p95, 3),
        confidence_scores=scores,
        recent_requests=rows[:8],
    )


@app.get("/")
def playground() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/dashboard")
def dashboard_page() -> FileResponse:
    return FileResponse(FRONTEND / "dashboard.html")


@app.get("/{path:path}")
def static_files(path: str) -> FileResponse:
    requested = (FRONTEND / path).resolve()
    if FRONTEND.resolve() not in requested.parents or not requested.is_file():
        return FileResponse(FRONTEND / "index.html")
    return FileResponse(requested)
