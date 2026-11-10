"""FEAT-STRAT-001 per-ticker params, done_when 3: the calibration methods.

Each method is fed synthetic inputs with a known answer, read with the
quantile, lookback and minimum the policy rows seeded by gcp/schema.sql give
(tests.lib.level_params_fixtures.seeded_policy), changed per test where the
test says so. On origin/main and the #1753 head lib/level_calibration.py does
not exist.
"""
from __future__ import annotations

import copy
from datetime import date

import numpy as np
import pandas as pd
import pytest

from lib import level_calibration as lc
from lib.strat_levels import PARAM_OK
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import seeded_policy

T = 100.0  # trigger
ATR = 1.0


def policy(**changes):
    p = copy.deepcopy(seeded_policy())
    for key, fields in changes.items():
        p[key].update(fields)
    return p


def _bdays(n, end="2026-11-05"):
    return pd.bdate_range(end=end, periods=n)


def _daily(highs, lows=None, close=100.0, atr=1.0, end="2026-11-05"):
    idx = _bdays(len(highs), end)
    lows = lows if lows is not None else [close] * len(highs)
    return pd.DataFrame({"Open": close, "High": highs, "Low": lows, "Close": close,
                         "atr_14": atr}, index=idx)


# ── statistics ─────────────────────────────────────────────────────────


def test_quantile_is_an_observed_value():
    vals = [0.004 * i for i in range(1, 1001)]
    assert lc.quantile(vals, 0.99) == pytest.approx(3.96)
    assert lc.reach_share_value([5, 4, 3, 2, 1], 0.4) == 4
    assert lc.reach_share_value([5, 4, 3, 2, 1], 0.41) == 3


# ── trigger windows ────────────────────────────────────────────────────


def test_trigger_window_known_answer():
    """1,000 sessions whose up-excursions are 0.004 x i ATR give
    trigger_window_long_atr 3.96 at coverage 0.99 when the lookback covers
    them all; with the seeded 750-session lookback only i = 251..1000 count
    and the answer is 3.972."""
    highs = [100.0] + [100.0 + 0.004 * i for i in range(1, 1001)]
    d = lc.normalize_daily(_daily(highs), "atr_14", "2026-11-06")
    got = lc.trigger_window(d, policy(trigger_window_long_atr={"lookback_sessions": 1000}), "long")
    assert got.status == PARAM_OK and got.value == pytest.approx(3.96) and got.sample_n == 1000
    got = lc.trigger_window(d, policy(), "long")
    assert got.value == pytest.approx(3.972) and got.sample_n == 750
    assert got.input_to == d.index[-1].date().isoformat()


def test_trigger_window_short_side_and_minimum_edge():
    lows = [100.0] + [100.0 - 0.01 * i for i in range(1, 250)]
    d = lc.normalize_daily(_daily([100.0] * 250, lows), "atr_14", "2026-11-06")
    got = lc.trigger_window(d, policy(), "short")
    assert got.status == "insufficient_history" and got.sample_n == 249 and got.value is None
    lows.append(100.0 - 2.5)
    d = lc.normalize_daily(_daily([100.0] * 251, lows), "atr_14", "2026-11-06")
    got = lc.trigger_window(d, policy(), "short")
    assert got.status == PARAM_OK and got.sample_n == 250


def test_trigger_window_measures_in_the_prior_sessions_atr():
    """The excursion of session t is divided by the ATR of t - 1."""
    d = _daily([100.0, 102.0, 103.0], atr=[2.0, 4.0, 1.0])
    exc = lc.daily_excursions(lc.normalize_daily(d, "atr_14", "2026-11-06"), "long")
    assert list(exc.values) == pytest.approx([2.0 / 2.0, 3.0 / 4.0])


# ── one-minute thresholds ──────────────────────────────────────────────


def _minutes(session, n, start="09:30", **cols):
    ts = pd.date_range(f"{session.date()} {start}", periods=n, freq="1min")
    base = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}
    base.update(cols)
    return pd.DataFrame({"timestamp": ts, **{k: (v if np.ndim(v) else [v] * n) for k, v in base.items()}})


