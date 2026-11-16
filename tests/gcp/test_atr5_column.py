"""FEAT-STRAT-001 per-ticker params, done_when 6: ATR(5) stored next to ATR(14).

* add_all_indicators emits ATR5 (IndicatorConfig.atr_extra_periods holds 5).
* The nightly fetcher's indicator row builder
  (gcp.fetchers.fetch_market_data.compute_and_upsert_daily_indicators)
  writes market_data_daily.atr_5 equal to
  lib.indicators.calculate_atr(high, low, close, 5) on the committed daily
  fixture, through gcp.database.DAILY_INDICATOR_TO_SQL_COLUMN.
* backfill-daily-indicators checks atr_5 for gaps in its short warmup class.
* lib.data_loader reads atr_5 back as ATR5.
* gcp/schema.sql declares the column.

On the #1753 head none of this exists.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from tests.lib import strat_2026_11_06 as fx

ROOT = Path(__file__).resolve().parents[2]


def test_indicator_config_emits_atr5():
    from lib.config import IndicatorConfig
    from lib.indicators import add_all_indicators, calculate_atr

    assert 5 in IndicatorConfig().atr_extra_periods
    d = fx.daily("SPY").reset_index(drop=True)
    out = add_all_indicators(d[["Open", "High", "Low", "Close", "Volume"]].copy(), close_col="Close")
    expected = calculate_atr(d["High"], d["Low"], d["Close"], 5)
    assert out["ATR5"].iloc[-1] == pytest.approx(float(expected.iloc[-1]))


def test_sql_column_map_carries_atr5():
    from gcp.database import DAILY_INDICATOR_TO_SQL_COLUMN

    assert DAILY_INDICATOR_TO_SQL_COLUMN["ATR5"] == "atr_5"


def test_nightly_row_builder_writes_atr5(monkeypatch):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd
    from lib.indicators import calculate_atr

    d = fx.daily("QQQ")
    bars = pd.DataFrame({
        "date": [ts.date() for ts in d.index], "Open": d["Open"].values, "High": d["High"].values,
        "Low": d["Low"].values, "Close": d["Close"].values, "Volume": d["Volume"].values,
    })
    fetch_date = str(d.index[-1].date())

    def fake_query(sql, params=None):
        if "market_data_intraday" in sql:
            return pd.DataFrame()
        # The builder reads newest-first, LIMIT 250.
        return bars.iloc[::-1].head(250).reset_index(drop=True)

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", fake_query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys, **k: written.append((table, df)) or len(df))
    fmd.compute_and_upsert_daily_indicators("QQQ", fetch_date)
    (table, df), = written
    assert table == "market_data_daily"
    window = bars.tail(250)
    expected = calculate_atr(window["High"], window["Low"], window["Close"], 5).iloc[-1]
    assert df.iloc[0]["atr_5"] == pytest.approx(float(expected))
    assert df.iloc[0]["atr_14"] == pytest.approx(
        float(calculate_atr(window["High"], window["Low"], window["Close"], 14).iloc[-1]))


def test_backfill_gap_list_contains_atr5():
    from gcp.fetchers import backfill_daily_indicators as bdi

    assert "atr_5" in bdi._DERIVED_COLS_FOR_GAP_CHECK
    assert "atr_5" in bdi._WARMUP_SHORT_COLS


def _loader(monkeypatch, answer):
    """A DataLoader whose Cloud SQL reads go to `answer(sql)`, with the
    optional-column flags reset; returns (loader, the SQL it sent)."""
    from lib import data_loader as dl
    monkeypatch.setattr(dl, "_PREMARKET_PROVENANCE_PRESENT", None)
    monkeypatch.setattr(dl, "_ATR5_PRESENT", None, raising=False)
    calls = []
    monkeypatch.setattr(dl, "_query_cloud_sql",
                        lambda sql, params=None: calls.append(sql) or answer(sql))
    return dl.DataLoader.__new__(dl.DataLoader), calls


_ROW = {"date": "2026-11-05", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5,
        "Volume": 10, "atr_14": 0.4, "pre_high": None}


def test_data_loader_reads_atr5(monkeypatch):
    loader, calls = _loader(monkeypatch, lambda sql: pd.DataFrame([{**_ROW, "atr_5": 0.3}]))
    df = loader._load_daily_from_sql("QQQ", None)
    assert re.search(r"\batr_5\b", calls[0])
    assert df["ATR5"].iloc[-1] == pytest.approx(0.3) and df["ATR14"].iloc[-1] == pytest.approx(0.4)


def test_data_loader_without_the_atr5_column_reads_null_atr5(monkeypatch):
    """Code that ships before market_data_daily.atr_5 exists: a query naming
    atr_5 fails (the reader answers empty), and load_daily must still return
    the bars, with ATR5 null, not an empty frame (the provenance columns'
    rule). Once known missing, atr_5 is not asked for again."""
    from lib import data_loader as dl

    def answer(sql):
        if "information_schema" in sql:
            # The table's column list: provenance yes, atr_5 no.
            return pd.DataFrame({"column_name": ["date", "pre_fetched_at"]})
        return pd.DataFrame() if re.search(r"\batr_5\b", sql) else pd.DataFrame([_ROW])

    loader, calls = _loader(monkeypatch, answer)
    df = loader._load_daily_from_sql("QQQ", None)
    calls[:] = [c for c in calls if "information_schema" not in c]
    assert len(df) == 1 and df["Close"].iloc[-1] == pytest.approx(1.5)
    assert "ATR5" in df.columns and df["ATR5"].isna().all()
    assert df["ATR14"].iloc[-1] == pytest.approx(0.4)
    assert dl._ATR5_PRESENT is False
    # The provenance columns were still asked for, and the table has them.
    assert dl._PREMARKET_PROVENANCE_PRESENT is True
    calls.clear()
    loader._load_daily_from_sql("QQQ", None)
    assert len(calls) == 1 and not re.search(r"\batr_5\b", calls[0])
    assert "pre_fetched_at" in calls[0]


def test_data_loader_transient_error_keeps_atr5_unknown(monkeypatch):
    """Codex P2 on #1784: the queries naming atr_5 hit a transient error
    (the reader answers empty for every error) and the narrower one
    succeeds. With the column-list probe failing too, atr_5 must stay
    unknown, not cached missing, so the next read asks for it again and
    gets ATR5 once the database recovers."""
    from lib import data_loader as dl
    outage = {"on": True}

    def answer(sql):
        if outage["on"] and (re.search(r"\batr_5\b", sql) or "information_schema" in sql):
            return pd.DataFrame()
        if "information_schema" in sql:
            return pd.DataFrame({"column_name": ["date", "pre_fetched_at", "atr_5"]})
        row = dict(_ROW)
        if re.search(r"\batr_5\b", sql):
            row["atr_5"] = 0.3
        return pd.DataFrame([row])

    loader, calls = _loader(monkeypatch, answer)
    df = loader._load_daily_from_sql("QQQ", None)
    assert len(df) == 1 and df["ATR5"].isna().all()
    assert dl._ATR5_PRESENT is None
    outage["on"] = False
    calls.clear()
    df = loader._load_daily_from_sql("QQQ", None)
    assert len(calls) == 1 and re.search(r"\batr_5\b", calls[0])
    assert df["ATR5"].iloc[-1] == pytest.approx(0.3)
    assert dl._ATR5_PRESENT is True


def test_data_loader_empty_ticker_learns_nothing(monkeypatch):
    """A ticker with no rows answers empty to every query: the frame is
    empty and neither optional column is marked missing."""
    from lib import data_loader as dl
    loader, _calls = _loader(monkeypatch, lambda sql: pd.DataFrame())
    assert loader._load_daily_from_sql("ZZZ", None).empty
    assert dl._ATR5_PRESENT is None and dl._PREMARKET_PROVENANCE_PRESENT is None


def test_schema_declares_atr5():
    schema = (ROOT / "gcp" / "schema.sql").read_text()
    assert re.search(r"ALTER TABLE market_data_daily\s+ADD COLUMN IF NOT EXISTS atr_5\s+DOUBLE PRECISION", schema)
