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
