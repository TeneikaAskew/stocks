"""The late slot's overwrite of premarket_analysis, against a real Postgres.

FEAT-PLAYBOOK-001, docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-late-slot.md.

The hermetic tests answer gcp.database from in-memory tables that are told
how Postgres behaves. This one asks Postgres: the real
gcp.premarket_brief.persist_to_cloud_sql and gcp.database.upsert_dataframe
run against the schema of gcp/schema.sql.

  * no overwrite moves analysis_ts unless the frame carries the column, and
    the late write does carry it (decision D);
  * the late write is ONE statement for every brief ticker (decision B);
  * the columns the frame does not carry (the signal monitor's put
    re-anchor, the resolver's outcome) are left as they are;
  * a late row never keeps the early model text;
  * a scheduled early-slot write still changes no canonical column.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import pytest
import sqlalchemy

from gcp import premarket_brief as pb

D = date(2026, 11, 13)
TICKERS = ['IWM', 'QQQ', 'SPY']
EARLY = '2026-11-13T13:20:33.123456+00:00'      # 08:20:33 America/New_York
LATE = '2026-11-13T14:20:40.500000+00:00'       # 09:20:40 America/New_York
INSTANT = datetime.fromisoformat('2026-11-13T14:22:00+00:00')   # 09:22:00, the write check


def _brief(trigger: float, fetched: str, *, llm=None) -> dict:
    """A three-ticker brief dated D whose calls trigger is `trigger` and
    whose level_basis records the premarket snapshot fetched at `fetched`."""
    return {
        'analysis_date': D, 'llm_overview': llm, 'llm_orb_explanation': llm,
        'tickers': {t: {
            'price': 758.0, 'rsi': 51.2, 'signal_status': 'NEUTRAL',
            'strat_candle': '2U', 'strat_combo': '', 'playbook': f'CALLS above {trigger:.2f}',
            'calls_trigger_name': 'PMK_H', 'calls_trigger_price': trigger,
            'calls_stop_name': 'PDC', 'calls_stop_price': 755.10,
            'calls_t1_price': trigger + 1.5, 'calls_plan_t1_price': trigger + 3.0,
            'puts_trigger_name': 'PMK_L', 'puts_trigger_price': 752.30,
            'puts_stop_name': 'PMK_H', 'puts_stop_price': trigger,
            'puts_t1_price': 750.0,
            'llm_analysis': llm, 'llm_playbook': llm,
            'level_basis': {'built_at': f'2026-11-13T{"08:30:50" if fetched == EARLY else "09:21:40"}-05:00',
                            'premarket_status': 'ok',
                            'premarket': {'date': '2026-11-13', 'fetched_at': fetched,
                                          'pre_high': trigger, 'pre_low': 752.30}},
        } for t in TICKERS}}


def _null(value):
    if value is None or isinstance(value, (dict, list, str)):
        return value
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value


@contextmanager
def _statements(engine):
    """The SQL text of every statement the engine sends inside the block."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    sqlalchemy.event.listen(engine, 'before_cursor_execute', record)
    try:
        yield seen
    finally:
        sqlalchemy.event.remove(engine, 'before_cursor_execute', record)


