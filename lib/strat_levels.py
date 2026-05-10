"""
Strat Levels Engine — multi-timeframe level classification, PMG, room-to-run.

In The Strat, levels ARE the trade:
  - Entry = break of a key level (PDH, PDL, PWH, PWL, etc.)
  - Stop  = opposite side of the triggering candle or inside bar
  - Target = next level in the direction of the trade

Each level gets a Strat classification relative to its prior period
(see docs/STRAT_METHODOLOGY.md §10-14).

Dependencies:
  - lib/strat.py (classify_candle for the structural step)
  - lib/indicators.py (calculate_historical_levels for Prev_* columns)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Dict, List, Optional, Tuple

from lib.strat import StratClassifier


# ─── Data structures ──────────────────────────────────────────────────────


@dataclass
class StratLevel:
    """A single Strat level with classification and context.

    All fields except `name` and `price` have sensible defaults so callers
    that only have rough info (e.g. realtime signal_monitor crossing
    detection) don't need to fabricate values they don't have. The
    methodology-driven build_level_map() always populates everything.
    """
    name: str              # e.g. "PDH", "PWL", "CDO"
    price: float           # the level price
    timeframe: str = ''    # "day", "week", "month", "quarter", "year"
    level_type: str = 'pivot'  # "high", "low", "open", "gap_high", "gap_low", "pivot"
    strat_class: str = ''  # "1", "2U", "2D", "Failed_2U", "Failed_2D", "3"
    is_current: bool = False  # True for current period levels (repaint)
    period_label: str = ''  # e.g. "2026-04-25", "2026-W17"


@dataclass
class LevelMap:
    """Complete level map for a ticker at a point in time.

    `pmg_zones` defaults to an empty list so callers in the realtime
    signal-monitor path can build a minimal LevelMap from just a few
    critical levels (PDH/PDL) without computing the full PMG cluster
    detection — used by check_level_breaks() to evaluate live ticks
    against pre-known support/resistance.
    """
    ticker: str
    as_of: str
    current_price: float
    levels: List[StratLevel]
    pmg_zones: list = field(default_factory=list)
    calls_trigger: Optional[dict] = None
    puts_trigger: Optional[dict] = None
    room_to_run_up: Optional[float] = None
    room_to_run_down: Optional[float] = None


# ─── Level classification ─────────────────────────────────────────────────


def classify_level_strat(
    current_high: float,
    current_low: float,
    current_close: float,
    current_open: float,
    prev_high: float,
    prev_low: float,
) -> str:
    """Classify current period's Strat type relative to previous period.

    Uses the same structural classification as classify_candle (1/2U/2D/3)
    then adds Failed_2 disambiguation via close vs open (§2 of methodology).
    """
    # Structural classification
    base = StratClassifier.classify_candle(
        current_high, current_low, prev_high, prev_low,
    )

    # Add Failed_2 disambiguation for directional bars
    if base == '2U':
        return 'Failed_2U' if current_close < current_open else '2U'
    elif base == '2D':
        return 'Failed_2D' if current_close > current_open else '2D'

    return base  # '1' or '3'


# ─── Previous period levels (fixed, no repainting) ───────────────────────


def compute_previous_levels(
    daily_df: pd.DataFrame,
    analysis_date: Optional[date_type] = None,
) -> Dict[str, StratLevel]:
    """Compute previous-period H/L/C levels from daily OHLCV data.

    Reads the raw OHLCV to compute period aggregates, then classifies
    each period relative to the one before it. Emits three levels per
    timeframe — high, low, AND close — so charts that reference PDC/PWC
    have the same source-of-truth as PDH/PDL.

    Args:
        daily_df: DataFrame with Open/High/Low/Close columns,
            DatetimeIndex or a 'date'/'Date'/'Time' column. Sorted
            ascending. Needs ~1 year for yearly levels.
        analysis_date: When given, treat this date as "today". For
            each timeframe (day, week, month, quarter, year) the
            function finds the period containing analysis_date and
            returns levels for the period immediately BEFORE that one.

            This fixes the off-by-one bug observed on 2026-05-06 QQQ:
            the brief filtered today's in-progress bar out via
            ``idx < analysis_date``, so iloc[-2] of each grouping
            picked the day-before-yesterday instead of yesterday — PDH
            wrote $676.73 (5/4 high) when the chart's PDH was $682.77
            (5/5 high), which fed the trade_planner a stale baseline
            and produced a $695.52 synthetic blue-sky trigger that
            price never touched.

            With analysis_date passed, the function uses period-filter
            semantics — ``period < pd.Period(analysis_date, freq=…)``
            for week/month/quarter and ``< analysis_date`` for day —
            independent of where df's last bar happens to sit.

            When None (legacy callers), falls back to iloc[-2]
            behavior, which assumes df's last row is today's
            in-progress bar.
    """
    if daily_df.empty or len(daily_df) < 2:
        return {}

    df = daily_df.copy()

    # Normalize date column
    if 'date' in df.columns:
        df['_date'] = pd.to_datetime(df['date'])
    elif 'Date' in df.columns:
        df['_date'] = pd.to_datetime(df['Date'])
    elif 'Time' in df.columns:
        df['_date'] = pd.to_datetime(df['Time'])
    elif isinstance(df.index, pd.DatetimeIndex):
        df['_date'] = df.index
    else:
        return {}

    # Normalize OHLC column names
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl == 'open':
            col_map[c] = '_open'
        elif cl == 'high':
            col_map[c] = '_high'
        elif cl == 'low':
            col_map[c] = '_low'
        elif cl in ('close', 'last'):
            col_map[c] = '_close'
    df = df.rename(columns=col_map)

    for needed in ['_open', '_high', '_low', '_close']:
        if needed not in df.columns:
            return {}

    df = df.sort_values('_date')

    levels: Dict[str, StratLevel] = {}

    # Period definitions: (group_key, tf_label, prefix, period_freq).
    # period_freq drives the analysis_date filter:
    #   None → groupby key is python date; compare directly
    #   'W' / 'M' / 'Q' → groupby key is pd.Period; compare to
    #     pd.Period(analysis_date, freq=…)
    #   'Y' → groupby key is int year; compare to analysis_date.year
    periods = [
        ('_day', 'day', 'PD', None),
        ('_week', 'week', 'PW', 'W'),
        ('_month', 'month', 'PM', 'M'),
        ('_quarter', 'quarter', 'PQ', 'Q'),
        ('_year', 'year', 'PY', 'Y'),
    ]

    df['_day'] = df['_date'].dt.date
    df['_week'] = df['_date'].dt.to_period('W')
    df['_month'] = df['_date'].dt.to_period('M')
    df['_quarter'] = df['_date'].dt.to_period('Q')
    df['_year'] = df['_date'].dt.year

    for group_col, tf_label, prefix, period_freq in periods:
        grp = df.groupby(group_col).agg(
            H=('_high', 'max'),
            L=('_low', 'min'),
            O=('_open', 'first'),
            C=('_close', 'last'),
        )
        if grp.empty:
            continue

        # Pick the previous-period row.
        if analysis_date is not None:
            if period_freq is None:
                cutoff = analysis_date
            elif period_freq == 'Y':
                cutoff = analysis_date.year
            else:
                cutoff = pd.Period(analysis_date, freq=period_freq)
            prev_grp = grp[grp.index < cutoff]
            if prev_grp.empty:
                continue
            prev_period = prev_grp.iloc[-1]
            prev_label = str(prev_grp.index[-1])
            p_n2 = prev_grp.iloc[-2] if len(prev_grp) >= 2 else None
        else:
            # Legacy: assume df's last row is today's in-progress bar
            # → previous period is iloc[-2].
            if len(grp) < 2:
                continue
            prev_period = grp.iloc[-2]
            prev_label = str(grp.index[-2])
            p_n2 = grp.iloc[-3] if len(grp) >= 3 else None

        h_name = f'{prefix}H'
        l_name = f'{prefix}L'
        c_name = f'{prefix}C'

        levels[h_name] = StratLevel(
            name=h_name, price=float(prev_period['H']),
            timeframe=tf_label, level_type='high',
            strat_class='', is_current=False,
            period_label=prev_label,
        )
        levels[l_name] = StratLevel(
            name=l_name, price=float(prev_period['L']),
            timeframe=tf_label, level_type='low',
            strat_class='', is_current=False,
            period_label=prev_label,
        )
        levels[c_name] = StratLevel(
            name=c_name, price=float(prev_period['C']),
            timeframe=tf_label, level_type='close',
            strat_class='', is_current=False,
            period_label=prev_label,
        )

        # Classify prev period vs the period before it.
        if p_n2 is not None:
            strat = classify_level_strat(
                prev_period['H'], prev_period['L'],
                prev_period['C'], prev_period['O'],
                p_n2['H'], p_n2['L'],
            )
            levels[h_name].strat_class = strat
            levels[l_name].strat_class = strat
            levels[c_name].strat_class = strat

    return levels


# ─── Current period levels (live, repainting) ────────────────────────────


def compute_current_levels(
    daily_df: pd.DataFrame,
    current_price: float,
) -> Dict[str, StratLevel]:
    """Compute current period open levels with live Strat classification.

    These levels REPAINT as price evolves.
    """
    if daily_df.empty or len(daily_df) < 2:
        return {}

    df = daily_df.copy()

    # Normalize
    if 'date' in df.columns:
        df['_date'] = pd.to_datetime(df['date'])
    elif 'Date' in df.columns:
        df['_date'] = pd.to_datetime(df['Date'])
    elif 'Time' in df.columns:
        df['_date'] = pd.to_datetime(df['Time'])
    elif isinstance(df.index, pd.DatetimeIndex):
        df['_date'] = df.index
    else:
        return {}

    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl == 'open':
            col_map[c] = '_open'
        elif cl == 'high':
            col_map[c] = '_high'
        elif cl == 'low':
            col_map[c] = '_low'
        elif cl in ('close', 'last'):
            col_map[c] = '_close'
    df = df.rename(columns=col_map)

    for needed in ['_open', '_high', '_low', '_close']:
        if needed not in df.columns:
            return {}

    df = df.sort_values('_date')
    levels: Dict[str, StratLevel] = {}

    # Current Day Open
    if len(df) >= 2:
        prev_day = df.iloc[-2]
        today = df.iloc[-1]
        # Today's row exists but may have NULL OHLC when the pre-market
        # refresh job (8:30 AM ET) populated only pre_* columns and the
        # 11pm fetcher hasn't filled in regular-session high/low/open/
        # close yet. Fall back to current_price so the brief at 8:45 AM
        # doesn't crash. The pre_high/pre_low values are surfaced
        # separately by the brief embed; here we just need a non-null
        # CDO + intraday high/low for the level-classification step.
        today_open = (float(today['_open'])
                      if pd.notna(today['_open']) else current_price)
        _h = today['_high']
        today_high = max(float(_h) if pd.notna(_h) else current_price,
                         current_price)
        _l = today['_low']
        today_low = min(float(_l) if pd.notna(_l) else current_price,
                        current_price)

        strat = classify_level_strat(
            today_high, today_low, current_price, today_open,
            float(prev_day['_high']), float(prev_day['_low']),
        )
        levels['CDO'] = StratLevel(
            name='CDO', price=today_open,
            timeframe='day', level_type='open',
            strat_class=strat, is_current=True,
            period_label=str(today['_date'].date()) if hasattr(today['_date'], 'date') else str(today['_date']),
        )

    # Current Week Open
    df['_week'] = df['_date'].dt.to_period('W')
    current_week = df['_week'].iloc[-1]
    this_week = df[df['_week'] == current_week]
    prev_weeks = df[df['_week'] < current_week]

    if not this_week.empty and not prev_weeks.empty:
        cw_open = float(this_week.iloc[0]['_open'])
        cw_high = max(float(this_week['_high'].max()), current_price)
        cw_low = min(float(this_week['_low'].min()), current_price)

        last_wk_period = prev_weeks['_week'].iloc[-1]
        last_wk = prev_weeks[prev_weeks['_week'] == last_wk_period]
        pw_high = float(last_wk['_high'].max())
        pw_low = float(last_wk['_low'].min())

        strat = classify_level_strat(cw_high, cw_low, current_price, cw_open, pw_high, pw_low)
        levels['CWO'] = StratLevel(
            name='CWO', price=cw_open,
            timeframe='week', level_type='open',
            strat_class=strat, is_current=True,
            period_label=str(current_week),
        )

    # Current Month Open
    df['_month'] = df['_date'].dt.to_period('M')
    current_month = df['_month'].iloc[-1]
    this_month = df[df['_month'] == current_month]
    prev_months = df[df['_month'] < current_month]

    if not this_month.empty and not prev_months.empty:
        cm_open = float(this_month.iloc[0]['_open'])
        cm_high = max(float(this_month['_high'].max()), current_price)
        cm_low = min(float(this_month['_low'].min()), current_price)

        last_m = prev_months[prev_months['_month'] == prev_months['_month'].iloc[-1]]
        pm_high = float(last_m['_high'].max())
        pm_low = float(last_m['_low'].min())

        strat = classify_level_strat(cm_high, cm_low, current_price, cm_open, pm_high, pm_low)
        levels['CMO'] = StratLevel(
            name='CMO', price=cm_open,
            timeframe='month', level_type='open',
            strat_class=strat, is_current=True,
            period_label=str(current_month),
        )

    return levels


# ��── Gap detection ────────────────────────────────────────────────────────


# ─── Intraday levels (premarket, ORB) — persisted alongside structural ─────


def compute_premarket_levels(
    pre_high: Optional[float],
    pre_low: Optional[float],
) -> Dict[str, StratLevel]:
    """Build StratLevel rows for premarket high / low.

    pre_high / pre_low come from `lib.indicators.calculate_premarket_context`
    (4:00–9:30 ET aggregation per `market_data_intraday`). Persisting
    them to `strat_levels` lets:

      * the live signal_monitor see PMK_H / PMK_L as triggerable
        crossings during RTH (PR #381 added the read-side; this PR
        adds the write-side data they read),
      * `lib/agents/trade_planner.select_trigger_and_regime` use them
        as candidate triggers in the blue-sky path instead of having
        to synthesize an ATR-projected level above pre_high (the
        5/6 QQQ case where the synthetic $695.52 trigger never got
        hit but pre_high $692.86 was the actual turn level — see
        the 5/6 chart's PWH/PWO inside-bar consolidation).

    Returns an empty dict when both inputs are None (no premarket
    data — typical for the first half-hour after a long weekend or
    when the intraday fetcher is mid-write). Caller decides what to
    do with that — premarket_brief logs and proceeds without these
    levels.

    NOTE: caller appends the resulting StratLevels to a LevelMap
    BEFORE calling persist_level_map, so they share the same as_of
    timestamp + source_data_as_of guard as the structural levels.
    """
    out: Dict[str, StratLevel] = {}
    if pre_high is not None and pre_high > 0:
        out['PMK_H'] = StratLevel(
            name='PMK_H', price=float(pre_high),
            timeframe='intraday', level_type='high',
            strat_class='', is_current=True,
            period_label='premarket',
        )
    if pre_low is not None and pre_low > 0:
        out['PMK_L'] = StratLevel(
            name='PMK_L', price=float(pre_low),
            timeframe='intraday', level_type='low',
            strat_class='', is_current=True,
            period_label='premarket',
        )
    return out


# ─── Gap levels ─────────────────────────────────────────────────────────────


def compute_gap_levels(daily_df: pd.DataFrame, lookback: int = 20) -> List[StratLevel]:
    """Detect unfilled gaps from recent sessions.

    A gap exists when today's low > yesterday's high (gap up)
    or today's high < yesterday's low (gap down).
    Gaps are magnetic targets — price fills them reliably.
    """
    if len(daily_df) < 2:
        return []

    df = daily_df.copy()

    # Normalize columns
    h_col = next((c for c in df.columns if c.lower() == 'high'), None)
    l_col = next((c for c in df.columns if c.lower() == 'low'), None)
    d_col = next((c for c in df.columns if c.lower() in ('date', 'time')), None)
    if not h_col or not l_col:
        return []

    df = df.tail(lookback + 1).reset_index(drop=True)
    gaps: List[StratLevel] = []

    for i in range(1, len(df)):
        prev_h = float(df[h_col].iloc[i - 1])
        prev_l = float(df[l_col].iloc[i - 1])
        curr_h = float(df[h_col].iloc[i])
        curr_l = float(df[l_col].iloc[i])

        label = str(df[d_col].iloc[i])[:10] if d_col else str(i)

        # Gap up
        if curr_l > prev_h:
            # Check if filled by subsequent bars
            subsequent = df.iloc[i + 1:] if i + 1 < len(df) else pd.DataFrame()
            if subsequent.empty or float(subsequent[l_col].min()) > prev_h:
                gaps.append(StratLevel(
                    name=f'GAP_H_{label}', price=float(curr_l),
                    timeframe='day', level_type='gap_high',
                    strat_class='gap_up', is_current=False,
                    period_label=label,
                ))
                gaps.append(StratLevel(
                    name=f'GAP_L_{label}', price=prev_h,
                    timeframe='day', level_type='gap_low',
                    strat_class='gap_up', is_current=False,
                    period_label=label,
                ))

        # Gap down
        elif curr_h < prev_l:
            subsequent = df.iloc[i + 1:] if i + 1 < len(df) else pd.DataFrame()
            if subsequent.empty or float(subsequent[h_col].max()) < prev_l:
                gaps.append(StratLevel(
                    name=f'GAP_H_{label}', price=prev_l,
                    timeframe='day', level_type='gap_high',
                    strat_class='gap_down', is_current=False,
                    period_label=label,
                ))
                gaps.append(StratLevel(
                    name=f'GAP_L_{label}', price=float(curr_h),
                    timeframe='day', level_type='gap_low',
                    strat_class='gap_down', is_current=False,
                    period_label=label,
                ))

    return gaps


# ─── PMG detection (spatial clustering) ───────────────────────────────────


def detect_level_clusters(
    levels: List[StratLevel],
    tolerance_pct: float = 0.15,
) -> list:
    """Detect PMG zones where multiple timeframe levels cluster.

    Args:
        levels: list of StratLevel objects
        tolerance_pct: percentage band (0.15 = within 0.15%)

    Returns:
        list of dicts: [{center_price, level_names, timeframes, count, strength}]
    """
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda lv: lv.price)
    zones = []
    used = set()

    for i, lvl in enumerate(sorted_levels):
        if i in used:
            continue

        cluster = [lvl]
        used.add(i)

        for j in range(i + 1, len(sorted_levels)):
            if j in used:
                continue
            if lvl.price == 0:
                continue
            pct_diff = abs(sorted_levels[j].price - lvl.price) / lvl.price * 100
            if pct_diff <= tolerance_pct:
                cluster.append(sorted_levels[j])
                used.add(j)

        if len(cluster) >= 2:
            center = sum(lv.price for lv in cluster) / len(cluster)
            timeframes = set(lv.timeframe for lv in cluster)
            strength = len(cluster) + (len(timeframes) - 1) * 0.5

            zones.append({
                'center_price': round(center, 2),
                'level_names': [lv.name for lv in cluster],
                'timeframes': sorted(timeframes),
                'count': len(cluster),
                'strength': round(strength, 1),
            })

    return sorted(zones, key=lambda z: z['strength'], reverse=True)


# ─── PMG temporal (consecutive higher-highs / lower-lows) ────────────────


def detect_pmg_temporal(
    daily_df: pd.DataFrame,
    n_consecutive: int = 3,
) -> List[dict]:
    """Detect N consecutive higher-high or lower-low days.

    This is the temporal PMG — "daily PMG" per AYCE terminology.
    """
    if len(daily_df) < n_consecutive + 1:
        return []

    h_col = next((c for c in daily_df.columns if c.lower() == 'high'), None)
    l_col = next((c for c in daily_df.columns if c.lower() == 'low'), None)
    if not h_col or not l_col:
        return []

    highs = daily_df[h_col].values
    lows = daily_df[l_col].values
    results = []

    # Higher highs
    hh_streak = 0
    for i in range(1, len(highs)):
        if highs[i] > highs[i - 1]:
            hh_streak += 1
            if hh_streak >= n_consecutive:
                results.append({
                    'type': 'higher_highs',
                    'count': hh_streak,
                    'end_index': i,
                    'price': float(highs[i]),
                })
        else:
            hh_streak = 0

    # Lower lows
    ll_streak = 0
    for i in range(1, len(lows)):
        if lows[i] < lows[i - 1]:
            ll_streak += 1
            if ll_streak >= n_consecutive:
                results.append({
                    'type': 'lower_lows',
                    'count': ll_streak,
                    'end_index': i,
                    'price': float(lows[i]),
                })
        else:
            ll_streak = 0

    return results


# ─── Room to run ──────────────────────────────────────────────────────────


MIN_ROOM_PCT = 0.20

# Staleness filter for trigger / stop selection. A level is too stale
# to drive an intraday playbook when BOTH conditions hold:
#   distance > MAX_TRIGGER_DISTANCE_ATR × atr_14    AND
#   distance > MAX_TRIGGER_DISTANCE_PCT × current_price
# Both axes matter:
#   * Pure ATR fails for high-vol small-caps (ASTX atr_14 ≈ 27% of
#     price → 5×ATR includes a year-old crash low at 41% from spot).
#   * Pure % fails for tight-range index ETFs where 8% would over-
#     filter every legitimate quarterly pivot.
# Defaults: 3.0 ATR matches `_EXTENDED_DISTANCE_ATR` in
# lib.agents.trade_planner; 8% is the empirical "too far for an
# intraday level-break" threshold from the ASTX 2026-04-28 case.
MAX_TRIGGER_DISTANCE_ATR = 3.0
MAX_TRIGGER_DISTANCE_PCT = 0.08


def compute_room_to_run(
    current_price: float,
    levels: List[StratLevel],
    direction: str,
) -> dict:
    """Distance from current price to next level in the trade direction.

    Args:
        current_price: current market price
        levels: list of StratLevel objects
        direction: "CALL" or "PUT"

    Returns:
        dict with next_level, distance_pct, targets, has_room
    """
    sorted_levels = sorted(levels, key=lambda lv: lv.price)

    if direction == 'CALL':
        targets = [lv for lv in sorted_levels if lv.price > current_price]
        if not targets:
            return {'next_level': None, 'distance_pct': 0.0, 'targets': [], 'has_room': False}
        next_level = targets[0]
        distance_pct = (next_level.price - current_price) / current_price * 100
    else:
        targets = [lv for lv in sorted_levels if lv.price < current_price]
        targets.reverse()
        if not targets:
            return {'next_level': None, 'distance_pct': 0.0, 'targets': [], 'has_room': False}
        next_level = targets[0]
        distance_pct = (current_price - next_level.price) / current_price * 100

    return {
        'next_level': next_level,
        'distance_pct': round(distance_pct, 3),
        'targets': targets[:5],
        'has_room': distance_pct >= MIN_ROOM_PCT,
    }


# ─── Risk/Reward ──────────────────────────────────────────────────────────


def compute_risk_reward(
    entry: float,
    stop: float,
    target: float,
) -> float:
    """Calculate risk/reward ratio. Returns 0.0 if risk is zero."""
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return 0.0
    return round(reward / risk, 2)


# ─── Trigger identification ───────────────────────────────────────────────


def _within_staleness_window(
    level_price: float, current_price: float, atr: Optional[float],
) -> bool:
    """A level is "fresh enough" to be a trigger/stop candidate when
    its distance from spot fits BOTH the ATR and percent budgets.

    When `atr` is None or non-positive, the ATR axis is skipped and
    only the percent budget is enforced (back-compat for callers that
    didn't pass ATR; preserves prior behavior for unit tests with
    synthetic data).
    """
    distance = abs(level_price - current_price)
    pct_ok = distance <= MAX_TRIGGER_DISTANCE_PCT * current_price
    if atr is None or atr <= 0:
        return pct_ok
    atr_ok = distance <= MAX_TRIGGER_DISTANCE_ATR * atr
    return pct_ok and atr_ok


def identify_triggers(
    current_price: float,
    levels: Dict[str, StratLevel],
    daily_strat_class: str = '',
    combo: str = '',
    atr: Optional[float] = None,
) -> dict:
    """Identify CALL/PUT trigger levels for the premarket brief.

    Produces the "CALLS above X (PDH) / PUTS below Y (PDL)" format.
    Wires daily_strat_class and combo into the reasoning string.

    Stale-level filter (PR for ASTX 2026-04-28):
      Levels farther than 3×ATR AND 8% from current price are excluded
      from trigger AND stop selection. They stay in the `levels` dict
      (and the persisted `strat_levels` table) so the realtime
      signal-monitor still tracks them for break alerts — but they no
      longer drive playbook entries. Without this, a year-old crash
      low (e.g. PYL 41% below spot) would surface as the PUT trigger,
      and the same level would be used as a 41% stop on the CALL side.
    """
    all_levels = sorted(levels.values(), key=lambda lv: lv.price)
    above_all = [lv for lv in all_levels if lv.price > current_price]
    below_all = [lv for lv in all_levels if lv.price < current_price]
    below_all.reverse()

    above_fresh = [
        lv for lv in above_all
        if _within_staleness_window(lv.price, current_price, atr)
    ]
    below_fresh = [
        lv for lv in below_all
        if _within_staleness_window(lv.price, current_price, atr)
    ]

    result = {'calls': None, 'puts': None}

    # Reasoning context
    ctx_parts = []
    if daily_strat_class:
        ctx_parts.append(f'Daily {daily_strat_class}')
    if combo and combo != 'none':
        ctx_parts.append(f'Combo: {combo}')
    reasoning = ', '.join(ctx_parts) if ctx_parts else ''

    if above_fresh:
        trigger = above_fresh[0]
        targets_above = above_fresh[1:4]
        room = compute_room_to_run(trigger.price, all_levels, 'CALL')

        # Stop on the OPPOSITE side must also be fresh — using a stale
        # year-low as the stop on a CALL trade gives a meaningless
        # 41%-below stop. If no fresh opposite-side level exists, omit
        # the stop and let the playbook formatter / persona logic
        # default to an ATR-based stop downstream.
        stop_lv = below_fresh[0] if below_fresh else None

        result['calls'] = {
            'trigger_level': trigger.price,
            'trigger_name': trigger.name,
            'targets': [
                {'price': t.price, 'name': t.name, 'timeframe': t.timeframe}
                for t in targets_above
            ],
            'stop': stop_lv.price if stop_lv else None,
            'stop_name': stop_lv.name if stop_lv else None,
            'room_to_first_target': room['distance_pct'] if room['targets'] else 0,
            'reasoning': reasoning,
        }

    if below_fresh:
        trigger = below_fresh[0]
        targets_below = below_fresh[1:4]
        room = compute_room_to_run(trigger.price, all_levels, 'PUT')
        stop_lv = above_fresh[0] if above_fresh else None

        result['puts'] = {
            'trigger_level': trigger.price,
            'trigger_name': trigger.name,
            'targets': [
                {'price': t.price, 'name': t.name, 'timeframe': t.timeframe}
                for t in targets_below
            ],
            'stop': stop_lv.price if stop_lv else None,
            'stop_name': stop_lv.name if stop_lv else None,
            'room_to_first_target': room['distance_pct'] if room['targets'] else 0,
            'reasoning': reasoning,
        }

    return result


# ─── Level map builder ────────────────────────────────────────────────────


def build_level_map(
    ticker: str,
    daily_df: pd.DataFrame,
    current_price: float,
    daily_strat_class: str = '',
    combo: str = '',
    atr: Optional[float] = None,
    analysis_date: Optional[date_type] = None,
) -> LevelMap:
    """Build the complete level map for a ticker.

    Top-level orchestrator called by the premarket brief and dashboard.

    `atr` (atr_14 from the most-recent daily row) enables the
    staleness filter inside `identify_triggers`. When None, only the
    percent-distance axis is enforced — back-compat for callers that
    haven't been updated to pass ATR.

    `analysis_date` flows through to compute_previous_levels — see its
    docstring. When the caller has already filtered df via
    ``idx < analysis_date`` (e.g. the premarket brief), passing
    analysis_date here yields PDH/PDL/PWH/etc. anchored to the period
    BEFORE analysis_date, regardless of df's iloc layout.
    """
    prev_levels = compute_previous_levels(daily_df, analysis_date=analysis_date)
    curr_levels = compute_current_levels(daily_df, current_price)
    gap_levels = compute_gap_levels(daily_df, lookback=20)

    # Trigger-eligible level set: prev + current periods. Gap levels
    # are context (PMG clustering) and not first-class trigger
    # candidates — they're typically the same horizontal lines that
    # already show up as PDH/PWH/etc, just labeled by gap origin.
    structural_dict = {**prev_levels, **curr_levels}
    structural_list = list(structural_dict.values())
    all_levels_list = structural_list + gap_levels

    pmg_zones = detect_level_clusters(all_levels_list, tolerance_pct=0.15)

    triggers = identify_triggers(
        current_price, structural_dict, daily_strat_class, combo, atr=atr,
    )

    # `room_to_run_*` must use the SAME level set as `identify_triggers`
    # so the playbook's 'Room to trigger: X%' number is consistent
    # with the actual trigger emitted. Previously this used
    # `all_levels_list` (incl. gaps) while triggers used
    # `structural_dict` (no gaps), so a gap level closer than the
    # trigger could dominate the room number even though it never
    # surfaced as a trigger candidate. (Commit 6 of the staleness fix.)
    room_up = compute_room_to_run(current_price, structural_list, 'CALL')
    room_down = compute_room_to_run(current_price, structural_list, 'PUT')

    return LevelMap(
        ticker=ticker,
        as_of=pd.Timestamp.now('US/Eastern').isoformat(),
        current_price=current_price,
        levels=sorted(all_levels_list, key=lambda lv: lv.price),
        pmg_zones=pmg_zones,
        calls_trigger=triggers.get('calls'),
        puts_trigger=triggers.get('puts'),
        room_to_run_up=room_up['distance_pct'],
        room_to_run_down=room_down['distance_pct'],
    )


# ─── Brief formatter ─────────────────────────────────────────────────────


def levels_to_named_dict(level_map: LevelMap) -> dict[str, float]:
    """Flatten a LevelMap.levels list into a {name: price} dict.

    Convenience for callers that need to drive `lib.agents.trade_planner.
    select_trigger_and_regime` from a LevelMap (e.g. the premarket brief
    computing regime per ticker without rebuilding the multi-tf series
    from scratch).
    """
    out: dict[str, float] = {}
    for lv in level_map.levels:
        if lv.name and lv.price is not None:
            out[lv.name] = float(lv.price)
    return out


def format_levels_for_brief(
    level_map: LevelMap,
    bias: str,
    combo: str = '',
    daily_strat_class: str = '',
    regime: str = 'normal',
    regime_long: Optional[str] = None,
    regime_short: Optional[str] = None,
    regime_compute_error: Optional[str] = None,
    atr: Optional[float] = None,
) -> str:
    """Format the level map into the playbook Discord format.

    Output (normal regime):
      IWM 215.42 — Daily 2U, Combo: 212_bull_reversal, FTFC +0.7 bullish
      CALLS above 215.85 (PDH)
        Stop: 213.20 (PDL)
        T1: 217.10 (PWH) — 0.58% room

    Regime-aware variants (PR α):
      * `orb_only`  — pre-market cleared every structural level in the
                      trade direction. CALLS/PUTS triggers are
                      suppressed (they'd be misleading on extreme gap
                      days like AMD 4/24); the playbook emits only an
                      ORB-wait banner.
      * `extended`  — next unbroken level >= 3 ATR away. Standard
                      CALLS/PUTS triggers render but a leading warning
                      tells the trader to wait for 15-min ORB
                      confirmation.
      * `normal`    — original layout, no banners.

    `regime_long` / `regime_short` are optional per-side overrides.
    When passed, the CALLS block reflects regime_long and the PUTS
    block reflects regime_short — so a bullish-bias ticker whose PUT
    side is gap-extended shows the right warning for the bias-denial
    setup. When omitted (legacy callers), `regime` applies to both.

    `regime_compute_error` surfaces a regime-classifier failure as a
    visible line in the playbook instead of silently rendering a stale
    'normal' regime — the bug pattern from
    gcp/premarket_brief.py:642-648 where exceptions were swallowed.
    """
    # Per-side regime fallback — when not explicitly passed, both
    # sides use the legacy single-regime value.
    if regime_long is None:
        regime_long = regime
    if regime_short is None:
        regime_short = regime

    lines = []
    if regime_compute_error:
        lines.append(
            f"  ⚠ regime classifier failed: {regime_compute_error} "
            f"-- defaulting to 'normal'; treat with care"
        )

    # ── Regime banner ──────────────────────────────────────────────
    # Per-side regimes: only emit the FULL "everything cleared"
    # short-circuit when BOTH sides are orb_only (the gap-up extreme
    # day case — AMD 4/24). Otherwise fall through and render per-side
    # banners inline next to each CALLS / PUTS block, so a bullish
    # ticker whose PUT side is gap-extended still shows a meaningful
    # CALLS playbook rather than being suppressed entirely.
    both_sides_orb_only = (
        regime_long == 'orb_only' and regime_short == 'orb_only'
    )
    if both_sides_orb_only:
        # Name the actual structural levels that pre-market price has
        # already cleared, so the trader sees the LAST level passed
        # (e.g. PWH $222 for a long bias, PQL $214 for a short bias).
        # Without this the banner read "every structural level" which
        # is technically true but useless — the trader still needs to
        # know which level they're now above/below.
        bias_l = (bias or '').lower()
        spot = level_map.current_price
        cleared_high = [
            lv for lv in level_map.levels
            if lv.level_type == 'high' and not lv.is_current
            and lv.price < spot
        ]
        cleared_low = [
            lv for lv in level_map.levels
            if lv.level_type == 'low' and not lv.is_current
            and lv.price > spot
        ]
        # Closest-to-spot first — that's the LAST level price passed.
        cleared_high.sort(key=lambda lv: spot - lv.price)
        cleared_low.sort(key=lambda lv: lv.price - spot)
        if 'bear' in bias_l and cleared_low:
            cleared = cleared_low[:4]
            direction_word = 'bearish'
        elif cleared_high:
            cleared = cleared_high[:4]
            direction_word = 'bullish'
        elif cleared_low:
            cleared = cleared_low[:4]
            direction_word = 'bearish'
        else:
            cleared = []
            direction_word = ''
        lines.append(
            "  ORB-only — pre-market cleared every structural "
            "level in the trade direction. No level-break trigger; "
            "wait for the 15-min opening range to establish before "
            "entering."
        )
        if cleared:
            lines.append('')
            lines.append(
                f"  Last {direction_word} level passed: "
                f"{cleared[0].name} {cleared[0].price:.2f} "
                f"(spot {spot:.2f})"
            )
            if len(cleared) > 1:
                rest = ', '.join(
                    f"{lv.name} {lv.price:.2f}" for lv in cleared[1:]
                )
                lines.append(f"  Other cleared: {rest}")
        return '\n'.join(lines)

    ct = level_map.calls_trigger
    pt = level_map.puts_trigger
    spot = level_map.current_price

    # Find the would-be trigger candidate that the staleness filter
    # rejected — the trader needs to know WHICH level was too far so
    # they can mentally place it on the chart. For PUTS, "next below"
    # is the closest level under spot; for CALLS, the closest above.
    def _stale_candidate(direction: str):
        """Return (level, distance_pct, distance_atr) for the closest
        filtered-out level on `direction`'s side. distance_atr is None
        when atr was not provided."""
        if direction == 'PUTS':
            cands = sorted(
                [lv for lv in level_map.levels if lv.price < spot],
                key=lambda lv: -lv.price,
            )
        else:
            cands = sorted(
                [lv for lv in level_map.levels if lv.price > spot],
                key=lambda lv: lv.price,
            )
        if not cands:
            return None, None, None
        nearest = cands[0]
        dist = abs(nearest.price - spot)
        dist_pct = dist / spot * 100
        dist_atr = (dist / atr) if (atr and atr > 0) else None
        return nearest, dist_pct, dist_atr

    # Per-side banner construction. Each side independently shows the
    # right warning for its own regime — so a bullish ticker whose
    # CALLS regime is 'normal' but PUTS regime is 'extended' renders
    # the CALLS playbook normally and warns ONLY on the PUT side.
    def _side_banner(direction: str, side_regime: str,
                     trigger_present: bool) -> Optional[str]:
        if not trigger_present:
            stale, dist_pct, dist_atr = _stale_candidate(direction)
            if stale is None:
                # No level on this side at all (young ticker, partial
                # history). Fall back to the generic banner.
                return (
                    f"  {direction}: no near-term structural level "
                    f"-- wait for ORB confirmation"
                )
            # Multi-line format mirrors the indentation of an active
            # CALLS/PUTS block so the trader's eye lands on the same
            # vertical rhythm — name on top, room/qualifiers indented,
            # ORB callout on the trailing line.
            direction_word = 'bearish' if direction == 'PUTS' else 'bullish'
            if dist_atr is not None:
                room_qual = f"({dist_atr:.1f}× ATR away, too far for intraday)"
            else:
                room_qual = "(too far for intraday)"
            return (
                f"  {direction}: no near-term structural level, "
                f"next {direction_word} level is {stale.name} {stale.price:.2f}\n"
                f"    Room to trigger: {dist_pct:.1f}% {room_qual}\n"
                f"    -- wait for ORB confirmation"
            )
        if side_regime == 'orb_only':
            return (
                f"  {direction}: pre-market cleared every structural "
                f"level on this side — wait for the 15-min ORB"
            )
        if side_regime == 'extended':
            return (
                f"  {direction}: extended gap — recommend 15-min ORB "
                f"confirmation before entry"
            )
        return None

    no_call_banner = _side_banner('CALLS', regime_long, ct is not None) if ct is None else None
    no_put_banner = _side_banner('PUTS', regime_short, pt is not None) if pt is None else None
    call_pre_banner = _side_banner('CALLS', regime_long, True) if ct is not None and regime_long != 'normal' else None
    put_pre_banner = _side_banner('PUTS', regime_short, True) if pt is not None and regime_short != 'normal' else None

    # Suppress the trigger block on any side whose regime is `orb_only`.
    # The regime classifier (`lib.agents.trade_planner.select_trigger_and_regime`)
    # marks `orb_only` when *pre-market* extremes have cleared every
    # structural level on that side — `cleared_above = max(ref, pre_high)`
    # for longs, `cleared_below = min(ref, pre_low)` for shorts. By the
    # time the brief renders at 8:30 AM ET, `level_map.current_price`
    # is yesterday's close (NOT the pre-market spike); so a check like
    # `trigger_level < current_price` would miss the audit's actual
    # case (IWM 5/7: yesterday's close 277.14 < trigger 278.24, but
    # pre-market spiked to ~287). The earlier draft of this fix made
    # exactly that mistake — Codex review on PR #307 caught it.
    #
    # The right policy is to trust the regime classifier's decision
    # without second-guessing: if it says `orb_only`, the structural
    # setup on that side has been compromised by pre-market action,
    # and the trigger / stop / target / room block is noise relative
    # to the banner. The banner ("pre-market cleared every structural
    # level on this side — wait for the 15-min ORB") is the
    # actionable signal.
    #
    # This mirrors the existing convention at line 988-989: the
    # `call_pre_banner` already renders purely from `regime_long`, no
    # spot check. We extend the same trust to the trigger-block
    # suppression.
    cleared_call = ct is not None and regime_long == 'orb_only'
    cleared_put = pt is not None and regime_short == 'orb_only'

    if ct:
        if call_pre_banner:
            lines.append(call_pre_banner)
        if not cleared_call:
            line = f"  CALLS above {ct['trigger_level']:.2f} ({ct['trigger_name']})"
            if bias == 'bearish':
                line += ' -- only if bias denied'
            lines.append(line)
            if ct.get('stop'):
                lines.append(f"    Stop: {ct['stop']:.2f} ({ct['stop_name']})")
            targets = ct.get('targets', [])
            for i, t in enumerate(targets, 1):
                lines.append(f"    T{i}: {t['price']:.2f} ({t['name']})")
            # Label the room number by what's actually below it. The line
            # printed here measures "current price -> trigger" (which
            # `room_to_run_up` returns), not "trigger -> T1". Calling it
            # "Room to T1" was a stale carryover from when triggers and T1
            # were the same level.
            if targets and level_map.room_to_run_up:
                lines.append(f"    Room to trigger: {level_map.room_to_run_up:.2f}%")
    elif no_call_banner:
        lines.append(no_call_banner)

    if (ct or no_call_banner) and (pt or no_put_banner):
        lines.append('')

    if pt:
        if put_pre_banner:
            lines.append(put_pre_banner)
        if not cleared_put:
            line = f"  PUTS below {pt['trigger_level']:.2f} ({pt['trigger_name']})"
            if bias == 'bullish':
                line += ' -- only if bias denied'
            lines.append(line)
            if pt.get('stop'):
                lines.append(f"    Stop: {pt['stop']:.2f} ({pt['stop_name']})")
            targets = pt.get('targets', [])
            for i, t in enumerate(targets, 1):
                lines.append(f"    T{i}: {t['price']:.2f} ({t['name']})")
            if targets and level_map.room_to_run_down:
                lines.append(f"    Room to trigger: {level_map.room_to_run_down:.2f}%")
    elif no_put_banner:
        lines.append(no_put_banner)

    if level_map.pmg_zones:
        lines.append('')
        lines.append('  PMG ZONES:')
        for z in level_map.pmg_zones[:3]:
            names = ', '.join(z['level_names'])
            lines.append(
                f"    {z['center_price']:.2f} ({names}) "
                f"[strength: {z['strength']}]"
            )

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Persistence — write the LevelMap into Cloud SQL `strat_levels` table.
# Ported from PR #101's operational layer to support the realtime
# signal-monitor's level-break detection path. Idempotent via
# ON CONFLICT DO UPDATE so the same (ticker, as_of, level_name) tuple
# can be re-upserted when intraday repaints (e.g. CDO updates).
# ---------------------------------------------------------------------------


class StaleSourceDataError(RuntimeError):
    """Raised when persist_level_map's source_data_as_of is too old.

    Defense-in-depth against the failure mode that bit production on
    2026-05-06: the daily fetcher was latched at 2026-04-27 from 4/28
    onward, so the brief at 8:30 ET on 5/6 read 4/27-stale data, built
    levels with `period_label='2026-04-24'`, and silently wrote them
    into `strat_levels` rows stamped `as_of=2026-05-06`. Every
    downstream consumer (signal_monitor, insight pipeline, dashboard)
    then trusted the levels.

    The data layer fixes (#322 fail-fast on stale --date, #323
    NULL-close filter, #325 on_stale guard on DataLoader) catch the
    upstream cause. This guard is the SECOND layer: even if a fresh
    bug or edge case lets stale data through, persist_level_map
    refuses to write rather than poison the level cache.
    """


def _trading_days_between(source_ts: pd.Timestamp, ref_ts: pd.Timestamp) -> int:
    """Count NYSE trading days from source_ts (exclusive) to ref_ts (inclusive).

    Returns 0 when source >= ref. Honors NYSE market holidays via
    `pandas_market_calendars.get_calendar('NYSE')`. Examples:
      Fri 5/8 close → Mon 5/11 brief = 1 trading day (Mon)
      Thu 5/22 close → Tue 5/27 (post-Memorial-Day) brief = 2 (Fri + Tue,
        skipping Memorial-Day Mon)
      4/27 close → 5/6 (the original 5/6 freeze) = 6 trading days

    The freshness guard uses business-days because that's the semantic
    intent: "no more than N trading sessions behind." Calendar days
    have to use a +3-day weekend buffer (max_age_days=4 to allow for
    Mon-after-Fri = 3 calendar days), which is implicit.
    """
    if source_ts >= ref_ts:
        return 0
    try:
        import pandas_market_calendars as mcal
    except ImportError:
        # Fallback: caller environment doesn't have the calendar lib.
        # Approximate with calendar-days / 1.4 (rough business-day ratio).
        # Defensive — production has the dep per requirements-gcp.txt.
        return max(0, int((ref_ts - source_ts).total_seconds() / 86400.0 / 1.4))
    nyse = mcal.get_calendar('NYSE')
    # `valid_days` returns DatetimeIndex of trading days in [start, end].
    # Use source_ts.normalize() + 1 day as start so source itself is excluded.
    start_date = (source_ts.normalize() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end_date = ref_ts.normalize().strftime('%Y-%m-%d')
    try:
        days = nyse.valid_days(start_date=start_date, end_date=end_date)
    except Exception:
        return 0
    return len(days)


def persist_level_map(
    level_map: 'LevelMap',
    conn,
    *,
    source_data_as_of=None,
    max_age_business_days: int = 2,
    today=None,
) -> int:
    """Persist a LevelMap into the strat_levels table.

    Inserts one row per StratLevel in level_map.levels. Re-runs of the
    same (ticker, as_of, level_name) update the price, strat_class,
    is_current, period_label, and source_data_as_of fields.

    Args:
        level_map: LevelMap returned by build_level_map()
        conn: an open psycopg2 / pg8000 connection. Caller manages
              the surrounding transaction (commit / rollback).
        source_data_as_of: timestamp of the latest `market_data_daily`
              row used to compute this level map. Stored on every row
              so readers can verify freshness in-band. When None, the
              column is NULL (back-compat for callers that haven't
              been updated; freshness check below short-circuits).
        max_age_business_days: refuse to write when more than this many
              NYSE trading days have elapsed since source_data_as_of.
              Default 2 = "Friday close → Monday OK (1 day); Thursday
              close → Tuesday-after-Memorial-Day OK (2 days)." The
              original 5/6 freeze was 6 trading days stale — well past
              2. Stricter callers (intraday re-runs, weekday backfills)
              can pass `=0` or `=1` to fail-fast on same-day or
              one-day-old data.

              Note: business-day semantics are clearer than the
              calendar-day approach used by sibling guards #323
              (audit watchdog) and #325 (DataLoader on_stale). A
              future PR should convert all three to business-days
              for consistency. See docs/audit/2026-05-08/ for the
              freshness-guard family rationale.
        today: datetime override for the freshness check (testability).
               Defaults to datetime.now() in UTC.

    Raises:
        StaleSourceDataError: when source_data_as_of is more than
            max_age_business_days NYSE trading days behind `today`.
            The caller's transaction should roll back. Pre-fix this
            path was silent — the row was written with stale prices
            and a fresh as_of timestamp, polluting every downstream
            reader.

    Returns:
        Number of rows attempted (== len(level_map.levels)).
    """
    if not level_map.levels:
        return 0

    # Freshness check (skipped only when source_data_as_of is None for
    # back-compat with callers that haven't been wired through yet —
    # those callers should be migrated; the None path is a transitional
    # convenience, not a long-term position).
    if source_data_as_of is not None:
        from datetime import datetime, timezone
        # Normalize to UTC so tz-aware vs naive comparisons don't raise.
        # The caller may pass a date, datetime (naive or aware), or
        # pandas Timestamp — coerce all to a UTC pd.Timestamp.
        ts = pd.Timestamp(source_data_as_of)
        if ts.tz is None:
            ts = ts.tz_localize('UTC')
        else:
            ts = ts.tz_convert('UTC')

        ref = today if today is not None else datetime.now(timezone.utc)
        ref_ts = pd.Timestamp(ref)
        if ref_ts.tz is None:
            ref_ts = ref_ts.tz_localize('UTC')
        else:
            ref_ts = ref_ts.tz_convert('UTC')

        # Business-day staleness via NYSE trading calendar.
        biz_days = _trading_days_between(ts, ref_ts)
        if biz_days > max_age_business_days:
            raise StaleSourceDataError(
                f"persist_level_map({level_map.ticker}): refusing to write — "
                f"source_data_as_of={ts.isoformat()} is {biz_days} NYSE "
                f"trading days behind {ref_ts.isoformat()} (threshold: "
                f"{max_age_business_days} trading days). The level map "
                f"was built off stale `market_data_daily` data; writing "
                f"it would propagate the staleness to every downstream "
                f"reader. Investigate the daily fetcher (likely a sticky "
                f"--date latch per docs/RUNBOOK_BACKFILL.md) before retrying."
            )

    sql = (
        "INSERT INTO strat_levels "
        "(ticker, as_of, level_name, price, timeframe, level_type, "
        " strat_class, is_current, period_label, source_data_as_of) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (ticker, as_of, level_name) DO UPDATE SET "
        "  price = EXCLUDED.price, "
        "  strat_class = EXCLUDED.strat_class, "
        "  is_current = EXCLUDED.is_current, "
        "  period_label = EXCLUDED.period_label, "
        "  source_data_as_of = EXCLUDED.source_data_as_of"
    )
    rows = [
        (
            level_map.ticker, level_map.as_of, lev.name, lev.price,
            lev.timeframe, lev.level_type, lev.strat_class,
            bool(lev.is_current), lev.period_label, source_data_as_of,
        )
        for lev in level_map.levels
    ]
    cur = conn.cursor()
    cur.executemany(sql, rows)
    return len(rows)
