"""Nothing fetches, stores or reads an adjusted price (FEAT-DATA-001).

The owner's rule, 2026-11-16: "Nothing should be adjusted. It should be as it
was traded." Every daily request asks AlphaVantage TIME_SERIES_DAILY, which
returns the same open, high, low, close and volume as the adjusted endpoint
without the adjusted close (spec Problem 2), and no writer carries an
adjusted_close column into market_data_daily.

The replies below hold only the fields TIME_SERIES_DAILY returns, so a writer
that still reads the adjusted endpoint's '5. adjusted close' or '6. volume'
raises KeyError. Several writers swallow that (fetch_daily_from_av returns {}
and migrate_market_data_daily_av logs and goes on), so every case asserts the
values it wrote, not only what is absent.

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]

# A TIME_SERIES_DAILY reply for SPY: fields 1 to 5 only, '5. volume' the volume.
DAILY_REPLY = {
    "Meta Data": {"2. Symbol": "SPY"},
    "Time Series (Daily)": {
        "2026-11-13": {"1. open": "671.11", "2. high": "675.38", "3. low": "668.12",
                       "4. close": "673.27", "5. volume": "81234567"},
        "2026-11-12": {"1. open": "670.00", "2. high": "672.50", "3. low": "667.90",
                       "4. close": "671.80", "5. volume": "70111222"},
    },
}

# One 1-minute bar of the session, as TIME_SERIES_INTRADAY returns it.
INTRADAY_REPLY = {
    "Meta Data": {"2. Symbol": "SPY"},
    "Time Series (1min)": {
        "2026-11-13 09:30:00": {"1. open": "671.20", "2. high": "671.90", "3. low": "671.00",
                                "4. close": "671.50", "5. volume": "250000"},
    },
}

# The adjusted column names a writer could carry into a frame.
ADJ = {"adjusted_close", "Adj Close"}


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _recording_get(answers: dict[str, dict]):
    """A requests.get that answers by params['function'] and records every
    params dict it was sent. A function with no answer gets an AlphaVantage
    error reply, so a request for the wrong endpoint yields no data."""
    sent: list[dict] = []

    def get(url, params=None, **kwargs):
        params = dict(params or {})
        sent.append(params)
        fn = params.get("function")
        if fn in answers:
            return _Resp(answers[fn])
        return _Resp({"Error Message": f"no stubbed answer for {fn}"})

    return get, sent


def _recording_upsert():
    """An upsert_dataframe stand-in recording (table, frame) pairs."""
    calls: list[tuple[str, pd.DataFrame]] = []

    def upsert(df, table, *args, **kwargs):
        calls.append((table, df.copy()))
        return len(df)

    return upsert, calls


def _daily_frames(calls):
    return [df for table, df in calls if table == "market_data_daily"]


# ─── Design 1: every daily writer requests TIME_SERIES_DAILY ────────────────


def _writer_fetch_daily_from_av(monkeypatch):
    from gcp.fetchers import fetch_market_data as fmd
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(fmd.requests, "get", get)

    out = fmd.fetch_daily_from_av("SPY", "2026-11-13", "k")

    assert len(sent) == 1
    assert sent[0]["function"] == "TIME_SERIES_DAILY"
    assert out == {"open": 671.11, "high": 675.38, "low": 668.12,
                   "close": 673.27, "volume": 81234567}


def _writer_av_get_full_daily_series(monkeypatch):
    from gcp.fetchers import fetch_market_data as fmd
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(fmd.requests, "get", get)

    frame = fmd._av_get_full_daily_series("SPY", "k", "full")

    assert len(sent) == 1
    assert sent[0]["function"] == "TIME_SERIES_DAILY"
    assert sent[0]["outputsize"] == "full"
    assert list(frame.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert frame.volume.tolist() == [70111222, 81234567]


def _writer_backfill_ticker(monkeypatch):
    import gcp.backfill_ticker as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)
    monkeypatch.setattr(mod, "compute_indicators_for_full_range", lambda ticker: 0)
    monkeypatch.setattr(mod, "compute_indicators_for_dates", lambda ticker, dates: None)
    for name, value in (("BACKFILL_TICKER", "SPY"), ("ALPHA_VANTAGE_API_KEY", "k"),
                        ("BACKFILL_INCLUDE_NEWS", "false"),
                        ("BACKFILL_ADD_TO_WATCHLIST", "false"),
                        ("BACKFILL_DATES", "2026-11-13")):
        monkeypatch.setenv(name, value)

    daily = mod.av_daily_full("SPY", "k")
    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    assert not (set(daily.columns) & ADJ), sorted(daily.columns)
    assert daily["volume"].tolist() == [70111222, 81234567]

    sent.clear()
    assert mod.run() == 0
    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    assert set(frame["data_source"]) == {"alphavantage"}
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_migrate_to_gcp(monkeypatch):
    import gcp.migrate_to_gcp as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setattr(mod, "AV_DAILY_SYMBOLS", {"spy": "SPY"})
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)

    mod.migrate_market_data_daily_av(Path("."), dry_run=False)

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    # The function logs and goes on after any exception, so a missing frame
    # is how a writer still reading the adjusted endpoint's fields fails.
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    assert set(frame["data_source"]) == {"alphavantage_daily"}
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_backfill_watchlist_data(monkeypatch):
    import requests

    import gcp.fetchers.fetch_market_data as fmd
    from scripts import backfill_watchlist_data as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setenv("AV_API_KEY", "k")
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)
    monkeypatch.setattr(fmd, "compute_and_upsert_daily_indicators",
                        lambda ticker, fetch_date, **kw: None)
    monkeypatch.setattr(fmd, "read_level_params_for_run", lambda tickers, day: {})

    assert mod.backfill_daily("SPY") is True

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_scripts_fetch_market_data(monkeypatch):
    from scripts import fetch_market_data as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(mod, "AV_API_KEY", "k")
    monkeypatch.setattr(mod.requests, "get", get)

    frame = mod.fetch_historical_daily_data("SPY", "2026-11-01", "2026-11-30")

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame["Volume"].tolist() == [70111222, 81234567]


WRITERS = {
    "fetch_daily_from_av": _writer_fetch_daily_from_av,
    "_av_get_full_daily_series": _writer_av_get_full_daily_series,
    "backfill_ticker": _writer_backfill_ticker,
    "migrate_to_gcp": _writer_migrate_to_gcp,
    "backfill_watchlist_data": _writer_backfill_watchlist_data,
    "scripts_fetch_market_data": _writer_scripts_fetch_market_data,
}


@pytest.mark.parametrize("writer", list(WRITERS))
def test_daily_writers_request_as_traded(writer, monkeypatch):
    """Each daily writer sends function TIME_SERIES_DAILY, reads volume from
    '5. volume', and returns or records no adjusted column."""
    WRITERS[writer](monkeypatch)


def test_no_writer_emits_adjusted_close(monkeypatch):
    """process_ticker over a 1-minute bar and a TIME_SERIES_DAILY reply, and
    the Yahoo ^VIX fetch, record market_data_daily frames with no adjusted
    column. On main the first carried adjusted_close through build_daily_row
    and the second set it equal to the close."""
    from gcp.fetchers import fetch_market_data as fmd

    get, sent = _recording_get({"TIME_SERIES_INTRADAY": INTRADAY_REPLY,
                                "TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    intraday_writes: list[str] = []
    indicator_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(fmd.requests, "get", get)
    monkeypatch.setattr(fmd, "upsert_dataframe", upsert)
    monkeypatch.setattr(fmd, "write_intraday_to_sql",
                        lambda ticker, df, fetch_date: intraday_writes.append(ticker))
    monkeypatch.setattr(fmd, "compute_and_upsert_daily_indicators",
                        lambda ticker, fetch_date, **kw: indicator_calls.append((ticker, fetch_date)))

    fmd.process_ticker("SPY", "2026-11-13", "k")

    assert intraday_writes == ["SPY"]
    assert [p["function"] for p in sent] == ["TIME_SERIES_INTRADAY", "TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert frames, "process_ticker recorded no market_data_daily frame"
    for frame in frames:
        assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    row = frames[0].iloc[0]
    assert row["data_source"] == "alphavantage_daily"
    assert row["volume"] == 81234567
    assert indicator_calls == [("SPY", "2026-11-13")]

    def epoch(day: str) -> int:
        return int(dt.datetime.strptime(day, "%Y-%m-%d")
                   .replace(tzinfo=dt.timezone.utc).timestamp())

    yahoo = {"chart": {"result": [{
        "timestamp": [epoch("2026-11-12"), epoch("2026-11-13")],
        "indicators": {"quote": [{"open": [18.0, 18.2], "high": [18.5, 19.0],
                                  "low": [17.8, 18.1], "close": [18.2, 18.7]}]},
    }]}}
    calls.clear()
    monkeypatch.setattr(fmd.requests, "get", lambda *a, **k: _Resp(yahoo))

    assert fmd.fetch_and_upsert_vix() == 2
    frames = _daily_frames(calls)
    assert len(frames) == 1
    assert not (set(frames[0].columns) & ADJ), sorted(frames[0].columns)
