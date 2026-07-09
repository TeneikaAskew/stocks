"""Append-only JSONL ledger of every experiment slice tested, so the synthesis
step can apply a multiple-comparisons correction. One row per (slice, ticker)."""
from __future__ import annotations
import json
import os


class SliceLedger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, slice_id, *, lever, target, conditioning, feature_set,
               ticker, fold_beats, meta=None) -> None:
        beats = [b for b in fold_beats if b is not None]
        row = {
            "slice_id": slice_id, "lever": lever, "target": target,
            "conditioning": conditioning, "feature_set": feature_set,
            "ticker": ticker, "fold_beats": list(fold_beats),
            "n_folds_beat": sum(1 for b in beats if b > 0),
            "meta": meta or {},
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def rows(self) -> list:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
