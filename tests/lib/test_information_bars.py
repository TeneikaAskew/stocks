"""Hermetic tests for lib/features/information_bars.py.

Pure numpy/pandas — no DB, no network, no repo state. Small synthetic
1-minute OHLCV frames exercise the volume- and dollar-bar resamplers, the
session-boundary flush, the vwap / n_min_bars columns, the threshold
suggester, and the no-silent-fallback skip on a zero-volume session.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from lib.features.information_bars import (
    resample_volume_bars,
    resample_dollar_bars,
    suggest_threshold,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_df(rows: list[dict]) -> pd.DataFrame:
    """Build a 1-min frame from row dicts, filling ts/bar_date conveniently.

    Each row dict must carry: ticker, minute (int offset), open, high, low,
    close, volume, and optionally day (date). ts is derived from day+minute.
    """
    out = []
    for r in rows:
        day = r.get("day", dt.date(2026, 6, 1))
        ts = dt.datetime(day.year, day.month, day.day, 9, 30) + dt.timedelta(
            minutes=r["minute"]
        )
        out.append(
            {
                "ticker": r["ticker"],
                "ts": ts,
                "bar_date": day,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": r["volume"],
            }
        )
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# 1. Volume bars: 3*threshold within one session -> exactly 3 bars, OHLC
#    aggregation invariant.
# --------------------------------------------------------------------------- #
def test_volume_bars_three_clean_bars_and_ohlc():
    # 6 one-min bars; volumes sum to 300 = 3 * threshold(100). Each pair of
    # minutes accumulates to exactly 100 -> 3 emitted bars of 2 minutes each.
    rows = [
        # minute, o, h, l, c, vol
        dict(ticker="SPY", minute=0, open=10, high=12, low=9, close=11, volume=40),
        dict(ticker="SPY", minute=1, open=11, high=13, low=10, close=12, volume=60),  # ->bar1
        dict(ticker="SPY", minute=2, open=12, high=14, low=8, close=13, volume=70),
        dict(ticker="SPY", minute=3, open=13, high=15, low=11, close=14, volume=30),  # ->bar2
        dict(ticker="SPY", minute=4, open=14, high=16, low=12, close=15, volume=50),
        dict(ticker="SPY", minute=5, open=15, high=20, low=7, close=16, volume=50),   # ->bar3
    ]
    df = _mk_df(rows)
    out = resample_volume_bars(df, threshold=100.0)

    assert len(out) == 3

    # bar1: minutes 0-1
    assert out.iloc[0]["open"] == 10
    assert out.iloc[0]["high"] == 13       # max(12,13)
    assert out.iloc[0]["low"] == 9         # min(9,10)
    assert out.iloc[0]["close"] == 12      # last close
    assert out.iloc[0]["volume"] == 100
    assert out.iloc[0]["n_min_bars"] == 2

    # bar2: minutes 2-3
    assert out.iloc[1]["open"] == 12
    assert out.iloc[1]["high"] == 15       # max(14,15)
    assert out.iloc[1]["low"] == 8         # min(8,11)
    assert out.iloc[1]["close"] == 14
    assert out.iloc[1]["volume"] == 100
    assert out.iloc[1]["n_min_bars"] == 2

    # bar3: minutes 4-5
    assert out.iloc[2]["open"] == 14
    assert out.iloc[2]["high"] == 20       # max(16,20)
    assert out.iloc[2]["low"] == 7         # min(12,7)
    assert out.iloc[2]["close"] == 16
    assert out.iloc[2]["volume"] == 100
    assert out.iloc[2]["n_min_bars"] == 2

    # OHLC invariants hold across the whole output.
    for _, b in out.iterrows():
        assert b["high"] >= b["open"]
        assert b["high"] >= b["close"]
        assert b["low"] <= b["open"]
        assert b["low"] <= b["close"]


# --------------------------------------------------------------------------- #
# 2. Dollar bars: analogous, accumulating close*volume.
# --------------------------------------------------------------------------- #
def test_dollar_bars_three_clean_bars_and_ohlc():
    # Construct close*volume sums of exactly 1000 per pair -> 3 bars.
    # pair1: 10*50 + 10*50 = 1000
    # pair2: 20*25 + 20*25 = 1000
    # pair3: 40*10 + 40*15 = 400 + 600 = 1000
    rows = [
        dict(ticker="QQQ", minute=0, open=10, high=11, low=9, close=10, volume=50),
        dict(ticker="QQQ", minute=1, open=10, high=12, low=8, close=10, volume=50),
        dict(ticker="QQQ", minute=2, open=20, high=21, low=19, close=20, volume=25),
        dict(ticker="QQQ", minute=3, open=20, high=22, low=18, close=20, volume=25),
        dict(ticker="QQQ", minute=4, open=40, high=41, low=39, close=40, volume=10),
        dict(ticker="QQQ", minute=5, open=40, high=45, low=35, close=40, volume=15),
    ]
    df = _mk_df(rows)
    out = resample_dollar_bars(df, threshold=1000.0)

    assert len(out) == 3

    assert out.iloc[0]["open"] == 10
    assert out.iloc[0]["high"] == 12
    assert out.iloc[0]["low"] == 8
    assert out.iloc[0]["close"] == 10
    assert out.iloc[0]["volume"] == 100
    assert out.iloc[0]["n_min_bars"] == 2

    assert out.iloc[1]["open"] == 20
    assert out.iloc[1]["high"] == 22
    assert out.iloc[1]["low"] == 18
    assert out.iloc[1]["volume"] == 50

    assert out.iloc[2]["open"] == 40
    assert out.iloc[2]["high"] == 45
    assert out.iloc[2]["low"] == 35
    assert out.iloc[2]["volume"] == 25

    # dollar-volume of each emitted bar is >= threshold (overshoot <= 1 minute)
    for _, b in out.iterrows():
        assert b["vwap"] * b["volume"] >= 1000.0 - 1e-9


# --------------------------------------------------------------------------- #
# 3. Session boundary: day-1 partial remainder emitted on its own, not merged
#    into day 2.
# --------------------------------------------------------------------------- #
def test_session_boundary_flushes_partial():
    d1 = dt.date(2026, 6, 1)
    d2 = dt.date(2026, 6, 2)
    rows = [
        # Day 1: 100 (=threshold) then a 30-vol partial remainder.
        dict(ticker="SPY", minute=0, open=10, high=11, low=9, close=10, volume=100, day=d1),
        dict(ticker="SPY", minute=1, open=10, high=11, low=9, close=10, volume=30, day=d1),
        # Day 2: 100 (=threshold).
        dict(ticker="SPY", minute=0, open=20, high=21, low=19, close=20, volume=100, day=d2),
    ]
    df = _mk_df(rows)
    out = resample_volume_bars(df, threshold=100.0)

    # Expect 3 bars: d1 full(100), d1 partial(30), d2 full(100).
    assert len(out) == 3

    b0, b1, b2 = out.iloc[0], out.iloc[1], out.iloc[2]

    assert b0["bar_date"] == d1 and b0["volume"] == 100 and b0["n_min_bars"] == 1
    # The partial is its own bar on day 1 (NOT merged into day 2).
    assert b1["bar_date"] == d1 and b1["volume"] == 30 and b1["n_min_bars"] == 1
    assert b1["open"] == 10 and b1["close"] == 10
    # Day 2's first bar starts fresh from day-2 data.
    assert b2["bar_date"] == d2 and b2["volume"] == 100
    assert b2["open"] == 20 and b2["close"] == 20


# --------------------------------------------------------------------------- #
# 4. vwap and n_min_bars on a hand-checked example.
# --------------------------------------------------------------------------- #
def test_vwap_and_n_min_bars_hand_checked():
    # Single emitted bar from 3 minutes.
    # closes: 10, 20, 30 ; vols: 100, 100, 100 -> threshold 300 emits 1 bar.
    # vwap = (10*100 + 20*100 + 30*100) / 300 = 6000/300 = 20.0
    rows = [
        dict(ticker="IWM", minute=0, open=10, high=10, low=10, close=10, volume=100),
        dict(ticker="IWM", minute=1, open=20, high=20, low=20, close=20, volume=100),
        dict(ticker="IWM", minute=2, open=30, high=30, low=30, close=30, volume=100),
    ]
    df = _mk_df(rows)
    out = resample_volume_bars(df, threshold=300.0)

    assert len(out) == 1
    assert out.iloc[0]["n_min_bars"] == 3
    assert out.iloc[0]["volume"] == 300
    assert out.iloc[0]["vwap"] == pytest.approx(20.0)

    # Dollar-bar vwap on a non-uniform example:
    # closes: 5, 10 ; vols: 200, 100
    # dollar: 1000 + 1000 = 2000 -> threshold 2000 -> 1 bar
    # vwap = 2000 / 300 = 6.6667
    rows2 = [
        dict(ticker="IWM", minute=0, open=5, high=5, low=5, close=5, volume=200),
        dict(ticker="IWM", minute=1, open=10, high=10, low=10, close=10, volume=100),
    ]
    df2 = _mk_df(rows2)
    out2 = resample_dollar_bars(df2, threshold=2000.0)
    assert len(out2) == 1
    assert out2.iloc[0]["n_min_bars"] == 2
    assert out2.iloc[0]["vwap"] == pytest.approx(2000.0 / 300.0)


# --------------------------------------------------------------------------- #
# 5. suggest_threshold returns median_daily_total / target.
# --------------------------------------------------------------------------- #
def test_suggest_threshold_volume_median_over_target():
    # Three sessions with daily total volumes: 1000, 2000, 3000 -> median 2000.
    # target 4 -> 2000 / 4 = 500.
    rows = []
    for day, total in [
        (dt.date(2026, 6, 1), 1000),
        (dt.date(2026, 6, 2), 2000),
        (dt.date(2026, 6, 3), 3000),
    ]:
        # two minutes each splitting the total
        rows.append(dict(ticker="SPY", minute=0, open=10, high=10, low=10, close=10,
                         volume=total // 2, day=day))
        rows.append(dict(ticker="SPY", minute=1, open=10, high=10, low=10, close=10,
                         volume=total - total // 2, day=day))
    df = _mk_df(rows)

    thr = suggest_threshold(df, bars_per_day_target=4, mode="volume")
    assert thr == pytest.approx(2000.0 / 4)

    # Dollar mode: close is 10 everywhere, so dollar totals are 10x the volume
    # totals -> daily dollar totals 10000/20000/30000, median 20000, /4 = 5000.
    thr_d = suggest_threshold(df, bars_per_day_target=4, mode="dollar")
    assert thr_d == pytest.approx(20000.0 / 4)


def test_suggest_threshold_validates_inputs():
    df = _mk_df(
        [dict(ticker="SPY", minute=0, open=10, high=10, low=10, close=10, volume=100)]
    )
    with pytest.raises(ValueError):
        suggest_threshold(df, bars_per_day_target=0, mode="volume")
    with pytest.raises(ValueError):
        suggest_threshold(df, bars_per_day_target=4, mode="bogus")
    with pytest.raises(ValueError):
        suggest_threshold(df.iloc[0:0], bars_per_day_target=4, mode="volume")


# --------------------------------------------------------------------------- #
# 6. Zero-volume session is skipped (warning), not fabricated.
# --------------------------------------------------------------------------- #
def test_zero_volume_session_skipped(caplog):
    d1 = dt.date(2026, 6, 1)
    d2 = dt.date(2026, 6, 2)
    rows = [
        # Day 1: all zero volume -> must be skipped, no bar.
        dict(ticker="SPY", minute=0, open=10, high=11, low=9, close=10, volume=0, day=d1),
        dict(ticker="SPY", minute=1, open=10, high=11, low=9, close=10, volume=0, day=d1),
        # Day 2: real volume -> emits.
        dict(ticker="SPY", minute=0, open=20, high=21, low=19, close=20, volume=100, day=d2),
    ]
    df = _mk_df(rows)
    with caplog.at_level("WARNING"):
        out = resample_volume_bars(df, threshold=100.0)

    # Only day 2 produced a bar.
    assert len(out) == 1
    assert out.iloc[0]["bar_date"] == d2
    assert out.iloc[0]["volume"] == 100
    # The zero-volume session was warned about, not fabricated.
    assert any("total volume" in rec.message for rec in caplog.records)
    # No fabricated zero-volume bar exists anywhere in the output.
    assert (out["volume"] > 0).all()


def test_zero_volume_dollar_session_skipped():
    # close > 0 but volume 0 -> dollar total 0 -> skipped.
    rows = [
        dict(ticker="SPY", minute=0, open=10, high=11, low=9, close=10, volume=0),
        dict(ticker="SPY", minute=1, open=10, high=11, low=9, close=10, volume=0),
    ]
    df = _mk_df(rows)
    out = resample_dollar_bars(df, threshold=1000.0)
    assert out.empty


# --------------------------------------------------------------------------- #
# Extra: empty input and invalid threshold / missing columns fail loud.
# --------------------------------------------------------------------------- #
def test_empty_input_returns_typed_empty_frame():
    df = _mk_df(
        [dict(ticker="SPY", minute=0, open=10, high=10, low=10, close=10, volume=100)]
    ).iloc[0:0]
    out = resample_volume_bars(df, threshold=100.0)
    assert out.empty
    assert list(out.columns) == [
        "ticker", "ts", "bar_date", "open", "high", "low", "close",
        "volume", "vwap", "n_min_bars",
    ]


def test_invalid_threshold_and_missing_columns_raise():
    df = _mk_df(
        [dict(ticker="SPY", minute=0, open=10, high=10, low=10, close=10, volume=100)]
    )
    with pytest.raises(ValueError):
        resample_volume_bars(df, threshold=0.0)
    with pytest.raises(ValueError):
        resample_volume_bars(df.drop(columns=["volume"]), threshold=100.0)


def test_caller_frame_not_mutated():
    df = _mk_df(
        [
            dict(ticker="SPY", minute=1, open=11, high=12, low=10, close=11, volume=60),
            dict(ticker="SPY", minute=0, open=10, high=11, low=9, close=10, volume=60),
        ]
    )
    before = df.copy(deep=True)
    resample_volume_bars(df, threshold=100.0)
    pd.testing.assert_frame_equal(df, before)
