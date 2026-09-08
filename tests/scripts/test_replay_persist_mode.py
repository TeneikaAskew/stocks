"""Tests for the REPLAY_PERSIST mode added in feat/replay-persist-mode.

The mode addresses two limitations of the existing hermetic replay:

  1. Cloud Run logs truncate the per-fire JSON output at ~85 records,
     blocking analysis that needs full per-fire detail.
  2. The hermetic replay processes 24-hour bars (~1,200/day) while live
     signal-monitor only runs RTH (~390 bars/day). Fire counts aren't
     comparable.

REPLAY_PERSIST=true / --persist:
  - Filters bars to RTH only (9:30-16:00 ET)
  - Persists captured fires to signal_alerts with run_kind='replay'
    and replay_id=<UUID> per execution
  - Adds basic exit simulation walking forward through subsequent bars

Tests below verify each piece independently. Integration with Cloud SQL
is mocked so the suite stays hermetic.
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── filter_to_rth — the RTH-only filter ──────────────────────────


def test_filter_to_rth_keeps_only_market_hours():
    """9:30 AM ET = 13:30 UTC (during EDT). Bars at 9:00 ET and 16:30 ET
    should be filtered out."""
    from scripts.replay_signal_monitor import filter_to_rth
    times = pd.to_datetime([
        '2026-05-06T13:00:00',  # 9:00 ET — premarket
        '2026-05-06T13:30:00',  # 9:30 ET — RTH open
        '2026-05-06T14:00:00',  # 10:00 ET — RTH
        '2026-05-06T19:59:00',  # 15:59 ET — last RTH min
        '2026-05-06T20:00:00',  # 16:00 ET — after-hours start
        '2026-05-06T20:30:00',  # 16:30 ET — after-hours
    ], utc=True)
    bars = pd.DataFrame({
        'Time': times,
        'Open': [1] * 6, 'High': [1] * 6, 'Low': [1] * 6, 'Close': [1] * 6,
        'Volume': [1] * 6,
    })
    rth = filter_to_rth(bars)
    # Should keep 9:30, 10:00, 15:59 — drop 9:00, 16:00, 16:30
    assert len(rth) == 3
    et = rth['Time'].dt.tz_convert('America/New_York').dt.time.tolist()
    assert all(t >= time(9, 30) for t in et)
    assert all(t < time(16, 0) for t in et)


def test_filter_to_rth_handles_naive_timestamps():
    """If 'Time' lacks tz info, treat as UTC."""
    from scripts.replay_signal_monitor import filter_to_rth
    bars = pd.DataFrame({
        'Time': pd.to_datetime(['2026-05-06T14:00:00']),  # naive UTC, 10:00 ET
        'Open': [1], 'High': [1], 'Low': [1], 'Close': [1], 'Volume': [1],
    })
    rth = filter_to_rth(bars)
    assert len(rth) == 1


def test_filter_to_rth_handles_empty_df():
    from scripts.replay_signal_monitor import filter_to_rth
    out = filter_to_rth(pd.DataFrame())
    assert out.empty


def test_filter_to_rth_handles_dst_transition():
    """November 1 2026 falls back from EDT (UTC-4) to EST (UTC-5).
    9:30 ET on Nov 5 (EST) = 14:30 UTC (not 13:30 like during EDT)."""
    from scripts.replay_signal_monitor import filter_to_rth
    times = pd.to_datetime([
        '2026-11-05T14:30:00',  # 9:30 EST — keep
        '2026-11-05T13:30:00',  # 8:30 EST — drop (premarket)
    ], utc=True)
    bars = pd.DataFrame({
        'Time': times,
        'Open': [1] * 2, 'High': [1] * 2, 'Low': [1] * 2, 'Close': [1] * 2,
        'Volume': [1] * 2,
    })
    rth = filter_to_rth(bars)
    assert len(rth) == 1
    et_hour = rth['Time'].dt.tz_convert('America/New_York').dt.time.iloc[0]
    assert et_hour == time(9, 30)


# ── simulate_exit — the per-fire exit-resolver pass ──────────────


def _mock_engine_with_bars(bars_df):
    """Build a SQLAlchemy engine mock that returns the given bars."""
    engine = MagicMock()
    with patch('pandas.read_sql', return_value=bars_df):
        yield engine


def test_simulate_exit_target_hit():
    """Fire at $100 with target $102. Subsequent bar high reaches 102.5
    → exit at target, +2% return."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00', '2026-05-06T14:02:00'], utc=True),
        'open': [100.0, 100.5], 'high': [100.5, 102.5],
        'low': [99.8, 100.2], 'close': [100.4, 102.3],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=102.0,
                              time_stop_minutes=60)
    assert result['exit_reason'] == 'target'
    assert result['exit_price'] == 102.0
    # Entry filled at first bar's open ($100.0); target $102.0
    # Return: (102.0 - 100.0) / 100.0 * 100 = +2.0%
    assert result['exit_return_pct'] == pytest.approx(2.0)


