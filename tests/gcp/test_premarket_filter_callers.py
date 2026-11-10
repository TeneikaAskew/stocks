"""FEAT-STRAT-001 done_when 4, caller level: both production writers of the
premarket columns (gcp/fetchers/fetch_market_data.py nightly and
gcp/fetchers/fetch_premarket_refresh.py at 08:20 ET) filter the session's
prints with the LAST COMPLETED session's close, open and ATR(14), and the
ticker's own pm_stale_print_atr and pm_spike_atr (here at the #1753 values,
level_params_fixtures.fixture_params).

Each caller runs its own SQL against an in-memory SQLite market_data_daily
and market_data_intraday loaded with the committed 2026-11-06 bars, so the
row it reads is the row its WHERE clause picks. Changing the fetch date's
own OHLC (and so the fetch date's ATR) leaves the filtered values unchanged.

On origin/main both fail: the nightly caller read the fetch date's
`atr_14` key from a frame whose column is ATR14 (always None, no filter),
and the refresh passed atr14=None.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pandas as pd
import pytest

from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import fixture_params

SESSION = fx.SESSION
EXPECTED = {"SPY": (738.04, 730.64), "QQQ": (660.398, 649.62), "IWM": (272.50, 269.13)}


def _sql_param(v):
    if isinstance(v, pd.Timestamp) or isinstance(v, datetime):
        ts = pd.Timestamp(v)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return v


class _Db:
    """market_data_daily and market_data_intraday in SQLite, queried with
    the caller's own SQL text."""

    def __init__(self, ticker: str, *, session_row: dict | None = None,
                 session_atr: float | None = None):
        self.conn = sqlite3.connect(":memory:")
        full = fx.daily(ticker, through=SESSION)
        atr = fx.wilder_atr(full)
        from lib.indicators import calculate_atr
        atr5 = calculate_atr(full["High"], full["Low"], full["Close"], 5)
        rows = []
        for ts, r in full.iterrows():
            d = ts.date()
            o, h, lo, c = r["Open"], r["High"], r["Low"], r["Close"]
            a = float(atr.loc[ts]) if pd.notna(atr.loc[ts]) else None
            if d == SESSION:
                if session_row is not None:
                    o, h, lo, c = (session_row[k] for k in ("Open", "High", "Low", "Close"))
                if session_atr is not None:
                    a = session_atr
            a5 = float(atr5.loc[ts]) if pd.notna(atr5.loc[ts]) else None
            rows.append((ticker, d.isoformat(), o, h, lo, c, float(r["Volume"]), a, a5))
        self.conn.execute("CREATE TABLE market_data_daily (ticker TEXT, date TEXT, open REAL, "
                          "high REAL, low REAL, close REAL, volume REAL, atr_14 REAL, atr_5 REAL)")
        self.conn.executemany("INSERT INTO market_data_daily VALUES (?,?,?,?,?,?,?,?,?)", rows)
        bars = fx.premarket_bars(ticker)
        utc = bars["timestamp"].dt.tz_localize("America/New_York").dt.tz_convert("UTC").dt.tz_localize(None)
        self.conn.execute("CREATE TABLE market_data_intraday (ticker TEXT, interval TEXT, ts TEXT, "
                          "open REAL, high REAL, low REAL, close REAL, volume REAL)")
        self.conn.executemany(
            "INSERT INTO market_data_intraday VALUES (?,?,?,?,?,?,?,?)",
            [(ticker, "1min", t.strftime("%Y-%m-%d %H:%M:%S"), o, h, lo, c, v)
             for t, o, h, lo, c, v in zip(utc, bars["open"], bars["high"], bars["low"],
                                          bars["close"], bars["volume"])])

    def query(self, sql, params=None):
        p = {k: _sql_param(v) for k, v in (params or {}).items()}
        df = pd.read_sql_query(sql, self.conn, params=p)
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("UTC")
        return df


