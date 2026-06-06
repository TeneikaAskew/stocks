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
from lib.indicators import add_all_indicators, FEATURE_GROUPS  # noqa: E402

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

# Target registry. forward_return is the original regression behaviour; the
# three classification targets score each indicator against per-class
# membership (mutual_info / class_lift / one-vs-rest rank_ic).
_ALL_TARGETS = ("forward_return", "regime", "strat", "signal")
# A column-level sentinel for "regression / overall" — see schema comment on
# indicator_correlation.target_class for why this is '' (NOT NULL), not NULL.
_OVERALL_CLASS = ""
# Forward-return horizon (minutes) used to label the regime target.
_REGIME_HORIZON = 15
# Minimum classification rows to trust per-class metrics.
_MIN_CLASS_ROWS = 200
# Minimum rows for the sparse signal-outcome target before we bother.
_MIN_SIGNAL_ROWS = 30


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


def indicator_columns(df: pd.DataFrame, min_valid: int = _MIN_VALID) -> List[str]:
    """Numeric, non-degenerate indicator columns eligible for correlation.

    `min_valid` is the minimum non-null/non-constant reading count; lowered for
    the sparse signal-outcome target where there are only ~hundreds of alerts.
    """
    cols: List[str] = []
    for c in df.columns:
        if c in _NON_INDICATOR_COLS or c.startswith(_RETURN_PREFIX):
            continue
        if not np.issubdtype(df[c].dtype, np.number):
            continue
        s = df[c]
        if s.notna().sum() < min_valid or s.nunique(dropna=True) <= 1:
            continue
        cols.append(c)
    return cols


def correlate(df: pd.DataFrame, ind_cols: List[str], horizons: List[int]) -> pd.DataFrame:
    """Tidy rows: indicator, horizon_min, pearson, rank_ic, abs_rank_ic, n.

    READER WARNING — the SIGN matters. The top forward_return drivers
    (Price_vs_VWAP, Price_vs_VWAP_ATR, the ORB-percent features) come in with
    rank_ic ~ -0.25 at the 30-min horizon: that is NEGATIVE — i.e. MEAN
    REVERSION (price extended above VWAP tends to give back), not momentum. When
    promoting any forward_return indicator, carry its sign; abs_rank_ic alone
    hides whether the edge is reversion or continuation.
    """
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
                "target_name": "forward_return",
                "target_class": _OVERALL_CLASS,
                "pearson": float(pearson) if pd.notna(pearson) else None,
                "rank_ic": float(rank_ic) if pd.notna(rank_ic) else None,
                "abs_rank_ic": abs(float(rank_ic)) if pd.notna(rank_ic) else None,
                "mutual_info": None,
                "class_lift": None,
                "n": int(len(pair)),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Per-class one-vs-rest metric helpers (classification targets)
# ---------------------------------------------------------------------------

def _class_rank_ic(x: pd.Series, y_binary: np.ndarray,
                   min_pairs: int = _MIN_PAIRS) -> Optional[float]:
    """One-vs-rest Spearman correlation of indicator `x` vs binary membership.

    Pairwise-drops NaN x. Returns None when fewer than `min_pairs` valid rows,
    or when either side is constant (corr undefined — NOT 0, per Rule 3.7).
    """
    pair = pd.DataFrame({"x": x.to_numpy(dtype="float64"), "y": y_binary.astype(float)}).dropna()
    if len(pair) < min_pairs:
        return None
    if pair["x"].nunique() <= 1 or pair["y"].nunique() <= 1:
        return None
    r = pair["x"].corr(pair["y"], method="spearman")
    return float(r) if pd.notna(r) else None


