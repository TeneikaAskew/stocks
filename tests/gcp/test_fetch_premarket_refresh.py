"""Unit tests for ``gcp/fetchers/fetch_premarket_refresh.py``.

The pre-market refresh job is the link that lets the 8:45 AM brief see
today's gap_pct. Tests cover universe selection, the UPSERT idempotency,
and graceful degradation when AV / Cloud SQL aren't reachable.

Live AV calls are stubbed via monkeypatch — see test_fetch_market_data*
for the AV integration tests.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# resolve_universe — priority ordering + filter on options_volume
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_db(monkeypatch):
    """Stub out gcp.database.is_cloud_sql_configured + query_to_dataframe.

    Returns a setter that lets each test feed a list of (sql, params, df)
    triples — the stubbed query_to_dataframe matches by which columns are
    in the SQL so we can route the watchlist call vs. the earnings calls
    independently.
    """
    from gcp import database

    captured = {"calls": []}

    routes = {}  # match-key → df

    def install_route(match_substring: str, df: pd.DataFrame):
        routes[match_substring] = df

    def fake_query(sql, params=None):
        captured["calls"].append((sql, params))
        for key, df in routes.items():
            if key in sql:
                return df.copy() if df is not None else pd.DataFrame()
        return pd.DataFrame()

    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "query_to_dataframe", fake_query)

    return install_route, captured


def test_resolve_universe_includes_watchlist_first(stub_db, monkeypatch):
    install, _ = stub_db
    # Today's earnings reporters
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': ['AMZN', 'MSFT'],
                          'opt_vol': [200_000, 100_000],
                          'mcap': [1.3e12, 3e12]}))
    # Yesterday's AMC reporters
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': ['SBUX']}))

    # Stub the watchlist
    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: ['SPY', 'QQQ', 'IWM'])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    universe = resolve_universe(date(2026, 4, 30), max_tickers=50)

    # Watchlist + today's earnings + yesterday's AMC, all unique
    assert set(universe) == {'SPY', 'QQQ', 'IWM', 'AMZN', 'MSFT', 'SBUX'}


def test_resolve_universe_caps_with_watchlist_priority(stub_db, monkeypatch):
    """When max_tickers is hit, watchlist tickers (priority 0) survive
    and earnings names (priority 1+) get trimmed."""
    install, _ = stub_db
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': [f'EARN{i}' for i in range(20)],
                          'opt_vol': [10_000] * 20,
                          'mcap': [1e9] * 20}))
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': []}))

    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: ['SPY', 'QQQ', 'IWM', 'SPX'])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    universe = resolve_universe(date(2026, 4, 30), max_tickers=8)

    # All 4 watchlist tickers must survive the trim
    assert {'SPY', 'QQQ', 'IWM', 'SPX'}.issubset(set(universe))
    assert len(universe) == 8


def test_resolve_universe_no_cloud_sql_returns_empty(monkeypatch):
    """No DB → empty list, not a crash."""
    from gcp import database
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: False)

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    assert resolve_universe(date(2026, 4, 30)) == []


def test_resolve_universe_walks_back_over_weekend(stub_db, monkeypatch):
    """If target_date is Monday, yesterday's-AMC lookup should hit the
    most recent weekday (Friday), not Sunday."""
    install, captured = stub_db
    install("MAX(options_volume) AS opt_vol",
            pd.DataFrame({'ticker': [], 'opt_vol': [], 'mcap': []}))
    install("SELECT DISTINCT ticker FROM earnings_calendar",
            pd.DataFrame({'ticker': []}))

    import gcp.fetchers._watchlist as wl
    monkeypatch.setattr(wl, "load_watchlist", lambda: [])

    from gcp.fetchers.fetch_premarket_refresh import resolve_universe
    # Monday 2026-05-04
    resolve_universe(date(2026, 5, 4), max_tickers=10)

    # Inspect AMC query params — should be 2026-05-01 (Friday), not 2026-05-03 (Sunday)
    amc_call = next((c for c in captured["calls"]
                     if "SELECT DISTINCT ticker FROM earnings_calendar" in c[0]), None)
    assert amc_call is not None
    assert amc_call[1]['d'] == date(2026, 5, 1)


# ──────────────────────────────────────────────────────────────────────
# compute_premarket_for_ticker — null-safe
# ──────────────────────────────────────────────────────────────────────


def test_compute_returns_none_when_no_intraday_bars(monkeypatch):
    """AV intraday returned 0 bars (early run, weekend, holiday) → None."""
    from gcp.fetchers import fetch_market_data
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: pd.DataFrame())

    from gcp.fetchers.fetch_premarket_refresh import compute_premarket_for_ticker
    assert compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key") is None


def test_compute_returns_none_when_no_premarket_window(monkeypatch):
    """Bars exist but none fall in the 4am-9:30am pre-market window —
    e.g. only 10am-4pm regular session bars. → None."""
    from gcp.fetchers import fetch_market_data
    # Single regular-hours bar at 10:00am ET
    bars = pd.DataFrame(
        {'Open': [180.0], 'High': [181.0], 'Low': [179.0],
         'Close': [180.5], 'Volume': [1_000_000]},
        index=pd.DatetimeIndex(['2026-04-30 10:00:00']),
    )
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: bars)
    # No prev_close lookup needed for this test — short-circuit it
    from gcp.fetchers import fetch_premarket_refresh as fpr
    monkeypatch.setattr(fpr, "_prior_session_from_db", lambda tk, d: {"close": 178.0, "atr_14": 10.0})

    result = fpr.compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key")
    assert result is None


def test_compute_returns_metrics_when_premarket_bars_present(monkeypatch):
    """Pre-market bars present → dict with pre_high/low/vwap/volume/gap_pct."""
    bars = pd.DataFrame(
        {
            'Open': [180.0, 182.0, 183.0],
            'High': [181.0, 182.5, 184.0],
            'Low':  [179.5, 181.5, 182.0],
            'Close': [180.5, 182.0, 183.5],
            'Volume': [10_000, 8_000, 12_000],
        },
        index=pd.DatetimeIndex([
            '2026-04-30 04:00:00',
            '2026-04-30 06:30:00',
            '2026-04-30 08:15:00',
        ]),
    )
    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_premarket_refresh as fpr
    monkeypatch.setattr(fetch_market_data, "fetch_minute_data",
                        lambda tk, d, k: bars)
    monkeypatch.setattr(fpr, "_prior_session_from_db", lambda tk, d: {"close": 175.0, "atr_14": 10.0})

    result = fpr.compute_premarket_for_ticker("AAPL", date(2026, 4, 30), "key")
    assert result is not None
    assert result['ticker'] == 'AAPL'
    assert result['date'] == date(2026, 4, 30)
    # FEAT-PLAYBOOK-001 B7: 184.0 and 179.5 are one bar's lone wick each, so
    # the extremes are the highest and lowest open or close (the 08:15 close
    # and the 04:00 open), which lie beyond the second bar high and low.
    assert result['pre_high'] == 183.5
    assert result['pre_low'] == 180.0
    # gap_pct = (180.0 - 175.0) / 175.0 * 100 ≈ +2.86%
    assert result['gap_pct'] is not None
    assert abs(result['gap_pct'] - 2.857) < 0.01


# ──────────────────────────────────────────────────────────────────────
# upsert_premarket — filter rows with no useful pre-market data
# ──────────────────────────────────────────────────────────────────────


class TestUpsertFiltering:
    """Regression: AV occasionally returns no pre-market bars for a
    ticker (early run, weekend, extended-hours not enabled). Without
    this filter, upsert would INSERT a row with all NULLs, which
    crashed the morning brief's compute_current_levels."""

    def test_skips_rows_with_all_pre_fields_null(self, monkeypatch):
        """Row where every pre_* field is None must NOT trigger INSERT."""
        from gcp.fetchers import fetch_premarket_refresh as fpr

        # Stub get_engine so we can detect any execute() call
        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        n = fpr.upsert_premarket([
            {'ticker': 'EMPTY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': None},
        ])
        assert n == 0
        assert executed == [], "no INSERT should fire for all-null row"

    def test_keeps_rows_with_at_least_one_pre_field(self, monkeypatch):
        from gcp.fetchers import fetch_premarket_refresh as fpr

        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        # Row with only gap_pct → keep
        n = fpr.upsert_premarket([
            {'ticker': 'GAP_ONLY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': 0.42},
        ])
        assert n == 1
        assert len(executed) == 1
        assert executed[0]['ticker'] == 'GAP_ONLY'

    def test_mixed_useful_and_empty_rows(self, monkeypatch):
        """Useful rows persist; empty ones are silently dropped."""
        from gcp.fetchers import fetch_premarket_refresh as fpr

        executed = []
        class FakeConn:
            def execute(self, sql, params):
                executed.append(params)
        class FakeBegin:
            def __enter__(self): return FakeConn()
            def __exit__(self, *a): return False
        class FakeEngine:
            def begin(self): return FakeBegin()
        from gcp import database
        monkeypatch.setattr(database, "get_engine", lambda: FakeEngine())

        n = fpr.upsert_premarket([
            {'ticker': 'GOOD', 'date': date(2026, 4, 30),
             'pre_high': 180.0, 'pre_low': 178.0, 'pre_vwap': 179.0,
             'pre_volume': 100, 'gap_pct': 1.5},
            {'ticker': 'EMPTY', 'date': date(2026, 4, 30),
             'pre_high': None, 'pre_low': None, 'pre_vwap': None,
             'pre_volume': None, 'gap_pct': None},
        ])
        assert n == 1
        assert {e['ticker'] for e in executed} == {'GOOD'}


