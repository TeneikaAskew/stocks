"""Strat levels engine — horizontal price markers used as triggers, stops,
targets, and PMG zones.

The brief and signal_monitor consume the LevelMap produced here to render
playbook output. Reuses existing data: the previous-period H/L/O/C
already live in market_data_daily, so this module reads from there
rather than recomputing.

See docs/STRAT_METHODOLOGY.md §6-§7 for the spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type, datetime
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from lib.strat import StratClassifier


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class StratLevel:
    """One horizontal level on a chart.

    `strat_class` is the live 1/2U/2D/3 (or '' if not applicable).
    `level_type` distinguishes support / resistance / pivot / gap / open.
    """

    name: str
    price: float
    timeframe: str = ''         # '1d', '1w', '1mo', '1q', '1y', or ''
    level_type: str = 'pivot'   # 'support' | 'resistance' | 'pivot' | 'gap' | 'open'
    strat_class: str = ''
    is_current: bool = False    # True for current-period opens
    period_label: str = ''      # human-readable (e.g. 'Q2 2024')

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'price': float(self.price),
            'timeframe': self.timeframe,
            'level_type': self.level_type,
            'strat_class': self.strat_class,
            'is_current': bool(self.is_current),
            'period_label': self.period_label,
        }


@dataclass
class LevelMap:
    """All levels for a single ticker at a given moment."""

    ticker: str
    as_of: datetime
    current_price: float
    levels: List[StratLevel] = field(default_factory=list)
    pmg_clusters: List[dict] = field(default_factory=list)
    pmg_temporal: dict = field(default_factory=dict)

    def by_name(self, name: str) -> Optional[StratLevel]:
        for lev in self.levels:
            if lev.name == name:
                return lev
        return None

    def above(self, price: float) -> List[StratLevel]:
        return sorted([l for l in self.levels if l.price > price],
                      key=lambda l: l.price)

    def below(self, price: float) -> List[StratLevel]:
        return sorted([l for l in self.levels if l.price < price],
                      key=lambda l: l.price, reverse=True)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_level_strat(
    curr_high: float, curr_low: float,
    curr_close: float, curr_open: float,
    prev_high: float, prev_low: float,
) -> str:
    """Strat classification for a level / current-period bar.

    Returns one of: '1', '2U', '2D', '3', 'f2u', 'f2d'.
    """
    base = StratClassifier.classify_candle(curr_high, curr_low, prev_high, prev_low)
    if base == '2U' and curr_close < curr_open:
        return 'f2u'
    if base == '2D' and curr_close > curr_open:
        return 'f2d'
    return base


# ---------------------------------------------------------------------------
# Previous-period levels (reads from market_data_daily)
# ---------------------------------------------------------------------------


_PREV_COLS_SHORT = {
    'Day':     ('PDH', 'PDL', 'PDO', 'PDC', '1d'),
    'Week':    ('PWH', 'PWL', 'PWO', 'PWC', '1w'),
    'Month':   ('PMH', 'PML', 'PMO', 'PMC', '1mo'),
    'Quarter': ('PQH', 'PQL', 'PQO', 'PQC', '1q'),
    'Year':    ('PYH', 'PYL', 'PYO', 'PYC', '1y'),
}


def compute_previous_levels(daily_df: pd.DataFrame) -> List[StratLevel]:
    """Extract Prev_Day/Week/Month/Quarter/Year levels from the *latest*
    market_data_daily row.

    Expects ``daily_df`` to contain ``Prev_<Period>_High/Low/Open/Close``
    columns (produced by ``lib.indicators.calculate_historical_levels``).
    Missing columns are skipped silently.
    """
    if daily_df is None or daily_df.empty:
        return []

    row = daily_df.iloc[-1]
    levels: List[StratLevel] = []

    for label, (h, l, o, c, tf) in _PREV_COLS_SHORT.items():
        for col_suffix, marker, ltype in [
            ('High', h, 'resistance'),
            ('Low',  l, 'support'),
            ('Open', o, 'pivot'),
            ('Close', c, 'pivot'),
        ]:
            col = f'Prev_{label}_{col_suffix}'
            val = row.get(col) if col in daily_df.columns else None
            if val is None or pd.isna(val):
                continue
            levels.append(StratLevel(
                name=marker,
                price=float(val),
                timeframe=tf,
                level_type=ltype,
            ))
    return levels


# ---------------------------------------------------------------------------
# Current-period opens (live classification vs prior period)
# ---------------------------------------------------------------------------


def compute_current_levels(
    daily_df: pd.DataFrame,
    current_price: float,
) -> List[StratLevel]:
    """Current Day/Week/Month/Quarter/Year opens classified live against
    the prior period's H/L using ``classify_level_strat``.

    Requires the most recent daily row to have an Open + the prior-period
    H/L columns. The first bar of each period is treated as the period's
    open; subsequent bars carry that same value forward.
    """
    if daily_df is None or daily_df.empty:
        return []

    row = daily_df.iloc[-1]
    levels: List[StratLevel] = []

    # The "current open" anchor is just today's daily Open. We classify
    # the live price against the prev-period H/L to derive a strat_class
    # for the current period.
    todays_open_val = row.get('Open')
    if todays_open_val is None or pd.isna(todays_open_val):
        return []
    todays_open = float(todays_open_val)

    period_specs = [
        ('Day',     'CDO', '1d'),
        ('Week',    'CWO', '1w'),
        ('Month',   'CMO', '1mo'),
        ('Quarter', 'CQO', '1q'),
        ('Year',    'CYO', '1y'),
    ]

    for label, marker, tf in period_specs:
        ph_col = f'Prev_{label}_High'
        pl_col = f'Prev_{label}_Low'
        if ph_col not in daily_df.columns or pl_col not in daily_df.columns:
            continue
        ph = row.get(ph_col)
        pl = row.get(pl_col)
        if ph is None or pl is None or pd.isna(ph) or pd.isna(pl):
            continue

        # Use the live current_price as the "high or low" probe — same
        # convention the brief uses for "are we above PDH yet?"
        live_h = max(current_price, todays_open)
        live_l = min(current_price, todays_open)
        live_c = float(current_price)
        live_o = todays_open

        sclass = classify_level_strat(live_h, live_l, live_c, live_o,
                                       float(ph), float(pl))
        levels.append(StratLevel(
            name=marker,
            price=todays_open,
            timeframe=tf,
            level_type='open',
            strat_class=sclass,
            is_current=True,
        ))

    return levels


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


def compute_gap_levels(
    daily_df: pd.DataFrame,
    lookback: int = 20,
    current_price: Optional[float] = None,
) -> List[StratLevel]:
    """Unfilled gap-up / gap-down levels in the last ``lookback`` daily bars.

    A gap-up is an Open above the prior day's High; it's "unfilled" if no
    subsequent bar's Low has touched the prior High. Gap-downs are
    mirrored. The level price is the prior day's High (gap-up) or Low
    (gap-down) — the magnet line price will revisit.
    """
    if daily_df is None or len(daily_df) < 2:
        return []

    df = daily_df.tail(lookback + 1).reset_index(drop=True)
    if 'Open' not in df.columns or 'High' not in df.columns or 'Low' not in df.columns:
        return []

    levels: List[StratLevel] = []
    for i in range(1, len(df)):
        prev_h = df.loc[i - 1, 'High']
        prev_l = df.loc[i - 1, 'Low']
        op = df.loc[i, 'Open']
        if pd.isna(prev_h) or pd.isna(prev_l) or pd.isna(op):
            continue

        # Gap up: today's open above prior day's high. Filled if any
        # subsequent low touches prev_h.
        if op > prev_h:
            future_lows = df.loc[i:, 'Low']
            filled = (future_lows <= prev_h).any()
            if not filled:
                date_label = ''
                if 'Time' in df.columns:
                    date_label = str(pd.to_datetime(df.loc[i, 'Time']).date())
                levels.append(StratLevel(
                    name=f'Gap_Up_{date_label or i}',
                    price=float(prev_h),
                    timeframe='1d',
                    level_type='gap',
                ))

        # Gap down
        if op < prev_l:
            future_highs = df.loc[i:, 'High']
            filled = (future_highs >= prev_l).any()
            if not filled:
                date_label = ''
                if 'Time' in df.columns:
                    date_label = str(pd.to_datetime(df.loc[i, 'Time']).date())
                levels.append(StratLevel(
                    name=f'Gap_Down_{date_label or i}',
                    price=float(prev_l),
                    timeframe='1d',
                    level_type='gap',
                ))

    return levels


# ---------------------------------------------------------------------------
# PMG (Pivot Machine Gun) — spatial + temporal
# ---------------------------------------------------------------------------


def detect_level_clusters(
    levels: Sequence[StratLevel],
    tolerance_pct: float = 0.15,
) -> List[dict]:
    """Spatial PMG: clusters of levels within ``tolerance_pct`` of each other.

    Returns a list of cluster dicts: ``{prices, names, mean_price, strength}``.
    Strength = number of levels in the cluster.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda l: l.price)
    clusters: List[dict] = []
    current = [sorted_levels[0]]

    for lev in sorted_levels[1:]:
        ref = current[-1].price
        threshold = ref * tolerance_pct / 100.0
        if (lev.price - ref) <= threshold:
            current.append(lev)
        else:
            if len(current) >= 2:
                clusters.append(_cluster_summary(current))
            current = [lev]

    if len(current) >= 2:
        clusters.append(_cluster_summary(current))

    return clusters


