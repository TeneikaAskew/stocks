"""Unit tests for `scripts/audit_data_freshness.py`.

The watchdog runs hourly via Cloud Scheduler and fires GitHub issues
on regressions. Wrong logic → noisy false alerts (cry-wolf) OR true
outages masked silent. Tests cover:

    - `most_recent_trading_day` UTC→ET conversion across DST + holiday
      walk-back (the load-bearing schedule logic)
    - `_query_freshness_one` status threshold (ok/warn/stale) +
      `min_rows_per_day` floor (the SPX silent-failure pattern)
    - `_query_freshness_one` "table doesn't exist" → status='unknown'
    - `_query_gap_scan` mid-window hole detection
    - `_query_value_sanity` flag-bad-rows-only behaviour
    - `FreshnessReport.overall_status` aggregation
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# most_recent_trading_day — schedule logic
# ──────────────────────────────────────────────────────────────────────


def test_before_close_returns_yesterday():
    """At 11 AM ET on a Tuesday, the most recent close is Monday."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Tue 2026-04-21 at 11:00 ET = 15:00 UTC (EDT, UTC-4)
    now = datetime(2026, 4, 21, 15, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 4, 20)  # Mon


def test_after_close_returns_today():
    """At 5 PM ET on a Tuesday, today's close is the most recent."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Tue 2026-04-21 at 17:00 ET = 21:00 UTC
    now = datetime(2026, 4, 21, 21, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 4, 21)


def test_weekend_walks_back_to_friday():
    """Sunday morning → Friday (the prior trading day)."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Sun 2026-04-26 at 10:00 UTC → ET 06:00, before close → Sat → Fri
    now = datetime(2026, 4, 26, 10, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 4, 24)  # Fri


def test_holiday_walks_back():
    """Day after a holiday → must skip the holiday. Memorial Day 2026
    is Mon 2026-05-25; Tuesday morning before close should walk back
    PAST Monday and Sunday and Saturday to Friday 2026-05-22."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Tue 2026-05-26 at 10:00 ET = 14:00 UTC, before close
    now = datetime(2026, 5, 26, 14, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 5, 22)


def test_dst_winter_uses_est():
    """In January (EST = UTC-5), 10 PM UTC = 5 PM ET → after close."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 2026-01-21 at 22:00 UTC = 17:00 EST → after close → Wed
    now = datetime(2026, 1, 21, 22, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 1, 21)
    # Sanity: at 20:00 UTC = 15:00 EST → before close → Tue
    now2 = datetime(2026, 1, 21, 20, 0, 0)
    assert most_recent_trading_day(now2) == date(2026, 1, 20)


def test_dst_summer_uses_edt():
    """In July (EDT = UTC-4), 21:00 UTC = 17:00 ET → after close."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 2026-07-15 at 21:00 UTC = 17:00 EDT → after close → Wed
    now = datetime(2026, 7, 15, 21, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 7, 15)


def test_thanksgiving_friday_is_holiday():
    """Black Friday 2026 (2026-11-27) is in the holiday set; Saturday
    morning should walk back through Fri→Thu (Thanksgiving)→Wed."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Sat 2026-11-28 at 10:00 ET = 15:00 UTC
    now = datetime(2026, 11, 28, 15, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 11, 25)  # Wed


# ──────────────────────────────────────────────────────────────────────
# _query_freshness_one — status thresholds + row-count floor
# ──────────────────────────────────────────────────────────────────────


def _patch_query(monkeypatch, df_or_exc):
    """Install a fake query_to_dataframe — accepts a DataFrame or an
    exception to raise."""
    from scripts import audit_data_freshness as mod

    def fake(sql, params=None):
        if isinstance(df_or_exc, BaseException):
            raise df_or_exc
        return df_or_exc.copy() if isinstance(df_or_exc, pd.DataFrame) else df_or_exc

    monkeypatch.setattr(mod, "query_to_dataframe", fake)


def test_freshness_ok_when_within_lag(monkeypatch):
    from scripts.audit_data_freshness import _query_freshness_one

    # 2 hours of lag against an expected-max of 24h → ok
    expected = date(2026, 4, 21)
    last_dt = datetime(2026, 4, 21, 18, 0, 0)  # 18:00 UTC vs 20:00 expected = 2h
    _patch_query(monkeypatch, pd.DataFrame([{"last_row_at": last_dt, "row_count_recent": 5000}]))

    check = {
        "name": "market_data_intraday", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
    }
    row = _query_freshness_one(check, expected)
    assert row.status == "ok"
    assert row.lag_hours == 2.0


