"""Tests for the watched-ticker ingest job (fetch-watched-tickers).

Task 1 covers ``fetch_market_data._run_backfill`` learning a forced
``outputsize`` and a ``data_source`` label, and returning the number of
rows it passed to ``upsert_dataframe``. Later tasks extend this file.

The ``av_stub`` fixture replaces the Alpha Vantage call and the DB upsert
and records what each saw, so tests assert on I/O shape, not on the network.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from gcp.fetchers import fetch_market_data as fmd


def make_bars(n: int, ticker: str = 'X') -> pd.DataFrame:
    """n daily bars ending on a past date, safely inside the 10y cutoff."""
    dates = pd.bdate_range(end='2026-01-30', periods=n).date
    return pd.DataFrame({
        'ticker': ticker, 'date': list(dates),
        'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0,
        'volume': 100, 'adjusted_close': 1.0,
    })


@pytest.fixture
def av_stub(monkeypatch):
    """Stub AV + upsert; returns a recorder.

    rec.av_calls: list of (ticker, outputsize); rec.frames: upserted frames.
    Set rec.bars_by_ticker[ticker] = n_bars to control returned data
    (default 3); 0 returns an empty frame ("no data returned").
    """
    rec = SimpleNamespace(av_calls=[], frames=[], bars_by_ticker={})

    def fake_av(ticker, api_key, outputsize):
        rec.av_calls.append((ticker, outputsize))
        n = rec.bars_by_ticker.get(ticker, 3)
        return make_bars(n, ticker) if n else pd.DataFrame()

    def fake_upsert(df, table, keys):
        rec.frames.append(df.copy())

    monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake-key')
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '0')
    monkeypatch.setattr(fmd, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(fmd, '_av_get_full_daily_series', fake_av)
    monkeypatch.setattr('gcp.database.upsert_dataframe', fake_upsert)
    return rec


def test_run_backfill_forced_outputsize_pulls_every_ticker_at_that_size(av_stub):
    fmd._run_backfill(['AAA', 'BBB'], outputsize='compact',
                      data_source='av_watched_backfill')
    assert av_stub.av_calls == [('AAA', 'compact'), ('BBB', 'compact')]
    assert len(av_stub.frames) == 2
    for frame in av_stub.frames:
        assert set(frame['data_source']) == {'av_watched_backfill'}


def test_run_backfill_without_keywords_keeps_full_and_default_source(av_stub):
    fmd._run_backfill(['AAA'])
    assert av_stub.av_calls == [('AAA', 'full')]
    assert set(av_stub.frames[0]['data_source']) == {'av_daily_backfill'}


def test_run_backfill_returns_the_rows_it_upserted(av_stub):
    av_stub.bars_by_ticker = {'AAA': 5, 'BBB': 7}
    assert fmd._run_backfill(['AAA', 'BBB']) == 12


def test_run_backfill_returns_zero_when_no_ticker_returns_data(av_stub):
    av_stub.bars_by_ticker = {'AAA': 0, 'BBB': 0}
    assert fmd._run_backfill(['AAA', 'BBB']) == 0
    assert av_stub.frames == []


# ---------------------------------------------------------------------------
# Task 3: config, the set read with its exact overflow, the second-guard dedup
# ---------------------------------------------------------------------------
import re
from datetime import date
from pathlib import Path

from gcp.fetchers import fetch_watched_tickers as fwt

_MODULE_SRC = (Path(__file__).resolve().parents[2]
               / 'gcp' / 'fetchers' / 'fetch_watched_tickers.py')


def _set_frame(tickers, eligible_total):
    return pd.DataFrame({'ticker': tickers,
                         'eligible_total': [eligible_total] * len(tickers)})


class _Query:
    def __init__(self, frame=None, exc=None):
        self.frame, self.exc, self.calls = frame, exc, []

    def __call__(self, sql, params=None, timeout_s=None):
        self.calls.append((sql, params, timeout_s))
        if self.exc:
            raise self.exc
        return self.frame


def test_config_default_and_env_override():
    assert fwt.Config.from_env({}).max_tickers == 50
    assert fwt.Config.from_env({'WATCHED_TICKERS_MAX': '7'}).max_tickers == 7


def test_config_non_integer_raises():
    with pytest.raises(ValueError):
        fwt.Config.from_env({'WATCHED_TICKERS_MAX': 'x'})


def test_set_read_passes_sql_params_and_timeout():
    q = _Query(_set_frame(['AAA'], 1))
    fwt.read_watched_set(q, fmd.TICKERS, 50)
    assert q.calls == [(fwt.WATCHED_SET_SQL,
                        {'limit': 50, 'exclude': list(fmd.TICKERS)},
                        fwt._SET_QUERY_TIMEOUT_S)]


def test_set_read_overflow_is_exact():
    names = [f'T{i}' for i in range(50)]
    ws = fwt.read_watched_set(_Query(_set_frame(names, 60)), fmd.TICKERS, 50)
    assert ws.tickers == names
    assert ws.eligible_total == 60
    assert ws.overflow == 10
    ws = fwt.read_watched_set(_Query(_set_frame(names, 51)), fmd.TICKERS, 50)
    assert ws.overflow == 1


def test_set_read_normalises_tickers():
    ws = fwt.read_watched_set(_Query(_set_frame([' aapl '], 1)), [], 50)
    assert ws.tickers == ['AAPL']


def test_set_read_empty_frame_is_a_legitimate_zero():
    ws = fwt.read_watched_set(
        _Query(pd.DataFrame({'ticker': [], 'eligible_total': []})), [], 50)
    assert ws.tickers == [] and ws.eligible_total == 0 and ws.overflow == 0


def test_set_read_failure_is_set_read_error():
    with pytest.raises(fwt.SetReadError):
        fwt.read_watched_set(_Query(exc=RuntimeError('db down')), [], 50)


@pytest.mark.parametrize('frame', [
    pd.DataFrame({'ticker': [None], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': [float('nan')], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': [5], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': ['AAA']}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': [None]}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': ['many']}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': [1.5]}),
])
def test_set_read_malformed_frame_is_set_read_error(frame):
    with pytest.raises(fwt.SetReadError):
        fwt.read_watched_set(_Query(frame), [], 50)


def test_dedup_second_guard_order_preserving():
    assert fwt.dedup(['aapl ', 'AAPL', 'SPY'], fmd.TICKERS) == ['AAPL']
    assert fwt.dedup(['B', 'A', 'B'], []) == ['B', 'A']


def test_set_sql_source_scan():
    sql = fwt.WATCHED_SET_SQL
    assert fwt.WATCHED_DATA_SOURCE == 'av_watched_backfill'
    assert sql.count('user_watchlists') == 1
    assert re.search(r'EXISTS \(SELECT 1 FROM user_watchlists[^)]*\)', sql)
    assert not re.search(r'owner|uid|email', sql, re.I)
    assert sql.index('<> ALL(:exclude)') < sql.index('LIMIT')
    assert not re.search(r'\bwatchlists\b', _MODULE_SRC.read_text())


def test_resolve_session_holiday_is_none():
    assert fwt.resolve_session(date(2026, 11, 26)) is None  # Thanksgiving


def test_resolve_session_weekend_is_none():
    assert fwt.resolve_session(date(2026, 11, 14)) is None  # Saturday


def test_resolve_session_trading_day_returns_date():
    assert fwt.resolve_session(date(2026, 11, 13)) == date(2026, 11, 13)  # Friday


# ---------------------------------------------------------------------------
# Task 5: coverage, the job's own outputsize decision, the plan of pulls
# ---------------------------------------------------------------------------
TODAY = date(2026, 11, 13)   # a Friday session
WATCHED = 'av_watched_backfill'


def _cov(t, bars, max_date, boot=False):
    return fwt.Coverage(t, bars, max_date, boot)


def test_plan_no_rows_is_full_with_watched_stamp():
    plan = fwt.plan_pulls({'NEW': _cov('NEW', 0, None)}, TODAY)
    assert plan == {('full', WATCHED): ['NEW']}


def test_plan_current_ticker_is_not_planned():
    assert fwt.plan_pulls({'CUR': _cov('CUR', 2000, TODAY)}, TODAY) == {}


def test_plan_bootstrapped_300_bars_current_is_not_planned():
    assert fwt.plan_pulls({'B': _cov('B', 300, TODAY, True)}, TODAY) == {}


def test_plan_bootstrapped_300_bars_two_sessions_behind_is_compact():
    plan = fwt.plan_pulls({'B': _cov('B', 300, date(2026, 11, 11), True)}, TODAY)
    assert plan == {('compact', WATCHED): ['B']}


def test_plan_bootstrapped_1800_bars_100_days_behind_is_full():
    plan = fwt.plan_pulls({'B': _cov('B', 1800, TODAY - pd.Timedelta(days=100), True)}, TODAY)
    assert plan == {('full', WATCHED): ['B']}


def test_plan_existing_orphan_keeps_its_stamp_and_pulls_full():
    plan = fwt.plan_pulls({'ORPH': _cov('ORPH', 300, date(2026, 11, 12))}, TODAY)
    assert plan == {('full', 'av_daily_backfill'): ['ORPH']}


def test_plan_future_dated_max_date_is_current_not_negative_staleness():
    future = date(2026, 11, 20)
    assert fwt._pick_watched_outputsize(300, future, True, TODAY) is None
    assert fwt._pick_watched_outputsize(1800, future, False, TODAY) is None
    assert fwt.plan_pulls({'F': _cov('F', 300, future, True)}, TODAY) == {}


def test_plan_null_max_date_with_rows_is_full():
    assert fwt._pick_watched_outputsize(1800, None, False, TODAY) == 'full'


def test_plan_groups_tickers_in_input_order_and_has_no_none_groups():
    covs = {'A': _cov('A', 0, None), 'B': _cov('B', 2000, TODAY),
            'C': _cov('C', 0, None)}
    plan = fwt.plan_pulls(covs, TODAY)
    assert plan == {('full', WATCHED): ['A', 'C']}


def test_stamp_for():
    assert fwt.stamp_for(_cov('A', 0, None)) == WATCHED
    assert fwt.stamp_for(_cov('A', 5, TODAY, True)) == WATCHED
    assert fwt.stamp_for(_cov('A', 5, TODAY, False)) == 'av_daily_backfill'


def test_pick_accepts_timestamp_and_nat_max_dates():
    assert fwt._pick_watched_outputsize(2000, pd.Timestamp('2026-11-13'), False, TODAY) is None
    assert fwt._pick_watched_outputsize(2000, pd.NaT, False, TODAY) == 'full'


def test_read_coverage_builds_strict_query_and_fills_absent_tickers():
    frame = pd.DataFrame({'ticker': ['AAA'], 'bar_count': [300],
                          'max_date': [date(2026, 11, 12)], 'bootstrapped': [True]})
    q = _Query(frame)
    out = fwt.read_coverage(['AAA', 'ZZZ'], query=q)
    assert q.calls == [(fwt.COVERAGE_SQL, {'kept': ['AAA', 'ZZZ']},
                        fwt._SET_QUERY_TIMEOUT_S)]
    assert out['AAA'] == fwt.Coverage('AAA', 300, date(2026, 11, 12), True)
    assert out['ZZZ'] == fwt.Coverage('ZZZ', 0, None, False)
    assert list(out) == ['AAA', 'ZZZ']


def test_read_coverage_default_reader_is_the_strict_one(monkeypatch):
    seen = []

    def strict(sql, params=None, timeout_s=None):
        seen.append(sql)
        return pd.DataFrame({'ticker': [], 'bar_count': [], 'max_date': [],
                             'bootstrapped': []})

    monkeypatch.setattr('gcp.database.query_to_dataframe_strict', strict)
    assert fwt.read_coverage(['A']) == {'A': fwt.Coverage('A', 0, None, False)}
    assert seen == [fwt.COVERAGE_SQL]


def test_read_coverage_failure_propagates():
    with pytest.raises(RuntimeError):
        fwt.read_coverage(['A'], query=_Query(exc=RuntimeError('db down')))


# ---------------------------------------------------------------------------
# Task 6: indicators where the session bar exists, then ticker info
# ---------------------------------------------------------------------------

def test_tickers_with_session_bar_strict_query_and_order():
    q = _Query(pd.DataFrame({'ticker': ['CCC', 'AAA']}))
    out = fwt.tickers_with_session_bar(['AAA', 'BBB', 'CCC'], date(2026, 11, 13), query=q)
    assert q.calls == [(fwt.SESSION_BAR_SQL,
                        {'fetch_date': date(2026, 11, 13), 'kept': ['AAA', 'BBB', 'CCC']},
                        fwt._SET_QUERY_TIMEOUT_S)]
    assert out == ['AAA', 'CCC']


def test_tickers_with_session_bar_failure_propagates():
    with pytest.raises(RuntimeError):
        fwt.tickers_with_session_bar(['A'], date(2026, 11, 13),
                                     query=_Query(exc=RuntimeError('db down')))


def test_compute_indicators_skips_ticker_without_session_bar(monkeypatch):
    calls, lp_calls = [], []
    monkeypatch.setattr(fmd_mod := fwt.fetch_market_data, 'read_level_params_for_run',
                        lambda tickers, d: lp_calls.append((list(tickers), d))
                        or {'AAA': 'LP_A', 'CCC': 'LP_C'})
    monkeypatch.setattr(fmd_mod, 'compute_and_upsert_daily_indicators',
                        lambda t, d, *, level_params: calls.append((t, d, level_params)))
    monkeypatch.setattr(fwt, 'tickers_with_session_bar',
                        lambda kept, d: [t for t in kept if t != 'BBB'])
    fwt.compute_indicators(['AAA', 'BBB', 'CCC'], date(2026, 11, 13))
    assert [c[0] for c in calls] == ['AAA', 'CCC']
    assert calls == [('AAA', '2026-11-13', 'LP_A'), ('CCC', '2026-11-13', 'LP_C')]
    assert lp_calls == [(['AAA', 'CCC'], '2026-11-13')]


def test_refresh_ticker_info_logs_and_continues(monkeypatch, caplog):
    seen = []

    def fake(t, max_age_days):
        seen.append((t, max_age_days))
        if t == 'BBB':
            raise RuntimeError('av down')

    monkeypatch.setattr('lib.ticker_info.get_ticker_info', fake)
    with caplog.at_level('WARNING'):
        fwt.refresh_ticker_info(['AAA', 'BBB', 'CCC'])
    assert seen == [('AAA', 30), ('BBB', 30), ('CCC', 30)]
    assert 'BBB' in caplog.text and 'av down' in caplog.text
