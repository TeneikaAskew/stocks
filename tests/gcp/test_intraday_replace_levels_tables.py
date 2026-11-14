"""A replaced month clears its six levels tables (FEAT-DATA-001, Design G).

``strat_features_levels_{1m,5m,15m,30m,60m,4h}`` are computed from the intraday
feature tables and keyed by ``(ticker, ts)`` like them. A replace that moves a
month's keys would otherwise leave their rows at keys no feature row has, so
the replace hands them over to be cleared in its transaction, beside the nine
tables it already clears.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from gcp.fetchers import fetch_alphavantage_intraday as fai

ON_MAIN = {
    "intraday_flow_15m", "intraday_gex_15m", "realtime_gex_15m",
    "strat_features_1m", "strat_features_5m", "strat_features_15m",
    "strat_features_30m", "strat_features_60m", "strat_features_4h",
}
LEVELS = {f"strat_features_levels_{tf}" for tf in ("1m", "5m", "15m", "30m", "60m", "4h")}


def _vendor_month(days: list[str]) -> pd.DataFrame:
    """fetch_month's shape: naive Eastern ts, one bar per listed day."""
    return pd.DataFrame({
        "ts": [pd.Timestamp(f"{d} 09:30") for d in days],
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })


def test_replace_month_clears_the_six_levels_tables(monkeypatch):
    captured: dict = {}

    def fake_replace(df, table, key, ts_col, start, end, **kw):
        captured.update(kw, table=table)
        return 961, len(df)

    monkeypatch.setattr(
        fai, "fetch_month", lambda *a, **k: (_vendor_month(["2026-09-24"]), fai.FETCH_OK))
    monkeypatch.setattr(fai, "_held_session_dates", lambda *a, **k: {date(2026, 9, 24): 1})
    monkeypatch.setattr(fai, "_held_digest", lambda *a, **k: "digest-0")
    monkeypatch.setattr(fai, "replace_rows_in_window", fake_replace)

    result = fai.replace_month("SPY", 2026, 9, "k", commit=True)

    assert result["status"] == fai.REPLACE_OK
    assert captured["table"] == "market_data_intraday"
    handed = list(captured["clear_tables"])
    assert len(ON_MAIN) == 9 and len(LEVELS) == 6
    assert set(handed) == ON_MAIN | LEVELS
    assert len(handed) == 15                     # no name twice
    assert "market_data_intraday" not in handed  # the bars table is never a clear target