def test_freshness_warn_when_1x_to_2x_lag(monkeypatch):
    from scripts.audit_data_freshness import _query_freshness_one

    # 30h lag against 24h expected = 1.25x → warn
    expected = date(2026, 4, 21)
    last_dt = datetime(2026, 4, 20, 14, 0, 0)
    _patch_query(monkeypatch, pd.DataFrame([{"last_row_at": last_dt, "row_count_recent": 100}]))
    check = {
        "name": "x", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
    }
    row = _query_freshness_one(check, expected)
    assert row.status == "warn"


def test_freshness_stale_when_over_2x_lag(monkeypatch):
    from scripts.audit_data_freshness import _query_freshness_one

    # 60h lag against 24h expected = 2.5x → stale
    expected = date(2026, 4, 21)
    last_dt = datetime(2026, 4, 18, 8, 0, 0)
    _patch_query(monkeypatch, pd.DataFrame([{"last_row_at": last_dt, "row_count_recent": 100}]))
    check = {
        "name": "x", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
    }
    row = _query_freshness_one(check, expected)
    assert row.status == "stale"


def test_min_rows_floor_flips_ok_to_stale(monkeypatch):
    """The SPX silent-failure pattern: timestamp looks fine but the
    fetcher wrote zero rows. min_rows_per_day catches it."""
    from scripts.audit_data_freshness import _query_freshness_one

    expected = date(2026, 4, 21)
    last_dt = datetime(2026, 4, 21, 19, 0, 0)  # 1h lag — would be ok
    _patch_query(monkeypatch, pd.DataFrame([{"last_row_at": last_dt, "row_count_recent": 5}]))
    check = {
        "name": "market_data_intraday", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
        "min_rows_per_day": 100,  # but only 5 rows landed → stale
    }
    row = _query_freshness_one(check, expected, ticker="SPX")
    assert row.status == "stale"
    assert row.row_count_recent == 5


def test_market_data_daily_check_filters_null_close():
    """Track A G.P0.3: the freshness audit must reject NULL-close
    placeholder rows that fetch-premarket-refresh writes — otherwise
    MAX(date) returns 'today' and the audit reports OK while the actual
    OHLCV write is stale. Config check guards this."""
    from scripts.audit_data_freshness import CHECKS

    md_check = next(c for c in CHECKS if c["name"] == "market_data_daily")
    assert md_check.get("where") == "close IS NOT NULL", (
        "market_data_daily must filter NULL-close rows so placeholder "
        "writes from fetch-premarket-refresh don't mask a stale fetcher."
    )


