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
        calendar = {}
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


def test_fetch_yahoo_one_calendar_picks_up_upcoming(monkeypatch):
    """The AMZN-tonight case: get_earnings_dates returns nothing in the
    window (because the report hasn't happened yet), but Ticker.calendar
    surfaces the upcoming date. Yahoo confirmation is what promotes
    AMZN from tier 4 to tier 2 in the brief.
    """
    class FakeTicker:
        def __init__(self, t): pass
        calendar = {
            "Earnings Date": [date(2026, 4, 29)],
            "Earnings Average": 1.65,
        }
        def get_earnings_dates(self, limit=8): return None  # no past rows

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    rows = fec._fetch_yahoo_one("AMZN", date(2026, 4, 1), date(2026, 5, 31))
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "AMZN"
    assert r["date"] == "2026-04-29"
    assert r["time"] == "unknown"  # calendar doesn't expose BMO/AMC
    assert r["eps_estimate"] == 1.65
    assert r["source"] == "Yahoo"


def test_fetch_yahoo_one_dedups_calendar_against_get_earnings(monkeypatch):
    """When both APIs report the same date, get_earnings_dates wins
    (it carries time-of-day) and the calendar entry is suppressed."""
    fake = _fake_earnings_df([(2026, 4, 28, 16, 0, 0.44, None, None)])

    class FakeTicker:
        def __init__(self, t): pass
        calendar = {"Earnings Date": [date(2026, 4, 28)], "Earnings Average": 0.44}
        def get_earnings_dates(self, limit=8): return fake

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    rows = fec._fetch_yahoo_one("SBUX", date(2026, 4, 1), date(2026, 5, 31))
    assert len(rows) == 1
    assert rows[0]["time"] == "postmarket"  # the get_earnings_dates row, not the calendar one


def test_fetch_yahoo_one_swallows_yfinance_errors(monkeypatch):
    """yfinance often raises KeyError on long-tail tickers — the worker
    must return [] not propagate, so the parallel fetch keeps running.
    Both API paths must be guarded.
    """
    class CrashyTicker:
        def __init__(self, t): pass
        @property
        def calendar(self):
            raise RuntimeError("calendar fetch failed")
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
        calendar = None
        def get_earnings_dates(self, limit=8): return None

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", EmptyTicker)

    assert fec._fetch_yahoo_one("X", date(2026, 4, 1), date(2026, 5, 1)) == []


# ──────────────────────────────────────────────────────────────────────
# fetch_yahoo_earnings — top-level orchestration
# ──────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────
# _fetch_yahoo_bulk — Calendars.get_earnings_calendar wrapper
# ──────────────────────────────────────────────────────────────────────


def _bulk_df(rows):
    """Build a yfinance-Calendars-shaped DataFrame.

    rows = [(symbol, marketcap, event_start_utc_str, timing, eps_est, eps_act), ...]
    """
    df = pd.DataFrame(rows, columns=[
        "Symbol", "Marketcap", "Event Start Date", "Timing",
        "EPS Estimate", "Reported EPS",
    ])
    df["Event Start Date"] = pd.to_datetime(df["Event Start Date"], utc=True)
    df["Company"] = df["Symbol"].apply(lambda s: f"{s} Inc")
    df["Event Name"] = None
    df["Surprise(%)"] = None
    df = df.set_index("Symbol")
    return df


def test_bulk_fetch_paginates_until_short_page(monkeypatch):
    """Full page (== page_size) → keep paging. Short page (< page_size)
    → exit. Stops cleanly without an extra empty call."""
    # Page 1 = exactly page_size rows → loop continues
    full_page = _bulk_df([
        (f"T{i:03d}", 1e9, "2026-04-28 20:00:00", "TAS", 1.0, None)
        for i in range(5)
    ])
    short_page = _bulk_df([
        ("AAPL", 3.9e12, "2026-04-30 20:00:00", "AMC", 1.94, None),
    ])

    calls = []
    class FakeCalendars:
        def __init__(self, start, end): pass
        def get_earnings_calendar(self, filter_most_active=False, limit=5,
                                   offset=0, force=True):
            calls.append(offset)
            if offset == 0: return full_page
            if offset == 5: return short_page
            return pd.DataFrame()

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)

    df = fec._fetch_yahoo_bulk(date(2026, 4, 27), date(2026, 5, 2),
                                page_size=5, max_pages=10)
    assert calls == [0, 5], "first page is full → second page is fetched"
    assert "AAPL" in set(df["ticker"])
    assert df["source"].eq("Yahoo").all()


def test_bulk_fetch_short_first_page_exits_immediately(monkeypatch):
    """If the very first page returns less than page_size rows, no
    further pages are fetched — common case when Yahoo's calendar is
    small for a tight window."""
    only_page = _bulk_df([
        ("AAPL", 3.9e12, "2026-04-30 20:00:00", "AMC", 1.94, None),
        ("V",    6.4e11, "2026-04-28 20:05:56", "TAS", 3.10, 3.31),
    ])

    calls = []
    class FakeCalendars:
        def __init__(self, start, end): pass
        def get_earnings_calendar(self, filter_most_active=False, limit=100,
                                   offset=0, force=True):
            calls.append(offset)
            if offset == 0: return only_page
            return pd.DataFrame()

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)

    df = fec._fetch_yahoo_bulk(date(2026, 4, 27), date(2026, 5, 2),
                                page_size=100, max_pages=10)
    assert calls == [0]   # short first page → no second call
    # Timing 'AMC' → postmarket; 'TAS' falls through to hour-based
    assert df.set_index("ticker").loc["AAPL", "time"] == "postmarket"
    assert df["source"].eq("Yahoo").all()


