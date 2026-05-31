"""Shared, label-agnostic indicator-combination mining.

This is the ONE source of truth for the combo-prediction math used by two
separate efforts (CLAUDE.md Rule 3.6 — no duplicated logic):

  * Effort A — general regime prediction (BIG / UP / DOWN / FLAT moves),
    driven by ``scripts/analysis/regime_combo_miner.py`` + the
    ``regime-combo`` Cloud Run job.
  * Effort B — Strat next-candle prediction (1 / 2U / 2D / 3), driven by
    ``scripts/analysis/strat_combo_miner.py`` + the strat-engine Stage 3b.

Every function here is PURE (no I/O, no globals, no network) so it is
hermetically unit-testable (Rule 0.3) and reusable from both the sandbox
analysis scripts and the Cloud Run jobs.

Design principle — **label-agnostic**: the miner takes a ``label: pd.Series``
plus a ``target_class: str`` rather than baking in any regime/strat vocabulary.
A binary regime is ``label ∈ {UP, DOWN, FLAT}`` with ``target_class="UP"``; a
Strat target is ``label ∈ {1, 2U, 2D, 3}`` with ``target_class="2U"``. The code
path is identical.

Leakage discipline (every cut-point is fit on TRAIN rows only):
  * ``binarize_conditions`` medians come from ``X.loc[train_mask]``.
  * ``select_top_features`` ranks on ``train_mask`` only.
  * Callers must build regime-label quantile thresholds on train only and must
    exclude non-stationary absolute-price columns + lag intrabar-range features
    (see ``stationary_feature_filter`` / ``add_candidate_features``).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Feature whitelist
# ---------------------------------------------------------------------------

# Stationary oscillators / ratios / %-distances / flags that are safe to feed a
# model trained on years of data — they do not drift with the absolute price
# level. Absolute-price columns (EMA/SMA/VWAP/ATR/BB bands/ORB price levels/OBV)
# are deliberately EXCLUDED: on a single ticker over years they would let the
# model memorise the price trajectory rather than learn structure.
_STATIONARY_EXACT = {
    # momentum / oscillators
    "RSI14", "RSI9", "RSI30", "RSI_Thrust_3", "StochRSI_K", "StochRSI_D",
    "MACD_Histogram",
    # volatility ratios
    "ATR_Expansion", "BB_Pct", "BB_Width",
    # volume ratios
    "RVOL", "RVol_Recent_20",
    # per-bar / position
    "Price_Change", "Close_vs_Range", "Daily_Range_Pct",
    "Consecutive_Up", "Consecutive_Down", "Consecutive_Up_5", "Consecutive_Down_5",
    # vol-normalised distances (existing %-based)
    "Price_vs_VWAP", "Price_vs_EMA9", "Price_vs_EMA20",
    # candidate (measure-first) features added by add_candidate_features
    "EMA9_Slope", "Mins_Since_Open", "Price_vs_EMA9_ATR", "Price_vs_EMA20_ATR",
    "Price_vs_VWAP_ATR", "EMA_Spread_ATR", "BB_Squeeze", "Realized_Vol_Short",
    "RSI_Divergence", "MACD_Hist_Slope",
}


def stationary_feature_filter(columns: Sequence[str]) -> List[str]:
    """Return the subset of ``columns`` that are leak-safe model features.

    Keeps the explicit stationary whitelist plus ORB *normalised* columns
    (``_Pct`` / ``_Trend`` / ``_Broke_*`` / ``_Within_Range``) — but NOT raw
    ORB price levels (``ORB_5m_High`` etc.), and NOT any 1-bar-lagged intrabar
    feature (handled by the caller via the explicit whitelist entry). ``_Lag1``
    variants of whitelisted features are also kept.
    """
    keep: List[str] = []
    for c in columns:
        base = c[:-5] if c.endswith("_Lag1") else c
        if base in _STATIONARY_EXACT:
            keep.append(c)
        elif base.startswith("ORB_") and (
            base.endswith("_Pct") or base.endswith("_Trend")
            or "_Broke_" in base or base.endswith("_Within_Range")
        ):
            keep.append(c)
    return keep


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComboResult:
    """One interpretable condition-combination and its out-of-sample stats."""
    conditions: tuple          # e.g. ("RSI14>med", "ATR_Expansion<=med")
    target: str                # the class this combo predicts ("UP", "2U", ...)
    hit_rate: float            # OOS P(target | combo)
    base_rate: float           # OOS P(target)
    lift: float                # hit_rate / base_rate
    support: int               # OOS rows matching the combo
    train_support: int         # TRAIN rows matching (stability sanity check)


@dataclass(frozen=True)
class ModelLift:
    """Out-of-sample model performance for a target, with feature importance."""
    target_name: str           # "direction" | "magnitude" | "next_bar_type"
    oos_accuracy: float
    base_rate: float           # most-frequent-class share in TEST
    lift: float                # oos_accuracy / base_rate
    perm_importance: Dict[str, float] = field(default_factory=dict)
    class_mix: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Conditions / feature ranking
# ---------------------------------------------------------------------------

def binarize_conditions(
    X: pd.DataFrame,
    feature_cols: Sequence[str],
    train_mask: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Map each feature to two boolean condition masks: ``{f}>med`` / ``{f}<=med``.

    The split median is computed on TRAIN rows ONLY (leakage control). Features
    that are constant on train (median undefined / degenerate split) are
    skipped.
    """
    conds: Dict[str, np.ndarray] = {}
    for f in feature_cols:
        col = X[f].astype(float)
        med = col[train_mask].median()
        if not np.isfinite(med):
            continue
        hi = (col > med).to_numpy()
        # Skip degenerate splits (all-True / all-False on train).
        tr_hi = hi[train_mask]
        if tr_hi.all() or (~tr_hi).all():
            continue
        conds[f"{f}>med"] = hi
        conds[f"{f}<=med"] = ~hi
    return conds


