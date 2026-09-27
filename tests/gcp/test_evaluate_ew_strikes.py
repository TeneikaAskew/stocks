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

import contextlib
import io
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
from gcp.fetchers import fetch_market_data as fmd  # noqa: E402


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


def _answer(x):
    """A fake vendor answer, as fetch_minute_bars returns it: (bars, reason).
    A bare frame is a fetch that came back: `success`, or `no_bars_on_date`
    when it is empty, the vendor's month without that day."""
    if isinstance(x, tuple):
        return x
    return x, ("success" if not x.empty else "no_bars_on_date")


@contextlib.contextmanager
def _patched(rows: pd.DataFrame, bars_for, now_utc: str):
    """The DB, vendor and clock patched. Yields (fetch_calls, engine)."""
    calls: list = []
    engine = _Engine()

    def fake_fetch(ticker, fetch_date, api_key, *args, **kw):
        calls.append((ticker, fetch_date, kw.get("adjusted", args[0] if args else None)))
        return _answer(bars_for(ticker, fetch_date) if bars_for is not None
                       else _day_bars(fetch_date))

    with patch("gcp.database.query_to_dataframe", return_value=rows), \
         patch("gcp.database.get_engine", return_value=engine), \
         patch("gcp.fetchers.fetch_market_data.fetch_minute_bars", create=True,
               side_effect=fake_fetch), \
         patch("gcp.fetchers.evaluate_ew_strikes._now_utc", create=True,
               return_value=pd.Timestamp(now_utc, tz="UTC")), \
         patch("time.sleep"):
        yield calls, engine


def _run(rows: pd.DataFrame, *, bars_for=None, now_utc="2026-09-30 12:00",
         **kwargs):
    """Run evaluate_range with the DB, vendor and clock patched. Returns
    (result, fetch_calls, engine)."""
    start = kwargs.pop("start", date(2026, 9, 1))
    end = kwargs.pop("end", date(2026, 9, 30))
    with _patched(rows, bars_for, now_utc) as (calls, engine):
        result = ew.evaluate_range(start, end, **kwargs)
    return result, calls, engine


def _main(argv: list[str], rows: pd.DataFrame, *, bars_for=None,
          now_utc="2026-09-30 12:00"):
    """Run main() patched, as the job runs. Returns (exit code, the counters
    it printed, fetch_calls, engine)."""
    out = io.StringIO()
    with _patched(rows, bars_for, now_utc) as (calls, engine), \
         contextlib.redirect_stdout(out):
        rc = ew.main(argv)
    printed = out.getvalue().split()[1:]
    return rc, {k: int(v) for k, v in (kv.split("=") for kv in printed)}, calls, engine


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
    """--force means the stored verdict is not trusted. A row the vendor
    answered for without bars is cleared to NULL for the nightly run to fill,
    never left holding a verdict computed against the wrong session. SPY has
    bars, so the empty answer is about this pick, not the vendor (#1181)."""
    rows = _rows((7, "XYZ", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, "HIT"))
    result, _, engine = _run(rows, force=True, bars_for=lambda t, d: (
        _day_bars(d) if t == "SPY" else pd.DataFrame()))
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


# ── what the vendor said, and when a night is an outage (#1181) ────────

def _two_picks(verdict=None):
    return _rows(
        (7, "AAA", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, verdict),
        (8, "BBB", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, verdict),
    )


_SEP24 = ["--start", "2026-09-24", "--end", "2026-09-24"]


def _cleared(engine) -> list[int]:
    return [p["id"] for sql, ps in engine.statements if "= NULL" in sql for p in ps]


# The wp7kf fill pass on 2026-09-26: the five picks still unscored, and what
# AlphaVantage said to each in the job log. Every call came back empty, so the
# old rule read an outage: exit 1 on both attempts, and #1180 was opened.
_WP7KF = [
    (1, "TGEN", date(2026, 5, 13), "TGEN", "invalid_api_call"),
    (2, "VSCO", date(2026, 6, 2), "VSCO", "no_bars_on_date"),
    (3, "MOG.A", date(2026, 7, 31), "MOG-A", "invalid_api_call"),
    (4, "ORLA", date(2026, 8, 4), "ORLA", "invalid_api_call"),
    (5, "BF.B", date(2026, 9, 2), "BF-B", "invalid_api_call"),
]


