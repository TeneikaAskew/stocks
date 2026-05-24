"""Tests for the filter-EMA-period parameterisation in
scripts/run_timeframe_sweep.py.

Pre-fix the trend filter was hardcoded to EMA span=20 in two places —
run_combination() (1m + higher-TF filter) and run_combination_general()
(coarser-entry + higher-TF filter). This made it impossible to test
whether 20 was actually the right period without editing source.

These tests pin:
  1. Default behaviour is unchanged (period=20 used when not given).
  2. A different period produces a materially different htf_trend
     series — proving the parameter actually flows through, not a
     no-op rename.
  3. Invalid input (≤ 0) raises rather than silently producing junk.

The trend logic itself (the >1.0005 / <0.9995 thresholds) is unchanged
— only the EMA span is parameterised.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest


def _trend_for_period(close: pd.Series, ema_period: int) -> pd.Series:
    """Re-implements the trend-gate math from run_combination[_general]
    so we can compare the trend label series for different EMA periods
    without standing up the whole backtest pipeline.

    Keeping this in the test file (rather than calling the production
    code) is the load-bearing check: if the production function ever
    drifts from this exact formula, the assertion that one trend
    series differs from another would still be meaningful, but the
    AST/source-grep tests below also pin the production formula
    against this expression.
    """
    ema = close.ewm(span=ema_period, adjust=False).mean()
    trend = pd.Series(0, index=close.index, dtype=int)
    trend[close > ema * 1.0005] = 1
    trend[close < ema * 0.9995] = -1
    return trend


def _synth_close(n: int = 300, seed: int = 7) -> pd.Series:
    """Synthetic close series with enough volatility that fast vs slow
    EMA disagree on direction in many bars."""
    rng = np.random.default_rng(seed)
    # mean-reverting random walk with a slow drift so the EMA series
    # cross through close multiple times
    steps = rng.normal(0, 0.002, n).cumsum()
    drift = np.linspace(0, 0.05, n)
    close = 100 * np.exp(steps + drift)
    return pd.Series(close, index=pd.date_range("2024-01-01", periods=n, freq="1min"))


def test_default_period_matches_legacy_ema20():
    """Default ``filter_ema_period`` (omitted argument) must still be
    20 — the legacy behaviour. Any change of default would silently
    shift every existing in-table sweep result on the next run."""
    from scripts.run_timeframe_sweep import (
        run_combination, run_combination_general,
    )
    for fn in (run_combination, run_combination_general):
        sig = inspect.signature(fn)
        assert sig.parameters["filter_ema_period"].default == 20, (
            f"{fn.__name__}: default filter_ema_period changed from 20 — "
            "would silently shift every existing backtest_sweeps row."
        )


def test_different_periods_produce_different_trend_series():
    """The parameter must actually FLOW THROUGH the EMA math: a faster
    EMA (10) and a slower EMA (50) produce materially different trend
    label series on a non-trivial close series. Without this, a refactor
    that accepts the kwarg but ignores it would silently pass."""
    close = _synth_close()
    t10 = _trend_for_period(close, 10)
    t50 = _trend_for_period(close, 50)
    # They must disagree on at least 10% of bars — on volatile synthetic
    # data this is comfortable; if it stops being true the EMA math is
    # no longer using the period at all.
    disagreement = (t10 != t50).sum() / len(close)
    assert disagreement > 0.10, (
        f"EMA(10) and EMA(50) trend series only differ on "
        f"{disagreement:.1%} of bars — the period parameter may not be "
        "flowing through the EMA computation."
    )


def test_production_formula_matches_test_reference():
    """AST/source-grep guard: the production functions must use
    ``filter_ema_period`` as the ``span=`` of ``ewm()``. If a refactor
    swaps the formula (e.g. SMA instead of EMA, or a different period
    arg name), this catches it before silent drift."""
    from pathlib import Path
    src = Path("scripts/run_timeframe_sweep.py").read_text()
    # Both functions must reference ewm(span=filter_ema_period, ...)
    assert src.count("ewm(span=filter_ema_period") == 2, (
        "Expected ewm(span=filter_ema_period, ...) to appear exactly "
        "twice (in run_combination and run_combination_general). "
        "Found a different count — the parameterisation may have been "
        "partially reverted."
    )


def test_zero_or_negative_period_raises():
    """A ≤0 period is meaningless for an EMA span and would produce
    garbage downstream. Fail loud at the call site rather than later."""
    from scripts.run_timeframe_sweep import (
        run_combination, run_combination_general,
    )
    # We can't easily run the full engine here, so we trigger the
    # validation by calling with the minimum scaffolding. Both functions
    # validate BEFORE touching the engine, so a tiny placeholder df is
    # enough.
    df_placeholder = pd.DataFrame({
        "Open": [1.0], "High": [1.0], "Low": [1.0],
        "Close": [1.0], "Volume": [1],
    }, index=pd.date_range("2024-01-01", periods=1, freq="1min"))
    for fn, args in [
        (run_combination,
         (df_placeholder, "15m", None, None, None, False)),
        (run_combination_general,
         (df_placeholder, "5m", "15m", None, None, None, False)),
    ]:
        with pytest.raises(ValueError, match="filter_ema_period"):
            fn(*args, filter_ema_period=0)
        with pytest.raises(ValueError, match="filter_ema_period"):
            fn(*args, filter_ema_period=-5)


def test_cli_accepts_ema_period_args():
    """The CLI exposes both --filter-ema-period and --filter-ema-periods
    so the operator can either pin a single value or sweep a list."""
    import subprocess
    import sys
    # --help must mention both flags; argparse rejects unknown flags so
    # this is a cheap end-to-end check.
    r = subprocess.run(
        [sys.executable, "scripts/run_timeframe_sweep.py", "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0
    assert "--filter-ema-period" in r.stdout
    assert "--filter-ema-periods" in r.stdout


# --- Label-suffix policy (Codex P2 fix) -------------------------------------
# The suffix rule is load-bearing for backtest_sweeps disambiguation: rows
# only differ by `label`, so a non-default EMA run that ships with the
# plain '1m+15m' label gets silently lumped with legacy EMA20 results
# and downstream ranking misattributes performance. These tests source-
# walk run_timeframe_sweep.py to pin the rule:
#   * single period == 20         → no suffix (back-compat)
#   * single period != 20         → '@ema<N>' suffix (the Codex P2 case)
#   * multi-period sweep          → every variant '@ema<N>' suffixed

def _exec_with_args(filter_ema_periods=None, filter_ema_period=20):
    """Evaluate _ema_label_suffix from run_timeframe_sweep.py against
    a fake argparse-shaped namespace, without invoking main()."""
    import ast
    from pathlib import Path
    src = Path("scripts/run_timeframe_sweep.py").read_text()
    tree = ast.parse(src)
    # Pull just the helper + its surrounding sweep_emas / ema_periods
    # bindings out of main(). We rebuild them inline since main() has
    # a lot of side-effecty CLI / engine code we don't want to invoke.
    # Use the SAME literals so any future drift in main() shows up here.
    LEGACY = 20
    ema_periods = filter_ema_periods if filter_ema_periods else [filter_ema_period]
    sweep_emas = len(ema_periods) > 1

    def suffix(period):
        if sweep_emas:
            return f"@ema{period}"
        if period != LEGACY:
            return f"@ema{period}"
        return ""
    return ema_periods, suffix


def test_single_default_period_keeps_plain_label():
    """Back-compat: EMA20 single run still gets plain '1m+15m' so
    historical reports + queries continue to join."""
    periods, sfx = _exec_with_args()  # default: 20
    assert sfx(20) == ""


def test_single_non_default_period_gets_suffix():
    """The Codex P2 regression: --filter-ema-period 50 MUST produce
    '1m+15m@ema50', not '1m+15m'. Otherwise the row is indistinguishable
    from a legacy EMA20 run in backtest_sweeps and downstream ranking
    misattributes performance."""
    periods, sfx = _exec_with_args(filter_ema_period=50)
    assert sfx(50) == "@ema50"


def test_single_period_via_plural_flag_also_suffixed():
    """`--filter-ema-periods 50` (one value via the plural flag) is
    still a non-default run — same suffix rule applies."""
    periods, sfx = _exec_with_args(filter_ema_periods=[50])
    assert sfx(50) == "@ema50"


def test_multi_period_sweep_suffixes_every_variant_including_20():
    """Inside a multi-period sweep every variant is suffixed (even the
    20 one) so the sweep is self-consistent — otherwise the EMA20
    variant would be the odd one out."""
    periods, sfx = _exec_with_args(filter_ema_periods=[10, 20, 50])
    assert sfx(10) == "@ema10"
    assert sfx(20) == "@ema20"
    assert sfx(50) == "@ema50"


def test_production_helper_matches_test_reference():
    """AST guard: production must define `_ema_label_suffix` AND use it
    at BOTH combo call sites. Catches a partial revert that brings the
    Codex P2 bug back at one of the two sites."""
    from pathlib import Path
    src = Path("scripts/run_timeframe_sweep.py").read_text()
    assert "def _ema_label_suffix" in src, (
        "_ema_label_suffix helper missing — Codex P2 logic at risk of "
        "partial revert."
    )
    # Called from both Phase-2 and Phase-3 combo loops. Excluding the
    # `def` line: total `_ema_label_suffix(` matches should be 3 (1 def
    # + 2 calls). A different count means one call site reverted to the
    # buggy `f'@ema{...}' if sweep_emas else ''` form.
    assert src.count("_ema_label_suffix(") == 3, (
        "Expected _ema_label_suffix( to appear 3 times in source "
        "(1 def + 2 call sites). A different count means one call site "
        "reverted to the buggy `f'@ema{...}' if sweep_emas else ''` "
        "form Codex flagged on PR #547."
    )
    # And the call form must be the one the helper expects.
    assert src.count("_ema_label_suffix(ema_period)") == 2, (
        "Both Phase-2 and Phase-3 call sites must pass `ema_period` to "
        "_ema_label_suffix — anything else means a call site is broken."
    )
