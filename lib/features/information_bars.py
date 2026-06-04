"""Information-driven bars from 1-minute OHLCV.

López de Prado, *Advances in Financial Machine Learning* (ch.2): instead of
sampling the market on a fixed clock (time bars), sample it when a fixed
quantum of *information* has arrived. Tick / volume / dollar / imbalance bars
all sample on activity rather than wall-clock time, which gives returns that
are closer to IID and better-behaved for downstream ML.

We do **not** have tick data — only 1-minute OHLCV — so this module
approximates the two activity-driven bar types that are recoverable from
minute aggregates:

  * **volume bars** — accumulate consecutive 1-min bars until the running
    Σ volume crosses a threshold, then emit one synthetic bar.
  * **dollar bars** — same, but the running sum is Σ(close · volume)
    (dollar volume), which is more robust to price-level drift than raw
    share volume.

The approximation: a 1-minute bar is the atomic unit, so a synthetic bar can
overshoot the threshold by at most one minute's worth of volume/dollars. With
real ticks you'd split mid-bar; we can't, and we do not fabricate intra-minute
structure to pretend we can.

SESSION-AWARE: a synthetic bar never spans two trading days. Accumulation is
reset both (a) when the threshold is crossed, and (b) at every new
``bar_date`` — a partial (sub-threshold) accumulation left at the end of a
session is emitted as its own (smaller) bar rather than bleeding into the
next session's first bar.

NO SILENT FALLBACKS (repo CLAUDE.md §3.7): a session with zero total volume
is skipped with a logged warning, not emitted as a fabricated zero bar. We
never ``fillna(0)`` a price field; missing volume is treated as missing, and
an all-missing-volume session produces no bars.

Pure numpy/pandas — no DB, no network. Importable in a hermetic test.

API
---
``resample_volume_bars(df_1min, threshold)``  -> DataFrame of volume bars
``resample_dollar_bars(df_1min, threshold)``  -> DataFrame of dollar bars
``suggest_threshold(df_1min, bars_per_day_target, mode)`` -> float
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Required input columns for the 1-min frame.
_REQUIRED_COLS = ("ticker", "ts", "open", "high", "low", "close", "volume", "bar_date")

# Output column order for an emitted info-bar frame.
_OUTPUT_COLS = (
    "ticker",
    "ts",
    "bar_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "n_min_bars",
)


def _validate(df_1min: pd.DataFrame) -> None:
    """Fail loud on a malformed input frame (INTERNAL contract — re-raise)."""
    missing = [c for c in _REQUIRED_COLS if c not in df_1min.columns]
    if missing:
        raise ValueError(
            f"df_1min is missing required columns {missing}; "
            f"got {list(df_1min.columns)}"
        )


def _empty_output() -> pd.DataFrame:
    """An empty, correctly-typed output frame (used when no bars are emitted).

    This is not a silent fallback: it is the honest representation of "this
    input produced no information bars" (e.g. an all-zero-volume input). The
    callers that produced it logged the reason at WARNING.
    """
    out = pd.DataFrame({c: pd.Series(dtype="object") for c in _OUTPUT_COLS})
    for c in ("open", "high", "low", "close", "volume", "vwap"):
        out[c] = out[c].astype("float64")
    out["n_min_bars"] = out["n_min_bars"].astype("int64")
    return out


def _resample(
    df_1min: pd.DataFrame,
    threshold: float,
    *,
    metric: Literal["volume", "dollar"],
) -> pd.DataFrame:
    """Core accumulator shared by the volume- and dollar-bar resamplers.

    ``metric`` selects what the running sum measures:
      * ``"volume"`` — Σ volume
      * ``"dollar"`` — Σ (close · volume)
    """
    _validate(df_1min)
    if threshold <= 0:
        raise ValueError(f"threshold must be > 0, got {threshold!r}")
    if metric not in ("volume", "dollar"):
        raise ValueError(f"metric must be 'volume' or 'dollar', got {metric!r}")

    if df_1min.empty:
        return _empty_output()

    # Deterministic order: by ticker, then bar_date, then timestamp. We do NOT
    # mutate the caller's frame.
    df = df_1min.sort_values(["ticker", "bar_date", "ts"], kind="stable")

    emitted: list[dict] = []

    # One independent accumulation stream per (ticker, session). A session
    # boundary (new ticker OR new bar_date) forces a flush, so a partial bar
    # never spans days or tickers.
    for (ticker, bar_date), session in df.groupby(["ticker", "bar_date"], sort=False):
        # Guard against missing volume rather than fillna(0)-ing it. A row with
        # NaN volume can't contribute to an Σvolume threshold honestly, so we
        # drop those rows and let the session's real volume decide.
        vol = session["volume"]
        if vol.isna().any():
            n_bad = int(vol.isna().sum())
            log.warning(
                "ticker=%s bar_date=%s: %d/%d 1-min bars have NaN volume; "
                "skipping those rows (no fabricated 0-volume).",
                ticker,
                bar_date,
                n_bad,
                len(session),
            )
            session = session[vol.notna()]

        if session.empty:
            log.warning(
                "ticker=%s bar_date=%s: no usable 1-min bars after dropping "
                "NaN-volume rows; session skipped.",
                ticker,
                bar_date,
            )
            continue

        session_total_vol = float(session["volume"].sum())
        if session_total_vol <= 0:
            # Zero-volume session: do NOT fabricate a bar. Skip + warn.
            log.warning(
                "ticker=%s bar_date=%s: session total volume is %s; "
                "no information bar emitted (skipped, not fabricated).",
                ticker,
                bar_date,
                session_total_vol,
            )
            continue

        # Running accumulators for the in-progress synthetic bar.
        acc_vol = 0.0          # Σ volume          (always tracked → output volume)
        acc_dollar = 0.0       # Σ close·volume    (always tracked → vwap numerator)
        acc_metric = 0.0       # the threshold-driving sum (volume OR dollar)
        acc_open: float | None = None
        acc_high = -np.inf
        acc_low = np.inf
        acc_close: float | None = None
        acc_ts = None
        acc_n = 0

        def _flush() -> None:
            nonlocal acc_vol, acc_dollar, acc_metric
            nonlocal acc_open, acc_high, acc_low, acc_close, acc_ts, acc_n
            if acc_n == 0:
                return
            # vwap = Σ(close·vol)/Σvol. acc_vol > 0 is guaranteed because we
            # only accumulate rows whose volume is non-NaN and a zero-only
            # session was already skipped above; but a single 0-volume minute
            # inside a non-zero session is possible, so guard the divide and
            # emit vwap=NaN (honest "undefined") rather than 0.
            vwap = (acc_dollar / acc_vol) if acc_vol > 0 else np.nan
            emitted.append(
                {
                    "ticker": ticker,
                    "ts": acc_ts,
                    "bar_date": bar_date,
                    "open": acc_open,
                    "high": acc_high,
                    "low": acc_low,
                    "close": acc_close,
                    "volume": acc_vol,
                    "vwap": vwap,
                    "n_min_bars": acc_n,
                }
            )
            acc_vol = 0.0
            acc_dollar = 0.0
            acc_metric = 0.0
            acc_open = None
            acc_high = -np.inf
            acc_low = np.inf
            acc_close = None
            acc_ts = None
            acc_n = 0

        for row in session.itertuples(index=False):
            o = float(row.open)
            h = float(row.high)
            lo = float(row.low)
            c = float(row.close)
            v = float(row.volume)
            dollar = c * v

            if acc_n == 0:
                acc_open = o
            acc_high = max(acc_high, h)
            acc_low = min(acc_low, lo)
            acc_close = c
            acc_ts = row.ts
            acc_vol += v
            acc_dollar += dollar
            acc_n += 1

            acc_metric += v if metric == "volume" else dollar

            if acc_metric >= threshold:
                _flush()

        # End of session: flush any sub-threshold remainder as its own bar so
        # it can't bleed into the next session.
        _flush()

    if not emitted:
        return _empty_output()

    out = pd.DataFrame(emitted, columns=list(_OUTPUT_COLS))
    for c in ("open", "high", "low", "close", "volume", "vwap"):
        out[c] = out[c].astype("float64")
    out["n_min_bars"] = out["n_min_bars"].astype("int64")
    return out.reset_index(drop=True)


def resample_volume_bars(df_1min: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Accumulate 1-min bars per session until Σ volume >= ``threshold``.

    Emits one synthetic bar per crossing with::

        open  = first constituent open
        high  = max constituent high
        low   = min constituent low
        close = last constituent close
        volume = Σ constituent volume
        ts    = last constituent ts
        vwap  = Σ(close·vol) / Σvol
        n_min_bars = number of 1-min bars composing the synthetic bar

    Accumulation resets on every threshold crossing AND at every new session
    (``ticker``/``bar_date`` boundary). A sub-threshold remainder at the end of
    a session is emitted as its own (smaller) bar.

    Zero-volume sessions are skipped with a WARNING (no fabricated bar).

    Parameters
    ----------
    df_1min : DataFrame
        Columns: ticker, ts, open, high, low, close, volume, bar_date.
    threshold : float
        Share-volume quantum per synthetic bar (> 0).

    Returns
    -------
    DataFrame with columns: ticker, ts, bar_date, open, high, low, close,
    volume, vwap, n_min_bars. Empty (typed) frame if nothing was emitted.
    """
    return _resample(df_1min, threshold, metric="volume")


