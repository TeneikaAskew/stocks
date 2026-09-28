"""Hermetic tests for the timeframe_tag backfill script.

Coverage:
  1. assign_timeframe_for_backfill — every branch of the approximate heuristic
  2. apply_tags — vectorized over a synthetic DataFrame
  3. parse_args — flag handling
  4. apply_tags handles NaN / None ATR gracefully
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.timeframe import (  # noqa: E402
    HIGH_ATR_5M_PCT,
    STRONG_CONFIRMATION,
    assign_timeframe_for_backfill,
)
from scripts.backfill_timeframe_tags import apply_tags, parse_args  # noqa: E402


# ── 1) assign_timeframe_for_backfill — every branch ──────────────────

def test_high_vol_strong_confirmation_gives_15m():
    tag, hold = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=STRONG_CONFIRMATION,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "15m"
    assert hold == 15


def test_high_vol_weak_confirmation_gives_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=STRONG_CONFIRMATION - 1,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


def test_mean_reversion_at_avg_vol_gives_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="mean_reversion", signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "30m"


def test_momentum_at_avg_vol_gives_15m():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "15m"


def test_unknown_strategy_at_avg_vol_falls_through_to_30m():
    tag, _ = assign_timeframe_for_backfill(
        strategy=None, signal_strength=3, atr_5m_pct=0.002,
    )
    assert tag == "30m"


def test_no_atr_treated_as_avg_vol():
    """Missing ATR shouldn't force the high-vol branch — falls through
    to strategy-default."""
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=5, atr_5m_pct=None,
    )
    assert tag == "15m"   # momentum at avg vol


def test_zero_signal_strength_doesnt_qualify_as_strong():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=0,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


def test_none_signal_strength_treated_as_zero():
    tag, _ = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=None,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "30m"


# ── 2) apply_tags — vectorized over DataFrame ────────────────────────

def test_apply_tags_populates_columns_per_row():
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 4, "atr_5m_pct": 0.005},
        {"ticker": "QQQ", "entry_time": "2026-04-29 14:31",
         "strategy": "mean_reversion", "signal_strength": 3, "atr_5m_pct": 0.002},
    ])
    out = apply_tags(df)
    assert "timeframe_tag" in out.columns
    assert "expected_hold_min" in out.columns
    assert out["timeframe_tag"].iloc[0] == "15m"
    assert out["expected_hold_min"].iloc[0] == 15
    assert out["timeframe_tag"].iloc[1] == "30m"
    assert out["expected_hold_min"].iloc[1] == 30


def test_apply_tags_empty_df_returns_empty():
    out = apply_tags(pd.DataFrame())
    assert out.empty


def test_apply_tags_handles_nan_atr():
    """signal_metrics may not exist for some rows → atr_5m_pct comes
    back as NaN from the LEFT JOIN. Must not crash."""
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 5, "atr_5m_pct": np.nan},
    ])
    out = apply_tags(df)
    # NaN ATR → NOT high vol, momentum strategy → 15m (default)
    assert out["timeframe_tag"].iloc[0] == "15m"


def test_apply_tags_handles_none_atr():
    df = pd.DataFrame([
        {"ticker": "SPY", "entry_time": "2026-04-29 14:30",
         "strategy": "momentum", "signal_strength": 5, "atr_5m_pct": None},
    ])
    out = apply_tags(df)
    assert out["timeframe_tag"].iloc[0] == "15m"


# ── 3) parse_args ────────────────────────────────────────────────────

def test_parse_args_defaults():
    args = parse_args([])
    assert args.tickers == ""
    assert args.limit is None
    assert args.chunk_size == 1000
    assert args.dry_run is False


def test_parse_args_with_tickers_and_limit():
    args = parse_args(["--tickers", "SPY,QQQ", "--limit", "100",
                       "--chunk-size", "50", "--dry-run"])
    assert args.tickers == "SPY,QQQ"
    assert args.limit == 100
    assert args.chunk_size == 50
    assert args.dry_run is True


# ── 4) --retag: rewrite existing tags after the lookup was retired (#1167) ──

import scripts.backfill_timeframe_tags as backfill  # noqa: E402


def _rows_with_old_tags():
    return pd.DataFrame([
        # The retired table tagged this momentum row 60m; the placeholder says 15m.
        {"ticker": "SPY", "entry_time": pd.Timestamp("2026-05-01 14:00", tz="UTC"),
         "strategy": "momentum", "signal_strength": 3, "entry_rsi": 50.0,
         "atr_5m_pct": 0.002, "old_tag": "60m", "old_hold": 60},
        # Already on the placeholder's answer: nothing to write.
        {"ticker": "QQQ", "entry_time": pd.Timestamp("2026-05-01 14:05", tz="UTC"),
         "strategy": "mean_reversion", "signal_strength": 3, "entry_rsi": 25.0,
         "atr_5m_pct": 0.002, "old_tag": "30m", "old_hold": 30},
        # Never tagged: a retag still fills it.
        {"ticker": "IWM", "entry_time": pd.Timestamp("2026-05-01 14:10", tz="UTC"),
         "strategy": "momentum", "signal_strength": 5, "entry_rsi": None,
         "atr_5m_pct": 0.005, "old_tag": None, "old_hold": None},
    ])


def test_parse_args_retag_defaults_off():
    assert parse_args([]).retag is False
    assert parse_args(["--retag"]).retag is True


def test_changed_rows_keeps_only_rows_whose_tag_or_hold_changes():
    df = backfill.changed_rows(apply_tags(_rows_with_old_tags()))
    assert list(df["ticker"]) == ["SPY", "IWM"]
    assert list(df["timeframe_tag"]) == ["15m", "15m"]


def test_fetch_selects_tagged_rows_only_when_retagging(monkeypatch):
    seen = []
    monkeypatch.setattr(backfill.pd, "read_sql",
                        lambda sql, engine, params=None: seen.append(str(sql)) or pd.DataFrame())
    backfill.fetch_rows_to_backfill(object())
    backfill.fetch_rows_to_backfill(object(), retag=True)
    assert "timeframe_tag IS NULL" in seen[0]
    assert "timeframe_tag IS NULL" not in seen[1]
    assert "AS old_tag" in seen[1] and "AS old_hold" in seen[1]


def _run_main(monkeypatch, argv):
    writes = []
    monkeypatch.setattr("gcp.database.get_engine", lambda: object())
    monkeypatch.setattr(backfill, "fetch_rows_to_backfill",
                        lambda engine, tickers=None, limit=None, retag=False: _rows_with_old_tags())
    monkeypatch.setattr(backfill, "upsert_chunk",
                        lambda engine, chunk: writes.append(chunk.copy()) or len(chunk))
    return backfill.main(argv), writes


def test_retag_dry_run_writes_nothing(monkeypatch):
    rc, writes = _run_main(monkeypatch, ["--retag", "--dry-run"])
    assert rc == 0 and writes == []


def test_retag_writes_only_the_rows_that_change(monkeypatch):
    rc, writes = _run_main(monkeypatch, ["--retag"])
    assert rc == 0
    written = pd.concat(writes)
    assert sorted(written["ticker"]) == ["IWM", "SPY"]


def test_a_staged_retag_reaches_every_stale_row(monkeypatch):
    """Codex on #1207: with --retag, --limit went to the SQL before the
    unchanged rows were filtered out. Once the first rows were current, every
    staged run selected them again and never reached the stale rows after
    them. The limit bounds the rows a run writes instead."""
    table = _rows_with_old_tags()
    # The earliest row is already current; the stale ones come after it.
    table.loc[table["ticker"] == "QQQ", "entry_time"] = pd.Timestamp("2026-05-01 13:55", tz="UTC")
    written = []

    def fetch(engine, tickers=None, limit=None, retag=False):
        rows = (table if retag else table[table["old_tag"].isna()]).sort_values("entry_time")
        return (rows.head(limit) if limit else rows).reset_index(drop=True)

    def upsert(engine, chunk):
        for _, r in chunk.iterrows():
            hit = (table["ticker"] == r["ticker"]) & (table["entry_time"] == r["entry_time"])
            table.loc[hit, ["old_tag", "old_hold"]] = [r["timeframe_tag"], r["expected_hold_min"]]
        written.append(len(chunk))
        return len(chunk)

    monkeypatch.setattr("gcp.database.get_engine", lambda: object())
    monkeypatch.setattr(backfill, "fetch_rows_to_backfill", fetch)
    monkeypatch.setattr(backfill, "upsert_chunk", upsert)
    for _ in range(3):
        assert backfill.main(["--retag", "--limit", "1"]) == 0
    assert backfill.changed_rows(apply_tags(table)).empty
    assert written == [1, 1]
