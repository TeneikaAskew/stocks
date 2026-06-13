#!/usr/bin/env python3
"""Phase 2 Step 2: Walk 10 years of 1-min RTH bars, fire gamma alerts via
production `lib.strategies.gamma_proximity.evaluate_all()`, record fwd
returns + stratification dimensions for every event.

Inputs (all in Cloud SQL, populated by Phase 1 + Phase 2 Step 1):
  - `gamma_levels_eod` (ticker, date, level_kind, level_strike, regime,
    flip_price, ...) — pre-computed K/G/F per (ticker, date)
  - `market_data_intraday_{spy,iwm,qqq}` — 1-min RTH bars 2015-2026
  - `market_data_daily` — daily bars for prev-day-direction + VIX

Output: `gamma_events` table — one row per fired alert with:
  - identifying: ticker, alert_ts, alert_kind, alert_direction, level_strike, regime
  - stratification: ftfc (prev_day_dir), vix_tercile, gamma_regime,
    tod_bucket (open/midday/afternoon/close), dow (mon-fri)
  - outcomes: bar_close (entry), fwd_close_5m/15m/30m/60m/240m/1d/5d,
    fwd_ret_*_bps (signed in alert direction)
  - context: distance_pct, n_kings_visible, total_gex

No production-replay drift: the alert detection is exactly
`evaluate_all(price, prev_close, summary, prev_day_dir=...)` with
the same default proximity_pct (0.5%), same dedup-key semantics
(per-session per (kind, strike)), same regime + direction mapping.

Rule 0 capacity:
  Volume:   3 tickers × ~2,861 days × ~390 RTH bars/day = ~3.35M bars
  Velocity: 1 SELECT per (ticker, day) for bars + 1 SELECT per
            (ticker, day) for levels = ~17k SELECTs. Plus 1 batch
            INSERT per ticker × day for events (~8.5k upserts but
            most days fire 0-10 alerts → small batches).
  Wall:     per-day processing ~50ms (load 390 bars, walk, eval).
            Total: 8.5k × 50ms = ~7 min raw + DB overhead ~3 min = 10 min.
            Estimate ~15 min wall-clock.
  Timeout:  3600s task-timeout (1 hour) = 4× wall estimate.
  Memory:   per-day bars (~390 rows × 50 bytes = 20KB) + levels (~5 rows)
            negligible. Peak: ~1GB for event accumulator before bulk-insert
            at end of each ticker. Set memory=4Gi for safety.
  Retries:  max-retries=0 (Cloud Run can't tell transient from permanent).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import execute_sql, get_engine, upsert_dataframe
from lib.gamma import GammaSummary, Level, SpotEstimate
from lib.strategies import gamma_proximity as gp
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

TICKERS_DEFAULT = ["SPY", "IWM", "QQQ"]
INTRADAY_TABLE_BY_TICKER = {
    "SPY": "market_data_intraday_spy",
    "IWM": "market_data_intraday_iwm",
    "QQQ": "market_data_intraday_qqq",
}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gamma_events (
    ticker            VARCHAR(16) NOT NULL,
    alert_ts          TIMESTAMPTZ NOT NULL,
    alert_date        DATE        NOT NULL,
    alert_kind        VARCHAR(32) NOT NULL,
    alert_direction   VARCHAR(8)  NOT NULL,   -- 'CALL' | 'PUT'
    level_kind        VARCHAR(20) NOT NULL,   -- 'king' | 'gate' | 'gamma_flip'
    level_strike      NUMERIC(12,4) NOT NULL,
    distance_pct      DOUBLE PRECISION,
    regime            VARCHAR(20),
    -- entry context
    bar_close         DOUBLE PRECISION NOT NULL,
    bar_open          DOUBLE PRECISION,
    -- stratification
    ftfc_prev_day_dir VARCHAR(8),   -- 'UP' | 'DOWN' | 'FLAT'
    vix_level         DOUBLE PRECISION,
    vix_tercile       VARCHAR(8),   -- 'LOW' | 'MID' | 'HIGH'
    tod_bucket        VARCHAR(16),  -- 'open' | 'midday' | 'afternoon' | 'close'
    dow               SMALLINT,     -- 0=Mon ... 4=Fri
    -- forward returns at multiple horizons
    fwd_close_5m      DOUBLE PRECISION,
    fwd_close_15m     DOUBLE PRECISION,
    fwd_close_30m     DOUBLE PRECISION,
    fwd_close_60m     DOUBLE PRECISION,
    fwd_close_240m    DOUBLE PRECISION,
    fwd_close_1d      DOUBLE PRECISION,
    fwd_close_5d      DOUBLE PRECISION,
    -- signed return bps (positive = move in alert direction)
    fwd_ret_5m_bps    DOUBLE PRECISION,
    fwd_ret_15m_bps   DOUBLE PRECISION,
    fwd_ret_30m_bps   DOUBLE PRECISION,
    fwd_ret_60m_bps   DOUBLE PRECISION,
    fwd_ret_240m_bps  DOUBLE PRECISION,
    fwd_ret_1d_bps    DOUBLE PRECISION,
    fwd_ret_5d_bps    DOUBLE PRECISION,
    -- run metadata
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, alert_ts, alert_kind, level_strike)
);
CREATE INDEX IF NOT EXISTS ix_gamma_events_date    ON gamma_events (alert_date);
CREATE INDEX IF NOT EXISTS ix_gamma_events_kind    ON gamma_events (alert_kind);
CREATE INDEX IF NOT EXISTS ix_gamma_events_ftfc    ON gamma_events (ftfc_prev_day_dir);
CREATE INDEX IF NOT EXISTS ix_gamma_events_tercile ON gamma_events (vix_tercile);
"""