def select_top_features(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    target: pd.Series,
    train_mask: np.ndarray,
    k: int,
    method: str = "spearman",
) -> List[str]:
    """Rank features for the combo search, TRAIN-only, return the top ``k``.

    method="spearman": |Spearman(feature, target)| — target is a numeric series
        (e.g. signed or absolute forward return). For the regime case.
    method="mutual_info": mutual information of feature vs a binary/one-vs-rest
        target. For the Strat case. Falls back to spearman if sklearn missing.
    """
    feature_cols = list(feature_cols)
    tr = np.asarray(train_mask)
    if method == "mutual_info":
        try:
            from sklearn.feature_selection import mutual_info_classif
            X = df.loc[tr, feature_cols].astype(float)
            # mutual_info needs finite values; impute train-median per column.
            X = X.fillna(X.median())
            y = np.asarray(target)[tr]
            # Cost control: MI is O(n_rows · n_features · n_neighbors). Cap the
            # train sample so feature selection stays cheap on multi-year data.
            if len(X) > 30000:
                sel = np.random.default_rng(42).choice(len(X), 30000, replace=False)
                X = X.iloc[sel]
                y = y[sel]
            mi = mutual_info_classif(X.values, y, random_state=42)
            order = pd.Series(mi, index=feature_cols).sort_values(ascending=False)
            return order.head(k).index.tolist()
        except Exception:
            method = "spearman"
    # spearman path
    tgt = pd.Series(np.asarray(target, dtype="float64")[tr], index=df.index[tr])
    scores = {}
    for f in feature_cols:
        s = df.loc[tr, f].astype(float)
        r = s.corr(tgt, method="spearman")
        scores[f] = abs(r) if pd.notna(r) else 0.0
    order = pd.Series(scores).sort_values(ascending=False)
    return order.head(k).index.tolist()


# ---------------------------------------------------------------------------
# Combo mining
# ---------------------------------------------------------------------------

