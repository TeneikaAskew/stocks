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
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

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

    `intraday_lookback` must have High, Low, and a close-price column at
    least `period + 1` bars long ending at (or just before) the signal
    time. Accepts either `Close` (MarketAnalyzer-enriched DataFrames)
    or `Last` (the column shape produced by `load_intraday_bars` —
    MarketAnalyzer's convention is to alias close as `Last`).

    Returns None if not enough bars are available or the close column
    is missing entirely.
    """
    if intraday_lookback is None or len(intraday_lookback) < period + 1 or entry_price <= 0:
        return None
    close = intraday_lookback["Close"] if "Close" in intraday_lookback.columns \
            else intraday_lookback.get("Last")
    if close is None:
        return None
    atr_series = calculate_atr(
        intraday_lookback["High"],
        intraday_lookback["Low"],
        close,
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
    p.add_argument("--start", help="UTC date YYYY-MM-DD (historical mode, with --end)")
    p.add_argument("--end", help="UTC date YYYY-MM-DD (historical mode, exclusive)")
    p.add_argument("--lookback-days", type=int, default=None,
                   help="Historical mode: process the last N days "
                        "(alternative to --start/--end). Used by the "
                        "nightly scheduler to promote pending → final "
                        "without computing explicit dates.")
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


def _resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Translate CLI args into a [start, end) UTC window.

    Three valid invocations:
      * --mode=rolling                   → end=now, start=now - lookback_hours
      * --mode=historical --lookback-days N → end=now, start=now - N days
      * --mode=historical --start X --end Y  → explicit window

    Raises ValueError on missing/conflicting args so the caller can
    return a non-zero exit code with a clear log line.
    """
    if args.mode == "rolling":
        end = datetime.now(timezone.utc)
        return end - timedelta(hours=args.lookback_hours), end

    # historical mode
    if args.lookback_days is not None:
        end = datetime.now(timezone.utc)
        return end - timedelta(days=args.lookback_days), end
    if args.start and args.end:
        start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        return start, end
    raise ValueError(
        "historical mode requires either --lookback-days N or --start/--end"
    )


def _slice_intraday(
    full_df: pd.DataFrame, entry_t: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cut the per-ticker intraday DataFrame into (forward, lookback) for
    one signal. Pure function — no DB.

    `forward` covers [entry_t, entry_t + max_extended_tf + 5min] for the
    extended-timeframe MFE computation; `lookback` covers
    [entry_t - 120min, entry_t) for the ATR context.
    """
    forward_end = entry_t + timedelta(minutes=max(EXTENDED_TFS_MIN) + 5)
    lookback_start = entry_t - timedelta(minutes=120)
    forward = full_df[(full_df["Time"] >= entry_t) & (full_df["Time"] <= forward_end)]
    lookback = full_df[(full_df["Time"] >= lookback_start) & (full_df["Time"] < entry_t)]
    return forward, lookback


def _normalize_entry_time(raw) -> datetime:
    """Coerce a source-row entry_time into a timezone-aware UTC datetime."""
    entry_t = pd.Timestamp(raw).to_pydatetime()
    if entry_t.tzinfo is None:
        entry_t = entry_t.replace(tzinfo=timezone.utc)
    return entry_t


def process_ticker_batch(
    engine, ticker: str, group: pd.DataFrame, *, mode: str,
    dry_run: bool = False,
) -> tuple[int, int, dict[str, int]]:
    """Process all signals for one ticker with ONE intraday query.

    This is the production-grade hot loop. The naive "two queries per
    signal" shape did 6000+ round-trips on a monthly backfill and
    timed out at 1 hour. The batched shape pulls one DataFrame
    covering the full per-ticker window, slices it in memory per
    signal, and upserts the resulting `SignalMetrics` rows in one
    chunked insert. Cloud Run round-trips drop from O(signals) to
    O(tickers).

    Memory: SPY's full month of 1-min bars is ~12k rows × ~50 bytes
    ≈ 600 KB; even a year is <10 MB per ticker. Per-ticker upsert
    keeps the metrics-list memory bounded too — we don't accumulate
    every ticker's results before any DB write.

    Returns (signals_processed, signals_upserted, classification_counts).
    """
    if group.empty:
        return (0, 0, {})

    earliest_entry = pd.Timestamp(group["entry_time"].min())
    latest_entry = pd.Timestamp(group["entry_time"].max())
    if earliest_entry.tzinfo is None:
        earliest_entry = earliest_entry.tz_localize(timezone.utc)
    if latest_entry.tzinfo is None:
        latest_entry = latest_entry.tz_localize(timezone.utc)

    fetch_start = earliest_entry - timedelta(minutes=120)
    fetch_end = latest_entry + timedelta(minutes=max(EXTENDED_TFS_MIN) + 5)

    logger.info(
        "ticker=%s signals=%d fetching intraday [%s, %s)",
        ticker, len(group), fetch_start, fetch_end,
    )
    full_df = fetch_intraday_window(engine, ticker, fetch_start, fetch_end)
    if full_df.empty:
        logger.warning(
            "ticker=%s no intraday bars in [%s, %s) — skipping %d signals",
            ticker, fetch_start, fetch_end, len(group),
        )
        return (len(group), 0, {})

    metrics: list[SignalMetrics] = []
    for _, row in group.iterrows():
        d = row.to_dict()
        d["entry_time"] = _normalize_entry_time(d["entry_time"])
        forward, lookback = _slice_intraday(full_df, pd.Timestamp(d["entry_time"]))
        m = compute_metrics_for_signal(
            d, intraday=forward, intraday_lookback=lookback, mode=mode,
        )
        metrics.append(m)

    counts = pd.Series([m.cls_60m for m in metrics]).value_counts().to_dict()
    if dry_run:
        logger.info(
            "ticker=%s --dry-run: %d rows ready, classifications=%s",
            ticker, len(metrics), counts,
        )
        return (len(metrics), 0, counts)

    n = upsert_signal_metrics(engine, metrics)
    logger.info(
        "ticker=%s upserted=%d/%d classifications=%s",
        ticker, n, len(metrics), counts,
    )
    return (len(metrics), n, counts)


def build_quality_report_embed(
    start: datetime, end: datetime, mode: str,
    processed: int, upserted: int, counts: dict,
) -> dict:
    """Build the Discord summary embed for a quality-report run.

    Pure function — no I/O, testable in isolation (per this module's
    hermetic-testable contract). `counts` is keyed by the labels from
    classify(): CLEAN_HIT / MIXED / NOISE / WRONG_DIRECTION /
    INSUFFICIENT_DATA.
    """
    clean = counts.get('CLEAN_HIT', 0)
    mixed = counts.get('MIXED', 0)
    noise = counts.get('NOISE', 0)
    wrong = counts.get('WRONG_DIRECTION', 0)
    insufficient = counts.get('INSUFFICIENT_DATA', 0)
    # Clean rate is measured only over signals whose window has closed.
    decided = clean + mixed + noise + wrong
    clean_rate = (clean / decided * 100.0) if decided else 0.0

    lines = [
        f"🟢 Clean hit: **{clean}**",
        f"🟡 Mixed: **{mixed}**",
        f"⚪ Noise: **{noise}**",
        f"🔴 Wrong direction: **{wrong}**",
    ]
    if insufficient:
        lines.append(f"⏳ Insufficient data: **{insufficient}** (window not closed)")

    return {
        'title': 'Signal Quality Report',
        'description': (
            f"Window **{start:%Y-%m-%d} → {end:%Y-%m-%d}** · mode `{mode}`\n"
            f"Processed **{processed}** signals · {upserted} upserted to "
            f"`signal_metrics`\n"
            f"Clean rate **{clean_rate:.1f}%** ({clean}/{decided} decided)\n\n"
            + '\n'.join(lines)
        ),
        'color': (0x2ecc71 if clean_rate >= 50
                  else 0xf1c40f if clean_rate >= 30 else 0xe74c3c),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    try:
        start, end = _resolve_window(args)
    except ValueError as e:
        logger.error("invalid CLI args: %s", e)
        return 2

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
    logger.info("loaded %d source rows across %d tickers",
                len(src), src["ticker"].nunique() if not src.empty else 0)
    if src.empty:
        logger.info("nothing to evaluate")
        return 0

    # Per-ticker batched processing — bounded memory, observable
    # progress, ONE intraday query per ticker (not per signal).
    total_processed = 0
    total_upserted = 0
    aggregate_counts: dict[str, int] = {}
    for ticker, group in src.groupby("ticker", sort=False):
        processed, upserted, counts = process_ticker_batch(
            engine, str(ticker), group, mode=args.mode, dry_run=args.dry_run,
        )
        total_processed += processed
        total_upserted += upserted
        for k, v in counts.items():
            aggregate_counts[k] = aggregate_counts.get(k, 0) + v

    logger.info(
        "DONE processed=%d upserted=%d classifications=%s",
        total_processed, total_upserted, aggregate_counts,
    )

    # Post a single summary embed to the dedicated signals channel
    # (falls back to the main webhook). Skipped on dry-run.
    webhook = (os.environ.get("DISCORD_WEBHOOK_SIGNALS_URL")
               or os.environ.get("DISCORD_WEBHOOK_URL"))
    if webhook and not args.dry_run:
        embed = build_quality_report_embed(
            start, end, args.mode,
            total_processed, total_upserted, aggregate_counts,
        )
        try:
            requests.post(webhook, json={'embeds': [embed]}, timeout=10)
            logger.info("quality report summary posted to Discord")
        except Exception as e:
            logger.warning("quality report Discord post failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
