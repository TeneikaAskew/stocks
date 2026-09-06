"""Hermetic tests for lib/features/intraday_gex — the PURE reconstruction math
(delta-gamma re-curve + scale-free derived features). Pins the §3.7
no-silent-fallback contract (missing chain / zero OI / bad spot -> NaN, never 0)
and the intraday DEX re-curve formula.
"""
import numpy as np
import pandas as pd
import pytest

from lib.features.intraday_gex import (compute_derived, reconstruct_day,
                                       FEATURE_COLS, RAW_COLS)


def _spots(rows):
    """rows: list of (ts_iso_utc, spot)."""
    return pd.DataFrame([{"ts": r[0], "spot": r[1]} for r in rows])


def _chain(rows):
    """rows: list of (option_type, strike, open_interest, delta, gamma)."""
    return pd.DataFrame(
        [{"option_type": r[0], "strike": r[1], "open_interest": r[2],
          "delta": r[3], "gamma": r[4]} for r in rows])


# ── reconstruct_day ────────────────────────────────────────────────────────

def test_empty_chain_yields_nan_greeks_not_zero():
    sp = _spots([("2024-03-01 14:30:00+00:00", 200.0)])
    out = reconstruct_day(pd.DataFrame(), 199.0, sp)
    assert list(out.columns) == RAW_COLS
    assert np.isnan(out["total_gex"].iloc[0])
    assert np.isnan(out["total_dex"].iloc[0])  # never 0 on missing chain


def test_bad_s_eod_yields_nan():
    sp = _spots([("2024-03-01 14:30:00+00:00", 200.0)])
    ch = _chain([("calls", 200.0, 1000, 0.5, 0.05)])
    out = reconstruct_day(ch, 0.0, sp)   # s_eod <= 0
    assert np.isnan(out["total_dex"].iloc[0])


def test_dex_recurve_formula():
    # Single call: delta 0.50, gamma 0.10, OI 1000, S_eod 100.
    # A = 0.50*1000*100 = 50000 ; B = 0.10*1000*100 = 10000
    # dex(S) = (A + B*(S - 100)) * S
    ch = _chain([("calls", 100.0, 1000, 0.50, 0.10)])
    sp = _spots([("2024-03-01 14:30:00+00:00", 100.0),
                 ("2024-03-01 14:45:00+00:00", 102.0)])
    out = reconstruct_day(ch, 100.0, sp)
    assert out["total_dex"].iloc[0] == pytest.approx((50000 + 0) * 100.0)
    # S=102: (50000 + 10000*2) * 102 = 70000*102 = 7,140,000
    assert out["total_dex"].iloc[1] == pytest.approx((50000 + 10000 * 2) * 102.0)
    assert out["total_oi"].iloc[0] == pytest.approx(1000.0)


def test_gex_scales_with_spot_squared():
    ch = _chain([("calls", 100.0, 1000, 0.50, 0.10),
                 ("puts", 100.0, 800, -0.50, 0.10)])
    sp = _spots([("2024-03-01 14:30:00+00:00", 100.0),
                 ("2024-03-01 14:45:00+00:00", 200.0)])
    out = reconstruct_day(ch, 100.0, sp)
    g1, g2 = out["total_gex"].iloc[0], out["total_gex"].iloc[1]
    # spot doubled -> GEX 4x (S^2), holding NetΓ fixed.
    assert g2 == pytest.approx(g1 * 4.0)


# ── compute_derived ────────────────────────────────────────────────────────

def _raw(rows):
    """rows: (ts, total_gex, total_dex, total_oi, gamma_flip, spot)."""
    return pd.DataFrame(
        [{"ts": r[0], "total_gex": r[1], "total_dex": r[2], "total_oi": r[3],
          "gamma_flip": r[4], "spot": r[5]} for r in rows])


def test_derived_empty_has_cols():
    out = compute_derived(_raw([]))
    assert list(out.columns) == FEATURE_COLS
    assert out.empty


def test_dist_to_flip_and_scale_free():
    out = compute_derived(_raw([
        ("2024-03-01 14:30:00+00:00", 5e9, 2e8, 1e6, 198.0, 200.0),
    ]))
    assert out["dist_to_flip_pct"].iloc[0] == pytest.approx((200.0 - 198.0) / 200.0)
    assert out["gex_per_oi"].iloc[0] == pytest.approx(5e9 / 1e6)
    assert out["dex_per_oi"].iloc[0] == pytest.approx(2e8 / (1e6 * 200.0 * 100.0))


def test_zero_oi_yields_nan_not_zero():
    out = compute_derived(_raw([
        ("2024-03-01 14:30:00+00:00", 5e9, 2e8, 0.0, 198.0, 200.0),
    ]))
    assert np.isnan(out["gex_per_oi"].iloc[0])   # 0 OI -> NaN, never 0/inf
    assert np.isnan(out["dex_per_oi"].iloc[0])


def test_zero_spot_yields_nan():
    out = compute_derived(_raw([
        ("2024-03-01 14:30:00+00:00", 5e9, 2e8, 1e6, 198.0, 0.0),
    ]))
    assert np.isnan(out["dist_to_flip_pct"].iloc[0])
    assert np.isnan(out["dex_per_oi"].iloc[0])


# ---------------------------------------------------------------------------
# aggregate_realtime_buckets — REAL-greeks per-bucket aggregation (build_realtime_gex).
# ---------------------------------------------------------------------------
from lib.features.intraday_gex import aggregate_realtime_buckets


def _chain_rt(rows):
    """rows: (ts, strike, call_g, put_g, dxoi, oi)."""
    return pd.DataFrame([{"ts": r[0], "strike": r[1], "call_g": r[2],
                          "put_g": r[3], "dxoi": r[4], "oi": r[5]} for r in rows])


def test_rt_empty_returns_cols():
    out = aggregate_realtime_buckets(_chain_rt([]), _spots([]))
    assert list(out.columns) == RAW_COLS
    assert out.empty


def test_rt_dex_and_gex_formula():
    # one bucket, two strikes; net γ·OI = (call_g-put_g) summed; Σδ·OI summed.
    ch = _chain_rt([
        ("2026-06-02 14:30:00+00:00", 100.0, 50.0, 10.0, 800.0, 1000.0),
        ("2026-06-02 14:30:00+00:00", 105.0, 20.0, 30.0, -200.0, 500.0),
    ])
    sp = _spots([("2026-06-02 14:30:00+00:00", 100.0)])
    out = aggregate_realtime_buckets(ch, sp)
    # net_gamma = (50-10)+(20-30) = 30 ; total_gex = 30*100^2*0.01 = 3000
    assert out["total_gex"].iloc[0] == pytest.approx(30 * 100.0 * 100.0 * 0.01)
    # net_delta_oi = 800 + (-200) = 600 ; total_dex = 600*100*100 = 6,000,000
    assert out["total_dex"].iloc[0] == pytest.approx(600 * 100.0 * 100.0)
    assert out["total_oi"].iloc[0] == pytest.approx(1500.0)


def test_rt_missing_spot_yields_nan_not_zero():
    ch = _chain_rt([("2026-06-02 14:30:00+00:00", 100.0, 50.0, 10.0, 800.0, 1000.0)])
    sp = _spots([("2026-06-02 14:30:00+00:00", 0.0)])  # bad spot
    out = aggregate_realtime_buckets(ch, sp)
    assert np.isnan(out["total_gex"].iloc[0])
    assert np.isnan(out["total_dex"].iloc[0])
    assert out["total_oi"].iloc[0] == pytest.approx(1000.0)  # OI still known
