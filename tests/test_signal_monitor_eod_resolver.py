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
