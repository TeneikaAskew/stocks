"""End-of-day resolver for brief-playbook outcomes.

For each row in premarket_analysis (analysis_date, ticker), walks the
day's market_data_intraday bars and computes:

  - When (if at all) the recommended CALL/PUT trigger was reached
  - When each of T1 / T2 / T3 was reached
  - When the stop was hit
  - Whether there was a reversal (price triggered, then went to stop)
  - Time-to-target-1 in minutes
  - MAE (max adverse excursion) and MFE (max favorable excursion) %
  - The traded outcome under rule ``cross-fill-t1-v1`` (FEAT-SIGNAL-001,
    docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md):
    entry status, fill price, exit reason, and the realized pnl % from the
    fill (all out at the first of the stop or T1, else the last RTH close)
  - EOD pnl in $ (assuming $10,000 notional)
  - The brief's exit plan in thirds, scored (FEAT-STRAT-001,
    docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md
    Design 6): plan entry status, fill, R per position and each leg's exit,
    see :func:`resolve_plan`

Idempotent: re-running on the same date overwrites with the same values.

Cron: ``15 21 * * 1-5`` America/New_York (9:15 PM ET). Intraday
ingestion lands Tue-Fri sessions at ~21:00 ET the same evening, so those
resolve same-night; Monday sessions land ~23:00 ET (measured from
market_data_intraday.inserted_at), so Monday resolves on Tuesday's sweep.
The old 16:30 ET slot raced ingestion every day and resolved nothing
from 2026-06-19 to 2026-08-25. Without PLAYBOOK_RESOLVE_DATE the job
sweeps every unresolved weekday date in a lookback window (default 14
days), so a missed night self-heals on the next run instead of orphaning
the date, and a same-day pre-ingestion miss is benign while a past date
with no bars turns the run red — unless that date is a known NYSE
holiday (see classify_date_outcome), which never gets bars and would
otherwise alarm once a day for the rest of the lookback window.

Environment overrides:
  - PLAYBOOK_RESOLVE_DATE=YYYY-MM-DD : resolve one specific date instead
    of sweeping the unresolved backlog (for backfill or manual one-off).
  - PLAYBOOK_RESOLVE_LOOKBACK_DAYS=14 : sweep window in calendar days.
  - PLAYBOOK_RESOLVE_TICKERS=SPY,QQQ : resolve only these tickers.
  - PLAYBOOK_RESOLVE_NOTIONAL=10000 : dollar notional for the $-pnl calc.
  - PLAYBOOK_RESOLVE_FORCE=true : re-resolve even if outcome_resolved_at
    is already set (default: skip).

Usage:
  # Daily cron (today's row, all tickers):
  python -m gcp.premarket_playbook_resolver

  # Backfill the 5/4-5/8 audit window:
  for d in 2026-05-04 2026-05-05 2026-05-06 2026-05-07 2026-05-08; do
    PLAYBOOK_RESOLVE_DATE=$d python -m gcp.premarket_playbook_resolver
  done

  # Force re-resolve one ticker on one date:
  PLAYBOOK_RESOLVE_DATE=2026-05-06 PLAYBOOK_RESOLVE_TICKERS=QQQ \
    PLAYBOOK_RESOLVE_FORCE=true python -m gcp.premarket_playbook_resolver
"""
from __future__ import annotations

from lib.eastern_time import ET, is_session
import logging
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text

# Holiday recognition reads the shared NYSE calendar
# (lib/eastern_time.is_session, FEAT-DATA-001), so a holiday date (a weekday
# brief row with no session, per pending_dates()'s docstring) is not
# classified as a resolver failure in any year. It replaced a 2026-only set
# imported from scripts/audit_data_freshness.py, which expired on 2027-01-01
# (#1076). Half days are sessions: NYSE trades until 13:00 ET on Black
# Friday, intraday bars do land, and zero resolved rows on it is a real gap
# this resolver must still flag red. A calendar failure raises (CLAUDE.md
# §3.7): there is no weekday-only fallback.

logger = logging.getLogger(__name__)

_ET = ET

# Resolver version stamped on every row — bump when the math changes so
# callers can detect "this row was resolved by an older version, re-run."
# 2026-11-11.v2 is rule cross-fill-t1-v1 (FEAT-SIGNAL-001): no fill when the
# session opens at or beyond the trigger, a later gap fills at its open, the
# trade is all out at the first of the stop or T1 (T1 only from the bar after
# the fill), and P&L is measured from the fill. Rows resolved by
# 2026-05-11.v1 booked the last target reached from the trigger price.
# 2026-11-12.v3 adds the plan columns (FEAT-STRAT-001 exits in thirds,
# Design 6, :func:`resolve_plan`); the existing columns are unchanged from
# 2026-11-11.v2.
RESOLVER_VERSION = '2026-11-12.v3'

# plan_r_status values, in the order the first that applies wins.
PLAN_TARGETS_UNAVAILABLE = 'targets_unavailable'
PLAN_STOP_UNAVAILABLE = 'stop_unavailable'
PLAN_NOT_ENTERED = 'not_entered'
PLAN_OK = 'ok'

# Default notional for $-pnl computation. Per-ticker overrides via env
# var; future enhancement could read from a config table.
DEFAULT_NOTIONAL = 10_000.0


@dataclass
class LegOutcome:
    """Resolved outcome for one CALL or PUT leg."""
    trigger_hit_ts: Optional[datetime] = None
    t1_hit_ts: Optional[datetime] = None
    t2_hit_ts: Optional[datetime] = None
    t3_hit_ts: Optional[datetime] = None
    stop_hit_ts: Optional[datetime] = None
    reversal_after_trigger: Optional[bool] = None
    time_to_t1_min: Optional[int] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    eod_pnl_pct: Optional[float] = None
    eod_pnl_dollar: Optional[float] = None
    # Rule cross-fill-t1-v1: 'gap_through' (the session opened at or beyond
    # the trigger: no entry), 'not_triggered', 'invalid_stop' (stop missing
    # or not beyond the fill on the losing side) or 'filled'. fill_price and
    # exit_reason ('stop', 't1', 'close') are set only for 'filled'.
    entry_status: Optional[str] = None
    fill_price: Optional[float] = None
    exit_reason: Optional[str] = None


