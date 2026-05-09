"""Per-ticker blue-sky synthetic-trigger offset calibration (G.P1.4 follow-up).

Refreshes ``exit_config_overrides.blue_sky_atr_offset`` per ticker by
measuring the historical (RTH high − pre_high) / ATR distribution on
gap-up days for longs and the symmetric (pre_low − RTH low) / ATR for
shorts. Used by ``lib/agents/trade_planner.select_trigger_and_regime``
when every multi-timeframe structural level has been cleared by
pre-market — synthesizes a trigger at ``cleared_above + offset × ATR``.

The default offset (``_BLUE_SKY_ATR_OFFSET = 0.20`` in trade_planner.py)
is the cross-ticker fallback. Per-ticker values from this script
take precedence via the same Tier-A → Tier-B resolver pattern Track E
established (lib/strategies/exit_config_overrides.py).

Refresh cadence: monthly (1st of each month at 02:30 UTC) via the
``calibrate-blue-sky-offset`` Cloud Run Job. Manual run any time:

    python -m scripts.calibrate_blue_sky_offset
        [--tickers SPY,QQQ,IWM]
        [--lookback-days 90]
        [--metric mean|median|p75]
        [--min-events 6]
        [--dry-run]

Reads from ``market_data_daily``; writes (UPDATE in place) to
``exit_config_overrides``. Designed to be tolerant of small samples —
when ``n_extension_events < min-events`` for a ticker, the script
SKIPS the update so a noisy estimate doesn't replace a known-good
value. Operator gets a warning log line per skipped ticker.

Audit 2026-05-08 G.P1.4 follow-up. The hand-seeded values from PR
#334 (SPY/IWM=0.15, QQQ=0.20) reflect ~18 days of pre_high coverage;
this script lets the values track real production data going
forward.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text

# Repo root on path so we can import gcp.* helpers
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import get_engine, is_cloud_sql_configured  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("calibrate_blue_sky_offset")

# Lower bound on the per-ticker offset. Below this the synthetic
# trigger would sit so close to pre_high that any pre-market wick
# would trip it on the open. 0.05 ATR is roughly 1 minute's worth of
# noise on a typical-vol bar.
_OFFSET_FLOOR = 0.05

# Upper bound on the per-ticker offset. Above this the synthetic
# trigger would be far enough that the entry typically misses, and
# the trader is better served waiting for the actual ORB. 0.50 ATR is
# the original PR #334 default before recalibration showed it was too
# aggressive.
_OFFSET_CEILING = 0.50

# Round computed offsets to this grid for stability across runs (avoid
# thrashing the value by 0.001 when N is small). 0.05 grid lines up
# with operator-friendly values (0.10, 0.15, 0.20, 0.25, ...).
_OFFSET_GRID = 0.05


def compute_blue_sky_offset(
    bars: pd.DataFrame,
    metric: str = "mean",
) -> Optional[dict]:
    """Compute the blue-sky offset for one ticker from daily bars.

    ``bars`` is a DataFrame with columns:
      * ``date``, ``close``, ``pre_high``, ``pre_low``, ``high``,
        ``low``, ``atr_14``

    Returns ``None`` when there's no usable extension data (no rows
    with both pre_high and a positive RTH extension past pre_high) so
    the caller can skip the update for this ticker.
    """
    if bars.empty:
        return None
    df = bars.copy()
    df = df.dropna(subset=["pre_high", "pre_low", "high", "low", "close", "atr_14"])
    df = df[df["atr_14"] > 0]
    if df.empty:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    df["prev_close"] = df["close"].shift(1)
    df = df.dropna(subset=["prev_close"])
    df = df[df["prev_close"] > 0]
    if df.empty:
        return None

    df["gap_up_atr"] = (df["pre_high"] - df["prev_close"]) / df["atr_14"]
    df["gap_down_atr"] = (df["prev_close"] - df["pre_low"]) / df["atr_14"]
    df["long_extension"] = (df["high"] - df["pre_high"]) / df["atr_14"]
    df["short_extension"] = (df["pre_low"] - df["low"]) / df["atr_14"]

    long_extensions = df.loc[
        (df["gap_up_atr"] > 0) & (df["long_extension"] > 0), "long_extension"
    ]
    short_extensions = df.loc[
        (df["gap_down_atr"] > 0) & (df["short_extension"] > 0), "short_extension"
    ]
    extensions = pd.concat([long_extensions, short_extensions])
    n_events = int(len(extensions))
    if n_events == 0:
        return None

    if metric == "mean":
        raw = float(extensions.mean())
    elif metric == "median":
        raw = float(extensions.median())
    elif metric == "p75":
        raw = float(extensions.quantile(0.75))
    else:
        raise ValueError(f"unknown metric {metric!r}")

    clamped = max(_OFFSET_FLOOR, min(_OFFSET_CEILING, raw))
    rounded = round(clamped / _OFFSET_GRID) * _OFFSET_GRID
    rounded = round(rounded, 2)

    return {
        "n_events": n_events,
        "n_long_events": int(len(long_extensions)),
        "n_short_events": int(len(short_extensions)),
        "raw_value": round(raw, 4),
        "clamped_value": round(clamped, 4),
        "offset": rounded,
    }


def fetch_bars(ticker: str, lookback_days: int, eng) -> pd.DataFrame:
    sql = text(
        """
        SELECT date, close, pre_high, pre_low, high, low, atr_14
          FROM market_data_daily
         WHERE ticker = :ticker
           AND date >= CURRENT_DATE - (:days || ' days')::interval
         ORDER BY date ASC
        """
    )
    return pd.read_sql(sql, eng, params={"ticker": ticker.upper(), "days": lookback_days})


def update_offset(eng, ticker: str, offset: float, n_events: int,
                  metric: str, lookback_days: int) -> int:
    """UPDATE the most-recent exit_config_overrides row for `ticker` in
    place, setting blue_sky_atr_offset and appending a calibration note.

    Returns the number of rows touched (0 if the ticker has no override
    row at all — operator should run the seed migration first).
    """
    sql = text(
        """
        WITH latest AS (
            SELECT ticker, calibration_date
              FROM exit_config_overrides
             WHERE ticker = :ticker
             ORDER BY calibration_date DESC
             LIMIT 1
        )
        UPDATE exit_config_overrides eco
           SET blue_sky_atr_offset = :offset,
               notes = COALESCE(eco.notes, '') ||
                       E'\n[' || CURRENT_DATE::text ||
                       '] blue_sky_atr_offset=' || :offset::text ||
                       ' (metric=' || :metric ||
                       ' n=' || :n_events::text ||
                       ' lookback=' || :lookback || 'd)'
          FROM latest
         WHERE eco.ticker = latest.ticker
           AND eco.calibration_date = latest.calibration_date
        """
    )
    with eng.begin() as conn:
        result = conn.execute(sql, {
            "ticker": ticker.upper(),
            "offset": float(offset),
            "metric": metric,
            "n_events": int(n_events),
            "lookback": int(lookback_days),
        })
        return result.rowcount


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default="SPY,QQQ,IWM",
                   help="Comma-separated tickers (default: SPY,QQQ,IWM)")
    p.add_argument("--lookback-days", type=int, default=90,
                   help="Window of daily bars (default: 90)")
    p.add_argument("--metric", default="mean", choices=("mean", "median", "p75"),
                   help="Distribution stat for the offset (default: mean)")
    p.add_argument("--min-events", type=int, default=6,
                   help="Skip ticker if extension-event count < this (default: 6)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute offsets but do NOT write to Cloud SQL")
    args = p.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env vars missing — aborting.")
        sys.exit(2)

    eng = get_engine()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("Calibrating blue-sky offset for %d ticker(s): %s",
             len(tickers), ", ".join(tickers))
    log.info("  lookback=%dd metric=%s min_events=%d",
             args.lookback_days, args.metric, args.min_events)

    written = 0
    skipped = 0
    for ticker in tickers:
        bars = fetch_bars(ticker, args.lookback_days, eng)
        result = compute_blue_sky_offset(bars, metric=args.metric)
        if result is None:
            log.warning("  %s: no usable extension data — skipping", ticker)
            skipped += 1
            continue
        if result["n_events"] < args.min_events:
            log.warning(
                "  %s: only %d extension events (< min %d) — skipping; "
                "raw=%.3f would_be=%.2f",
                ticker, result["n_events"], args.min_events,
                result["raw_value"], result["offset"],
            )
            skipped += 1
            continue
        log.info(
            "  %s: n_events=%d (long=%d short=%d) raw=%.3f → offset=%.2f",
            ticker, result["n_events"],
            result["n_long_events"], result["n_short_events"],
            result["raw_value"], result["offset"],
        )
        if args.dry_run:
            log.info("    --dry-run: would UPDATE exit_config_overrides for %s", ticker)
            continue
        n_rows = update_offset(eng, ticker, result["offset"],
                               result["n_events"], args.metric,
                               args.lookback_days)
        if n_rows == 0:
            log.warning(
                "  %s: no exit_config_overrides row exists — operator "
                "should seed via schema.sql migration first",
                ticker,
            )
            skipped += 1
        else:
            written += 1

    log.info("✓ wrote=%d skipped=%d", written, skipped)
    if written == 0 and not args.dry_run:
        log.error("No rows written — aborting with non-zero exit so the "
                  "scheduler surfaces this run as failed.")
        sys.exit(3)


if __name__ == "__main__":
    main()
