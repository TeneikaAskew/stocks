"""Unit tests for gcp/fetchers/compute_earnings_reactions.py

Focus on the pure-compute layer (`normalize_timing`, `compute_reaction`)
which can be tested without Cloud SQL.

Covers:
- AMC happy path (post-market reporter)
- BMO happy path (pre-market reporter)
- Timing normalization (various source formats)
- Edge cases: missing D-1, missing D+1, missing D+5/D+10, no D-10
- Reversal flag firing correctly
- Direction consistency edge cases (zero reaction_gap)
"""
from datetime import date

import pandas as pd
import pytest

from gcp.fetchers.compute_earnings_reactions import (
    normalize_timing,
    compute_reaction,
)


# ────────────────────────────────────────────────────────────
# normalize_timing — resolves reaction_basis from the two sources
# ────────────────────────────────────────────────────────────

class TestNormalizeTiming:
    def test_report_time_pre_market_wins(self):
        assert normalize_timing('pre-market', None) == 'BMO'

    def test_report_time_post_market_wins(self):
        assert normalize_timing('post-market', None) == 'AMC'

    def test_report_time_takes_precedence_over_calendar(self):
        # AV report_time says BMO, calendar says postmarket
        # AV wins over calendar (Yahoo not present)
        assert normalize_timing('pre-market', 'postmarket') == 'BMO'

    def test_calendar_fallback_premarket(self):
        assert normalize_timing(None, 'premarket') == 'BMO'

    def test_calendar_fallback_postmarket(self):
        assert normalize_timing(None, 'postmarket') == 'AMC'

    def test_both_missing_defaults_amc(self):
        assert normalize_timing(None, None) == 'AMC'

    def test_unknown_value_falls_through(self):
        # 'unknown' is not in the recognized list → falls back to next source
        assert normalize_timing('unknown', 'premarket') == 'BMO'

    def test_both_unknown_defaults_amc(self):
        assert normalize_timing('unknown', 'unknown') == 'AMC'

    def test_case_insensitive(self):
        assert normalize_timing('Pre-Market', None) == 'BMO'
        assert normalize_timing('POST-MARKET', None) == 'AMC'

    def test_whitespace_handled(self):
        assert normalize_timing('  pre-market  ', None) == 'BMO'

    def test_empty_string_falls_through(self):
        assert normalize_timing('', 'postmarket') == 'AMC'

    # ── Yahoo precedence tests (added 2026-05-01 per user directive) ──

    def test_yahoo_overrides_av_disagreement(self):
        """The NVDA 2026-02-25 case: AV=pre-market (wrong), Yahoo=post-market.
        Yahoo wins. This is the exact bug the directive came from."""
        result = normalize_timing(
            report_time='pre-market',
            earnings_time=None,
            yahoo_report_time='post-market',
        )
        assert result == 'AMC'

    def test_yahoo_overrides_av_other_direction(self):
        """Yahoo says BMO, AV says AMC — Yahoo wins."""
        result = normalize_timing(
            report_time='post-market',
            earnings_time='postmarket',
            yahoo_report_time='pre-market',
        )
        assert result == 'BMO'

    def test_yahoo_missing_falls_back_to_av(self):
        """When yahoo_report_time is None, AV report_time is the source."""
        result = normalize_timing(
            report_time='post-market',
            earnings_time=None,
            yahoo_report_time=None,
        )
        assert result == 'AMC'

    def test_yahoo_present_av_missing(self):
        """Yahoo alone is sufficient when AV is missing."""
        result = normalize_timing(
            report_time=None,
            earnings_time=None,
            yahoo_report_time='pre-market',
        )
        assert result == 'BMO'

    def test_yahoo_unknown_falls_through_to_av(self):
        """Yahoo 'unknown' value falls through to AV (next in precedence)."""
        result = normalize_timing(
            report_time='post-market',
            earnings_time=None,
            yahoo_report_time='unknown',
        )
        assert result == 'AMC'


# ────────────────────────────────────────────────────────────
# compute_reaction — core math
# ────────────────────────────────────────────────────────────

def _bars(prices_per_day):
    """Build a daily OHLCV DataFrame from a list of (date, o, h, l, c) tuples."""
    rows = [
        {'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': 100_000}
        for d, o, h, l, c in prices_per_day
    ]
    return pd.DataFrame(rows)


