"""The max_daily_trades cap must engage in replay too (#818).

`scripts/replay_signal_monitor.py` replaces `SignalMonitor.fire_alert`
wholesale with a capturing stub. Production increments the per-ticker fire
counter inside `fire_alert`, so the stub silently dropped it: `daily_trades`
stayed 0 for the whole replay and the cap check in `evaluate_ticker` never
engaged.

That matters beyond replay fidelity. Per Codex's review of #816, the daily cap
is currently the *only* thing bounding concurrent exposure, so a replay in
which it never binds cannot reproduce today's behaviour as a baseline for any
shadow-control analysis.
"""
import pandas as pd
import pytest

from gcp.signal_monitor import SignalMonitor
from scripts.replay_signal_monitor import make_capturing_fire_alert


def _monitor():
    m = SignalMonitor()
    m.webhook_url = ""
    return m


def _install_stub(monitor, captured):
    fn = make_capturing_fire_alert(captured, monitor)
    monitor.fire_alert = fn.__get__(monitor, type(monitor))


_SIG = {'direction': 'CALL', 'base_score': 5, 'conditions_met': ['x']}
_LATEST = {'Close': 100.0, 'Time': pd.Timestamp('2026-08-28 10:00:00')}


def _fire(monitor, ticker='SPY'):
    monitor.fire_alert(ticker, dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                       dict(_LATEST))


def test_replay_fire_increments_the_daily_cap_counter():
    """Pre-fix this stayed 0 no matter how many times replay fired."""
    m = _monitor()
    captured = []
    _install_stub(m, captured)
    for _ in range(3):
        _fire(m)
    assert len(captured) == 3
    assert m.daily_trades.get('SPY') == 3, (
        "replay fires must consume daily-trade cap the way production does")


def test_replay_cap_predicate_engages_at_the_configured_cap():
    """The exact predicate evaluate_ticker uses must become True in replay."""
    m = _monitor()
    m.risk.max_daily_trades = 2
    captured = []
    _install_stub(m, captured)
    for _ in range(2):
        _fire(m)
    assert (m.daily_trades.get('SPY', 0) >= m.risk.max_daily_trades), (
        "cap gate would still not engage in replay")


def test_level_gate_suppressed_fire_does_not_consume_cap():
    """Ordering parity: production increments AFTER the level-gate return,
    so a suppressed fire must not count against the cap."""
    m = _monitor()
    m.signal_cfg.level_gate_mode = 'enforce'
    captured = []
    _install_stub(m, captured)

    def _late(_ticker, _direction):
        return 'post_t1', 'fresh'
    m._resolve_level_state = _late

    _fire(m)
    assert captured == [], "enforce mode should suppress a post_t1 fire"
    assert m.daily_trades.get('SPY', 0) == 0, (
        "a suppressed fire must not consume cap")


# --------------------------------------------------------------------------
# Codex review of PR #934 — two defects, both reproduced before fixing.
# --------------------------------------------------------------------------

def test_rvol_enforce_below_does_not_capture_or_consume_cap():
    """Production fire_alert returns on a 'below' verdict under enforce
    BEFORE persist and before the counter — its own comment says a suppressed
    fire is "invisible to the risk caps too". The stub must match, or every
    below-threshold candidate burns cap and starves later valid signals."""
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'enforce'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    low = dict(_LATEST, RVOL=0.4)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0, low)
    assert captured == [], "below-threshold fire must not be captured"
    assert m.daily_trades.get('SPY', 0) == 0, "and must not consume cap"


def test_rvol_enforce_above_still_fires_and_counts():
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'enforce'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                 dict(_LATEST, RVOL=2.0))
    assert len(captured) == 1 and m.daily_trades.get('SPY') == 1


def test_rvol_shadow_mode_does_not_suppress():
    """shadow is the default and must change nothing."""
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'shadow'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                 dict(_LATEST, RVOL=0.1))
    assert len(captured) == 1 and m.daily_trades.get('SPY') == 1


