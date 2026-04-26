"""
Unit tests for :mod:`lib.options_greeks` — Black-Scholes-Merton math, put-call
parity spot derivation, and the high-level ``enrich_av_chain_with_greeks``
no-op path.

These tests are hermetic — no Cloud SQL, no FRED, no AlphaVantage. They pin
known-good textbook BSM values so a sign error or formula bug fails CI before
any production backfill runs.

Skipped automatically if ``py_vollib_vectorized`` is not installed (the math
tests need it; the no-op tests do not).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# Skip the math-heavy tests if the optional dependency isn't installed.
py_vollib_vectorized = pytest.importorskip(
    "py_vollib_vectorized",
    reason="py_vollib_vectorized not installed — install with "
           "`pip install py_vollib_vectorized` before running these tests.",
)

from lib.options_greeks import (
    COMPUTE_GREEKS_TICKERS,
    COMPUTED_COLS,
    compute_greeks_from_prices,
    derive_spot_from_chain,
    enrich_av_chain_with_greeks,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _bsm_price(flag, S, K, t, r, q, sigma):
    """Reference Black-Scholes-Merton price.

    py_vollib_vectorized monkey-patches black_scholes_merton to return a
    DataFrame even for scalar inputs, so we extract the scalar manually.
    """
    from py_vollib.black_scholes_merton import black_scholes_merton
    val = black_scholes_merton(flag, S, K, t, r, sigma, q)
    if hasattr(val, "iloc"):
        return float(val.iloc[0, 0]) if hasattr(val.iloc[0], "__len__") else float(val.iloc[0])
    if hasattr(val, "__len__"):
        return float(val[0])
    return float(val)


def _bsm_call_price(S, K, t, r, q, sigma):
    return _bsm_price("c", S, K, t, r, q, sigma)


def _bsm_put_price(S, K, t, r, q, sigma):
    return _bsm_price("p", S, K, t, r, q, sigma)


def _build_textbook_chain(spot, strikes, snapshot, expiration, r, q, sigma):
    """Build a synthetic chain whose mid prices come from BSM-with-known-IV.

    compute_greeks_from_prices() should solve back the same sigma and produce
    Greeks consistent with the analytical formulas.
    """
    t = (expiration - snapshot).days / 365.0
    rows = []
    for k in strikes:
        c = _bsm_call_price(spot, k, t, r, q, sigma)
        p = _bsm_put_price(spot, k, t, r, q, sigma)
        rows.append({
            "option_type": "calls",
            "strike": float(k),
            "expiration": expiration,
            "bid": c - 0.05,
            "ask": c + 0.05,
            "last_price": c,
        })
        rows.append({
            "option_type": "puts",
            "strike": float(k),
            "expiration": expiration,
            "bid": p - 0.05,
            "ask": p + 0.05,
            "last_price": p,
        })
    return pd.DataFrame(rows)


# ── Math: textbook BSM example ──────────────────────────────────────────────

def test_compute_greeks_textbook_call():
    """ATM European call, dividend-paying.

    Hull Ch. 14 textbook values:
        S = 100, K = 100, T = 0.25y, r = 0.05, q = 0.02, sigma = 0.20
    Expected (approximate, verified against py_vollib directly):
        call price ≈ 4.05
        delta ≈ 0.555
        gamma ≈ 0.039
        vega  ≈ 19.7  (per unit sigma; py_vollib returns per 1% so /100)
    """
    spot, sigma, r, q = 100.0, 0.20, 0.05, 0.02
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=int(0.25 * 365))
    df = _build_textbook_chain(spot, [100.0], snapshot, expiration, r, q, sigma)

    out = compute_greeks_from_prices(
        df, spot=spot, snapshot_date=snapshot, risk_free=r, dividend_yield=q,
    )

    # All sidecar columns exist
    for col in COMPUTED_COLS:
        assert col in out.columns

    # Pull the call row
    call_row = out[out["option_type"] == "calls"].iloc[0]
    assert call_row["implied_volatility_computed"] == pytest.approx(sigma, rel=0.02)
    assert call_row["delta_computed"] == pytest.approx(0.555, abs=0.02)
    assert call_row["gamma_computed"] == pytest.approx(0.039, abs=0.005)
    # vega in py_vollib is per 1% change: ~0.197
    assert call_row["vega_computed"] == pytest.approx(0.197, abs=0.02)

    # Put has negative delta in BSM-with-q convention
    put_row = out[out["option_type"] == "puts"].iloc[0]
    assert put_row["delta_computed"] < 0
    assert put_row["gamma_computed"] == pytest.approx(call_row["gamma_computed"], abs=1e-4)


def test_iv_solver_recovers_input_sigma_across_strikes():
    """For a chain priced at sigma=0.25, the IV solver should recover ~0.25
    on every liquid strike (within 1%)."""
    spot, sigma, r, q = 4500.0, 0.25, 0.045, 0.013
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=30)
    strikes = [4400, 4450, 4500, 4550, 4600]
    df = _build_textbook_chain(spot, strikes, snapshot, expiration, r, q, sigma)

    out = compute_greeks_from_prices(
        df, spot=spot, snapshot_date=snapshot, risk_free=r, dividend_yield=q,
    )
    iv = out["implied_volatility_computed"].dropna()
    assert len(iv) == len(df)
    # Allow small numerical noise.
    assert (iv - sigma).abs().max() < 0.01


def test_put_call_parity_invariant():
    """C - P = S·e^{-qT} - K·e^{-rT}. Check on a few strikes."""
    spot, sigma, r, q = 4500.0, 0.20, 0.045, 0.013
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=45)
    strikes = [4400, 4500, 4600]
    df = _build_textbook_chain(spot, strikes, snapshot, expiration, r, q, sigma)

    t = (expiration - snapshot).days / 365.0
    for k in strikes:
        c = df[(df["option_type"] == "calls") & (df["strike"] == k)]["last_price"].iloc[0]
        p = df[(df["option_type"] == "puts") & (df["strike"] == k)]["last_price"].iloc[0]
        lhs = c - p
        rhs = spot * math.exp(-q * t) - k * math.exp(-r * t)
        assert lhs == pytest.approx(rhs, abs=1e-3)


def test_deep_otm_call_delta_near_zero():
    """Deep-OTM call: delta should approach 0, IV solver may return NaN."""
    spot, sigma, r, q = 4500.0, 0.20, 0.045, 0.013
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=14)
    df = _build_textbook_chain(spot, [6000.0], snapshot, expiration, r, q, sigma)

    out = compute_greeks_from_prices(
        df, spot=spot, snapshot_date=snapshot, risk_free=r, dividend_yield=q,
    )
    call_row = out[out["option_type"] == "calls"].iloc[0]
    # Delta near zero or NaN are both acceptable
    if not pd.isna(call_row["delta_computed"]):
        assert call_row["delta_computed"] < 0.05


def test_deep_itm_call_delta_near_one():
    """Deep-ITM call: delta should approach 1."""
    spot, sigma, r, q = 4500.0, 0.20, 0.045, 0.013
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=14)
    df = _build_textbook_chain(spot, [3500.0], snapshot, expiration, r, q, sigma)

    out = compute_greeks_from_prices(
        df, spot=spot, snapshot_date=snapshot, risk_free=r, dividend_yield=q,
    )
    call_row = out[out["option_type"] == "calls"].iloc[0]
    if not pd.isna(call_row["delta_computed"]):
        assert call_row["delta_computed"] > 0.95


# ── derive_spot_from_chain ──────────────────────────────────────────────────

def test_derive_spot_from_chain_recovers_textbook_spot():
    """A synthetic chain priced at S=4500 should yield ~4500 via PCP."""
    spot, sigma, r, q = 4500.0, 0.20, 0.045, 0.013
    snapshot = date(2026, 4, 14)
    expiration = snapshot + timedelta(days=30)
    strikes = [4400, 4450, 4500, 4550, 4600]
    df = _build_textbook_chain(spot, strikes, snapshot, expiration, r, q, sigma)

    derived = derive_spot_from_chain(
        df, snapshot_date=snapshot, risk_free=r, dividend_yield=q, n_strikes=5,
    )
    assert derived is not None
    assert derived == pytest.approx(spot, rel=1e-3)


def test_derive_spot_returns_none_when_no_valid_pairs():
    df = pd.DataFrame(columns=["option_type", "strike", "expiration", "bid", "ask", "last_price"])
    assert derive_spot_from_chain(df, snapshot_date=date(2026, 4, 14),
                                  risk_free=0.045, dividend_yield=0.013) is None


# ── enrich_av_chain_with_greeks: the no-op cases ────────────────────────────

def test_enrich_noop_for_non_index_ticker():
    """SPY/IWM/QQQ should pass through untouched (no sidecar columns added)."""
    df = pd.DataFrame([{
        "option_type": "calls", "strike": 500.0,
        "expiration": date(2026, 5, 16),
        "bid": 1.0, "ask": 1.1, "last_price": 1.05,
    }])
    out = enrich_av_chain_with_greeks(df, ticker="SPY", snapshot_date=date(2026, 4, 14))
    # Untouched — sidecar columns shouldn't be added for non-compute tickers.
    assert "gamma_computed" not in out.columns


def test_enrich_idempotent_when_already_populated():
    """A chain that already has finite gamma_computed values should be skipped."""
    df = pd.DataFrame([{
        "option_type": "calls", "strike": 4500.0,
        "expiration": date(2026, 5, 16),
        "bid": 50.0, "ask": 51.0, "last_price": 50.5,
        "gamma_computed": 0.0001,  # already populated
        "delta_computed": 0.5,
    }])
    out = enrich_av_chain_with_greeks(df, ticker="SPX", snapshot_date=date(2026, 4, 14))
    # Sentinel values preserved — function returned early.
    assert out.iloc[0]["gamma_computed"] == 0.0001


def test_compute_greeks_tickers_set():
    assert "SPX" in COMPUTE_GREEKS_TICKERS
    assert "SPY" not in COMPUTE_GREEKS_TICKERS
    assert "IWM" not in COMPUTE_GREEKS_TICKERS
