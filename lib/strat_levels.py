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

from lib.eastern_time import ET_NAME, session_count
import pandas as pd
import numpy as np
import re
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
    # Next-N structural levels each way (nearest-first), each a dict with
    # price/name/period/level_type/distance_pct. `call_levels` are above the
    # current price, `put_levels` below; see SessionLevels.to_level_map().
    call_levels: list = field(default_factory=list)
    put_levels: list = field(default_factory=list)
    # Per-side regime and orb_only reason from build_session_levels.
    regime_long: str = 'normal'
    regime_short: str = 'normal'
    reason_long: Optional[str] = None
    reason_short: Optional[str] = None
    atr: Optional[float] = None
    # 'ok' or 'premarket_unavailable' from build_session_levels; the brief
    # prints PREMARKET_MISSING_NOTE when the snapshot was unavailable.
    premarket_status: Optional[str] = None


# ─── Per-leg intraday state (resolver-parity) ─────────────────────────────

# States a playbook leg moves through intraday, in escalation order.
# 'invalidated' outranks 'post_t1' at read time: once the stop has traded
# after the trigger, the leg is dead regardless of how many targets it
# tagged on the way.
LEG_STATES = ('no_setup', 'fresh', 'triggered', 'post_t1', 'post_t1_open',
              'invalidated')


@dataclass
class LegStateTracker:
    """Incremental intraday state for ONE playbook leg (calls or puts).

    Touch semantics deliberately mirror
    ``gcp.premarket_playbook_resolver.resolve_leg`` so the live tag and
    the nightly resolver can never disagree about what "triggered" or
    "stopped" means:

      * trigger — first bar whose high >= trigger (call) / low <= trigger
        (put). Until then T1/stop touches DO NOT count (a session that
        trades through the call-side stop without ever triggering the
        call leg leaves that leg 'fresh', exactly as the resolver's
        stop-scan starts at the trigger bar).
      * T1 / stop — first touch from the trigger bar INCLUSIVE onward,
        so a one-bar sweep through trigger+T1 (64.8%% of T1 hits in the
        Mar–Aug 2026 sample — audit §15) lands in 'post_t1' immediately.

    Feed bars in chronological order via ``update``; read ``state`` any
    time. The 2026-08-26 audit §15 validated the states as an outcome
    predictor: fires in 'post_t1'/'invalidated' lose (fwd30 t=-3.6,
    holdout t=-2.7) while 'fresh'/'triggered' fires win.
    """
    direction: str                  # 'call' | 'put'
    trigger: Optional[float] = None
    t1: Optional[float] = None
    stop: Optional[float] = None
    triggered: bool = False
    t1_hit: bool = False
    stop_hit: bool = False
    # True when the session's FIRST bar OPENED at or beyond the trigger and
    # also cleared T1 — a genuine gap-through, price never traded on the
    # near side of the level during RTH.
    #
    # The opening PRICE is what makes this a gap-through. An earlier draft
    # keyed only on the first bar's high/low reaching T1, which also
    # captured a call that opened BELOW the trigger and rallied through
    # both inside the 09:30 minute — intraday progression that merely
    # happened in minute one (Codex review, PR #803). `opening_price` is
    # therefore required; without it the flag stays False and the leg is
    # reported as plain 'post_t1' rather than guessed at.
    #
    # Audit §16.1 splits post_t1 into these two routes because they behave
    # differently, and 2026-08-27 was a live gap-and-go where the
    # gap-through fires won. Both remain suppressed under enforce — the
    # historical gap-through sample is significantly negative and outranks
    # one session. The flag exists to make the routes separable in shadow
    # data so the rule can be revisited per-route with evidence.
    opened_through: bool = False
    # Identity of the first bar seen, so a re-delivered snapshot of the
    # still-forming opening minute is still recognised as that same first
    # bar. A plain call counter got this wrong: the live monitor re-folds
    # the watermark bar every poll, so a 09:30 snapshot that crossed only
    # the trigger followed by a later 09:30 snapshot that reached T1 would
    # look like two bars and lose the gap-through tag, while a replay of
    # the completed bar kept it (Codex review, PR #803).
    _first_bar_key: object = None
    _seen_any_bar: bool = False

    def update(self, bar_high: float, bar_low: float,
               opening_price: Optional[float] = None,
               bar_key: object = None) -> None:
        """Fold one bar's high/low into the leg state (chronological).

        `opening_price` is that bar's open, required to recognise a
        gap-through. `bar_key` identifies the bar (its timestamp); passing
        it lets a re-delivered snapshot of the same minute be folded again
        without being mistaken for a new bar.
        """
        if self.trigger is None or self.trigger <= 0:
            return
        if bar_high != bar_high or bar_low != bar_low:  # NaN bar
            return
        is_call = (self.direction == 'call')
        if not self._seen_any_bar:
            self._seen_any_bar = True
            self._first_bar_key = bar_key
        # Without a key we cannot tell a re-delivered snapshot from a new
        # bar, so only the very first update can be the opening bar.
        first_bar = (bar_key is not None and bar_key == self._first_bar_key)
        if not self.triggered:
            crossed = (bar_high >= self.trigger) if is_call else (bar_low <= self.trigger)
            if not crossed:
                return
            self.triggered = True
        # From the trigger bar inclusive — same bar may sweep T1/stop.
        if not self.t1_hit and self.t1 is not None and self.t1 > 0:
            if (bar_high >= self.t1) if is_call else (bar_low <= self.t1):
                self.t1_hit = True
                # Gap-through: the opening bar's OPEN was already past the
                # trigger, and that same bar cleared T1.
                if first_bar and opening_price is not None:
                    gapped = ((opening_price >= self.trigger) if is_call
                              else (opening_price <= self.trigger))
                    if gapped:
                        self.opened_through = True
        if not self.stop_hit and self.stop is not None and self.stop > 0:
            if (bar_low <= self.stop) if is_call else (bar_high >= self.stop):
                self.stop_hit = True

    @property
    def state(self) -> str:
        if self.trigger is None or self.trigger <= 0:
            return 'no_setup'
        if self.stop_hit:
            return 'invalidated'
        if self.t1_hit:
            return 'post_t1_open' if self.opened_through else 'post_t1'
        if self.triggered:
            return 'triggered'
        return 'fresh'


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