def test_the_wp7kf_night_is_not_an_outage():
    """Four symbols the vendor refused and one day it has no bars for are
    answers about the picks. SPY on the latest session fetched has bars, so the
    vendor is up and the run exits 0. Even the dashed share classes are refused
    here, so this is the outage rule alone."""
    rows = _rows(*[(i, t, d, "premarket", "Long Calls", 100.0, None)
                   for i, t, d, _, _ in _WP7KF])
    said = {sent: (pd.DataFrame(), reason) for _, _, _, sent, reason in _WP7KF}
    rc, n, calls, engine = _main(
        ["--start", "2026-04-13", "--end", "2026-09-25"], rows,
        bars_for=lambda t, d: _day_bars(d) if t == "SPY" else said[t])
    assert rc == 0
    assert (n["fetches"], n["empty_fetches"], n["unsupported_symbol"]) == (5, 5, 4)
    assert (n["no_bars"], n["fetch_failed"], n["scored"]) == (5, 0, 0)
    assert (n["canary_fetches"], n["canary_empty"]) == (1, 0)
    assert calls[-1][:2] == ("SPY", "2026-09-02")      # the latest session fetched
    assert engine.statements == []


def test_a_share_class_is_requested_in_the_vendors_dashed_form():
    """Earnings Whispers writes BF.B and MOG.A. AlphaVantage lists them as
    BF-B and MOG-A (SYMBOL_SEARCH, 2026-09-26) and refused the dotted form on
    the wp7kf night."""
    rows = _rows(
        (1, "BF.B", date(2026, 9, 2), "premarket", "Covered Calls", 50.0, None),
        (2, "MOG.A", date(2026, 7, 31), "premarket", "Long Calls", 105.0, None),
    )
    result, calls, _ = _run(rows, start=date(2026, 7, 1))
    assert sorted(t for t, _, _ in calls) == ["BF-B", "MOG-A"]
    assert result["scored"] == 2


@pytest.mark.parametrize("reason, counter, outcome", [
    ("invalid_api_call", "unsupported_symbol", "no_bars"),
    ("no_bars_on_date", None, "no_bars"),
    ("rate_limit", "rate_limited", "fetch_failed"),
    ("info_message", "rate_limited", "fetch_failed"),
    ("request_error", "transport_error", "fetch_failed"),
    ("no_timeseries", "transport_error", "fetch_failed"),
])
def test_each_vendor_answer_is_counted_by_what_it_says(reason, counter, outcome):
    """A refused symbol or a day without bars is an answer about the pick. A
    rate limit, a transport error or a reply without a time series says
    nothing about it, so the pick is left for the next run."""
    result, _, _ = _run(_two_picks(), bars_for=lambda t, d: (
        (pd.DataFrame(), reason) if t == "AAA" else _day_bars(d)))
    assert (result["scored"], result[outcome]) == (1, 1)
    kinds = ("unsupported_symbol", "rate_limited", "transport_error")
    assert {k: result[k] for k in kinds} == {k: int(k == counter) for k in kinds}
    assert (result["fetches"], result["empty_fetches"], result["canary_fetches"]) == (2, 1, 0)


@pytest.mark.parametrize("reason", ["rate_limit", "invalid_api_call", "request_error"])
def test_every_call_and_the_canary_empty_is_an_outage(reason):
    """SPY came back without bars too, so the vendor or the request is broken,
    whatever the symbols. AlphaVantage answers a bad API key with the same
    `Error Message` as an unknown symbol, so a refused SPY counts here."""
    rc, n, calls, _ = _main(_SEP24, _two_picks(),
                            bars_for=lambda t, d: (pd.DataFrame(), reason))
    assert rc == 1
    assert (n["empty_fetches"], n["canary_fetches"], n["canary_empty"]) == (2, 1, 1)
    assert [t for t, _, _ in calls] == ["AAA", "BBB", "SPY"]


def test_a_rate_limited_night_with_a_working_vendor_is_retried_not_failed():
    """SPY answers, so the limit was transient. The picks stay unscored for the
    next night's 7-day lookback, and nothing is written."""
    rc, n, _, engine = _main(_SEP24, _two_picks(), bars_for=lambda t, d: (
        _day_bars(d) if t == "SPY" else (pd.DataFrame(), "rate_limit")))
    assert rc == 0
    assert (n["fetch_failed"], n["rate_limited"], n["canary_empty"]) == (2, 2, 0)
    assert engine.statements == []


