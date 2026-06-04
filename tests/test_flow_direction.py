"""Hermetic tests for lib/features/flow_direction.py.

These run with numpy+pandas+scipy ONLY — no DB, no sqlalchemy. They lock the
DEX sign convention, validate vanna/charm against finite differences, exercise
the short-DTE filter and NaN handling, and assert the module imports without
sqlalchemy at top level.
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import pandas as pd
import pytest

from lib.features import flow_direction as fd


SNAP = dt.date(2024, 1, 2)


def _contract(option_type, strike, oi, iv, delta, dte):
    return {
        "snapshot_date": SNAP,
        "option_type": option_type,
        "strike": strike,
        "open_interest": oi,
        "implied_volatility": iv,
        "delta": delta,
        "expiration": SNAP + dt.timedelta(days=dte),
    }


# --------------------------------------------------------------------------
# 1. DEX sign lock
# --------------------------------------------------------------------------
def test_dex_sign_calls_negative_puts_positive():
    # Only long customer CALLS (positive delta, OI > 0) -> NEGATIVE dealer dex.
    call_chain = pd.DataFrame([
        _contract("calls", 100, 500, 0.20, 0.55, 30),
        _contract("calls", 105, 300, 0.20, 0.40, 30),
    ])
    feat = fd.compute_chain_features(call_chain, SNAP)
    assert feat["dex_d1"] < 0, f"call-heavy dealer dex should be <0, got {feat['dex_d1']}"

    # Put-heavy chain (negative delta) -> POSITIVE dealer dex.
    put_chain = pd.DataFrame([
        _contract("puts", 100, 500, 0.20, -0.55, 30),
        _contract("puts", 95, 300, 0.20, -0.40, 30),
    ])
    feat_p = fd.compute_chain_features(put_chain, SNAP)
    assert feat_p["dex_d1"] > 0, f"put-heavy dealer dex should be >0, got {feat_p['dex_d1']}"

    # Exact value check: dealer dex = -(Σ delta·OI)
    expected = -(0.55 * 500 + 0.40 * 300)
    assert feat["dex_d1"] == pytest.approx(expected)


def test_dex_per_oi_scale_free():
    chain = pd.DataFrame([
        _contract("calls", 100, 1000, 0.20, 0.50, 30),
    ])
    feat = fd.compute_chain_features(chain, SNAP)
    # dex = -(0.50*1000) = -500; total_oi = 1000; per_oi = -0.5
    assert feat["dex_per_oi_d1"] == pytest.approx(-0.5)


# --------------------------------------------------------------------------
# 2. Vanna validation vs finite difference ∂delta/∂sigma
# --------------------------------------------------------------------------
@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("K", [90.0, 100.0, 115.0])
def test_vanna_matches_finite_difference(is_call, K):
    S, t, r, q, sigma = 100.0, 0.25, 0.04, 0.015, 0.22
    h = 1e-4
    d_up = float(fd.bs_delta(S, K, t, r, q, sigma + h, is_call))
    d_dn = float(fd.bs_delta(S, K, t, r, q, sigma - h, is_call))
    fd_vanna = (d_up - d_dn) / (2 * h)
    analytic = float(fd.bs_vanna(S, K, t, r, q, sigma))
    assert analytic == pytest.approx(fd_vanna, abs=1e-4), \
        f"vanna {analytic} vs FD {fd_vanna} (K={K}, call={is_call})"


# --------------------------------------------------------------------------
# 3. Charm validation vs finite difference delta(t-1/365) - delta(t)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("K", [90.0, 100.0, 115.0])
def test_charm_matches_finite_difference(is_call, K):
    S, t, r, q, sigma = 100.0, 0.25, 0.04, 0.015, 0.22
    one_day = 1.0 / 365.0
    d_now = float(fd.bs_delta(S, K, t, r, q, sigma, is_call))
    # one calendar day passing -> t shrinks by one_day
    d_next = float(fd.bs_delta(S, K, t - one_day, r, q, sigma, is_call))
    fd_charm = d_next - d_now  # d(delta)/d(calendar day)
    analytic = float(fd.bs_charm_per_day(S, K, t, r, q, sigma, is_call))
    # abs=3e-5: the one-sided one-calendar-day difference has O(h) truncation
    # error (~7e-6 here); the analytic charm is the limit. Headroom avoids a
    # flake on shorter-dated contracts (review M-1).
    assert analytic == pytest.approx(fd_charm, abs=3e-5), \
        f"charm {analytic} vs FD {fd_charm} (K={K}, call={is_call})"


def test_vanna_charm_net_dealer_sign():
    # Net dealer greek = -(Σ_all greek·OI) — dealer is SHORT the customer book,
    # the SAME negation as DEX (review H-1). Exercise call, put, AND mixed so
    # the put-branch aggregation sign is covered (review H-2).
    vanna_c = float(fd.bs_vanna(100.0, 100.0, 90 / 365.0, fd.DEFAULT_R,
                                fd.DEFAULT_Q, 0.22))  # same for call & put
    charm_call = float(fd.bs_charm_per_day(100.0, 100.0, 90 / 365.0, fd.DEFAULT_R,
                                           fd.DEFAULT_Q, 0.22, True))
    charm_put = float(fd.bs_charm_per_day(100.0, 100.0, 90 / 365.0, fd.DEFAULT_R,
                                          fd.DEFAULT_Q, 0.22, False))

    # Single CALL: dealer vanna/charm = -(greec·OI).
    call = _contract("calls", 100, 1000, 0.22, 0.50, 90)
    fc = fd.compute_chain_features(pd.DataFrame([call]), SNAP, spot=100.0)
    assert fc["vanna_d1"] == pytest.approx(-vanna_c * 1000, rel=1e-6)
    assert fc["charm_d1"] == pytest.approx(-charm_call * 1000, rel=1e-6)

    # Single PUT (exercises the put branch of the dealer-short aggregation).
    put = _contract("puts", 100, 800, 0.22, -0.50, 90)
    fp = fd.compute_chain_features(pd.DataFrame([put]), SNAP, spot=100.0)
    assert fp["vanna_d1"] == pytest.approx(-vanna_c * 800, rel=1e-6)
    assert fp["charm_d1"] == pytest.approx(-charm_put * 800, rel=1e-6)

    # Mixed call + put: dealer aggregate = -(call + put) for BOTH greeks.
    fm = fd.compute_chain_features(pd.DataFrame([call, put]), SNAP, spot=100.0)
    assert fm["vanna_d1"] == pytest.approx(-(vanna_c * 1000 + vanna_c * 800), rel=1e-6)
    assert fm["charm_d1"] == pytest.approx(
        -(charm_call * 1000 + charm_put * 800), rel=1e-6)


# --------------------------------------------------------------------------
# 4. short_dte filter: dte > 2 excluded from short_dte_dex_d1
# --------------------------------------------------------------------------
def test_short_dte_filter():
    chain = pd.DataFrame([
        _contract("calls", 100, 500, 0.20, 0.50, 1),    # dte=1 -> included
        _contract("calls", 101, 400, 0.20, 0.50, 2),    # dte=2 -> included
        _contract("calls", 102, 300, 0.20, 0.50, 5),    # dte=5 -> excluded
        _contract("calls", 103, 200, 0.20, 0.50, 30),   # dte=30 -> excluded
    ])
    feat = fd.compute_chain_features(chain, SNAP)
    # short dex only from dte<=2: -(0.50*500 + 0.50*400) = -450
    assert feat["short_dte_dex_d1"] == pytest.approx(-(0.50 * 500 + 0.50 * 400))
    # full dex includes all four
    assert feat["dex_d1"] == pytest.approx(
        -(0.50 * (500 + 400 + 300 + 200)))
    # full != short (the far contracts really were excluded)
    assert feat["short_dte_dex_d1"] != feat["dex_d1"]


def test_short_dte_no_near_contracts_is_nan():
    # No 0-2DTE contracts -> short_dte_dex_d1 is NaN, not 0.
    chain = pd.DataFrame([
        _contract("calls", 100, 500, 0.20, 0.50, 30),
    ])
    feat = fd.compute_chain_features(chain, SNAP)
    assert np.isnan(feat["short_dte_dex_d1"])


# --------------------------------------------------------------------------
# 5. NaN handling: a date that can't form a ratio yields NaN, not 0
# --------------------------------------------------------------------------
def test_dex_chg_5d_nan_when_no_prior():
    # Build 3 dates only; shift(5) has no prior -> dex_chg_5d NaN everywhere.
    rows = []
    for i in range(3):
        d = dt.date(2024, 1, 2 + i)
        rows.append({**_contract("calls", 100, 500, 0.20, 0.50, 30),
                     "snapshot_date": d,
                     "expiration": d + dt.timedelta(days=30)})
    daily = fd.compute_daily_features(pd.DataFrame(rows))
    assert daily["dex_chg_5d"].isna().all()


def test_missing_delta_yields_nan_not_zero():
    # A date with delta all-NaN cannot form dex -> NaN, never 0.
    chain = pd.DataFrame([
        {**_contract("calls", 100, 500, 0.20, np.nan, 30)},
        {**_contract("puts", 100, 500, 0.20, np.nan, 30)},
    ])
    feat = fd.compute_chain_features(chain, SNAP)
    assert np.isnan(feat["dex_d1"])
    assert feat["dex_d1"] != 0


def test_no_calls_ratio_path_is_nan():
    # dex_per_oi when total_oi is NaN/0 -> NaN, not 0.
    empty = pd.DataFrame(columns=["snapshot_date", "option_type", "strike",
                                  "open_interest", "implied_volatility",
                                  "delta", "expiration"])
    feat = fd.compute_chain_features(empty, SNAP)
    assert np.isnan(feat["dex_d1"])
    assert np.isnan(feat["dex_per_oi_d1"])
    assert np.isnan(feat["vanna_d1"])
    assert np.isnan(feat["charm_d1"])


# --------------------------------------------------------------------------
# 6. Module imports with only numpy/pandas/scipy (no top-level sqlalchemy)
# --------------------------------------------------------------------------
def test_no_sqlalchemy_at_import_time():
    # If flow_direction imported sqlalchemy at module top-level, importing it
    # would have pulled sqlalchemy into sys.modules. The lazy-import discipline
    # means a fresh interpreter could import it without sqlalchemy installed.
    import importlib
    mod = importlib.import_module("lib.features.flow_direction")
    src = mod.__file__
    with open(src) as f:
        head = f.read().split("def _load_dex_aggregates")[0]
    assert "import sqlalchemy" not in head
    assert "from sqlalchemy" not in head


def test_feature_cols_contract():
    assert fd.FEATURE_COLS == [
        "dex_d1", "dex_per_oi_d1", "dex_chg_5d",
        "vanna_d1", "charm_d1", "short_dte_dex_d1",
    ]