def test_late_overwrite_on_postgres(clean_db, run_sql, db_engine, monkeypatch):
    for key in ('BRIEF_AS_OF', 'BRIEF_UPDATE', 'BRIEF_RUN_SLOT'):
        monkeypatch.delenv(key, raising=False)
    # clean_db truncates premarket_analysis and not its history.
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text('TRUNCATE TABLE premarket_analysis_history RESTART IDENTITY'))

    def rows():
        frame = run_sql("SELECT * FROM premarket_analysis WHERE analysis_date = :d ORDER BY ticker",
                        {'d': D})
        return [{k: _null(v) for k, v in record.items()} for record in frame.to_dict('records')]

    def history_notes():
        frame = run_sql("SELECT notes FROM premarket_analysis_history "
                        "WHERE analysis_date = :d ORDER BY written_at, ticker", {'d': D})
        return [_null(v) for v in frame['notes']]

    # The early scheduled write, with model text.
    assert pb.persist_to_cloud_sql(_brief(759.737, EARLY, llm='early text'), run_kind='scheduled',
                                   triggered_by='cloud-scheduler:premarket-brief-daily') == 3
    # What the signal monitor and the resolver write later, set here by hand.
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text(
            "UPDATE premarket_analysis SET puts_reanchor_open = 101.5, "
            "outcome_resolved_at = '2026-11-13 21:15:00+00' WHERE analysis_date = '2026-11-13'"))
    before = rows()
    assert [r['ticker'] for r in before] == TICKERS
    assert all(r['llm_analysis'] == 'early text' and r['llm_overview'] == 'early text' for r in before)

    # The late write: the rows in force read through the production read,
    # then the one guarded statement.
    read = pb._read_rows_in_force(D, TICKERS)
    assert sorted(read) == TICKERS
    for ticker, old in zip(TICKERS, before):
        assert read[ticker]['run_kind'] == 'live'
        assert read[ticker]['analysis_ts'] == old['analysis_ts']
        assert read[ticker]['fetched_at'] == datetime.fromisoformat(EARLY)
        assert read[ticker]['built_at'] == '2026-11-13T08:30:50-05:00'
        assert (read[ticker]['calls_trigger_price'], read[ticker]['pre_high']) == (759.737, 759.737)
    assert not pb._rows_current(read, {t: datetime.fromisoformat(LATE) for t in TICKERS}, TICKERS)

    w = pb.LateSlotWrite(pb._late_slot_clock(D), TICKERS, read, now=lambda: INSTANT)
    with _statements(db_engine) as seen:
        assert pb.persist_to_cloud_sql(_brief(762.693, LATE), run_kind='scheduled',
                                       triggered_by='cloud-scheduler:premarket-brief-late',
                                       late_slot=w) == 3
    assert (w.outcome, w.history_recorded, w.written_at) == ('applied', True, INSTANT)
    # All tickers in ONE canonical statement (decision B).
    assert sum(s.lstrip().upper().startswith('INSERT INTO PREMARKET_ANALYSIS ') for s in seen) == 1

    after = rows()
    for old, new in zip(before, after):
        assert new['analysis_ts'] == INSTANT and old['analysis_ts'] != INSTANT     # decision D
        assert new['calls_trigger_price'] == 762.693 and new['run_kind'] == 'live'
        assert new['calls_t1_price'] == 762.693 + 1.5 and new['puts_stop_price'] == 762.693
        assert new['calls_plan_t1_price'] == 762.693 + 3.0
        basis = new['level_basis'] if isinstance(new['level_basis'], dict) else json.loads(new['level_basis'])
        assert basis['premarket']['fetched_at'] == LATE
        # Columns the frame does not carry are untouched.
        assert new['puts_reanchor_open'] == 101.5
        assert new['outcome_resolved_at'] == old['outcome_resolved_at'] is not None
        # A late row never keeps the early model text.
        for col in ('llm_overview', 'llm_orb_explanation', 'llm_analysis', 'llm_playbook'):
            assert old[col] == 'early text' and new[col] is None
    assert history_notes() == [None] * 3 + ['LATE_SLOT_APPLIED'] * 3

    # The rows now read as current against the late stamp.
    now_rows = pb._read_rows_in_force(D, TICKERS)
    assert pb._rows_current(now_rows, {t: datetime.fromisoformat(LATE) for t in TICKERS}, TICKERS)
    assert all(now_rows[t]['analysis_ts'] == INSTANT for t in TICKERS)

    # A second early-slot scheduled write still changes no canonical column.
    assert pb.persist_to_cloud_sql(_brief(770.0, LATE), run_kind='scheduled', triggered_by='x') == 0
    assert rows() == after


def test_a_late_write_past_the_cutoff_leaves_postgres_as_it_was(clean_db, run_sql, db_engine,
                                                                 monkeypatch):
    for key in ('BRIEF_AS_OF', 'BRIEF_UPDATE', 'BRIEF_RUN_SLOT'):
        monkeypatch.delenv(key, raising=False)
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text('TRUNCATE TABLE premarket_analysis_history RESTART IDENTITY'))

    def rows():
        frame = run_sql("SELECT * FROM premarket_analysis WHERE analysis_date = :d ORDER BY ticker",
                        {'d': D})
        return [{k: _null(v) for k, v in record.items()} for record in frame.to_dict('records')]

    assert pb.persist_to_cloud_sql(_brief(759.737, EARLY), run_kind='scheduled',
                                   triggered_by='cloud-scheduler:premarket-brief-daily') == 3
    before = rows()
    cutoff = datetime.fromisoformat('2026-11-13T14:29:30+00:00')
    w = pb.LateSlotWrite(pb._late_slot_clock(D), TICKERS, pb._read_rows_in_force(D, TICKERS),
                         now=lambda: cutoff)
    with _statements(db_engine) as seen:
        assert pb.persist_to_cloud_sql(_brief(762.693, LATE), run_kind='scheduled',
                                       triggered_by='cloud-scheduler:premarket-brief-late',
                                       late_slot=w) == 0
    assert w.outcome == 'past_cutoff'
    assert not any(s.lstrip().upper().startswith('INSERT INTO PREMARKET_ANALYSIS ') for s in seen)
    assert rows() == before
    notes = run_sql("SELECT notes FROM premarket_analysis_history WHERE analysis_date = :d "
                    "AND notes IS NOT NULL", {'d': D})['notes'].tolist()
    assert len(notes) == 3 and all(n.startswith('LATE_SLOT_NOT_APPLIED: past_cutoff') for n in notes)
