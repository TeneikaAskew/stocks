"""Tests for Phase 1.6 — Post-Event Conditional Reads.

Covers:
  - classify_lean: maps (n, held, reversed, gap) → plain-English phrase
  - conditional_lean_summary: end-to-end with mocked DB query
  - SBUX 4/28 validation: real-world example should produce 'expect reversal'
  - Env-var configurability of all four knobs
"""
import importlib
import os
import pytest

from lib.earnings_reactions import (
    classify_lean,
    conditional_lean_summary,
    query_conditional_reactions,
)


# ────────────────────────────────────────────────────────────
# classify_lean — pure-compute classification
# ────────────────────────────────────────────────────────────

class TestClassifyLean:
    def test_empty_stats_skip(self):
        assert classify_lean({}) == 'skip'

    def test_zero_n_skip(self):
        stats = {'n': 0, 'held': 0, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats) == 'skip'

    def test_below_min_sample_skip(self):
        # n=2 < default min_sample=3 → skip even if 100% reversed
        stats = {'n': 2, 'held': 0, 'reversed': 2, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=4.0) == 'skip'

    def test_at_min_sample_classifies(self):
        # n=3, all reversed → expect reversal
        stats = {'n': 3, 'held': 0, 'reversed': 3, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=4.0) == 'expect reversal'

    def test_75_percent_reversed_threshold(self):
        # 3 of 4 reversed = 75% → expect reversal (the SBUX 4/28 case)
        stats = {'n': 4, 'held': 1, 'reversed': 3, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=4.85) == 'expect reversal'

    def test_just_below_threshold_low_conviction(self):
        # 2 of 4 reversed = 50% → low conviction
        stats = {'n': 4, 'held': 2, 'reversed': 2, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=4.0) == 'low conviction'

    def test_held_with_bullish_gap(self):
        # 4 of 4 held + gap up → bullish gap play
        stats = {'n': 4, 'held': 4, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=5.0) == 'bullish gap play'

    def test_held_with_bearish_gap(self):
        # 4 of 4 held + gap down → bearish gap play
        stats = {'n': 4, 'held': 4, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=-3.0) == 'bearish gap play'

    def test_held_no_gap_direction(self):
        # held=100% but actual_gap=None → low conviction (can't pick direction)
        stats = {'n': 4, 'held': 4, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=None) == 'low conviction'

    def test_zero_gap_yields_low_conviction(self):
        # gap == 0 → can't be bullish or bearish
        stats = {'n': 4, 'held': 4, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=0.0) == 'low conviction'

    def test_custom_threshold_loose(self):
        # 60% reversed at threshold=0.6 → expect reversal
        stats = {'n': 5, 'held': 2, 'reversed': 3, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=4.0, threshold=0.6) == 'expect reversal'
        # Same stats at default 0.75 → low conviction
        assert classify_lean(stats, actual_gap_pct=4.0) == 'low conviction'

    def test_custom_min_sample(self):
        # n=3 below min_sample=5 → skip
        stats = {'n': 3, 'held': 3, 'reversed': 0, 'unclear': 0}
        assert classify_lean(stats, actual_gap_pct=5.0, min_sample=5) == 'skip'

    def test_unclear_dominates_no_directional_call(self):
        # held=2, reversed=1, unclear=2, n=5
        # held/n = 40%, reversed/n = 20% → both below 75% → low conviction
        stats = {'n': 5, 'held': 2, 'reversed': 1, 'unclear': 2}
        assert classify_lean(stats, actual_gap_pct=4.0) == 'low conviction'


# ────────────────────────────────────────────────────────────
# conditional_lean_summary — end-to-end with mocked DB
# ────────────────────────────────────────────────────────────

