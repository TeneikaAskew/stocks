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

from lib import eastern_time
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
    # 'ok', 'premarket_unavailable' or 'premarket_unfiltered' from
    # build_session_levels; the brief prints PREMARKET_MISSING_NOTE when the
    # snapshot was unavailable and PREMARKET_UNFILTERED_NOTE when the
    # snapshot was refused for want of calibrated filter thresholds.
    premarket_status: Optional[str] = None
    # Each side's trigger-window parameter (LevelParam.to_basis() plus key
    # and ticker), so the orb_only copy states the ticker's own window.
    window_long: Optional[dict] = None
    window_short: Optional[dict] = None
    # 'ok', or why there are no PMG zones (the cluster tolerance's status).
    pmg_status: str = 'ok'


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


# The gap-level lookback in bars: a count that sets the product's shape, not a
# distance (the per-ticker parameter spec's Non-goals keep it).
GAP_LEVEL_LOOKBACK_BARS = 20


def compute_gap_levels(daily_df: pd.DataFrame, lookback: int = GAP_LEVEL_LOOKBACK_BARS) -> List[StratLevel]:
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
    tolerance_atr: float,
    atr: float,
) -> list:
    """Detect PMG zones where multiple timeframe levels cluster.

    Args:
        levels: list of StratLevel objects
        tolerance_atr: the ticker's level_cluster_atr parameter: two levels
            closer than this many ATRs (the ticker's typical 15-minute move)
            trade as one zone
        atr: the ATR of the policy's basis for the last completed session

    Returns:
        list of dicts: [{center_price, level_names, timeframes, count, strength}]
    """
    if not levels:
        return []
    band = float(tolerance_atr) * float(atr)

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
            if abs(sorted_levels[j].price - lvl.price) <= band:
                cluster.append(sorted_levels[j])
                used.add(j)

        if len(cluster) >= 2:
            center = sum(lv.price for lv in cluster) / len(cluster)
            timeframes = set(lv.timeframe for lv in cluster)
            # One point per level and half a point per extra timeframe.
            strength = (2 * len(cluster) + len(timeframes) - 1) / 2

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
    window_atr: Optional[float],
) -> bool:
    """The one distance rule (FEAT-STRAT-001): a level is close enough to be a
    trigger, a stop, a target, a ladder rung or the Room to trigger line when
    its distance from the reference is within `window_atr` of this ticker's
    ATR. `window_atr` is the side's calibrated window: a level above the
    reference uses trigger_window_long_atr, a level below uses
    trigger_window_short_atr (so a long's stop is windowed by the short one).

    There is no percent axis and no fallback: without a positive ATR or a
    window nothing is in it, and build_session_levels reports the reason.
    """
    if atr is None or not _finite_positive(atr):
        return False
    if window_atr is None or not _finite_positive(window_atr):
        return False
    if current_price is None or not _finite_positive(current_price):
        return False
    distance = abs(float(level_price) - float(current_price))
    return distance <= float(window_atr) * float(atr)


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
    from decimal import Decimal, ROUND_HALF_UP

    return int(Decimal(str(float(x))).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)


# ─── Per-ticker level parameters (FEAT-STRAT-001, 2026-11-08) ────────────
#
# Every distance the level and plan code decides with is a per-ticker value
# calibrated from the ticker's own bars (lib.level_calibration) and stored in
# ticker_level_params, under the statistic, lookback and minimum sample of
# level_param_policy (gcp/schema.sql). load_level_params reads the rows in
# force on a session for every ticker of a run in one query. There is no
# default row and no constant behind it.

PARAM_OK = 'ok'
# Statuses a calibration run writes (ticker_level_params.status).
CALIBRATION_STATUSES = ('ok', 'insufficient_history', 'input_unavailable',
                        'no_positive_target')
# Statuses only the loader gives: no row for the ticker and key, or rows only
# in an ATR basis other than the policy's basis in force on the session.
PARAMS_UNAVAILABLE = 'params_unavailable'
PARAMS_BASIS_MISMATCH = 'params_basis_mismatch'
LOADER_STATUSES = (PARAMS_UNAVAILABLE, PARAMS_BASIS_MISMATCH)

# Policy keys that are not parameters.
POLICY_ATR_BASIS = 'atr_basis'
POLICY_CALIBRATION_UNIVERSE = 'calibration_universe'
NON_PARAMETER_KEYS = (POLICY_ATR_BASIS, POLICY_CALIBRATION_UNIVERSE)

# The ATR columns a basis may name, with the add_all_indicators column each
# is read from in a DataLoader frame.
ATR_COLUMNS = {'atr_14': 'ATR14', 'atr_5': 'ATR5'}

PERSONAS = ('aggressive', 'neutral', 'conservative')


def trigger_window_key(side: str) -> str:
    return 'trigger_window_long_atr' if side == 'long' else 'trigger_window_short_atr'


def entry_buffer_key(persona: str, edge: str) -> str:
    return f'entry_buffer_{persona}_{edge}_atr'


def stop_key(persona: str) -> str:
    return f'stop_{persona}_atr'


MIN_STOP_KEY = 'min_stop_atr'
PM_SPIKE_KEY = 'pm_spike_atr'
PM_STALE_PRINT_KEY = 'pm_stale_print_atr'
LEVEL_CLUSTER_KEY = 'level_cluster_atr'
# FEAT-STRAT-001 exits in thirds (2026-11-11 spec). Two per-ticker keys
# seeded by policy (method policy_seed) and two policy-wide keys: the leg
# count and the entry cutoff are plan shape and clock, read from the policy
# row in force, never from a ticker row.
TARGET_SPACING_KEY = 'target_min_spacing_atr'
GAP_FILL_FLAG_KEY = 'gap_fill_flag_atr'
EXIT_LEGS_KEY = 'exit_legs'
ENTRY_CUTOFF_KEY = 'entry_cutoff_et'
POLICY_SEED_METHOD = 'policy_seed'
POLICY_SEEDED_KEYS = (TARGET_SPACING_KEY, GAP_FILL_FLAG_KEY)
POLICY_WIDE_KEYS = (EXIT_LEGS_KEY, ENTRY_CUTOFF_KEY)


def target_key(persona: str, k: int) -> str:
    return f'target_{persona}_{k}_r'


# The persona whose stop tightens to the nearest structure on the stop side.
STRUCTURAL_STOP_PERSONA = 'conservative'


def persona_stop_price(persona: str, sign: float, midpoint: float, atr: float,
                       stop_atr: float, min_stop_atr: float, structure=()) -> float:
    """The persona's stop price for an entry midpoint: the one rule the
    planner publishes (lib.agents.trade_planner) and the calibration
    measures its targets' R with (lib.level_calibration), so a published
    target's reach share is a share in the R the plan actually carries.

    The stop sits stop_atr x ATR from the midpoint on the losing side
    (`sign` is +1 for a long, -1 for a short). The conservative persona
    tightens it to the closest level in `structure` (the caller's swing
    extreme, 200-day SMA and the builder's stop anchor) that lies on the
    stop side of the midpoint. Then the floor: no stop closer to the
    midpoint than min_stop_atr x ATR."""
    stop = midpoint - sign * stop_atr * atr
    if persona == STRUCTURAL_STOP_PERSONA:
        candidates = [stop]
        for level in structure:
            if level is None:
                continue
            if (sign > 0 and level < midpoint) or (sign < 0 and level > midpoint):
                candidates.append(level)
        stop = max(candidates) if sign > 0 else min(candidates)
    min_distance = min_stop_atr * atr
    if abs(midpoint - stop) < min_distance:
        stop = midpoint - sign * min_distance
    return stop


class LevelParamsUnavailable(RuntimeError):
    """The parameter tables cannot be read: a missing table, a failed query,
    or an empty policy. An INTERNAL failure (CLAUDE.md 3.7): the brief exits
    non-zero, the insight run is marked failed with reason
    level_params_unavailable, the signal monitor skips its level refresh."""

    reason = 'level_params_unavailable'