def test_pm_spike_known_answer_and_session_minimum():
    """40 sessions of 390 RTH bars with flat bodies; one bar a session has a
    0.5 ATR wick above every body around it: the 0.999 quantile of the
    31,200 wick excesses is 0.5. A session under 300 bars is not counted, so
    39 full sessions are insufficient_history with sample 39."""
    days = _bdays(41)
    d = lc.normalize_daily(_daily([100.0] * 41), "atr_14", "2026-11-06")
    frames = []
    for s in days[1:]:
        highs = np.full(390, 100.0)
        highs[200] = 100.5
        frames.append(_minutes(s, 390, high=highs))
    m = lc.normalize_minutes(pd.concat(frames), "2026-11-06")
    got = lc.pm_spike(d, m, policy())
    assert got.status == PARAM_OK and got.value == pytest.approx(0.5) and got.sample_n == 40
    short = pd.concat(frames[:39] + [_minutes(days[-1], 299)])
    got = lc.pm_spike(d, lc.normalize_minutes(short, "2026-11-06"), policy())
    assert got.status == "insufficient_history" and got.sample_n == 39


def test_wick_excess_is_the_filters_rule():
    """The excess is min(beyond own body, beyond the highest body of the two
    bars each side): a wick above its own body but inside a neighbour's
    body has no excess."""
    bars = pd.DataFrame({"open": [100, 100, 100, 101, 100], "close": [100, 100, 100, 101, 100],
                         "high": [100, 100, 100.6, 101, 100], "low": [100] * 5}, dtype=float)
    up = lc.wick_excesses(bars)[:5]
    assert up[2] == pytest.approx(-0.4)  # 0.6 above its body, 0.4 below PDH-like neighbour body
    bars.loc[2, "high"] = 101.3
    assert lc.wick_excesses(bars)[2] == pytest.approx(0.3)


def test_pm_stale_print_known_answer_drops_echo_and_spike_bars():
    """40 sessions of 70 premarket bars. Sixty clean bars a session have a
    spread of 0.002 x i ATR around their open-close midpoint (i = 1..60):
    the 0.95 quantile of the 2,400 clean spreads is 0.114. Each session also
    has five bars printing the prior close's cent and five spike bars, all
    with a 3 ATR spread; none of them is in the population."""
    days = _bdays(41)
    daily = _daily([100.0] * 41, close=[99.0] * 41)
    d = lc.normalize_daily(daily, "atr_14", "2026-11-06")
    frames = []
    for s in days[1:]:
        spreads = [0.002 * i for i in range(1, 61)]
        high = [100 + x for x in spreads] + [99.0] * 5 + [105.0] * 5
        low = [100 - x for x in spreads] + [97.0] * 5 + [100.0] * 5
        frames.append(_minutes(s, 70, start="04:00", high=np.array(high), low=np.array(low)))
    m = lc.normalize_minutes(pd.concat(frames), "2026-11-06")
    spike = lc.Calibrated("pm_spike_atr", PARAM_OK, 1.0, 40, "rth_wick_excess_quantile")
    got = lc.pm_stale_print(d, m, policy(), spike)
    assert got.status == PARAM_OK and got.value == pytest.approx(0.114) and got.sample_n == 40


def test_pm_stale_print_needs_a_calibrated_spike():
    d = lc.normalize_daily(_daily([100.0] * 3), "atr_14", "2026-11-06")
    m = lc.normalize_minutes(None, "2026-11-06")
    spike = lc.Calibrated("pm_spike_atr", "insufficient_history", None, 0, "x")
    got = lc.pm_stale_print(d, m, policy(), spike)
    assert got.status == "insufficient_history" and got.value is None


def test_no_one_minute_bars_is_insufficient_history():
    d = lc.normalize_daily(_daily([100.0] * 100), "atr_14", "2026-11-06")
    m = lc.normalize_minutes(None, "2026-11-06")
    for got in (lc.pm_spike(d, m, policy()), lc.level_cluster(d, m, policy())):
        assert got.status == "insufficient_history" and got.sample_n == 0