@dataclass
class PlanOutcome:
    """The brief's exit plan for one side, scored (exits spec Design 6)."""
    entry_status: Optional[str] = None     # entered | opened_through | late_cross | no_cross | no_trigger
    fill_price: Optional[float] = None
    fill_ts: Optional[datetime] = None
    r: Optional[float] = None
    r_status: Optional[str] = None         # ok | targets_unavailable | stop_unavailable | not_entered
    t1_hit_ts: Optional[datetime] = None
    t2_hit_ts: Optional[datetime] = None
    t3_hit_ts: Optional[datetime] = None
    exit: Optional[str] = None             # each leg's exit in order, e.g. 't1,t2,close'


@dataclass
class PlanInputs:
    """What the brief published for one side's plan: its trigger, stop,
    plan targets in order, leg count, entry cutoff (minutes after midnight
    ET) and the level_basis target_status. A side with no published plan
    has plan_available False."""
    trigger_price: Optional[float] = None
    stop_price: Optional[float] = None
    targets: tuple = ()
    legs: Optional[int] = None
    cutoff_minutes: Optional[int] = None
    target_status: Optional[str] = None

    @property
    def plan_available(self) -> bool:
        return (self.target_status == PLAN_OK and self.legs is not None and self.legs >= 1
                and self.cutoff_minutes is not None)


def derive_level_map_from_daily(ticker: str, analysis_date: date, engine) -> Optional[dict]:
    """Self-healing fallback: re-derive the structured CALL/PUT setup by
    calling the same ``lib.strat_levels.build_session_levels`` the brief
    writer uses, against daily data before ``analysis_date`` and the
    session's own premarket snapshot (FEAT-STRAT-001).

    Returns a dict of structured fields ready to UPSERT into
    premarket_analysis (calls_trigger_price / puts_trigger_price /
    stops / T1-T3 / *_name), or None when daily data is missing.

    This exists because historical premarket_analysis rows (pre-PR shipping
    the structured-column writer) have NULL trigger/stop/target columns.
    Rather than parse the prose ``playbook`` text (fragile + error-prone),
    the resolver re-runs the brief's level-map logic against the same
    daily data the brief would have seen. Same source-of-truth function,
    same answer. CLAUDE.md §3.6 — production replay paths, no throwaway
    harnesses.
    """
    from lib.strat_levels import (  # local import to keep top-level light
        SessionLevels, atr_inputs_from_frame, basis_records_params,
        build_session_levels, load_level_params, read_live_level_basis,
        read_session_premarket,
    )

    def _query(sql, params):
        return pd.read_sql(text(sql), engine, params=params)

    def _params():
        # The ticker's level parameters in force on analysis_date (a replay
        # of session D reads the rows effective on D). A failed read raises
        # LevelParamsUnavailable (CLAUDE.md 3.7); pd.read_sql does not
        # swallow errors.
        return load_level_params(_query, [ticker], analysis_date)[ticker.upper()]

    # The session's LIVE level_basis, written by the brief with the row, is
    # the source when present (a replay row is never read); only without
    # one are the levels built from daily bars. A basis that recorded its
    # parameters rebuilds with them and never reads the tables.
    basis = read_live_level_basis(_query, ticker, analysis_date)
    if basis is not None:
        stored = SessionLevels.from_basis(
            basis, params=None if basis_records_params(basis) else _params())
        if stored.status == 'ok':
            return _structured_inputs(stored.to_level_map())

    # Load daily history for this ticker. We want everything up to and
    # NOT including analysis_date so the level map only sees data the
    # brief could have known about premarket.
    daily_sql = text("""
        SELECT date, open, high, low, close, atr_14, atr_5, strat_candle, strat_combo
        FROM market_data_daily
        WHERE ticker = :t AND date < :d
        ORDER BY date
    """)
    df = pd.read_sql(daily_sql, engine, params={'t': ticker.upper(), 'd': str(analysis_date)})
    if df.empty or len(df) < 2:
        logger.warning("derive_level_map: insufficient daily rows for %s before %s (%d)",
                       ticker, analysis_date, len(df))
        return None

    df['Date'] = pd.to_datetime(df['date'])
    df = df.set_index('Date').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
    })

    last = df.iloc[-1]
    # The last completed session's ATR columns; the policy's basis picks
    # one. Missing gives no trigger (reason atr_unavailable), never a
    # percent-only window.
    atrs = atr_inputs_from_frame(df, analysis_date)
    strat_class = str(last.get('strat_candle') or '')
    premarket = read_session_premarket(_query, ticker, analysis_date)

    level_map = build_session_levels(
        ticker, analysis_date, df, atrs, premarket, _params(),
        daily_strat_class=strat_class,
    ).to_level_map()
    return _structured_inputs(level_map)


def _structured_inputs(level_map) -> dict:
    """The structured CALL/PUT columns of one LevelMap."""
    ct = level_map.calls_trigger or {}
    pt = level_map.puts_trigger or {}
    ct_targets = ct.get('targets', []) if ct else []
    pt_targets = pt.get('targets', []) if pt else []
    return {
        'calls_trigger_price': ct.get('trigger_level'),
        'calls_trigger_name':  ct.get('trigger_name'),
        'calls_stop_price':    ct.get('stop'),
        'calls_stop_name':     ct.get('stop_name'),
        'calls_t1_price': ct_targets[0]['price'] if len(ct_targets) >= 1 else None,
        'calls_t2_price': ct_targets[1]['price'] if len(ct_targets) >= 2 else None,
        'calls_t3_price': ct_targets[2]['price'] if len(ct_targets) >= 3 else None,
        'puts_trigger_price': pt.get('trigger_level'),
        'puts_trigger_name':  pt.get('trigger_name'),
        'puts_stop_price':    pt.get('stop'),
        'puts_stop_name':     pt.get('stop_name'),
        'puts_t1_price': pt_targets[0]['price'] if len(pt_targets) >= 1 else None,
        'puts_t2_price': pt_targets[1]['price'] if len(pt_targets) >= 2 else None,
        'puts_t3_price': pt_targets[2]['price'] if len(pt_targets) >= 3 else None,
    }