class LevelParamUnavailable(LookupError):
    """A caller asked for the value of a parameter whose status is not ok.
    Names the key, the status and the sample so the copy can say why."""

    def __init__(self, param: 'LevelParam'):
        self.param = param
        self.key = param.key
        self.status = param.status
        super().__init__(
            f"level parameter {param.key} for {param.ticker or '<ticker>'} is "
            f"{param.status} (sample_n={param.sample_n}, min_sample={param.min_sample})")


def _iso(v) -> Optional[str]:
    d = _to_date(v)
    return d.isoformat() if d is not None else None


def _opt_float(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _opt_int(v) -> Optional[int]:
    f = _opt_float(v)
    return int(f) if f is not None else None


def _json_obj(v) -> dict:
    import json as _json
    if v is None:
        return {}
    if isinstance(v, dict):
        return dict(v)
    if isinstance(v, str):
        try:
            out = _json.loads(v)
        except ValueError:
            return {}
        return out if isinstance(out, dict) else {}
    return {}


@dataclass(frozen=True)
class LevelParam:
    """One parameter of one ticker as in force on one session."""
    key: str
    status: str
    value: Optional[float] = None
    ticker: str = ''
    effective_from: Optional[str] = None
    method_id: Optional[str] = None
    sample_n: Optional[int] = None
    min_sample: Optional[int] = None
    statistic_q: Optional[float] = None
    lookback_sessions: Optional[int] = None
    input_from: Optional[str] = None
    input_to: Optional[str] = None
    run_id: Optional[str] = None
    atr_basis: Optional[str] = None
    policy_effective_from: Optional[str] = None
    source: Optional[str] = None
    # A policy-wide key's policy extra (exit_legs {"legs": n},
    # entry_cutoff_et {"time_et": "HH:MM"}); None for a ticker parameter.
    extra: Optional[dict] = None

    @property
    def ok(self) -> bool:
        return self.status == PARAM_OK and self.value is not None

    def to_basis(self) -> dict:
        return {
            'value': self.value, 'status': self.status,
            'effective_from': self.effective_from, 'method_id': self.method_id,
            'sample_n': self.sample_n, 'min_sample': self.min_sample,
            'statistic_q': self.statistic_q,
            'lookback_sessions': self.lookback_sessions,
            'input_from': self.input_from, 'input_to': self.input_to,
            'run_id': self.run_id, 'atr_basis': self.atr_basis,
            'policy_effective_from': self.policy_effective_from,
            'source': self.source,
            **({'extra': dict(self.extra)} if self.extra is not None else {}),
        }

    @classmethod
    def from_basis(cls, key: str, d: dict, ticker: str = '') -> 'LevelParam':
        status = d.get('status') or PARAMS_UNAVAILABLE
        value = _opt_float(d.get('value')) if status == PARAM_OK else None
        if status == PARAM_OK and value is None:
            raise ValueError(f"level_basis records {key} as ok with no value")
        return cls(
            key=key, status=status, value=value, ticker=ticker,
            effective_from=_iso(d.get('effective_from')), method_id=d.get('method_id'),
            sample_n=_opt_int(d.get('sample_n')), min_sample=_opt_int(d.get('min_sample')),
            statistic_q=_opt_float(d.get('statistic_q')),
            lookback_sessions=_opt_int(d.get('lookback_sessions')),
            input_from=_iso(d.get('input_from')), input_to=_iso(d.get('input_to')),
            run_id=(str(d['run_id']) if d.get('run_id') is not None else None),
            atr_basis=d.get('atr_basis'),
            policy_effective_from=_iso(d.get('policy_effective_from')),
            source=d.get('source'),
            extra=(dict(d['extra']) if isinstance(d.get('extra'), dict) else None),
        )


@dataclass
class LevelParams:
    """Every level and plan parameter of one ticker in force on one session,
    with the policy that produced them. ``value(key)`` answers only for status
    ok and raises LevelParamUnavailable otherwise; ``status(key)`` always
    answers."""
    ticker: str
    session_date: Optional[date_type]
    atr_basis: str
    policy_effective_from: Optional[str]
    params: Dict[str, LevelParam] = field(default_factory=dict)

    def param(self, key: str) -> LevelParam:
        p = self.params.get(key)
        if p is None:
            return LevelParam(key=key, status=PARAMS_UNAVAILABLE, ticker=self.ticker)
        return p

    def status(self, key: str) -> str:
        return self.param(key).status

    def ok(self, key: str) -> bool:
        return self.param(key).ok

    def value(self, key: str) -> float:
        p = self.param(key)
        if not p.ok:
            raise LevelParamUnavailable(p)
        return float(p.value)

    def first_not_ok(self, keys) -> Optional[LevelParam]:
        for k in keys:
            p = self.param(k)
            if not p.ok:
                return p
        return None

    def to_basis(self) -> dict:
        return {
            'atr_basis': self.atr_basis,
            'policy_effective_from': self.policy_effective_from,
            'params': {k: p.to_basis() for k, p in sorted(self.params.items())},
        }

    @classmethod
    def from_basis(cls, ticker: str, session_date, d: Optional[dict]) -> Optional['LevelParams']:
        """The parameters a level_basis recorded, or None when it recorded
        none (a basis written before per-ticker parameters)."""
        if not isinstance(d, dict) or not isinstance(d.get('params'), dict) or not d.get('atr_basis'):
            return None
        return cls(
            ticker=ticker, session_date=_to_date(session_date),
            atr_basis=str(d['atr_basis']),
            policy_effective_from=_iso(d.get('policy_effective_from')),
            params={k: LevelParam.from_basis(k, v, ticker)
                    for k, v in d['params'].items() if isinstance(v, dict)},
        )


def basis_records_params(basis) -> bool:
    """Whether a stored level_basis recorded the parameters it was built
    with. A reader that holds such a basis never reads the parameter tables;
    one that does not (a basis written before parameters were recorded)
    passes the rows in force on that basis's session to from_basis."""
    return isinstance(basis, dict) and isinstance(basis.get('params'), dict) \
        and bool(basis.get('atr_basis'))


LEVEL_PARAMS_SQL = (
    "SELECT 'policy' AS row_kind, NULL AS ticker, p.param_key, NULL AS value, "
    "NULL AS status, NULL AS atr_basis, p.method_id, p.statistic_q, "
    "p.lookback_sessions, p.min_sample, p.extra, p.effective_from, "
    "NULL AS policy_effective_from, NULL AS sample_n, NULL AS input_from, "
    "NULL AS input_to, NULL AS run_id, NULL AS source "
    "FROM level_param_policy p WHERE p.effective_from <= :session_date "
    "UNION ALL "
    "SELECT 'ticker' AS row_kind, t.ticker, t.param_key, t.value, t.status, "
    "t.atr_basis, t.method_id, NULL AS statistic_q, NULL AS lookback_sessions, "
    "NULL AS min_sample, NULL AS extra, t.effective_from, "
    "t.policy_effective_from, t.sample_n, t.input_from, t.input_to, t.run_id, "
    "t.source FROM ("
    "SELECT tp.ticker, tp.param_key, tp.value, tp.status, tp.atr_basis, "
    "tp.method_id, tp.effective_from, tp.policy_effective_from, tp.sample_n, "
    "tp.input_from, tp.input_to, tp.run_id, tp.source, "
    "ROW_NUMBER() OVER (PARTITION BY tp.ticker, tp.param_key, tp.atr_basis "
    "ORDER BY tp.effective_from DESC) AS rn "
    "FROM ticker_level_params tp "
    "WHERE tp.ticker IN ({tickers}) AND tp.effective_from <= :session_date"
    ") t WHERE t.rn = 1"
)


def _policy_row(r) -> dict:
    return {
        'param_key': r['param_key'], 'method_id': r.get('method_id'),
        'statistic_q': _opt_float(r.get('statistic_q')),
        'lookback_sessions': _opt_int(r.get('lookback_sessions')),
        'min_sample': _opt_int(r.get('min_sample')),
        'extra': _json_obj(r.get('extra')), 'effective_from': _iso(r.get('effective_from')),
    }


def policy_in_force(rows) -> Dict[str, dict]:
    """The policy row in force per key from policy rows already bounded to
    effective_from on or before the session: the greatest effective_from."""
    out: Dict[str, dict] = {}
    for r in rows:
        row = _policy_row(r)
        key, eff = row['param_key'], row['effective_from']
        if key not in out or (eff or '') > (out[key]['effective_from'] or ''):
            out[key] = row
    return out


def policy_atr_basis(policy: Dict[str, dict]) -> str:
    row = policy.get(POLICY_ATR_BASIS)
    column = (row or {}).get('extra', {}).get('column')
    if column not in ATR_COLUMNS:
        raise LevelParamsUnavailable(
            f"level_param_policy has no usable atr_basis row in force (got {column!r}); "
            f"expected one of {sorted(ATR_COLUMNS)}")
    return column


def policy_time_minutes(text) -> Optional[int]:
    """Minutes after midnight of an 'HH:MM' clock time, or None."""
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', str(text or '').strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h >= 24 or mi >= 60:
        return None
    return h * 60 + mi


def policy_wide_param(key: str, pol: dict, ticker: str, atr_basis: str) -> LevelParam:
    """A policy-wide key (exit_legs, entry_cutoff_et) as a LevelParam for
    one ticker: the policy row in force is the value, the same for every
    ticker. A row whose extra does not hold a usable value is
    input_unavailable, so the plan that needs it is not published."""
    extra = dict(pol.get('extra') or {})
    value = None
    if key == EXIT_LEGS_KEY:
        legs = extra.get('legs')
        if isinstance(legs, int) and not isinstance(legs, bool) and legs >= 1:
            value = float(legs)
    elif key == ENTRY_CUTOFF_KEY:
        mins = policy_time_minutes(extra.get('time_et'))
        value = float(mins) if mins is not None else None
    return LevelParam(
        key=key, status=PARAM_OK if value is not None else 'input_unavailable',
        value=value, ticker=ticker, effective_from=pol.get('effective_from'),
        method_id=pol.get('method_id'), atr_basis=atr_basis,
        policy_effective_from=pol.get('effective_from'), source='policy', extra=extra)


def load_level_params(query_fn, tickers, session_date) -> Dict[str, LevelParams]:
    """The parameters in force on `session_date` for every ticker in
    `tickers`, in ONE query. `query_fn(sql, params)` returns a DataFrame and
    must raise on failure (gcp.database.query_to_dataframe_strict).

    Per ticker and parameter key, the row used is, among the rows whose
    atr_basis is the policy atr_basis in force on the session, the one with
    the greatest effective_from on or before it. A key with rows only in
    another basis gets status params_basis_mismatch (no row of another basis
    is ever used); a key with no row gets params_unavailable. A missing
    table, a failed query or an empty policy raises LevelParamsUnavailable.

    Callers read once per run and pass the result to every build: the run's
    cache is the dict this returns.
    """
    session = _to_date(session_date)
    if session is None:
        raise LevelParamsUnavailable(f"load_level_params: no session date ({session_date!r})")
    names = sorted({str(t).upper() for t in tickers if t})
    if not names:
        return {}
    placeholders = ', '.join(f':t{i}' for i in range(len(names)))
    sql_params = {f't{i}': t for i, t in enumerate(names)}
    sql_params['session_date'] = session.isoformat()
    try:
        df = query_fn(LEVEL_PARAMS_SQL.format(tickers=placeholders), sql_params)
    except Exception as exc:
        raise LevelParamsUnavailable(f"level parameter query failed: {exc}") from exc
    if df is None:
        raise LevelParamsUnavailable("level parameter query returned no result set")
    records = df.to_dict('records') if len(df) else []
    policy_records = [r for r in records if r.get('row_kind') == 'policy']
    policy = policy_in_force(policy_records)
    # Every policy version on or before the session, by key and
    # effective_from: a ticker row carries the metadata (quantile, minimum
    # sample, lookback) of the policy version it was calibrated under, not
    # the version in force now (Codex P2 on e4bb463e). A value retained
    # under an older policy keeps that policy's coverage claim.
    versions = {(row['param_key'], row['effective_from']): row
                for row in map(_policy_row, policy_records)}
    if not policy:
        raise LevelParamsUnavailable(
            f"level_param_policy holds no row in force on {session.isoformat()}")
    basis = policy_atr_basis(policy)
    policy_version = max(p['effective_from'] or '' for p in policy.values()) or None
    keys = sorted(k for k in policy if k not in NON_PARAMETER_KEYS)
    by_ticker: Dict[str, Dict[str, list]] = {t: {} for t in names}
    for r in records:
        if r.get('row_kind') != 'ticker':
            continue
        t = str(r.get('ticker') or '').upper()
        if t in by_ticker:
            by_ticker[t].setdefault(r['param_key'], []).append(r)
    out: Dict[str, LevelParams] = {}
    for t in names:
        params: Dict[str, LevelParam] = {}
        for key in keys:
            pol = policy[key]
            if key in POLICY_WIDE_KEYS:
                params[key] = policy_wide_param(key, pol, t, basis)
                continue
            common = dict(key=key, ticker=t, min_sample=pol['min_sample'],
                          statistic_q=pol['statistic_q'],
                          lookback_sessions=pol['lookback_sessions'])
            rows = by_ticker[t].get(key, [])
            same = [r for r in rows if r.get('atr_basis') == basis]
            if same:
                r = max(same, key=lambda x: _iso(x.get('effective_from')) or '')
                row_policy = _iso(r.get('policy_effective_from'))
                ver = versions.get((key, row_policy))
                if ver is None:
                    raise LevelParamsUnavailable(
                        f"ticker_level_params {t} {key} (effective {_iso(r.get('effective_from'))}) "
                        f"names policy version {row_policy!r}, which level_param_policy does not hold "
                        f"on or before {session.isoformat()}")
                common = dict(key=key, ticker=t, min_sample=ver['min_sample'],
                              statistic_q=ver['statistic_q'],
                              lookback_sessions=ver['lookback_sessions'])
                status = r.get('status') or PARAMS_UNAVAILABLE
                value = _opt_float(r.get('value')) if status == PARAM_OK else None
                if status == PARAM_OK and value is None:
                    raise LevelParamsUnavailable(
                        f"ticker_level_params {t} {key} is ok with no value; the table's CHECK was bypassed")
                params[key] = LevelParam(
                    status=status, value=value,
                    effective_from=_iso(r.get('effective_from')), method_id=r.get('method_id'),
                    sample_n=_opt_int(r.get('sample_n')),
                    input_from=_iso(r.get('input_from')), input_to=_iso(r.get('input_to')),
                    run_id=(str(r['run_id']) if r.get('run_id') is not None else None),
                    atr_basis=basis,
                    policy_effective_from=_iso(r.get('policy_effective_from')),
                    source=r.get('source'), **common)
            elif rows:
                other = max(rows, key=lambda x: _iso(x.get('effective_from')) or '')
                params[key] = LevelParam(
                    status=PARAMS_BASIS_MISMATCH, method_id=pol['method_id'],
                    atr_basis=other.get('atr_basis'),
                    effective_from=_iso(other.get('effective_from')), **common)
            else:
                params[key] = LevelParam(status=PARAMS_UNAVAILABLE,
                                         method_id=pol['method_id'], **common)
        out[t] = LevelParams(ticker=t, session_date=session, atr_basis=basis,
                             policy_effective_from=policy_version, params=params)
    return out


# ─── One level builder (FEAT-STRAT-001) ───────────────────────────────────
#
# build_session_levels is the only code that turns daily bars, ATR(14) and a
# premarket snapshot into levels, side lists, triggers, stops, targets and the
# ladder. The brief, the planner, the signal monitor, the playbook resolver and
# the movement statement all read a SessionLevels (or its level_basis JSON).

# v2 (2026-11-08): every distance is a per-ticker calibrated parameter
# recorded in level_basis.params; reach rates count only v2 rows.
# v3 (2026-11-11 exits in thirds): targets are spaced by the ticker's
# target_min_spacing_atr and planned in exit_legs legs; gate_targets keep the
# v2 targets for the signal monitor and the structured t1..t3 columns. A
# stored v2 basis is rebuilt with the v2 rule.
LEVEL_RULE_V2 = 'feat-strat-001.v2'
LEVEL_RULE_VERSION = 'feat-strat-001.v3'

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

# A side with no trigger because its window parameter is not ok carries the
# parameter's status as its reason (Design 6).
PARAM_ORB_ONLY_REASONS = {
    'insufficient_history': 'params_insufficient_history',
    'input_unavailable': 'params_input_unavailable',
    'no_positive_target': 'params_unavailable',
    PARAMS_UNAVAILABLE: 'params_unavailable',
    PARAMS_BASIS_MISMATCH: 'params_basis_mismatch',
}

ORB_ONLY_REASONS = (
    'all_broken_by_premarket', 'next_level_outside_window', 'no_levels',
    'atr_unavailable', 'stale_daily', 'params_insufficient_history',
    'params_input_unavailable', 'params_unavailable', 'params_basis_mismatch',
)

_WAIT = "Wait for the 15-min opening range."

# The one copy table for an orb_only side, rendered by the brief banners, the
# planner rationale, the Discord push and the schema descriptions. The
# window and parameter rows are filled from the side's recorded parameter
# (orb_only_text's `detail`): the ticker's own window, its coverage share
# (the sessions whose move stayed inside it) and its exceedance share (the
# sessions that went past it), each its own figure.
ORB_ONLY_COPY = {
    'all_broken_by_premarket': (
        "Pre-market traded through every {side} level within reach. " + _WAIT
    ),
    'next_level_outside_window': (
        "No unbroken {side} level within {window} x ATR({atr_n}); {ticker}'s "
        "daily move stayed inside that distance on {coverage} of the last "
        "{lookback} sessions and went past it on {exceedance}. " + _WAIT
    ),
    'no_levels': (
        "No {side} level in the level history. " + _WAIT
    ),
    'atr_unavailable': (
        "ATR({atr_n}) is unavailable, so no {side} level can be checked against "
        "{ticker}'s {window} x ATR({atr_n}) window. " + _WAIT
    ),
    'stale_daily': (
        "The prior session's daily bar is missing, so no {side} level is "
        "published. " + _WAIT
    ),
    'params_insufficient_history': (
        "No {side} trigger: {param} needs {min_sample} samples of {ticker}'s "
        "history and has {sample_n}, so its window is not calibrated. " + _WAIT
    ),
    'params_input_unavailable': (
        "No {side} trigger: the bars {param} is calibrated from are unavailable "
        "for {ticker}. " + _WAIT
    ),
    'params_unavailable': (
        "No {side} trigger: {param} has no calibrated value for {ticker}. " + _WAIT
    ),
    'params_basis_mismatch': (
        "No {side} trigger: {ticker}'s values are being recalibrated for the new "
        "ATR basis, so {param} is not used until that run completes. " + _WAIT
    ),
}

# Fallback lines for a row whose detail was not recorded (a level_basis from
# before per-ticker parameters); they state no number.
_ORB_ONLY_COPY_NO_DETAIL = {
    'next_level_outside_window': "No unbroken {side} level within the ticker's calibrated window. " + _WAIT,
    'atr_unavailable': "ATR is unavailable, so no {side} level can be checked against the ticker's window. " + _WAIT,
    'params_insufficient_history': "No {side} trigger: the ticker's window parameter has too little history. " + _WAIT,
    'params_input_unavailable': "No {side} trigger: the window parameter's input bars are unavailable. " + _WAIT,
    'params_unavailable': "No {side} trigger: the ticker's window parameter is not calibrated. " + _WAIT,
    'params_basis_mismatch': "No {side} trigger: the ticker's values are being recalibrated for the new ATR basis. " + _WAIT,
}

# Owner ruling 2026-11-08: a brief built without the session's premarket
# snapshot points the reader to Insights, whose refresh reads it later.
PREMARKET_MISSING_NOTE = (
    "Premarket levels were not available when this brief ran. "
    "Refer to Insights for premarket levels."
)

# A snapshot whose prints were not filtered with the ticker's calibrated
# thresholds (pre_filter_status not ok) is refused by the builder.
PREMARKET_UNFILTERED_NOTE = (
    "Premarket high and low are unfiltered (this ticker's print-filter "
    "thresholds are not calibrated), so levels use the prior close."
)

ORB_ONLY_SCHEMA_DESCRIPTION = (
    "'orb_only' = no trigger on this side; the reason is one of "
    + ", ".join(ORB_ONLY_REASONS)
    + " (lib.strat_levels.ORB_ONLY_COPY). " + _WAIT
)


def share_text(x: float) -> str:
    """A share as a whole percent, or one decimal under 10%."""
    pct = float(x) * 100
    return f"{pct:.0f}%" if round(pct, 1) == round(pct) else f"{pct:.1f}%"


def atr_length(basis: Optional[str]) -> str:
    """'14' for atr_14, '5' for atr_5."""
    return str(basis or '').rsplit('_', 1)[-1] or '?'


def multiple_text(x: float) -> str:
    """An ATR multiple as copy: two decimals with trailing zeros dropped
    (2.4, 2.61, 3)."""
    return f"{float(x):.2f}".rstrip('0').rstrip('.')


def orb_only_text(reason: Optional[str], side: str, detail: Optional[dict] = None) -> str:
    """The orb_only copy for one side. `side` is long/short or call/put.
    `detail` is the side's recorded window parameter (SideLevels.window: a
    LevelParam.to_basis() dict plus key and ticker); the window, coverage and
    parameter rows state the ticker's own values from it."""
    word = {'long': 'call', 'short': 'put', 'calls': 'call', 'puts': 'put',
            'CALLS': 'call', 'PUTS': 'put'}.get(side, side)
    reason = reason or 'no_levels'
    template = ORB_ONLY_COPY.get(reason, ORB_ONLY_COPY['no_levels'])
    d = detail if isinstance(detail, dict) else {}
    q = _opt_float(d.get('statistic_q'))
    value = _opt_float(d.get('value'))
    fields = {
        'side': word, 'ticker': d.get('ticker') or 'the ticker',
        'atr_n': atr_length(d.get('atr_basis')), 'param': d.get('key') or 'the window parameter',
        'window': multiple_text(value) if value is not None else None,
        'coverage': share_text(q) if q is not None else None,
        'exceedance': share_text(1 - q) if q is not None else None,
        'lookback': d.get('lookback_sessions'),
        'sample_n': d.get('sample_n'), 'min_sample': d.get('min_sample'),
    }
    needed = {name for name in ('window', 'coverage', 'exceedance', 'lookback', 'sample_n', 'min_sample')
              if '{' + name + '}' in template}
    if any(fields[name] is None for name in needed):
        template = _ORB_ONLY_COPY_NO_DETAIL.get(reason, template)
    return template.format(**fields)


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
    # The side's trigger-window parameter as used (LevelParam.to_basis()
    # plus key and ticker); the copy states the ticker's own window from it.
    window: Optional[dict] = None
    # v3 (exits in thirds): `targets` are the spaced plan targets; the first
    # three rungs past the trigger with no spacing (the v2 targets) are kept
    # as `gate_targets`, which the signal monitor's leg trackers and the
    # structured t1..t3 columns read. `skipped` lists the candidates the
    # spacing walk passed over (with their distance in ATR from the level
    # before them); `target_status` is ok or the spacing or leg parameter's
    # status, in which case the side publishes no target and no plan.
    gate_targets: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    target_status: str = PARAM_OK
    # The plan: spacing (multiple and price), legs and the entry cutoff,
    # recorded so the copy and the resolver read one source.
    plan: Optional[dict] = None

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
            'distance_atr': self.distance_atr, 'window': self.window,
            'gate_targets': self.gate_targets, 'skipped': self.skipped,
            'target_status': self.target_status, 'plan': self.plan,
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
    # The ATR every parameter is measured in: the column the policy's
    # atr_basis names, for the last completed session.
    atr: Optional[float] = None
    atr_14: Optional[float] = None
    atr_5: Optional[float] = None
    atr_basis: Optional[str] = None
    # The ticker's level parameters in force on the session (or recorded in
    # the level_basis it was rebuilt from). Never read from the tables here.
    params: Optional[LevelParams] = None
    pmg_status: str = 'ok'
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
        snap, status = _accept_premarket(premarket, self.session_date)
        if snap is None:
            if status == 'premarket_unfiltered' and self.premarket is None:
                return _assemble(self, premarket=None, premarket_status=status,
                                 reference=None, reference_source=None)
            return self
        return _assemble(self, premarket=snap, premarket_status='ok',
                         reference=None, reference_source=None)

    def with_reference(self, reference: float) -> 'SessionLevels':
        """The same levels against a caller's reference (the signal
        monitor's put re-anchor passes the session open)."""
        return _assemble(self, premarket=self.premarket,
                         premarket_status=self.premarket_status,
                         reference=reference, reference_source='caller')

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
            window_long=self.long.window,
            window_short=self.short.window,
            pmg_status=self.pmg_status,
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
            'atr_14': self.atr_14,
            'atr_5': self.atr_5,
            'atr_basis': self.atr_basis,
            'policy_effective_from': self.params.policy_effective_from if self.params else None,
            'params': self.params.to_basis()['params'] if self.params else None,
            'pmg_status': self.pmg_status,
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
    def from_basis(cls, basis: dict, params: Optional[LevelParams] = None) -> 'SessionLevels':
        """Rebuild from a stored level_basis. The levels, ATR, prior close,
        premarket snapshot and the parameters it recorded are the inputs; the
        picks are recomputed under the current rule so a reader never trusts
        a stale pick. The parameter tables are never read: a basis that
        recorded parameters rebuilds with exactly those, so a later
        calibration run leaves its picks unchanged. `params` is used only
        for a basis written before parameters were recorded (a replay passes
        the rows in force on the replayed session); with neither, every side
        is orb_only with reason params_unavailable."""
        if not isinstance(basis, dict):
            raise ValueError('level_basis must be a JSON object')
        session = _to_date(basis.get('session_date'))
        if session is None:
            raise ValueError('level_basis has no session_date')
        ticker = str(basis.get('ticker') or '')
        recorded = LevelParams.from_basis(ticker, session, {
            'atr_basis': basis.get('atr_basis'),
            'policy_effective_from': basis.get('policy_effective_from'),
            'params': basis.get('params'),
        })
        use = recorded if recorded is not None else params
        atr_basis = use.atr_basis if use is not None else basis.get('atr_basis')
        atr_14 = _opt_float(basis.get('atr_14'))
        atr_5 = _opt_float(basis.get('atr_5'))
        if recorded is None and basis.get('atr_14') is None:
            # A pre-parameter basis recorded ATR(14) as `atr`.
            atr_14 = _opt_float(basis.get('atr'))
        atrs = {'atr_14': atr_14, 'atr_5': atr_5}
        basis_atr = atrs.get(atr_basis) if atr_basis else None
        # A v3 basis is rebuilt with the v3 rule and its recorded values; any
        # earlier basis with the v2 rule (no spacing, three targets), so a
        # stored brief and its replay do not change.
        rule = (LEVEL_RULE_VERSION if basis.get('rule_version') == LEVEL_RULE_VERSION
                else LEVEL_RULE_V2)
        base = cls(
            ticker=ticker,
            session_date=session,
            rule_version=rule,
            status=basis.get('status') or 'ok',
            built_at=basis.get('built_at') or '',
            last_bar_date=_to_date(basis.get('last_bar_date')),
            atr=basis_atr if _finite_positive(basis_atr) else None,
            atr_14=atr_14, atr_5=atr_5, atr_basis=atr_basis, params=use,
            pmg_status=basis.get('pmg_status') or 'ok',
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
        if recorded is None:
            # A pre-parameter basis stored zones from the old percentage
            # tolerance: they are rebuilt from its levels with the
            # parameters supplied (or none), never carried as calibrated
            # output (Codex P2 on e4bb463e).
            base.pmg_zones, base.pmg_status = _pmg_zones(
                [lv for lv in base.levels if lv.name not in (
                    PREMARKET_HIGH, PREMARKET_LOW, PARENT_BAR_HIGH, PARENT_BAR_LOW)],
                use, base.atr)
        if base.status != 'ok':
            return _assemble(base, premarket=None, premarket_status='premarket_unavailable',
                             reference=None, reference_source=None)
        snap, pm_status = _accept_premarket(basis.get('premarket'), session)
        if snap is None and basis.get('premarket_status') == 'premarket_unfiltered':
            pm_status = 'premarket_unfiltered'
        ref = basis.get('reference') if basis.get('reference_source') == 'caller' else None
        return _assemble(base, premarket=snap, premarket_status=pm_status, reference=ref,
                         reference_source='caller' if ref is not None else None)


def _to_date(v) -> Optional[date_type]:
    """A date from a date, datetime, Timestamp or ISO string; None otherwise."""
    from datetime import datetime as _dt
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
    # Per-ticker level parameters (2026-11-08): whether the prints were
    # filtered with the ticker's calibrated thresholds, and which.
    'pre_filter_status': 'pre_filter_status',
    'pre_filter_params': 'pre_filter_params',
}


SESSION_PREMARKET_SQL = (
    "SELECT date, pre_high, pre_low, pre_vwap, gap_pct{provenance} "
    "FROM market_data_daily WHERE ticker = :ticker AND date = :d LIMIT 1"
)


def premarket_filter_inputs(params: 'LevelParams', atrs) -> dict:
    """What the premarket print filter (lib.indicators
    calculate_premarket_context) runs with for one ticker, and what the
    fetcher records beside the snapshot (pre_filter_status,
    pre_filter_params).

    `params` is the ticker's LevelParams in force on the session; `atrs` the
    last completed session's ATR columns ({'atr_14': x, 'atr_5': y}). Returns
    {status, atr, stale_print_atr, spike_atr, params}: status 'ok' when both
    thresholds are ok and the ATR in the policy's basis is positive, and then
    the three numbers are set; otherwise the first non-ok threshold status,
    or 'atr_unavailable', and the three numbers are None so no print is
    filtered and the snapshot is labelled unfiltered."""
    if not isinstance(params, LevelParams):
        raise TypeError(f"premarket_filter_inputs takes LevelParams, not {type(params).__name__}")
    atr = _atr_inputs(atrs).get(params.atr_basis)
    stale = params.param(PM_STALE_PRINT_KEY)
    spike = params.param(PM_SPIKE_KEY)
    record = {
        'atr_basis': params.atr_basis,
        'atr': atr,
        'policy_effective_from': params.policy_effective_from,
    }
    for p in (stale, spike):
        record[p.key] = {'value': p.value, 'status': p.status,
                         'effective_from': p.effective_from, 'run_id': p.run_id}
    not_ok = next((p.status for p in (stale, spike) if not p.ok), None)
    status = not_ok or ('atr_unavailable' if atr is None else PARAM_OK)
    ok = status == PARAM_OK
    return {
        'status': status,
        'atr': atr if ok else None,
        'stale_print_atr': stale.value if ok else None,
        'spike_atr': spike.value if ok else None,
        'params': record,
    }


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


def _accept_premarket(premarket, session_date: date_type) -> Tuple[Optional[dict], str]:
    """The session's own premarket snapshot as a plain dict with
    'ok', or (None, why). A snapshot with no date, or dated any other day,
    is refused as premarket_unavailable. A snapshot whose prints were not
    filtered with the ticker's calibrated thresholds (pre_filter_status not
    'ok', including a row written before the status existed) is refused as
    premarket_unfiltered: its pre_high, pre_low and pre_vwap may carry the
    bad prints the filter drops."""
    if premarket is None:
        return None, 'premarket_unavailable'
    get = premarket.get if isinstance(premarket, dict) else (lambda k, d=None: getattr(premarket, k, d))
    snap_date = _to_date(get('date'))
    if snap_date is None or snap_date != session_date:
        return None, 'premarket_unavailable'
    if get('pre_filter_status') != PARAM_OK:
        has_values = any(_premarket_value(premarket, k) is not None
                         for k in ('pre_high', 'pre_low', 'pre_vwap'))
        return None, ('premarket_unfiltered' if has_values else 'premarket_unavailable')
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
        'pre_filter_status': PARAM_OK,
        'pre_filter_params': _json_obj(get('pre_filter_params')) or None,
    }
    gp = get('gap_pct')
    try:
        out['gap_pct'] = float(gp) if gp is not None and float(gp) == float(gp) else None
    except (TypeError, ValueError):
        out['gap_pct'] = None
    if out['pre_high'] is None and out['pre_low'] is None and out['pre_vwap'] is None:
        return None, 'premarket_unavailable'
    return out, 'ok'


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


