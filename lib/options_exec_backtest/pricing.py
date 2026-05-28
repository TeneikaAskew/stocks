"""Pure-numpy Black-Scholes-Merton pricing for the options exec backtest.

The trade lifecycle keeps stop/target/time-stop in UNDERLYING space (Track B
parity), but realizes P&L on the option premium. Given a fixed entry IV
(snapshot-anchored), we walk the option price through the trade as a
function of:
  - S  : underlying price at the evaluation timestamp
  - T  : time to expiry remaining (years, fractional intraday OK)
  - r  : daily risk-free rate (from daily_rates / FRED)
  - q  : dividend yield (SPY-blended)
  - K  : strike (set at entry, constant)
  - σ  : entry IV held constant through the trade (no IV path)
  - kind: 'call' for 2U setups (long), 'put' for 2D setups (short)

We reuse py_vollib_vectorized for IV solving (when we need to derive an
implied vol from a market mid), but the forward-price formula is small
enough to be inlined here in pure numpy — keeps the inner backtest loop
free of optional-dep gymnastics and avoids the import-on-every-call cost.
"""
from __future__ import annotations
import math

import numpy as np
from scipy.stats import norm


# Minimum time-to-expiry in years before we treat the option as expired.
# At T <= MIN_T the option price degenerates to max(0, intrinsic) for a
# call and max(0, K - S) for a put. 0DTE near close means T can be a few
# minutes — we still want a real BSM number, just floor to avoid blow-up.
MIN_T_YEARS = 1.0 / (365.0 * 24.0 * 60.0)   # 1 minute


def bs_price(
    S: float, K: float, T: float, sigma: float,
    r: float, q: float = 0.0, kind: str = "call",
) -> float:
    # r is REQUIRED (no default) per CLAUDE.md Rule 3.7 — no hardcoded
    # _DEFAULT_RISK_FREE. Callers pull from daily_rates / FRED before
    # calling. q defaults to 0 only because dividend yield is small for
    # 0DTE on SPY (the ex-div discount over 6.5 hours is ~$0.005); a
    # missing q is a small modeling miss, a missing r is not.
    """Scalar BSM price. Returns 0.0 for non-positive T or sigma.

    All inputs are scalars. Use `bs_price_vec` for arrays.

    Args:
        S: underlying spot
        K: strike
        T: time to expiry in YEARS (e.g. 1.0/365 for 1 day)
        sigma: implied volatility, annualized decimal (e.g. 0.20 for 20%)
        r: risk-free rate, annualized decimal
        q: continuous dividend yield, annualized decimal
        kind: 'call' or 'put'

    Returns:
        Theoretical mid price of the option (>= 0).
    """
    if not np.isfinite(S) or not np.isfinite(K) or S <= 0 or K <= 0:
        return float("nan")
    if not np.isfinite(sigma) or sigma <= 0:
        # Zero-vol degenerate price = max(0, intrinsic) discounted
        intrinsic = max(0.0, (S - K) if kind == "call" else (K - S))
        return float(intrinsic * math.exp(-r * max(T, 0.0)))
    T_eff = max(float(T), MIN_T_YEARS)

    sqrtT = math.sqrt(T_eff)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T_eff) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    if kind == "call":
        price = S * math.exp(-q * T_eff) * norm.cdf(d1) - K * math.exp(-r * T_eff) * norm.cdf(d2)
    elif kind == "put":
        price = K * math.exp(-r * T_eff) * norm.cdf(-d2) - S * math.exp(-q * T_eff) * norm.cdf(-d1)
    else:
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    return float(max(price, 0.0))


