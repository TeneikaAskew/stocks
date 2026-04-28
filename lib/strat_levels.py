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


def compute_previous_levels(daily_df: pd.DataFrame) -> Dict[str, StratLevel]:
    """Compute previous period H/L levels from daily OHLCV data.

    Reads the raw OHLCV to compute period aggregates, then classifies
    each period relative to the one before it.

    Args:
        daily_df: DataFrame with Open/High/Low/Close columns,
                  DatetimeIndex or a 'date'/'Date'/'Time' column.
                  Sorted ascending. Needs ~1 year for yearly levels.
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

    # Period definitions: (group_key, label, abbreviation_prefix)
    periods = [
        ('_day', 'day', 'PD'),
        ('_week', 'week', 'PW'),
        ('_month', 'month', 'PM'),
        ('_quarter', 'quarter', 'PQ'),
        ('_year', 'year', 'PY'),
    ]

    df['_day'] = df['_date'].dt.date
    df['_week'] = df['_date'].dt.to_period('W')
    df['_month'] = df['_date'].dt.to_period('M')
    df['_quarter'] = df['_date'].dt.to_period('Q')
    df['_year'] = df['_date'].dt.year

    for group_col, tf_label, prefix in periods:
        grp = df.groupby(group_col).agg(
            H=('_high', 'max'),
            L=('_low', 'min'),
            O=('_open', 'first'),
            C=('_close', 'last'),
        )
        if len(grp) < 2:
            continue

        # Previous completed period
        prev_period = grp.iloc[-2]
        prev_label = str(grp.index[-2])

        h_name = f'{prefix}H'
        l_name = f'{prefix}L'

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

        # Classify: compare prev period to the one before it
        if len(grp) >= 3:
            p_n1 = grp.iloc[-2]  # prev period
            p_n2 = grp.iloc[-3]  # period before prev
            strat = classify_level_strat(
                p_n1['H'], p_n1['L'], p_n1['C'], p_n1['O'],
                p_n2['H'], p_n2['L'],
            )
            levels[h_name].strat_class = strat
            levels[l_name].strat_class = strat

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
        today_open = float(today['_open'])
        today_high = max(float(today['_high']), current_price)
        today_low = min(float(today['_low']), current_price)

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


def identify_triggers(
    current_price: float,
    levels: Dict[str, StratLevel],
    daily_strat_class: str = '',
    combo: str = '',
) -> dict:
    """Identify CALL/PUT trigger levels for the premarket brief.

    Produces the "CALLS above X (PDH) / PUTS below Y (PDL)" format.
    Wires daily_strat_class and combo into the reasoning string.
    """
    all_levels = sorted(levels.values(), key=lambda lv: lv.price)
    above = [lv for lv in all_levels if lv.price > current_price]
    below = [lv for lv in all_levels if lv.price < current_price]
    below.reverse()

    result = {'calls': None, 'puts': None}

    # Reasoning context
    ctx_parts = []
    if daily_strat_class:
        ctx_parts.append(f'Daily {daily_strat_class}')
    if combo and combo != 'none':
        ctx_parts.append(f'Combo: {combo}')
    reasoning = ', '.join(ctx_parts) if ctx_parts else ''

    if above:
        trigger = above[0]
        targets_above = above[1:4]
        room = compute_room_to_run(trigger.price, all_levels, 'CALL')

        result['calls'] = {
            'trigger_level': trigger.price,
            'trigger_name': trigger.name,
            'targets': [
                {'price': t.price, 'name': t.name, 'timeframe': t.timeframe}
                for t in targets_above
            ],
            'stop': below[0].price if below else None,
            'stop_name': below[0].name if below else None,
            'room_to_first_target': room['distance_pct'] if room['targets'] else 0,
            'reasoning': reasoning,
        }

    if below:
        trigger = below[0]
        targets_below = below[1:4]
        room = compute_room_to_run(trigger.price, all_levels, 'PUT')

        result['puts'] = {
            'trigger_level': trigger.price,
            'trigger_name': trigger.name,
            'targets': [
                {'price': t.price, 'name': t.name, 'timeframe': t.timeframe}
                for t in targets_below
            ],
            'stop': above[0].price if above else None,
            'stop_name': above[0].name if above else None,
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
) -> LevelMap:
    """Build the complete level map for a ticker.

    Top-level orchestrator called by the premarket brief and dashboard.
    """
    prev_levels = compute_previous_levels(daily_df)
    curr_levels = compute_current_levels(daily_df, current_price)
    gap_levels = compute_gap_levels(daily_df, lookback=20)

    all_levels_dict = {**prev_levels, **curr_levels}
    all_levels_list = list(all_levels_dict.values()) + gap_levels

    pmg_zones = detect_level_clusters(all_levels_list, tolerance_pct=0.15)

    triggers = identify_triggers(
        current_price, all_levels_dict, daily_strat_class, combo,
    )

    room_up = compute_room_to_run(current_price, all_levels_list, 'CALL')
    room_down = compute_room_to_run(current_price, all_levels_list, 'PUT')

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


def format_levels_for_brief(
    level_map: LevelMap,
    bias: str,
    combo: str = '',
    daily_strat_class: str = '',
) -> str:
    """Format the level map into the playbook Discord format.

    Output:
      IWM 215.42 — Daily 2U, Combo: 212_bull_reversal, FTFC +0.7 bullish
      CALLS above 215.85 (PDH)
        Stop: 213.20 (PDL)
        T1: 217.10 (PWH) — 0.58% room
    """
    lines = []
    ct = level_map.calls_trigger
    pt = level_map.puts_trigger

    if ct:
        line = f"  CALLS above {ct['trigger_level']:.2f} ({ct['trigger_name']})"
        if bias == 'bearish':
            line += ' -- only if bias denied'
        lines.append(line)
        if ct.get('stop'):
            lines.append(f"    Stop: {ct['stop']:.2f} ({ct['stop_name']})")
        for i, t in enumerate(ct.get('targets', []), 1):
            lines.append(f"    T{i}: {t['price']:.2f} ({t['name']})")
        if level_map.room_to_run_up:
            lines.append(f"    Room to T1: {level_map.room_to_run_up:.2f}%")

    if ct and pt:
        lines.append('')

    if pt:
        line = f"  PUTS below {pt['trigger_level']:.2f} ({pt['trigger_name']})"
        if bias == 'bullish':
            line += ' -- only if bias denied'
        lines.append(line)
        if pt.get('stop'):
            lines.append(f"    Stop: {pt['stop']:.2f} ({pt['stop_name']})")
        for i, t in enumerate(pt.get('targets', []), 1):
            lines.append(f"    T{i}: {t['price']:.2f} ({t['name']})")
        if level_map.room_to_run_down:
            lines.append(f"    Room to T1: {level_map.room_to_run_down:.2f}%")

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


def persist_level_map(level_map: 'LevelMap', conn) -> int:
    """Persist a LevelMap into the strat_levels table.

    Inserts one row per StratLevel in level_map.levels. Re-runs of the
    same (ticker, as_of, level_name) update the price, strat_class,
    is_current, and period_label fields.

    Args:
        level_map: LevelMap returned by build_level_map()
        conn: an open psycopg2 / pg8000 connection. Caller manages
              the surrounding transaction (commit / rollback).

    Returns:
        Number of rows attempted (== len(level_map.levels)).
    """
    if not level_map.levels:
        return 0

    sql = (
        "INSERT INTO strat_levels "
        "(ticker, as_of, level_name, price, timeframe, level_type, "
        " strat_class, is_current, period_label) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (ticker, as_of, level_name) DO UPDATE SET "
        "  price = EXCLUDED.price, "
        "  strat_class = EXCLUDED.strat_class, "
        "  is_current = EXCLUDED.is_current, "
        "  period_label = EXCLUDED.period_label"
    )
    rows = [
        (
            level_map.ticker, level_map.as_of, lev.name, lev.price,
            lev.timeframe, lev.level_type, lev.strat_class,
            bool(lev.is_current), lev.period_label,
        )
        for lev in level_map.levels
    ]
    cur = conn.cursor()
    cur.executemany(sql, rows)
    return len(rows)