def mine_combos(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    label: pd.Series,
    target_class: str,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    *,
    max_order: int = 3,
    min_support: int = 500,
    top_k: int = 12,
) -> List[ComboResult]:
    """Rank interpretable 1..``max_order``-way condition combos by OOS hit-rate.

    For ``target_class`` (one value of ``label``), build candidate conditions by
    binarising ``feature_cols`` at their train median, then enumerate combos of
    size 1..max_order. A combo's stats are computed on TEST rows only; combos
    with OOS support below ``min_support`` are dropped. Returns the ``top_k``
    combos by hit-rate (ties broken by lift then support).

    A feature's HIGH and its own LOW are never combined (vacuous). Pure — no
    side effects.
    """
    test_mask = np.asarray(test_mask)
    train_mask = np.asarray(train_mask)
    y = (np.asarray(label) == target_class)
    base = float(y[test_mask].mean())
    if base <= 0:
        return []

    conds = binarize_conditions(df, feature_cols, train_mask)
    names = list(conds)

    rows: List[ComboResult] = []
    for order in range(1, max_order + 1):
        for combo in itertools.combinations(names, order):
            # don't combine a feature's HIGH with its own LOW
            bases = [c.rsplit(">med", 1)[0].rsplit("<=med", 1)[0] for c in combo]
            if len(set(bases)) != len(bases):
                continue
            mask = np.ones(len(df), dtype=bool)
            for c in combo:
                mask &= conds[c]
            test_sel = mask & test_mask
            n = int(test_sel.sum())
            if n < min_support:
                continue
            hit = float(y[test_sel].mean())
            rows.append(ComboResult(
                conditions=tuple(combo),
                target=target_class,
                hit_rate=hit,
                base_rate=base,
                lift=hit / base if base else float("nan"),
                support=n,
                train_support=int((mask & train_mask).sum()),
            ))
    rows.sort(key=lambda r: (r.hit_rate, r.lift, r.support), reverse=True)
    return rows[:top_k]


# ---------------------------------------------------------------------------
# Model lift (gradient-boosted, OOS) + permutation importance
# ---------------------------------------------------------------------------

