"""Tests for the extracted Strat label core (gcp.research.strat_engine.strat_dataset).

Locks the session-aware t+1 labeling so it cannot regress (the 2026-05-25
cross-session contamination bug) and proves the pure helper is importable
without the Cloud SQL stack — the property the local combo miner relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.research.strat_engine.strat_dataset import label_next_bar_type  # noqa: E402


def _two_sessions(candles_per_day):
    rows = []
    for d in ("2026-01-02", "2026-01-05"):
        for i, cdl in enumerate(candles_per_day):
            rows.append({"bar_date": d, "ts": pd.Timestamp(f"{d} 09:{30+i:02d}"),
                         "strat_candle": cdl})
    return pd.DataFrame(rows)


def test_label_is_within_session_t_plus_1():
    df = _two_sessions(["2U", "1", "2D", "3", "2U", "1"])
    out = label_next_bar_type(df, "5m", drop_warmup=False)
    # For each session, next_bar_type[i] == strat_candle[i+1]; last bar dropped.
    for d, g in df.groupby("bar_date"):
        g = g.reset_index(drop=True)
        sub = out[out["bar_date"] == d].reset_index(drop=True)
        # out has session length-1 rows (last bar has no within-session next)
        assert len(sub) == len(g) - 1
        for i in range(len(sub)):
            assert sub["next_bar_type"].iloc[i] == g["strat_candle"].iloc[i + 1]


def test_no_cross_session_leak():
    # If labeling leaked across the overnight gap, the last bar of day-1 would
    # be labeled with day-2's first candle. With session-aware shift it's
    # dropped instead. Make day-1 end with a UNIQUE candle and day-2 start with
    # a different unique one; assert that pairing never appears.
    rows = []
    for d, candles in [("2026-01-02", ["2U", "1", "2D", "3", "2U"]),
                       ("2026-01-05", ["1", "2D", "3", "2U", "1"])]:
        for i, c in enumerate(candles):
            rows.append({"bar_date": d, "ts": pd.Timestamp(f"{d} 09:{30+i:02d}"),
                         "strat_candle": c})
    df = pd.DataFrame(rows)
    out = label_next_bar_type(df, "15m", drop_warmup=False)
    last_day1 = out[(out["bar_date"] == "2026-01-02")].tail(1)
    # day-1's surviving last labeled bar is its 2nd-to-last ('3'→'2U'), never
    # '2U'→'1' (which would be the cross-session pairing).
    assert (last_day1["strat_candle"].iloc[0], last_day1["next_bar_type"].iloc[0]) == ("3", "2U")


def test_warmup_drops_first_three_bars():
    df = _two_sessions(["2U", "1", "2D", "3", "2U", "1"])
    out = label_next_bar_type(df, "5m", drop_warmup=True)
    # 6 bars/session: drop first 3 (no prev3) + last (no next) → 2 survive/session.
    assert len(out) == 4
    assert out["prev3_candle"].notna().all()


def test_invalid_classes_filtered():
    df = _two_sessions(["2U", "1", "X", "3", "2U", "Z"])
    out = label_next_bar_type(df, "5m", drop_warmup=False)
    assert set(out["next_bar_type"].unique()) <= {"1", "2U", "2D", "3"}


def test_coarse_tf_uses_cross_bar_shift():
    # 4h is NOT session-aware: prev/next walk across bars regardless of day.
    df = _two_sessions(["2U", "1"])  # only 2 bars/day → session-aware would drop all
    out = label_next_bar_type(df, "4h", drop_warmup=False)
    # cross-bar: 4 bars total, last has no next → 3 labeled rows
    assert len(out) == 3
