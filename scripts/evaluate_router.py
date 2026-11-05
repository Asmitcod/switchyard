"""Evaluate routing strategies on the collected labeled dataset."""

import argparse
import json
import pickle
import random
import sys
from statistics import mean
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.router import score_prompt
from app.training import training_pipeline


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


def bootstrap_quality(rows, scores, threshold, iterations=1000):
    rng = random.Random(42)
    samples = []
    for _ in range(iterations):
        indexes = [rng.randrange(len(rows)) for _ in rows]
        selected = [
            rows[index]["labels"]["cheap"] if scores[index] >= threshold else rows[index]["labels"]["strong"]
            for index in indexes
        ]
        samples.append(sum(selected) / len(selected))
    samples.sort()
    return {
        "estimate": round(mean(samples), 4),
        "lower_95": round(samples[int(iterations * 0.025)], 4),
        "upper_95": round(samples[int(iterations * 0.975) - 1], 4),
    }


def calibration(rows, scores, bins=5):
    result = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        selected = [(score, row["labels"]["cheap"]) for row, score in zip(rows, scores) if lower <= score < upper or (index == bins - 1 and score == 1)]
        if selected:
            result.append({
                "range": f"{lower:.1f}-{upper:.1f}",
                "count": len(selected),
                "mean_score": round(mean(score for score, _ in selected), 4),
                "observed_quality": round(mean(int(label) for _, label in selected), 4),
            })
    return result


def category_heldout(rows):
    categories = sorted({row["category"] for row in rows})
    results = []
    for held_out in categories:
        train = [row for row in rows if row["category"] != held_out]
        test = [row for row in rows if row["category"] == held_out]
        labels = [int(row["labels"]["cheap"]) for row in train]
        if len(set(labels)) < 2 or not test:
            continue
        model = training_pipeline()
        model.fit([row["prompt"] for row in train], labels)
        predictions = model.predict_proba([row["prompt"] for row in test])[:, 1]
        correct = sum((score >= 0.5) == bool(row["labels"]["cheap"]) for score, row in zip(predictions, test))
        results.append({
            "held_out_category": held_out,
            "test_size": len(test),
            "accuracy": round(correct / len(test), 4),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/router_dataset.jsonl")
    parser.add_argument("--output", default="data/evaluation.json")
    args = parser.parse_args()
    rows = [json.loads(line) for line in (ROOT / args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("Dataset is empty")
    random.Random(42).shuffle(rows)
    split = max(1, round(len(rows) * 0.2))
    test_rows = rows[:split]
    scores = [heuristic_score(row["prompt"]) for row in test_rows]
    thresholds = [round(index / 20, 2) for index in range(21)]
    router = [evaluate(test_rows, scores, threshold) for threshold in thresholds]
    random.seed(42)
    random_scores = [random.random() for _ in test_rows]
    random_curve = [evaluate(test_rows, random_scores, threshold) for threshold in thresholds]
    report = {
        "dataset_size": len(rows),
        "held_out_size": len(test_rows),
        "strategies": {
            "always_cheap": {"quality": round(sum(row["labels"]["cheap"] for row in test_rows) / len(test_rows), 4), "cheap_share": 1.0, "cost_per_million_tokens": CHEAP_COST},
            "always_strong": {"quality": round(sum(row["labels"]["strong"] for row in test_rows) / len(test_rows), 4), "cheap_share": 0.0, "cost_per_million_tokens": STRONG_COST},
            "router": router,
            "random": random_curve,
        },
        "confidence_intervals": {
            "router_at_0.75": bootstrap_quality(test_rows, scores, 0.75),
            "always_cheap": bootstrap_quality(test_rows, [1.0] * len(test_rows), 1.0),
            "always_strong": bootstrap_quality(test_rows, [0.0] * len(test_rows), 1.0),
        },
        "calibration": calibration(test_rows, scores),
        "category_heldout": category_heldout(rows),
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
