import os
import pickle
import re
import time
from functools import lru_cache
from pathlib import Path


CHEAP_PRICE_PER_MILLION = 0.05
STRONG_PRICE_PER_MILLION = 0.60
EASY_TERMS = ("capital", "translate", "define", "what is", "summarize", "spell", "convert", "list", "rewrite")
HARD_TERMS = ("prove", "derive", "step by step", "optimize", "debug", "analyze", "compare", "why", "design", "algorithm", "integral", "code")
MODEL_PATH = Path(os.getenv("ROUTEWISE_MODEL_PATH", Path(__file__).resolve().parents[1] / "data" / "router_model.pkl"))
USE_TRAINED_MODEL = os.getenv("ROUTEWISE_USE_TRAINED_MODEL", "false").lower() == "true"


@lru_cache(maxsize=1)
def _trained_model():
    if not MODEL_PATH.is_file():
        return None
    try:
        with MODEL_PATH.open("rb") as file:
            return pickle.load(file)
    except (OSError, EOFError, ImportError, AttributeError, ValueError):
        return None


def _trained_score(prompt: str) -> float | None:
    if not USE_TRAINED_MODEL:
        return None
    model = _trained_model()
    if model is None:
        return None
    try:
        return float(model.predict_proba([prompt])[0][1])
    except (AttributeError, ValueError):
        return None


def score_prompt(prompt: str) -> float:
    trained_score = _trained_score(prompt)
    if trained_score is not None:
        return max(0.03, min(0.97, trained_score))
    lowered = prompt.lower()
    words = len(lowered.split())
    score = 0.78 - min(words, 120) / 120 * 0.32
    score += sum(0.10 for term in EASY_TERMS if term in lowered)
    score -= sum(0.14 for term in HARD_TERMS if term in lowered)
    if re.search(r"\d.*[+\-*/^=].*\d", lowered):
        score -= 0.10
    if re.search(r"```|def |function |class ", lowered):
        score -= 0.12
    return max(0.03, min(0.97, score))


def route_prompt(prompt: str, threshold: float) -> dict:
    started = time.perf_counter()
    score = score_prompt(prompt)
    cheap = score >= threshold
    token_estimate = round(len(prompt.split()) * 1.4) + 150
    chosen_price = CHEAP_PRICE_PER_MILLION if cheap else STRONG_PRICE_PER_MILLION
    router_latency_ms = (time.perf_counter() - started) * 1000
    return {
        "score": round(score, 4),
        "threshold": threshold,
        "chosen_model": "cheap" if cheap else "strong",
        "cheap": cheap,
        "estimated_cost_per_1000": round(token_estimate * chosen_price / 1_000_000 * 1000, 5),
        "strong_cost_per_1000": round(token_estimate * STRONG_PRICE_PER_MILLION / 1_000_000 * 1000, 5),
        "latency_ms": 320.0 if cheap else 900.0,
        "router_latency_ms": round(router_latency_ms, 3),
        "explanation": (
            f"The router is {round(score * 100)}% sure the cheap model can answer this."
        ),
    }
