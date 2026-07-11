"""Pre-registered success gate for the direction-predictability program.

A slice is PREDICTABLE iff it beats the base-rate constant (log-loss beat > 0)
in >= min_folds of `total` folds AND replicates on all required tickers.
"""
from __future__ import annotations


def slice_passes_folds(fold_beats, min_folds: int = 6, total: int = 8) -> bool:
    beats = [b for b in fold_beats if b is not None]
    return sum(1 for b in beats if b > 0) >= min_folds


def slice_predictable(per_ticker_beats, min_folds: int = 6, total: int = 8,
                      tickers=("IWM", "SPY", "QQQ")) -> dict:
    per = {tk: slice_passes_folds(per_ticker_beats.get(tk, []), min_folds, total)
           for tk in tickers}
    return {"predictable": all(per.values()),
            "per_ticker_pass": per,
            "n_tickers_pass": sum(per.values())}
