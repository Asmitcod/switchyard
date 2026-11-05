import re
import time


CHEAP_PRICE_PER_MILLION = 0.05
STRONG_PRICE_PER_MILLION = 0.60
EASY_TERMS = ("capital", "translate", "define", "what is", "summarize", "spell", "convert", "list", "rewrite")
HARD_TERMS = ("prove", "derive", "step by step", "optimize", "debug", "analyze", "compare", "why", "design", "algorithm", "integral", "code")


def score_prompt(prompt: str) -> float:
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
