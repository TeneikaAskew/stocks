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

Before #1746 the IWM and QQQ short plans were built on the 2025 yearly lows
(171.73 and 402.39), 15 to 22 ATR below price. Under FEAT-STRAT-001's one
level source the planner reads the brief's level_basis (carried on the bundle
as session_levels), so with that morning's unfiltered premarket extremes:
IWM's short is built on the premarket low 269.13, QQQ's on PDL 647.05 (which
premarket touched to the cent, so it is unbroken) and SPY's on the premarket
low 730.64 (PDL 732.71 was broken). A short with no level inside the window is
served orb_only with null entry and stop.

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
from tests.lib.session_levels_helpers import basis  # noqa: E402
from tests.lib.test_trade_planner_distance_cap import (  # noqa: E402
    IWM_2026_11_06,
    QQQ_2026_11_06,
    SPY_2026_11_06,
)

_NAMES = {"effective_pdh": "PDH", "effective_pdl": "PDL", "pwh": "PWH", "pwl": "PWL",
          "pmh": "PMH", "pml": "PML", "pqh": "PQH", "pql": "PQL", "pyh": "PYH", "pyl": "PYL"}

# A short with no premarket snapshot and the only level below 20 ATR away:
# nothing inside 3 x ATR and 8% of the reference.
FAR_ONLY = dict(close=100.0, atr=1.0, effective_pdh=101.0, pyl=80.0,
                pre_high=None, pre_low=None, pre_vwap=None)


def _overlay(bundle: dict, values: dict) -> dict:
    """The bundle the live pipeline builds for a brief ticker: that morning's
    close, ATR(14) and premarket block, and the brief's level_basis as
    session_levels, which context_from_bundle reads."""
    b = copy.deepcopy(bundle)
    market = dict(b.get("market") or {})
    market.update(close=values["close"], atr_14=values["atr"])
    pm = {"pre_high": values["pre_high"], "pre_low": values["pre_low"],
          "pre_vwap": values["pre_vwap"]}
    if all(v is None for v in pm.values()):
        pm = None
    market["premarket"] = dict(pm or {}, gap_pct=None)
    named = {_NAMES[k]: v for k, v in values.items() if k in _NAMES}
    b["market"] = market
    b["session_levels"] = {"level_basis": basis(named, prior_close=values["close"],
                                                atr=values["atr"], premarket=pm)}
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
    zone = plan.get("entry_zone") or {}
    return [p for p in (zone.get("low"), zone.get("high"), plan.get("stop"), *plan["targets"])
            if p is not None]


def _assert_served_is_the_planner(served: dict, planned: dict) -> None:
    plans = {p["persona"]: p for p in served["persona_plans"]}
    assert set(plans) == set(planned)
    for persona, plan in planned.items():
        got = plans[persona]
        assert got["regime"] == plan.regime
        assert got["position_size_pct"] == pytest.approx(plan.position_size_pct)
        if plan.entry_zone is None:
            assert got["entry_zone"] is None
        else:
            assert got["entry_zone"]["low"] == pytest.approx(plan.entry_zone.low)
            assert got["entry_zone"]["high"] == pytest.approx(plan.entry_zone.high)
        assert got["stop"] == (None if plan.stop is None else pytest.approx(plan.stop))
        assert got["targets"] == pytest.approx(plan.targets)


def test_iwm_short_served_on_the_premarket_low(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, IWM_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    atr = IWM_2026_11_06["atr"]
    for plan in served["persona_plans"]:
        lo, hi = plan["entry_zone"]["low"], plan["entry_zone"]["high"]
        assert plan["regime"] == "normal"
        # Built on the premarket low 269.13 (PDL and PML were broken), and
        # nothing served sits on the 2025 yearly low, 22 ATR below price.
        assert lo - atr <= 269.13 <= hi + atr
        assert all(abs(p - 171.73) > 1.0 for p in _served_prices(plan))


def test_qqq_short_served_on_the_touched_pdl(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, QQQ_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    atr = QQQ_2026_11_06["atr"]
    for plan in served["persona_plans"]:
        lo, hi = plan["entry_zone"]["low"], plan["entry_zone"]["high"]
        assert plan["regime"] == "normal"
        # The entry is built on PDL 647.05, not PYL 402.39.
        assert lo - atr <= 647.05 <= hi + atr
        assert all(abs(p - 402.39) > 1.0 for p in _served_prices(plan))


def test_spy_short_served_on_the_premarket_low(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, SPY_2026_11_06)
    _assert_served_is_the_planner(served, planned)
    atr = SPY_2026_11_06["atr"]
    for plan in served["persona_plans"]:
        lo, hi = plan["entry_zone"]["low"], plan["entry_zone"]["high"]
        assert plan["regime"] == "normal"
        assert lo - atr <= 730.64 <= hi + atr


def test_short_with_no_level_in_the_window_is_served_with_null_entry_and_stop(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    served, planned = _served(monkeypatch, client, seven_role_snapshot, FAR_ONLY)
    _assert_served_is_the_planner(served, planned)
    for plan in served["persona_plans"]:
        assert plan["regime"] == "orb_only"
        assert plan["position_size_pct"] == 0.0
        assert plan["entry_zone"] is None and plan["stop"] is None
        assert plan["targets"] == []
    assert served["regime"] == "orb_only"
    assert served["entry_zone"] is None and served["stop"] is None
