"""Tests for gcp/signal_monitor_eod_resolver.py — EOD reconciliation Cloud Run Job.

Track D audit § 2 / G.P0.10: ~1,209 historical alerts have exit_ts NULL
because the in-process exit-watcher in signal_monitor.py only resolves
positions while the SignalMonitor process is alive. EODResolver replays
exit logic against historical bars and resolves them to target_hit /
time_stop / rsi_extreme / eod_close.

These tests lock in the post-fix behaviour:
  1. Each exit reason fires correctly when the bar pattern triggers it
  2. Eod_close fallback fires when nothing else triggered before session
  3. RSI is computed once per (ticker, day) and cached (capacity calc)
  4. Skips gracefully when an intraday partition is missing
  5. _exit_return_pct matches lib/backtest.py / signal_monitor parity
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


@pytest.fixture
def make_resolver():
    """Build an EODResolver with a stubbed DataLoader."""
    def _make(intraday_df=None):
        from gcp.signal_monitor_eod_resolver import EODResolver
        resolver = EODResolver()
        if intraday_df is not None:
            resolver.loader = MagicMock()
            resolver.loader.load_intraday.return_value = intraday_df
        return resolver
    return _make


def _intraday(rows):
    """Build a fake intraday DataFrame: rows = [(ts, close), ...]."""
    df = pd.DataFrame([
        {'Time': pd.Timestamp(ts), 'Open': c, 'High': c, 'Low': c, 'Close': c, 'Volume': 1_000_000}
        for ts, c in rows
    ])
    return df


# ── 1) _exit_return_pct parity with signal_monitor ────────────────────

def test_exit_return_pct_call_profit():
    from gcp.signal_monitor_eod_resolver import _exit_return_pct
    # +1% on a CALL: (101 - 100) / 100 * 100 = 1.0
    assert _exit_return_pct('CALL', 100.0, 101.0) == pytest.approx(1.0)


def test_exit_return_pct_put_profit():
    from gcp.signal_monitor_eod_resolver import _exit_return_pct
    # PUT profits when price drops: (100 - 99) / 100 * 100 = 1.0
    assert _exit_return_pct('PUT', 100.0, 99.0) == pytest.approx(1.0)


def test_exit_return_pct_call_loss():
    from gcp.signal_monitor_eod_resolver import _exit_return_pct
    assert _exit_return_pct('CALL', 100.0, 99.0) == pytest.approx(-1.0)


# ── 2) target_hit fires on the first bar that crosses the threshold ───

def test_resolve_one_target_hit_call(make_resolver):
    """A CALL position resolves to target_hit on the first bar at or above target.

    Constructed so target hits BEFORE RSI matures past 80 — a steady rise
    to RSI=100 in a few bars would correctly fire rsi_extreme first
    (matches SignalMonitor live behaviour). To isolate target_hit the
    series stays below target while RSI is still NaN, then jumps to target
    on a single bar."""
    bars = _intraday([
        ('2026-05-07 13:30', 100.0),  # alert bar — RSI NaN (no history)
        ('2026-05-07 13:31', 101.0),  # AT target — RSI still NaN-ish
    ])
    resolver = make_resolver(bars)

    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': datetime(2026, 5, 7, 13, 30, 0),
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 101.0,
        'time_stop_minutes': 30,
    })
    res = resolver.resolve_one(alert)
    assert res is not None
    assert res['exit_reason'] == 'target_hit'
    assert res['exit_price'] == pytest.approx(101.0)
    assert res['exit_ts'] == datetime(2026, 5, 7, 13, 31, 0)
    assert res['exit_return_pct'] == pytest.approx(1.0)


def test_resolve_one_target_hit_put(make_resolver):
    """PUT resolves to target_hit when price falls AT or BELOW target.

    Same RSI-isolation reasoning as the CALL case — RSI of a single
    losing bar stays below 80 (and below put_rsi_exit threshold of 20
    via the `0 < rsi <= put_rsi_exit` guard) so target_hit wins."""
    bars = _intraday([
        ('2026-05-07 13:30', 100.0),
        ('2026-05-07 13:31', 99.0),  # AT target — fires here
    ])
    resolver = make_resolver(bars)
    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': datetime(2026, 5, 7, 13, 30, 0),
        'alert_date': '2026-05-07',
        'direction': 'PUT',
        'price_at_signal': 100.0,
        'target_price': 99.0,
        'time_stop_minutes': 30,
    })
    res = resolver.resolve_one(alert)
    assert res['exit_reason'] == 'target_hit'
    assert res['exit_price'] == pytest.approx(99.0)


# ── 3) time_stop fires when no target hit and elapsed >= time_stop ────

def test_resolve_one_time_stop(make_resolver):
    """When neither target nor RSI fires, time_stop fires after the
    configured minutes have elapsed."""
    # Build 35 bars at 1-minute increments — price stays flat, never
    # hits target. RSI stays around 50 with flat prices so rsi_extreme
    # also never fires.
    base = datetime(2026, 5, 7, 13, 30, 0)
    rows = [(base + timedelta(minutes=i), 100.0) for i in range(35)]
    bars = _intraday(rows)
    resolver = make_resolver(bars)

    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': base,
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 110.0,   # never reached
        'time_stop_minutes': 30,
    })
    res = resolver.resolve_one(alert)
    assert res is not None
    assert res['exit_reason'] == 'time_stop'
    # 30 minutes elapsed at 14:00; first bar with elapsed >= 30 wins
    assert res['exit_ts'] == datetime(2026, 5, 7, 14, 0, 0)


# ── 4) eod_close fallback when nothing fired before last bar ──────────

def test_resolve_one_eod_close_fallback(make_resolver):
    """If neither target/time_stop/RSI fires within the day's bars,
    fall back to eod_close at session close (16:00 ET)."""
    # 5 bars at perfectly flat price — RSI stays at 50 (or NaN with
    # only 5 bars vs period=14), target never reached, time_stop
    # never elapses. Forces the eod_close branch.
    bars = _intraday([
        ('2026-05-07 15:30', 100.0),
        ('2026-05-07 15:31', 100.0),
        ('2026-05-07 15:32', 100.0),
        ('2026-05-07 15:33', 100.0),
        ('2026-05-07 15:34', 100.0),
    ])
    resolver = make_resolver(bars)

    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': datetime(2026, 5, 7, 15, 30, 0),
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 110.0,    # never reached
        'time_stop_minutes': 60,  # never elapses (only 4 min of bars)
    })
    res = resolver.resolve_one(alert)
    assert res is not None
    assert res['exit_reason'] == 'eod_close'
    # exit_ts = 16:00 ET = 20:00 UTC naive
    assert res['exit_ts'].hour == 20
    # Exit price comes from the day's last bar (100.0)
    assert res['exit_price'] == pytest.approx(100.0)


def test_resolve_one_eod_close_when_alert_after_last_bar(make_resolver):
    """Alert fires at 15:59 but AV's last logged bar is 15:58 — the
    forward window is empty. Must still resolve to eod_close, not None."""
    bars = _intraday([
        ('2026-05-07 15:55', 100.0),
        ('2026-05-07 15:56', 100.05),
        ('2026-05-07 15:57', 100.1),
        ('2026-05-07 15:58', 100.1),  # last logged bar
    ])
    resolver = make_resolver(bars)
    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': datetime(2026, 5, 7, 15, 59, 0),  # AFTER last bar
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.1,
        'target_price': 110.0,
        'time_stop_minutes': 30,
    })
    res = resolver.resolve_one(alert)
    assert res is not None
    assert res['exit_reason'] == 'eod_close'


# ── 5) Missing intraday partition → skipped, not crashed ─────────────

def test_resolve_one_skips_when_intraday_empty(make_resolver):
    """A (ticker, day) with no intraday data returns None — caller logs
    + continues. Backfill robustness: one missing day shouldn't kill
    the batch."""
    resolver = make_resolver(pd.DataFrame())
    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': datetime(2026, 5, 7, 13, 30, 0),
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 101.0,
        'time_stop_minutes': 30,
    })
    assert resolver.resolve_one(alert) is None


# ── 6) Per-day cache: load_intraday called once per (ticker, day) ─────

def test_intraday_cache_hits_once_per_ticker_day(make_resolver):
    """Two alerts on the same (ticker, alert_date) should trigger a
    single load_intraday call — capacity calc per CLAUDE.md §0."""
    bars = _intraday([
        ('2026-05-07 13:30', 100.0),
        ('2026-05-07 13:31', 101.0),  # target
    ])
    resolver = make_resolver(bars)
    alert_template = {
        'ticker': 'SPY',
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 101.0,
        'time_stop_minutes': 30,
    }
    a1 = pd.Series({**alert_template, 'alert_ts': datetime(2026, 5, 7, 13, 30, 0)})
    a2 = pd.Series({**alert_template, 'alert_ts': datetime(2026, 5, 7, 13, 30, 30)})

    resolver.resolve_one(a1)
    resolver.resolve_one(a2)
    assert resolver.loader.load_intraday.call_count == 1, (
        "Two alerts on same (SPY, 2026-05-07) MUST share one load_intraday call"
    )


# ── 6b) Codex P1: predicate must include today's session ─────────────

def test_find_open_alerts_predicate_uses_le_not_lt():
    """Codex P1 review on PR #319 (#3211892819): the original
    `alert_date < CURRENT_DATE` predicate skipped today's session
    because at the 16:30 ET / 20:30 UTC schedule, Postgres
    CURRENT_DATE IS the same calendar day as the alerts being
    reconciled. Lock in `alert_date <= CURRENT_DATE` so the daily
    EOD run actually closes its scheduled session."""
    from gcp.signal_monitor_eod_resolver import EODResolver
    from unittest.mock import patch
    resolver = EODResolver()
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.query_to_dataframe', return_value=pd.DataFrame()) as mock_q:
        resolver.find_open_alerts()
    sql_arg = mock_q.call_args[0][0]
    # The fix: must be <= not <
    assert 'alert_date <= CURRENT_DATE' in sql_arg, (
        "predicate must use `alert_date <= CURRENT_DATE` so today's "
        "alerts are included in the daily EOD sweep; got SQL:\n" + sql_arg
    )
    assert 'alert_date < CURRENT_DATE' not in sql_arg, (
        "regression: `<` predicate excludes today's session entirely; "
        "Friday alerts would wait until Monday's run"
    )


# ── 6c) Codex P1: load_intraday gets a full-day range ────────────────

def test_load_day_passes_full_day_range_not_midnight_start():
    """Codex P1 review on PR #319 (#3211892821): passing `start_date`
    and `end_date` as the same bare date string produces a Postgres
    predicate `ts >= :start AND ts <= :end` where Postgres parses both
    as midnight start-of-day. With end_date='2026-05-07', `ts <=
    '2026-05-07'` excludes every market-hours bar (which all have
    ts > midnight). Lock in a full-day range — start at 00:00 of
    alert_date, end at 00:00 of next day — so market hours bars are
    captured."""
    from gcp.signal_monitor_eod_resolver import EODResolver
    from unittest.mock import MagicMock
    resolver = EODResolver()
    resolver.loader = MagicMock()
    resolver.loader.load_intraday.return_value = pd.DataFrame()
    # Trigger _load_day for (SPY, 2026-05-07)
    resolver._load_day('SPY', '2026-05-07')
    args, kwargs = resolver.loader.load_intraday.call_args
    start = kwargs.get('start_date') or (args[1] if len(args) > 1 else None)
    end = kwargs.get('end_date') or (args[2] if len(args) > 2 else None)
    assert start and end, f"load_intraday must receive both start and end; got args={args} kwargs={kwargs}"
    # start_date should resolve to midnight 5/7
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    assert start_ts == pd.Timestamp('2026-05-07 00:00:00'), (
        f"start_date should be 5/7 midnight, got {start_ts}"
    )
    # end_date must be STRICTLY AFTER 5/7 midnight to capture market bars
    assert end_ts > pd.Timestamp('2026-05-07 00:00:00'), (
        f"end_date must be after 5/7 00:00:00 to capture market bars; "
        f"got {end_ts} which would match zero bars (Codex P1 regression)"
    )
    # end should cover at least through end-of-day (16:00 ET = 20:00 UTC).
    # The fix uses next-day midnight (5/8 00:00:00) which trivially covers it.
    assert end_ts >= pd.Timestamp('2026-05-07 20:00:00'), (
        f"end_date should cover through session close; got {end_ts}"
    )


# ── 7) RSI extreme fires on a CALL when RSI >= call_rsi_exit ──────────

def test_resolve_one_rsi_extreme_call(make_resolver):
    """A CALL position should resolve to rsi_extreme when RSI crosses
    the call_rsi_exit threshold (default 80) BEFORE target_hit."""
    # Construct a steady-rise series — RSI matures to 100 within a
    # couple bars. Target is set unreachably high so target_hit doesn't
    # pre-empt rsi_extreme.
    base = datetime(2026, 5, 7, 13, 30, 0)
    closes = [100.0]
    for _ in range(30):
        closes.append(closes[-1] + 0.5)   # steady gains → RSI → 100
    rows = [(base + timedelta(minutes=i), c) for i, c in enumerate(closes)]
    bars = _intraday(rows)
    resolver = make_resolver(bars)
    alert = pd.Series({
        'ticker': 'SPY',
        'alert_ts': base,
        'alert_date': '2026-05-07',
        'direction': 'CALL',
        'price_at_signal': 100.0,
        'target_price': 200.0,    # never reached — out of the way
        'time_stop_minutes': 999, # never elapses — out of the way
    })
    res = resolver.resolve_one(alert)
    assert res is not None
    assert res['exit_reason'] == 'rsi_extreme', (
        f"steady-rise CALL must trip RSI>=80 before any other reason; got {res['exit_reason']}"
    )


# ── 6) build_digest_embed — EOD Discord summary ───────────────────────

def _resolved(ticker, direction, reason, ret):
    return {'ticker': ticker, 'direction': direction,
            'exit_reason': reason, 'exit_return_pct': ret}


def test_build_digest_embed_basic_summary():
    from gcp.signal_monitor_eod_resolver import EODResolver
    exits = [
        _resolved('SPY', 'CALL', 'target_hit', 2.5),
        _resolved('IWM', 'PUT', 'time_stop', -1.0),
        _resolved('QQQ', 'CALL', 'eod_close', 0.5),
    ]
    embed = EODResolver.build_digest_embed(exits, since=None)
    assert embed['title'] == 'EOD Signal Resolution'
    desc = embed['description']
    assert 'Resolved **3** post-close exits' in desc
    # by-reason summary, sorted
    assert '1 eod_close' in desc and '1 target_hit' in desc and '1 time_stop' in desc
    # net = 2.5 - 1.0 + 0.5 = 2.0, avg = 0.667, wins = 2/3
    assert 'Win rate 2/3' in desc
    assert 'net +2.00%' in desc
    # net positive → green
    assert embed['color'] == 0x2ecc71


def test_build_digest_embed_net_negative_is_red():
    from gcp.signal_monitor_eod_resolver import EODResolver
    exits = [_resolved('SPY', 'CALL', 'time_stop', -3.0),
             _resolved('IWM', 'PUT', 'eod_close', 1.0)]
    embed = EODResolver.build_digest_embed(exits, since=None)
    assert embed['color'] == 0xe74c3c
    assert 'net -2.00%' in embed['description']


def test_build_digest_embed_caps_list_at_25():
    from gcp.signal_monitor_eod_resolver import EODResolver
    # 30 exits — list capped at 25, overflow line shown
    exits = [_resolved(f'T{i}', 'CALL', 'target_hit', float(i)) for i in range(1, 31)]
    embed = EODResolver.build_digest_embed(exits, since=None)
    desc = embed['description']
    assert 'Resolved **30** post-close exits' in desc
    assert '_…and 5 more_' in desc
    # ranked by |return| desc — biggest mover (T30, +30%) must appear
    assert '**T30**' in desc


def test_build_digest_embed_since_in_description():
    from gcp.signal_monitor_eod_resolver import EODResolver
    embed = EODResolver.build_digest_embed(
        [_resolved('SPY', 'CALL', 'target_hit', 1.0)], since='2026-04-01')
    assert '(since 2026-04-01)' in embed['description']


def test_post_digest_noop_without_webhook(make_resolver):
    """_post_digest must not raise / not POST when webhook is unset."""
    resolver = make_resolver()
    resolver.webhook_url = None
    with patch('gcp.signal_monitor_eod_resolver.requests.post') as post:
        resolver._post_digest([_resolved('SPY', 'CALL', 'target_hit', 1.0)], None)
    post.assert_not_called()


def test_post_digest_noop_with_no_exits(make_resolver):
    """Empty resolution batch → no Discord post even with a webhook set."""
    resolver = make_resolver()
    resolver.webhook_url = 'https://discord.com/api/webhooks/x/y'
    with patch('gcp.signal_monitor_eod_resolver.requests.post') as post:
        resolver._post_digest([], None)
    post.assert_not_called()
