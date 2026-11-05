import os
import time
from dataclasses import dataclass

import httpx


class ProviderError(Exception):
    """Raised when an upstream model provider cannot complete a request."""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


def provider_config(tier: str) -> ProviderConfig | None:
    prefix = tier.upper()
    base_url = os.getenv(f"{prefix}_PROVIDER_BASE_URL", os.getenv("GROQ_BASE_URL"))
    api_key = os.getenv(f"{prefix}_PROVIDER_API_KEY", os.getenv("GROQ_API_KEY"))
    model = os.getenv(
        f"{prefix}_PROVIDER_MODEL",
        os.getenv("CHEAP_MODEL" if tier == "cheap" else "STRONG_MODEL"),
    )
    if not base_url or not api_key or not model:
        return None
    return ProviderConfig(tier, base_url.rstrip("/"), api_key, model)


def complete(config: ProviderConfig, messages: list[dict], temperature: float | None, max_tokens: int | None) -> dict:
    payload = {"model": config.model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    try:
        response = httpx.post(
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json=payload,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        response.raise_for_status()
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
        raise ProviderError(f"{config.name} provider request failed: {error}") from error
    data = response.json()
    if not data.get("choices"):
        raise ProviderError(f"{config.name} provider returned no choices")
    message = data["choices"][0].get("message", {})
    if not message.get("content") and not message.get("tool_calls"):
        raise ProviderError(f"{config.name} provider returned an empty assistant message")
    return data


def stream_complete(config: ProviderConfig, messages: list[dict], temperature: float | None, max_tokens: int | None):
    payload = {"model": config.model, "messages": messages, "stream": True}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    try:
        with httpx.stream(
            "POST",
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json=payload,
            timeout=httpx.Timeout(60.0, connect=5.0),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield line
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
        raise ProviderError(f"{config.name} streaming request failed: {error}") from error


def fallback_order(cheap: bool) -> tuple[str, str]:
    return ("cheap", "strong") if cheap else ("strong", "cheap")
