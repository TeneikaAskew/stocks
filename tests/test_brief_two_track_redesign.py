"""Regression guards for the 2026-05-14 brief redesign.

Three coordinated changes locked in here:
1. reversal_play archetype → STRDL action tag (was FADE). The directional
   fade is anti-predictive at high conviction per the 2026-05-14
   backtest (Q5 hit rate 37.2% vs Q1 41.8%), so we play vol instead.
2. Q1-Q5 quintile column replaced with English confidence labels
   (🔥 HIGH / ✅ SOLID / 🟡 OK / ❓ WEAK / 🚫 SKIP).
3. New Track B "High-Flow Watchlist" section for IPO-edge names with
   huge flow but < 12Q history (OI ≥ 50k AND vol ≥ 5k).

Pin the row format and section presence so a future refactor can't
silently undo any of them.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.earnings_reactions import (
    CONFIDENCE_LABELS,
    confidence_label,
    score_quintile,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers — score_quintile + confidence_label boundary tests
# ──────────────────────────────────────────────────────────────────────

def test_quintile_boundaries():
    # Calibration source: 2026-05-14 backtest (avg score per quintile
    # 13.03 / 18.38 / 24.06 / 32.29 / 51.50, midpoints used as cuts).
    assert score_quintile(0) == 'Q1'
    assert score_quintile(15.6) == 'Q1'
    assert score_quintile(15.7) == 'Q2'    # exactly on boundary → next quintile
    assert score_quintile(20) == 'Q2'
    assert score_quintile(21.2) == 'Q3'
    assert score_quintile(25) == 'Q3'
    assert score_quintile(28.2) == 'Q4'
    assert score_quintile(35) == 'Q4'
    assert score_quintile(41.9) == 'Q5'
    assert score_quintile(100) == 'Q5'
    assert score_quintile(None) is None


def test_confidence_labels_are_actionable_text():
    # Every Q level maps to a human-readable label with an emoji prefix.
    # If you change the wording, update the brief renderer + glossary.
    assert CONFIDENCE_LABELS['Q5'] == '🔥 HIGH'
    assert CONFIDENCE_LABELS['Q4'] == '✅ SOLID'
    assert CONFIDENCE_LABELS['Q3'] == '🟡 OK'
    assert CONFIDENCE_LABELS['Q2'] == '❓ WEAK'
    assert CONFIDENCE_LABELS['Q1'] == '🚫 SKIP'


def test_confidence_label_passes_through():
    assert confidence_label(50) == '🔥 HIGH'
    assert confidence_label(35) == '✅ SOLID'
    assert confidence_label(25) == '🟡 OK'
    assert confidence_label(18) == '❓ WEAK'
    assert confidence_label(5)  == '🚫 SKIP'
    assert confidence_label(None) is None


# ──────────────────────────────────────────────────────────────────────
# Brief renderer — action map + Track B section + Q1 drop
# ──────────────────────────────────────────────────────────────────────

def _make_row(ticker, archetype, score, *, time='postmarket', oi=200_000,
              vol=10_000, em=2.0, mcap=5e9, nq=12, eps=0.10):
    return {
        'ticker': ticker, 'date': date(2026, 5, 11),
        'expected_move': em, 'eps_estimate': eps,
        'options_volume': vol, 'open_interest': oi, 'market_cap': mcap,
        'earnings_time': time, 'time': time,
        'sources': ['alphavantage', 'earnings_whispers', 'unusual_whales', 'yahoo'],
        'tier': 1,
        'playability_archetype': archetype,
        'playability_score': score,
        'playability_n_q': nq,
        'strategy': None, 'strike': None, 'gap_pct': None,
        'eps_actual': None, 'eps_surprise_pct': None,
    }


def _build(earnings, watchlist=None):
    import gcp.premarket_brief as pb
    data = {
        'mode': 'daily', 'start': date(2026, 5, 11), 'end': date(2026, 5, 11),
        'earnings': earnings, 'watchlist': watchlist or [],
    }
    return pb._build_earnings_embed(data)


def test_bullish_trend_renders_CALL():
    embed = _build([_make_row('AVGO', 'bullish_trend', 50.0)])
    assert '**AVGO**' in embed['description']
    assert 'CALL' in embed['description']
    assert 'FADE' not in embed['description']     # legacy tag must not appear
    assert 'STRDL' not in embed['description']    # not a straddle


def test_bearish_trend_renders_PUT():
    embed = _build([_make_row('XYZ', 'bearish_trend', 35.0)])
    assert 'PUT' in embed['description']
    assert 'FADE' not in embed['description']


def test_reversal_play_renders_STRDL_not_FADE():
    """Pinning the 2026-05-14 behavior: FADE is gone; reversal_play → STRDL.

    Regression guard: if a future refactor re-introduces FADE for
    reversal_play, this test fails loudly. The directional fade is
    anti-predictive per the 21,592-prediction backtest.
    """
    embed = _build([_make_row('RGTI', 'reversal_play', 35.0)])
    assert 'STRDL' in embed['description']
    assert 'FADE' not in embed['description']


def test_mixed_renders_STRDL():
    embed = _build([_make_row('NVDA', 'mixed', 35.0)])
    assert 'STRDL' in embed['description']


def test_q1_classifier_identifies_skip_candidates():
    """Q1 = below-baseline hit rate (34.8%). The upstream data-layer
    filter in load_earnings_for_brief() drops these rows before they
    reach the renderer (see gcp/premarket_brief.py line ~461). This
    test pins the *classification* used by that filter so future
    boundary tweaks can't silently let Q1 rows leak through.
    """
    # Anything < 15.7 is Q1 per the calibrated boundaries.
    for score in (0, 5, 10, 15.0, 15.69):
        assert score_quintile(score) == 'Q1', f"score={score} should be Q1"
    # And exactly at the boundary jumps to Q2.
    assert score_quintile(15.7) == 'Q2'


def test_renderer_shows_skip_label_if_q1_leaks_through():
    """Defense-in-depth check: if the upstream Q1 filter is ever
    bypassed (e.g. BRIEF_INCLUDE_UNCONFIRMED=1 for debug), the renderer
    must still surface the 🚫 SKIP label so the reader knows not to
    trade that row. Pins the visible signaling.
    """
    embed = _build([_make_row('LOWY', 'mixed', 5.0)])  # Q1 score
    assert '**LOWY**' in embed['description']
    assert '🚫 SKIP' in embed['description']


def test_confidence_labels_appear_in_rows():
    embed = _build([
        _make_row('Q5', 'mixed', 50.0),
        _make_row('Q4', 'mixed', 35.0),
        _make_row('Q3', 'mixed', 25.0),
        _make_row('Q2', 'mixed', 18.0),
    ])
    desc = embed['description']
    assert '🔥 HIGH' in desc
    assert '✅ SOLID' in desc
    assert '🟡 OK' in desc
    assert '❓ WEAK' in desc


def test_track_b_section_renders_when_watchlist_present():
    """High-Flow Watchlist (Track B) section pins:
    1. Header includes the 📊 icon and the section name.
    2. DYOR caveat is visible.
    3. Row shows flow stats (OI/Vol/mcap) but NO archetype / action /
       confidence label.
    """
    crcl = _make_row('CRCL', archetype=None, score=None,
                     oi=768_000, vol=178_000, em=8.0, mcap=30.3e9, nq=5)
    crcl.pop('playability_archetype', None)
    crcl['playability_score'] = None
    embed = _build([_make_row('AVGO', 'bullish_trend', 50.0)], watchlist=[crcl])
    desc = embed['description']
    assert '📊 High-Flow Watchlist' in desc
    assert 'DYOR' in desc
    assert '**CRCL**' in desc
    assert 'OI 768k' in desc
    assert 'Vol 178k' in desc
    assert '30.3B mcap' in desc
    assert 'nQ=5' in desc
    # Track B rows must NOT show action / confidence (sample too small).
    crcl_idx = desc.find('**CRCL**')
    crcl_line_end = desc.find('\n', crcl_idx)
    crcl_line = desc[crcl_idx:crcl_line_end if crcl_line_end > 0 else None]
    for forbidden in ('STRDL', 'CALL', 'PUT', '🔥', '✅', '🟡', '❓'):
        assert forbidden not in crcl_line, f"{forbidden!r} leaked into Track B row: {crcl_line!r}"


def test_track_b_omitted_when_watchlist_empty():
    embed = _build([_make_row('AVGO', 'bullish_trend', 50.0)], watchlist=[])
    assert '📊 High-Flow Watchlist' not in embed['description']


def test_bmo_amc_headers_split_by_earnings_time():
    """The brief shows ☀️ Reporting Before Open and 🌙 Reporting After
    Close section headers. Pin them so a future refactor doesn't drop
    the BMO/AMC bucketing the user relies on."""
    embed = _build([
        _make_row('PREM', 'mixed', 35.0, time='premarket'),
        _make_row('POST', 'mixed', 35.0, time='postmarket'),
    ])
    desc = embed['description']
    assert '☀️ Reporting Before Open' in desc
    assert '🌙 Reporting After Close' in desc
    # Each header sees its respective ticker.
    pre_idx  = desc.find('☀️ Reporting Before Open')
    post_idx = desc.find('🌙 Reporting After Close')
    assert pre_idx >= 0 and post_idx >= 0
    # PREM appears in the BMO half, POST in the AMC half.
    assert desc.find('**PREM**', pre_idx) < post_idx
    assert desc.find('**POST**', post_idx) > 0
