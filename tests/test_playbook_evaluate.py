"""Tests for `POST /api/playbook/evaluate` and the `_eval_condition`
regex/threshold logic that backs it.

This is the server-side replacement for the TypeScript `evalCondition`
that commit `6aa0afa` removed from `playbookEvaluator.ts`. Per CLAUDE.md
"single source of truth for math" the rules live here in Python and
the React app posts snapshots over HTTP. Tests cover every regex
branch and the integration through the FastAPI router.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


@pytest.fixture(scope="module")
def evaluator():
    """Direct access to `_eval_condition` and the snapshot Pydantic types
    so per-rule tests can call the function without HTTP overhead."""
    original_cwd = os.getcwd()
    os.chdir(str(PLATFORM_DIR))
    try:
        from api.routers import playbook as pb
    finally:
        os.chdir(original_cwd)
    return pb


@pytest.fixture
def make_snapshot(evaluator):
    """Build a `_Snapshot` with sane defaults; tests override the few
    fields they care about."""
    def factory(**overrides):
        ind_overrides = overrides.pop("ind", {})
        ind_defaults = {
            "ema9": 200.0, "ema20": 198.0, "ema50": 195.0,
            "rsi": 55.0, "stochK": 60.0, "stochD": 58.0,
            "atr": 3.5, "vwap": 199.0, "stochKPrev": None,
        }
        ind_defaults.update(ind_overrides)
        snap_defaults = {
            "price": 201.0,
            "prevClose": 198.0,
            "prevHigh": 203.0,
            "prevLow": 196.0,
            "volumeToday": 15_000_000,
            "avgVolume20d": 10_000_000,
            "orbHigh": 202.0,
            "orbLow": 199.5,
            "lastBar": {
                "time": "2026-04-25 10:30",
                "open": 200.5, "high": 201.2, "low": 200.0,
                "close": 201.0, "volume": 1_200_000,
            },
            "minutesSinceOpen": 60.0,
            "stochKPrev": None,
            "indicators": ind_defaults,
        }
        snap_defaults.update(overrides)
        return evaluator._Snapshot.model_validate(snap_defaults)
    return factory


# ──────────────────────────────────────────────────────────────────────
# RSI rules
# ──────────────────────────────────────────────────────────────────────


def test_rsi_between_inside_range(evaluator, make_snapshot):
    s = make_snapshot(ind={"rsi": 55.0})
    r = evaluator._eval_condition("RSI between 40-65 (not overbought yet)", s)
    assert r.status == "met"
    assert "55.0" in r.detail


def test_rsi_between_outside_range(evaluator, make_snapshot):
    s = make_snapshot(ind={"rsi": 75.0})
    r = evaluator._eval_condition("RSI between 40-65", s)
    assert r.status == "unmet"


def test_rsi_between_em_dash_separator(evaluator, make_snapshot):
    """The regex accepts `-` and the Unicode em dash `–`."""
    s = make_snapshot(ind={"rsi": 55.0})
    r = evaluator._eval_condition("RSI between 40–65", s)
    assert r.status == "met"


def test_rsi_between_unknown_when_rsi_missing(evaluator, make_snapshot):
    s = make_snapshot(ind={"rsi": None})
    r = evaluator._eval_condition("RSI between 40-65", s)
    assert r.status == "unknown"
    assert "RSI" in r.reason


def test_rsi_less_than_threshold(evaluator, make_snapshot):
    s = make_snapshot(ind={"rsi": 30.0})
    r = evaluator._eval_condition("RSI < 45", s)
    assert r.status == "met"


def test_rsi_greater_than_threshold(evaluator, make_snapshot):
    s = make_snapshot(ind={"rsi": 60.0})
    r = evaluator._eval_condition("RSI > 50", s)
    assert r.status == "met"


def test_stochrsi_phrase_does_not_match_rsi_rule(evaluator, make_snapshot):
    """`StochRSI` mentions must not be hijacked by the bare RSI cmp."""
    s = make_snapshot(ind={"rsi": 55.0})
    # This phrase has < but it's about StochRSI — should not interpret as RSI<
    r = evaluator._eval_condition("StochRSI was oversold (<20) turning up", s)
    # Hits the StochRSI branch, not the RSI<N branch
    assert r.status in ("met", "unmet", "unknown")
    # Detail should reference StochK if it produced a comparison
    if r.detail:
        assert "RSI 55" not in r.detail


# ──────────────────────────────────────────────────────────────────────
# Price vs VWAP / EMA
# ──────────────────────────────────────────────────────────────────────


def test_price_above_vwap_met(evaluator, make_snapshot):
    s = make_snapshot(price=201.0, ind={"vwap": 199.0})
    r = evaluator._eval_condition("Price above VWAP", s)
    assert r.status == "met"


def test_price_below_vwap_met(evaluator, make_snapshot):
    s = make_snapshot(price=198.0, ind={"vwap": 199.0})
    r = evaluator._eval_condition("Price below VWAP", s)
    assert r.status == "met"


def test_price_above_ema20(evaluator, make_snapshot):
    s = make_snapshot(price=201.0, ind={"ema20": 198.0})
    r = evaluator._eval_condition("Price above EMA20", s)
    assert r.status == "met"


def test_price_below_ema9(evaluator, make_snapshot):
    s = make_snapshot(price=199.0, ind={"ema9": 200.0})
    r = evaluator._eval_condition("Price below EMA9", s)
    assert r.status == "met"


def test_price_above_ema_unknown_when_ema_missing(evaluator, make_snapshot):
    s = make_snapshot(price=201.0, ind={"ema50": None})
    r = evaluator._eval_condition("Price above EMA50", s)
    assert r.status == "unknown"
    assert "EMA50" in r.reason


# ──────────────────────────────────────────────────────────────────────
# EMA cross
# ──────────────────────────────────────────────────────────────────────


def test_ema9_greater_than_ema20_bullish(evaluator, make_snapshot):
    s = make_snapshot(ind={"ema9": 200.0, "ema20": 198.0})
    r = evaluator._eval_condition("EMA9 > EMA20 (bullish cross)", s)
    assert r.status == "met"


def test_ema9_less_than_ema20_bearish(evaluator, make_snapshot):
    s = make_snapshot(ind={"ema9": 197.0, "ema20": 198.0})
    r = evaluator._eval_condition("EMA9 < EMA20 (bearish cross)", s)
    assert r.status == "met"


# ──────────────────────────────────────────────────────────────────────
# RVOL — relative volume
# ──────────────────────────────────────────────────────────────────────


def test_rvol_greater_than_threshold(evaluator, make_snapshot):
    s = make_snapshot(volumeToday=15_000_000, avgVolume20d=10_000_000)
    # 15M / 10M = 1.5
    r = evaluator._eval_condition("RVOL > 1.0", s)
    assert r.status == "met"


def test_rvol_unknown_when_avg_zero(evaluator, make_snapshot):
    """Defensive divide-by-zero — avgVolume20d=0 returns unknown not crash."""
    s = make_snapshot(volumeToday=15_000_000, avgVolume20d=0)
    r = evaluator._eval_condition("RVOL > 1.0", s)
    assert r.status == "unknown"


# ──────────────────────────────────────────────────────────────────────
# StochRSI turn
# ──────────────────────────────────────────────────────────────────────


def test_stochrsi_oversold_turning_up(evaluator, make_snapshot):
    """Was below threshold AND now turning up → met."""
    s = make_snapshot(stochKPrev=15.0, ind={"stochK": 25.0})
    r = evaluator._eval_condition(
        "StochRSI was oversold (<20) turning up", s
    )
    assert r.status == "met"
    assert "15" in r.detail and "25" in r.detail


def test_stochrsi_oversold_not_turning_up(evaluator, make_snapshot):
    s = make_snapshot(stochKPrev=15.0, ind={"stochK": 12.0})
    r = evaluator._eval_condition(
        "StochRSI was oversold (<20) turning up", s
    )
    assert r.status == "unmet"


def test_stochrsi_overbought_turning_down(evaluator, make_snapshot):
    s = make_snapshot(stochKPrev=85.0, ind={"stochK": 75.0})
    r = evaluator._eval_condition(
        "StochRSI was overbought (>80) turning down", s
    )
    assert r.status == "met"


# ──────────────────────────────────────────────────────────────────────
# ORB break + 30m trend
# ──────────────────────────────────────────────────────────────────────


def test_orb_high_break_met(evaluator, make_snapshot):
    s = make_snapshot(price=203.0, orbHigh=202.0)
    r = evaluator._eval_condition(
        "Price has broken above the opening range high", s
    )
    assert r.status == "met"


def test_orb_low_break_met(evaluator, make_snapshot):
    s = make_snapshot(price=199.0, orbLow=199.5)
    r = evaluator._eval_condition(
        "Price has broken below the opening range low", s
    )
    assert r.status == "met"


def test_orb_30m_trend_bullish(evaluator, make_snapshot):
    s = make_snapshot(price=201.5, orbHigh=202.0, orbLow=199.5)
    # mid = 200.75; price 201.5 > mid → met
    r = evaluator._eval_condition("ORB 30m trend is bullish", s)
    assert r.status == "met"


def test_orb_30m_trend_bearish(evaluator, make_snapshot):
    s = make_snapshot(price=200.0, orbHigh=202.0, orbLow=199.5)
    # mid = 200.75; price 200.0 < mid → bearish met
    r = evaluator._eval_condition("ORB 30m trend is bearish", s)
    assert r.status == "met"


# ──────────────────────────────────────────────────────────────────────
# Minutes since open
# ──────────────────────────────────────────────────────────────────────


def test_minutes_after_open_satisfied(evaluator, make_snapshot):
    s = make_snapshot(minutesSinceOpen=60.0)
    r = evaluator._eval_condition(
        "At least 30 minutes after market open", s
    )
    assert r.status == "met"


def test_minutes_after_open_not_satisfied(evaluator, make_snapshot):
    s = make_snapshot(minutesSinceOpen=15.0)
    r = evaluator._eval_condition(
        "At least 30 minutes after market open", s
    )
    assert r.status == "unmet"


def test_minutes_after_open_unknown_when_market_closed(evaluator, make_snapshot):
    s = make_snapshot(minutesSinceOpen=None)
    r = evaluator._eval_condition(
        "At least 30 minutes after market open", s
    )
    assert r.status == "unknown"


# ──────────────────────────────────────────────────────────────────────
# Close in upper/lower half
# ──────────────────────────────────────────────────────────────────────


def test_close_in_upper_half(evaluator, make_snapshot):
    s = make_snapshot(lastBar={
        "time": "x", "open": 200.0, "high": 202.0, "low": 200.0,
        "close": 201.5, "volume": 1.0,
    })
    # mid = 201; close 201.5 > mid → met
    r = evaluator._eval_condition("Close in upper half of bar", s)
    assert r.status == "met"


def test_close_in_lower_half(evaluator, make_snapshot):
    s = make_snapshot(lastBar={
        "time": "x", "open": 201.0, "high": 202.0, "low": 200.0,
        "close": 200.4, "volume": 1.0,
    })
    r = evaluator._eval_condition("Close in lower half of bar", s)
    assert r.status == "met"


# ──────────────────────────────────────────────────────────────────────
# Support / resistance proximity
# ──────────────────────────────────────────────────────────────────────


def test_price_at_support_within_threshold(evaluator, make_snapshot):
    """Within PRICE_PROXIMITY_PCT of prevLow → met. Default ~0.3% so
    197.0 vs 196.0 = 0.51% off — outside; 196.5 → 0.25% — within."""
    s = make_snapshot(price=196.5, prevLow=196.0)
    r = evaluator._eval_condition("Price at or near support", s)
    assert r.status == "met"


def test_price_at_resistance_outside_threshold(evaluator, make_snapshot):
    s = make_snapshot(price=210.0, prevHigh=203.0)
    r = evaluator._eval_condition("Price at or near resistance", s)
    assert r.status == "unmet"


# ──────────────────────────────────────────────────────────────────────
# Unknown / unrecognized fallthrough
# ──────────────────────────────────────────────────────────────────────


def test_subjective_higher_timeframe(evaluator, make_snapshot):
    s = make_snapshot()
    r = evaluator._eval_condition("Higher timeframe supports the direction", s)
    assert r.status == "unknown"
    assert "subjective" in r.reason


def test_strat_pattern_unknown(evaluator, make_snapshot):
    s = make_snapshot()
    r = evaluator._eval_condition("Type 3 outside bar setup", s)
    assert r.status == "unknown"
    assert "strat" in r.reason.lower()


def test_unrecognized_condition(evaluator, make_snapshot):
    s = make_snapshot()
    r = evaluator._eval_condition("Jupiter is in retrograde", s)
    assert r.status == "unknown"
    assert r.reason == "unrecognized"


# ──────────────────────────────────────────────────────────────────────
# HTTP integration — the router contract
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    original_cwd = os.getcwd()
    os.chdir(str(PLATFORM_DIR))
    try:
        from starlette.testclient import TestClient
        from api.main import app
        with TestClient(app) as c:
            yield c
    finally:
        os.chdir(original_cwd)


def _basic_snapshot_payload():
    return {
        "price": 201.0,
        "prevClose": 198.0,
        "prevHigh": 203.0,
        "prevLow": 196.0,
        "volumeToday": 15_000_000,
        "avgVolume20d": 10_000_000,
        "orbHigh": 202.0,
        "orbLow": 199.5,
        "lastBar": {
            "time": "2026-04-25 10:30",
            "open": 200.5, "high": 201.2, "low": 200.0,
            "close": 201.0, "volume": 1_200_000,
        },
        "minutesSinceOpen": 60.0,
        "stochKPrev": 15.0,
        "indicators": {
            "ema9": 200.0, "ema20": 198.0, "ema50": 195.0,
            "rsi": 55.0, "stochK": 25.0, "stochD": 22.0,
            "atr": 3.5, "vwap": 199.0,
        },
    }


def test_evaluate_flat_conditions_returns_results_in_order(client):
    body = {
        "snapshot": _basic_snapshot_payload(),
        "conditions": [
            "RSI between 40-65",
            "Price above VWAP",
            "Bogus condition",
        ],
    }
    r = client.post("/api/playbook/evaluate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) == 3
    assert data["results"][0]["status"] == "met"
    assert data["results"][1]["status"] == "met"
    assert data["results"][2]["status"] == "unknown"


def test_evaluate_batches_returns_results_by_key(client):
    body = {
        "snapshot": _basic_snapshot_payload(),
        "batches": {
            "card_a": ["RSI > 50", "Price above VWAP"],
            "card_b": ["RVOL > 2.0"],  # 1.5 < 2.0 → unmet
        },
    }
    r = client.post("/api/playbook/evaluate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "results_by_key" in data
    assert len(data["results_by_key"]["card_a"]) == 2
    assert all(r["status"] == "met" for r in data["results_by_key"]["card_a"])
    assert data["results_by_key"]["card_b"][0]["status"] == "unmet"


def test_evaluate_400_when_neither_conditions_nor_batches(client):
    """The endpoint requires at least one input shape."""
    r = client.post(
        "/api/playbook/evaluate",
        json={"snapshot": _basic_snapshot_payload()},
    )
    assert r.status_code == 400
    assert "conditions" in r.json()["detail"] or "batches" in r.json()["detail"]


def test_evaluate_validates_snapshot_shape(client):
    """Missing required `indicators` field → 422."""
    bad = _basic_snapshot_payload()
    del bad["indicators"]
    r = client.post(
        "/api/playbook/evaluate",
        json={"snapshot": bad, "conditions": ["RSI > 50"]},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Structured playbook_cards source (_cards_from_db) — the typed path that
# replaces regex-scraping the markdown. Verifies the fraction->percent and
# bps->percent conversions and that NaN/NULL never become a fabricated 0.
# ---------------------------------------------------------------------------

def test_cards_from_db_converts_and_preserves_nulls(monkeypatch, evaluator):
    pb = evaluator
    import numpy as np
    import pandas as pd
    import gcp.database as dbmod

    rows = pd.DataFrame([
        {"card_num": 1, "name": "IWM CARD 1: Bullish", "description": "two-up",
         "direction": "CALL", "conditions": ["RSI 40-65", "Above VWAP"],
         "win_rate": 0.48, "avg_return_bps": -10.0, "sample_n": 90,
         "horizons": [{"minutes": 5, "win_rate": 0.46, "avg_return_bps": -0.38, "sample_n": 90},
                      {"minutes": 60, "win_rate": 0.36, "avg_return_bps": -0.18, "sample_n": 90}],
         "best_horizon_min": 60, "best_horizon_win_rate": 0.36, "best_horizon_avg_bps": -0.18},
        {"card_num": 2, "name": "IWM CARD 2: Bearish", "description": None,
         "direction": "PUT", "conditions": '["Below VWAP"]',   # JSON string form
         "win_rate": np.nan, "avg_return_bps": np.nan, "sample_n": 0,
         "horizons": '[]', "best_horizon_min": None,           # JSON string + NULLs
         "best_horizon_win_rate": np.nan, "best_horizon_avg_bps": np.nan},
    ])
    monkeypatch.setattr(dbmod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(dbmod, "query_to_dataframe", lambda sql, params=None: rows)

    cards = pb._cards_from_db("IWM")
    assert cards is not None and len(cards) == 2

    c1 = cards[0]
    assert c1["win_rate"] == 48.0            # fraction -> percent
    assert c1["avg_return"] == pytest.approx(-0.10)   # bps -> percent
    assert c1["conditions"] == ["RSI 40-65", "Above VWAP"]
    assert c1["direction"] == "CALL"
    # per-hold-window sweep + best-avg-return hold (win% in %, returns in bps)
    assert [h["minutes"] for h in c1["horizons"]] == [5, 60]
    assert c1["horizons"][0]["win_rate"] == 46.0
    assert c1["horizons"][1]["avg_return_bps"] == pytest.approx(-0.18)
    assert c1["best_horizon_min"] == 60
    assert c1["best_horizon_win_rate"] == 36.0
    assert c1["best_horizon_avg_bps"] == pytest.approx(-0.18)

    c2 = cards[1]
    assert c2["win_rate"] is None            # NaN -> None, never 0 (3.7)
    assert c2["avg_return"] is None
    assert c2["conditions"] == ["Below VWAP"]   # JSON string parsed
    assert c2["description"] == ""
    assert c2["horizons"] == []                 # JSON-string '[]' parsed
    assert c2["best_horizon_min"] is None       # NULL stays None
    assert c2["best_horizon_avg_bps"] is None


def test_cards_from_db_bridges_when_cloud_sql_off(monkeypatch, evaluator):
    pb = evaluator
    import gcp.database as dbmod
    monkeypatch.setattr(dbmod, "is_cloud_sql_configured", lambda: False)
    assert pb._cards_from_db("IWM") is None      # signals caller to use markdown
