from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant|tool)$")
    content: str = Field(min_length=1, max_length=12000)


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="routewise")
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    stream: bool = False
    threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class RouteResponse(BaseModel):
    score: float
    threshold: float
    chosen_model: str
    cheap: bool
    estimated_cost_per_1000: float
    strong_cost_per_1000: float
    latency_ms: float
    router_latency_ms: float
    explanation: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


class DashboardResponse(BaseModel):
    requests_routed: int
    cheap_share: float
    estimated_savings: float
    router_p95_ms: float
    confidence_scores: list[float]
    recent_requests: list[RouteResponse]