def test_level_cluster_known_answer():
    """40 sessions whose k-th 15-minute interval closes 0.01 x k ATR from the
    previous one (k = 1..25): the median absolute change is 0.13."""
    days = _bdays(41)
    d = lc.normalize_daily(_daily([100.0] * 41), "atr_14", "2026-11-06")
    frames = []
    for s in days[1:]:
        close, level = [], 100.0
        for j in range(390):
            k = j // 15
            if j % 15 == 0 and k > 0:
                level += 0.01 * k * (1 if k % 2 else -1)
            close.append(level)
        frames.append(_minutes(s, 390, close=np.array(close)))
    m = lc.normalize_minutes(pd.concat(frames), "2026-11-06")
    got = lc.level_cluster(d, m, policy())
    assert got.status == PARAM_OK and got.value == pytest.approx(0.13) and got.sample_n == 40
    got = lc.level_cluster(d, lc.normalize_minutes(pd.concat(frames[:39]), "2026-11-06"), policy())
    assert got.status == "insufficient_history" and got.sample_n == 39


# ── breaks ─────────────────────────────────────────────────────────────


def mk_break(bars, *, side="long", held=True, session="2026-10-01", trigger=T, atr=ATR):
    """bars: (open, high, low, close) from the break bar on, one a minute
    from 09:45."""
    ts = pd.date_range(f"{session} 09:45", periods=len(bars), freq="1min")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], dtype=float)
    df.insert(0, "timestamp", ts)
    return lc.Break(session=pd.Timestamp(session), side=side, trigger=trigger, atr=atr,
                    held=held, bars=df)


def test_follow_through_stops_at_the_retest_and_the_time_limit():
    b = mk_break([(T, T + 0.3, T, T + 0.3), (T + 0.3, T + 0.8, T + 0.1, T + 0.5),
                  (T + 0.5, T + 0.5, T, T), (T, T + 3, T, T + 3)])
    assert lc.follow_through(b, 15) == pytest.approx(0.8)
    run = [(T, T + 0.1 * (j + 1), T + 0.01, T) for j in range(20)]
    run[0] = (T, T + 0.1, T, T)
    assert lc.follow_through(mk_break(run), 15) == pytest.approx(1.5)
    short = mk_break([(T, T, T - 0.4, T - 0.4), (T - 0.4, T, T - 0.6, T)], side="short")
    assert lc.follow_through(short, 15) == pytest.approx(0.4)


def test_fill_bar_adverse_extreme_counts_and_its_stop_ends_the_trade():
    """A long filled at the fill bar's open whose same bar trades 2 ATR lower,
    later bars staying above the fill: adverse excursion 2 ATR. With a stop
    inside 2 ATR the fill bar takes it, and the later rally reaches no
    target."""
    m = T + 0.5
    b = mk_break([(T, T + 0.5, T, T + 0.5), (m, m, m - 2.0, m), (m, m + 3, m + 0.1, m + 3)])
    o = lc.persona_outcome(b, m)
    assert o.filled and o.mae_atr >= 2.0
    assert lc.persona_outcome(b, m, risk_atr=1.5).reach_r == 0.0
    assert lc.persona_outcome(b, m, risk_atr=2.5).reach_r == pytest.approx(3 / 2.5)


def test_the_fill_bars_favourable_extreme_counts_toward_nothing():
    m = T + 0.5
    b = mk_break([(T, T + 0.5, T, T + 0.5), (m, m + 4, m - 0.1, m), (m, m + 1, m - 0.1, m)])
    assert lc.persona_outcome(b, m, risk_atr=1.0).reach_r == pytest.approx(1.0)


def test_a_bar_touching_stop_and_target_counts_as_stopped():
    m = T + 0.5
    b = mk_break([(T, T + 0.5, T, T + 0.5), (m, m, m - 0.1, m), (m, m + 5, m - 1.0, m),
                  (m, m + 6, m, m)])
    assert lc.persona_outcome(b, m, risk_atr=1.0).reach_r == 0.0


