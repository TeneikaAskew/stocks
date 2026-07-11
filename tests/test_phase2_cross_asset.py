import numpy as np
import pandas as pd
from gcp.research.direction_program.phase2_features import cross_asset_features


def test_cross_asset_uses_strictly_prior_peer_bar():
    base = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 15:00", "2026-01-05 15:05"], utc=True),
        "close": [100.0, 101.0],
    })
    peer = pd.DataFrame({
        "ts": pd.to_datetime(
            ["2026-01-05 14:50", "2026-01-05 14:55", "2026-01-05 15:00"], utc=True),
        "close": [50.0, 51.0, 52.0],  # 14:55->15:00 return = 52/51-1
    })
    out = cross_asset_features(base, {"SPY": peer})
    assert "xa_SPY_ret_1" in out.columns
    # bar at 15:00 uses peer bars strictly before 15:00: last is 14:55 (51),
    # prior 14:50 (50) -> ret = 51/50 - 1 = 0.02
    assert abs(out.iloc[0]["xa_SPY_ret_1"] - 0.02) < 1e-6


def test_cross_asset_missing_peer_is_nan():
    # Peer has >=2 bars, ALL strictly AFTER the base bar's ts, with distinct
    # close prices so the peer's own shift(1) return on its LAST row is a
    # REAL, non-NaN number (0.10). This makes the test able to distinguish
    # the correct explicit-NaN guard from a regression that lets idx == -1
    # wrap (numpy negative indexing) to the peer's last bar: with a
    # single-row peer fixture, that wraparound would coincidentally also be
    # NaN (a fresh series' first shift(1) is always NaN) and the test would
    # pass for the wrong reason.
    base = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 09:30"], utc=True), "close": [100.0]})
    peer = pd.DataFrame({
        "ts": pd.to_datetime(
            ["2026-01-05 10:00", "2026-01-05 10:05"], utc=True),
        "close": [50.0, 55.0],  # last-row return = 55/50 - 1 = 0.10 (real, non-NaN)
    })
    out = cross_asset_features(base, {"SPY": peer})
    assert np.isnan(out.iloc[0]["xa_SPY_ret_1"])  # no strictly-prior peer bar
