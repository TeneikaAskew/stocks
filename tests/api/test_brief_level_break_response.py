"""FEAT-IND-001: a producer-derived level break reaches GET /api/dashboard/brief.

The level-break unit tests stop at the scoring helpers. This one follows the
status the dashboard briefing strip shows end to end:

  real daily bars
  -> gcp.premarket_brief.generate_premarket_brief (the real add_brief_indicators,
     check_call_conditions / check_put_conditions and _resolve_signal_status)
  -> gcp.premarket_brief.persist_to_cloud_sql (the real row builder; only the
     database writes are captured in memory)
  -> GET /api/dashboard/brief/{ticker} (the real router, reading the captured
     premarket_analysis row through a fake _query_fn that applies the router's
     own WHERE ticker / run_kind = 'live' / analysis_date <= date filter)

The control run is the same bars with the two Broke_Prev_Day_* columns dropped
from add_brief_indicators' output, which is what origin/main produces (it never
creates them). The published status must move from CALL building to CALL setup.

No network and no database: sockets refuse to connect, and every Cloud SQL
call is replaced at the gcp.database boundary.
"""
from __future__ import annotations

import socket
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TICKER = 'IWM'
FLAGS = ['Broke_Prev_Day_High', 'Broke_Prev_Day_Low']
CALL_OTHERS = ['consecutive_down', 'rsi_oversold_zone', 'below_vwap', 'stoch_rsi_oversold']
PUT_OTHERS = ['consecutive_up', 'rsi_overbought_zone', 'above_vwap', 'stoch_rsi_overbought']


@pytest.fixture(scope="module")
def client():
    import os
    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)
    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c
    os.chdir(original_cwd)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('external I/O attempted in an isolated API test')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)


def _bars(n: int = 250, seed: int = 4) -> pd.DataFrame:
    """Valid daily OHLCV bars (High and Low bound Open and Close)."""
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    idx = pd.bdate_range('2026-01-05', periods=n, name='Time')
    df = pd.DataFrame({
        'Open': open_,
        'High': body_hi + rng.uniform(0.2, 1.5, n),
        'Low': body_lo - rng.uniform(0.2, 1.5, n),
        'Close': close,
        'Volume': rng.randint(1e6, 5e6, n).astype(float),
    }, index=idx)
    df['Time'] = df.index
    return df


def _session_where_the_break_decides(bars: pd.DataFrame) -> int:
    """First session whose close is above the prior session's high, whose CALL
    score is 2 on every other condition (so the break is what would make it a
    setup), and whose PUT score is below building. Found with the real
    producers, and without reading the new columns, so the same search runs
    on origin/main and the test fails there on the published status."""
    from lib.indicators import add_brief_indicators
    from lib.signals import check_call_conditions, check_put_conditions
    rows = add_brief_indicators(bars.copy(), close_col='Close')
    broke_high = bars['Close'] > bars['High'].shift(1)
    for i in range(60, len(rows) - 1):
        if not broke_high.iloc[i]:
            continue
        row = rows.iloc[i]
        without, _ = check_call_conditions(row, enabled_conditions=CALL_OTHERS)
        put, _ = check_put_conditions(row, enabled_conditions=PUT_OTHERS)
        if without == 2 and put < 2:
            return i
    raise AssertionError('fixture has no session where the level break decides the status')


class _FakeEngine:
    @contextmanager
    def connect(self):
        class _Conn:
            class connection:
                @staticmethod
                def commit():
                    return None
        yield _Conn()


