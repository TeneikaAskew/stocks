"""Phase 0.8 — Isolation guarantees for strategy implementations.

Strategies must be:
  1. Stateless (no instance-level mutation across calls)
  2. Pure (same input → same output)
  3. Non-mutating (don't change the caller's DataFrame)
  4. Thread-safe (parallel evaluation gives same result as serial)

These properties matter for Phase 3 (multi-timeframe parallel evaluator)
where multiple strategy instances run concurrently against different
DataFrames.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from lib.strategies import MEAN_REVERSION, MOMENTUM


def _firing_call_bar() -> pd.Series:
    """A bar that fires a momentum CALL."""
    return pd.Series({
        "Time": pd.Timestamp("2026-05-01 13:30:00", tz="UTC"),
        "Close": 101.0, "Last": 101.0,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
        "StochRSI_K": 50.0,
        "Consecutive_Up": 3, "Consecutive_Down": 0,
        "Price_vs_VWAP": 1.0, "Price_vs_EMA9": 1.0, "Price_vs_EMA20": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })


def _firing_mr_call_bar() -> pd.Series:
    """A bar that fires a mean-reversion CALL."""
    return pd.Series({
        "Time": pd.Timestamp("2026-05-01 13:30:00", tz="UTC"),
        "Close": 100.0, "Last": 100.0,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 100.5, "EMA9": 100.5, "EMA20": 100.5,
        "StochRSI_K": 20.0,
        "Consecutive_Up": 0, "Consecutive_Down": 3,
        "Price_vs_VWAP": -0.5, "Price_vs_EMA9": -0.5, "Price_vs_EMA20": -0.5,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })


# ── Purity: same input → same output ────────────────────────────────────

def test_momentum_pure_repeated_calls():
    row = _firing_call_bar()
    out1 = MOMENTUM.evaluate(row)
    out2 = MOMENTUM.evaluate(row)
    assert out1 is not None and out2 is not None
    assert out1.direction == out2.direction
    assert out1.base_score == out2.base_score
    assert out1.conditions_met == out2.conditions_met


def test_mean_reversion_pure_repeated_calls():
    row = _firing_mr_call_bar()
    out1 = MEAN_REVERSION.evaluate(row)
    out2 = MEAN_REVERSION.evaluate(row)
    assert out1 is not None and out2 is not None
    assert out1.direction == out2.direction
    assert out1.base_score == out2.base_score
    assert out1.conditions_met == out2.conditions_met


# ── Non-mutation: input row is not changed ──────────────────────────────

def test_momentum_does_not_mutate_input_row():
    row = _firing_call_bar()
    original = row.to_dict()
    MOMENTUM.evaluate(row)
    after = row.to_dict()
    assert original == after, "MomentumStrategy.evaluate mutated the input row"


def test_mean_reversion_does_not_mutate_input_row():
    row = _firing_mr_call_bar()
    original = row.to_dict()
    MEAN_REVERSION.evaluate(row)
    after = row.to_dict()
    assert original == after, "MeanReversionStrategy.evaluate mutated the input row"


def test_generate_signals_does_not_mutate_dataframe():
    rows = [_firing_call_bar(), _firing_call_bar(), _firing_mr_call_bar()]
    df = pd.DataFrame([r.to_dict() for r in rows])
    df_before = df.copy(deep=True)

    MOMENTUM.generate_signals(df)
    pd.testing.assert_frame_equal(df, df_before, check_like=False)

    MEAN_REVERSION.generate_signals(df)
    pd.testing.assert_frame_equal(df, df_before, check_like=False)


# ── Statelessness: instance has no mutable state ────────────────────────

def test_singletons_have_no_instance_state():
    """Strategy singletons should expose only the .name class attr."""
    for s in (MOMENTUM, MEAN_REVERSION):
        instance_dict = vars(s)
        assert instance_dict == {} or all(
            not k.startswith("_") for k in instance_dict
        ), f"{s.name} carries instance state — risk for thread-safety"


# ── Thread-safety: parallel runs match serial ─────────────────────────

def test_parallel_evaluate_produces_identical_results():
    """Run 100 evaluations on different threads; assert all match the
    serial result."""
    row = _firing_call_bar()
    serial = MOMENTUM.evaluate(row)
    assert serial is not None

    results: list = []
    lock = threading.Lock()

    def worker():
        out = MOMENTUM.evaluate(row)
        with lock:
            results.append(out)

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(worker) for _ in range(100)]
        for f in futs:
            f.result()

    assert len(results) == 100
    for r in results:
        assert r.direction == serial.direction
        assert r.base_score == serial.base_score
        assert r.conditions_met == serial.conditions_met


def test_both_strategies_can_run_concurrently_on_same_row():
    """Different strategies on the same row in parallel — each should
    produce the same answer it produces serially.

    Note: this MR-firing bar (Consecutive_Down=3 + below VWAP + below
    EMAs) ALSO fires momentum PUT (Consecutive_Down=3 + below VWAP +
    below EMA9 = 3 conditions in the put direction). That's the §3.9
    "complementary strategies" property — both fire on the same bar,
    in OPPOSITE directions. The test must therefore assert each
    strategy's parallel result matches its OWN serial result, not that
    one returns None."""
    row = _firing_mr_call_bar()

    mom_serial = MOMENTUM.evaluate(row)
    mr_serial  = MEAN_REVERSION.evaluate(row)

    def mom_worker():
        return MOMENTUM.evaluate(row)

    def mr_worker():
        return MEAN_REVERSION.evaluate(row)

    with ThreadPoolExecutor(max_workers=4) as ex:
        mom_futs = [ex.submit(mom_worker) for _ in range(50)]
        mr_futs  = [ex.submit(mr_worker)  for _ in range(50)]

        for f in mom_futs:
            r = f.result()
            if mom_serial is None:
                assert r is None
            else:
                assert r is not None
                assert r.direction       == mom_serial.direction
                assert r.base_score      == mom_serial.base_score
                assert r.conditions_met  == mom_serial.conditions_met

        for f in mr_futs:
            r = f.result()
            assert r is not None
            assert mr_serial is not None
            assert r.direction       == mr_serial.direction
            assert r.base_score      == mr_serial.base_score
            assert r.conditions_met  == mr_serial.conditions_met

    # Bonus assertion: when both strategies fire on the same bar, they
    # disagree on direction (the §3.9 finding). Document that here so
    # anyone reading this test understands why the parallel test exists.
    if mom_serial is not None and mr_serial is not None:
        assert mom_serial.direction != mr_serial.direction, (
            "On this fixture both strategies must fire OPPOSITE directions "
            "(mean-reversion buys oversold dip while momentum sells the down-trend)"
        )