def _eps(reported_date, ticker='TEST', surprise_pct=2.5):
    return {
        'ticker': ticker,
        'fiscal_date_ending': date(2026, 1, 31),
        'reported_date': reported_date,
        'reported_eps': 2.05,
        'estimated_eps': 2.00,
        'surprise_pct': surprise_pct,
    }


class TestComputeReactionAMC:
    """AMC: report drops 4:15 PM on D. Reaction = D+1 open vs D close."""

    def _build_bars(self):
        # 15 trading days, simple linear, with a clear "earnings reaction" on D+1.
        # D = 2026-03-04 (Wednesday). Need D-10..D+10.
        return _bars([
            # D-10..D-1 — drift up from 100 to 110
            (date(2026, 2, 18), 100.0, 101.0, 99.5, 100.5),
            (date(2026, 2, 19), 100.5, 102.0, 100.0, 101.0),
            (date(2026, 2, 20), 101.0, 103.0, 100.5, 102.0),
            (date(2026, 2, 23), 102.0, 104.0, 101.5, 103.0),
            (date(2026, 2, 24), 103.0, 105.0, 102.5, 104.0),
            (date(2026, 2, 25), 104.0, 106.0, 103.5, 105.0),
            (date(2026, 2, 26), 105.0, 107.0, 104.5, 106.0),
            (date(2026, 2, 27), 106.0, 108.0, 105.5, 107.0),
            (date(2026, 3, 2),  107.0, 109.0, 106.5, 108.0),
            (date(2026, 3, 3),  108.0, 110.5, 107.5, 110.0),  # D-1 close = 110
            # D — report day (AMC report drops at 4:15 PM)
            (date(2026, 3, 4),  110.5, 112.0, 109.5, 111.0),  # close = 111
            # D+1 — gap up (the reaction)
            (date(2026, 3, 5),  120.0, 125.0, 119.0, 122.0),  # open = 120 (gap +8.1%)
            # D+2..D+5 — fade slightly
            (date(2026, 3, 6),  121.0, 122.0, 119.5, 121.5),
            (date(2026, 3, 9),  121.0, 123.0, 120.0, 122.5),
            (date(2026, 3, 10), 122.0, 123.5, 121.0, 123.0),
            (date(2026, 3, 11), 122.5, 124.0, 121.0, 123.5),  # D+5 close = 123.5
            (date(2026, 3, 12), 123.0, 124.5, 122.0, 123.0),
            (date(2026, 3, 13), 122.5, 124.0, 121.5, 122.0),
            (date(2026, 3, 16), 121.0, 123.0, 120.0, 121.5),
            (date(2026, 3, 17), 121.5, 122.0, 120.0, 120.5),
            (date(2026, 3, 18), 120.0, 121.5, 119.0, 121.0),  # D+10 close = 121
        ])

    def test_amc_reaction_gap_is_d1_open_vs_d_close(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # post_gap = (120.00 - 111.00) / 111.00 * 100 ≈ 8.1081
        assert abs(r['post_gap_pct'] - 8.1081) < 0.01
        assert abs(r['reaction_gap_pct'] - 8.1081) < 0.01
        assert r['reaction_basis'] == 'AMC'
        # Anchor for AMC = D+1 open
        assert r['reaction_anchor_price'] == 120.0

    def test_amc_sustain_5d_anchored_at_d_plus_1_open(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        # sustain_5d = (D+5 close 123.5 - D+1 open 120.0) / 120.0 * 100 ≈ 2.917%
        assert abs(r['sustain_5d_pct'] - 2.9167) < 0.01

    def test_amc_pre_drift_10d(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        # D-10 close = 100.5 (from 2026-02-18). D-1 close = 110.0
        # drift = (110.0 - 100.5) / 100.5 ≈ 9.45%
        assert r['d_minus_10_close'] == 100.5
        assert r['d_minus_1_close'] == 110.0
        assert abs(r['pre_earnings_drift_10d_pct'] - 9.4527) < 0.01

    def test_amc_max_run_and_drawdown(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        # On D+1: open=120, high=125, low=119
        # max_run = (125 - 120) / 120 * 100 ≈ 4.17%
        # max_drawdown = (119 - 120) / 120 * 100 ≈ -0.83%
        assert abs(r['reaction_max_run_pct'] - 4.1667) < 0.01
        assert abs(r['reaction_max_drawdown_pct'] - (-0.8333)) < 0.01

    def test_amc_direction_consistent(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        # reaction_gap +8.1%, sustain_5d +2.9% — same sign
        assert r['direction_consistent_5d'] is True
        assert r['is_reversal_5d'] is False


class TestComputeReactionBMO:
    """BMO: report drops 6:30 AM on D. Reaction = D open vs D-1 close."""

    def _build_bars(self):
        return _bars([
            (date(2026, 1, 21), 100.0, 101.0, 99.5, 100.5),
            (date(2026, 1, 22), 100.5, 102.0, 100.0, 101.0),
            (date(2026, 1, 23), 101.0, 103.0, 100.5, 102.0),
            (date(2026, 1, 26), 102.0, 104.0, 101.5, 103.0),
            (date(2026, 1, 27), 103.0, 105.0, 102.5, 104.0),
            (date(2026, 1, 28), 104.0, 106.0, 103.5, 105.0),
            (date(2026, 1, 29), 105.0, 107.0, 104.5, 106.0),
            (date(2026, 1, 30), 106.0, 108.0, 105.5, 107.0),
            (date(2026, 2, 2),  107.0, 109.0, 106.5, 108.0),
            (date(2026, 2, 3),  108.0, 110.5, 107.5, 110.0),  # D-1 close = 110
            # D — report drops 6:30 AM, market opens with a big gap
            (date(2026, 2, 4),  120.0, 125.0, 118.0, 122.0),  # open=120 (gap +9.09%), close=122
            # D+1..D+5
            (date(2026, 2, 5),  121.5, 123.0, 119.0, 119.5),
            (date(2026, 2, 6),  119.0, 121.0, 118.5, 120.5),
            (date(2026, 2, 9),  120.0, 122.0, 119.0, 121.0),
            (date(2026, 2, 10), 121.0, 122.5, 120.0, 121.5),
            (date(2026, 2, 11), 121.0, 123.0, 120.0, 122.5),  # D+5 (sustain anchor=D close=122; sustain ≈ +0.41%)
            (date(2026, 2, 12), 122.0, 124.0, 121.0, 123.0),
            (date(2026, 2, 13), 122.5, 123.5, 121.5, 122.0),
            (date(2026, 2, 17), 121.0, 122.0, 119.5, 120.5),
            (date(2026, 2, 18), 120.0, 121.0, 119.0, 119.5),
        ])

    def test_bmo_reaction_gap_is_d_open_vs_d_minus_1_close(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 2, 4)), df, 'BMO')
        assert r is not None
        # pre_gap = (120 - 110) / 110 * 100 ≈ 9.0909%
        assert abs(r['pre_report_gap_pct'] - 9.0909) < 0.01
        assert abs(r['reaction_gap_pct'] - 9.0909) < 0.01
        assert r['reaction_basis'] == 'BMO'
        # Anchor for BMO = D close
        assert r['reaction_anchor_price'] == 122.0

    def test_bmo_sustain_5d_anchored_at_d_close(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 2, 4)), df, 'BMO')
        # For BMO, D+5 means "5 trading days after D" = d_idx + 0 + 5 = d_idx + 5
        # In our bars D is at index 10, so D+5 is at index 15 (2026-02-11)
        # close at D+5 = 122.5; anchor = 122.0
        # sustain = (122.5 - 122.0) / 122.0 ≈ 0.41%
        assert abs(r['sustain_5d_pct'] - 0.4098) < 0.01

    def test_bmo_max_run_uses_d_high(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 2, 4)), df, 'BMO')
        # On D: open=120, high=125
        # max_run = (125 - 120) / 120 * 100 ≈ 4.17%
        assert abs(r['reaction_max_run_pct'] - 4.1667) < 0.01

    def test_bmo_post_gap_still_computed_for_completeness(self):
        df = self._build_bars()
        r = compute_reaction(_eps(date(2026, 2, 4)), df, 'BMO')
        # post_gap = (D+1 open 121.5 - D close 122) / 122 = -0.41%
        # We compute this even though reaction_gap uses pre_gap for BMO
        assert abs(r['post_gap_pct'] - (-0.4098)) < 0.01