def test_a_break_never_trading_back_to_the_midpoint_is_unfilled():
    b = mk_break([(T, T + 0.3, T, T + 0.3), (T + 0.3, T + 2, T + 0.3, T + 2)])
    assert lc.persona_fill(b, T + 0.2) is None
    assert not lc.persona_outcome(b, T + 0.2).filled


def _family(n, *, held=True, up=None, dn=None):
    """n long breaks with follow-through exactly 1 ATR (bar 0 runs to T+1,
    bar 1 retests to T), so every entry buffer quantile is 1.0 except the
    at_trigger edges (0): aggressive and neutral fill at T+0.5, conservative
    at T+1, all on bar 1, whose low T is an adverse excursion of 0.5 and 1.0
    from those fills. Bar 2 trades down a_i = dn(i) below T and up u_i =
    up(i) above the aggressive fill."""
    out = []
    for i in range(1, n + 1):
        a = dn(i) if dn else 0.01 * i
        u = up(i) if up else 0.02 * i
        out.append(mk_break([(T, T + 1, T, T + 1), (T + 1, T + 1, T, T + 0.5),
                             (T + 0.5, T + 0.5 + u, T - a, T)], held=held,
                            session=str(_bdays(n)[i - 1].date())))
    return out


def test_break_params_known_answers():
    """200 held breaks of the family: stop_aggressive (q 0.90 of 0.5 + a_i) =
    2.30, stop_neutral (q 0.75) = 2.00, stop_conservative (q 0.60 of
    1.0 + a_i) = 2.20, min_stop (q 0.50, neutral) = 1.50. Aggressive targets:
    risk 2.30 ATR, stop at T - 1.80, so breaks i >= 180 are stopped on bar 2
    (stop and target on one bar count as stopped) and reach 0; break i < 180
    reaches 0.02 i / 2.30 R. Bar 2's rally is cut to 0 from i = 175, away
    from the stop's own boundary (the 180th break touches the stop exactly),
    so the reaches are 0.02 i / 2.30 for i < 175 and 0 after. T1 at share
    0.40 is the 80th largest reach (i = 95), T2 at 0.25 the 50th (i = 125),
    T3 at 0.15 the 30th (i = 145)."""
    out = lc.break_params(_family(200, up=lambda i: 0.02 * i if i < 175 else 0.0), policy())
    v = {k: c.value for k, c in out.items()}
    assert v["entry_buffer_aggressive_lo_atr"] == 0.0 and v["entry_buffer_aggressive_hi_atr"] == 1.0
    assert v["entry_buffer_conservative_lo_atr"] == 1.0
    assert v["stop_aggressive_atr"] == pytest.approx(2.30)
    assert v["stop_neutral_atr"] == pytest.approx(2.00)
    assert v["stop_conservative_atr"] == pytest.approx(2.20)
    assert v["min_stop_atr"] == pytest.approx(1.50)
    assert v["target_aggressive_1_r"] == pytest.approx(0.02 * 95 / 2.30)
    assert v["target_aggressive_2_r"] == pytest.approx(0.02 * 125 / 2.30)
    assert v["target_aggressive_3_r"] == pytest.approx(0.02 * 145 / 2.30)
    for persona in lc.PERSONAS:
        ts = [c for k, c in sorted(out.items()) if k.startswith(f"target_{persona}_") and c.ok]
        assert all(t.value > 0 for t in ts)
        assert all(b.value > a.value for a, b in zip(ts, ts[1:]))


