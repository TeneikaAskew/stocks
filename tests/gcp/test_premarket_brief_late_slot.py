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

import inspect
import socket
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from gcp import premarket_brief as pb  # noqa: E402


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
