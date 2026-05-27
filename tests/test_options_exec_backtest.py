"""Tests for lib/options_exec_backtest.

Coverage:
  - BSM price parity vs py_vollib_vectorized (the ground-truth library
    already used by lib/options_greeks). 10-point grid covering ATM, ITM,
    OTM, near-expiry, and long-dated.
  - bs_price degenerate paths: zero/negative sigma, expired, NaN inputs.
  - atm_strike: ATM selection + OTM offset + out-of-band offset.
  - years_to_expiry: 0DTE morning, EOD, T+1 morning, edge cases.
"""
from __future__ import annotations
import math

import numpy as np
import pandas as pd
import pytest

from lib.options_exec_backtest.pricing import (
    MIN_T_YEARS, atm_strike, bs_price, bs_price_vec, years_to_expiry,
)


# ─────────────────────────────────────────── BSM parity ───────────────────────────────────

def _pvv_price(S, K, T, sigma, r, q, kind):
    """Reference price from py_vollib_vectorized. Loaded lazily because the
    library isn't a hard dep — if missing, the parity test is skipped."""
    try:
        from py_vollib_vectorized.api import price_dataframe
    except ImportError:
        pytest.skip("py_vollib_vectorized not installed")
    flag = "c" if kind == "call" else "p"
    df = pd.DataFrame({
        "S": [S], "K": [K], "t": [T], "r": [r], "q": [q], "flag": [flag],
        "price": [0.0],  # not used for forward price; library wants the col
    })
    # The vectorized API exposes black_scholes_merton via `price`:
    from py_vollib.black_scholes_merton import black_scholes_merton as bsm_ref
    return float(bsm_ref(flag, S, K, T, r, sigma, q))


PARITY_GRID = [
    # (S, K, T, sigma, r, q, kind, label)
    (450.0, 450.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "ATM 1DTE"),
    (450.0, 450.0, 6.5 / (365 * 24), 0.20, 0.045, 0.013, "call", "ATM 6.5h-0DTE"),
    (450.0, 455.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "5-OTM 1DTE call"),
    (450.0, 445.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "5-ITM 1DTE call"),
    (450.0, 450.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "ATM 1DTE put"),
    (450.0, 455.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "5-ITM 1DTE put"),
    (450.0, 445.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "5-OTM 1DTE put"),
    (450.0, 450.0, 30.0 / 365.0, 0.18, 0.045, 0.013, "call", "ATM 30DTE"),
    (450.0, 470.0, 30.0 / 365.0, 0.18, 0.045, 0.013, "call", "20-OTM 30DTE"),
    (200.0, 200.0, 7.0 / 365.0, 0.30, 0.045, 0.0, "call", "ATM 7DTE IWM-ish"),
]


@pytest.mark.parametrize("S,K,T,sigma,r,q,kind,label", PARITY_GRID)
def test_bs_price_parity(S, K, T, sigma, r, q, kind, label):
    """Our BSM price must match py_vollib's BSM to within 1e-6 — the
    Greeks engine elsewhere in the repo uses py_vollib, so any drift
    would create a self-inconsistency."""
    expected = _pvv_price(S, K, T, sigma, r, q, kind)
    actual = bs_price(S, K, T, sigma, r, q, kind=kind)
    assert math.isclose(actual, expected, abs_tol=1e-6), (
        f"{label}: expected {expected:.8f}, got {actual:.8f}, diff "
        f"{actual - expected:.8e}"
    )


def test_bs_price_vec_matches_scalar():
    """Vector BSM must match scalar BSM elementwise."""
    S = np.array([450.0, 450.0, 450.0, 200.0])
    K = np.array([450.0, 455.0, 445.0, 200.0])
    T = np.array([1, 1, 1, 7], dtype=float) / 365.0
    sigma = np.array([0.20, 0.20, 0.20, 0.30])
    r = np.array([0.045, 0.045, 0.045, 0.045])
    q = np.array([0.013, 0.013, 0.013, 0.0])
    vec_call = bs_price_vec(S, K, T, sigma, r, q, kind="call")
    for i in range(len(S)):
        scalar = bs_price(S[i], K[i], T[i], sigma[i], r[i], q[i], kind="call")
        assert math.isclose(vec_call[i], scalar, abs_tol=1e-9), (
            f"row {i}: vec {vec_call[i]} vs scalar {scalar}"
        )


# ─────────────────────────────────────────── Degenerate paths ─────────────────────────────