def model_lift(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    label: pd.Series,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    target_name: str,
    *,
    n_perm_repeats: int = 2,
    perm_sample_cap: int = 8000,
    train_sample_cap: int = 80000,
    random_state: int = 0,
) -> ModelLift:
    """OOS accuracy vs base rate + permutation importance for a (binary OR
    multiclass) ``label``. HistGradientBoosting handles both natively, which is
    why a single function serves regime and Strat targets.

    Cost control (CLAUDE.md Rule 0): permutation_importance is O(n_features ×
    n_repeats × n_rows) and dominates wall-clock, so the test set is subsampled
    to ``perm_sample_cap`` rows for the importance pass and the training set is
    capped at ``train_sample_cap`` rows (uniform random, seeded). Accuracy/base
    are still measured on the FULL test set — only the importance attribution
    and the fit are subsampled.

    Requires scikit-learn; raises ImportError if unavailable (the caller — an
    analysis script or research-image job — is expected to have it).
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import accuracy_score

    train_mask = np.asarray(train_mask)
    test_mask = np.asarray(test_mask)
    feature_cols = list(feature_cols)
    rng = np.random.default_rng(random_state)

    X = df[feature_cols].astype(float).to_numpy()
    y = np.asarray(label)
    tr_idx = np.flatnonzero(train_mask)
    te_idx = np.flatnonzero(test_mask)
    if tr_idx.size > train_sample_cap:
        tr_idx = rng.choice(tr_idx, size=train_sample_cap, replace=False)
    Xtr, ytr = X[tr_idx], y[tr_idx]
    Xte, yte = X[te_idx], y[te_idx]

    clf = HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.06,
        l2_regularization=1.0, random_state=random_state,
    )
    clf.fit(Xtr, ytr)
    acc = float(accuracy_score(yte, clf.predict(Xte)))

    vc = pd.Series(yte).value_counts(normalize=True)
    base = float(vc.iloc[0]) if len(vc) else float("nan")
    class_mix = {str(k): float(v) for k, v in vc.items()}

    # permutation importance on a small capped test subsample (cost control)
    perm: Dict[str, float] = {}
    if te_idx.size:
        sub = (rng.choice(te_idx.size, size=min(perm_sample_cap, te_idx.size),
                          replace=False))
        pi = permutation_importance(
            clf, Xte[sub], yte[sub], n_repeats=n_perm_repeats,
            random_state=random_state, scoring="accuracy",
        )
        perm = {f: float(m) for f, m in zip(feature_cols, pi.importances_mean)}
        perm = dict(sorted(perm.items(), key=lambda kv: kv[1], reverse=True))

    return ModelLift(
        target_name=target_name,
        oos_accuracy=acc,
        base_rate=base,
        lift=acc / base if base else float("nan"),
        perm_importance=perm,
        class_mix=class_mix,
    )


# ---------------------------------------------------------------------------
# Candidate (measure-first) features
# ---------------------------------------------------------------------------

def add_candidate_features(
    df: pd.DataFrame,
    indicator_config=None,
    *,
    bb_squeeze_window: int = 20,
    ema_slope_lookback: int = 5,
    realized_vol_window: int = 20,
) -> pd.DataFrame:
    """Append un-promoted candidate features ON TOP of ``add_all_indicators``
    output. MEASURE-FIRST staging area — winners are promoted into
    ``lib/indicators.py`` in a separate gated step; losers stay here or are
    deleted (never silently shipped, Rule 3.7).

    Every candidate is stationary by construction (slopes / ATR-normalised
    distances / ratios) and derives only from columns ``add_all_indicators``
    already produced (EMA9/20, VWAP, ATR14, BB_Width, Close), so promotion later
    is a copy of the formula, not a reimplementation.

    Also emits 1-bar-LAGGED variants of intrabar-range features
    (``Daily_Range_Pct``, ``Close_vs_Range``) so a same-bar regime label cannot
    see the labelled bar's own range (leakage control, user decision).
    """
    from lib.config import IndicatorConfig
    ic = indicator_config or IndicatorConfig()
    out = df.copy()
    c = out["Close"].astype(float)

    atr_col = ic.atr_col  # e.g. "ATR14"
    atr = out[atr_col].astype(float) if atr_col in out.columns else None

    def _safe_div(num, den):
        den = den.where(den.abs() > 0, np.nan)
        return num / den

    # 1. EMA9_Slope — n-bar change in EMA9, ATR-normalised (momentum velocity).
    if "EMA9" in out.columns and atr is not None:
        out["EMA9_Slope"] = _safe_div(out["EMA9"].astype(float).diff(ema_slope_lookback), atr)

    # 2. Mins_Since_Open — minutes since 09:30 (intraday clock). Guarded on Time.
    if "Time" in out.columns:
        ts = pd.to_datetime(out["Time"])
        out["Mins_Since_Open"] = (ts.dt.hour * 60 + ts.dt.minute - (9 * 60 + 30)).astype(float)

    # 3. ATR-normalised distances (stationary twins of the %-based columns).
    if atr is not None:
        if "EMA9" in out.columns:
            out["Price_vs_EMA9_ATR"] = _safe_div(c - out["EMA9"].astype(float), atr)
        if "EMA20" in out.columns:
            out["Price_vs_EMA20_ATR"] = _safe_div(c - out["EMA20"].astype(float), atr)
        if "VWAP" in out.columns:
            out["Price_vs_VWAP_ATR"] = _safe_div(c - out["VWAP"].astype(float), atr)
        # 4. EMA_Spread_ATR — trend separation, vol-normalised.
        if "EMA9" in out.columns and "EMA20" in out.columns:
            out["EMA_Spread_ATR"] = _safe_div(
                out["EMA9"].astype(float) - out["EMA20"].astype(float), atr)

    # 5. BB_Squeeze — BB_Width relative to its own rolling median (compression).
    if "BB_Width" in out.columns:
        bw = out["BB_Width"].astype(float)
        roll = bw.rolling(bb_squeeze_window, min_periods=bb_squeeze_window).median()
        out["BB_Squeeze"] = _safe_div(bw, roll)

    # 6. Realized_Vol_Short — rolling std of 1-bar log returns.
    logret = np.log(c).diff()
    out["Realized_Vol_Short"] = logret.rolling(
        realized_vol_window, min_periods=realized_vol_window).std()

    # Exploratory: RSI fast-vs-slow divergence + MACD histogram slope.
    if "RSI9" in out.columns and "RSI14" in out.columns:
        out["RSI_Divergence"] = out["RSI9"].astype(float) - out["RSI14"].astype(float)
    if "MACD_Histogram" in out.columns:
        out["MACD_Hist_Slope"] = out["MACD_Histogram"].astype(float).diff(3)

    # 1-bar-lagged intrabar-range features (leakage-safe regime inputs).
    for src in ("Daily_Range_Pct", "Close_vs_Range"):
        if src in out.columns:
            out[f"{src}_Lag1"] = out[src].astype(float).shift(1)

    return out