def resolve_leg(
    direction: str,         # 'call' or 'put'
    trigger_price: Optional[float],
    stop_price: Optional[float],
    target_prices: list[Optional[float]],   # [t1, t2, t3]
    bars: pd.DataFrame,
    notional: float = DEFAULT_NOTIONAL,
) -> LegOutcome:
    """Resolve one leg's outcome by walking RTH bars chronologically.

    bars: DataFrame with columns 'time', 'open', 'high', 'low', 'close',
    sorted ascending by time. RTH only (caller filters).

    Returns a LegOutcome with hit timestamps and pnl. Fields stay None
    when the leg was never triggered or the input prices are missing.

    The touch timestamps, MAE/MFE and the reversal flag describe where price
    went from the trigger and are computed exactly as before. The traded
    outcome (entry_status, fill_price, exit_reason, eod_pnl_pct and
    eod_pnl_dollar) follows rule cross-fill-t1-v1, see :func:`_traded_exit`.
    """
    out = LegOutcome()
    if trigger_price is None or trigger_price <= 0:
        return out
    if bars.empty:
        return out

    is_call = (direction == 'call')
    sign = 1 if is_call else -1
    targets = [t for t in target_prices if t is not None and t > 0]

    # Phase 1: walk for trigger hit
    trigger_idx = None
    for i, bar in bars.iterrows():
        if is_call:
            if bar['high'] >= trigger_price:
                trigger_idx = i
                break
        else:
            if bar['low'] <= trigger_price:
                trigger_idx = i
                break
    if trigger_idx is None:
        # Never triggered — no pnl, no timestamps.
        out.entry_status = 'not_triggered'
        return out
    out.trigger_hit_ts = bars.loc[trigger_idx, 'time']

    # Phase 2: from trigger onwards, walk for stop / each target / EOD
    after = bars.loc[trigger_idx:].reset_index(drop=True)
    if after.empty:
        return out

    # Tracking: which targets have been hit (by index in `targets`)
    target_hit_ts = [None] * len(targets)
    stop_hit_ts = None

    # MAE/MFE accumulators over the post-trigger window
    if is_call:
        mfe_price = trigger_price  # max high seen after trigger
        mae_price = trigger_price  # min low seen after trigger
    else:
        mfe_price = trigger_price
        mae_price = trigger_price

    for _, bar in after.iterrows():
        # MFE / MAE update (always)
        if is_call:
            if bar['high'] > mfe_price:
                mfe_price = bar['high']
            if bar['low'] < mae_price:
                mae_price = bar['low']
        else:
            if bar['low'] < mfe_price:
                mfe_price = bar['low']
            if bar['high'] > mae_price:
                mae_price = bar['high']

        # Targets — earliest hit timestamp wins (don't overwrite)
        for ti, tp in enumerate(targets):
            if target_hit_ts[ti] is not None:
                continue
            if is_call and bar['high'] >= tp:
                target_hit_ts[ti] = bar['time']
            elif not is_call and bar['low'] <= tp:
                target_hit_ts[ti] = bar['time']

        # Stop — earliest hit timestamp
        if stop_hit_ts is None and stop_price is not None and stop_price > 0:
            if is_call and bar['low'] <= stop_price:
                stop_hit_ts = bar['time']
            elif not is_call and bar['high'] >= stop_price:
                stop_hit_ts = bar['time']

    # Populate target hit timestamps
    if len(targets) >= 1: out.t1_hit_ts = target_hit_ts[0]
    if len(targets) >= 2: out.t2_hit_ts = target_hit_ts[1]
    if len(targets) >= 3: out.t3_hit_ts = target_hit_ts[2]
    out.stop_hit_ts = stop_hit_ts
    out.reversal_after_trigger = bool(stop_hit_ts and stop_hit_ts > out.trigger_hit_ts)

    # Time-to-T1
    if out.t1_hit_ts:
        delta_sec = (out.t1_hit_ts - out.trigger_hit_ts).total_seconds()
        out.time_to_t1_min = int(delta_sec / 60)

    # MAE/MFE in % (always positive distances)
    if is_call:
        out.mfe_pct = round((mfe_price - trigger_price) / trigger_price * 100, 4)
        out.mae_pct = round((trigger_price - mae_price) / trigger_price * 100, 4)
    else:
        out.mfe_pct = round((trigger_price - mfe_price) / trigger_price * 100, 4)
        out.mae_pct = round((mae_price - trigger_price) / trigger_price * 100, 4)

    # The traded outcome: rule cross-fill-t1-v1.
    status, fill, exit_price, reason = _traded_exit(
        is_call, trigger_price, stop_price, targets, bars)
    out.entry_status = status
    if status == 'filled':
        out.fill_price = fill
        out.exit_reason = reason
        out.eod_pnl_pct = round(sign * (exit_price - fill) / fill * 100, 4)
        out.eod_pnl_dollar = round(out.eod_pnl_pct / 100.0 * notional, 2)
    return out


