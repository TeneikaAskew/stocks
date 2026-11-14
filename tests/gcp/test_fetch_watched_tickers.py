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


@pytest.mark.parametrize('tickers', [None, []])
@pytest.mark.parametrize('kwargs', [
    {'data_source': 'av_watched_backfill'},
    {'outputsize': 'compact'},
    {'outputsize': 'full', 'data_source': 'av_watched_backfill'},
])
def test_run_backfill_keywords_without_tickers_raise(av_stub, monkeypatch, tickers, kwargs):
    """Without explicit tickers the keywords would apply to the whole earnings
    universe: refused before any target read or vendor call."""
    def no_targets():
        raise AssertionError('_backfill_targets must not be read')

    monkeypatch.setattr(fmd, '_backfill_targets', no_targets)
    with pytest.raises(ValueError, match='tickers'):
        fmd._run_backfill(tickers, **kwargs)
    assert av_stub.av_calls == [] and av_stub.frames == []


def test_run_backfill_defaults_without_tickers_still_read_targets(av_stub, monkeypatch):
    monkeypatch.setattr(fmd, '_backfill_targets', lambda: [('AAA', 0, None)])
    assert fmd._run_backfill() == 3
    assert fmd._run_backfill([], data_source='av_daily_backfill') == 3
    assert av_stub.av_calls == [('AAA', 'full'), ('AAA', 'full')]


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


@pytest.mark.parametrize('raw', ['0', '-3'])
def test_config_below_one_raises_naming_the_variable(raw):
    with pytest.raises(ValueError, match='WATCHED_TICKERS_MAX'):
        fwt.Config.from_env({'WATCHED_TICKERS_MAX': raw})


def test_config_one_is_valid():
    assert fwt.Config.from_env({'WATCHED_TICKERS_MAX': '1'}).max_tickers == 1


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


def test_set_read_differing_eligible_totals_is_set_read_error():
    frame = pd.DataFrame({'ticker': ['AAA', 'BBB'], 'eligible_total': [2, 3]})
    with pytest.raises(fwt.SetReadError, match='differs between rows'):
        fwt.read_watched_set(_Query(frame), [], 50)


@pytest.mark.parametrize('blank', ['', '   '])
def test_set_read_empty_string_ticker_is_set_read_error(blank):
    frame = pd.DataFrame({'ticker': ['AAA', blank], 'eligible_total': [2, 2]})
    with pytest.raises(fwt.SetReadError, match='null or non-string ticker'):
        fwt.read_watched_set(_Query(frame), [], 50)


def test_set_read_bool_eligible_total_is_set_read_error():
    frame = pd.DataFrame({'ticker': ['AAA'],
                          'eligible_total': pd.Series([True], dtype=object)})
    with pytest.raises(fwt.SetReadError, match='not an integer'):
        fwt.read_watched_set(_Query(frame), [], 50)


def test_dedup_second_guard_order_preserving():
    assert fwt.dedup(['aapl ', 'AAPL', 'SPY'], fmd.TICKERS) == ['AAPL']
    assert fwt.dedup(['B', 'A', 'B'], []) == ['B', 'A']


# done_when item 6: identifiers that would let a per-user row reach the job.
_FORBIDDEN_IDENTIFIERS = ('watchlists', 'watchlist_history', 'owner_uid',
                          'owner_email', 'user_id', 'email')


def _strip_comments(src: str) -> str:
    """``src`` with every ``#`` comment removed; strings and docstrings stay."""
    import io
    import tokenize
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type != tokenize.COMMENT]
    return tokenize.untokenize(toks)


def _select_list(sql: str) -> str:
    """The outer SELECT list of ``sql``, up to ``FROM watched_tickers``."""
    m = re.match(r'\s*SELECT\s+(.*?)\s+FROM\s+watched_tickers\b', sql, re.S | re.I)
    assert m, f'set SQL does not select from watched_tickers: {sql}'
    return m.group(1)


