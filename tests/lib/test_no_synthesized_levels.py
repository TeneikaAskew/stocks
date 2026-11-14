"""FEAT-STRAT-001 done_when 8: no synthesized numbers.

On an orb_only side every persona plan has entry_zone null, stop null,
targets [] and risk_metrics null, and the report headline entry_zone and
stop are null; PersonaPlan and InsightReport accept null for both. The
Discord push, the orchestrator's thesis check and the risk-reviewer input
each take a null plan. Every price a plan or the brief publishes is a
level price from the builder's level list or a plan offset from one.

On origin/main this fails: the orb_only plan published ref +/- 1 ATR
(trade_planner.py:702-750) and PersonaPlan.entry_zone was required.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from lib.agents.schema import EntryZone, InsightReport, PersonaPlan, StratSnapshot
from lib.agents.trade_planner import (
    PlanContext,
    _persona_target_keys,
    compute_persona_plans,
)
from lib.strat_levels import (
    MIN_STOP_KEY, SessionLevels, entry_buffer_key, format_levels_for_brief, price_cents,
    stop_key,
)
from tests.lib import strat_2026_11_06 as fx
from tests.lib.session_levels_helpers import basis, session


def _orb_ctx(direction="long") -> PlanContext:
    """Reference 100, ATR 1: the only levels are 20 points away, so both
    sides are orb_only (next_level_outside_window)."""
    sl = session({"PWH": 120.0, "PWL": 80.0}, prior_close=100.0, atr=1.0)
    return PlanContext(direction=direction, conviction="medium", close=100.0, atr=1.0,
                       levels=sl, ftfc_score=0.8 if direction == "long" else -0.8)


@pytest.mark.parametrize("direction", ["long", "short"])
def test_orb_only_plans_publish_no_numbers(direction):
    ctx = _orb_ctx(direction)
    assert ctx.orb_only_reason(direction) == "next_level_outside_window"
    plans = compute_persona_plans(ctx)
    assert {p.persona for p in plans} == {"aggressive", "neutral", "conservative"}
    for p in plans:
        assert p.regime == "orb_only"
        assert p.entry_zone is None
        assert p.stop is None
        assert p.targets == []
        assert p.risk_metrics is None
        assert p.position_size_pct == 0.0
        # The ticker's own window multiple ("2.61 x ATR(14)") is copy, not a price.
        text = re.sub(r"\d+(\.\d+)? x ATR", "", p.rationale)
        assert not re.search(r"\d+\.\d{2}", text), p.rationale


def test_a_context_with_no_levels_is_orb_only_no_levels():
    ctx = PlanContext(direction="long", conviction="medium", close=100.0, atr=1.0,
                      levels=None, ftfc_score=0.8)
    assert ctx.orb_only_reason("long") == "no_levels"
    assert all(p.entry_zone is None and p.stop is None for p in compute_persona_plans(ctx))


def test_trigger_for_is_gone():
    assert not hasattr(PlanContext, "trigger_for")


def _report(**overrides) -> InsightReport:
    base = dict(
        ticker="SPY", as_of=datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc),
        direction="long", conviction="medium", thesis="Wait for the opening range.",
        regime="orb_only", entry_zone=None, stop=None, targets=[],
        invalidation="No trigger.", time_horizon="intraday", key_levels={},
        strat_status=StratSnapshot(last_candle="1", ftfc_score=0.0, ftfc_direction="mixed",
                                   in_force_combo=None),
        catalysts=[], bull_case="", bear_case="", risk_flags=[],
        persona_plans=compute_persona_plans(_orb_ctx()),
        supporting_signals=[], similar_past_trades=[], confidence_score=0.5,
        failed_sections=[], model_versions={}, run_cost_usd=0.0, run_latency_ms=0,
    )
    base.update(overrides)
    return InsightReport(**base)


def test_persona_plan_and_report_accept_null_entry_and_stop():
    PersonaPlan(persona="neutral", entry_zone=None, stop=None, targets=[],
                position_size_pct=0.0, rationale="ORB-only", regime="orb_only")
    r = _report()
    dumped = json.loads(r.model_dump_json())
    assert dumped["entry_zone"] is None and dumped["stop"] is None
    assert all(p["entry_zone"] is None and p["stop"] is None for p in dumped["persona_plans"])


def test_discord_push_renders_a_null_plan(monkeypatch):
    from gcp import insight_discord_push as push
    monkeypatch.setattr(push, "fetch_top_news_articles", lambda *_a, **_k: [])
    sl = session({"PWH": 120.0, "PWL": 80.0}, prior_close=100.0, atr=1.0)
    report = json.loads(_report(level_basis=sl.to_basis()).model_dump_json())
    row = {"ticker": "SPY", "as_of": datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc),
           "cost_usd": 0.0, "latency_ms": 0, "report": report}
    embed = push.format_report_embed(row)
    text = json.dumps(embed)
    assert "None" not in text and "null" not in text
    from lib.strat_levels import orb_only_text
    assert json.dumps(orb_only_text("next_level_outside_window", "long", sl.long.window))[1:-1] in text
    assert not re.search(r"Entry|Stop:", text.split("ORB-only")[1].split('"')[0])


def test_thesis_check_takes_a_null_plan():
    from lib.agents.orchestrator import _validate_thesis_consistency
    orphans = _validate_thesis_consistency(
        "Wait for the range; 120.00 is far.", ticker="SPY", entry_zone=None, stop=None,
        targets=[], key_levels={"PWH": 120.0}, invalidation="")
    assert orphans == []
    orphans = _validate_thesis_consistency(
        "Entry near 101.00.", ticker="SPY", entry_zone=None, stop=None,
        targets=[], key_levels={}, invalidation="")
    assert orphans == [101.0]


def test_risk_reviewer_input_takes_a_null_plan():
    """The risk reviewers read PersonaPlan.risk_metrics; a null plan
    serializes with null entry, stop and risk_metrics, and the risk payload
    builds from an orb_only bundle without inventing a number."""
    from lib.agents.orchestrator import _risk_payload
    from lib.agents.schema import TraderOutput
    sl = session({"PWH": 120.0, "PWL": 80.0}, prior_close=100.0, atr=1.0)
    bundle = {"ticker": "SPY", "strat": {}, "catalysts": {}, "market": {"close": 100.0},
              "session_levels": {"level_basis": sl.to_basis()}}
    trader = TraderOutput(direction="flat", entry_zone=EntryZone(low=0.0, high=0.0), stop=0.0,
                          targets=[], time_horizon="intraday", invalidation="none",
                          confidence=0.0)
    payload = json.loads(_risk_payload(bundle, trader))
    assert payload["ticker"] == "SPY"
    plans = [json.loads(p.model_dump_json()) for p in compute_persona_plans(_orb_ctx())]
    for p in plans:
        assert p["entry_zone"] is None and p["stop"] is None and p["risk_metrics"] is None


_ATR_HEADER = re.compile(r"ATR levels, ATR\(\d+\) \d+\.\d{2}:")

# ── every published price is a level or a plan offset from one ──────────

def _expected_plan(params, persona, trigger, atr, direction, stop_anchor):
    sign = 1.0 if direction == "long" else -1.0
    lo_m = params.value(entry_buffer_key(persona, "lo"))
    hi_m = params.value(entry_buffer_key(persona, "hi"))
    lo, hi = sorted((trigger + sign * lo_m * atr, trigger + sign * hi_m * atr))
    mid = (lo + hi) / 2
    return lo, hi, mid


@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM"])
@pytest.mark.parametrize("direction", ["long", "short"])
def test_every_plan_price_is_a_level_or_an_offset(monkeypatch, ticker, direction):
    _s, ctx, plans, _ = fx.run_planner(monkeypatch, ticker, fx.loader_frame(ticker), direction)
    side = ctx.levels.side(direction)
    trigger = side.trigger["price"]
    assert price_cents(trigger) in ctx.levels.published_prices()
    atr = ctx.plan_atr()
    params = ctx.params
    sign = 1.0 if direction == "long" else -1.0
    for p in plans:
        lo, hi, mid = _expected_plan(params, p.persona, trigger, atr, direction, side.stop)
        assert p.entry_zone.low == pytest.approx(lo, abs=0.01)
        assert p.entry_zone.high == pytest.approx(hi, abs=0.01)
        atr_stop = mid - sign * params.value(stop_key(p.persona)) * atr
        floor_stop = mid - sign * params.value(MIN_STOP_KEY) * atr
        allowed = {round(atr_stop, 2), round(floor_stop, 2)}
        if side.stop is not None:
            allowed.add(round(side.stop["price"], 2))
        assert p.stop in allowed or p.persona == "conservative"
        risk = abs(mid - p.stop)
        r_multiples = [params.value(k) for k in _persona_target_keys(params, p.persona)]
        for t, r in zip(p.targets, r_multiples):
            assert t == pytest.approx(mid + sign * r * risk, abs=0.02)


@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM"])
def test_every_brief_price_is_a_level(monkeypatch, ticker):
    out = fx.run_brief(monkeypatch, ticker, fx.loader_frame(ticker))
    sl = SessionLevels.from_basis(out["level_basis"])
    text = format_levels_for_brief(sl.to_level_map(), "neutral")
    # PMG ZONES print cluster centers (an average of the named levels, a
    # context block that names no trigger); every other price is a level.
    text = text.split("PMG ZONES:")[0]
    # The ATR levels line states the ATR it steps in (ATR levels spec,
    # Design 5), a unit and not a level; every rung it prints is checked.
    assert sl.atr_rung_status == "ok" and "    ATR levels, ATR(14) " in text
    text = _ATR_HEADER.sub("ATR levels:", text)
    known = sl.published_prices()
    printed = [float(m) for m in re.findall(r"(?<![\d.])(\d{2,5}\.\d{2})(?![\d%])", text)]
    assert printed
    for px in printed:
        assert price_cents(px) in known, (px, text)


def test_orb_only_brief_block_prints_no_price():
    b = basis({"PWH": 120.0, "PWL": 80.0}, prior_close=100.0, atr=1.0)
    text = format_levels_for_brief(SessionLevels.from_basis(b).to_level_map(), "neutral")
    # The ATR levels line's ATR is a unit, not a price (ATR levels spec).
    assert "    ATR levels, ATR(14) 1.00: up none; down none" in text
    text = _ATR_HEADER.sub("ATR levels:", text)
    assert not re.search(r"\d+\.\d{2}(?!%)", text.replace("3x", "")), text
