"""Tests for lib/strat_levels.py — Strat levels engine."""

import pandas as pd
import numpy as np
import pytest

from lib.strat_levels import (
    classify_level_strat,
    _compute_previous_levels as compute_previous_levels,
    _compute_current_levels as compute_current_levels,
    compute_gap_levels,
    detect_level_clusters,
    detect_pmg_temporal,
    compute_risk_reward,
    build_session_levels,
    format_levels_for_brief,
    StratLevel,
    LevelMap,
)
from lib.strat_levels import build_level_map as _build_level_map
from tests.lib.level_params_fixtures import fixture_params
from tests.lib.session_levels_helpers import D8_LEVELS, d8_session


def build_level_map(ticker, df, price, *args, atr=None, **kw):
    """The deprecated shim with the ticker's LevelParams (every key at the
    #1753 values) and the ATR named as ATR(14), the policy's day-one basis."""
    return _build_level_map(ticker, df, price, *args,
                            atr={'atr_14': atr} if atr is not None else {},
                            params=fixture_params(ticker), **kw)


def _daily_df(n=60):
    """Build a sample daily OHLCV DataFrame with ~n trading days."""
    np.random.seed(42)
    dates = pd.bdate_range('2025-01-02', periods=n)
    close = 200 * np.exp(np.cumsum(np.random.normal(0.0003, 0.01, n)))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = np.roll(close, 1)
    open_[0] = 200.0
    return pd.DataFrame({
        'Date': dates,
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': np.random.randint(1_000_000, 5_000_000, n),
    })


# ─── classify_level_strat ─────────────────────────────────────────────────


class TestClassifyLevelStrat:
    def test_inside(self):
        assert classify_level_strat(99, 96, 98, 97, 100, 95) == '1'

    def test_2u_bullish(self):
        assert classify_level_strat(101, 96, 100, 97, 100, 95) == '2U'

    def test_2d_bearish(self):
        assert classify_level_strat(99, 94, 95, 97, 100, 95) == '2D'

    def test_failed_2u(self):
        """Broke prev high but closed bearish (C < O)."""
        assert classify_level_strat(101, 96, 97, 100, 100, 95) == 'Failed_2U'

    def test_failed_2d(self):
        """Broke prev low but closed bullish (C > O)."""
        assert classify_level_strat(99, 94, 98, 96, 100, 95) == 'Failed_2D'

    def test_outside(self):
        assert classify_level_strat(101, 94, 98, 97, 100, 95) == '3'

    def test_equal_is_inside(self):
        """H==pH AND L==pL → inside."""
        assert classify_level_strat(100, 95, 98, 97, 100, 95) == '1'


# ─── compute_previous_levels ──────────────────────────────────────────────


def _prev(df):
    """Previous-period levels with the last row's date as the session, the
    only path the builder uses (no iloc[-2] fallback, FEAT-STRAT-001)."""
    return compute_previous_levels(df, analysis_date=pd.Timestamp(df['Date'].iloc[-1]).date())


class TestComputePreviousLevels:
    def test_returns_daily_levels(self):
        df = _daily_df(30)
        levels = _prev(df)
        assert 'PDH' in levels
        assert 'PDL' in levels
        assert levels['PDH'].timeframe == 'day'
        assert levels['PDL'].level_type == 'low'

    def test_returns_weekly_levels(self):
        df = _daily_df(30)
        levels = _prev(df)
        assert 'PWH' in levels
        assert 'PWL' in levels
        assert levels['PWH'].timeframe == 'week'

    def test_returns_monthly_levels(self):
        df = _daily_df(60)
        levels = _prev(df)
        assert 'PMH' in levels
        assert 'PML' in levels

    def test_returns_quarter_levels(self):
        df = _daily_df(200)
        levels = _prev(df)
        assert 'PQH' in levels
        assert 'PQL' in levels
        assert levels['PQH'].timeframe == 'quarter'

    def test_pdh_price_matches_prev_day_high(self):
        df = _daily_df(30)
        levels = _prev(df)
        expected = float(df['High'].iloc[-2])
        assert levels['PDH'].price == expected

    def test_levels_classified(self):
        df = _daily_df(30)
        levels = _prev(df)
        assert levels['PDH'].strat_class in ('1', '2U', '2D', '3', 'Failed_2U', 'Failed_2D')

    def test_empty_df(self):
        assert compute_previous_levels(pd.DataFrame(), analysis_date=pd.Timestamp('2025-03-03').date()) == {}

    def test_returns_close_levels(self):
        """Close levels (PDC/PWC/PMC/PQC/PYC) ship alongside H/L so
        traders charting against PDC have a source of truth.

        Uses 520 biz days (about 2 years) so a previous year exists for
        the year timeframe (PYC).
        """
        df = _daily_df(520)
        levels = _prev(df)
        for k in ('PDC', 'PWC', 'PMC', 'PQC', 'PYC'):
            assert k in levels, f"missing {k}"
            assert levels[k].level_type == 'close'

    def test_pdc_price_matches_prev_day_close(self):
        df = _daily_df(30)
        levels = _prev(df)
        # analysis_date is the last row's date, so the prior day is iloc[-2]
        expected = float(df['Close'].iloc[-2])
        assert levels['PDC'].price == expected


class TestComputePreviousLevelsAnalysisDate:
    """Tests for the analysis_date path that fixed 2026-05-06 QQQ.

    Without analysis_date, the brief filters today's bar out and the
    function's iloc[-2] picked day-before-yesterday — PDH wrote 5/4's
    high when it should have been 5/5's. The chart's PDH=$682.77
    (5/5 high) but strat_levels persisted PDH=$676.73 (5/4 high), and
    the trade_planner derived a synthetic blue-sky entry of $695.52
    that price never touched."""

    def test_pdh_picks_period_before_analysis_date(self):
        """When analysis_date is given, PDH is the high of the day
        BEFORE analysis_date — not the second-to-last row of df."""
        from datetime import date
        df = _daily_df(30)
        # Pretend analysis_date is the day AFTER df's last bar (the
        # brief's typical state: today excluded by < analysis_date).
        last_bar = pd.to_datetime(df['Date'].iloc[-1]).date()
        # df contains business days; nudge analysis_date one biz day
        # forward — the last bar IS the previous day from
        # analysis_date's perspective.
        analysis_date = (pd.Timestamp(last_bar) + pd.tseries.offsets.BDay(1)).date()
        levels = compute_previous_levels(df, analysis_date=analysis_date)
        assert levels['PDH'].price == float(df['High'].iloc[-1])
        assert levels['PDC'].price == float(df['Close'].iloc[-1])
        assert levels['PDL'].price == float(df['Low'].iloc[-1])

    def test_week_period_picks_week_before_analysis_week(self):
        """Critical fidelity test: when df contains bars from the
        SAME week as analysis_date (e.g. Mon+Tue, with analysis_date
        on Wed), PWH must reflect the PREVIOUS week — not df's last
        bar's week (which is the same as analysis_date's week)."""
        from datetime import date
        # Build a small df spanning two weeks: prev week 5/29-6/2,
        # analysis week 6/5-6/9 with bars on 6/5 and 6/6.
        dates = pd.to_datetime([
            '2025-05-29', '2025-05-30',  # prev week (W22)
            '2025-06-02', '2025-06-03',  # actually still W22
            '2025-06-05', '2025-06-06',  # current week (W23)
        ])
        df = pd.DataFrame({
            'Date': dates,
            'Open':  [100., 101., 102., 103., 104., 105.],
            'High':  [110., 111., 112., 113., 114., 115.],
            'Low':   [ 90.,  91.,  92.,  93.,  94.,  95.],
            'Close': [105., 106., 107., 108., 109., 110.],
        })
        # Analysis date: Wed 6/9 (W24). Last bar 6/6 is in W23.
        analysis_date = date(2025, 6, 9)
        levels = compute_previous_levels(df, analysis_date=analysis_date)
        # Previous week to W24 is W23 → high = max(114, 115) = 115.
        assert levels['PWH'].price == 115.0

    def test_week_period_skips_in_progress_week(self):
        """When analysis_date is in same week as df's last bars (the
        bug scenario), PWH must come from the PRIOR week — not from
        the in-progress week containing analysis_date."""
        from datetime import date
        # Build df where last bars are in same week as analysis_date.
        # 5/4 (Mon) and 5/5 (Tue) are W19 along with 5/6 (Wed).
        dates = pd.to_datetime([
            '2026-04-27', '2026-04-28', '2026-04-29',  # W18
            '2026-04-30', '2026-05-01',  # W18
            '2026-05-04', '2026-05-05',  # W19 — same week as analysis_date
        ])
        df = pd.DataFrame({
            'Date': dates,
            'Open':  [100.] * 7,
            'High':  [200., 201., 202., 203., 204., 800., 801.],
            'Low':   [ 90.] * 7,
            'Close': [150.] * 7,
        })
        analysis_date = date(2026, 5, 6)  # Wed of W19
        levels = compute_previous_levels(df, analysis_date=analysis_date)
        # PWH must NOT be 800/801 (those are in W19 with analysis_date).
        # Must be max of W18 highs = 204.
        assert levels['PWH'].price == 204.0

    def test_month_period_skips_in_progress_month(self):
        from datetime import date
        dates = pd.to_datetime([
            '2026-04-15', '2026-04-30',  # April
            '2026-05-01', '2026-05-05',  # May (in-progress)
        ])
        df = pd.DataFrame({
            'Date': dates,
            'Open':  [100.] * 4,
            'High':  [200., 250., 800., 900.],
            'Low':   [ 90.] * 4,
            'Close': [150., 160., 170., 180.],
        })
        analysis_date = date(2026, 5, 6)
        levels = compute_previous_levels(df, analysis_date=analysis_date)
        assert levels['PMH'].price == 250.0
        assert levels['PMC'].price == 160.0  # April's last close

    def test_year_period_skips_in_progress_year(self):
        from datetime import date
        dates = pd.to_datetime([
            '2025-12-30', '2025-12-31',  # 2025
            '2026-01-02', '2026-05-05',  # 2026 (in-progress)
        ])
        df = pd.DataFrame({
            'Date': dates,
            'Open':  [100.] * 4,
            'High':  [200., 250., 800., 900.],
            'Low':   [ 90.] * 4,
            'Close': [150., 160., 170., 180.],
        })
        analysis_date = date(2026, 5, 6)
        levels = compute_previous_levels(df, analysis_date=analysis_date)
        assert levels['PYH'].price == 250.0
        assert levels['PYL'].price == 90.0
        assert levels['PYC'].price == 160.0


