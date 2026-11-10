"""FEAT-STRAT-001 done_when 5, 6 and 7: one window, one level set and side
rule, one broken rule.

* Window: 3 x the ticker's own ATR(14) and 8% of the reference, on the
  brief, planner, signal-monitor refresh, playbook resolver and movement
  statement paths; ATR missing gives atr_unavailable on both sides.
* Side rule: a candidate is long when its cent is at or above the
  cleared-above mark and short when at or below the cleared-below mark,
  whatever kind of level it is; closes count.
* Broken rule: a level touched to the cent is unbroken.

The synthetic fixtures go through the brief's projection (SessionLevels to
LevelMap to format_levels_for_brief, the block the brief prints and
stores) and the planner's (context_from_bundle then
select_trigger_and_regime and compute_persona_plans). The QQQ fixture goes
through the brief's production loop and the planner's production path.

On origin/main the side-rule fixtures fail (the planner walked only highs
for a long and had no closes), the QQQ PDL fixture fails (the brief's cents
partition dropped 647.05), and the atr_unavailable cases fail (the brief
fell back to the percent axis; the signal monitor passed no ATR).
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from lib.strat_levels import (
    SessionLevels,
    build_session_levels,
    format_levels_for_brief,
    price_cents,
)
from tests.lib import strat_2026_11_06 as fx
from tests.lib.session_levels_helpers import basis

ATR = 3.0          # window: min(3 x 3, 8% of 100) = 8 points around 100


# ── surfaces ─────────────────────────────────────────────────────────────

def _brief_pick(b: dict, side: str):
    """The brief's printed trigger for one side: (price, name) or None."""
    lm = SessionLevels.from_basis(b).to_level_map()
    text = format_levels_for_brief(lm, "neutral")
    label = "CALLS above" if side == "long" else "PUTS below"
    m = re.search(rf"{label} ([0-9.]+) \(([^)]+)\)", text)
    return (float(m.group(1)), m.group(2)) if m else None


def _planner_ctx(b: dict, direction: str):
    from lib.agents.trade_planner import context_from_bundle
    bundle = {
        "ticker": b["ticker"],
        "market": {"close": b["prior_close"], "atr_14": b["atr"] or 0.0},
        "strat": {"ftfc_score": 0.8 if direction == "long" else -0.8},
        "session_levels": {"available": True, "source": "level_basis", "level_basis": b},
    }
    return context_from_bundle(bundle, direction, "medium")


def _planner_pick(b: dict, side: str):
    from lib.agents.trade_planner import compute_persona_plans, select_trigger_and_regime
    ctx = _planner_ctx(b, side)
    _regime, trigger, _stop, _dist, _blue = select_trigger_and_regime(ctx, side)
    if trigger is None:
        return None
    plans = compute_persona_plans(ctx)
    assert plans and all(p.entry_zone is not None for p in plans)
    return (trigger, ctx.levels.side(side).trigger["name"])


def _both(b: dict, side: str):
    return _brief_pick(b, side), _planner_pick(b, side)


# ── side rule (no premarket snapshot, reference = prior close 100) ───────

@pytest.mark.parametrize("levels, side, expected", [
    ({"PWL": 103.0, "PDH": 106.0}, "long", (103.0, "PWL")),   # a low above price is resistance
    ({"PYH": 97.0, "PDL": 94.0}, "short", (97.0, "PYH")),     # a high below price is support
    ({"PWC": 102.0, "PDH": 104.0}, "long", (102.0, "PWC")),   # closes count
], ids=["low_above_is_long", "high_below_is_short", "close_is_a_level"])
def test_side_rule_in_the_brief_and_the_planner(levels, side, expected):
    b = basis(levels, prior_close=100.0, atr=ATR)
    brief, planner = _both(b, side)
    assert brief == expected
    assert planner[0] == pytest.approx(expected[0]) and planner[1] == expected[1]


# ── touch fixtures (reference 100 = pre_vwap) ───────────────────────────

def test_premarket_high_touching_pwh_keeps_pwh_unbroken():
    b = basis({"PWH": 101.0, "PDL": 96.0}, prior_close=100.0, atr=ATR,
              premarket={"pre_high": 101.0, "pre_low": 99.6, "pre_vwap": 100.0})
    brief, planner = _both(b, "long")
    assert brief == (101.0, "PWH")
    assert planner == (pytest.approx(101.0), "PWH")
    trig = SessionLevels.from_basis(b).long.trigger
    assert "PMK_H" in trig["aliases"]                 # one rung, the structural name


