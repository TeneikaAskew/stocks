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
    level_kind        VARCHAR(8)  NOT NULL,
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
           regime, flip_price, total_gex, spot_estimate
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


def _load_bars_for_date(engine, ticker: str, day: _date) -> pd.DataFrame:
    """Load 1-min RTH bars for a single (ticker, date), index by ts."""
    from sqlalchemy import text
    table = INTRADAY_TABLE_BY_TICKER[ticker]
    sql = text(f"""
    SELECT ts, open, high, low, close, volume
    FROM {table}
    WHERE ts::date = :d
      AND interval = '1min'
      AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:59'
    ORDER BY ts
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"d": day})


def _build_summary_from_levels(ticker: str, snap_date: _date,
                                day_levels: pd.DataFrame) -> Optional[GammaSummary]:
    """Reconstruct a minimal GammaSummary from the gamma_levels_eod rows
    for a single (ticker, prior-business-day). Only the fields needed by
    `gp.evaluate_all()` are populated — kings, gates, flip, regime."""
    if day_levels.empty:
        return None

    spot_price = float(day_levels["spot_estimate"].iloc[0] or 0.0)
    flip = day_levels.loc[day_levels["level_kind"] == "flip", "level_strike"]
    flip_val = float(flip.iloc[0]) if not flip.empty else None
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
        flip=flip_val,
        regime=regime,
        total_gex=total_gex,
        levels=kings + gates,
        kings=kings,
        gates=gates,
        flip_levels=[],
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

    levels_by_date = {d: g for d, g in levels_all.groupby("snapshot_date")}
    daily_by_date = daily.set_index("date").to_dict("index")

    # Iterate dates that have BOTH a prior-day level AND today's daily row.
    sorted_dates = sorted(daily.set_index("date").index.tolist())
    prev_date = None

    event_rows: list[dict] = []
    n_bars_processed = 0
    n_alerts = 0
    t0 = time.time()

    for cur_date in sorted_dates:
        if prev_date is None:
            prev_date = cur_date
            continue
        # Use prev_date's EOD chain → summary
        levels_for_today = levels_by_date.get(prev_date)
        if levels_for_today is None or levels_for_today.empty:
            prev_date = cur_date
            continue

        summary = _build_summary_from_levels(ticker, cur_date, levels_for_today)
        if summary is None:
            prev_date = cur_date
            continue

        # FTFC proxy: prev day's daily direction
        today_row = daily_by_date.get(cur_date, {})
        prev_day_dir = today_row.get("prev_day_dir")  # already computed
        vix_today = today_row.get("vix_close")
        vix_tercile = _vix_tercile(vix_today)
        dow = cur_date.weekday() if hasattr(cur_date, "weekday") else None

        # Load bars for cur_date
        bars = _load_bars_for_date(engine, ticker, cur_date)
        if bars.empty:
            prev_date = cur_date
            continue
        n_bars_processed += len(bars)

        # Walk bars chronologically, evaluate alerts, dedup per session
        fired_keys: set[tuple] = set()
        prev_close: Optional[float] = None
        bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
        for i, bar in bars.iterrows():
            close = float(bar["close"])
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
                ts = bar["ts"]
                event_rows.append({
                    "ticker": ticker,
                    "alert_ts": ts,
                    "alert_date": cur_date,
                    "alert_kind": a.kind,
                    "alert_direction": a.direction,
                    "level_kind": a.level_kind,
                    "level_strike": a.level_strike,
                    "distance_pct": a.distance_pct,
                    "regime": a.regime,
                    "bar_close": close,
                    "bar_open": float(bar.get("open") or 0.0) or None,
                    "ftfc_prev_day_dir": prev_day_dir,
                    "vix_level": vix_today,
                    "vix_tercile": vix_tercile,
                    "tod_bucket": _tod_bucket(ts),
                    "dow": dow,
                    # Forward closes — computed after the bar walk below
                    "_bar_idx": i,
                })
            prev_close = close

        # After walking, compute fwd_close_* for each event from the bars table
        if event_rows and event_rows[-1].get("ticker") == ticker:
            # Process events that belong to THIS date in this pass
            cur_events = [e for e in event_rows if e["alert_date"] == cur_date and "_bar_idx" in e]
            closes = bars["close"].astype(float).values
            for e in cur_events:
                idx = e.pop("_bar_idx")
                # Intraday horizons (5m=5 bars, 15m=15 bars, etc.)
                for horizon_min in (5, 15, 30, 60, 240):
                    j = idx + horizon_min
                    fwd_close = float(closes[j]) if j < len(closes) else None
                    e[f"fwd_close_{horizon_min}m"] = fwd_close
                    e[f"fwd_ret_{horizon_min}m_bps"] = _signed_ret_bps(
                        e["bar_close"], fwd_close, e["alert_direction"])
                # 1-day / 5-day: use daily-bar closes
                # Find the future daily close for cur_date+1 / cur_date+5 (trading days)
                # Walk daily_by_date forward
                next_n_days = []
                future_iter = iter(d for d in sorted_dates if d > cur_date)
                for _ in range(5):
                    try:
                        next_n_days.append(next(future_iter))
                    except StopIteration:
                        break
                if next_n_days:
                    d1 = daily_by_date.get(next_n_days[0], {}).get("close")
                    e["fwd_close_1d"] = float(d1) if d1 is not None else None
                    e["fwd_ret_1d_bps"] = _signed_ret_bps(
                        e["bar_close"], e["fwd_close_1d"], e["alert_direction"])
                if len(next_n_days) >= 5:
                    d5 = daily_by_date.get(next_n_days[4], {}).get("close")
                    e["fwd_close_5d"] = float(d5) if d5 is not None else None
                    e["fwd_ret_5d_bps"] = _signed_ret_bps(
                        e["bar_close"], e["fwd_close_5d"], e["alert_direction"])

        # Bulk-insert events every 200 trading days (memory bound)
        if cur_date.month % 6 == 0 and cur_date.day < 8 and len(event_rows) > 2000:
            df = pd.DataFrame(event_rows)
            # drop the helper column if present
            if "_bar_idx" in df.columns:
                df = df.drop(columns=["_bar_idx"])
            upsert_dataframe(
                df, "gamma_events",
                conflict_cols=["ticker", "alert_ts", "alert_kind", "level_strike"],
                update_cols=[c for c in df.columns
                             if c not in ("ticker", "alert_ts", "alert_kind",
                                          "level_strike", "computed_at")],
            )
            log.info("%s: flushed %d events through %s; n_bars=%d, n_alerts=%d, dt=%.1fs",
                     ticker, len(df), cur_date, n_bars_processed, n_alerts,
                     time.time() - t0)
            event_rows = []

        prev_date = cur_date

    # Final flush
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
        log.info("%s: final flush %d events", ticker, len(df))

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
