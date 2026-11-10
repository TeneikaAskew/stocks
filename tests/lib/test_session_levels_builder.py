"""FEAT-STRAT-001 done_when 3: the session date.

build_session_levels bounds daily bars to dates before the session, drops
null-close rows, takes previous periods by period filter, finds the parent
bar from the last completed bar, returns stale_daily when the prior session
is missing, and refuses a premarket snapshot dated another day. Each case is
also driven through a production path (the planner's
summarize_session_levels, the brief's playbook loop). On origin/main these
fail: summarizers read the newest row as "today" (AVGO PDL 321.74, the
2026-11-05 pre_vwap 318.14) and the brief reads the prior day's premarket.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from lib.strat_levels import build_session_levels, find_parent_bar
from tests.lib import strat_2026_11_06 as fx

SESSION = fx.SESSION


def _avgo_frame_before_its_row_exists() -> pd.DataFrame:
    """AVGO at 08:45 ET on 2026-11-06 before that day's market_data_daily
    row exists: bars through 2026-11-05, whose row still carries the
    2026-11-05 premarket (pre_vwap 318.14)."""
    df = fx.daily("AVGO").copy()
    df["ATR14"] = fx.wilder_atr(df)
    for col in ("pre_high", "pre_low", "pre_vwap", "gap_pct"):
        df[col] = float("nan")
    df.loc[pd.Timestamp("2026-11-05"), "pre_vwap"] = 318.14
    return df


def test_avgo_live_before_the_session_row_exists():
    df = _avgo_frame_before_its_row_exists()
    from lib.strat_levels import premarket_snapshot_from_daily
    snap = premarket_snapshot_from_daily(df, SESSION)
    assert snap is None                      # 2026-11-05's pre_vwap is not this session's
    sl = build_session_levels("AVGO", SESSION, df, float(df["ATR14"].iloc[-1]), snap)
    assert sl.status == "ok"
    assert sl.level_named("PDL").price == pytest.approx(290.12)   # not 321.74
    assert sl.level_named("PDH").price == pytest.approx(314.0)
    assert sl.premarket is None and sl.premarket_status == "premarket_unavailable"
    assert sl.reference_source == "prior_close"
    assert sl.reference == pytest.approx(291.53)


def test_avgo_through_the_planners_production_path(monkeypatch):
    df = _avgo_frame_before_its_row_exists()
    section, ctx, _plans, loads = fx.run_planner(monkeypatch, "AVGO", df, "long")
    assert section["source"] == "builder" and loads == 1
    assert section["premarket_status"] == "premarket_unavailable"
    names = {lv["name"]: lv["price"] for lv in section["level_basis"]["levels"]}
    assert names["PDL"] == pytest.approx(290.12)
    assert ctx.levels.premarket is None
    assert ctx.reference_price() == pytest.approx(291.53)   # never 318.14


def test_avgo_through_the_briefs_playbook_path(monkeypatch):
    out = fx.run_brief(monkeypatch, "AVGO", _avgo_frame_before_its_row_exists())
    basis = out["level_basis"]
    names = {lv["name"]: lv["price"] for lv in basis["levels"]}
    assert names["PDL"] == pytest.approx(290.12)
    assert basis["premarket"] is None
    assert out["premarket_status"] == "premarket_unavailable"


def test_the_session_bar_and_later_bars_are_never_read():
    """A replay frame that already holds the session's completed bar (and
    later ones) gives the same levels as the live frame."""
    full = fx.daily("SPY", through=None)
    live = fx.daily("SPY")
    atr = fx.prior_atr("SPY")
    a = build_session_levels("SPY", SESSION, full, atr)
    b = build_session_levels("SPY", SESSION, live, atr)
    assert a.last_bar_date == b.last_bar_date == date(2026, 11, 5)
    assert [(lv.name, lv.price) for lv in a.levels] == [(lv.name, lv.price) for lv in b.levels]
    assert a.level_named("PDH").price == pytest.approx(765.97)


def test_null_close_rows_are_dropped():
    df = fx.daily("SPY").copy()
    df.loc[pd.Timestamp("2026-11-04"), "Close"] = float("nan")
    sl = build_session_levels("SPY", SESSION, df, fx.prior_atr("SPY"))
    assert sl.status == "ok"
    assert all(lv.price == lv.price for lv in sl.levels)
    assert sl.level_named("PDC").price == pytest.approx(733.0)


def _bars(rows, start="2026-10-26"):
    idx = pd.bdate_range(start, periods=len(rows))
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)
    df["Time"] = df.index
    return df


def test_a_prior_2u_bar_gives_its_own_high_and_low():
    """The frame ends at the prior session and that bar is a 2U: its high
    and low are the day levels and it is its own parent bar (the origin/main
    summarizer read the bar before it)."""
    df = _bars([(100, 103, 98, 101), (101, 102, 99, 100), (100, 102.5, 99.5, 102),
                (102, 106, 101, 105)])          # last bar 2U over (102.5, 99.5)
    session = (df.index[-1] + pd.offsets.BDay(1)).date()
    sl = build_session_levels("TST", session, df, 2.0)
    assert sl.level_named("PDH").price == 106.0
    assert sl.level_named("PDL").price == 101.0
    assert sl.level_named("parent_bar_high").price == 106.0
    assert sl.level_named("parent_bar_low").price == 101.0


def test_a_prior_2u_bar_through_the_planners_production_path(monkeypatch):
    from lib.agents import summarizers
    df = _bars([(100, 103, 98, 101), (101, 102, 99, 100), (100, 102.5, 99.5, 102),
                (102, 106, 101, 105)])
    df["ATR14"] = 2.0
    session = (df.index[-1] + pd.offsets.BDay(1)).date()
    monkeypatch.setattr(summarizers, "_query", lambda *a, **k: pd.DataFrame())

    class _L:
        def load_daily(self, *a, **k):
            return df.copy()

    out = summarizers.summarize_session_levels("TST", as_of=session, loader=_L())
    names = {lv["name"]: lv["price"] for lv in out["level_basis"]["levels"]}
    assert names["PDH"] == 106.0 and names["PDL"] == 101.0
    assert names["parent_bar_high"] == 106.0


def test_an_inside_prior_bar_walks_back_to_its_parent():
    df = _bars([(100, 110, 90, 105), (104, 108, 95, 100), (100, 107, 96, 101)])
    assert find_parent_bar(df) == (110.0, 90.0, str(df.index[0].date()))


def test_a_missing_prior_session_is_stale_daily():
    df = fx.daily("SPY", through=date(2026, 11, 2))     # last bar Monday, session Friday
    sl = build_session_levels("SPY", SESSION, df, fx.prior_atr("SPY"),
                              fx.session_premarket("SPY"))
    assert sl.status == "stale_daily"
    assert sl.levels == []
    for side in (sl.long, sl.short):
        assert side.trigger is None and side.reason == "stale_daily"


def test_a_premarket_snapshot_dated_another_day_is_refused():
    snap = dict(fx.session_premarket("SPY"), date="2026-11-05")
    sl = build_session_levels("SPY", SESSION, fx.daily("SPY"), fx.prior_atr("SPY"), snap)
    assert sl.premarket is None and sl.premarket_status == "premarket_unavailable"
    assert sl.level_named("PMK_H") is None
    later = sl.with_premarket(snap)
    assert later.premarket is None
    undated = {k: v for k, v in fx.session_premarket("SPY").items() if k != "date"}
    assert build_session_levels("SPY", SESSION, fx.daily("SPY"), fx.prior_atr("SPY"),
                                undated).premarket is None


def test_the_brief_reads_the_sessions_own_premarket_row(monkeypatch):
    """At 08:30 ET the loader frame holds the session's own premarket row
    (written 08:20) and the prior day's row with that day's premarket. The
    brief uses the session's (the origin/main loop read the prior day's)."""
    frame = fx.loader_frame("QQQ")
    frame.loc[pd.Timestamp("2026-11-05"), ["pre_high", "pre_low", "pre_vwap"]] = [690.0, 640.0, 684.0]
    out = fx.run_brief(monkeypatch, "QQQ", frame)
    pm = out["level_basis"]["premarket"]
    assert pm["date"] == "2026-11-06"
    assert pm["pre_high"] == pytest.approx(660.398)
    assert pm["pre_low"] == pytest.approx(649.62)
    assert out["premarket_status"] == "ok"
