"""Tests for gcp/fetchers/evaluate_ew_strikes.py (#1151).

The evaluator writes HIT / MISS / KEPT / ASSIGNED verdicts for Earnings
Whispers strike picks. It scored every pick against the session of
`earnings_date` itself, which for an after-close reporter is the session
BEFORE the news (#1151: 1,263 of 2,383 scored rows). These pin the session
each `earnings_time` is scored against, the verdict arithmetic, and the job's
I/O shape.

Hermetic: the DB, the vendor fetch and the clock are patched. The NYSE
calendar is the real `pandas_market_calendars` one, which computes sessions
locally.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.fetchers import evaluate_ew_strikes as ew  # noqa: E402


# ── fixtures ───────────────────────────────────────────────────────────


def _day_bars(day: str, base: float = 100.0, *, spike_at: str | None = None,
              spike_to: float | None = None) -> pd.DataFrame:
    """One naive-ET 1-min bar from 04:00 to 19:59, the extended-hours shape
    fetch_minute_data returns. Price is flat at `base` (high +0.5, low
    -0.5) unless a spike is requested at one minute."""
    idx = pd.date_range(f"{day} 04:00", f"{day} 19:59", freq="1min")
    df = pd.DataFrame({"Open": base, "High": base + 0.5, "Low": base - 0.5,
                       "Close": base, "Volume": 100}, index=idx)
    if spike_at is not None:
        ts = pd.Timestamp(f"{day} {spike_at}")
        df.loc[ts, ["High", "Close"]] = [spike_to, spike_to]
    return df


class _Conn:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt, params=None):
        self._log.append((str(stmt), params))


class _Engine:
    def __init__(self):
        self.statements: list = []
        self.transactions = 0

    def begin(self):
        self.transactions += 1
        return _Conn(self.statements)


def _rows(*rows) -> pd.DataFrame:
    cols = ["id", "ticker", "earnings_date", "earnings_time", "strategy",
            "strike", "ew_strike_verdict"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)


def _run(rows: pd.DataFrame, *, bars_for=None, now_utc="2026-09-30 12:00",
         **kwargs):
    """Run evaluate_range with the DB, vendor and clock patched. Returns
    (result, fetch_calls, engine)."""
    calls: list = []
    engine = _Engine()

    def fake_fetch(ticker, fetch_date, api_key, *args, **kw):
        calls.append((ticker, fetch_date, kw.get("adjusted", args[0] if args else None)))
        if bars_for is not None:
            return bars_for(ticker, fetch_date)
        return _day_bars(fetch_date)

    start = kwargs.pop("start", date(2026, 9, 1))
    end = kwargs.pop("end", date(2026, 9, 30))
    with patch("gcp.database.query_to_dataframe", return_value=rows), \
         patch("gcp.database.get_engine", return_value=engine), \
         patch("gcp.fetchers.fetch_market_data.fetch_minute_data", side_effect=fake_fetch), \
         patch("gcp.fetchers.evaluate_ew_strikes._now_utc", create=True,
               return_value=pd.Timestamp(now_utc, tz="UTC")), \
         patch("time.sleep"):
        result = ew.evaluate_range(start, end, **kwargs)
    return result, calls, engine


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")


# ── the session each timing is scored against ─────────────────────────


def test_an_after_close_reporter_is_scored_on_the_next_session():
    """#1151 itself: a postmarket pick on Thu 2026-09-24 reacts on Fri
    2026-09-25, so that is the day whose bars are fetched."""
    rows = _rows((1, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None))
    _, calls, _ = _run(rows)
    assert [c[1] for c in calls] == ["2026-09-25"]


SESSIONS = None


def _sessions():
    global SESSIONS
    if SESSIONS is None:
        SESSIONS = ew.nyse_sessions(date(2026, 4, 1), date(2026, 12, 31))
    return SESSIONS


@pytest.mark.parametrize("earnings_date, timing, want", [
    (date(2026, 9, 24), "postmarket", date(2026, 9, 25)),    # Thu close -> Fri
    (date(2026, 8, 14), "postmarket", date(2026, 8, 17)),    # Fri close -> Mon
    (date(2026, 11, 25), "postmarket", date(2026, 11, 27)),  # Thanksgiving skipped
    (date(2026, 9, 24), "premarket", date(2026, 9, 24)),     # before the open
    (date(2026, 5, 25), "premarket", date(2026, 5, 26)),     # Memorial Day -> Tue
    (date(2026, 9, 24), "intraday", date(2026, 9, 24)),      # stated: same session
    (date(2026, 9, 24), "PostMarket", date(2026, 9, 25)),    # case-insensitive
])
def test_scoring_session_by_timing(earnings_date, timing, want):
    s = ew.scoring_session(earnings_date, timing, _sessions())
    assert s is not None and s.date == want


@pytest.mark.parametrize("timing", [None, float("nan"), "", "unknown", "amc"])
def test_a_timing_the_writer_does_not_emit_has_no_session(timing):
    """scripts/fetch_earnings_calendar.py normalises to premarket, intraday,
    postmarket or unknown. Anything else is skipped and counted, never
    defaulted to a session."""
    assert ew.scoring_session(date(2026, 9, 24), timing, _sessions()) is None


def test_a_null_timing_read_back_as_nan_is_counted_not_a_crash():
    """pandas can hand a NULL earnings_time back as NaN, which is truthy."""
    rows = _rows((1, "XYZ", date(2026, 9, 24), float("nan"), "Long Calls", 105.0, None))
    result, calls, _ = _run(rows)
    assert (result["unknown_timing"], calls) == (1, [])


def test_intraday_on_a_closed_day_has_no_session():
    assert ew.scoring_session(date(2026, 5, 25), "intraday", _sessions()) is None


def test_an_early_close_session_ends_at_one_pm():
    s = ew.scoring_session(date(2026, 11, 25), "postmarket", _sessions())
    assert (s.open_et, s.close_et) == (pd.Timestamp("2026-11-27 09:30"),
                                       pd.Timestamp("2026-11-27 13:00"))


# ── the verdict arithmetic (_compute_verdict had no tests) ────────────


def _session_bars(day, **kw):
    return _day_bars(day, **kw).between_time("09:30", "15:59")


@pytest.mark.parametrize("strategy, strike, spike_to, verdict", [
    ("Long Calls", 105.0, 106.0, "HIT"),       # high reached the strike
    ("Long Calls", 110.0, 106.0, "MISS"),
    ("Covered Calls", 105.0, 100.0, "KEPT"),   # close stayed at or below
    ("Covered Calls", 99.0, 100.0, "ASSIGNED"),
])
def test_compute_verdict(strategy, strike, spike_to, verdict):
    bars = _session_bars("2026-09-25", spike_at="12:00", spike_to=spike_to)
    assert ew._compute_verdict(strategy, strike, bars)["verdict"] == verdict


def test_an_unsupported_strategy_gets_no_verdict():
    bars = _session_bars("2026-09-25")
    assert ew._compute_verdict("Straddles", 100.0, bars)["verdict"] is None


# ── what the job fetches, scores and writes ───────────────────────────


def test_bars_outside_the_session_do_not_count():
    """A 13:30 spike through the strike on 2026-11-27 is after that day's
    13:00 early close, so it is after-hours and the verdict is MISS."""
    rows = _rows((1, "XYZ", date(2026, 11, 25), "postmarket", "Long Calls", 105.0, None))
    result, _, engine = _run(
        rows, start=date(2026, 11, 25), end=date(2026, 11, 25),
        now_utc="2026-11-28 12:00",
        bars_for=lambda t, d: _day_bars(d, spike_at="13:30", spike_to=106.0))
    written = [p for sql, ps in engine.statements for p in (ps or [])]
    assert [p["verdict"] for p in written] == ["MISS"]
    assert result["scored"] == 1


def test_n_rows_over_k_sessions_fetch_k_times():
    """Four picks, two (ticker, session) pairs: exactly two vendor calls."""
    rows = _rows(
        (1, "AAA", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
        (2, "AAA", date(2026, 9, 24), "postmarket", "Covered Calls", 99.0, None),
        (3, "BBB", date(2026, 9, 25), "premarket", "Long Calls", 105.0, None),
        (4, "BBB", date(2026, 9, 24), "postmarket", "Covered Calls", 99.0, None),
    )
    result, calls, _ = _run(rows)
    assert sorted((t, d) for t, d, _ in calls) == [("AAA", "2026-09-25"),
                                                  ("BBB", "2026-09-25")]
    assert result["scored"] == 4


def test_the_evaluator_fetches_as_traded_bars():
    """A re-score months later must compare as-traded bars with as-traded
    strikes; split-adjusted history would not match the pick."""
    rows = _rows((1, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None))
    _, calls, _ = _run(rows)
    assert calls[0][2] is False


def test_a_session_that_has_not_closed_is_left_for_a_later_run():
    """At 23:00 ET on the report day, an after-close pick's session is
    tomorrow; it is counted pending and not fetched."""
    rows = _rows((1, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None))
    result, calls, engine = _run(rows, now_utc="2026-09-25 03:00")
    assert calls == []
    assert result["pending_session"] == 1
    assert engine.statements == []


def test_force_clears_a_row_it_cannot_rescore():
    """--force means the stored verdict is not trusted. A row that cannot be
    recomputed now is cleared to NULL for the nightly run to fill, never left
    holding a verdict computed against the wrong session."""
    rows = _rows((7, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, "HIT"))
    result, _, engine = _run(rows, force=True,
                             bars_for=lambda t, d: pd.DataFrame())
    cleared = [(sql, ps) for sql, ps in engine.statements if "= NULL" in sql]
    assert cleared and [p["id"] for p in cleared[0][1]] == [7]
    assert result["cleared"] == 1


def test_dry_run_writes_nothing():
    rows = _rows((1, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None))
    result, calls, engine = _run(rows, dry_run=True)
    assert len(calls) == 1 and result["scored"] == 1
    assert engine.statements == [] and engine.transactions == 0


def test_a_missing_api_key_fails_loudly(monkeypatch):
    """It returned 0 rows updated and exited 0: a run that did nothing looked
    like a quiet night."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY")
    rows = _rows((1, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None))
    with pytest.raises(RuntimeError, match="ALPHA_VANTAGE_API_KEY"):
        _run(rows)


