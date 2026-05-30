#!/usr/bin/env python3
"""Intraday indicator → forward-return correlation / Information Coefficient (Cloud Run Job).

Reads 1-minute bars from Cloud SQL `market_data_intraday`, computes the full
production indicator suite via `lib.indicators.add_all_indicators` (the same
code path signal_monitor and the backtests use — no hand-rolled math, per
CLAUDE.md Rule 3.6), and ranks every numeric indicator by its correlation
against strictly-causal forward log-returns at configurable horizons.

For each (ticker, indicator, horizon) it writes:
  - pearson  : linear correlation
  - rank_ic  : Spearman rank correlation == the quant Information Coefficient
A POOLED pseudo-ticker row is also written (all tickers stacked) — that is the
headline cross-sectional ranking, since per-ticker raw price-level columns
(EMA/SMA/VWAP) are non-stationary and only reflect drift over the window.

Results land in the `indicator_correlation` table (idempotent upsert keyed on
(computed_date, window_start, window_end, ticker, indicator, horizon_min)), so
re-runs converge rather than duplicate.

Run modes
---------
    # Scheduled / default: trailing N sessions ending today
    python -m gcp.indicator_correlation_job

    # Historical replay: trailing N sessions ending AS-OF a date
    python -m gcp.indicator_correlation_job --as-of 2026-05-08

    # Tunables (also settable via env for Cloud Run --set-env-vars)
    python -m gcp.indicator_correlation_job \
        --tickers SPY,IWM,QQQ --horizons 5,15,30 --lookback-days 30 --dry-run

Env overrides (Cloud Run friendly): INDICATOR_CORR_TICKERS,
INDICATOR_CORR_HORIZONS, INDICATOR_CORR_LOOKBACK_DAYS, INDICATOR_CORR_AS_OF.

Exit codes: 0 = success (incl. clean no-op when a ticker has no data),
1 = unrecoverable error (e.g. ALL tickers empty → likely a stale-data /
connection problem worth surfacing as a failed run).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

# Repo root on path before any lib/gcp imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("indicator_correlation_job")

from lib.config import IndicatorConfig  # noqa: E402
from lib.indicators import add_all_indicators  # noqa: E402

RTH_START = time(9, 30)
RTH_END = time(16, 0)
RESULTS_TABLE = "indicator_correlation"

# OHLCV + bookkeeping columns — never ranked as "indicators".
_NON_INDICATOR_COLS = {"Open", "High", "Low", "Close", "Volume", "ticker", "Time", "Date"}
_RETURN_PREFIX = "fwd_ret_"

# Minimum paired (indicator, return) observations to trust a correlation.
_MIN_PAIRS = 200
# Minimum non-null / non-constant readings for a column to be an indicator.
_MIN_VALID = 100


# ---------------------------------------------------------------------------
# Pure functions (I/O-free — unit-tested without Cloud SQL, per Rule 0.3)
# ---------------------------------------------------------------------------

def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only regular-trading-hours bars (09:30–16:00 ET)."""
    if df.empty:
        return df
    if "Time" in df.columns:
        t = pd.to_datetime(df["Time"]).dt.time
    else:
        t = pd.Series(pd.to_datetime(df.index).time, index=df.index)
    return df[(t >= RTH_START) & (t <= RTH_END)].copy()


