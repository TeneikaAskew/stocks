#!/usr/bin/env python3
"""Emit JSON promotion reports from finalized JSONL evaluation rows."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.promotion_evaluator import PromotionPolicy, evaluate_promotions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rows", type=Path, help="JSONL evaluation rows")
    parser.add_argument("policy", type=Path, help="PromotionPolicy JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text().splitlines() if line.strip()]
    policy = PromotionPolicy(**json.loads(args.policy.read_text()))
    reports = evaluate_promotions(rows, policy)
    if len(reports) != 1:
        parser.error(
            f"expected exactly one ticker/model report, found {len(reports)}; "
            "partition input rows and assign each report its own immutable URI"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports[0], indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
