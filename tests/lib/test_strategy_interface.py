"""Phase 0.8 — Test the unified Signal/Strategy interface.

Validates that both strategies present the same shape so callers can
swap them at runtime without conditional logic.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.strategies import (
    ALL,
    MEAN_REVERSION,
    MOMENTUM,
    MeanReversionStrategy,
    MomentumStrategy,
    Signal,
    Strategy,
    get_strategy,
)


def test_get_strategy_by_name():
    assert get_strategy("momentum").name == "momentum"
    assert get_strategy("mean_reversion").name == "mean_reversion"


def test_get_strategy_unknown_raises():
    with pytest.raises(KeyError):
        get_strategy("garbage")


def test_singletons_are_correct_type():
    assert isinstance(MOMENTUM, MomentumStrategy)
    assert isinstance(MEAN_REVERSION, MeanReversionStrategy)
    assert isinstance(MOMENTUM, Strategy)
    assert isinstance(MEAN_REVERSION, Strategy)


def test_all_contains_both_strategies():
    names = {s.name for s in ALL}
    assert names == {"momentum", "mean_reversion"}


def test_signal_dataclass_required_fields():
    sig = Signal(
        strategy="momentum",
        direction="CALL",
        timestamp=pd.Timestamp("2026-05-01 13:30:00", tz="UTC"),
        entry_price=720.0,
        base_score=4.0,
        weighted_score=4.0,
        conditions_met=["consecutive_up", "above_vwap"],
    )
    d = sig.to_dict()
    for k in ("strategy", "direction", "timestamp", "entry_price",
              "base_score", "weighted_score", "conditions_met"):
        assert k in d


def test_signal_to_dict_is_json_serializable():
    import json
    sig = Signal(
        strategy="mean_reversion",
        direction="PUT",
        timestamp=pd.Timestamp("2026-05-01 14:00:00", tz="UTC"),
        entry_price=665.5,
        base_score=4.0,
        weighted_score=4.0,
        conditions_met=["consecutive_up", "rsi_overbought_zone", "above_vwap", "near_above_emas"],
        rsi=72.5,
        rvol=1.4,
        extras={"level_broken": "PDH"},
    )
    serialized = json.dumps(sig.to_dict())
    parsed = json.loads(serialized)
    assert parsed["strategy"] == "mean_reversion"
    assert parsed["direction"] == "PUT"
    assert parsed["rsi"] == 72.5
    assert parsed["extras"]["level_broken"] == "PDH"


def test_both_strategies_produce_same_signal_shape_on_no_fire():
    """Both should return None on a row that doesn't satisfy their conditions."""
    flat_row = pd.Series({
        "Time": pd.Timestamp("2026-05-01 14:00:00", tz="UTC"),
        "Close": 100.0, "Last": 100.0,
        "RSI14": 55.0, "RSI14_W": 55.0,
        "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
        "StochRSI_K": 50.0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Consecutive_Up": 1, "Consecutive_Down": 1,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })
    assert MOMENTUM.evaluate(flat_row) is None
    assert MEAN_REVERSION.evaluate(flat_row) is None


def test_warmup_bars_return_none_for_both():
    """A row where RSI/StochRSI is NaN (pre-warmup) should yield None."""
    nan_row = pd.Series({
        "Time": pd.Timestamp("2026-05-01 13:30:00", tz="UTC"),
        "Close": 720.0, "Last": 720.0,
        "RSI14": float("nan"), "RSI14_W": float("nan"),
        "VWAP": 720.0, "EMA9": 720.0, "EMA20": 720.0,
        "StochRSI_K": float("nan"),
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })
    assert MOMENTUM.evaluate(nan_row) is None
    assert MEAN_REVERSION.evaluate(nan_row) is None