def _traded_exit(
    is_call: bool,
    trigger_price: float,
    stop_price: Optional[float],
    targets: list[float],
    bars: pd.DataFrame,
) -> tuple[str, Optional[float], Optional[float], Optional[str]]:
    """Rule cross-fill-t1-v1 for one leg on the session's RTH bars.

    Returns ``(entry_status, fill, exit_price, exit_reason)``:

    - the first bar opens at or beyond the trigger: ``gap_through``, no fill
      (the brief's trigger means a cross, and at a gap there is none);
    - no bar reaches the trigger: ``not_triggered``;
    - the first bar that reaches it fills at the trigger when it opened on
      the near side, else at its own open (a gap after the open);
    - a stop missing or not beyond the fill on the losing side:
      ``invalid_stop``, no exit;
    - targets are those strictly beyond the fill, in their order; T1 is the
      first of them;
    - walking from the fill bar, the stop exits at the stop price (on the
      fill bar, or on a later bar that did not open beyond it) or at a later
      bar's open beyond it, and wins a tie with T1; T1 exits at its price
      only from the bar after the fill, even when that bar opened beyond it;
      otherwise the last RTH close.
    """
    o = bars['open'].to_numpy(dtype=float)
    h = bars['high'].to_numpy(dtype=float)
    lo = bars['low'].to_numpy(dtype=float)
    c = bars['close'].to_numpy(dtype=float)

    if (o[0] >= trigger_price) if is_call else (o[0] <= trigger_price):
        return 'gap_through', None, None, None
    reached = (h >= trigger_price) if is_call else (lo <= trigger_price)
    if not reached.any():
        return 'not_triggered', None, None, None
    i = int(reached.argmax())
    opened_beyond = (o[i] > trigger_price) if is_call else (o[i] < trigger_price)
    fill = float(o[i]) if opened_beyond else float(trigger_price)

    if stop_price is None or not math.isfinite(stop_price) or stop_price <= 0 or (
            (stop_price >= fill) if is_call else (stop_price <= fill)):
        return 'invalid_stop', fill, None, None

    beyond = [t for t in targets if (t > fill if is_call else t < fill)]
    t1 = beyond[0] if beyond else None

    for j in range(i, len(o)):
        stop_touched = (lo[j] <= stop_price) if is_call else (h[j] >= stop_price)
        if stop_touched:
            if j == i:
                return 'filled', fill, float(stop_price), 'stop'
            gap_exit = min(stop_price, o[j]) if is_call else max(stop_price, o[j])
            return 'filled', fill, float(gap_exit), 'stop'
        if j > i and t1 is not None and ((h[j] >= t1) if is_call else (lo[j] <= t1)):
            return 'filled', fill, float(t1), 't1'
    return 'filled', fill, float(c[-1]), 'close'


def _valid_stop(is_call: bool, stop_price: Optional[float], fill: Optional[float]) -> bool:
    """A stop that defines the trade's risk: finite, positive and, once
    there is a fill, beyond it on the losing side."""
    if stop_price is None or not math.isfinite(stop_price) or stop_price <= 0:
        return False
    if fill is None:
        return True
    return stop_price < fill if is_call else stop_price > fill


def _bar_minutes_et(ts) -> int:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize('UTC')
    t = t.tz_convert(_ET)
    return t.hour * 60 + t.minute


def resolve_plan(direction: str, plan: PlanInputs, bars: pd.DataFrame) -> PlanOutcome:
    """Score the brief's exit plan for one side on the session's RTH bars
    (exits spec Design 6).

    Entry: the first bar opens at or beyond the trigger -> ``opened_through``
    (no entry, even if price later comes back and crosses); no bar reaches
    it -> ``no_cross``; the first bar that reaches it starts at or after the
    entry cutoff -> ``late_cross``; otherwise ``entered``, filled at the
    trigger, or at that bar's open when it opened beyond the trigger.

    Each of ``legs`` legs is 1/legs of the position; leg k exits at plan
    target k, a leg with no target (fewer targets than legs) is held to the
    stop or the close. Exits are causal: a target at or behind the fill is
    not an exit (its leg is held), targets count only from the bar after the
    fill bar and fill at their price even on a bar that opened beyond them;
    the stop fills at its price, or at a later bar's open beyond it, and a
    bar touching the stop and a target counts the stop first; legs still
    open exit at the last RTH close. With no valid stop the legs exit at
    their targets or the close, and plan_r is NULL (``stop_unavailable``).

    The plan hit timestamps are touches of the plan targets by the same walk
    as LegOutcome.t1_hit_ts (from the first bar reaching the trigger), not
    exits. A side whose plan was not published (``targets_unavailable``)
    keeps its entry status and fill but no exits, R or hit timestamps.
    """
    out = PlanOutcome()
    is_call = (direction == 'call')
    sign = 1 if is_call else -1
    trigger = plan.trigger_price
    if trigger is None or not math.isfinite(trigger) or trigger <= 0:
        out.entry_status = 'no_trigger'
        out.r_status = PLAN_TARGETS_UNAVAILABLE if (
            plan.target_status not in (None, PLAN_OK)) else PLAN_NOT_ENTERED
        return out
    if bars.empty:
        return out
    if plan.cutoff_minutes is None:
        # No entry cutoff in force: the plan's entry rule cannot be applied.
        out.r_status = PLAN_TARGETS_UNAVAILABLE
        return out

    o = bars['open'].to_numpy(dtype=float)
    h = bars['high'].to_numpy(dtype=float)
    lo = bars['low'].to_numpy(dtype=float)
    c = bars['close'].to_numpy(dtype=float)
    times = list(bars['time'])
    reached = (h >= trigger) if is_call else (lo <= trigger)

    fill = i = None
    if (o[0] >= trigger) if is_call else (o[0] <= trigger):
        out.entry_status = 'opened_through'
    elif not reached.any():
        out.entry_status = 'no_cross'
    else:
        i = int(reached.argmax())
        if _bar_minutes_et(times[i]) >= plan.cutoff_minutes:
            out.entry_status = 'late_cross'
            i = None
        else:
            out.entry_status = 'entered'
            opened_beyond = (o[i] > trigger) if is_call else (o[i] < trigger)
            fill = float(o[i]) if opened_beyond else float(trigger)
            out.fill_price = fill
            out.fill_ts = times[i]

    if not plan.plan_available:
        out.r_status = PLAN_TARGETS_UNAVAILABLE
        return out

    targets = [float(t) for t in plan.targets[:plan.legs]]
    # Plan hit timestamps: the existing walk (first touch from the trigger bar).
    if reached.any():
        first = int(reached.argmax())
        hits = []
        for t in targets[:3]:
            touched = (h[first:] >= t) if is_call else (lo[first:] <= t)
            hits.append(times[first + int(touched.argmax())] if touched.any() else None)
        out.t1_hit_ts, out.t2_hit_ts, out.t3_hit_ts = (hits + [None, None, None])[:3]

    stop_ok = _valid_stop(is_call, plan.stop_price, fill)
    if not stop_ok:
        out.r_status = PLAN_STOP_UNAVAILABLE
    elif out.entry_status != 'entered':
        out.r_status = PLAN_NOT_ENTERED
    else:
        out.r_status = PLAN_OK
    if out.entry_status != 'entered':
        return out

    legs = plan.legs
    leg_target = [targets[k] if k < len(targets) else None for k in range(legs)]
    # A target at or behind the fill is not an exit: the leg is held.
    leg_target = [t if t is not None and (t > fill if is_call else t < fill) else None
                  for t in leg_target]
    exits: list = [None] * legs        # (price, label)
    stop = plan.stop_price if stop_ok else None
    for j in range(i, len(o)):
        if stop is not None and ((lo[j] <= stop) if is_call else (h[j] >= stop)):
            px = stop if j == i else (min(stop, o[j]) if is_call else max(stop, o[j]))
            exits = [e if e is not None else (float(px), 'stop') for e in exits]
            break
        if j > i:
            for k, t in enumerate(leg_target):
                if exits[k] is None and t is not None and ((h[j] >= t) if is_call else (lo[j] <= t)):
                    exits[k] = (t, f't{k + 1}')
        if all(e is not None for e in exits):
            break
    exits = [e if e is not None else (float(c[-1]), 'close') for e in exits]
    out.exit = ','.join(label for _, label in exits)
    if out.r_status == PLAN_OK:
        risk = abs(fill - stop)
        out.r = round(sum(sign * (px - fill) / risk for px, _ in exits) / legs, 4)
    return out