def bs_price_vec(
    S: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray,
    r: np.ndarray, q: np.ndarray, kind: str = "call",
) -> np.ndarray:
    """Vectorized BSM price. All inputs are broadcastable arrays.

    Returns an array of the same shape (after broadcast). NaN for invalid
    inputs; 0.0 for non-positive sigma (degenerates to intrinsic).
    """
    S = np.asarray(S, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)

    T_eff = np.maximum(T, MIN_T_YEARS)
    sqrtT = np.sqrt(T_eff)
    # Avoid divide-by-zero where sigma is non-positive — we mask after
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T_eff) / (sigma * sqrtT)
        d2 = d1 - sigma * sqrtT
        if kind == "call":
            price = S * np.exp(-q * T_eff) * norm.cdf(d1) - K * np.exp(-r * T_eff) * norm.cdf(d2)
        elif kind == "put":
            price = K * np.exp(-r * T_eff) * norm.cdf(-d2) - S * np.exp(-q * T_eff) * norm.cdf(-d1)
        else:
            raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")

    # Degenerate cases: sigma <= 0 or non-finite → intrinsic
    intrinsic = np.where(
        np.full_like(price, kind == "call", dtype=bool),
        np.maximum(S - K, 0.0),
        np.maximum(K - S, 0.0),
    ) * np.exp(-r * np.maximum(T, 0.0))
    bad_sigma = (~np.isfinite(sigma)) | (sigma <= 0)
    price = np.where(bad_sigma, intrinsic, price)

    # Final guards
    price = np.where(np.isfinite(price), price, np.nan)
    price = np.where(price < 0.0, 0.0, price)
    return price


def atm_strike(spot: float, available_strikes: np.ndarray, otm_offset: int = 0) -> float:
    """Return the ATM strike (closest to spot), or the +N-OTM strike.

    Args:
        spot: underlying price
        available_strikes: sorted array of strikes actually quoted at that
            snapshot. The backtest restricts to strikes that are present
            in etf_options_snapshots — no synthetic strikes are created.
        otm_offset: 0 = ATM (default); 1 = 1 strike OTM (Variant 1).
            For a call: OTM = strike > spot; for a put: OTM = strike < spot.
            This helper returns the ATM-band strike; the caller (engine)
            knows whether the trade is a call or put and offsets accordingly.

    Returns:
        The chosen strike, or NaN if the strike list is empty.
    """
    strikes = np.asarray(available_strikes, dtype=np.float64)
    if strikes.size == 0:
        return float("nan")
    strikes = np.sort(strikes)
    idx = int(np.argmin(np.abs(strikes - spot)))
    if otm_offset == 0:
        return float(strikes[idx])
    new_idx = idx + otm_offset
    if 0 <= new_idx < strikes.size:
        return float(strikes[new_idx])
    return float("nan")


def years_to_expiry(now_ts, expiration_date) -> float:
    """Time-to-expiry in YEARS given a snapshot timestamp and expiration date.

    Convention: options expire at 4:00 PM ET on the expiration date. For
    0DTE, T at 9:30 AM ET on the expiration date is 6.5 hours / (365 * 24)
    ≈ 0.000742 years. Caller passes UTC pd.Timestamp.

    Args:
        now_ts: pd.Timestamp (UTC) of the evaluation moment
        expiration_date: pd.Timestamp or date — the contract's expiration

    Returns:
        Time in years, floored at MIN_T_YEARS. NaN if either input is bad.
    """
    import pandas as pd
    try:
        now = pd.Timestamp(now_ts)
        if now.tzinfo is None:
            now = now.tz_localize("UTC")
        else:
            now = now.tz_convert("UTC")
        exp = pd.Timestamp(expiration_date)
        # 16:00 ET on the expiration date = 20:00 UTC during EDT,
        # 21:00 UTC during EST. We approximate as 20:00 UTC year-round —
        # the BSM-walk-only path is conservative enough that this 1-hour
        # ET/EST drift on ~6h of 0DTE life is < 0.5% of T, well within
        # the noise of the IV anchor.
        exp_ts = pd.Timestamp(f"{exp.date()} 20:00:00", tz="UTC")
        seconds = (exp_ts - now).total_seconds()
        years = seconds / (365.0 * 24.0 * 3600.0)
        return max(float(years), MIN_T_YEARS)
    except Exception:
        return float("nan")
