"""Tests for lib/earnings_reactions.py — playability score + archetype.

Covers the pure-compute layer (compute_playability_score,
classify_archetype). DB query helpers are integration-tested via the
brief, not here.
"""
import math

import pytest

from lib.earnings_reactions import (
    compute_playability_score,
    classify_archetype,
    enrich_with_playability,
)


# ────────────────────────────────────────────────────────────
# compute_playability_score
# ────────────────────────────────────────────────────────────

class TestPlayabilityScore:
    def test_avgo_phase05_baseline(self):
        """AVGO from Phase 0.5: move_mag=6.47, typical=1.30,
        dir_cons=0.83, rev=0.17. Locked-in expected score ≈ 56.07."""
        score = compute_playability_score(
            move_magnitude_pct=6.47,
            typical_daily_return_pct=1.30,
            dir_consistency=0.83,
            reversal_rate=0.17,
            options_volume=729134,
        )
        # mag_norm = 4.977; confidence = max(0.83, 0.5+0.5*0.17) = 0.83
        # log(729135) = 13.499
        # score = 4.977 * 0.83 * 13.499 ≈ 55.76
        assert score is not None
        assert 55.0 < score < 56.5

    def test_fdx_phase05_baseline(self):
        """FDX from Phase 0.5: move_mag=7.39, typical=0.90, dir_cons=0.33,
        rev=0.50. Reversal-rate confidence floor kicks in."""
        score = compute_playability_score(
            move_magnitude_pct=7.39,
            typical_daily_return_pct=0.90,
            dir_consistency=0.33,
            reversal_rate=0.50,
            options_volume=142737,
        )
        # mag_norm = 8.211; confidence = max(0.33, 0.5+0.5*0.50) = 0.75
        # log(142738) = 11.869
        # score = 8.211 * 0.75 * 11.869 ≈ 73.10
        assert score is not None
        assert 72.0 < score < 74.0

    def test_jpm_phase05_baseline(self):
        """JPM lowest-ranked from Phase 0.5: small magnitude, low score."""
        score = compute_playability_score(
            move_magnitude_pct=1.34,
            typical_daily_return_pct=0.90,
            dir_consistency=0.58,
            reversal_rate=0.25,
            options_volume=234744,
        )
        # mag_norm = 1.489; confidence = max(0.58, 0.625) = 0.625
        # log(234745) = 12.366
        # score = 1.489 * 0.625 * 12.366 ≈ 11.51
        assert score is not None
        assert 11.0 < score < 12.0

    def test_missing_move_magnitude_returns_none(self):
        s = compute_playability_score(None, 1.0, 0.5, 0.2, 100000)
        assert s is None

    def test_missing_typical_returns_none(self):
        s = compute_playability_score(5.0, None, 0.5, 0.2, 100000)
        assert s is None

    def test_zero_typical_returns_none(self):
        """A flat-line stock would div-by-zero. Return None instead."""
        s = compute_playability_score(5.0, 0.0, 0.5, 0.2, 100000)
        assert s is None

    def test_negative_typical_returns_none(self):
        """Defensive — negative typical-return makes no sense."""
        s = compute_playability_score(5.0, -0.5, 0.5, 0.2, 100000)
        assert s is None

    def test_missing_dir_consistency_returns_none(self):
        s = compute_playability_score(5.0, 1.0, None, 0.2, 100000)
        assert s is None

    def test_missing_reversal_rate_returns_none(self):
        s = compute_playability_score(5.0, 1.0, 0.5, None, 100000)
        assert s is None

    def test_zero_options_volume_returns_none(self):
        """A ticker with no options can't be played via options."""
        s = compute_playability_score(5.0, 1.0, 0.5, 0.2, 0)
        assert s is None

    def test_none_options_volume_returns_none(self):
        s = compute_playability_score(5.0, 1.0, 0.5, 0.2, None)
        assert s is None

    def test_reversal_floor_dominates_when_dir_cons_low(self):
        """When dir_consistency is low but reversal_rate is high, the
        confidence floor (0.5 + 0.5*rev) wins."""
        # dir_cons=0.30, rev=0.60 → confidence = max(0.30, 0.80) = 0.80
        # vs dir_cons=0.30 alone → would be 0.30
        score_with_rev = compute_playability_score(5.0, 1.0, 0.30, 0.60, 100000)
        score_without = compute_playability_score(5.0, 1.0, 0.30, 0.0, 100000)
        assert score_with_rev > score_without

    def test_high_dir_cons_dominates_low_rev(self):
        """When dir_consistency is high, reversal_rate floor doesn't
        kick in (max picks dir_consistency)."""
        # dir_cons=0.85, rev=0.10 → max(0.85, 0.55) = 0.85
        score = compute_playability_score(5.0, 1.0, 0.85, 0.10, 100000)
        # confidence should be 0.85, not 0.55
        # mag_norm * 0.85 * log(100001) = 5 * 0.85 * 11.513 = 48.93
        assert score is not None
        assert 48.0 < score < 50.0


# ────────────────────────────────────────────────────────────
# classify_archetype
# ────────────────────────────────────────────────────────────

