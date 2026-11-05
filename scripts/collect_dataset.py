"""Collect a small, verifiable router dataset with resumable checkpoints."""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.providers import ProviderError, complete, provider_config


PROMPTS = [
    ("knowledge", "What is the capital of Australia?", "canberra"),
    ("knowledge", "What gas do plants absorb from the atmosphere?", "carbon dioxide"),
    ("knowledge", "What is the largest ocean on Earth?", "pacific"),
    ("knowledge", "What is the boiling point of water at sea level in Celsius?", "100"),
    ("math", "What is 17 multiplied by 6?", "102"),
    ("math", "What is 144 divided by 12?", "12"),
    ("math", "What is 25 percent of 80?", "20"),
    ("math", "What is the square root of 81?", "9"),
    ("formatting", "Convert this list to comma-separated values: apples, oranges, bananas.", "apples, oranges, bananas"),
    ("formatting", "Write the word hello in uppercase.", "HELLO"),
    ("formatting", "List the numbers 1, 2, and 3 in ascending order.", "1, 2, 3"),
    ("translation", "Translate 'good morning' to Spanish.", "buenos días"),
    ("translation", "Translate 'thank you' to French.", "merci"),
    ("reasoning", "Explain why testing software before deployment is useful in two sentences.", "bugs"),
    ("reasoning", "Compare a bicycle and a car in one sentence.", "transport"),
    ("code", "Write a Python function that adds two numbers.", "def"),
]

for number in range(1, 21):
    PROMPTS.extend(
        [
            ("math", f"What is {number} plus {number + 7}?", str(number + number + 7)),
            ("math", f"What is {number + 3} multiplied by 2?", str((number + 3) * 2)),
            ("knowledge", f"How many sides does a regular polygon with {number} sides have?", str(number)),
        ]
    )


def answer(config, prompt: str) -> tuple[str, int, int]:
    result = complete(config, [{"role": "user", "content": prompt}], 0.0, 256)
    message = result["choices"][0]["message"]
    usage = result.get("usage", {})
    return (
        message.get("content", ""),
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/router_dataset.jsonl")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=len(PROMPTS))
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    cheap = provider_config("cheap")
    strong = provider_config("strong")
    if not cheap or not strong:
        raise SystemExit("Both provider tiers must be configured in .env")

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line)["prompt"])

    with output.open("a", encoding="utf-8") as file:
        for category, prompt, expected in PROMPTS[: args.limit]:
            if prompt in completed:
                continue
            row = {
                "category": category,
                "prompt": prompt,
                "expected": expected,
                "responses": {},
                "usage": {},
            }
            for tier, config in (("cheap", cheap), ("strong", strong)):
                try:
                    text, input_tokens, output_tokens = answer(config, prompt)
                    row["responses"][tier] = text
                    row["usage"][tier] = {"input": input_tokens, "output": output_tokens}
                except ProviderError as error:
                    row["responses"][tier] = ""
                    row["usage"][tier] = {"error": str(error)}
                time.sleep(args.delay)
            row["labels"] = {
                tier: bool(expected) and expected.lower() in text.lower()
                for tier, text in row["responses"].items()
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            print(f"collected: {category} - {prompt}")


if __name__ == "__main__":
    main()
