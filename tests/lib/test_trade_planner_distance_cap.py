"""FEAT-INSIGHT-001: the insight planner's trigger walk is capped by distance.

Regression for the 2026-11-06 insight reports, where the short triggers
for IWM (171.73) and QQQ (402.39) were the 2025 yearly lows, 15 to 22
ATR below price. Inputs below are that morning's values rebuilt from
Alpha Vantage daily and extended-hours bars (ATR(14) per ticker).
"""

import pytest

from lib.agents.trade_planner import (
    PlanContext,
    compute_persona_plans,
    select_trigger_and_regime,
)


def _ctx(direction="short", **kw) -> PlanContext:
    return PlanContext(direction=direction, conviction="medium", ftfc_score=-0.75, **kw)


QQQ_2026_11_06 = dict(
    close=647.05, atr=16.42, trigger_high=683.65, trigger_low=647.05,
    effective_pdh=683.65, effective_pdl=647.05,
    pwh=726.14, pwl=683.45, pmh=762.86, pml=683.45,
    pqh=748.349, pql=661.14, pyh=640.0, pyl=402.39,
    # pre_low 647.05 is an extended-hours print at exactly the prior close
    pre_high=683.50, pre_low=647.05, pre_vwap=656.60,
)
IWM_2026_11_06 = dict(
    close=270.98, atr=4.58, trigger_high=284.70, trigger_low=270.52,
    effective_pdh=284.70, effective_pdl=270.52,
    pwh=285.26, pwl=276.89, pmh=285.26, pml=269.875,
    pqh=305.18, pql=277.41, pyh=255.0, pyl=171.73,
    # 4 AM print 269.13 broke PDL and PML for real
    pre_high=283.745, pre_low=269.13, pre_vwap=272.01,
)
SPY_2026_11_06 = dict(
    close=733.00, atr=10.97, trigger_high=765.97, trigger_low=732.71,
    effective_pdh=765.97, effective_pdl=732.71,
    pwh=773.36, pwl=750.36, pmh=781.62, pml=750.36,
    pqh=779.37, pql=729.10, pyh=690.0, pyl=481.80,
    pre_high=765.5267, pre_low=730.64, pre_vwap=736.45,
)


def test_qqq_level_touched_exactly_is_not_broken():
    regime, trigger, _, distance, blue = select_trigger_and_regime(_ctx(**QQQ_2026_11_06), "short")
    assert trigger == pytest.approx(647.05, abs=0.001)  # PDL, not PYL 402.39
    assert regime == "normal" and blue is False
    assert distance < 1.0


def test_iwm_far_yearly_low_is_not_a_trigger():
    """IWM broke PDL 270.52 and PML 269.875 pre-market; the next real
    level below is PYL 171.73, about 22 ATR away. No level is
    synthesized, so the short plan waits for the opening range."""
    regime, trigger, _, distance, blue = select_trigger_and_regime(_ctx(**IWM_2026_11_06), "short")
    assert trigger is None and distance is None and blue is False
    assert regime == "orb_only"
    for plan in compute_persona_plans(_ctx(**IWM_2026_11_06)):
        assert plan.regime == "orb_only" and plan.position_size_pct == 0.0


def test_spy_unchanged():
    regime, trigger, _, _, blue = select_trigger_and_regime(_ctx(**SPY_2026_11_06), "short")
    assert trigger == pytest.approx(729.10, abs=0.001)  # PQL, within 1 ATR
    assert regime == "normal" and blue is False


@pytest.mark.parametrize("ticker", [QQQ_2026_11_06, SPY_2026_11_06])
def test_every_persona_entry_is_within_the_cap(ticker):
    ctx = _ctx(**ticker)
    for plan in compute_persona_plans(ctx):
        assert plan.regime == "normal"
        for edge in (plan.entry_zone.low, plan.entry_zone.high):
            assert abs(edge - ctx.reference_price()) <= 3.0 * ctx.atr + 0.40 * ctx.atr


def test_cap_uses_this_tickers_own_atr():
    """Same prices, different ATR: a level 4 points away is a trigger at
    ATR 2 (2 ATR) and is past the cap at ATR 1 (4 ATR), leaving no trigger."""
    base = dict(
        close=100.0, trigger_high=101.0, trigger_low=99.0,
        effective_pdh=101.0, effective_pdl=99.0,  # both cleared by pre-market
        pwh=101.2, pwl=99.5, pmh=104.0, pml=90.0,
        pqh=120.0, pql=80.0, pyh=130.0, pyl=70.0,
        pre_high=101.5, pre_low=99.0, pre_vwap=100.0,
    )
    _, wide, _, _, wide_blue = select_trigger_and_regime(_ctx("long", atr=2.0, **base), "long")
    _, tight, _, _, tight_blue = select_trigger_and_regime(_ctx("long", atr=1.0, **base), "long")
    assert wide == pytest.approx(104.0) and wide_blue is False
    assert tight is None and tight_blue is False


def test_long_level_touched_exactly_is_not_broken():
    ctx = _ctx(
        "long", close=100.0, atr=2.0, trigger_high=102.0, trigger_low=98.0,
        effective_pdh=102.0, effective_pdl=98.0,
        pwh=110.0, pwl=95.0, pmh=115.0, pml=90.0,
        pqh=120.0, pql=85.0, pyh=160.0, pyl=60.0,
        pre_high=102.0, pre_low=99.5, pre_vwap=100.5,
    )
    regime, trigger, _, _, blue = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(102.0) and blue is False and regime == "normal"


def test_pre_low_itself_is_never_the_trigger():
    """pre_low IS the cleared mark; the tie tolerance applies to structural
    levels only, so pre_low never becomes its own short trigger."""
    regime, trigger, _, _, _ = select_trigger_and_regime(_ctx(**SPY_2026_11_06), "short")
    assert trigger != pytest.approx(730.64, abs=0.001)


def test_percent_axis_of_the_window_binds_on_its_own():
    """Reference 100, ATR 4: a level at 109 is 2.25 ATR away (inside 3 ATR)
    but 9% of price (outside 8%), so the shared window rejects it."""
    ctx = _ctx(
        "long", close=100.0, atr=4.0, trigger_high=100.5, trigger_low=98.0,
        effective_pdh=100.5, effective_pdl=98.0,  # PDH cleared by pre_high
        pwh=109.0, pwl=95.0, pmh=120.0, pml=90.0,
        pqh=130.0, pql=85.0, pyh=160.0, pyl=60.0,
        pre_high=101.0, pre_low=99.5, pre_vwap=100.0,
    )
    regime, trigger, _, _, blue = select_trigger_and_regime(ctx, "long")
    assert trigger is None and blue is False and regime == "orb_only"


@pytest.mark.parametrize("direction", ["long", "short"])
def test_no_trigger_is_ever_synthesized(direction):
    """Every trigger the planner returns is one of the context's own
    levels; when none qualifies there is no trigger at all."""
    for t in (QQQ_2026_11_06, IWM_2026_11_06, SPY_2026_11_06):
        ctx = _ctx(direction, **t)
        _, trigger, _, _, blue = select_trigger_and_regime(ctx, direction)
        assert blue is False
        if trigger is not None:
            real = {round(float(v), 4) for k, v in t.items()
                    if k not in ("close", "atr", "pre_vwap") and v is not None}
            assert round(trigger, 4) in real