def plan_inputs(side: str, row, basis: Optional[dict], policy_fn) -> PlanInputs:
    """One side's published plan (exits spec Design 6). `side` is 'calls'
    or 'puts'. A v3 level_basis is the source (rebuilt with the values it
    recorded, so the table rows are never read); a v2 basis, which has no
    plan, falls back to the row's structured trigger, stop and t1..t3
    columns with the leg count and cutoff `policy_fn()` returns (the policy
    in force on the session, a LevelParams). A row with no level_basis has
    no plan."""
    from lib.strat_levels import (  # local import to keep top-level light
        ENTRY_CUTOFF_KEY, EXIT_LEGS_KEY, LEVEL_RULE_VERSION, SessionLevels,
        policy_time_minutes,
    )

    def _f(v):
        return float(v) if v is not None and pd.notna(v) else None

    if basis is None:
        return PlanInputs(trigger_price=_f(row.get(f'{side}_trigger_price')),
                          stop_price=_f(row.get(f'{side}_stop_price')),
                          target_status=PLAN_TARGETS_UNAVAILABLE)
    if basis.get('rule_version') == LEVEL_RULE_VERSION:
        sl = SessionLevels.from_basis(basis)
        s = sl.long if side == 'calls' else sl.short
        plan = s.plan or {}
        legs = plan.get('legs')
        return PlanInputs(
            trigger_price=_f(s.trigger['price']) if s.trigger else None,
            stop_price=_f(s.stop['price']) if s.stop else None,
            targets=tuple(float(t['price']) for t in s.targets),
            legs=int(legs) if legs is not None else None,
            cutoff_minutes=policy_time_minutes(plan.get('entry_cutoff_et')),
            # A side with a trigger and no plan has no leg count, so it is
            # targets_unavailable; a side with no trigger is not entered.
            target_status=s.target_status)
    params = policy_fn()
    legs, cutoff = params.param(EXIT_LEGS_KEY), params.param(ENTRY_CUTOFF_KEY)
    ok = legs.ok and cutoff.ok
    return PlanInputs(
        trigger_price=_f(row.get(f'{side}_trigger_price')),
        stop_price=_f(row.get(f'{side}_stop_price')),
        targets=tuple(t for t in (_f(row.get(f'{side}_t{k}_price')) for k in (1, 2, 3))
                      if t is not None),
        legs=int(legs.value) if legs.ok else None,
        cutoff_minutes=int(cutoff.value) if cutoff.ok else None,
        target_status=PLAN_OK if ok else (legs.status if not legs.ok else cutoff.status))