def _class_mutual_info(x: pd.Series, y_binary: np.ndarray,
                       min_pairs: int = _MIN_PAIRS) -> Optional[float]:
    """Mutual information between indicator `x` and binary class membership.

    Uses sklearn's mutual_info_classif (continuous feature, discrete target).
    Returns None if sklearn is unavailable or there are too few valid rows —
    NOT 0 (a real MI of 0 and "couldn't compute" must stay distinguishable).
    """
    pair = pd.DataFrame({"x": x.to_numpy(dtype="float64"), "y": y_binary.astype(int)}).dropna()
    if len(pair) < min_pairs or pair["x"].nunique() <= 1 or pair["y"].nunique() <= 1:
        return None
    try:
        from sklearn.feature_selection import mutual_info_classif
    except ImportError:
        # sklearn absent in this environment — mutual_info column stays NULL
        # (distinguishable from a real MI of 0). A non-ImportError here would be
        # an INTERNAL bug, so we deliberately do not swallow it.
        return None
    mi = mutual_info_classif(
        pair[["x"]].to_numpy(), pair["y"].to_numpy(), random_state=42,
    )
    return float(mi[0])


def _class_lift(x: pd.Series, y_binary: np.ndarray,
                min_pairs: int = _MIN_PAIRS) -> Optional[float]:
    """Median-split class lift: P(class | x > median(x)) / base-rate.

    Splits on the indicator's own median; lift > 1 means the class is
    over-represented in the high-indicator half. Returns None on too-few
    rows, a degenerate split, or a zero base-rate (undefined ratio — NOT 0).
    """
    pair = pd.DataFrame({"x": x.to_numpy(dtype="float64"), "y": y_binary.astype(float)}).dropna()
    if len(pair) < min_pairs:
        return None
    med = pair["x"].median()
    if not np.isfinite(med):
        return None
    hi = pair["x"] > med
    if hi.sum() == 0 or (~hi).sum() == 0:
        return None  # degenerate split
    base = pair["y"].mean()
    if base <= 0:
        return None  # undefined ratio — never fabricate a 1.0
    hi_rate = pair.loc[hi, "y"].mean()
    return float(hi_rate / base)


