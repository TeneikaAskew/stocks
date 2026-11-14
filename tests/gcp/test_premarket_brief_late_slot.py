"""FEAT-PLAYBOOK-001: the brief's late slot (BRIEF_RUN_SLOT=late).

Spec: docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-late-slot.md.

A second run of premarket-brief at 09:20 America/New_York waits for the
premarket refresh, rebuilds the day's levels from that snapshot, replaces the
session's canonical premarket_analysis rows in one guarded statement before
09:29:30 and posts one short note. Every run without the variable does what
it does on main.

Hermetic: no test here opens a socket or a database. The clock is the
exchange's, replaced through lib.eastern_time.eastern_now.
"""
from __future__ import annotations

import copy
import inspect
import logging
import socket
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# The module, not the class: a Test* name at this module's top level would be
# collected here a second time.
import tests.gcp.test_premarket_brief as brief_tests  # noqa: E402
from gcp import premarket_brief as pb  # noqa: E402
from lib.eastern_time import ET, ET_NAME, as_eastern_time  # noqa: E402

SESSION, LAST_BAR, TICKERS = '2026-11-13', '2026-11-12', ('IWM', 'QQQ', 'SPY')
# America/New_York wall times of the two refresh writes.
EARLY_STAMP, LATE_STAMP = '2026-11-13 08:20:33.123456', '2026-11-13 09:20:40.500000'
LATE_STAMP_ISO = '2026-11-13T14:20:40.500000+00:00'    # how level_basis stores it
MAIN_HOOK, EARNINGS_HOOK = 'https://discord.test/main', 'https://discord.test/earnings'

# The structured playbook columns of premarket_analysis: trigger, stop and the
# gating targets of each side, and the spaced plan targets (#1832).
LEVEL_COLUMNS = tuple(
    f'{side}_{name}' for side in ('calls', 'puts')
    for name in ('trigger_price', 'trigger_name', 'stop_price', 'stop_name',
                 't1_price', 't2_price', 't3_price',
                 'plan_t1_price', 'plan_t2_price', 'plan_t3_price'))


def _refuse(*_a, **_k):
    raise AssertionError('I/O attempted where the late slot must do none')


def _refuse_all_io(monkeypatch):
    """Every gcp.database function, the build, the Discord post and a socket
    connect raise: a run that exits before any I/O touches none of them."""
    import gcp.database as database

    for name, obj in inspect.getmembers(database, inspect.isfunction):
        if obj.__module__ == database.__name__:
            monkeypatch.setattr(database, name, _refuse)
    monkeypatch.setattr(pb, 'generate_premarket_brief', _refuse)
    monkeypatch.setattr(pb, 'send_to_discord', _refuse)
    monkeypatch.setattr(socket.socket, 'connect', _refuse)
    monkeypatch.setattr(socket, 'create_connection', _refuse)


def _null(value):
    """NaN and NaT as None, the way a NULL comes back from Postgres."""
    if value is None or isinstance(value, (dict, list, str)):
        return value
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value


def raise_(exc):
    """A function that raises `exc` whatever it is given."""
    def raiser(*_a, **_k):
        raise exc
    return raiser


class Harness:
    """`TestLiveDateIsTheExchangeDate._run` as an object: `main()` against
    in-memory tables, with the exchange clock, the refresh's stamps, the
    Discord webhook and every gcp.database call answered here.

    The upsert keeps a stored analysis_ts unless the frame carries the column,
    as Postgres does (gcp.database.upsert_dataframe updates only the frame's
    columns); a new key without the column gets the clock's now, the column
    default."""

    def __init__(self, monkeypatch, *, session=SESSION, last_bar=LAST_BAR):
        self.monkeypatch = monkeypatch
        self.session, self.last_bar = session, last_bar
        self.tables = {'premarket_analysis': {}, 'premarket_analysis_history': [],
                       'market_data_daily': {}}
        self.sent: list = []          # (webhook_url, payload), in order
        self.send_attempts = 0        # every call, raised or not
        self.writes: list = []        # ('upsert' | 'insert', table), one per call
        self.strat_levels: list = []
        self.generated = 0
        self.stamp_reads = 0
        self.row_reads = 0
        self.queries = 0              # every database read, of any kind
        self.last_brief: Optional[dict] = None
        self.hooks: dict = {}         # stamp_read, row_read, generate, built, upsert, insert, send
        self.built_was: dict = {}     # ticker -> built() of the row in force before the last run
        self.now: Optional[datetime] = None

    # ── clock ────────────────────────────────────────────────────────────
    @staticmethod
    def at(text: str) -> datetime:
        return datetime.fromisoformat(text).replace(tzinfo=ET)

    def set_clock(self, text: str) -> None:
        self._set_now(self.at(text))

    def _set_now(self, eastern: datetime) -> None:
        self.now = eastern
        brief_tests._freeze_exchange_clock(self.monkeypatch, eastern)

    # ── the refresh's rows ───────────────────────────────────────────────
    def snapshot(self, tickers=TICKERS, *, stamp: str, up=0.6, down=0.6, status='ok') -> None:
        fetched = pd.Timestamp(stamp, tz=ET_NAME).tz_convert('UTC')
        for ticker in tickers:
            self.tables['market_data_daily'][ticker] = {
                'pre_fetched_at': fetched, 'pre_filter_status': status, 'up': up, 'down': down}

    def _daily(self, ticker: str) -> pd.DataFrame:
        bars = brief_tests.TestLiveDateIsTheExchangeDate._bars
        snap = self.tables['market_data_daily'].get(ticker)
        if snap is None:
            frame = bars(self.last_bar)
            frame['pre_fetched_at'] = pd.Series(pd.NaT, index=frame.index,
                                                dtype='datetime64[ns, UTC]')
            return frame
        frame = bars(self.last_bar, self.session)
        day = pd.Timestamp(self.session)
        last = float(frame['Close'].iloc[-2])
        frame.loc[day, 'pre_high'] = last + snap['up']
        frame.loc[day, 'pre_low'] = last - snap['down']
        frame.loc[day, 'pre_filter_status'] = snap['pre_filter_status']
        fetched = pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns, UTC]')
        fetched.loc[day] = snap['pre_fetched_at']
        frame['pre_fetched_at'] = fetched
        return frame

    def built(self, ticker: str) -> str:
        """HH:MM:SS Eastern of the stored row's level_basis built_at."""
        basis = self.tables['premarket_analysis'][(self.session, ticker)]['level_basis']
        return as_eastern_time(datetime.fromisoformat(basis['built_at'])).strftime('%H:%M:%S')

    # ── the doubles ──────────────────────────────────────────────────────
    def _hook(self, name, *args):
        hook = self.hooks.get(name)
        if hook is not None:
            hook(self, *args)

    def _strict(self, sql, params=None, timeout_s=None):
        self.queries += 1
        params = dict(params or {})
        if 'level_param_policy' in sql or 'ticker_level_params' in sql:
            return self._level_params.query(sql, params)
        binds = {str(v) for v in params.values()}
        if 'FROM market_data_daily' in sql:
            self.stamp_reads += 1
            self._hook('stamp_read')
            rows = [{'ticker': t, 'pre_fetched_at': r['pre_fetched_at'],
                     'pre_filter_status': r['pre_filter_status']}
                    for t, r in self.tables['market_data_daily'].items()
                    if t in binds and str(self.session) in binds]
            return pd.DataFrame(rows, columns=['ticker', 'pre_fetched_at', 'pre_filter_status'])
        if 'FROM premarket_analysis' in sql:
            self.row_reads += 1
            self._hook('row_read')
            columns = [c.strip() for c in
                       sql.split('SELECT', 1)[1].split('FROM', 1)[0].split(',')]
            rows = [{c: row.get(c) for c in columns}
                    for (day, ticker), row in self.tables['premarket_analysis'].items()
                    if day in binds and ticker in binds]
            return pd.DataFrame(rows, columns=columns)
        raise AssertionError(f'unexpected strict read: {sql}')

    def _query(self, sql, params=None):
        self.queries += 1
        return pd.DataFrame()

    def _row_exists(self, table, where):
        self.queries += 1
        return any(all(str(row.get(k)) == str(v) for k, v in where.items())
                   for row in self.tables[table].values())

    def _upsert(self, df, table, keys):
        self._hook('upsert', df, table)
        for record in df.to_dict('records'):
            record = {k: _null(v) for k, v in record.items()}
            key = tuple(str(record[k]) for k in keys)
            stored = self.tables[table].get(key)
            merged = {**(stored or {}), **record}
            if 'analysis_ts' not in df.columns:
                merged['analysis_ts'] = stored['analysis_ts'] if stored else self.now
            self.tables[table][key] = merged
        self.writes.append(('upsert', table))
        return len(df)

    def _bulk_insert(self, df, table):
        self._hook('insert', df, table)
        self.tables[table].extend(
            {**{k: _null(v) for k, v in record.items()}, 'written_at': self.now}
            for record in df.to_dict('records'))
        self.writes.append(('insert', table))
        return len(df)

    def _send(self, message, webhook_url, timeout=10):
        self.send_attempts += 1
        self._hook('send', message, webhook_url)
        self.sent.append((webhook_url, message))

    def _slept(self, seconds):
        self._set_now(self.now + timedelta(seconds=seconds))

    def _install(self) -> None:
        import gcp.database as database
        import lib.strat_levels as sl
        import lib.strategies.calibration as calibration
        from lib.data_loader import DataLoader
        from tests.lib.level_params_fixtures import legacy_db

        mp = self.monkeypatch
        mp.setattr(socket.socket, 'connect', _refuse)
        mp.setattr(socket, 'create_connection', _refuse)
        self._level_params = legacy_db(list(TICKERS))

        mp.setattr(DataLoader, 'load_daily',
                   lambda _loader, ticker, *a, **k: self._daily(ticker))
        mp.setattr(pb, '_load_gamma_freshness', lambda *a, **k: dict(
            data_source='unavailable', snapshot_ts=None, snapshot_date=None, days_behind=None))
        mp.setattr(pb, '_delete_null_close_rows', lambda *a: None)
        mp.setattr(calibration, '_latest_calibration', lambda *a, **k: None)
        mp.setattr(pb, 'load_yesterday_amc_reactions', lambda today, top_n=5: [])
        mp.setattr(pb, 'load_economic_events',
                   lambda today, days_ahead=5: {'today': [], 'week': []})

        class _Conn:
            class connection:  # noqa: N801
                @staticmethod
                def commit():
                    return None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _Engine:
            def connect(self):
                return _Conn()

        def persist_level_map(level_map, conn, **_k):
            self.strat_levels.append(level_map.ticker)
            return len(level_map.levels)

        mp.setattr(database, 'is_cloud_sql_configured', lambda: True)
        mp.setattr(database, 'query_to_dataframe', self._query)
        mp.setattr(database, 'query_to_dataframe_strict', self._strict)
        mp.setattr(database, 'get_engine', lambda: _Engine())
        mp.setattr(database, 'row_exists', self._row_exists)
        mp.setattr(database, 'upsert_dataframe', self._upsert)
        mp.setattr(database, 'bulk_insert_dataframe', self._bulk_insert)
        mp.setattr(sl, 'persist_level_map', persist_level_map)
        mp.setattr(pb, 'send_to_discord', self._send)
        mp.setattr(pb, '_sleep', self._slept, raising=False)

        real_generate = getattr(pb.generate_premarket_brief, '__wrapped__',
                                pb.generate_premarket_brief)

        def generate(*a, **k):
            self.generated += 1
            self._hook('generate')
            brief = real_generate(*a, **k)
            self._hook('built', brief)
            self.last_brief = brief
            return brief

        generate.__wrapped__ = real_generate
        mp.setattr(pb, 'generate_premarket_brief', generate)

    # ── one run of main() ────────────────────────────────────────────────
    def run(self, at: str, *, late=False, env=None, argv=()) -> Optional[int]:
        """`main(argv)` at exchange clock `at`. Returns the SystemExit code,
        or None when main returned. Any other exception propagates."""
        mp = self.monkeypatch
        self.set_clock(at)
        self._install()
        for key in ('BRIEF_AS_OF', 'BRIEF_UPDATE', 'BRIEF_POST_TO_DISCORD', 'BRIEF_AMC_REACTIONS',
                    'BRIEF_POST_EXISTING_TICKER', 'BRIEF_POST_EXISTING_DATE', 'BRIEF_RUN_SLOT'):
            mp.delenv(key, raising=False)
        mp.setenv('BRIEF_TICKERS', ','.join(TICKERS))
        mp.setenv('BRIEF_LLM_DISABLE', '1')
        mp.setenv('DISCORD_WEBHOOK_URL', MAIN_HOOK)
        mp.setenv('DISCORD_WEBHOOK_EARNINGS_URL', EARNINGS_HOOK)
        mp.setenv('BRIEF_TRIGGERED_BY', 'cloud-scheduler:premarket-brief-daily')
        if late:
            mp.setenv('BRIEF_RUN_SLOT', 'late')
            mp.setenv('BRIEF_TRIGGERED_BY', 'cloud-scheduler:premarket-brief-late')
        for key, value in (env or {}).items():
            if value is None:
                mp.delenv(key, raising=False)
            else:
                mp.setenv(key, value)
        # What the rows in force said they were built at before this run.
        self.built_was = {t: self.built(t) for (day, t) in self.tables['premarket_analysis']
                          if day == self.session
                          and self.tables['premarket_analysis'][(day, t)].get('level_basis')}
        try:
            pb.main(list(argv))
        except SystemExit as stop:
            return stop.code
        return None