class TestConditionalLeanSummary:
    def test_empty_when_query_returns_nothing(self, monkeypatch):
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {})
        result = conditional_lean_summary('AAA', 'AMC', 5.0)
        assert result['n'] == 0
        assert result['lean'] == 'skip'
        # Phase 1.6 update: surface "no historical analog" so the brief
        # tells the reader we looked but found nothing
        assert 'no historical analog' in result['sentence']

    def test_too_few_samples(self, monkeypatch):
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {
                                'n': 2, 'held': 1, 'reversed': 1,
                                'unclear': 0, 'avg_sustain_5d_pct': 0.5,
                            })
        result = conditional_lean_summary('AAA', 'AMC', 5.0)
        assert result['n'] == 2
        assert result['lean'] == 'skip'
        assert 'too few' in result['sentence']
        assert '(2)' in result['sentence']

    def test_majority_reversed_renders_correct_sentence(self, monkeypatch):
        """The SBUX 4/28 case: 3 of 4 similar gaps reversed."""
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {
                                'n': 4, 'held': 1, 'reversed': 3,
                                'unclear': 0, 'avg_sustain_5d_pct': -3.5,
                            })
        result = conditional_lean_summary('SBUX', 'AMC', 4.85)
        assert result['n'] == 4
        assert result['held'] == 1
        assert result['reversed'] == 3
        assert result['lean'] == 'expect reversal'
        assert result['sentence'] == '3 of 4 similar past gaps reversed'

    def test_majority_held_bullish(self, monkeypatch):
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {
                                'n': 4, 'held': 4, 'reversed': 0,
                                'unclear': 0, 'avg_sustain_5d_pct': 4.2,
                            })
        result = conditional_lean_summary('NFLX', 'AMC', 4.2)
        assert result['lean'] == 'bullish gap play'
        assert result['sentence'] == '4 of 4 similar past gaps held'

    def test_majority_held_bearish(self, monkeypatch):
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {
                                'n': 4, 'held': 4, 'reversed': 0,
                                'unclear': 0, 'avg_sustain_5d_pct': -4.0,
                            })
        result = conditional_lean_summary('AAA', 'AMC', -4.0)
        assert result['lean'] == 'bearish gap play'

    def test_mixed_split(self, monkeypatch):
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_conditional_reactions',
                            lambda *a, **kw: {
                                'n': 5, 'held': 2, 'reversed': 2,
                                'unclear': 1, 'avg_sustain_5d_pct': 0.0,
                            })
        result = conditional_lean_summary('XYZ', 'AMC', 3.0)
        assert result['lean'] == 'low conviction'
        # When held >= reversed (and equal here), sentence reports held count
        # When reversed >= held, sentence reports reversed count


# ────────────────────────────────────────────────────────────
# query_conditional_reactions — input validation
# ────────────────────────────────────────────────────────────

class TestQueryInputValidation:
    def test_invalid_basis_returns_empty(self):
        result = query_conditional_reactions('AVGO', 'XYZ', 5.0)
        assert result == {}

    def test_basis_amc_accepted(self, monkeypatch):
        """Just verify input is normalized; DB call is mocked away."""
        import pandas as pd
        from gcp import database
        called_with = {}
        def fake_query(sql, params):
            called_with['params'] = params
            return pd.DataFrame([{'n': 0, 'held': 0, 'reversed': 0,
                                  'unclear': 0, 'avg_sustain_5d_pct': None}])
        monkeypatch.setattr(database, 'query_to_dataframe', fake_query)
        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)

        query_conditional_reactions('AVGO', 'AMC', 5.0, gap_band_pct=2.0)
        assert called_with['params']['ticker'] == 'AVGO'
        assert called_with['params']['basis'] == 'AMC'
        assert called_with['params']['lo'] == 3.0
        assert called_with['params']['hi'] == 7.0

    def test_negative_gap_band_correct(self, monkeypatch):
        """For a -4% gap, band [-6, -2] preserves direction."""
        import pandas as pd
        from gcp import database
        called_with = {}
        def fake_query(sql, params):
            called_with['params'] = params
            return pd.DataFrame([{'n': 0, 'held': 0, 'reversed': 0,
                                  'unclear': 0, 'avg_sustain_5d_pct': None}])
        monkeypatch.setattr(database, 'query_to_dataframe', fake_query)
        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)

        query_conditional_reactions('AAA', 'AMC', -4.0)
        assert called_with['params']['lo'] == -6.0
        assert called_with['params']['hi'] == -2.0


# ────────────────────────────────────────────────────────────
# Env-var configurability — Phase 1.6 tunable knobs
# ────────────────────────────────────────────────────────────

