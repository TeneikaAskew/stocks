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


def test_data_loader_reads_atr5():
    src = (ROOT / "lib" / "data_loader.py").read_text()
    select = re.search(r"SELECT date, open AS \"Open\".*?FROM market_data_daily", src, re.S).group(0)
    assert re.search(r"\batr_5\b", select)
    assert "'atr_5': 'ATR5'" in src


def test_schema_declares_atr5():
    schema = (ROOT / "gcp" / "schema.sql").read_text()
    assert re.search(r"ALTER TABLE market_data_daily\s+ADD COLUMN IF NOT EXISTS atr_5\s+DOUBLE PRECISION", schema)