def test_unfilled_breaks_are_outside_the_conservative_populations():
    """100 breaks run 1.5 ATR and never trade back below T + 1.2. With the
    family's 200 they put the conservative midpoint at T + 1.0 (both its
    quantiles are 1.0), which those 100 never trade at after their break
    bar: they are outside the conservative stop and target populations,
    which hold the family's 200 filled breaks only."""
    never = [mk_break([(T, T + 1.5, T, T + 1.5), (T + 1.5, T + 1.5, T + 1.2, T + 1.3),
                       (T + 1.3, T + 1.4, T + 1.25, T + 1.3)], session="2026-06-01")
             for _ in range(100)]
    out = lc.break_params(_family(200) + never, policy())
    assert out["entry_buffer_conservative_lo_atr"].sample_n == 300
    m_cons = (out["entry_buffer_conservative_lo_atr"].value
              + out["entry_buffer_conservative_hi_atr"].value) / 2
    assert m_cons == pytest.approx(1.0)
    assert out["stop_conservative_atr"].sample_n == 200
    assert out["target_conservative_1_r"].sample_n == 200
    assert out["stop_conservative_atr"].value == pytest.approx(lc.quantile(
        [1.0 + 0.01 * i for i in range(1, 201)], 0.60))


def test_break_params_minimum_sample_edges():
    """149 breaks: every entry buffer is insufficient_history with sample 149,
    and every stop, the floor and every target carry that status."""
    out = lc.break_params(_family(149), policy())
    for key, c in out.items():
        assert c.status == "insufficient_history" and c.value is None, key
    assert out["entry_buffer_neutral_hi_atr"].sample_n == 149
    # 150 breaks with 149 held: buffers ok, stops one held break short.
    fam = _family(150)
    fam[0].held = False
    out = lc.break_params(fam, policy())
    assert out["entry_buffer_neutral_hi_atr"].ok
    for persona in lc.PERSONAS:
        assert out[f"stop_{persona}_atr"].status == "insufficient_history"
        assert out[f"stop_{persona}_atr"].sample_n == 149
    assert out["min_stop_atr"].sample_n == 149


def test_target_share_that_cannot_be_met_is_no_positive_target_onward():
    """The family's stops (aggressive risk 2.30 ATR), and every break that
    is not stopped rallies the same 2.30 ATR: 174 breaks reach exactly 1.0 R
    and the rest 0. T1 (share 0.40) is 1.0; T2 (share 0.25) is 1.0 again,
    not greater than T1, so T2 and T3 are no_positive_target with no
    value."""
    out = lc.break_params(_family(200, up=lambda i: 2.30 if i < 175 else 0.0), policy())
    assert out["target_aggressive_1_r"].value == pytest.approx(1.0)
    for k in (2, 3):
        c = out[f"target_aggressive_{k}_r"]
        assert c.status == "no_positive_target" and c.value is None
    # No break reaches anything: no_positive_target from T1.
    out = lc.break_params(_family(200, up=lambda i: 0.0), policy())
    for k in (1, 2, 3):
        assert out[f"target_neutral_{k}_r"].status == "no_positive_target"