def test_simulate_exit_time_stop():
    """Fire at $100, target $200 (never reached). Exits at last bar
    via time_stop with the bar's close as exit_price."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00', '2026-05-06T14:02:00'], utc=True),
        'open': [100.0, 100.5], 'high': [100.5, 100.7],
        'low': [99.8, 100.2], 'close': [100.4, 100.6],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=200.0)
    assert result['exit_reason'] == 'time_stop'
    assert result['exit_price'] == 100.6  # last close
    # (100.6 - 100.0) / 100.0 * 100 = +0.6%
    assert result['exit_return_pct'] == pytest.approx(0.6)


def test_simulate_exit_short_inverts_sign():
    """PUT fire: target hit when low <= target. Short return = -(exit - entry) / entry."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='PUT',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=[],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00'], utc=True),
        'open': [100.0], 'high': [100.5], 'low': [97.5], 'close': [98.0],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=98.0)
    assert result['exit_reason'] == 'target'
    # Entry $100, target $98 (PUT side); return = -(98-100)/100 * 100 = +2.0
    assert result['exit_return_pct'] == pytest.approx(2.0)


def test_simulate_exit_no_data_returns_safe_default():
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=[],
        embed_title='test',
    )
    with patch('pandas.read_sql', return_value=pd.DataFrame()):
        result = simulate_exit(fire, MagicMock())
    assert result['exit_reason'] == 'no_data'
    assert result['exit_price'] is None
    assert result['exit_return_pct'] == 0.0


# ── persist_fire_to_signal_alerts — write-path integration ───────


def test_persist_fire_calls_insert_with_run_kind_replay():
    """Verify the INSERT is called with run_kind='replay' and replay_id."""
    from scripts.replay_signal_monitor import persist_fire_to_signal_alerts, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    replay_id = '12345678-1234-5678-9012-123456789012'
    persist_fire_to_signal_alerts(fire, MagicMock(), engine, replay_id)
    # The conn.execute call should have been made
    assert conn.execute.called
    # Inspect the params dict (second positional arg)
    call_args = conn.execute.call_args
    params = call_args[0][1]
    assert params['ticker'] == 'SPY'
    assert params['direction'] == 'CALL'
    assert params['replay_id'] == replay_id
    # The SQL string contains run_kind='replay' baked in (not a param)


def test_persist_fire_strength_label_thresholds():
    """Verify total_score → strength_label mapping."""
    from scripts.replay_signal_monitor import persist_fire_to_signal_alerts, FireRecord
    cases = [(1.5, 'replay-weak'), (3.5, 'replay-medium'), (5.5, 'replay-strong')]
    for score, expected in cases:
        fire = FireRecord(
            timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
            ticker='SPY', direction='CALL',
            base_score=int(score), total_score=score,
            timeframe_tag='30m', expected_hold_min=60,
            strategy_agreement=None, conditions_met=[],
            embed_title='test',
        )
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        persist_fire_to_signal_alerts(fire, MagicMock(), engine, 'test-id')
        params = conn.execute.call_args[0][1]
        assert params['strength'] == expected, \
            f"score {score} should map to {expected}, got {params['strength']}"


