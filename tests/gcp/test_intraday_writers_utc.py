"""Every writer to market_data_intraday stores true UTC instants.

CLAUDE.md 3.9: two writers stored AlphaVantage's naive Eastern wall time
straight into the TIMESTAMPTZ ``ts`` column, where Postgres (TimeZone=UTC)
read it as UTC. The Eastern-labelled 13:30 bar then landed on the key of the
true 09:30 bar and overwrote it, so the table held two conventions and lost
bars wherever they collided. These tests pin the conversion at each writer and
the backstop in ``gcp.database`` that refuses a naive ``ts`` for the table.

AV fixture stamps below are naive Eastern, exactly as the vendor returns them.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

EDT_OPEN_ET = "2026-09-24 09:30:00"   # EDT: 13:30Z
EST_OPEN_ET = "2026-01-15 09:30:00"   # EST: 14:30Z


def _av_frame(stamps: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 10},
        index=pd.to_datetime(stamps),
    )
    return df


def _intraday_calls(mock_upsert: MagicMock) -> list[pd.DataFrame]:
    return [c.args[0] for c in mock_upsert.call_args_list
            if len(c.args) > 1 and c.args[1] == "market_data_intraday"]


# ── W1: gcp/fetchers/fetch_market_data.write_intraday_to_sql ─────────────────


@pytest.mark.parametrize("stamp,expected", [
    (EDT_OPEN_ET, pd.Timestamp("2026-09-24 13:30", tz="UTC")),
    (EST_OPEN_ET, pd.Timestamp("2026-01-15 14:30", tz="UTC")),
])
def test_fetch_market_data_writes_utc_instants(stamp, expected):
    import gcp.fetchers.fetch_market_data as mod

    with patch.object(mod, "upsert_dataframe") as up:
        mod.write_intraday_to_sql("SPY", _av_frame([stamp]), stamp[:10])
    (written,) = _intraday_calls(up)
    ts = pd.DatetimeIndex(written["ts"])
    assert str(ts.tz) == "UTC", "ts must be tz-aware UTC, not naive Eastern"
    assert ts[0] == expected


def test_fetch_market_data_refuses_an_already_aware_vendor_index():
    """An aware index is an instant; relabelling it by dropping the zone is
    exactly how the bug was written. It must raise, not guess."""
    import gcp.fetchers.fetch_market_data as mod

    df = _av_frame([EDT_OPEN_ET])
    df.index = df.index.tz_localize("UTC")
    with patch.object(mod, "upsert_dataframe"), pytest.raises(ValueError):
        mod.write_intraday_to_sql("SPY", df, "2026-09-24")


# ── W3: gcp/backfill_ticker.run (Discord /replay, backfill_and_replay) ───────


def test_backfill_ticker_writes_utc_instants(monkeypatch):
    import gcp.backfill_ticker as mod

    monkeypatch.setenv("BACKFILL_TICKER", "amd")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("BACKFILL_DATES", "2026-09-24")
    monkeypatch.setenv("BACKFILL_INCLUDE_NEWS", "false")
    monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", "false")
    daily = pd.DataFrame({
        "date": [date(2026, 9, 23), date(2026, 9, 24)],
        "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
        "close": [1.0, 1.0], "adjusted_close": [1.0, 1.0], "volume": [1, 1],
    })
    up = MagicMock()
    with patch.object(mod, "av_daily_full", return_value=daily), \
         patch.object(mod, "av_intraday_month", return_value=_av_frame([EDT_OPEN_ET])), \
         patch.object(mod, "compute_indicators_for_full_range", return_value=0), \
         patch.object(mod, "compute_indicators_for_dates"), \
         patch("gcp.database.upsert_dataframe", up):
        assert mod.run() == 0
    written = _intraday_calls(up)
    assert written, "backfill_ticker wrote no intraday rows"
    for df in written:
        ts = pd.DatetimeIndex(df["ts"])
        assert str(ts.tz) == "UTC"
        assert ts[0] == pd.Timestamp("2026-09-24 13:30", tz="UTC")


# ── Backstop: gcp.database refuses naive ts for market_data_intraday ─────────


@pytest.mark.parametrize("writer", ["upsert_dataframe", "bulk_copy_upsert", "bulk_insert_dataframe"])
def test_database_refuses_naive_intraday_ts(writer):
    import gcp.database as db

    df = pd.DataFrame({
        "ticker": ["SPY"], "interval": ["1min"],
        "ts": pd.to_datetime([EDT_OPEN_ET]),   # naive
        "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1],
    })
    fn = getattr(db, writer)
    args = (df, "market_data_intraday") + ((["ticker", "interval", "ts"],)
                                           if writer != "bulk_insert_dataframe" else ())
    with patch.object(db, "get_engine", side_effect=AssertionError("must fail before any DB call")), \
         pytest.raises(ValueError, match="naive"):
        fn(*args)


def test_database_accepts_utc_intraday_ts_and_ignores_other_tables():
    import gcp.database as db

    aware = pd.DataFrame({"ts": pd.to_datetime([EDT_OPEN_ET]).tz_localize("UTC")})
    naive_other = pd.DataFrame({"date": pd.to_datetime(["2026-09-24"])})
    db._require_utc_ts(aware, "market_data_intraday")      # no raise
    db._require_utc_ts(naive_other, "market_data_daily")   # other tables untouched