def _run_brief_and_persist(monkeypatch, bars: pd.DataFrame, analysis_date: date,
                           drop_flags: bool) -> pd.DataFrame:
    """Run the real brief for one ticker on `bars` and return the
    premarket_analysis rows persist_to_cloud_sql writes."""
    from gcp import premarket_brief as pb
    import gcp.database as database
    import lib.strat_levels as strat_levels
    from lib.config import AppConfig
    from lib.data_loader import DataLoader

    monkeypatch.delenv('BRIEF_AS_OF', raising=False)        # a live run
    for key, value in {'BRIEF_AMC_REACTIONS': '0', 'BRIEF_LLM_DISABLE': '1',
                       'BRIEF_TICKERS': TICKER}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(pb, '_resolve_analysis_date', lambda: analysis_date)
    # The level parameters (per-ticker parameters, 2026-11-08): every key at
    # the #1753 values, through load_level_params's own SQL.
    from tests.lib.level_params_fixtures import legacy_db
    monkeypatch.setattr(pb, '_level_params_query', legacy_db(TICKER).query)
    monkeypatch.setattr(DataLoader, 'load_daily', lambda *a, **k: bars.copy())
    monkeypatch.setattr(pb, 'load_earnings_for_brief', lambda *a, **k: {'earnings': []})
    monkeypatch.setattr(pb, '_ew_recap_or_unavailable', lambda *a, **k: {})
    monkeypatch.setattr(pb, 'load_economic_events', lambda *a, **k: {'today': []})
    monkeypatch.setattr(pb, '_load_gamma_freshness', lambda *a, **k: dict(
        data_source='unavailable', snapshot_ts=None, snapshot_date=None, days_behind=None))
    # The playbook's strat_levels write is a database write: capture it.
    monkeypatch.setattr(database, 'get_engine', lambda *a, **k: _FakeEngine())
    monkeypatch.setattr(strat_levels, 'persist_level_map', lambda *a, **k: 0)
    # Set on every run, so one run's choice never leaks into the next.
    from lib.indicators import add_brief_indicators as real
    monkeypatch.setattr(pb, 'add_brief_indicators',
                        (lambda df, **k: real(df, **k).drop(columns=FLAGS, errors='ignore')) if drop_flags
                        else real)

    cfg = AppConfig()
    cfg.market.tickers = [TICKER]
    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: False)
    brief = pb.generate_premarket_brief(cfg=cfg)
    assert brief['tickers'][TICKER].get('playbook_error') is None

    written: dict[str, list[pd.DataFrame]] = {}

    def capture(df, table, *_a, **_k):
        written.setdefault(table, []).append(df.copy())
        return len(df)

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'bulk_insert_dataframe', capture)
    monkeypatch.setattr(database, 'upsert_dataframe', capture)
    monkeypatch.setattr(database, 'row_exists', lambda *a, **k: False)
    assert pb.persist_to_cloud_sql(brief) == 1
    return pd.concat(written['premarket_analysis'], ignore_index=True)


def _serve(monkeypatch, premarket_table: pd.DataFrame):
    """Install a fake _query_fn backed by an in-memory premarket_analysis
    table, applying the router's own filter for the premarket query."""
    from api.routers import dashboard as dash_module
    monkeypatch.setattr(dash_module, '_CLOUD_SQL', True)

    def fake_query(sql, params=None):
        params = params or {}
        if 'FROM premarket_analysis' in sql:
            assert "run_kind = 'live'" in sql
            t = premarket_table
            t = t[(t['ticker'] == params['ticker']) & (t['run_kind'] == 'live')]
            if 'date' in params:
                t = t[pd.to_datetime(t['analysis_date']) <= pd.Timestamp(params['date'])]
            return t.sort_values('analysis_date', ascending=False).head(1).reset_index(drop=True)
        return pd.DataFrame()

    monkeypatch.setattr(dash_module, '_query_fn', fake_query)


def test_a_level_break_changes_the_published_brief_status(client, monkeypatch, no_network):
    bars = _bars()
    i = _session_where_the_break_decides(bars)
    session = bars.index[i]
    analysis_date = bars.index[i + 1].date()     # the brief scores session D = i
    history = bars.iloc[:i + 1]

    before = _run_brief_and_persist(monkeypatch, history, analysis_date, drop_flags=True)
    after = _run_brief_and_persist(monkeypatch, history, analysis_date, drop_flags=False)
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
    print(f'GET {url} without the level-break flags (origin/main): '
          f'signal_status={b["signal_status"]!r}')
    print(f'GET {url} with the flags (this branch): signal_status={a["signal_status"]!r}')

    assert b['source'] == a['source'] == 'cloud_sql'
    assert b['has_premarket'] is a['has_premarket'] is True
    assert str(b['analysis_date']).startswith(analysis_date.isoformat())
    assert b['signal_status'] == 'CALL building (2/5)'
    assert a['signal_status'] == 'CALL setup (3/5)'
    # Only the status moves: every other premarket field the router serves is
    # the same in both responses.
    same = {k: v for k, v in b.items() if k != 'signal_status'}
    assert {k: a[k] for k in same} == same