def test_market_data_daily_query_injects_close_not_null(monkeypatch):
    """End-to-end: dispatching `_query_freshness_one` for the
    market_data_daily check sends `close IS NOT NULL` into both the
    MAX(date) and COUNT(*) subqueries."""
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_freshness_one, CHECKS

    captured = {}

    def fake(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return pd.DataFrame([
            {"last_row_at": datetime(2026, 5, 8, 18, 0, 0), "row_count_recent": 0}
        ])

    monkeypatch.setattr(mod, "query_to_dataframe", fake)
    md_check = next(c for c in CHECKS if c["name"] == "market_data_daily")
    row = _query_freshness_one(md_check, date(2026, 5, 8), ticker="SPY")

    assert "close IS NOT NULL" in captured["sql"], (
        "Both the outer MAX query and the inline COUNT(*) subquery must "
        "filter NULL closes so placeholder rows can't fool the watchdog."
    )
    # row_count_recent=0 with min_rows_per_day=1 → status flips to stale
    assert row.status == "stale"
    assert row.row_count_recent == 0


def test_freshness_unknown_when_table_missing(monkeypatch):
    """Missing table → 'unknown' status (not 'stale'), so overall
    aggregation reports warn rather than failure."""
    from scripts.audit_data_freshness import _query_freshness_one

    _patch_query(monkeypatch, RuntimeError(
        'relation "missing_table" does not exist'
    ))
    check = {
        "name": "missing_table", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
    }
    row = _query_freshness_one(check, date(2026, 4, 21))
    assert row.status == "unknown"
    assert row.lag_hours is None


def test_freshness_stale_when_no_rows_at_all(monkeypatch):
    """Query returns df with last_row_at=None → table empty for filters."""
    from scripts.audit_data_freshness import _query_freshness_one

    _patch_query(monkeypatch, pd.DataFrame([
        {"last_row_at": None, "row_count_recent": 0}
    ]))
    check = {
        "name": "x", "ts_column": "ts",
        "ts_is_date": False, "expected_lag_hours": 24,
    }
    row = _query_freshness_one(check, date(2026, 4, 21))
    assert row.status == "stale"


def test_freshness_uses_market_close_not_wall_clock(monkeypatch):
    """Lag is measured against expected session close, not wall clock —
    otherwise Friday data looks 65h old on Monday morning. Test by
    using a now_utc that's much later than expected close, but data
    that lands at expected close → 0h lag."""
    from scripts.audit_data_freshness import _query_freshness_one

    expected = date(2026, 4, 17)  # Fri
    # Last row exactly at expected close (16:00 ET = 20:00 UTC)
    last_dt = datetime(2026, 4, 17, 20, 0, 0)
    _patch_query(monkeypatch, pd.DataFrame([{"last_row_at": last_dt, "row_count_recent": 100}]))
    check = {"name": "x", "ts_column": "ts", "ts_is_date": False,
             "expected_lag_hours": 24}

    # Wall clock is Mon morning — 65h after close; lag math should still be 0
    now = datetime(2026, 4, 20, 13, 0, 0)
    row = _query_freshness_one(check, expected, now_utc=now)
    assert row.lag_hours == 0.0
    assert row.status == "ok"


# ──────────────────────────────────────────────────────────────────────
# _query_gap_scan — mid-window holes
# ──────────────────────────────────────────────────────────────────────


def test_gap_scan_flags_missing_days_per_ticker(monkeypatch):
    """SPX missed 2026-04-15 in the last 5 trading days; SPY didn't."""
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_gap_scan

    # _recent_trading_days(2026-04-17 after-close, 5) = the last 5
    # weekdays ending Fri 04-17 = [04-17, 04-16, 04-15, 04-14, 04-13].
    # SPY rows for all 5; SPX missed 04-15.
    days = [date(2026, 4, 17), date(2026, 4, 16), date(2026, 4, 15),
            date(2026, 4, 14), date(2026, 4, 13)]
    rows = []
    for d in days:
        rows.append({"ticker": "SPY", "d": d, "c": 390})
        if d != date(2026, 4, 15):  # SPX missed Apr 15
            rows.append({"ticker": "SPX", "d": d, "c": 390})

    monkeypatch.setattr(
        mod, "query_to_dataframe",
        lambda sql, params: pd.DataFrame(rows),
    )

    check = {
        "name": "market_data_intraday", "ts_column": "ts",
        "ts_is_date": False, "per_ticker": True,
        "gap_scan_days": 5, "tickers": ["SPY", "SPX"],
    }
    # Anchor "now" so _recent_trading_days returns the same 5 days
    now = datetime(2026, 4, 17, 21, 0, 0)
    rows_out = _query_gap_scan(check, now)
    assert len(rows_out) == 1
    assert rows_out[0].ticker == "SPX"
    assert rows_out[0].status == "stale"
    assert "[gap]" in rows_out[0].table


def test_gap_scan_silent_when_no_gaps(monkeypatch):
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_gap_scan

    # 3 trading days ending Fri 04-17 = [04-17, 04-16, 04-15]
    days = [date(2026, 4, 17), date(2026, 4, 16), date(2026, 4, 15)]
    rows = [{"ticker": t, "d": d, "c": 100}
            for d in days for t in ("SPY", "QQQ")]
    monkeypatch.setattr(
        mod, "query_to_dataframe",
        lambda sql, params: pd.DataFrame(rows),
    )

    check = {
        "name": "x", "ts_column": "ts",
        "ts_is_date": False, "per_ticker": True,
        "gap_scan_days": 3, "tickers": ["SPY", "QQQ"],
    }
    now = datetime(2026, 4, 17, 21, 0, 0)
    out = _query_gap_scan(check, now)
    assert out == []


def test_gap_scan_returns_empty_for_non_per_ticker_check(monkeypatch):
    """`per_ticker=False` → not applicable, return []."""
    from scripts.audit_data_freshness import _query_gap_scan

    out = _query_gap_scan(
        {"name": "x", "per_ticker": False, "gap_scan_days": 5}, datetime.now()
    )
    assert out == []


# ──────────────────────────────────────────────────────────────────────
# _query_value_sanity — silent unless bad rows present
# ──────────────────────────────────────────────────────────────────────


def test_value_sanity_silent_when_clean(monkeypatch):
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_value_sanity

    monkeypatch.setattr(
        mod, "query_to_dataframe",
        lambda sql, params=None: pd.DataFrame([{"bad": 0}]),
    )
    out = _query_value_sanity(datetime(2026, 4, 21))
    assert out == []


def test_value_sanity_flags_bad_rows(monkeypatch):
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_value_sanity

    # First call returns clean, second returns 7 bad SPX rows, third clean
    call = {"n": 0}

    def fake(sql, params=None):
        call["n"] += 1
        if call["n"] == 2:
            return pd.DataFrame([{"bad": 7}])
        return pd.DataFrame([{"bad": 0}])

    monkeypatch.setattr(mod, "query_to_dataframe", fake)
    out = _query_value_sanity(datetime(2026, 4, 21))
    assert len(out) == 1
    assert "SPX" in out[0].table
    assert out[0].row_count_recent == 7
    assert out[0].status == "stale"


def test_value_sanity_skips_missing_tables(monkeypatch):
    """Don't fail the whole sanity sweep if one table is missing."""
    from scripts import audit_data_freshness as mod
    from scripts.audit_data_freshness import _query_value_sanity

    def fake(sql, params=None):
        raise RuntimeError('relation "etf_options_snapshots" does not exist')

    monkeypatch.setattr(mod, "query_to_dataframe", fake)
    out = _query_value_sanity(datetime(2026, 4, 21))
    assert out == []


# ──────────────────────────────────────────────────────────────────────
# FreshnessReport.overall_status — aggregation
# ──────────────────────────────────────────────────────────────────────


def test_overall_status_stale_dominates():
    from scripts.audit_data_freshness import FreshnessReport, FreshnessRow

    rep = FreshnessReport(
        checked_at="x", expected_market_close="y",
        rows=[
            FreshnessRow(table="a", ticker=None, last_row_at=None,
                         expected_latest="x", lag_hours=None,
                         expected_max_hours=24, status="ok"),
            FreshnessRow(table="b", ticker=None, last_row_at=None,
                         expected_latest="x", lag_hours=None,
                         expected_max_hours=24, status="warn"),
            FreshnessRow(table="c", ticker=None, last_row_at=None,
                         expected_latest="x", lag_hours=None,
                         expected_max_hours=24, status="stale"),
        ],
    )
    assert rep.overall_status == "stale"


def test_overall_status_warn_when_only_unknown_and_ok():
    """Unknown is NOT silent — escalates to warn so missing tables
    show up in the dashboard."""
    from scripts.audit_data_freshness import FreshnessReport, FreshnessRow

    rep = FreshnessReport(
        checked_at="x", expected_market_close="y",
        rows=[
            FreshnessRow(table="a", ticker=None, last_row_at=None,
                         expected_latest="x", lag_hours=None,
                         expected_max_hours=24, status="ok"),
            FreshnessRow(table="b", ticker=None, last_row_at=None,
                         expected_latest="x", lag_hours=None,
                         expected_max_hours=24, status="unknown"),
        ],
    )
    assert rep.overall_status == "warn"


def test_overall_status_unknown_when_no_rows():
    from scripts.audit_data_freshness import FreshnessReport

    rep = FreshnessReport(checked_at="x", expected_market_close="y", rows=[])
    assert rep.overall_status == "unknown"


# ── settle_hour_et: per-table fetcher-aware day cutoff ───────────────────────
# Pre-fix bug: most_recent_trading_day() always returned today after 16 ET
# (market close), but after-hours fetchers don't write today's row until
# 21-23 ET. So between market close and fetcher run, the gap-scan flagged
# today's row as missing → STALE → freshness watchdog fired hourly.
# fetch-market-data Cloud Scheduler is at 23:00 ET; etf_options_snapshots
# (PR #489) at 21:00 ET. The settle_hour_et knob lets each CHECK declare
# when day-D's row is "expected" so the gap-scan doesn't false-flag.


def test_settle_hour_default_is_market_close():
    """Default settle_hour_et=16 preserves prior behavior."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 2026-05-13 17:00 ET = 21:00 UTC. Past market close (16 ET) →
    # today is most recent.
    now = datetime(2026, 5, 13, 21, 0, 0)
    assert most_recent_trading_day(now) == date(2026, 5, 13)


def test_settle_hour_23_returns_yesterday_when_before_settle():
    """For market_data_daily (settle_hour_et=23), Wed 17 ET should return
    Tue (today's row not expected yet since fetcher hasn't run)."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 2026-05-13 17:00 ET = 21:00 UTC — past 16 (market close) but
    # before 23 (fetcher run). Should return Tue.
    now = datetime(2026, 5, 13, 21, 0, 0)
    assert most_recent_trading_day(now, settle_hour_et=23) == date(2026, 5, 12)


def test_settle_hour_23_returns_today_when_past_settle():
    """For market_data_daily, Wed 23:30 ET (= Thu 03:30 UTC) is past
    settle, today's row expected, returns today."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 2026-05-13 23:30 ET = Thu 2026-05-14 03:30 UTC
    now = datetime(2026, 5, 14, 3, 30, 0)
    assert most_recent_trading_day(now, settle_hour_et=23) == date(2026, 5, 13)


def test_settle_hour_21_for_etf_options():
    """etf_options_snapshots fetcher fires 21:00 ET. Wed 19 ET → yesterday;
    Wed 22 ET → today."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Wed 19:00 ET = 23:00 UTC. Before settle 21 → yesterday.
    pre = datetime(2026, 5, 13, 23, 0, 0)
    assert most_recent_trading_day(pre, settle_hour_et=21) == date(2026, 5, 12)
    # Wed 22:00 ET = Thu 02:00 UTC. After settle 21 → today.
    post = datetime(2026, 5, 14, 2, 0, 0)
    assert most_recent_trading_day(post, settle_hour_et=21) == date(2026, 5, 13)


def test_recent_trading_days_uses_settle_hour():
    """_recent_trading_days plumbs settle_hour_et through to
    most_recent_trading_day so the gap scan rolls back when before settle."""
    from scripts.audit_data_freshness import _recent_trading_days

    # Wed 17 ET = 21 UTC. settle_hour_et=23 (market_data_daily) → end at Tue.
    now = datetime(2026, 5, 13, 21, 0, 0)
    days = _recent_trading_days(now, n=3, settle_hour_et=23)
    # End should be Tue 5/12, going back: Tue, Mon, Fri
    assert days == [date(2026, 5, 12), date(2026, 5, 11), date(2026, 5, 8)]


def test_settle_hour_walks_past_weekend():
    """Settle-hour rollback also respects weekend skip. Sat morning with
    settle_hour_et=23 → previous Friday."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Sat 2026-05-16 10:00 UTC. Way past Friday's settle (23 ET Fri =
    # Sat 03 UTC). settle_hour_et=23 → expected = Fri 5/15.
    now = datetime(2026, 5, 16, 10, 0, 0)
    assert most_recent_trading_day(now, settle_hour_et=23) == date(2026, 5, 15)


def test_check_dicts_declare_settle_hour_for_after_hours_fetchers():
    """Regression guard: the after-hours fetchers must declare
    settle_hour_et so the cron rollouts stay in sync with the watchdog."""
    from scripts.audit_data_freshness import CHECKS

    by_name = {c["name"]: c for c in CHECKS}
    # market_data_daily — 23:00 ET cron, no lag (writes today's bar)
    assert by_name["market_data_daily"]["settle_hour_et"] == 23
    assert by_name["market_data_daily"].get("settle_lag_days", 0) == 0
    # etf_options_snapshots — 21:00 ET cron (PR #489 av-options-daily)
    assert by_name["etf_options_snapshots"]["settle_hour_et"] == 21
    assert by_name["etf_options_snapshots"].get("settle_lag_days", 0) == 0
    # market_data_intraday — 21:00 ET cron Tue-Sat, picks up D-1 bars
    # (Tue 21 ET writes Mon's bars). Codex P2 on PR #494.
    assert by_name["market_data_intraday"]["settle_hour_et"] == 21
    assert by_name["market_data_intraday"]["settle_lag_days"] == 1


def test_spx_not_monitored_in_market_data_daily():
    """SPX must NOT be in the market_data_daily freshness check. The S&P
    500 *index* has no genuine OHLCV feed (AlphaVantage TIME_SERIES_DAILY
    excludes index symbols); the old FRED-SP500 → SPX hack was removed
    2026-05-15. SPX options Greeks derive spot via put-call parity, so
    no market_data_daily SPX row is needed. SPX remains valid for the
    etf_options_snapshots check (AV does provide SPX *option* chains)."""
    from scripts.audit_data_freshness import CHECKS

    md_checks = [c for c in CHECKS if c["name"] == "market_data_daily"]
    assert len(md_checks) == 1, "expected exactly 1 market_data_daily check"
    assert "SPX" not in md_checks[0]["tickers"], (
        "SPX must not be monitored in market_data_daily — it has no "
        "real index OHLCV source"
    )
    # SPX IS still monitored for options (AV provides SPX option chains).
    opt_check = next(c for c in CHECKS if c["name"] == "etf_options_snapshots")
    assert "SPX" in opt_check["tickers"]


# ── settle_lag_days: writer fires N trading days after the data ─────────────


def test_settle_lag_1_intraday_pre_settle_returns_friday_on_monday():
    """av-intraday-nightly cron is Tue-Sat at 21 ET. On Mon morning, the
    most recent settled day is Friday (whose bars were written Sat 21 ET).
    Mon's bars won't be written until Tue 21 ET."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Mon 2026-05-11 10:00 ET = 14:00 UTC. Pre-settle on Mon, lag=1 →
    # most recent settled = Friday 5/8.
    now = datetime(2026, 5, 11, 14, 0, 0)
    result = most_recent_trading_day(now, settle_hour_et=21, settle_lag_days=1)
    assert result == date(2026, 5, 8)


def test_settle_lag_1_intraday_post_settle_on_tuesday_returns_monday():
    """Tue 22 ET — the Tue 21 ET cron has fired and written Mon's bars."""
    from scripts.audit_data_freshness import most_recent_trading_day

    # Tue 2026-05-12 22:00 ET = Wed 02:00 UTC.
    now = datetime(2026, 5, 13, 2, 0, 0)
    result = most_recent_trading_day(now, settle_hour_et=21, settle_lag_days=1)
    assert result == date(2026, 5, 11)


def test_settle_lag_1_pre_settle_on_tuesday_returns_friday():
    """Tue 19 ET — Tue 21 ET cron has NOT fired. Mon's bars NOT yet
    expected. Most recent settled = Friday."""
    from scripts.audit_data_freshness import most_recent_trading_day

    now = datetime(2026, 5, 12, 23, 0, 0)  # Tue 19 ET = 23 UTC
    result = most_recent_trading_day(now, settle_hour_et=21, settle_lag_days=1)
    assert result == date(2026, 5, 8)


def test_settle_lag_0_unaffected_by_new_param():
    """Default settle_lag_days=0 preserves prior behavior."""
    from scripts.audit_data_freshness import most_recent_trading_day

    now = datetime(2026, 5, 14, 2, 0, 0)  # Wed 22 ET
    assert most_recent_trading_day(now, settle_hour_et=21) == date(2026, 5, 13)
    assert most_recent_trading_day(
        now, settle_hour_et=21, settle_lag_days=0,
    ) == date(2026, 5, 13)


def test_recent_trading_days_with_lag_1():
    """_recent_trading_days plumbs settle_lag_days through."""
    from scripts.audit_data_freshness import _recent_trading_days

    now = datetime(2026, 5, 14, 2, 0, 0)  # Wed 22 ET
    days = _recent_trading_days(now, n=3, settle_hour_et=21, settle_lag_days=1)
    # Anchor=Wed (post-21 ET), lag=1 → end at Tue 5/12, going back: Tue, Mon, Fri
    assert days == [date(2026, 5, 12), date(2026, 5, 11), date(2026, 5, 8)]