# ── --persist CLI flag + REPLAY_PERSIST env var ─────────────────


def test_persist_cli_flag_recognised(monkeypatch):
    """--persist sets args.persist=True."""
    from scripts.replay_signal_monitor import parse_args
    args = parse_args(['--ticker', 'SPY', '--date', '2026-05-06', '--persist'])
    assert args.persist is True


def test_persist_default_false(monkeypatch):
    """Without --persist, the default is hermetic mode."""
    from scripts.replay_signal_monitor import parse_args
    args = parse_args(['--ticker', 'SPY', '--date', '2026-05-06'])
    assert args.persist is False


# ── premarket warm-up parity (#1022) ─────────────────────────────────


def _two_day_bars():
    """Two ET sessions, each with premarket bars then RTH bars."""
    import pandas as pd

    rows = []
    for day in ("2026-09-02", "2026-09-03"):
        # 40 premarket minutes ending 09:29, then 40 RTH minutes from 09:30.
        pre = pd.date_range(f"{day} 08:50", periods=40, freq="1min", tz="America/New_York")
        rth = pd.date_range(f"{day} 09:30", periods=40, freq="1min", tz="America/New_York")
        for ts in list(pre) + list(rth):
            rows.append({"Time": ts.tz_convert("UTC"), "Open": 100.0, "High": 100.5,
                         "Low": 99.5, "Close": 100.2, "Volume": 1000})
    return pd.DataFrame(rows)


def test_a_persisted_session_is_evaluated_with_its_own_premarket_warm_up():
    """A persisted replay dropped premarket bars before they reached the
    window, so each session began at 09:30 with nothing in it and
    evaluate_ticker suppressed every bar until min_bars_for_signals (30)
    RTH bars existed — roughly 09:30 to 09:59 missing from every day
    (Codex on #1022).

    Live does not start empty: run_loop's first in-hours fetch asks for
    `extended_hours=true, outputsize=compact`, so at 09:30 the window
    already holds ~100 of that day's premarket bars and the open is
    evaluable. Filtering to RTH is right for what FIRES and wrong for what
    the window HOLDS; the two are now separate."""
    from unittest.mock import MagicMock

    from scripts.replay_signal_monitor import replay_ticker

    monitor = MagicMock()
    monitor.replay_clock_ts = None
    windows = {}
    seen_eval_times = []

    def _update(ticker, bar):
        import pandas as pd
        windows[ticker] = pd.concat([windows.get(ticker, pd.DataFrame()), bar])

    def _now(tz=None):
        return monitor.replay_clock_ts.tz_convert("America/New_York")

    def _evaluate(ticker):
        seen_eval_times.append((monitor.replay_clock_ts, len(windows[ticker])))

    def _reset(ticker):
        import pandas as pd
        windows[ticker] = pd.DataFrame()

    monitor.update_window.side_effect = _update
    monitor.evaluate_ticker.side_effect = _evaluate
    monitor.reset_session_state.side_effect = _reset
    monitor._now.side_effect = _now

    bars = _two_day_bars()
    replay_ticker(monitor, "IWM", bars, [], evaluate_rth_only=True)

    et = [t.tz_convert("America/New_York") for t, _ in seen_eval_times]
    assert et, "nothing was evaluated"
    assert all(t.time() >= __import__("datetime").time(9, 30) for t in et), \
        "premarket bars must not be evaluated; only the window sees them"

    # Day 2's FIRST evaluated bar must already have its own premarket
    # history behind it, the way live does.
    day2 = [(t, n) for t, n in seen_eval_times
            if t.tz_convert("America/New_York").date().isoformat() == "2026-09-03"]
    assert day2, "day 2 was never evaluated"
    first_ts, first_len = day2[0]
    assert first_ts.tz_convert("America/New_York").time() == __import__("datetime").time(9, 30)
    assert first_len >= 30, (
        "day 2's open was evaluated with %d bars in the window; live has that "
        "day's premarket behind it, so the open is not blind" % first_len)


