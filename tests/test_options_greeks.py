"""
Unit tests for :mod:`lib.options_greeks` — Black-Scholes-Merton math, put-call
parity spot derivation, and the high-level ``enrich_av_chain_with_greeks``
no-op path.

These tests are hermetic — no Cloud SQL, no FRED, no AlphaVantage. They pin
known-good textbook BSM values so a sign error or formula bug fails CI before
any production backfill runs.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# DO NOT importorskip py_vollib_vectorized here. lib/options_greeks no
# longer uses it (replaced with scipy on 2026-05-31 after py_vollib_vectorized's
# numba decoration started failing with "cannot type infer runaway recursion"
# on the current numba version). Importing py_vollib_vectorized at all in
# this process monkey-patches py_vollib.black_scholes_merton globally and
# breaks the _bsm_price helper below. The test now requires only scipy +
# py_vollib (the unpatched plain-Python library), both standard deps.

from lib.options_greeks import (
    COMPUTE_GREEKS_TICKERS,
    COMPUTED_COLS,
    compute_greeks_from_prices,
    derive_spot_from_chain,
    enrich_av_chain_with_greeks,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _bsm_price(flag, S, K, t, r, q, sigma):
    """Reference Black-Scholes-Merton price via scipy.

    py_vollib_vectorized (still installed per requirements.txt) monkey-patches
    py_vollib.black_scholes_merton at import time to route through a Numba JIT
    path.  Numba ≥0.65 cannot compile the recursive black() helper
    ("cannot type infer runaway recursion"), causing this test to fail
    intermittently whenever py_vollib_vectorized is imported first by another
    test in the same pytest session.  Using scipy makes this helper immune to
    that side-effect.  The math is identical (BSM, Hull Ch. 14).
    """
    from scipy.stats import norm
    if t <= 0:
        intrinsic = max(S - K, 0.0) if flag == "c" else max(K - S, 0.0)
        return float(intrinsic)
    if sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    fwd = S * math.exp(-q * t)
    disc = math.exp(-r * t)
    if flag == "c":
        return float(fwd * norm.cdf(d1) - K * disc * norm.cdf(d2))
    return float(K * disc * norm.cdf(-d2) - fwd * norm.cdf(-d1))


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


# ──────────────────────────────────────────────────────────────────────
# get_rate_and_yield — Cloud SQL fallback chain
#
# Wrong rate ⇒ wrong IV solve across the entire chain. Tests verify
# every fallback layer:
#   1. Direct hit on `daily_rates` for `:date`
#   2. Fallback to most-recent date <= target (holiday/warmup bridge)
#   3. Cloud SQL exception → defaults
#   4. Empty-everything → defaults
#   5. NULL columns in row → per-column default
# ──────────────────────────────────────────────────────────────────────


def _patch_query_to_dataframe(monkeypatch, fn_or_df):
    """Patch `gcp.database.query_to_dataframe`. Accepts:
       - a callable (sql, params) → DataFrame
       - a DataFrame (returned for every call)
       - an Exception class/instance (raised every call)
    The lru_cache on `get_rate_and_yield` is also cleared so tests
    don't pollute each other."""
    from lib import options_greeks as og
    og.get_rate_and_yield.cache_clear()

    if isinstance(fn_or_df, type) and issubclass(fn_or_df, BaseException):
        def fake(sql, params=None): raise fn_or_df()
    elif isinstance(fn_or_df, BaseException):
        def fake(sql, params=None): raise fn_or_df
    elif callable(fn_or_df):
        fake = fn_or_df
    else:
        def fake(sql, params=None): return fn_or_df.copy()

    # The function does `from gcp.database import query_to_dataframe`
    # at call time — patch the source module so the late import resolves
    # to our fake.
    import gcp.database
    monkeypatch.setattr(gcp.database, "query_to_dataframe", fake)


def test_get_rate_and_yield_direct_hit(monkeypatch):
    """Exact-date row in daily_rates → use those values."""
    from lib.options_greeks import get_rate_and_yield

    _patch_query_to_dataframe(
        monkeypatch,
        pd.DataFrame([{"dgs3mo": 0.052, "sp500_div_yld": 0.018}]),
    )
    r, q = get_rate_and_yield(date(2026, 4, 14))
    assert r == 0.052
    assert q == 0.018


