"""Pure-helper tests for scripts.analysis.per_factor_walkforward.

The DB pull is exercised separately at integration runtime — these
tests verify the math (fire rate, win rate, discrimination, walk-
forward stability, KEEP/DEMOTE/DROP classification) on synthetic
DataFrames so they run hermetically.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from scripts.analysis.per_factor_walkforward import (
    base_win_rate,
    classify_factor,
    explode_conditions,
    fire_rate,
    walk_forward_fire_rates,
    win_rate_on_fire,
)


def _alerts_df(rows: list[dict]) -> pd.DataFrame:
    """Build the SQL-projection shape the script expects."""
    base_ts = datetime(2026, 5, 12, 9, 30)
    out = []
    for i, r in enumerate(rows):
        out.append({
            "id": r.get("id", f"alert-{i:03d}"),
            "ticker": r.get("ticker", "SPY"),
            "alert_ts": r.get("alert_ts", base_ts + timedelta(minutes=i)),
            "direction": r.get("direction", "CALL"),
            "strategy_name": r.get("strategy_name", "momentum"),
            "conditions_met": r.get("conditions_met", []),
            "outcome_return_pct": r.get("outcome_return_pct"),
        })
    return pd.DataFrame(out)


# ── explode_conditions ──────────────────────────────────────────────


def test_explode_conditions_long_form():
    df = _alerts_df([
        {"id": "a1", "conditions_met": ["x", "y"], "outcome_return_pct": 0.5},
        {"id": "a2", "conditions_met": ["y"], "outcome_return_pct": -0.2},
    ])
    out = explode_conditions(df)
    assert len(out) == 3
    assert set(out["factor"]) == {"x", "y"}
    assert out.loc[out["alert_id"] == "a1", "won"].iloc[0] is True or \
        out.loc[out["alert_id"] == "a1", "won"].iloc[0] == 1


def test_explode_conditions_handles_jsonb_string():
    """Cloud SQL pre-G.P0.6 stored conditions as a JSON-encoded string;
    explode_conditions decodes safely."""
    df = _alerts_df([{"id": "a1", "conditions_met": '["x", "y"]'}])
    out = explode_conditions(df)
    assert set(out["factor"]) == {"x", "y"}


def test_explode_conditions_empty():
    """Empty alerts → empty long-form (with the right columns)."""
    out = explode_conditions(_alerts_df([]))
    assert "alert_id" in out.columns
    assert len(out) == 0


# ── fire_rate ────────────────────────────────────────────────────────


def test_fire_rate_when_factor_fires_on_subset():
    df = _alerts_df([
        {"id": "a1", "conditions_met": ["x"]},
        {"id": "a2", "conditions_met": ["x", "y"]},
        {"id": "a3", "conditions_met": ["y"]},
        {"id": "a4", "conditions_met": []},
    ])
    exploded = explode_conditions(df)
    # x fired on 2 of the 4 alerts. Caller passes total_alerts=4
    # (computed from the pre-explode frame) because explode drops
    # the empty-condition row.
    assert fire_rate(exploded, "x", "momentum", total_alerts=4) == 0.5
    assert fire_rate(exploded, "y", "momentum", total_alerts=4) == 0.5
    assert fire_rate(exploded, "x", "mean_reversion", total_alerts=4) == 0.0


def test_fire_rate_falls_back_to_exploded_count():
    """Backwards-compat: when caller doesn't pass total_alerts, helper
    counts distinct alert_ids in the exploded frame. Under-counts when
    some alerts had empty conditions_met."""
    df = _alerts_df([
        {"id": "a1", "conditions_met": ["x"]},
        {"id": "a2", "conditions_met": ["x", "y"]},
        {"id": "a3", "conditions_met": ["y"]},
    ])
    exploded = explode_conditions(df)
    assert fire_rate(exploded, "x", "momentum") == 2 / 3


# ── win_rate_on_fire + base_win_rate + discrimination ────────────────


def test_win_rate_on_fire_picks_only_factor_alerts():
    """Production alerts always have ≥1 condition (they cleared the
    score threshold), so the 4-alert fixture mirrors that."""
    df = _alerts_df([
        {"id": "a1", "conditions_met": ["x"],      "outcome_return_pct": 1.0},
        {"id": "a2", "conditions_met": ["x"],      "outcome_return_pct": -0.5},
        {"id": "a3", "conditions_met": ["y"],      "outcome_return_pct": 0.5},
        {"id": "a4", "conditions_met": ["y", "z"], "outcome_return_pct": -1.0},
    ])
    exploded = explode_conditions(df)
    # x fired on a1 (won) and a2 (lost) → 50% win on fire
    assert win_rate_on_fire(exploded, "x", "momentum") == 0.5
    # y fired on a3 (won) and a4 (lost) → 50%
    assert win_rate_on_fire(exploded, "y", "momentum") == 0.5
    # Base across all 4 alerts (a1+a3 won, a2+a4 lost) = 50%
    assert base_win_rate(exploded, "momentum") == 0.5


def test_win_rate_on_fire_returns_none_for_no_outcomes():
    df = _alerts_df([
        {"id": "a1", "conditions_met": ["x"], "outcome_return_pct": None},
    ])
    exploded = explode_conditions(df)
    assert win_rate_on_fire(exploded, "x", "momentum") is None


# ── walk_forward_fire_rates ──────────────────────────────────────────


def test_walk_forward_fire_rates_evenly_distributed():
    """Construct 20 alerts evenly spaced. All alerts fire `core` (so
    the fold denominator is the full 20). `confirmer` fires on every
    other alert. Per-fold fire rate of `confirmer` is ≈ 0.5; sd is
    small."""
    base_ts = datetime(2026, 5, 12, 9, 30)
    rows = [
        {
            "id": f"a{i:03d}",
            "alert_ts": base_ts + timedelta(minutes=i),
            "conditions_met": (
                ["core", "confirmer"] if i % 2 else ["core"]
            ),
        }
        for i in range(20)
    ]
    exploded = explode_conditions(_alerts_df(rows))
    rates = walk_forward_fire_rates(exploded, "confirmer", "momentum", folds=4)
    assert len(rates) == 4
    for r in rates:
        assert 0.4 <= r <= 0.6
    # `core` fires on every alert → per-fold rate is 1.0
    core_rates = walk_forward_fire_rates(exploded, "core", "momentum", folds=4)
    assert all(r == 1.0 for r in core_rates)


def test_walk_forward_fire_rates_too_few_alerts_returns_empty():
    """Fewer than folds*5 alerts → return [] so caller can flag
    insufficient data rather than computing a noisy stat."""
    df = _alerts_df([
        {"id": f"a{i}", "conditions_met": ["x"]} for i in range(8)
    ])
    exploded = explode_conditions(df)
    assert walk_forward_fire_rates(exploded, "x", "momentum", folds=4) == []


# ── classify_factor ───────────────────────────────────────────────────


def test_classify_factor_keep_path():
    assert classify_factor(
        fire_rate_value=0.30,
        discrimination=0.08,
        walkforward_sd=0.10,
    ) == "KEEP"


def test_classify_factor_demote_when_too_frequent():
    assert classify_factor(
        fire_rate_value=0.85,
        discrimination=0.20,
        walkforward_sd=0.05,
    ) == "DEMOTE"


def test_classify_factor_demote_when_no_discrimination():
    assert classify_factor(
        fire_rate_value=0.30,
        discrimination=0.02,
        walkforward_sd=0.05,
    ) == "DEMOTE"


def test_classify_factor_demote_when_unstable():
    assert classify_factor(
        fire_rate_value=0.30,
        discrimination=0.08,
        walkforward_sd=0.20,
    ) == "DEMOTE"


def test_classify_factor_drop_when_almost_never_fires():
    assert classify_factor(
        fire_rate_value=0.02,
        discrimination=0.0,
        walkforward_sd=0.10,
    ) == "DROP"


def test_classify_factor_drop_when_fires_always_with_no_signal():
    assert classify_factor(
        fire_rate_value=0.85,
        discrimination=0.01,
        walkforward_sd=0.05,
    ) == "DROP"


def test_classify_factor_insufficient_data():
    assert classify_factor(
        fire_rate_value=0.30,
        discrimination=None,
        walkforward_sd=0.05,
    ) == "INSUFFICIENT_DATA"
    assert classify_factor(
        fire_rate_value=0.30,
        discrimination=0.08,
        walkforward_sd=None,
    ) == "INSUFFICIENT_DATA"


# ─── _infer_strategy (PR #355 codex review fix) ─────────────────────


def test_infer_strategy_momentum_when_momentum_only_factor_present():
    """signal_alerts has no strategy_name column; the SQL query was
    failing with UndefinedColumn until we derived strategy from
    conditions_met content. Codex review on PR #355."""
    from scripts.analysis.per_factor_walkforward import _infer_strategy

    # rsi_bullish_recovery is momentum-exclusive
    assert _infer_strategy(
        ["consecutive_down", "rsi_bullish_recovery", "above_ema9"]
    ) == "momentum"
    # above_ema9 alone is momentum-exclusive
    assert _infer_strategy(["above_ema9"]) == "momentum"


def test_infer_strategy_mean_reversion_when_no_momentum_factor():
    from scripts.analysis.per_factor_walkforward import _infer_strategy

    # MR-exclusive: above_vwap, stoch_rsi_overbought, level_break_pdl
    assert _infer_strategy(
        ["consecutive_up", "rsi_overbought_zone", "above_vwap",
         "stoch_rsi_overbought"]
    ) == "mean_reversion"


def test_infer_strategy_handles_jsonb_string_form():
    """conditions_met may come back as a JSON-encoded string for
    legacy pre-#308 rows."""
    from scripts.analysis.per_factor_walkforward import _infer_strategy

    assert _infer_strategy('["above_ema9"]') == "momentum"
    assert _infer_strategy('["consecutive_up","above_vwap"]') == "mean_reversion"


def test_infer_strategy_handles_none_and_empty():
    from scripts.analysis.per_factor_walkforward import _infer_strategy

    assert _infer_strategy(None) == "mean_reversion"
    assert _infer_strategy([]) == "mean_reversion"
    assert _infer_strategy("not-json") == "mean_reversion"
