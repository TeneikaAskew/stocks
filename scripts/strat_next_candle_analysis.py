#!/usr/bin/env python3
"""What predicts the NEXT daily Strat candle? — three views, run vs Cloud SQL.

PART A — FTFC-CONDITIONED transition: P(next candle | current candle, higher-TF
  alignment). Does continuation jump when the (completed) weekly + monthly bars
  agree with the daily direction? (causal — only prior-completed higher-TF bars.)

PART B — MODEL vs BASE RATE: a daily next_bar_type LightGBM (same method as the
  validated intraday STRAT-TYPE model, applied to daily), walk-forward; accuracy
  & log-loss vs the base rate (majority class / train prior). Answers "does a
  model beat just reading the current candle?"

PART C — FEATURE CORRELATION: mutual information of each daily feature with the
  next candle + each feature's lean toward next-up vs next-down. Answers "is
  anything correlated to the next candle?"

    python -m scripts.strat_next_candle_analysis --tickers SPY,QQQ,IWM --days 2000
"""
from __future__ import annotations
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from lib.strat import StratClassifier

CANDLES = ["2U", "2D", "1", "3"]


def _candle_dir(series: pd.Series) -> pd.Series:
    return series.map({"2U": 1, "2D": -1}).fillna(0)


def build_daily(ticker: str, days: int):
    """Daily OHLCV + Strat labels + causal feature matrix + next_bar_type."""
    df = DataLoader().load_daily(ticker)
    if df is None or len(df) < 260:
        return None
    df = df.tail(days + 5).copy()
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    clf = StratClassifier()
    labels = clf.classify_series(df)
    df["candle"] = labels.values
    df["next_candle"] = df["candle"].shift(-1)

    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df.get("Volume", pd.Series(index=df.index, dtype=float))
    prev_c = c.shift(1)
    f = pd.DataFrame(index=df.index)
    # momentum / returns (all known at bar t close)
    for n in (1, 2, 3, 5, 10):
        f[f"ret_{n}d"] = c.pct_change(n)
    # RSI(14)
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    f["rsi_14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # ATR(14) %
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    f["atr_pct"] = tr.rolling(14).mean() / c
    # EMA distances
    for n in (20, 50, 200):
        f[f"ema{n}_dist"] = (c - c.ewm(span=n, adjust=False).mean()) / c
    # MACD histogram
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    f["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    # Bollinger %b (20)
    m20, s20 = c.rolling(20).mean(), c.rolling(20).std()
    f["bb_pctb"] = (c - (m20 - 2 * s20)) / ((m20 + 2 * s20) - (m20 - 2 * s20))
    # volume z, gap, range, close-location-value
    f["vol_z"] = (v - v.rolling(20).mean()) / v.rolling(20).std()
    f["gap_pct"] = (o - prev_c) / prev_c
    f["range_pct"] = (h - l) / c
    f["clv"] = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    # streaks
    up_day = (c > prev_c).astype(int)
    f["consec_up"] = up_day * (up_day.groupby((up_day != up_day.shift()).cumsum()).cumcount() + 1)
    dn_day = (c < prev_c).astype(int)
    f["consec_dn"] = dn_day * (dn_day.groupby((dn_day != dn_day.shift()).cumsum()).cumcount() + 1)
    # current-candle one-hots (is the candle itself the signal?)
    for cc in CANDLES:
        f[f"cand_{cc}"] = (df["candle"] == cc).astype(int)
    f["dow"] = df.index.dayofweek
    # FTFC: prior-completed weekly + monthly direction (causal)
    f["ftfc"] = _ftfc_per_bar(df)
    # market_data_daily may already carry some indicator columns; let our freshly
    # computed features win and avoid duplicate-named columns (→ 2-D selection).
    df = df.drop(columns=[c for c in f.columns if c in df.columns])
    df = pd.concat([df, f], axis=1)
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _ftfc_per_bar(df: pd.DataFrame) -> pd.Series:
    """Sum of prior-COMPLETED weekly + monthly candle direction, per daily bar.
    Strictly-before merge_asof → no lookahead from an in-progress higher bar."""
    loader = DataLoader()
    clf = StratClassifier()
    out = pd.Series(0.0, index=df.index)
    ohlcv = df[["Open", "High", "Low", "Close"]].copy()
    ohlcv["Volume"] = df["Volume"] if "Volume" in df.columns else 0.0
    for tf in ("1w", "1mo"):
        try:
            agg = loader.aggregate_to_timeframe(ohlcv, tf)
            agg = agg.dropna(subset=["High", "Low"])
            d = _candle_dir(clf.classify_series(agg))
            right = pd.DataFrame({"htf_date": agg.index, "dir": d.values}).sort_values("htf_date")
            left = pd.DataFrame({"date": df.index}).sort_values("date")
            merged = pd.merge_asof(left, right, left_on="date", right_on="htf_date",
                                   direction="backward", allow_exact_matches=False)
            out = out + pd.Series(merged["dir"].fillna(0).values, index=df.index)
        except Exception:
            continue
    return out


def part_a_ftfc(df: pd.DataFrame) -> None:
    print("  PART A — transition conditioned on FTFC (weekly+monthly) alignment:")
    sub = df.dropna(subset=["next_candle"])
    for cur in ("2U", "2D"):
        block = sub[sub["candle"] == cur]
        cont = cur  # continuation candle = same direction
        print(f"    after {cur}:")
        for name, mask in (("FTFC aligned-up (>0)", block["ftfc"] > 0),
                           ("FTFC mixed (=0)", block["ftfc"] == 0),
                           ("FTFC aligned-down (<0)", block["ftfc"] < 0)):
            g = block[mask]
            if len(g) < 15:
                print(f"      {name:<24} n={len(g):<4} (thin)")
                continue
            cont_rate = (g["next_candle"] == cont).mean()
            rev = "2D" if cur == "2U" else "2U"
            rev_rate = (g["next_candle"] == rev).mean()
            print(f"      {name:<24} n={len(g):<4} continuation {100*cont_rate:.0f}% | "
                  f"reversal {100*rev_rate:.0f}%")


def part_c_correlation(df: pd.DataFrame, feat_cols: list) -> None:
    from sklearn.feature_selection import mutual_info_classif
    sub = df.dropna(subset=["next_candle"]).copy()
    X = sub[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    y = sub["next_candle"].values
    mi = mutual_info_classif(X, y, random_state=42)
    order = np.argsort(mi)[::-1]
    nxt_up = (sub["next_candle"] == "2U").astype(int).values
    nxt_dn = (sub["next_candle"] == "2D").astype(int).values
    print("  PART C — feature → next-candle (mutual info; + lean toward next-up/down):")
    print(f"    {'feature':<14}{'MI':>8}{'corr→2U':>9}{'corr→2D':>9}")
    for i in order[:12]:
        col = sub[feat_cols[i]].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        cu = np.corrcoef(col, nxt_up)[0, 1] if col.std() > 0 else 0.0
        cd = np.corrcoef(col, nxt_dn)[0, 1] if col.std() > 0 else 0.0
        print(f"    {feat_cols[i]:<14}{mi[i]:>8.4f}{cu:>9.3f}{cd:>9.3f}")


def part_b_model(df: pd.DataFrame, feat_cols: list) -> None:
    import lightgbm as lgb
    from sklearn.metrics import log_loss
    sub = df.dropna(subset=["next_candle"]).copy()
    sub = sub[sub["candle"] != "X"]
    y_idx = sub["next_candle"].map({c: i for i, c in enumerate(CANDLES)})
    sub = sub[y_idx.notna()]
    y = y_idx[y_idx.notna()].astype(int).values
    X = sub[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    years = pd.DatetimeIndex(sub.index).year
    cuts = [y_ for y_ in (2024, 2025, 2026) if (years >= y_).any() and (years < y_).sum() > 200]
    print("  PART B — daily next-candle MODEL vs base rate (walk-forward):")
    print(f"    {'test':<8}{'n':>5}{'model_acc':>11}{'base_acc':>10}{'Δacc':>7}"
          f"{'model_LL':>10}{'base_LL':>9}{'beat':>8}")
    for cut in cuts:
        tr, te = years < cut, years == cut
        if te.sum() < 60 or tr.sum() < 250:
            continue
        m = lgb.LGBMClassifier(objective="multiclass", num_class=4, n_estimators=300,
                               learning_rate=0.05, max_depth=6, num_leaves=31,
                               min_child_samples=50, random_state=42, verbose=-1)
        m.fit(X[tr], y[tr])
        proba = m.predict_proba(X[te])
        pred = proba.argmax(1)
        acc = (pred == y[te]).mean()
        # base: predict train-majority class; base logloss = train class prior
        prior = np.bincount(y[tr], minlength=4) / tr.sum()
        base_acc = max(prior)  # majority-class accuracy ≈ prior of top class
        base_acc = (y[te] == prior.argmax()).mean()
        ll = log_loss(y[te], proba, labels=[0, 1, 2, 3])
        base_ll = log_loss(y[te], np.tile(prior, (te.sum(), 1)), labels=[0, 1, 2, 3])
        print(f"    {cut:<8}{int(te.sum()):>5}{100*acc:>10.1f}%{100*base_acc:>9.1f}%"
              f"{100*(acc-base_acc):>+6.1f}{ll:>10.3f}{base_ll:>9.3f}{base_ll-ll:>+8.3f}")


def analyze(ticker: str, days: int) -> None:
    print("=" * 80)
    df = build_daily(ticker, days)
    if df is None:
        print(f"{ticker:6} — UNAVAILABLE (insufficient daily bars)"); return
    feat_cols = [c for c in df.columns if c in {
        "ret_1d", "ret_2d", "ret_3d", "ret_5d", "ret_10d", "rsi_14", "atr_pct",
        "ema20_dist", "ema50_dist", "ema200_dist", "macd_hist", "bb_pctb",
        "vol_z", "gap_pct", "range_pct", "clv", "consec_up", "consec_dn",
        "cand_2U", "cand_2D", "cand_1", "cand_3", "dow", "ftfc"}]
    print(f"{ticker:6}  {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(df)} sessions, {len(feat_cols)} features)")
    part_a_ftfc(df)
    part_b_model(df, feat_cols)
    part_c_correlation(df, feat_cols)
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=2000)
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    print(f"NEXT-CANDLE ANALYSIS — {len(tickers)} tickers, last {args.days} sessions\n")
    for t in tickers:
        try:
            analyze(t, args.days)
        except Exception as e:
            import traceback
            print(f"{t:6} — ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