def test_multi_date_replay_rolls_the_cap_counter_over():
    """daily_trades is SESSION state — production runs one monitor per day.
    Without a rollover, date 1 exhausting the cap silently suppresses every
    later date in a --start/--end replay."""
    from scripts.replay_signal_monitor import replay_ticker
    m = _monitor()
    m.risk.max_daily_trades = 2
    captured = []
    _install_stub(m, captured)
    m.daily_trades['SPY'] = 2          # date 1 exhausted the cap

    bars = pd.DataFrame([
        {'Time': pd.Timestamp('2026-08-27 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
    ])
    replay_ticker(m, 'SPY', bars, captured)
    assert m.daily_trades.get('SPY') == 0, (
        "crossing into a new session must reset the per-day fire counter")


def test_multi_date_replay_invalidates_the_cached_level_map():
    """Codex on #1022: refresh_level_map now bounds the daily frame to rows
    before the session's analysis date, so a map built for date 1 is wrong
    for date 2. evaluate_ticker refreshes only when the cached entry is
    None, so the replay rollover must clear it along with daily_trades."""
    from scripts.replay_signal_monitor import replay_ticker
    m = _monitor()
    captured = []
    _install_stub(m, captured)
    stale = object()
    m.level_maps['SPY'] = stale          # date 1's map

    bars = pd.DataFrame([
        {'Time': pd.Timestamp('2026-08-27 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
    ])
    replay_ticker(m, 'SPY', bars, captured)
    assert m.level_maps.get('SPY') is not stale, (
        "crossing into a new session must drop the previous session's level map")


def test_multi_date_replay_rolls_over_on_the_eastern_date_not_utc():
    """Codex on #1022 (round 10): refresh_level_map bounds the frame by the
    monitor's ET date (_now(_ET)), so the rollover must key on the same
    date. Replay bars carry naive UTC stamps: 23:30 UTC and 01:30 UTC the
    next day are ONE Eastern session (19:30 and 21:30 ET) and must not
    reset; 12:00 UTC the next day (08:00 ET) is the next session and must."""
    from scripts.replay_signal_monitor import replay_ticker
    m = _monitor()
    captured = []
    _install_stub(m, captured)
    stale = object()
    m.level_maps['SPY'] = stale
    m.daily_trades['SPY'] = 2
    seen: list = []
    m.evaluate_ticker = lambda ticker: seen.append(
        (m.level_maps.get(ticker) is stale, m.daily_trades.get(ticker)))

    bars = pd.DataFrame([
        {'Time': pd.Timestamp('2026-08-27 23:30:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 01:30:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 12:00:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
    ])
    replay_ticker(m, 'SPY', bars, captured)
    assert seen == [(True, 2), (True, 2), (False, 0)], seen


def test_reset_session_state_returns_every_session_field_to_fresh():
    """Codex on #1022 (round 11): the rollover reset fields one at a time
    and kept missing some (brief cache, last price, fired breaks). The
    monitor now owns the list: everything a fresh SignalMonitor starts a
    session with is reset for the ticker, while the rolling bar window
    and the observability counters survive, and other tickers are untouched."""
    m = _monitor()
    m.daily_trades['SPY'] = 3
    m.daily_pnl['SPY'] = 1.5
    m.active_positions['SPY'] = [{'x': 1}]
    m.orb_levels['SPY'] = {'high': 1.0}
    m.session_extremes['SPY'] = {'date': 'd', 'high': 1.0, 'low': 0.5}
    m.leg_trackers['SPY'] = {'date': 'd'}
    m.volume_baselines['SPY'] = {'date': 'd', 'baseline': {}}
    m.level_maps['SPY'] = object()
    m.level_map_atr['SPY'] = 2.0
    m.last_prices['SPY'] = 100.0
    m.fired_breaks = {('SPY', 'PDH', 'up'), ('IWM', 'PDL', 'down')}
    m._brief_bias_cache['SPY'] = {'bias': 'LONG'}
    m._brief_bias_cache['IWM'] = {'bias': 'SHORT'}
    m._last_fire_ts['SPY'] = 'ts'
    m.insight_cache.get('SPY', lambda t: None)
    m.insight_cache.get('IWM', lambda t: None)
    m.insight_invalidated['SPY'] = True
    m.insight_invalidated['IWM'] = True
    m.windows['SPY'] = pd.DataFrame({'Close': [1.0, 2.0]})
    m.level_refresh_success_count['SPY'] = 4

    m.reset_session_state('SPY')

    fetched: list = []
    m.insight_cache.get('SPY', lambda t: fetched.append(t))
    m.insight_cache.get('IWM', lambda t: fetched.append(t))
    assert fetched == ['SPY'], "SPY's insight evicted (refetched), IWM's still cached"
    assert 'SPY' not in m.insight_invalidated and m.insight_invalidated['IWM'] is True

    assert m.daily_trades['SPY'] == 0 and m.daily_pnl['SPY'] == 0.0
    assert m.active_positions['SPY'] == [] and m.orb_levels['SPY'] == {}
    assert m.session_extremes['SPY'] == {} and m.leg_trackers['SPY'] == {}
    assert m.volume_baselines['SPY'] == {}
    assert m.level_maps['SPY'] is None and 'SPY' not in m.level_map_atr
    assert m.last_prices['SPY'] is None
    assert m.fired_breaks == {('IWM', 'PDL', 'down')}
    assert 'SPY' not in m._brief_bias_cache and m._brief_bias_cache['IWM'] == {'bias': 'SHORT'}
    assert 'SPY' not in m._last_fire_ts
    assert len(m.windows['SPY']) == 2, "the rolling bar window is not session state"
    assert m.level_refresh_success_count['SPY'] == 4, "counters are observability, kept"


def test_multi_date_replay_rollover_clears_brief_cache_and_level_break_state():
    """Codex on #1022 (round 11): day 2's leg trackers were built from day
    1's cached brief (cached by ticker only), and last_prices / fired_breaks
    carried over so the first bar could false-cross yesterday's close and a
    repeat crossing was suppressed."""
    from scripts.replay_signal_monitor import replay_ticker
    m = _monitor()
    captured = []
    _install_stub(m, captured)
    day1_brief = {'bias': 'LONG'}
    m._brief_bias_cache['SPY'] = day1_brief
    m.last_prices['SPY'] = 100.0
    m.fired_breaks = {('SPY', 'PDH', 'up')}
    seen: list = []
    # Observed inside evaluate_ticker, i.e. AFTER update_window has run for
    # the bar: on day 2 the leg trackers reload the brief through the
    # replay clock, so the cache may be populated again, but never with
    # day 1's object.
    m.evaluate_ticker = lambda ticker: seen.append(
        (m._brief_bias_cache.get('SPY') is day1_brief, m.last_prices.get('SPY'),
         ('SPY', 'PDH', 'up') in m.fired_breaks))

    bars = pd.DataFrame([
        {'Time': pd.Timestamp('2026-08-27 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
    ])
    replay_ticker(m, 'SPY', bars, captured)
    assert seen == [(True, 100.0, True), (False, None, False)], seen
