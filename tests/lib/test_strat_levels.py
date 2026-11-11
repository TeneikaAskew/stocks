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
