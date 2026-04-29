"""Unit tests for the Yahoo earnings cross-check in fetch_earnings_calendar.py.

Yahoo is the third independent date source (added after we observed AV
booking wrong dates for ~20% of SP500 names like SBUX, V, STX, EA, FSLR).

These tests stub yfinance.Ticker.get_earnings_dates so the fetcher can be
exercised without network. The integration / live-Yahoo path is exercised
by the smoke-test in scripts/.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# _yahoo_time_from_ts — hour → premarket / postmarket / intraday
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hour,expected", [
    (4, "premarket"),
    (7, "premarket"),
    (8, "premarket"),
    (9, "intraday"),    # 9:00 is at the boundary — Yahoo often shows TNS as 12
    (12, "intraday"),
    (15, "intraday"),
    (16, "postmarket"),
    (17, "postmarket"),
    (20, "postmarket"),
])
def test_yahoo_time_from_hour(hour, expected):
    from scripts.fetch_earnings_calendar import _yahoo_time_from_ts
    ts = pd.Timestamp(2026, 4, 28, hour, 0, tz="US/Eastern")
    assert _yahoo_time_from_ts(ts) == expected


def test_yahoo_time_handles_non_timestamp():
    """Defensive: bad input shouldn't crash the fetch loop."""
    from scripts.fetch_earnings_calendar import _yahoo_time_from_ts
    assert _yahoo_time_from_ts(None) == "unknown"
    assert _yahoo_time_from_ts("2026-04-28") == "unknown"


# ──────────────────────────────────────────────────────────────────────
# _fetch_yahoo_one — per-ticker normalization
# ──────────────────────────────────────────────────────────────────────


def _fake_earnings_df(rows):
    """Build a yfinance-shaped DataFrame: tz-aware index + standard columns."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(*r[:5], tz="US/Eastern") for r in rows],
        name="Earnings Date",
    )
    return pd.DataFrame(
        {"EPS Estimate": [r[5] for r in rows],
         "Reported EPS": [r[6] for r in rows],
         "Surprise(%)":  [r[7] for r in rows]},
        index=idx,
    )


def test_fetch_yahoo_one_filters_to_window(monkeypatch):
    """Only dates inside [start_date, end_date] are returned."""
    fake = _fake_earnings_df([
        # (year, month, day, hour, minute, eps_est, eps_reported, surprise)
        (2026, 4, 28, 16, 0, 0.44, None, None),   # in-window AMC
        (2026, 7, 28, 16, 0, 0.65, None, None),   # out-of-window (future)
        (2025, 1, 28, 16, 0, 0.30, 0.32, 6.7),    # out-of-window (past)
    ])

    class FakeTicker:
        def __init__(self, t): self.t = t
        def get_earnings_dates(self, limit=8): return fake

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    rows = fec._fetch_yahoo_one("SBUX", date(2026, 4, 1), date(2026, 5, 31))
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "SBUX"
    assert r["date"] == "2026-04-28"
    assert r["time"] == "postmarket"
    assert r["eps_estimate"] == 0.44
    assert r["source"] == "Yahoo"


def test_fetch_yahoo_one_swallows_yfinance_errors(monkeypatch):
    """yfinance often raises KeyError on long-tail tickers — the worker
    must return [] not propagate, so the parallel fetch keeps running."""
    class CrashyTicker:
        def __init__(self, t): pass
        def get_earnings_dates(self, limit=8):
            raise KeyError("Earnings Date")  # the real failure mode

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", CrashyTicker)

    rows = fec._fetch_yahoo_one("BOGUS", date(2026, 4, 1), date(2026, 5, 31))
    assert rows == []


def test_fetch_yahoo_one_handles_empty_df(monkeypatch):
    """yfinance returning None or empty df → no rows, no crash."""
    class EmptyTicker:
        def __init__(self, t): pass
        def get_earnings_dates(self, limit=8): return None

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", EmptyTicker)

    assert fec._fetch_yahoo_one("X", date(2026, 4, 1), date(2026, 5, 1)) == []


# ──────────────────────────────────────────────────────────────────────
# fetch_yahoo_earnings — top-level orchestration
# ──────────────────────────────────────────────────────────────────────


def test_fetch_yahoo_earnings_combines_tickers(monkeypatch):
    """End-to-end: multiple tickers → one DataFrame with proper schema."""
    sbux_df = _fake_earnings_df([(2026, 4, 28, 16, 0, 0.44, None, None)])
    v_df    = _fake_earnings_df([(2026, 4, 28, 16, 0, 3.10, None, None)])
    aapl_df = _fake_earnings_df([(2026, 4, 30, 16, 0, 1.94, None, None)])

    fakes = {"SBUX": sbux_df, "V": v_df, "AAPL": aapl_df}

    class FakeTicker:
        def __init__(self, t): self.t = t
        def get_earnings_dates(self, limit=8): return fakes.get(self.t)

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    df = fec.fetch_yahoo_earnings(
        ["SBUX", "V", "AAPL"],
        date(2026, 4, 1), date(2026, 5, 31),
        max_workers=2,
    )
    assert len(df) == 3
    assert set(df["ticker"]) == {"SBUX", "V", "AAPL"}
    assert (df["source"] == "Yahoo").all()
    assert (df["time"] == "postmarket").all()


def test_fetch_yahoo_earnings_empty_ticker_list_returns_empty():
    """Caller passing [] (e.g. AV/UW/EW all returned empty) is a no-op,
    not an error."""
    from scripts.fetch_earnings_calendar import fetch_yahoo_earnings
    df = fetch_yahoo_earnings([], date(2026, 4, 1), date(2026, 5, 1))
    assert df.empty


def test_fetch_yahoo_earnings_dedups_same_ticker_date(monkeypatch):
    """Yahoo sometimes returns the same date twice (annual + quarterly).
    The fetcher must dedup before passing to persist."""
    dup = _fake_earnings_df([
        (2026, 4, 28, 16, 0, 0.44, None, None),
        (2026, 4, 28, 16, 0, 0.44, None, None),  # exact dup
    ])

    class FakeTicker:
        def __init__(self, t): pass
        def get_earnings_dates(self, limit=8): return dup

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    df = fec.fetch_yahoo_earnings(["SBUX"], date(2026, 4, 1), date(2026, 5, 1))
    assert len(df) == 1