@pytest.fixture
def make_harness(monkeypatch):
    def make(session=SESSION, last_bar=LAST_BAR):
        return Harness(monkeypatch, session=session, last_bar=last_bar)
    return make


@pytest.fixture
def harness(make_harness):
    return make_harness()


class TestRunSlot:
    def test_names(self):
        assert pb.RUN_SLOTS == ('early', 'late')
        assert (pb.LATE_SLOT_START, pb.LATE_SLOT_WAIT_DEADLINE, pb.LATE_SLOT_WRITE_CUTOFF,
                pb.LATE_SLOT_POLL_SECONDS) == (time(9, 20), time(9, 27), time(9, 29, 30), 5)

    @pytest.mark.parametrize('raw,slot', [(None, 'early'), ('', 'early'), ('   ', 'early'),
                                          ('early', 'early'), ('late', 'late'), (' late ', 'late')])
    def test_resolve(self, monkeypatch, raw, slot):
        if raw is None:
            monkeypatch.delenv('BRIEF_RUN_SLOT', raising=False)
        else:
            monkeypatch.setenv('BRIEF_RUN_SLOT', raw)
        assert pb._resolve_run_slot() == slot

    @pytest.mark.parametrize('raw', ['LATE', 'Late', 'both', '0920'])
    def test_an_unknown_value_is_refused_by_name(self, monkeypatch, raw):
        monkeypatch.setenv('BRIEF_RUN_SLOT', raw)
        with pytest.raises(ValueError, match=raw):
            pb._resolve_run_slot()

    @pytest.mark.parametrize('raw', ['LATE', 'Late', 'both', '0920'])
    def test_an_unknown_value_exits_2_before_any_io(self, monkeypatch, capsys, raw):
        for key in ('BRIEF_AS_OF', 'BRIEF_UPDATE', 'BRIEF_POST_EXISTING_TICKER',
                    'BRIEF_POST_EXISTING_DATE'):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv('BRIEF_RUN_SLOT', raw)
        _refuse_all_io(monkeypatch)
        with pytest.raises(SystemExit) as stop:
            pb.main([])
        assert stop.value.code == 2
        err = capsys.readouterr().err
        assert "BRIEF_RUN_SLOT must be one of ('early', 'late')" in err and repr(raw) in err

    @pytest.mark.parametrize('day,start,deadline,cutoff', [
        (date(2026, 11, 16), '14:20:00', '14:27:00', '14:29:30'),
        (date(2026, 7, 13), '13:20:00', '13:27:00', '13:29:30')])
    def test_clock(self, day, start, deadline, cutoff):
        def utc(t):
            return datetime.fromisoformat(f'{day}T{t}+00:00')

        clock = pb._late_slot_clock(day)
        assert clock == (utc(start), utc(deadline), utc(cutoff))
        assert (clock.start, clock.wait_deadline, clock.write_cutoff) == tuple(clock)

    def test_now_is_the_exchange_clock_looked_up_at_call_time(self, monkeypatch):
        import lib.eastern_time as eastern_time
        from lib.eastern_time import ET

        frozen = datetime(2026, 11, 13, 9, 21, 30, tzinfo=ET)
        monkeypatch.setattr(eastern_time, 'eastern_now', lambda: frozen)
        assert pb._eastern_now() == frozen


class TestEarlySlotUnchanged:
    """The pin: with BRIEF_RUN_SLOT unset or 'early' the run is the run of
    main. A second scheduled run writes history and no canonical row."""

    def test_unset_and_early_are_the_run_of_main(self, make_harness, caplog):
        seen = []
        for slot in (None, 'early'):
            h = make_harness()
            h.snapshot(stamp=EARLY_STAMP)
            assert h.run('2026-11-13 08:30:50', env={'BRIEF_RUN_SLOT': slot}) is None
            first = copy.deepcopy(h.tables['premarket_analysis'])
            assert sorted(first) == [(SESSION, t) for t in TICKERS]
            with caplog.at_level(logging.WARNING, logger='gcp.premarket_brief'):
                assert h.run('2026-11-13 08:35:00', env={'BRIEF_RUN_SLOT': slot}) is None
            assert h.tables['premarket_analysis'] == first
            assert h.writes.count(('upsert', 'premarket_analysis')) == 1
            assert 'row already exists' in caplog.text
            assert len(h.tables['premarket_analysis_history']) == 6
            assert [url for url, _ in h.sent] == [MAIN_HOOK, MAIN_HOOK, EARNINGS_HOOK, MAIN_HOOK] * 2
            assert h.stamp_reads == 0 and h.row_reads == 0
            seen.append([(url, [e.get('title') for e in m['embeds']]) for url, m in h.sent])
            caplog.clear()
        assert seen[0] == seen[1]


