"""Hermetic tests for the intraday-theta calibration's pure curve builder.

No Cloud SQL dependency — ``build_decay_curve`` is fed synthetic ATM-straddle
series so the normalization / pooling / monotonicity / terminal-pin logic is
checked against known shapes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.calibrate_intraday_theta import build_decay_curve


def _session(tkr: str, d: str, base: float,
             decayed_at_close: float = 0.8) -> pd.DataFrame:
    """Synthetic session: straddle decays LINEARLY from ``base`` to
    ``base*(1-decayed_at_close)`` across 09:30->16:00 (UTC 13:30 = 09:30 EDT)."""
    minfos = np.arange(0, 391, 30)
    straddle = base * (1.0 - decayed_at_close * (minfos / 390.0))
    ts = pd.Timestamp(f"{d} 13:30", tz="UTC") + pd.to_timedelta(minfos, unit="m")
    return pd.DataFrame({"tkr": tkr, "d": d, "snapshot_ts": ts,
                         "atm_straddle": straddle})


def test_endpoints_pinned_and_monotone():
    df = pd.concat([
        _session("SPY", "2026-06-04", 4.0), _session("IWM", "2026-06-04", 2.5),
        _session("SPY", "2026-06-08", 5.0), _session("IWM", "2026-06-08", 2.0),
    ], ignore_index=True)
    knots = build_decay_curve(df)
    assert knots[0] == (0, 0.0)
    assert knots[-1] == (390, 1.0)          # expiry pin / terminal cliff
    gs = [g for _, g in knots]
    assert all(b >= a for a, b in zip(gs, gs[1:]))   # cumulative-max monotone


def test_linear_input_recovers_linear_interior():
    # Normalized g is base-independent, so a linear straddle decay yields
    # interior g(t) ≈ decayed_at_close * t/390 regardless of ticker scale.
    df = pd.concat([_session("SPY", "2026-06-04", 4.0),
                    _session("QQQ", "2026-06-08", 6.0)], ignore_index=True)
    kd = dict(build_decay_curve(df))
    assert kd[180] == pytest.approx(0.8 * 180 / 390, abs=0.02)
    assert kd[300] == pytest.approx(0.8 * 300 / 390, abs=0.02)


def test_degenerate_open_session_is_dropped():
    # A session whose open straddle <= $0.20 (stale/penny data) must not poison
    # the pooled curve — it is dropped, the good session still calibrates.
    good = _session("SPY", "2026-06-04", 4.0)
    bad = _session("QQQ", "2026-06-04", 0.10)
    knots = build_decay_curve(pd.concat([good, bad], ignore_index=True))
    assert knots[0] == (0, 0.0) and knots[-1] == (390, 1.0)
    # Recovers the good session's linear shape, unpolluted by the bad open.
    assert dict(knots)[180] == pytest.approx(0.8 * 180 / 390, abs=0.02)