def _session_bars(day, pre_n, rth_n, post_n=0):
    import pandas as pd
    rows = []
    if pre_n:
        pre = pd.date_range(end=f"{day} 09:29", periods=pre_n, freq="1min",
                            tz="America/New_York")
        rows += list(pre)
    if rth_n:
        rows += list(pd.date_range(f"{day} 09:30", periods=rth_n, freq="1min",
                                   tz="America/New_York"))
    if post_n:
        rows += list(pd.date_range(f"{day} 16:00", periods=post_n, freq="1min",
                                   tz="America/New_York"))
    return pd.DataFrame([{"Time": t.tz_convert("UTC"), "Open": 100.0, "High": 100.5,
                          "Low": 99.5, "Close": 100.2, "Volume": 1000} for t in rows])


def test_the_warm_up_is_capped_at_the_live_fetch_size():
    """Feeding every bar since Eastern midnight warms the open with up to
    `rolling_window_bars` (200) bars, but live's first in-hours fetch is
    `outputsize=compact` — at most 100 points — so cumulative VWAP and the
    seeded EMA/MACD values differ enough to change fires (Codex on #1022).

    Parity means the same warm-up SIZE, not merely a non-empty one. Bars
    after 16:00 are dropped for the same reason: run_loop stops fetching at
    the close, so they never enter the live window either."""
    import pandas as pd

    from scripts.replay_signal_monitor import trim_to_live_window_scope

    bars = pd.concat([
        _session_bars("2026-09-02", pre_n=300, rth_n=20, post_n=15),
        _session_bars("2026-09-03", pre_n=300, rth_n=20, post_n=15),
    ], ignore_index=True)

    out = trim_to_live_window_scope(bars, warmup_bars=100)
    et = out["Time"].dt.tz_convert("America/New_York")
    for day in ("2026-09-02", "2026-09-03"):
        same = et[et.dt.date.astype(str) == day]
        pre = same[same.dt.time < __import__("datetime").time(9, 30)]
        rth = same[(same.dt.time >= __import__("datetime").time(9, 30))
                   & (same.dt.time < __import__("datetime").time(16, 0))]
        post = same[same.dt.time >= __import__("datetime").time(16, 0)]
        assert len(pre) == 100, f"{day}: {len(pre)} warm-up bars, live has at most 100"
        assert len(rth) == 20, f"{day}: RTH bars must not be trimmed"
        assert len(post) == 0, f"{day}: post-close bars never enter the live window"
    assert out["Time"].is_monotonic_increasing


def test_the_limit_counts_bars_that_are_actually_evaluated():
    """`--limit N` selected from the Eastern-midnight query before the
    RTH-only gate, so on a ticker with N or more premarket bars every
    selected bar was warm-up and the replay evaluated NOTHING (Codex on
    #1022). Before the warm-up change, persist mode filtered to RTH first,
    so the limit counted evaluated bars. It counts them again."""
    from scripts.replay_signal_monitor import limit_to_evaluated_bars, filter_to_rth

    bars = _session_bars("2026-09-02", pre_n=120, rth_n=50)
    out = limit_to_evaluated_bars(bars, 10)
    assert len(filter_to_rth(out)) == 10, (
        "the limit must count RTH bars; got %d" % len(filter_to_rth(out)))
    assert len(out) > 10, "the warm-up before those bars must be kept"


def test_the_limit_is_a_no_op_when_there_are_fewer_rth_bars():
    from scripts.replay_signal_monitor import limit_to_evaluated_bars

    bars = _session_bars("2026-09-02", pre_n=10, rth_n=5)
    assert len(limit_to_evaluated_bars(bars, 50)) == len(bars)
    assert len(limit_to_evaluated_bars(bars, None)) == len(bars)