class TestLateSlotPrecedence:
    @pytest.mark.parametrize('argv,env', [(['--update'], {}), ([], {'BRIEF_UPDATE': 'true'})])
    def test_late_with_an_update_exits_2(self, harness, capsys, argv, env):
        harness.snapshot(stamp=LATE_STAMP)
        assert harness.run('2026-11-13 09:21:30', late=True, env=env, argv=argv) == 2
        assert (harness.queries, harness.writes, harness.sent, harness.generated) == (0, [], [], 0)
        assert 'ERROR: BRIEF_RUN_SLOT=late cannot be combined' in capsys.readouterr().err

    def test_a_late_replay_is_the_replay_of_main(self, make_harness, caplog):
        plain, slotted = make_harness(), make_harness()
        for h, late in ((plain, False), (slotted, True)):
            h.snapshot(stamp=LATE_STAMP)
            with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
                assert h.run('2026-11-14 10:00:00', late=late, env={'BRIEF_AS_OF': SESSION}) is None
        assert slotted.sent == [] and slotted.stamp_reads == 0 and slotted.row_reads == 0
        assert {r['run_kind'] for r in slotted.tables['premarket_analysis_history']} == {'replay_refresh'}
        assert {r['run_kind'] for r in slotted.tables['premarket_analysis'].values()} == {'replay'}
        assert sorted(slotted.tables['premarket_analysis']) == [(SESSION, t) for t in TICKERS]
        for key, row in slotted.tables['premarket_analysis'].items():
            for col in LEVEL_COLUMNS:
                assert row[col] == plain.tables['premarket_analysis'][key][col]
        assert sum('has no effect on a BRIEF_AS_OF replay' in r.getMessage()
                   for r in caplog.records) == 1          # the slotted run only, once

    @pytest.mark.parametrize('env', [{'BRIEF_AS_OF': SESSION}, {}])
    def test_an_unknown_slot_exits_2_replay_or_not(self, harness, env):
        assert harness.run('2026-11-13 09:21:30', env={'BRIEF_RUN_SLOT': 'both', **env}) == 2
        assert harness.queries == 0 and harness.writes == []

    def test_late_update_and_replay_together_exit_2(self, harness):
        env = {'BRIEF_AS_OF': SESSION, 'BRIEF_UPDATE': 'true'}
        assert harness.run('2026-11-13 09:21:30', late=True, env=env) == 2
        assert (harness.queries, harness.writes, harness.sent, harness.generated) == (0, [], [], 0)


# ── The stamp read and the wait ─────────────────────────────────────────────

D = date(2026, 11, 13)
CLOCK = pb._late_slot_clock(D)
T = list(TICKERS)


def _utc(eastern_text: str) -> datetime:
    """An America/New_York wall time of the session date as a UTC instant."""
    from lib.eastern_time import as_utc_instant
    return as_utc_instant(datetime.fromisoformat(f'{D} {eastern_text}').replace(tzinfo=ET))


EARLY = {'pre_fetched_at': _utc('08:20:57'), 'pre_filter_status': 'ok'}
LATE = {'pre_fetched_at': _utc('09:20:40'), 'pre_filter_status': 'ok'}


def _all(row):
    return {t: dict(row) for t in T}


class _ticking:
    """A clock that only moves when it is slept on."""

    def __init__(self, start: str):
        self.t = datetime.fromisoformat(f'{D} {start}').replace(tzinfo=ET)
        self.slept: list = []

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds) -> None:
        self.slept.append(seconds)
        self.t = self.t + timedelta(seconds=seconds)


def _wait(tick, read):
    return pb._wait_for_late_snapshot(D, T, CLOCK, now=tick.now, sleep=tick.sleep, read=read)


class TestLateSlotWait:
    def test_ready_on_the_third_read(self):
        tick, reads = _ticking('09:20:05'), iter([_all(EARLY), _all(EARLY), _all(LATE)])
        out = _wait(tick, lambda d, t: next(reads))
        assert (out.ready, out.polls, tick.slept, out.reasons, out.waited_s) == (True, 3, [5, 5], {}, 10)
        assert set(out.stamps.values()) == {LATE['pre_fetched_at']}
        assert sorted(out.stamps) == T

    def test_the_early_stamp_never_passes_and_no_read_follows_the_deadline(self):
        from lib.eastern_time import as_utc_instant
        tick, calls = _ticking('09:26:50'), []
        out = _wait(tick, lambda d, t: calls.append(tick.now()) or _all(EARLY))
        assert not out.ready and out.polls == 2 and len(calls) == 2
        assert all(as_utc_instant(c) < CLOCK.wait_deadline for c in calls)
        assert out.reasons == {t: 'stamp 08:20:57' for t in T}
        assert out.stamps == {t: EARLY['pre_fetched_at'] for t in T}

    @pytest.mark.parametrize('row,reason', [
        ({'pre_fetched_at': LATE['pre_fetched_at'], 'pre_filter_status': 'level_params_unavailable'},
         'status level_params_unavailable'),
        ({'pre_fetched_at': LATE['pre_fetched_at'], 'pre_filter_status': None}, 'status none'),
        ({'pre_fetched_at': None, 'pre_filter_status': 'ok'}, 'no stamp'),
        (None, 'no row')])
    def test_one_ticker_that_does_not_pass(self, row, reason):
        rows = _all(LATE)
        if row is None:
            del rows['QQQ']
        else:
            rows['QQQ'] = row
        out = _wait(_ticking('09:26:58'), lambda d, t: rows)
        assert not out.ready and out.reasons == {'QQQ': reason}

    @pytest.mark.parametrize('stamp,passes', [('09:19:59.999999', False), ('09:20:00', True)])
    def test_the_boundary(self, stamp, passes):
        rows = _all({'pre_fetched_at': _utc(stamp), 'pre_filter_status': 'ok'})
        out = _wait(_ticking('09:26:58'), lambda d, t: rows)
        assert out.ready is passes and out.polls == 1

    def test_a_read_that_raises_is_logged_and_polled_again(self, caplog):
        reads = iter([ConnectionError('down'), _all(LATE)])

        def read(d, t):
            item = next(reads)
            if isinstance(item, Exception):
                raise item
            return item

        with caplog.at_level(logging.WARNING, logger='gcp.premarket_brief'):
            out = _wait(_ticking('09:20:05'), read)
        assert out.ready and out.polls == 2
        assert any(r.levelno == logging.WARNING
                   and 'late slot stamp read failed: ConnectionError: down' in r.getMessage()
                   for r in caplog.records)

    def test_no_read_succeeds(self):
        out = _wait(_ticking('09:26:50'), raise_(ConnectionError('down')))
        assert not out.ready and out.polls == 2
        assert out.reasons == {t: 'read failed: ConnectionError' for t in T}
        assert out.stamps == {t: None for t in T}

    def test_reasons_come_from_the_last_read_that_succeeded(self):
        reads = iter([_all(EARLY), ConnectionError('down')])

        def read(d, t):
            item = next(reads)
            if isinstance(item, Exception):
                raise item
            return item

        out = _wait(_ticking('09:26:50'), read)
        assert not out.ready and out.polls == 2
        assert out.reasons == {t: 'stamp 08:20:57' for t in T}

    def test_a_stamp_without_a_zone_does_not_pass(self):
        naive = datetime(2026, 11, 13, 14, 20, 40)        # what a zone-less driver would hand back
        out = _wait(_ticking('09:26:58'),
                    lambda d, t: _all({'pre_fetched_at': naive, 'pre_filter_status': 'ok'}))
        assert not out.ready
        assert out.reasons == {t: 'stamp has no zone' for t in T}

    def test_a_start_after_the_deadline_reads_nothing(self):
        out = _wait(_ticking('09:28:00'), _refuse)
        assert (out.ready, out.polls) == (False, 0)
        assert out.reasons == {t: 'no read before the deadline' for t in T}
        assert out.stamps == {t: None for t in T}

    def test_the_defaults_are_the_module_clock_sleep_and_read(self, monkeypatch):
        import lib.eastern_time as eastern_time
        tick = _ticking('09:26:50')
        monkeypatch.setattr(eastern_time, 'eastern_now', tick.now)
        monkeypatch.setattr(pb, '_sleep', tick.sleep)
        monkeypatch.setattr(pb, '_read_late_slot_stamps', lambda d, t: _all(EARLY))
        out = pb._wait_for_late_snapshot(D, T, CLOCK)
        assert (out.ready, out.polls, tick.slept) == (False, 2, [5, 5])

    def test_the_read_is_one_keyed_statement(self, monkeypatch):
        import gcp.database as database
        seen = []

        def strict(sql, params=None, timeout_s=None):
            seen.append((sql, dict(params or {}), timeout_s))
            return pd.DataFrame({
                'ticker': ['IWM', 'SPY'],
                'pre_fetched_at': pd.to_datetime([LATE['pre_fetched_at'], None], utc=True),
                'pre_filter_status': ['ok', None]})

        monkeypatch.setattr(database, 'query_to_dataframe_strict', strict)
        out = pb._read_late_slot_stamps(D, T)
        ((sql, params, timeout_s),) = seen
        assert 'FROM market_data_daily' in sql and 'date = :session_date' in sql
        assert not any(t in sql for t in T) and timeout_s == 5 == pb.LATE_SLOT_READ_TIMEOUT_S
        assert params['session_date'] == D
        assert {v for k, v in params.items() if k != 'session_date'} == set(T)
        assert set(out) == {'IWM', 'SPY'}          # QQQ has no row, so it is absent
        assert out['IWM'] == {'pre_fetched_at': LATE['pre_fetched_at'], 'pre_filter_status': 'ok'}
        assert out['SPY'] == {'pre_fetched_at': None, 'pre_filter_status': None}

    def test_a_failed_stamp_read_raises_from_the_reader(self, monkeypatch):
        import gcp.database as database
        monkeypatch.setattr(database, 'query_to_dataframe_strict', raise_(ConnectionError('down')))
        with pytest.raises(ConnectionError):
            pb._read_late_slot_stamps(D, T)


# ── The rows in force, "current", and the build check ──────────────────────

EARLY_FETCHED_ISO = '2026-11-13T13:20:33.123456+00:00'     # 08:20:33.123456 Eastern
EARLY_BUILT_AT = '2026-11-13T08:30:50.100000-05:00'
ROW_LEVELS = ('calls_trigger_name', 'calls_trigger_price', 'calls_stop_price', 'calls_t1_price',
              'puts_trigger_name', 'puts_trigger_price', 'puts_stop_price', 'puts_t1_price')


