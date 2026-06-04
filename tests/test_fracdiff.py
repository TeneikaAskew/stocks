"""Hermetic tests for lib/features/fracdiff.py.

Pure numpy/pandas/scipy/statsmodels — no DB, no network, no repo state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.features.fracdiff import (
    frac_diff_weights,
    frac_diff_ffd,
    find_min_d,
    add_fracdiff_features,
)


# --------------------------------------------------------------------------- #
# 1. Weights
# --------------------------------------------------------------------------- #
def test_weights_d1_is_ordinary_differencing():
    w = frac_diff_weights(1.0, 5)
    np.testing.assert_allclose(w, [1.0, -1.0, 0.0, 0.0, 0.0], atol=1e-12)


def test_weights_d0_is_identity():
    w = frac_diff_weights(0.0, 5)
    np.testing.assert_allclose(w, [1.0, 0.0, 0.0, 0.0, 0.0], atol=1e-12)


def test_weights_d2_is_second_difference():
    # second difference kernel is [1, -2, 1, 0, ...]
    w = frac_diff_weights(2.0, 5)
    np.testing.assert_allclose(w, [1.0, -2.0, 1.0, 0.0, 0.0], atol=1e-12)


def test_weights_fractional_decay_and_sign():
    # For 0<d<1 weights alternate sign and decay in magnitude.
    w = frac_diff_weights(0.4, 10)
    assert w[0] == 1.0
    assert w[1] < 0  # -d
    np.testing.assert_allclose(w[1], -0.4, atol=1e-12)
    # magnitudes decay
    assert np.all(np.abs(w[2:]) < np.abs(w[1]))


# --------------------------------------------------------------------------- #
# 2. Memory preservation
# --------------------------------------------------------------------------- #
def _random_walk(n=3000, seed=42):
    """A pure random walk (cumsum of i.i.d. normals).

    seed=42 / n=3000 is a realization that is clearly non-stationary
    (raw ADF p ~ 0.64), so it exercises the fracdiff -> stationary path
    rather than a finite-sample fluke that already tests stationary.
    """
    rng = np.random.default_rng(seed)
    rw = np.cumsum(rng.standard_normal(n)) + 100.0
    return pd.Series(rw, name="price")


def test_memory_preserved_low_d_vs_returns():
    """Low-d fracdiff retains memory of the level; d=1 returns do not.

    The conceptually meaningful, realization-robust claim (AFML ch.5) is
    *relative*: a low fractional order stays strongly correlated with the
    underlying level series, whereas ordinary differencing (d=1, i.e.
    returns) is ~memoryless w.r.t. the level. The absolute correlation of
    the FFD series with the level depends on the fixed window width (set
    by ``thresh``) and the particular path, so we assert the robust
    separation rather than a brittle single-number floor.
    """
    s = _random_walk()

    fd = frac_diff_ffd(s, d=0.4, thresh=1e-4)
    # correlate fracdiff with the original LEVEL series (memory)
    mask = fd.notna()
    corr_fd = np.corrcoef(fd[mask], s[mask])[0, 1]

    # d=1 -> ordinary returns (diff). low correlation with the level.
    ret = frac_diff_ffd(s, d=1.0, thresh=1e-4)
    rmask = ret.notna()
    corr_ret = np.corrcoef(ret[rmask], s[rmask])[0, 1]

    # fracdiff keeps substantial memory of the level...
    assert corr_fd > 0.5, f"d=0.4 should preserve memory, corr={corr_fd}"
    # ...while d=1 returns are ~memoryless w.r.t. the level...
    assert abs(corr_ret) < 0.3, f"d=1 returns should be ~memoryless, corr={corr_ret}"
    # ...and the gap between them is large (memory vs no-memory).
    assert corr_fd > 5 * abs(corr_ret), (
        f"low-d fracdiff should retain far more memory than d=1 returns: "
        f"corr_fd={corr_fd}, corr_ret={corr_ret}"
    )


# --------------------------------------------------------------------------- #
# 3. Stationarity / find_min_d
# --------------------------------------------------------------------------- #
def test_find_min_d_random_walk():
    from statsmodels.tsa.stattools import adfuller

    s = _random_walk()

    # raw random walk is NOT stationary
    raw_p = adfuller(s.to_numpy(), autolag="AIC")[1]
    assert raw_p >= 0.05, f"raw RW should be non-stationary, p={raw_p}"

    d_star = find_min_d(s, thresh=1e-4, max_d=1.0, step=0.05, adf_p=0.05)
    assert 0.0 < d_star < 1.0, f"expected 0<d*<1, got {d_star}"

    fd = frac_diff_ffd(s, d=d_star, thresh=1e-4)
    p = adfuller(fd.dropna().to_numpy(), autolag="AIC")[1]
    assert p < 0.05, f"FFD at d*={d_star} should be stationary, p={p}"


# --------------------------------------------------------------------------- #
# 4. NaN policy
# --------------------------------------------------------------------------- #
def test_leading_window_is_nan_not_zero():
    s = _random_walk(n=500)
    d = 0.4
    fd = frac_diff_ffd(s, d=d, thresh=1e-4)

    # Recompute the fixed window width the same way the impl does.
    from lib.features.fracdiff import _ffd_weights
    w = _ffd_weights(d, 1e-4, max_size=len(s))
    width = len(w)
    assert width > 1

    leading = fd.iloc[: width - 1]
    assert leading.isna().all(), "leading window must be NaN"
    # none of the leading entries are silently zero-filled
    assert (leading == 0).sum() == 0
    # the first valid index is exactly width-1
    assert fd.notna().idxmax() == s.index[width - 1]
    assert fd.iloc[width - 1:].notna().all()


# --------------------------------------------------------------------------- #
# 5. Session awareness
# --------------------------------------------------------------------------- #
def test_session_aware_resets_each_bar_date():
    rng = np.random.default_rng(11)
    n_per_day = 400
    day1 = np.cumsum(rng.standard_normal(n_per_day)) + 100.0
    day2 = np.cumsum(rng.standard_normal(n_per_day)) + 250.0  # discontinuous jump
    df = pd.DataFrame(
        {
            "bar_date": (["2026-06-02"] * n_per_day) + (["2026-06-03"] * n_per_day),
            "close": np.concatenate([day1, day2]),
        }
    )

    out = add_fracdiff_features(df, ["close"], d=0.4, thresh=1e-4, prefix="fd_")
    assert "fd_close" in out.columns

    from lib.features.fracdiff import _ffd_weights
    width = len(_ffd_weights(0.4, 1e-4, max_size=n_per_day))

    # first row of day 2 must be NaN: the window did NOT bridge the overnight gap
    day2_block = out[out["bar_date"] == "2026-06-03"]["fd_close"]
    assert np.isnan(day2_block.iloc[0]), "day-2 first bar should be NaN (reset)"
    # the leading window of day 2 is all NaN
    assert day2_block.iloc[: width - 1].isna().all()
    # and day 2 does produce valid values once its own window fills
    assert day2_block.iloc[width - 1:].notna().all()

    # day 1 also has its own leading NaN window
    day1_block = out[out["bar_date"] == "2026-06-02"]["fd_close"]
    assert day1_block.iloc[: width - 1].isna().all()
    assert day1_block.iloc[width - 1:].notna().all()


def test_add_fracdiff_d_none_infers_per_column():
    s = _random_walk(n=1500)
    df = pd.DataFrame({"price": s.to_numpy()})
    out = add_fracdiff_features(df, ["price"], d=None, thresh=1e-4)
    assert "fd_price" in out.columns
    # inferred d* makes the column stationary
    from statsmodels.tsa.stattools import adfuller
    p = adfuller(out["fd_price"].dropna().to_numpy(), autolag="AIC")[1]
    assert p < 0.05


def test_add_fracdiff_does_not_mutate_input():
    df = pd.DataFrame({"price": _random_walk(n=300).to_numpy()})
    cols_before = list(df.columns)
    add_fracdiff_features(df, ["price"], d=0.4)
    assert list(df.columns) == cols_before


def test_missing_price_col_raises():
    df = pd.DataFrame({"price": [1.0, 2.0, 3.0]})
    with pytest.raises(KeyError):
        add_fracdiff_features(df, ["does_not_exist"], d=0.4)
