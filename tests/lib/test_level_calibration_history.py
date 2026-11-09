"""FEAT-STRAT-001 per-ticker params, review findings 1 and 2: history mode.

* The break outcomes are computed on padded arrays for many breaks at once
  (lib.level_calibration.BreakBatch). Each kernel must equal the scalar rule
  it replaced (tests.lib.level_calibration_reference, the code as it stood
  before the change) on every break of a synthetic ticker.
* lib.level_calibration.HistoryCalibrator measures each session's samples
  once and cuts them per effective date. For every session of a synthetic
  fixture, under a policy that changes part-way through (a quantile and the
  ATR basis), it must give exactly what calibrate() gives for that date and
  that date's policy.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from lib import level_calibration as lc
from tests.lib import level_calibration_reference as ref
from tests.lib.level_params_fixtures import seeded_policy


def synthetic_ticker(n_days=70, minute_days=40, seed=1, start="2026-07-01"):
    """Random-walk daily bars (atr_14 1.2, atr_5 1.1) and 4:00-16:00 ET
    one-minute bars on the last `minute_days` sessions."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_days)
    close = 100 + np.cumsum(rng.normal(0, 1, n_days))
    daily = pd.DataFrame({
        "date": days, "open": close + rng.normal(0, .3, n_days),
        "high": close + rng.uniform(0.2, 1.5, n_days), "low": close - rng.uniform(0.2, 1.5, n_days),
        "close": close, "atr_14": 1.2, "atr_5": 1.1,
        "sma_200": close - 2.0,
    })
    frames = []
    for i, d in enumerate(days[-minute_days:]):
        ts = pd.date_range(d + pd.Timedelta(hours=4), d + pd.Timedelta(hours=16), freq="1min",
                           inclusive="left")
        p = daily["open"].iloc[n_days - minute_days + i] + np.cumsum(rng.normal(0, 0.03, len(ts)))
        frames.append(pd.DataFrame({"timestamp": ts, "open": p, "high": p + .02, "low": p - .02,
                                    "close": p + rng.normal(0, .01, len(ts)), "volume": 100}))
    return daily, pd.concat(frames, ignore_index=True)


def small_policy(*, basis="atr_14", long_q=None, effective_from="2015-01-02"):
    """The seeded policy with lookbacks and minimums shrunk to the fixture."""
    p = copy.deepcopy(seeded_policy())
    for key, row in p.items():
        row["effective_from"] = effective_from
        if key.startswith("trigger_window"):
            row.update(lookback_sessions=20, min_sample=10)
        elif key.startswith(("pm_", "level_cluster")):
            row.update(lookback_sessions=8, min_sample=4)
        elif row.get("lookback_sessions"):
            row.update(lookback_sessions=12, min_sample=3)
    p["atr_basis"]["extra"] = {"column": basis}
    if long_q is not None:
        p["trigger_window_long_atr"]["statistic_q"] = long_q
    return p


@pytest.fixture(scope="module")
def ticker():
    return synthetic_ticker()


def _breaks(daily, minutes, policy, as_of):
    as_of = pd.Timestamp(as_of)
    basis = lc.policy_atr_basis(policy)
    d = lc.normalize_daily(daily, basis, as_of)
    m = lc.normalize_minutes(minutes, as_of)
    sessions = sorted(set(m["session"]))
    trig = lc.replay_triggers("TST", lc.daily_before(daily, as_of), d, policy, sessions, basis)
    return d, m, trig


def test_break_kernels_equal_the_scalar_reference(ticker):
    daily, minutes = ticker
    end = pd.Timestamp(daily["date"].iloc[-1]) + pd.offsets.BDay(1)
    d, m, trig = _breaks(daily, minutes, small_policy(), end)
    new, old = lc.find_breaks(d, m, trig), ref.find_breaks(d, m, trig)
    assert len(new) == len(old) > 20
    for a, b in zip(new, old):
        assert (a.session, a.side, a.trigger, a.atr, a.held, a.structure) == \
               (b.session, b.side, b.trigger, b.atr, b.held, b.structure)
        pd.testing.assert_frame_equal(a.bars, b.bars)
    rng = np.random.default_rng(7)
    filled = with_reach = 0
    for b in old:
        for minutes_ in (1, 5, 15, 60):
            assert lc.follow_through(b, minutes_) == ref.follow_through(b, minutes_)
        for lo, hi in ((0.0, 0.0), (0.0, 0.3), (0.1, 0.6), tuple(sorted(rng.uniform(0, 1, 2)))):
            mid = b.trigger + b.sign * (lo + hi) / 2 * b.atr
            assert lc.persona_fill(b, mid) == ref.persona_fill(b, mid)
            assert lc.persona_outcome(b, mid) == ref.persona_outcome(b, mid)
            for risk in (0.2, 0.5, 1.0):
                got, want = lc.persona_outcome(b, mid, risk), ref.persona_outcome(b, mid, risk)
                assert got == want
                with_reach += want.reach_r is not None and want.reach_r > 0
            stop = mid - b.sign * 0.4 * b.atr
            got, want = lc.persona_outcome(b, mid, stop=stop), ref.persona_outcome(b, mid, stop=stop)
            assert got == want
            filled += want.filled
    assert filled and with_reach  # the fixture exercises fills and reaches


def test_premarket_spreads_equal_the_scalar_reference(ticker):
    daily, minutes = ticker
    m = lc.normalize_minutes(minutes, pd.Timestamp(daily["date"].iloc[-1]) + pd.offsets.BDay(1))
    pm = lc._premarket(m)
    for s, g in pm.groupby("session"):
        pc = float(round(g["open"].iloc[0], 2))
        for spike in (0.02, 0.05, 1.0):
            np.testing.assert_array_equal(lc.clean_premarket_spreads(g, pc, spike),
                                          ref.clean_premarket_spreads(g, pc, spike))


def test_history_calibrator_equals_calibrate_on_every_session(ticker):
    """Every session from the first with one-minute bars to the session
    after the last bar, the policy changing (long trigger quantile and ATR
    basis) half way: HistoryCalibrator.calibrate(policy in force, date) ==
    calibrate(..., policy in force, date), key for key, value for value."""
    daily, minutes = ticker
    first = pd.Timestamp(minutes["timestamp"].iloc[0]).normalize()
    last = pd.Timestamp(daily["date"].iloc[-1]) + pd.offsets.BDay(1)
    dates = list(pd.bdate_range(first, last))
    change = dates[len(dates) // 2]
    old = small_policy()
    new = small_policy(basis="atr_5", long_q=0.9, effective_from=change.date().isoformat())
    hc = lc.HistoryCalibrator("TST", daily, minutes, last)
    ok_seen = set()
    for eff in dates:
        policy = new if eff >= change else old
        want = lc.calibrate("TST", daily, minutes, policy, eff)
        got = hc.calibrate(policy, eff)
        assert got == want, eff
        ok_seen |= {k for k, v in want.items() if v.ok}
    # Every parameter came out ok on some date, so every rule was compared.
    assert ok_seen == set(want)


def test_history_calibrator_reads_no_bar_on_or_after_its_date(ticker):
    daily, minutes = ticker
    last = pd.Timestamp(daily["date"].iloc[-1])
    hc = lc.HistoryCalibrator("TST", daily, minutes, last)
    with pytest.raises(ValueError):
        hc.calibrate(small_policy(), last + pd.offsets.BDay(1))