# ──────────────────────────────────────────────────────────────────────
# The newest premarket bar per ticker (FEAT-PLAYBOOK-001, the late slot)
# ──────────────────────────────────────────────────────────────────────


def _minute_bars(first: str, last: str) -> pd.DataFrame:
    """One-minute bars of 2026-04-30 from `first` through `last`, in the
    vendor's naive Eastern wall time."""
    idx = pd.date_range(f'2026-04-30 {first}', f'2026-04-30 {last}', freq='1min')
    return pd.DataFrame({'Open': 180.0, 'High': 181.0, 'Low': 179.5, 'Close': 180.5,
                         'Volume': 1_000}, index=idx)


def test_compute_logs_the_newest_premarket_bar(monkeypatch, caplog):
    """How late the vendor's newest bar is at the fetch is what the late
    brief's levels depend on, and nothing recorded it. One INFO record per
    ticker names the premarket bar count, the newest premarket bar (the
    vendor's own Eastern wall time) and the fetch time in America/New_York.
    Nothing is stored."""
    import logging
    from datetime import datetime, timezone

    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_premarket_refresh as fpr

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 30, 13, 20, 41, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(fpr, 'datetime', FrozenDatetime)
    monkeypatch.setattr(fpr, '_prior_session_from_db',
                        lambda tk, d: {'close': 178.0, 'atr_14': 10.0})
    frames = {}
    monkeypatch.setattr(fetch_market_data, 'fetch_minute_data', lambda tk, d, k: frames['bars'])

    def record():     # the INFO records of the module that name a bar time
        return [r.getMessage() for r in caplog.records
                if r.name == 'gcp.fetchers.fetch_premarket_refresh'
                and r.levelno == logging.INFO and 'newest_bar=' in r.getMessage()]

    with caplog.at_level(logging.INFO, logger='gcp.fetchers.fetch_premarket_refresh'):
        # 04:00 through 09:19: 320 premarket bars
        frames['bars'] = _minute_bars('04:00', '09:19')
        snapshot = fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key')
        assert snapshot is not None
        (line,) = record()
        assert 'AAPL' in line and 'bars=320' in line and 'newest_bar=09:19 ET' in line
        assert 'fetched_at=09:20:41 ET' in line
        # the record stores nothing: the snapshot is what it was
        assert snapshot['pre_fetched_at'] == datetime(2026, 4, 30, 13, 20, 41, tzinfo=timezone.utc)
        assert not any('newest' in key for key in snapshot)

        # 04:00 through 15:59: the newest premarket bar is 09:29, not the last bar of the day
        caplog.clear()
        frames['bars'] = _minute_bars('04:00', '15:59')
        assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is not None
        (line,) = record()
        assert 'bars=330' in line and 'newest_bar=09:29 ET' in line

        # one bar at 10:00: no premarket bar, no record
        caplog.clear()
        frames['bars'] = _minute_bars('10:00', '10:00')
        assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is None
        assert record() == []