# ── Helpers ─────────────────────────────────────────────────────────


def _load_levels_for_prior_day(engine, ticker: str) -> pd.DataFrame:
    """Load all levels for a ticker, keyed on snapshot_date.

    Caller uses date D-1's levels for date D's analysis (no leak —
    matches production's `_latest_gamma_for_ticker_pure` semantics).
    """
    from sqlalchemy import text
    sql = text("""
    SELECT snapshot_date, level_kind, level_strike, gex, score, tags,
           regime, gamma_balance_price, gamma_flip, total_gex, spot_estimate
    FROM gamma_levels_eod
    WHERE ticker = :ticker
    ORDER BY snapshot_date, level_kind, level_strike
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"ticker": ticker})


def _load_daily_features(engine, ticker: str) -> pd.DataFrame:
    """Load per-date OHLC + prev-day-direction + VIX level for the ticker."""
    from sqlalchemy import text
    sql = text("""
    WITH t_daily AS (
      SELECT date, open, high, low, close
      FROM market_data_daily
      WHERE ticker = :ticker
    ),
    vix AS (
      SELECT date, close AS vix_close
      FROM market_data_daily
      WHERE ticker = '^VIX'
    )
    SELECT t.date, t.open, t.close,
           CASE
             WHEN t.close > t.open THEN 'UP'
             WHEN t.close < t.open THEN 'DOWN'
             ELSE 'FLAT'
           END AS today_dir,
           LAG(CASE WHEN t.close > t.open THEN 'UP'
                    WHEN t.close < t.open THEN 'DOWN'
                    ELSE 'FLAT' END) OVER (ORDER BY t.date) AS prev_day_dir,
           v.vix_close
    FROM t_daily t
    LEFT JOIN vix v ON v.date = t.date
    ORDER BY t.date
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"ticker": ticker})


def _load_bars_for_year(engine, ticker: str, year: int) -> pd.DataFrame:
    """Load 1-min RTH bars for one ticker × full year.

    Refactored from per-date to per-year (2026-05-23) — the per-date version
    did 2,858 round-trips per ticker. Per-year is 12 round-trips per ticker.
    Each year is ~98k rows × ~50 bytes = ~5MB, well within memory.
    """
    from sqlalchemy import text
    table = INTRADAY_TABLE_BY_TICKER[ticker]
    sql = text(f"""
    SELECT ts, open, high, low, close, volume,
           (ts AT TIME ZONE 'America/New_York')::date AS local_date
    FROM {table}
    WHERE ts >= :y_start
      AND ts <  :y_end
      AND interval = '1min'
      AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:59'
    ORDER BY ts
    """)
    y_start = pd.Timestamp(year, 1, 1, tz="UTC")
    y_end = pd.Timestamp(year + 1, 1, 1, tz="UTC")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"y_start": y_start, "y_end": y_end})
    return df


