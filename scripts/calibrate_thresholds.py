"""Phase 0.6 — per-ticker threshold calibration (production-grade).

Replaces the universal-across-tickers THRESHOLDS dict (hard-coded 0.5%
for "clean at 60m" applied to SPY, QQQ, and IWM equally) with per-ticker
calibrated thresholds derived from the rolling 60-day bar history.

For each (ticker, timeframe) pair, computes:
  * ATR median (in % of price) — the noise floor
  * RVOL distribution (P25 / P50 / P75 / P95) — the volume regime
  * RSI distribution (P10 / P25 / P50 / P75 / P90) — for sanity-checking
    that the universal CALL/PUT RSI ranges in lib/strategies/config.py
    are still appropriate

And writes ticker-specific clean/wrong/noise thresholds as ATR multiples
to the `ticker_calibration` Cloud SQL table.

Refresh cadence: quarterly (1st of Jan / Apr / Jul / Oct at 02:00 ET)
via the `calibrate-thresholds` Cloud Run Job. Manual run any time:

    python -m scripts.calibrate_thresholds [--tickers SPY,QQQ,IWM]
                                            [--lookback-days 60]
                                            [--dry-run]

Reads from `market_data_intraday` Cloud SQL table; writes to
`ticker_calibration`. Idempotent — re-running on the same date upserts
the row (PRIMARY KEY = (ticker, calibration_date)).

Three-tier classification (per docs/plans/SIGNAL_QUALITY_TEST_PLAN.md):
  Tier A — values produced by THIS script (per-ticker, calibrated)
  Tier B — universal-but-tested constants in lib/strategies/config.py
  Tier C — universal, stays (CONSECUTIVE_PERIODS = 3)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Repo root on path so we can import gcp.* helpers
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import get_engine, is_cloud_sql_configured, upsert_dataframe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("calibrate_thresholds")

# ── Constants (Tier C — universal, structural) ─────────────────────────

# The 7 timeframes the multi-tf evaluator measures. Each gets its own
# calibrated clean/wrong/noise threshold based on per-ticker ATR.
TIMEFRAMES_MIN = {
    "5m": 5, "15m": 15, "30m": 30, "60m": 60,
    "90m": 90, "120m": 120, "240m": 240,
}

# How aggressively to scale the per-tf threshold from per-tf ATR median.
# clean threshold = atr × CLEAN_ATR_MULT; wrong = -atr × WRONG_ATR_MULT;
# noise = atr × NOISE_ATR_MULT (signed comparison absolutized at evaluation).
# Keeping these uniform across tickers is correct: the ATR itself is
# per-ticker, so scaling by a constant multiple of ATR gives per-ticker
# thresholds. (If different tickers wanted different multiples too, that
# becomes Tier A. So far one multiple suffices.)
CLEAN_ATR_MULT = 1.0     # >= 1 ATR move = clean hit
WRONG_ATR_MULT = 1.0     # <= -1 ATR adverse move = wrong direction
NOISE_ATR_MULT = 0.6     # |move| < 0.6 ATR = noise


# ── Bar resampling + indicators ────────────────────────────────────────

def resample_to_tf(bars_1min: pd.DataFrame, tf_min: int) -> pd.DataFrame:
    """Resample 1-min bars to a higher timeframe."""
    if tf_min == 1:
        return bars_1min.copy()
    df = bars_1min.set_index("ts").copy()
    rule = f"{tf_min}min"
    out = df.resample(rule, label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])
    return out.reset_index()


def compute_atr_pct(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range as % of close price."""
    if len(bars) < period + 1:
        return pd.Series([], dtype=float)
    h, l, c = bars["high"], bars["low"], bars["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    return (atr / c) * 100.0


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI."""
    if len(close) < period + 1:
        return pd.Series([], dtype=float)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_rvol(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume / rolling-N-period mean volume."""
    if len(volume) < period + 1:
        return pd.Series([], dtype=float)
    avg = volume.rolling(period, min_periods=period).mean()
    return volume / avg.replace(0, np.nan)


# ── Per-ticker calibration ─────────────────────────────────────────────

def calibrate_ticker(ticker: str, bars_1min: pd.DataFrame, lookback_days: int) -> dict:
    """Compute calibration for a single ticker."""
    if bars_1min.empty:
        log.warning("  %s: no bars; skipping", ticker)
        return {}

    log.info("  %s: %d bars from %s to %s",
             ticker, len(bars_1min),
             bars_1min["ts"].min(), bars_1min["ts"].max())

    out = {
        "ticker": ticker,
        "calibration_date": date.today(),
        "lookback_days": lookback_days,
        "n_bars_used": len(bars_1min),
        "earliest_bar_date": bars_1min["ts"].min().date(),
        "latest_bar_date": bars_1min["ts"].max().date(),
    }

    # ATR median per timeframe
    threshold_clean = {}
    threshold_wrong = {}
    threshold_noise = {}
    for tf_label, tf_min in TIMEFRAMES_MIN.items():
        tf_bars = resample_to_tf(bars_1min, tf_min)
        atr_pct = compute_atr_pct(tf_bars)
        atr_median = float(atr_pct.dropna().median()) if not atr_pct.dropna().empty else None
        out[f"atr_{tf_label}_median"] = atr_median

        if atr_median is None or np.isnan(atr_median) or atr_median <= 0:
            log.warning("  %s @ %s: insufficient ATR data", ticker, tf_label)
            continue

        threshold_clean[tf_label] = round(atr_median * CLEAN_ATR_MULT, 4)
        threshold_wrong[tf_label] = round(-atr_median * WRONG_ATR_MULT, 4)
        threshold_noise[tf_label] = round(atr_median * NOISE_ATR_MULT, 4)

    out["threshold_clean"] = json.dumps(threshold_clean)
    out["threshold_wrong"] = json.dumps(threshold_wrong)
    out["threshold_noise"] = json.dumps(threshold_noise)

    # RVOL distribution (computed on 1-min bars where the noise is sharpest)
    rvol = compute_rvol(bars_1min["volume"]).dropna()
    if not rvol.empty:
        out["rvol_p25"] = float(rvol.quantile(0.25))
        out["rvol_p50"] = float(rvol.quantile(0.50))
        out["rvol_p75"] = float(rvol.quantile(0.75))
        out["rvol_p95"] = float(rvol.quantile(0.95))
        # Filter band: P25 to P75 captures the meaty middle of the distribution.
        # Below P25 = thin tape (skip), above P75 = event-driven spike (consider
        # separately at fire time). Calibrated per-ticker so QQQ's "high RVOL"
        # bar at 1.2 doesn't get mis-treated like SPY's at 1.2.
        out["rvol_min"] = round(float(rvol.quantile(0.25)), 3)
        out["rvol_max"] = round(float(rvol.quantile(0.75)), 3)

    # RSI distribution (computed on 1-min bars; reveals regime)
    rsi = compute_rsi(bars_1min["close"]).dropna()
    if not rsi.empty:
        out["rsi_p10"] = float(rsi.quantile(0.10))
        out["rsi_p25"] = float(rsi.quantile(0.25))
        out["rsi_p50"] = float(rsi.quantile(0.50))
        out["rsi_p75"] = float(rsi.quantile(0.75))
        out["rsi_p90"] = float(rsi.quantile(0.90))

    out["atr_expansion_x"] = 1.3   # placeholder; future tuning may make this per-ticker

    return out


# ── Main ───────────────────────────────────────────────────────────────

def fetch_bars(ticker: str, lookback_days: int, eng) -> pd.DataFrame:
    """Pull 1-min bars for `ticker` from market_data_intraday for the
    most recent `lookback_days` calendar days.

    Uses the partitioned-table primary key (ticker, interval, ts) so the
    query hits the per-ticker partition directly.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    df = pd.read_sql(
        """
        SELECT ts, open, high, low, close, volume
          FROM market_data_intraday
         WHERE ticker = %s
           AND interval = '1min'
           AND ts >= %s
         ORDER BY ts
        """,
        eng,
        params=[ticker, cutoff],
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default="SPY,QQQ,IWM",
                   help="Comma-separated tickers (default: SPY,QQQ,IWM)")
    p.add_argument("--lookback-days", type=int, default=60,
                   help="Bar history window (default: 60)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute calibration but do not write to Cloud SQL")
    args = p.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env vars missing — aborting.")
        sys.exit(2)

    eng = get_engine()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("Calibrating %d ticker(s): %s (lookback=%dd)",
             len(tickers), ", ".join(tickers), args.lookback_days)

    rows = []
    for ticker in tickers:
        log.info("→ %s", ticker)
        bars = fetch_bars(ticker, args.lookback_days, eng)
        cal = calibrate_ticker(ticker, bars, args.lookback_days)
        if cal:
            rows.append(cal)
            log.info("  ✓ atr_60m=%s%%  rvol[%s, %s]  rsi_med=%s",
                     cal.get("atr_60m_median"),
                     cal.get("rvol_min"), cal.get("rvol_max"),
                     cal.get("rsi_p50"))

    if not rows:
        log.error("No calibration rows produced. Aborting.")
        sys.exit(3)

    df = pd.DataFrame(rows)

    if args.dry_run:
        log.info("--dry-run: would have written %d row(s):", len(df))
        for _, r in df.iterrows():
            log.info("  %s @ %s: clean=%s",
                     r["ticker"], r["calibration_date"], r["threshold_clean"])
        return

    n = upsert_dataframe(df, "ticker_calibration",
                          ["ticker", "calibration_date"])
    log.info("✓ wrote %d row(s) to ticker_calibration", n)


if __name__ == "__main__":
    main()