def test_bulk_fetch_filters_outside_window(monkeypatch):
    """Yahoo's API sometimes returns adjacent-day events; the post-fetch
    date filter strips them so callers see only requested-window rows."""
    df = _bulk_df([
        ("OUT_PRE",  1e9, "2026-04-26 20:00:00", "TAS", 1.0, None),  # before window
        ("IN",       1e9, "2026-04-28 20:00:00", "TAS", 1.0, None),
        ("OUT_POST", 1e9, "2026-05-04 20:00:00", "AMC", 1.0, None),  # after window
    ])
    class FakeCalendars:
        def __init__(self, start, end): pass
        def get_earnings_calendar(self, **kw):
            return df if kw.get("offset", 0) == 0 else pd.DataFrame()

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)

    out = fec._fetch_yahoo_bulk(date(2026, 4, 27), date(2026, 5, 2))
    assert set(out["ticker"]) == {"IN"}


def test_bulk_fetch_handles_single_day_by_widening(monkeypatch):
    """Single-day calls return 0 from Yahoo's API (observed). The bulk
    fetcher widens to 2 days; the date filter then trims back."""
    captured_starts = []
    class FakeCalendars:
        def __init__(self, start, end):
            captured_starts.append((start, end))
        def get_earnings_calendar(self, **kw): return pd.DataFrame()

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)

    fec._fetch_yahoo_bulk(date(2026, 4, 29), date(2026, 4, 29))
    assert captured_starts == [("2026-04-29", "2026-04-30")]


# ──────────────────────────────────────────────────────────────────────
# fetch_yahoo_earnings — bulk + optional per-ticker fill
# ──────────────────────────────────────────────────────────────────────


def test_fetch_yahoo_earnings_bulk_only(monkeypatch):
    """No fill_tickers → bulk path is the only call made."""
    bulk = _bulk_df([
        ("AAPL", 3.9e12, "2026-04-30 20:00:00", "AMC", 1.94, None),
    ])
    class FakeCalendars:
        def __init__(self, *a, **kw): pass
        def get_earnings_calendar(self, **kw):
            return bulk if kw.get("offset", 0) == 0 else pd.DataFrame()

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)
    # Tracks whether per-ticker path is called — should NOT be
    monkeypatch.setattr(yfinance, "Ticker",
                        lambda t: pytest.fail(f"per-ticker called for {t} but fill_tickers was None"))

    df = fec.fetch_yahoo_earnings(date(2026, 4, 1), date(2026, 5, 31))
    assert set(df["ticker"]) == {"AAPL"}


def test_fetch_yahoo_earnings_fills_missing_tickers(monkeypatch):
    """The AMZN-tonight case: bulk misses today's pending AMC, but
    fill_tickers triggers per-ticker calendar lookup that catches it."""
    bulk = _bulk_df([
        ("AAPL", 3.9e12, "2026-04-30 20:00:00", "AMC", 1.94, None),
    ])
    class FakeCalendars:
        def __init__(self, *a, **kw): pass
        def get_earnings_calendar(self, **kw):
            return bulk if kw.get("offset", 0) == 0 else pd.DataFrame()

    class FakeTicker:
        def __init__(self, t): self.t = t
        @property
        def calendar(self):
            if self.t == "AMZN":
                return {"Earnings Date": [date(2026, 4, 29)],
                        "Earnings Average": 1.65}
            return None
        def get_earnings_dates(self, limit=8): return None

    import scripts.fetch_earnings_calendar as fec
    import yfinance
    monkeypatch.setattr(yfinance, "Calendars", FakeCalendars)
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)

    df = fec.fetch_yahoo_earnings(
        date(2026, 4, 1), date(2026, 5, 31),
        fill_tickers=["AAPL", "AMZN"],   # AAPL already in bulk → no per-ticker; AMZN missing → call
        max_workers=2,
    )
    tickers = set(df["ticker"])
    assert "AAPL" in tickers, "bulk row preserved"
    assert "AMZN" in tickers, "per-ticker fill caught AMZN"


def test_fetch_yahoo_earnings_no_yfinance(monkeypatch):
    """Graceful empty-return when yfinance isn't installed."""
    import sys
    monkeypatch.setitem(sys.modules, "yfinance", None)
    # The probe import block in fetch_yahoo_earnings catches ImportError
    # by trying to import yfinance — when sys.modules entry is None,
    # `import yfinance` raises ImportError.
    from scripts.fetch_earnings_calendar import fetch_yahoo_earnings
    df = fetch_yahoo_earnings(date(2026, 4, 1), date(2026, 5, 1))
    assert df.empty