def _basis(*, fetched=EARLY_FETCHED_ISO, built_at=EARLY_BUILT_AT, high=759.737, low=755.73,
           premarket_status='ok') -> dict:
    return {'built_at': built_at, 'premarket_status': premarket_status,
            'premarket': {'date': SESSION, 'fetched_at': fetched, 'pre_high': high, 'pre_low': low,
                          'pre_filter_status': 'ok'}}


def _stored(ticker, *, run_kind='live', analysis_ts='08:30:54', level_basis='default', **levels):
    """One premarket_analysis row as the strict reader hands it back."""
    row = {'ticker': ticker, 'run_kind': run_kind,
           'analysis_ts': pd.Timestamp(_utc(analysis_ts)),
           'level_basis': _basis() if level_basis == 'default' else level_basis,
           'calls_trigger_name': 'PMK_H', 'calls_trigger_price': 759.737,
           'calls_stop_price': 758.10, 'calls_t1_price': 762.63,
           'puts_trigger_name': 'PMK_L', 'puts_trigger_price': 755.73,
           'puts_stop_price': 759.737, 'puts_t1_price': 753.20}
    row.update(levels)
    return row


def _answer_rows(monkeypatch, records):
    """Answer gcp.database's strict reader with `records`; returns the calls."""
    import gcp.database as database
    seen = []

    def strict(sql, params=None, timeout_s=None):
        seen.append((sql, dict(params or {}), timeout_s))
        return pd.DataFrame(records, columns=['ticker', 'run_kind', 'analysis_ts', 'level_basis',
                                              *ROW_LEVELS])

    monkeypatch.setattr(database, 'query_to_dataframe_strict', strict)
    return seen


class TestRowsInForce:
    def test_shape_of_the_read(self, monkeypatch):
        seen = _answer_rows(monkeypatch, [])
        assert pb._read_rows_in_force(D, T) == {}
        ((sql, params, timeout_s),) = seen
        assert 'FROM premarket_analysis' in sql and 'analysis_date = :session_date' in sql
        assert 'run_kind =' not in sql and timeout_s is None
        assert not any(t in sql for t in T)
        assert params['session_date'] == D
        assert {v for k, v in params.items() if k != 'session_date'} == set(T)
        selected = [c.strip() for c in sql.split('SELECT', 1)[1].split('FROM', 1)[0].split(',')]
        assert selected == ['ticker', 'run_kind', 'analysis_ts', 'level_basis', *ROW_LEVELS]

    def test_a_live_a_replay_and_a_bare_row(self, monkeypatch):
        import json
        _answer_rows(monkeypatch, [
            _stored('SPY'),
            _stored('QQQ', run_kind='replay', level_basis=json.dumps(_basis(high=691.94, low=685.0))),
            _stored('IWM', level_basis=None)])
        rows = pb._read_rows_in_force(D, T + ['DIA'])
        assert rows['SPY']['fetched_at'] == datetime.fromisoformat('2026-11-13T13:20:33.123456+00:00')
        assert rows['SPY']['built_at'] == '2026-11-13T08:30:50.100000-05:00'
        assert rows['SPY']['built'] == datetime.fromisoformat(EARLY_BUILT_AT)
        assert (rows['SPY']['run_kind'], rows['SPY']['pre_high'], rows['SPY']['pre_low']) == (
            'live', 759.737, 755.73)
        assert rows['SPY']['analysis_ts'] == _utc('08:30:54')
        assert {k: rows['SPY'][k] for k in ROW_LEVELS} == {
            'calls_trigger_name': 'PMK_H', 'calls_trigger_price': 759.737,
            'calls_stop_price': 758.10, 'calls_t1_price': 762.63,
            'puts_trigger_name': 'PMK_L', 'puts_trigger_price': 755.73,
            'puts_stop_price': 759.737, 'puts_t1_price': 753.20}
        assert rows['QQQ']['run_kind'] == 'replay' and rows['QQQ']['pre_high'] == 691.94
        assert rows['IWM']['built_at'] is None and rows['IWM']['fetched_at'] is None
        assert rows['IWM']['pre_high'] is None and rows['IWM']['pre_low'] is None
        assert rows['IWM']['built'] == rows['IWM']['analysis_ts'] == _utc('08:30:54')
        assert 'DIA' not in rows

    def test_null_and_nan_prices_are_none(self, monkeypatch):
        _answer_rows(monkeypatch, [_stored('SPY', calls_stop_price=float('nan'), puts_t1_price=None,
                                           puts_trigger_name=None)])
        rows = pb._read_rows_in_force(D, T)
        assert rows['SPY']['calls_stop_price'] is None and rows['SPY']['puts_t1_price'] is None
        assert rows['SPY']['puts_trigger_name'] is None
        assert rows['SPY']['calls_trigger_price'] == 759.737

    def test_a_basis_with_no_usable_times(self, monkeypatch):
        # A fetch time with no zone is not a fetch time; a build time with no
        # zone falls back to the row's own write time. Neither is localized.
        _answer_rows(monkeypatch, [_stored('SPY', level_basis=_basis(
            fetched='2026-11-13T13:20:33', built_at='2026-11-13T08:30:50'))])
        rows = pb._read_rows_in_force(D, T)
        assert rows['SPY']['fetched_at'] is None
        assert rows['SPY']['built'] == rows['SPY']['analysis_ts']
        assert rows['SPY']['built_at'] == '2026-11-13T08:30:50'

    def test_a_failed_read_raises(self, monkeypatch):
        import gcp.database as database
        monkeypatch.setattr(database, 'query_to_dataframe_strict', raise_(ConnectionError('down')))
        with pytest.raises(ConnectionError):
            pb._read_rows_in_force(D, T)

    @pytest.mark.parametrize('edit,current', [
        (None, True), ('equal instant', True), ('SPY replay', False), ('SPY missing', False),
        ('SPY fetched before its stamp', False), ('SPY stamp None', False), ('SPY fetched None', False)])
    def test_current(self, edit, current):
        late = LATE['pre_fetched_at']
        rows = {t: {'run_kind': 'live', 'fetched_at': late + timedelta(seconds=3)} for t in T}
        stamps = {t: late for t in T}
        if edit == 'equal instant':
            rows['SPY']['fetched_at'] = late
        elif edit == 'SPY replay':
            rows['SPY']['run_kind'] = 'replay'
        elif edit == 'SPY missing':
            del rows['SPY']
        elif edit == 'SPY fetched before its stamp':
            rows['SPY']['fetched_at'] = late - timedelta(microseconds=1)
        elif edit == 'SPY stamp None':
            stamps['SPY'] = None
        elif edit == 'SPY fetched None':
            rows['SPY']['fetched_at'] = None
        assert pb._rows_current(rows, stamps, T) is current

    def test_current_of_no_tickers_is_false(self):
        assert pb._rows_current({}, {}, []) is False


def _late_brief(tickers=TICKERS) -> dict:
    """A three-ticker brief dated the session whose every level_basis was
    built on the late snapshot."""
    return {
        'date': 'Fri Nov 13, 2026', 'analysis_date': D, 'llm_overview': None,
        'tickers': {t: {
            'price': 760.0, 'level_basis': _basis(fetched=LATE_STAMP_ISO, high=762.693,
                                                  built_at='2026-11-13T09:21:20.000000-05:00'),
            'calls_trigger_name': 'PMK_H', 'calls_trigger_price': 762.693,
            'calls_stop_price': 758.10, 'calls_t1_price': 763.04,
            'puts_trigger_name': 'PMK_L', 'puts_trigger_price': 755.73,
            'puts_stop_price': 762.693, 'puts_t1_price': 753.20,
        } for t in tickers}}


class TestLateBuildCheck:
    def test_a_usable_build(self):
        assert pb._late_build_refusal(_late_brief(), T, CLOCK) is None

    @pytest.mark.parametrize('edit,text', [
        (lambda b: b['tickers']['QQQ']['level_basis'].update(premarket_status='premarket_unfiltered'),
         'QQQ: premarket_status premarket_unfiltered'),
        (lambda b: b['tickers']['QQQ']['level_basis']['premarket'].update(
            fetched_at='2026-11-13T13:20:33.123456+00:00'),
         'QQQ: snapshot fetched 08:20:33 ET, before 09:20:00 ET'),
        (lambda b: b['tickers']['QQQ']['level_basis']['premarket'].update(fetched_at=None),
         'QQQ: snapshot has no fetch time'),
        (lambda b: b['tickers']['QQQ']['level_basis'].update(premarket=None),
         'QQQ: snapshot has no fetch time'),
        (lambda b: b['tickers']['QQQ'].update(status='NO DATA'), 'QQQ: status NO DATA'),
        (lambda b: b['tickers']['QQQ'].update(status='STALE_DAILY_DATA'), 'QQQ: status STALE_DAILY_DATA'),
        (lambda b: b['tickers']['QQQ'].update(status='PLAYBOOK_FAILED'), 'QQQ: status PLAYBOOK_FAILED'),
        (lambda b: b['tickers'].__setitem__('QQQ', {'status': 'NO DATA (all rows null)'}),
         'QQQ: no level_basis'),
        (lambda b: b['tickers']['QQQ'].pop('level_basis'), 'QQQ: no level_basis'),
        (lambda b: b['tickers'].pop('QQQ'), 'QQQ: not built'),
        (lambda b: b['tickers'].__setitem__('DIA', dict(b['tickers']['SPY'])),
         "built ['DIA', 'IWM', 'QQQ', 'SPY'], waited on ['IWM', 'QQQ', 'SPY']")])
    def test_refusals(self, edit, text):
        brief = _late_brief()
        edit(brief)
        assert pb._late_build_refusal(brief, T, CLOCK) == text

    def test_the_first_ticker_that_fails_is_named(self):
        brief = _late_brief()
        brief['tickers']['SPY']['status'] = 'PLAYBOOK_FAILED'
        brief['tickers']['IWM']['level_basis']['premarket_status'] = 'premarket_unavailable'
        assert pb._late_build_refusal(brief, T, CLOCK) == 'IWM: premarket_status premarket_unavailable'

    def test_a_snapshot_stamped_at_the_start_is_usable(self):
        brief = _late_brief()
        for t in T:
            brief['tickers'][t]['level_basis']['premarket']['fetched_at'] = '2026-11-13T14:20:00+00:00'
        assert pb._late_build_refusal(brief, T, CLOCK) is None

    def test_a_build_of_no_tickers_is_refused(self):
        assert pb._late_build_refusal({'tickers': {}}, T, CLOCK) == 'IWM: not built'