def test_get_rate_and_yield_fallback_to_most_recent(monkeypatch):
    """No row for target date → backstop query for most-recent <= target.
    Tests verify the second query path is taken."""
    from lib.options_greeks import get_rate_and_yield

    call_count = {"n": 0}

    def fake(sql, params=None):
        call_count["n"] += 1
        # First call (date = :d) returns empty, second (<= :d ORDER BY)
        # returns the most-recent prior row
        if call_count["n"] == 1:
            return pd.DataFrame()
        return pd.DataFrame([{"dgs3mo": 0.045, "sp500_div_yld": 0.020}])

    _patch_query_to_dataframe(monkeypatch, fake)
    r, q = get_rate_and_yield(date(2026, 4, 13))  # Sunday — no row
    assert r == 0.045
    assert q == 0.020
    assert call_count["n"] == 2, "second (backstop) query must run"


def test_get_rate_and_yield_falls_back_when_table_missing(monkeypatch):
    """`daily_rates` table doesn't exist → defaults, no crash."""
    from lib.options_greeks import (
        get_rate_and_yield, _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD,
    )

    _patch_query_to_dataframe(
        monkeypatch,
        RuntimeError('relation "daily_rates" does not exist'),
    )
    r, q = get_rate_and_yield(date(2026, 4, 14))
    assert r == _DEFAULT_RISK_FREE
    assert q == _DEFAULT_DIV_YIELD


def test_get_rate_and_yield_falls_back_when_both_queries_empty(monkeypatch):
    """Table exists but no rows at all (fresh deploy, FRED fetch
    hasn't run yet). Both queries return empty → defaults."""
    from lib.options_greeks import (
        get_rate_and_yield, _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD,
    )

    _patch_query_to_dataframe(monkeypatch, pd.DataFrame())
    r, q = get_rate_and_yield(date(2026, 4, 15))
    assert r == _DEFAULT_RISK_FREE
    assert q == _DEFAULT_DIV_YIELD


def test_get_rate_and_yield_partial_null_per_column_default(monkeypatch):
    """Row found but one column is NULL (e.g. div_yld backfill lagged).
    Use the row's value for the present column and default for the NULL."""
    from lib.options_greeks import (
        get_rate_and_yield, _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD,
    )

    _patch_query_to_dataframe(
        monkeypatch,
        pd.DataFrame([{"dgs3mo": 0.06, "sp500_div_yld": None}]),
    )
    r, q = get_rate_and_yield(date(2026, 4, 16))
    assert r == 0.06
    assert q == _DEFAULT_DIV_YIELD


# ──────────────────────────────────────────────────────────────────────
# enrich_av_chain_with_greeks — three-tier spot cascade
# ──────────────────────────────────────────────────────────────────────


def test_enrich_uses_market_data_daily_when_available(monkeypatch):
    """Tier 1: market_data_daily close — used directly without any
    chain-derivation work."""
    from lib import options_greeks as og

    monkeypatch.setattr(og, "_get_close_price", lambda t, d: 5800.0)
    monkeypatch.setattr(
        og, "get_rate_and_yield", lambda d: (0.05, 0.013),
    )
    derive_calls = {"n": 0}
    def boom(*a, **k): derive_calls["n"] += 1; return None
    monkeypatch.setattr(og, "derive_spot_from_chain", boom)

    # Minimal SPX chain — strikes around 5800 so IV solves
    df = pd.DataFrame([
        {"option_type": "calls", "strike": 5800.0,
         "expiration": date(2026, 5, 16),
         "bid": 60.0, "ask": 62.0, "last_price": 61.0,
         "delta": None, "gamma": None, "theta": None,
         "vega": None, "rho": None, "implied_volatility": None},
    ])
    og.enrich_av_chain_with_greeks(
        df, ticker="SPX", snapshot_date=date(2026, 4, 14),
    )
    assert derive_calls["n"] == 0, "tier-2 derivation should be skipped"


def test_enrich_falls_back_to_chain_derivation(monkeypatch):
    """Tier 2: market_data_daily missing → derive from put-call parity."""
    from lib import options_greeks as og

    monkeypatch.setattr(og, "_get_close_price", lambda t, d: None)  # tier 1 miss
    monkeypatch.setattr(og, "get_rate_and_yield", lambda d: (0.05, 0.013))
    derive_called = {"n": 0}
    def fake_derive(df, snap, r, q):
        derive_called["n"] += 1
        return 5800.0
    monkeypatch.setattr(og, "derive_spot_from_chain", fake_derive)

    df = pd.DataFrame([
        {"option_type": "calls", "strike": 5800.0,
         "expiration": date(2026, 5, 16),
         "bid": 60.0, "ask": 62.0, "last_price": 61.0,
         "delta": None, "gamma": None, "theta": None,
         "vega": None, "rho": None, "implied_volatility": None},
    ])
    og.enrich_av_chain_with_greeks(
        df, ticker="SPX", snapshot_date=date(2026, 4, 14),
    )
    assert derive_called["n"] == 1, "tier-2 must run when tier-1 returns None"