def test_premarket_low_touching_pwl_keeps_pwl_unbroken():
    b = basis({"PWL": 99.0, "PDH": 104.0}, prior_close=100.0, atr=ATR,
              premarket={"pre_high": 100.4, "pre_low": 99.0, "pre_vwap": 100.0})
    brief, planner = _both(b, "short")
    assert brief == (99.0, "PWL")
    assert planner == (pytest.approx(99.0), "PWL")


def test_qqq_touch_fixture_unfiltered_low_on_pdl():
    """Reference 650.00, unfiltered pre_low 647.05, PDL 647.05: PDL is the
    short trigger in both, one rung named for the structural level."""
    b = basis({"PDL": 647.05, "PDH": 683.65, "PQL": 661.14, "PYH": 637.01},
              prior_close=647.05, atr=16.42, ticker="QQQ",
              premarket={"pre_high": 652.0, "pre_low": 647.05, "pre_vwap": 650.0})
    brief, planner = _both(b, "short")
    assert brief == (647.05, "PDL")
    assert planner == (pytest.approx(647.05), "PDL")
    sl = SessionLevels.from_basis(b)
    assert sl.short.trigger["aliases"] == ["PMK_L"]
    assert [c["name"] for c in sl.short.candidates].count("PDL") == 1


# ── the reference's own cent (spec revision 2) ──────────────────────────

def test_no_premarket_level_on_the_references_cent_is_on_neither_list():
    """done_when 6 fixture: prior close and reference 100, PDC 100, PWL 103,
    PYH 97 give long trigger PWL 103 and short trigger PYH 97, not PDC 100
    on both sides, in both the brief and the planner."""
    b = basis({"PDC": 100.0, "PWL": 103.0, "PYH": 97.0}, prior_close=100.0, atr=ATR)
    assert _both(b, "long") == ((103.0, "PWL"), (pytest.approx(103.0), "PWL"))
    assert _both(b, "short") == ((97.0, "PYH"), (pytest.approx(97.0), "PYH"))
    sl = SessionLevels.from_basis(b)
    assert sl.reference_source == "prior_close"
    for side in (sl.long, sl.short):
        assert all(c["cents"] != 10000 for c in side.candidates)
    assert any(lv.name == "PDC" for lv in sl.levels)          # still a level


def test_no_premarket_any_level_sharing_the_references_cent_is_on_neither_list():
    b = basis({"PDC": 100.0, "PWH": 100.0, "PWL": 103.0, "PYH": 97.0},
              prior_close=100.0, atr=ATR)
    sl = SessionLevels.from_basis(b)
    assert sl.long.trigger["name"] == "PWL" and sl.short.trigger["name"] == "PYH"
    names = {c["name"] for side in (sl.long, sl.short) for c in side.candidates}
    assert not names & {"PDC", "PWH"}


def test_with_premarket_a_level_on_the_references_cent_is_on_both_lists():
    """With a snapshot nothing changes: a level on the reference's own cent
    with no premarket beyond it is on both lists."""
    b = basis({"PDC": 100.0, "PWL": 103.0, "PYH": 97.0}, prior_close=100.0, atr=ATR,
              premarket={"pre_high": 100.0, "pre_low": 100.0, "pre_vwap": 100.0})
    sl = SessionLevels.from_basis(b)
    assert sl.reference_source == "pre_vwap"
    assert sl.long.trigger["name"] == "PDC" and sl.short.trigger["name"] == "PDC"
    assert _brief_pick(b, "long") == (100.0, "PDC")


# ── broken rule on the real 2026-11-06 QQQ session ──────────────────────

def _short_list(side_dict: dict) -> list:
    return [(c["name"], c["cents"], c["broken"]) for c in side_dict["candidates"]
            if c["in_window"]]


