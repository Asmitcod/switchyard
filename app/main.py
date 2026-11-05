import hashlib
import time
from pathlib import Path
from statistics import quantiles

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    DashboardResponse,
    RouteRequest,
    RouteResponse,
)
from .database import dashboard_rows, initialize_database, log_request
from .providers import ProviderError, complete, fallback_order, provider_config
from .router import route_prompt


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
load_dotenv(ROOT / ".env")
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


@app.post("/api/route", response_model=RouteResponse)
def route(request: RouteRequest) -> RouteResponse:
    result = RouteResponse(**route_prompt(request.prompt, request.threshold))
    log_request(result.model_dump(), request.prompt)
    return result


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    if request.stream:
        raise HTTPException(status_code=501, detail="Streaming support is not configured yet")
    prompt = next((message.content for message in reversed(request.messages) if message.role == "user"), None)
    if not prompt:
        raise HTTPException(status_code=422, detail="At least one user message is required")
    routing = route_prompt(prompt, request.threshold)
    messages = [message.model_dump() for message in request.messages]
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


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
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