def _build_summary_from_levels(ticker: str, snap_date: _date,
                                day_levels: pd.DataFrame) -> Optional[GammaSummary]:
    """Reconstruct a minimal GammaSummary from the gamma_levels_eod rows
    for a single (ticker, prior-business-day). Only the fields needed by
    `gp.evaluate_all()` are populated — kings, gates, flip, regime."""
    if day_levels.empty:
        return None

    spot_price = float(day_levels["spot_estimate"].iloc[0] or 0.0)
    _gb = day_levels["gamma_balance_price"].iloc[0]
    gamma_balance_val = float(_gb) if pd.notna(_gb) else None
    _gf = day_levels["gamma_flip"].iloc[0]
    gamma_flip_val = float(_gf) if pd.notna(_gf) else None
    regime = day_levels["regime"].iloc[0] or "unknown"
    total_gex = float(day_levels["total_gex"].iloc[0] or 0.0)

    def _to_level(row) -> Level:
        return Level(
            strike=float(row["level_strike"]),
            gex=float(row["gex"] or 0.0),
            net_gamma=float(row["gex"] or 0.0),  # gex stored as net_gamma in build_summary
            call_oi=0, put_oi=0,
            distance_pct=0.0,
            score=float(row["score"] or 0.0),
            kind=row["level_kind"],
            tags=(row["tags"] or "").split(",") if row["tags"] else [row["level_kind"]],
        )

    kings = [_to_level(r) for _, r in
             day_levels[day_levels["level_kind"] == "king"].iterrows()]
    gates = [_to_level(r) for _, r in
             day_levels[day_levels["level_kind"] == "gate"].iterrows()]

    return GammaSummary(
        ticker=ticker,
        snapshot_date=str(snap_date),
        spot=SpotEstimate(price=spot_price, method="from_levels_eod"),
        gamma_balance=gamma_balance_val,
        gamma_flip=gamma_flip_val,
        regime=regime,
        total_gex=total_gex,
        levels=kings + gates,
        kings=kings,
        gates=gates,
        gamma_balance_levels=[],
        window_pct=8.0,
    )


def _tod_bucket(ts: pd.Timestamp) -> str:
    """Bucket a bar timestamp into open / midday / afternoon / close."""
    t = ts.tz_convert("America/New_York").time()
    if t <= datetime.strptime("10:30", "%H:%M").time():
        return "open"
    if t <= datetime.strptime("13:00", "%H:%M").time():
        return "midday"
    if t <= datetime.strptime("15:00", "%H:%M").time():
        return "afternoon"
    return "close"


def _vix_tercile(vix: Optional[float]) -> Optional[str]:
    """Bucket VIX using P1 tercile thresholds (p33=14.65, p67=19.40)."""
    if vix is None or pd.isna(vix):
        return None
    if vix < 14.65:
        return "LOW"
    if vix < 19.40:
        return "MID"
    return "HIGH"


def _signed_ret_bps(entry: float, fwd: Optional[float], direction: str) -> Optional[float]:
    """Return signed bps, positive when fwd moves in alert direction."""
    if fwd is None or pd.isna(fwd) or entry <= 0:
        return None
    raw = (fwd - entry) / entry * 10000.0
    return raw if direction == "CALL" else -raw


# ── Main per-ticker iteration ──────────────────────────────────────