def _privacy_scan(src: str, sql: str) -> list[str]:
    """Every way ``src`` (the module text) and ``sql`` (its set query) break
    done_when item 6; an empty list means the module passes."""
    code = _strip_comments(src)
    out = [f'identifier {name!r} appears'
           for name in _FORBIDDEN_IDENTIFIERS
           if re.search(rf'\b{name}\b', code)]
    n = len(re.findall(r'\buser_watchlists\b', code))
    if n != 1:
        out.append(f'user_watchlists appears {n} times outside comments, not once')
    exists = re.search(r'EXISTS \(SELECT 1 FROM user_watchlists u WHERE [^()]*\)', sql)
    if sql.count('user_watchlists') != 1 or not exists:
        out.append('the set SQL names user_watchlists outside its EXISTS predicate')
    if n == 1 and exists and exists.group(0) not in code:
        out.append('the one user_watchlists outside comments is not the set SQL predicate')
    if len(re.findall(r'\bwatched_tickers\b', code)) != 1:
        out.append('watched_tickers is read outside the set SQL')
    items = [i.strip() for i in _select_list(sql).split(',')]
    for item in items:
        if item == 'w.ticker' or re.fullmatch(r'COUNT\(\*\) OVER \(\) AS eligible_total', item):
            continue
        out.append(f'the set SQL selects {item!r} from watched_tickers')
    return out


def test_set_sql_source_scan():
    sql = fwt.WATCHED_SET_SQL
    assert fwt.WATCHED_DATA_SOURCE == 'av_watched_backfill'
    assert sql.index('<> ALL(:exclude)') < sql.index('LIMIT')
    assert _privacy_scan(_MODULE_SRC.read_text(), sql) == []


@pytest.mark.parametrize('extra', [
    'OWNER_SQL = "SELECT owner_uid FROM user_watchlists WHERE ticker = :t"',
    'EMAILS = "SELECT email FROM users"',
    'HIST = "SELECT ticker FROM watchlist_history"',
    'X = "SELECT user_id FROM watchlists"',
    'OWNER = "SELECT owner_email FROM accounts"',
    'MORE = "SELECT w.ticker, w.created_at FROM watched_tickers w"',
])
def test_set_sql_source_scan_catches_a_later_owner_read(extra):
    """The scan fails when a read of per-user data is added anywhere."""
    src = _MODULE_SRC.read_text() + '\n' + extra + '\n'
    assert _privacy_scan(src, fwt.WATCHED_SET_SQL) != []


@pytest.mark.parametrize('sql', [
    fwt.WATCHED_SET_SQL.replace('SELECT w.ticker,', 'SELECT w.ticker, w.created_at,'),
    fwt.WATCHED_SET_SQL.replace('AND w.ticker <> ALL',
                                'AND w.ticker IN (SELECT ticker FROM user_watchlists) '
                                'AND w.ticker <> ALL'),
])
def test_set_sql_source_scan_catches_a_widened_set_query(sql):
    assert _privacy_scan(_MODULE_SRC.read_text(), sql) != []


def test_set_sql_source_scan_ignores_comments():
    src = _MODULE_SRC.read_text() + '\n# owner_uid and email from user_watchlists\n'
    assert _privacy_scan(src, fwt.WATCHED_SET_SQL) == []


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


@pytest.mark.parametrize('flag', [None, float('nan')])
def test_read_coverage_null_bootstrapped_is_false(flag):
    """bool_or over rows whose data_source is all NULL is NULL; pandas may
    hand it over as None or NaN, and either reads as not bootstrapped, so a
    legacy null-sourced orphan keeps the other writer's stamp."""
    frame = pd.DataFrame({'ticker': ['ORPH'], 'bar_count': [300],
                          'max_date': [date(2026, 11, 12)],
                          'bootstrapped': pd.Series([flag], dtype=object)})
    cov = fwt.read_coverage(['ORPH'], query=_Query(frame))['ORPH']
    assert cov.bootstrapped is False
    assert fwt.stamp_for(cov) == 'av_daily_backfill'


def test_read_coverage_float_column_with_nan_is_false():
    """A mixed column (one True, one NULL) arrives as object or float: the
    NULL row still reads False and the True row True."""
    frame = pd.DataFrame({'ticker': ['A', 'B'], 'bar_count': [300, 300],
                          'max_date': [date(2026, 11, 12)] * 2,
                          'bootstrapped': [1.0, float('nan')]})
    out = fwt.read_coverage(['A', 'B'], query=_Query(frame))
    assert out['A'].bootstrapped is True and out['B'].bootstrapped is False


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


