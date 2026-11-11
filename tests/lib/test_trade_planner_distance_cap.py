"""FEAT-INSIGHT-001 distance cap, now read from the one level builder.

Regression for the 2026-11-06 insight reports, where the short triggers
for IWM (171.73) and QQQ (402.39) were the 2025 yearly lows, 15 to 22
ATR below price. FEAT-STRAT-001 moved the walk into
lib.strat_levels.build_session_levels and made the session's premarket
high and low candidates, so the picks below follow those rules: the
ticker's window (trigger_window_{long,short}_atr x ATR, here the #1753 value 3) still keeps far levels out,
and nothing is ever synthesized. Inputs are that morning's values with the
UNFILTERED premarket extremes the FEAT-INSIGHT-001 tests used.
"""

import pytest

from lib.agents.trade_planner import (
    PlanContext,
    compute_persona_plans,
    select_trigger_and_regime,
)
from tests.lib.level_params_fixtures import fixture_params
from tests.lib.session_levels_helpers import session

_NAMES = {"effective_pdh": "PDH", "effective_pdl": "PDL", "pwh": "PWH", "pwl": "PWL",
          "pmh": "PMH", "pml": "PML", "pqh": "PQH", "pql": "PQL", "pyh": "PYH", "pyl": "PYL"}


def _ctx(direction="short", *, close, atr, pre_high=None, pre_low=None, pre_vwap=None,
         **levels) -> PlanContext:
    named = {_NAMES[k]: v for k, v in levels.items() if k in _NAMES}
    pm = None
    if pre_high is not None or pre_low is not None or pre_vwap is not None:
        pm = {"pre_high": pre_high, "pre_low": pre_low, "pre_vwap": pre_vwap}
    sl = session(named, prior_close=close, atr=atr, premarket=pm)
    return PlanContext(direction=direction, conviction="medium", close=close, atr=atr,
                       levels=sl, ftfc_score=-0.75 if direction == "short" else 0.75)


QQQ_2026_11_06 = dict(
    close=647.05, atr=16.42,
    effective_pdh=683.65, effective_pdl=647.05,
    pwh=726.14, pwl=683.45, pmh=762.86, pml=683.45,
    pqh=748.349, pql=661.14, pyh=637.01, pyl=402.39,
    # pre_low 647.05 is an extended-hours print at exactly the prior close
    pre_high=683.50, pre_low=647.05, pre_vwap=656.60,
)
IWM_2026_11_06 = dict(
    close=270.98, atr=4.58,
    effective_pdh=284.70, effective_pdl=270.52,
    pwh=285.26, pwl=276.0, pmh=285.26, pml=269.875,
    pqh=305.18, pql=277.41, pyh=258.2, pyl=171.73,
    # 4 AM print 269.13 broke PDL and PML for real
    pre_high=283.745, pre_low=269.13, pre_vwap=272.01,
)
SPY_2026_11_06 = dict(
    close=733.00, atr=10.97,
    effective_pdh=765.97, effective_pdl=732.71,
    pwh=773.36, pwl=750.36, pmh=781.62, pml=750.36,
    pqh=779.37, pql=729.10, pyh=691.66, pyl=481.80,
    pre_high=765.5267, pre_low=730.64, pre_vwap=736.45,
)


def test_qqq_level_touched_exactly_is_not_broken():
    ctx = _ctx(**QQQ_2026_11_06)
    regime, trigger, _, distance, blue = select_trigger_and_regime(ctx, "short")
    assert trigger == pytest.approx(647.05, abs=0.001)  # PDL, not PYL 402.39
    assert ctx.levels.short.trigger["name"] == "PDL"     # one rung, the structural name
    assert regime == "normal" and blue is False
    assert distance < 1.0


def test_iwm_far_yearly_low_is_never_a_trigger():
    """IWM broke PDL 270.52 and PML 269.875 premarket; the premarket low
    269.13 is the short trigger and PYL 171.73 (22 ATR away) is outside
    the window, so it is neither the trigger nor a target."""
    ctx = _ctx(**IWM_2026_11_06)
    regime, trigger, _, _distance, blue = select_trigger_and_regime(ctx, "short")
    assert trigger == pytest.approx(269.13) and blue is False and regime == "normal"
    published = {c["price"] for c in ctx.levels.short.targets}
    assert 171.73 not in published
    broken = {c["name"] for c in ctx.levels.short.candidates if c["broken"]}
    assert {"PDL", "PML"} <= broken


