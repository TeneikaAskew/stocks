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
from datetime import date, timedelta

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


# ────────────────────────────────────────────────────────────
# Best-exit / worst-drawdown over the swing window (PR #240)
# Window starts at reaction-day bar (D for BMO, D+1 for AMC).
# Anchor matches sustain math: D close (BMO) or D+1 open (AMC).
# ────────────────────────────────────────────────────────────

class TestComputeReactionSwingWindowExtremes:

    def test_amc_max_high_3d_above_d_plus_3_close(self):
        """The screenshot's PRIME case: stock spikes to a peak on day +1
        but closes lower; sustain_3d_close shows 0% but max_high captures
        the actual best exit."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),     # D-1
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),    # D close=100
            (date(2026, 3, 5), 105.0, 115.0, 104.0, 106.0),   # D+1: anchor=105, high=115 (+9.52%)
            (date(2026, 3, 6), 106.0, 108.0, 102.0, 105.0),
            (date(2026, 3, 9), 105.0, 106.0, 101.0, 105.0),   # D+3 close = 105 (sustain ≈ 0)
            (date(2026, 3, 10), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 11), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 12), 105.0, 106.0, 102.0, 105.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # sustain_3d at the close: D+3 close (105) vs anchor (105) ≈ 0%
        assert abs(r['sustain_3d_pct']) < 0.01
        # But max_high_3d captures the actual peak: high (115) on D+1 vs anchor (105)
        # = (115 - 105) / 105 × 100 = 9.524%
        assert abs(r['max_high_3d_pct'] - 9.524) < 0.01

    def test_amc_min_low_3d_below_d_plus_3_close(self):
        """Mirror case: stock dipped below anchor intraday but recovered."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),
            (date(2026, 3, 5), 105.0, 106.0, 95.0, 105.0),    # D+1 open=105 (anchor), low=95
            (date(2026, 3, 6), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 9), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 10), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 11), 105.0, 106.0, 102.0, 105.0),
            (date(2026, 3, 12), 105.0, 106.0, 102.0, 105.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # min_low_3d: 95 vs 105 anchor = -9.524%
        assert abs(r['min_low_3d_pct'] - (-9.524)) < 0.01

    def test_bmo_window_starts_at_d(self):
        """For BMO reports, the reaction is on D itself; the window
        should INCLUDE D's high/low, not start at D+1."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),    # D-1
            (date(2026, 3, 4), 105.0, 115.0, 104.0, 110.0),  # D = reaction day, high=115 (+10.0%)
            (date(2026, 3, 5), 110.0, 112.0, 108.0, 110.0),
            (date(2026, 3, 6), 110.0, 112.0, 108.0, 110.0),
            (date(2026, 3, 9), 110.0, 112.0, 108.0, 110.0),
            (date(2026, 3, 10), 110.0, 112.0, 108.0, 110.0),
            (date(2026, 3, 11), 110.0, 112.0, 108.0, 110.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'BMO')
        assert r is not None
        # BMO anchor = D close = 110. max_high_3d = max high in [D, D+1, D+2, D+3]
        # = 115 on D itself = (115-110)/110 = +4.55%
        assert abs(r['max_high_3d_pct'] - 4.5455) < 0.01

    def test_5d_and_10d_windows_extend_past_3d(self):
        """A spike on day +6 should appear in 10d but NOT in 3d or 5d windows."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),
            (date(2026, 3, 5), 100.0, 101.0, 99.0, 100.0),    # D+1: anchor=100
            (date(2026, 3, 6), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 9), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 10), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 11), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 12), 100.0, 120.0, 99.0, 100.0),   # D+7: spike to 120
            (date(2026, 3, 13), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 16), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 17), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 18), 100.0, 101.0, 99.0, 100.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # 3d window: [D+1..D+4] = max high 101 → +1.0%
        assert abs(r['max_high_3d_pct'] - 1.0) < 0.01
        # 5d window: [D+1..D+6] = still 101 (spike on D+7 not yet) → +1.0%
        assert abs(r['max_high_5d_pct'] - 1.0) < 0.01
        # 10d window: [D+1..D+11] = includes D+7 spike → +20.0%
        assert abs(r['max_high_10d_pct'] - 20.0) < 0.01

    def test_truncated_window_returns_null(self):
        """If the daily window doesn't reach D+10, max_high_10d_pct stays NULL
        but the 3d / 5d versions still populate when their windows fit."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),
            (date(2026, 3, 5), 100.0, 105.0, 99.0, 100.0),    # D+1
            (date(2026, 3, 6), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 9), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 10), 100.0, 101.0, 99.0, 100.0),
            # No data past D+5 — 10d window can't fit
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # 3d fits — should be populated (max high 105 vs anchor 100 = +5%)
        assert abs(r['max_high_3d_pct'] - 5.0) < 0.01
        # 10d doesn't fit — should be NULL
        assert r['max_high_10d_pct'] is None
        assert r['min_low_10d_pct'] is None

    def test_split_anomaly_nulls_the_extreme(self):
        """A 3-for-1 split between D+1 and D+5 produces a fictitious -66%
        min_low. Should be nulled the same way sustain handles it."""
        df = _bars([
            (date(2026, 3, 3), 100.0, 101.0, 99.0, 100.0),
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 100.0),
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),   # D+1 anchor=105
            (date(2026, 3, 6), 106.0, 108.0, 105.0, 107.0),
            (date(2026, 3, 9), 107.0, 109.0, 106.0, 108.0),
            (date(2026, 3, 10), 108.0, 110.0, 107.0, 109.0),
            (date(2026, 3, 11), 36.0, 37.0, 35.0, 36.5),       # 3-for-1 split → low 35
            (date(2026, 3, 12), 36.5, 37.5, 36.0, 37.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # min_low_5d would be 35 vs 105 = -66.7%, exceeds 50% anomaly cap → null
        assert r['min_low_5d_pct'] is None


# ────────────────────────────────────────────────────────────
# _resolve_tickers — broadened default scope (Phase 1.6 fix)
# ────────────────────────────────────────────────────────────

class TestResolveTickersBroadScope:
    """Default scope changed from "watchlist + tomorrow's brief-set"
    to "every ticker in earnings_history" so the brief sees historical
    profiles for all major reporters automatically."""

    def test_default_returns_all_earnings_history_tickers(self, monkeypatch):
        """The new default queries earnings_history (broad), not the
        narrow brief-set + watchlist union."""
        import argparse
        from gcp.fetchers import compute_earnings_reactions as cer

        captured = {}
        def fake_query(sql, params=None):
            captured['sql'] = sql
            return pd.DataFrame({'ticker': ['AMZN', 'AVGO', 'MSFT', 'NVDA']})
        monkeypatch.setattr(cer, 'query_to_dataframe', fake_query)

        args = argparse.Namespace(tickers=None, dry_run=False)
        result = cer._resolve_tickers(args)
        assert result == ['AMZN', 'AVGO', 'MSFT', 'NVDA']
        # Verify it queries earnings_history, not the narrow brief-set
        sql_upper = captured['sql'].upper()
        assert 'EARNINGS_HISTORY' in sql_upper
        # No longer scoped via watchlists or earnings_calendar
        assert 'WATCHLISTS' not in sql_upper
        assert 'EARNINGS_CALENDAR' not in sql_upper

    def test_filters_placeholder_rows(self, monkeypatch):
        """The query should exclude placeholder rows (NULL or 0
        reported_eps) so we don't waste compute on rows that aren't
        actually reports yet."""
        import argparse
        from gcp.fetchers import compute_earnings_reactions as cer

        captured = {}
        def fake_query(sql, params=None):
            captured['sql'] = sql
            return pd.DataFrame({'ticker': ['AAA']})
        monkeypatch.setattr(cer, 'query_to_dataframe', fake_query)

        args = argparse.Namespace(tickers=None, dry_run=False)
        cer._resolve_tickers(args)
        # The placeholder filter pattern from the rest of the codebase
        sql_compact = ' '.join(captured['sql'].split())
        assert 'reported_eps > 0 OR reported_eps < 0' in sql_compact

    def test_explicit_tickers_override_still_works(self):
        """--tickers override bypasses DB query entirely."""
        import argparse
        from gcp.fetchers import compute_earnings_reactions as cer

        args = argparse.Namespace(tickers='avgo,nvda,fdx', dry_run=False)
        result = cer._resolve_tickers(args)
        assert result == ['AVGO', 'NVDA', 'FDX']

    def test_empty_db_returns_empty(self, monkeypatch):
        import argparse
        from gcp.fetchers import compute_earnings_reactions as cer
        monkeypatch.setattr(cer, 'query_to_dataframe',
                            lambda sql, params=None: pd.DataFrame())
        args = argparse.Namespace(tickers=None, dry_run=False)
        assert cer._resolve_tickers(args) == []


# ────────────────────────────────────────────────────────────
# ATR context (added 2026-05-04). Extends the daily window with an
# atr_14 column and asserts compute_reaction emits the 4 new
# size-relative fields. Independent test class so the existing
# _bars() helper stays untouched (it builds frames WITHOUT atr_14
# to confirm graceful-NULL behaviour for legacy data).
# ────────────────────────────────────────────────────────────

def _bars_with_atr(prices_per_day):
    """Build a daily OHLCV DataFrame WITH an atr_14 column.

    Each row tuple: (date, o, h, l, c, atr_14)
    """
    rows = [
        {'date': d, 'open': o, 'high': h, 'low': l, 'close': c,
         'volume': 100_000, 'atr_14': atr}
        for d, o, h, l, c, atr in prices_per_day
    ]
    return pd.DataFrame(rows)


class TestComputeReactionATR:
    """Timing-aware ATR columns:
       pre_report_atr / pre_report_atr_pct / post_report_atr /
       reaction_day_range / reaction_day_range_in_atr_units.

    Mapping:
       BMO: pre = atr on D-1, post = atr on D, reaction_bar = D
       AMC: pre = atr on D,  post = atr on D+1, reaction_bar = D+1
    """

    def test_amc_uses_d_for_pre_and_d_plus_1_for_reaction(self):
        """AMC report: D is normal trading (pre), D+1 is the reaction day."""
        df = _bars_with_atr([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0, 2.0),    # D-1
            (date(2026, 3, 4), 100.0, 102.0, 99.0, 101.0, 2.2),   # D = pre
            (date(2026, 3, 5), 105.0, 115.0, 104.0, 110.0, 3.0),  # D+1 = reaction (range 11.0)
            (date(2026, 3, 6), 110.0, 111.0, 109.0, 110.0, 3.1),
            (date(2026, 3, 9), 110.0, 111.0, 109.0, 110.0, 3.2),
            (date(2026, 3, 10), 110.0, 111.0, 109.0, 110.0, 3.3),
            (date(2026, 3, 11), 110.0, 111.0, 109.0, 110.0, 3.4),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        # AMC: pre = D's atr (2.2), post = D+1's atr (3.0)
        assert r['pre_report_atr'] == 2.2
        assert r['post_report_atr'] == 3.0
        # pre_atr_pct: 2.2 / 101.0 (D close) * 100 ≈ 2.178
        assert abs(r['pre_report_atr_pct'] - 2.178) < 0.01
        # reaction-day range: D+1 high - D+1 low = 115 - 104 = 11.0
        assert r['reaction_day_range'] == 11.0
        # range/pre_atr: 11.0 / 2.2 = 5.0
        assert abs(r['reaction_day_range_in_atr_units'] - 5.0) < 0.001

    def test_bmo_uses_d_minus_1_for_pre_and_d_for_reaction(self):
        """BMO report: D-1 is pre-report (last bar before), D is the
        reaction day (gap-and-go on the open)."""
        df = _bars_with_atr([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0, 2.0),    # D-1 = pre
            (date(2026, 3, 4), 105.0, 115.0, 104.0, 110.0, 3.0),  # D = reaction (range 11.0)
            (date(2026, 3, 5), 110.0, 112.0, 109.0, 111.0, 3.1),
            (date(2026, 3, 6), 111.0, 112.0, 110.0, 111.0, 3.2),
            (date(2026, 3, 9), 111.0, 112.0, 110.0, 111.0, 3.3),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'BMO')
        assert r is not None
        # BMO: pre = D-1's atr (2.0), post = D's atr (3.0)
        assert r['pre_report_atr'] == 2.0
        assert r['post_report_atr'] == 3.0
        # pre_atr_pct: 2.0 / 100.0 (D-1 close) * 100 = 2.0
        assert abs(r['pre_report_atr_pct'] - 2.0) < 0.001
        # reaction-day range: D high - D low = 115 - 104 = 11.0
        assert r['reaction_day_range'] == 11.0
        # range/pre_atr: 11.0 / 2.0 = 5.5
        assert abs(r['reaction_day_range_in_atr_units'] - 5.5) < 0.001

    def test_amc_mck_2026_02_screenshot_match(self):
        """Smoke test against the McKesson 2026-02-04 AMC report. Real
        numbers from market_data_daily — confirms the timing-aware
        calc reproduces the third-party screenshot's 6.0× day-range/ATR
        for AMC reports (the buggy first cut produced 1.92×)."""
        df = _bars_with_atr([
            (date(2026, 1, 21), 800.0, 802.0, 798.0, 800.0, 17.0),
            (date(2026, 1, 22), 800.0, 802.0, 798.0, 800.0, 17.1),
            (date(2026, 1, 23), 800.0, 802.0, 798.0, 800.0, 17.2),
            (date(2026, 1, 26), 800.0, 802.0, 798.0, 800.0, 17.3),
            (date(2026, 1, 27), 800.0, 802.0, 798.0, 800.0, 17.4),
            (date(2026, 1, 28), 800.0, 802.0, 798.0, 800.0, 17.5),
            (date(2026, 1, 29), 800.0, 802.0, 798.0, 800.0, 17.6),
            (date(2026, 1, 30), 800.0, 802.0, 798.0, 800.0, 17.7),
            (date(2026, 2, 2),  800.0, 802.0, 798.0, 800.0, 17.7),
            (date(2026, 2, 3),  850.0, 852.0, 848.0, 851.12, 17.68),  # D-1
            # D = AMC report day (still a regular session, 33.94 range)
            (date(2026, 2, 4),  845.0, 851.11, 817.17, 822.0, 18.80),  # D = pre
            # D+1 = reaction day. $109.93 range — the 6× ATR move.
            (date(2026, 2, 5),  862.0, 971.93, 862.0, 957.80, 22.50),  # D+1 = reaction
            (date(2026, 2, 6),  957.0, 960.0, 950.0, 955.0, 22.0),
            (date(2026, 2, 9),  955.0, 957.0, 950.0, 953.0, 21.8),
            (date(2026, 2, 10), 953.0, 955.0, 949.0, 952.0, 21.6),
        ])
        r = compute_reaction(_eps(date(2026, 2, 4)), df, 'AMC')
        assert r is not None
        # Pre-report ATR for AMC = atr on D = 18.80 (matches third-party)
        assert r['pre_report_atr'] == 18.80
        # Reaction day range = 971.93 - 862.00 = 109.93
        assert abs(r['reaction_day_range'] - 109.93) < 0.01
        # 109.93 / 18.80 = 5.847... ≈ the screenshot's 6.0×
        assert abs(r['reaction_day_range_in_atr_units'] - 5.847) < 0.01

    def test_atr_columns_null_when_atr_14_missing_from_frame(self):
        """Legacy daily windows (no atr_14 column at all) — the populator
        must return the row with reaction stats intact and ATR fields NULL."""
        df = _bars([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0),
            (date(2026, 3, 4), 100.0, 105.0, 99.0, 102.0),
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['pre_report_atr'] is None
        assert r['pre_report_atr_pct'] is None
        assert r['post_report_atr'] is None
        # reaction_day_range comes from raw OHLC, doesn't need atr_14
        assert r['reaction_day_range'] is not None
        # but the ratio needs pre_atr — null without it
        assert r['reaction_day_range_in_atr_units'] is None
        # And the existing reaction fields are unaffected
        assert r['reaction_gap_pct'] is not None

    def test_amc_pre_atr_null_when_d_atr_is_nan(self):
        """Even if the column exists, individual NaN values stay NULL.
        For AMC, pre_report_atr looks at D — if D's atr is NaN, pre is null."""
        import numpy as np
        df = _bars_with_atr([
            (date(2026, 3, 3), 99.0, 100.5, 98.5, 100.0, 2.0),
            (date(2026, 3, 4), 100.0, 105.0, 99.0, 102.0, np.nan),  # D atr missing
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0, 2.4),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['pre_report_atr'] is None       # AMC pre = D's atr (NaN)
        assert r['pre_report_atr_pct'] is None
        # reaction-day range computable from raw OHLC
        assert r['reaction_day_range'] is not None
        # But ratio needs pre — null
        assert r['reaction_day_range_in_atr_units'] is None
        # post_report_atr (D+1 for AMC) is independent and present
        assert r['post_report_atr'] == 2.4

    def test_inline_atr14_fallback_when_upstream_column_missing(self):
        """When ``atr_14`` is NaN/missing but the daily window has ≥15
        bars, the populator computes ATR-14 inline from OHLC and produces
        a non-NULL pre_report_atr. Guards against the regression where
        the column was 1.7%-populated upstream and silently NULLed 99%
        of earnings_reactions rows for the brief."""
        import numpy as np
        # 16 bars (15 pre + 1 reaction). Synthetic OHLC with constant
        # 2.0-wide bars makes ATR-14 deterministic.
        rows = []
        for i in range(15):
            d = date(2026, 3, 2) + timedelta(days=i)
            # weekday-only — skip weekends
            if d.weekday() >= 5:
                continue
            rows.append((d, 100.0, 102.0, 100.0, 101.0, np.nan))
        # tack on extras until we have at least 17 trading days
        cur = rows[-1][0] + timedelta(days=1)
        while len(rows) < 18:
            if cur.weekday() < 5:
                rows.append((cur, 100.0, 102.0, 100.0, 101.0, np.nan))
            cur += timedelta(days=1)
        df = _bars_with_atr(rows)
        # Pick a D that has 14+ prior bars in the frame
        d_report = df.iloc[15]['date']
        r = compute_reaction(_eps(d_report), df, 'AMC')
        assert r is not None, "compute should succeed with 16 bars"
        assert r['pre_report_atr'] is not None, \
            "inline ATR-14 should fire when upstream is NaN"
        # All bars have TR = high - low = 2.0; ATR-14 converges to 2.0
        assert abs(r['pre_report_atr'] - 2.0) < 0.01

    def test_atr_ratio_null_when_pre_atr_is_zero(self):
        """A zero pre-report ATR (synthetic / market-closed edge case)
        shouldn't produce a divide-by-zero — the ratio stays NULL.

        Post-fix semantics: a zero atr_14 in the daily frame is treated
        as 'missing' and triggers the inline ATR-14 fallback in _atr().
        With only 3 bars in this fixture the inline fallback also can't
        compute (needs 14 prior bars), so pre_report_atr surfaces as
        None. The original assertion only cared that the ratio not
        divide-by-zero — both old (=0.0) and new (=None) shapes satisfy
        that, and None is a more honest value for a meaningless 0 ATR.
        """
        df = _bars_with_atr([
            (date(2026, 3, 3), 100.0, 100.0, 100.0, 100.0, 1.0),
            (date(2026, 3, 4), 100.0, 100.0, 100.0, 100.0, 0.0),  # D atr = 0 (AMC pre)
            (date(2026, 3, 5), 105.0, 107.0, 104.0, 106.0, 0.7),
        ])
        r = compute_reaction(_eps(date(2026, 3, 4)), df, 'AMC')
        assert r is not None
        assert r['pre_report_atr'] is None
        # ratio undefined regardless of which path produced the None
        assert r['reaction_day_range_in_atr_units'] is None


# ─────────────────────────────────────────────────────────────
# fetch_daily_windows_for_ticker_dates — per-ticker batching
# (issue #452 — N+1 → 1 SQL query per ticker)
# ─────────────────────────────────────────────────────────────

from unittest.mock import patch

class TestFetchDailyWindowsForTickerDates:
    """The bulk fetcher is the architectural fix for the 30-min Cloud Run
    task-timeout — it MUST issue exactly one query per ticker (not one
    per reported_date). Pin that contract with a query-counter test."""

    def _sample_bars(self):
        """30-year daily-bar coverage spanning two reported_dates."""
        import pandas as pd
        from datetime import date as _date, timedelta as _td
        rows = []
        start = _date(2025, 1, 1)
        for i in range(500):
            d = start + _td(days=i)
            rows.append({
                'date': d, 'open': 100.0, 'high': 101.0,
                'low':  99.0, 'close': 100.5, 'volume': 1000,
                'atr_14': 1.5,
            })
        return pd.DataFrame(rows)

    def test_empty_reported_dates_returns_empty(self):
        from gcp.fetchers.compute_earnings_reactions import (
            fetch_daily_windows_for_ticker_dates,
        )
        out = fetch_daily_windows_for_ticker_dates('AAPL', [])
        assert out == {}

    def test_one_query_per_ticker_regardless_of_date_count(self):
        """4 reported_dates → 1 SQL query (not 4). This is the contract
        that makes the timeout fix work."""
        from gcp.fetchers import compute_earnings_reactions as cer
        bars = self._sample_bars()
        with patch.object(cer, 'query_to_dataframe', return_value=bars) as qm:
            from datetime import date
            out = cer.fetch_daily_windows_for_ticker_dates(
                'AAPL',
                [date(2025, 2, 1), date(2025, 4, 15),
                 date(2025, 6, 1), date(2025, 12, 1)],
            )
        assert qm.call_count == 1, (
            "bulk fetcher must issue exactly one DB round-trip per ticker "
            "regardless of how many reported_dates are passed in"
        )
        assert set(out.keys()) == {
            __import__('datetime').date(2025, 2, 1),
            __import__('datetime').date(2025, 4, 15),
            __import__('datetime').date(2025, 6, 1),
            __import__('datetime').date(2025, 12, 1),
        }

    def test_window_slices_per_reported_date(self):
        """Each returned df is bounded to [reported_date-40d, +25d].
        The -40 floor gives the inline ATR-14 fallback its 14 prior bars."""
        from gcp.fetchers import compute_earnings_reactions as cer
        bars = self._sample_bars()
        from datetime import date, timedelta
        with patch.object(cer, 'query_to_dataframe', return_value=bars):
            out = cer.fetch_daily_windows_for_ticker_dates(
                'AAPL', [date(2025, 6, 1)],
            )
        win = out[date(2025, 6, 1)]
        assert not win.empty
        assert win['date'].min() >= date(2025, 6, 1) - timedelta(days=40)
        assert win['date'].max() <= date(2025, 6, 1) + timedelta(days=25)

    def test_empty_db_returns_empty_window_per_date(self):
        """If market_data_daily has no rows for the ticker (sparse data),
        every reported_date maps to an empty DataFrame so the caller's
        compute_reaction returns None for each — never crashes."""
        import pandas as pd
        from gcp.fetchers import compute_earnings_reactions as cer
        from datetime import date
        with patch.object(cer, 'query_to_dataframe',
                          return_value=pd.DataFrame()):
            out = cer.fetch_daily_windows_for_ticker_dates(
                'XYZ',
                [date(2025, 1, 1), date(2025, 6, 1)],
            )
        assert all(df.empty for df in out.values())
        assert set(out.keys()) == {date(2025, 1, 1), date(2025, 6, 1)}

    def test_query_range_covers_union_of_dates(self):
        """The single SQL query's date range must cover the union of all
        reported_dates' windows — min-40d to max+25d. The -40 floor (was
        -20) gives the inline ATR-14 fallback its 14 prior trading bars."""
        from gcp.fetchers import compute_earnings_reactions as cer
        bars = self._sample_bars()
        from datetime import date, timedelta
        with patch.object(cer, 'query_to_dataframe', return_value=bars) as qm:
            cer.fetch_daily_windows_for_ticker_dates(
                'AAPL', [date(2025, 2, 1), date(2025, 10, 1)],
            )
        args, kwargs = qm.call_args
        # query_to_dataframe(sql, params) — params is the 2nd positional
        params = args[1] if len(args) > 1 else kwargs.get('params') or kwargs
        # Accept either dict-style or kwargs-style param passing
        if hasattr(params, 'get'):
            assert params['start'] == date(2025, 2, 1) - timedelta(days=40)
            assert params['end']   == date(2025, 10, 1) + timedelta(days=25)