def add_forward_returns(df: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    """Add strictly-causal forward log-returns per session.

    ret_h(t) = ln(Close[t+h]) - ln(Close[t]); shifted WITHIN each trading day
    so the lookahead never crosses the session close. The trailing h bars of
    each session become NaN and are dropped pairwise in `correlate`.
    """
    if df.empty:
        return df
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Time"]).dt.date
    for h in horizons:
        out[f"{_RETURN_PREFIX}{h}"] = out.groupby("Date")["Close"].transform(
            lambda s: np.log(s).shift(-h) - np.log(s)
        )
    return out


def indicator_columns(df: pd.DataFrame) -> List[str]:
    """Numeric, non-degenerate indicator columns eligible for correlation."""
    cols: List[str] = []
    for c in df.columns:
        if c in _NON_INDICATOR_COLS or c.startswith(_RETURN_PREFIX):
            continue
        if not np.issubdtype(df[c].dtype, np.number):
            continue
        s = df[c]
        if s.notna().sum() < _MIN_VALID or s.nunique(dropna=True) <= 1:
            continue
        cols.append(c)
    return cols


def correlate(df: pd.DataFrame, ind_cols: List[str], horizons: List[int]) -> pd.DataFrame:
    """Tidy rows: indicator, horizon_min, pearson, rank_ic, abs_rank_ic, n."""
    rows = []
    for h in horizons:
        ret_col = f"{_RETURN_PREFIX}{h}"
        if ret_col not in df.columns:
            continue
        y = df[ret_col]
        for col in ind_cols:
            pair = pd.concat([df[col], y], axis=1).dropna()
            if len(pair) < _MIN_PAIRS:
                continue
            xv, yv = pair.iloc[:, 0], pair.iloc[:, 1]
            pearson = xv.corr(yv, method="pearson")
            rank_ic = xv.corr(yv, method="spearman")
            rows.append({
                "indicator": col,
                "horizon_min": h,
                "pearson": float(pearson) if pd.notna(pearson) else None,
                "rank_ic": float(rank_ic) if pd.notna(rank_ic) else None,
                "abs_rank_ic": abs(float(rank_ic)) if pd.notna(rank_ic) else None,
                "n": int(len(pair)),
            })
    return pd.DataFrame(rows)


def enrich(raw: pd.DataFrame, cfg: IndicatorConfig, horizons: List[int]) -> pd.DataFrame:
    """Raw OHLCV (with Time) → RTH bars with full indicator suite + fwd returns.

    Runs the production indicator engine, so the columns are byte-identical to
    what signal_monitor / backtests compute.
    """
    enriched = add_all_indicators(raw, close_col="Close", indicator_config=cfg)
    enriched = add_forward_returns(enriched, horizons)
    return filter_rth(enriched)


# ---------------------------------------------------------------------------
# Argument / env resolution
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) else v


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default=_env("INDICATOR_CORR_TICKERS", "SPY,IWM,QQQ"),
                   help="Comma-separated tickers (default SPY,IWM,QQQ).")
    p.add_argument("--horizons", default=_env("INDICATOR_CORR_HORIZONS", "5,15,30"),
                   help="Comma-separated forward-return horizons in minutes.")
    p.add_argument("--lookback-days", type=int,
                   default=int(_env("INDICATOR_CORR_LOOKBACK_DAYS", "30")),
                   help="Calendar days of intraday history to pull (default 30).")
    p.add_argument("--as-of", default=_env("INDICATOR_CORR_AS_OF", "") or None,
                   help="End date YYYY-MM-DD for historical replay (default today).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute + log but do not write to Cloud SQL.")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Job orchestration
# ---------------------------------------------------------------------------