# ─── compute_current_levels ───────────────────────────────────────────────


class TestComputeCurrentLevels:
    def test_returns_cdo(self):
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        levels = compute_current_levels(df, price)
        assert 'CDO' in levels
        assert levels['CDO'].is_current is True

    def test_cdo_price_is_today_open(self):
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        levels = compute_current_levels(df, price)
        assert levels['CDO'].price == float(df['Open'].iloc[-1])

    def test_cdo_flips_to_2u_on_high_price(self):
        df = _daily_df(10)
        # Price well above prev day high → should be 2U
        prev_high = float(df['High'].iloc[-2])
        price = prev_high + 5.0
        levels = compute_current_levels(df, price)
        # CDO should be 2U or Failed_2U depending on open
        assert levels['CDO'].strat_class in ('2U', 'Failed_2U')

    def test_cdo_inside_when_price_in_range(self):
        df = _daily_df(10)
        prev_high = float(df['High'].iloc[-2])
        prev_low = float(df['Low'].iloc[-2])
        mid = (prev_high + prev_low) / 2
        # Override today's OHLC to be well within prev range
        df.iloc[-1, df.columns.get_loc('High')] = prev_high - 0.5
        df.iloc[-1, df.columns.get_loc('Low')] = prev_low + 0.5
        df.iloc[-1, df.columns.get_loc('Open')] = mid
        levels = compute_current_levels(df, mid)
        assert levels['CDO'].strat_class == '1'

    def test_handles_null_today_ohlc_from_premarket_only_row(self):
        """Regression: when fetch-premarket-refresh writes today's
        market_data_daily row with only pre_high/pre_low/gap_pct (NULL
        OHLC because the regular session hasn't run yet), compute_
        current_levels must NOT crash on `max(NULL, current_price)`.
        Falls back to current_price for missing values.
        """
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        # Simulate the pre-market-only row: nuke today's OHLC
        df.iloc[-1, df.columns.get_loc('Open')] = None
        df.iloc[-1, df.columns.get_loc('High')] = None
        df.iloc[-1, df.columns.get_loc('Low')] = None
        # Should not raise — pre-fix this called max(None, float) and
        # blew up with TypeError
        levels = compute_current_levels(df, price)
        assert 'CDO' in levels
        # Sentinel: CDO falls back to current_price when open is NULL
        assert levels['CDO'].price == price


# ─── compute_current_levels — premarket label disambiguation ─────────────
#
# The 8:30 AM ET brief filters its df to `date < analysis_date` so today's
# NULL-OHLC row doesn't poison the level math. After that filter,
# `df.iloc[-1]` is the previous trading day. Pre-fix this was still labelled
# CDO (Current Day Open) which leaked the implication "today's open exists"
# — but today hasn't opened yet. Fix: emit PDO/PWO/PMO when analysis_date
# falls in a later period than the last row.


class TestComputeCurrentLevelsPremarketLabels:
    """Verify the CDO/PDO (etc.) label switch driven by analysis_date."""

    def test_legacy_callers_get_cdo_label_when_no_analysis_date(self):
        """No analysis_date passed → legacy CDO label preserved."""
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        levels = compute_current_levels(df, price)   # no analysis_date
        assert 'CDO' in levels
        assert 'PDO' not in levels
        assert levels['CDO'].is_current is True

    def test_analysis_date_same_day_as_last_row_emits_cdo(self):
        """When the last bar's date == analysis_date (EOD analytics
        with today's bar already in the data) the label IS honest."""
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        ad = pd.Timestamp(df['Date'].iloc[-1]).date()
        levels = compute_current_levels(df, price, analysis_date=ad)
        assert 'CDO' in levels
        assert 'PDO' not in levels

    def test_analysis_date_after_last_row_swaps_to_pdo(self):
        """8:30 AM premarket brief on Monday: filtered df ends at Friday.
        analysis_date = Monday → label MUST be PDO, not CDO.
        Price value is unchanged (the bug is purely labelling).
        """
        df = _daily_df(20)
        last_dt = pd.Timestamp(df['Date'].iloc[-1])
        ad = (last_dt + pd.tseries.offsets.BDay(1)).date()
        price = float(df['Close'].iloc[-1])

        levels = compute_current_levels(df, price, analysis_date=ad)
        assert 'PDO' in levels
        assert 'CDO' not in levels
        # Value is unchanged — pre-fix it would have been emitted as CDO
        # with the SAME price; the fix is purely cosmetic on the label.
        assert levels['PDO'].price == float(df['Open'].iloc[-1])
        # is_current=False once relabelled — PDO is not "current"
        assert levels['PDO'].is_current is False

    def test_analysis_date_in_new_week_swaps_cwo_to_pwo(self):
        """Monday brief: filtered df ends Friday. The week of iloc[-1]
        is BEFORE analysis_date's week. Label must be PWO."""
        df = _daily_df(30)
        # Find the first Monday strictly after the last bar's date.
        last_dt = pd.Timestamp(df['Date'].iloc[-1])
        ad_ts = last_dt + pd.Timedelta(days=1)
        while ad_ts.dayofweek != 0:
            ad_ts = ad_ts + pd.Timedelta(days=1)
        # Brief-style cutoff: drop any row on/after ad
        df_filtered = df[pd.to_datetime(df['Date']) < ad_ts].copy()
        price = float(df_filtered['Close'].iloc[-1])

        levels = compute_current_levels(
            df_filtered, price, analysis_date=ad_ts.date(),
        )
        assert 'PWO' in levels
        assert 'CWO' not in levels

    def test_pdo_strat_class_is_stable_across_premarket_price_gaps(self):
        """Codex P2 review on PR #445: when emitting PDO, strat_class
        must be computed from yesterday's CLOSE — not today's
        ``current_price`` — so a premarket gap can't repaint a
        completed session's classification.

        Scenario: yesterday closed inside its own range. Today gaps
        sharply above prev-day high. With the bug, today's
        current_price gets folded into yesterday's high → reclassified
        as 2U/Failed_2U. With the fix, PDO.strat_class is locked in
        based on yesterday's actual close.
        """
        df = _daily_df(20)
        # Override the last bar so we know its exact OHLC:
        #   yesterday's range = [195, 205], close = 200 (inside both
        #   prev-day H and L, so strat_class = '1' inside bar).
        last_idx = len(df) - 1
        df.iloc[last_idx, df.columns.get_loc('Open')]  = 197.0
        df.iloc[last_idx, df.columns.get_loc('High')]  = 205.0
        df.iloc[last_idx, df.columns.get_loc('Low')]   = 195.0
        df.iloc[last_idx, df.columns.get_loc('Close')] = 200.0
        # Set the prev-day above/below this range so '1' is the
        # natural strat class
        df.iloc[last_idx - 1, df.columns.get_loc('High')] = 210.0
        df.iloc[last_idx - 1, df.columns.get_loc('Low')]  = 190.0

        last_dt = pd.Timestamp(df['Date'].iloc[-1])
        ad = (last_dt + pd.tseries.offsets.BDay(1)).date()

        # Today gaps WAY above yesterday's high
        gap_price = 230.0
        levels = compute_current_levels(df, gap_price, analysis_date=ad)

        assert 'PDO' in levels
        # With the fix, PDO inherits yesterday's stable classification —
        # current_price=230 does NOT leak into it. Pre-fix this would
        # have been '2U' or 'Failed_2U' because today_high =
        # max(205, 230) = 230 broke prev_day_high=210.
        # We accept any class as long as it's NOT one that requires
        # today's gap-up to compute (2U/Failed_2U/3).
        assert levels['PDO'].strat_class not in ('2U', 'Failed_2U', '3'), \
            f"PDO repainted to {levels['PDO'].strat_class} from premarket gap — expected stable class"

    def test_analysis_date_in_new_month_swaps_cmo_to_pmo(self):
        """First-trading-day-of-month brief: filtered df ends in the
        prior month AND a prior month already exists in the history.
        Label must be PMO."""
        # 90 business days starting in late October — gives us Oct, Nov,
        # Dec rows AND ends in late January, then we set analysis_date to
        # the first business day of February.
        dates = pd.bdate_range('2024-10-01', '2025-01-31')
        n = len(dates)
        np.random.seed(7)
        close = 200 * np.exp(np.cumsum(np.random.normal(0.0003, 0.01, n)))
        df = pd.DataFrame({
            'Date': dates,
            'Open': close * (1 - 0.002),
            'High': close * (1 + 0.005),
            'Low':  close * (1 - 0.005),
            'Close': close,
            'Volume': 1_000_000,
        })
        ad = pd.Timestamp('2025-02-03').date()  # Mon, first business day Feb
        price = float(df['Close'].iloc[-1])

        levels = compute_current_levels(df, price, analysis_date=ad)
        assert 'PMO' in levels
        assert 'CMO' not in levels


