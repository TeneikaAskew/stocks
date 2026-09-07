"""Tests for the playability sub-section renderer in premarket_brief.

Covers _playability_lines — the helper that converts a bucket of
enriched earnings rows into the indented "🎯 Playability — top N" lines
that appear inside BMO and AMC sections.
"""
import pytest

from gcp.premarket_brief import _playability_lines


def _enriched_row(ticker, score, archetype='mixed', mag=5.0, cons=0.5, rev=0.2, n_q=12):
    """Build a minimal row dict matching the shape that
    enrich_with_playability would produce."""
    return {
        'ticker': ticker,
        'playability_score': score,
        'playability_archetype': archetype,
        'playability_move_mag_pct': mag,
        'playability_dir_consistency': cons,
        'playability_reversal_rate': rev,
        'playability_n_q': n_q,
    }


class TestPlayabilityLines:
    def test_empty_bucket_returns_empty_list(self):
        assert _playability_lines([]) == []

    def test_bucket_without_scores_returns_empty(self):
        """When no row has historical data, the section is hidden."""
        rows = [
            {'ticker': 'AAA', 'playability_score': None},
            {'ticker': 'BBB'},
        ]
        assert _playability_lines(rows) == []

    def test_top_n_default_5(self):
        """6 scored rows → header + 5 ranked = 6 lines."""
        rows = [_enriched_row(t, score=10 + i)
                for i, t in enumerate(['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF'])]
        lines = _playability_lines(rows)
        assert len(lines) == 6  # 1 header + 5 ranked rows

    def test_top_n_caps_correctly(self):
        rows = [_enriched_row(t, score=i * 10)
                for i, t in enumerate('ABCDEFGHIJ')]
        lines = _playability_lines(rows, top_n=3)
        assert len(lines) == 4  # header + top 3

    def test_sorted_descending_by_score(self):
        rows = [
            _enriched_row('LOW', score=10),
            _enriched_row('HIGH', score=100),
            _enriched_row('MID', score=50),
        ]
        lines = _playability_lines(rows)
        # Position 1 = HIGH, position 2 = MID, position 3 = LOW
        assert '**HIGH**' in lines[1]
        assert '**MID**' in lines[2]
        assert '**LOW**' in lines[3]

    def test_header_indented_and_includes_count(self):
        rows = [_enriched_row('AAA', score=50)]
        lines = _playability_lines(rows)
        assert lines[0].startswith('  🎯')
        assert 'top 1' in lines[0]
        assert '12Q' in lines[0]

    def test_row_format_includes_all_components(self):
        row = _enriched_row(
            'AVGO', score=56.07, archetype='bullish_trend',
            mag=6.47, cons=0.83, rev=0.17, n_q=12,
        )
        lines = _playability_lines([row])
        line = lines[1]
        # Each component visible
        assert '**AVGO**' in line
        assert '`56`' in line
        assert 'bullish_trend' in line
        assert 'gap 6.5%' in line          # rounded to 1 decimal
        assert 'cons dir 83%' in line
        assert 'rev 17%' in line
        assert 'bullish gap play' in line  # Option A action hint
        # n=12 = full sample → suppressed (header already says 12Q)
        assert 'n=12' not in line

    def test_short_sample_shows_n_count(self):
        """When a ticker has fewer than 12 valid quarters (e.g. some
        reports skipped due to missing OHLCV), surface the count so
        the reader knows the sample is short."""
        row = _enriched_row('NEW', score=30, n_q=8)
        lines = _playability_lines([row])
        line = lines[1]
        assert 'n=8' in line

    def test_full_sample_suppresses_n_count(self):
        """The header says 12Q already — don't repeat per row."""
        row = _enriched_row('FULL', score=30, n_q=12)
        lines = _playability_lines([row])
        assert 'n=' not in lines[1]

    def test_archetype_to_hint_mapping(self):
        archetypes_and_hints = [
            ('bullish_trend', 'bullish gap play'),
            ('bearish_trend', 'bearish gap play'),
            ('reversal_play', 'gap reversal play'),
            ('mixed',         'low conviction'),
            ('quiet',         'skip'),
        ]
        for archetype, expected_hint in archetypes_and_hints:
            row = _enriched_row('XYZ', score=10, archetype=archetype)
            lines = _playability_lines([row])
            assert expected_hint in lines[1], (
                f'{archetype} → expected hint {expected_hint!r} '
                f'in line: {lines[1]!r}'
            )

    def test_mixed_scored_and_unscored_rows(self):
        """Some rows have scores, some don't — only scored ones appear."""
        rows = [
            _enriched_row('SCORED1', score=50),
            {'ticker': 'NOSCORE', 'playability_score': None},
            _enriched_row('SCORED2', score=80),
        ]
        lines = _playability_lines(rows)
        # 1 header + 2 ranked rows
        assert len(lines) == 3
        assert '**SCORED2**' in lines[1]  # higher score first
        assert '**SCORED1**' in lines[2]
        # NOSCORE doesn't appear at all
        assert all('NOSCORE' not in l for l in lines)

    def test_indentation_for_visual_nesting(self):
        """All lines start with two spaces so they nest under the parent
        BMO/AMC section in Discord."""
        rows = [_enriched_row('AAA', score=50)]
        lines = _playability_lines(rows)
        for line in lines:
            assert line.startswith('  '), f'missing indent: {line!r}'

    def test_zero_score_excluded(self):
        """A score of 0 (real, non-None) is allowed but rare. Test it
        renders correctly without crashing."""
        rows = [_enriched_row('ZERO', score=0.0)]
        lines = _playability_lines(rows)
        assert len(lines) == 2  # header + 1 row
        assert '`0`' in lines[1]

    def test_none_inputs_render_as_zero_in_display(self):
        """Defensive — if some intermediate fields are None, display 0
        rather than crashing."""
        row = {
            'ticker': 'PARTIAL',
            'playability_score': 42.5,
            'playability_archetype': 'mixed',
            'playability_move_mag_pct': None,
            'playability_dir_consistency': None,
            'playability_reversal_rate': None,
            'playability_n_q': 0,
        }
        lines = _playability_lines([row])
        assert len(lines) == 2
        line = lines[1]
        # Should render without error; values display as 0
        assert 'gap 0.0%' in line
        assert 'cons dir 0%' in line
        assert 'rev 0%' in line
        assert 'low conviction' in line  # archetype=mixed → Option A hint
        # n=0 is below target → surface the short-sample warning
        assert 'n=0' in line
