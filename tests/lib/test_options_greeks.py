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
    """Reference Black-Scholes-Merton price using scipy (not py_vollib).

    py_vollib_vectorized auto-imports at Python startup (via its .pth file)
    and monkey-patches py_vollib.black_scholes_merton globally, routing it
    through a numba-decorated path that raises "cannot type infer runaway
    recursion" on Python 3.12 / numba >= 0.65. Using scipy directly avoids
    that poisoned path entirely.  Formula is identical to the production
    _bsm_price_scalar in lib/options_greeks.py so chain prices are
    self-consistent with the IV solver and Greeks.
    """
    from scipy.stats import norm as _norm
    if t <= 0 or sigma <= 0:
        return float(max(S - K, 0.0) if flag == "c" else max(K - S, 0.0))
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if flag == "c":
        return float(S * math.exp(-q * t) * _norm.cdf(d1) - K * math.exp(-r * t) * _norm.cdf(d2))
    return float(K * math.exp(-r * t) * _norm.cdf(-d2) - S * math.exp(-q * t) * _norm.cdf(-d1))


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
# get_rate_and_yield — Cloud SQL lookup, and what it does when it fails
#
# Wrong rate => wrong IV solve across the entire chain, and the output is a
# plausible number either way. This block used to assert that every failure
# path returned the `_DEFAULT_*` constants (a 2024-era rate) at `log.debug`
# level. That was finding C-03 of docs/audits/FALLBACK_AUDIT_2026-05-13.md
# and it stayed open for four months; the tests were pinning the bug.
#
# The contract now:
#   1. exact-date row               -> that row's values
#   2. no exact row                 -> most-recent row at or before (bridges
#                                      weekends, holidays, FRED's 1-2d lag)
#   3. query failed                 -> RateLookupError
#   4. no row at all                -> RateLookupError
#   5. NULL in either column        -> RateLookupError
#   6. backstop row too old         -> RateLookupError
#   7. allow_defaults=True          -> the constants, at WARNING, for the
#                                      caller that explicitly asked
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

    # The function does `from gcp.database import query_to_dataframe_strict`
    # at call time — patch the source module so the late import resolves to
    # our fake. The STRICT helper is the one under test: the swallowing
    # sibling returns an empty DataFrame on a connection error, which is
    # indistinguishable from "no row" and would route a real outage down the
    # missing-data path.
    import gcp.database
    monkeypatch.setattr(gcp.database, "query_to_dataframe_strict", fake)
    monkeypatch.setattr(gcp.database, "query_to_dataframe", fake)


def _rates_row(d, r=0.052, q=0.018):
    """One `daily_rates` row. `date` is read for the staleness check."""
    return pd.DataFrame([{"date": d, "dgs3mo": r, "sp500_div_yld": q}])


def test_get_rate_and_yield_direct_hit(monkeypatch):
    """Exact-date row in daily_rates -> use those values."""
    from lib.options_greeks import get_rate_and_yield

    _patch_query_to_dataframe(monkeypatch, _rates_row(date(2026, 4, 14)))
    r, q = get_rate_and_yield(date(2026, 4, 14))
    assert r == 0.052
    assert q == 0.018


def test_get_rate_and_yield_fallback_to_most_recent(monkeypatch):
    """No row for the target date -> backstop query for most-recent <= target.

    This is the weekend/holiday bridge and stays a normal success path: a
    Sunday has no row and the Friday rate is the right answer.
    """
    from lib.options_greeks import get_rate_and_yield

    calls = {"n": 0}

    def fake(sql, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return pd.DataFrame()
        return _rates_row(date(2026, 4, 10), r=0.045, q=0.020)  # Friday

    _patch_query_to_dataframe(monkeypatch, fake)
    r, q = get_rate_and_yield(date(2026, 4, 12))  # Sunday
    assert (r, q) == (0.045, 0.020)
    assert calls["n"] == 2, "second (backstop) query must run"


def test_get_rate_and_yield_raises_when_table_missing(monkeypatch):
    """C-03: this used to return a 2024 rate and log at debug level."""
    from lib.options_greeks import get_rate_and_yield, RateLookupError

    _patch_query_to_dataframe(
        monkeypatch, RuntimeError('relation "daily_rates" does not exist'))
    with pytest.raises(RateLookupError, match="query failed"):
        get_rate_and_yield(date(2026, 4, 14))


def test_get_rate_and_yield_raises_when_no_row_exists(monkeypatch):
    from lib.options_greeks import get_rate_and_yield, RateLookupError

    _patch_query_to_dataframe(monkeypatch, pd.DataFrame())
    with pytest.raises(RateLookupError, match="no row at or before"):
        get_rate_and_yield(date(2026, 4, 15))


def test_get_rate_and_yield_raises_on_null_column(monkeypatch):
    """A NULL div-yield used to be silently replaced per-column.

    Half-measured Greeks are not better than none: the caller could not tell
    which of r and q came from the database.
    """
    from lib.options_greeks import get_rate_and_yield, RateLookupError

    _patch_query_to_dataframe(
        monkeypatch, _rates_row(date(2026, 4, 16), r=0.06, q=None))
    with pytest.raises(RateLookupError, match="sp500_div_yld is NULL"):
        get_rate_and_yield(date(2026, 4, 16))


def test_get_rate_and_yield_raises_when_backstop_is_too_stale(monkeypatch):
    """The backstop is unbounded without this: `date <= :d ORDER BY date DESC`
    happily returns a 2016 rate if fred-rates-daily stopped in 2016."""
    from lib.options_greeks import (
        get_rate_and_yield, RateLookupError, _RATE_MAX_STALENESS_DAYS,
    )

    stale = date(2026, 4, 1)
    target = date(2026, 4, 1 + _RATE_MAX_STALENESS_DAYS + 1)
    _patch_query_to_dataframe(monkeypatch, _rates_row(stale))
    with pytest.raises(RateLookupError, match="stale"):
        get_rate_and_yield(target)


def test_get_rate_and_yield_accepts_a_backstop_inside_the_staleness_bound(
        monkeypatch):
    """A long weekend plus FRED's publishing lag must NOT raise."""
    from lib.options_greeks import get_rate_and_yield, _RATE_MAX_STALENESS_DAYS

    row_date = date(2026, 4, 1)
    target = date(2026, 4, 1 + _RATE_MAX_STALENESS_DAYS)
    _patch_query_to_dataframe(monkeypatch, _rates_row(row_date))
    r, q = get_rate_and_yield(target)
    assert (r, q) == (0.052, 0.018)


def test_allow_defaults_opts_in_explicitly(monkeypatch, caplog):
    """The escape hatch exists, is opt-in, and says so at WARNING.

    It used to be the silent default at `log.debug`, which is invisible in
    production logging.
    """
    import logging
    from lib.options_greeks import (
        get_rate_and_yield, _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD,
    )

    _patch_query_to_dataframe(monkeypatch, pd.DataFrame())
    with caplog.at_level(logging.WARNING):
        r, q = get_rate_and_yield(date(2026, 4, 15), allow_defaults=True)
    assert (r, q) == (_DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD)
    assert any("NOT measured" in rec.message or "NOT measured" in rec.getMessage()
               for rec in caplog.records), "the substitution must be logged loudly"


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