class TestArchetype:
    def test_avgo_bullish_trend(self):
        # AVGO: move_mag=6.47, bias=+3.24, dir_cons=0.83, rev=0.17
        a = classify_archetype(6.47, 3.24, 0.83, 0.17)
        assert a == 'bullish_trend'

    def test_fdx_reversal_play(self):
        # FDX: move_mag=7.39, bias=-0.83, dir_cons=0.33, rev=0.50
        a = classify_archetype(7.39, -0.83, 0.33, 0.50)
        assert a == 'reversal_play'

    def test_nvda_mixed(self):
        # NVDA: move_mag=5.98, bias=+5.21, dir_cons=0.58, rev=0.25
        # Not high enough dir_cons (0.65 threshold) to be a trend, no
        # reversal pattern → mixed
        a = classify_archetype(5.98, 5.21, 0.58, 0.25)
        assert a == 'mixed'

    def test_lly_bullish_trend(self):
        # LLY: move_mag=6.74, bias=+2.15, dir_cons=0.67, rev=0.25
        a = classify_archetype(6.74, 2.15, 0.67, 0.25)
        assert a == 'bullish_trend'

    def test_jpm_mixed(self):
        # JPM: move_mag=1.34, bias=+0.03 — magnitude below 1.5 floor → quiet
        a = classify_archetype(1.34, 0.03, 0.58, 0.25)
        assert a == 'quiet'

    def test_small_magnitude_is_quiet(self):
        a = classify_archetype(0.5, 0.0, 0.99, 0.01)
        assert a == 'quiet'

    def test_bearish_trend(self):
        # High dir_cons + negative bias = bearish_trend
        a = classify_archetype(5.0, -3.0, 0.75, 0.20)
        assert a == 'bearish_trend'

    def test_neutral_bias_high_consistency_is_mixed(self):
        # Bias near zero → neither bull nor bear
        a = classify_archetype(5.0, 0.1, 0.80, 0.10)
        assert a == 'mixed'

    def test_high_reversal_low_dir_cons(self):
        a = classify_archetype(5.0, 0.0, 0.40, 0.50)
        assert a == 'reversal_play'

    def test_missing_inputs_yield_quiet(self):
        a = classify_archetype(None, None, None, None)
        assert a == 'quiet'


# ────────────────────────────────────────────────────────────
# enrich_with_playability — integration with the data shape
# ────────────────────────────────────────────────────────────

class TestEnrichWithPlayability:
    def test_empty_rows_returns_empty(self):
        result = enrich_with_playability([])
        assert result == []

    def test_no_db_data_yields_quiet_rows(self, monkeypatch):
        """When the DB returns nothing (e.g. populator hasn't run), every
        row should still get the playability_* keys, but with None
        score and 'quiet' archetype. Brief code shouldn't crash."""
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_reaction_stats',
                            lambda tickers, lookback_quarters=12: {})
        monkeypatch.setattr(earnings_reactions, 'query_typical_daily_return',
                            lambda tickers, window_days=60: {})

        rows = [
            {'ticker': 'AVGO', 'options_volume': 1000000},
            {'ticker': 'FDX',  'options_volume': 50000},
        ]
        enrich_with_playability(rows)
        for r in rows:
            assert r['playability_score'] is None
            assert r['playability_archetype'] == 'quiet'
            assert r['playability_n_q'] == 0

    def test_full_pipeline_with_mock_data(self, monkeypatch):
        """Synthetic stats map → score and archetype computed correctly."""
        from lib import earnings_reactions

        def fake_stats(tickers, lookback_quarters=12):
            return {
                'AVGO': {
                    'n_q': 12,
                    'move_magnitude_pct': 6.47,
                    'directional_bias_pct': 3.24,
                    'dir_consistency': 0.83,
                    'reversal_rate': 0.17,
                },
                'FDX': {
                    'n_q': 12,
                    'move_magnitude_pct': 7.39,
                    'directional_bias_pct': -0.83,
                    'dir_consistency': 0.33,
                    'reversal_rate': 0.50,
                },
            }

        def fake_typical(tickers, window_days=60):
            return {'AVGO': 1.30, 'FDX': 0.90}

        monkeypatch.setattr(earnings_reactions, 'query_reaction_stats', fake_stats)
        monkeypatch.setattr(earnings_reactions, 'query_typical_daily_return', fake_typical)

        rows = [
            {'ticker': 'AVGO', 'options_volume': 729134},
            {'ticker': 'FDX',  'options_volume': 142737},
        ]
        enrich_with_playability(rows)

        avgo = rows[0]
        assert avgo['playability_score'] is not None
        assert 55.0 < avgo['playability_score'] < 56.5
        assert avgo['playability_archetype'] == 'bullish_trend'
        assert avgo['playability_n_q'] == 12

        fdx = rows[1]
        assert fdx['playability_score'] is not None
        assert 72.0 < fdx['playability_score'] < 74.0
        assert fdx['playability_archetype'] == 'reversal_play'

    def test_row_without_options_volume_yields_none_score(self, monkeypatch):
        """Stats present but options_volume None → score is None,
        but archetype still classified from reaction profile."""
        from lib import earnings_reactions
        monkeypatch.setattr(earnings_reactions, 'query_reaction_stats',
                            lambda tickers, lookback_quarters=12: {
                                'AVGO': {
                                    'n_q': 12,
                                    'move_magnitude_pct': 6.47,
                                    'directional_bias_pct': 3.24,
                                    'dir_consistency': 0.83,
                                    'reversal_rate': 0.17,
                                }
                            })
        monkeypatch.setattr(earnings_reactions, 'query_typical_daily_return',
                            lambda tickers, window_days=60: {'AVGO': 1.30})

        rows = [{'ticker': 'AVGO', 'options_volume': None}]
        enrich_with_playability(rows)
        assert rows[0]['playability_score'] is None
        # Archetype is still classifiable from the reaction profile alone
        assert rows[0]['playability_archetype'] == 'bullish_trend'
