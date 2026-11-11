"""The retired EarningsWhispers score: recommendations are unavailable, not
derived from the archetype alone (RETIREMENT-DESIGN 3.3-3.4).

``earnings_calendar.score`` had one writer, EarningsWhispers. With it
retired, ``refresh_daily`` writes playability_score, quintile,
confidence_label and both recommended structures as NULL on every row,
while archetype, implied_move_pct, the lean stats and last_3_events keep
their non-EW values. The fixture is a bullish_trend ticker under an
over-priced calibration with a 20% implied move: on main the EW score 85
gives Q5 -> SKIP / IC, and the same loop with the score merely missing
would give LONG CALL / CALL. Neither may reach the table.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from gcp import refresh_earnings_views as rev
from lib.earnings_reactions import (
    confidence_label, recommended_structure, score_quintile,
)
from tests.fixtures.earnings_calendar_sources import (
    av, ew_only, hydrated, make_db, run_earnings_sql, uw,
)

TODAY = date.today()
D = TODAY + timedelta(days=2)
RETIRED_FIELDS = ('playability_score', 'quintile', 'confidence_label',
                  'recommended_structure_long_only', 'recommended_structure_ic_mode')
OVER_PRICED = {'realized_vs_implied_ratio': 0.636, 'avg_short_strangle_pnl_pct': 20.3}


def _lean(ticker, gap):
    return {'ticker': ticker, 'total_quarters': 12, 'n_beats': 9, 'n_meets': 1,
            'n_misses': 2, 'beat_rate_pct': 75.0, 'avg_abs_gap_pct': 6.0,
            'avg_gap_pct': gap, 'dir_consistency_pct': 80.0,
            'reversal_rate_pct': 10.0, 'avg_ratio': 1.1, 'lean_score': 0.4,
            'long_winner_count': 3, 'short_winner_count': 1}


def run_refresh(monkeypatch, *, lean=None) -> pd.DataFrame:
    """refresh_daily over the fixture; returns the upserted frame."""
    rows = [
        # BULL: bullish_trend; EW row (score 85) on the same date.
        av('BULL', D), uw('BULL', D, expected_move=20.0),
        hydrated(ew_only('BULL', D)),
        # BEAR: bearish_trend variant.
        av('BEAR', D), uw('BEAR', D, expected_move=20.0),
        hydrated(ew_only('BEAR', D)),
        # NOLEAN: no lean row -> archetype None.
        av('NOLEAN', D), uw('NOLEAN', D, expected_move=20.0),
        hydrated(ew_only('NOLEAN', D)),
    ]
    market = [{'ticker': t, 'date': TODAY - timedelta(days=1), 'close': 100.0}
              for t in ('BULL', 'BEAR', 'NOLEAN')]
    conn = make_db(rows, market)
    lean = lean if lean is not None else [_lean('BULL', 3.0), _lean('BEAR', -3.0)]
    last3 = pd.DataFrame([{'ticker': 'BULL', 'reported_date': date(2026, 7, 30),
                           'beat_meet_miss': 'beat', 'reaction_gap_pct': 4.0,
                           'eps_surprise_pct': 5.0, 'realized_vs_implied_ratio': 1.2}])
    state = {}

    def query(sql, params=None):
        if 'FROM earnings_calendar' in sql:
            return run_earnings_sql(conn, sql, params, today=TODAY)
        if 'FROM earnings_ticker_lean' in sql:
            return pd.DataFrame(lean)
        if 'FROM earnings_event_outcomes' in sql:
            return last3.copy()
        if 'FROM earnings_calibration' in sql:
            return pd.DataFrame([OVER_PRICED])
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    def replace(df, refresh_date):
        assert refresh_date == TODAY
        state['df'] = df.copy()
        return len(df)

    from gcp import database
    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'query_to_dataframe', query)
    monkeypatch.setattr(rev, 'query_to_dataframe', query)
    monkeypatch.setattr(rev, 'execute_sql', lambda *a, **k: None)
    monkeypatch.setattr(rev, '_replace_upcoming_rows', replace)
    rev.refresh_daily(14)
    return state['df']


def _rows(df) -> dict:
    return {r['ticker']: r for r in df.to_dict('records')}


def test_retired_fields_are_null_on_every_row(monkeypatch):
    rows = _rows(run_refresh(monkeypatch))
    assert set(rows) == {'BULL', 'BEAR', 'NOLEAN'}
    for tk, r in rows.items():
        for f in RETIRED_FIELDS:
            assert r[f] is None, (tk, f, r[f])


def test_bullish_over_priced_is_never_a_long_entry(monkeypatch):
    bull = _rows(run_refresh(monkeypatch))['BULL']
    assert bull['recommended_structure_long_only'] not in ('SKIP', 'LONG CALL')
    assert bull['recommended_structure_ic_mode'] not in ('IC', 'CALL')
    assert bull['recommended_structure_long_only'] is None
    assert bull['recommended_structure_ic_mode'] is None


def test_bearish_variant_is_never_a_long_put(monkeypatch):
    bear = _rows(run_refresh(monkeypatch))['BEAR']
    assert bear['archetype'] == 'bearish_trend'
    assert bear['recommended_structure_long_only'] is None
    assert bear['recommended_structure_ic_mode'] is None


def test_archetype_implied_move_lean_and_last3_are_kept(monkeypatch):
    rows = _rows(run_refresh(monkeypatch))
    bull = rows['BULL']
    assert bull['archetype'] == 'bullish_trend'
    assert bull['expected_move'] == 20.0
    assert bull['prev_close'] == 100.0
    assert bull['implied_move_pct'] == pytest.approx(20.0)
    assert bull['total_quarters'] == 12
    assert bull['dir_consistency_pct'] == 80.0
    assert bull['lean_score'] == 0.4
    assert bull['long_winner_count'] == 3
    assert bull['last_3_events'] == [{
        'date': '2026-07-30', 'beat_meet_miss': 'beat', 'gap_pct': 4.0,
        'eps_surprise_pct': 5.0, 'ratio': 1.2, 'daily_path_v1': None,
    }]
    nolean = rows['NOLEAN']
    assert pd.isna(nolean['archetype'])
    assert pd.isna(nolean['total_quarters'])


def test_main_loop_negative_control():
    """What the NULL contract avoids, pinned on the unchanged library: with
    the EW score the fixture is SKIP / IC; with the score merely missing the
    same calls turn it into a long entry. lib.earnings_reactions is not
    changed by the retirement."""
    score = 85.0
    q = score_quintile(score)
    assert (q, confidence_label(score)) == ('Q5', confidence_label(85.0))
    assert recommended_structure('bullish_trend', q, OVER_PRICED,
                                 implied_move_pct=20.0, long_only=True) == 'SKIP'
    assert recommended_structure('bullish_trend', q, OVER_PRICED,
                                 implied_move_pct=20.0, long_only=False) == 'IC'
    missing = score_quintile(None)
    assert missing is None
    assert recommended_structure('bullish_trend', missing, OVER_PRICED,
                                 implied_move_pct=20.0, long_only=True) == 'LONG CALL'
    assert recommended_structure('bullish_trend', missing, OVER_PRICED,
                                 implied_move_pct=20.0, long_only=False) == 'CALL'
    assert recommended_structure('bearish_trend', missing, OVER_PRICED,
                                 implied_move_pct=20.0, long_only=True) == 'LONG PUT'