def test_no_canary_call_when_any_call_returned_bars():
    """The canary costs a vendor call, and only a night whose every call came
    back empty pays it."""
    rc, n, calls, _ = _main(_SEP24, _two_picks(), bars_for=lambda t, d: (
        (pd.DataFrame(), "invalid_api_call") if t == "BBB" else _day_bars(d)))
    assert rc == 0
    assert [t for t, _, _ in calls] == ["AAA", "BBB"]
    assert (n["scored"], n["no_bars"], n["canary_fetches"]) == (1, 1, 0)


@pytest.mark.parametrize("spy_has_bars, rc", [(True, 0), (False, 1)])
def test_a_lone_empty_call_is_decided_by_the_canary(spy_has_bars, rc):
    """Before #1181 a night's only call could never be an outage, even with the
    vendor down: from 2026-04-20 to 2026-09-24, 16 of 110 sessions had no fresh
    pick to fetch. The canary decides it now."""
    rows = _rows((1, "BF.B", date(2026, 9, 24), "postmarket", "Covered Calls", 50.0, None))
    got, n, _, _ = _main(_SEP24, rows, bars_for=lambda t, d: (
        _day_bars(d) if t == "SPY" and spy_has_bars else pd.DataFrame()))
    assert got == rc
    assert (n["fetches"], n["canary_fetches"], n["canary_empty"]) == (1, 1, int(not spy_has_bars))


def test_two_picks_on_one_ticker_are_one_call():
    """Calls, not rows: two picks on one ticker's session share one call."""
    rows = _rows(
        (1, "BF.B", date(2026, 9, 24), "postmarket", "Covered Calls", 50.0, None),
        (2, "BF.B", date(2026, 9, 24), "postmarket", "Long Calls", 55.0, None),
    )
    rc, n, calls, _ = _main(_SEP24, rows, bars_for=lambda t, d: (
        _day_bars(d) if t == "SPY" else pd.DataFrame()))
    assert rc == 0
    assert (n["no_bars"], n["fetches"]) == (2, 1)
    assert [t for t, _, _ in calls] == ["BF-B", "SPY"]


def test_force_keeps_a_verdict_the_vendor_gave_no_answer_for():
    """--force clears a verdict only on an answer about the pick. A rate limit
    is not one: the stored verdict stays, and the run exits 1, because a
    partial re-score must not read as a complete one."""
    rc, n, _, engine = _main(_SEP24 + ["--force"], _two_picks("HIT"), bars_for=lambda t, d: (
        (pd.DataFrame(), "rate_limit") if t == "AAA" else _day_bars(d)))
    assert rc == 1
    assert (n["fetch_failed"], n["scored"], n["cleared"]) == (1, 1, 0)
    assert _cleared(engine) == []


def test_force_clears_nothing_on_refusals_until_the_vendor_has_answered():
    """A bad key reads as `Error Message` for every symbol. Until a call or the
    canary returns bars, a refusal is not evidence about the pick, so --force
    clears nothing and the run exits 1."""
    rc, n, _, engine = _main(_SEP24 + ["--force"], _two_picks("HIT"),
                             bars_for=lambda t, d: (pd.DataFrame(), "invalid_api_call"))
    assert rc == 1
    assert (n["cleared"], n["canary_empty"]) == (0, 1)
    assert _cleared(engine) == []


def test_force_clears_a_refused_symbol_once_the_vendor_has_answered():
    result, _, engine = _run(_two_picks("HIT"), force=True, bars_for=lambda t, d: (
        (pd.DataFrame(), "invalid_api_call") if t == "AAA" else _day_bars(d)))
    assert _cleared(engine) == [7]
    assert (result["cleared"], result["scored"]) == (1, 1)


def test_the_force_clears_land_in_one_transaction_after_the_updates():
    """Held clears are written together at the end, once the vendor is known
    to answer; the re-scored rows keep their per-session transactions."""
    rows = _rows(
        (7, "AAA", date(2026, 9, 23), "postmarket", "Long Calls", 105.0, "HIT"),
        (8, "BBB", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, "HIT"),
        (9, "CCC", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, "MISS"),
    )
    result, _, engine = _run(rows, force=True, bars_for=lambda t, d: (
        pd.DataFrame() if t in ("AAA", "BBB") else _day_bars(d)))
    assert _cleared(engine) == [7, 8]
    assert "= NULL" in engine.statements[-1][0]
    assert (result["cleared"], result["scored"]) == (2, 1)


