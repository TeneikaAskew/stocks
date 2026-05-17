"""Hermetic tests for gcp/signal_replay.py — the stored-alert Discord replay.

No Cloud SQL, no live network. Covers:
  1. parse_time_block  — ET→UTC conversion, bad input, non-positive window
  2. build_replay_embed — REPLAY tag, original fire time, entry/exit, gray
  3. build_header_embed — batch announcement + cap warning
  4. _present          — None / NaN / real-value discrimination
  5. post_replays      — paced posting, posted/failed accounting
  6. fetch_alerts      — ticker filter applied in-memory
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.signal_replay import (  # noqa: E402
    _present,
    build_header_embed,
    build_replay_embed,
    fetch_alerts,
    parse_time_block,
    post_replays,
)

_UTC = ZoneInfo("UTC")
_ET = ZoneInfo("America/New_York")


# ── 1) parse_time_block ────────────────────────────────────────────────

def test_parse_time_block_et_to_utc():
    """May is EDT (UTC-4): 09:30 ET → 13:30 UTC, 10:30 ET → 14:30 UTC."""
    start, end = parse_time_block("2026-05-15", "09:30", "10:30")
    assert start == datetime(2026, 5, 15, 13, 30, tzinfo=_UTC)
    assert end == datetime(2026, 5, 15, 14, 30, tzinfo=_UTC)


def test_parse_time_block_first_half_hour():
    start, end = parse_time_block("2026-05-15", "09:30", "10:00")
    assert (end - start).total_seconds() == 30 * 60


def test_parse_time_block_bad_date():
    with pytest.raises(ValueError, match="date must be YYYY-MM-DD"):
        parse_time_block("05/15/2026", "09:30", "10:30")


def test_parse_time_block_bad_time():
    with pytest.raises(ValueError, match="must be HH:MM"):
        parse_time_block("2026-05-15", "9h30", "10:30")


def test_parse_time_block_end_not_after_start():
    with pytest.raises(ValueError, match="must be after start"):
        parse_time_block("2026-05-15", "10:30", "09:30")


def test_parse_time_block_equal_window_rejected():
    with pytest.raises(ValueError, match="must be after start"):
        parse_time_block("2026-05-15", "10:00", "10:00")


# ── 2) _present ────────────────────────────────────────────────────────

def test_present_discriminates_none_nan_value():
    assert _present(0.0) is True       # a real 0 is present
    assert _present(12.5) is True
    assert _present("CALL") is True
    assert _present(None) is False
    assert _present(float("nan")) is False


# ── 3) build_replay_embed ──────────────────────────────────────────────

def _alert(**over):
    base = {
        'ticker': 'SPY', 'alert_ts': datetime(2026, 5, 15, 13, 42, 15, tzinfo=_UTC),
        'direction': 'CALL', 'total_score': 8.5, 'strength_label': 'strong',
        'price_at_signal': 521.30, 'target_price': 524.10,
        'time_stop_minutes': 30, 'rsi': 63.2, 'rvol': 1.85,
        'level_broken': 'PDH', 'exit_ts': None, 'exit_reason': None,
        'exit_price': None, 'exit_return_pct': None,
    }
    base.update(over)
    return base


def test_build_replay_embed_tagged_and_shows_fire_time():
    embed = build_replay_embed(_alert())
    assert embed['title'].startswith('🔁 REPLAY')
    assert 'SPY' in embed['title'] and 'CALL' in embed['title']
    # 13:42:15 UTC → 09:42:15 EDT
    assert 'Would have fired:** 2026-05-15 09:42:15 ET' in embed['description']
    assert embed['color'] == 0x95a5a6   # gray


def test_build_replay_embed_includes_entry_and_indicators():
    desc = build_replay_embed(_alert())['description']
    assert 'Score 8.5 · strong' in desc
    assert 'Entry $521.30 → Target $524.10' in desc
    assert 'Level broken: PDH' in desc
    assert 'RSI 63.2' in desc and 'RVOL 1.85' in desc


def test_build_replay_embed_unresolved_outcome():
    desc = build_replay_embed(_alert())['description']
    assert 'Outcome: unresolved' in desc


def test_build_replay_embed_resolved_outcome():
    desc = build_replay_embed(_alert(
        exit_reason='target_hit', exit_price=524.10, exit_return_pct=0.54,
    ))['description']
    assert '**Outcome:** target_hit @ $524.10 (+0.54%)' in desc


def test_build_replay_embed_omits_missing_fields_not_zero():
    """Missing financial fields are omitted entirely — never rendered 0."""
    desc = build_replay_embed(_alert(
        total_score=None, rsi=float('nan'), rvol=None, level_broken=None,
    ))['description']
    assert 'Score' not in desc
    assert 'RSI' not in desc and 'RVOL' not in desc
    assert 'Level broken' not in desc
    # entry/target still present
    assert 'Entry $521.30' in desc


def test_build_replay_embed_naive_timestamp_treated_as_utc():
    """A tz-naive alert_ts is read as UTC, then rendered in ET."""
    desc = build_replay_embed(_alert(
        alert_ts=datetime(2026, 5, 15, 13, 42, 15),
    ))['description']
    assert '09:42:15 ET' in desc


def test_build_replay_embed_put_uses_red_dot():
    assert '🔴' in build_replay_embed(_alert(direction='PUT'))['title']


# ── 4) build_header_embed ──────────────────────────────────────────────

def test_build_header_embed_basic():
    embed = build_header_embed('2026-05-15', '09:30', '10:30', None, 12)
    assert embed['title'] == '🔁 Signal Replay'
    assert 'Re-posting **12** stored alerts' in embed['description']
    assert '2026-05-15 09:30–10:30 ET' in embed['description']
    assert 'not live alerts' in embed['description']


def test_build_header_embed_ticker_scope_and_cap_warning():
    embed = build_header_embed('2026-05-15', '09:30', '16:00',
                               ['spy', 'qqq'], 200, capped=True)
    assert 'SPY, QQQ' in embed['description']
    assert 'Narrow the time block' in embed['description']


def test_build_header_embed_singular_alert():
    embed = build_header_embed('2026-05-15', '09:30', '09:45', None, 1)
    assert 'Re-posting **1** stored alert from' in embed['description']


# ── 5) post_replays ────────────────────────────────────────────────────

def test_post_replays_posts_each_alert_paced():
    alerts = [_alert(ticker='SPY'), _alert(ticker='QQQ'), _alert(ticker='IWM')]
    resp = MagicMock(status_code=204)
    with patch('gcp.signal_replay.requests.post', return_value=resp) as post, \
         patch('gcp.signal_replay.time.sleep') as sleep:
        posted, failed = post_replays(alerts, 'https://discord.com/api/webhooks/x')
    assert (posted, failed) == (3, 0)
    assert post.call_count == 3
    # paced between posts: N-1 sleeps
    assert sleep.call_count == 2


def test_post_replays_counts_failures_without_aborting_batch():
    """A failed post is counted (not silently dropped) and the batch
    continues — the alert AFTER the failure still posts."""
    alerts = [_alert(ticker='SPY'), _alert(ticker='QQQ'), _alert(ticker='IWM')]
    ok = MagicMock(status_code=204)
    bad = MagicMock(status_code=500)
    bad.raise_for_status.side_effect = RuntimeError("500")
    # SPY ok · QQQ fails (500 is not retried — only 429 is) · IWM ok
    with patch('gcp.signal_replay.requests.post',
               side_effect=[ok, bad, ok]), \
         patch('gcp.signal_replay.time.sleep'):
        posted, failed = post_replays(alerts, 'https://discord.com/api/webhooks/x')
    assert (posted, failed) == (2, 1)


def test_post_replays_honors_429_retry_after():
    alerts = [_alert(ticker='SPY')]
    rate_limited = MagicMock(status_code=429, headers={'Retry-After': '0.1'})
    ok = MagicMock(status_code=204)
    with patch('gcp.signal_replay.requests.post',
               side_effect=[rate_limited, ok]) as post, \
         patch('gcp.signal_replay.time.sleep') as sleep:
        posted, failed = post_replays(alerts, 'https://discord.com/api/webhooks/x')
    assert (posted, failed) == (1, 0)
    assert post.call_count == 2          # retried after the 429
    sleep.assert_any_call(0.1 + 0.5)     # Retry-After honored


# ── 6) fetch_alerts ────────────────────────────────────────────────────

def test_fetch_alerts_applies_ticker_filter_in_memory():
    import pandas as pd
    rows = pd.DataFrame([
        {'ticker': 'SPY', 'alert_ts': datetime(2026, 5, 15, 14, tzinfo=_UTC)},
        {'ticker': 'QQQ', 'alert_ts': datetime(2026, 5, 15, 14, 5, tzinfo=_UTC)},
        {'ticker': 'IWM', 'alert_ts': datetime(2026, 5, 15, 14, 9, tzinfo=_UTC)},
    ])
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.query_to_dataframe', return_value=rows):
        out = fetch_alerts(datetime(2026, 5, 15, 13, 30, tzinfo=_UTC),
                           datetime(2026, 5, 15, 14, 30, tzinfo=_UTC),
                           tickers=['spy', 'IWM'])
    assert {r['ticker'] for r in out} == {'SPY', 'IWM'}


def test_fetch_alerts_raises_when_cloud_sql_unconfigured():
    """No silent empty list — a missing DB config fails loud."""
    with patch('gcp.database.is_cloud_sql_configured', return_value=False):
        with pytest.raises(RuntimeError, match="Cloud SQL not configured"):
            fetch_alerts(datetime(2026, 5, 15, 13, 30, tzinfo=_UTC),
                         datetime(2026, 5, 15, 14, 30, tzinfo=_UTC))