# ── The late write in persist_to_cloud_sql ─────────────────────────────────

class _WriteDoubles:
    """gcp.database's writers and the re-read, recorded in call order."""

    def __init__(self, monkeypatch):
        import gcp.database as database

        self.calls: list = []          # ('upsert' | 'insert' | 'exists', frame or where)
        self.fail: dict = {}           # 'upsert' | 'insert' -> exception to raise
        self.now_rows = {t: {'run_kind': 'live', 'analysis_ts': _utc('08:30:54'),
                             'built_at': EARLY_BUILT_AT} for t in T}
        self.read_rows = lambda d, t: self.now_rows

        def upsert(df, table, keys):
            if 'upsert' in self.fail:
                raise self.fail['upsert']
            assert (table, keys) == ('premarket_analysis', ['analysis_date', 'ticker'])
            self.calls.append(('upsert', df))
            return len(df)

        def insert(df, table):
            if 'insert' in self.fail:
                raise self.fail['insert']
            assert table == 'premarket_analysis_history'
            self.calls.append(('insert', df))
            return len(df)

        def exists(table, where):
            self.calls.append(('exists', where))
            return False

        monkeypatch.delenv('BRIEF_AS_OF', raising=False)
        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.setattr(database, 'upsert_dataframe', upsert)
        monkeypatch.setattr(database, 'bulk_insert_dataframe', insert)
        monkeypatch.setattr(database, 'row_exists', exists)
        monkeypatch.setattr(pb, '_read_rows_in_force', lambda d, t: self.read_rows(d, t))

    def kinds(self):
        return [kind for kind, _ in self.calls]

    def late(self, at: str, *, refusal=None, tickers=None):
        """A LateSlotWrite whose rows_read equal now_rows as they are now
        and whose clock reads `at` Eastern on the session date."""
        instant = datetime.fromisoformat(f'{D} {at}').replace(tzinfo=ET)
        return pb.LateSlotWrite(CLOCK, list(tickers or T), copy.deepcopy(self.now_rows),
                                refusal=refusal, now=lambda: instant)


@pytest.fixture
def db(monkeypatch):
    return _WriteDoubles(monkeypatch)


class TestLateWrite:
    def test_applied(self, db):
        w = db.late('09:21:30')
        assert pb.persist_to_cloud_sql(_late_brief(), run_kind='scheduled', triggered_by='x',
                                       late_slot=w) == 3
        assert db.kinds() == ['upsert', 'insert']
        df = db.calls[0][1]
        assert sorted(df['ticker']) == list(TICKERS) and set(df['run_kind']) == {'live'}
        assert set(df['analysis_ts']) == {datetime.fromisoformat('2026-11-13T14:21:30+00:00')}
        assert set(db.calls[1][1]['notes']) == {'LATE_SLOT_APPLIED'}
        assert set(db.calls[1][1]['run_kind']) == {'scheduled'}
        assert 'analysis_ts' not in db.calls[1][1].columns
        assert (w.outcome, w.reason, w.history_recorded) == ('applied', None, True)
        assert w.written_at == datetime.fromisoformat('2026-11-13T14:21:30+00:00')
        assert w.rows_now is db.now_rows
        for col in ('llm_overview', 'llm_orb_explanation', 'llm_analysis', 'llm_playbook'):
            assert col in df.columns and df[col].isna().all()     # NULL is written, not skipped

    @pytest.mark.parametrize('at,outcome', [('09:29:29.999999', 'applied'),
                                            ('09:29:30', 'past_cutoff'), ('09:35:00', 'past_cutoff')])
    def test_the_cutoff(self, db, at, outcome):
        w = db.late(at)
        n = pb.persist_to_cloud_sql(_late_brief(), run_kind='scheduled', triggered_by='x', late_slot=w)
        assert w.outcome == outcome
        if outcome == 'past_cutoff':
            assert n == 0 and db.kinds() == ['insert']
            assert all(note.startswith('LATE_SLOT_NOT_APPLIED: past_cutoff')
                       for note in db.calls[0][1]['notes'])
            assert w.reason == (f'write check at {at} ET, at or after the write cutoff 09:29:30 ET')
            assert w.written_at is None
        else:
            assert n == 3 and db.kinds() == ['upsert', 'insert']

    @pytest.mark.parametrize('edit', ['run_kind', 'analysis_ts', 'built_at', 'row appeared', 'row gone'])
    def test_a_row_that_changed(self, db, edit):
        if edit == 'row appeared':
            del db.now_rows['SPY']
        w = db.late('09:21:30')                 # rows_read: a copy of the rows as the run read them
        if edit == 'run_kind':
            db.now_rows['SPY']['run_kind'] = 'replay'
        elif edit == 'analysis_ts':
            db.now_rows['SPY']['analysis_ts'] = _utc('09:22:00')
        elif edit == 'built_at':
            db.now_rows['SPY']['built_at'] = '2026-11-13T09:22:00-05:00'
        elif edit == 'row appeared':
            db.now_rows['SPY'] = {'run_kind': 'live', 'analysis_ts': _utc('09:22:00'),
                                  'built_at': '2026-11-13T09:22:00-05:00'}
        elif edit == 'row gone':
            del db.now_rows['SPY']
        assert pb.persist_to_cloud_sql(_late_brief(), late_slot=w) == 0
        assert (w.outcome, db.kinds()) == ('row_changed', ['insert'])
        assert w.reason == 'changed since this run read them: SPY' and w.rows_now is db.now_rows
        assert all(note.startswith('LATE_SLOT_NOT_APPLIED: row_changed')
                   for note in db.calls[0][1]['notes'])

    def test_a_refused_build_is_history_only_and_reads_nothing(self, db):
        db.read_rows = _refuse
        w = db.late('09:21:30', refusal='QQQ: status PLAYBOOK_FAILED')
        brief = _late_brief()
        brief['tickers']['QQQ'].update(status='PLAYBOOK_FAILED', playbook_error='KeyError: boom')
        assert pb.persist_to_cloud_sql(brief, late_slot=w) == 0
        assert (w.outcome, w.reason, db.kinds()) == (
            'build_not_usable', 'QQQ: status PLAYBOOK_FAILED', ['insert'])
        notes = dict(zip(db.calls[0][1]['ticker'], db.calls[0][1]['notes']))
        assert all(note.startswith('LATE_SLOT_NOT_APPLIED: build_not_usable QQQ: status PLAYBOOK_FAILED')
                   for note in notes.values())
        # the ticker's own failed note follows the late slot's
        assert notes['QQQ'].endswith('; PLAYBOOK_FAILED: KeyError: boom')
        assert notes['SPY'] == 'LATE_SLOT_NOT_APPLIED: build_not_usable QQQ: status PLAYBOOK_FAILED'

    def test_a_ticker_missing_from_the_rows_is_refused(self, db):
        w = db.late('09:21:30')                      # no refusal given
        assert pb.persist_to_cloud_sql(_late_brief(('IWM', 'SPY')), late_slot=w) == 0
        assert (w.outcome, db.kinds()) == ('build_not_usable', ['insert'])
        assert 'QQQ' in w.reason

    def test_a_failed_ticker_is_never_written_alone(self, db):
        # STALE_DAILY_DATA with no refusal handed in: the canonical frame
        # would hold two of three tickers, so nothing is written.
        brief = _late_brief()
        brief['tickers']['QQQ']['status'] = 'STALE_DAILY_DATA'
        w = db.late('09:21:30')
        assert pb.persist_to_cloud_sql(brief, late_slot=w) == 0
        assert (w.outcome, db.kinds()) == ('build_not_usable', ['insert'])

    def test_a_build_with_no_rows_still_has_an_outcome(self, db):
        brief = _late_brief()
        for t in T:
            brief['tickers'][t] = {'status': 'NO DATA'}
        w = db.late('09:21:30', refusal='IWM: status NO DATA')
        assert pb.persist_to_cloud_sql(brief, late_slot=w) == 0
        assert (w.outcome, db.kinds()) == ('build_not_usable', [])

    def test_a_failed_history_insert_keeps_the_write(self, db, caplog):
        db.fail['insert'] = OSError('history down')
        w = db.late('09:21:30')
        with caplog.at_level(logging.ERROR, logger='gcp.premarket_brief'):
            assert pb.persist_to_cloud_sql(_late_brief(), late_slot=w) == 3
        assert (w.outcome, w.history_recorded) == ('applied', False)
        assert db.kinds() == ['upsert']
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_a_failed_canonical_write_raises_and_records_no_history(self, db):
        db.fail['upsert'] = OSError('db down')
        w = db.late('09:21:30')
        with pytest.raises(OSError):
            pb.persist_to_cloud_sql(_late_brief(), late_slot=w)
        assert db.kinds() == [] and w.outcome is None

    def test_a_failed_re_read_raises_and_writes_nothing(self, db):
        db.read_rows = raise_(ConnectionError('db down'))
        w = db.late('09:21:30')
        with pytest.raises(ConnectionError):
            pb.persist_to_cloud_sql(_late_brief(), late_slot=w)
        assert db.kinds() == [] and w.outcome is None

    def test_late_with_an_update_is_refused(self, db):
        w = db.late('09:21:30')
        with pytest.raises(ValueError):
            pb.persist_to_cloud_sql(_late_brief(), allow_update=True, late_slot=w)
        assert db.calls == []

    def test_late_on_a_replay_is_refused(self, db, monkeypatch):
        monkeypatch.setenv('BRIEF_AS_OF', SESSION)
        w = db.late('09:21:30')
        with pytest.raises(ValueError):
            pb.persist_to_cloud_sql(_late_brief(), late_slot=w)
        assert db.calls == []

    def test_no_database_leaves_the_outcome_unset(self, db, monkeypatch):
        import gcp.database as database
        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: False)
        w = db.late('09:21:30')
        assert pb.persist_to_cloud_sql(_late_brief(), late_slot=w) == 0
        assert w.outcome is None and db.calls == []

    def test_the_early_path_is_the_path_of_main(self, db):
        pb.persist_to_cloud_sql(_late_brief(), run_kind='scheduled', triggered_by='x')
        assert db.kinds() == ['insert', 'exists', 'exists', 'exists', 'upsert']
        assert 'analysis_ts' not in db.calls[-1][1].columns and db.calls[0][1]['notes'].isna().all()


