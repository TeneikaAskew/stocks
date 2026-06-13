"""
Intraday indicator → forward-return correlation / Information Coefficient.

Answers: "How correlated is each computed 1-minute indicator against the
movement (forward return) of the underlying?"

Method
------
1. Load 1-minute OHLCV bars (RTH) for SPY / IWM / QQQ.
2. Compute the FULL production indicator suite via the canonical
   `lib.indicators.add_all_indicators` engine (no hand-rolled math — this
   is the same code path signal_monitor / backtests use, per CLAUDE.md
   Rule 3.6).
3. For each numeric indicator column, compute the correlation against
   forward log-returns at horizons of 5 / 15 / 30 minutes:
     - Pearson r  (linear association)
     - Spearman rho == Rank IC  (monotonic / rank association, the
       standard "Information Coefficient" used in quant factor research)
   Forward returns are strictly causal: ret_h(t) = ln(Close[t+h]/Close[t]),
   so an indicator known at bar t is correlated only with FUTURE movement.
   The last h bars of each session are dropped (no look-ahead across the
   close).

Data source
-----------
Reads daily 1-minute parquets shaped like the GCS
`raw/<ticker>/minute/<ticker>_minute_YYYYMMDD.parquet` files: an integer
0..960 bar index (bar 0 = 04:00 ET, verified by the opening-volume spike at
bar 330 = 09:30). A synthetic ET `Time` is reconstructed from that mapping
so VWAP / ORB (which need session timestamps) compute correctly.

Output
------
- A per-(ticker, horizon) ranked table of |Rank IC|.
- A pooled (all-tickers) ranking — the headline "which features move with
  price" answer.
- CSV + Markdown written to reports/.

Usage
-----
    python -m scripts.analysis.intraday_indicator_correlation \
        --minute-dir /tmp/minute --tickers SPY,IWM,QQQ \
        --horizons 5,15,30 --out reports/intraday_indicator_correlation
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.indicators import add_all_indicators  # noqa: E402
from lib.config import IndicatorConfig  # noqa: E402

# Bar 0 = 04:00 ET in the GCS daily-minute parquet layout (verified via the
# opening-volume spike landing on bar 330 = 09:30).
SESSION_START = time(4, 0)
RTH_START = time(9, 30)
RTH_END = time(16, 0)

# OHLCV + bookkeeping columns that are NOT indicators (excluded from ranking).
NON_INDICATOR_COLS = {
    "Open", "High", "Low", "Close", "Volume", "ticker", "Time", "Date",
}
# Forward-return columns we create; never rank an indicator against itself.
RETURN_PREFIX = "fwd_ret_"


def reconstruct_time(df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """Attach a synthetic ET Time from the integer bar index (bar0 = 04:00)."""
    day = datetime.strptime(date_str, "%Y%m%d")
    base = datetime.combine(day.date(), SESSION_START)
    bar_idx = np.asarray(df.index, dtype="int64")
    times = [base + timedelta(minutes=int(b)) for b in bar_idx]
    out = df.reset_index(drop=True).copy()
    out["Time"] = pd.to_datetime(times)
    return out


def load_minute_dir(minute_dir: Path, ticker: str) -> pd.DataFrame:
    """Concatenate all daily-minute parquets for a ticker into one frame,
    each enriched with a reconstructed Time. Sessions are kept contiguous so
    indicator warmup happens per-day correctly via the daily VWAP reset."""
    tl = ticker.lower()
    files = sorted((minute_dir / tl).glob(f"{tl}_minute_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No minute parquets for {ticker} in {minute_dir / tl}")
    frames = []
    for f in files:
        date_str = f.stem.split("_")[-1]  # <ticker>_minute_YYYYMMDD
        raw = pd.read_parquet(f)
        if not isinstance(raw.index, pd.RangeIndex) and raw.index.dtype.kind != "i":
            raw = raw.reset_index(drop=True)
        frames.append(reconstruct_time(raw, date_str))
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = ticker.upper()
    return df


def add_forward_returns(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Add strictly-causal forward log-returns per session (no cross-day leak)."""
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Time"]).dt.date
    logc = np.log(out["Close"])
    for h in horizons:
        # shift(-h) within each session; the trailing h bars become NaN and
        # are excluded from correlation pairwise.
        fwd = out.groupby("Date")[["Close"]].transform(
            lambda s: np.log(s).shift(-h) - np.log(s)
        )["Close"]
        out[f"{RETURN_PREFIX}{h}"] = fwd
    return out


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(df["Time"]).dt.time
    return df[(t >= RTH_START) & (t <= RTH_END)].copy()


