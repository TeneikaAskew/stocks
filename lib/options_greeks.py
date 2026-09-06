"""
Black-Scholes-Merton implied volatility solve and Greeks computation for
options-chain DataFrames whose source did not provide Greeks.

Why this exists
---------------
AlphaVantage ``HISTORICAL_OPTIONS`` returns the literal string ``'-'`` for
delta/gamma/theta/vega/rho/implied_volatility on cash-settled index options
(SPX, NDX, etc.). The fetcher coerces those to NaN, which the API then
serializes as null, leaving the Options Flow heatmap flat for SPX.

This module fills the gap: solve IV from the AV mid price, then compute the
five Greeks analytically. Results are written to **sidecar** columns
``delta_computed``, ``gamma_computed``, ``theta_computed``, ``vega_computed``,
``rho_computed``, ``implied_volatility_computed`` — the original source
columns are NEVER touched, preserving provenance.

Single integration point
------------------------
:func:`enrich_av_chain_with_greeks` is the only function fetchers and
backfill scripts need to call. It handles the rate/yield lookup, the
three-tier spot derivation, idempotency, and the BSM math. New tickers that
need self-computed Greeks just go into :data:`COMPUTE_GREEKS_TICKERS`.

Idempotency
-----------
Re-running on a chain that already has computed Greeks is a no-op (checked
via ``gamma_computed`` finite values, not ``IS NOT NULL`` — NaN-as-stored
is treated as "not yet computed").

Numerical edge cases
--------------------
``py_vollib`` returns NaN for prices where vega is too small to solve IV
numerically (deep OTM/ITM, near-expiry). Those rows keep NaN Greeks. The
frontend's ``?? 0`` fallback in greeksCalculator.ts handles this correctly:
strikes with no measurable gamma exposure don't move the heatmap.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Tickers whose source data does not include Greeks. Add new entries here
# (NDX, RUT, XSP, ...) as we onboard them. SPY/IWM/QQQ are intentionally
# excluded — AV provides Greeks for those.
COMPUTE_GREEKS_TICKERS = {"SPX", "SPXW", "NDX", "RUT", "XSP"}

# Rates used ONLY when a caller explicitly asks for them via
# `get_rate_and_yield(..., allow_defaults=True)` — offline work, or a fixture
# that needs a deterministic r/q. They approximate the late-2024 / early-2025
# regime, so they are years stale and getting staler.
#
# They used to be returned SILENTLY whenever the `daily_rates` lookup failed,
# at `log.debug` level. Greeks computed from a 2024 risk-free rate are wrong
# in theta and rho and slightly wrong in delta and gamma, and nothing
# downstream could tell them from measured ones — CLAUDE.md Rule 3.7, and
# finding C-03 of docs/audits/FALLBACK_AUDIT_2026-05-13.md, unfixed since May.
_DEFAULT_RISK_FREE = 0.045
_DEFAULT_DIV_YIELD = 0.013

# How stale the backstop row may be before the lookup fails instead.
# `daily_rates` is written every weekday at 06:30 ET by `fred-rates-daily`,
# and FRED itself publishes with a 1-2 day lag, so a healthy table can
# legitimately be a few days behind over a long weekend. Seven days clears
# that and still catches a fetcher that has stopped.
_RATE_MAX_STALENESS_DAYS = 7


class RateLookupError(RuntimeError):
    """`daily_rates` could not supply a rate for the requested date.

    Raised rather than substituting a constant: a wrong `r` produces Greeks
    that look measured. Callers that genuinely want a constant must ask for
    one with `allow_defaults=True` and own that choice.
    """

# Sidecar column names — single source of truth.
COMPUTED_COLS = (
    "delta_computed",
    "gamma_computed",
    "theta_computed",
    "vega_computed",
    "rho_computed",
    "implied_volatility_computed",
)


# ── shared BSM gamma (single public source) ──────────────────────────────────

def bs_gamma(S, K, t, r, q, sigma):
    """Black-Scholes-Merton per-share gamma, vectorized (numpy-broadcast).

    ``gamma = exp(-q·t)·φ(d1) / (S·σ·√t)``,
    ``d1 = (ln(S/K) + (r − q + 0.5σ²)t) / (σ√t)``.

    All args may be scalars or numpy arrays; they broadcast. This is the SAME
    formula used inside :func:`compute_greeks_from_prices` (`_bsm_greeks_vec`,
    line ~368) — factored out so other callers (e.g. ``lib.gamma``'s
    Black-Scholes gamma-flip recurve) use one source instead of re-deriving it.
    Non-finite / non-positive ``sigma`` or ``t`` carry NaN through (np.errstate
    guarded) rather than raising — the caller decides how to treat NaN.
    """
    from scipy.stats import norm  # lazy: keep module import light + scipy-optional
    S = np.asarray(S, dtype="float64")
    K = np.asarray(K, dtype="float64")
    t = np.asarray(t, dtype="float64")
    r = np.asarray(r, dtype="float64")
    q = np.asarray(q, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        sqrt_t = np.sqrt(t)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
        gamma = np.exp(-q * t) * norm.pdf(d1) / (S * sigma * sqrt_t)
    return gamma


# ── rate / yield lookup ──────────────────────────────────────────────────────

@lru_cache(maxsize=10000)
def get_rate_and_yield(target_date: date,
                       allow_defaults: bool = False) -> Tuple[float, float]:
    """Return ``(risk_free_rate, dividend_yield)`` for ``target_date``.

    Reads Cloud SQL ``daily_rates``: the exact date first, then the most
    recent row at or before it (which bridges weekends, holidays, and FRED's
    own 1-2 day publishing lag).

    **Raises** :class:`RateLookupError` rather than returning a constant when
    the rate cannot be established — the query failed, no row exists at or
    before the date, the backstop row is more than
    ``_RATE_MAX_STALENESS_DAYS`` old, or the column is NULL. A wrong ``r``
    does not announce itself: it shifts theta and rho on every contract in
    the chain, and the output is a plausible number either way.

    ``allow_defaults=True`` restores the old behaviour for callers that
    genuinely want a constant — offline analysis, a fixture needing a fixed
    ``r``. It is a parameter rather than a default so the choice appears at
    the call site.

    Cached per (date, allow_defaults) in-process: backfill scripts covering
    thousands of dates pay the lookup once per distinct date.
    """
    def _fallback_or_raise(reason: str) -> Tuple[float, float]:
        if allow_defaults:
            log.warning(
                "daily_rates lookup for %s: %s — using the %.3f/%.3f "
                "constants because allow_defaults=True. Greeks computed from "
                "these are NOT measured.",
                target_date, reason, _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD)
            return _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD
        raise RateLookupError(
            f"no risk-free rate available for {target_date}: {reason}. "
            f"Refusing to substitute a constant; pass allow_defaults=True "
            f"only if a fabricated rate is acceptable for this caller.")

    try:
        from gcp.database import query_to_dataframe_strict
    except ImportError as exc:
        return _fallback_or_raise(f"gcp.database unavailable ({exc})")

    target_param = target_date if isinstance(target_date, (date, datetime)) else str(target_date)

    # The STRICT helper: the swallowing `query_to_dataframe` returns an empty
    # DataFrame on a connection error, which is indistinguishable from "no
    # row" and would send a real outage down the missing-data path.
    try:
        df = query_to_dataframe_strict(
            "SELECT date, dgs3mo, sp500_div_yld FROM daily_rates "
            "WHERE date = :d LIMIT 1",
            {"d": target_param},
        )
        if df.empty:
            df = query_to_dataframe_strict(
                "SELECT date, dgs3mo, sp500_div_yld FROM daily_rates "
                "WHERE date <= :d ORDER BY date DESC LIMIT 1",
                {"d": target_param},
            )
    except Exception as exc:
        return _fallback_or_raise(f"daily_rates query failed ({type(exc).__name__}: {exc})")

    if df.empty:
        return _fallback_or_raise("no row at or before that date")

    row = df.iloc[0]

    row_date = row["date"]
    if isinstance(row_date, datetime):
        row_date = row_date.date()
    elif isinstance(row_date, str):
        row_date = pd.to_datetime(row_date).date()
    ref = target_date.date() if isinstance(target_date, datetime) else target_date
    if isinstance(row_date, date) and isinstance(ref, date):
        age = (ref - row_date).days
        if age > _RATE_MAX_STALENESS_DAYS:
            return _fallback_or_raise(
                f"newest row at or before that date is {row_date}, {age} days "
                f"stale (limit {_RATE_MAX_STALENESS_DAYS}) — the fred-rates-daily "
                f"job has probably stopped")

    if row["dgs3mo"] is None or pd.isna(row["dgs3mo"]):
        return _fallback_or_raise(f"dgs3mo is NULL on {row_date}")
    if row["sp500_div_yld"] is None or pd.isna(row["sp500_div_yld"]):
        return _fallback_or_raise(f"sp500_div_yld is NULL on {row_date}")

    return float(row["dgs3mo"]), float(row["sp500_div_yld"])


# ── close-price lookup ──────────────────────────────────────────────────────

def _get_close_price(ticker: str, target_date) -> Optional[float]:
    """Return the daily Close for ``ticker`` on ``target_date``, else None.

    Wraps :class:`lib.data_loader.DataLoader.load_daily` since main has no
    module-level ``get_close_price`` helper. Falls back to the most-recent
    close <= target_date so weekends/holidays don't break lookups.
    """
    if isinstance(target_date, str):
        target_date = pd.to_datetime(target_date).date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()

    try:
        from lib.data_loader import DataLoader
        loader = DataLoader()
        df = loader.load_daily(ticker, year=target_date.year)
    except Exception as exc:
        log.debug("load_daily(%s, %s) failed: %s", ticker, target_date.year, exc)
        return None

    if df is None or df.empty or "Close" not in df.columns:
        return None

    target_ts = pd.Timestamp(target_date)
    # DataLoader sets the index to tz-naive datetime named 'Time'.
    # Normalize to date-only for matching.
    idx_dates = df.index.normalize()
    if (idx_dates == target_ts).any():
        return float(df.loc[idx_dates == target_ts, "Close"].iloc[-1])
    earlier = df[idx_dates <= target_ts]
    if earlier.empty:
        return None
    return float(earlier["Close"].iloc[-1])


# ── spot derivation ─────────────────────────────────────────────────────────

def derive_spot_from_chain(
    df: pd.DataFrame,
    snapshot_date,
    risk_free: float,
    dividend_yield: float,
    n_strikes: int = 5,
) -> Optional[float]:
    """Derive the underlying spot price from the option chain via put-call parity.

    For each ATM strike :math:`K` with mid call :math:`C` and mid put :math:`P`:

    .. math::
        F = K + (C - P) e^{rT}
        S = F e^{-(r-q)T}

    We average across the ``n_strikes`` straddles closest to the rough ATM
    estimate (the chain's median strike is a reasonable seed). Each strike's
    straddle independently implies the spot, so the median across them is
    robust to one bad quote.

    Uses the **front month** (nearest expiration) only — wider expirations
    have looser bid-ask which inflates the put-call parity error.

    Returns ``None`` if no usable straddle exists.
    """
    if df.empty or "expiration" not in df.columns or "strike" not in df.columns:
        return None

    work = df.copy()
    # Coerce types defensively — backfill loop reads from SQL where some
    # columns may arrive as Decimal / object.
    for col in ("strike", "bid", "ask", "last_price"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work["mid"] = ((work["bid"].fillna(0) + work["ask"].fillna(0)) / 2.0).where(
        (work["bid"].fillna(0) > 0) & (work["ask"].fillna(0) > 0),
        work.get("last_price"),
    )

    # Front-month only (tightest spreads).
    exp_col = pd.to_datetime(work["expiration"], errors="coerce")
    work["_exp"] = exp_col
    work = work.dropna(subset=["_exp", "mid", "strike", "option_type"])
    if work.empty:
        return None
    front = work["_exp"].min()
    work = work[work["_exp"] == front]

    # Pivot to (strike → call_mid, put_mid) pairs.
    calls = work[work["option_type"] == "calls"].set_index("strike")["mid"]
    puts = work[work["option_type"] == "puts"].set_index("strike")["mid"]
    common = calls.index.intersection(puts.index)
    if len(common) == 0:
        return None

    # Seed ATM estimate: median of strikes (typically chain centered ATM).
    seed = float(np.median(common.to_numpy(dtype=float)))
    # Pick the n_strikes straddles closest to the seed.
    diffs = np.abs(common.to_numpy(dtype=float) - seed)
    pick_idx = np.argsort(diffs)[:n_strikes]
    pick_strikes = common.to_numpy(dtype=float)[pick_idx]

    snapshot_dt = pd.to_datetime(snapshot_date)
    front_dt = pd.to_datetime(front)
    t_years = max((front_dt - snapshot_dt).days / 365.0, 1.0 / 365.0)

    spots = []
    for k in pick_strikes:
        c = float(calls.loc[k])
        p = float(puts.loc[k])
        if not (c > 0 and p > 0):
            continue
        forward = k + (c - p) * math.exp(risk_free * t_years)
        spot = forward * math.exp(-(risk_free - dividend_yield) * t_years)
        if spot > 0 and not math.isnan(spot):
            spots.append(spot)

    if not spots:
        return None
    return float(np.median(spots))


# ── BSM math ────────────────────────────────────────────────────────────────

def compute_greeks_from_prices(
    df: pd.DataFrame,
    spot: float,
    snapshot_date,
    risk_free: float,
    dividend_yield: float,
) -> pd.DataFrame:
    """Solve IV from option mid prices and compute analytical BSM Greeks.

    Uses ``py_vollib_vectorized`` for batch evaluation — ~9k contracts in
    well under a second. Returns a copy of ``df`` with the six sidecar
    columns populated. Rows where the IV solver fails (deep OTM/ITM with
    vega ~ 0) get NaN Greeks; callers must accept that.

    The original ``delta``/``gamma``/etc. columns are not modified.
    """
    if df.empty:
        return df

    # IV solver and Greeks formulas — implemented inline with scipy. We used
    # to import these from py_vollib_vectorized; that library's IV solver and
    # BSM pricer route through numba-decorated functions that have a self-
    # recursive call current numba can't type-infer ("cannot type infer
    # runaway recursion"). The bug started after a 2026-05 numba upgrade
    # and broke both production and tests on main. Inlined scipy
    # implementations are independent of py_vollib_vectorized entirely.
    from scipy.stats import norm
    from scipy.optimize import brentq

    out = df.copy()

    # Reset the sidecar columns (NaN by default) so a partial recompute is clean.
    for col in COMPUTED_COLS:
        out[col] = np.nan

    # Build the inputs vectorized.
    bid = pd.to_numeric(out.get("bid"), errors="coerce").fillna(0)
    ask = pd.to_numeric(out.get("ask"), errors="coerce").fillna(0)
    last = pd.to_numeric(out.get("last_price"), errors="coerce")
    mid = ((bid + ask) / 2.0).where((bid > 0) & (ask > 0), last)

    strike = pd.to_numeric(out["strike"], errors="coerce")
    expiry = pd.to_datetime(out["expiration"], errors="coerce")
    snap_dt = pd.to_datetime(snapshot_date)
    t_days = (expiry - snap_dt).dt.days.astype("float64")
    # Floor at 1 day so expired/zero-DTE rows don't become divide-by-zero.
    t_years = np.maximum(t_days / 365.0, 1.0 / 365.0)
    flag = out["option_type"].map({"calls": "c", "puts": "p"})

    # Mask out rows we can't price (no mid, no strike, no flag).
    valid = (
        mid.notna() & (mid > 0)
        & strike.notna() & (strike > 0)
        & expiry.notna()
        & flag.notna()
    )
    if not valid.any():
        log.debug("compute_greeks_from_prices: 0 valid rows")
        return out

    sub = pd.DataFrame({
        "price":  mid[valid].astype("float64").values,
        "S":      np.full(int(valid.sum()), float(spot), dtype="float64"),
        "K":      strike[valid].astype("float64").values,
        "t":      t_years[valid].astype("float64").values,
        "r":      np.full(int(valid.sum()), float(risk_free), dtype="float64"),
        "q":      np.full(int(valid.sum()), float(dividend_yield), dtype="float64"),
        "flag":   flag[valid].values,
    })

    # --- BSM building blocks (scipy-based, no py_vollib) ---
    def _bsm_price_scalar(S, K, t, r, q, sigma, flag):
        if t <= 0 or sigma <= 0:
            intrinsic = max(S - K, 0.0) if flag == "c" else max(K - S, 0.0)
            return float(intrinsic)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * np.sqrt(t))
        d2 = d1 - sigma * np.sqrt(t)
        if flag == "c":
            return float(S * np.exp(-q * t) * norm.cdf(d1)
                          - K * np.exp(-r * t) * norm.cdf(d2))
        return float(K * np.exp(-r * t) * norm.cdf(-d2)
                      - S * np.exp(-q * t) * norm.cdf(-d1))

    def _bsm_iv_solve(price_arr, S_arr, K_arr, t_arr, r_arr, q_arr, flag_arr):
        """Per-row Brent IV solver. Bracket [1e-6, 5.0] = 0.0001%..500% vol.
        Returns NaN where the solver fails (deep OTM/ITM with vega ~ 0,
        price outside no-arbitrage bounds, etc.)."""
        out_iv = np.full(len(price_arr), np.nan, dtype="float64")
        for i in range(len(price_arr)):
            S, K, t, r, q = S_arr[i], K_arr[i], t_arr[i], r_arr[i], q_arr[i]
            tgt = float(price_arr[i])
            flg = flag_arr[i]
            def f(sigma):
                return _bsm_price_scalar(S, K, t, r, q, sigma, flg) - tgt
            try:
                out_iv[i] = brentq(f, 1e-6, 5.0, xtol=1e-6, maxiter=100)
            except (ValueError, RuntimeError):
                # Brent's bracket failed (price outside no-arb bounds, etc.)
                out_iv[i] = np.nan
        return out_iv

    def _bsm_greeks_vec(S, K, t, r, q, sigma, flag):
        """Vectorized BSM Greeks. Returns (delta, gamma, theta, vega, rho).
        Conventions match py_vollib_vectorized:
          - vega: per 1% change in sigma → divided by 100
          - rho:  per 1% change in r     → divided by 100
          - theta: per CALENDAR day      → divided by 365
        """
        # Mask non-finite sigma; carry NaN through.
        with np.errstate(divide="ignore", invalid="ignore"):
            sqrt_t = np.sqrt(t)
            d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
            d2 = d1 - sigma * sqrt_t
            n_d1 = norm.cdf(d1)
            n_d2 = norm.cdf(d2)
            nn_d1 = norm.cdf(-d1)
            nn_d2 = norm.cdf(-d2)
            pdf_d1 = norm.pdf(d1)
            is_call = flag == "c"

            delta = np.where(is_call,
                              np.exp(-q * t) * n_d1,
                              -np.exp(-q * t) * nn_d1)
            gamma = np.exp(-q * t) * pdf_d1 / (S * sigma * sqrt_t)
            # Theta (annualised), then convert to per-calendar-day below.
            term1 = -(S * np.exp(-q * t) * pdf_d1 * sigma) / (2.0 * sqrt_t)
            theta_call = term1 - r * K * np.exp(-r * t) * n_d2 + q * S * np.exp(-q * t) * n_d1
            theta_put  = term1 + r * K * np.exp(-r * t) * nn_d2 - q * S * np.exp(-q * t) * nn_d1
            theta_annual = np.where(is_call, theta_call, theta_put)
            theta = theta_annual / 365.0
            vega = (S * np.exp(-q * t) * pdf_d1 * sqrt_t) / 100.0  # per 1% sigma
            rho_call = (K * t * np.exp(-r * t) * n_d2) / 100.0     # per 1% r
            rho_put  = -(K * t * np.exp(-r * t) * nn_d2) / 100.0
            rho = np.where(is_call, rho_call, rho_put)
        return delta, gamma, theta, vega, rho

    iv = _bsm_iv_solve(
        sub["price"].values,
        sub["S"].values,
        sub["K"].values,
        sub["t"].values,
        sub["r"].values,
        sub["q"].values,
        sub["flag"].values,
    )
    iv = np.where((iv > 0) & np.isfinite(iv), iv, np.nan)

    deltas, gammas, thetas, vegas, rhos = _bsm_greeks_vec(
        sub["S"].values, sub["K"].values, sub["t"].values,
        sub["r"].values, sub["q"].values, iv, sub["flag"].values,
    )

    # Write into the sidecar columns at the right positions.
    out.loc[valid, "implied_volatility_computed"] = iv
    out.loc[valid, "delta_computed"] = deltas
    out.loc[valid, "gamma_computed"] = gammas
    out.loc[valid, "theta_computed"] = thetas
    out.loc[valid, "vega_computed"] = vegas
    out.loc[valid, "rho_computed"] = rhos

    n_solved = int(np.isfinite(iv).sum())
    log.info(
        "compute_greeks_from_prices: solved %d / %d (%.0f%%) at spot=%.2f r=%.4f q=%.4f",
        n_solved, int(valid.sum()), 100.0 * n_solved / max(1, int(valid.sum())),
        spot, risk_free, dividend_yield,
    )
    return out


# ── high-level orchestration ────────────────────────────────────────────────

def _has_existing_computed_greeks(df: pd.DataFrame) -> bool:
    """Return True if the DataFrame already has computed Greeks for this chain.

    Treats NaN as "missing" — important because the AV NaN floats appear
    ``IS NOT NULL`` in SQL but are not real values.
    """
    if "gamma_computed" not in df.columns:
        return False
    col = pd.to_numeric(df["gamma_computed"], errors="coerce")
    return bool(col.notna().any() and np.isfinite(col).any())


def enrich_av_chain_with_greeks(
    df: pd.DataFrame,
    ticker: str,
    snapshot_date,
) -> pd.DataFrame:
    """High-level orchestration entry point.

    Looks up the risk-free rate and dividend yield, derives the spot price
    via a three-tier cascade (Cloud SQL ``market_data_daily`` → put-call
    parity → SPY × 10), computes BSM Greeks, and returns the chain with
    the six ``*_computed`` sidecar columns populated. The original
    ``delta``/``gamma``/etc. columns are never touched.

    No-op for tickers outside :data:`COMPUTE_GREEKS_TICKERS`. Idempotent
    when computed Greeks are already present.

    Parameters
    ----------
    df             : option chain DataFrame (as produced by the AV fetcher's
                     ``_normalize_av_response``).
    ticker         : 'SPX', 'NDX', etc. Ignored if not in
                     :data:`COMPUTE_GREEKS_TICKERS`.
    snapshot_date  : ``datetime.date`` (or string) of the snapshot.

    Returns
    -------
    DataFrame — same row count, with sidecar columns added/populated.
    """
    if df.empty:
        return df

    ticker_u = ticker.upper()
    if ticker_u not in COMPUTE_GREEKS_TICKERS:
        return df  # SPY/IWM/QQQ already have AV-provided Greeks

    if _has_existing_computed_greeks(df):
        log.debug("%s %s: computed Greeks already present — skip", ticker_u, snapshot_date)
        return df

    if isinstance(snapshot_date, str):
        snapshot_date = pd.to_datetime(snapshot_date).date()
    elif isinstance(snapshot_date, datetime):
        snapshot_date = snapshot_date.date()

    try:
        risk_free, div_yld = get_rate_and_yield(snapshot_date)
    except RateLookupError as exc:
        # Rule 3.7: an explicit unavailable state, not Greeks at a made-up
        # rate. The chain is returned with the vendor's own Greeks and
        # WITHOUT the `*_computed` sidecar columns, so a caller can tell the
        # difference -- which it could not when this substituted a 2024
        # constant. ERROR, not debug: this is a pipeline outage.
        log.error("%s %s: skipping computed Greeks -- %s",
                  ticker_u, snapshot_date, exc)
        return df

    # Three-tier spot cascade.
    spot: Optional[float] = None
    spot_source = "none"
    spot = _get_close_price(ticker_u, snapshot_date)
    if spot is not None and spot > 0:
        spot_source = "market_data_daily"

    if spot is None or spot <= 0:
        spot = derive_spot_from_chain(df, snapshot_date, risk_free, div_yld)
        if spot is not None and spot > 0:
            spot_source = "put_call_parity"

    if (spot is None or spot <= 0) and ticker_u in ("SPX", "SPXW"):
        spy = _get_close_price("SPY", snapshot_date)
        if spy is not None and spy > 0:
            spot = spy * 10.0
            spot_source = "spy_proxy"
            log.warning("%s %s: falling back to SPY*10 = %.2f",
                        ticker_u, snapshot_date, spot)

    if spot is None or spot <= 0:
        log.warning("No spot derivable for %s %s — leaving Greeks NaN",
                    ticker_u, snapshot_date)
        for col in COMPUTED_COLS:
            if col not in df.columns:
                df = df.copy()
                df[col] = np.nan
        return df

    log.info("%s %s: spot=%.2f from %s, r=%.4f q=%.4f",
             ticker_u, snapshot_date, spot, spot_source, risk_free, div_yld)

    return compute_greeks_from_prices(
        df,
        spot=spot,
        snapshot_date=snapshot_date,
        risk_free=risk_free,
        dividend_yield=div_yld,
    )