def test_the_trim_and_the_limit_compose_across_sessions():
    """The two run in sequence in persist mode, so their interaction is a
    third thing to get right: the limit's cutoff can land inside a session
    whose warm-up the trim has already reduced.

    What must hold: the trim never removes a bar the limit then needs, and
    the limit never leaves an evaluated bar without its warm-up."""
    import pandas as pd

    from scripts.replay_signal_monitor import (
        filter_to_rth, limit_to_evaluated_bars, trim_to_live_window_scope,
    )

    bars = pd.concat([
        _session_bars("2026-09-02", pre_n=250, rth_n=30),
        _session_bars("2026-09-03", pre_n=250, rth_n=30),
    ], ignore_index=True)

    # 45 evaluated bars: all 30 of day 1 and the first 15 of day 2.
    out = limit_to_evaluated_bars(trim_to_live_window_scope(bars, warmup_bars=100), 45)
    et = out["Time"].dt.tz_convert("America/New_York")
    rth = filter_to_rth(out)
    assert len(rth) == 45, len(rth)

    day2 = et[et.dt.date.astype(str) == "2026-09-03"]
    day2_pre = day2[day2.dt.time < __import__("datetime").time(9, 30)]
    assert len(day2_pre) == 100, (
        "day 2's evaluated bars must keep their full warm-up; got %d" % len(day2_pre))
    day1 = et[et.dt.date.astype(str) == "2026-09-02"]
    assert len(day1[day1.dt.time < __import__("datetime").time(9, 30)]) == 100


def test_the_live_window_scope_is_not_gated_on_where_output_goes():
    """The parity work was reachable only with `--persist`, and no
    documented invocation passes it: CLAUDE.md 3.6's canonical command is
    `--date ... --tickers ...`, the signal-monitor job wrapper never adds
    the flag when it forwards REPLAY_DATE, and the resolve-issue workflow
    explicitly runs `env -u REPLAY_PERSIST` to stay hermetic.

    So the same date produced two different fire counts depending on a flag
    whose documented job is where rows are written. The simulation must not
    depend on its destination: the scope is unconditional and `--persist`
    only decides whether signal_alerts is written."""
    import inspect

    from scripts import replay_signal_monitor as mod

    src = inspect.getsource(mod.main)
    assert "evaluate_rth_only=persist_mode" not in src, (
        "evaluation scope must not be gated on the persistence flag")
    assert "trim_to_live_window_scope(bars)" in src
    # The trim must not sit inside a persist-only branch.
    trim_line = next(l for l in src.splitlines() if "trim_to_live_window_scope(bars)" in l)
    indent = len(trim_line) - len(trim_line.lstrip())
    for line in src.splitlines():
        if "if persist_mode:" in line:
            assert len(line) - len(line.lstrip()) >= indent, (
                "the trim is inside a persist-only branch")


def test_the_warm_up_matches_the_live_fetch_exactly():
    """`outputsize=compact` returns the last 100 points INCLUDING the bar
    being fetched, so at the 09:30 poll live holds at most 99 premarket
    bars, not 100. Measured on a shared price path, the extra bar moved
    Price_vs_VWAP by 5.9e-4 percentage points at the open."""
    from scripts.replay_signal_monitor import _LIVE_WARMUP_BARS

    assert _LIVE_WARMUP_BARS == 99, (
        "live's 100 points include the 09:30 bar itself")