def test_bs_price_zero_sigma_call_intrinsic():
    """sigma=0 → degenerates to discounted intrinsic value."""
    # ITM call: intrinsic = max(0, S-K) = 5
    p = bs_price(S=450, K=445, T=1 / 365, sigma=0.0, r=0.045, q=0.0, kind="call")
    # Discounted by e^(-rT): 5 * e^(-0.045/365) ≈ 4.99938
    assert 4.99 < p < 5.01


def test_bs_price_zero_sigma_otm_zero():
    """OTM with zero vol → 0."""
    p = bs_price(S=450, K=460, T=1 / 365, sigma=0.0, r=0.045, q=0.0, kind="call")
    assert p == 0.0


def test_bs_price_nan_inputs():
    """NaN underlying / strike → NaN price (not 0 — never silently lie)."""
    p = bs_price(S=float("nan"), K=450, T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)
    p = bs_price(S=450, K=float("nan"), T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)


def test_bs_price_negative_underlying_nan():
    """Negative S → NaN (never silently coerce)."""
    p = bs_price(S=-1.0, K=450, T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)


def test_bs_price_expired_floored():
    """T <= 0 floored to MIN_T_YEARS so the formula doesn't divide by zero."""
    p_zero = bs_price(S=450, K=450, T=0.0, sigma=0.2, r=0.045, q=0.0, kind="call")
    p_one_min = bs_price(S=450, K=450, T=MIN_T_YEARS, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isclose(p_zero, p_one_min, abs_tol=1e-9)
    assert p_zero > 0  # ATM with any vol > 0


# ─────────────────────────────────────────── ATM strike ───────────────────────────────────

def test_atm_strike_exact_match():
    s = atm_strike(450.0, np.array([445, 450, 455]))
    assert s == 450.0


def test_atm_strike_closest():
    """Spot is 451.6; closest strike is 452."""
    s = atm_strike(451.6, np.array([445, 450, 452, 455]))
    assert s == 452.0


def test_atm_strike_otm_offset():
    """+1 from ATM 450 should be the next strike up (the spec is generic —
    engine knows whether call or put and offsets accordingly)."""
    s = atm_strike(450.0, np.array([440, 445, 450, 455, 460]), otm_offset=1)
    assert s == 455.0


def test_atm_strike_out_of_band_nan():
    """Asking for +5-OTM when only 1 strike is above ATM → NaN."""
    s = atm_strike(450.0, np.array([445, 450, 455]), otm_offset=5)
    assert math.isnan(s)


def test_atm_strike_empty_list_nan():
    s = atm_strike(450.0, np.array([]))
    assert math.isnan(s)


# ─────────────────────────────────────────── years_to_expiry ──────────────────────────────

def test_years_to_expiry_0dte_morning():
    """0DTE at 9:30 ET (14:30 UTC EDT) on the expiration date — about
    5.5 hours until 20:00 UTC = 5.5/24/365 ≈ 6.28e-4 years."""
    now = pd.Timestamp("2024-06-03 13:30:00", tz="UTC")  # 9:30 AM ET on a non-DST day
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    # 20:00 UTC - 13:30 UTC = 6.5 hours → 6.5 / (365*24) = 7.42e-4
    assert 7.0e-4 < y < 7.8e-4


def test_years_to_expiry_at_close():
    """At 20:00 UTC on expiration day, T should floor at MIN_T_YEARS."""
    now = pd.Timestamp("2024-06-03 20:00:00", tz="UTC")
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    assert y == MIN_T_YEARS


def test_years_to_expiry_one_day():
    """24h to expiry → ~1/365 years (give or take 1h ET/EDT slop)."""
    now = pd.Timestamp("2024-06-02 20:00:00", tz="UTC")
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    assert 0.00273 < y < 0.00274


def test_years_to_expiry_bad_input_nan():
    y = years_to_expiry("not-a-ts", pd.Timestamp("2024-06-03").date())
    assert math.isnan(y)


# ─────────────────────────────────────────── Sanity: BSM walk through trade ───────────────

def test_bsm_walk_underlying_rises_call_premium_rises():
    """Long call: underlying rises → premium rises. Sanity for the engine."""
    p0 = bs_price(S=450.0, K=450.0, T=6.5 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    p1 = bs_price(S=451.0, K=450.0, T=6.0 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    # Even with 30 min of theta decay, a $1 underlying rise on a $1-wide
    # ATM 0DTE call should net-positive (delta ~0.5, theta loss ~$0.10 over 30 min)
    assert p1 > p0


def test_bsm_walk_theta_decay_only_premium_falls():
    """Same underlying, less time-to-expiry → call premium falls (positive theta cost
    to a long option holder)."""
    p0 = bs_price(S=450.0, K=450.0, T=6.5 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    p1 = bs_price(S=450.0, K=450.0, T=3.0 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    assert p1 < p0
