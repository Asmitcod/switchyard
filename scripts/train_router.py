"""Train a TF-IDF/logistic router from collected verifiable examples."""

import argparse
import json
import pickle
import random
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training import training_pipeline


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/router_dataset.jsonl")
    parser.add_argument("--output", default="data/router_model.pkl")
    args = parser.parse_args()
    source = ROOT / args.input
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    random.Random(42).shuffle(rows)
    split = max(1, round(len(rows) * 0.2))
    test_rows = rows[:split]
    train_rows = rows[split:]
    examples = [(row["prompt"], int(row["labels"]["cheap"])) for row in train_rows]
    if len({label for _, label in examples}) < 2:
        raise SystemExit("Training requires both successful and unsuccessful cheap-model labels")
    model = training_pipeline()
    model.fit([prompt for prompt, _ in examples], [label for _, label in examples])
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as file:
        pickle.dump(model, file)
    predictions = model.predict_proba([row["prompt"] for row in test_rows])[:, 1]
    correct = sum((score >= 0.5) == bool(row["labels"]["cheap"]) for score, row in zip(predictions, test_rows))
    print(f"trained_examples: {len(examples)}")
    print(f"held_out_examples: {len(test_rows)}")
    print(f"held_out_accuracy: {correct / len(test_rows):.4f}")
    print(f"model: {output}")


if __name__ == "__main__":
    main()