def test_upsert_indicators_skips_ticker_without_session_bar(monkeypatch):
    calls, lp_calls = [], []
    monkeypatch.setattr(fmd_mod := fwt.fetch_market_data, 'read_level_params_for_run',
                        lambda tickers, d: lp_calls.append((list(tickers), d))
                        or {'AAA': 'LP_A', 'CCC': 'LP_C'})
    monkeypatch.setattr(fmd_mod, 'compute_and_upsert_daily_indicators',
                        lambda t, d, *, level_params: calls.append((t, d, level_params)))
    fwt.upsert_indicators(['AAA', 'BBB', 'CCC'], ['AAA', 'CCC'], date(2026, 11, 13))
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


# --- Task 7: per-ticker verification ---------------------------------------

from datetime import datetime, timedelta, timezone

_NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
_FETCH = date(2026, 11, 13)


def _verify_query(bars_rows, info_rows, exc_on=None):
    """A query seam answering the bars read and the info read by SQL text."""
    calls = []

    def q(sql, params=None, timeout_s=None):
        calls.append((sql, params, timeout_s))
        if exc_on == sql:
            raise RuntimeError('db down')
        if sql == fwt.VERIFY_BARS_SQL:
            return pd.DataFrame(bars_rows, columns=['ticker', 'close', 'atr_14', 'bar_count'])
        if sql == fwt.VERIFY_INFO_SQL:
            return pd.DataFrame(info_rows, columns=['ticker', 'updated_at'])
        raise AssertionError(sql)

    q.calls = calls
    return q


def test_verify_four_tickers_one_reason_each():
    fresh = pd.Timestamp(_NOW - timedelta(days=1))
    stale = pd.Timestamp(_NOW - timedelta(days=31))
    q = _verify_query(
        [('NOBAR', None, None, 300),      # null close -> bars
         ('NOATR', 10.0, None, 300),      # null atr, deep -> indicators
         ('STALE', 10.0, 1.0, 300),       # stale info
         ('GOOD', 10.0, 1.0, 300)],
        [('NOATR', fresh), ('STALE', stale), ('GOOD', fresh), ('NOBAR', stale)])
    v = fwt.verify_tickers(['NOBAR', 'NOATR', 'STALE', 'GOOD', 'MISSING'],
                           _FETCH, _NOW, query=q)
    assert v.failed == {'NOBAR': 'bars', 'NOATR': 'indicators',
                        'STALE': 'ticker_info', 'MISSING': 'bars'}
    assert v.too_short == []
    assert [c[0] for c in q.calls] == [fwt.VERIFY_BARS_SQL, fwt.VERIFY_INFO_SQL]
    assert q.calls[0][1] == {'fetch_date': _FETCH,
                             'kept': ['NOBAR', 'NOATR', 'STALE', 'GOOD', 'MISSING']}
    assert q.calls[0][2] == fwt._SET_QUERY_TIMEOUT_S


def test_verify_too_short_is_not_a_failure():
    fresh = pd.Timestamp(_NOW)
    q = _verify_query([('NEW', 5.0, None, 10)], [('NEW', fresh)])
    v = fwt.verify_tickers(['NEW'], _FETCH, _NOW, query=q)
    assert v.failed == {} and v.too_short == ['NEW']


def test_verify_too_short_with_missing_info_still_fails_info():
    q = _verify_query([('NEW', 5.0, None, 10)], [])
    v = fwt.verify_tickers(['NEW'], _FETCH, _NOW, query=q)
    assert v.failed == {'NEW': 'ticker_info'} and v.too_short == ['NEW']


@pytest.mark.parametrize('stamp', [
    pd.Timestamp('2026-11-13 12:00:00'),                      # naive, treated as UTC
    pd.Timestamp('2026-11-13 07:00:00', tz='America/New_York'),  # aware, other zone
])
def test_verify_updated_at_naive_or_aware_does_not_raise(stamp):
    q = _verify_query([('A', 1.0, 1.0, 300)], [('A', stamp)])
    assert fwt.verify_tickers(['A'], _FETCH, _NOW, query=q).failed == {}


def test_verify_naive_stale_updated_at_is_stale():
    q = _verify_query([('A', 1.0, 1.0, 300)], [('A', pd.Timestamp('2026-10-01 00:00:00'))])
    assert fwt.verify_tickers(['A'], _FETCH, _NOW, query=q).failed == {'A': 'ticker_info'}