def test_the_warm_up_never_reaches_the_mis_framed_overnight_band():
    """`market_data_intraday` holds two time conventions (CLAUDE.md 3.9),
    and the ET-as-UTC rows land at labelled 00:00-03:59 ET where no US
    equity bar can exist. Measured on SPY 2026-09-02 the 100-bar warm-up
    stops at 07:50 ET and does not reach them, but that margin depends on
    the ticker-date having enough genuine premarket bars. The floor makes
    it unconditional."""
    import pandas as pd

    from scripts.replay_signal_monitor import trim_to_live_window_scope

    ghosts = pd.date_range("2026-09-02 00:00", periods=200, freq="1min",
                           tz="America/New_York")
    real_pre = pd.date_range("2026-09-02 08:00", periods=30, freq="1min",
                             tz="America/New_York")
    rth = pd.date_range("2026-09-02 09:30", periods=10, freq="1min",
                        tz="America/New_York")
    bars = pd.DataFrame([{"Time": t.tz_convert("UTC"), "Open": 1.0, "High": 1.0,
                          "Low": 1.0, "Close": 1.0, "Volume": 1}
                         for t in list(ghosts) + list(real_pre) + list(rth)])

    out = trim_to_live_window_scope(bars, warmup_bars=99)
    et = out["Time"].dt.tz_convert("America/New_York")
    assert (et.dt.time >= __import__("datetime").time(4, 0)).all(), (
        "no bar before 04:00 ET may be used as warm-up; those are the "
        "mis-framed rows from the second write convention")
    assert len(out) == 40, len(out)


def test_a_bar_with_no_time_is_not_evaluated():
    """A missing `Time` silently disables VWAP in lib/indicators, which is
    the 5/6 V2 harness failure. `_is_rth` returned True for such a bar, so
    it would have been scored with VWAP quietly off. Skip instead."""
    import pandas as pd

    from scripts.replay_signal_monitor import _is_rth

    assert _is_rth(pd.DataFrame([{"Close": 1.0}])) is False


def test_the_true_utc_session_is_kept_and_the_duplicate_block_dropped():
    """The frame is raw stamps from `market_data_intraday`, not ET.

    Codex read the ET conversion here as unsafe because that table holds two
    write conventions (CLAUDE.md 3.9): if a raw 09:30 stamp meant 09:30 ET,
    converting it would push the opening bell to 05:30 and drop it, and the
    replay would score the afternoon instead. Production says otherwise —
    the volume proves which stamp is the bell. SPY 2026-09-02:

        raw 09:30  close 759.93   volume        606   <- premarket
        raw 13:30  close 762.005  volume    383,770   <- the opening bell
        raw 20:00  close 765.05   volume     99,559   <- the closing auction

    and across 2015-2026, of 9,731 ticker-days on SPY/IWM/QQQ the
    peak-volume minute lands in the true-UTC open or close window on
    essentially all of them and on the ET-as-UTC OPEN window on **zero**.
    The RTH block is true UTC, so converting it is right.

    The one genuinely ET-framed population is the raw 04:00-07:59 block,
    which under true UTC would be 00:00-03:59 ET where no US equity bar
    exists. It is a byte-identical duplicate of the true-UTC premarket four
    hours later — measured on the same day, raw 04:00 and raw 08:00 carry
    the same close (760.999) and the same volume (25,669), as do 04:30/08:30,
    05:00/09:00, 06:00/10:00, 07:00/11:00 and 07:59/11:59. `_PREMARKET_FLOOR`
    is what excludes it, and this test pins both halves at once."""
    import pandas as pd

    from scripts.replay_signal_monitor import trim_to_live_window_scope

    def raw(t, close, vol):
        return {"Time": pd.Timestamp(f"2026-09-02 {t}", tz="UTC"), "Open": close,
                "High": close, "Low": close, "Close": close, "Volume": vol}

    # Prices move minute to minute, as they do in the table. A frame where
    # every bar carries identical OHLCV is not a market, and it would make
    # each bar a byte-identical twin of the one an offset later, which is the
    # signature `_et_as_utc_restamps` reads.
    rows = []
    # The ET-as-UTC duplicate block, raw 04:00-07:59.
    rows += [raw(f"{h:02d}:{m:02d}", 100.0 + (h * 60 + m) * 0.01, 25669)
             for h in range(4, 8) for m in range(60)]
    # The true-UTC extended session, raw 08:00-23:59 = 04:00-19:59 ET.
    rows += [raw(f"{h:02d}:{m:02d}", 200.0 + (h * 60 + m) * 0.01, 1000)
             for h in range(8, 24) for m in range(60)]
    bars = pd.DataFrame(rows)

    out = trim_to_live_window_scope(bars, warmup_bars=99)
    kept = out["Time"].dt.strftime("%H:%M").tolist()

    # The opening bell is raw 13:30 and it survives.
    assert "13:30" in kept, "the true-UTC opening bell must be evaluated"
    # The closing bar under `< 16:00 ET` is raw 19:59.
    assert "19:59" in kept and "20:00" not in kept, kept[-3:]
    # Not one bar of the duplicate block survives.
    assert not [k for k in kept if k < "08:00"], (
        "the ET-as-UTC duplicate block must be dropped whole: %s"
        % [k for k in kept if k < "08:00"])
    # 390 RTH bars (raw 13:30-19:59) plus the 99-bar warm-up in front.
    assert len(out) == 390 + 99, len(out)
    assert kept[0] == "11:51", (
        "the warm-up must be the 99 bars immediately before the bell: %s" % kept[0])


