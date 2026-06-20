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