def test_conservative_targets_are_measured_in_the_planners_r():
    """The planner tightens the conservative stop to the nearest structure
    on the stop side of the midpoint (the builder's stop anchor here, at
    T - 0.8), so its R is |midpoint - anchor| = 1.8 ATR, not
    max(stop_conservative_atr, min_stop_atr) = 2.2 ATR. The calibration
    measures each filled break's reach in the R the planner publishes for
    that break: the two agree break by break, and the conservative targets
    are the reach shares in that R (breaks with a >= 0.8, i >= 80, are
    stopped at the anchor and reach nothing)."""
    from lib.agents.trade_planner import PlanContext, compute_persona_plans
    from tests.lib.level_params_fixtures import fixture_params
    from tests.lib.session_levels_helpers import with_triggers

    anchor = T - 0.8
    fam = _family(200, up=lambda i: 0.03 * i)
    for b in fam:
        b.structure = (None, anchor)
    pol = policy(target_conservative_1_r={"statistic_q": 0.3},
                 target_conservative_2_r={"statistic_q": 0.2})
    out = lc.break_params(fam, pol)
    v = {k: c.value for k, c in out.items() if c.ok}
    assert v["stop_conservative_atr"] == pytest.approx(2.2) and v["min_stop_atr"] == pytest.approx(1.5)
    lp = fixture_params("TST", overrides=v)
    reaches = []
    for b in fam:
        mid, stop = lc.planned_stop(b, "conservative", v["entry_buffer_conservative_lo_atr"],
                                    v["entry_buffer_conservative_hi_atr"],
                                    v["stop_conservative_atr"], v["min_stop_atr"])
        ctx = PlanContext(direction="long", conviction="medium", close=T, atr=b.atr,
                          levels=with_triggers(long=b.trigger, long_stop=anchor, atr=b.atr,
                                               params=lp), ftfc_score=1.0)
        plan = {p.persona: p for p in compute_persona_plans(ctx)}["conservative"]
        plan_mid = (plan.entry_zone.low + plan.entry_zone.high) / 2
        assert (mid, stop) == pytest.approx((plan_mid, plan.stop), abs=0.005)
        assert mid - stop == pytest.approx(1.8)
        reaches.append(lc.persona_outcome(b, mid, stop=stop).reach_r)
    assert out["target_conservative_1_r"].value == pytest.approx(lc.reach_share_value(reaches, 0.3))
    assert out["target_conservative_1_r"].value == pytest.approx((0.03 * 20 - 0.5) / 1.8)
    assert out["target_conservative_2_r"].value == pytest.approx((0.03 * 40 - 0.5) / 1.8)
    # The R the old rule used (max(stop, floor) x ATR = 2.2) gives other values.
    old = [lc.persona_outcome(b, T + 1.0, risk_atr=2.2).reach_r for b in fam]
    assert lc.reach_share_value(old, 0.3) != pytest.approx(out["target_conservative_1_r"].value)


# ── whole ticker, no look-ahead ─────────────────────────────────────────


def _qqq_minutes(daily, sessions):
    """Synthetic one-minute bars for `sessions` from each day's OHLC: 120
    premarket bars around the prior close, 390 RTH bars walking open to high
    to low to close."""
    frames = []
    prev = daily["Close"].shift(1)
    for s in sessions:
        r = daily.loc[s]
        pc = float(prev.loc[s])
        pm = _minutes(s, 120, start="07:30", open=pc + 0.05, close=pc + 0.07,
                      high=pc + 0.1, low=pc - 0.02)
        path = np.concatenate([np.linspace(r.Open, r.High, 130), np.linspace(r.High, r.Low, 130),
                               np.linspace(r.Low, r.Close, 130)])
        rth = _minutes(s, 390, open=path, close=path, high=path + 0.01, low=path - 0.01)
        frames += [pm, rth]
    return pd.concat(frames, ignore_index=True)


def test_no_look_ahead():
    """Bars dated on or after effective_from change no value: the same
    calibration with every later daily and one-minute bar dropped, and with
    them replaced by wild values, returns the same rows."""
    from lib.indicators import calculate_atr
    daily = fx.daily("QQQ", through=date(2026, 11, 5))
    daily["atr_14"] = calculate_atr(daily["High"], daily["Low"], daily["Close"], 14)
    eff = pd.Timestamp("2026-10-15")
    sessions = [s for s in daily.index[-60:]]
    minutes = _qqq_minutes(daily, sessions)
    base = lc.calibrate("QQQ", daily[daily.index < eff], minutes[minutes["timestamp"] < eff],
                        policy(), eff)
    full = lc.calibrate("QQQ", daily, minutes, policy(), eff)
    wild = daily.copy()
    wild.loc[wild.index >= eff, ["High", "Low", "Close", "atr_14"]] *= 3
    wm = minutes.copy()
    wm.loc[wm["timestamp"] >= eff, ["open", "high", "low", "close"]] *= 3
    later = lc.calibrate("QQQ", wild, wm, policy(), eff)
    assert base == full == later
    assert base["trigger_window_long_atr"].ok
    assert base["trigger_window_long_atr"].input_to < "2026-10-15"
    assert set(base) == set(k for k in seeded_policy() if k not in ("atr_basis", "calibration_universe"))