def _floor():
    from scripts.replay_signal_monitor import _PREMARKET_FLOOR
    return _PREMARKET_FLOOR


def _et_as_utc_copy(row_time):
    """Where an ET-as-UTC write of ``row_time`` lands as a raw stamp.

    The writer stores Eastern wall-clock naively as UTC, so the copy's raw
    stamp is the true instant minus one Eastern UTC offset: 4h under EDT,
    5h under EST.
    """
    et = row_time.tz_convert("America/New_York")
    return row_time + et.utcoffset()


def test_an_rth_bar_restamped_as_premarket_is_not_used_as_warm_up():
    """The 04:00 ET floor drops the CONTIGUOUS mis-framed band and no more.

    A second, smaller ET-as-UTC population sits ABOVE the floor, inside the
    warm-up the trim keeps. Measured on production over 2026-08-01..09-05,
    in the ET 07:45-09:29 zone the 99-bar warm-up actually reaches:

        ticker  bars in zone  identical +4h twin  sessions
        IWM           2625            80          21 of 25
        QQQ           2625             0           0 of 25
        SPY           2625             0           0 of 25

    They are RTH bars wearing a premarket stamp, not thin premarket ticks.
    Same window, IWM, duplicated vs genuine bars in that zone:

        is_dup      n   median volume   median 1-min move
        False    2545             812               $0.040
        True       80          19,400               $1.045

    $1.045 in one minute on a ~$290 instrument is 0.36%, twenty-six times
    the genuine median. `_add_vwap` cumsums within the raw date and the kept
    band is one raw date, so those bars enter the same VWAP group as the
    session they precede and displace `Price_vs_VWAP` at the open, which
    `above_vwap`/`below_vwap` read as a strict sign test.

    An earlier version of this file asserted the ET-framed population was
    only the raw 04:00-07:59 band. That was wrong, and the floor alone is
    not sufficient (internal replay-integrity review of #1022).
    """
    import pandas as pd

    from scripts.replay_signal_monitor import trim_to_live_window_scope

    def bar(t, close, vol):
        return {"Time": t, "Open": close, "High": close, "Low": close,
                "Close": close, "Volume": vol}

    rows = []
    # A genuine premarket ramp, ET 06:00-09:29: thin, smooth.
    pre = pd.date_range("2026-09-02 06:00", "2026-09-02 09:29", freq="1min",
                        tz="America/New_York")
    for i, t in enumerate(pre):
        rows.append(bar(t.tz_convert("UTC"), 290.0 + i * 0.001, 800))
    # RTH, ET 09:30-15:59.
    rth = pd.date_range("2026-09-02 09:30", "2026-09-02 15:59", freq="1min",
                        tz="America/New_York")
    for i, t in enumerate(rth):
        rows.append(bar(t.tz_convert("UTC"), 295.0 + i * 0.01, 19400))
    # Three of those RTH bars written a second time under the ET-as-UTC
    # convention, which lands them inside the last-99 warm-up zone.
    # Offsets chosen so the copy lands inside the LAST 99 premarket bars
    # (ET 07:51-09:29), which is the zone the warm-up actually keeps; a copy
    # further back would be dropped by the cap and prove nothing. Source ET
    # 11:55 / 12:15 / 12:35 -> copy ET 07:55 / 08:15 / 08:35.
    copies = []
    for offset in (145, 165, 185):
        src = rth[offset].tz_convert("UTC")
        copy_at = _et_as_utc_copy(src)
        copies.append(copy_at)
        rows.append(bar(copy_at, 295.0 + offset * 0.01, 19400))

    bars = pd.DataFrame(rows).sort_values("Time").reset_index(drop=True)
    out = trim_to_live_window_scope(bars, warmup_bars=99)

    et_out = out["Time"].dt.tz_convert("America/New_York")
    for c in copies:
        assert c.tz_convert("America/New_York").time() >= _floor(), (
            "the copy must land above the floor, or this test proves nothing")
    # A copy shares its stamp with the genuine premarket bar of that minute,
    # so identify it by its values: only an RTH-volume row in the premarket
    # band is a re-stamp.
    premarket_out = out[et_out.dt.time < time(9, 30)]
    assert (premarket_out["Volume"] == 800).all(), (
        "an RTH bar re-stamped into the premarket band must not warm the "
        "window: %s" % premarket_out[premarket_out["Volume"] != 800].to_dict("records"))
    # The genuine warm-up and the whole session survive intact.
    assert len(premarket_out) == 99, len(premarket_out)
    assert len(out) == 99 + len(rth), len(out)


