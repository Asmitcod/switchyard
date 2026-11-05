import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException


WINDOW_SECONDS = 60
DEFAULT_LIMIT = 60
_REQUESTS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = Lock()


def configured_api_keys() -> set[str]:
    return {key.strip() for key in os.getenv("ROUTEWISE_API_KEYS", "").split(",") if key.strip()}


def authenticate_and_rate_limit(authorization: str | None = Header(default=None)) -> str:
    keys = configured_api_keys()
    if not keys:
        return "local"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer API key required")
    key = authorization.removeprefix("Bearer ").strip()
    if key not in keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    now = time.monotonic()
    with _LOCK:
        requests = _REQUESTS[key]
        while requests and now - requests[0] >= WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= int(os.getenv("ROUTEWISE_RATE_LIMIT", DEFAULT_LIMIT)):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        requests.append(now)
    return key