def test_spy_short_is_the_premarket_low():
    regime, trigger, _, _, blue = select_trigger_and_regime(_ctx(**SPY_2026_11_06), "short")
    assert trigger == pytest.approx(730.64, abs=0.001)  # PMK_L; PDL 732.71 was broken
    assert regime == "normal" and blue is False


@pytest.mark.parametrize("ticker", [QQQ_2026_11_06, SPY_2026_11_06, IWM_2026_11_06])
def test_every_persona_entry_is_within_the_cap(ticker):
    ctx = _ctx(**ticker)
    for plan in compute_persona_plans(ctx):
        assert plan.regime == "normal"
        for edge in (plan.entry_zone.low, plan.entry_zone.high):
            assert abs(edge - ctx.reference_price()) <= 3.0 * ctx.atr + 0.40 * ctx.atr


def test_cap_uses_this_tickers_own_atr():
    """Same prices, different ATR: a level 4 points away is a trigger at
    ATR 2 (2 ATR) and is past the cap at ATR 1 (4 ATR), leaving no trigger."""
    base = dict(close=100.0, pmh=104.0, pml=90.0)
    _, wide, _, _, _ = select_trigger_and_regime(_ctx("long", atr=2.0, **base), "long")
    tight_ctx = _ctx("long", atr=1.0, **base)
    _, tight, _, _, _ = select_trigger_and_regime(tight_ctx, "long")
    assert wide == pytest.approx(104.0)
    assert tight is None
    assert tight_ctx.orb_only_reason("long") == "next_level_outside_window"


def test_long_level_touched_exactly_is_not_broken():
    ctx = _ctx(
        "long", close=100.0, atr=2.0,
        effective_pdh=102.0, effective_pdl=98.0,
        pwh=110.0, pwl=95.0, pmh=115.0, pml=90.0,
        pre_high=102.0, pre_low=99.5, pre_vwap=100.5,
    )
    regime, trigger, _, _, blue = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(102.0) and blue is False and regime == "normal"
    assert ctx.levels.long.trigger["name"] == "PDH"


def test_the_tickers_window_is_the_only_axis():
    """Reference 100, ATR 4: a level at 109 is 2.25 ATR away and 9% of
    price. The percent-of-price axis is gone (per-ticker parameters,
    2026-11-08): inside the ticker's 3 x ATR window it is the trigger, and
    with a 2 x ATR window it is not."""
    ctx = _ctx("long", close=100.0, atr=4.0, effective_pdl=98.0, pwh=109.0, pwl=95.0)
    regime, trigger, _, _, blue = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(109.0) and blue is False and regime == "normal"
    named = {"PDL": 98.0, "PWH": 109.0, "PWL": 95.0}
    sl = session(named, prior_close=100.0, atr=4.0,
                 params=fixture_params("TST", overrides={"trigger_window_long_atr": 2.0}))
    narrow = PlanContext(direction="long", conviction="medium", close=100.0, atr=4.0,
                         levels=sl, ftfc_score=0.75)
    regime, trigger, _, _, blue = select_trigger_and_regime(narrow, "long")
    assert trigger is None and blue is False and regime == "orb_only"
    assert narrow.orb_only_reason("long") == "next_level_outside_window"


@pytest.mark.parametrize("direction", ["long", "short"])
def test_no_trigger_is_ever_synthesized(direction):
    """Every trigger is one of the session's own levels (structural or the
    premarket high or low); when none qualifies there is no trigger."""
    for t in (QQQ_2026_11_06, IWM_2026_11_06, SPY_2026_11_06):
        ctx = _ctx(direction, **t)
        _, trigger, _, _, blue = select_trigger_and_regime(ctx, direction)
        assert blue is False
        if trigger is not None:
            real = {round(float(v), 2) for k, v in t.items()
                    if k not in ("close", "atr", "pre_vwap") and v is not None}
            assert round(trigger, 2) in real


def test_level_exactly_at_the_cap_is_a_normal_trigger():
    """Reference 100, ATR 1, unbroken PWH 103: exactly 3 ATR away. The
    window is inclusive, so it is the trigger, and the regime is normal
    (not extended with an ORB-confirmation rationale)."""
    ctx = _ctx("long", close=100.0, atr=1.0, effective_pdl=99.0, pwh=103.0, pwl=95.0)
    regime, trigger, _, distance, blue = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(103.0) and blue is False
    assert distance == pytest.approx(3.0)
    assert regime == "normal"
    for plan in compute_persona_plans(ctx):
        assert plan.regime == "normal"
        assert "Extended gap" not in plan.rationale
