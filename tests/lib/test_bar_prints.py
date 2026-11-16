"""The isolated-print rule on hand-written bars (FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 1). Every expected row is a literal written here, never a value the
code under test computed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.bar_prints import PARAMS, RULE_VERSION, isolated_prints, print_geometry
from lib.level_calibration import wick_excesses

GEOMETRY_COLUMNS = [
    "ts", "reference_high", "excess_high", "reference_low", "excess_low", "judged",
]
VALUE_COLUMNS = ["reference_high", "excess_high", "reference_low", "excess_low"]
PRICE_COLUMNS = ["open", "high", "low", "close"]
FLAG_COLUMNS = [
    "ts", "side", "print_kind", "observed", "reference", "bound", "scale", "excess_bp",
]


def flat(n: int, bar_range: float = 0.05) -> pd.DataFrame:
    """n one-minute bars: open and close 100.00, low 100.00, high 100 + range."""
    return pd.DataFrame({
        "ts": pd.date_range("2024-03-05 15:00", periods=n, freq="1min", tz="UTC"),
        "open": 100.0,
        "high": 100.0 + bar_range,
        "low": 100.0,
        "close": 100.0,
    })


# Task 1: print_geometry


def test_geometry_low_wick():
    bars = flat(9)
    bars.loc[4, "low"] = 99.40
    out = print_geometry(bars)

    assert list(out.columns) == GEOMETRY_COLUMNS
    assert list(out.ts) == list(bars.ts)
    assert list(out.judged) == [False, False, True, True, True, True, True, False, False]
    row = out.iloc[4]
    assert row.reference_low == 100.0
    assert row.excess_low == pytest.approx(0.60)
    assert row.reference_high == 100.0
    assert row.excess_high == pytest.approx(0.05)
    assert bool(row.judged) is True
    for i in (0, 1, 7, 8):
        assert out.loc[i, VALUE_COLUMNS].isna().all(), i
    assert not out.loc[2:6, VALUE_COLUMNS].isna().any().any()


def test_geometry_own_open_or_close_is_left_out_only_when_it_is_the_extreme():
    # The open is the low; the close, back at 100, still counts.
    bars = flat(9)
    bars.loc[4, ["open", "low"]] = 99.40
    assert print_geometry(bars).loc[4, "reference_low"] == 100.0

    # Open and close are both the low: the neighbours' bodies alone.
    bars = flat(9)
    bars.loc[4, ["open", "low", "close"]] = 99.40
    out = print_geometry(bars)
    assert out.loc[4, "reference_low"] == 100.0
    assert out.loc[4, "excess_low"] == pytest.approx(0.60)

    # A close that is above the low is kept, and it is the reference when it
    # is lower than every neighbour's open and close.
    bars = flat(9)
    bars.loc[4, "low"] = 99.40
    bars.loc[4, "close"] = 99.90
    assert print_geometry(bars).loc[4, "reference_low"] == 99.90

    # The mirror: the open is the high.
    bars = flat(9)
    bars.loc[4, ["open", "high"]] = 100.60
    out = print_geometry(bars)
    assert out.loc[4, "reference_high"] == 100.0
    assert out.loc[4, "excess_high"] == pytest.approx(0.60)


def test_geometry_agrees_with_wick_excesses():
    n = 300
    rng = np.random.default_rng(20261116)
    mid = 100.0 + np.cumsum(rng.normal(0.0, 0.08, n))
    open_ = mid + rng.uniform(-0.05, 0.05, n)
    close = mid + rng.uniform(-0.05, 0.05, n)
    high = np.maximum(open_, close) + rng.uniform(0.01, 0.30, n)
    low = np.minimum(open_, close) - rng.uniform(0.01, 0.30, n)
    bars = pd.DataFrame({
        "ts": pd.date_range("2024-03-05 14:30", periods=n, freq="1min", tz="UTC"),
        "open": open_, "high": high, "low": low, "close": close,
    })
    assert ((bars.open < bars.high) & (bars.close < bars.high)).all()
    assert ((bars.open > bars.low) & (bars.close > bars.low)).all()

    g = print_geometry(bars)
    w = wick_excesses(bars)
    assert len(w) == 2 * n
    j = g.judged.to_numpy()
    assert j.sum() == n - 4
    assert np.array_equal(g.excess_high[j].to_numpy(), w[:n][j])
    assert np.array_equal(g.excess_low[j].to_numpy(), w[n:][j])


def test_geometry_bad_input():
    empty = print_geometry(flat(0))
    assert list(empty.columns) == GEOMETRY_COLUMNS
    assert len(empty) == 0

    for column in PRICE_COLUMNS:
        bars = flat(9)
        bars.loc[5, column] = np.nan
        with pytest.raises(ValueError) as err:
            print_geometry(bars)
        assert str(bars.ts[5]) in str(err.value), column

    equal = flat(9)
    equal.loc[5, "ts"] = equal.ts[4]
    with pytest.raises(ValueError):
        print_geometry(equal)

    decreasing = flat(9).iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError):
        print_geometry(decreasing)


# Task 2: isolated_prints


def low_wick(low: float, n: int = 61, at: int = 30, bar_range: float = 0.05) -> pd.DataFrame:
    bars = flat(n, bar_range)
    bars.loc[at, "low"] = low
    return bars


def open_at_low() -> pd.DataFrame:
    bars = flat(61)
    bars.loc[30, ["open", "low"]] = 99.40
    return bars


def close_at_low() -> pd.DataFrame:
    bars = flat(61)
    bars.loc[30, ["close", "low"]] = 99.40
    return bars


def one_price() -> pd.DataFrame:
    bars = flat(61)
    bars.loc[30, PRICE_COLUMNS] = 99.40
    return bars


def five_wicks() -> pd.DataFrame:
    bars = flat(61)
    bars.loc[28:32, "low"] = 99.40
    return bars


def both_sides() -> pd.DataFrame:
    bars = flat(61)
    bars.loc[30, "high"] = 100.60
    bars.loc[30, "low"] = 99.40
    return bars


def test_low_wick_60bp():
    bars = low_wick(99.40)
    flags, judged = isolated_prints(bars)

    assert list(flags.columns) == FLAG_COLUMNS
    assert len(flags) == 1
    row = flags.iloc[0]
    assert row.ts == bars.ts[30]
    assert row.side == "low"
    assert row.print_kind == "wick"
    assert row.observed == 99.40
    assert row.reference == 100.0
    assert row.scale == pytest.approx(0.05)
    assert row.bound == pytest.approx(99.50)  # 100 - max(6 x 0.05, 0.0050 x 100)
    assert row.excess_bp == pytest.approx(60.0)
    assert judged.dtype == bool
    assert len(judged) == 61


def test_open_close_and_one_price():
    for bars, kind in ((open_at_low(), "open"), (close_at_low(), "close"),
                       (one_price(), "open_and_close")):
        flags, _ = isolated_prints(bars)
        assert len(flags) == 1, kind
        row = flags.iloc[0]
        assert row.ts == bars.ts[30], kind
        assert row.side == "low", kind
        assert row.print_kind == kind
        assert row.observed == 99.40, kind
        assert row.reference == 100.0, kind
        assert row.excess_bp == pytest.approx(60.0), kind


def test_five_consecutive_wicks():
    bars = five_wicks()
    flags, _ = isolated_prints(bars)
    assert list(flags.ts) == [bars.ts[i] for i in (28, 29, 30, 31, 32)]
    assert list(flags.side) == ["low"] * 5
    assert list(flags.print_kind) == ["wick"] * 5
    assert list(flags.observed) == [99.40] * 5
    assert list(flags.reference) == [100.0] * 5


def test_level_shift_is_not_flagged():
    bars = flat(61)
    bars.loc[30:, ["open", "close", "low"]] = 99.40
    bars.loc[30:, "high"] = 99.45
    assert ((bars.high >= bars[["open", "close"]].max(axis=1))
            & (bars.low <= bars[["open", "close"]].min(axis=1))).all()
    flags, _ = isolated_prints(bars)
    assert len(flags) == 0


def test_under_the_floor_and_at_the_bound():
    under, _ = isolated_prints(low_wick(99.51))  # 49 bp
    assert len(under) == 0
    at_bound, _ = isolated_prints(low_wick(99.50))  # exactly the bound
    assert len(at_bound) == 0
    # The first price past the bound is flagged, so the two cases above are
    # held back by the bound and by nothing else.
    past, _ = isolated_prints(low_wick(99.49))
    assert len(past) == 1


def test_wide_scale():
    # 6 x 0.15 = 0.90, above the 0.60 wick.
    flags, _ = isolated_prints(low_wick(99.40, bar_range=0.15))
    assert len(flags) == 0


def test_ends_are_not_judged():
    bars = low_wick(99.40)
    _, judged = isolated_prints(bars)
    assert not judged[:2].any()
    assert not judged[-2:].any()
    assert judged[2:-2].all()
    assert np.array_equal(judged, print_geometry(bars).judged.to_numpy())

    # A wick on a bar that is not judged is not flagged.
    edge = flat(61)
    edge.loc[1, "low"] = 99.40
    edge.loc[59, "low"] = 99.40
    flags, _ = isolated_prints(edge)
    assert len(flags) == 0


def test_flags_rest_on_print_geometry():
    cases = (low_wick(99.40), open_at_low(), close_at_low(), one_price(),
             five_wicks(), both_sides())
    seen = 0
    for bars in cases:
        flags, _ = isolated_prints(bars)
        geometry = print_geometry(bars).set_index("ts")
        for flag in flags.itertuples():
            measured = geometry.loc[flag.ts]
            reference = measured[f"reference_{flag.side}"]
            excess = measured[f"excess_{flag.side}"]
            assert flag.reference == reference
            assert flag.excess_bp == excess / reference * 10_000
            seen += 1
    assert seen == 11


def test_bad_input():
    flags, judged = isolated_prints(flat(0))
    assert list(flags.columns) == FLAG_COLUMNS
    assert len(flags) == 0
    assert isinstance(judged, np.ndarray)
    assert len(judged) == 0

    for column in PRICE_COLUMNS:
        bars = flat(61)
        bars.loc[30, column] = np.nan
        with pytest.raises(ValueError) as err:
            isolated_prints(bars)
        assert str(bars.ts[30]) in str(err.value), column

    equal = flat(61)
    equal.loc[30, "ts"] = equal.ts[29]
    with pytest.raises(ValueError):
        isolated_prints(equal)


def test_version_pins_the_parameters():
    assert RULE_VERSION == "isolated-print-v1"
    assert PARAMS == {
        "neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0,
    }


def test_high_side_and_both_sides():
    bars = both_sides()
    flags, _ = isolated_prints(bars)
    assert len(flags) == 2
    assert set(flags.ts) == {bars.ts[30]}
    by_side = flags.set_index("side")
    assert sorted(by_side.index) == ["high", "low"]

    high = by_side.loc["high"]
    assert high.print_kind == "wick"
    assert high.observed == 100.60
    assert high.reference == 100.0
    assert high.bound == pytest.approx(100.50)
    assert high.excess_bp == pytest.approx(60.0)

    low = by_side.loc["low"]
    assert low.print_kind == "wick"
    assert low.observed == 99.40
    assert low.reference == 100.0
    assert low.bound == pytest.approx(99.50)
    assert low.excess_bp == pytest.approx(60.0)


def test_short_input():
    bars = flat(4)
    bars.loc[2, "low"] = 99.40
    flags, judged = isolated_prints(bars)
    assert len(flags) == 0
    assert list(judged) == [False, False, False, False]