# ── The three notes ────────────────────────────────────────────────────────

PUTS = ('PMK_L', 755.73, 759.90, 753.20)


def _earlier(*, high=759.737, low=755.73, fetched='08:20:33', built='08:30:50',
             calls=('PMK_H', 759.737, 758.10, 762.63), puts=PUTS, run_kind='live') -> dict:
    """A row in force, in the shape _read_rows_in_force returns."""
    built_at = datetime.fromisoformat(f'{D} {built}').replace(tzinfo=ET)
    return {'run_kind': run_kind, 'analysis_ts': _utc('08:30:54'),
            'built_at': built_at.isoformat(), 'built': _utc(built),
            'fetched_at': _utc(fetched) if fetched else None, 'pre_high': high, 'pre_low': low,
            'calls_trigger_name': calls[0], 'calls_trigger_price': calls[1],
            'calls_stop_price': calls[2], 'calls_t1_price': calls[3],
            'puts_trigger_name': puts[0], 'puts_trigger_price': puts[1],
            'puts_stop_price': puts[2], 'puts_t1_price': puts[3]}


def _bare_row(analysis_ts='08:30:54') -> dict:
    """A row in force with no level_basis: its write time is all it has."""
    row = _earlier(fetched=None, high=None, low=None)
    row.update(analysis_ts=_utc(analysis_ts), built_at=None, built=_utc(analysis_ts))
    return row


def _late_entry(*, high=762.693, low=755.73, fetched='09:20:40',
                calls=('PMK_H', 762.693, 758.10, 763.04), puts=PUTS) -> dict:
    """One ticker of a late brief."""
    return {'level_basis': {'premarket_status': 'ok',
                            'premarket': {'fetched_at': _utc(fetched).isoformat(),
                                          'pre_high': high, 'pre_low': low}},
            'calls_trigger_name': calls[0], 'calls_trigger_price': calls[1],
            'calls_stop_price': calls[2], 'calls_t1_price': calls[3],
            'puts_trigger_name': puts[0], 'puts_trigger_price': puts[1],
            'puts_stop_price': puts[2], 'puts_t1_price': puts[3]}


def _note(*, earlier: dict, late: dict, history_recorded=True):
    """(payload, description) of the levels-updated note for a write at
    09:21:30 Eastern."""
    result = pb.LateSlotWrite(CLOCK, list(late), earlier)
    result.outcome, result.written_at, result.history_recorded = 'applied', _utc('09:21:30'), history_recorded
    payload = pb.format_levels_updated_note(D, earlier, {'tickers': late}, result)
    (embed,) = payload['embeds']
    return payload, embed['description']


def _block_of(desc: str, ticker: str) -> str:
    lines, out = desc.splitlines(), []
    for line in lines:
        if line.startswith(f'{ticker}  '):
            out = [line]
        elif out and line.startswith(' '):
            out.append(line)
        elif out:
            break
    return '\n'.join(out)


class TestLevelsUpdatedNote:
    def test_the_spec_example(self):
        payload, text = _note(earlier={'SPY': _earlier()}, late={'SPY': _late_entry()})
        assert 'premarket high $759.74 to $762.69, low $755.73 unchanged' in text
        assert '(fetched 08:20, 09:20; earlier row built 08:30:50 ET)' in text
        assert 'calls: trigger PMK_H $759.74 to PMK_H $762.69; first target $762.63 to $763.04' in text
        assert 'puts:' not in text and 'stop' not in text
        assert payload['embeds'][0]['title'] == 'Levels updated: Fri Nov 13, 09:21 ET'
        assert text.splitlines()[0].startswith('SPY  premarket high')

    def test_the_same_cent_is_unchanged(self):
        same = ('PMK_H', 759.7401, 758.10, 762.63)
        _, text = _note(earlier={'SPY': _earlier()},
                        late={'SPY': _late_entry(high=759.7401, calls=same)})
        assert 'premarket high $759.74 unchanged, low $755.73 unchanged' in text
        assert 'trigger, stop and first target unchanged' in text and 'calls:' not in text
        assert 'puts:' not in text

    def test_a_new_name_at_the_same_price_is_a_change(self):
        _, text = _note(earlier={'SPY': _earlier()},
                        late={'SPY': _late_entry(calls=('PDH', 759.737, 758.10, 762.63))})
        assert 'calls: trigger PMK_H $759.74 to PDH $759.74' in text
        assert 'unchanged\n' not in text.split('(fetched')[1]      # no "unchanged" phrase line

    def test_a_puts_change_is_listed_on_its_side(self):
        _, text = _note(earlier={'SPY': _earlier()},
                        late={'SPY': _late_entry(calls=('PMK_H', 759.737, 758.10, 762.63),
                                                 puts=('PMK_L', 755.73, 762.693, 753.20))})
        assert 'puts: stop $759.90 to $762.69' in text and 'calls:' not in text

    @pytest.mark.parametrize('missing', [None, float('nan')])
    def test_a_missing_price_is_na_never_zero(self, missing):
        gone = ('PMK_L', 755.73, 759.90, missing)       # the puts first target, missing on both sides
        _, text = _note(
            earlier={'SPY': _earlier(calls=('PMK_H', 759.737, missing, 762.63), puts=gone)},
            late={'SPY': _late_entry(calls=('PMK_H', 759.737, 758.10, 762.63), puts=gone)})
        assert 'stop N/A to $758.10' in text
        assert '$nan' not in text and '$0.00' not in text and 'first target N/A to N/A' not in text
        assert 'puts:' not in text

    @pytest.mark.parametrize('missing', [None, float('nan')])
    def test_a_missing_premarket_value_is_na(self, missing):
        _, text = _note(earlier={'SPY': _earlier(high=missing, low=missing)},
                        late={'SPY': _late_entry(low=missing)})
        assert 'premarket high N/A to $762.69, low N/A unchanged' in text
        assert '$nan' not in text and '$0.00' not in text

    def test_a_missing_name_prints_none(self):
        _, text = _note(earlier={'SPY': _earlier(calls=(None, None, None, None))},
                        late={'SPY': _late_entry()})
        assert 'calls: trigger none N/A to PMK_H $762.69; stop N/A to $758.10; first target N/A to $763.04' in text

    def test_no_earlier_row_is_shown_in_full(self):
        _, text = _note(earlier={}, late={'SPY': _late_entry()})
        assert 'SPY  no earlier row for the session; premarket high $762.69, low $755.73 (fetched 09:20)' in text
        assert 'calls: trigger PMK_H $762.69; stop $758.10; first target $763.04' in text
        assert 'puts: trigger PMK_L $755.73; stop $759.90; first target $753.20' in text

    def test_an_earlier_row_with_no_basis_gives_its_write_time(self):
        _, text = _note(earlier={'SPY': _bare_row()}, late={'SPY': _late_entry()})
        assert 'premarket high N/A to $762.69, low N/A to $755.73' in text
        assert '(fetched N/A, 09:20; earlier row built 08:30:54 ET)' in text

    def test_blocks_follow_the_brief_order(self):
        late = {t: _late_entry() for t in ('SPY', 'IWM', 'QQQ')}
        _, text = _note(earlier={t: _earlier() for t in late}, late=late)
        firsts = [line.split('  ')[0] for line in text.splitlines() if not line.startswith(' ')]
        assert firsts == ['SPY', 'IWM', 'QQQ']

    def test_twelve_tickers_stay_inside_discord(self):
        import json
        tickers12 = [f'T{i:02d}' for i in range(12)]
        earlier = {t: _earlier(high=41759.737, low=41755.73,
                               calls=('PMK_H', 41759.737, 41758.10, 41762.63),
                               puts=('PMK_L', 41755.73, 41759.90, 41753.20)) for t in tickers12}
        late = {t: _late_entry(high=41762.693, low=41754.11,
                               calls=('PDH', 41762.693, 41757.20, 41763.04),
                               puts=('PDL', 41754.11, 41762.693, 41751.00)) for t in tickers12}
        payload, desc = _note(earlier=earlier, late=late)
        assert len(desc) <= 4096 and len(json.dumps(payload)) <= 6000
        shown = [t for t in tickers12 if f'{t}  premarket high' in desc]
        assert shown == tickers12[:len(shown)] and 0 < len(shown) < 12
        assert f'{12 - len(shown)} more ticker(s) not shown.' in desc
        for t in shown:
            block = _block_of(desc, t)
            assert f'{t}  premarket high' in block and 'puts: trigger' in block     # never cut inside a block
            assert 'calls: trigger PMK_H $41,759.74 to PDH $41,762.69' in block

    def test_three_tickers_drop_nothing(self):
        late = {t: _late_entry() for t in T}
        _, text = _note(earlier={t: _earlier() for t in T}, late=late)
        assert 'not shown' not in text and all(f'{t}  premarket high' in text for t in T)

    def test_an_unrecorded_history_row_is_said(self):
        _, text = _note(earlier={'SPY': _earlier()}, late={'SPY': _late_entry()},
                        history_recorded=False)
        assert text.rstrip().endswith('History row not recorded: the late build is in the job log.')

    def test_a_recorded_history_row_is_not_mentioned(self):
        _, text = _note(earlier={'SPY': _earlier()}, late={'SPY': _late_entry()})
        assert 'History row' not in text