def test_every_fetch_failing_is_an_outage_not_a_quiet_night():
    rows = _rows(
        (1, "AAA", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
        (2, "BBB", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
    )
    result, _, _ = _run(rows, bars_for=lambda t, d: pd.DataFrame())
    assert result["no_bars"] == 2
    assert (result["fetches"], result["empty_fetches"]) == (2, 2)
    assert ew.run_failed(result)


def test_a_lone_empty_fetch_is_not_an_outage():
    """One empty vendor call cannot tell an outage from a symbol the vendor
    lacks. From 2026-04-20 to 2026-09-24, 16 of 110 sessions had no fresh
    pick to fetch, so a 7-day straggler the vendor never serves would be the
    night's only call, and failing on it would open an issue on a quiet
    night. It is counted and retried instead."""
    rows = _rows((1, "BF.B", date(2026, 9, 24), "postmarket", "Covered Calls", 50.0, None))
    result, _, _ = _run(rows, bars_for=lambda t, d: pd.DataFrame())
    assert (result["no_bars"], result["fetches"], result["empty_fetches"]) == (1, 1, 1)
    assert not ew.run_failed(result)


def test_two_picks_on_one_empty_ticker_are_one_fetch_not_an_outage():
    """The rule counts vendor calls, not rows: two picks on one ticker's
    session share one call."""
    rows = _rows(
        (1, "BF.B", date(2026, 9, 24), "postmarket", "Covered Calls", 50.0, None),
        (2, "BF.B", date(2026, 9, 24), "postmarket", "Long Calls", 55.0, None),
    )
    result, _, _ = _run(rows, bars_for=lambda t, d: pd.DataFrame())
    assert (result["no_bars"], result["fetches"]) == (2, 1)
    assert not ew.run_failed(result)


def test_one_missing_ticker_is_not_an_outage():
    rows = _rows(
        (1, "AAA", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
        (2, "BBB", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
    )
    result, _, _ = _run(rows, bars_for=lambda t, d: (
        pd.DataFrame() if t == "BBB" else _day_bars(d)))
    assert (result["scored"], result["no_bars"]) == (1, 1)
    assert not ew.run_failed(result)


def test_writes_are_one_transaction_per_session_date():
    rows = _rows(
        (1, "AAA", date(2026, 9, 23), "postmarket", "Long Calls", 105.0, None),
        (2, "BBB", date(2026, 9, 23), "postmarket", "Long Calls", 105.0, None),
        (3, "CCC", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
    )
    _, _, engine = _run(rows)
    assert engine.transactions == 2          # 2026-09-24 and 2026-09-25