def test_verify_null_updated_at_is_ticker_info_failure():
    q = _verify_query([('A', 1.0, 1.0, 300)], [('A', pd.NaT)])
    assert fwt.verify_tickers(['A'], _FETCH, _NOW, query=q).failed == {'A': 'ticker_info'}


@pytest.mark.parametrize('which', ['bars', 'info'])
def test_verify_failed_read_propagates(which):
    sql = fwt.VERIFY_BARS_SQL if which == 'bars' else fwt.VERIFY_INFO_SQL
    q = _verify_query([], [], exc_on=sql)
    with pytest.raises(RuntimeError):
        fwt.verify_tickers(['A'], _FETCH, _NOW, query=q)


# ---------------------------------------------------------------------------
# Task 8: run() and main(), end to end with mocks only at the Alpha Vantage
# (requests.get) and Cloud SQL (the strict query seam, upsert_dataframe,
# query_to_dataframe, execute_sql) boundaries.
# ---------------------------------------------------------------------------
import logging

_SESSION = date(2026, 11, 13)          # Friday, a session
_RUN_NOW = datetime(2026, 11, 14, 4, 45, tzinfo=timezone.utc)   # 23:45 ET


class _FakeDB:
    """In-memory market_data_daily + ticker_info behind the job's SQL texts."""

    def __init__(self, set_frame=None, set_exc=None):
        self.set_frame = set_frame
        self.set_exc = set_exc
        self.bars: dict[str, dict[date, dict]] = {}
        self.info: dict[str, datetime] = {}
        self.calls: list[str] = []
        self.params: list[dict] = []
        self.history_fail: set[str] = set()

    # the strict reader seam: query(sql, params, timeout_s=...)
    def __call__(self, sql, params=None, timeout_s=None):
        self.calls.append(sql)
        self.params.append(params)
        if sql == fwt.WATCHED_SET_SQL:
            if self.set_exc:
                raise self.set_exc
            return self.set_frame
        kept = list(params.get('kept', []))
        if sql == fwt.COVERAGE_SQL:
            rows = []
            for t in kept:
                rs = self.bars.get(t)
                if rs:
                    rows.append((t, len(rs), max(rs),
                                 any(r.get('data_source') == WATCHED for r in rs.values())))
            return pd.DataFrame(rows, columns=['ticker', 'bar_count', 'max_date', 'bootstrapped'])
        if sql == fwt.SESSION_BAR_SQL:
            d = params['fetch_date']
            return pd.DataFrame({'ticker': [t for t in kept
                                            if self._close(t, d) is not None]})
        if sql == fwt.VERIFY_BARS_SQL:
            d = params['fetch_date']
            rows = [(t, self._close(t, d), self.bars[t][d].get('atr_14'), len(self.bars[t]))
                    for t in kept if d in self.bars.get(t, {})]
            return pd.DataFrame(rows, columns=['ticker', 'close', 'atr_14', 'bar_count'])
        if sql == fwt.VERIFY_INFO_SQL:
            rows = [(t, pd.Timestamp(self.info[t])) for t in kept if t in self.info]
            return pd.DataFrame(rows, columns=['ticker', 'updated_at'])
        raise AssertionError(f'unexpected strict query: {sql}')

    def _close(self, t, d):
        r = self.bars.get(t, {}).get(d)
        if r is None or r.get('close') is None or pd.isna(r.get('close')):
            return None
        return r['close']

    def seed(self, ticker, n, end=_SESSION, source='av_daily_backfill'):
        for d in pd.bdate_range(end=end, periods=n).date:
            self.bars.setdefault(ticker, {})[d] = {
                'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0,
                'volume': 100, 'data_source': source}

    # upsert_dataframe(df, table, keys): merge on (ticker, date)
    def upsert(self, df, table, keys):
        assert table == 'market_data_daily' and keys == ['ticker', 'date']
        for rec in df.to_dict('records'):
            t, d = rec.pop('ticker'), pd.Timestamp(rec.pop('date')).date()
            self.bars.setdefault(t, {}).setdefault(d, {}).update(rec)

    # compute_and_upsert_daily_indicators' history read (query_to_dataframe)
    def history(self, sql, params=None):
        if 'FROM market_data_daily' not in sql:
            return pd.DataFrame()   # intraday reads: none in this fake
        t = params['ticker']
        if t in self.history_fail:
            return pd.DataFrame()   # what the non-strict reader returns on a failed read
        cut = pd.Timestamp(params['fetch_date']).date()
        rows = sorted(((d, r) for d, r in self.bars.get(t, {}).items()
                       if d <= cut and r.get('close') is not None), reverse=True)[:250]
        return pd.DataFrame([{'date': d, 'Open': r['open'], 'High': r['high'],
                              'Low': r['low'], 'Close': r['close'], 'Volume': r['volume']}
                             for d, r in rows])