class TestLateNotAppliedNote:
    def test_lines(self):
        payload = pb.format_late_not_applied_note(
            D, 'snapshot_not_ready', 'no usable snapshot by 09:27:00 ET for QQQ (no row)',
            {'SPY': _earlier(), 'IWM': _bare_row(analysis_ts='08:30:54')}, T)
        lines = payload['embeds'][0]['description'].splitlines()
        assert lines[0] == 'snapshot_not_ready: no usable snapshot by 09:27:00 ET for QQQ (no row)'
        assert 'SPY: row in force built 08:30:50 ET on the snapshot fetched 08:20:33 ET' in lines
        assert 'IWM: row in force built 08:30:54 ET, no premarket snapshot recorded' in lines
        assert 'QQQ: no row for the session' in lines
        assert lines[1:] == [next(line for line in lines if line.startswith(f'{t}:')) for t in T]
        assert payload['embeds'][0]['title'] == 'Late levels not applied: Fri Nov 13'

    def test_a_long_reason_stays_inside_discord(self):
        import json
        tickers = [f'T{i:03d}' for i in range(200)]
        reason = 'no usable snapshot by 09:27:00 ET for ' + ', '.join(f'{t} (stamp 08:20:33)' for t in tickers)
        payload = pb.format_late_not_applied_note(D, 'snapshot_not_ready', reason,
                                                  {t: _earlier() for t in tickers}, tickers)
        desc = payload['embeds'][0]['description']
        assert len(desc) <= 4096 and len(json.dumps(payload)) <= 6000
        assert desc.startswith('snapshot_not_ready: no usable snapshot by 09:27:00 ET for T000')
        assert 'more ticker(s) not shown.' in desc

    def test_run_failed(self):
        payload = pb.format_late_run_failed_note(KeyError('x'))
        assert payload['embeds'][0]['description'] == \
            'Late brief run failed (KeyError). Check the brief row before the open.'
        assert set(payload['embeds'][0]) == {'title', 'description', 'color'}


# ── The late flow, end to end ──────────────────────────────────────────────

def _cents(value) -> int:
    from lib.strat_levels import price_cents
    return price_cents(value)


def _canonical(h) -> dict:
    return h.tables['premarket_analysis']


def _late_record(caplog, outcome: str) -> str:
    """The one `late_slot outcome=<outcome>` log record of a run."""
    (record,) = [r for r in caplog.records if f'late_slot outcome={outcome}' in r.getMessage()]
    assert record.levelno == logging.INFO
    return record.getMessage()


class TestLateSlotEndToEnd:
    def test_late_run_rewrites_the_early_rows(self, harness, caplog):
        h = harness
        h.snapshot(stamp=EARLY_STAMP, up=0.6)
        assert h.run('2026-11-13 08:30:50') is None
        early = copy.deepcopy(_canonical(h))
        sent, writes = len(h.sent), len(h.writes)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert h.run('2026-11-13 09:21:30', late=True) == 0
        for t in TICKERS:
            row, was = _canonical(h)[(SESSION, t)], early[(SESSION, t)]
            assert row['run_kind'] == 'live' and row['analysis_ts'] == h.at('2026-11-13 09:21:30')
            assert was['analysis_ts'] == h.at('2026-11-13 08:30:50')
            assert row['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
            assert row['calls_trigger_name'] == 'PMK_H' and row['llm_analysis'] is None   # BRIEF_LLM_DISABLE=1
            assert _cents(row['calls_trigger_price']) == _cents(was['calls_trigger_price']) + 30
            assert _cents(row['puts_stop_price']) == _cents(was['puts_stop_price']) + 30
            for col in LEVEL_COLUMNS:
                assert row[col] == h.last_brief['tickers'][t][col]
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == 3
        assert {(r['run_kind'], r['triggered_by'], r['notes']) for r in late_history} == {
            ('scheduled', 'cloud-scheduler:premarket-brief-late', 'LATE_SLOT_APPLIED')}
        # One message, to the main webhook; nothing to the earnings webhook.
        assert [url for url, _ in h.sent[sent:]] == [MAIN_HOOK]
        (embed,) = h.sent[-1][1]['embeds']
        assert embed['title'] == 'Levels updated: Fri Nov 13, 09:21 ET'
        for t in TICKERS:
            assert f'{t}  premarket high' in embed['description']
            assert f'(fetched 08:20, 09:20; earlier row built {h.built_was[t]} ET)' in embed['description']
        assert h.writes[writes:] == [('upsert', 'premarket_analysis'),
                                     ('insert', 'premarket_analysis_history')]
        assert (h.stamp_reads, h.row_reads) == (1, 2)
        record = _late_record(caplog, 'applied')
        for part in ('session=2026-11-13', 'tickers=IWM,QQQ,SPY', 'polls=1', 'waited_s=0',
                     'stamps=IWM=09:20:40,QQQ=09:20:40,SPY=09:20:40', 'applied=True'):
            assert part in record

    @pytest.mark.parametrize('moved,status,named', [
        ((), {}, {'IWM': 'stamp 08:20:33', 'QQQ': 'stamp 08:20:33', 'SPY': 'stamp 08:20:33'}),
        (('SPY',), {}, {'IWM': 'stamp 08:20:33', 'QQQ': 'stamp 08:20:33'}),
        (TICKERS, {'QQQ': 'level_params_unavailable'}, {'QQQ': 'status level_params_unavailable'})],
        ids=['no-stamp-moves', 'one-stamp-moves', 'one-unfiltered'])
    def test_no_late_snapshot_leaves_the_early_levels(self, harness, caplog, moved, status, named):
        h = harness
        before = _After(h)
        for t in moved:
            h.snapshot((t,), stamp=LATE_STAMP, up=0.9, status=status.get(t, 'ok'))
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            # the sleep double walks the clock past 09:27:00
            assert h.run('2026-11-13 09:20:30', late=True) == 1
        assert h.generated == 1 and len(h.strat_levels) == before.levels        # the early build only
        assert before.unchanged(h) and h.writes[before.writes:] == []
        assert h.stamp_reads == 78 and [u for u, _ in h.sent[before.sent:]] == [MAIN_HOOK]
        assert h.now == h.at('2026-11-13 09:27:00')
        lines = _note_lines(h)
        assert lines[0].startswith('snapshot_not_ready: no usable snapshot by 09:27:00 ET for ')
        for t in TICKERS:
            if t in named:
                assert f'{t} ({named[t]})' in lines[0]
            else:
                assert f'{t} (' not in lines[0]
            assert _in_force_line(h, t) in lines
        assert h.sent[-1][1]['embeds'][0]['title'] == 'Late levels not applied: Fri Nov 13'
        record = _late_record(caplog, 'snapshot_not_ready')
        assert 'polls=78 waited_s=390' in record and 'applied=False' in record


class TestLateSlotRows:
    def test_no_earlier_row(self, harness):
        harness.snapshot(stamp=LATE_STAMP, up=0.9)
        assert harness.run('2026-11-13 09:21:30', late=True) == 0
        text = harness.sent[-1][1]['embeds'][0]['description']
        assert len(harness.sent) == 1
        for t in TICKERS:
            row = _canonical(harness)[(SESSION, t)]
            assert row['run_kind'] == 'live' and f'{t}  no earlier row for the session' in text
            for col in ('calls_trigger_price', 'calls_stop_price', 'calls_t1_price',
                        'puts_trigger_price', 'puts_stop_price', 'puts_t1_price'):
                assert pb._fmt_price(row[col]) in text
            pm = row['level_basis']['premarket']
            assert pb._fmt_price(pm['pre_high']) in text and pb._fmt_price(pm['pre_low']) in text
        assert {r['notes'] for r in harness.tables['premarket_analysis_history']} == {'LATE_SLOT_APPLIED'}

    def test_a_replay_row_becomes_live(self, harness):
        h = harness
        h.snapshot(stamp=EARLY_STAMP)
        assert h.run('2026-11-13 08:30:50') is None
        for row in _canonical(h).values():
            row['run_kind'] = 'replay'
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        assert {r['run_kind'] for r in _canonical(h).values()} == {'live'}
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
                   for r in _canonical(h).values())

    def test_an_operators_update_row_is_replaced(self, harness):
        h = harness
        h.snapshot(stamp=EARLY_STAMP)
        assert h.run('2026-11-13 08:30:50') is None
        assert h.run('2026-11-13 08:50:00', env={'BRIEF_UPDATE': 'true'}) is None
        # the operator's overwrite does not move analysis_ts
        assert all(r['analysis_ts'] == h.at('2026-11-13 08:30:50') for r in _canonical(h).values())
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        assert all(r['analysis_ts'] == h.at('2026-11-13 09:21:30') for r in _canonical(h).values())
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
                   for r in _canonical(h).values())

    def test_a_hand_started_late_run_applies_as_manual_replay(self, harness):
        h = harness
        h.snapshot(stamp=EARLY_STAMP)
        assert h.run('2026-11-13 08:30:50') is None
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run('2026-11-13 09:21:30', late=True, env={'BRIEF_TRIGGERED_BY': 'operator:late'}) == 0
        history = h.tables['premarket_analysis_history']
        assert {(r['run_kind'], r['notes']) for r in history[3:]} == {('manual_replay', 'LATE_SLOT_APPLIED')}
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
                   for r in _canonical(h).values())

    @pytest.mark.parametrize('off', [{'env': {'BRIEF_POST_TO_DISCORD': 'false'}},
                                     {'argv': ['--no-discord']}])
    def test_posting_turned_off_prints_and_exits_0(self, harness, capsys, off):
        harness.snapshot(stamp=LATE_STAMP, up=0.9)
        assert harness.run('2026-11-13 09:21:30', late=True, **off) == 0
        assert harness.sent == [] and harness.send_attempts == 0
        assert 'Levels updated' in capsys.readouterr().out
        assert len(_canonical(harness)) == 3

    def test_no_brief_tickers_is_an_error(self, harness, monkeypatch):
        harness.snapshot(stamp=LATE_STAMP, up=0.9)
        real_install = harness._install

        def install():
            real_install()
            monkeypatch.setattr(pb, '_resolve_brief_tickers', lambda default: [])

        harness._install = install
        with pytest.raises(RuntimeError, match='no brief tickers'):
            harness.run('2026-11-13 09:21:30', late=True)
        assert harness.writes == [] and harness.stamp_reads == 0 and harness.generated == 0