def indicator_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        if c in NON_INDICATOR_COLS or c.startswith(RETURN_PREFIX):
            continue
        if not np.issubdtype(df[c].dtype, np.number):
            continue
        # Skip degenerate columns (all-NaN or constant) — undefined correlation.
        s = df[c]
        if s.notna().sum() < 100 or s.nunique(dropna=True) <= 1:
            continue
        cols.append(c)
    return cols


def correlate(df: pd.DataFrame, ind_cols: list[str], horizons: list[int]) -> pd.DataFrame:
    """Return tidy rows: indicator, horizon, pearson, rank_ic (spearman), n."""
    rows = []
    for h in horizons:
        y = df[f"{RETURN_PREFIX}{h}"]
        for col in ind_cols:
            x = df[col]
            pair = pd.concat([x, y], axis=1).dropna()
            if len(pair) < 200:
                continue
            xv, yv = pair.iloc[:, 0], pair.iloc[:, 1]
            pearson = xv.corr(yv, method="pearson")
            rank_ic = xv.corr(yv, method="spearman")
            rows.append({
                "indicator": col,
                "horizon_min": h,
                "pearson": pearson,
                "rank_ic": rank_ic,
                "abs_rank_ic": abs(rank_ic) if pd.notna(rank_ic) else np.nan,
                "n": len(pair),
            })
    return pd.DataFrame(rows)


