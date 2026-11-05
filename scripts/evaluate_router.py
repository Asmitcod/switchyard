"""Evaluate routing strategies on the collected labeled dataset."""

import argparse
import json
import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.router import score_prompt


CHEAP_COST = 0.05
STRONG_COST = 0.60


def heuristic_score(prompt: str) -> float:
    model_path = ROOT / "data" / "router_model.pkl"
    if model_path.exists():
        with model_path.open("rb") as file:
            model = pickle.load(file)
        return float(model.predict_proba([prompt])[0][1])
    return score_prompt(prompt)


def evaluate(rows, scores, threshold):
    cheap_quality = sum(row["labels"]["cheap"] for row in rows) / len(rows)
    strong_quality = sum(row["labels"]["strong"] for row in rows) / len(rows)
    selected = [row["labels"]["cheap"] if score >= threshold else row["labels"]["strong"] for row, score in zip(rows, scores)]
    cheap_count = sum(score >= threshold for score in scores)
    cost = (cheap_count * CHEAP_COST + (len(rows) - cheap_count) * STRONG_COST) / len(rows)
    return {
        "threshold": threshold,
        "quality": round(sum(selected) / len(selected), 4),
        "cost_per_million_tokens": round(cost, 4),
        "cheap_share": round(cheap_count / len(rows), 4),
        "cheap_quality": round(cheap_quality, 4),
        "strong_quality": round(strong_quality, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/router_dataset.jsonl")
    parser.add_argument("--output", default="data/evaluation.json")
    args = parser.parse_args()
    rows = [json.loads(line) for line in (ROOT / args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("Dataset is empty")
    scores = [heuristic_score(row["prompt"]) for row in rows]
    thresholds = [round(index / 20, 2) for index in range(21)]
    router = [evaluate(rows, scores, threshold) for threshold in thresholds]
    random.seed(42)
    random_scores = [random.random() for _ in rows]
    random_curve = [evaluate(rows, random_scores, threshold) for threshold in thresholds]
    report = {
        "dataset_size": len(rows),
        "strategies": {
            "always_cheap": {"quality": round(sum(row["labels"]["cheap"] for row in rows) / len(rows), 4), "cheap_share": 1.0, "cost_per_million_tokens": CHEAP_COST},
            "always_strong": {"quality": round(sum(row["labels"]["strong"] for row in rows) / len(rows), 4), "cheap_share": 0.0, "cost_per_million_tokens": STRONG_COST},
            "router": router,
            "random": random_curve,
        },
        "notes": [
            "Labels use exact or substring checks against expected answers.",
            "This dataset is a smoke-test benchmark and is too small for production claims.",
        ],
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"dataset_size: {len(rows)}")
    print(f"always_cheap_quality: {report['strategies']['always_cheap']['quality']}")
    print(f"always_strong_quality: {report['strategies']['always_strong']['quality']}")
    print(f"report: {output}")


if __name__ == "__main__":
    main()