class TestLateSlotSessionGate:
    @pytest.mark.parametrize('at', ['2026-11-26 09:20:30', '2026-11-14 09:20:30'])
    def test_holiday_and_weekend_exit_clean(self, harness, caplog, at):     # the real is_session
        harness.snapshot(stamp=LATE_STAMP)
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert harness.run(at, late=True) == 0
        assert (harness.queries, harness.generated, harness.writes, harness.sent) == (0, 0, [], [])
        assert harness.send_attempts == 0
        record = _late_record(caplog, 'not_session')
        for part in (f'session={at[:10]}', 'tickers=-', 'polls=0', 'waited_s=0', 'stamps=-',
                     'applied=False'):
            assert part in record

    def test_a_half_day_passes_the_gate(self, make_harness):
        h = make_harness(session='2026-11-27', last_bar='2026-11-25')
        h.snapshot(stamp='2026-11-27 09:20:10')
        assert h.run('2026-11-27 09:20:30', late=True) == 0
        assert h.stamp_reads >= 1
        assert sorted(_canonical(h)) == [('2026-11-27', t) for t in TICKERS]


# ── Every late run that does not apply ─────────────────────────────────────

class _After:
    """The state after the early run of 08:30:50 on the 08:20 snapshot."""

    def __init__(self, h):
        h.snapshot(stamp=EARLY_STAMP)
        assert h.run('2026-11-13 08:30:50') is None
        self.tables = copy.deepcopy(h.tables)
        self.sent, self.writes, self.levels = len(h.sent), len(h.writes), len(h.strat_levels)
        self.attempts = h.send_attempts

    def unchanged(self, h) -> bool:
        """Both brief tables are as the early run left them (the stamp
        table is left out: the tests move it)."""
        return all(h.tables[name] == self.tables[name]
                   for name in ('premarket_analysis', 'premarket_analysis_history'))


def _note_lines(h) -> list:
    (embed,) = h.sent[-1][1]['embeds']
    return embed['description'].splitlines()


def _in_force_line(h, ticker: str) -> str:
    return f'{ticker}: row in force built {h.built(ticker)} ET on the snapshot fetched 08:20:33 ET'


class TestLateSlotCutoff:
    @pytest.mark.parametrize('at,outcome,reason', [
        ('2026-11-13 09:29:30', 'past_cutoff',
         'started 09:29:30 ET, at or after the write cutoff 09:29:30 ET'),
        ('2026-11-13 09:35:00', 'past_cutoff',
         'started 09:35:00 ET, at or after the write cutoff 09:29:30 ET'),
        ('2026-11-13 09:19:59', 'before_slot',
         'started 09:19:59 ET, before the slot opens at 09:20:00 ET')])
    def test_outside_the_window_at_the_first_check(self, harness, caplog, at, outcome, reason):
        h = harness
        before = _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert h.run(at, late=True) == 1
        assert (h.stamp_reads, h.generated, len(h.strat_levels)) == (0, 1, before.levels)
        assert before.unchanged(h) and h.writes[before.writes:] == []
        assert [u for u, _ in h.sent[before.sent:]] == [MAIN_HOOK]
        lines = _note_lines(h)
        assert lines[0] == f'{outcome}: {reason}'
        for t in TICKERS:
            assert _in_force_line(h, t) in lines
        record = _late_record(caplog, outcome)
        assert 'polls=0' in record and 'applied=False' in record

    def test_the_cutoff_passes_between_the_wait_and_the_write(self, harness):
        h = harness
        before = _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        h.hooks['generate'] = lambda h: h.set_clock('2026-11-13 09:29:30')
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert _canonical(h) == before.tables['premarket_analysis']
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == 3
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: past_cutoff') for r in late_history)
        assert _note_lines(h)[0] == ('past_cutoff: write check at 09:29:30 ET, at or after the '
                                     'write cutoff 09:29:30 ET')
        assert len(h.sent) == before.sent + 1
        assert h.writes[before.writes:] == [('insert', 'premarket_analysis_history')]

    def test_one_second_before_the_cutoff_writes(self, harness):
        h = harness
        _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        h.hooks['generate'] = lambda h: h.set_clock('2026-11-13 09:29:29')
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        assert all(r['analysis_ts'] == h.at('2026-11-13 09:29:29') for r in _canonical(h).values())
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
                   for r in _canonical(h).values())


class TestLateSlotRepeat:
    def test_a_second_late_run_on_the_same_stamps_does_nothing(self, harness, caplog):
        h = harness
        _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        after = copy.deepcopy(h.tables)
        writes_after, sent_after, levels_after = list(h.writes), list(h.sent), len(h.strat_levels)
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert h.run('2026-11-13 09:24:00', late=True) == 0
        assert h.tables == after and h.writes == writes_after and h.sent == sent_after
        assert h.generated == 2 and len(h.strat_levels) == levels_after
        record = _late_record(caplog, 'already_current')
        assert 'tickers=IWM,QQQ,SPY' in record and 'applied=False' in record

    def test_one_newer_stamp_rebuilds_all(self, harness):
        h = harness
        _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        h.snapshot(('QQQ',), stamp='2026-11-13 09:23:10', up=0.9)
        assert h.run('2026-11-13 09:24:00', late=True) == 0
        assert all(r['analysis_ts'] == h.at('2026-11-13 09:24:00') for r in _canonical(h).values())
        assert len(h.tables['premarket_analysis_history']) == 9
        assert h.generated == 3


class TestLateSlotRefusals:
    @pytest.mark.parametrize('edit,rows', [
        (lambda b: b['tickers']['QQQ']['level_basis'].update(premarket_status='premarket_unfiltered'), 3),
        (lambda b: b['tickers']['QQQ']['level_basis']['premarket'].update(
            fetched_at='2026-11-13T13:20:33.123456+00:00'), 3),
        (lambda b: b['tickers']['QQQ'].update(status='NO DATA'), 2),   # a NO DATA ticker builds no row
        (lambda b: b['tickers']['QQQ'].update(status='STALE_DAILY_DATA'), 3),
        (lambda b: b['tickers']['QQQ'].update(status='PLAYBOOK_FAILED'), 3)],
        ids=['unfiltered', 'early-snapshot', 'no-data', 'stale', 'playbook-failed'])
    def test_a_build_that_cannot_be_used(self, harness, edit, rows):
        h = harness
        before = _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        h.hooks['built'] = lambda h, brief: edit(brief)
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert _canonical(h) == before.tables['premarket_analysis']
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == rows
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: build_not_usable')
                   for r in late_history)
        assert h.writes[before.writes:] == [('insert', 'premarket_analysis_history')]
        lines = _note_lines(h)
        assert lines[0].startswith('build_not_usable: QQQ: ') and len(h.sent) == before.sent + 1
        for t in TICKERS:
            assert _in_force_line(h, t) in lines

    @pytest.mark.parametrize('change', [
        {'run_kind': 'replay'}, {'analysis_ts': '2026-11-13 09:22:00'},
        {'built_at': '2026-11-13T09:22:00-05:00'}], ids=['run_kind', 'analysis_ts', 'built_at'])
    def test_a_row_changed_under_the_run(self, harness, change):
        h = harness
        before = _After(h)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        state = {}

        def another_writer(h):       # lands while this run builds
            row = _canonical(h)[(SESSION, 'SPY')]
            if 'run_kind' in change:
                row['run_kind'] = change['run_kind']
            if 'analysis_ts' in change:
                row['analysis_ts'] = h.at(change['analysis_ts'])
            if 'built_at' in change:
                row['level_basis']['built_at'] = change['built_at']
            state['changed'] = copy.deepcopy(_canonical(h))

        h.hooks['generate'] = another_writer
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert _canonical(h) == state['changed']                       # nothing rewritten
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == 3
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: row_changed') for r in late_history)
        assert h.writes[before.writes:] == [('insert', 'premarket_analysis_history')]
        lines = _note_lines(h)
        assert lines[0] == 'row_changed: changed since this run read them: SPY'
        assert _in_force_line(h, 'SPY') in lines and len(h.sent) == before.sent + 1