class TestComputeReactionEdgeCases:
    def test_missing_d_minus_1_returns_none(self):
        """Reported_date is the very first bar — no D-1 available."""
        df = _bars([
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 101.0),
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is None

    def test_missing_d_plus_1_returns_none(self):
        """Reported_date is the very last bar — no D+1 available."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 101.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is None

    def test_empty_daily_returns_none(self):
        r = compute_reaction(_eps(date(2026, 3, 4)), pd.DataFrame(), 'AMC')
        assert r is None

    def test_reported_date_after_window_returns_none(self):
        df = _bars([
            (date(2026, 1, 1), 100.0, 101.0, 99.0, 100.5),
            (date(2026, 1, 2), 100.5, 101.5, 100.0, 101.0),
        ])
        r = compute_reaction(_eps(date(2026, 6, 1)), df, 'AMC')
        assert r is None

    def test_no_d_minus_10_leaves_drift_null_but_returns_row(self):
        """Window only has D-1, D, D+1 — drift_10d should be null but row is OK."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 101.0),
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['d_minus_10_close'] is None
        assert r['pre_earnings_drift_10d_pct'] is None
        # But the reaction itself is computed
        assert r['reaction_gap_pct'] is not None

    def test_no_d_plus_5_leaves_sustain_null_but_returns_row(self):
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 101.0),
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),
            (date(2026, 3, 6), 106.0, 108.0, 105.0, 107.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['sustain_5d_pct'] is None
        assert r['sustain_3d_pct'] is None
        # Reaction still valid
        assert r['reaction_gap_pct'] is not None
        # Direction consistency requires sustain_5d, so it should be None too
        assert r['direction_consistent_5d'] is None
        assert r['is_reversal_5d'] is None

    def test_reversal_detected_when_gap_up_then_dump(self):
        """post_gap +8%, sustain_5d -10% — sign flip + magnitude meets threshold"""
        df = _bars([
            (date(2026, 3, 3), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),  # D close = 100
            (date(2026, 3, 5), 108.0, 110.0, 107.0, 109.0),  # D+1 open = 108 (gap +8%)
            (date(2026, 3, 6), 108.0, 109.0, 105.0, 105.0),
            (date(2026, 3, 9), 105.0, 106.0, 100.0, 100.0),
            (date(2026, 3, 10), 100.0, 101.0, 95.0, 96.0),
            (date(2026, 3, 11), 96.0, 98.0, 95.0, 97.0),
            (date(2026, 3, 12), 97.2, 98.0, 96.5, 97.20),  # D+5 — anchor was 108
            # sustain_5d = (97.20 - 108) / 108 = -10.0%, |sustain| > 0.5*|gap|
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['reaction_gap_pct'] > 0
        assert r['sustain_5d_pct'] < 0
        assert r['direction_consistent_5d'] is False
        assert r['is_reversal_5d'] is True

    def test_no_reversal_when_magnitude_below_threshold(self):
        """post_gap +8%, sustain_5d -1% — sign flip but magnitude too small"""
        df = _bars([
            (date(2026, 3, 3), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),
            (date(2026, 3, 5), 108.0, 110.0, 107.0, 109.0),  # D+1 open = 108
            (date(2026, 3, 6), 108.0, 109.0, 107.0, 108.5),
            (date(2026, 3, 9), 108.5, 109.0, 107.0, 108.0),
            (date(2026, 3, 10), 108.0, 109.0, 107.0, 107.5),
            (date(2026, 3, 11), 107.5, 108.0, 106.0, 107.0),
            (date(2026, 3, 12), 107.0, 108.0, 106.5, 106.92),  # sustain ≈ -1%
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # Sign flipped, but magnitude (1%) << threshold (0.5 * 8% = 4%)
        assert r['direction_consistent_5d'] is False
        assert r['is_reversal_5d'] is False

    def test_zero_reaction_gap_yields_null_consistency(self):
        """When reaction_gap is exactly 0, direction can't be determined."""
        df = _bars([
            (date(2026, 3, 3), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 4), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 5), 100.0, 100.0, 100.0, 100.0),  # D+1 open = D close (zero gap)
            (date(2026, 3, 6), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 9), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 10), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 11), 100.0, 100.0, 100.0, 100.0),
            (date(2026, 3, 12), 100.0, 100.0, 100.0, 100.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['reaction_gap_pct'] == 0.0
        assert r['direction_consistent_5d'] is None
        assert r['is_reversal_5d'] is None

    def test_split_anomaly_nulls_sustain(self):
        """The WMT 2024-02-20 case: 3-for-1 split between D+1 and D+5
        produces a fictitious -66% sustain. compute_reaction must null
        the affected sustain values so they don't poison aggregates."""
        # D=2026-03-04 reaction. Then a 3-for-1 split between D+4 and D+5
        # collapses prices by 1/3.
        df = _bars([
            (date(2026, 3, 3), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),  # D close = 100
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),  # D+1 anchor=105 (AMC)
            (date(2026, 3, 6), 106.0, 108.0, 105.0, 107.0),
            (date(2026, 3, 9), 107.0, 109.0, 106.0, 108.0),
            (date(2026, 3, 10), 108.0, 110.0, 107.0, 109.0),
            (date(2026, 3, 11), 36.0, 37.0, 35.5, 36.5),  # 3-for-1 split executed
            (date(2026, 3, 12), 36.5, 37.5, 36.0, 37.0),
            (date(2026, 3, 13), 37.0, 38.0, 36.5, 37.5),
            (date(2026, 3, 16), 37.0, 38.5, 36.5, 38.0),
            (date(2026, 3, 17), 38.0, 39.0, 37.5, 38.5),
            (date(2026, 3, 18), 38.5, 39.5, 38.0, 39.0),  # D+10 (post-split)
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # Reaction itself is fine (D vs D+1 doesn't span the split)
        assert abs(r['reaction_gap_pct'] - 5.0) < 0.01  # (105-100)/100 = 5%
        # sustain_5d would have been (36.5 - 105) / 105 ≈ -65% — should be NULL
        assert r['sustain_5d_pct'] is None
        # sustain_10d also crossed the split — should be NULL
        assert r['sustain_10d_pct'] is None
        # direction_consistent_5d / is_reversal_5d need sustain_5d, so also NULL
        assert r['direction_consistent_5d'] is None
        assert r['is_reversal_5d'] is None
        # sustain_3d does NOT cross the split (D+3 = 2026-03-09 close=108)
        # = (108 - 105) / 105 ≈ 2.86%, well within threshold
        assert r['sustain_3d_pct'] is not None
        assert abs(r['sustain_3d_pct'] - 2.857) < 0.01

    def test_amc_and_bmo_yield_different_reaction_for_same_bars(self):
        """Sanity check: same OHLCV, different reaction_basis -> different reaction_gap."""
        df = _bars([
            (date(2026, 3, 3), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 4), 105.0, 106.0, 104.0, 105.5),  # gapped up at D open
            (date(2026, 3, 5), 110.0, 112.0, 109.0, 111.0),  # then gapped up again at D+1
            (date(2026, 3, 6), 111.0, 112.0, 110.0, 111.0),
            (date(2026, 3, 9), 111.0, 112.0, 110.0, 111.0),
            (date(2026, 3, 10), 111.0, 112.0, 110.0, 111.0),
            (date(2026, 3, 11), 111.0, 112.0, 110.0, 111.0),
            (date(2026, 3, 12), 111.0, 112.0, 110.0, 111.0),
        ])
        r_amc = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        r_bmo = compute_reaction(_eps(date(2026, 3, 4)), df, 'BMO')
        # AMC reaction = D+1 open vs D close = (110 - 105.5)/105.5 ≈ 4.27%
        # BMO reaction = D open vs D-1 close = (105 - 100)/100 = 5.00%
        assert abs(r_amc['reaction_gap_pct'] - 4.265) < 0.01
        assert abs(r_bmo['reaction_gap_pct'] - 5.0) < 0.01
        assert r_amc['reaction_anchor_price'] == 110.0  # D+1 open
        assert r_bmo['reaction_anchor_price'] == 105.5  # D close
