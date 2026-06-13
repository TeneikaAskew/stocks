"""Tests for lib/strat_levels.py — Strat levels engine."""

import pandas as pd
import numpy as np
import pytest

from lib.strat_levels import (
    classify_level_strat,
    compute_previous_levels,
    compute_current_levels,
    compute_gap_levels,
    detect_level_clusters,
    detect_pmg_temporal,
    compute_room_to_run,
    compute_risk_reward,
    identify_triggers,
    build_level_map,
    format_levels_for_brief,
    select_nearest_levels,
    StratLevel,
    LevelMap,
    MIN_ROOM_PCT,
)


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


class TestComputePreviousLevels:
    def test_returns_daily_levels(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert 'PDH' in levels
        assert 'PDL' in levels
        assert levels['PDH'].timeframe == 'day'
        assert levels['PDL'].level_type == 'low'

    def test_returns_weekly_levels(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert 'PWH' in levels
        assert 'PWL' in levels
        assert levels['PWH'].timeframe == 'week'

    def test_returns_monthly_levels(self):
        df = _daily_df(60)
        levels = compute_previous_levels(df)
        assert 'PMH' in levels
        assert 'PML' in levels

    def test_returns_quarter_levels(self):
        df = _daily_df(200)
        levels = compute_previous_levels(df)
        assert 'PQH' in levels
        assert 'PQL' in levels
        assert levels['PQH'].timeframe == 'quarter'

    def test_pdh_price_matches_prev_day_high(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        expected = float(df['High'].iloc[-2])
        assert levels['PDH'].price == expected

    def test_levels_classified(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert levels['PDH'].strat_class in ('1', '2U', '2D', '3', 'Failed_2U', 'Failed_2D')

    def test_empty_df(self):
        assert compute_previous_levels(pd.DataFrame()) == {}

    def test_returns_close_levels(self):
        """Close levels (PDC/PWC/PMC/PQC/PYC) ship alongside H/L so
        traders charting against PDC have a source of truth.

        Uses 520 biz days (~2 years) so the legacy path's "need ≥2
        groupings to compute previous period" requirement is satisfied
        even for the year timeframe (PYC).
        """
        df = _daily_df(520)
        levels = compute_previous_levels(df)
        for k in ('PDC', 'PWC', 'PMC', 'PQC', 'PYC'):
            assert k in levels, f"missing {k}"
            assert levels[k].level_type == 'close'

    def test_pdc_price_matches_prev_day_close(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        # Legacy path: prev day = iloc[-2]
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
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 1
        assert 'PDL' in zones[0]['level_names']
        assert 'PWL' in zones[0]['level_names']

    def test_no_cluster_when_far_apart(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            StratLevel('PWH', 270.00, 'week', 'high', '2U', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 0

    def test_strength_scoring(self):
        levels = [
            StratLevel('PDL', 262.14, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 262.30, 'week', 'low', '2D', False, ''),
            StratLevel('GAP_L', 262.10, 'day', 'gap_low', 'gap_up', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 1
        # count=3, unique TFs=2 (day, week) → 3 + 0.5 = 3.5
        assert zones[0]['strength'] == 3.5

    def test_empty(self):
        assert detect_level_clusters([], tolerance_pct=0.15) == []


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


# ─── compute_room_to_run ─────────────────────────────────────────────────


class TestRoomToRun:
    def test_call_direction(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            StratLevel('PWH', 268.00, 'week', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'CALL')
        assert result['next_level'].name == 'PDH'
        assert result['distance_pct'] > 0
        assert result['has_room'] is True

    def test_put_direction(self):
        levels = [
            StratLevel('PDL', 260.00, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 257.00, 'week', 'low', '2D', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'PUT')
        assert result['next_level'].name == 'PDL'
        assert result['has_room'] is True

    def test_insufficient_room(self):
        levels = [
            StratLevel('PDH', 263.05, 'day', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'CALL')
        # 0.05/263 = 0.019% < MIN_ROOM_PCT
        assert result['has_room'] is False

    def test_no_levels_in_direction(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(266.00, levels, 'CALL')
        assert result['next_level'] is None


# ─── compute_risk_reward ─────────────────────────────────────────────────


class TestRiskReward:
    def test_basic(self):
        assert compute_risk_reward(100, 99, 102) == 2.0

    def test_zero_risk(self):
        assert compute_risk_reward(100, 100, 105) == 0.0

    def test_put_direction(self):
        assert compute_risk_reward(100, 101, 97) == 3.0


# ─── identify_triggers ───────────────────────────────────────────────────


class TestIdentifyTriggers:
    def _levels(self):
        return {
            'PDH': StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            'PDL': StratLevel('PDL', 260.00, 'day', 'low', '2D', False, ''),
            'PWH': StratLevel('PWH', 268.00, 'week', 'high', '2U', False, ''),
            'PWL': StratLevel('PWL', 257.00, 'week', 'low', '2D', False, ''),
        }

    def test_calls_trigger(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['calls'] is not None
        assert triggers['calls']['trigger_name'] == 'PDH'
        assert triggers['calls']['trigger_level'] == 265.00

    def test_puts_trigger(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['puts'] is not None
        assert triggers['puts']['trigger_name'] == 'PDL'

    def test_reasoning_includes_combo(self):
        triggers = identify_triggers(
            263.00, self._levels(),
            daily_strat_class='2U', combo='212_bull_reversal',
        )
        assert '212_bull_reversal' in triggers['calls']['reasoning']
        assert 'Daily 2U' in triggers['calls']['reasoning']

    def test_reasoning_empty_when_no_context(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['calls']['reasoning'] == ''


# ─── build_level_map ──────────────────────────────────────────────────────


class TestBuildLevelMap:
    def test_returns_level_map(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price, '2U', '212_bull_reversal')
        assert isinstance(lm, LevelMap)
        assert lm.ticker == 'IWM'
        assert len(lm.levels) > 0
        assert lm.current_price == price

    def test_has_triggers(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('SPY', df, price)
        # Should have at least calls or puts
        assert lm.calls_trigger is not None or lm.puts_trigger is not None


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
    def test_contains_calls_puts(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price, '2U', '212_bull_reversal')
        text = format_levels_for_brief(lm, 'bullish', '212_bull_reversal', '2U')
        assert 'CALLS above' in text or 'PUTS below' in text

    def test_bias_denied_for_puts_when_bullish(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        if 'PUTS below' in text:
            assert 'only if bias denied' in text

    def test_bearish_bias_denied_for_calls(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bearish')
        if 'CALLS above' in text:
            assert 'only if bias denied' in text

    # ── Regime-aware playbook output (PR α) ───────────────────────────

    def test_orb_only_regime_suppresses_calls_and_puts(self):
        """orb_only: pre-market cleared every level; the playbook
        replaces CALLS/PUTS with an ORB-wait banner."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish', regime='orb_only')
        assert 'ORB-only' in text
        assert 'wait' in text.lower() or '15-min' in text
        # Suppressed: no CALLS/PUTS lines
        assert 'CALLS above' not in text
        assert 'PUTS below' not in text

    def test_orb_only_banner_names_cleared_levels(self):
        """orb_only: banner must name the LAST cleared structural level
        with its price so the trader sees what's now behind them.
        Regression for the original 'every structural level' wording
        which was technically true but useless."""
        levels = [
            StratLevel(name='PDH', price=220.0, timeframe='day',
                       level_type='high', strat_class='2U'),
            StratLevel(name='PWH', price=225.0, timeframe='week',
                       level_type='high', strat_class='2U'),
            StratLevel(name='PMH', price=228.0, timeframe='month',
                       level_type='high', strat_class='2U'),
            StratLevel(name='PDL', price=215.0, timeframe='day',
                       level_type='low', strat_class='2U'),
        ]
        lm = LevelMap(
            ticker='IWM', as_of='2026-04-28',
            current_price=230.0, levels=levels,
        )
        text = format_levels_for_brief(lm, 'bullish', regime='orb_only')
        # Last cleared bullish level (closest to spot) named with price
        assert 'Last bullish level passed' in text
        assert 'PMH' in text and '228.00' in text
        assert 'PWH' in text and '225.00' in text
        assert 'PDH' in text and '220.00' in text
        # Spot price referenced for context
        assert '230.00' in text

    def test_orb_only_banner_short_bias_names_cleared_lows(self):
        """Mirror: bear bias names the LAST cleared LOW with its price."""
        levels = [
            StratLevel(name='PDL', price=200.0, timeframe='day',
                       level_type='low', strat_class='2D'),
            StratLevel(name='PWL', price=195.0, timeframe='week',
                       level_type='low', strat_class='2D'),
            StratLevel(name='PQL', price=190.0, timeframe='quarter',
                       level_type='low', strat_class='2D'),
        ]
        lm = LevelMap(
            ticker='IWM', as_of='2026-04-28',
            current_price=185.0, levels=levels,
        )
        text = format_levels_for_brief(lm, 'bearish', regime='orb_only')
        assert 'Last bearish level passed' in text
        # Closest-to-spot low (PQL $190) is the LAST level price passed
        assert 'PQL' in text and '190.00' in text
        assert 'PWL' in text and '195.00' in text

    def test_orb_only_banner_no_warning_emoji(self):
        """No ⚠ in the banner — user wants plain text. Brain emoji is
        added by the embed builder, not by the level formatter."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish', regime='orb_only')
        assert '⚠' not in text

    def test_extended_regime_prepends_warning_keeps_triggers(self):
        """extended: per-side warning header + standard CALLS/PUTS still
        rendered. The legacy global 'Extended gap' header was replaced
        with per-side banners ('CALLS: extended gap...' /
        'PUTS: extended gap...') so a bullish ticker whose CALL side is
        normal but PUT side is gap-extended only sees a warning on the
        relevant side."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish', regime='extended')
        # Per-side banner uses lowercase 'extended gap'.
        assert 'extended gap' in text
        assert 'ORB' in text
        # Still has trigger lines (extended ≠ skip the trade)
        assert 'CALLS above' in text or 'PUTS below' in text

    def test_normal_regime_matches_legacy_output(self):
        """normal regime: identical to the legacy no-regime call."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text_normal = format_levels_for_brief(lm, 'bullish', regime='normal')
        text_legacy = format_levels_for_brief(lm, 'bullish')
        assert text_normal == text_legacy

    def test_default_regime_is_normal(self):
        """No regime kwarg → backwards-compat with pre-α callers."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        # No regime banner of any kind when default is 'normal'.
        assert 'extended gap' not in text.lower()
        assert 'ORB-only' not in text


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


class TestSelectNearestLevels:
    """The brief's 'next two call levels / next two put levels' display.

    Mirrors the user's worked example: price 250, with PWH 251.50 and PDH
    252 above (call levels) and PQL 248 and PMH 245 below (put levels).
    """

    def _levels(self):
        return {
            'PWH': StratLevel('PWH', 251.50, timeframe='week', level_type='high'),
            'PDH': StratLevel('PDH', 252.00, timeframe='day', level_type='high'),
            'PQL': StratLevel('PQL', 248.00, timeframe='quarter', level_type='low'),
            'PMH': StratLevel('PMH', 245.00, timeframe='month', level_type='high'),
        }

    def test_next_two_call_levels_nearest_first(self):
        out = select_nearest_levels(250.0, self._levels(), atr=5.0, n=2)
        assert [lv['name'] for lv in out['calls']] == ['PWH', 'PDH']
        assert out['calls'][0]['price'] == 251.50
        assert out['calls'][0]['period'] == 'week'
        assert out['calls'][1]['price'] == 252.00

    def test_next_two_put_levels_nearest_first(self):
        out = select_nearest_levels(250.0, self._levels(), atr=5.0, n=2)
        # nearest below first: PQL (248) then PMH (245)
        assert [lv['name'] for lv in out['puts']] == ['PQL', 'PMH']
        assert out['puts'][0]['price'] == 248.00
        assert out['puts'][1]['price'] == 245.00

    def test_direction_is_positional_not_by_high_low(self):
        # a prior-month HIGH below price is a PUT (bearish) level
        out = select_nearest_levels(250.0, self._levels(), atr=5.0, n=2)
        put_names = [lv['name'] for lv in out['puts']]
        assert 'PMH' in put_names  # month HIGH, but it sits below price

    def test_distance_pct_sign(self):
        out = select_nearest_levels(250.0, self._levels(), atr=5.0, n=2)
        assert out['calls'][0]['distance_pct'] > 0   # above
        assert out['puts'][0]['distance_pct'] < 0    # below

    def test_dedup_coincident_prices(self):
        lvls = {
            'PDH': StratLevel('PDH', 252.00, timeframe='day', level_type='high'),
            'PWH': StratLevel('PWH', 252.00, timeframe='week', level_type='high'),
            'PMH': StratLevel('PMH', 255.00, timeframe='month', level_type='high'),
        }
        out = select_nearest_levels(250.0, lvls, atr=5.0, n=2)
        prices = [lv['price'] for lv in out['calls']]
        assert prices == [252.00, 255.00]  # 252 not counted twice

    def test_short_side_not_padded(self):
        # only one level above -> calls has length 1, never fabricated
        lvls = {'PDH': StratLevel('PDH', 252.00, timeframe='day', level_type='high')}
        out = select_nearest_levels(250.0, lvls, atr=5.0, n=2)
        assert len(out['calls']) == 1
        assert out['puts'] == []

    def test_build_level_map_populates_call_put_levels(self):
        df = _daily_df(120)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('TEST', df, price, atr=float(df['Close'].iloc[-1] * 0.01))
        assert isinstance(lm.call_levels, list)
        assert isinstance(lm.put_levels, list)
        for lv in lm.call_levels:
            assert lv['price'] > price
        for lv in lm.put_levels:
            assert lv['price'] < price