def correlate_classes(
    df: pd.DataFrame,
    ind_cols: List[str],
    label: pd.Series,
    classes: List[str],
    target_name: str,
    *,
    min_class_rows: int = _MIN_CLASS_ROWS,
    min_pairs: int = _MIN_PAIRS,
) -> pd.DataFrame:
    """Per-(indicator × class) one-vs-rest MI / class_lift / rank_ic rows.

    `label` is a categorical Series aligned to `df`. For each class in
    `classes` we build a binary one-vs-rest membership vector and score every
    indicator. horizon_min is stamped 0 (these targets are not horizon-swept;
    the regime label already bakes in its forward horizon). pearson is left
    NULL (linear correlation against a 0/1 membership is not the headline
    statistic here; rank_ic carries the monotone signal).

    `min_class_rows` / `min_pairs` are lowered for the sparse signal target.
    """
    rows = []
    lab = pd.Series(np.asarray(label), index=df.index)
    for cls in classes:
        y = (lab == cls).to_numpy()
        n_cls = int(y.sum())
        if n_cls < min_class_rows:
            logger.info("[%s] class %s has %d rows (<%d) — skipping.",
                        target_name, cls, n_cls, min_class_rows)
            continue
        for col in ind_cols:
            x = df[col]
            rank_ic = _class_rank_ic(x, y, min_pairs=min_pairs)
            mi = _class_mutual_info(x, y, min_pairs=min_pairs)
            lift = _class_lift(x, y, min_pairs=min_pairs)
            if rank_ic is None and mi is None and lift is None:
                continue
            n_valid = int(pd.concat([x, pd.Series(y, index=df.index)], axis=1).dropna().shape[0])
            rows.append({
                "indicator": col,
                "horizon_min": 0,
                "target_name": target_name,
                "target_class": cls,
                "pearson": None,
                "rank_ic": rank_ic,
                "abs_rank_ic": abs(rank_ic) if rank_ic is not None else None,
                "mutual_info": mi,
                "class_lift": lift,
                "n": n_valid,
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
# Label builders for the classification targets (shared production helpers)
# ---------------------------------------------------------------------------

def _label_regime(enriched: pd.DataFrame, horizon: int) -> Optional[pd.Series]:
    """Per-bar regime class (BIG / UP / DOWN / FLAT) from the forward return.

    Reuses scripts.analysis.regime_combo_miner.label_regimes — the ONE regime
    label definition (CLAUDE.md Rule 3.6). Thresholds are fit on the full
    in-window sample (this is a measure-first ranking job, not an OOS model;
    train_mask = all rows). Returns a Series of {BIG,UP,DOWN,FLAT} on the rows
    with a defined forward return, else None.
    """
    ret_col = f"{_RETURN_PREFIX}{horizon}"
    if ret_col not in enriched.columns:
        return None
    sub = enriched.dropna(subset=[ret_col])
    if len(sub) < _MIN_CLASS_ROWS:
        return None
    from scripts.analysis.regime_combo_miner import label_regimes

    train_mask = np.ones(len(sub), dtype=bool)
    direction, magnitude, _, _ = label_regimes(sub, ret_col, train_mask)
    # Collapse to a single 4-way regime label: BIG dominates direction.
    regime = np.where(magnitude.to_numpy() == "BIG", "BIG", direction.to_numpy())
    return pd.Series(regime, index=sub.index)


def _label_strat_next(enriched: pd.DataFrame) -> pd.Series:
    """Next-bar Strat class (1/2U/2D/3), session-aware shift(-1).

    Uses lib.strat.StratClassifier (the production candle classifier) to label
    each bar, then leads it by one bar WITHIN each session so the label is the
    NEXT bar's type without crossing the overnight gap. Returns a Series aligned
    to `enriched`, NaN on each session's last bar (no next bar).

    READER WARNING — interpreting the strat-target rank_ic. The strongest single
    predictor of next-bar 2U/2D here is ``Close_vs_Range`` (rank_ic ~ +0.45 for
    2U / -0.45 for 2D, cross-ticker). This is the MECHANICAL next-open poke, NOT
    a directional forecast: the next bar opens at this bar's close, so a bar
    closing near its high starts just under the prior high and any uptick prints
    2U. It is non-tradeable (a 2U can nick the high by a tick and reverse) and
    does NOT convert to the "real move" direction — confirmed by the `regime`
    target's UP/DOWN classes collapsing to ~1.3x lift. Do NOT promote
    Close_vs_Range as a directional signal off the strat 2U/2D rank_ic. (To get
    one honest direction number, score against an ATR-scaled "took out the prior
    high by >= k*ATR and closed beyond it" target instead — see
    docs/STRAT_ENGINE_AND_COMBO_PIPELINE.md.)
    """
    from lib.strat import StratClassifier

    cls = StratClassifier().classify_series(enriched)  # '1'|'2U'|'2D'|'3'
    if "Date" in enriched.columns:
        grp_date = enriched["Date"]
    else:
        grp_date = pd.to_datetime(enriched["Time"]).dt.date
    nxt = cls.groupby(grp_date.values).shift(-1)
    return nxt


def compute_target_rows(
    enriched: pd.DataFrame,
    ind_cols: List[str],
    horizons: List[int],
    target: str,
) -> pd.DataFrame:
    """Dispatch one target → tidy rows (already tagged with target_name/class).

    forward_return keeps the exact original pearson + rank_ic horizon sweep.
    regime / strat build a per-bar class label and score one-vs-rest per class.
    signal is handled separately in `run` (it joins signal_alerts outcomes).
    """
    if target == "forward_return":
        return correlate(enriched, ind_cols, horizons)
    if target == "regime":
        label = _label_regime(enriched, _REGIME_HORIZON)
        if label is None:
            logger.warning("regime target: insufficient labelled rows; skipping.")
            return pd.DataFrame()
        sub = enriched.loc[label.index]
        return correlate_classes(sub, ind_cols, label, ["BIG", "UP", "DOWN", "FLAT"], "regime")
    if target == "strat":
        label = _label_strat_next(enriched)
        valid = label.notna()
        if valid.sum() < _MIN_CLASS_ROWS:
            logger.warning("strat target: %d labelled rows (<%d); skipping.",
                           int(valid.sum()), _MIN_CLASS_ROWS)
            return pd.DataFrame()
        sub = enriched.loc[valid]
        return correlate_classes(sub, ind_cols, label.loc[valid], ["1", "2U", "2D", "3"], "strat")
    raise ValueError(f"unknown target {target!r}")


def compute_signal_target(
    enriched_by_ticker: dict,
    tickers: List[str],
    start_str: str,
    end_str: str,
) -> pd.DataFrame:
    """Score indicators at signal-fire time against the win/loss outcome.

    signal_alerts stores only a sparse (rsi, rvol) snapshot, so we read the
    fire-bar indicator values from the per-ticker enriched intraday frames
    already in memory (Rule 0: no per-row SQL — one bars pull per ticker, sliced
    here) and join each alert to its fire-bar by (ticker, alert_ts). Outcome =
    exit_return_pct > 0. Binary class 'WIN'.

    Scoring is restricted to the LEAN live signal feature set
    (FEATURE_GROUPS['signal']) — the indicators the live monitor actually
    computed when it made the fire decision. We deliberately do NOT score the
    ORB / Bollinger / promoted-regime columns the enriched frame also carries:
    those were never available to the live signal logic, so attributing a win to
    them would be misleading provenance.

    Returns tidy rows (target_name='signal'); empty DataFrame (with a warning)
    when there are too few alerts — never a fabricated row (Rule 3.7).
    """
    alerts = _load_signal_outcomes(tickers, start_str, end_str)
    if alerts is None or alerts.empty:
        logger.warning("signal target: no signal_alerts with outcomes in window; skipping.")
        return pd.DataFrame()

    frames = []
    for tk in tickers:
        enr = enriched_by_ticker.get(tk)
        if enr is None or enr.empty:
            continue
        tk_alerts = alerts[alerts["ticker"] == tk]
        if tk_alerts.empty:
            continue
        # Align each alert to its intraday bar by timestamp (minute resolution).
        bars = enr.copy()
        bars_ts = pd.to_datetime(bars["Time"]).dt.tz_localize(None).dt.floor("min")
        bars = bars.assign(_ts=bars_ts.values)
        # Guard against duplicate/overlapping source bars on the same minute —
        # reindex raises InvalidIndexError on a non-unique index. Keep the last
        # bar for a given minute (matches the monitor's last-write-wins window).
        bars = bars[~bars["_ts"].duplicated(keep="last")].set_index("_ts")
        a_ts = pd.to_datetime(tk_alerts["alert_ts"]).dt.tz_localize(None).dt.floor("min")
        joined = bars.reindex(a_ts.values)
        joined = joined.assign(_win=(tk_alerts["exit_return_pct"].to_numpy() > 0).astype(int))
        frames.append(joined)

    if not frames:
        logger.warning("signal target: no alerts matched intraday bars; skipping.")
        return pd.DataFrame()

    matched = pd.concat(frames, ignore_index=True)
    n = int(matched["_win"].notna().sum())
    logger.info("signal target: %d alert rows matched to fire-bar indicators.", n)
    if n < _MIN_SIGNAL_ROWS:
        logger.warning("signal target: only %d matched rows (<%d); skipping.",
                       n, _MIN_SIGNAL_ROWS)
        return pd.DataFrame()

    # Sparse dataset: lower the valid-column and paired-observation floors to
    # the signal-row floor so the ~hundreds of alerts aren't filtered to zero.
    signal_feat = set(FEATURE_GROUPS["signal"])
    sig_ind_cols = [c for c in indicator_columns(matched, min_valid=_MIN_SIGNAL_ROWS)
                    if c != "_win" and c in signal_feat]
    label = matched["_win"].map({1: "WIN", 0: "LOSS"})
    # Single binary class — score the WIN side one-vs-rest.
    return correlate_classes(
        matched, sig_ind_cols, label, ["WIN"], "signal",
        min_class_rows=_MIN_SIGNAL_ROWS, min_pairs=_MIN_SIGNAL_ROWS,
    )


def _load_signal_outcomes(tickers, start_str, end_str):
    """Pull resolved signal_alerts (ticker, alert_ts, exit_return_pct) in window.

    Isolated for test monkeypatching. One batched query (Rule 0) — not per-row.

    The signal target is OPTIONAL and depends on an EXTERNAL resource (Cloud
    SQL) the job can't guarantee is reachable (e.g. local/CI runs with no DB
    configured). Per the INTERNAL/EXTERNAL principle in Rule 3.7: a DB-unavailable
    here is the EXTERNAL bucket — we surface it explicitly (logged reason) and
    return None so the caller SKIPS the signal target, while the INTERNAL,
    self-computable targets (forward_return / regime / strat) still run. We never
    fabricate outcome rows.
    """
    try:
        from gcp.database import get_engine
        import sqlalchemy
    except ImportError as e:  # driver/DB layer not installed (local/CI) — skip target
        logger.warning("signal target: DB layer unavailable (%s); skipping target.", e)
        return None

    q = sqlalchemy.text(
        """
        SELECT ticker, alert_ts, exit_return_pct
        FROM signal_alerts
        WHERE alert_date BETWEEN :start AND :end
          AND ticker = ANY(:tickers)
          AND exit_return_pct IS NOT NULL
        """
    )
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(q, conn, params={
                "start": start_str, "end": end_str, "tickers": list(tickers),
            })
    except sqlalchemy.exc.OperationalError as e:  # Cloud SQL unreachable — EXTERNAL
        logger.warning("signal target: signal_alerts query failed (%s); skipping target.", e)
        return None
    # Any other exception (schema drift, misconfig, programming error) is an
    # INTERNAL bug and is allowed to propagate — Rule 3.7.
    return df


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
    p.add_argument("--targets",
                   default=_env("INDICATOR_CORR_TARGETS", ",".join(_ALL_TARGETS)),
                   help="Comma-separated targets: forward_return,regime,strat,signal "
                        "(default all four).")
    p.add_argument("--target", default=None,
                   help="Single target shortcut (overrides --targets).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute + log but do not write to Cloud SQL.")
    return p.parse_args(argv)


def _resolve_targets(args: argparse.Namespace) -> List[str]:
    """Resolve the requested targets, validating against the registry."""
    raw = args.target if args.target else args.targets
    requested = [t.strip().lower() for t in raw.split(",") if t.strip()]
    unknown = [t for t in requested if t not in _ALL_TARGETS]
    if unknown:
        raise ValueError(f"unknown target(s) {unknown}; valid: {list(_ALL_TARGETS)}")
    # Preserve registry order, de-dup.
    return [t for t in _ALL_TARGETS if t in set(requested)]


# ---------------------------------------------------------------------------
# Job orchestration
# ---------------------------------------------------------------------------

def run(
    tickers: List[str],
    horizons: List[int],
    lookback_days: int,
    as_of: date,
    dry_run: bool,
    targets: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Compute the correlation table for all tickers + a POOLED row set.

    `targets` selects which scoring targets to compute (default: all four —
    forward_return, regime, strat, signal). Each ticker's bars are pulled ONCE
    (Rule 0) and enriched once; every target is scored against that single
    enriched frame. Per-ticker rows are written for each target; the
    forward_return target additionally writes a POOLED cross-sectional row set.

    Returns the tidy results DataFrame (also the value persisted). Reading and
    writing are injected via module-level functions so tests can monkeypatch
    them without a live database.
    """
    from lib.data_loader import DataLoader

    if targets is None:
        targets = list(_ALL_TARGETS)

    cfg = IndicatorConfig()
    loader = DataLoader(data_dir=_env("DATA_DIR", "data"))

    start = as_of - timedelta(days=lookback_days)
    start_str, end_str = start.isoformat(), as_of.isoformat()
    logger.info("Window %s → %s | tickers=%s | horizons=%s | targets=%s",
                start_str, end_str, tickers, horizons, targets)

    per_ticker_results: List[pd.DataFrame] = []
    pooled_frames: List[pd.DataFrame] = []
    enriched_by_ticker: dict = {}
    loaded = 0

    # Classification targets computed per-ticker against the enriched frame.
    class_targets = [t for t in targets if t in ("regime", "strat")]
    do_forward = "forward_return" in targets

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
        # Only the signal target consumes the retained per-ticker frames; don't
        # accumulate them (~10s of MB/ticker) when signal isn't requested.
        if "signal" in targets:
            enriched_by_ticker[tk] = enriched
        ind_cols = indicator_columns(enriched)
        sessions = enriched["Date"].nunique() if "Date" in enriched else 0
        logger.info("[%s] %d RTH bars, %d sessions, %d indicator columns",
                    tk, len(enriched), sessions, len(ind_cols))

        if do_forward:
            tidy = correlate(enriched, ind_cols, horizons)
            if not tidy.empty:
                tidy.insert(0, "ticker", tk)
                per_ticker_results.append(tidy)
            keep = ind_cols + [f"{_RETURN_PREFIX}{h}" for h in horizons]
            pooled_frames.append(enriched[keep])

        for tgt in class_targets:
            ct = compute_target_rows(enriched, ind_cols, horizons, tgt)
            if not ct.empty:
                ct.insert(0, "ticker", tk)
                per_ticker_results.append(ct)

    if loaded == 0:
        # All tickers empty → this is NOT a clean no-op; it almost certainly
        # signals a connection / staleness problem. Fail loud (Rule 3.7).
        raise RuntimeError(
            f"No intraday data for ANY of {tickers} in window {start_str}..{end_str}. "
            "Refusing to write an empty/misleading result set."
        )

    # Signal target — joins signal_alerts outcomes to the in-memory bars.
    if "signal" in targets:
        sig_rows = compute_signal_target(enriched_by_ticker, tickers, start_str, end_str)
        if not sig_rows.empty:
            sig_rows.insert(0, "ticker", "POOLED")
            per_ticker_results.append(sig_rows)

    if not per_ticker_results:
        raise RuntimeError(
            f"No result rows computed for targets={targets} in window "
            f"{start_str}..{end_str}. Refusing to write an empty result set."
        )

    results = pd.concat(per_ticker_results, ignore_index=True)

    # POOLED ranking across the common indicator set (forward_return only).
    if do_forward and len(pooled_frames) > 1:
        common = set.intersection(*[set(indicator_columns(f)) for f in pooled_frames])
        if common:
            pooled = pd.concat(pooled_frames, ignore_index=True)
            pooled_tidy = correlate(pooled, sorted(common), horizons)
            if not pooled_tidy.empty:
                pooled_tidy.insert(0, "ticker", "POOLED")
                results = pd.concat([results, pooled_tidy], ignore_index=True)

    # Stamp window metadata for the upsert key + provenance.
    results["computed_date"] = as_of
    results["window_start"] = start
    results["window_end"] = as_of
    results["lookback_days"] = lookback_days

    logger.info("Computed %d result rows across targets %s.", len(results), targets)
    for tname, cnt in results.groupby("target_name").size().items():
        logger.info("  target=%s rows=%d", tname, cnt)

    # Headline log: pooled forward_return top drivers at the mid horizon.
    if do_forward:
        mid = horizons[len(horizons) // 2]
        pooled_mid = results[
            (results.ticker == "POOLED")
            & (results.target_name == "forward_return")
            & (results.horizon_min == mid)
        ]
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
                "indicator", "horizon_min", "target_name", "target_class"]
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
        targets = _resolve_targets(args)
    except ValueError as e:
        logger.error("%s", e)
        return 1
    if not targets:
        logger.error("No targets resolved; nothing to do.")
        return 1

    try:
        run(tickers, horizons, args.lookback_days, as_of, args.dry_run, targets=targets)
    except Exception as e:  # noqa: BLE001 — top-level boundary: log + non-zero exit
        logger.error("indicator_correlation_job failed: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