def _process_ticker(engine, ticker: str) -> int:
    log.info("=== %s: loading levels + daily features ===", ticker)
    levels_all = _load_levels_for_prior_day(engine, ticker)
    daily = _load_daily_features(engine, ticker)
    log.info("%s: %d level rows across %d days; %d daily rows",
             ticker, len(levels_all), levels_all["snapshot_date"].nunique(), len(daily))

    levels_by_date: dict = {d: g for d, g in levels_all.groupby("snapshot_date")}
    daily_by_date: dict = daily.set_index("date").to_dict("index")
    sorted_dates = sorted(daily.set_index("date").index.tolist())

    n_bars_processed = 0
    n_alerts = 0
    t0 = time.time()

    # Determine year span from levels coverage
    if not levels_all.empty:
        min_year = pd.Timestamp(levels_all["snapshot_date"].min()).year
        max_year = pd.Timestamp(levels_all["snapshot_date"].max()).year
    else:
        log.warning("%s: no levels loaded — skipping ticker", ticker)
        return 0

    for year in range(min_year, max_year + 1):
        yt0 = time.time()
        bars_year = _load_bars_for_year(engine, ticker, year)
        if bars_year.empty:
            log.info("%s %d: no bars", ticker, year)
            continue
        log.info("%s %d: loaded %d bars", ticker, year, len(bars_year))

        # Group by local trading date
        bars_year["local_date"] = pd.to_datetime(bars_year["local_date"]).dt.date
        event_rows: list[dict] = []

        dates_in_year = sorted(bars_year["local_date"].unique())
        prev_trading_date: Optional[_date] = None
        for d in sorted_dates:
            if d.year > year:
                break
            if d.year < year:
                prev_trading_date = d
                continue
            if d not in dates_in_year:
                prev_trading_date = d
                continue

            # Use prev_trading_date's EOD chain for D's analysis
            if prev_trading_date is None:
                prev_trading_date = d
                continue
            levels_for_today = levels_by_date.get(prev_trading_date)
            if levels_for_today is None or levels_for_today.empty:
                prev_trading_date = d
                continue
            summary = _build_summary_from_levels(ticker, d, levels_for_today)
            if summary is None:
                prev_trading_date = d
                continue

            today_row = daily_by_date.get(d, {})
            prev_day_dir = today_row.get("prev_day_dir")
            vix_today = today_row.get("vix_close")
            vix_tercile = _vix_tercile(vix_today)
            dow = d.weekday()

            bars = bars_year[bars_year["local_date"] == d].copy()
            if bars.empty:
                prev_trading_date = d
                continue
            n_bars_processed += len(bars)
            bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
            closes = bars["close"].astype(float).values
            bars_ts = bars["ts"].tolist()

            fired_keys: set[tuple] = set()
            day_events: list[dict] = []
            prev_close: Optional[float] = None
            for i in range(len(bars)):
                close = float(closes[i])
                alerts = gp.evaluate_all(
                    price=close,
                    prev_close=prev_close,
                    summary=summary,
                    prev_day_dir=prev_day_dir,
                )
                for a in alerts:
                    key = (a.kind, round(a.level_strike, 4))
                    if key in fired_keys:
                        continue
                    fired_keys.add(key)
                    n_alerts += 1
                    day_events.append({
                        "ticker": ticker,
                        "alert_ts": bars_ts[i],
                        "alert_date": d,
                        "alert_kind": a.kind,
                        "alert_direction": a.direction,
                        "level_kind": a.level_kind,
                        "level_strike": a.level_strike,
                        "distance_pct": a.distance_pct,
                        "regime": a.regime,
                        "bar_close": close,
                        "bar_open": float(bars.iloc[i].get("open") or 0.0) or None,
                        "ftfc_prev_day_dir": prev_day_dir,
                        "vix_level": vix_today,
                        "vix_tercile": vix_tercile,
                        "tod_bucket": _tod_bucket(bars_ts[i]),
                        "dow": dow,
                        "_bar_idx": i,
                    })
                prev_close = close

            # Fwd returns for events fired today
            for e in day_events:
                idx = e.pop("_bar_idx")
                for horizon_min in (5, 15, 30, 60, 240):
                    j = idx + horizon_min
                    fwd = float(closes[j]) if j < len(closes) else None
                    e[f"fwd_close_{horizon_min}m"] = fwd
                    e[f"fwd_ret_{horizon_min}m_bps"] = _signed_ret_bps(
                        e["bar_close"], fwd, e["alert_direction"])
                # Daily-horizon forwards
                future_dates = [fd for fd in sorted_dates if fd > d][:5]
                d1c = daily_by_date.get(future_dates[0], {}).get("close") if future_dates else None
                e["fwd_close_1d"] = float(d1c) if d1c is not None else None
                e["fwd_ret_1d_bps"] = _signed_ret_bps(
                    e["bar_close"], e["fwd_close_1d"], e["alert_direction"])
                if len(future_dates) >= 5:
                    d5c = daily_by_date.get(future_dates[4], {}).get("close")
                    e["fwd_close_5d"] = float(d5c) if d5c is not None else None
                    e["fwd_ret_5d_bps"] = _signed_ret_bps(
                        e["bar_close"], e["fwd_close_5d"], e["alert_direction"])

            event_rows.extend(day_events)
            prev_trading_date = d

        # Flush the year's events
        if event_rows:
            df = pd.DataFrame(event_rows)
            if "_bar_idx" in df.columns:
                df = df.drop(columns=["_bar_idx"])
            upsert_dataframe(
                df, "gamma_events",
                conflict_cols=["ticker", "alert_ts", "alert_kind", "level_strike"],
                update_cols=[c for c in df.columns
                             if c not in ("ticker", "alert_ts", "alert_kind",
                                          "level_strike", "computed_at")],
            )
            log.info("%s %d: flushed %d events (%.1fs, cumulative n_bars=%d, n_alerts=%d)",
                     ticker, year, len(df), time.time() - yt0,
                     n_bars_processed, n_alerts)
        else:
            log.info("%s %d: no events fired", ticker, year)

    log.info("=== %s: done — %d bars walked, %d alerts fired in %.1fs ===",
             ticker, n_bars_processed, n_alerts, time.time() - t0)
    return n_alerts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(TICKERS_DEFAULT))
    parser.add_argument("--create-table-only", action="store_true")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("Phase 2 Step 2: gamma_events for %s", tickers)

    execute_sql(CREATE_TABLE_SQL)
    log.info("Ensured gamma_events table exists")
    if args.create_table_only:
        return

    engine = get_engine()
    grand_total = 0
    for ticker in tickers:
        grand_total += _process_ticker(engine, ticker)

    log.info("All done — %d total alerts fired across tickers", grand_total)


if __name__ == "__main__":
    main()