@pytest.mark.parametrize('index,newest', [
    (pd.DatetimeIndex(['2026-04-30 03:59:00', '2026-04-30 04:00:00', '2026-04-30 09:29:00',
                       '2026-04-30 09:30:00']), '2026-04-30 09:29:00'),
    # a zone-aware index is read in Eastern: 13:19Z is 09:19 EDT
    (pd.DatetimeIndex(['2026-04-30 08:00:00', '2026-04-30 13:19:00', '2026-04-30 13:30:00'],
                      tz='UTC'), '2026-04-30 09:19:00'),
    (pd.DatetimeIndex(['2026-04-30 03:59:00', '2026-04-30 09:30:00']), None),
    (pd.DatetimeIndex([]), None),
])
def test_newest_premarket_bar(index, newest):
    from gcp.fetchers import fetch_premarket_refresh as fpr

    got = fpr._newest_premarket_bar(index)
    if newest is None:
        assert got is None
    else:
        assert got.strftime('%Y-%m-%d %H:%M:%S') == newest


# ──────────────────────────────────────────────────────────────────────
# The premarket bars as read (FEAT-DATA-001,
# docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md)
# ──────────────────────────────────────────────────────────────────────

AS_READ_SESSION = date(2026, 11, 16)


def _as_read_fetched_at():
    from datetime import datetime, timezone
    return datetime(2026, 11, 16, 13, 20, 1, 123456, tzinfo=timezone.utc)


