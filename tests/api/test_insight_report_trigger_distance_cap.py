"""FEAT-INSIGHT-001: the trigger distance cap in what GET /api/insights/report serves.

tests/lib/test_trade_planner_distance_cap.py calls the planner directly. This
file follows the same three 2026-11-06 short setups end to end, the way the
insights page receives them:

  canned summarizer data (the orchestrator suite's canned_bundle), with the
  strat levels, close, ATR(14) and premarket block set to that morning's
  values for the ticker
  -> lib.agents.orchestrator.run_insight_pipeline (the real bundle build,
     context_from_bundle and compute_persona_plans; only the LLM is mocked,
     and it returns a short)
  -> gcp.insight_pipeline_job._upsert_report (the real row writer; the
     connection is captured in memory)
  -> GET /api/insights/report/{ticker} (the real router, reading the
     captured row through a fake connection that applies the router's own
     ticker / run_kind = 'live' filter)

On origin/main the IWM and QQQ short plans are built on the 2025 yearly lows
(171.73 and 402.39), 15 to 22 ATR below price. Here IWM's short is orb_only
with no size, QQQ's short is built on PDL 647.05, which premarket touched to
the cent, and SPY's short on PQL 729.10 is unchanged.

No network and no database.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.agents.test_agent_orchestrator import (  # noqa: E402
    _mock_factory_ctor,
    canned_bundle,  # noqa: F401  (pytest fixture)
    seven_role_snapshot,  # noqa: F401  (pytest fixture)
)
from tests.api.test_insight_report_conservative_short import (  # noqa: E402
    _Conn,
    _ShortMockLLM,
    client,  # noqa: F401  (pytest fixture)
    no_network,  # noqa: F401  (pytest fixture)
)
from tests.lib.test_trade_planner_distance_cap import (  # noqa: E402
    IWM_2026_11_06,
    QQQ_2026_11_06,
    SPY_2026_11_06,
)

_LEVEL_KEYS = {
    "effective_pdh": "effective_PDH", "effective_pdl": "effective_PDL",
    "pwh": "PWH", "pwl": "PWL", "pmh": "PMH", "pml": "PML",
    "pqh": "PQH", "pql": "PQL", "pyh": "PYH", "pyl": "PYL",
}


def _overlay(bundle: dict, values: dict) -> dict:
    """The bundle summarize_market_context and summarize_strat_status would
    have built from that morning's rows: same shape, that ticker's numbers."""
    b = copy.deepcopy(bundle)
    market = dict(b.get("market") or {})
    market.update(close=values["close"], atr_14=values["atr"])
    market["premarket"] = {"pre_high": values["pre_high"], "pre_low": values["pre_low"],
                           "pre_vwap": values["pre_vwap"], "gap_pct": None}
    strat = dict(b.get("strat") or {})
    strat.update(trigger_high=values["trigger_high"], trigger_low=values["trigger_low"])
    levels = {"PDH": values["effective_pdh"], "PDL": values["effective_pdl"]}
    levels.update({_LEVEL_KEYS[k]: values[k] for k in _LEVEL_KEYS})
    strat["levels"] = levels
    b["market"], b["strat"] = market, strat
    return b


def _served(monkeypatch, client, snapshot, values: dict):  # noqa: F811
    """Run the real pipeline on a short with `values`, persist it with the
    real writer, and return (served report, the planner's own plans)."""
    from lib.agents import orchestrator
    from lib.agents import trade_planner
    import gcp.insight_pipeline_job as job
    from api.routers import insights as insights_router

    real = trade_planner.context_from_bundle
    seen: dict = {}

    def with_levels(bundle, direction, conviction):
        ctx = real(_overlay(bundle, values), direction, conviction)
        seen["plans"] = trade_planner.compute_persona_plans(ctx)
        return ctx
    monkeypatch.setattr(trade_planner, "context_from_bundle", with_levels)

    report = asyncio.run(orchestrator.run_insight_pipeline(
        "SPY", snapshot=snapshot, llm_factory=_mock_factory_ctor(_ShortMockLLM())))
    assert report.direction == "short"

    store: list = []
    monkeypatch.delenv("INSIGHT_AS_OF", raising=False)        # a live run
    monkeypatch.setattr(job, "connect", lambda: _Conn(store))
    monkeypatch.setattr(insights_router, "connect", lambda: _Conn(store))
    assert job._upsert_report(report) is not None

    r = client.get("/api/insights/report/SPY")
    assert r.status_code == 200, r.text
    served = r.json()["report"]
    assert served["direction"] == "short"
    return served, {p.persona: p for p in seen["plans"]}


def _served_prices(plan: dict) -> list[float]:
    return [plan["entry_zone"]["low"], plan["entry_zone"]["high"], plan["stop"],
            *plan["targets"]]


def _assert_served_is_the_planner(served: dict, planned: dict) -> None:
    plans = {p["persona"]: p for p in served["persona_plans"]}
    assert set(plans) == set(planned)
    for persona, plan in planned.items():
        got = plans[persona]
        assert got["regime"] == plan.regime
        assert got["position_size_pct"] == pytest.approx(plan.position_size_pct)
        assert got["entry_zone"]["low"] == pytest.approx(plan.entry_zone.low)
        assert got["entry_zone"]["high"] == pytest.approx(plan.entry_zone.high)
        assert got["stop"] == pytest.approx(plan.stop)
        assert got["targets"] == pytest.approx(plan.targets)


def test_iwm_short_served_as_orb_only_with_no_size(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, IWM_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    for plan in served["persona_plans"]:
        print(f"\nIWM short {plan['persona']}: regime={plan['regime']} "
              f"size={plan['position_size_pct']}")
        assert plan["regime"] == "orb_only"
        assert plan["position_size_pct"] == 0.0
        # Nothing served sits on the 2025 yearly low, 22 ATR below price.
        assert all(abs(p - 171.73) > 1.0 for p in _served_prices(plan))
    assert served["regime"] == "orb_only"


def test_qqq_short_served_on_the_touched_pdl(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, QQQ_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    atr = QQQ_2026_11_06["atr"]
    for plan in served["persona_plans"]:
        lo, hi = plan["entry_zone"]["low"], plan["entry_zone"]["high"]
        print(f"\nQQQ short {plan['persona']}: regime={plan['regime']} entry={lo}-{hi} "
              f"stop={plan['stop']}")
        assert plan["regime"] == "normal"
        # The entry is built on PDL 647.05, not PYL 402.39.
        assert lo - atr <= 647.05 <= hi + atr
        assert all(abs(p - 402.39) > 1.0 for p in _served_prices(plan))


def test_spy_short_served_on_pql_unchanged(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, SPY_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    atr = SPY_2026_11_06["atr"]
    for plan in served["persona_plans"]:
        lo, hi = plan["entry_zone"]["low"], plan["entry_zone"]["high"]
        assert plan["regime"] == "normal"
        assert lo - atr <= 729.10 <= hi + atr