class TestEnvVarConfig:
    """Each knob: verify default + env-var override."""

    def test_default_lookback_is_12(self):
        from lib.earnings_reactions import DEFAULT_LOOKBACK_QUARTERS
        # When env var is unset, default is 12. Most CI runs leave it
        # unset, so the loaded value should be 12.
        if 'BRIEF_REACTION_LOOKBACK_QUARTERS' not in os.environ:
            assert DEFAULT_LOOKBACK_QUARTERS == 12

    def test_default_gap_band_is_2(self):
        from lib.earnings_reactions import DEFAULT_GAP_BAND_PCT
        if 'BRIEF_CONDITIONAL_GAP_BAND_PCT' not in os.environ:
            assert DEFAULT_GAP_BAND_PCT == 2.0

    def test_default_threshold_is_75pct(self):
        from lib.earnings_reactions import DEFAULT_CONDITIONAL_THRESHOLD
        if 'BRIEF_CONDITIONAL_THRESHOLD' not in os.environ:
            assert DEFAULT_CONDITIONAL_THRESHOLD == 0.75

    def test_default_min_sample_is_3(self):
        from lib.earnings_reactions import DEFAULT_CONDITIONAL_MIN_SAMPLE
        if 'BRIEF_CONDITIONAL_MIN_SAMPLE' not in os.environ:
            assert DEFAULT_CONDITIONAL_MIN_SAMPLE == 3

    def test_env_override_lookback(self, monkeypatch):
        """BRIEF_REACTION_LOOKBACK_QUARTERS=8 should produce 8 on reload."""
        monkeypatch.setenv('BRIEF_REACTION_LOOKBACK_QUARTERS', '8')
        # Force re-import so module-level constants pick up the env var
        import lib.earnings_reactions as er
        importlib.reload(er)
        assert er.DEFAULT_LOOKBACK_QUARTERS == 8
        # Restore
        importlib.reload(er)

    def test_env_override_gap_band(self, monkeypatch):
        monkeypatch.setenv('BRIEF_CONDITIONAL_GAP_BAND_PCT', '3.5')
        import lib.earnings_reactions as er
        importlib.reload(er)
        assert er.DEFAULT_GAP_BAND_PCT == 3.5
        importlib.reload(er)

    def test_env_override_threshold(self, monkeypatch):
        monkeypatch.setenv('BRIEF_CONDITIONAL_THRESHOLD', '0.6')
        import lib.earnings_reactions as er
        importlib.reload(er)
        assert er.DEFAULT_CONDITIONAL_THRESHOLD == 0.6
        importlib.reload(er)

    def test_env_override_min_sample(self, monkeypatch):
        monkeypatch.setenv('BRIEF_CONDITIONAL_MIN_SAMPLE', '5')
        import lib.earnings_reactions as er
        importlib.reload(er)
        assert er.DEFAULT_CONDITIONAL_MIN_SAMPLE == 5
        importlib.reload(er)

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        """Bad env values shouldn't crash; should use default."""
        monkeypatch.setenv('BRIEF_CONDITIONAL_GAP_BAND_PCT', 'not_a_number')
        import lib.earnings_reactions as er
        importlib.reload(er)
        assert er.DEFAULT_GAP_BAND_PCT == 2.0
        importlib.reload(er)

    def test_classify_lean_uses_env_threshold(self, monkeypatch):
        """When env override changes threshold, classify_lean should
        reflect it without explicit param."""
        monkeypatch.setenv('BRIEF_CONDITIONAL_THRESHOLD', '0.5')
        import lib.earnings_reactions as er
        importlib.reload(er)
        # 50% reversed at threshold=0.5 → expect reversal
        result = er.classify_lean(
            {'n': 4, 'held': 2, 'reversed': 2, 'unclear': 0},
            actual_gap_pct=4.0,
        )
        # Note: 2/4 = 0.5 exactly meets 0.5 threshold -> reversal wins?
        # held >= 0.5? yes (held/n = 0.5). bullish gap play takes precedence
        # (held is checked first in classify_lean, then reversal).
        assert result == 'bullish gap play'
        importlib.reload(er)