def resolve_one(
    analysis_date: date,
    ticker: str,
    engine,
    notional: float = DEFAULT_NOTIONAL,
    force: bool = False,
) -> tuple[Optional[dict], str]:
    """Resolve outcomes for one (analysis_date, ticker).

    Returns (updates, reason): (dict, 'resolved') on success, else
    (None, reason) with reason one of 'already_resolved' (idempotent
    no-op — not a failure), 'no_row', 'no_setup', 'no_bars'.
    """
    # Pull the row
    row_sql = text("""
        SELECT
            calls_trigger_price, calls_stop_price,
            calls_t1_price, calls_t2_price, calls_t3_price,
            puts_trigger_price, puts_stop_price,
            puts_t1_price, puts_t2_price, puts_t3_price,
            level_basis, outcome_resolved_at
        FROM premarket_analysis
        WHERE analysis_date = :d AND ticker = :t
        LIMIT 1
    """)
    row_df = pd.read_sql(row_sql, engine, params={'d': str(analysis_date), 't': ticker.upper()})
    if row_df.empty:
        logger.info("no premarket_analysis row for %s on %s — skipping", ticker, analysis_date)
        return None, 'no_row'
    row = row_df.iloc[0]

    if row['outcome_resolved_at'] is not None and pd.notna(row['outcome_resolved_at']) and not force:
        logger.info("%s %s already resolved at %s — skipping (use force=True to re-run)",
                    ticker, analysis_date, row['outcome_resolved_at'])
        return None, 'already_resolved'

    # Self-healing fallback: if structured input columns are NULL (e.g.
    # historical row written before the structured-column persistence
    # PR), re-derive the level map from daily data using the same
    # build_level_map() function the brief writer uses, then UPDATE the
    # structured columns in-place. Same source-of-truth, same answer.
    structured_inputs = None
    if (
        (row['calls_trigger_price'] is None or pd.isna(row['calls_trigger_price']))
        and (row['puts_trigger_price'] is None or pd.isna(row['puts_trigger_price']))
    ):
        logger.info("%s %s structured inputs are NULL — deriving from daily data",
                    ticker, analysis_date)
        structured_inputs = derive_level_map_from_daily(ticker, analysis_date, engine)
        if structured_inputs is None or (
            structured_inputs['calls_trigger_price'] is None
            and structured_inputs['puts_trigger_price'] is None
        ):
            logger.info("%s %s level map yielded no triggers — skipping", ticker, analysis_date)
            return None, 'no_setup'
        # Make the row dict look as if these came from the DB so the
        # downstream resolve_leg(...) calls work unchanged.
        row = {**row.to_dict(), **structured_inputs}

    # Pull RTH intraday bars (9:30-16:00 ET = 13:30-20:00 UTC during EDT,
    # 14:30-21:00 UTC during EST). Use ET-aware filtering for DST safety.
    bars_sql = text("""
        SELECT ts AS time, open, high, low, close
        FROM market_data_intraday
        WHERE ticker = :t
          AND (ts AT TIME ZONE 'America/New_York')::date = :d
          AND (ts AT TIME ZONE 'America/New_York')::time >= '09:30'
          AND (ts AT TIME ZONE 'America/New_York')::time <  '16:00'
          AND interval = '1min'
        ORDER BY ts
    """)
    bars = pd.read_sql(bars_sql, engine, params={'t': ticker.upper(), 'd': str(analysis_date)})
    if bars.empty:
        logger.warning("no intraday bars for %s on %s — skipping", ticker, analysis_date)
        return None, 'no_bars'
    bars['time'] = pd.to_datetime(bars['time'], utc=True)

    def _f(v):
        return float(v) if v is not None and pd.notna(v) else None

    calls_out = resolve_leg(
        direction='call',
        trigger_price=_f(row['calls_trigger_price']),
        stop_price=_f(row['calls_stop_price']),
        target_prices=[
            _f(row['calls_t1_price']), _f(row['calls_t2_price']), _f(row['calls_t3_price'])
        ],
        bars=bars,
        notional=notional,
    )
    puts_out = resolve_leg(
        direction='put',
        trigger_price=_f(row['puts_trigger_price']),
        stop_price=_f(row['puts_stop_price']),
        target_prices=[
            _f(row['puts_t1_price']), _f(row['puts_t2_price']), _f(row['puts_t3_price'])
        ],
        bars=bars,
        notional=notional,
    )

    # The brief's exit plan (FEAT-STRAT-001 exits spec, Design 6).
    from lib.strat_levels import load_level_params, parse_level_basis

    basis = parse_level_basis(row.get('level_basis') if hasattr(row, 'get') else None)
    _policy = {}

    def _policy_fn():
        # A v2 row's leg count and cutoff: the policy in force on the session.
        # A failed read raises (CLAUDE.md 3.7).
        if 'p' not in _policy:
            _policy['p'] = load_level_params(
                lambda sql, params: pd.read_sql(text(sql), engine, params=params),
                [ticker], analysis_date)[ticker.upper()]
        return _policy['p']

    calls_plan = resolve_plan('call', plan_inputs('calls', row, basis, _policy_fn), bars)
    puts_plan = resolve_plan('put', plan_inputs('puts', row, basis, _policy_fn), bars)

    # Build update payload
    updates = {
        'calls_trigger_hit_ts': calls_out.trigger_hit_ts,
        'calls_t1_hit_ts':      calls_out.t1_hit_ts,
        'calls_t2_hit_ts':      calls_out.t2_hit_ts,
        'calls_t3_hit_ts':      calls_out.t3_hit_ts,
        'calls_stop_hit_ts':    calls_out.stop_hit_ts,
        'calls_reversal_after_trigger': calls_out.reversal_after_trigger,
        'calls_time_to_t1_min': calls_out.time_to_t1_min,
        'calls_mae_pct':        calls_out.mae_pct,
        'calls_mfe_pct':        calls_out.mfe_pct,
        'calls_eod_pnl_pct':    calls_out.eod_pnl_pct,
        'calls_eod_pnl_dollar': calls_out.eod_pnl_dollar,
        'puts_trigger_hit_ts':  puts_out.trigger_hit_ts,
        'puts_t1_hit_ts':       puts_out.t1_hit_ts,
        'puts_t2_hit_ts':       puts_out.t2_hit_ts,
        'puts_t3_hit_ts':       puts_out.t3_hit_ts,
        'puts_stop_hit_ts':     puts_out.stop_hit_ts,
        'puts_reversal_after_trigger': puts_out.reversal_after_trigger,
        'puts_time_to_t1_min':  puts_out.time_to_t1_min,
        'puts_mae_pct':         puts_out.mae_pct,
        'puts_mfe_pct':         puts_out.mfe_pct,
        'puts_eod_pnl_pct':     puts_out.eod_pnl_pct,
        'puts_eod_pnl_dollar':  puts_out.eod_pnl_dollar,
        # Rule cross-fill-t1-v1 (FEAT-SIGNAL-001): a gap_through,
        # not_triggered or invalid_stop leg binds its status with NULL fill,
        # exit and P&L.
        'calls_entry_status':   calls_out.entry_status,
        'calls_fill_price':     calls_out.fill_price,
        'calls_exit_reason':    calls_out.exit_reason,
        'puts_entry_status':    puts_out.entry_status,
        'puts_fill_price':      puts_out.fill_price,
        'puts_exit_reason':     puts_out.exit_reason,
        **_plan_updates('calls', calls_plan),
        **_plan_updates('puts', puts_plan),
        'outcome_resolved_at':  datetime.utcnow(),
        'outcome_resolver_version': RESOLVER_VERSION,
    }

    # If the fallback re-derived structured inputs, write those too so
    # the row becomes self-describing and future resolver runs skip the
    # re-derivation step.
    if structured_inputs is not None:
        updates.update(structured_inputs)

    update_sql_set_clauses = [
        "calls_trigger_hit_ts = :calls_trigger_hit_ts",
        "calls_t1_hit_ts = :calls_t1_hit_ts",
        "calls_t2_hit_ts = :calls_t2_hit_ts",
        "calls_t3_hit_ts = :calls_t3_hit_ts",
        "calls_stop_hit_ts = :calls_stop_hit_ts",
        "calls_reversal_after_trigger = :calls_reversal_after_trigger",
        "calls_time_to_t1_min = :calls_time_to_t1_min",
        "calls_mae_pct = :calls_mae_pct",
        "calls_mfe_pct = :calls_mfe_pct",
        "calls_eod_pnl_pct = :calls_eod_pnl_pct",
        "calls_eod_pnl_dollar = :calls_eod_pnl_dollar",
        "puts_trigger_hit_ts = :puts_trigger_hit_ts",
        "puts_t1_hit_ts = :puts_t1_hit_ts",
        "puts_t2_hit_ts = :puts_t2_hit_ts",
        "puts_t3_hit_ts = :puts_t3_hit_ts",
        "puts_stop_hit_ts = :puts_stop_hit_ts",
        "puts_reversal_after_trigger = :puts_reversal_after_trigger",
        "puts_time_to_t1_min = :puts_time_to_t1_min",
        "puts_mae_pct = :puts_mae_pct",
        "puts_mfe_pct = :puts_mfe_pct",
        "puts_eod_pnl_pct = :puts_eod_pnl_pct",
        "puts_eod_pnl_dollar = :puts_eod_pnl_dollar",
        "calls_entry_status = :calls_entry_status",
        "calls_fill_price = :calls_fill_price",
        "calls_exit_reason = :calls_exit_reason",
        "puts_entry_status = :puts_entry_status",
        "puts_fill_price = :puts_fill_price",
        "puts_exit_reason = :puts_exit_reason",
        *(f"{col} = :{col}" for side in ('calls', 'puts') for col in _plan_columns(side)),
        "outcome_resolved_at = :outcome_resolved_at",
        "outcome_resolver_version = :outcome_resolver_version",
    ]
    if structured_inputs is not None:
        update_sql_set_clauses.extend([
            "calls_trigger_price = :calls_trigger_price",
            "calls_trigger_name = :calls_trigger_name",
            "calls_stop_price = :calls_stop_price",
            "calls_stop_name = :calls_stop_name",
            "calls_t1_price = :calls_t1_price",
            "calls_t2_price = :calls_t2_price",
            "calls_t3_price = :calls_t3_price",
            "puts_trigger_price = :puts_trigger_price",
            "puts_trigger_name = :puts_trigger_name",
            "puts_stop_price = :puts_stop_price",
            "puts_stop_name = :puts_stop_name",
            "puts_t1_price = :puts_t1_price",
            "puts_t2_price = :puts_t2_price",
            "puts_t3_price = :puts_t3_price",
        ])
    update_sql = text(
        "UPDATE premarket_analysis SET " + ", ".join(update_sql_set_clauses)
        + " WHERE analysis_date = :d AND ticker = :t"
    )

    with engine.begin() as conn:
        conn.execute(update_sql, {**updates, 'd': str(analysis_date), 't': ticker.upper()})
    logger.info("resolved %s %s: calls_pnl=%s%% puts_pnl=%s%%",
                ticker, analysis_date,
                calls_out.eod_pnl_pct, puts_out.eod_pnl_pct)
    return updates, 'resolved'


