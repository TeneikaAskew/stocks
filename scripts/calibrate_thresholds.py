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
from sqlalchemy import text

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

def calibrate_ticker(
    ticker: str,
    bars_1min: pd.DataFrame,
    lookback_days: int,
    *,
    as_of: Optional[date] = None,
) -> dict:
    """Compute calibration for a single ticker.

    `as_of` overrides the `calibration_date` written to the output row.
    Used by the #250 backfill so historical-window calibrations are
    timestamped at the quarter boundary they represent, not at the
    moment the backfill happens to run.
    """
    if bars_1min.empty:
        log.warning("  %s: no bars; skipping", ticker)
        return {}

    log.info("  %s: %d bars from %s to %s",
             ticker, len(bars_1min),
             bars_1min["ts"].min(), bars_1min["ts"].max())

    out = {
        "ticker": ticker,
        "calibration_date": as_of or date.today(),
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

def fetch_bars(
    ticker: str,
    lookback_days: int,
    eng,
    *,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """Pull 1-min bars for `ticker` from market_data_intraday for the
    `lookback_days` calendar-day window ending on `as_of` (defaults to today).

    `as_of` lets the calibrator be replayed against any historical date —
    used by the #250 backfill to populate `ticker_calibration` rows for
    prior quarters (Q4-2025, Q1-2026, Q2-2026) so the drift guard has
    a 4-quarter rolling window without waiting until 2027-01.

    Uses the partitioned-table primary key (ticker, interval, ts) so the
    query hits the per-ticker partition directly.
    """
    end = as_of or date.today()
    cutoff = end - timedelta(days=lookback_days)
    sql = text("""
        SELECT ts, open, high, low, close, volume
          FROM market_data_intraday
         WHERE ticker = :ticker
           AND interval = '1min'
           AND ts >= :cutoff
           AND ts <  :end_excl
         ORDER BY ts
    """)
    df = pd.read_sql(
        sql, eng,
        params={"ticker": ticker,
                "cutoff": cutoff,
                "end_excl": end + timedelta(days=1)},
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


# ── #250 Drift guard ───────────────────────────────────────────────────
#
# Compares each new calibration row against the rolling-4-row mean/stdev
# for the same ticker. Numeric columns checked: ATR medians per timeframe,
# RVOL p25/p50/p75/p95, RSI p10/p25/p50/p75/p90.
#
#   |new - mean| > 2σ  → flag drift_flagged=TRUE; row is written, but
#                         lib/strategies/calibration.py falls back to Tier-B
#                         when reading flagged rows (single anomalous
#                         quarter doesn't whipsaw production).
#   |new - mean| > 3σ  → REFUSE the write (this ticker is skipped this
#                         run unless --force is passed).
#
# Requires ≥3 prior rows to compute meaningful stdev. Fewer than that =
# pass-through (drift_flagged=FALSE, no refusal).

# Numeric columns checked for drift. Threshold (clean/wrong/noise) and
# atr_expansion_x are deliberately excluded:
#   - threshold_* are JSONB (composed values; checking the inputs catches
#     the same drift)
#   - atr_expansion_x is a fixed constant in the calibration (1.3) so
#     drift would mean the constant changed in code, not a market shift
_DRIFT_COLUMNS = (
    "atr_5m_median", "atr_15m_median", "atr_30m_median", "atr_60m_median",
    "atr_90m_median", "atr_120m_median", "atr_240m_median",
    "rvol_p25", "rvol_p50", "rvol_p75", "rvol_p95",
    "rsi_p10", "rsi_p25", "rsi_p50", "rsi_p75", "rsi_p90",
)
_DRIFT_WARN_SIGMAS = 2.0
_DRIFT_REFUSE_SIGMAS = 3.0
_DRIFT_MIN_PRIOR_ROWS = 3   # need ≥3 to compute stdev meaningfully


def check_drift(
    ticker: str,
    new_row: dict,
    eng,
    *,
    warn_sigmas: float = _DRIFT_WARN_SIGMAS,
    refuse_sigmas: float = _DRIFT_REFUSE_SIGMAS,
    min_prior: int = _DRIFT_MIN_PRIOR_ROWS,
) -> tuple[bool, bool, list[str]]:
    """Compare `new_row` against the prior calibrations for `ticker`.

    Returns (drift_flagged, refuse, messages):
      drift_flagged: any column exceeded warn_sigmas
      refuse:        any column exceeded refuse_sigmas (caller respects
                     --force to override)
      messages:      human-readable per-column drift details for logging

    Pure SQL + numeric — does NOT mutate the new row. Caller sets
    `new_row["drift_flagged"]` based on the return value.

    Returns (False, False, [...]) when fewer than `min_prior` prior rows
    exist (drift can't be measured against a sample size of 0-2).
    """
    import statistics
    from sqlalchemy import text

    # Pull the most recent 4 prior calibration rows for this ticker.
    # Strict < calibration_date so re-running on the same date doesn't
    # compare against itself (the upsert would write into the same row).
    sql = text(
        f"SELECT calibration_date, {', '.join(_DRIFT_COLUMNS)} "
        f"FROM ticker_calibration "
        f"WHERE ticker = :t AND calibration_date < :d "
        f"ORDER BY calibration_date DESC LIMIT 4"
    )
    df = pd.read_sql(
        sql, eng,
        params={"t": ticker, "d": new_row["calibration_date"]},
    )

    if len(df) < min_prior:
        return (False, False, [
            f"{ticker}: only {len(df)} prior row(s); skipping drift check "
            f"(need ≥{min_prior})"
        ])

    drift_flagged = False
    refuse = False
    messages: list[str] = []
    for col in _DRIFT_COLUMNS:
        new_val = new_row.get(col)
        if new_val is None:
            continue
        prior = [v for v in df[col].tolist() if v is not None and not pd.isna(v)]
        if len(prior) < min_prior:
            continue
        try:
            mean = statistics.fmean(prior)
            sd = statistics.stdev(prior) if len(prior) > 1 else 0.0
        except statistics.StatisticsError:
            continue
        if sd == 0.0:
            # All prior values identical — only flag if the new value
            # differs at all (any change is "drift" relative to a flat history).
            if abs(new_val - mean) > 0:
                messages.append(
                    f"  {ticker}.{col}: new={new_val:.6g} mean={mean:.6g} "
                    f"sd=0 (history is flat) → ANY change is drift"
                )
                drift_flagged = True
            continue
        z = abs(new_val - mean) / sd
        if z >= refuse_sigmas:
            messages.append(
                f"  {ticker}.{col}: new={new_val:.6g} mean={mean:.6g} "
                f"sd={sd:.6g} → {z:.2f}σ DRIFT (>{refuse_sigmas}σ — REFUSE)"
            )
            drift_flagged = True
            refuse = True
        elif z >= warn_sigmas:
            messages.append(
                f"  {ticker}.{col}: new={new_val:.6g} mean={mean:.6g} "
                f"sd={sd:.6g} → {z:.2f}σ DRIFT (>{warn_sigmas}σ — flag)"
            )
            drift_flagged = True
    return (drift_flagged, refuse, messages)


def _parse_as_of(raw: Optional[str]) -> Optional[date]:
    """Parse `--as-of YYYY-MM-DD` into a date. Refuses future dates so the
    backfill can't accidentally calibrate against bars that don't exist yet.
    """
    if not raw:
        return None
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise SystemExit(f"--as-of {raw!r} is not a valid YYYY-MM-DD date")
    if d > date.today():
        raise SystemExit(f"--as-of {raw!r} is in the future")
    return d


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default="SPY,QQQ,IWM",
                   help="Comma-separated tickers (default: SPY,QQQ,IWM)")
    p.add_argument("--lookback-days", type=int, default=60,
                   help="Bar history window (default: 60)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute calibration but do not write to Cloud SQL")
    p.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                   help="Calibrate AS OF this date — uses bars from "
                        "(as-of − lookback-days) to as-of inclusive, "
                        "and writes calibration_date = as-of. Used by the "
                        "#250 backfill to populate prior-quarter rows; "
                        "default is today (live cadence).")
    p.add_argument("--force", action="store_true",
                   help="Write rows that the #250 drift guard would otherwise "
                        "refuse (>3σ deviation from rolling 4-row mean). Use "
                        "after you have manually verified the new value is "
                        "real — e.g. legitimate regime change vs. broken "
                        "calibration window. Without --force, drifted rows "
                        "are skipped and logged.")
    args = p.parse_args()

    as_of = _parse_as_of(args.as_of)

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env vars missing — aborting.")
        sys.exit(2)

    eng = get_engine()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if as_of:
        log.info("Calibrating %d ticker(s) AS OF %s: %s (lookback=%dd)",
                 len(tickers), as_of, ", ".join(tickers), args.lookback_days)
    else:
        log.info("Calibrating %d ticker(s): %s (lookback=%dd)",
                 len(tickers), ", ".join(tickers), args.lookback_days)

    rows = []
    refused = []   # (ticker, drift_messages) tuples for end-of-run summary
    for ticker in tickers:
        log.info("→ %s", ticker)
        bars = fetch_bars(ticker, args.lookback_days, eng, as_of=as_of)
        cal = calibrate_ticker(ticker, bars, args.lookback_days, as_of=as_of)
        if not cal:
            continue
        # #250 drift guard — compare against rolling 4-row history.
        drift_flagged, refuse, drift_msgs = check_drift(ticker, cal, eng)
        for m in drift_msgs:
            log.info(m)
        if refuse and not args.force:
            log.error(
                "  ✗ %s: drift exceeded 3σ — REFUSING write. Re-run with "
                "--force to override after manual verification.", ticker
            )
            refused.append((ticker, drift_msgs))
            continue
        # #250 / Codex P2 on #397: --force is the manual-override path. When
        # the operator passes --force, they're attesting that the drift is
        # legitimate (e.g. real regime change vs broken calibration window),
        # so the written row gets drift_flagged=FALSE — otherwise the
        # resolver would still fall back to Tier-B and the manual override
        # would be a no-op for production. The drift evidence is preserved
        # in the run log (drift_msgs above) for audit trail.
        if drift_flagged and args.force:
            log.warning(
                "  ⚠ %s: --force overrides drift detection (was %s) — "
                "writing drift_flagged=FALSE; operator has accepted the "
                "new calibration. Drift evidence preserved in log above.",
                ticker, "REFUSE (>3σ)" if refuse else "FLAG (>2σ)"
            )
            cal["drift_flagged"] = False
        elif drift_flagged:
            cal["drift_flagged"] = True
            log.warning(
                "  ⚠ %s: drift_flagged=TRUE (>2σ on at least one column); "
                "live resolver will fall back to Tier-B until either the "
                "next calibration confirms the new regime, or the operator "
                "re-runs with --force to manually accept it", ticker
            )
        else:
            cal["drift_flagged"] = False
        rows.append(cal)
        log.info("  ✓ atr_60m=%s%%  rvol[%s, %s]  rsi_med=%s  drift=%s",
                 cal.get("atr_60m_median"),
                 cal.get("rvol_min"), cal.get("rvol_max"),
                 cal.get("rsi_p50"), drift_flagged)

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