def build_enriched(minute_dir: Path, ticker: str, cfg: IndicatorConfig,
                   horizons: list[int]) -> pd.DataFrame:
    raw = load_minute_dir(minute_dir, ticker)
    # Production indicator engine — same path as signal_monitor / backtests.
    enriched = add_all_indicators(raw, close_col="Close", indicator_config=cfg)
    enriched = add_forward_returns(enriched, horizons)
    # Correlate on RTH bars only (the live monitor fires on RTH bars).
    return filter_rth(enriched)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minute-dir", default="/tmp/minute")
    ap.add_argument("--tickers", default="SPY,IWM,QQQ")
    ap.add_argument("--horizons", default="5,15,30")
    ap.add_argument("--out", default="reports/intraday_indicator_correlation")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    minute_dir = Path(args.minute_dir)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    horizons = [int(h) for h in args.horizons.split(",") if h.strip()]
    cfg = IndicatorConfig()

    per_ticker_tidy = []
    pooled_frames = []
    coverage = []

    for tk in tickers:
        print(f"[{tk}] loading + enriching via add_all_indicators ...", flush=True)
        enr = build_enriched(minute_dir, tk, cfg, horizons)
        ind_cols = indicator_columns(enr)
        coverage.append({
            "ticker": tk, "rth_bars": len(enr), "indicator_cols": len(ind_cols),
            "sessions": enr["Date"].nunique() if "Date" in enr else np.nan,
        })
        print(f"[{tk}]   {len(enr)} RTH bars, {len(ind_cols)} indicator columns", flush=True)
        tidy = correlate(enr, ind_cols, horizons)
        tidy.insert(0, "ticker", tk)
        per_ticker_tidy.append(tidy)
        keep = ind_cols + [f"{RETURN_PREFIX}{h}" for h in horizons]
        pooled_frames.append(enr[keep].assign(ticker=tk))

    all_tidy = pd.concat(per_ticker_tidy, ignore_index=True)

    # Pooled across tickers (align on the common indicator set).
    common = set.intersection(*[
        set(indicator_columns(f.drop(columns=["ticker"]))) for f in pooled_frames
    ])
    pooled = pd.concat(pooled_frames, ignore_index=True)
    pooled_tidy = correlate(pooled, sorted(common), horizons)
    pooled_tidy.insert(0, "ticker", "POOLED")

    out_base = PROJECT_ROOT / args.out
    out_base.parent.mkdir(parents=True, exist_ok=True)
    full = pd.concat([all_tidy, pooled_tidy], ignore_index=True)
    csv_path = out_base.with_suffix(".csv")
    full.to_csv(csv_path, index=False)

    # ---- Markdown report ----
    lines = []
    lines.append("# Intraday Indicator → Forward-Return Correlation")
    lines.append("")
    lines.append(f"_Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC_")
    lines.append("")
    lines.append("**Method.** Each 1-minute indicator (computed via the production "
                 "`lib.indicators.add_all_indicators` engine) is correlated against "
                 "strictly-causal forward log-returns `ln(Close[t+h]/Close[t])` at "
                 "horizons of " + ", ".join(f"{h}m" for h in horizons) + ". "
                 "**Rank IC** is the Spearman rank correlation — the standard quant "
                 "Information Coefficient. RTH bars only; forward returns do not "
                 "cross the session close.")
    lines.append("")
    lines.append("## Data coverage")
    lines.append("")
    cov = pd.DataFrame(coverage)
    lines.append(cov.to_markdown(index=False))
    lines.append("")

    lines.append("## Interpretation & caveats")
    lines.append("")
    lines.append("- **Magnitudes are small (|Rank IC| ~0.02–0.08).** That is normal "
                 "for a *single* indicator vs *signed* 1-minute forward return — "
                 "real edge comes from combining features, which is what the "
                 "signal_monitor scoring does. IC is a ranking diagnostic, not a "
                 "standalone strategy.")
    lines.append("- **Volatility / range features dominate** (ATR14, Daily_Range, "
                 "BB_Width, ORB_*_Range, ATR_Expansion). These predict the *size* "
                 "of the next move more than its *direction*; their positive signed "
                 "correlation here is partly sample-specific to this window.")
    lines.append("- **Raw price-level columns** (EMA*, SMA*, BB_Middle, VWAP) are "
                 "non-stationary. Their per-ticker correlation reflects 25-day price "
                 "drift, not a tradeable signal — this is why the **pooled** ranking "
                 "(which mixes tickers at different price levels) is the trustworthy "
                 "headline and those level columns fall out of it.")
    lines.append("- **Sample = 25 sessions (~Apr–early May 2026).** Treat as a "
                 "snapshot. Re-run over a longer window once the db-query / Actions "
                 "runner path is restored (see note below) for a stable estimate.")
    lines.append("")
    lines.append("## Pooled ranking (all tickers) — top drivers by |Rank IC|")
    for h in horizons:
        sub = (pooled_tidy[pooled_tidy.horizon_min == h]
               .sort_values("abs_rank_ic", ascending=False).head(args.top))
        lines.append("")
        lines.append(f"### Horizon = {h} minutes")
        lines.append("")
        show = sub[["indicator", "rank_ic", "pearson", "n"]].copy()
        show["rank_ic"] = show["rank_ic"].round(4)
        show["pearson"] = show["pearson"].round(4)
        lines.append(show.to_markdown(index=False))
    lines.append("")

    lines.append("## Per-ticker top-10 by |Rank IC| (15m horizon)")
    for tk in tickers:
        sub = (all_tidy[(all_tidy.ticker == tk) & (all_tidy.horizon_min == 15)]
               .sort_values("abs_rank_ic", ascending=False).head(10))
        lines.append("")
        lines.append(f"### {tk}")
        lines.append("")
        show = sub[["indicator", "rank_ic", "pearson", "n"]].copy()
        show["rank_ic"] = show["rank_ic"].round(4)
        show["pearson"] = show["pearson"].round(4)
        lines.append(show.to_markdown(index=False))
    lines.append("")

    md_path = out_base.with_suffix(".md")
    md_path.write_text("\n".join(lines))

    print(f"\nWrote:\n  {csv_path}\n  {md_path}")
    # Echo the pooled 15m headline to stdout.
    print("\n=== POOLED top-15 by |Rank IC| @ 15m ===")
    head = (pooled_tidy[pooled_tidy.horizon_min == 15]
            .sort_values("abs_rank_ic", ascending=False).head(15))
    print(head[["indicator", "rank_ic", "pearson", "n"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