_PLAN_FIELDS = ('entry_status', 'fill_price', 'fill_ts', 'r', 'r_status',
                't1_hit_ts', 't2_hit_ts', 't3_hit_ts', 'exit')


def _plan_columns(side: str) -> list[str]:
    """The premarket_analysis plan columns of one side, in field order."""
    return [f'{side}_plan_{f}' for f in _PLAN_FIELDS]


def _plan_updates(side: str, plan: PlanOutcome) -> dict:
    return {col: getattr(plan, f) for col, f in zip(_plan_columns(side), _PLAN_FIELDS)}


def pending_dates(engine, today_et: date, lookback_days: int) -> list[date]:
    """Distinct weekday analysis_dates with unresolved rows, oldest first.

    Bounded to `lookback_days` calendar days so dates that can never resolve
    (market holidays — a weekday brief row with no session) age out instead
    of re-attempting forever. Weekend-dated rows (the Sunday brief writes
    rows dated Sunday) are excluded structurally — there is no session to
    resolve them against. Deeper history is reachable via the explicit
    PLAYBOOK_RESOLVE_DATE override.
    """
    floor = today_et - timedelta(days=lookback_days)
    df = pd.read_sql(
        text(
            "SELECT DISTINCT analysis_date FROM premarket_analysis "
            "WHERE outcome_resolved_at IS NULL "
            "  AND analysis_date <= :today AND analysis_date >= :floor "
            "  AND extract(isodow FROM analysis_date) < 6 "
            "ORDER BY analysis_date"
        ),
        engine, params={'today': str(today_et), 'floor': str(floor)},
    )
    # pd.read_sql returns a pandas.Timestamp for a Postgres DATE column, and
    # Timestamp subclasses datetime.datetime which subclasses date, so the
    # naive `isinstance(d, date)` check this used to have is true for BOTH
    # and never normalizes the Timestamp. A Timestamp then compares unequal
    # to every plain `date` it's checked against downstream — `analysis_date
    # == now_et.date()` and the old 2026 holiday-set membership test were
    # both always False for it (Python: comparing a date/datetime across classes
    # is never equal), so classify_date_outcome's benign_pending AND
    # benign_holiday cases were both unreachable from this sweep in
    # production. Check datetime first so a Timestamp gets .date()'d; a
    # genuine plain date (not expected from this query, but harmless if it
    # ever occurs) passes through unchanged.
    return [d.date() if isinstance(d, datetime) else d for d in df['analysis_date']]


