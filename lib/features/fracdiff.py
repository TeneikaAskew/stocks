"""Fractional differentiation features (López de Prado, AFML ch.5).

Transform a price (level) series into one that is **stationary** while
**preserving long memory**, so it can be fed to ML models as a feature.

Motivation
----------
The repo's existing features are almost all built on returns (d=1
differencing). d=1 makes a series stationary, but it is *memoryless* — by
fully differencing the level away, you destroy the long-range dependence
that often carries predictive signal. Fractional differentiation lets you
choose a *real-valued* differencing order d* (typically ~0.3-0.5) that is
the MINIMUM amount of differencing needed to pass a stationarity test
(ADF). At d*, the transformed series is stationary AND retains the most
memory possible (highest correlation with the original level series).

The four public entry points:

  - ``frac_diff_weights(d, size)``  — the binomial weight kernel.
  - ``frac_diff_ffd(series, d, thresh)`` — Fixed-Width-Window fracdiff.
  - ``find_min_d(series, ...)`` — search for the minimum stationary d*.
  - ``add_fracdiff_features(df, price_cols, ...)`` — DataFrame helper.

Window / NaN policy (NO silent fallbacks, per repo CLAUDE.md §3.7)
-----------------------------------------------------------------
The FFD kernel has a fixed width ``W`` (the number of weights kept before
``|w_k|`` drops below ``thresh``). The first ``W - 1`` observations do not
have a full window behind them, so their fracdiff value is **left as NaN**.
We never ``fillna(0)`` — a 0 there would be indistinguishable from a real
computed value, which is exactly the kind of silent fallback the repo
forbids. The model treats NaN as "missing".

Session awareness
-----------------
``add_fracdiff_features`` is session-aware: if the DataFrame has a
``bar_date`` column, fracdiff is computed *independently within each
bar_date group*, so the convolution kernel never reaches across an
overnight boundary (the close-to-open gap is not a continuous price move
and shouldn't leak into the window). Without a ``bar_date`` column it
operates on the whole series in order.

Pure / hermetic: depends only on numpy, pandas, scipy, statsmodels. No DB
access, no repo imports.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 1. Binomial weight kernel
# --------------------------------------------------------------------------- #
def frac_diff_weights(d: float, size: int) -> np.ndarray:
    """Binomial weight series for fractional differencing order ``d``.

    The weights follow the recurrence (AFML eq. 5.2):

        w_0 = 1
        w_k = -w_{k-1} * (d - k + 1) / k        for k >= 1

    Returns an array of length ``size`` (``w_0 .. w_{size-1}``).

    Sanity checks:
      - d = 1 -> [1, -1, 0, 0, ...]  (ordinary first differencing)
      - d = 0 -> [1,  0, 0, 0, ...]  (identity)
      - d = 2 -> [1, -2, 1, 0, ...]  (second difference)
    """
    if size < 1:
        raise ValueError(f"size must be >= 1, got {size}")
    w = [1.0]
    for k in range(1, size):
        w_k = -w[-1] * (d - k + 1) / k
        w.append(w_k)
    return np.array(w, dtype=float)


def _ffd_weights(d: float, thresh: float, max_size: Optional[int] = None) -> np.ndarray:
    """Fixed-width-window weights: keep terms until ``|w_k| < thresh``.

    Returns weights ordered ``[w_{W-1}, ..., w_1, w_0]`` (oldest -> newest),
    i.e. already arranged for a dot-product against a trailing window where
    the most recent observation is last. ``w_0 == 1`` is always the last
    element. Length is the window width ``W``.
    """
    if thresh <= 0:
        raise ValueError(f"thresh must be > 0, got {thresh}")
    w = [1.0]
    k = 1
    while True:
        w_k = -w[-1] * (d - k + 1) / k
        if abs(w_k) < thresh:
            break
        w.append(w_k)
        k += 1
        if max_size is not None and k >= max_size:
            break
    # w currently [w_0, w_1, ... w_{W-1}] (newest-first conceptually).
    # Reverse so the trailing window (oldest..newest) lines up with weights.
    return np.array(w[::-1], dtype=float)


# --------------------------------------------------------------------------- #
# 2. Fixed-Width-Window fractional differencing
# --------------------------------------------------------------------------- #
def frac_diff_ffd(series: pd.Series, d: float, thresh: float = 1e-4) -> pd.Series:
    """Fixed-Width-Window (FFD) fractional differentiation (AFML §5.5).

    Computes the kernel weights until ``|w_k| < thresh`` (giving a fixed
    window width ``W``), then convolves them against the series. The first
    ``W - 1`` observations lack a full window and are returned as **NaN**
    (never zero-filled).

    Parameters
    ----------
    series : pd.Series
        The level series (typically a price). Index is preserved.
    d : float
        Fractional differencing order (>= 0).
    thresh : float
        Weight-magnitude cutoff that sets the fixed window width.

    Returns
    -------
    pd.Series
        Same index as ``series``; leading ``W-1`` entries are NaN.
    """
    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")
    if d < 0:
        raise ValueError(f"d must be >= 0, got {d}")

    w = _ffd_weights(d, thresh, max_size=len(series))
    width = len(w)  # W

    values = series.to_numpy(dtype=float)
    n = len(values)
    out = np.full(n, np.nan, dtype=float)

    if width > n:
        # Not enough data to fill even one window -> all NaN. Loud, not silent:
        # the result is explicitly all-NaN, not zeros.
        log.debug("frac_diff_ffd: window width %d > series length %d; all NaN",
                  width, n)
        return pd.Series(out, index=series.index, name=series.name)

    # Slide the fixed window. If any value inside the window is NaN, the
    # dot-product is NaN — propagated, not swallowed.
    for i in range(width - 1, n):
        window = values[i - width + 1: i + 1]
        out[i] = np.dot(w, window)

    return pd.Series(out, index=series.index, name=series.name)


# --------------------------------------------------------------------------- #
# 3. Minimum-d search (stationary while preserving memory)
# --------------------------------------------------------------------------- #
def _adfuller_pvalue(series: pd.Series) -> float:
    """Run ADF on the non-NaN tail of ``series``; return the p-value.

    Lazy-imports statsmodels so the rest of the module is usable without it.
    Raises ImportError with a clear message if statsmodels is missing.
    """
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError as exc:  # explicit, not a silent fallback
        raise ImportError(
            "find_min_d / ADF stationarity testing requires statsmodels. "
            "Install it with `pip install statsmodels`."
        ) from exc

    clean = series.dropna()
    if len(clean) < 10:
        raise ValueError(
            f"Too few non-NaN observations ({len(clean)}) for an ADF test."
        )
    # adfuller returns (adf_stat, pvalue, usedlag, nobs, crit_values, icbest)
    result = adfuller(clean.to_numpy(), maxlag=None, autolag="AIC")
    return float(result[1])


def find_min_d(
    series: pd.Series,
    thresh: float = 1e-4,
    max_d: float = 1.0,
    step: float = 0.05,
    adf_p: float = 0.05,
) -> float:
    """Find the MINIMUM d in [0, max_d] whose FFD series passes ADF.

    Scans d from 0 upward in increments of ``step``. For each candidate it
    computes the FFD series and runs the Augmented Dickey-Fuller test; the
    first d whose ADF p-value < ``adf_p`` is returned. Smaller d means more
    memory retained, so the first passing d is the memory-maximal stationary
    choice (AFML's d*).

    Returns
    -------
    float
        The minimal stationary d*. If even d == max_d does not pass, raises
        RuntimeError (loud, not a silent sentinel).

    Notes
    -----
    statsmodels is lazy-imported inside the ADF helper; a missing install
    raises a clear ImportError.
    """
    if step <= 0:
        raise ValueError(f"step must be > 0, got {step}")
    if max_d < 0:
        raise ValueError(f"max_d must be >= 0, got {max_d}")

    n_steps = int(round(max_d / step))
    candidates = [round(i * step, 10) for i in range(n_steps + 1)]

    last_p = None
    for d in candidates:
        fd = frac_diff_ffd(series, d, thresh=thresh)
        try:
            pval = _adfuller_pvalue(fd)
        except ValueError:
            # Not enough non-NaN points at this (usually tiny) d — the window
            # is wider than usable data. Skip to a larger d (wider differencing
            # narrows the window). This is NOT a silent value fallback: we make
            # no claim about stationarity, we just can't test it here.
            log.debug("find_min_d: insufficient data to ADF-test d=%.4f; skipping", d)
            continue
        last_p = pval
        log.debug("find_min_d: d=%.4f adf_p=%.4g", d, pval)
        if pval < adf_p:
            return float(d)

    raise RuntimeError(
        f"No d in [0, {max_d}] (step {step}) made the series stationary at "
        f"adf_p={adf_p}. Last tested p-value={last_p}. Increase max_d or "
        f"relax adf_p."
    )


# --------------------------------------------------------------------------- #
# 4. DataFrame helper (session-aware)
# --------------------------------------------------------------------------- #
def add_fracdiff_features(
    df: pd.DataFrame,
    price_cols: list[str],
    d: Optional[float] = None,
    thresh: float = 1e-4,
    prefix: str = "fd_",
) -> pd.DataFrame:
    """Add a fracdiff column ``{prefix}{col}`` for each price column.

    Session awareness
    -----------------
    If ``df`` has a ``bar_date`` column, fracdiff is computed independently
    within each ``bar_date`` group (the kernel never reaches across an
    overnight gap). Each group's leading ``W-1`` rows are NaN — including
    the first rows of every new session. Without a ``bar_date`` column the
    whole column is treated as one continuous series.

    Parameters
    ----------
    df : pd.DataFrame
        Input frame (not mutated; a copy is returned).
    price_cols : list[str]
        Columns to fractionally difference.
    d : float | None
        Differencing order. If None, ``find_min_d`` is called per column
        (and, when session-aware, on the whole column ordered by index —
        d* is a global property, then applied per session).
    thresh : float
        FFD weight cutoff (sets window width).
    prefix : str
        New-column name prefix.

    Returns
    -------
    pd.DataFrame
        Copy of ``df`` with the new ``{prefix}{col}`` columns. NaNs in the
        leading window of each session are preserved (never zero-filled).
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    missing = [c for c in price_cols if c not in df.columns]
    if missing:
        raise KeyError(f"price_cols not in df: {missing}")

    out = df.copy()
    session_aware = "bar_date" in out.columns

    for col in price_cols:
        new_col = f"{prefix}{col}"

        # Resolve d for this column. d* is a property of the level series'
        # memory, so we determine it once on the full (cross-session) series
        # then apply the same d per session. This keeps the differencing
        # order consistent within a column.
        if d is None:
            d_col = find_min_d(out[col], thresh=thresh)
            log.info("add_fracdiff_features: col=%s d*=%.4f", col, d_col)
        else:
            d_col = d

        if session_aware:
            # transform preserves the original index alignment per group.
            out[new_col] = out.groupby("bar_date", sort=False)[col].transform(
                lambda s: frac_diff_ffd(s, d_col, thresh=thresh)
            )
        else:
            out[new_col] = frac_diff_ffd(out[col], d_col, thresh=thresh)

    return out