# ─── compute_gap_levels ──────────────────────────────────────────────────


class TestComputeGapLevels:
    def test_detects_gap_up(self):
        df = pd.DataFrame({
            'Date': pd.bdate_range('2025-01-02', periods=3),
            'Open': [100, 105, 108],
            'High': [102, 107, 110],
            'Low': [99, 104, 107],     # day 2 low (104) > day 1 high (102) → gap
            'Close': [101, 106, 109],
        })
        gaps = compute_gap_levels(df, lookback=5)
        assert len(gaps) >= 2  # gap_high and gap_low
        gap_types = {g.level_type for g in gaps}
        assert 'gap_high' in gap_types
        assert 'gap_low' in gap_types

    def test_filled_gap_excluded(self):
        df = pd.DataFrame({
            'Date': pd.bdate_range('2025-01-02', periods=4),
            'Open': [100, 105, 100, 98],
            'High': [102, 107, 103, 101],
            'Low': [99, 104, 99, 97],    # day 2 low (104) > day 1 high (102) → gap
            'Close': [101, 106, 100, 99], # but day 3 low (99) fills the gap
        })
        gaps = compute_gap_levels(df, lookback=5)
        # Gap should be filtered out because day 3 filled it
        gap_up = [g for g in gaps if g.strat_class == 'gap_up']
        assert len(gap_up) == 0

    def test_empty_df(self):
        assert compute_gap_levels(pd.DataFrame(), lookback=5) == []


# ─── detect_level_clusters (spatial PMG) ──────────────────────────────────


