"""FEAT-CATALYST-001: recommended_structure's implied_move_invalid keyword.

Contract: docs/superpowers/specs/2026-11-01-feat-catalyst-001-implied-move-invalid-guard-source-note.md
(approved successor of the 2026-10-31 spec merged as ca043892; done_when items 1 to 6
are byte-identical). The keyword is an explicit invalid-state
interface for a caller that saw an implied move that was present but not a
usable number. It is not an upstream data repair: no caller passes it yet.
"""
import itertools

import pytest

import lib.earnings_reactions as er
from lib.earnings_reactions import (
    _IC_RATIO_THRESHOLD,
    _IC_STRANGLE_THRESHOLD,
    recommended_structure,
)

ARCHETYPES = ('bullish_trend', 'bearish_trend', 'reversal_play', 'mixed', None)
QUINTILES = ('Q1', 'Q5', None)
IMPLIED = (None, 5.0, 20.0)
MODES = (True, False)

_UNDER = {'realized_vs_implied_ratio': 0.95, 'avg_short_strangle_pnl_pct': 3.0}
_OVER = {'realized_vs_implied_ratio': 0.636, 'avg_short_strangle_pnl_pct': 20.3}
CALIBRATIONS = {'none': None, 'under': _UNDER, 'over': _OVER}

_LONG = {
    'bullish_trend': 'LONG CALL',
    'bearish_trend': 'LONG PUT',
    'reversal_play': 'LONG STRDL',
    'mixed': 'LONG STRDL',
    None: None,
}
_DEFAULT = {
    'bullish_trend': 'CALL',
    'bearish_trend': 'PUT',
    'reversal_play': 'STRDL',
    'mixed': 'STRDL',
    None: None,
}

