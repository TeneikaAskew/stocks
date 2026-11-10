"""FEAT-STRAT-001 done_when 2: brief and planner parity.

The brief's production playbook path (gcp.premarket_brief) and the
planner's production path (summarize_session_levels, context_from_bundle,
compute_persona_plans) run on the same 2026-11-06 inputs for SPY, QQQ and
IWM and pick the same trigger per side, each the session's filtered
premarket extreme, with the same first long target.

The fidelity test runs the level code production ran that morning (a
vendored copy of origin/main's lib/strat_levels.py) on the fixture bars,
anchored on the prior close with Wilder ATR(14), and reproduces the picks
premarket_analysis stored, so the fixture is what production saw.

On origin/main the parity test fails: the brief and the planner walked
levels separately (the planner's short for QQQ was the premarket low
647.05 at the prior close; the brief's was PYH 637.01).
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

import pytest

from lib.strat_levels import price_cents
from tests.lib import strat_2026_11_06 as fx

PARITY = {
    #       long trig  short trig  long T1   T1 name  T1 aliases
    "SPY": (738.04, 730.64, 750.36, "PWL", {"PML"}),
    "QQQ": (660.40, 649.62, 661.14, "PQL", set()),
    "IWM": (272.50, 269.13, 276.00, "PWL", set()),
}


@pytest.mark.parametrize("ticker", sorted(PARITY))
def test_brief_and_planner_pick_the_same_levels(monkeypatch, ticker):
    long_px, short_px, t1_px, t1_name, t1_aliases = PARITY[ticker]
    frame = fx.loader_frame(ticker)

    brief = fx.run_brief(monkeypatch, ticker, frame)["level_basis"]
    _l_section, long_ctx, long_plans, _ = fx.run_planner(monkeypatch, ticker, frame, "long")
    _s_section, short_ctx, short_plans, _ = fx.run_planner(monkeypatch, ticker, frame, "short")

    # Same trigger per side, in cents, from both paths.
    assert price_cents(brief["long"]["trigger"]["price"]) == price_cents(long_px)
    assert price_cents(brief["short"]["trigger"]["price"]) == price_cents(short_px)
    assert brief["long"]["trigger"]["name"] == "PMK_H"
    assert brief["short"]["trigger"]["name"] == "PMK_L"
    for ctx in (long_ctx, short_ctx):
        assert price_cents(ctx.levels.long.trigger["price"]) == price_cents(long_px)
        assert price_cents(ctx.levels.short.trigger["price"]) == price_cents(short_px)
        assert ctx.levels.long.trigger["name"] == brief["long"]["trigger"]["name"]
        assert ctx.levels.short.trigger["name"] == brief["short"]["trigger"]["name"]

    # The same ordered side lists.
    for side in ("long", "short"):
        b_rungs = [(c["name"], c["cents"]) for c in brief[side]["candidates"]
                   if not c["broken"] and c["in_window"]]
        p_rungs = [(c["name"], c["cents"]) for c in long_ctx.levels.side(side).rungs]
        assert b_rungs == p_rungs

    # First long target.
    t1 = brief["long"]["targets"][0]
    assert t1["price"] == pytest.approx(t1_px) and t1["name"] == t1_name
    assert set(t1["aliases"]) == t1_aliases
    assert long_ctx.levels.long.targets[0]["name"] == t1_name

    # Every persona plan enters at the trigger the brief prints.
    for plan in long_plans:
        assert price_cents(plan.entry_zone.low) >= price_cents(long_px)
    for plan in short_plans:
        assert price_cents(plan.entry_zone.high) <= price_cents(short_px)


# ── fidelity: the fixture is what production saw ───────────────────────

LEGACY = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_strat_levels_5e1142ae.py"

STORED = {
    # ticker: (calls trigger name, price or None, puts trigger name, price or None)
    "SPY": ("PWL", 750.36, "PDL", 732.71),
    "QQQ": ("PQL", 661.14, "PYH", 637.01),
    "IWM": ("PWL", 276.00, "PDL", 270.52),
}


@lru_cache(maxsize=1)
def _legacy():
    spec = importlib.util.spec_from_file_location("legacy_strat_levels_5e1142ae", LEGACY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("ticker", sorted(STORED))
def test_origin_main_level_code_reproduces_the_stored_picks(ticker):
    legacy = _legacy()
    df = fx.daily(ticker)
    prior_close = float(df["Close"].iloc[-1])
    lm = legacy.build_level_map(
        ticker=ticker, daily_df=df, current_price=prior_close,
        atr=fx.prior_atr(ticker), analysis_date=fx.SESSION,
    )
    c_name, c_px, p_name, p_px = STORED[ticker]
    assert lm.calls_trigger["trigger_name"] == c_name
    assert lm.calls_trigger["trigger_level"] == pytest.approx(c_px)
    assert lm.puts_trigger["trigger_name"] == p_name
    assert lm.puts_trigger["trigger_level"] == pytest.approx(p_px)
