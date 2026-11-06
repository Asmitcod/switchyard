"""Recompute labels for stored responses using the collector's accepted-answer rules."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.collect_dataset import label_matches


def main() -> None:
    path = ROOT / "data" / "router_dataset.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        row["labels"] = {
            tier: label_matches(row["expected"], response)
            for tier, response in row["responses"].items()
        }
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"relabeled_rows: {len(rows)}")


if __name__ == "__main__":
    main()
