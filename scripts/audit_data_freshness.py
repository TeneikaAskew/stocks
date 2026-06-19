#!/usr/bin/env python3
"""
Audit Cloud SQL data freshness across the platform.

Queries every critical data table, computes the age of its most recent row,
and compares against expected cadence. Catches failures like the April 13
`market_data_daily` gap that sat silent for 4+ days.

Usage:
    python scripts/audit_data_freshness.py                  # Pretty terminal table
    python scripts/audit_data_freshness.py --json           # JSON output
    python scripts/audit_data_freshness.py --strict         # Exit 1 if any table is stale (for CI)

Required env vars: CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# Add project root for gcp.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gcp.database import is_cloud_sql_configured, query_to_dataframe  # noqa: E402

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────

TICKERS = ("IWM", "SPY", "QQQ", "SPX")

# Tables to check. Each entry describes how to compute freshness for one table.
#
# Fields:
#   name: Cloud SQL table name
#   ts_column: the date/timestamp column to use for "most recent row"
#   ts_is_date: True if the column is DATE, False if TIMESTAMPTZ
#   expected_lag_hours: warn if last_row_at is older than this many hours from
#                       the latest expected trading session
#   per_ticker: if True, compute freshness per ticker and report each
#   tickers: override the default ticker list
#   where: optional extra WHERE clause (e.g. to filter out archival rows)
#   tolerate_holidays: if True, don't flag as stale on market holidays
CHECKS: list[dict] = [
    {
        "name": "market_data_daily",
        "ts_column": "date",
        "ts_is_date": True,
        "expected_lag_hours": 30,
        "per_ticker": True,
        # SPX is intentionally NOT here. SPX is the S&P 500 *index* —
        # AlphaVantage's TIME_SERIES_DAILY does not cover index symbols,
        # so SPX never had a genuine OHLCV feed. It used to be written
        # from FRED's SP500 series (close-only, 1-2 trading days late);
        # that confusing not-real-market-data hack was removed
        # 2026-05-15. SPX options Greeks derive spot from the live
        # option chain via put-call parity — they do not need a
        # market_data_daily row. See gcp/fetchers/fetch_fred_rates.py.
        "tickers": ("IWM", "SPY", "QQQ"),
        # Filter out the NULL-close placeholder rows the
        # `fetch-premarket-refresh` job writes during pre-market hours.
        # Without this, MAX(date) returns today even when the actual OHLCV
        # write hasn't happened yet, masking a stale fetcher (the exact
        # failure mode the 2026-05-08 audit caught — Track A G.P0.3).
        "where": "close IS NOT NULL",
        "min_rows_per_day": 1,
        "gap_scan_days": 5,
        # fetch-market-data-daily Cloud Scheduler fires 23:00 ET — give
        # 30min buffer for AV pull + DB upsert. Today's row is "expected"
        # starting 23:30 ET; before that the gap-scan rolls back to D-1.
        "settle_hour_et": 23,
    },
    {
        "name": "market_data_intraday",
        "ts_column": "ts",
        "ts_is_date": False,
        "expected_lag_hours": 30,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ"),
        "where": "interval = '1min'",
        "min_rows_per_day": 350,    # ~full RTH session at 1-min
        "gap_scan_days": 5,
        # av-intraday-nightly cron `0 21 * * 2-6` ET — fires Tue-Sat at
        # 21 ET, picking up the PREVIOUS day's bars (Tue 21 ET writes
        # Mon's bars; Sat 21 ET writes Fri's). So intraday data lags by
        # 1 trading day relative to the cron's fire date. Codex P2 on
        # PR #494 caught this: settle_hour_et=21 alone would expect
        # Mon's bars at Mon 21 ET (when nothing has fired) and false-
        # flag every Tuesday morning.
        "settle_hour_et": 21,
        "settle_lag_days": 1,
    },
    {
        "name": "etf_options_snapshots",
        "ts_column": "snapshot_date",
        "ts_is_date": True,
        "expected_lag_hours": 30,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ", "SPX"),
        "where": "data_source = 'alphavantage'",
        "min_rows_per_day": 100,    # chain is typically 1k+, 100 is a conservative floor
        "gap_scan_days": 5,
        # av-options-daily fires 21:00 ET Mon-Fri (PR #489) → today's
        # chain expected by ~21:30 ET.
        "settle_hour_et": 21,
    },
    # Skipped 2026-05-10: earnings_options_snapshots is an orphan table.
    # No live writer; only `gcp/migrate_to_gcp.py` (the one-time historical
    # migration) ever populated it. No production read path consumes it —
    # briefs, insights, ranker, summarizers, and catalyst-proximity all
    # read `earnings_calendar` instead. Re-enable this entry once a live
    # writer ships (currently no plan).
    # {
    #     "name": "earnings_options_snapshots",
    #     "ts_column": "snapshot_date",
    #     "ts_is_date": True,
    #     "expected_lag_hours": 24,
    #     "per_ticker": False,
    #     "ticker_column": "symbol",
    # },
    {
        "name": "earnings_calendar",
        "ts_column": "fetched_at",
        "ts_is_date": False,
        "expected_lag_hours": 192,  # Weekly = ~8 days OK
        "per_ticker": False,
    },
    {
        "name": "economic_events",
        "ts_column": "inserted_at",  # event_date is the event schedule (future); inserted_at is the fetch time
        "ts_is_date": False,
        "expected_lag_hours": 192,  # Weekly
        "per_ticker": False,
    },
    {
        "name": "premarket_analysis",
        "ts_column": "analysis_date",
        "ts_is_date": True,
        "expected_lag_hours": 30,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ"),
    },
    {
        # The insight-pipeline Cloud Run job (insight-pipeline-daily Cloud
        # Scheduler, weekday mornings) is the only writer. `as_of` is the
        # report's effective session date. This is the failure surface for
        # the pipeline now that daily-insight-reports.yml no longer carries
        # its own GitHub Actions cron — a failed run leaves this stale.
        "name": "insight_reports",
        "ts_column": "as_of",
        "ts_is_date": False,
        "expected_lag_hours": 30,
        "per_ticker": True,
        "tickers": ("SPY", "IWM", "QQQ"),
    },
    {
        "name": "signal_alerts",
        "ts_column": "alert_date",
        "ts_is_date": True,
        "expected_lag_hours": 30,
        "per_ticker": False,
    },
    {
        "name": "daily_rates",
        "ts_column": "date",
        "ts_is_date": True,
        "expected_lag_hours": 72,   # FRED publishes with 1-2 day lag
        "per_ticker": False,
    },
    # historical_signals — written by historical-signals-watchlist daily at
    # 05:00 UTC. Audit 2026-06-02 (F11 in
    # docs/incidents/2026-06-01-pipeline-failures-audit.md) found this table
    # going stale silently because the writer job's per-ticker exception
    # handler swallowed errors and reported `success` even when ALL tickers
    # crashed. Tracking it here means the next watchdog run after a silent
    # zero-output day will flag it.
    {
        "name": "historical_signals",
        "ts_column": "inserted_at",
        "ts_is_date": False,
        "expected_lag_hours": 36,           # daily cron at 05:00 UTC + 6h buffer
        "per_ticker": False,
        "writer_job": "historical-signals-watchlist",
        "settle_hour_et": 1,                # 05:00 UTC ≈ 01:00 ET
        "tolerate_holidays": True,
    },
    # strat_features_5m / _15m / _30m — written by strat-engine in
    # default-mode (incremental). 2026-06-19 investigation found these
    # three tables had been silently stale since 2026-06-09 because
    # strat-engine had NO scheduler entry at all and its job-spec
    # `--args` had been hand-edited to a one-off `--recompute-cols=...`
    # invocation. Magnitude-inference (correctly per §3.7) failed
    # ZERO-OUTPUT every cron — but the watchdog never caught the
    # upstream staleness because these tables weren't in CHECKS.
    #
    # This PR fixes both ends: scheduler registered in deploy.sh, plus
    # these CHECKS entries so any future stall — scheduler-failure,
    # job-spec drift, or data-quality bug — alerts within one
    # watchdog cycle. settle_hour_et=23 matches the strat-engine-daily
    # cron (Mon-Fri 23:35 ET).
    # Codex P2 #622 — expected_lag_hours alone wouldn't flag a single
    # missed daily run: MAX(ts) only advances ~24h per run, so a missed
    # Tuesday run leaves Wednesday's check at ~36h which would only
    # `warn`, not `stale`. The `min_rows_per_day` + `gap_scan_days`
    # pattern (mirrored from market_data_intraday / etf_options_snapshots)
    # checks "did today's expected partition land at all?" — a missed
    # run fails IMMEDIATELY because today's row_count == 0 < min.
    #
    # min_rows_per_day floors (conservative RTH-only counts; the builder
    # may emit more if extended-hours bars are configured):
    #   5m  → 70  (RTH 6.5h × 12 bars/hr = 78, give 10% margin)
    #   15m → 24  (RTH 26 bars, give margin)
    #   30m → 12  (RTH 13 bars, give margin)
    {
        "name": "strat_features_5m",
        "ts_column": "ts",
        "ts_is_date": False,
        "expected_lag_hours": 24,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ"),
        "writer_job": "strat-engine",
        "settle_hour_et": 23,
        "tolerate_holidays": True,
        "min_rows_per_day": 70,
        "gap_scan_days": 5,
    },
    {
        "name": "strat_features_15m",
        "ts_column": "ts",
        "ts_is_date": False,
        "expected_lag_hours": 24,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ"),
        "writer_job": "strat-engine",
        "settle_hour_et": 23,
        "tolerate_holidays": True,
        "min_rows_per_day": 24,
        "gap_scan_days": 5,
    },
    {
        "name": "strat_features_30m",
        "ts_column": "ts",
        "ts_is_date": False,
        "expected_lag_hours": 24,
        "per_ticker": True,
        "tickers": ("IWM", "SPY", "QQQ"),
        "writer_job": "strat-engine",
        "settle_hour_et": 23,
        "tolerate_holidays": True,
        "min_rows_per_day": 12,
        "gap_scan_days": 5,
    },
]


# ── Domain helpers ───────────────────────────────────────────────────────────

# Market holidays for 2026 (NYSE). Used to avoid false "stale" alerts
# when the most recent expected trading session was a holiday.
MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day observed
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 11, 27),  # Black Friday (early close, treated as closed)
    date(2026, 12, 25),  # Christmas
}


def most_recent_trading_day(
    now_utc: datetime,
    settle_hour_et: int = 16,
    settle_lag_days: int = 0,
) -> date:
    """Return the most recent trading day for which data is settled at `now`.

    Two parameters model the writer's cadence:

    `settle_hour_et` — the ET hour-of-day after which the writer is
        expected to have run for that day's data. Defaults to 16 (4 PM
        ET = market close) for tables written during RTH (signal_alerts,
        premarket_analysis).

    `settle_lag_days` — how many trading days the writer LAGS behind the
        data it writes. Defaults to 0 (writer fires same day as the
        data, e.g. fetch-market-data at 23 ET writes today's daily bar).
        Set to 1 when the cron fires the NEXT trading day (e.g.
        av-intraday-nightly at 21 ET on day D+1 writes day D's bars —
        Codex P2 caught this on PR #494).

    The two combine: anchor the most-recent day at settle_hour_et, then
    roll back `settle_lag_days` additional trading days. Examples for
    av-intraday-nightly (settle_hour_et=21, settle_lag_days=1):

        Tue 22 ET (post-settle): anchor=Tue, roll back 1 → Mon ✅
            (Tue's cron fired and wrote Mon's bars)
        Tue 19 ET (pre-settle):  anchor=Mon, roll back 1 → Friday ✅
            (Tue's cron not yet fired; Mon's bars not yet expected)

    Without the lag knob, the watchdog would expect Mon's bars at Mon
    21 ET (when the cron hasn't fired) and false-flag every Tuesday
    morning until 21 ET.

    Without the hour knob (the original bug), the watchdog flagged today
    as missing for ~7 hours every weekday between 16:00 ET market close
    and 23:00 ET fetcher run — creating ~70 false-positive freshness
    issues on #449 over a few days.

    Converts UTC to America/New_York to handle EDT/EST correctly (UTC-4
    in summer, UTC-5 in winter) before checking against settle_hour_et.
    """
    et_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
    # Step 1: anchor on the most recent CALENDAR day whose settle-hour
    # has passed. For lag-0 fetchers this is just "today if past
    # settle_hour else yesterday." For lag-1 fetchers (intraday cron is
    # Tue-Sat) the cron's fire-day can be a Saturday — that's fine,
    # cron-fire-day is a calendar concept; the trading-day skip happens
    # in the lag-walk-back step below.
    cron_day = et_now.date()
    if et_now.time() < time(settle_hour_et, 0, 0):
        cron_day = cron_day - timedelta(days=1)
    # Step 2: convert cron_day to the trading-day whose data was written.
    # For lag=0 (writer fires same-day): walk back from cron_day to the
    # nearest trading day (handles Sun/Sat/holiday cron_days).
    # For lag=N (writer fires N trading days AFTER the data, e.g.
    # av-intraday-nightly Tue 21 ET writes Mon's bars): walk back N
    # trading days from cron_day.
    data_day = cron_day
    walks_remaining = max(settle_lag_days, 0)
    if walks_remaining == 0:
        while data_day.weekday() >= 5 or data_day in MARKET_HOLIDAYS_2026:
            data_day = data_day - timedelta(days=1)
    else:
        for _ in range(walks_remaining):
            data_day = data_day - timedelta(days=1)
            while data_day.weekday() >= 5 or data_day in MARKET_HOLIDAYS_2026:
                data_day = data_day - timedelta(days=1)
    return data_day


# ── Freshness report dataclass ───────────────────────────────────────────────


@dataclass
class FreshnessRow:
    table: str
    ticker: Optional[str]
    last_row_at: Optional[str]
    expected_latest: str
    lag_hours: Optional[float]
    expected_max_hours: float
    status: str  # ok | warn | stale | unknown
    row_count_recent: int = 0
    # Optional: name of the Cloud Run Job whose successful execution should
    # produce rows in this table. When set, a stale row points at the
    # likely culprit job — the operator doesn't have to grep deploy.sh to
    # know which fetcher to investigate. Surfaced via to_dict() / JSON
    # output and the terminal `format_terminal` summary. Added 2026-06-02
    # for the F11 silent-fallback follow-up.
    writer_job: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FreshnessReport:
    checked_at: str
    expected_market_close: str
    rows: list[FreshnessRow] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if not self.rows:
            return "unknown"
        if any(r.status == "stale" for r in self.rows):
            return "stale"
        if any(r.status == "warn" for r in self.rows):
            return "warn"
        if any(r.status == "unknown" for r in self.rows):
            return "warn"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "expected_market_close": self.expected_market_close,
            "overall_status": self.overall_status,
            "tables": [r.to_dict() for r in self.rows],
        }


# ── Query implementation ─────────────────────────────────────────────────────


def _query_freshness_one(
    check: dict,
    expected_date: date,
    ticker: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> FreshnessRow:
    """Run the freshness query for one (table, ticker) combination."""
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    ts_col = check["ts_column"]
    ticker_col = check.get("ticker_column", "ticker")
    where_clauses = []
    params: dict = {}

    if ticker:
        where_clauses.append(f"{ticker_col} = :ticker")
        params["ticker"] = ticker

    extra_where = check.get("where")
    if extra_where:
        where_clauses.append(extra_where)

    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Count how many rows land on the expected trading day (sanity check).
    # For timestamp columns use a half-open range on the raw column rather than
    # DATE(ts_col) = :date — wrapping the column in DATE() is NOT sargable, so
    # Postgres can't use the ts index and falls back to a full table scan. That
    # scan, run per (table, ticker), is the dominant cost of this audit on the
    # large market_data_intraday / etf_options_snapshots tables (it pushed the
    # endpoint past 150s). The range form counts the identical rows.
    if check["ts_is_date"]:
        count_filter = f"{ts_col} = :expected_date"
        params["expected_date"] = expected_date
    else:
        count_filter = f"{ts_col} >= :day_start AND {ts_col} < :day_end"
        params["day_start"] = datetime.combine(expected_date, time.min)
        params["day_end"] = datetime.combine(expected_date, time.min) + timedelta(days=1)

    count_where = list(where_clauses) + [count_filter]
    count_where_sql = " WHERE " + " AND ".join(count_where)

    q = f"""
    SELECT
      MAX({ts_col}) AS last_row_at,
      (SELECT COUNT(*) FROM {check['name']} {count_where_sql}) AS row_count_recent
    FROM {check['name']}
    {where_sql}
    """

    try:
        df = query_to_dataframe(q, params)
    except Exception as e:
        err_msg = str(e)
        # Missing table is a specific failure mode — the table either hasn't
        # been created yet or the migration never ran. Treat as "unknown" so
        # overall status becomes warn instead of stale.
        if "does not exist" in err_msg or "relation" in err_msg.lower():
            log.debug("Table %s does not exist: %s", check["name"], err_msg)
        else:
            log.warning("Query failed for %s (%s): %s", check["name"], ticker, e)
        return FreshnessRow(
            table=check["name"],
            ticker=ticker,
            last_row_at=None,
            expected_latest=expected_date.isoformat(),
            lag_hours=None,
            expected_max_hours=check["expected_lag_hours"],
            status="unknown",
            writer_job=check.get("writer_job"),
        )

    if df.empty or df["last_row_at"].iloc[0] is None:
        return FreshnessRow(
            table=check["name"],
            ticker=ticker,
            last_row_at=None,
            expected_latest=expected_date.isoformat(),
            lag_hours=None,
            expected_max_hours=check["expected_lag_hours"],
            status="stale",
            writer_job=check.get("writer_job"),
        )

    last_row_at = df["last_row_at"].iloc[0]
    row_count_recent = int(df["row_count_recent"].iloc[0])

    # Normalize last_row_at to a naive UTC datetime for lag math.
    if isinstance(last_row_at, date) and not isinstance(last_row_at, datetime):
        # DATE column — assume 16:00 ET = 20:00 UTC (market close) for lag
        last_dt = datetime.combine(last_row_at, time(20, 0, 0))
    else:
        # TIMESTAMPTZ — convert to naive UTC
        last_dt = last_row_at
        if hasattr(last_dt, "tzinfo") and last_dt.tzinfo is not None:
            last_dt = last_dt.replace(tzinfo=None)

    # Measure lag relative to expected session close, not wall clock.
    # Wall-clock lag inflates over weekends/holidays (e.g., Friday data looks
    # 65h old on Monday morning), causing false stale alarms.
    expected_close_dt = datetime.combine(expected_date, time(20, 0, 0))  # 4 PM ET = 20:00 UTC
    lag_hours = max(0, (expected_close_dt - last_dt).total_seconds() / 3600.0)
    expected_max = check["expected_lag_hours"]

    # Status:
    #   ok     — within expected lag
    #   warn   — 1-2x the expected lag (likely delayed but recoverable)
    #   stale  — >2x the expected lag (real problem)
    if lag_hours <= expected_max:
        status = "ok"
    elif lag_hours <= expected_max * 2:
        status = "warn"
    else:
        status = "stale"

    # Row-count floor: catches "fetcher ran but wrote 0 rows" (the exact
    # failure mode that sat silent for SPX for 4 months).
    min_rows = check.get("min_rows_per_day")
    if min_rows is not None and status == "ok" and row_count_recent < min_rows:
        status = "stale"

    return FreshnessRow(
        table=check["name"],
        ticker=ticker,
        last_row_at=last_row_at.isoformat() if hasattr(last_row_at, "isoformat") else str(last_row_at),
        expected_latest=expected_date.isoformat(),
        lag_hours=round(lag_hours, 1),
        expected_max_hours=expected_max,
        status=status,
        row_count_recent=row_count_recent,
        writer_job=check.get("writer_job"),
    )


def _recent_trading_days(
    now_utc: datetime,
    n: int,
    settle_hour_et: int = 16,
    settle_lag_days: int = 0,
) -> list[date]:
    """Return the last `n` trading days ending at the most recent SETTLED day.

    Both `settle_hour_et` and `settle_lag_days` are passed through to
    most_recent_trading_day — see its docstring for the model. Tables
    with delayed-cron writers (market_data_intraday) need
    settle_lag_days=1 so the gap-scan doesn't expect bars before they're
    written.
    """
    end = most_recent_trading_day(
        now_utc, settle_hour_et=settle_hour_et, settle_lag_days=settle_lag_days,
    )
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5 and d not in MARKET_HOLIDAYS_2026:
            days.append(d)
        d = d - timedelta(days=1)
    return days


def _query_gap_scan(check: dict, now_utc: datetime) -> list[FreshnessRow]:
    """For per-ticker tables, check whether every expected trading day in the
    last N days has at least one row per ticker. Catches mid-window holes
    that the simple MAX(ts) check misses.
    """
    if not check.get("per_ticker") or not check.get("gap_scan_days"):
        return []

    ts_col = check["ts_column"]
    ticker_col = check.get("ticker_column", "ticker")
    n = check["gap_scan_days"]
    settle = check.get("settle_hour_et", 16)
    lag = check.get("settle_lag_days", 0)
    expected_days = _recent_trading_days(
        now_utc, n, settle_hour_et=settle, settle_lag_days=lag,
    )
    tickers = check.get("tickers", TICKERS)

    date_expr = ts_col if check["ts_is_date"] else f"DATE({ts_col})"
    extra_where = check.get("where")
    # Bound the scan with a sargable range on the raw ts column. Filtering on
    # DATE(ts_col) (a function on the column) is not sargable and forces a full
    # table scan; the raw-column range lets Postgres use the ts index. GROUP BY
    # still buckets by calendar day, so the result is identical.
    if check["ts_is_date"]:
        range_where = [f"{ts_col} >= :start_bound", f"{ts_col} <= :end_bound"]
        range_params = {"start_bound": expected_days[-1], "end_bound": expected_days[0]}
    else:
        range_where = [f"{ts_col} >= :start_bound", f"{ts_col} < :end_bound"]
        range_params = {
            "start_bound": datetime.combine(expected_days[-1], time.min),
            "end_bound": datetime.combine(expected_days[0], time.min) + timedelta(days=1),
        }
    where_parts = [f"{ticker_col} = ANY(:tickers)"] + range_where
    if extra_where:
        where_parts.append(extra_where)
    where_sql = " WHERE " + " AND ".join(where_parts)

    sql = f"""
    SELECT {ticker_col} AS ticker, {date_expr} AS d, COUNT(*) AS c
    FROM {check['name']}
    {where_sql}
    GROUP BY {ticker_col}, {date_expr}
    """
    try:
        df = query_to_dataframe(sql, {"tickers": list(tickers), **range_params})
    except Exception as e:
        if "does not exist" not in str(e):
            log.warning("Gap scan failed for %s: %s", check["name"], e)
        return []

    present: dict[str, set] = {t: set() for t in tickers}
    if not df.empty:
        for _, r in df.iterrows():
            tkr = r["ticker"]
            d = r["d"]
            if tkr in present:
                present[tkr].add(d if isinstance(d, date) else d.date())

    rows: list[FreshnessRow] = []
    for tkr in tickers:
        missing = [d for d in expected_days if d not in present[tkr]]
        if not missing:
            continue
        rows.append(FreshnessRow(
            table=f"{check['name']} [gap]",
            ticker=tkr,
            last_row_at=None,
            expected_latest=expected_days[0].isoformat(),
            lag_hours=None,
            expected_max_hours=0,
            status="stale",
            writer_job=check.get("writer_job"),
            row_count_recent=len(expected_days) - len(missing),
        ))
    return rows


def _query_value_sanity(now_utc: datetime) -> list[FreshnessRow]:
    """Hardcoded cross-table sanity checks on recent rows. Returns only
    FAILING rows; silent when everything is within range.
    """
    # Scope the options scan to the tracked tickers AND end-of-day snapshots so
    # it uses the idx_etf_options_eod_agg (ticker, snapshot_date) partial index
    # and examines ~1 snapshot/day instead of all intraday snapshots. Without
    # both predicates the snapshot_date range matches no index and the audit
    # full-scans the large etf_options_snapshots table (>120s); with them ~4s.
    # EOD is the canonical daily snapshot; TICKERS is the set this audit tracks.
    tkr_array = "ARRAY[" + ", ".join(f"'{t}'" for t in TICKERS) + "]"
    checks: list[tuple[str, str, str]] = [
        # (label, SQL returning count of bad rows, description)
        (
            "market_data_daily [sanity]",
            """SELECT COUNT(*) AS bad FROM market_data_daily
               WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                 AND (high < low OR close < 0 OR volume < 0)""",
            "high<low or negative values",
        ),
        (
            "market_data_daily [sanity:SPX]",
            """SELECT COUNT(*) AS bad FROM market_data_daily
               WHERE ticker='SPX'
                 AND date >= CURRENT_DATE - INTERVAL '30 days'
                 AND (close < 1000 OR close > 20000)""",
            "SPX close out of sane range",
        ),
        (
            "etf_options_snapshots [sanity]",
            f"""SELECT COUNT(*) AS bad FROM etf_options_snapshots
               WHERE ticker = ANY({tkr_array})
                 AND market_session = 'EOD'
                 AND snapshot_date >= CURRENT_DATE - INTERVAL '7 days'
                 AND data_source = 'alphavantage'
                 AND (strike <= 0 OR mark < 0)""",
            "non-positive strike or negative mark",
        ),
    ]

    results: list[FreshnessRow] = []
    for label, sql, desc in checks:
        try:
            df = query_to_dataframe(sql)
            bad = int(df["bad"].iloc[0]) if not df.empty else 0
        except Exception as e:
            if "does not exist" in str(e):
                continue
            log.warning("Sanity check %s failed: %s", label, e)
            continue
        if bad > 0:
            results.append(FreshnessRow(
                table=label,
                ticker=None,
                last_row_at=desc,
                expected_latest="",
                lag_hours=None,
                expected_max_hours=0,
                status="stale",
                row_count_recent=bad,
            ))
    return results


def audit_all(now_utc: Optional[datetime] = None) -> FreshnessReport:
    """Run all freshness checks and return a full report.

    Each CHECK can declare `settle_hour_et` — the ET hour after which
    day-D's data is expected. Defaults to 16 (market close). Tables
    written by after-hours fetchers (market_data_daily at 23 ET,
    etf_options_snapshots at 21 ET) set higher values so the gap-scan
    doesn't false-flag today's row as missing during the
    market-close → fetcher-run window.
    """
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    # The "global" expected_date is anchored at market close (16 ET) for
    # the report header only — actual freshness checks use per-CHECK
    # settle_hour_et below.
    expected_date_for_header = most_recent_trading_day(now)

    report = FreshnessReport(
        checked_at=now.isoformat() + "Z",
        expected_market_close=expected_date_for_header.isoformat(),
    )

    for check in CHECKS:
        check_settle = check.get("settle_hour_et", 16)
        check_lag = check.get("settle_lag_days", 0)
        check_expected_date = most_recent_trading_day(
            now, settle_hour_et=check_settle, settle_lag_days=check_lag,
        )
        tickers_to_check = check.get("tickers", TICKERS) if check.get("per_ticker") else [None]
        for t in tickers_to_check:
            row = _query_freshness_one(check, check_expected_date, ticker=t, now_utc=now)
            report.rows.append(row)

        # Gap scan: only reports failing (ticker, day) combinations
        report.rows.extend(_query_gap_scan(check, now))

    # Value sanity across tables — only reports failures
    report.rows.extend(_query_value_sanity(now))

    return report


# ── Output formats ───────────────────────────────────────────────────────────


def format_terminal(report: FreshnessReport) -> str:
    """Pretty terminal output with colored status markers (ANSI)."""
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    DIM = "\033[2m"
    BOLD = "\033[1m"

    status_icon = {
        "ok": f"{GREEN}●{RESET}",
        "warn": f"{YELLOW}●{RESET}",
        "stale": f"{RED}●{RESET}",
        "unknown": f"{DIM}●{RESET}",
    }

    lines = []
    lines.append(f"{BOLD}Data freshness audit{RESET}  —  {DIM}expected close: {report.expected_market_close}, checked: {report.checked_at}{RESET}")
    lines.append("")

    # Header
    lines.append(f"  {BOLD}{'TABLE':<28} {'TICKER':<7} {'LAST ROW':<22} {'LAG (h)':>10} {'LIMIT':>8}  STATUS{RESET}")
    lines.append(f"  {DIM}{'─' * 28} {'─' * 7} {'─' * 22} {'─' * 10} {'─' * 8}  ──────{RESET}")

    for r in report.rows:
        icon = status_icon.get(r.status, "●")
        ticker = r.ticker or "—"
        last = (r.last_row_at or "(none)")[:22]
        lag = f"{r.lag_hours:.1f}" if r.lag_hours is not None else "—"
        lim = f"{r.expected_max_hours:.0f}"
        lines.append(f"  {r.table:<28} {ticker:<7} {last:<22} {lag:>10} {lim:>8}  {icon} {r.status}")
        # Surface the responsible writer-job under stale/warn rows so the
        # operator doesn't have to grep deploy.sh to know who to debug.
        if r.writer_job and r.status in ("stale", "warn"):
            lines.append(f"  {DIM}    └─ writer-job: {r.writer_job}{RESET}")

    lines.append("")
    overall_color = {"ok": GREEN, "warn": YELLOW, "stale": RED, "unknown": DIM}[report.overall_status]
    lines.append(f"  {BOLD}Overall:{RESET} {overall_color}{report.overall_status.upper()}{RESET}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit Cloud SQL data freshness across the platform."
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a pretty table")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any table is stale (for CI)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    # Silence Cloud SQL query failures — we handle them gracefully and re-report
    # in the output table, so raw pg8000 errors would just be noise.
    logging.getLogger("gcp.database").setLevel(logging.ERROR + 1)

    if not is_cloud_sql_configured():
        msg = "Cloud SQL not configured. Set CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME."
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(msg, file=sys.stderr)
        sys.exit(2)

    report = audit_all()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(format_terminal(report))

    if args.strict and report.overall_status == "stale":
        sys.exit(1)


if __name__ == "__main__":
    main()