def test_qqq_pdl_is_unbroken_behind_the_premarket_low_in_the_brief(monkeypatch):
    out = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))
    short = out["level_basis"]["short"]
    assert short["trigger"]["name"] == "PMK_L"
    assert price_cents(short["trigger"]["price"]) == 64962
    rungs = [(c["name"], c["cents"]) for c in short["candidates"]
             if not c["broken"] and c["in_window"]]
    assert rungs[:2] == [("PMK_L", 64962), ("PDL", 64705)]
    assert short["targets"][0]["name"] == "PDL"
    ladder = [lv["price"] for lv in out["level_basis"]["short"]["ladder"]]
    assert ladder == [649.62, 647.05]


def test_qqq_pdl_is_unbroken_behind_the_premarket_low_in_the_planner(monkeypatch):
    _section, ctx, plans, _ = fx.run_planner(monkeypatch, "QQQ", fx.loader_frame("QQQ"), "short")
    rungs = [(c["name"], c["cents"]) for c in ctx.levels.short.rungs]
    assert rungs[:2] == [("PMK_L", 64962), ("PDL", 64705)]
    pdl = next(c for c in ctx.levels.short.candidates if c["name"] == "PDL")
    assert pdl["broken"] is False
    assert all(p.entry_zone is not None for p in plans)


# ── one window on every path ────────────────────────────────────────────

def _assert_in_window(prices, ref, atr):
    lim = min(3.0 * atr, 0.08 * ref)
    for p in prices:
        assert abs(p - ref) <= lim + 1e-9, (p, ref, atr)