def classify_date_outcome(analysis_date: date, n_resolved: int, n_skipped: int,
                          now_et: datetime) -> str:
    """Classify one date's resolution pass:
    'ok' | 'benign_pending' | 'benign_holiday' | 'failed'.

    - 'ok':             at least one row resolved, or nothing to do (rows
                        already resolved / nothing attempted).
    - 'benign_pending': nothing resolved on TODAY's date. Ingestion time
                        varies by weekday (`av-intraday-nightly` lands
                        Tue-Fri sessions ~21:00 ET the same evening, but
                        Monday sessions ~23:00 ET, measured from
                        market_data_intraday.inserted_at), so same-day
                        missing bars are always the expected pre-ingestion
                        race — the next run's sweep picks the date up.
    - 'benign_holiday': nothing resolved on a PAST date that is a known
                        NYSE market holiday. There is no session, so
                        market_data_intraday will never have bars for it
                        — this is the "weekday brief row with no session"
                        case pending_dates() already documents as
                        expected to age out. Without this check every
                        holiday alarmed as 'failed' once a day for the
                        full lookback window (e.g. #1068: 2026-09-07
                        Labor Day fired 'failed' on the 09-08 sweep and
                        would have kept firing daily through 09-21).
    - 'failed':         nothing resolved on a PAST, non-holiday date — a
                        real gap that must turn the run red, not exit 0.
                        This is the silent failure that left every date
                        after 2026-06-19 unresolved for two months. A
                        genuine ingestion outage therefore alarms on the
                        next run (within ~24h), when the date ages into
                        'past'.

    n_skipped must count only rows that could not resolve (missing bars,
    no setup, missing row) — never already-resolved no-ops, so an
    idempotent retry of a fully-resolved date reports 'ok'.
    """
    if n_resolved > 0 or n_skipped == 0:
        return 'ok'
    if analysis_date == now_et.date():
        return 'benign_pending'
    if not is_session(analysis_date):
        return 'benign_holiday'
    return 'failed'


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s :: %(message)s',
    )
    from gcp.database import get_engine, is_cloud_sql_configured

    if not is_cloud_sql_configured():
        logger.error("Cloud SQL not configured; set CLOUD_SQL_CONNECTION_NAME etc.")
        return 1

    raw_tickers = os.environ.get('PLAYBOOK_RESOLVE_TICKERS', '').strip()
    notional = float(os.environ.get('PLAYBOOK_RESOLVE_NOTIONAL', DEFAULT_NOTIONAL))
    force = os.environ.get('PLAYBOOK_RESOLVE_FORCE', '').lower() == 'true'

    engine = get_engine()
    now_et = datetime.now(_ET)

    # Target dates: explicit PLAYBOOK_RESOLVE_DATE, or every unresolved
    # weekday date in the lookback window. The sweep (rather than
    # today-only) is what makes the job self-healing: a date whose bars
    # weren't ingested yet resolves on the next run instead of being
    # orphaned forever (the 2026-06-19 → 2026-08-25 outage mode).
    raw_date = os.environ.get('PLAYBOOK_RESOLVE_DATE')
    if raw_date:
        target_dates = [date.fromisoformat(raw_date)]
    else:
        lookback = int(os.environ.get('PLAYBOOK_RESOLVE_LOOKBACK_DAYS', '14'))
        target_dates = pending_dates(engine, now_et.date(), lookback)
        if not target_dates:
            logger.info("no unresolved dates in the %d-day lookback — nothing to do",
                        lookback)
            return 0

    n_failed_dates = 0
    n_exceptions = 0
    for target_date in target_dates:
        if raw_tickers:
            tickers = [t.strip().upper() for t in raw_tickers.split(',') if t.strip()]
        else:
            df = pd.read_sql(
                text("SELECT DISTINCT ticker FROM premarket_analysis WHERE analysis_date = :d"),
                engine, params={'d': str(target_date)},
            )
            tickers = df['ticker'].tolist()

        logger.info("resolving %s for %d tickers (force=%s notional=$%.0f): %s",
                    target_date, len(tickers), force, notional, ', '.join(tickers))

        n_resolved = 0
        n_skipped = 0
        n_noop = 0
        for ticker in tickers:
            try:
                result, reason = resolve_one(target_date, ticker, engine,
                                             notional=notional, force=force)
                if result is not None:
                    n_resolved += 1
                elif reason == 'already_resolved':
                    # Idempotent retry of a resolved row — success, not a
                    # skip: it must never flip a date to 'failed'.
                    n_noop += 1
                else:
                    n_skipped += 1
            except Exception as exc:
                logger.exception("resolve failed for %s %s: %s", ticker, target_date, exc)
                n_skipped += 1
                n_exceptions += 1

        outcome = classify_date_outcome(target_date, n_resolved, n_skipped, now_et)
        logger.info("done %s: %d resolved, %d already-resolved, %d skipped (%s)",
                    target_date, n_resolved, n_noop, n_skipped, outcome)
        if outcome == 'failed':
            n_failed_dates += 1

    if n_failed_dates or n_exceptions:
        logger.error("run had %d failed date(s) and %d exception(s) — exiting non-zero",
                     n_failed_dates, n_exceptions)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
