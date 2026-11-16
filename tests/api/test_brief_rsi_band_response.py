"""FEAT-SIGNAL-001: the ticker's calibrated RSI band reaches GET /api/dashboard/brief.

The RSI-band unit tests (tests/gcp/test_premarket_brief.py::TestBriefRsiBands)
stop at the brief's ticker record. This one follows the status the dashboard
briefing strip shows end to end, the same path as
tests/api/test_brief_level_break_response.py:

  real daily bars
  -> gcp.premarket_brief.generate_premarket_brief (the real add_brief_indicators,
     resolve_rsi_bands, check_call_conditions / check_put_conditions and
     _resolve_signal_status)
  -> gcp.premarket_brief.persist_to_cloud_sql (the real row builder; only the
     database writes are captured in memory)
  -> GET /api/dashboard/brief/{ticker} (the real router, reading the captured
     premarket_analysis row through a fake _query_fn)

The control run has no ticker_calibration row, so the resolver falls back to
Tier B, the hard-coded (25, 50) / (50, 75) bands origin/main always used. The
treatment run has a Tier-A row (p10 35.0, p50 50.5, p90 65.0) in force on the
analysis date. The session is one whose daily RSI sits between 25 and 35, so
the RSI point is what moves the published status from CALL setup to CALL
building. Only lib.strategies.calibration._latest_calibration (the SQL read)
is replaced.

No network and no database: sockets refuse to connect, and every Cloud SQL
call is replaced at the gcp.database boundary.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.api.test_brief_level_break_response import (  # noqa: F401  (fixtures)
    TICKER, _bars, _run_brief_and_persist, _serve, client, no_network,
)

TIER_A_CALL = (35.0, 50.5)
TIER_A_PUT = (50.5, 65.0)


def _sessions_where_the_band_decides(bars) -> list[int]:
    """Sessions whose CALL score is 3 under the hard-coded band and 2 under
    Tier A's, with PUT below building under both. Found with the real
    producers, so the same search runs on origin/main. The FTFC gate can
    still publish another side, so the test takes the first of these the
    control brief publishes as CALL setup."""
    from lib.indicators import add_brief_indicators
    from lib.signals import check_call_conditions, check_put_conditions
    rows = add_brief_indicators(bars.copy(), close_col='Close')
    found = []
    for i in range(60, len(rows) - 1):
        row = rows.iloc[i]
        hard, _ = check_call_conditions(row)
        tier_a, _ = check_call_conditions(row, rsi_range=TIER_A_CALL)
        put_hard, _ = check_put_conditions(row)
        put_a, _ = check_put_conditions(row, rsi_range=TIER_A_PUT)
        if hard == 3 and tier_a == 2 and put_hard < 2 and put_a < 2:
            found.append(i)
    return found


def _calibration(monkeypatch, row):
    from lib.strategies import calibration
    seen = []

    def latest(ticker, as_of=None):
        seen.append((ticker, as_of))
        return row
    monkeypatch.setattr(calibration, '_latest_calibration', latest)
    return seen


def test_the_calibrated_band_changes_the_published_brief_status(client, monkeypatch, no_network):
    def candidates():
        for seed in range(1, 21):
            bars = _bars(seed=seed)
            for i in _sessions_where_the_band_decides(bars):
                yield bars, i

    for bars, i in candidates():
        analysis_date = bars.index[i + 1].date()     # the brief scores session D = i
        _calibration(monkeypatch, None)
        control = _run_brief_and_persist(monkeypatch, bars.iloc[:i + 1], analysis_date,
                                         drop_flags=False)
        if control['signal_status'].tolist() == ['CALL setup (3/5)']:
            break
    else:
        raise AssertionError('no candidate session publishes CALL setup under the FTFC gate')
    session = bars.index[i]
    history = bars.iloc[:i + 1]
    tier_a_row = {'calibration_date': analysis_date - timedelta(days=30),
                  'rsi_p10': TIER_A_CALL[0], 'rsi_p25': 43.0, 'rsi_p50': TIER_A_CALL[1],
                  'rsi_p75': 57.0, 'rsi_p90': TIER_A_PUT[1], 'drift_flagged': False}

    seen_b = _calibration(monkeypatch, None)
    before = _run_brief_and_persist(monkeypatch, history, analysis_date, drop_flags=False)
    seen_a = _calibration(monkeypatch, tier_a_row)
    after = _run_brief_and_persist(monkeypatch, history, analysis_date, drop_flags=False)
    assert seen_b == seen_a == [(TICKER, analysis_date)]
    for rows in (before, after):
        assert rows['run_kind'].tolist() == ['live']
        assert rows['ticker'].tolist() == [TICKER]

    url = f'/api/dashboard/brief/{TICKER}?date={analysis_date.isoformat()}'
    _serve(monkeypatch, before)
    r_before = client.get(url)
    _serve(monkeypatch, after)
    r_after = client.get(url)
    assert r_before.status_code == r_after.status_code == 200
    b, a = r_before.json(), r_after.json()
    print(f'\nscored session {session.date()}, analysis_date {analysis_date}')
    print(f'GET {url} with no calibration row (Tier B, origin/main bands): '
          f'signal_status={b["signal_status"]!r}')
    print(f'GET {url} with the Tier-A row (this branch): signal_status={a["signal_status"]!r}')

    assert b['source'] == a['source'] == 'cloud_sql'
    assert b['has_premarket'] is a['has_premarket'] is True
    assert str(b['analysis_date']).startswith(analysis_date.isoformat())
    assert b['signal_status'] == 'CALL setup (3/5)'
    assert a['signal_status'] == 'CALL building (2/5)'
    # Only the status moves: every other premarket field the router serves is
    # the same in both responses.
    same = {k: v for k, v in b.items() if k != 'signal_status'}
    assert {k: a[k] for k in same} == same