def run(
    tickers: List[str],
    horizons: List[int],
    lookback_days: int,
    as_of: date,
    dry_run: bool,
) -> pd.DataFrame:
    """Compute the correlation table for all tickers + a POOLED row set.

    Returns the tidy results DataFrame (also the value persisted). Reading and
    writing are injected via module-level functions so tests can monkeypatch
    them without a live database.
    """
    from lib.data_loader import DataLoader

    cfg = IndicatorConfig()
    loader = DataLoader(data_dir=_env("DATA_DIR", "data"))

    start = as_of - timedelta(days=lookback_days)
    start_str, end_str = start.isoformat(), as_of.isoformat()
    logger.info("Window %s → %s | tickers=%s | horizons=%s",
                start_str, end_str, tickers, horizons)

    per_ticker_results: List[pd.DataFrame] = []
    pooled_frames: List[pd.DataFrame] = []
    loaded = 0

    for tk in tickers:
        raw = loader.load_intraday(tk, start_date=start_str, end_date=end_str,
                                   on_stale="warn")
        if raw is None or raw.empty:
            # Rule 3.7: do NOT fabricate a zero-correlation row. Skip with an
            # explicit reason; the all-empty case is caught below as a failure.
            logger.warning("No intraday data for %s in window; skipping ticker.", tk)
            continue
        if "Time" not in raw.columns:
            raw = raw.copy()
            raw["Time"] = pd.to_datetime(raw.index)
        loaded += 1

        enriched = enrich(raw, cfg, horizons)
        ind_cols = indicator_columns(enriched)
        sessions = enriched["Date"].nunique() if "Date" in enriched else 0
        logger.info("[%s] %d RTH bars, %d sessions, %d indicator columns",
                    tk, len(enriched), sessions, len(ind_cols))

        tidy = correlate(enriched, ind_cols, horizons)
        tidy.insert(0, "ticker", tk)
        per_ticker_results.append(tidy)

        keep = ind_cols + [f"{_RETURN_PREFIX}{h}" for h in horizons]
        pooled_frames.append(enriched[keep])

    if loaded == 0:
        # All tickers empty → this is NOT a clean no-op; it almost certainly
        # signals a connection / staleness problem. Fail loud (Rule 3.7).
        raise RuntimeError(
            f"No intraday data for ANY of {tickers} in window {start_str}..{end_str}. "
            "Refusing to write an empty/misleading result set."
        )

    results = pd.concat(per_ticker_results, ignore_index=True)

    # POOLED ranking across the common indicator set.
    if len(pooled_frames) > 1:
        common = set.intersection(*[set(indicator_columns(f)) for f in pooled_frames])
        if common:
            pooled = pd.concat(pooled_frames, ignore_index=True)
            pooled_tidy = correlate(pooled, sorted(common), horizons)
            pooled_tidy.insert(0, "ticker", "POOLED")
            results = pd.concat([results, pooled_tidy], ignore_index=True)

    # Stamp window metadata for the upsert key + provenance.
    results["computed_date"] = as_of
    results["window_start"] = start
    results["window_end"] = as_of
    results["lookback_days"] = lookback_days

    logger.info("Computed %d (ticker, indicator, horizon) correlation rows.",
                len(results))

    # Headline log: pooled top drivers at the mid horizon.
    mid = horizons[len(horizons) // 2]
    pooled_mid = results[(results.ticker == "POOLED") & (results.horizon_min == mid)]
    if not pooled_mid.empty:
        top = pooled_mid.reindex(
            pooled_mid["abs_rank_ic"].astype(float).sort_values(ascending=False).index
        ).head(10)
        for _, r in top.iterrows():
            logger.info("  POOLED %dm | %-22s rank_ic=%+.4f pearson=%+.4f n=%d",
                        mid, r["indicator"], r["rank_ic"], r["pearson"], r["n"])

    if dry_run:
        logger.info("(dry-run) skipping write of %d rows to %s", len(results), RESULTS_TABLE)
        return results

    _persist(results)
    return results


def _persist(results: pd.DataFrame) -> int:
    """Upsert the tidy results into Cloud SQL. Isolated for test monkeypatching."""
    from gcp.database import upsert_dataframe

    conflict = ["computed_date", "window_start", "window_end", "ticker",
                "indicator", "horizon_min"]
    n = upsert_dataframe(results, RESULTS_TABLE, conflict_cols=conflict)
    logger.info("Upserted %d rows into %s", n, RESULTS_TABLE)
    return n


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    horizons = sorted({int(h) for h in args.horizons.split(",") if h.strip()})
    as_of = (datetime.strptime(args.as_of, "%Y-%m-%d").date()
             if args.as_of else date.today())

    if not tickers:
        logger.error("No tickers resolved; nothing to do.")
        return 1
    if not horizons:
        logger.error("No horizons resolved; nothing to do.")
        return 1

    try:
        run(tickers, horizons, args.lookback_days, as_of, args.dry_run)
    except Exception as e:  # noqa: BLE001 — top-level boundary: log + non-zero exit
        logger.error("indicator_correlation_job failed: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