def _atr_inputs(atr) -> Dict[str, Optional[float]]:
    """The ATR columns a caller passes, {'atr_14': x, 'atr_5': y}, each a
    positive float or None. A bare number is refused: which ATR it is decides
    every distance, so the caller names the column."""
    if not hasattr(atr, 'get'):
        raise TypeError(
            "build_session_levels takes atr as a mapping of ATR columns "
            f"({sorted(ATR_COLUMNS)}) to the last completed session's values, not {atr!r}")
    out = {}
    for col in ATR_COLUMNS:
        v = atr.get(col)
        out[col] = float(v) if _finite_positive(v) else None
    return out


def atr_inputs_from_frame(daily_df: pd.DataFrame, session_date) -> Dict[str, Optional[float]]:
    """ATR(14) and ATR(5) of the last completed session before `session_date`
    from a DataLoader frame (columns ATR14 / ATR5) or a market_data_daily
    frame (atr_14 / atr_5). A column the frame lacks is None."""
    df = _normalize_daily(daily_df) if daily_df is not None and len(daily_df) else None
    out: Dict[str, Optional[float]] = {col: None for col in ATR_COLUMNS}
    if df is None or not len(df):
        return out
    df = df[df.index.normalize() < pd.Timestamp(_to_date(session_date))]
    df = df[df['Close'].notna()]
    if not len(df):
        return out
    last = df.iloc[-1]
    for col, frame_col in ATR_COLUMNS.items():
        for c in (frame_col, col):
            if c in df.columns:
                v = last.get(c)
                out[col] = float(v) if _finite_positive(v) else None
                break
    return out