def _r1_bars(ticker: str = 'SPY') -> pd.DataFrame:
    """The spec's four bars (Design 2) as fetch_minute_data returns them."""
    df = pd.DataFrame(
        {'Open': [752.5, 752.4, 752.3, 752.2], 'High': [752.6, 752.5, 752.4, 752.3],
         'Low': [752.4, 752.3, 752.02, 752.1], 'Close': [752.5, 752.4, 752.3, 752.2],
         'Volume': pd.Series([500, 300, 968, 10], dtype='int64').to_numpy()},
        index=pd.DatetimeIndex(['2026-11-16 04:00:00', '2026-11-16 04:01:00',
                                '2026-11-16 04:02:00', '2026-11-16 04:03:00'], name='timestamp'))
    df['ticker'] = ticker
    return df


def _as_reads(tickers=('SPY', 'QQQ', 'IWM'), fetched_at=None) -> dict:
    from gcp.fetchers.fetch_market_data import minute_bars_request
    from gcp.fetchers.premarket_as_read import AsRead
    at = fetched_at or _as_read_fetched_at()
    return {t: AsRead(_r1_bars(t), at, minute_bars_request(t, '2026-11')) for t in tickers}


def _as_read_name(ticker: str, fetched_at=None) -> str:
    from gcp.fetchers.premarket_as_read import object_name
    return object_name(ticker, AS_READ_SESSION, fetched_at or _as_read_fetched_at())


