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


ALIASES = {
    "tradeoff": ("tradeoff", "trade off"),
    "validate": ("validate", "validation"),
    "constant": ("constant", "o(1)", "constant time"),
    "duplicate": ("duplicate", "duplicated"),
    "invalid": ("invalid", "stale", "out of date"),
    "monitor": ("monitor", "monitoring", "observability"),
    "unseen": ("unseen", "held out", "generalize"),
    "secret": ("secret", "api key", "credential"),
    "bugs": ("bug", "error", "failure"),
}


def label_matches(expected: str, response: str) -> bool:
    normalized = " ".join(response.lower().split())
    accepted = ALIASES.get(expected.lower(), (expected.lower(),))
    return bool(response.strip()) and any(term in normalized for term in accepted)


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
    ("math", "A train travels 180 kilometers in 3 hours. What is its average speed in kilometers per hour? Show the calculation.", "60"),
    ("math", "If a rectangle has length 12 and width 7, what is its area and perimeter?", "84"),
    ("math", "A shop gives 20 percent off a 150 dollar item. What is the final price?", "120"),
    ("math", "Solve for x: 3x + 7 = 25. Explain each step.", "6"),
    ("math", "A bag has 3 red balls and 2 blue balls. What is the probability of drawing a red ball?", "3/5"),
    ("reasoning", "Explain the difference between correlation and causation with a concrete example.", "causation"),
    ("reasoning", "Give three risks of deploying a machine-learning model without monitoring.", "monitor"),
    ("reasoning", "Explain why a database index can speed up reads but slow down writes.", "write"),
    ("reasoning", "Compare REST and event-driven architecture and give one use case for each.", "event"),
    ("reasoning", "Explain how a cache improves latency and describe one cache invalidation problem.", "invalid"),
    ("code", "Find the bug in this Python code: def add(a, b): return a - b. Explain the fix.", "a + b"),
    ("code", "Write a Python function that returns the largest value in a list without using max.", "for"),
    ("code", "Explain the time complexity of binary search and why the input must be sorted.", "log"),
    ("code", "Debug this loop so it prints numbers 1 through 5: for i in range(1, 5): print(i).", "5"),
    ("code", "Design a function that removes duplicate values from a list while preserving order.", "set"),
    ("reasoning", "A system has a 1 percent failure rate per request. Why can failures still be common at large scale?", "large"),
    ("reasoning", "Explain the difference between authentication and authorization.", "authorization"),
    ("reasoning", "Why should API keys never be committed to a public Git repository?", "secret"),
    ("reasoning", "Describe two strategies for handling a provider timeout in an API proxy.", "retry"),
    ("reasoning", "Explain why a held-out test set is needed when evaluating a machine-learning model.", "unseen"),
]

for number in range(1, 21):
    PROMPTS.extend(
        [
            ("math", f"What is {number} plus {number + 7}?", str(number + number + 7)),
            ("math", f"What is {number + 3} multiplied by 2?", str((number + 3) * 2)),
            ("knowledge", f"How many sides does a regular polygon with {number} sides have?", str(number)),
        ]
    )

for index in range(1, 31):
    PROMPTS.extend(
        [
            ("reasoning", f"Explain one practical tradeoff of caching in a web service, example {index}.", "tradeoff"),
            ("reasoning", f"Explain one reason an API should validate input, example {index}.", "validate"),
            ("code", f"Explain why a Python dictionary lookup is usually fast, example {index}.", "constant"),
            ("code", f"Describe one edge case when removing duplicates from a list, example {index}.", "duplicate"),
            ("math", f"A service receives {index + 2} requests per second for 10 seconds. How many requests arrive?", str((index + 2) * 10)),
        ]
    )


def answer(config, prompt: str) -> tuple[str, int, int]:
    result = complete(config, [{"role": "user", "content": prompt}], 0.0, 768)
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
                row = json.loads(line)
                if all(row.get("responses", {}).get(tier, "").strip() for tier in ("cheap", "strong")):
                    completed.add(row["prompt"])

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
                tier: label_matches(expected, text)
                for tier, text in row["responses"].items()
            }
            if all(row["responses"].get(tier, "").strip() for tier in ("cheap", "strong")):
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
                file.flush()
                print(f"collected: {category} - {prompt}")
            else:
                print(f"retry-needed: {category} - {prompt}")


if __name__ == "__main__":
    main()