def build_session_levels(
    ticker: str,
    session_date: date_type,
    daily_df: pd.DataFrame,
    atr,
    premarket,
    params: LevelParams,
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
      gap_pct, fetched_at, excluded_stale_prints, excluded_spikes,
      pre_filter_status) is used only when its own date is session_date and
      its prints were filtered with the ticker's calibrated thresholds;
      otherwise premarket_unavailable or premarket_unfiltered is recorded.
    * The reference is the snapshot's pre_vwap, else the prior close, unless
      the caller passes `reference`.
    * `atr` maps ATR columns to the last completed session's values
      ({'atr_14': ..., 'atr_5': ...}); the policy's atr_basis picks the one
      every distance is measured in. Missing or not positive gives no
      trigger on either side, reason atr_unavailable.
    * `params` is the ticker's LevelParams in force on the session
      (load_level_params, read once per run). Each side's window is its own
      trigger_window_*_atr; a window that is not ok gives no trigger on that
      side with the parameter's status as the reason. PMG zones use
      level_cluster_atr.
    """
    if not isinstance(params, LevelParams):
        raise TypeError("build_session_levels needs the ticker's LevelParams "
                        "(lib.strat_levels.load_level_params)")
    session_date = _to_date(session_date)
    atrs = _atr_inputs(atr)
    atr_v = atrs.get(params.atr_basis)
    base = SessionLevels(ticker=ticker, session_date=session_date, atr=atr_v,
                         atr_14=atrs['atr_14'], atr_5=atrs['atr_5'],
                         atr_basis=params.atr_basis, params=params,
                         built_at=pd.Timestamp.now(ET_NAME).isoformat(),
                         strat_class=daily_strat_class or '')
    df = _normalize_daily(daily_df)
    if len(df):
        df = df[df.index.normalize() < pd.Timestamp(session_date)]
        df = df[df['Close'].notna() & df['High'].notna() & df['Low'].notna()]
    if len(df) < 2:
        base.status = 'no_data'
        return _assemble(base, premarket=None, premarket_status='premarket_unavailable',
                         reference=None, reference_source=None)
    last_bar = df.index[-1].date()
    base.last_bar_date = last_bar
    is_stale, _gap, _status = daily_data_freshness(last_bar, session_date)
    if is_stale:
        base.status = 'stale_daily'
        return _assemble(base, premarket=None, premarket_status='premarket_unavailable',
                         reference=None, reference_source=None)
    base.prior_close = float(df['Close'].iloc[-1])

    snap, pm_status = _accept_premarket(premarket, session_date)
    anchor = (float(reference) if reference is not None
              else (snap['pre_vwap'] if snap and snap.get('pre_vwap') else base.prior_close))

    prev_levels = _compute_previous_levels(df, analysis_date=session_date)
    curr_levels = _compute_current_levels(df, anchor, analysis_date=session_date)
    gap_levels = compute_gap_levels(df.assign(Time=df.index))
    base.pmg_zones, base.pmg_status = _pmg_zones(
        list(prev_levels.values()) + list(curr_levels.values()) + gap_levels, params, atr_v)
    levels = list(prev_levels.values()) + list(curr_levels.values()) + gap_levels
    parent = find_parent_bar(df)
    if parent is not None:
        ph, pl, plabel = parent
        levels.append(StratLevel(name=PARENT_BAR_HIGH, price=ph, timeframe='day',
                                 level_type='high', period_label=plabel))
        levels.append(StratLevel(name=PARENT_BAR_LOW, price=pl, timeframe='day',
                                 level_type='low', period_label=plabel))
    base.levels = levels
    return _assemble(base, premarket=snap, premarket_status=pm_status, reference=reference,
                     reference_source='caller' if reference is not None else None)


def _pmg_zones(levels: List[StratLevel], params: Optional[LevelParams],
               atr: Optional[float]) -> tuple:
    """(PMG zones, pmg_status) for the clustered levels: the previous,
    current and gap levels (never premarket or parent-bar levels), with the
    ticker's level_cluster_atr in force. The one rule for a fresh build and
    for a stored basis that recorded no parameters."""
    if params is None:
        return [], PARAMS_UNAVAILABLE
    if atr is None:
        return [], 'atr_unavailable'
    cluster = params.param(LEVEL_CLUSTER_KEY)
    if not cluster.ok:
        return [], cluster.status
    return detect_level_clusters(levels, tolerance_atr=cluster.value, atr=atr), 'ok'



def _assemble(base: SessionLevels, *, premarket: Optional[dict], premarket_status: str,
              reference: Optional[float], reference_source: Optional[str]) -> SessionLevels:
    """Recompute reference, cleared marks, broken status and picks from a
    SessionLevels' structural levels plus a premarket snapshot."""
    rule = base.rule_version if base.rule_version == LEVEL_RULE_V2 else LEVEL_RULE_VERSION
    out = SessionLevels(
        ticker=base.ticker, session_date=base.session_date, status=base.status,
        rule_version=rule, built_at=base.built_at,
        last_bar_date=base.last_bar_date, atr=base.atr, atr_14=base.atr_14,
        atr_5=base.atr_5, atr_basis=base.atr_basis, params=base.params,
        pmg_status=base.pmg_status,
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
    out.premarket_status = 'ok' if premarket else premarket_status
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
    out.long = _pick_side('long', candidates, ref, out.cleared_above, out.atr, out.params,
                          rule_version=rule, prior_close=out.prior_close)
    out.short = _pick_side('short', candidates, ref, out.cleared_below, out.atr, out.params,
                           rule_version=rule, prior_close=out.prior_close)
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


def _window_detail(params: Optional[LevelParams], side: str) -> Optional[dict]:
    """The side's trigger-window parameter as recorded on the side."""
    if params is None:
        return None
    key = trigger_window_key(side)
    return {'key': key, 'ticker': params.ticker, **params.param(key).to_basis(),
            'atr_basis': params.atr_basis}


def _pick_side(side: str, candidates: list, ref: float, cleared: float,
               atr: Optional[float], params: Optional[LevelParams], *,
               rule_version: str = LEVEL_RULE_VERSION,
               prior_close: Optional[float] = None) -> SideLevels:
    """One side rule, one broken rule, one window.

    A candidate is on the long list when its cent is at or above the
    cleared-above mark, max(reference, premarket high), and on the short list
    when at or below the cleared-below mark, whatever kind of level it is.
    A candidate between the reference and the mark was traded through by
    premarket: it is listed as broken and is never a pick.

    The side's own window parameter windows its trigger, targets and ladder;
    the other side's windows its stop (the stop lies on the other side of the
    reference). A window that is not ok gives no trigger, with its status as
    the reason.
    """
    own = params.param(trigger_window_key(side)) if params is not None else None
    opp_side = 'short' if side == 'long' else 'long'
    opp = params.param(trigger_window_key(opp_side)) if params is not None else None
    window = own.value if own is not None and own.ok else None
    stop_window = opp.value if opp is not None and opp.ok else None
    ref_c = price_cents(ref)
    mark_c = price_cents(cleared)
    if side == 'long':
        on_side = [c for c in candidates if c['cents'] >= ref_c]
        broken = lambda c: c['cents'] < mark_c
        other = sorted((c for c in candidates if c['cents'] < ref_c), key=lambda c: -c['cents'])
    else:
        on_side = sorted((c for c in candidates if c['cents'] <= ref_c), key=lambda c: -c['cents'])
        broken = lambda c: c['cents'] > mark_c
        other = [c for c in candidates if c['cents'] > ref_c]
    listed = []
    for c in on_side:
        listed.append({**_rung(c, ref), 'cents': c['cents'], 'broken': broken(c),
                       'in_window': _within_staleness_window(c['price'], ref, atr, window),
                       'distance_atr': (round(abs(c['price'] - ref) / atr, 3) if atr else None)})
    out = SideLevels(side, candidates=listed, window=_window_detail(params, side))
    if not candidates:
        out.reason = 'no_levels'
        return out
    # No parameters at all (a level_basis written before they were
    # recorded, rebuilt with none offered): the parameters also name the
    # ATR basis, so without them the ATR is undefined too and the reason
    # is the parameters, checked before the ATR.
    if own is None:
        out.reason = 'params_unavailable'
        return out
    if atr is None:
        out.reason = 'atr_unavailable'
        return out
    if not own.ok:
        out.reason = PARAM_ORB_ONLY_REASONS.get(own.status, 'params_unavailable')
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
    out.gate_targets = [_rung(c, ref) for c in rungs[1:4]]
    if rule_version == LEVEL_RULE_V2:
        out.targets = list(out.gate_targets)
    else:
        _plan_targets(out, rungs, ref, atr, params, prior_close)
    stop = next((c for c in other if _within_staleness_window(c['price'], ref, atr, stop_window)), None)
    out.stop = _rung(stop, ref) if stop else None
    out.ladder = [_ladder_entry(c, ref) for c in rungs[:2]]
    out.room_pct = round(abs(trig['price'] - ref) / ref * 100, 3)
    out.distance_atr = round(abs(trig['price'] - ref) / atr, 3)
    return out


def _plan_targets(out: SideLevels, rungs: list, ref: float, atr: float,
                  params: LevelParams, prior_close: Optional[float]) -> None:
    """Design 1 and 2 of the exits spec: walk the side's rungs past the
    trigger in order, keeping a candidate only when it is at least the
    ticker's spacing (target_min_spacing_atr x ATR, to the cent, equal kept)
    past the trigger or the target before it, until exit_legs targets are
    kept. A spacing, leg or entry cutoff parameter that is not ok publishes
    no target and records its status: there is no unspaced fallback, and no
    plan without the entry rule it is scored on (CLAUDE.md 3.7)."""
    missing = params.first_not_ok((TARGET_SPACING_KEY, EXIT_LEGS_KEY, ENTRY_CUTOFF_KEY))
    cutoff = params.param(ENTRY_CUTOFF_KEY)
    flag = params.param(GAP_FILL_FLAG_KEY)
    out.plan = {
        'spacing_atr': params.param(TARGET_SPACING_KEY).value,
        'spacing_price': None,
        'atr_basis': params.param(TARGET_SPACING_KEY).atr_basis,
        'legs': int(params.value(EXIT_LEGS_KEY)) if params.ok(EXIT_LEGS_KEY) else None,
        'entry_cutoff_et': (cutoff.extra or {}).get('time_et') if cutoff.ok else None,
        'entry_cutoff_status': cutoff.status,
        'gap_fill_flag_atr': flag.value if flag.ok else None,
        'gap_fill_flag_status': flag.status,
    }
    if missing is not None:
        out.target_status = missing.status
        out.targets = []
        return
    spacing = params.value(TARGET_SPACING_KEY)
    legs = int(params.value(EXIT_LEGS_KEY))
    spacing_cents = price_cents(spacing * atr)
    out.plan['spacing_price'] = spacing_cents / 100.0
    prev = rungs[0]
    targets, skipped = [], []
    for c in rungs[1:]:
        if len(targets) == legs:
            break
        if abs(c['cents'] - prev['cents']) >= spacing_cents:
            targets.append(c)
            prev = c
        else:
            skipped.append({**_rung(c, ref),
                            'distance_atr': round(abs(c['cents'] - prev['cents']) / 100.0 / atr, 3)})
    gap_atr = (abs(ref - prior_close) / atr) if prior_close is not None else None
    pdc_cents = price_cents(prior_close) if prior_close is not None else None
    out.targets = []
    for c in targets:
        r = _rung(c, ref)
        is_pdc = c['name'] == 'PDC' or 'PDC' in c['aliases'] or c['cents'] == pdc_cents
        if (is_pdc and flag.ok and gap_atr is not None
                and gap_atr >= flag.value):
            r['gap_fill_atr'] = round(gap_atr, 2)
        out.targets.append(r)
    out.skipped = skipped
    out.target_status = PARAM_OK


def _legacy_trigger_dict(s: SideLevels) -> Optional[dict]:
    """A side pick in the {trigger_level, trigger_name, targets, stop, ...}
    shape persisted to premarket_analysis and read by the formatter."""
    if s.trigger is None:
        return None
    t = s.trigger
    # `targets` keep the v2 meaning (the gating targets the structured
    # t1..t3 columns, the resolver's existing outcome and the monitor read);
    # `plan_targets` are the spaced plan the brief prints (exits spec).
    targets = [{'price': x['price'], 'name': x['name'], 'timeframe': x['timeframe']}
               for x in s.gate_targets]
    room_t1 = (round(abs(targets[0]['price'] - t['price']) / t['price'] * 100, 3)
               if targets else 0)
    out = {
        'trigger_level': t['price'], 'trigger_name': t['name'],
        'targets': targets,
        'stop': s.stop['price'] if s.stop else None,
        'stop_name': s.stop['name'] if s.stop else None,
        'room_to_first_target': room_t1,
        'reasoning': '',
    }
    if s.plan is not None:
        out.update({
            'plan_targets': [{'price': x['price'], 'name': x['name'],
                              'timeframe': x['timeframe'],
                              **({'gap_fill_atr': x['gap_fill_atr']} if 'gap_fill_atr' in x else {})}
                             for x in s.targets],
            'skipped': [{'price': x['price'], 'name': x['name']} for x in s.skipped],
            'target_status': s.target_status,
            'plan': dict(s.plan),
        })
    return out


LIVE_LEVEL_BASIS_SQL = (
    "SELECT ticker, level_basis FROM premarket_analysis "
    "WHERE ticker = :ticker AND analysis_date = :d AND run_kind = 'live' "
    "AND level_basis IS NOT NULL LIMIT 1"
)


def parse_level_basis(value) -> Optional[dict]:
    """A level_basis cell (JSONB dict or its JSON text) as a dict, or None."""
    import json as _json
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
    atr=None,
    analysis_date: Optional[date_type] = None,
    *,
    params: LevelParams,
) -> LevelMap:
    """Deprecated shim: build_session_levels with the caller's price as the
    reference and no premarket snapshot, projected to a LevelMap. Consumers
    call build_session_levels; this stays for read-only callers in tests and
    notebooks and applies the same rules, with the caller's LevelParams and
    ATR columns."""
    if analysis_date is None:
        df = _normalize_daily(daily_df)
        if len(df):
            analysis_date = (df.index[-1] + pd.Timedelta(days=1)).date()
        else:
            from lib.eastern_time import eastern_now
            analysis_date = eastern_now().date()
    sl = build_session_levels(ticker, analysis_date, daily_df, atr or {}, None, params,
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
    elif level_map.premarket_status == 'premarket_unfiltered':
        lines.append(f"  {PREMARKET_UNFILTERED_NOTE}")
        lines.append('')
    if regime_compute_error:
        lines.append(
            f"  ⚠ regime classifier failed: {regime_compute_error} "
            f"-- no level-break trigger published; treat with care"
        )

    def _side_block(label: str, side: str, trig: Optional[dict], reason: Optional[str],
                    room: Optional[float], denied_bias: str, side_regime: Optional[str],
                    window: Optional[dict]) -> list:
        # An orb_only side never prints a trigger block, even when a caller
        # hands a LevelMap that still carries one (G.P1.7).
        if not trig or side_regime == 'orb_only':
            return [f"  {label}: " + orb_only_text(reason, side, window)]
        word = 'above' if side == 'long' else 'below'
        line = f"  {label} {word} {trig['trigger_level']:.2f} ({_display_level_name(trig['trigger_name'])})"
        if bias == denied_bias:
            line += ' -- only if bias denied'
        plan = trig.get('plan')
        if plan is not None:
            return _plan_block(line, side, trig, plan, room, plan.get('atr_basis') or atr_basis)
        out = [line]
        if trig.get('stop') is not None:
            out.append(f"    Stop: {trig['stop']:.2f} ({_display_level_name(trig['stop_name'])})")
        for i, t in enumerate(trig.get('targets', []), 1):
            out.append(f"    T{i}: {t['price']:.2f} ({_display_level_name(t['name'])})")
        if room is not None:
            out.append(f"    Room to trigger: {room:.2f}%")
        return out

    atr_basis = next(((w or {}).get('atr_basis') for w in (level_map.window_long,
                                                           level_map.window_short) if w), None)

    lines.extend(_side_block('CALLS', 'long', level_map.calls_trigger,
                             level_map.reason_long, level_map.room_to_run_up, 'bearish',
                             regime_long, level_map.window_long))
    lines.append('')
    lines.extend(_side_block('PUTS', 'short', level_map.puts_trigger,
                             level_map.reason_short, level_map.room_to_run_down, 'bullish',
                             regime_short, level_map.window_short))

    next_block = _format_next_levels(level_map)
    if next_block:
        lines.append('')
        lines.extend(next_block)

    if level_map.pmg_status == 'atr_unavailable':
        lines.append('')
        lines.append("  PMG ZONES: none (ATR unavailable)")
    elif level_map.pmg_status not in (None, 'ok'):
        lines.append('')
        lines.append(f"  PMG ZONES: none (the level-cluster tolerance is not calibrated: "
                     f"{level_map.pmg_status})")
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


def _clock_text(t) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _plan_block(line: str, side: str, trig: dict, plan: dict, room: Optional[float],
                atr_basis: Optional[str]) -> list:
    """A side's exit plan (exits in thirds spec, Design 8): the entry
    window, the opened-through rule, the stop, up to `legs` spaced targets
    each selling 1/legs, the legs left over held to the close or the stop,
    the candidates skipped for the spacing, and the room to the trigger."""
    from lib.indicators import REGULAR_SESSION_OPEN  # noqa: PLC0415

    cutoff = plan.get('entry_cutoff_et')
    if cutoff:
        line += f", new entries {_clock_text(REGULAR_SESSION_OPEN)} to {cutoff} ET"
    elif plan.get('entry_cutoff_status') not in (None, PARAM_OK):
        line += f", entry window unavailable ({plan['entry_cutoff_status']})"
    out = [line]
    price = trig['trigger_level']
    past = 'at or above' if side == 'long' else 'at or below'
    out.append(f"    No entry if the open is {past} {price:.2f}.")
    if trig.get('stop') is not None:
        out.append(f"    Stop: {trig['stop']:.2f} ({_display_level_name(trig['stop_name'])})")
    status = trig.get('target_status') or PARAM_OK
    legs = plan.get('legs')
    spacing = plan.get('spacing_atr')
    spacing_text = (f"{multiple_text(spacing)} x ATR({atr_length(atr_basis)}) = "
                    f"{plan['spacing_price']:.2f}"
                    if spacing is not None and plan.get('spacing_price') is not None else None)
    if status != PARAM_OK or not legs:
        out.append(f"    Targets unavailable ({status}): no exit plan for this side.")
    else:
        targets = trig.get('plan_targets') or []
        if not targets:
            out.append(f"    No target at least {spacing_text} past the trigger: "
                       f"hold to the close or the stop.")
        share = f"1/{legs}"
        for i, tg in enumerate(targets, 1):
            name = _display_level_name(tg['name'])
            if tg.get('gap_fill_atr') is not None:
                name += f", gap fill: gap {tg['gap_fill_atr']:.2f} x ATR"
            text = f"    T{i}: {tg['price']:.2f} ({name}), "
            left = legs - len(targets)
            if i < len(targets):
                text += f"sell {share}"
            elif left == 0:
                text += f"sell the last {share}, or hold to the close or the stop"
            else:
                text += f"sell {share}, hold the last {left}/{legs} to the close or the stop"
            out.append(text)
        skipped = trig.get('skipped') or []
        if skipped:
            out.append(f"    Skipped, closer than {spacing_text}: " + ', '.join(
                f"{s['price']:.2f} ({_display_level_name(s['name'])})" for s in skipped))
    if room is not None:
        out.append(f"    Room to trigger: {room:.2f}%")
    return out


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
    None input maps to -1 / 'unknown'. Fresh when the gap is <= 1 day, or when
    the last bar is on or after the last NYSE session strictly before
    `analysis_date` (lib.eastern_time.previous_session): the market's most
    recent close. That covers the weekend bridges (a Monday or a Sunday weekly
    brief reading Friday) and every session after an NYSE holiday (the Tuesday
    after Memorial Day reading Friday, the Friday after Thanksgiving reading
    Wednesday). A frame missing a session, such as a Monday reading Thursday,
    is 'STALE_DAILY_DATA' (under-flagging republished a frozen 2026-04-27 bar
    four mornings running, Track B audit G.P0.4). The calendar is read only
    when the gap is two days or more, and a calendar failure raises (Rule 3.7)
    instead of answering fresh or stale (FEAT-DATA-001, 2026-11-11 spec).
    """
    if last_bar_date is None:
        return False, -1, 'unknown'
    gap = (analysis_date - last_bar_date).days
    if gap <= 1:
        return False, gap, 'fresh'
    if last_bar_date >= eastern_time.previous_session(analysis_date):
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