def _no_atr(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ATR14"] = float("nan")
    return out


def test_brief_window_and_atr_unavailable(monkeypatch):
    out = fx.run_brief(monkeypatch, "SPY", fx.loader_frame("SPY"))
    b = out["level_basis"]
    for side in ("long", "short"):
        s = b[side]
        rung_prices = [c["price"] for c in s["candidates"] if not c["broken"] and c["in_window"]]
        _assert_in_window(rung_prices, b["reference"], b["atr"])
        far = [c for c in s["candidates"] if not c["in_window"]]
        assert far and all(c["name"] not in {t["name"] for t in s["targets"]} for c in far)
    assert b["atr"] == pytest.approx(fx.prior_atr("SPY"))

    # The brief computes ATR(14) itself from the bars it loads; make that
    # indicator come back empty.
    from gcp import premarket_brief as pb
    real = pb.add_brief_indicators

    def no_atr(df, **k):
        out = real(df, **k)
        out["ATR14"] = float("nan")
        return out

    monkeypatch.setattr(pb, "add_brief_indicators", no_atr)
    none = fx.run_brief(monkeypatch, "SPY", fx.loader_frame("SPY"))["level_basis"]
    assert none["atr"] is None and none["levels"]
    for side in ("long", "short"):
        assert none[side]["trigger"] is None
        assert none[side]["reason"] == "atr_unavailable"


def test_planner_window_and_atr_unavailable(monkeypatch):
    _s, ctx, _p, _ = fx.run_planner(monkeypatch, "SPY", fx.loader_frame("SPY"), "long")
    for side in ("long", "short"):
        _assert_in_window([c["price"] for c in ctx.levels.side(side).rungs],
                          ctx.levels.reference, ctx.levels.atr)

    _s, ctx, plans, _ = fx.run_planner(monkeypatch, "SPY", _no_atr(fx.loader_frame("SPY")), "long")
    assert ctx.levels.long.trigger is None and ctx.levels.short.trigger is None
    assert ctx.orb_only_reason("long") == "atr_unavailable"
    assert ctx.orb_only_reason("short") == "atr_unavailable"
    # safe_atr never feeds the level walk: plans stay null on the side.
    for p in plans:
        assert p.entry_zone is None and p.stop is None and p.targets == []


def _monitor_refresh(monkeypatch, frame):
    from gcp import signal_monitor as sm
    monitor = sm.SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = datetime(2026, 11, 6, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(monitor, "_live_level_basis", lambda *a, **k: None)

    class _L:
        def __init__(self, *a, **k):
            pass

        def load_daily(self, *a, **k):
            return frame.copy()

    monkeypatch.setattr("lib.data_loader.DataLoader", _L)
    monitor.refresh_level_map("SPY")
    return monitor.session_levels["SPY"]


def test_signal_monitor_refresh_window_and_atr_unavailable(monkeypatch):
    sl = _monitor_refresh(monkeypatch, fx.loader_frame("SPY"))
    assert sl.atr == pytest.approx(fx.prior_atr("SPY"))
    for side in ("long", "short"):
        _assert_in_window([c["price"] for c in sl.side(side).rungs], sl.reference, sl.atr)
    assert sl.long.trigger["name"] == "PMK_H" and sl.short.trigger["name"] == "PMK_L"

    sl = _monitor_refresh(monkeypatch, _no_atr(fx.loader_frame("SPY")))
    assert sl.long.reason == "atr_unavailable" and sl.short.reason == "atr_unavailable"
    assert sl.long.trigger is None and sl.short.trigger is None


def _resolver_engine(ticker, *, atr_missing=False):
    from sqlalchemy import create_engine
    eng = create_engine("sqlite://")
    d = fx.daily(ticker)
    atr = fx.wilder_atr(d)
    rows = pd.DataFrame({
        "ticker": ticker, "date": [t.date().isoformat() for t in d.index],
        "open": d["Open"].values, "high": d["High"].values, "low": d["Low"].values,
        "close": d["Close"].values,
        "atr_14": [None] * len(d) if atr_missing else atr.values,
        "strat_candle": "", "strat_combo": "",
        "pre_high": None, "pre_low": None, "pre_vwap": None, "gap_pct": None,
    })
    snap = fx.session_premarket(ticker)
    rows = pd.concat([rows, pd.DataFrame([{
        "ticker": ticker, "date": fx.SESSION.isoformat(), "open": None, "high": None,
        "low": None, "close": None, "atr_14": None, "strat_candle": "", "strat_combo": "",
        "pre_high": snap["pre_high"], "pre_low": snap["pre_low"],
        "pre_vwap": snap["pre_vwap"], "gap_pct": snap["gap_pct"]}])], ignore_index=True)
    rows.to_sql("market_data_daily", eng, index=False)
    return eng


def test_playbook_resolver_window_and_atr_unavailable():
    from gcp.premarket_playbook_resolver import derive_level_map_from_daily
    got = derive_level_map_from_daily("SPY", fx.SESSION, _resolver_engine("SPY"))
    assert got["calls_trigger_price"] == pytest.approx(738.04)
    assert got["puts_trigger_price"] == pytest.approx(730.64)
    ref = fx.session_premarket("SPY")["pre_vwap"]
    prices = [got[k] for k in ("calls_trigger_price", "calls_t1_price", "calls_t2_price",
                               "calls_t3_price", "puts_trigger_price", "puts_t1_price",
                               "puts_stop_price", "calls_stop_price") if got.get(k) is not None]
    _assert_in_window(prices, ref, fx.prior_atr("SPY"))

    none = derive_level_map_from_daily("SPY", fx.SESSION, _resolver_engine("SPY", atr_missing=True))
    assert none["calls_trigger_price"] is None and none["puts_trigger_price"] is None


def _dashboard(monkeypatch):
    import sys
    from pathlib import Path
    pytest.importorskip("fastapi")
    root = Path(__file__).resolve().parents[2]
    for p in (str(root / "platform"), str(root / "platform" / "api")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from routers import dashboard
    monkeypatch.setattr(dashboard, "_query_fn", None)     # no live level_basis row
    return dashboard


def _movement_map(monkeypatch, frame):
    dashboard = _dashboard(monkeypatch)
    from lib.data_loader import DataLoader
    monkeypatch.setattr(DataLoader, "load_daily", lambda *a, **k: frame.copy())
    return dashboard._build_movement_level_map("SPY", analysis_date=fx.SESSION)


def test_movement_statement_window_and_atr_unavailable(monkeypatch):
    lm = _movement_map(monkeypatch, fx.loader_frame("SPY"))
    assert lm is not None
    assert lm.calls_trigger["trigger_name"] == "PMK_H"
    assert lm.puts_trigger["trigger_name"] == "PMK_L"
    rungs = [lv["price"] for lv in lm.call_levels + lm.put_levels]
    rungs += [t["price"] for t in lm.calls_trigger["targets"] + lm.puts_trigger["targets"]]
    _assert_in_window(rungs, lm.current_price, fx.prior_atr("SPY"))

    lm = _movement_map(monkeypatch, _no_atr(fx.loader_frame("SPY")))
    assert lm.calls_trigger is None and lm.puts_trigger is None
    assert lm.reason_long == "atr_unavailable" and lm.reason_short == "atr_unavailable"
    assert lm.call_levels == [] and lm.put_levels == []
