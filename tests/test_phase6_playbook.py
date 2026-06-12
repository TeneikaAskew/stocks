"""Unit tests for the triggered target/stop/time-stop backtest in
scripts/analysis/phase6_playbook.compute_card_stats.

These lock in the methodology upgrade away from the old "did the next
1-minute bar tick up" proxy (which ignored the card's own target/stop).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.analysis.phase6_playbook import (
    compute_card_stats, generate_card, write_playbook_cards,
)

TARGET_BPS = 30.0   # +0.30%
STOP_BPS = 15.0     # -0.15%
ENTRY = 100.0
TGT_PX = ENTRY * (1 + TARGET_BPS / 1e4)   # 100.30
STP_PX = ENTRY * (1 - STOP_BPS / 1e4)     # 99.85


def _bars(rows, start="2026-06-01 09:30"):
    """rows: list of (open, high, low, close). Single RTH session."""
    idx = pd.date_range(start, periods=len(rows), freq="1min")
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
    df["Volume"] = 1
    return df


def _mask(df, positions):
    m = pd.Series(False, index=df.index)
    for p in positions:
        m.iloc[p] = True
    return m


def _stats(df, mask, direction="CALL", time_stop_min=30):
    return compute_card_stats(df, pd.Series("2U", index=df.index), mask,
                              direction, TARGET_BPS, STOP_BPS, time_stop_min)


def test_no_occurrence_returns_count_zero():
    df = _bars([(100, 100, 100, 100)] * 3)
    out = _stats(df, _mask(df, []))
    assert out == {"count": 0}


def test_target_before_stop_is_a_win():
    # entry bar (pos 0) close 100; next bar tags the target, never the stop
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.35, 99.95, 100.3),  # hits 100.30 target, low stays > 99.85
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["resolved"] == 1
    assert out["win_rate"] == 1.0
    assert out["avg_return_bps"] == pytest.approx(TARGET_BPS)


def test_stop_before_target_is_a_loss():
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.05, 99.80, 99.85),  # hits 99.85 stop, never 100.30
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["win_rate"] == 0.0
    assert out["avg_return_bps"] == pytest.approx(-STOP_BPS)


def test_same_bar_target_and_stop_assumes_stop():
    # both target and stop inside one bar -> pessimistic: stop counted
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.40, 99.80, 100.0),  # high>=tgt AND low<=stop
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["win_rate"] == 0.0
    assert out["avg_return_bps"] == pytest.approx(-STOP_BPS)


def test_time_stop_marks_to_close():
    # neither target nor stop touched within time_stop_min -> mark to close
    df = _bars([
        (100, 100, 100, 100),          # entry
        (100, 100.10, 99.95, 100.05),  # drift
        (100, 100.12, 99.95, 100.10),  # close here at time stop
    ])
    out = _stats(df, _mask(df, [0]), "CALL", time_stop_min=2)
    assert out["resolved"] == 1
    # marked to close at 100.10 -> +10 bps, a win
    assert out["avg_return_bps"] == pytest.approx(10.0, abs=0.5)
    assert out["win_rate"] == 1.0


def test_put_direction_mirrors():
    # PUT target is price DOWN; this bar drops to the put target
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.05, 99.65, 99.70),  # low 99.65 <= 100*(1-30bps)=99.70 target
    ])
    out = _stats(df, _mask(df, [0]), "PUT")
    assert out["win_rate"] == 1.0
    assert out["avg_return_bps"] == pytest.approx(TARGET_BPS)


def test_insufficient_forward_bars_are_skipped_not_zeroed():
    # entry on the LAST bar -> no forward bar -> excluded from denominator
    df = _bars([(100, 100, 100, 100), (100, 100, 100, 100)])
    out = _stats(df, _mask(df, [1]), "CALL")
    assert out["count"] == 1
    assert out["resolved"] == 0
    assert out["skipped_insufficient_bars"] == 1
    assert np.isnan(out["win_rate"])        # NOT coerced to 0 (CLAUDE.md 3.7)


def test_overnight_gap_does_not_leak_into_trade():
    # entry at end of session 1; session 2 gaps up past target. The gap must
    # NOT count -- there are no same-session forward bars, so it's skipped.
    idx = pd.to_datetime([
        "2026-06-01 15:59",   # entry (last bar of day 1)
        "2026-06-02 09:30",   # next day open, gaps to 101 (would be a win)
        "2026-06-02 09:31",
    ])
    df = pd.DataFrame(
        [(100, 100, 100, 100), (101, 101.5, 101, 101.4), (101.4, 101.6, 101.3, 101.5)],
        columns=["Open", "High", "Low", "Close"], index=idx)
    df["Volume"] = 1
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["resolved"] == 0
    assert out["skipped_insufficient_bars"] == 1


# ---------------------------------------------------------------------------
# Structured-record path (playbook_cards table) — the typed source of truth
# that replaces regex-scraping the markdown.
# ---------------------------------------------------------------------------

_GOOD_STATS = {
    "count": 100, "resolved": 90, "win_rate": 0.48, "avg_return_bps": -0.10,
    "confidence": "Moderate", "avg_mfe": 12.0, "avg_mae": -8.0,
}


def _card(stats, direction="CALL"):
    return generate_card(
        1, "Bullish Continuation (2U-2U-2U)", "IWM",
        "  * Daily bar is 2U\n  * 15m bar is 2U\n  * 1m shows: 2U -> 2U -> 2U",
        ["RSI between 40-65", "Price above VWAP"],
        direction, stats, "+0.30%", "-0.15%", "10-15 min",
        ["RSI > 75 -> take profit"], ["IWM mean-reverts more"],
    )


def test_generate_card_returns_markdown_and_record():
    md, rec = _card(_GOOD_STATS)
    assert isinstance(md, str) and "IWM CARD 1" in md           # markdown intact
    assert rec["card_num"] == 1
    assert rec["name"] == "IWM CARD 1: Bullish Continuation (2U-2U-2U)"
    assert rec["direction"] == "CALL"
    assert rec["win_rate"] == pytest.approx(0.48)               # fraction, not %
    assert rec["avg_return_bps"] == pytest.approx(-0.10)
    assert rec["sample_n"] == 90
    assert rec["conditions"] == ["RSI between 40-65", "Price above VWAP"]
    assert "Daily bar is 2U" in rec["description"]
    assert rec["target_pct"] == "+0.30%" and rec["stop_pct"] == "-0.15%"


def test_generate_card_record_keeps_missing_as_none_not_zero():
    # Unresolved pattern -> NaN stats must surface as None, never 0 (3.7).
    stats = {"count": 5, "resolved": 0, "win_rate": float("nan"),
             "avg_return_bps": float("nan"), "confidence": "Low",
             "avg_mfe": float("nan"), "avg_mae": float("nan")}
    _md, rec = _card(stats, "PUT")
    assert rec["win_rate"] is None
    assert rec["avg_return_bps"] is None
    assert rec["sample_n"] is None
    assert rec["avg_mfe_bps"] is None and rec["avg_mae_bps"] is None


def test_write_playbook_cards_upserts_typed_rows(monkeypatch):
    import gcp.database as dbmod
    captured = {}

    def fake_upsert(df, table, conflict_cols, **kw):
        captured["df"] = df
        captured["table"] = table
        captured["conflict"] = conflict_cols
        return len(df)

    monkeypatch.setattr(dbmod, "upsert_dataframe", fake_upsert)

    _md, rec = _card(_GOOD_STATS)
    n = write_playbook_cards("iwm", [rec])

    assert n == 1
    assert captured["table"] == "playbook_cards"
    assert captured["conflict"] == ["ticker", "card_num"]
    row = captured["df"].iloc[0]
    assert row["ticker"] == "IWM"                      # upper-cased
    assert row["card_num"] == 1
    # conditions passed as a Python list so the reflected JSONB column
    # serializes it exactly once (no double-encoding).
    assert row["conditions"] == ["RSI between 40-65", "Price above VWAP"]
    assert row["win_rate"] == pytest.approx(0.48)


def test_write_playbook_cards_empty_is_noop(monkeypatch):
    import gcp.database as dbmod
    called = {"n": 0}
    monkeypatch.setattr(dbmod, "upsert_dataframe",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    assert write_playbook_cards("IWM", []) == 0
    assert called["n"] == 0                              # never touched the DB