def resample_dollar_bars(df_1min: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Accumulate 1-min bars per session until Σ(close·volume) >= ``threshold``.

    Identical aggregation contract to :func:`resample_volume_bars`, but the
    threshold is driven by *dollar* volume (Σ close·volume) rather than raw
    share volume. Dollar bars are more robust to price-level drift, since a
    fixed share count represents a different dollar exposure at $10 vs $400.

    Parameters
    ----------
    df_1min : DataFrame
        Columns: ticker, ts, open, high, low, close, volume, bar_date.
    threshold : float
        Dollar-volume quantum per synthetic bar (> 0).

    Returns
    -------
    DataFrame, same schema as :func:`resample_volume_bars`.
    """
    return _resample(df_1min, threshold, metric="dollar")


def suggest_threshold(
    df_1min: pd.DataFrame,
    bars_per_day_target: int,
    mode: Literal["volume", "dollar"],
) -> float:
    """Suggest a threshold giving ~``bars_per_day_target`` info-bars per session.

    threshold = median(daily total) / bars_per_day_target

    where "daily total" is per-session Σ volume (``mode="volume"``) or
    per-session Σ(close·volume) (``mode="dollar"``). Using the median across
    sessions makes the suggestion robust to a few unusually heavy/light days.

    Example
    -------
    To match a ~15-minute cadence (≈26 bars in a 6.5h RTH session), call with
    ``bars_per_day_target=26, mode="dollar"`` and the returned threshold will,
    on a median day, produce ~26 dollar bars.

    Zero-volume sessions are excluded from the median (they would otherwise
    bias the median toward 0 and produce a nonsensically small threshold).

    Parameters
    ----------
    df_1min : DataFrame
        Same schema as the resamplers.
    bars_per_day_target : int
        Desired average number of info-bars per session (> 0).
    mode : {"volume", "dollar"}
        Which daily total to base the threshold on.

    Returns
    -------
    float : the suggested threshold (> 0).

    Raises
    ------
    ValueError if the frame is empty, malformed, has a non-positive target, an
    invalid mode, or no session with positive volume to compute a median from.
    These are INTERNAL failures — re-raise, don't return a fabricated 0.
    """
    _validate(df_1min)
    if mode not in ("volume", "dollar"):
        raise ValueError(f"mode must be 'volume' or 'dollar', got {mode!r}")
    if bars_per_day_target <= 0:
        raise ValueError(
            f"bars_per_day_target must be > 0, got {bars_per_day_target!r}"
        )
    if df_1min.empty:
        raise ValueError("df_1min is empty; cannot suggest a threshold.")

    df = df_1min.copy()
    if df["volume"].isna().any():
        df = df[df["volume"].notna()]

    if mode == "dollar":
        df = df.assign(_metric=df["close"].astype(float) * df["volume"].astype(float))
    else:
        df = df.assign(_metric=df["volume"].astype(float))

    daily_totals = df.groupby(["ticker", "bar_date"])["_metric"].sum()
    daily_totals = daily_totals[daily_totals > 0]

    if daily_totals.empty:
        raise ValueError(
            "No session with positive volume; cannot suggest a threshold "
            "(refusing to fabricate one from zero-volume data)."
        )

    median_daily = float(daily_totals.median())
    return median_daily / float(bars_per_day_target)