def _errors(caplog) -> list[str]:
    import logging
    return [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def test_the_record_step_is_bounded(caplog):
    """R5: each write is one attempt (retry None) given what is left of the
    deadline as its timeout, and once the deadline has passed the remaining
    tickers fail with reason deadline and no write is attempted."""
    import logging

    from gcp.fetchers import premarket_as_read as par
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    ticks = iter([0.0, 1.0, 4.0, 11.0])     # start, then before SPY, QQQ, IWM
    bucket = MemoryBucket()
    with caplog.at_level(logging.INFO):
        written, failed = par.write_records(lambda: bucket, AS_READ_SESSION, _as_reads(),
                                            {'SPY': None, 'QQQ': None, 'IWM': None},
                                            clock=lambda: next(ticks), env={})
    assert list(ticks) == []                # the clock was read four times, no more
    assert par.AS_READ_DEADLINE_S == 10
    assert bucket.timeouts == [9.0, 6.0]
    assert bucket.retries == [None, None]
    assert written == [_as_read_name('SPY'), _as_read_name('QQQ')]
    assert failed == [('IWM', 'deadline')]
    assert not any('/IWM/' in name for name in bucket.writes)
    assert _errors(caplog) == ['as_read_failed ticker=IWM reason=deadline']


def test_two_runs_on_one_date_keep_both_objects():
    """The 08:20 and the 09:20 reads of one date are two objects; the second
    never overwrites the first."""
    from datetime import timedelta

    from gcp.fetchers import premarket_as_read as par
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    bucket = MemoryBucket()
    first = _as_read_fetched_at()
    second = first + timedelta(hours=1)
    env = {'CLOUD_RUN_EXECUTION': 'fetch-premarket-refresh-x1', 'CLOUD_RUN_TASK_ATTEMPT': '0'}
    for at in (first, second):
        written, failed = par.write_records(lambda: bucket, AS_READ_SESSION,
                                            _as_reads(('SPY',), at), {'SPY': None}, env=env)
        assert (written, failed) == ([_as_read_name('SPY', at)], [])
    assert set(bucket.objects) == {_as_read_name('SPY', first), _as_read_name('SPY', second)}
    headers = [par.read_record(bucket.objects[_as_read_name('SPY', at)])[0]
               for at in (first, second)]
    assert [h['fetched_at'] for h in headers] == [first.isoformat(), second.isoformat()]
    assert {(h['execution'], h['task_attempt']) for h in headers} == {
        ('fetch-premarket-refresh-x1', '0')}


def test_write_records_counts_each_failure(caplog):
    """R4, the bucket half: a raising write, an object already present and a
    bucket that cannot be built each fail their tickers with the error, the
    other tickers are still written, and every write is create-only."""
    import logging

    from gcp.fetchers import premarket_as_read as par
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    snapshots = {'SPY': None, 'QQQ': None, 'IWM': None}

    # a write that raises
    bucket = MemoryBucket()
    bucket.fail_write = lambda name: OSError('boom') if '/QQQ/' in name else None
    with caplog.at_level(logging.INFO):
        written, failed = par.write_records(lambda: bucket, AS_READ_SESSION, _as_reads(),
                                            snapshots, clock=lambda: 0.0, env={})
    assert written == [_as_read_name('SPY'), _as_read_name('IWM')]
    assert failed == [('QQQ', 'OSError: boom')]
    assert _errors(caplog) == ['as_read_failed ticker=QQQ reason=OSError: boom']
    assert {p for _, p in bucket.preconditions} == {0}

    # an object already at SPY's name: never overwritten
    caplog.clear()
    bucket = MemoryBucket()
    bucket.put(_as_read_name('SPY'), b'earlier')
    with caplog.at_level(logging.INFO):
        written, failed = par.write_records(lambda: bucket, AS_READ_SESSION, _as_reads(),
                                            snapshots, clock=lambda: 0.0, env={})
    assert written == [_as_read_name('QQQ'), _as_read_name('IWM')]
    ((ticker, reason),) = failed
    assert ticker == 'SPY' and reason.startswith('GenerationMismatch: ')
    assert bucket.objects[_as_read_name('SPY')] == b'earlier'
    assert {p for _, p in bucket.preconditions} == {0}
    assert _errors(caplog) == [f'as_read_failed ticker=SPY reason={reason}']

    # no bucket to write to
    caplog.clear()

    def no_bucket():
        raise RuntimeError('GCS_BUCKET is not set: the bar export has no bucket to write to')

    with caplog.at_level(logging.INFO):
        written, failed = par.write_records(no_bucket, AS_READ_SESSION, _as_reads(),
                                            snapshots, clock=lambda: 0.0, env={})
    reason = 'RuntimeError: GCS_BUCKET is not set: the bar export has no bucket to write to'
    assert written == []
    assert failed == [('SPY', reason), ('QQQ', reason), ('IWM', reason)]
    assert _errors(caplog) == [f'as_read_failed ticker={t} reason={reason}'
                               for t in ('SPY', 'QQQ', 'IWM')]


_PRIOR = {'close': 750.0, 'open': 749.0, 'atr_14': 10.0, 'atr_5': None}


def _run_refresh(monkeypatch, *, bars_for, tickers=('SPY', 'QQQ', 'IWM', 'AAPL'),
                 prior_for=None, bucket=None, env=None, events=None):
    """Run the refresh job's main() on 2026-11-16 with the vendor, the prior
    session, the level parameters, the clock and the upsert stood in.

    ``bars_for(ticker)`` is what fetch_minute_data returns; ``prior_for(ticker)``
    the prior session (it may raise), else ``_PRIOR``. With *bucket* the
    record step writes to it; without, ``_as_read_bucket`` runs as written,
    on the environment (``GCS_BUCKET`` unset unless *env* sets it). The
    patches end with the call, so a second call starts clean. Returns the
    exit code (None when main() returned), the rows bound to
    upsert_premarket, and the events in order: ``'upsert'`` when it ran, and
    each object name as the bucket starts to write it.
    """
    import sys
    from datetime import datetime

    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_premarket_refresh as fpr

    events = [] if events is None else events
    rows: list[dict] = []
    frozen = _as_read_fetched_at()

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz)

    def prior(ticker, fetch_date):
        return prior_for(ticker) if prior_for is not None else dict(_PRIOR)

    def upsert(bound):
        rows.extend(bound)
        events.append('upsert')
        return len(bound)

    with monkeypatch.context() as mp:
        for name in ('GCS_BUCKET', 'CLOUD_RUN_EXECUTION', 'CLOUD_RUN_TASK_ATTEMPT'):
            mp.delenv(name, raising=False)
        for name, value in (env or {}).items():
            mp.setenv(name, value)
        mp.setenv('ALPHA_VANTAGE_API_KEY', 'TEST-KEY-not-real')
        mp.setattr(sys, 'argv', ['fetch_premarket_refresh', '--tickers', *tickers,
                                 '--date', '2026-11-16'])
        mp.setattr(fetch_market_data, 'fetch_minute_data', lambda tk, d, k: bars_for(tk))
        mp.setattr(fpr, '_prior_session_from_db', prior)
        mp.setattr(fpr, 'read_level_params_for_run', lambda tks, d: {})
        mp.setattr(fpr, 'datetime', FrozenDatetime)
        mp.setattr(fpr, 'upsert_premarket', upsert)
        if bucket is not None:
            bucket.before_write = events.append
            mp.setattr(fpr, '_as_read_bucket', lambda: bucket)
        try:
            fpr.main()
        except SystemExit as exc:
            return exc.code, rows, events
    return None, rows, events