# ── the vendor's answer, as fetch_minute_bars names it (#1181) ─────────


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _month(day: str) -> dict:
    """A TIME_SERIES_INTRADAY reply holding three bars on `day`."""
    ts = {f"{day} 09:3{i}:00": {"1. open": "10", "2. high": "11", "3. low": "9",
                                  "4. close": "10.5", "5. volume": "100"}
          for i in range(3)}
    return {"Meta Data": {}, "Time Series (1min)": ts}


@pytest.mark.parametrize("payload, reason", [
    ({"Error Message": "Invalid API call. Please retry or visit the documentation"},
     "invalid_api_call"),
    ({"Note": "Thank you for using Alpha Vantage! Please consider spreading out"},
     "rate_limit"),
    ({"Information": "Thank you for using Alpha Vantage! This is a premium endpoint"},
     "info_message"),
    ({"Meta Data": {}}, "no_timeseries"),
    ({"Meta Data": {}, "Time Series (1min)": {}}, "no_timeseries"),
    (_month("2026-06-01"), "no_bars_on_date"),
])
def test_fetch_minute_bars_names_the_vendors_answer(payload, reason):
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        bars, got = fmd.fetch_minute_bars("VSCO", "2026-06-02", "key")
    assert bars.empty and got == reason


def test_a_transport_failure_is_named():
    with patch.object(fmd.requests, "get", side_effect=fmd.requests.ConnectionError("reset")):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
    assert bars.empty and got == "request_error"


@pytest.mark.parametrize("payload", [
    [], None, "Invalid API call", 5,
    {"Meta Data": {}, "Time Series (1min)": ["2026-09-25 09:30:00"]},
    {"Meta Data": {}, "Time Series (1min)": "unavailable"},
])
def test_a_reply_that_is_not_a_json_object_is_the_vendors_shape(payload):
    """Codex on #1202: a body that parses as JSON but is not an object, or a
    time series that is not one, raised AttributeError or TypeError out of
    this function. Before #1181 a bare `except Exception` made it an empty
    frame; it is the vendor's reply, so it is named like any other reply with
    no time series. The daily fetcher then still falls back to the daily
    endpoint, and the premarket refresh, which has no per-ticker guard, keeps
    going."""
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
        df = fmd.fetch_minute_data("SPY", "2026-09-25", "key")
    assert bars.empty and got == "no_timeseries"
    assert isinstance(df, pd.DataFrame) and df.empty


def test_bars_on_the_date_come_back_ok():
    with patch.object(fmd.requests, "get", return_value=_Resp(_month("2026-09-25"))):
        bars, got = fmd.fetch_minute_bars("SPY", "2026-09-25", "key")
    assert got == "success" and len(bars) == 3 and set(bars["ticker"]) == {"SPY"}


@pytest.mark.parametrize("payload, n", [(_month("2026-09-25"), 3), ({"Note": "x"}, 0)])
def test_fetch_minute_data_keeps_its_contract(payload, n):
    """The daily fetcher and the premarket refresh still get one frame, empty
    on any failure. The reason is for callers that ask for it."""
    with patch.object(fmd.requests, "get", return_value=_Resp(payload)):
        df = fmd.fetch_minute_data("SPY", "2026-09-25", "key")
    assert isinstance(df, pd.DataFrame) and len(df) == n


@pytest.mark.parametrize("ticker, sent", [("BF.B", "BF-B"), ("MOG.A", "MOG-A"), ("SPY", "SPY")])
def test_av_listed_symbol(ticker, sent):
    assert fmd.av_listed_symbol(ticker) == sent


def test_writes_are_one_transaction_per_session_date():
    rows = _rows(
        (1, "AAA", date(2026, 9, 23), "postmarket", "Long Calls", 105.0, None),
        (2, "BBB", date(2026, 9, 23), "postmarket", "Long Calls", 105.0, None),
        (3, "CCC", date(2026, 9, 24), "postmarket", "Long Calls", 105.0, None),
    )
    _, _, engine = _run(rows)
    assert engine.transactions == 2          # 2026-09-24 and 2026-09-25