def _cluster_summary(group: List[StratLevel]) -> dict:
    prices = [l.price for l in group]
    return {
        'prices': prices,
        'names': [l.name for l in group],
        'mean_price': sum(prices) / len(prices),
        'strength': float(len(group)),
    }


def detect_pmg_temporal(
    daily_df: pd.DataFrame,
    n_consecutive: int = 3,
) -> dict:
    """Temporal PMG: N-consecutive higher-highs or lower-lows.

    Returns ``{higher_highs: bool, lower_lows: bool, count: int}`` based on
    the last ``n_consecutive`` bars in the frame.
    """
    if daily_df is None or len(daily_df) < n_consecutive + 1:
        return {'higher_highs': False, 'lower_lows': False, 'count': 0}

    tail = daily_df.tail(n_consecutive + 1)
    highs = tail['High'].to_list() if 'High' in tail.columns else []
    lows = tail['Low'].to_list() if 'Low' in tail.columns else []

    higher_highs = (
        len(highs) >= n_consecutive + 1
        and all(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    )
    lower_lows = (
        len(lows) >= n_consecutive + 1
        and all(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    )
    return {
        'higher_highs': bool(higher_highs),
        'lower_lows': bool(lower_lows),
        'count': int(n_consecutive) if (higher_highs or lower_lows) else 0,
    }


# ---------------------------------------------------------------------------
# Room-to-run + R:R + triggers
# ---------------------------------------------------------------------------


def compute_room_to_run(
    price: float,
    levels: Sequence[StratLevel],
    direction: str,
    min_room_pct: float = 0.30,
) -> dict:
    """Distance to the next level in trade direction.

    direction: 'long' (next level above) or 'short' (next level below).
    """
    if direction == 'long':
        candidates = [l for l in levels if l.price > price]
        if not candidates:
            return {'next_level': None, 'distance': 0.0, 'distance_pct': 0.0,
                    'has_min_room': False}
        target = min(candidates, key=lambda l: l.price)
    else:
        candidates = [l for l in levels if l.price < price]
        if not candidates:
            return {'next_level': None, 'distance': 0.0, 'distance_pct': 0.0,
                    'has_min_room': False}
        target = max(candidates, key=lambda l: l.price)

    distance = abs(target.price - price)
    distance_pct = (distance / price) * 100.0 if price else 0.0
    return {
        'next_level': target.as_dict(),
        'distance': distance,
        'distance_pct': distance_pct,
        'has_min_room': distance_pct >= min_room_pct,
    }


def compute_risk_reward(entry: float, stop: float, target: float) -> float:
    """Return R:R = reward / risk. Returns 0.0 if risk == 0."""
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return float(reward / risk) if risk > 0 else 0.0


def identify_triggers(
    price: float,
    levels: Sequence[StratLevel],
    daily_strat_class: str,
    combo: Optional[str],
) -> dict:
    """Wire combo + daily classification into a trigger description.

    Returns a dict with ``entry_long``, ``entry_short``, ``stop_long``,
    ``stop_short``, ``t1_long``, ``t2_long``, ``t1_short``, ``t2_short``,
    and ``reasoning`` (string referencing both combo and daily class).
    """
    above = sorted([l for l in levels if l.price > price], key=lambda l: l.price)
    below = sorted([l for l in levels if l.price < price], key=lambda l: l.price, reverse=True)

    def _opt(seq: List[StratLevel], i: int) -> Optional[dict]:
        return seq[i].as_dict() if len(seq) > i else None

    reasoning = (
        f"daily={daily_strat_class or 'X'} "
        f"combo={combo or 'none'} "
        f"price={price:.2f}"
    )

    return {
        'entry_long':  _opt(above, 0),
        't1_long':     _opt(above, 1),
        't2_long':     _opt(above, 2),
        'stop_long':   _opt(below, 0),
        'entry_short': _opt(below, 0),
        't1_short':    _opt(below, 1),
        't2_short':    _opt(below, 2),
        'stop_short':  _opt(above, 0),
        'reasoning':   reasoning,
    }


# ---------------------------------------------------------------------------
# Orchestrator + brief formatting + persistence
# ---------------------------------------------------------------------------


def build_level_map(
    ticker: str,
    daily_df: pd.DataFrame,
    current_price: float,
    as_of: Optional[datetime] = None,
    gap_lookback: int = 20,
    cluster_tolerance_pct: float = 0.15,
    pmg_window: int = 3,
) -> LevelMap:
    """Build the full LevelMap for a ticker."""
    if as_of is None:
        as_of = datetime.utcnow()

    levels: List[StratLevel] = []
    levels.extend(compute_previous_levels(daily_df))
    levels.extend(compute_current_levels(daily_df, current_price))
    levels.extend(compute_gap_levels(daily_df, lookback=gap_lookback,
                                       current_price=current_price))

    clusters = detect_level_clusters(levels, tolerance_pct=cluster_tolerance_pct)
    pmg_t = detect_pmg_temporal(daily_df, n_consecutive=pmg_window)

    return LevelMap(
        ticker=ticker,
        as_of=as_of,
        current_price=float(current_price),
        levels=levels,
        pmg_clusters=clusters,
        pmg_temporal=pmg_t,
    )


def format_levels_for_brief(
    level_map: LevelMap,
    bias: str,
    combo: Optional[str],
    daily_strat_class: Optional[str],
) -> str:
    """Render the playbook block for the premarket brief Discord embed.

    Format mirrors §7 of methodology doc:

        TICKER 215.42 — Daily 2U, Combo: 212_bull_reversal, FTFC bullish
        CALLS above 215.85 (PDH)
          Stop: 213.20 (PDL)
          T1: 217.10 (PWH) — 0.58% room (R:R 1.7)
          T2: 218.45 (PMH) — 1.40% room (R:R 4.1)
        PUTS below 213.20 (PDL) — only if bias denied
        PMG: 217.05 (PWH+PMH cluster, strength 2.5)
    """
    price = level_map.current_price
    triggers = identify_triggers(price, level_map.levels, daily_strat_class or '', combo)

    lines: List[str] = []
    header = (
        f"{level_map.ticker} {price:.2f} — Daily {daily_strat_class or 'X'}, "
        f"Combo: {combo or 'none'}, FTFC {bias}"
    )
    lines.append(header)

    long_entry = triggers['entry_long']
    long_stop = triggers['stop_long']
    long_t1 = triggers['t1_long']
    long_t2 = triggers['t2_long']
    short_entry = triggers['entry_short']

    if long_entry and long_stop:
        lines.append(f"CALLS above {long_entry['price']:.2f} ({long_entry['name']})")
        lines.append(f"  Stop: {long_stop['price']:.2f} ({long_stop['name']})")
        for label, level in [('T1', long_t1), ('T2', long_t2)]:
            if not level:
                continue
            distance_pct = (level['price'] - price) / price * 100.0
            rr = compute_risk_reward(long_entry['price'], long_stop['price'], level['price'])
            lines.append(
                f"  {label}: {level['price']:.2f} ({level['name']}) "
                f"— {distance_pct:.2f}% room (R:R {rr:.1f})"
            )

    if short_entry:
        lines.append(
            f"PUTS below {short_entry['price']:.2f} ({short_entry['name']}) "
            f"— only if bias denied"
        )

    for cluster in level_map.pmg_clusters:
        names = '+'.join(cluster['names'])
        lines.append(
            f"PMG: {cluster['mean_price']:.2f} "
            f"({names} cluster, strength {cluster['strength']:.1f})"
        )

    return '\n'.join(lines)


def persist_level_map(level_map: LevelMap, conn) -> int:
    """Persist a LevelMap into the strat_levels table.

    Returns the number of rows written. Caller manages transactions.
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