def _run_nightly(monkeypatch, ticker, db: _Db) -> dict:
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    monkeypatch.setattr(fmd, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    fmd.compute_and_upsert_daily_indicators(ticker, SESSION.isoformat(),
                                            level_params=fixture_params(ticker, SESSION))
    rows = [r for t, r in written if t == "market_data_daily"]
    assert rows, "nothing written"
    return rows[-1]


def _run_refresh(monkeypatch, ticker, db: _Db) -> dict:
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd
    from gcp.fetchers import fetch_premarket_refresh as fpr

    bars = fx.premarket_bars(ticker)
    minute = pd.DataFrame(
        {"Open": bars["open"].values, "High": bars["high"].values, "Low": bars["low"].values,
         "Close": bars["close"].values, "Volume": bars["volume"].values},
        index=pd.DatetimeIndex(bars["timestamp"]).tz_localize("America/New_York"),
    )
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monkeypatch.setattr(fmd, "fetch_minute_data", lambda tk, d, k: minute)
    out = fpr.compute_premarket_for_ticker(ticker, SESSION, "key",
                                           level_params=fixture_params(ticker, SESSION))
    assert out is not None
    return out


@pytest.mark.parametrize("ticker", sorted(EXPECTED))
def test_nightly_writer_filters_with_the_prior_sessions_atr(monkeypatch, ticker):
    row = _run_nightly(monkeypatch, ticker, _Db(ticker))
    hi, lo = EXPECTED[ticker]
    assert row["pre_high"] == pytest.approx(hi)
    assert row["pre_low"] == pytest.approx(lo)


@pytest.mark.parametrize("ticker", sorted(EXPECTED))
def test_refresh_writer_filters_with_the_prior_sessions_atr(monkeypatch, ticker):
    out = _run_refresh(monkeypatch, ticker, _Db(ticker))
    hi, lo = EXPECTED[ticker]
    assert out["pre_high"] == pytest.approx(hi)
    assert out["pre_low"] == pytest.approx(lo)
    assert out["excluded_prior_close_prints"] > 0


def test_nightly_values_do_not_move_with_the_fetch_dates_own_bar(monkeypatch):
    """A wild 2026-11-06 bar (range 600, so a far larger ATR for that day)
    changes nothing about the premarket filter, which reads 2026-11-05."""
    base = _run_nightly(monkeypatch, "SPY", _Db("SPY"))
    wild = _run_nightly(monkeypatch, "SPY", _Db(
        "SPY", session_row={"Open": 700.0, "High": 1200.0, "Low": 600.0, "Close": 1100.0}))
    for col in ("pre_high", "pre_low", "pre_vwap"):
        assert wild[col] == pytest.approx(base[col]), col
    assert wild["pre_high"] == pytest.approx(738.04)


def test_refresh_values_do_not_move_with_the_fetch_dates_own_row(monkeypatch):
    """A 2026-11-06 row already holding a close and an atr_14 (a rerun
    after the nightly job) is never the prior session."""
    base = _run_refresh(monkeypatch, "QQQ", _Db("QQQ"))
    later = _run_refresh(monkeypatch, "QQQ", _Db(
        "QQQ", session_row={"Open": 500.0, "High": 900.0, "Low": 400.0, "Close": 800.0},
        session_atr=200.0))
    for col in ("pre_high", "pre_low", "pre_vwap", "gap_pct"):
        assert later[col] == pytest.approx(base[col]), col
    assert later["pre_low"] == pytest.approx(649.62)


def test_refresh_reads_the_prior_sessions_close_open_and_atr(monkeypatch):
    import gcp.database as database
    from gcp.fetchers import fetch_premarket_refresh as fpr

    db = _Db("IWM", session_row={"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5},
             session_atr=99.0)
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    prior = fpr._prior_session_from_db("IWM", SESSION)
    d = fx.daily("IWM")
    assert prior["close"] == pytest.approx(float(d["Close"].iloc[-1]))
    assert prior["open"] == pytest.approx(float(d["Open"].iloc[-1]))
    assert prior["atr_14"] == pytest.approx(fx.prior_atr("IWM"))


# ── Withheld, never unfiltered (Codex review on #1753) ──────────────────────
# A snapshot the filter could not run on is never written: on origin/main a
# failed prior-session lookup returned {} and the refresh wrote the raw
# 08:05 prints (SPY pre_high 765.5267) with zero excluded-print counts.


class _FailingDb(_Db):
    def query(self, sql, params=None):
        if "atr_14" in sql and "date < :d" in sql:
            raise TimeoutError("statement timeout")
        return super().query(sql, params)


def _refresh_out(monkeypatch, ticker, db):
    from gcp import database
    from gcp.fetchers import fetch_market_data as fmd
    from gcp.fetchers import fetch_premarket_refresh as fpr

    bars = fx.premarket_bars(ticker)
    minute = pd.DataFrame(
        {"Open": bars["open"].values, "High": bars["high"].values, "Low": bars["low"].values,
         "Close": bars["close"].values, "Volume": bars["volume"].values},
        index=pd.DatetimeIndex(bars["timestamp"]).tz_localize("America/New_York"),
    )
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monkeypatch.setattr(fmd, "fetch_minute_data", lambda tk, d, k: minute)
    return fpr.compute_premarket_for_ticker(ticker, SESSION, "key")


def test_refresh_withholds_the_snapshot_when_the_prior_lookup_fails(monkeypatch):
    assert _refresh_out(monkeypatch, "SPY", _FailingDb("SPY")) is None


def test_prior_session_lookup_raises_instead_of_returning_empty(monkeypatch):
    from gcp import database
    from gcp.fetchers import fetch_premarket_refresh as fpr

    monkeypatch.setattr(database, "query_to_dataframe", _FailingDb("SPY").query)
    with pytest.raises(TimeoutError):
        fpr._prior_session_from_db("SPY", SESSION)


def test_refresh_withholds_the_snapshot_when_the_prior_atr_is_missing(monkeypatch):
    db = _Db("SPY")
    db.conn.execute("UPDATE market_data_daily SET atr_14 = NULL")
    assert _refresh_out(monkeypatch, "SPY", db) is None


def test_nightly_writes_no_premarket_when_the_prior_atr_is_missing(monkeypatch):
    from lib import indicators

    real = indicators.add_all_indicators

    def no_atr(df, **k):
        return real(df, **k).drop(columns=["ATR14"], errors="ignore")

    monkeypatch.setattr(indicators, "add_all_indicators", no_atr)
    row = _run_nightly(monkeypatch, "SPY", _Db("SPY"))
    for col in ("pre_high", "pre_low", "pre_vwap"):
        assert row.get(col) is None or pd.isna(row.get(col)), col