def test_enrich_spx_falls_back_to_spy_x10(monkeypatch):
    """Tier 3: SPX-only fallback. Both tier-1 and tier-2 fail; SPY
    close * 10 is used as a last resort. NDX/non-SPX tickers do NOT
    take this path."""
    from lib import options_greeks as og

    # SPX direct close fails; SPY close = 580 → spot = 5800
    def fake_close(ticker, target_date):
        if ticker.upper() == "SPY":
            return 580.0
        return None

    monkeypatch.setattr(og, "_get_close_price", fake_close)
    monkeypatch.setattr(og, "get_rate_and_yield", lambda d: (0.05, 0.013))
    monkeypatch.setattr(og, "derive_spot_from_chain", lambda *a, **k: None)

    captured_spot: dict = {}

    def fake_compute(df, *, spot, snapshot_date, risk_free, dividend_yield):
        captured_spot["spot"] = spot
        return df

    monkeypatch.setattr(og, "compute_greeks_from_prices", fake_compute)

    df = pd.DataFrame([
        {"option_type": "calls", "strike": 5800.0,
         "expiration": date(2026, 5, 16),
         "bid": 60.0, "ask": 62.0, "last_price": 61.0},
    ])
    og.enrich_av_chain_with_greeks(
        df, ticker="SPX", snapshot_date=date(2026, 4, 14),
    )
    assert captured_spot["spot"] == 5800.0, "SPY×10 = 5800"


def test_enrich_no_spot_at_all_leaves_greeks_nan(monkeypatch):
    """All three spot tiers fail → return df with NaN sidecar columns,
    NOT a crash. Backfill loops through 1000s of (ticker, date) pairs;
    one missing day shouldn't take down the whole run."""
    from lib import options_greeks as og

    monkeypatch.setattr(og, "_get_close_price", lambda t, d: None)
    monkeypatch.setattr(og, "get_rate_and_yield", lambda d: (0.05, 0.013))
    monkeypatch.setattr(og, "derive_spot_from_chain", lambda *a, **k: None)

    compute_calls = {"n": 0}
    def boom(*a, **k): compute_calls["n"] += 1; return a[0]
    monkeypatch.setattr(og, "compute_greeks_from_prices", boom)

    df = pd.DataFrame([
        {"option_type": "calls", "strike": 5800.0,
         "expiration": date(2026, 5, 16),
         "bid": 60.0, "ask": 62.0, "last_price": 61.0},
    ])
    out = og.enrich_av_chain_with_greeks(
        df, ticker="SPX", snapshot_date=date(2026, 4, 14),
    )
    assert compute_calls["n"] == 0, "compute_greeks must NOT be called"
    # NaN sidecar columns added for the consumer to recognise "no greeks"
    assert "gamma_computed" in out.columns
    assert pd.isna(out.iloc[0]["gamma_computed"])


def test_enrich_ndx_does_not_use_spy_proxy(monkeypatch):
    """NDX is in COMPUTE_GREEKS_TICKERS but the SPY*10 fallback is
    SPX-specific. NDX with all tier-1/2 failed → NaN, not 1/10 of SPY."""
    from lib import options_greeks as og

    spy_calls = {"n": 0}
    def fake_close(ticker, target_date):
        if ticker.upper() == "SPY":
            spy_calls["n"] += 1
            return 580.0
        return None

    monkeypatch.setattr(og, "_get_close_price", fake_close)
    monkeypatch.setattr(og, "get_rate_and_yield", lambda d: (0.05, 0.013))
    monkeypatch.setattr(og, "derive_spot_from_chain", lambda *a, **k: None)
    monkeypatch.setattr(og, "compute_greeks_from_prices", lambda df, **k: df)

    df = pd.DataFrame([
        {"option_type": "calls", "strike": 18000.0,
         "expiration": date(2026, 5, 16),
         "bid": 50.0, "ask": 51.0, "last_price": 50.5},
    ])
    og.enrich_av_chain_with_greeks(
        df, ticker="NDX", snapshot_date=date(2026, 4, 14),
    )
    assert spy_calls["n"] == 0, "SPY proxy is SPX-only"