# Return values of recommended_structure on main d806bfd1 for every
# (archetype, score_quintile, calibration, implied_move_pct, long_only)
# combination, keyword omitted. Captured by running the d806bfd1 bytes of
# lib/earnings_reactions.py (identical to main 38ff5193) over the product of
# the axes above; long_only is always passed, so RECOMMEND_LONG_ONLY is not read.
MAIN_D806BFD1 = (
    ('bullish_trend', 'Q1', 'none', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'none', None, False, 'CALL'),
    ('bullish_trend', 'Q1', 'none', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'none', 5.0, False, 'CALL'),
    ('bullish_trend', 'Q1', 'none', 20.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'none', 20.0, False, 'CALL'),
    ('bullish_trend', 'Q1', 'under', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'under', None, False, 'CALL'),
    ('bullish_trend', 'Q1', 'under', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'under', 5.0, False, 'CALL'),
    ('bullish_trend', 'Q1', 'under', 20.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'under', 20.0, False, 'CALL'),
    ('bullish_trend', 'Q1', 'over', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'over', None, False, 'CALL'),
    ('bullish_trend', 'Q1', 'over', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'over', 5.0, False, 'CALL'),
    ('bullish_trend', 'Q1', 'over', 20.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q1', 'over', 20.0, False, 'CALL'),
    ('bullish_trend', 'Q5', 'none', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'none', None, False, 'CALL'),
    ('bullish_trend', 'Q5', 'none', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'none', 5.0, False, 'CALL'),
    ('bullish_trend', 'Q5', 'none', 20.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'none', 20.0, False, 'CALL'),
    ('bullish_trend', 'Q5', 'under', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'under', None, False, 'CALL'),
    ('bullish_trend', 'Q5', 'under', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'under', 5.0, False, 'CALL'),
    ('bullish_trend', 'Q5', 'under', 20.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'under', 20.0, False, 'CALL'),
    ('bullish_trend', 'Q5', 'over', None, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'over', None, False, 'IC'),
    ('bullish_trend', 'Q5', 'over', 5.0, True, 'LONG CALL'),
    ('bullish_trend', 'Q5', 'over', 5.0, False, 'IC'),
    ('bullish_trend', 'Q5', 'over', 20.0, True, 'SKIP'),
    ('bullish_trend', 'Q5', 'over', 20.0, False, 'IC'),
    ('bullish_trend', None, 'none', None, True, 'LONG CALL'),
    ('bullish_trend', None, 'none', None, False, 'CALL'),
    ('bullish_trend', None, 'none', 5.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'none', 5.0, False, 'CALL'),
    ('bullish_trend', None, 'none', 20.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'none', 20.0, False, 'CALL'),
    ('bullish_trend', None, 'under', None, True, 'LONG CALL'),
    ('bullish_trend', None, 'under', None, False, 'CALL'),
    ('bullish_trend', None, 'under', 5.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'under', 5.0, False, 'CALL'),
    ('bullish_trend', None, 'under', 20.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'under', 20.0, False, 'CALL'),
    ('bullish_trend', None, 'over', None, True, 'LONG CALL'),
    ('bullish_trend', None, 'over', None, False, 'CALL'),
    ('bullish_trend', None, 'over', 5.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'over', 5.0, False, 'CALL'),
    ('bullish_trend', None, 'over', 20.0, True, 'LONG CALL'),
    ('bullish_trend', None, 'over', 20.0, False, 'CALL'),
    ('bearish_trend', 'Q1', 'none', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'none', None, False, 'PUT'),
    ('bearish_trend', 'Q1', 'none', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'none', 5.0, False, 'PUT'),
    ('bearish_trend', 'Q1', 'none', 20.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'none', 20.0, False, 'PUT'),
    ('bearish_trend', 'Q1', 'under', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'under', None, False, 'PUT'),
    ('bearish_trend', 'Q1', 'under', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'under', 5.0, False, 'PUT'),
    ('bearish_trend', 'Q1', 'under', 20.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'under', 20.0, False, 'PUT'),
    ('bearish_trend', 'Q1', 'over', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'over', None, False, 'PUT'),
    ('bearish_trend', 'Q1', 'over', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'over', 5.0, False, 'PUT'),
    ('bearish_trend', 'Q1', 'over', 20.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q1', 'over', 20.0, False, 'PUT'),
    ('bearish_trend', 'Q5', 'none', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'none', None, False, 'PUT'),
    ('bearish_trend', 'Q5', 'none', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'none', 5.0, False, 'PUT'),
    ('bearish_trend', 'Q5', 'none', 20.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'none', 20.0, False, 'PUT'),
    ('bearish_trend', 'Q5', 'under', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'under', None, False, 'PUT'),
    ('bearish_trend', 'Q5', 'under', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'under', 5.0, False, 'PUT'),
    ('bearish_trend', 'Q5', 'under', 20.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'under', 20.0, False, 'PUT'),
    ('bearish_trend', 'Q5', 'over', None, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'over', None, False, 'IC'),
    ('bearish_trend', 'Q5', 'over', 5.0, True, 'LONG PUT'),
    ('bearish_trend', 'Q5', 'over', 5.0, False, 'IC'),
    ('bearish_trend', 'Q5', 'over', 20.0, True, 'SKIP'),
    ('bearish_trend', 'Q5', 'over', 20.0, False, 'IC'),
    ('bearish_trend', None, 'none', None, True, 'LONG PUT'),
    ('bearish_trend', None, 'none', None, False, 'PUT'),
    ('bearish_trend', None, 'none', 5.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'none', 5.0, False, 'PUT'),
    ('bearish_trend', None, 'none', 20.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'none', 20.0, False, 'PUT'),
    ('bearish_trend', None, 'under', None, True, 'LONG PUT'),
    ('bearish_trend', None, 'under', None, False, 'PUT'),
    ('bearish_trend', None, 'under', 5.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'under', 5.0, False, 'PUT'),
    ('bearish_trend', None, 'under', 20.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'under', 20.0, False, 'PUT'),
    ('bearish_trend', None, 'over', None, True, 'LONG PUT'),
    ('bearish_trend', None, 'over', None, False, 'PUT'),
    ('bearish_trend', None, 'over', 5.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'over', 5.0, False, 'PUT'),
    ('bearish_trend', None, 'over', 20.0, True, 'LONG PUT'),
    ('bearish_trend', None, 'over', 20.0, False, 'PUT'),
    ('reversal_play', 'Q1', 'none', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'none', None, False, 'STRDL'),
    ('reversal_play', 'Q1', 'none', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'none', 5.0, False, 'STRDL'),
    ('reversal_play', 'Q1', 'none', 20.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'none', 20.0, False, 'STRDL'),
    ('reversal_play', 'Q1', 'under', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'under', None, False, 'STRDL'),
    ('reversal_play', 'Q1', 'under', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'under', 5.0, False, 'STRDL'),
    ('reversal_play', 'Q1', 'under', 20.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'under', 20.0, False, 'STRDL'),
    ('reversal_play', 'Q1', 'over', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'over', None, False, 'STRDL'),
    ('reversal_play', 'Q1', 'over', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'over', 5.0, False, 'STRDL'),
    ('reversal_play', 'Q1', 'over', 20.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q1', 'over', 20.0, False, 'STRDL'),
    ('reversal_play', 'Q5', 'none', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'none', None, False, 'STRDL'),
    ('reversal_play', 'Q5', 'none', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'none', 5.0, False, 'STRDL'),
    ('reversal_play', 'Q5', 'none', 20.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'none', 20.0, False, 'STRDL'),
    ('reversal_play', 'Q5', 'under', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'under', None, False, 'STRDL'),
    ('reversal_play', 'Q5', 'under', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'under', 5.0, False, 'STRDL'),
    ('reversal_play', 'Q5', 'under', 20.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'under', 20.0, False, 'STRDL'),
    ('reversal_play', 'Q5', 'over', None, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'over', None, False, 'IC'),
    ('reversal_play', 'Q5', 'over', 5.0, True, 'LONG STRDL'),
    ('reversal_play', 'Q5', 'over', 5.0, False, 'IC'),
    ('reversal_play', 'Q5', 'over', 20.0, True, 'SKIP'),
    ('reversal_play', 'Q5', 'over', 20.0, False, 'IC'),
    ('reversal_play', None, 'none', None, True, 'LONG STRDL'),
    ('reversal_play', None, 'none', None, False, 'STRDL'),
    ('reversal_play', None, 'none', 5.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'none', 5.0, False, 'STRDL'),
    ('reversal_play', None, 'none', 20.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'none', 20.0, False, 'STRDL'),
    ('reversal_play', None, 'under', None, True, 'LONG STRDL'),
    ('reversal_play', None, 'under', None, False, 'STRDL'),
    ('reversal_play', None, 'under', 5.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'under', 5.0, False, 'STRDL'),
    ('reversal_play', None, 'under', 20.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'under', 20.0, False, 'STRDL'),
    ('reversal_play', None, 'over', None, True, 'LONG STRDL'),
    ('reversal_play', None, 'over', None, False, 'STRDL'),
    ('reversal_play', None, 'over', 5.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'over', 5.0, False, 'STRDL'),
    ('reversal_play', None, 'over', 20.0, True, 'LONG STRDL'),
    ('reversal_play', None, 'over', 20.0, False, 'STRDL'),
    ('mixed', 'Q1', 'none', None, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'none', None, False, 'STRDL'),
    ('mixed', 'Q1', 'none', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'none', 5.0, False, 'STRDL'),
    ('mixed', 'Q1', 'none', 20.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'none', 20.0, False, 'STRDL'),
    ('mixed', 'Q1', 'under', None, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'under', None, False, 'STRDL'),
    ('mixed', 'Q1', 'under', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'under', 5.0, False, 'STRDL'),
    ('mixed', 'Q1', 'under', 20.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'under', 20.0, False, 'STRDL'),
    ('mixed', 'Q1', 'over', None, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'over', None, False, 'STRDL'),
    ('mixed', 'Q1', 'over', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'over', 5.0, False, 'STRDL'),
    ('mixed', 'Q1', 'over', 20.0, True, 'LONG STRDL'),
    ('mixed', 'Q1', 'over', 20.0, False, 'STRDL'),
    ('mixed', 'Q5', 'none', None, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'none', None, False, 'STRDL'),
    ('mixed', 'Q5', 'none', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'none', 5.0, False, 'STRDL'),
    ('mixed', 'Q5', 'none', 20.0, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'none', 20.0, False, 'STRDL'),
    ('mixed', 'Q5', 'under', None, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'under', None, False, 'STRDL'),
    ('mixed', 'Q5', 'under', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'under', 5.0, False, 'STRDL'),
    ('mixed', 'Q5', 'under', 20.0, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'under', 20.0, False, 'STRDL'),
    ('mixed', 'Q5', 'over', None, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'over', None, False, 'IC'),
    ('mixed', 'Q5', 'over', 5.0, True, 'LONG STRDL'),
    ('mixed', 'Q5', 'over', 5.0, False, 'IC'),
    ('mixed', 'Q5', 'over', 20.0, True, 'SKIP'),
    ('mixed', 'Q5', 'over', 20.0, False, 'IC'),
    ('mixed', None, 'none', None, True, 'LONG STRDL'),
    ('mixed', None, 'none', None, False, 'STRDL'),
    ('mixed', None, 'none', 5.0, True, 'LONG STRDL'),
    ('mixed', None, 'none', 5.0, False, 'STRDL'),
    ('mixed', None, 'none', 20.0, True, 'LONG STRDL'),
    ('mixed', None, 'none', 20.0, False, 'STRDL'),
    ('mixed', None, 'under', None, True, 'LONG STRDL'),
    ('mixed', None, 'under', None, False, 'STRDL'),
    ('mixed', None, 'under', 5.0, True, 'LONG STRDL'),
    ('mixed', None, 'under', 5.0, False, 'STRDL'),
    ('mixed', None, 'under', 20.0, True, 'LONG STRDL'),
    ('mixed', None, 'under', 20.0, False, 'STRDL'),
    ('mixed', None, 'over', None, True, 'LONG STRDL'),
    ('mixed', None, 'over', None, False, 'STRDL'),
    ('mixed', None, 'over', 5.0, True, 'LONG STRDL'),
    ('mixed', None, 'over', 5.0, False, 'STRDL'),
    ('mixed', None, 'over', 20.0, True, 'LONG STRDL'),
    ('mixed', None, 'over', 20.0, False, 'STRDL'),
    (None, 'Q1', 'none', None, True, None),
    (None, 'Q1', 'none', None, False, None),
    (None, 'Q1', 'none', 5.0, True, None),
    (None, 'Q1', 'none', 5.0, False, None),
    (None, 'Q1', 'none', 20.0, True, None),
    (None, 'Q1', 'none', 20.0, False, None),
    (None, 'Q1', 'under', None, True, None),
    (None, 'Q1', 'under', None, False, None),
    (None, 'Q1', 'under', 5.0, True, None),
    (None, 'Q1', 'under', 5.0, False, None),
    (None, 'Q1', 'under', 20.0, True, None),
    (None, 'Q1', 'under', 20.0, False, None),
    (None, 'Q1', 'over', None, True, None),
    (None, 'Q1', 'over', None, False, None),
    (None, 'Q1', 'over', 5.0, True, None),
    (None, 'Q1', 'over', 5.0, False, None),
    (None, 'Q1', 'over', 20.0, True, None),
    (None, 'Q1', 'over', 20.0, False, None),
    (None, 'Q5', 'none', None, True, None),
    (None, 'Q5', 'none', None, False, None),
    (None, 'Q5', 'none', 5.0, True, None),
    (None, 'Q5', 'none', 5.0, False, None),
    (None, 'Q5', 'none', 20.0, True, None),
    (None, 'Q5', 'none', 20.0, False, None),
    (None, 'Q5', 'under', None, True, None),
    (None, 'Q5', 'under', None, False, None),
    (None, 'Q5', 'under', 5.0, True, None),
    (None, 'Q5', 'under', 5.0, False, None),
    (None, 'Q5', 'under', 20.0, True, None),
    (None, 'Q5', 'under', 20.0, False, None),
    (None, 'Q5', 'over', None, True, None),
    (None, 'Q5', 'over', None, False, 'IC'),
    (None, 'Q5', 'over', 5.0, True, None),
    (None, 'Q5', 'over', 5.0, False, 'IC'),
    (None, 'Q5', 'over', 20.0, True, 'SKIP'),
    (None, 'Q5', 'over', 20.0, False, 'IC'),
    (None, None, 'none', None, True, None),
    (None, None, 'none', None, False, None),
    (None, None, 'none', 5.0, True, None),
    (None, None, 'none', 5.0, False, None),
    (None, None, 'none', 20.0, True, None),
    (None, None, 'none', 20.0, False, None),
    (None, None, 'under', None, True, None),
    (None, None, 'under', None, False, None),
    (None, None, 'under', 5.0, True, None),
    (None, None, 'under', 5.0, False, None),
    (None, None, 'under', 20.0, True, None),
    (None, None, 'under', 20.0, False, None),
    (None, None, 'over', None, True, None),
    (None, None, 'over', None, False, None),
    (None, None, 'over', 5.0, True, None),
    (None, None, 'over', 5.0, False, None),
    (None, None, 'over', 20.0, True, None),
    (None, None, 'over', 20.0, False, None),
)


def test_calibration_fixtures_match_the_thresholds():
    assert _OVER['realized_vs_implied_ratio'] < _IC_RATIO_THRESHOLD
    assert _OVER['avg_short_strangle_pnl_pct'] > _IC_STRANGLE_THRESHOLD
    assert not (_UNDER['realized_vs_implied_ratio'] < _IC_RATIO_THRESHOLD
                and _UNDER['avg_short_strangle_pnl_pct'] > _IC_STRANGLE_THRESHOLD)


def test_implied_move_invalid_returns_skip_only_where_the_guard_is_consulted():
    # The guarded case: long-only, Q5, over-pricing confirmed, no valid number.
    for archetype in ARCHETYPES:
        without = recommended_structure(archetype, 'Q5', _OVER, implied_move_pct=None, long_only=True)
        assert without == _LONG[archetype]
        assert recommended_structure(
            archetype, 'Q5', _OVER, implied_move_pct=None, long_only=True,
            implied_move_invalid=True) == 'SKIP'
        assert recommended_structure(
            archetype, 'Q5', _OVER, long_only=True, implied_move_invalid=True) == 'SKIP'

    # Every other branch is unchanged with the keyword True.
    for archetype in ARCHETYPES:
        for quintile in ('Q1', None):
            for cal in CALIBRATIONS.values():
                assert recommended_structure(
                    archetype, quintile, cal, implied_move_pct=None, long_only=True,
                    implied_move_invalid=True) == _LONG[archetype]
                assert recommended_structure(
                    archetype, quintile, cal, implied_move_pct=None, long_only=False,
                    implied_move_invalid=True) == _DEFAULT[archetype]
        for cal in (None, {}, _UNDER):
            assert recommended_structure(
                archetype, 'Q5', cal, implied_move_pct=None, long_only=True,
                implied_move_invalid=True) == _LONG[archetype]
            assert recommended_structure(
                archetype, 'Q5', cal, implied_move_pct=None, long_only=False,
                implied_move_invalid=True) == _DEFAULT[archetype]
        assert recommended_structure(
            archetype, 'Q5', _OVER, implied_move_pct=None, long_only=False,
            implied_move_invalid=True) == 'IC'


def test_default_false_is_byte_identical_behaviour():
    expected_keys = set(itertools.product(ARCHETYPES, QUINTILES, CALIBRATIONS, IMPLIED, MODES))
    table = {row[:5]: row[5] for row in MAIN_D806BFD1}
    assert len(MAIN_D806BFD1) == 270 and set(table) == expected_keys

    for (archetype, quintile, cal_name, implied, long_only), main_value in table.items():
        cal = CALIBRATIONS[cal_name]
        assert recommended_structure(
            archetype, quintile, cal, implied_move_pct=implied, long_only=long_only) == main_value
        assert recommended_structure(
            archetype, quintile, cal, implied_move_pct=implied, long_only=long_only,
            implied_move_invalid=False) == main_value


def test_invalid_flag_is_keyword_only_and_does_not_shadow_a_valid_implied_move(monkeypatch):
    with pytest.raises(TypeError):
        recommended_structure('mixed', 'Q5', _OVER, None, True, True)

    # The entry check runs before any branch, including the env read for long_only=None.
    def _env_read_is_a_branch():
        raise AssertionError('entry check must run before _env_long_only')
    monkeypatch.setattr(er, '_env_long_only', _env_read_is_a_branch)

    for archetype in ARCHETYPES:
        for quintile in QUINTILES:
            for cal in CALIBRATIONS.values():
                for implied in (0.0, 5.0, 20.0, float('nan')):
                    for long_only in (True, False, None):
                        with pytest.raises(ValueError):
                            recommended_structure(
                                archetype, quintile, cal, implied_move_pct=implied,
                                long_only=long_only, implied_move_invalid=True)
