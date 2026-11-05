"""Train a TF-IDF/logistic router from collected verifiable examples."""

import argparse
import json
import pickle
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/router_dataset.jsonl")
    parser.add_argument("--output", default="data/router_model.pkl")
    args = parser.parse_args()
    source = ROOT / args.input
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    examples = [(row["prompt"], int(row["labels"]["cheap"])) for row in rows]
    if len({label for _, label in examples}) < 2:
        raise SystemExit("Training requires both successful and unsuccessful cheap-model labels")
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )
    model.fit([prompt for prompt, _ in examples], [label for _, label in examples])
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as file:
        pickle.dump(model, file)
    print(f"trained_examples: {len(examples)}")
    print(f"model: {output}")


if __name__ == "__main__":
    main()