def _as_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Vendor bars as read_record returns them."""
    return pd.DataFrame({
        'ts': pd.Series(pd.DatetimeIndex(df.index), dtype='datetime64[ns]').reset_index(drop=True),
        'open': df['Open'].to_numpy(dtype='float64'), 'high': df['High'].to_numpy(dtype='float64'),
        'low': df['Low'].to_numpy(dtype='float64'), 'close': df['Close'].to_numpy(dtype='float64'),
        'volume': df['Volume'].to_numpy(dtype='int64'),
    })


def _assert_recorded(bucket, events, rows, ticker):
    """*ticker*'s object was written create-only after the upsert, holds the
    four bars its fetch returned, the fetch instant bound to the upsert and
    the values bound for it."""
    from gcp.fetchers import fetch_premarket_refresh as fpr
    from gcp.fetchers.premarket_as_read import read_record, snapshot_record

    name = _as_read_name(ticker)
    assert (name, 0) in bucket.preconditions
    assert events.index('upsert') < events.index(name)
    header, bars = read_record(bucket.objects[name])
    pd.testing.assert_frame_equal(bars, _as_frame(_r1_bars(ticker)))
    (row,) = [r for r in rows if r['ticker'] == ticker]
    assert header['fetched_at'] == row['pre_fetched_at'].isoformat()
    assert header['snapshot'] == snapshot_record(row, fpr._UPSERT_KEYS)
    assert header['snapshot']['pre_high'] is not None
    return header


def test_run_records_what_each_of_the_three_tickers_read(monkeypatch):
    """R3: one object per SPY, QQQ and IWM read, none for the rest of the
    universe, each written once after the upsert, holding the fetch instant
    and the values bound for its ticker; the rows bound are the rows of a
    run with no bucket."""
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    bucket = MemoryBucket()
    code, rows, events = _run_refresh(monkeypatch, bars_for=_r1_bars, bucket=bucket)
    assert code is None
    names = [_as_read_name(t) for t in ('SPY', 'QQQ', 'IWM')]
    assert sorted(bucket.objects) == sorted(names)
    assert not any('AAPL' in name for name in bucket.writes)
    assert events == ['upsert', *names]
    assert [p for _, p in bucket.preconditions] == [0, 0, 0]
    assert sorted(r['ticker'] for r in rows) == ['AAPL', 'IWM', 'QQQ', 'SPY']
    for ticker in ('SPY', 'QQQ', 'IWM'):
        header = _assert_recorded(bucket, events, rows, ticker)
        assert header['bar_count'] == 4 and header['ticker'] == ticker

    # with no bucket at all the run binds the same rows (and exits 1, R4)
    code, unrecorded_rows, events = _run_refresh(monkeypatch, bars_for=_r1_bars)
    assert code == 1 and events == ['upsert']
    assert unrecorded_rows == rows


def test_a_failed_prior_session_lookup_is_still_recorded(monkeypatch):
    """R3: a read whose prior-session lookup failed binds no row and is
    still on file, with the bars it read and a null snapshot."""
    from gcp.fetchers.premarket_as_read import read_record
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    def prior_for(ticker):
        if ticker == 'QQQ':
            raise RuntimeError('prior lookup down')
        return dict(_PRIOR)

    bucket = MemoryBucket()
    code, rows, events = _run_refresh(monkeypatch, bars_for=_r1_bars, prior_for=prior_for,
                                      bucket=bucket)
    assert code is None
    assert 'QQQ' not in {r['ticker'] for r in rows}
    name = _as_read_name('QQQ')
    assert (name, 0) in bucket.preconditions
    assert events.index('upsert') < events.index(name)
    header, bars = read_record(bucket.objects[name])
    pd.testing.assert_frame_equal(bars, _as_frame(_r1_bars('QQQ')))
    assert header['snapshot'] is None and header['bar_count'] == 4
    for ticker in ('SPY', 'IWM'):
        _assert_recorded(bucket, events, rows, ticker)


def test_an_empty_fetch_is_still_recorded(monkeypatch):
    """R6: a fetch that returned no bars (the columnless frame
    fetch_minute_bars returns) binds no row and is on file with no bars."""
    from gcp.fetchers.premarket_as_read import read_record
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    bucket = MemoryBucket()
    code, rows, events = _run_refresh(
        monkeypatch, tickers=('SPY', 'QQQ', 'IWM'), bucket=bucket,
        bars_for=lambda t: pd.DataFrame() if t == 'SPY' else _r1_bars(t))
    assert code is None
    assert 'SPY' not in {r['ticker'] for r in rows}
    name = _as_read_name('SPY')
    assert (name, 0) in bucket.preconditions
    assert events.index('upsert') < events.index(name)
    header, bars = read_record(bucket.objects[name])
    assert header['bar_count'] == 0 and header['snapshot'] is None and bars.empty
    for ticker in ('QQQ', 'IWM'):
        _assert_recorded(bucket, events, rows, ticker)


@pytest.mark.parametrize('case', ['write_raises', 'no_bucket', 'already_present'])
def test_a_failed_record_write_fails_the_run_after_the_upsert(monkeypatch, caplog, case):
    """R4: a record that cannot be written is an ERROR line naming the
    ticker and the error and exit 1, after the upsert has run for every
    ticker; the other tickers' records are still written."""
    import logging

    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    bucket = MemoryBucket()
    if case == 'write_raises':
        bucket.fail_write = lambda name: OSError('bucket down') if '/QQQ/' in name else None
        failed = {'QQQ': 'OSError: bucket down'}
    elif case == 'already_present':
        bucket.put(_as_read_name('SPY'), b'earlier')
        failed = {'SPY': 'GenerationMismatch: '}
    else:
        bucket = None
        failed = {t: 'RuntimeError: GCS_BUCKET is not set' for t in ('SPY', 'QQQ', 'IWM')}

    with caplog.at_level(logging.INFO):
        code, rows, events = _run_refresh(monkeypatch, bars_for=_r1_bars, bucket=bucket)
    assert code == 1
    assert events[0] == 'upsert' and events.count('upsert') == 1
    assert sorted(r['ticker'] for r in rows) == ['AAPL', 'IWM', 'QQQ', 'SPY']
    errors = [m for m in _errors(caplog) if m.startswith('as_read_failed')]
    assert len(errors) == len(failed)
    for ticker, reason in failed.items():
        assert sum(m.startswith(f'as_read_failed ticker={ticker} reason={reason}')
                   for m in errors) == 1
    if bucket is not None:
        for ticker in {'SPY', 'QQQ', 'IWM'} - set(failed):
            assert _as_read_name(ticker) in bucket.writes
            assert _as_read_name(ticker) in bucket.objects
    if case == 'already_present':
        assert bucket.objects[_as_read_name('SPY')] == b'earlier'


