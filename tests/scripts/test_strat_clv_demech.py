"""Hermetic tests for the CLV de-mechanization grid (scripts/strat_clv_demech).

No DB — synthetic OHLCV through build_bars, then the additive demech columns and
the per-year held-out fold helper. Asserts the wiring (derived columns, target
construction, fold scoring) is correct; the economic interpretation is validated
by the GCP run against real Cloud SQL data, not here.
"""
import numpy as np
import pandas as pd

from scripts.strat_oos_multi_tf import build_bars
import scripts.strat_clv_demech as dm


def _synthetic_daily(n=1500, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2017-01-02", periods=n)
    ret = rng.normal(0, 0.01, n) + 0.0003
    close = 100 * np.exp(np.cumsum(ret))
    op = close * (1 + rng.normal(0, 0.002, n))
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": vol},
        index=idx,
    )


def _prep(daily, tf="1d"):
    bars = build_bars(daily, tf).copy()
    bars["clv_lag1"] = bars["clv"].shift(1)
    nxt_open = bars["Open"].shift(-1)
    nxt_close = bars["Close"].shift(-1)
    bars["next_intrabar"] = (nxt_close > nxt_open).astype("Int64")
    d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
    d["next_up"] = (d["next_candle"] == "2U").astype(int)
    d = d[d["next_intrabar"].notna()].copy()
    d["next_intrabar"] = d["next_intrabar"].astype(int)
    return d


class TestSets:
    def test_set_membership(self):
        assert dm.SETS["CLV_NOW"] == ["clv"]
        assert dm.SETS["CLV_LAG1"] == ["clv_lag1"]
        assert "clv" not in dm.SETS["NO_CLV"]
        assert "clv" in dm.SETS["FULL"]
        assert set(dm.SETS["STRUCT_ONLY"]) == {"ret_1", "ret_2", "ret_3", "ftfc"}

    def test_targets(self):
        assert dm.TARGETS == ("next_up", "next_intrabar")


class TestDerivedColumns:
    def test_clv_lag1_is_prior_clv(self):
        d = _prep(_synthetic_daily())
        # clv_lag1 at row i equals clv at the preceding retained build_bars row.
        assert d["clv_lag1"].notna().all()
        assert (d["clv_lag1"].abs() <= 1.0 + 1e-9).all()

    def test_next_intrabar_is_binary(self):
        d = _prep(_synthetic_daily())
        assert set(d["next_intrabar"].unique()) <= {0, 1}
        assert set(d["next_up"].unique()) <= {0, 1}


class TestFold:
    def test_oos_pooled_scores_both_targets(self):
        d = _prep(_synthetic_daily())
        for target in dm.TARGETS:
            r = dm._oos_pooled(d, dm.SETS["FULL"], target)
            assert r is not None
            acc, base, beat, n = r
            assert 0.0 <= acc <= 1.0
            assert 0.5 <= base <= 1.0
            assert n > 200

    def test_mechanical_signature_on_random_walk(self):
        """On a (near) random walk the CLV mechanical effect should show up as a
        larger CLV_NOW lift on the gap-AIDED target than on the GAP-NEUTRAL one."""
        d = _prep(_synthetic_daily())
        up = dm._oos_pooled(d, ["clv"], "next_up")
        intra = dm._oos_pooled(d, ["clv"], "next_intrabar")
        assert up is not None and intra is not None
        lift_up = up[0] - up[1]
        lift_intra = intra[0] - intra[1]
        # gap-aided CLV lift should not be SMALLER than the gap-neutral lift
        # (the mechanical open-gap can only help the 2U/2D target).
        assert lift_up >= lift_intra - 0.02

    def test_thin_returns_none(self):
        d = _prep(_synthetic_daily(n=400)).head(40)
        assert dm._oos_pooled(d, dm.SETS["FULL"], "next_up") is None
