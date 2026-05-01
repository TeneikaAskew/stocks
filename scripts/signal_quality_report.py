"""Phase 0.5 — productionized signal-quality analysis.

Promoted from `scripts/_signal_eval_v*.py` (the local throwaways that
read creds from `.creds_tmp/` and wrote CSVs). This is the canonical
production pipeline: persisted output to `signal_metrics`, scheduled,
regression-alarmed.

Inputs:
    historical_signals     — source rows (one per fire) with the
                             return_5min..return_60min columns already
                             populated by the historical_signals job.
    market_data_intraday   — used to extend MFE windows past 60 min
                             (90/120/240m) and to compute ATR context.

Outputs:
    signal_metrics         — one row per (ticker, entry_time, strategy)
                             with classifications + returns at every
                             timeframe + ATR-normalized MFE.

Modes:
    --mode=historical      — backfill: process completed signals only.
                             All rows write status='final'.
    --mode=rolling         — incremental: process the last N hours of
                             fires. Rows with not-yet-closed timeframes
                             write status='pending' and get re-evaluated
                             on the next hourly run, eventually
                             promoting to 'final' once all 7 windows
                             have closed.

Stale-data fail-loud: in `rolling` mode, if `market_data_intraday`
is more than 1 hour stale during market hours, the script exits
non-zero rather than silently producing wrong numbers.

Hermetic-testable: `classify()`, `compute_metrics_for_signal()`, and
`determine_status()` are pure functions that don't touch the DB. Only
the CLI orchestrator does I/O.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.indicators import calculate_atr  # noqa: E402

logger = logging.getLogger(__name__)


# ── Classification thresholds (Tier C — universal, structural) ────────
# These are the same numbers the v4 throwaway script used. They live
# here as named constants instead of inline magic so the test suite can
# patch them and the weekly QA report can reference the exact value.
# Returns are FRACTIONS (0.005 = 0.5%), matching historical_signals
# return_*min columns.

CLEAN_THRESHOLD: float = 0.005   # |return| ≥ 0.5% → CLEAN_HIT or WRONG_DIRECTION
NOISE_THRESHOLD: float = 0.003   # |return| < 0.3% → NOISE
                                 # in-between → MIXED

# Timeframes evaluated, in minutes, in the order they appear in the
# signal_metrics columns. The first 4 come straight from
# historical_signals.return_*min; the last 3 require intraday-bar
# extension so they're computed inline below.
SOURCE_TFS_MIN: tuple[int, ...] = (5, 15, 30, 60)
EXTENDED_TFS_MIN: tuple[int, ...] = (90, 120, 240)
ALL_TFS_MIN: tuple[int, ...] = SOURCE_TFS_MIN + EXTENDED_TFS_MIN


# ── Pure helpers (no I/O) ─────────────────────────────────────────────

def classify(return_pct: Optional[float]) -> str:
    """Map a directional return to a classification label.

    Input is the FAVORABLE-EXCURSION return for the source signal's
    direction — historical_signals.return_*min columns are already
    direction-adjusted, so positive = favorable for both CALL and PUT.

    Returns one of:
        'INSUFFICIENT_DATA' — return is None / NaN (window not closed)
        'WRONG_DIRECTION'   — return ≤ -CLEAN_THRESHOLD
        'NOISE'             — |return| < NOISE_THRESHOLD
        'CLEAN_HIT'         — return ≥ +CLEAN_THRESHOLD
        'MIXED'             — between NOISE and CLEAN, in either sign
    """
    if return_pct is None or (isinstance(return_pct, float) and np.isnan(return_pct)):
        return "INSUFFICIENT_DATA"
    r = float(return_pct)
    if r <= -CLEAN_THRESHOLD:
        return "WRONG_DIRECTION"
    if r >= CLEAN_THRESHOLD:
        return "CLEAN_HIT"
    if abs(r) < NOISE_THRESHOLD:
        return "NOISE"
    return "MIXED"


def best_clean_timeframe(returns_by_tf: dict[int, Optional[float]]) -> Optional[str]:
    """Return the shortest timeframe that classified CLEAN_HIT, e.g. '15m'.

    Used to surface "fastest winner" in the weekly QA report — a signal
    that's clean at 15m is more useful than one only clean at 240m.
    Returns None if no timeframe classified clean.
    """
    for mins in sorted(returns_by_tf):  # ascending
        if classify(returns_by_tf[mins]) == "CLEAN_HIT":
            return f"{mins}m"
    return None


def determine_status(
    returns_by_tf: dict[int, Optional[float]],
    *,
    mode: str,
) -> str:
    """Whether this row is provisional ('pending') or settled ('final').

    Historical mode always returns 'final' — by definition the window
    has closed. Rolling mode returns 'pending' if any timeframe lacks
    data, since we'll re-evaluate on the next hourly run and promote
    the row once all windows have closed.
    """
    if mode == "historical":
        return "final"
    has_all = all(
        v is not None and not (isinstance(v, float) and np.isnan(v))
        for v in returns_by_tf.values()
    )
    return "final" if has_all else "pending"


def extend_returns_from_intraday(
    intraday: pd.DataFrame,
    entry_time: pd.Timestamp,
    entry_price: float,
    direction: str,
    extra_tfs_min: tuple[int, ...] = EXTENDED_TFS_MIN,
) -> dict[int, Optional[float]]:
    """Compute MFE-style returns at the extended timeframes.

    `intraday` must have at least: Time (datetime), High, Low. Bars
    must be sorted by Time and cover [entry_time, entry_time + max(tf)].

    Returns a dict {minutes: fractional_return_or_None}.

    For CALL: favorable excursion = (max High in window - entry) / entry
    For PUT:  favorable excursion = (entry - min Low in window)  / entry

    Sign convention matches historical_signals.return_*min — positive
    is always favorable, regardless of direction.
    """
    out: dict[int, Optional[float]] = {}
    if intraday is None or intraday.empty or entry_price <= 0:
        return {tf: None for tf in extra_tfs_min}

    bars = intraday[intraday["Time"] >= entry_time]
    direction_upper = direction.upper()

    for tf_min in extra_tfs_min:
        window_end = entry_time + timedelta(minutes=tf_min)
        window = bars[bars["Time"] <= window_end]
        if window.empty:
            out[tf_min] = None
            continue
        if direction_upper == "CALL":
            best = float(window["High"].max())
            ret = (best - entry_price) / entry_price
        elif direction_upper == "PUT":
            best = float(window["Low"].min())
            ret = (entry_price - best) / entry_price
        else:
            out[tf_min] = None
            continue
        out[tf_min] = ret
    return out


def compute_atr_pct(
    intraday_lookback: pd.DataFrame, entry_price: float, period: int = 14,
) -> Optional[float]:
    """ATR(14) on 5m bars, expressed as a fraction of entry price.

    `intraday_lookback` must have High, Low, Close columns and at least
    `period + 1` bars ending at (or just before) the signal time.
    Returns None if not enough bars are available.
    """
    if intraday_lookback is None or len(intraday_lookback) < period + 1 or entry_price <= 0:
        return None
    atr_series = calculate_atr(
        intraday_lookback["High"],
        intraday_lookback["Low"],
        intraday_lookback["Close"],
        period=period,
    )
    if atr_series.empty or pd.isna(atr_series.iloc[-1]):
        return None
    return float(atr_series.iloc[-1]) / float(entry_price)


@dataclass
class SignalMetrics:
    """The full metrics row written to signal_metrics for one signal."""
    ticker: str
    entry_time: datetime
    strategy: str
    cls_5m: str
    cls_15m: str
    cls_30m: str
    cls_60m: str
    cls_90m: str
    cls_120m: str
    cls_240m: str
    best_tf: Optional[str]
    return_5m: Optional[float]
    return_15m: Optional[float]
    return_30m: Optional[float]
    return_60m: Optional[float]
    return_90m: Optional[float]
    return_120m: Optional[float]
    return_240m: Optional[float]
    atr_5m_pct: Optional[float]
    mfe_60m_atrs: Optional[float]
    status: str

    def to_dict(self) -> dict:
        return {
            "ticker":        self.ticker,
            "entry_time":    self.entry_time,
            "strategy":      self.strategy,
            "cls_5m":        self.cls_5m,
            "cls_15m":       self.cls_15m,
            "cls_30m":       self.cls_30m,
            "cls_60m":       self.cls_60m,
            "cls_90m":       self.cls_90m,
            "cls_120m":      self.cls_120m,
            "cls_240m":      self.cls_240m,
            "best_tf":       self.best_tf,
            "return_5m":     self.return_5m,
            "return_15m":    self.return_15m,
            "return_30m":    self.return_30m,
            "return_60m":    self.return_60m,
            "return_90m":    self.return_90m,
            "return_120m":   self.return_120m,
            "return_240m":   self.return_240m,
            "atr_5m_pct":    self.atr_5m_pct,
            "mfe_60m_atrs":  self.mfe_60m_atrs,
            "status":        self.status,
        }


def compute_metrics_for_signal(
    source_row: dict,
    intraday: Optional[pd.DataFrame] = None,
    intraday_lookback: Optional[pd.DataFrame] = None,
    *,
    mode: str = "historical",
) -> SignalMetrics:
    """Pure function: build a SignalMetrics from one historical_signals row.

    Args:
        source_row: dict with keys ticker, entry_time, strategy,
            entry_price, trade_type (or direction), return_5min,
            return_15min, return_30min, return_60min.
        intraday: bars from entry_time forward — used to compute the
            extended (90/120/240m) returns. Pass None to leave those
            timeframes as INSUFFICIENT_DATA.
        intraday_lookback: bars ending at entry_time — used for ATR.
            Pass None to leave atr_5m_pct as None.
        mode: 'historical' or 'rolling' — controls status field.

    No DB access. Same input → same output.
    """
    direction = (
        source_row.get("direction")
        or source_row.get("trade_type")
        or "CALL"
    )
    direction_upper = str(direction).upper()
    entry_price = float(source_row.get("entry_price") or 0.0)

    returns_by_tf: dict[int, Optional[float]] = {
        5:  _safe_float(source_row.get("return_5min")),
        15: _safe_float(source_row.get("return_15min")),
        30: _safe_float(source_row.get("return_30min")),
        60: _safe_float(source_row.get("return_60min")),
    }

    if intraday is not None:
        extended = extend_returns_from_intraday(
            intraday,
            pd.Timestamp(source_row["entry_time"]),
            entry_price,
            direction_upper,
        )
        returns_by_tf.update(extended)
    else:
        for tf in EXTENDED_TFS_MIN:
            returns_by_tf[tf] = None

    atr_pct = compute_atr_pct(intraday_lookback, entry_price) if intraday_lookback is not None else None
    r60 = returns_by_tf.get(60)
    mfe_60m_atrs = (r60 / atr_pct) if (r60 is not None and atr_pct and atr_pct > 0) else None

    return SignalMetrics(
        ticker=source_row["ticker"],
        entry_time=source_row["entry_time"],
        strategy=source_row.get("strategy", "momentum"),
        cls_5m=classify(returns_by_tf[5]),
        cls_15m=classify(returns_by_tf[15]),
        cls_30m=classify(returns_by_tf[30]),
        cls_60m=classify(returns_by_tf[60]),
        cls_90m=classify(returns_by_tf[90]),
        cls_120m=classify(returns_by_tf[120]),
        cls_240m=classify(returns_by_tf[240]),
        best_tf=best_clean_timeframe(returns_by_tf),
        return_5m=returns_by_tf[5],
        return_15m=returns_by_tf[15],
        return_30m=returns_by_tf[30],
        return_60m=returns_by_tf[60],
        return_90m=returns_by_tf[90],
        return_120m=returns_by_tf[120],
        return_240m=returns_by_tf[240],
        atr_5m_pct=atr_pct,
        mfe_60m_atrs=mfe_60m_atrs,
        status=determine_status(returns_by_tf, mode=mode),
    )


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f):
        return None
    return f


# ── DB I/O (only the CLI orchestrator calls these) ────────────────────

def fetch_source_rows(engine, start: datetime, end: datetime,
                      tickers: Optional[list[str]] = None,
                      strategies: Optional[list[str]] = None) -> pd.DataFrame:
    """Pull the historical_signals rows that need (re-)evaluation."""
    from sqlalchemy import text  # local import — not needed for unit tests

    where = ["entry_time >= :start", "entry_time < :end"]
    params: dict = {"start": start, "end": end}
    if tickers:
        where.append("ticker = ANY(:tickers)")
        params["tickers"] = [t.upper() for t in tickers]
    if strategies:
        where.append("strategy = ANY(:strategies)")
        params["strategies"] = list(strategies)

    sql = text(f"""
        SELECT ticker, entry_time, strategy, trade_type, entry_price,
               return_5min, return_15min, return_30min, return_60min
          FROM historical_signals
         WHERE {' AND '.join(where)}
         ORDER BY entry_time
    """)
    return pd.read_sql(sql, engine, params=params)


def fetch_intraday_window(engine, ticker: str, start: datetime,
                          end: datetime) -> pd.DataFrame:
    """One-min bars for [start, end). Empty DataFrame if none."""
    from gcp.historical_signals import load_intraday_bars
    return load_intraday_bars(ticker, start, end)


def check_intraday_freshness(engine, max_age_minutes: int = 60) -> None:
    """Raise SystemExit(1) if intraday is stale during market hours.

    The 4-day-stale incident on 5/1 motivated this guard — the
    throwaway analysis silently produced wrong numbers because nobody
    noticed the source data was behind. Production fails loudly.
    """
    from sqlalchemy import text

    now_utc = datetime.now(timezone.utc)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(ts) FROM market_data_intraday")).fetchone()
    max_ts = row[0] if row else None
    if max_ts is None:
        logger.error("market_data_intraday is empty — refusing to run")
        sys.exit(1)
    if max_ts.tzinfo is None:
        max_ts = max_ts.replace(tzinfo=timezone.utc)

    age = now_utc - max_ts
    if age > timedelta(minutes=max_age_minutes):
        logger.error(
            "market_data_intraday is stale: max(ts)=%s, age=%s — refusing to run",
            max_ts, age,
        )
        sys.exit(1)
    logger.info("intraday freshness OK — max(ts)=%s, age=%s", max_ts, age)


def upsert_signal_metrics(engine, rows: list[SignalMetrics]) -> int:
    """Idempotent upsert into signal_metrics. ON CONFLICT updates the row.

    Returns the count of rows written. Built one multi-row INSERT per
    chunk — same pattern as gcp/historical_signals.bulk_insert.
    """
    if not rows:
        return 0
    from sqlalchemy import text

    cols = list(rows[0].to_dict().keys())
    chunk_size = 500

    with engine.begin() as conn:
        n = 0
        for chunk_start in range(0, len(rows), chunk_size):
            chunk = rows[chunk_start: chunk_start + chunk_size]
            value_tuples: list[str] = []
            params: dict = {}
            for i, m in enumerate(chunk):
                d = m.to_dict()
                row_keys = []
                for c in cols:
                    key = f"p{i}_{c}"
                    val = d[c]
                    if isinstance(val, float) and (pd.isna(val) or val in (float("inf"), float("-inf"))):
                        val = None
                    params[key] = val
                    row_keys.append(f":{key}")
                value_tuples.append(f"({', '.join(row_keys)})")

            update_set = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in cols
                if c not in ("ticker", "entry_time", "strategy")
            )
            sql = text(
                f"INSERT INTO signal_metrics ({', '.join(cols)}) VALUES "
                + ", ".join(value_tuples)
                + " ON CONFLICT (ticker, entry_time, strategy) DO UPDATE SET "
                + update_set
                + ", evaluated_at = NOW()"
            )
            result = conn.execute(sql, params)
            n += result.rowcount or 0
    return n


# ── CLI orchestrator ──────────────────────────────────────────────────

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 0.5 signal-quality report")
    p.add_argument("--mode", choices=("historical", "rolling"), required=True)
    p.add_argument("--start", help="UTC date YYYY-MM-DD (historical mode)")
    p.add_argument("--end", help="UTC date YYYY-MM-DD (historical mode, exclusive)")
    p.add_argument("--lookback-hours", type=int, default=4,
                   help="Rolling mode: how far back to scan for fires (default 4)")
    p.add_argument("--tickers", default="",
                   help="Comma-separated ticker filter (default: all)")
    p.add_argument("--strategy", choices=("momentum", "mean_reversion", "all"),
                   default="all")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute metrics but skip the DB write")
    p.add_argument("--skip-freshness-check", action="store_true",
                   help="Skip intraday-staleness guard (for backfills)")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    if args.mode == "historical":
        if not (args.start and args.end):
            logger.error("--start and --end are required in historical mode")
            return 2
        start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.lookback_hours)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None
    strategies = None if args.strategy == "all" else [args.strategy]

    from gcp.database import get_engine
    engine = get_engine()

    if args.mode == "rolling" and not args.skip_freshness_check:
        check_intraday_freshness(engine)

    logger.info(
        "fetching source rows: %s → %s tickers=%s strategy=%s",
        start, end, tickers or "ALL", args.strategy,
    )
    src = fetch_source_rows(engine, start, end, tickers=tickers, strategies=strategies)
    logger.info("loaded %d source rows", len(src))
    if src.empty:
        logger.info("nothing to evaluate")
        return 0

    metrics: list[SignalMetrics] = []
    for _, row in src.iterrows():
        d = row.to_dict()
        ticker = d["ticker"]
        entry_t = pd.Timestamp(d["entry_time"]).to_pydatetime()
        if entry_t.tzinfo is None:
            entry_t = entry_t.replace(tzinfo=timezone.utc)
        d["entry_time"] = entry_t

        intraday = fetch_intraday_window(
            engine, ticker, entry_t, entry_t + timedelta(minutes=max(EXTENDED_TFS_MIN) + 5),
        )
        lookback = fetch_intraday_window(
            engine, ticker, entry_t - timedelta(minutes=120), entry_t,
        )
        m = compute_metrics_for_signal(
            d, intraday=intraday, intraday_lookback=lookback, mode=args.mode,
        )
        metrics.append(m)

    counts = pd.Series([m.cls_60m for m in metrics]).value_counts().to_dict()
    logger.info("60m classification distribution: %s", counts)

    if args.dry_run:
        logger.info("--dry-run set — skipping DB write (%d rows ready)", len(metrics))
        return 0

    n = upsert_signal_metrics(engine, metrics)
    logger.info("upserted %d signal_metrics rows", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
