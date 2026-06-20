"""_load_gamma_levels must not fabricate a 0 for a missing total_gex.

Rule 3.7: a missing GEX must be NULL/None — not a fabricated 0 that downstream
can't distinguish from a real ~0 reading, and that would pollute the GEX
tercile distribution with fake zeros. A genuine 0.0 is preserved.
"""
from __future__ import annotations

import math

import pandas as pd

from gcp.research.strat_engine import strat_data_builder as mod


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Engine:
    def connect(self):
        return _Conn()


def _raw():
    """Raw gamma_levels_eod rows: a normal date, a date with MISSING total_gex,
    and a date with a GENUINE 0.0."""
    return pd.DataFrame([
        {"snapshot_date": "2026-06-16", "level_kind": "king", "level_strike": 500.0,
         "gex": 1.0, "score": 1.0, "regime": "positive_gamma",
         "gamma_balance_price": 498.0, "gamma_flip": 497.0,
         "total_gex": 1.5e7, "spot_estimate": 499.0},
        {"snapshot_date": "2026-06-17", "level_kind": "king", "level_strike": 501.0,
         "gex": 1.0, "score": 1.0, "regime": "negative_gamma",
         "gamma_balance_price": 499.0, "gamma_flip": 498.0,
         "total_gex": None, "spot_estimate": 500.0},   # missing GEX
        {"snapshot_date": "2026-06-18", "level_kind": "gate", "level_strike": 502.0,
         "gex": 0.0, "score": 0.0, "regime": "unknown",
         "gamma_balance_price": 500.0, "gamma_flip": 499.0,
         "total_gex": 0.0, "spot_estimate": 501.0},    # genuine zero
    ])


def test_missing_gex_is_null_genuine_zero_preserved(monkeypatch):
    monkeypatch.setattr(mod.pd, "read_sql", lambda *a, **k: _raw())

    out = mod._load_gamma_levels(_Engine(), "SPY")

    missing = out.loc[pd.Timestamp("2026-06-17").date(), "total_gex"]
    assert missing is None or (isinstance(missing, float) and math.isnan(missing)), \
        "missing total_gex must be NULL, not a fabricated 0"

    assert out.loc[pd.Timestamp("2026-06-18").date(), "total_gex"] == 0.0, \
        "a genuine 0.0 GEX must be preserved, not nulled"
    assert out.loc[pd.Timestamp("2026-06-16").date(), "total_gex"] == 1.5e7


def test_terciles_drop_null_gex(monkeypatch):
    """The NULL GEX must be excluded from the tercile distribution (dropna),
    not counted as a fake 0 that drags the percentiles down."""
    monkeypatch.setattr(mod.pd, "read_sql", lambda *a, **k: _raw())
    out = mod._load_gamma_levels(_Engine(), "SPY")
    # 3 dates, 1 NULL → 2 non-null feed terciles. (<30 rows → (nan, nan), but
    # the point is the series passed to _compute_terciles has the NULL dropped.)
    assert out["total_gex"].notna().sum() == 2


def test_dealer_regime_null_when_gex_missing():
    """_add_context must NULL dealer_regime when a tercile is missing, not
    persist a malformed "GEX_nan_VEX_*" that downstream null-filters keep
    (Codex review on #640)."""
    import datetime as dt
    import numpy as np

    d15, d16, d17 = dt.date(2026, 6, 15), dt.date(2026, 6, 16), dt.date(2026, 6, 17)
    gamma_df = pd.DataFrame([
        {"snapshot_date": d15, "total_gex": np.nan, "gamma_balance_price": 498.0,
         "gamma_flip": 497.0, "regime": "negative_gamma", "spot": 499.0,
         "min_king_strike": 500.0, "min_gate_strike": 495.0},
        {"snapshot_date": d16, "total_gex": 2e7, "gamma_balance_price": 499.0,
         "gamma_flip": 498.0, "regime": "positive_gamma", "spot": 500.0,
         "min_king_strike": 501.0, "min_gate_strike": 496.0},
        {"snapshot_date": d17, "total_gex": 2.5e7, "gamma_balance_price": 500.0,
         "gamma_flip": 499.0, "regime": "positive_gamma", "spot": 501.0,
         "min_king_strike": 502.0, "min_gate_strike": 497.0},
    ]).set_index("snapshot_date")
    vex_df = pd.DataFrame([
        {"snapshot_date": d15, "total_vex": 5e6},
        {"snapshot_date": d16, "total_vex": 6e6},
        {"snapshot_date": d17, "total_vex": 6.5e6},
    ]).set_index("snapshot_date")
    vix_df = pd.DataFrame([
        {"date": d15, "vix_close": 17.0},
        {"date": d16, "vix_close": 18.0},
        {"date": d17, "vix_close": 19.0},
    ]).set_index("date")
    # bar on d16 → prior day d15 (NaN GEX); bar on d17 → prior day d16 (GEX present)
    out = pd.DataFrame({"bar_date": [d16, d17], "close": [500.0, 501.0]})

    res = mod._add_context(out, "SPY", vix_df, gamma_df, vex_df,
                           gex_terciles=(1e7, 3e7), vex_terciles=(4e6, 7e6)
                           ).set_index("bar_date")

    # d16: prior GEX missing → tercile NaN → dealer_regime null (NaN/None, both
    # write as SQL NULL) — NOT the malformed "GEX_nan_VEX_MID" string
    assert pd.isna(res.loc[d16, "total_gex"])
    assert pd.isna(res.loc[d16, "dealer_regime"])
    # d17: prior GEX present → valid 9-cell label, no "nan"
    dr = res.loc[d17, "dealer_regime"]
    assert dr is not None and dr.startswith("GEX_") and "nan" not in dr