def test_calibration_universe_reads_the_policy_sources():
    got = lc.load_calibration_universe(
        policy(), market_tickers=["SPY", "QQQ", "IWM"], insight_tickers=["spy", "NVDA"],
        watchlist_fn=lambda: ["AAPL", "QQQ"], on_demand_fn=lambda: ["TSLA"])
    assert got == ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "TSLA"]

    def broken():
        raise RuntimeError("watchlist read failed")
    with pytest.raises(RuntimeError):
        lc.load_calibration_universe(policy(), market_tickers=[], insight_tickers=[],
                                     watchlist_fn=broken, on_demand_fn=lambda: [])


def test_to_rows_matches_the_table():
    out = lc.break_params(_family(149), policy())
    rows = lc.to_rows("qqq", out, policy(), date(2026, 11, 9), "run-1", "nightly", "ts")
    r = next(r for r in rows if r["param_key"] == "stop_neutral_atr")
    assert r["ticker"] == "QQQ" and r["atr_basis"] == "atr_14" and r["status"] == "insufficient_history"
    assert r["value"] is None and r["effective_from"] == "2026-11-09"
    assert r["policy_effective_from"] == "2015-01-02"


def test_each_break_parameter_takes_its_own_lookback():
    """Codex P2 on e4bb463e: with the daily sessions passed, a stop, the
    floor or a target whose policy row has a shorter lookback than the entry
    buffers is measured on the breaks inside its own window only. The
    family's 200 breaks are one a session; stop_neutral with a 20-session
    lookback (minimum 10) reads breaks 181..200, and a one-session target
    lookback is insufficient_history with the one break in it."""
    fam = _family(200)
    idx = _bdays(200)
    pol = policy(stop_neutral_atr={"lookback_sessions": 20, "min_sample": 10},
                 target_neutral_1_r={"lookback_sessions": 1})
    out = lc.break_params(fam, pol, session_index=idx)
    s = out["stop_neutral_atr"]
    assert s.status == PARAM_OK and s.sample_n == 20
    assert s.input_from == idx[180].date().isoformat() and s.input_to == idx[-1].date().isoformat()
    assert s.value == pytest.approx(lc.quantile([0.5 + 0.01 * i for i in range(181, 201)], 0.75))
    t1 = out["target_neutral_1_r"]
    assert t1.status == "insufficient_history" and t1.sample_n == 1
    # The entry buffers keep their 750-session window: all 200 breaks.
    assert out["entry_buffer_neutral_hi_atr"].sample_n == 200
    # Without the session index every given break is in every window.
    assert lc.break_params(fam, pol)["stop_neutral_atr"].sample_n == 200


def test_break_lookback_is_the_longest_break_parameter_lookback():
    assert lc._break_lookback(policy()) == 750
    assert lc._break_lookback(policy(target_aggressive_3_r={"lookback_sessions": 900})) == 900
    assert lc._break_lookback(policy(min_stop_atr={"lookback_sessions": 800})) == 800


def test_regular_session_bars_end_at_the_actual_close():
    """Codex P2 on e4bb463e: 2025-11-28 closed at 13:00 ET. Its regular
    session is 09:30 to 12:59; a 13:01 after-hours bar is not in it, while a
    full day keeps 09:30 to 15:59. A bar on a non-session day is none."""
    half = pd.Timestamp("2025-11-28")
    full = pd.Timestamp("2025-11-26")
    holiday = pd.Timestamp("2025-11-27")
    raw = pd.concat([_minutes(half, 300), _minutes(full, 420), _minutes(holiday, 10)])
    m = lc.normalize_minutes(raw, "2025-12-01")
    rth = lc._rth(m)
    by = rth.groupby("session")["timestamp"].agg(["min", "max", "size"])
    assert by.loc[half, "max"] == pd.Timestamp("2025-11-28 12:59")
    assert by.loc[half, "size"] == 210
    assert by.loc[full, "max"] == pd.Timestamp("2025-11-26 15:59")
    assert by.loc[full, "size"] == 390
    assert holiday not in by.index
