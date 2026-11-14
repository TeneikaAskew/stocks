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