class TestDetectLevelClusters:
    def test_finds_cluster(self):
        levels = [
            StratLevel('PDL', 262.14, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 262.30, 'week', 'low', '2D', False, ''),
            StratLevel('PMH', 270.00, 'month', 'high', '2U', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_atr=0.15, atr=2.62)
        assert len(zones) == 1
        assert 'PDL' in zones[0]['level_names']
        assert 'PWL' in zones[0]['level_names']

    def test_no_cluster_when_far_apart(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            StratLevel('PWH', 270.00, 'week', 'high', '2U', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_atr=0.15, atr=2.62)
        assert len(zones) == 0

    def test_strength_scoring(self):
        levels = [
            StratLevel('PDL', 262.14, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 262.30, 'week', 'low', '2D', False, ''),
            StratLevel('GAP_L', 262.10, 'day', 'gap_low', 'gap_up', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_atr=0.15, atr=2.62)
        assert len(zones) == 1
        # count=3, unique TFs=2 (day, week) → 3 + 0.5 = 3.5
        assert zones[0]['strength'] == 3.5

    def test_empty(self):
        assert detect_level_clusters([], tolerance_atr=0.15, atr=2.62) == []


# ─── detect_pmg_temporal ──────────────────────────────────────────────────


class TestDetectPMGTemporal:
    def test_detects_higher_highs(self):
        df = pd.DataFrame({
            'High': [100, 101, 102, 103, 104],
            'Low': [95, 96, 97, 98, 99],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        hh = [r for r in results if r['type'] == 'higher_highs']
        assert len(hh) >= 1
        assert hh[0]['count'] >= 3

    def test_detects_lower_lows(self):
        df = pd.DataFrame({
            'High': [104, 103, 102, 101, 100],
            'Low': [99, 98, 97, 96, 95],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        ll = [r for r in results if r['type'] == 'lower_lows']
        assert len(ll) >= 1

    def test_no_streak(self):
        df = pd.DataFrame({
            'High': [100, 101, 99, 102, 98],
            'Low': [95, 96, 94, 97, 93],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        assert len(results) == 0


# ─── compute_risk_reward ─────────────────────────────────────────────────


class TestRiskReward:
    def test_basic(self):
        assert compute_risk_reward(100, 99, 102) == 2.0

    def test_zero_risk(self):
        assert compute_risk_reward(100, 100, 105) == 0.0

    def test_put_direction(self):
        assert compute_risk_reward(100, 101, 97) == 3.0


# ─── identify_triggers ───────────────────────────────────────────────────


class TestSessionPicks:
    """The side picks build_session_levels makes (they replaced
    identify_triggers): one candidate set, one side rule, one window."""

    def _session(self, levels, ref, atr=5.0):
        from tests.lib.session_levels_helpers import session
        return session(levels, prior_close=ref, atr=atr)

    def _levels(self):
        return {'PDH': 265.00, 'PDL': 260.00, 'PWH': 268.00, 'PWL': 257.00}

    def test_calls_trigger(self):
        sl = self._session(self._levels(), 263.00)
        assert sl.long.trigger['name'] == 'PDH'
        assert sl.long.trigger['price'] == 265.00
        assert sl.to_level_map().calls_trigger['trigger_level'] == 265.00

    def test_puts_trigger(self):
        sl = self._session(self._levels(), 263.00)
        assert sl.short.trigger['name'] == 'PDL'
        assert sl.to_level_map().puts_trigger['trigger_name'] == 'PDL'

    def test_targets_are_distinct_prices_beyond_the_trigger(self):
        """Two lines on one cent are one rung (the structural name in
        priority order wins), a line at the trigger's own cent is never a
        target, and opens are never candidates."""
        sl = self._session({
            'PDH': 265.00, 'PWH': 265.00,        # == trigger: one rung, alias PWH
            'PWC': 266.504, 'PMH': 268.00, 'PQH': 270.00, 'PDL': 260.00,
        }, 263.00)
        assert sl.long.trigger['name'] == 'PDH'
        assert sl.long.trigger['aliases'] == ['PWH']
        assert [round(t['price'], 2) for t in sl.long.targets] == [266.50, 268.00, 270.00]

    def test_room_is_measured_to_the_first_distinct_target(self):
        sl = self._session({'PDH': 100.004, 'PWC': 100.0049, 'PMH': 101.00, 'PDL': 98.00},
                           99.5, atr=1.0)
        calls = sl.to_level_map().calls_trigger
        assert [t['price'] for t in calls['targets']] == [101.00]
        assert calls['room_to_first_target'] == pytest.approx(
            (101.0 - 100.004) / 100.004 * 100, abs=1e-3)

    def test_no_premarket_a_level_on_the_references_cent_is_on_neither_list(self):
        """Spec revision 2: with no premarket snapshot, a level on the
        reference's own cent is on neither list; the trigger is the next
        real level out."""
        sl = self._session({'PDH': 101.00, 'PDC': 100.0041, 'PWL': 98.00}, 100.004, atr=1.0)
        assert sl.long.trigger['name'] == 'PDH'
        assert sl.short.trigger['name'] == 'PWL'

    def test_with_premarket_a_level_on_the_references_cent_is_on_both_lists(self):
        """With a snapshot and no premarket beyond it, a level on the
        reference's own cent is both the long and the short trigger."""
        from tests.lib.session_levels_helpers import session
        sl = session({'PDH': 101.00, 'PDC': 100.0041, 'PWL': 98.00}, prior_close=100.004,
                     atr=1.0, premarket={'pre_high': 100.0, 'pre_low': 100.0,
                                         'pre_vwap': 100.004})
        assert sl.long.trigger['name'] == 'PDC'
        assert sl.short.trigger['name'] == 'PDC'
        assert sl.long.targets[0]['name'] == 'PDH'
        assert sl.short.targets[0]['name'] == 'PWL'

    def test_targets_one_cent_apart_are_distinct_despite_float_error(self):
        """240.01 - 240.00 < 0.01 in binary; integer cents keep them apart."""
        sl = self._session({'PDH': 240.00, 'PWH': 240.01, 'PMH': 241.00, 'PDL': 235.00}, 238.00)
        assert sl.long.trigger['price'] == 240.00
        assert [t['price'] for t in sl.long.targets] == [240.01, 241.00]


# ─── build_level_map (deprecated shim over build_session_levels) ─────────


class TestBuildLevelMap:
    def test_returns_level_map(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price, '2U', '212_bull_reversal', atr=3.0)
        assert isinstance(lm, LevelMap)
        assert lm.ticker == 'IWM'
        assert len(lm.levels) > 0
        assert lm.current_price == price

    def test_has_triggers(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('SPY', df, price, atr=3.0)
        assert lm.calls_trigger is not None or lm.puts_trigger is not None

    def test_no_atr_gives_no_trigger(self):
        df = _daily_df(60)
        lm = build_level_map('SPY', df, float(df['Close'].iloc[-1]))
        assert lm.calls_trigger is None and lm.puts_trigger is None
        assert lm.reason_long == lm.reason_short == 'atr_unavailable'


# ─── format_levels_for_brief ──────────────────────────────────────────────


class TestDisplayLevelName:
    """The gap-level naming convention is GAP_H_YYYY-MM-DD internally;
    display renders this as 'M/D Gap High' / 'M/D Gap Low'. Internal
    StratLevel.name stays canonical so signal_monitor's level-break
    detection still keys on it; only Discord/brief output uses the
    friendlier form."""

    def _display(self, name):
        from lib.strat_levels import _display_level_name
        return _display_level_name(name)

    def test_gap_high_with_iso_date_renders_short_form(self):
        assert self._display('GAP_H_2026-05-05') == '5/5 Gap High'

    def test_gap_low_with_iso_date_renders_short_form(self):
        assert self._display('GAP_L_2026-05-05') == '5/5 Gap Low'

    def test_gap_drops_leading_zeros_in_month_and_day(self):
        assert self._display('GAP_H_2026-04-28') == '4/28 Gap High'
        assert self._display('GAP_L_2026-01-03') == '1/3 Gap Low'

    def test_gap_keeps_double_digit_months_and_days(self):
        assert self._display('GAP_H_2026-12-31') == '12/31 Gap High'
        assert self._display('GAP_L_2026-11-15') == '11/15 Gap Low'

    def test_non_gap_names_pass_through_unchanged(self):
        for name in ('PDH', 'PDL', 'PWH', 'PMH', 'PQH', 'PYH',
                     'PDC', 'PWC', 'PMC', 'CDO', 'CWO', 'CMO', 'PMK_H'):
            assert self._display(name) == name

    def test_malformed_gap_names_pass_through(self):
        """If the gap regex doesn't match (legacy data, future format
        change), pass through unchanged rather than crash."""
        assert self._display('GAP_H_2026') == 'GAP_H_2026'  # no date
        assert self._display('GAP_X_2026-05-05') == 'GAP_X_2026-05-05'  # wrong side
        assert self._display('') == ''
        assert self._display('SOMETHING_ELSE') == 'SOMETHING_ELSE'


class TestFormatLevelsForBrief:
    def _lm(self, atr=3.0):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        return build_level_map('IWM', df, price, '2U', '212_bull_reversal', atr=atr)

    def test_contains_calls_puts(self):
        text = format_levels_for_brief(self._lm(), 'bullish', '212_bull_reversal', '2U')
        assert 'CALLS above' in text or 'PUTS below' in text

    def test_bias_denied_for_puts_when_bullish(self):
        text = format_levels_for_brief(self._lm(), 'bullish')
        if 'PUTS below' in text:
            assert 'only if bias denied' in text

    def test_bearish_bias_denied_for_calls(self):
        text = format_levels_for_brief(self._lm(), 'bearish')
        if 'CALLS above' in text:
            assert 'only if bias denied' in text

    def test_room_to_trigger_is_the_triggers_own_distance(self):
        from tests.lib.session_levels_helpers import session
        lm = session({'PDH': 102.0, 'PWH': 104.0, 'PDL': 99.0}, prior_close=100.0,
                     atr=2.0).to_level_map()
        text = format_levels_for_brief(lm, 'bullish')
        assert 'CALLS above 102.00 (PDH)' in text
        assert 'T1: 104.00 (PWH)' in text
        assert 'Room to trigger: 2.00%' in text

    # ── orb_only: one copy per reason (FEAT-STRAT-001 Design 6) ────────

    def test_orb_only_sides_render_the_reason_copy(self):
        """A side with no trigger prints its ORB_ONLY_COPY line and no
        CALLS above / PUTS below line."""
        from lib.strat_levels import orb_only_text
        lm = self._lm(atr=None)
        text = format_levels_for_brief(lm, 'bullish', regime='orb_only')
        assert '  CALLS: ' + orb_only_text('atr_unavailable', 'long', lm.window_long) in text
        assert '  PUTS: ' + orb_only_text('atr_unavailable', 'short', lm.window_short) in text
        assert 'CALLS above' not in text
        assert 'PUTS below' not in text

    def test_all_broken_by_premarket_copy(self):
        from lib.strat_levels import orb_only_text
        from tests.lib.session_levels_helpers import session
        sl = session({'PDH': 220.0, 'PWH': 225.0, 'PMH': 228.0, 'PDL': 215.0},
                     prior_close=218.0, atr=2.0,
                     premarket={'pre_high': 240.0, 'pre_low': 216.0, 'pre_vwap': 219.0})
        assert sl.long.reason == 'all_broken_by_premarket'
        text = format_levels_for_brief(sl.to_level_map(), 'bullish')
        assert '  CALLS: ' + orb_only_text('all_broken_by_premarket', 'long') in text
        assert 'cleared every structural' not in text

    def test_orb_only_banner_no_warning_emoji(self):
        """No warning sign in the banner; the embed builder adds its own."""
        text = format_levels_for_brief(self._lm(atr=None), 'bullish', regime='orb_only')
        assert '\u26a0' not in text

    def test_regime_argument_does_not_change_the_side_blocks(self):
        """The sides come from the SessionLevels projection, so a caller's
        regime argument cannot relabel a side that has a trigger."""
        lm = self._lm()
        assert (format_levels_for_brief(lm, 'bullish', regime='normal')
                == format_levels_for_brief(lm, 'bullish'))

    def test_default_regime_is_normal(self):
        text = format_levels_for_brief(self._lm(), 'bullish')
        assert 'extended gap' not in text.lower()


# ─── levels_to_named_dict (PR α adapter) ──────────────────────────────────


class TestLevelsToNamedDict:
    def test_extracts_named_levels(self):
        from lib.strat_levels import levels_to_named_dict
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        d = levels_to_named_dict(lm)
        # PDH/PDL should always be present after 60 days of data
        assert 'PDH' in d
        assert 'PDL' in d
        # All values should be floats
        assert all(isinstance(v, float) for v in d.values())

    def test_empty_level_map(self):
        from lib.strat_levels import LevelMap, levels_to_named_dict
        empty = LevelMap(
            ticker='X', as_of='2026-01-01', current_price=100.0,
            levels=[], pmg_zones=[],
        )
        assert levels_to_named_dict(empty) == {}


# ─── select_nearest_levels (next-N each way) ─────────────────────────────


class TestNextLevelsLadder:
    """The brief's NEXT LEVELS ladder: the first two rungs of each side
    list from build_session_levels (it replaced select_nearest_levels).

    The user's worked example: price 250, with PWH 251.50 and PDH 252 above
    (call levels) and PQL 248 and PMH 245 below (put levels).
    """

    @staticmethod
    def _ladder(levels, ref=250.0, atr=5.0):
        from tests.lib.session_levels_helpers import session
        lm = session(levels, prior_close=ref, atr=atr).to_level_map()
        return {'calls': lm.call_levels, 'puts': lm.put_levels}

    def _levels(self):
        return {'PWH': 251.50, 'PDH': 252.00, 'PQL': 248.00, 'PMH': 245.00}

    def test_next_two_call_levels_nearest_first(self):
        out = self._ladder(self._levels())
        assert [lv['name'] for lv in out['calls']] == ['PWH', 'PDH']
        assert out['calls'][0]['price'] == 251.50
        assert out['calls'][0]['period'] == 'week'
        assert out['calls'][1]['price'] == 252.00

    def test_next_two_put_levels_nearest_first(self):
        out = self._ladder(self._levels())
        assert [lv['name'] for lv in out['puts']] == ['PQL', 'PMH']
        assert out['puts'][0]['price'] == 248.00
        assert out['puts'][1]['price'] == 245.00

    def test_emitted_price_uses_the_shared_cents_rule(self):
        """292.705 renders as 292.71 (half-up, matching Postgres numeric), not
        the 292.70 Python's round() gives; and two lines on the same cent
        collapse to one rung."""
        out = self._ladder({'PWH': 292.705, 'PDH': 292.714, 'PMH': 294.0}, ref=290.0)
        assert [lv['price'] for lv in out['calls']] == [292.71, 294.0]

    def test_with_premarket_a_level_on_the_references_cent_is_on_both_sides(self):
        """FEAT-STRAT-001: with a snapshot and no premarket beyond it, a level
        on the reference's own cent is on both lists, once, as one rung."""
        from tests.lib.session_levels_helpers import session
        lm = session({'PDH': 100.0041, 'PDL': 100.0039, 'PWH': 101.0, 'PWL': 99.0},
                     prior_close=100.004, atr=5.0,
                     premarket={'pre_high': 100.0, 'pre_low': 100.0,
                                'pre_vwap': 100.004}).to_level_map()
        out = {'calls': lm.call_levels, 'puts': lm.put_levels}
        assert [lv['price'] for lv in out['calls']] == [100.0, 101.0]
        assert [lv['price'] for lv in out['puts']] == [100.0, 99.0]
        assert out['calls'][0]['name'] == out['puts'][0]['name'] == 'PDH'

    def test_no_premarket_a_level_on_the_references_cent_is_on_neither_side(self):
        """Spec revision 2: with no snapshot the reference's own cent is on
        neither ladder."""
        out = self._ladder({'PDH': 100.0041, 'PDL': 100.0039, 'PWH': 101.0, 'PWL': 99.0},
                           ref=100.004)
        assert [lv['price'] for lv in out['calls']] == [101.0]
        assert [lv['price'] for lv in out['puts']] == [99.0]

    def test_direction_is_positional_not_by_high_low(self):
        out = self._ladder(self._levels())
        assert 'PMH' in [lv['name'] for lv in out['puts']]  # a month HIGH below price

    def test_distance_pct_sign(self):
        out = self._ladder(self._levels())
        assert out['calls'][0]['distance_pct'] > 0
        assert out['puts'][0]['distance_pct'] < 0

    def test_dedup_coincident_prices(self):
        out = self._ladder({'PDH': 252.00, 'PWH': 252.00, 'PMH': 255.00})
        assert [lv['price'] for lv in out['calls']] == [252.00, 255.00]

    def test_short_side_not_padded(self):
        out = self._ladder({'PDH': 252.00})
        assert len(out['calls']) == 1
        assert out['puts'] == []

    def test_build_level_map_populates_call_put_levels(self):
        df = _daily_df(120)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('TEST', df, price, atr=float(df['Close'].iloc[-1] * 0.01))
        assert isinstance(lm.call_levels, list)
        assert isinstance(lm.put_levels, list)
        from lib.strat_levels import price_cents
        for lv in lm.call_levels:
            assert price_cents(lv['price']) >= price_cents(price)
        for lv in lm.put_levels:
            assert price_cents(lv['price']) <= price_cents(price)


# ─── daily_data_freshness (shared with the premarket brief) ──────────────


class TestDailyDataFreshness:
    """One rule for the brief's playbook row and the movement-statement
    ladder matched against it (Codex P2 on #1030, round 6)."""

    def test_same_or_next_day_is_fresh(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(2026, 9, 10), date(2026, 9, 11)) == (False, 1, 'fresh')

    def test_monday_reading_friday_is_fresh(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(2026, 9, 11), date(2026, 9, 14)) == (False, 3, 'fresh')

    def test_monday_reading_thursday_is_stale(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        stale, gap, status = daily_data_freshness(date(2026, 9, 10), date(2026, 9, 14))
        assert (stale, gap, status) == (True, 4, 'STALE_DAILY_DATA')

    def test_tuesday_reading_friday_is_stale_by_design(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(2026, 9, 11), date(2026, 9, 15))[0] is True

    def test_sunday_weekly_reading_friday_is_fresh(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(2026, 9, 11), date(2026, 9, 13)) == (False, 2, 'fresh')

    def test_none_is_unknown(self):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(None, date(2026, 9, 14)) == (False, -1, 'unknown')

    def test_brief_entry_point_delegates_here(self):
        from datetime import date
        from gcp.premarket_brief import _resolve_data_freshness
        from lib.strat_levels import daily_data_freshness
        for last, ad in ((date(2026, 9, 10), date(2026, 9, 14)), (date(2026, 9, 11), date(2026, 9, 14)), (None, date(2026, 9, 14))):
            assert _resolve_data_freshness(last, ad) == daily_data_freshness(last, ad)

    # FEAT-DATA-001 (2026-11-11 spec): the rule counts NYSE sessions, so a
    # session that follows only weekend days and holidays reads its previous
    # session as fresh. On origin/main every one of these was STALE_DAILY_DATA
    # and the brief skipped the ticker.
    @pytest.mark.parametrize('last, session, gap', [
        ((2026, 5, 22), (2026, 5, 26), 4),   # Memorial Day Monday
        ((2026, 6, 18), (2026, 6, 22), 4),   # Juneteenth Friday
        ((2026, 7, 2), (2026, 7, 6), 4),     # Independence Day observed Friday
        ((2026, 9, 4), (2026, 9, 8), 4),     # Labor Day Monday
        ((2026, 11, 25), (2026, 11, 27), 2), # Thanksgiving Thursday
        ((2026, 4, 2), (2026, 4, 5), 3),     # Sunday weekly brief across Good Friday
    ])
    def test_previous_session_across_holidays_is_fresh(self, last, session, gap):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(*last), date(*session)) == (False, gap, 'fresh')

    @pytest.mark.parametrize('last, session, gap', [
        ((2026, 5, 21), (2026, 5, 26), 5),   # Friday 05-22 missing
        ((2026, 11, 24), (2026, 11, 27), 3), # Wednesday 11-25 missing
        ((2026, 9, 10), (2026, 9, 14), 4),   # Friday 09-11 missing
        ((2026, 9, 11), (2026, 9, 15), 4),   # Monday 09-14 missing
    ])
    def test_a_missing_session_is_still_stale(self, last, session, gap):
        from datetime import date
        from lib.strat_levels import daily_data_freshness
        assert daily_data_freshness(date(*last), date(*session)) == (True, gap, 'STALE_DAILY_DATA')

    def test_short_gap_never_reads_the_calendar(self, monkeypatch):
        from datetime import date
        from lib import eastern_time
        from lib.strat_levels import daily_data_freshness

        def boom(*_a, **_k):
            raise AssertionError('calendar consulted for a gap of 0 or 1 day')
        monkeypatch.setattr(eastern_time, 'previous_session', boom)
        assert daily_data_freshness(date(2026, 11, 25), date(2026, 11, 25)) == (False, 0, 'fresh')
        assert daily_data_freshness(date(2026, 11, 25), date(2026, 11, 26)) == (False, 1, 'fresh')

    def test_calendar_failure_raises(self, monkeypatch):
        from datetime import date
        import pandas_market_calendars as mcal
        from lib import eastern_time
        from lib.strat_levels import daily_data_freshness

        def no_calendar(name, *a, **k):
            raise RuntimeError('calendar down')
        eastern_time._reset_session_cache()
        monkeypatch.setattr(mcal, 'get_calendar', no_calendar)
        try:
            with pytest.raises(RuntimeError, match='calendar down'):
                daily_data_freshness(date(2026, 11, 25), date(2026, 11, 27))
        finally:
            monkeypatch.undo()
            eastern_time._reset_session_cache()


# ─── Exits in thirds (docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md)


def _prices(rungs):
    return [round(r['price'], 2) for r in rungs]


class TestTargetSpacing:
    """Design 1: a target is at least target_min_spacing_atr x ATR past the
    trigger or the target before it; the gating targets keep origin/main's
    meaning."""

    def test_design_8_fixture(self):
        sl = d8_session()
        assert (sl.long.trigger['name'], sl.long.trigger['price']) == ('PMK_H', 252.10)
        assert _prices(sl.long.targets) == [275.00, 280.00, 285.00]
        assert _prices(sl.long.skipped) == [253.00]
        assert (sl.short.trigger['name'], sl.short.trigger['price']) == ('PMK_L', 248.20)
        assert _prices(sl.short.targets) == [225.00, 220.00, 215.00]
        assert _prices(sl.short.skipped) == [247.50, 247.00]
        assert sl.long.stop['price'] == 248.20 and sl.short.stop['price'] == 252.10
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]
        assert sl.long.target_status == sl.short.target_status == 'ok'

    def test_a_wider_atr_spaces_the_targets_further(self):
        sl = d8_session(atr=24.0, window=1.6)
        assert _prices(sl.long.targets) == [275.00, 285.00]
        assert _prices(sl.long.skipped) == [253.00, 280.00]
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]

    def test_the_ticker_row_sets_the_spacing(self):
        """A ticker_level_params row of 0.05 publishes 253.00 with no code change."""
        sl = d8_session(spacing=0.05)
        assert _prices(sl.long.targets) == [253.00, 275.00, 280.00]
        assert sl.long.skipped == []
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]

    @pytest.mark.parametrize('first, kept', [(255.61, True), (255.60, False)])
    def test_a_distance_equal_to_the_spacing_in_cents_is_kept(self, first, kept):
        """0.25 x 14.02 = 3.505, which price_cents rounds half-up to 351
        cents: 255.61 (351 cents past 252.10) is kept, 255.60 is skipped."""
        from lib.strat_levels import price_cents
        assert price_cents(0.25 * 14.02) == 351
        levels = {**D8_LEVELS, 'PDH': first}
        sl = d8_session(levels, atr=14.02)
        assert (first in _prices(sl.long.targets)) is kept
        assert (first in _prices(sl.long.skipped)) is not kept

    def test_a_spacing_not_ok_publishes_no_target(self):
        sl = d8_session(statuses={'target_min_spacing_atr': 'insufficient_history'})
        for side in (sl.long, sl.short):
            assert side.trigger is not None and side.stop is not None
            assert side.targets == [] and side.skipped == []
            assert side.target_status == 'insufficient_history'
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]

    def test_exit_legs_not_ok_publishes_no_target(self):
        sl = d8_session(statuses={'exit_legs': 'input_unavailable'})
        assert sl.long.targets == [] and sl.long.target_status == 'input_unavailable'

    @pytest.mark.parametrize('status', ['input_unavailable', 'params_unavailable'])
    def test_an_entry_cutoff_not_ok_publishes_no_target(self, status):
        """No plan without the entry rule it is scored on (Codex P1 on
        #1832): the side keeps its trigger, stop and gate targets and
        records the cutoff's status, as for spacing and legs."""
        sl = d8_session(statuses={'entry_cutoff_et': status})
        for side in (sl.long, sl.short):
            assert side.trigger is not None and side.stop is not None
            assert side.targets == [] and side.skipped == []
            assert side.target_status == status
            assert side.plan['entry_cutoff_et'] is None
            assert side.plan['entry_cutoff_status'] == status
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]
        from lib.strat_levels import SessionLevels
        again = SessionLevels.from_basis(sl.to_basis())
        assert again.long.targets == [] and again.long.target_status == status

    def test_the_legs_bound_the_targets(self):
        sl = d8_session(spacing=0.05, exit_legs=2)
        assert _prices(sl.long.targets) == [253.00, 275.00]

    def test_the_brief_columns_hold_gate_and_plan_targets(self):
        from gcp.premarket_brief import structured_playbook_columns
        for kw in ({}, {'atr': 24.0, 'window': 1.6}, {'spacing': 0.05}):
            sl = d8_session(**kw)
            cols = structured_playbook_columns(sl.to_level_map())
            assert [cols[f'calls_t{k}_price'] for k in (1, 2, 3)] == [253.00, 275.00, 280.00]
            plan = _prices(sl.long.targets) + [None] * (3 - len(sl.long.targets))
            assert [cols[f'calls_plan_t{k}_price'] for k in (1, 2, 3)] == plan
            assert cols['calls_trigger_price'] == 252.10 and cols['calls_stop_price'] == 248.20


D8_CALLS = """  CALLS above 252.10 (PMK_H), new entries 09:30 to 10:00 ET
    No entry if the open is at or above 252.10.
    Stop: 248.20 (PMK_L)
    T1: 275.00 (PMH), sell 1/3
    T2: 280.00 (PQH), sell 1/3
    T3: 285.00 (PYH), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 253.00 (PDH)
    Room to trigger: 0.84%"""

D8_PUTS = """  PUTS below 248.20 (PMK_L), new entries 09:30 to 10:00 ET
    No entry if the open is at or below 248.20.
    Stop: 252.10 (PMK_H)
    T1: 225.00 (PML), sell 1/3
    T2: 220.00 (PQL), sell 1/3
    T3: 215.00 (PYL), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 247.50 (PDL), 247.00 (PDC)
    Room to trigger: 0.72%"""


class TestExitPlanCopy:
    """Designs 2 to 5 and 8: the brief's exit plan copy."""

    def _text(self, **kw):
        return format_levels_for_brief(d8_session(**kw).to_level_map(), 'neutral')

    def test_design_8_text(self):
        text = self._text()
        assert D8_CALLS in text
        assert D8_PUTS in text

    def test_fewer_targets_than_legs_hold_the_rest(self):
        text = self._text(atr=24.0, window=1.6)
        assert "    T1: 275.00 (PMH), sell 1/3\n" in text
        assert ("    T2: 285.00 (PYH), sell 1/3, hold the last 1/3 to the close or the stop\n"
                in text)

    def test_no_target_past_the_spacing(self):
        text = self._text(spacing=5.0)
        assert ("    No target at least 5 x ATR(14) = 70.00 past the trigger: "
                "hold to the close or the stop.") in text
        assert "    T1:" not in text

    def test_targets_unavailable(self):
        text = self._text(statuses={'target_min_spacing_atr': 'insufficient_history'})
        assert "    Targets unavailable (insufficient_history): no exit plan for this side." in text
        assert "No target at least" not in text and "    T1:" not in text
        assert "Skipped" not in text

    def test_entry_cutoff_unavailable(self):
        """An entry cutoff that is not ok prints no entry window and no
        exit plan, and says so (Codex P1 on #1832)."""
        text = self._text(statuses={'entry_cutoff_et': 'input_unavailable'})
        assert ("  CALLS above 252.10 (PMK_H), entry window unavailable (input_unavailable)\n"
                in text)
        assert ("  PUTS below 248.20 (PMK_L), entry window unavailable (input_unavailable)\n"
                in text)
        assert "new entries" not in text
        assert text.count(
            "    Targets unavailable (input_unavailable): no exit plan for this side.") == 2
        assert "No target at least" not in text and "    T1:" not in text
        assert "Skipped" not in text and "sell 1/" not in text

    @pytest.mark.parametrize('flag, label', [
        (0.2, "    T2: 247.00 (PDC, gap fill: gap 0.21 x ATR), sell 1/3\n"),
        (0.5, "    T2: 247.00 (PDC), sell 1/3\n"),
    ])
    def test_prior_close_gap_fill_label(self, flag, label):
        """The gap is |250.00 - 247.00| / 14.00 = 0.21 ATR: labelled a gap
        fill when the ticker's flag is 0.2, plain when it is 0.5."""
        text = self._text(spacing=0.0, gap_fill_flag_atr=flag)
        assert label in text

    @pytest.mark.parametrize('status', ['input_unavailable', 'params_unavailable'])
    def test_an_unavailable_gap_fill_flag_is_said_not_dropped(self, status):
        """Codex P1 on #1832: a gap-fill flag that is not ok labels the
        prior-close target as unclassified instead of printing a plain
        (PDC), so it reads differently from a gap below the threshold; the
        rest of the plan is unchanged and the label survives from_basis."""
        sl = d8_session(spacing=0.0, statuses={'gap_fill_flag_atr': status})
        text = format_levels_for_brief(sl.to_level_map(), 'neutral')
        assert (f"    T2: 247.00 (PDC, gap fill flag unavailable ({status})), sell 1/3\n"
                in text)
        assert "    T2: 247.00 (PDC), sell 1/3\n" not in text
        assert sl.short.target_status == 'ok'
        assert all('gap_fill_status' not in t for t in sl.long.targets)
        from lib.strat_levels import SessionLevels
        again = SessionLevels.from_basis(sl.to_basis())
        assert format_levels_for_brief(again.to_level_map(), 'neutral') == text

    def test_the_cutoff_and_legs_come_from_the_policy(self):
        text = self._text(exit_legs=2, spacing=0.05)
        assert "    T1: 253.00 (PDH), sell 1/2\n" in text
        assert "    T2: 275.00 (PMH), sell the last 1/2, or hold to the close or the stop\n" in text

    def test_orb_only_copy_is_unchanged(self):
        from lib.strat_levels import orb_only_text
        from tests.lib.session_levels_helpers import session
        sl = session({'PDH': 220.0, 'PWH': 225.0, 'PMH': 228.0, 'PDL': 215.0},
                     prior_close=218.0, atr=2.0,
                     premarket={'pre_high': 240.0, 'pre_low': 216.0, 'pre_vwap': 219.0})
        text = format_levels_for_brief(sl.to_level_map(), 'bullish')
        assert '  CALLS: ' + orb_only_text('all_broken_by_premarket', 'long') + '\n' in text


# ─── ATR levels spec (2026-11-11), display only ────────────────────────

D8_RUNG_PARAMS = ('atr_rung_anchors', 'atr_rung_step_atr', 'atr_rung_max_atr',
                  'atr_rung_stretch_atr')


def _rung_view(rungs):
    return [(round(r['price'], 2), r['label']) for r in rungs]


class TestAtrRungs:
    """ATR levels spec, done_when 'ATR rungs', on the exits spec's Design 8
    fixture with the seeded anchors [PDH, PDL, PMK_H, PMK_L], step 0.5, max
    2.0 and stretch 1.5."""

    def test_32_rungs_before_thinning(self):
        from lib.strat_levels import _atr_rung_ladder
        sl = d8_session()
        rungs, distinct, anchors = _atr_rung_ladder(sl.levels, sl.params, sl.atr,
                                                     sl.params.atr_rung_anchors())
        assert len(rungs) == len(distinct) == 32
        want = set()
        for name, price in (('PDH', 253.00), ('PDL', 247.50), ('PMK_H', 252.10), ('PMK_L', 248.20)):
            for k, mult in (('0.5', 0.5), ('1', 1.0), ('1.5', 1.5), ('2', 2.0)):
                want.add((round(price + mult * 14.0, 2), f'{name}+{k}'))
                want.add((round(price - mult * 14.0, 2), f'{name}-{k}'))
        assert set(_rung_view(rungs)) == want
        assert [a['name'] for a in anchors] == ['PDH', 'PDL', 'PMK_H', 'PMK_L']
        assert {a['status'] for a in anchors} == {'ok'}

    def test_design_8_keeps_four_rungs(self):
        sl = d8_session()
        assert sl.atr_rung_status == 'ok'
        assert _rung_view(sl.atr_rungs) == [(234.20, 'PMK_L-1'), (241.20, 'PMK_L-0.5'),
                                            (259.10, 'PMK_H+0.5'), (266.10, 'PMK_H+1')]
        assert [r['name'] for r in sl.atr_rungs] == ['PMK_L-1ATR', 'PMK_L-0.5ATR',
                                                     'PMK_H+0.5ATR', 'PMK_H+1ATR']
        assert len(sl.atr_rungs_dropped) == 28
        assert {r['reason'] for r in sl.atr_rungs_dropped} == {'neighbor', 'structural'}
        pdh_m2 = next(r for r in sl.atr_rungs_dropped if r['price'] == 225.00)
        assert (pdh_m2['name'], pdh_m2['reason'], pdh_m2['alias_of']) == ('PDH-2ATR', 'structural', 'PML')

    def test_a_rung_far_from_its_neighbor_but_near_a_structural_level_is_dropped(self):
        """273.10 (PMK_H+1.5) is 7.00 from 266.10 but 1.90 from 275.00 (PMH)."""
        sl = d8_session()
        r = next(r for r in sl.atr_rungs_dropped if r['label'] == 'PMK_H+1.5')
        assert r['price'] == 273.10 and r['reason'] == 'structural' and r['near'] == 'PMH'

    @pytest.mark.parametrize('pdh, kept', [(255.60, True), (255.61, False)])
    def test_spacing_equal_to_a_structural_level_in_cents_is_kept(self, pdh, kept):
        """259.10 against a structural PDH: 3.50 away (0.25 x 14.00 = 350
        cents) is kept, 3.49 away is dropped as structural."""
        sl = d8_session({**D8_LEVELS, 'PDH': pdh}, anchors=['PDL', 'PMK_H', 'PMK_L'])
        assert (259.10 in [r['price'] for r in sl.atr_rungs]) is kept
        if not kept:
            r = next(r for r in sl.atr_rungs_dropped if r['price'] == 259.10)
            assert r['reason'] == 'structural' and r['near'] == 'PDH'

    @pytest.mark.parametrize('pdh, kept', [(255.60, True), (255.59, False)])
    def test_spacing_equal_to_the_open_side_neighbor_in_cents_is_kept(self, pdh, kept):
        """Anchors [PMK_H, PDH], one step of 0.5: 259.10 (PMK_H+0.5) is kept
        and PDH+0.5 is the next rung out, clear of every structural level.
        PDH 255.60 puts it 350 cents (0.25 x 14.00) past 259.10: kept; PDH
        255.59 puts it 349 cents past: dropped as neighbor."""
        sl = d8_session({'PDH': pdh, 'PDL': 247.50, 'PMH': 300.00}, anchors=['PMK_H', 'PDH'],
                        atr_rung_max_atr=0.5)
        assert 259.10 in [r['price'] for r in sl.atr_rungs]
        rung = [r for r in sl.atr_rungs + sl.atr_rungs_dropped if r['label'] == 'PDH+0.5']
        assert len(rung) == 1 and rung[0]['price'] == round(pdh + 7.0, 2)
        assert (rung[0] in sl.atr_rungs) is kept
        if not kept:
            assert rung[0]['reason'] == 'neighbor' and rung[0]['near_price'] == 259.10

    @pytest.mark.parametrize('stretch, marked', [(1.5, True), (21.01 / 14.0, False)])
    def test_stretch_from_the_stretch_mark_in_cents(self, stretch, marked):
        """PMK_H+1.5 is 21.00 from its anchor: stretch when the mark is
        1.5 x 14.00 = 2100 cents, not when it is one cent more."""
        from lib.strat_levels import _atr_rung_ladder
        sl = d8_session(atr_rung_stretch_atr=stretch)
        rungs, _d, _a = _atr_rung_ladder(sl.levels, sl.params, sl.atr, sl.params.atr_rung_anchors())
        by_label = {r['label']: r for r in rungs}
        assert by_label['PMK_H+1.5']['stretch'] is marked
        assert by_label['PMK_H+2']['stretch'] is True
        assert by_label['PMK_H+1']['stretch'] is False

    def test_two_rungs_on_one_cent_take_the_first_anchor_name(self):
        """PDL 246.00 = PDH 253.00 - 7.00: PDL-1 (232.00) and PDH-1.5
        (232.00) share a cent, and so do PDL+0.5 and PDH (253.00 = 246+7,
        a structural cent). The anchor listed first (PDH) keeps the name."""
        from lib.strat_levels import _atr_rung_ladder
        sl = d8_session({**D8_LEVELS, 'PDL': 246.00})
        _all, distinct, _a = _atr_rung_ladder(sl.levels, sl.params, sl.atr,
                                              sl.params.atr_rung_anchors())
        at = {r['cents']: r for r in distinct}
        assert at[23200]['name'] == 'PDH-1.5ATR' and at[23200]['aliases'] == ['PDL-1ATR']
        flipped = d8_session({**D8_LEVELS, 'PDL': 246.00}, anchors=['PDL', 'PDH', 'PMK_H', 'PMK_L'])
        _all, distinct, _a = _atr_rung_ladder(flipped.levels, flipped.params, flipped.atr,
                                              flipped.params.atr_rung_anchors())
        at = {r['cents']: r for r in distinct}
        assert at[23200]['name'] == 'PDL-1ATR' and at[23200]['aliases'] == ['PDH-1.5ATR']

    def test_no_premarket_snapshot_builds_from_pdh_and_pdl(self):
        from lib.strat_levels import SessionLevels
        from tests.lib.session_levels_helpers import basis, d8_params
        sl = SessionLevels.from_basis(basis(D8_LEVELS, prior_close=247.00, atr=14.0,
                                            premarket=None, params=d8_params()))
        assert sl.atr_rung_status == 'ok'
        assert {r['anchor'] for r in sl.atr_rungs + sl.atr_rungs_dropped} == {'PDH', 'PDL'}
        assert len(sl.atr_rungs) + len(sl.atr_rungs_dropped) == 16
        assert [(a['name'], a['status']) for a in sl.atr_rung_anchors] == [
            ('PDH', 'ok'), ('PDL', 'ok'), ('PMK_H', 'anchor_unavailable'),
            ('PMK_L', 'anchor_unavailable')]
        basis_out = sl.to_basis()
        assert [a['status'] for a in basis_out['atr_rung_anchors']][2:] == ['anchor_unavailable'] * 2

    @pytest.mark.parametrize('key', D8_RUNG_PARAMS + ('target_min_spacing_atr',))
    @pytest.mark.parametrize('status', ['insufficient_history', 'params_unavailable'])
    def test_a_parameter_not_ok_gives_no_rungs(self, key, status):
        sl = d8_session(statuses={key: status})
        assert sl.atr_rungs == [] and sl.atr_rungs_dropped == []
        assert sl.atr_rung_status == status


class TestAtrRungsDisplayOnly:
    """ATR levels spec, done_when 'Display only' and 'Unchanged': the plan
    decisions, the NEXT LEVELS ladders and the brief's structured columns
    are the base's for every case (tests/lib/atr_levels_display_only.py,
    golden written on the base)."""

    def test_every_case_matches_the_base(self):
        import json
        from pathlib import Path
        from tests.lib.atr_levels_display_only import projections
        golden = json.loads((Path(__file__).resolve().parents[1] / 'fixtures'
                             / 'atr_levels_display_only_base.json').read_text())
        head = projections()
        assert sorted(head) == sorted(golden)
        for name in golden:
            assert head[name] == golden[name], name

    def test_the_brief_writes_the_base_columns(self, monkeypatch):
        """gcp.premarket_brief on the committed 2026-11-06 fixture (SPY, QQQ,
        IWM, the production brief path offline): every premarket_analysis
        column the brief writes is the base's, including calls/puts t1..t3
        and plan_t1..plan_t3, except two. The playbook is the base's text
        with exactly one line added, the last NEXT LEVELS line. level_basis
        is the base's with the ATR rung keys and the four rung parameters
        added and nothing else changed."""
        import json
        from pathlib import Path
        from tests.lib.atr_levels_display_only import BRIEF_TICKERS, brief_entries
        golden = json.loads((Path(__file__).resolve().parents[1] / 'fixtures'
                             / 'atr_levels_brief_base.json').read_text())
        head = brief_entries(monkeypatch)
        assert sorted(head) == sorted(golden) == sorted(BRIEF_TICKERS)
        rung_keys = {'atr_rungs', 'atr_rungs_dropped', 'atr_rung_status', 'atr_rung_anchors',
                     'atr_rung_params'}
        for t in BRIEF_TICKERS:
            h, b = dict(head[t]), dict(golden[t])
            hp, bp = h.pop('playbook').split('\n'), b.pop('playbook').split('\n')
            added = [i for i, ln in enumerate(hp) if ln.startswith('    ATR levels')]
            assert len(added) == 1 and hp[:added[0]] + hp[added[0] + 1:] == bp, t
            assert hp[added[0] - 1].startswith('    Puts (down): '), t
            hb, bb = h.pop('level_basis'), b.pop('level_basis')
            assert set(hb) - set(bb) == rung_keys and not set(bb) - set(hb), t
            assert hb['atr_rung_status'] == 'ok' and hb['atr_rungs'], t
            hparams = dict(hb['params'])
            for k in D8_RUNG_PARAMS:
                hparams.pop(k)
            assert hparams == bb['params'], t
            assert {k: v for k, v in hb.items() if k not in rung_keys | {'params'}} == {
                k: v for k, v in bb.items() if k != 'params'}, t
            assert h == b, t
            for side in ('calls', 'puts'):
                for k in (1, 2, 3):
                    assert f'{side}_t{k}_price' in h and f'{side}_plan_t{k}_price' in h

    def test_design_8_plan(self):
        sl = d8_session()
        assert (sl.long.trigger['price'], sl.long.stop['price']) == (252.10, 248.20)
        assert _prices(sl.long.gate_targets) == [253.00, 275.00, 280.00]
        assert _prices(sl.long.targets) == [275.00, 280.00, 285.00]
        assert _prices(sl.long.skipped) == [253.00]
        assert (sl.short.trigger['price'], sl.short.stop['price']) == (248.20, 252.10)
        assert _prices(sl.short.gate_targets) == [247.50, 247.00, 225.00]
        assert _prices(sl.short.targets) == [225.00, 220.00, 215.00]
        assert _prices(sl.short.skipped) == [247.50, 247.00]

    def test_no_rung_reaches_the_candidates_or_the_side_pick(self, monkeypatch):
        """A session whose only level past the trigger would be a rung
        (259.10, PMK_H+0.5) gets the base's targets: none past the trigger.
        _candidate_rungs and _pick_side are spied: no ATR rung name or
        price reaches either."""
        import lib.strat_levels as m
        seen = []
        real_cands, real_pick = m._candidate_rungs, m._pick_side

        def cands(levels):
            seen.extend(lv.name for lv in levels)
            return real_cands(levels)

        def pick(side, candidates, *a, **kw):
            seen.extend(c['name'] for c in candidates)
            return real_pick(side, candidates, *a, **kw)

        monkeypatch.setattr(m, '_candidate_rungs', cands)
        monkeypatch.setattr(m, '_pick_side', pick)
        sl = d8_session({'PDL': 247.50, 'PML': 225.00})
        assert sl.atr_rung_status == 'ok'
        assert 259.10 in [r['price'] for r in sl.atr_rungs]
        assert sl.long.trigger['price'] == 252.10
        assert sl.long.gate_targets == [] and sl.long.targets == [] and sl.long.skipped == []
        assert seen and not any(n.endswith('ATR') for n in seen)
        assert not any(lv.name.endswith('ATR') for lv in sl.levels)

    def test_the_rule_version_and_persisted_levels_are_unchanged(self):
        from lib.strat_levels import LEVEL_RULE_VERSION
        sl = d8_session()
        assert LEVEL_RULE_VERSION == sl.rule_version == 'feat-strat-001.v3'
        lm = sl.to_level_map()
        assert sorted(lv.name for lv in lm.levels) == sorted(list(D8_LEVELS) + ['PMK_H', 'PMK_L'])
        assert [(r['price'], r['name']) for r in lm.call_levels] == [(252.10, 'PMK_H'), (253.00, 'PDH')]
        assert [(r['price'], r['name']) for r in lm.put_levels] == [(248.20, 'PMK_L'), (247.50, 'PDL')]


D8_NEXT_LEVELS = """  NEXT LEVELS:
    Calls (up):  252.10 PMK_H (intraday) +0.84%, 253.00 PDH (day) +1.20%
    Puts (down): 248.20 PMK_L (intraday) -0.72%, 247.50 PDL (day) -1.00%"""
D8_ATR_LINE = ("    ATR levels, ATR(14) 14.00: up 259.10 (PMK_H+0.5), 266.10 (PMK_H+1); "
               "down 241.20 (PMK_L-0.5), 234.20 (PMK_L-1)")


class TestAtrLevelsCopy:
    """ATR levels spec, done_when 'Brief copy' (Design 5)."""

    def test_design_8_golden_text(self):
        text = format_levels_for_brief(d8_session().to_level_map(), 'neutral')
        assert text == (D8_CALLS + "\n\n" + D8_PUTS + "\n\n" + D8_NEXT_LEVELS + "\n" + D8_ATR_LINE)

    def test_every_other_line_is_the_base_text(self):
        """Removing the one ATR line leaves the exits spec's Design 8 text
        and the base's NEXT LEVELS lines, byte for byte."""
        text = format_levels_for_brief(d8_session().to_level_map(), 'neutral')
        lines = text.split('\n')
        assert lines[-1] == D8_ATR_LINE and lines.count(D8_ATR_LINE) == 1
        assert '\n'.join(lines[:-1]) == D8_CALLS + "\n\n" + D8_PUTS + "\n\n" + D8_NEXT_LEVELS

    def test_stretch_and_alias_labels(self):
        """Windows 3.0 and stretch 0.5: every kept rung is stretch; with PDL
        on 246.00 the PDH-1.5 rung (232.00) also carries PDL-1."""
        from lib.strat_levels import _format_atr_levels
        sl = d8_session({**D8_LEVELS, 'PDL': 246.00}, window=3.0, atr_rung_stretch_atr=0.5)
        line = _format_atr_levels(sl.to_level_map().atr_levels)
        assert line.startswith("    ATR levels, ATR(14) 14.00: up ")
        assert "(PMK_H+0.5 stretch)" in line
        alias = [r for r in sl.atr_rungs + sl.atr_rungs_dropped if r['aliases']]
        assert alias
        kept_alias = [r for r in sl.atr_rungs if r['aliases']]
        for r in kept_alias:
            assert f", also {r['aliases'][0].removesuffix('ATR')}" in line

    def test_a_kept_rung_with_an_alias_prints_it(self):
        from lib.strat_levels import _format_atr_levels
        lm = {'status': 'ok', 'atr': 14.0, 'atr_basis': 'atr_14',
              'up': [{'label': 'PDH+1', 'price': 267.0, 'stretch': True, 'aliases': ['PDL+1.5ATR']}],
              'down': []}
        assert _format_atr_levels(lm) == (
            "    ATR levels, ATR(14) 14.00: up 267.00 (PDH+1 stretch, also PDL+1.5); down none")

    def test_rungs_outside_the_window_are_not_printed(self):
        """Windows 0.7 x 14 = 9.80 from 250.00: 259.10 and 241.20 are
        inside, 266.10 and 234.20 are not."""
        sl = d8_session(window=0.7)
        line = format_levels_for_brief(sl.to_level_map(), 'neutral').split('\n')[-1]
        assert line == ("    ATR levels, ATR(14) 14.00: up 259.10 (PMK_H+0.5); "
                        "down 241.20 (PMK_L-0.5)")

    @pytest.mark.parametrize('key', D8_RUNG_PARAMS + ('target_min_spacing_atr',))
    def test_unavailable_line(self, key):
        text = format_levels_for_brief(
            d8_session(statuses={key: 'params_unavailable'}).to_level_map(), 'neutral')
        assert text.split('\n')[-1] == "    ATR levels unavailable (params_unavailable)."
        assert "ATR levels, ATR(" not in text

    def test_orb_only_and_no_trigger_sides_are_unchanged(self):
        from lib.strat_levels import orb_only_text
        from tests.lib.session_levels_helpers import session
        sl = session({'PDH': 220.0, 'PWH': 225.0, 'PMH': 228.0, 'PDL': 215.0},
                     prior_close=218.0, atr=2.0,
                     premarket={'pre_high': 240.0, 'pre_low': 216.0, 'pre_vwap': 219.0})
        text = format_levels_for_brief(sl.to_level_map(), 'bullish')
        assert '  CALLS: ' + orb_only_text('all_broken_by_premarket', 'long') + '\n' in text
        lines = text.split('\n')
        calls = [ln for ln in lines if ln.startswith('  CALLS')]
        assert calls == ['  CALLS: ' + orb_only_text('all_broken_by_premarket', 'long')]
        assert lines[-1].startswith('    ATR levels')

    def test_a_basis_without_rungs_prints_no_line(self):
        """A stored level_basis written before ATR rungs rebuilds none and
        renders the base's text."""
        import json
        from lib.strat_levels import SessionLevels
        stored = json.loads(json.dumps(d8_session().to_basis()))
        for k in ('atr_rungs', 'atr_rungs_dropped', 'atr_rung_status', 'atr_rung_anchors',
                  'atr_rung_params'):
            stored.pop(k)
        for k in D8_RUNG_PARAMS:
            stored['params'].pop(k)
        old = SessionLevels.from_basis(stored)
        assert old.atr_rungs == [] and old.atr_rung_status is None
        text = format_levels_for_brief(old.to_level_map(), 'neutral')
        assert text == D8_CALLS + "\n\n" + D8_PUTS + "\n\n" + D8_NEXT_LEVELS