def test_a_frame_with_no_time_column_raises_rather_than_replaying_nothing():
    """A `Time`-less frame used to pass straight through both filters, so the
    run logged "loaded N bars" and reported zero fires with no error.

    That is the shape of the 5/6 incident this file exists to prevent: a
    harness that silently disabled VWAP and reported "0 above_vwap fires"
    while production was firing 46. `_is_rth` already fails closed per bar;
    the two frame-level filters returned the frame untouched, which is a
    distinguishable-only-by-inspection zero (CLAUDE.md 3.7). An EMPTY frame
    is different and stays a no-op: no bars for the window is an answer, not
    a defect (internal replay-integrity review of #1022)."""
    import pandas as pd
    import pytest as _pytest

    from scripts.replay_signal_monitor import (
        filter_to_rth, limit_to_evaluated_bars, trim_to_live_window_scope,
    )

    timeless = pd.DataFrame([{"Open": 1.0, "High": 1.0, "Low": 1.0,
                              "Close": 1.0, "Volume": 10}])
    for fn in (filter_to_rth, trim_to_live_window_scope):
        with _pytest.raises(ValueError, match="Time"):
            fn(timeless)
    with _pytest.raises(ValueError, match="Time"):
        limit_to_evaluated_bars(timeless, 5)

    # An empty frame is still a no-op, in both the with- and without-columns
    # shapes a caller can produce.
    assert filter_to_rth(pd.DataFrame()).empty
    assert trim_to_live_window_scope(pd.DataFrame()).empty
    assert limit_to_evaluated_bars(pd.DataFrame(), 5).empty


def test_a_non_positive_limit_is_rejected_rather_than_ignored():
    """`if not limit` treated 0 as "no limit" and replayed the whole window,
    which is the opposite of what `--limit 0` asks for."""
    import pandas as pd
    import pytest as _pytest

    from scripts.replay_signal_monitor import limit_to_evaluated_bars

    bars = _session_bars("2026-09-02", pre_n=5, rth_n=20)
    assert len(limit_to_evaluated_bars(bars, None)) == len(bars)
    for bad in (0, -1):
        with _pytest.raises(ValueError, match="limit"):
            limit_to_evaluated_bars(bars, bad)