def test_a_retryable_upload_error_stays_inside_the_deadline(monkeypatch, caplog):
    """R5, through the real GcsBucket.write on a real storage client whose
    transport answers 503 and advances the clock by each request's timeout:
    one attempt, no sleep, the other tickers fail with reason deadline, and
    the step ends inside AS_READ_DEADLINE_S.

    google-cloud-storage 3.17.1 also queues, on a client's first upload, a
    bucket GET on a daemon thread (``_bucket_metadata_cache``, for its trace
    attributes) with the library's default retry; the upload does not wait
    for it. Each thread therefore reads its own clock: the main thread's
    clock, sleeps and requests are the record step's, and the background
    thread is answered 503 too and joined before the test ends."""
    import logging
    import threading
    import time

    import google.cloud.storage as storage
    import requests
    from google.auth.credentials import AnonymousCredentials

    from gcp.fetchers.premarket_as_read import AS_READ_DEADLINE_S

    clocks: dict[int, float] = {}
    sleeps, calls, background, events = [], [], [], []

    def on_main() -> bool:
        return threading.current_thread() is threading.main_thread()

    def now() -> float:
        return clocks.setdefault(threading.get_ident(), 1000.0)

    def advance(seconds: float) -> None:
        clocks[threading.get_ident()] = now() + seconds

    def sleep(seconds):
        if on_main():
            sleeps.append(seconds)
        advance(seconds)

    monkeypatch.setattr(time, 'monotonic', now)
    monkeypatch.setattr(time, 'sleep', sleep)

    class _Answer503(requests.Session):
        is_mtls = False

        def request(self, method, url, **kw):
            if on_main():
                calls.append((method, url, kw['timeout']))
                events.append('request')
            else:
                background.append((method, url))
            advance(kw['timeout'])
            response = requests.Response()
            response.status_code = 503
            response._content = b'{"error": {"code": 503, "message": "Service Unavailable"}}'
            response.headers['Content-Type'] = 'application/json'
            response.url = url
            response.request = requests.Request(method, url).prepare()
            return response

    real_client = storage.Client
    monkeypatch.setattr(storage, 'Client', lambda *a, **k: real_client(
        project='test-project', credentials=AnonymousCredentials(), _http=_Answer503()))

    before = set(threading.enumerate())
    with caplog.at_level(logging.INFO):
        code, rows, events = _run_refresh(monkeypatch, bars_for=_r1_bars,
                                          tickers=('SPY', 'QQQ', 'IWM'),
                                          env={'GCS_BUCKET': 'test-bucket'}, events=events)
    for thread in set(threading.enumerate()) - before:
        thread.join(timeout=30)
        assert not thread.is_alive()
    main_clock = clocks[threading.main_thread().ident]

    assert code == 1
    assert events.index('upsert') < events.index('request')
    ((method, url, timeout),) = calls
    assert method == 'POST' and '/upload/storage/v1/b/test-bucket/o' in url
    assert timeout == 10.0                  # all of the deadline: nothing moved the clock before it
    assert sleeps == []
    assert all(m == 'GET' and '/b/test-bucket?' in u for m, u in background)
    errors = [m for m in _errors(caplog) if m.startswith('as_read_failed')]
    assert errors[0].startswith('as_read_failed ticker=SPY reason=ServiceUnavailable: ')
    assert errors[1:] == ['as_read_failed ticker=QQQ reason=deadline',
                          'as_read_failed ticker=IWM reason=deadline']
    assert main_clock - 1000.0 <= AS_READ_DEADLINE_S


def test_a_run_that_read_none_of_the_three_builds_no_bucket():
    """A universe without SPY, QQQ or IWM has nothing to record: no bucket is
    built (no storage client for nothing) and nothing fails."""
    from gcp.fetchers import premarket_as_read as par

    built = []
    assert par.write_records(lambda: built.append(1), AS_READ_SESSION, {}, {},
                             clock=lambda: 0.0, env={}) == ([], [])
    assert built == []