def _av_json(n, end=_SESSION):
    ts = {}
    for i, d in enumerate(pd.bdate_range(end=end, periods=n).date):
        px = 10.0 + i * 0.1
        ts[d.isoformat()] = {'1. open': str(px), '2. high': str(px + 0.5),
                             '3. low': str(px - 0.5), '4. close': str(px + 0.1),
                             '6. volume': '1000'}
    return {'Time Series (Daily)': ts}


@pytest.fixture
def job(monkeypatch):
    """The job wired to a fake Cloud SQL and a fake Alpha Vantage HTTP layer.

    rec.av_calls: (ticker, outputsize) for every _av_get_full_daily_series call;
    rec.av_raise / rec.av_empty: tickers whose HTTP call raises / returns no series;
    rec.av_bars: bars per pull (default 30); rec.runs: record_job_run calls;
    rec.indicator_calls: tickers compute_and_upsert_daily_indicators ran for;
    rec.info_fail: tickers whose ticker_info execute_sql raises.
    """
    db = _FakeDB()
    rec = SimpleNamespace(db=db, av_calls=[], av_raise=set(), av_empty=set(),
                          av_bars=30, runs=[], record_result=True,
                          indicator_calls=[], info_fail=set(), upserts=0)

    real_av = fmd._av_get_full_daily_series

    def av_spy(ticker, api_key, outputsize):
        rec.av_calls.append((ticker, outputsize))
        return real_av(ticker, api_key, outputsize)

    def fake_get(url, params=None, timeout=None):
        sym = params['symbol']
        if sym in rec.av_raise:
            raise ConnectionError(f'AV down for {sym}')
        body = {} if sym in rec.av_empty else _av_json(rec.av_bars)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

    def upsert(df, table, keys):
        rec.upserts += 1
        db.upsert(df, table, keys)

    real_ind = fmd.compute_and_upsert_daily_indicators

    def ind_spy(t, d, *, level_params=None):
        rec.indicator_calls.append((t, d))
        return real_ind(t, d, level_params=level_params)

    def execute_sql(sql, params=None):
        assert 'INSERT INTO ticker_info' in sql
        t = params['ticker']
        if t in rec.info_fail:
            raise RuntimeError('ticker_info write failed')
        db.info[t] = _RUN_NOW
        return 1

    def record(job_name, started_at, status, **kw):
        rec.runs.append(dict(job_name=job_name, started_at=started_at, status=status, **kw))
        return rec.record_result

    monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake-key')
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '0')
    monkeypatch.setattr(fmd, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(fmd, '_av_get_full_daily_series', av_spy)
    monkeypatch.setattr(fmd.requests, 'get', fake_get)
    monkeypatch.setattr('gcp.database.upsert_dataframe', upsert)
    monkeypatch.setattr('gcp.database.query_to_dataframe', db.history)
    monkeypatch.setattr('gcp.database.execute_sql', execute_sql)
    monkeypatch.setattr(fmd, 'compute_and_upsert_daily_indicators', ind_spy)
    monkeypatch.setattr(fmd, 'read_level_params_for_run', lambda tickers, d: {})
    import lib.ticker_info as ti
    monkeypatch.setattr(ti, '_cloud_sql_available', lambda: True)
    monkeypatch.setattr(ti, '_read_from_cloud_sql', lambda t: None)
    monkeypatch.setattr(ti, '_load_local_cache', dict)
    monkeypatch.setattr(ti, '_merge_into_local_cache', lambda *a, **k: None)
    monkeypatch.setattr(ti, 'fetch_ticker_overview', lambda t: {'Symbol': t, 'Name': t})
    monkeypatch.setattr(fwt, 'record_job_run', record)
    return rec


def _run(rec, tickers, eligible_total=None, *, max_tickers=50, today=_SESSION):
    rec.db.set_frame = _set_frame(tickers, len(tickers) if eligible_total is None
                                  else eligible_total)
    return fwt.run(fwt.Config(max_tickers=max_tickers), today=today, now=_RUN_NOW,
                   query=rec.db)


def _only_run(rec):
    assert len(rec.runs) == 1, rec.runs
    r = rec.runs[0]
    assert r['job_name'] == 'fetch-watched-tickers'
    assert r['started_at'] == _RUN_NOW
    return r


def test_run_set_read_failure_records_error_and_makes_no_vendor_call(job):
    job.db.set_exc = RuntimeError('db down')
    rc = fwt.run(fwt.Config(), today=_SESSION, now=_RUN_NOW, query=job.db)
    assert rc == 2
    r = _only_run(job)
    assert r['status'] == 'error' and r['note'].startswith('set_read:')
    assert job.av_calls == [] and job.upserts == 0
    assert job.db.calls == [fwt.WATCHED_SET_SQL]


def test_run_empty_set_is_success_with_zero_items(job):
    rc = _run(job, [])
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success' and r['items_total'] == 0
    assert job.av_calls == [] and job.upserts == 0
    assert job.db.calls == [fwt.WATCHED_SET_SQL]   # no ANY(:kept) read on []


def test_run_fifty_of_sixty_records_overflow_and_processes_fifty(job, caplog):
    names = [f'W{i:02d}' for i in range(50)]
    with caplog.at_level(logging.INFO):
        rc = _run(job, names, eligible_total=60)
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success'
    assert r['items_total'] == 50 and r['items_processed'] == 50 and r['items_failed'] == 0
    assert r['note'].startswith('overflow=10')
    assert [t for t, _ in job.av_calls] == names
    assert all(size == 'full' for _, size in job.av_calls)
    assert r['rows_written'] == 50 * 30
    assert any(rr.levelno == logging.ERROR and 'overflow=10' in rr.getMessage()
               for rr in caplog.records)
    assert 'ticker=W00 step=bars processed=1/50' in caplog.text
    assert 'ticker=W49 step=verify processed=50/50' in caplog.text


def test_run_one_vendor_failure_is_counted_and_others_proceed(job):
    job.av_raise = {'BBB'}
    rc = _run(job, ['AAA', 'BBB', 'CCC'])
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success'
    assert (r['items_total'], r['items_processed'], r['items_failed']) == (3, 2, 1)
    assert r['note'] == 'failed=BBB:bars'
    assert [t for t, _ in job.av_calls] == ['AAA', 'BBB', 'CCC']
    assert [t for t, _ in job.indicator_calls] == ['AAA', 'CCC']


def test_run_every_ticker_failing_is_error_and_exit_one(job):
    job.av_raise = {'AAA', 'BBB'}
    rc = _run(job, ['AAA', 'BBB'])
    assert rc == 1
    r = _only_run(job)
    assert r['status'] == 'error'
    assert (r['items_total'], r['items_processed'], r['items_failed']) == (2, 0, 2)
    assert r['note'] == 'failed=AAA:bars,BBB:bars'
    assert job.indicator_calls == []


def test_run_two_groups_sum_rows_written(job, monkeypatch):
    job.db.seed('BOOT', 300, end=date(2026, 11, 10), source=WATCHED)  # compact
    calls = []

    def fake_backfill(tickers, *, outputsize, data_source):
        calls.append((list(tickers), outputsize, data_source))
        n = {'full': 12, 'compact': 3}[outputsize]
        for t in tickers:   # the pull lands the session's bars
            job.db.seed(t, n, source=data_source)
        return n

    monkeypatch.setattr(fmd, '_run_backfill', fake_backfill)
    rc = _run(job, ['NEW', 'BOOT'])
    r = _only_run(job)
    assert sorted(calls) == sorted([(['NEW'], 'full', WATCHED), (['BOOT'], 'compact', WATCHED)])
    assert r['rows_written'] == 15
    assert rc == 0
    assert r['status'] == 'success' and r['items_failed'] == 0


@pytest.mark.parametrize('day', [date(2026, 11, 26), date(2026, 11, 14)])  # Thanksgiving, Saturday
def test_run_non_session_records_success_and_touches_nothing(job, day):
    rc = _run(job, ['AAA'], today=day)
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success' and r['items_total'] == 0 and r['note'] == 'non_session'
    assert job.db.calls == []              # no set query
    assert job.av_calls == [] and job.upserts == 0 and job.indicator_calls == []


def test_run_mixed_set_verification_end_to_end(job):
    """done_when[2]: four tickers get session bars; the indicator history read
    fails for one, the vendor returns nothing for another and execute_sql
    raises for a third's ticker_info upsert."""
    job.db.history_fail = {'NOIND'}
    job.av_empty = {'NOBARS'}
    job.info_fail = {'NOINFO'}
    rc = _run(job, ['GOOD', 'NOIND', 'NOBARS', 'NOINFO'])
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success'
    assert (r['items_total'], r['items_processed'], r['items_failed']) == (4, 1, 3)
    assert r['note'] == 'failed=NOIND:indicators,NOBARS:bars,NOINFO:ticker_info'
    # the ticker whose fetch returned nothing gets no indicator call and no session row
    assert 'NOBARS' not in [t for t, _ in job.indicator_calls]
    assert _SESSION not in job.db.bars.get('NOBARS', {})
    assert job.db.bars['GOOD'][_SESSION]['atr_14'] is not None


def test_run_too_short_is_noted_not_failed(job):
    job.av_bars = 10
    rc = _run(job, ['NEW'])
    assert rc == 0
    r = _only_run(job)
    assert r['status'] == 'success' and r['items_failed'] == 0
    assert r['note'] == 'too_short=[NEW]'


@pytest.mark.parametrize('phase,target', [
    ('coverage', 'read_coverage'),
    ('backfill', None),
    ('session_bars', 'tickers_with_session_bar'),
    ('indicators', 'read_level_params_for_run'),
    ('ticker_info', 'refresh_ticker_info'),
    ('verify', 'verify_tickers'),
])
def test_run_failure_after_the_set_read_records_the_phase(job, monkeypatch, caplog, phase, target):
    def boom(*a, **k):
        raise RuntimeError(f'{phase} broke')

    if phase == 'backfill':
        monkeypatch.delenv('ALPHA_VANTAGE_API_KEY')   # _run_backfill raises RuntimeError
    elif target == 'read_level_params_for_run':
        monkeypatch.setattr(fmd, target, boom)
    else:
        monkeypatch.setattr(fwt, target, boom)
    with caplog.at_level(logging.ERROR):
        rc = _run(job, ['AAA', 'BBB'])
    assert rc == 2
    r = _only_run(job)
    assert r['status'] == 'error' and r['items_total'] == 2
    assert r['note'].startswith(f'{phase}: ')
    assert any(rr.levelno == logging.ERROR for rr in caplog.records)


def test_run_phase_error_keeps_overflow_and_rows_written(job, monkeypatch):
    """An indicators failure after the bars were written, with 60 of 61
    eligible tickers served: the error row says overflow=1 and counts the
    rows the backfill already wrote."""
    def boom(*a, **k):
        raise RuntimeError('levels unavailable')

    monkeypatch.setattr(fmd, 'read_level_params_for_run', boom)
    names = [f'W{i:02d}' for i in range(60)]
    rc = _run(job, names, eligible_total=61, max_tickers=60)
    assert rc == 2
    r = _only_run(job)
    assert r['status'] == 'error' and r['items_total'] == 60
    assert r['note'].startswith('indicators: ')
    assert 'overflow=1' in r['note'].split('; ')
    assert r['rows_written'] == 60 * 30
    assert job.upserts == 60


def test_run_phase_error_before_any_write_records_zero_rows_and_no_overflow(job, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('coverage read broke')

    monkeypatch.setattr(fwt, 'read_coverage', boom)
    assert _run(job, ['AAA']) == 2
    r = _only_run(job)
    assert r['rows_written'] == 0
    assert r['note'] == 'coverage: coverage read broke'


def test_run_record_failure_logs_error_and_keeps_exit_code(job, caplog):
    job.record_result = False
    with caplog.at_level(logging.ERROR):
        assert _run(job, []) == 0
    assert any(rr.levelno == logging.ERROR and 'job_runs write failed' in rr.getMessage()
               for rr in caplog.records)
    job.runs.clear()
    job.av_raise = {'AAA'}
    with caplog.at_level(logging.ERROR):
        assert _run(job, ['AAA']) == 1


def test_run_never_calls_post_fetch_rows_check(job, monkeypatch):
    """The job verifies every ticker itself; the default list's row check
    (which returns unchecked without SPY, IWM or QQQ) is never called."""
    calls = []
    monkeypatch.setattr(fmd, '_verify_post_fetch_rows',
                        lambda *a, **k: calls.append((a, k)))
    assert _run(job, ['AAA', 'BBB']) == 0
    assert _only_run(job)['status'] == 'success'
    assert calls == []


def test_run_dedup_second_guard_drops_static_ticker(job):
    rc = _run(job, ['SPY', 'aaa', 'AAA'], eligible_total=3)
    assert rc == 0
    r = _only_run(job)
    assert r['items_total'] == 1
    assert [t for t, _ in job.av_calls] == ['AAA']


def test_run_set_read_uses_static_exclusion_and_ceiling(job):
    _run(job, ['AAA'], max_tickers=7)
    assert job.db.calls[0] == fwt.WATCHED_SET_SQL
    assert job.db.params[0] == {'limit': 7, 'exclude': list(fmd.TICKERS)}
    assert job.db.calls.count(fwt.WATCHED_SET_SQL) == 1


def test_main_non_integer_ceiling_records_config_error(monkeypatch):
    runs, av = [], []
    monkeypatch.setenv('WATCHED_TICKERS_MAX', 'x')
    monkeypatch.setattr(fwt, 'record_job_run',
                        lambda *a, **k: runs.append((a, k)) or True)
    monkeypatch.setattr(fmd, '_av_get_full_daily_series',
                        lambda *a, **k: av.append(a) or pd.DataFrame())
    assert fwt.main() == 2
    assert len(runs) == 1
    (job_name, _started, status), kw = runs[0]
    assert job_name == 'fetch-watched-tickers' and status == 'error'
    assert kw['items_total'] == 0 and kw['note'].startswith('config:')
    assert av == []


@pytest.mark.parametrize('raw', ['0', '-3'])
def test_main_ceiling_below_one_records_config_error(monkeypatch, raw):
    runs, av, set_reads = [], [], []
    monkeypatch.setenv('WATCHED_TICKERS_MAX', raw)
    monkeypatch.setattr(fwt, 'record_job_run',
                        lambda *a, **k: runs.append((a, k)) or True)
    monkeypatch.setattr(fwt, 'read_watched_set',
                        lambda *a, **k: set_reads.append(a) or fwt.WatchedSet([], 0, 0))
    monkeypatch.setattr(fmd, '_av_get_full_daily_series',
                        lambda *a, **k: av.append(a) or pd.DataFrame())
    monkeypatch.setattr(fwt, 'market_today', lambda: _SESSION)
    assert fwt.main() == 2
    assert len(runs) == 1
    (job_name, _started, status), kw = runs[0]
    assert job_name == 'fetch-watched-tickers' and status == 'error'
    assert kw['items_total'] == 0
    assert kw['note'].startswith('config:') and 'WATCHED_TICKERS_MAX' in kw['note']
    assert set_reads == [] and av == []


def test_main_ceiling_of_one_runs(monkeypatch):
    seen = []
    monkeypatch.setenv('WATCHED_TICKERS_MAX', '1')
    monkeypatch.setattr(fwt, 'market_today', lambda: _SESSION)
    monkeypatch.setattr(fwt, 'run', lambda cfg, *, today, now: seen.append(cfg) or 0)
    assert fwt.main() == 0
    assert seen == [fwt.Config(1)]


def test_main_runs_with_market_today_and_started(monkeypatch):
    seen = []
    monkeypatch.delenv('WATCHED_TICKERS_MAX', raising=False)
    monkeypatch.setattr(fwt, 'market_today', lambda: _SESSION)
    monkeypatch.setattr(fwt, 'run', lambda cfg, *, today, now: seen.append((cfg, today, now)) or 0)
    assert fwt.main() == 0
    cfg, today, now = seen[0]
    assert cfg == fwt.Config(50) and today == _SESSION and now.tzinfo is not None