def _compute_previous_levels(
    daily_df: pd.DataFrame,
    analysis_date: date_type,
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

            Required. There is no iloc[-2] fallback: the previous
            period always comes from the period filter (FEAT-STRAT-001).
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

        # Pick the previous-period row by period filter only: the period
        # immediately before the one containing analysis_date. There is no
        # iloc[-2] fallback (FEAT-STRAT-001 done_when 3).
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


def _compute_current_levels(
    daily_df: pd.DataFrame,
    current_price: float,
    analysis_date: Optional[date_type] = None,
) -> Dict[str, StratLevel]:
    """Compute the latest available day/week/month open levels.

    These levels REPAINT as price evolves intraday.

    Label semantics — CDO / PDO disambiguation
    ──────────────────────────────────────────
    Pre-2026-05-11 this function always labelled the latest open as
    ``CDO`` ("Current Day Open"). That was correct only when the
    caller passed a df whose last row was actually *today*'s session
    — i.e. mid-session or post-close with today's RTH open populated.

    The 8:30 AM ET premarket brief filters its df to
    ``date < analysis_date`` (so today's NULL-OHLC row doesn't poison
    the level builder). After that filter, ``df.iloc[-1]`` is the
    PREVIOUS trading day. Labelling that open "CDO" silently leaks
    the implication "this is today's open" — but today hasn't opened
    yet. Across replays (5/6: CDO = 5/5 open; 5/11: CDO = 5/8 open)
    this was consistently the previous session's open.

    Fix: when ``analysis_date`` is passed, compare the last row's date
    against it:
      - same day → emit ``CDO`` (label is honest)
      - earlier  → emit ``PDO`` (Previous Day Open)
    Same logic for week (CWO ↔ PWO) and month (CMO ↔ PMO).

    When ``analysis_date`` is None (legacy / live mid-session use),
    keep the historical ``CDO``/``CWO``/``CMO`` labels — no semantic
    shift for those callers.
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

    # Convert analysis_date once for period comparisons.
    if analysis_date is not None:
        ad_ts = pd.Timestamp(analysis_date)
        if ad_ts.tz is not None:
            ad_ts = ad_ts.tz_convert('UTC').tz_localize(None)
        ad_date = ad_ts.normalize().date()
        ad_week_period = pd.Period(ad_ts, freq='W')
        ad_month_period = pd.Period(ad_ts, freq='M')
    else:
        ad_date = None
        ad_week_period = None
        ad_month_period = None

    # Day-level open
    if len(df) >= 2:
        prev_day = df.iloc[-2]
        today = df.iloc[-1]
        today_open = (float(today['_open'])
                      if pd.notna(today['_open']) else current_price)
        # Is `today` actually today, or yesterday (df was filtered)?
        today_row_date = pd.Timestamp(today['_date']).normalize().date()
        is_actually_today = (ad_date is None or today_row_date == ad_date)

        if is_actually_today:
            # Live mid-session / EOD context: fold current_price into
            # today's repainting H/L so the strat class evolves with
            # the tape.
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
            day_name = 'CDO'
            day_is_current = True
        else:
            # Premarket replay context: `today` is yesterday's COMPLETED
            # session. Codex P2 review on PR #445 — folding
            # current_price into yesterday's H/L would let today's
            # premarket gap repaint a closed session's strat class.
            # Use yesterday's actual close instead.
            yday_high = float(today['_high']) if pd.notna(today['_high']) else today_open
            yday_low  = float(today['_low'])  if pd.notna(today['_low'])  else today_open
            yday_close = float(today['_close']) if pd.notna(today['_close']) else today_open
            strat = classify_level_strat(
                yday_high, yday_low, yday_close, today_open,
                float(prev_day['_high']), float(prev_day['_low']),
            )
            day_name = 'PDO'
            day_is_current = False
        levels[day_name] = StratLevel(
            name=day_name, price=today_open,
            timeframe='day', level_type='open',
            strat_class=strat, is_current=day_is_current,
            period_label=str(today_row_date),
        )

    # Week-level open
    df['_week'] = df['_date'].dt.to_period('W')
    current_week = df['_week'].iloc[-1]
    this_week = df[df['_week'] == current_week]
    prev_weeks = df[df['_week'] < current_week]

    if not this_week.empty and not prev_weeks.empty:
        cw_open = float(this_week.iloc[0]['_open'])

        last_wk_period = prev_weeks['_week'].iloc[-1]
        last_wk = prev_weeks[prev_weeks['_week'] == last_wk_period]
        pw_high = float(last_wk['_high'].max())
        pw_low = float(last_wk['_low'].min())

        is_current_week = (ad_week_period is None or current_week == ad_week_period)
        if is_current_week:
            # In-progress week — fold today's tape into the repainting H/L.
            cw_high = max(float(this_week['_high'].max()), current_price)
            cw_low = min(float(this_week['_low'].min()), current_price)
            strat = classify_level_strat(cw_high, cw_low, current_price, cw_open, pw_high, pw_low)
            wk_name = 'CWO'
            wk_is_current = True
        else:
            # Completed previous week — strat class from the week's own
            # close, not today's price (Codex P2 review on PR #445).
            cw_high = float(this_week['_high'].max())
            cw_low  = float(this_week['_low'].min())
            cw_close = float(this_week.iloc[-1]['_close'])
            strat = classify_level_strat(cw_high, cw_low, cw_close, cw_open, pw_high, pw_low)
            wk_name = 'PWO'
            wk_is_current = False
        levels[wk_name] = StratLevel(
            name=wk_name, price=cw_open,
            timeframe='week', level_type='open',
            strat_class=strat, is_current=wk_is_current,
            period_label=str(current_week),
        )

    # Month-level open
    df['_month'] = df['_date'].dt.to_period('M')
    current_month = df['_month'].iloc[-1]
    this_month = df[df['_month'] == current_month]
    prev_months = df[df['_month'] < current_month]

    if not this_month.empty and not prev_months.empty:
        cm_open = float(this_month.iloc[0]['_open'])

        last_m = prev_months[prev_months['_month'] == prev_months['_month'].iloc[-1]]
        pm_high = float(last_m['_high'].max())
        pm_low = float(last_m['_low'].min())

        is_current_month = (ad_month_period is None or current_month == ad_month_period)
        if is_current_month:
            cm_high = max(float(this_month['_high'].max()), current_price)
            cm_low = min(float(this_month['_low'].min()), current_price)
            strat = classify_level_strat(cm_high, cm_low, current_price, cm_open, pm_high, pm_low)
            mo_name = 'CMO'
            mo_is_current = True
        else:
            # Completed previous month — fixed strat class from month's
            # own close (Codex P2 review on PR #445).
            cm_high = float(this_month['_high'].max())
            cm_low  = float(this_month['_low'].min())
            cm_close = float(this_month.iloc[-1]['_close'])
            strat = classify_level_strat(cm_high, cm_low, cm_close, cm_open, pm_high, pm_low)
            mo_name = 'PMO'
            mo_is_current = False
        levels[mo_name] = StratLevel(
            name=mo_name, price=cm_open,
            timeframe='month', level_type='open',
            strat_class=strat, is_current=mo_is_current,
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
# Defaults: 3.0 ATR and 8%, the one window every consumer reads through
# build_session_levels (FEAT-STRAT-001); 8% is the empirical "too far for an
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


# ─── Distance window and the cents rule ───────────────────────────────────


def _within_staleness_window(
    level_price: float, current_price: float, atr: Optional[float],
) -> bool:
    """The one distance rule (FEAT-STRAT-001): a level is close enough to be a
    trigger, a stop, a target, a ladder rung or the Room to trigger line when
    its distance from the reference fits BOTH budgets, 3 x this ticker's own
    ATR(14) and 8% of the reference.

    There is no percent-only fallback: without a positive ATR nothing is in
    the window, and build_session_levels reports reason atr_unavailable.
    """
    if atr is None or not _finite_positive(atr):
        return False
    if current_price is None or not _finite_positive(current_price):
        return False
    distance = abs(float(level_price) - float(current_price))
    return (distance <= MAX_TRIGGER_DISTANCE_PCT * float(current_price)
            and distance <= MAX_TRIGGER_DISTANCE_ATR * float(atr))


def _finite_positive(x) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return v == v and v not in (float('inf'), float('-inf')) and v > 0


def price_cents(x) -> int:
    """A price as integer cents, under ONE rounding rule shared by everything
    that decides whether two lines are "the same price": the side lists, the
    broken rule, target de-duplication, the movement-statement slot match, and
    the reach-rate SQL's `round(price::numeric, 2)`.

    Decimal on the float's shortest repr, half-up, because three other rules
    disagree on real data (Codex P2 on #1030): for 292.705, Python
    `round(x, 2)` gives 292.70 (binary 292.705 is a hair below),
    `int(round(x * 100))` gives 29270, and Postgres `round(::numeric, 2)`
    gives 292.71. This helper gives 29271, matching Postgres, so a level
    persisted raw in `premarket_analysis` and the same level rendered on the
    ladder land on the same cent.
    """
    from decimal import Decimal, ROUND_HALF_UP  # noqa: PLC0415

    return int(Decimal(str(float(x))).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)


# ─── One level builder (FEAT-STRAT-001) ───────────────────────────────────
#
# build_session_levels is the only code that turns daily bars, ATR(14) and a
# premarket snapshot into levels, side lists, triggers, stops, targets and the
# ladder. The brief, the planner, the signal monitor, the playbook resolver and
# the movement statement all read a SessionLevels (or its level_basis JSON).

LEVEL_RULE_VERSION = 'feat-strat-001.v1'

# Trigger candidates in tie-break priority: at one price to the cent the
# earlier name wins, so a structural level beats the parent bar and both beat
# a premarket extreme on the same cent.
PRIOR_PERIOD_CANDIDATES = (
    'PDH', 'PDL', 'PDC', 'PWH', 'PWL', 'PWC', 'PMH', 'PML', 'PMC',
    'PQH', 'PQL', 'PQC', 'PYH', 'PYL', 'PYC',
)
PARENT_BAR_HIGH = 'parent_bar_high'
PARENT_BAR_LOW = 'parent_bar_low'
PREMARKET_HIGH = 'PMK_H'
PREMARKET_LOW = 'PMK_L'
_CANDIDATE_ORDER = PRIOR_PERIOD_CANDIDATES + (
    PARENT_BAR_HIGH, PARENT_BAR_LOW, PREMARKET_HIGH, PREMARKET_LOW,
)
_CANDIDATE_PRIORITY = {name: i for i, name in enumerate(_CANDIDATE_ORDER)}

# Inside-bar walks stop after this many bars, as the planner's walk did.
_PARENT_BAR_LOOKBACK = 10

ORB_ONLY_REASONS = (
    'all_broken_by_premarket', 'next_level_outside_window', 'no_levels',
    'atr_unavailable', 'stale_daily',
)

# The one copy table for an orb_only side, rendered by the brief banners, the
# planner rationale, the Discord push and the schema descriptions.
ORB_ONLY_COPY = {
    'all_broken_by_premarket': (
        "Pre-market traded through every {side} level within reach. "
        "Wait for the 15-min opening range."
    ),
    'next_level_outside_window': (
        "No unbroken {side} level within 3x ATR and 8% of price. "
        "Wait for the 15-min opening range."
    ),
    'no_levels': (
        "No {side} level in the level history. "
        "Wait for the 15-min opening range."
    ),
    'atr_unavailable': (
        "ATR(14) is unavailable, so no {side} level can be checked against "
        "the 3x ATR window. Wait for the 15-min opening range."
    ),
    'stale_daily': (
        "The prior session's daily bar is missing, so no {side} level is "
        "published. Wait for the 15-min opening range."
    ),
}

# Owner ruling 2026-11-08: a brief built without the session's premarket
# snapshot points the reader to Insights, whose refresh reads it later.
PREMARKET_MISSING_NOTE = (
    "Premarket levels were not available when this brief ran. "
    "Refer to Insights for premarket levels."
)

ORB_ONLY_SCHEMA_DESCRIPTION = (
    "'orb_only' = no trigger on this side; the reason is one of "
    + ", ".join(ORB_ONLY_REASONS)
    + " (lib.strat_levels.ORB_ONLY_COPY). Wait for the 15-min opening range."
)


def orb_only_text(reason: Optional[str], side: str) -> str:
    """The orb_only copy for one side. `side` is long/short or call/put."""
    word = {'long': 'call', 'short': 'put', 'calls': 'call', 'puts': 'put',
            'CALLS': 'call', 'PUTS': 'put'}.get(side, side)
    template = ORB_ONLY_COPY.get(reason or 'no_levels', ORB_ONLY_COPY['no_levels'])
    return template.format(side=word)


@dataclass
class SideLevels:
    """One side (long = calls, short = puts) of a session's levels."""
    side: str
    candidates: list = field(default_factory=list)
    trigger: Optional[dict] = None
    regime: str = 'orb_only'
    reason: Optional[str] = 'no_levels'
    targets: list = field(default_factory=list)
    stop: Optional[dict] = None
    ladder: list = field(default_factory=list)
    room_pct: Optional[float] = None
    distance_atr: Optional[float] = None

    @property
    def rungs(self) -> list:
        """The ordered side list: unbroken, in-window, distinct by cent."""
        return [c for c in self.candidates if not c['broken'] and c['in_window']]

    def to_dict(self) -> dict:
        return {
            'side': self.side, 'candidates': self.candidates,
            'trigger': self.trigger, 'regime': self.regime,
            'reason': self.reason, 'targets': self.targets, 'stop': self.stop,
            'ladder': self.ladder, 'room_pct': self.room_pct,
            'distance_atr': self.distance_atr,
        }


@dataclass
class SessionLevels:
    """Every level decision for one ticker and session (FEAT-STRAT-001)."""
    ticker: str
    session_date: date_type
    status: str = 'ok'                       # ok | stale_daily | no_data
    rule_version: str = LEVEL_RULE_VERSION
    built_at: str = ''
    last_bar_date: Optional[date_type] = None
    atr: Optional[float] = None
    prior_close: Optional[float] = None
    reference: Optional[float] = None
    reference_source: str = 'prior_close'    # pre_vwap | prior_close | caller
    premarket: Optional[dict] = None
    premarket_status: str = 'premarket_unavailable'
    cleared_above: Optional[float] = None
    cleared_below: Optional[float] = None
    levels: List[StratLevel] = field(default_factory=list)
    pmg_zones: list = field(default_factory=list)
    strat_class: str = ''
    long: SideLevels = field(default_factory=lambda: SideLevels('long'))
    short: SideLevels = field(default_factory=lambda: SideLevels('short'))

    def side(self, direction: str) -> SideLevels:
        return self.long if direction in ('long', 'calls', 'call') else self.short

    def level_named(self, name: str) -> Optional[StratLevel]:
        return next((lv for lv in self.levels if lv.name == name), None)

    # ── derived builds ──────────────────────────────────────────────
    def with_premarket(self, premarket) -> 'SessionLevels':
        """Apply a newer premarket snapshot: it replaces the premarket high
        and low candidates and the reference, keeps every structural level,
        and recomputes broken status and picks. A snapshot dated another
        session is refused and recorded as premarket_unavailable."""
        snap = _accept_premarket(premarket, self.session_date)
        if snap is None:
            return self
        return _assemble(self, premarket=snap, reference=None,
                         reference_source=None)

    def with_reference(self, reference: float) -> 'SessionLevels':
        """The same levels against a caller's reference (the signal
        monitor's put re-anchor passes the session open)."""
        return _assemble(self, premarket=self.premarket, reference=reference,
                         reference_source='caller')

    # ── projections ─────────────────────────────────────────────────
    def to_level_map(self, include_premarket: bool = True) -> LevelMap:
        """The LevelMap shape persist_level_map, the strat_levels writes and
        format_levels_for_brief consume. Parent-bar levels are candidates
        only and are not persisted as strat_levels rows."""
        persisted = [
            lv for lv in self.levels
            if lv.name not in (PARENT_BAR_HIGH, PARENT_BAR_LOW)
            and (include_premarket or lv.name not in (PREMARKET_HIGH, PREMARKET_LOW))
        ]
        return LevelMap(
            ticker=self.ticker,
            as_of=self.built_at or pd.Timestamp.now(ET_NAME).isoformat(),
            current_price=float(self.reference) if self.reference is not None else float('nan'),
            levels=sorted(persisted, key=lambda lv: lv.price),
            pmg_zones=list(self.pmg_zones),
            calls_trigger=_legacy_trigger_dict(self.long),
            puts_trigger=_legacy_trigger_dict(self.short),
            room_to_run_up=self.long.room_pct,
            room_to_run_down=self.short.room_pct,
            call_levels=list(self.long.ladder),
            put_levels=list(self.short.ladder),
            regime_long=self.long.regime,
            regime_short=self.short.regime,
            reason_long=self.long.reason,
            reason_short=self.short.reason,
            atr=self.atr,
            premarket_status=self.premarket_status,
        )

    def published_prices(self) -> set:
        """Cents of every level the builder knows; any published price must
        be one of these or an offset from one."""
        return {price_cents(lv.price) for lv in self.levels}

    def to_basis(self) -> dict:
        """The level_basis JSON written with a brief row and carried on an
        insight report."""
        def _lv(lv: StratLevel) -> dict:
            return {'name': lv.name, 'price': float(lv.price),
                    'timeframe': lv.timeframe, 'level_type': lv.level_type,
                    'period_label': lv.period_label,
                    'strat_class': lv.strat_class, 'is_current': bool(lv.is_current)}
        return {
            'rule_version': self.rule_version,
            'ticker': self.ticker,
            'session_date': self.session_date.isoformat(),
            'built_at': self.built_at,
            'status': self.status,
            'last_bar_date': self.last_bar_date.isoformat() if self.last_bar_date else None,
            'atr': self.atr,
            'prior_close': self.prior_close,
            'reference': self.reference,
            'reference_source': self.reference_source,
            'premarket': dict(self.premarket) if self.premarket else None,
            'premarket_status': self.premarket_status,
            'cleared_above': self.cleared_above,
            'cleared_below': self.cleared_below,
            'strat_class': self.strat_class,
            'levels': [_lv(lv) for lv in self.levels],
            'pmg_zones': list(self.pmg_zones),
            'long': self.long.to_dict(),
            'short': self.short.to_dict(),
        }

    @classmethod
    def from_basis(cls, basis: dict) -> 'SessionLevels':
        """Rebuild from a stored level_basis. The levels, ATR, prior close
        and premarket snapshot are the inputs; the picks are recomputed under
        the current rule so a reader never trusts a stale pick."""
        if not isinstance(basis, dict):
            raise ValueError('level_basis must be a JSON object')
        session = _to_date(basis.get('session_date'))
        if session is None:
            raise ValueError('level_basis has no session_date')
        base = cls(
            ticker=str(basis.get('ticker') or ''),
            session_date=session,
            status=basis.get('status') or 'ok',
            built_at=basis.get('built_at') or '',
            last_bar_date=_to_date(basis.get('last_bar_date')),
            atr=basis.get('atr'),
            prior_close=basis.get('prior_close'),
            strat_class=basis.get('strat_class') or '',
            levels=[StratLevel(
                name=d['name'], price=float(d['price']),
                timeframe=d.get('timeframe', ''), level_type=d.get('level_type', 'pivot'),
                strat_class=d.get('strat_class', ''), is_current=bool(d.get('is_current')),
                period_label=d.get('period_label', ''),
            ) for d in (basis.get('levels') or [])],
            pmg_zones=list(basis.get('pmg_zones') or []),
        )
        if base.status != 'ok':
            return _assemble(base, premarket=None, reference=None, reference_source=None)
        snap = _accept_premarket(basis.get('premarket'), session)
        ref = basis.get('reference') if basis.get('reference_source') == 'caller' else None
        return _assemble(base, premarket=snap, reference=ref,
                         reference_source='caller' if ref is not None else None)


def _to_date(v) -> Optional[date_type]:
    """A date from a date, datetime, Timestamp or ISO string; None otherwise."""
    from datetime import datetime as _dt  # noqa: PLC0415
    if v is None:
        return None
    if isinstance(v, _dt):
        return v.date()
    if isinstance(v, date_type):
        return v
    try:
        ts = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(ts):
        return None
    return ts.date()


def _premarket_value(snap, key):
    if snap is None:
        return None
    v = snap.get(key) if isinstance(snap, dict) else getattr(snap, key, None)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 0 else None


def _premarket_count(v) -> Optional[int]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == f and f >= 0 else None


# The premarket provenance columns on market_data_daily (FEAT-STRAT-001):
# when the snapshot was fetched and how many prints the filter dropped. Every
# reader tolerates their absence (the schema change waits on the owner).
PREMARKET_PROVENANCE_COLUMNS = {
    'pre_fetched_at': 'fetched_at',
    'pre_excluded_stale_prints': 'excluded_stale_prints',
    'pre_excluded_spikes': 'excluded_spikes',
}


SESSION_PREMARKET_SQL = (
    "SELECT date, pre_high, pre_low, pre_vwap, gap_pct{provenance} "
    "FROM market_data_daily WHERE ticker = :ticker AND date = :d LIMIT 1"
)


_MISSING_SCHEMA_MARKERS = (
    '42703', '42p01',                      # PostgreSQL undefined_column / undefined_table
    'undefinedcolumn', 'undefinedtable',
    'no such column', 'no such table',     # SQLite
)


def _is_missing_schema_error(exc: BaseException) -> bool:
    """True when `exc` says a column or table does not exist (the schema
    change not applied yet), and only then. A timeout, a lost connection or
    any other failure is not a missing schema."""
    text_ = f"{type(exc).__name__} {exc}".lower()
    if any(m in text_ for m in _MISSING_SCHEMA_MARKERS):
        return True
    return 'does not exist' in text_ and ('column' in text_ or 'relation' in text_)


def read_session_premarket(query_fn, ticker: str, session_date) -> Optional[dict]:
    """The session's own premarket snapshot from its market_data_daily row,
    with the provenance columns when the table has them. `query_fn(sql,
    params)` returns a DataFrame. A missing-column error (the schema change
    not applied yet) or an empty result retries the read without the
    provenance columns; any other raised failure propagates, so a failed
    read is never taken for a session with no premarket."""
    params = {'ticker': str(ticker).upper(), 'd': str(_to_date(session_date))}
    extended = SESSION_PREMARKET_SQL.format(
        provenance=''.join(f', {c}' for c in PREMARKET_PROVENANCE_COLUMNS))
    try:
        df = query_fn(extended, params)
    except Exception as exc:  # re-raised unless a missing column
        if not _is_missing_schema_error(exc):
            raise
        df = None
    if df is None or getattr(df, 'empty', True):
        # A missing provenance column, or a query_fn that already turns its
        # SQL errors into an empty frame: read the snapshot without them.
        df = query_fn(SESSION_PREMARKET_SQL.format(provenance=''), params)
    if df is None or getattr(df, 'empty', True):
        return None
    return premarket_snapshot_from_row(df.iloc[0], session_date)


def premarket_snapshot_from_row(row, session_date) -> Optional[dict]:
    """A premarket snapshot dated `session_date` from one market_data_daily
    row (a dict or Series with pre_high, pre_low, pre_vwap, gap_pct and, when
    present, the provenance columns), or None when it holds no premarket."""
    if row is None:
        return None
    get = row.get if hasattr(row, 'get') else (lambda k, d=None: getattr(row, k, d))
    snap = {'date': _to_date(session_date).isoformat()}
    for col in ('pre_high', 'pre_low', 'pre_vwap', 'gap_pct'):
        v = get(col, None)
        try:
            snap[col] = float(v) if v is not None and pd.notna(v) else None
        except (TypeError, ValueError):
            snap[col] = None
    for col, key in PREMARKET_PROVENANCE_COLUMNS.items():
        v = get(col, None)
        try:
            snap[key] = None if v is None or pd.isna(v) else v
        except (TypeError, ValueError):
            snap[key] = v
    if snap['pre_high'] is None and snap['pre_low'] is None and snap['pre_vwap'] is None:
        return None
    return snap


def _accept_premarket(premarket, session_date: date_type) -> Optional[dict]:
    """The session's own premarket snapshot as a plain dict, or None. A
    snapshot with no date, or dated any other day, is refused."""
    if premarket is None:
        return None
    get = premarket.get if isinstance(premarket, dict) else (lambda k, d=None: getattr(premarket, k, d))
    snap_date = _to_date(get('date'))
    if snap_date is None or snap_date != session_date:
        return None
    fetched = get('fetched_at')
    if fetched is not None:
        try:
            ts = pd.Timestamp(fetched)
            fetched = None if pd.isna(ts) else (
                ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')).isoformat()
        except (TypeError, ValueError):
            fetched = None
    stale = _premarket_count(get('excluded_stale_prints'))
    spikes = _premarket_count(get('excluded_spikes'))
    out = {
        'date': snap_date.isoformat(),
        'fetched_at': fetched,
        'pre_high': _premarket_value(premarket, 'pre_high'),
        'pre_low': _premarket_value(premarket, 'pre_low'),
        'pre_vwap': _premarket_value(premarket, 'pre_vwap'),
        'gap_pct': None,
        # Prints the premarket filter dropped (lib.indicators
        # calculate_premarket_context): stale prior-close prints and
        # isolated spikes. None when the writer did not record them.
        'excluded_stale_prints': stale,
        'excluded_spikes': spikes,
        'excluded_bars': (None if stale is None and spikes is None
                          else (stale or 0) + (spikes or 0)),
    }
    gp = get('gap_pct')
    try:
        out['gap_pct'] = float(gp) if gp is not None and float(gp) == float(gp) else None
    except (TypeError, ValueError):
        out['gap_pct'] = None
    if out['pre_high'] is None and out['pre_low'] is None and out['pre_vwap'] is None:
        return None
    return out


def _normalize_daily(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Daily bars on a naive DatetimeIndex with Open/High/Low/Close columns."""
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close'])
    df = daily_df.copy()
    for c in ('date', 'Date', 'Time', 'timestamp'):
        if c in df.columns:
            df.index = pd.to_datetime(df[c])
            break
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)  # tz-ok: daily bars are session-date labels; the wall date is kept
    rename = {}
    for c in df.columns:
        cl = str(c).lower()
        if cl in ('open', 'high', 'low') and c not in ('Open', 'High', 'Low'):
            rename[c] = cl.capitalize()
        elif cl in ('close', 'last') and 'Close' not in df.columns and c != 'Close':
            rename[c] = 'Close'
    df = df.rename(columns=rename)
    for c in ('Open', 'High', 'Low', 'Close'):
        if c not in df.columns:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close'])
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.sort_index()


def find_parent_bar(daily_df: pd.DataFrame) -> Optional[Tuple[float, float, str]]:
    """The parent bar of the last completed bar in `daily_df`.

    `daily_df` must already end at the prior session (build_session_levels
    bounds it). When that bar is not an inside bar it is its own parent; when
    it is, walk back through the run of inside bars to the bar that contains
    them. Returns (high, low, date label) or None.
    """
    df = _normalize_daily(daily_df)
    n = len(df)
    if n == 0:
        return None
    highs = df['High'].to_numpy(dtype=float)
    lows = df['Low'].to_numpy(dtype=float)
    i = n - 1
    walked = 0
    while (i >= 1 and walked < _PARENT_BAR_LOOKBACK
           and StratClassifier.classify_candle(highs[i], lows[i], highs[i - 1], lows[i - 1]) == '1'):
        i -= 1
        walked += 1
    if highs[i] != highs[i] or lows[i] != lows[i]:
        return None
    return float(highs[i]), float(lows[i]), str(df.index[i].date())


def build_session_levels(
    ticker: str,
    session_date: date_type,
    daily_df: pd.DataFrame,
    atr: Optional[float],
    premarket=None,
    reference: Optional[float] = None,
    *,
    daily_strat_class: str = '',
) -> SessionLevels:
    """Build every level decision for `ticker` on `session_date`.

    * Daily bars are bounded to dates before session_date, null-close rows
      dropped, and freshness checked with daily_data_freshness: a frame whose
      last bar is not the prior session gives status stale_daily, no levels.
    * Previous periods come from the period filter only, never iloc[-2].
    * The parent bar is found from the last completed bar.
    * `premarket` (a dict or object with date, pre_high, pre_low, pre_vwap,
      gap_pct, fetched_at, excluded_stale_prints, excluded_spikes) is used
      only when its own date is session_date; otherwise
      premarket_unavailable is recorded.
    * The reference is the snapshot's pre_vwap, else the prior close, unless
      the caller passes `reference`.
    * `atr` is the last completed session's ATR(14). Missing or not positive
      gives no trigger on either side, reason atr_unavailable.
    """
    session_date = _to_date(session_date)
    atr_v = float(atr) if _finite_positive(atr) else None
    base = SessionLevels(ticker=ticker, session_date=session_date, atr=atr_v,
                         built_at=pd.Timestamp.now(ET_NAME).isoformat(),
                         strat_class=daily_strat_class or '')
    df = _normalize_daily(daily_df)
    if len(df):
        df = df[df.index.normalize() < pd.Timestamp(session_date)]
        df = df[df['Close'].notna() & df['High'].notna() & df['Low'].notna()]
    if len(df) < 2:
        base.status = 'no_data'
        return _assemble(base, premarket=None, reference=None, reference_source=None)
    last_bar = df.index[-1].date()
    base.last_bar_date = last_bar
    is_stale, _gap, _status = daily_data_freshness(last_bar, session_date)
    if is_stale:
        base.status = 'stale_daily'
        return _assemble(base, premarket=None, reference=None, reference_source=None)
    base.prior_close = float(df['Close'].iloc[-1])

    snap = _accept_premarket(premarket, session_date)
    anchor = (float(reference) if reference is not None
              else (snap['pre_vwap'] if snap and snap.get('pre_vwap') else base.prior_close))

    prev_levels = _compute_previous_levels(df, analysis_date=session_date)
    curr_levels = _compute_current_levels(df, anchor, analysis_date=session_date)
    gap_levels = compute_gap_levels(df.assign(Time=df.index), lookback=20)
    base.pmg_zones = detect_level_clusters(
        list(prev_levels.values()) + list(curr_levels.values()) + gap_levels,
        tolerance_pct=0.15,
    )
    levels = list(prev_levels.values()) + list(curr_levels.values()) + gap_levels
    parent = find_parent_bar(df)
    if parent is not None:
        ph, pl, plabel = parent
        levels.append(StratLevel(name=PARENT_BAR_HIGH, price=ph, timeframe='day',
                                 level_type='high', period_label=plabel))
        levels.append(StratLevel(name=PARENT_BAR_LOW, price=pl, timeframe='day',
                                 level_type='low', period_label=plabel))
    base.levels = levels
    return _assemble(base, premarket=snap, reference=reference,
                     reference_source='caller' if reference is not None else None)


def _assemble(base: SessionLevels, *, premarket: Optional[dict],
              reference: Optional[float], reference_source: Optional[str]) -> SessionLevels:
    """Recompute reference, cleared marks, broken status and picks from a
    SessionLevels' structural levels plus a premarket snapshot."""
    out = SessionLevels(
        ticker=base.ticker, session_date=base.session_date, status=base.status,
        rule_version=LEVEL_RULE_VERSION, built_at=base.built_at,
        last_bar_date=base.last_bar_date, atr=base.atr,
        prior_close=base.prior_close, strat_class=base.strat_class,
        pmg_zones=list(base.pmg_zones),
    )
    structural = [lv for lv in base.levels
                  if lv.name not in (PREMARKET_HIGH, PREMARKET_LOW)]
    if base.status != 'ok':
        out.levels = []
        out.long = SideLevels('long', reason=base.status if base.status == 'stale_daily' else 'no_levels')
        out.short = SideLevels('short', reason=out.long.reason)
        return out

    out.premarket = premarket
    out.premarket_status = 'ok' if premarket else 'premarket_unavailable'
    pre_high = premarket.get('pre_high') if premarket else None
    pre_low = premarket.get('pre_low') if premarket else None
    if reference is not None:
        out.reference = float(reference)
        out.reference_source = 'caller'
    elif premarket and premarket.get('pre_vwap'):
        out.reference = float(premarket['pre_vwap'])
        out.reference_source = 'pre_vwap'
    else:
        out.reference = float(base.prior_close) if base.prior_close is not None else None
        out.reference_source = 'prior_close'

    pm_levels = compute_premarket_levels(pre_high, pre_low)
    out.levels = structural + list(pm_levels.values())

    ref = out.reference
    if ref is None:
        out.long = SideLevels('long', reason='no_levels')
        out.short = SideLevels('short', reason='no_levels')
        return out
    out.cleared_above = max(ref, pre_high) if pre_high is not None else ref
    out.cleared_below = min(ref, pre_low) if pre_low is not None else ref
    candidates = _candidate_rungs(out.levels)
    if not premarket:
        # Spec revision 2: with no premarket snapshot nothing has traded
        # yet, so a candidate on the reference's own cent (PDC itself when
        # the reference is the prior close, or any level sharing that cent)
        # is on neither side list and the trigger is the next real level
        # out. With a snapshot such a level stays on both lists.
        ref_cents = price_cents(ref)
        candidates = [c for c in candidates if c['cents'] != ref_cents]
    out.long = _pick_side('long', candidates, ref, out.cleared_above, out.atr)
    out.short = _pick_side('short', candidates, ref, out.cleared_below, out.atr)
    return out


def _candidate_rungs(levels: List[StratLevel]) -> list:
    """The one candidate set, distinct by cent: prior-period highs, lows and
    closes, the parent bar's high and low, and the premarket high and low.
    At one cent the higher-priority name wins and the others are aliases."""
    by_cent: Dict[int, dict] = {}
    for lv in sorted((lv for lv in levels if lv.name in _CANDIDATE_PRIORITY),
                     key=lambda lv: _CANDIDATE_PRIORITY[lv.name]):
        c = price_cents(lv.price)
        if c in by_cent:
            by_cent[c]['aliases'].append(lv.name)
            continue
        by_cent[c] = {
            'name': lv.name, 'price': float(lv.price), 'cents': c,
            'level_type': lv.level_type, 'timeframe': lv.timeframe,
            'period': lv.period_label, 'aliases': [],
        }
    return sorted(by_cent.values(), key=lambda d: d['cents'])


def _rung(c: dict, ref: float) -> dict:
    return {
        'name': c['name'], 'price': c['price'], 'level_type': c['level_type'],
        'timeframe': c['timeframe'], 'period': c['period'],
        'aliases': list(c['aliases']),
    }


def _ladder_entry(c: dict, ref: float) -> dict:
    p = c['cents'] / 100.0
    return {
        'price': p, 'name': c['name'], 'period': c['timeframe'],
        'level_type': c['level_type'],
        'distance_pct': round((p - ref) / ref * 100, 2),
    }


def _pick_side(side: str, candidates: list, ref: float, cleared: float,
               atr: Optional[float]) -> SideLevels:
    """One side rule, one broken rule, one window.

    A candidate is on the long list when its cent is at or above the
    cleared-above mark, max(reference, premarket high), and on the short list
    when at or below the cleared-below mark, whatever kind of level it is.
    A candidate between the reference and the mark was traded through by
    premarket: it is listed as broken and is never a pick.
    """
    ref_c = price_cents(ref)
    mark_c = price_cents(cleared)
    if side == 'long':
        on_side = [c for c in candidates if c['cents'] >= ref_c]
        broken = lambda c: c['cents'] < mark_c  # noqa: E731
        other = sorted((c for c in candidates if c['cents'] < ref_c), key=lambda c: -c['cents'])
    else:
        on_side = sorted((c for c in candidates if c['cents'] <= ref_c), key=lambda c: -c['cents'])
        broken = lambda c: c['cents'] > mark_c  # noqa: E731
        other = [c for c in candidates if c['cents'] > ref_c]
    listed = []
    for c in on_side:
        listed.append({**_rung(c, ref), 'cents': c['cents'], 'broken': broken(c),
                       'in_window': _within_staleness_window(c['price'], ref, atr),
                       'distance_atr': (round(abs(c['price'] - ref) / atr, 3) if atr else None)})
    out = SideLevels(side, candidates=listed)
    if not candidates:
        out.reason = 'no_levels'
        return out
    if atr is None:
        out.reason = 'atr_unavailable'
        return out
    unbroken = [c for c in listed if not c['broken']]
    rungs = [c for c in unbroken if c['in_window']]
    if not rungs:
        # The premarket extreme sits on the cleared mark and is never
        # broken, so "all broken" means every STRUCTURAL candidate on the
        # side was traded through and only the premarket extreme (outside
        # the window) is left.
        structural_unbroken = [c for c in unbroken
                               if c['name'] not in (PREMARKET_HIGH, PREMARKET_LOW)]
        if structural_unbroken:
            out.reason = 'next_level_outside_window'
        elif any(c['broken'] for c in listed):
            out.reason = 'all_broken_by_premarket'
        elif listed:
            out.reason = 'next_level_outside_window'
        else:
            out.reason = 'no_levels'
        return out
    trig = rungs[0]
    out.trigger = _rung(trig, ref)
    out.regime = 'normal'
    out.reason = None
    out.targets = [_rung(c, ref) for c in rungs[1:4]]
    stop = next((c for c in other if _within_staleness_window(c['price'], ref, atr)), None)
    out.stop = _rung(stop, ref) if stop else None
    out.ladder = [_ladder_entry(c, ref) for c in rungs[:2]]
    out.room_pct = round(abs(trig['price'] - ref) / ref * 100, 3)
    out.distance_atr = round(abs(trig['price'] - ref) / atr, 3)
    return out


def _legacy_trigger_dict(s: SideLevels) -> Optional[dict]:
    """A side pick in the {trigger_level, trigger_name, targets, stop, ...}
    shape persisted to premarket_analysis and read by the formatter."""
    if s.trigger is None:
        return None
    t = s.trigger
    targets = [{'price': x['price'], 'name': x['name'], 'timeframe': x['timeframe']}
               for x in s.targets]
    room_t1 = (round(abs(targets[0]['price'] - t['price']) / t['price'] * 100, 3)
               if targets else 0)
    return {
        'trigger_level': t['price'], 'trigger_name': t['name'],
        'targets': targets,
        'stop': s.stop['price'] if s.stop else None,
        'stop_name': s.stop['name'] if s.stop else None,
        'room_to_first_target': room_t1,
        'reasoning': '',
    }


LIVE_LEVEL_BASIS_SQL = (
    "SELECT ticker, level_basis FROM premarket_analysis "
    "WHERE ticker = :ticker AND analysis_date = :d AND run_kind = 'live' "
    "AND level_basis IS NOT NULL LIMIT 1"
)


def parse_level_basis(value) -> Optional[dict]:
    """A level_basis cell (JSONB dict or its JSON text) as a dict, or None."""
    import json as _json  # noqa: PLC0415
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = _json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def read_live_level_basis(query_fn, ticker: str, session_date) -> Optional[dict]:
    """The session's level_basis from its LIVE premarket_analysis row.

    `query_fn(sql, params)` returns a DataFrame. A replay row for the same
    ticker and session is never read; a missing row or a missing column
    (the schema not applied yet) gives None, and the caller builds with
    build_session_levels instead. Any other failed query raises."""
    try:
        df = query_fn(LIVE_LEVEL_BASIS_SQL,
                      {'ticker': str(ticker).upper(), 'd': str(_to_date(session_date))})
    except Exception as exc:  # re-raised unless a missing column
        if not _is_missing_schema_error(exc):
            raise
        return None
    if df is None or getattr(df, 'empty', True) or 'level_basis' not in df.columns:
        return None
    return parse_level_basis(df.iloc[0]['level_basis'])


def premarket_snapshot_from_daily(df: pd.DataFrame, session_date) -> Optional[dict]:
    """The premarket snapshot dated `session_date` from a daily frame whose
    rows carry pre_high / pre_low / pre_vwap / gap_pct (the session's own
    row, written by fetch-premarket-refresh at 08:20 ET), or None when that
    row is absent. A prior day's pre_* is never returned."""
    if df is None or len(df) == 0:
        return None
    frame = _normalize_daily(df) if not isinstance(df.index, pd.DatetimeIndex) else df
    idx = frame.index.tz_localize(None) if frame.index.tz is not None else frame.index  # tz-ok: session-date labels, wall date kept
    session = _to_date(session_date)
    rows = frame.loc[idx.normalize() == pd.Timestamp(session)]
    if rows.empty:
        return None
    return premarket_snapshot_from_row(rows.iloc[-1], session)


# ─── LevelMap compatibility wrapper ───────────────────────────────────────


def build_level_map(
    ticker: str,
    daily_df: pd.DataFrame,
    current_price: float,
    daily_strat_class: str = '',
    combo: str = '',
    atr: Optional[float] = None,
    analysis_date: Optional[date_type] = None,
) -> LevelMap:
    """Deprecated shim: build_session_levels with the caller's price as the
    reference and no premarket snapshot, projected to a LevelMap. Consumers
    call build_session_levels; this stays for read-only callers in tests and
    notebooks and applies the same rules."""
    if analysis_date is None:
        df = _normalize_daily(daily_df)
        if len(df):
            analysis_date = (df.index[-1] + pd.Timedelta(days=1)).date()
        else:
            from lib.eastern_time import eastern_now
            analysis_date = eastern_now().date()
    sl = build_session_levels(ticker, analysis_date, daily_df, atr, None,
                              reference=current_price,
                              daily_strat_class=daily_strat_class)
    return sl.to_level_map()


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


# Match the canonical gap-level name shape: GAP_H_YYYY-MM-DD / GAP_L_YYYY-MM-DD.
# The internal `StratLevel.name` keeps the canonical form (signal_monitor's
# level-break detection keys on it), but Discord/brief display renders the
# friendlier "M/D Gap High" / "M/D Gap Low" via `_display_level_name`.
_GAP_NAME_RE = re.compile(
    r'^GAP_([HL])_(\d{4})-(\d{2})-(\d{2})$'
)


_DISPLAY_NAMES = {
    PARENT_BAR_HIGH: 'Parent bar high',
    PARENT_BAR_LOW: 'Parent bar low',
}


def _display_level_name(name: str) -> str:
    """Render a StratLevel.name in the brief-friendly form.

    Most names pass through unchanged (PDH, PWH, CMO, …). The exception is
    gap levels emitted by ``compute_gap_levels`` whose canonical names look
    like ``GAP_H_2026-05-05`` — those get rewritten to ``5/5 Gap High``
    (likewise ``GAP_L_…`` → ``5/5 Gap Low``). Internal data is untouched;
    this only changes the Discord/playbook rendering.
    """
    if name in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[name]
    m = _GAP_NAME_RE.match(name or '')
    if not m:
        return name
    side_code, _yyyy, mm, dd = m.groups()
    side = 'High' if side_code == 'H' else 'Low'
    return f"{int(mm)}/{int(dd)} Gap {side}"


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
    """Format a SessionLevels' LevelMap projection into the playbook block.

    Output (a side with a trigger):
      CALLS above 215.85 (PDH)
        Stop: 213.20 (PDL)
        T1: 217.10 (PWH)
        Room to trigger: 0.20%

    A side with no trigger renders the one orb_only line for its reason from
    ORB_ONLY_COPY. The trigger, the targets and NEXT LEVELS are the same
    ordered side list from build_session_levels, and Room to trigger is the
    trigger's own distance from the reference.
    """
    if regime_long is None:
        regime_long = level_map.regime_long or regime
    if regime_short is None:
        regime_short = level_map.regime_short or regime

    lines = []
    if level_map.premarket_status == 'premarket_unavailable':
        lines.append(f"  {PREMARKET_MISSING_NOTE}")
        lines.append('')
    if regime_compute_error:
        lines.append(
            f"  ⚠ regime classifier failed: {regime_compute_error} "
            f"-- no level-break trigger published; treat with care"
        )

    def _side_block(label: str, side: str, trig: Optional[dict], reason: Optional[str],
                    room: Optional[float], denied_bias: str, side_regime: Optional[str]) -> list:
        # An orb_only side never prints a trigger block, even when a caller
        # hands a LevelMap that still carries one (G.P1.7).
        if not trig or side_regime == 'orb_only':
            return [f"  {label}: " + orb_only_text(reason, side)]
        word = 'above' if side == 'long' else 'below'
        line = f"  {label} {word} {trig['trigger_level']:.2f} ({_display_level_name(trig['trigger_name'])})"
        if bias == denied_bias:
            line += ' -- only if bias denied'
        out = [line]
        if trig.get('stop') is not None:
            out.append(f"    Stop: {trig['stop']:.2f} ({_display_level_name(trig['stop_name'])})")
        for i, t in enumerate(trig.get('targets', []), 1):
            out.append(f"    T{i}: {t['price']:.2f} ({_display_level_name(t['name'])})")
        if room is not None:
            out.append(f"    Room to trigger: {room:.2f}%")
        return out

    lines.extend(_side_block('CALLS', 'long', level_map.calls_trigger,
                             level_map.reason_long, level_map.room_to_run_up, 'bearish',
                             regime_long))
    lines.append('')
    lines.extend(_side_block('PUTS', 'short', level_map.puts_trigger,
                             level_map.reason_short, level_map.room_to_run_down, 'bullish',
                             regime_short))

    next_block = _format_next_levels(level_map)
    if next_block:
        lines.append('')
        lines.extend(next_block)

    if level_map.pmg_zones:
        lines.append('')
        lines.append('  PMG ZONES:')
        for z in level_map.pmg_zones[:3]:
            names = ', '.join(_display_level_name(n) for n in z['level_names'])
            lines.append(
                f"    {z['center_price']:.2f} ({names}) "
                f"[strength: {z['strength']}]"
            )

    return '\n'.join(lines)


def _format_next_levels(level_map: LevelMap) -> list:
    """Render LevelMap.call_levels / put_levels as brief lines.

    Example:
      NEXT LEVELS:
        Calls (up):  251.50 PWH (week) +0.60%, 252.00 PDH (day) +0.80%
        Puts (down): 248.00 PQL (quarter) -0.80%, 245.00 PMH (month) -2.00%
    """
    calls = level_map.call_levels or []
    puts = level_map.put_levels or []
    if not calls and not puts:
        return []

    def _fmt(lv):
        period = f" ({lv['period']})" if lv.get('period') else ''
        return (f"{lv['price']:.2f} {_display_level_name(lv['name'])}"
                f"{period} {lv['distance_pct']:+.2f}%")

    out = ['  NEXT LEVELS:']
    if calls:
        out.append('    Calls (up):  ' + ', '.join(_fmt(lv) for lv in calls))
    if puts:
        out.append('    Puts (down): ' + ', '.join(_fmt(lv) for lv in puts))
    return out


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


def daily_data_freshness(
    last_bar_date: Optional[date_type], analysis_date: date_type,
) -> tuple[bool, int, str]:
    """Is a daily frame whose last bar is `last_bar_date` fresh for a session
    dated `analysis_date`? ONE rule for the premarket brief and the
    movement-statement endpoint, so the playbook row and the ladder matched
    against it are withheld on the same days (Codex P2 on #1030, round 6).

    Returns (is_stale, gap_days, status). gap_days is the calendar-day gap;
    None input maps to -1 / 'unknown'. Fresh when the gap is <= 1 day, or on
    the two weekend bridges where Friday's bar IS the market's most recent
    close: a Monday session reading Friday (gap 3) and a Sunday weekly brief
    reading Friday (gap 2). Anything else, including a Monday reading
    Thursday (gap 4) and a Tuesday after a Monday holiday (gap 4), is
    'STALE_DAILY_DATA': the deliberate bias is toward over-flagging on
    holiday weeks, because under-flagging republished a frozen 2026-04-27 bar
    four mornings running (Track B audit G.P0.4). Pure; no calendar library,
    so it behaves identically in the API image, which does not ship
    pandas-market-calendars.
    """
    if last_bar_date is None:
        return False, -1, 'unknown'
    gap = (analysis_date - last_bar_date).days
    if gap <= 1:
        return False, gap, 'fresh'
    weekday = analysis_date.weekday()
    weekend_exempt = (
        (weekday == 0 and gap == 3)     # Monday → Friday
        or (weekday == 6 and gap == 2)  # Sunday weekly brief → Friday
    )
    if weekend_exempt:
        return False, gap, 'fresh'
    return True, gap, 'STALE_DAILY_DATA'


def _trading_days_between(source_ts: pd.Timestamp, ref_ts: pd.Timestamp) -> int:
    """Count NYSE trading days from source_ts (exclusive) to ref_ts (inclusive).

    Returns 0 when source >= ref. Delegates to the shared NYSE calendar
    (`lib.eastern_time.session_count`, FEAT-DATA-001), which honours holidays
    and raises, never approximates, when the calendar is unavailable.
    Examples:
      Fri 5/8 close → Mon 5/11 brief = 1 trading day (Mon)
      Thu 5/22 close → Tue 5/27 (post-Memorial-Day) brief = 2 (Fri + Tue,
        skipping Memorial-Day Mon)
      4/27 close → 5/6 (the original 5/6 freeze) = 6 trading days

    Each end counts as the calendar date it carries (``Timestamp.date()``,
    the same date the old ``normalize()`` walk used), not as an Eastern
    instant. Callers hand in date-valued stamps localised to UTC midnight
    (``df.index.max()`` and ``analysis_date`` in the premarket brief);
    converting those to Eastern would move each back to the previous evening
    and change the count whenever the reference day is a weekend or holiday.

    The freshness guard uses business-days because that's the semantic
    intent: "no more than N trading sessions behind." Calendar days
    have to use a +3-day weekend buffer (max_age_days=4 to allow for
    Mon-after-Fri = 3 calendar days), which is implicit.

    Rule 3.7: the only caller does `if biz_days > max_age_business_days:
    raise StaleSourceDataError`, so a count that fell back to an estimate or
    to 0 on a calendar failure would disable the staleness guard. Every
    calendar error therefore propagates.
    """
    return session_count(source_ts.date(), ref_ts.date())


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
