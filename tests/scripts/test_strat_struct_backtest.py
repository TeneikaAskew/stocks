"""Hermetic tests for the structural-residual costed underlying backtest
(scripts/strat_struct_backtest). No DB — synthetic OHLCV; asserts wiring, cost
accounting, and the hold-mode/cost monotonicities. Economic verdict comes from
the GCP run against real Cloud SQL data.
"""
import numpy as np
import pandas as pd

from scripts.strat_oos_multi_tf import build_bars
import scripts.strat_struct_backtest as bt


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
    bars["cur_close"] = bars["Close"]
    bars["next_open"] = bars["Open"].shift(-1)
    bars["next_close"] = bars["Close"].shift(-1)
    bars["atr20"] = bt._atr20(bars)
    d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
    d["next_up"] = (d["next_candle"] == "2U").astype(int)
    d = d[d["next_open"].notna() & d["next_close"].notna()
          & (d["next_open"] > 0) & d["atr20"].notna()].copy()
    return d


class TestSets:
    def test_struct_is_momentum_plus_ftfc(self):
        assert set(bt.SETS["STRUCT"]) == {"ret_1", "ret_2", "ret_3", "ftfc"}
        assert "clv" not in bt.SETS["STRUCT"]
        assert bt.SETS["CLV_ONLY"] == ["clv"]


class TestAtr:
    def test_atr20_positive(self):
        bars = build_bars(_synthetic_daily(), "1d")
        atr = bt._atr20(bars).dropna()
        assert (atr > 0).all()


class TestBacktest:
    def test_runs_both_holds(self):
        d = _prep(_synthetic_daily())
        for hold in ("oc", "cc"):
            s = bt._backtest(d, bt.SETS["STRUCT"], hold, 2 / 1e4, 0.05)
            assert s is not None
            assert s["n_trades"] > 50
            assert 0.0 <= s["hit"] <= 1.0
            assert s["tot_years"] >= 3

    def test_cost_reduces_net(self):
        """Higher slippage must lower net_bps (cost accounting sanity)."""
        d = _prep(_synthetic_daily())
        lo = bt._backtest(d, bt.SETS["FULL"], "oc", 1 / 1e4, 0.05)
        hi = bt._backtest(d, bt.SETS["FULL"], "oc", 10 / 1e4, 0.05)
        assert hi["net_bps"] < lo["net_bps"]
        # gross unchanged by slippage
        assert abs(hi["gross_bps"] - lo["gross_bps"]) < 1e-6

    def test_wider_band_trades_less(self):
        d = _prep(_synthetic_daily())
        narrow = bt._backtest(d, bt.SETS["FULL"], "oc", 2 / 1e4, 0.0)
        wide = bt._backtest(d, bt.SETS["FULL"], "oc", 2 / 1e4, 0.15)
        assert wide["n_trades"] <= narrow["n_trades"]

    def test_thin_returns_none(self):
        d = _prep(_synthetic_daily(n=400)).head(40)
        assert bt._backtest(d, bt.SETS["STRUCT"], "oc", 2 / 1e4, 0.05) is None
