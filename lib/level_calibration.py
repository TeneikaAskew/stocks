"""Per-ticker level and plan parameter calibration (FEAT-STRAT-001,
docs/superpowers/specs/2026-11-08-feat-strat-001-per-ticker-params.md,
Design 2).

Every parameter is a statistic of the ticker's own history, in the policy's
ATR basis (the ATR of the last completed session before the measured
session). The statistic's quantile or reach share, its lookback and its
minimum sample are read from level_param_policy (``policy``: the rows in
force, lib.strat_levels.policy_in_force); nothing here holds a distance.

Inputs are dated strictly before the calibration's effective_from: every
function takes ``as_of`` (the effective_from of the rows it produces) and
drops bars dated on or after it, so appending later bars changes no value.

Layers:

* Pure statistics on samples (``quantile``, ``reach_share_value``) and the
  per-parameter samplers (``daily_excursions``, ``wick_excesses``,
  ``clean_premarket_spreads``, ``interval_changes``, ``follow_through``,
  ``persona_outcome``).
* ``replay_triggers`` and ``find_breaks``: the side's trigger each session
  from lib.strat_levels.build_session_levels (daily bars, no premarket
  snapshot, the trigger windows in force that session) and the first RTH bar
  that trades one cent beyond it.
* ``BreakBatch`` and ``BreakBank``: the break outcomes (follow-through,
  fill, adverse excursion, reach) on padded arrays for many breaks at once,
  each break's result from its own bars only, kept per break for reuse.
* ``calibrate``: every Design 2 parameter for one ticker and effective date,
  in the spec's order (windows, breaks, entry buffers, fills, stops and the
  floor, targets; the three one-minute thresholds from their own bars). The
  reference path: everything measured afresh for that date.
* ``HistoryCalibrator``: the same results for many effective dates (history
  mode), each under the policy in force on it, from one pass over the bars.
* ``calibrate_ticker``: on-demand calibration of one ticker (Design 3).
* Evidence rows for the implementation PR (``window_exceedance_by_year``,
  ``premarket_drops``, ``break_counts_by_year``).
* ``load_calibration_universe``: the tickers the job calibrates.

Statuses (the ticker_level_params CHECK constraint): ok,
insufficient_history (fewer samples than the policy minimum; sample_n is the
count found), input_unavailable (the ATR in the policy basis is missing for
every session in the lookback, or an upstream parameter this one is
measured with is not ok), no_positive_target (a target that is not above
zero R or not above the persona's previous target, and every target after
it).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from datetime import date as date_type, time
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from lib.strat_levels import (
    LEVEL_CLUSTER_KEY, MIN_STOP_KEY, PARAM_OK, PM_SPIKE_KEY, PM_STALE_PRINT_KEY,
    POLICY_SEEDED_KEYS, LevelParam, LevelParams, LevelParamsUnavailable, build_session_levels, entry_buffer_key, persona_stop_price, policy_atr_basis,
    price_cents, stop_key, target_key, trigger_window_key,
)

logger = logging.getLogger(__name__)

INSUFFICIENT_HISTORY = 'insufficient_history'
INPUT_UNAVAILABLE = 'input_unavailable'
NO_POSITIVE_TARGET = 'no_positive_target'

PERSONAS = ('aggressive', 'neutral', 'conservative')
SIDES = ('long', 'short')

PREMARKET_START = time(4, 0)
RTH_OPEN = time(9, 30)


# ── results ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Calibrated:
    """One parameter's calibration for one ticker and effective date."""
    key: str
    status: str
    value: Optional[float]
    sample_n: int
    method_id: Optional[str]
    input_from: Optional[str] = None
    input_to: Optional[str] = None

    def __post_init__(self):
        if (self.status == PARAM_OK) != (self.value is not None):
            raise ValueError(f"{self.key}: value must be set exactly when status is ok "
                             f"(status {self.status}, value {self.value})")

    @property
    def ok(self) -> bool:
        return self.status == PARAM_OK


def _iso(d) -> Optional[str]:
    if d is None:
        return None
    return pd.Timestamp(d).date().isoformat()


def _result(key: str, policy_row: dict, status: str, value: Optional[float], n: int,
            dates: Sequence) -> Calibrated:
    dates = [d for d in dates if d is not None]
    return Calibrated(
        key=key, status=status,
        value=(float(value) if status == PARAM_OK else None),
        sample_n=int(n), method_id=policy_row.get('method_id'),
        input_from=_iso(min(dates)) if dates else None,
        input_to=_iso(max(dates)) if dates else None,
    )


def _policy(policy: Dict[str, dict], key: str) -> dict:
    row = policy.get(key)
    if row is None:
        raise KeyError(f"level_param_policy has no row in force for {key}")
    return row


def _q(row: dict) -> float:
    q = row.get('statistic_q')
    if q is None:
        raise ValueError(f"{row.get('param_key')}: policy row has no statistic_q")
    return float(q)


# ── statistics ───────────────────────────────────────────────────────────


def quantile(values: Iterable[float], q: float) -> float:
    """The smallest sample value at or above which no more than 1 - q of the
    samples lie (the inverted CDF): an observed value, so a window at
    quantile q is a distance the ticker's move stayed inside on at least q
    of its sessions."""
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        raise ValueError("quantile of no samples")
    return float(np.quantile(arr, q, method='inverted_cdf'))


def reach_share_value(reaches: Iterable[float], share: float) -> float:
    """The largest value that at least `share` of the samples reached (the
    sample value of rank ceil(share x n) from the top)."""
    arr = np.sort(np.asarray(list(reaches), dtype=float))[::-1]
    if not len(arr):
        raise ValueError("reach share of no samples")
    k = max(math.ceil(share * len(arr)), 1)
    return float(arr[k - 1])


def _stat(key: str, row: dict, samples: List[float], dates: Sequence, *, n: Optional[int] = None,
          value_fn: Optional[Callable[[List[float]], float]] = None) -> Calibrated:
    n = len(samples) if n is None else n
    if n < int(row['min_sample']):
        return _result(key, row, INSUFFICIENT_HISTORY, None, n, dates)
    value = value_fn(samples) if value_fn else quantile(samples, _q(row))
    return _result(key, row, PARAM_OK, value, n, dates)


# ── inputs ───────────────────────────────────────────────────────────────


def normalize_daily(daily: pd.DataFrame, atr_col: str, as_of) -> pd.DataFrame:
    """Daily bars dated strictly before `as_of`, one row per session on a
    date index, with columns high, low, close, atr (the policy-basis ATR),
    prior_close and prior_atr (the previous session's close and ATR) and
    prior_sma_200 (the previous session's stored sma_200 at the two decimals
    the planner reads it with, lib.agents.summarizers; NaN when the frame
    carries no sma_200)."""
    df = daily.copy()
    if 'date' in df.columns:
        df = df.set_index('date')
    df.index = pd.to_datetime(df.index).normalize()
    df.columns = [str(c).lower() for c in df.columns]
    atr_name = atr_col.lower()
    if atr_name not in df.columns:
        alias = {'atr_14': 'atr14', 'atr_5': 'atr5'}.get(atr_name)
        atr_name = alias if alias in df.columns else atr_name
    if atr_name not in df.columns:
        raise KeyError(f"daily bars carry no {atr_col} column")
    sma_name = next((c for c in ('sma_200', 'sma200') if c in df.columns), None)
    df = df[df.index < pd.Timestamp(as_of)].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    out = pd.DataFrame({
        'open': pd.to_numeric(df.get('open'), errors='coerce') if 'open' in df else np.nan,
        'high': pd.to_numeric(df['high'], errors='coerce'),
        'low': pd.to_numeric(df['low'], errors='coerce'),
        'close': pd.to_numeric(df['close'], errors='coerce'),
        'atr': pd.to_numeric(df[atr_name], errors='coerce'),
        'sma_200': (pd.to_numeric(df[sma_name], errors='coerce') if sma_name else np.nan),
    }, index=df.index)
    out = out[out['close'].notna()]
    out['prior_close'] = out['close'].shift(1)
    out['prior_atr'] = out['atr'].shift(1)
    out['prior_sma_200'] = out['sma_200'].shift(1).round(2)
    return out


def normalize_minutes(minutes: Optional[pd.DataFrame], as_of) -> pd.DataFrame:
    """One-minute bars (timestamp, open, high, low, close[, volume]) in ET,
    dated strictly before `as_of`, with session date and time-of-day."""
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'session', 'tod']
    if minutes is None or len(minutes) == 0:
        return pd.DataFrame(columns=cols)
    m = minutes.copy()
    m.columns = [str(c).lower() for c in m.columns]
    ts = pd.to_datetime(m['timestamp'])
    if getattr(ts.dt, 'tz', None) is not None:
        # Aware instants: converted to Eastern wall time, never relabelled.
        from lib.eastern_time import utc_to_eastern_naive  # noqa: PLC0415
        ts = utc_to_eastern_naive(ts)
    m['timestamp'] = ts
    for c in ('open', 'high', 'low', 'close'):
        m[c] = pd.to_numeric(m[c], errors='coerce').astype(float)
    m['session'] = ts.dt.normalize()
    m['tod'] = ts.dt.time
    m = m[m['session'] < pd.Timestamp(as_of)]
    return m.sort_values('timestamp').reset_index(drop=True)[cols]


def daily_before(daily: pd.DataFrame, as_of) -> pd.DataFrame:
    """The caller's daily frame, unchanged in shape, cut to rows dated
    strictly before `as_of` (what build_session_levels reads)."""
    dates = pd.to_datetime(daily['date'] if 'date' in daily.columns else daily.index)
    return daily[np.asarray(pd.DatetimeIndex(dates).normalize() < pd.Timestamp(as_of))]


def _rth(m: pd.DataFrame) -> pd.DataFrame:
    """Regular-session bars, bounded by each session's actual NYSE open and
    close (lib.eastern_time.session_schedule): 13:00 ET on half days, so
    after-hours bars past an early close are not regular-session samples
    (Codex P2 on e4bb463e). Bars on a day that is not a session are none."""
    if not len(m):
        return m
    from lib.eastern_time import session_schedule, utc_to_eastern_naive  # noqa: PLC0415
    sched = session_schedule(m['session'].min().date(), m['session'].max().date())
    day = pd.DatetimeIndex(sched.index).normalize()
    opens = pd.Series(utc_to_eastern_naive(sched['market_open']).to_numpy(), index=day)
    closes = pd.Series(utc_to_eastern_naive(sched['market_close']).to_numpy(), index=day)
    ts = pd.to_datetime(m['timestamp'])
    lo, hi = m['session'].map(opens), m['session'].map(closes)
    return m[(ts >= lo) & (ts < hi)]


def _premarket(m: pd.DataFrame) -> pd.DataFrame:
    return m[(m['tod'] >= PREMARKET_START) & (m['tod'] < RTH_OPEN)]


def _lookback_sessions(d: pd.DataFrame, n: int) -> pd.DatetimeIndex:
    return d.index[-int(n):] if n else d.index[:0]


# ── trigger windows (daily bars) ─────────────────────────────────────────


def daily_excursions(d: pd.DataFrame, side: str) -> pd.Series:
    """Per session: (high - prior close) / prior ATR for long, (prior close
    - low) / prior ATR for short; sessions without a positive prior ATR are
    left out."""
    ok = d['prior_atr'].notna() & (d['prior_atr'] > 0) & d['prior_close'].notna()
    if side == 'long':
        x = (d['high'] - d['prior_close']) / d['prior_atr']
    else:
        x = (d['prior_close'] - d['low']) / d['prior_atr']
    return x[ok & x.notna()]


def trigger_window(d: pd.DataFrame, policy: Dict[str, dict], side: str) -> Calibrated:
    key = trigger_window_key(side)
    row = _policy(policy, key)
    # Bound to the lookback's sessions first, so a session with no usable
    # prior ATR inside it is a missing sample, not replaced by an older one.
    exc = daily_excursions(d.iloc[-int(row['lookback_sessions']):], side)
    if len(d) > 1 and exc.empty and d['prior_atr'].notna().sum() == 0:
        return _result(key, row, INPUT_UNAVAILABLE, None, 0, [])
    return _stat(key, row, list(exc.values), list(exc.index))


def _window_params(ticker: str, session, atr_basis: str, windows: Dict[str, Calibrated],
                   policy: Dict[str, dict]) -> LevelParams:
    """The LevelParams a replayed session's build reads: the two trigger
    windows in force that session (the other keys are not read by the side
    picks)."""
    params = {}
    for side in SIDES:
        key = trigger_window_key(side)
        c = windows[side]
        row = policy.get(key, {})
        params[key] = LevelParam(
            key=key, status=c.status, value=c.value, ticker=ticker,
            effective_from=_iso(session), method_id=c.method_id, sample_n=c.sample_n,
            min_sample=row.get('min_sample'), statistic_q=row.get('statistic_q'),
            lookback_sessions=row.get('lookback_sessions'), input_from=c.input_from,
            input_to=c.input_to, atr_basis=atr_basis,
        )
    return LevelParams(ticker=ticker, session_date=pd.Timestamp(session).date(),
                       atr_basis=atr_basis, policy_effective_from=None, params=params)


# ── one-minute thresholds ────────────────────────────────────────────────


def wick_excesses(bars: pd.DataFrame) -> np.ndarray:
    """For each bar of one session, in price units: min(high - own body top,
    high - the highest body top of the two bars each side), and the mirror
    for lows, the same rule lib.indicators.calculate_premarket_context flags
    a spike with. Returns highs' and lows' excesses together."""
    o, c = bars['open'].reset_index(drop=True), bars['close'].reset_index(drop=True)
    h, lo = bars['high'].reset_index(drop=True), bars['low'].reset_index(drop=True)
    body_hi = pd.concat([o, c], axis=1).max(axis=1)
    body_lo = pd.concat([o, c], axis=1).min(axis=1)
    shifts = (-2, -1, 1, 2)
    nb_hi = pd.concat([body_hi.shift(s) for s in shifts], axis=1).max(axis=1)
    nb_lo = pd.concat([body_lo.shift(s) for s in shifts], axis=1).min(axis=1)
    up = np.minimum(h - body_hi, h - nb_hi)
    dn = np.minimum(body_lo - lo, nb_lo - lo)
    out = pd.concat([up, dn]).to_numpy(dtype=float)
    return out[np.isfinite(out)]


def _session_minutes(m: pd.DataFrame, sessions: pd.DatetimeIndex) -> Dict[pd.Timestamp, pd.DataFrame]:
    want = set(sessions)
    return {s: g for s, g in m.groupby('session') if s in want}


def pm_spike(d: pd.DataFrame, m: pd.DataFrame, policy: Dict[str, dict]) -> Calibrated:
    row = _policy(policy, PM_SPIKE_KEY)
    min_bars = int(row['extra'].get('min_bars_per_session') or 0)
    sessions = _lookback_sessions(d, row['lookback_sessions'])
    samples, used = [], []
    # Spec revision 2: the population is the premarket bars the filter judges.
    for s, g in _session_minutes(_premarket(m), sessions).items():
        atr = d.at[s, 'prior_atr']
        if len(g) < min_bars or not (atr == atr and atr > 0):
            continue
        x = wick_excesses(g) / atr
        if len(x):
            samples.extend(list(x))
            used.append(s)
    return _stat(PM_SPIKE_KEY, row, samples, used, n=len(used))


def cents_array(values) -> np.ndarray:
    """lib.strat_levels.price_cents of every value, as int64, computed once
    per distinct value (prices repeat heavily across one-minute bars)."""
    a = np.asarray(values, dtype=float)
    if not len(a):
        return np.zeros(0, dtype=np.int64)
    uniq, inv = np.unique(a, return_inverse=True)
    return np.array([price_cents(v) for v in uniq], dtype=np.int64)[inv.reshape(-1)]


@dataclass(frozen=True)
class SpreadParts:
    """One session's premarket bars, measured once for the stale-print
    population: each bar's spread around its open-close midpoint, whether it
    printed the prior close's cent, and the four wick distances the spike
    rule compares with its threshold (own body and neighbour bodies, high
    and low side). clean_spreads(parts, spike_price) applies the rule."""
    spread: np.ndarray
    echo: np.ndarray
    up_own: np.ndarray
    up_nb: np.ndarray
    dn_own: np.ndarray
    dn_nb: np.ndarray


def premarket_spread_parts(bars: pd.DataFrame, prior_close: float) -> SpreadParts:
    b = bars.reset_index(drop=True)
    pc = price_cents(prior_close)
    echo = np.zeros(len(b), dtype=bool)
    for col in ('open', 'high', 'low', 'close'):
        v = b[col].to_numpy(dtype=float)
        ok = v == v
        c = np.zeros(len(v), dtype=np.int64)
        c[ok] = cents_array(v[ok])
        echo |= ok & (c == pc)
    body_hi = b[['open', 'close']].max(axis=1)
    body_lo = b[['open', 'close']].min(axis=1)
    shifts = (-2, -1, 1, 2)
    nb_hi = pd.concat([body_hi.shift(s) for s in shifts], axis=1).max(axis=1)
    nb_lo = pd.concat([body_lo.shift(s) for s in shifts], axis=1).min(axis=1)
    mid = (b['open'] + b['close']) / 2
    return SpreadParts(
        spread=np.maximum(b['high'] - mid, mid - b['low']).to_numpy(dtype=float),
        echo=echo,
        up_own=(b['high'] - body_hi).to_numpy(dtype=float),
        up_nb=(b['high'] - nb_hi).to_numpy(dtype=float),
        dn_own=(body_lo - b['low']).to_numpy(dtype=float),
        dn_nb=(nb_lo - b['low']).to_numpy(dtype=float),
    )


def clean_spreads(parts: SpreadParts, spike_price: float) -> np.ndarray:
    spike = (((parts.up_own > spike_price) & (parts.up_nb > spike_price))
             | ((parts.dn_own > spike_price) & (parts.dn_nb > spike_price)))
    out = parts.spread[~(parts.echo | spike)]
    return out[np.isfinite(out)]


def clean_premarket_spreads(bars: pd.DataFrame, prior_close: float, spike_price: float) -> np.ndarray:
    """max(high - midpoint, midpoint - low) of each premarket bar with no
    print on the prior close's cent and no wick beyond `spike_price` (the
    spike rule at the ticker's calibrated pm_spike_atr), where the midpoint
    is the bar's open-close midpoint, the one the stale-print rule measures
    from."""
    return clean_spreads(premarket_spread_parts(bars, prior_close), spike_price)


def pm_stale_print(d: pd.DataFrame, m: pd.DataFrame, policy: Dict[str, dict],
                   spike: Calibrated) -> Calibrated:
    """Clean premarket bars exclude the spike rule's flags at the ticker's
    calibrated pm_spike_atr; with that parameter not ok there is no clean
    population and the status is the spike's (insufficient_history) or
    input_unavailable."""
    row = _policy(policy, PM_STALE_PRINT_KEY)
    if not spike.ok:
        status = spike.status if spike.status == INSUFFICIENT_HISTORY else INPUT_UNAVAILABLE
        return _result(PM_STALE_PRINT_KEY, row, status, None, 0, [])
    min_bars = int(row['extra'].get('min_bars_per_session') or 0)
    sessions = _lookback_sessions(d, row['lookback_sessions'])
    samples, used = [], []
    for s, g in _session_minutes(_premarket(m), sessions).items():
        atr, pc = d.at[s, 'prior_atr'], d.at[s, 'prior_close']
        if len(g) < min_bars or not (atr == atr and atr > 0) or not pc == pc:
            continue
        x = clean_premarket_spreads(g, pc, spike.value * atr) / atr
        if len(x):  # a session whose every bar was excluded has no clean bar
            samples.extend(list(x))
            used.append(s)
    return _stat(PM_STALE_PRINT_KEY, row, samples, used, n=len(used))


def interval_changes(bars: pd.DataFrame, minutes: int) -> np.ndarray:
    """Absolute close-to-close change between consecutive `minutes`-minute
    RTH intervals of one session (each interval's last close). Only adjacent
    intervals give a change: across an interval with no bar the move spans
    more than `minutes` and is left out."""
    t = bars['timestamp']
    since_open = (t - t.dt.normalize() - pd.Timedelta(hours=RTH_OPEN.hour, minutes=RTH_OPEN.minute))
    bucket = (since_open // pd.Timedelta(minutes=int(minutes))).to_numpy()
    last = bars.assign(_b=bucket).groupby('_b')['close'].last()
    idx = last.index.to_numpy()
    closes = last.to_numpy(dtype=float)
    adjacent = np.diff(idx) == 1
    return np.abs(np.diff(closes))[adjacent]


def level_cluster(d: pd.DataFrame, m: pd.DataFrame, policy: Dict[str, dict]) -> Calibrated:
    row = _policy(policy, LEVEL_CLUSTER_KEY)
    mins = int(row['extra'].get('interval_minutes') or 0)
    if mins <= 0:
        raise ValueError("level_cluster_atr policy names no interval_minutes")
    sessions = _lookback_sessions(d, row['lookback_sessions'])
    samples, used = [], []
    for s, g in _session_minutes(_rth(m), sessions).items():
        atr = d.at[s, 'prior_atr']
        ch = interval_changes(g, mins)
        if not len(ch) or not (atr == atr and atr > 0):
            continue
        samples.extend(list(ch / atr))
        used.append(s)
    return _stat(LEVEL_CLUSTER_KEY, row, samples, used, n=len(used))


# ── breaks ───────────────────────────────────────────────────────────────


@dataclass
class Break:
    """The first RTH bar of `session` that trades one cent beyond `side`'s
    trigger, and the session's RTH bars from that bar on (index 0)."""
    session: pd.Timestamp
    side: str
    trigger: float
    atr: float
    held: bool
    bars: pd.DataFrame = field(repr=False)
    # The structure the planner tightens the conservative stop to on this
    # side: the session's 200-day SMA (as of the prior session) and the
    # builder's stop anchor for the side (lib.strat_levels.persona_stop_price).
    structure: tuple = ()
    # (timestamps ns, high, low, high cents, low cents) of `bars`, filled by
    # find_breaks or on first use.
    arrays: Optional[tuple] = field(default=None, repr=False, compare=False)

    @property
    def sign(self) -> float:
        return 1.0 if self.side == 'long' else -1.0

    def bar_arrays(self) -> tuple:
        if self.arrays is None:
            h = self.bars['high'].to_numpy(dtype=float)
            lo = self.bars['low'].to_numpy(dtype=float)
            ts = pd.DatetimeIndex(self.bars['timestamp']).asi8
            self.arrays = (ts, h, lo, cents_array(h), cents_array(lo))
        return self.arrays


def replay_trigger(ticker: str, daily: pd.DataFrame, before: pd.DataFrame, policy: Dict[str, dict],
                   session: pd.Timestamp, atr_basis: str) -> dict:
    """One session's long and short trigger and stop as
    lib.strat_levels.build_session_levels picks them from the daily bars
    before the session (`daily`, cut to the session by the builder; `before`,
    the normalized bars before it), with no premarket snapshot (reference =
    the prior close) and the trigger windows calibrated from the excursions
    before it."""
    windows = {side: trigger_window(before, policy, side) for side in SIDES}
    atr = before['atr'].iloc[-1] if len(before) else None
    atrs = {'atr_14': None, 'atr_5': None}
    atrs[atr_basis] = float(atr) if atr == atr and atr is not None else None
    lp = _window_params(ticker, session, atr_basis, windows, policy)
    sl = build_session_levels(ticker, session.date(), daily, atrs, None, lp)
    out = {side: (float(sl.side(side).trigger['price']) if sl.side(side).trigger else None)
           for side in SIDES}
    for side in SIDES:
        stop = sl.side(side).stop
        out[f'{side}_stop'] = float(stop['price']) if stop else None
    out['atr'] = atrs[atr_basis]
    return out


def replay_triggers(ticker: str, daily: pd.DataFrame, d: pd.DataFrame, policy: Dict[str, dict],
                    sessions: Iterable[pd.Timestamp], atr_basis: str,
                    window_policy_at: Optional[Callable[[pd.Timestamp], Dict[str, dict]]] = None
                    ) -> Dict[pd.Timestamp, dict]:
    """Each session's long and short trigger (replay_trigger), the trigger
    windows in force that session calibrated from the excursions before it
    under the policy in force that session (`window_policy_at(session)`;
    None: `policy` for every session). Design 2 defines a break by the
    parameters in force on its own session, so a policy change effective D
    never rewrites the breaks of the sessions before D."""
    return {s: replay_trigger(ticker, daily, d[d.index < s],
                              window_policy_at(s) if window_policy_at else policy, s, atr_basis)
            for s in sessions}


def session_breaks(s: pd.Timestamp, trig: dict, bars: Optional[pd.DataFrame], close: float,
                   sma: Optional[float], cents: Optional[tuple] = None) -> List[Break]:
    """The long and short break of one session (find_breaks for one
    session). `cents` is (high cents, low cents) of `bars` when the caller
    has them."""
    atr = trig.get('atr')
    if bars is None or not len(bars) or not (atr and atr > 0):
        return []
    h = bars['high'].to_numpy(dtype=float)
    lo = bars['low'].to_numpy(dtype=float)
    hc, lc = cents if cents is not None else (cents_array(h), cents_array(lo))
    ts = pd.DatetimeIndex(bars['timestamp']).asi8
    out = []
    for side in SIDES:
        t = trig.get(side)
        if t is None:
            continue
        tc = price_cents(t)
        hit = hc > tc if side == 'long' else lc < tc
        if not hit.any():
            continue
        i = int(np.argmax(hit))
        held = (price_cents(close) > tc) if side == 'long' else (price_cents(close) < tc)
        out.append(Break(session=s, side=side, trigger=float(t), atr=float(atr),
                         held=bool(held), bars=bars.iloc[i:].reset_index(drop=True),
                         structure=(sma, trig.get(f'{side}_stop')),
                         arrays=(ts[i:], h[i:], lo[i:], hc[i:], lc[i:])))
    return out


def _prior_sma(d: pd.DataFrame, s) -> Optional[float]:
    sma = d.at[s, 'prior_sma_200'] if 'prior_sma_200' in d.columns else None
    return float(sma) if sma is not None and sma == sma else None


def find_breaks(d: pd.DataFrame, m: pd.DataFrame,
                triggers: Dict[pd.Timestamp, dict]) -> List[Break]:
    """The break of each session and side whose trigger exists: the first
    RTH bar whose high (long) or low (short) is one cent or more beyond the
    trigger's cent. A held break's session close is beyond the trigger on
    its side."""
    out = []
    by_session = dict(tuple(_rth(m).groupby('session')))
    for s, trig in sorted(triggers.items()):
        if s not in d.index:
            continue
        out.extend(session_breaks(s, trig, by_session.get(s), d.at[s, 'close'], _prior_sma(d, s)))
    return out


# Break outcomes are computed for many breaks at once on padded arrays
# (BreakBatch): row i is break i's bars from its break bar on, padded with
# invalid cells. Every rule reads only a row's own valid cells, so a row's
# result does not depend on which other breaks share the batch.

_NS_PER_MINUTE = int(pd.Timedelta(minutes=1).value)


class BreakBatch:
    """Breaks as padded arrays. `rows(idx)` takes a sub-batch."""

    def __init__(self, breaks: Sequence[Break] = (), *, _arrays: Optional[dict] = None):
        if _arrays is not None:
            self.__dict__.update(_arrays)
            return
        n = len(breaks)
        arrs = [b.bar_arrays() for b in breaks]
        w = max([len(a[0]) for a in arrs] + [1])
        self.ts = np.zeros((n, w), dtype=np.int64)
        self.h = np.full((n, w), np.nan)
        self.lo = np.full((n, w), np.nan)
        self.hc = np.zeros((n, w), dtype=np.int64)
        self.lc = np.zeros((n, w), dtype=np.int64)
        self.valid = np.zeros((n, w), dtype=bool)
        for i, (ts, h, lo, hc, lc) in enumerate(arrs):
            k = len(ts)
            self.ts[i, :k], self.h[i, :k], self.lo[i, :k] = ts, h, lo
            self.hc[i, :k], self.lc[i, :k] = hc, lc
            self.valid[i, :k] = True
        self.trigger = np.array([b.trigger for b in breaks], dtype=float)
        self.atr = np.array([b.atr for b in breaks], dtype=float)
        self.sign = np.array([b.sign for b in breaks], dtype=float)
        self.long = self.sign > 0
        self.held = np.array([b.held for b in breaks], dtype=bool)
        self.tcents = np.array([price_cents(b.trigger) for b in breaks], dtype=np.int64)

    def __len__(self) -> int:
        return len(self.trigger)

    def rows(self, idx) -> 'BreakBatch':
        return BreakBatch(_arrays={k: v[idx] for k, v in self.__dict__.items()})

    @property
    def _col(self) -> np.ndarray:
        return np.arange(self.h.shape[1])[None, :]

    def follow_through(self, minutes: int) -> np.ndarray:
        """F per break: the furthest beyond the trigger, in ATR, from the
        break bar until the first later bar that trades back to the
        trigger's cent, or until `minutes` after the break bar."""
        col = self._col
        late = self.ts >= (self.ts[:, :1] + int(minutes) * _NS_PER_MINUTE)
        back = np.where(self.long[:, None], self.lc <= self.tcents[:, None],
                        self.hc >= self.tcents[:, None]) & (col > 0)
        end = ~self.valid | late | back
        first = np.where(end.any(axis=1), end.argmax(axis=1), end.shape[1])
        run = np.where(self.long[:, None], self.h - self.trigger[:, None],
                       self.trigger[:, None] - self.lo) / self.atr[:, None]
        keep = (col < first[:, None]) & ~np.isnan(run)
        best = np.where(keep, run, -np.inf).max(axis=1, initial=-np.inf)
        return np.maximum(0.0, best) + 0.0

    def fill(self, midpoint: np.ndarray) -> np.ndarray:
        """Fill bar per break (the first bar after the break bar that trades
        at the midpoint), -1 when never filled."""
        mid = np.asarray(midpoint, dtype=float)[:, None]
        hit = self.valid[:, 1:] & (self.lo[:, 1:] <= mid) & (self.h[:, 1:] >= mid)
        if hit.shape[1] == 0:  # only break bars: nothing after them to fill on
            return np.full(hit.shape[0], -1)
        return np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, -1)

    def mae(self, midpoint: np.ndarray, j: np.ndarray) -> np.ndarray:
        """Adverse excursion in ATR from the fill price, the fill bar's
        adverse extreme included, to the close (filled rows)."""
        mid = np.asarray(midpoint, dtype=float)[:, None]
        adverse = np.where(self.long[:, None], mid - self.lo, self.h - mid)
        keep = self.valid & (self._col >= j[:, None])
        worst = np.where(keep, adverse, -np.inf).max(axis=1, initial=-np.inf)
        return np.maximum(worst, 0.0) / self.atr

    def reach(self, midpoint: np.ndarray, j: np.ndarray, stop: np.ndarray,
              risk: np.ndarray) -> np.ndarray:
        """Favourable excursion in R = `risk` (price) on bars after the fill
        bar, before the first bar from the fill bar on that touches `stop`
        (the fill bar's stop, or a bar touching stop and target, counts as
        first)."""
        col = self._col
        mid = np.asarray(midpoint, dtype=float)[:, None]
        stop = np.asarray(stop, dtype=float)[:, None]
        from_fill = self.valid & (col >= j[:, None])
        stopped = from_fill & np.where(self.long[:, None], self.lo <= stop, self.h >= stop)
        first = np.where(stopped.any(axis=1), stopped.argmax(axis=1), stopped.shape[1])
        fav = np.where(self.long[:, None], self.h - mid, mid - self.lo) / np.asarray(risk)[:, None]
        keep = from_fill & (col > j[:, None]) & (col < first[:, None]) & ~np.isnan(fav)
        best = np.where(keep, fav, -np.inf).max(axis=1, initial=-np.inf)
        return np.maximum(0.0, best)


def follow_through(b: Break, minutes: int) -> float:
    """F: the furthest the break ran beyond the trigger, in ATR, from the
    break bar until the first later bar that trades back to the trigger's
    cent or until `minutes` after the break bar, whichever comes first."""
    return float(BreakBatch([b]).follow_through(minutes)[0])


@dataclass(frozen=True)
class Outcome:
    """One persona's trade on one break: unfilled, or filled with its
    adverse excursion (ATR) and its favourable reach (R) before the stop."""
    filled: bool
    mae_atr: Optional[float] = None
    reach_r: Optional[float] = None


def persona_fill(b: Break, midpoint: float) -> Optional[int]:
    """Index of the fill bar: the first bar after the break bar that trades
    at the entry midpoint."""
    j = int(BreakBatch([b]).fill(np.array([midpoint]))[0])
    return j if j >= 0 else None


def persona_outcome(b: Break, midpoint: float, risk_atr: Optional[float] = None, *,
                    stop: Optional[float] = None) -> Outcome:
    """Fill at `midpoint`, then, from the fill bar to the close:

    * mae_atr: the largest adverse excursion from the fill price, the fill
      bar's adverse extreme included (taken as after the fill);
    * reach_r (when `stop`, a price, or `risk_atr` is given): the largest
      favourable excursion, in R = |fill - stop| (or risk_atr x ATR, the
      stop at fill - R), on bars after the fill bar, before a bar that
      touches the stop (a stop touched on the fill bar, or on the same bar
      as a favourable extreme, is taken as first). The fill bar's
      favourable extreme counts toward nothing.
    """
    batch = BreakBatch([b])
    mid = np.array([midpoint], dtype=float)
    j = batch.fill(mid)
    if j[0] < 0:
        return Outcome(filled=False)
    mae = float(batch.mae(mid, j)[0])
    if stop is None and risk_atr is None:
        return Outcome(filled=True, mae_atr=mae)
    if stop is None:
        risk = float(risk_atr) * b.atr
        stop = midpoint - b.sign * risk
    else:
        risk = abs(midpoint - stop)
    reach = float(batch.reach(mid, j, np.array([stop]), np.array([risk]))[0])
    return Outcome(filled=True, mae_atr=mae, reach_r=reach)


def _midpoint(b: Break, lo_atr: float, hi_atr: float) -> float:
    return b.trigger + b.sign * (lo_atr + hi_atr) / 2 * b.atr


def planned_stop(b: Break, persona: str, lo_atr: float, hi_atr: float, stop_atr: float,
                 min_stop_atr: float) -> tuple:
    """(entry midpoint, stop price) the planner would publish for `persona`
    on this break's trigger, with these calibrated values, by the planner's
    own rule (lib.strat_levels.persona_stop_price, the conservative stop
    tightened to the break's structure). A target's reach is measured in
    R = |midpoint - stop|, the R the published plan carries."""
    mid = _midpoint(b, lo_atr, hi_atr)
    return mid, persona_stop_price(persona, b.sign, mid, b.atr, stop_atr, min_stop_atr,
                                   b.structure)


def _not_ok(key: str, row: dict, upstream: Calibrated) -> Calibrated:
    status = upstream.status if upstream.status == INSUFFICIENT_HISTORY else INPUT_UNAVAILABLE
    return _result(key, row, status, None, upstream.sample_n, [])


class BreakBank:
    """Every break one calibration reads, with per-break results kept across
    calibrations: follow-through per follow_through_minutes, and each
    persona's fill, adverse excursion and reach for the last set of values
    they were computed with (a later calibration whose values are the same
    computes only the breaks it has not seen). Results are per break and do
    not depend on which other breaks a calibration reads, so a calibration
    through a bank equals one on a fresh bank of its own breaks."""

    def __init__(self, breaks: Sequence[Break] = ()):
        self.breaks: List[Break] = []
        # Row storage with spare capacity (doubled when full), so adding a
        # session's breaks does not copy every earlier break's bars.
        self._store: Optional[dict] = None
        self._ft: Dict[int, np.ndarray] = {}
        self._fill: Dict[str, tuple] = {}
        self._reach: Dict[str, tuple] = {}
        self.add(breaks)

    @property
    def batch(self) -> Optional[BreakBatch]:
        if self._store is None:
            return None
        n = len(self.breaks)
        return BreakBatch(_arrays={k: v[:n] for k, v in self._store.items()})

    def _reserve(self, rows: int, width: int) -> None:
        st = self._store
        cap, w = (0, 0) if st is None else (len(st['trigger']), st['h'].shape[1])
        if st is not None and rows <= cap and width <= w:
            return
        new_cap, new_w = max(rows, 2 * cap, 64), max(width, w)
        template = BreakBatch([])
        out = {}
        for k, v in template.__dict__.items():
            if v.ndim == 2:
                fill = np.nan if v.dtype.kind == 'f' else (False if v.dtype == bool else 0)
                a = np.full((new_cap, new_w), fill, dtype=v.dtype)
                if st is not None:
                    a[:cap, :w] = st[k]
            else:
                a = np.zeros(new_cap, dtype=v.dtype)
                if st is not None:
                    a[:cap] = st[k]
            out[k] = a
        self._store = out

    def add(self, breaks: Sequence[Break]) -> np.ndarray:
        """Append breaks; returns their ids."""
        start = len(self.breaks)
        if not breaks:
            return np.arange(start, start)
        new = BreakBatch(breaks)
        end = start + len(breaks)
        self._reserve(end, new.h.shape[1])
        for k, v in new.__dict__.items():
            if v.ndim == 2:
                self._store[k][start:end, :v.shape[1]] = v
            else:
                self._store[k][start:end] = v
        self.breaks.extend(breaks)
        for k in list(self._ft):
            self._ft[k] = np.concatenate([self._ft[k], np.full(len(breaks), np.nan)])
        for d in (self._fill, self._reach):
            for k, (key, arrs) in list(d.items()):
                d[k] = (key, tuple(np.concatenate([a, np.full(len(breaks), np.nan)])
                                   for a in arrs))
        return np.arange(start, end)

    def follow_through(self, ids: np.ndarray, minutes: int) -> np.ndarray:
        ft = self._ft.setdefault(int(minutes), np.full(len(self.breaks), np.nan))
        todo = ids[np.isnan(ft[ids])]
        if len(todo):
            ft[todo] = self.batch.rows(todo).follow_through(minutes)
        return ft[ids]

    def _cached(self, store: dict, persona: str, key: tuple, ids: np.ndarray, n_out: int, compute):
        prev = store.get(persona)
        if prev is None or prev[0] != key:
            prev = (key, tuple(np.full(len(self.breaks), np.nan) for _ in range(n_out)))
            store[persona] = prev
        arrs = prev[1]
        todo = ids[np.isnan(arrs[0][ids])]
        if len(todo):
            for a, v in zip(arrs, compute(todo)):
                a[todo] = v
        return tuple(a[ids] for a in arrs)

    def fills(self, ids: np.ndarray, persona: str, lo_atr: float, hi_atr: float) -> tuple:
        """(midpoint, fill bar or -1, adverse excursion in ATR or NaN)."""
        def compute(todo):
            mid = np.array([_midpoint(self.breaks[i], lo_atr, hi_atr) for i in todo])
            sub = self.batch.rows(todo)
            j = sub.fill(mid)
            mae = np.full(len(todo), np.nan)
            ok = j >= 0
            if ok.any():
                mae[ok] = sub.rows(np.flatnonzero(ok)).mae(mid[ok], j[ok])
            return mid, j.astype(float), mae
        mid, j, mae = self._cached(self._fill, persona, (lo_atr, hi_atr), ids, 3, compute)
        return mid, j.astype(int), mae

    def reaches(self, ids: np.ndarray, persona: str, lo_atr: float, hi_atr: float,
                stop_atr: float, min_stop_atr: float) -> np.ndarray:
        """Reach in the planner's R for filled breaks among `ids`."""
        def compute(todo):
            mid, j, _mae = self.fills(todo, persona, lo_atr, hi_atr)
            stops = np.array([planned_stop(self.breaks[i], persona, lo_atr, hi_atr, stop_atr,
                                           min_stop_atr)[1] for i in todo])
            risk = np.abs(mid - stops)
            out = np.full(len(todo), np.nan)
            ok = j >= 0
            if ok.any():
                out[ok] = self.batch.rows(todo[ok]).reach(mid[ok], j[ok], stops[ok], risk[ok])
            return (out,)
        # A filled break's reach is never NaN; an unfilled one's stays NaN,
        # so it is recomputed (cheaply, it is never filled) on a cache hit.
        (out,) = self._cached(self._reach, persona, (lo_atr, hi_atr, stop_atr, min_stop_atr),
                              ids, 1, compute)
        return out


def _span(sessions: np.ndarray) -> list:
    return [sessions.min(), sessions.max()] if len(sessions) else []


def break_params(breaks: List[Break], policy: Dict[str, dict], *,
                 bank: Optional[BreakBank] = None, ids: Optional[np.ndarray] = None,
                 session_index: Optional[pd.DatetimeIndex] = None
                 ) -> Dict[str, Calibrated]:
    """Entry buffers, stops, the floor and targets from the breaks (both
    sides pooled), in the spec's order. A parameter measured with another
    that is not ok carries that one's status. `bank` and `ids` (history
    mode) name the breaks in a BreakBank whose per-break results are reused
    across calibrations; without them the breaks get a bank of their own.

    `session_index` is the daily sessions before the effective date (the
    calibrators pass it): each parameter then takes its statistic over the
    breaks in its own policy row's lookback_sessions only (the breaks given
    cover the longest of them, break_lookback). Without it every given
    break is in every parameter's window (callers that pass one window's
    breaks)."""
    if bank is None:
        bank = BreakBank(breaks)
        ids = np.arange(len(breaks))
    ids = np.asarray(ids, dtype=int)
    out: Dict[str, Calibrated] = {}
    sessions = np.array([bank.breaks[i].session for i in ids], dtype='datetime64[ns]')
    held = (bank.batch.held[ids] if len(ids) else np.zeros(0, dtype=bool))
    n = len(ids)

    def dates(mask=None) -> list:
        return [pd.Timestamp(x) for x in _span(sessions if mask is None else sessions[mask])]

    def window(row: dict) -> np.ndarray:
        """The breaks inside this row's own lookback (Codex P2 on e4bb463e)."""
        if session_index is None:
            return np.ones(n, dtype=bool)
        lb = _lookback_sessions(pd.DataFrame(index=session_index), row['lookback_sessions'])
        if not len(lb):
            return np.zeros(n, dtype=bool)
        return sessions >= np.datetime64(pd.Timestamp(lb[0]), 'ns')

    # Entry buffers: quantiles of follow-through over all breaks.
    for persona in PERSONAS:
        for edge in ('lo', 'hi'):
            key = entry_buffer_key(persona, edge)
            row = _policy(policy, key)
            win = window(row)
            minutes = int(row['extra'].get('follow_through_minutes') or 0)
            if row.get('method_id') == 'at_trigger':
                out[key] = _stat(key, row, [0.0] * int(win.sum()), dates(win),
                                 value_fn=lambda _s: 0.0)
                continue
            ft = bank.follow_through(ids[win], minutes) if win.any() else np.zeros(0)
            out[key] = _stat(key, row, ft, dates(win))

    # Fills at each persona's entry midpoint; stops on filled held breaks.
    fills: Dict[str, np.ndarray] = {}
    maes: Dict[str, np.ndarray] = {}
    for persona in PERSONAS:
        lo, hi = out[entry_buffer_key(persona, 'lo')], out[entry_buffer_key(persona, 'hi')]
        skey = stop_key(persona)
        srow = _policy(policy, skey)
        if not (lo.ok and hi.ok):
            out[skey] = _not_ok(skey, srow, lo if not lo.ok else hi)
            fills[persona] = np.zeros(n, dtype=bool)
            continue
        _mid, j, mae = bank.fills(ids, persona, lo.value, hi.value) if n else \
            (np.zeros(0), np.zeros(0, dtype=int), np.zeros(0))
        fills[persona], maes[persona] = j >= 0, mae
        sel = fills[persona] & held & window(srow)
        out[skey] = _stat(skey, srow, mae[sel], dates(sel))

    mrow = _policy(policy, MIN_STOP_KEY)
    floor_persona = mrow['extra'].get('persona') or 'neutral'
    flo, fhi = out[entry_buffer_key(floor_persona, 'lo')], out[entry_buffer_key(floor_persona, 'hi')]
    if not (flo.ok and fhi.ok):
        out[MIN_STOP_KEY] = _not_ok(MIN_STOP_KEY, mrow, flo if not flo.ok else fhi)
    else:
        sel = fills[floor_persona] & held & window(mrow)
        out[MIN_STOP_KEY] = _stat(MIN_STOP_KEY, mrow, maes[floor_persona][sel], dates(sel))

    # Targets: reach shares on filled breaks, in the R the planner publishes
    # (lib.strat_levels.persona_stop_price). The reaches do not depend on
    # the share, so they are measured once per persona.
    for persona in PERSONAS:
        k = 1
        stop_c, floor_c = out[stop_key(persona)], out[MIN_STOP_KEY]
        prev, blocked, reaches = None, None, None
        sel = fills[persona]
        while target_key(persona, k) in policy:
            key = target_key(persona, k)
            row = _policy(policy, key)
            k += 1
            if blocked is not None:
                out[key] = _result(key, row, blocked.status, None, blocked.sample_n, [])
                continue
            if not (stop_c.ok and floor_c.ok):
                out[key] = _not_ok(key, row, stop_c if not stop_c.ok else floor_c)
                continue
            if reaches is None:
                lo = out[entry_buffer_key(persona, 'lo')].value
                hi = out[entry_buffer_key(persona, 'hi')].value
                reaches = bank.reaches(ids, persona, lo, hi, stop_c.value,
                                       floor_c.value) if n else np.zeros(0)
            in_win = sel & window(row)
            used = dates(in_win)
            share = _q(row)
            c = _stat(key, row, reaches[in_win], used,
                      value_fn=lambda s, share=share: reach_share_value(s, share))
            if c.ok and (c.value <= 0 or (prev is not None and c.value <= prev)):
                c = _result(key, row, NO_POSITIVE_TARGET, None, c.sample_n, used)
                blocked = c
            elif c.ok:
                prev = c.value
            out[key] = c
    return out


# ── one ticker, one effective date ───────────────────────────────────────


def _break_keys(policy: Dict[str, dict]) -> List[str]:
    keys = [entry_buffer_key(p, e) for p in PERSONAS for e in ('lo', 'hi')]
    keys += [stop_key(p) for p in PERSONAS] + [MIN_STOP_KEY]
    for p in PERSONAS:
        k = 1
        while target_key(p, k) in policy:
            keys.append(target_key(p, k))
            k += 1
    return keys


def break_lookback(policy: Dict[str, dict]) -> int:
    """The longest lookback of any break-derived parameter: the breaks a
    calibration reads; break_params cuts each parameter to its own."""
    return max(int(_policy(policy, k)['lookback_sessions'] or 0) for k in _break_keys(policy))


def policy_seeds(policy: Dict[str, dict]) -> Dict[str, Calibrated]:
    """The policy_seed keys (exits in thirds spec, Design 1 and 5): each
    ticker's value is the seed of the policy row in force, status ok, until a
    per-ticker method replaces the row. A policy in force without one of
    these rows, or whose row holds no numeric seed, cannot calibrate."""
    out: Dict[str, Calibrated] = {}
    for key in POLICY_SEEDED_KEYS:
        row = policy.get(key)
        if row is None:
            raise LevelParamsUnavailable(f"level_param_policy has no row in force for {key}")
        seed = (row.get('extra') or {}).get('seed')
        if isinstance(seed, bool) or not isinstance(seed, (int, float)) or not math.isfinite(seed):
            raise LevelParamsUnavailable(
                f"level_param_policy {key} (effective {row.get('effective_from')}) holds no numeric seed")
        out[key] = Calibrated(key=key, status=PARAM_OK, value=float(seed), sample_n=0,
                              method_id=row.get('method_id'))
    return out


def calibrate(ticker: str, daily: pd.DataFrame, minutes: Optional[pd.DataFrame],
              policy: Dict[str, dict], as_of,
              window_policy_at: Optional[Callable[[pd.Timestamp], Dict[str, dict]]] = None
              ) -> Dict[str, Calibrated]:
    """Every Design 2 parameter for `ticker`, effective `as_of`, from bars
    dated strictly before it. `daily` carries High, Low, Close and the
    policy's ATR column (atr_14 or atr_5, or ATR14/ATR5); `minutes` the
    one-minute bars (timestamp in ET, open, high, low, close).

    The reference path: everything is measured afresh for `as_of`.
    HistoryCalibrator gives the same results for many effective dates from
    one pass over the bars."""
    as_of = pd.Timestamp(as_of).normalize()
    atr_basis = policy_atr_basis(policy)
    seeds = policy_seeds(policy)
    d = normalize_daily(daily, atr_basis, as_of)
    m = normalize_minutes(minutes, as_of)
    out: Dict[str, Calibrated] = dict(seeds)
    for side in SIDES:
        out[trigger_window_key(side)] = trigger_window(d, policy, side)
    spike = pm_spike(d, m, policy)
    out[PM_SPIKE_KEY] = spike
    out[PM_STALE_PRINT_KEY] = pm_stale_print(d, m, policy, spike)
    out[LEVEL_CLUSTER_KEY] = level_cluster(d, m, policy)

    sessions = _lookback_sessions(d, break_lookback(policy))
    minute_sessions = set(m['session'].unique()) if len(m) else set()
    sessions = [s for s in sessions if s in minute_sessions]
    trig = replay_triggers(ticker, daily_before(daily, as_of), d, policy, sessions, atr_basis,
                           window_policy_at)
    out.update(break_params(find_breaks(d, m, trig), policy, session_index=d.index))
    return out


class HistoryCalibrator:
    """History mode for one ticker: the parameters for many effective dates,
    each from bars strictly before it and under the policy in force on it,
    equal to calibrate() for that date and policy, from one read of the
    bars.

    What does not depend on the effective date is measured once and reused:
    each session's one-minute samples (wick excesses, premarket spread parts,
    interval changes), each session's replayed trigger under a given trigger
    window policy and ATR basis, each session's breaks, and each break's
    follow-through, fill, adverse excursion and reach (BreakBank). Each date
    then cuts the per-session results to its own lookback and takes its
    statistics."""

    def __init__(self, ticker: str, daily: pd.DataFrame, minutes: Optional[pd.DataFrame], before):
        self.ticker = ticker
        self.before = pd.Timestamp(before).normalize()
        self.daily = daily_before(daily, self.before)
        self.m = normalize_minutes(minutes, self.before)
        self.rth = dict(tuple(_rth(self.m).groupby('session'))) if len(self.m) else {}
        self.pm = dict(tuple(_premarket(self.m).groupby('session'))) if len(self.m) else {}
        self.minute_sessions = set(self.m['session'].unique()) if len(self.m) else set()
        self._d: Dict[str, pd.DataFrame] = {}
        self._wick: Dict[pd.Timestamp, np.ndarray] = {}
        self._parts: Dict[pd.Timestamp, SpreadParts] = {}
        self._changes: Dict[tuple, np.ndarray] = {}
        self._rth_cents: Dict[pd.Timestamp, tuple] = {}
        # Per (trigger window policy, ATR basis) and session: the replayed
        # trigger and the session's breaks (ids in the bank of that basis).
        # One bank per basis, so sessions replayed under different window
        # policies pool into one population.
        self._trig: Dict[tuple, dict] = {}
        self._banks: Dict[str, BreakBank] = {}
        self._break_ids: Dict[tuple, np.ndarray] = {}

    def daily_frame(self, atr_basis: str) -> pd.DataFrame:
        if atr_basis not in self._d:
            self._d[atr_basis] = normalize_daily(self.daily, atr_basis, self.before)
        return self._d[atr_basis]

    @staticmethod
    def _cut(d: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
        return d.iloc[:int(d.index.searchsorted(as_of, side='left'))]

    # ── one-minute thresholds ───────────────────────────────────────
    def _pm_spike(self, d: pd.DataFrame, policy: Dict[str, dict]) -> Calibrated:
        row = _policy(policy, PM_SPIKE_KEY)
        min_bars = int(row['extra'].get('min_bars_per_session') or 0)
        samples, used = [], []
        for s in _lookback_sessions(d, row['lookback_sessions']):
            g = self.pm.get(s)  # spec revision 2: premarket bars
            if g is None:
                continue
            atr = d.at[s, 'prior_atr']
            if len(g) < min_bars or not (atr == atr and atr > 0):
                continue
            if s not in self._wick:
                self._wick[s] = wick_excesses(g)
            x = self._wick[s] / atr
            if len(x):
                samples.append(x)
                used.append(s)
        return _stat(PM_SPIKE_KEY, row, np.concatenate(samples) if samples else [], used,
                     n=len(used))

    def _pm_stale_print(self, d: pd.DataFrame, policy: Dict[str, dict],
                        spike: Calibrated) -> Calibrated:
        row = _policy(policy, PM_STALE_PRINT_KEY)
        if not spike.ok:
            status = spike.status if spike.status == INSUFFICIENT_HISTORY else INPUT_UNAVAILABLE
            return _result(PM_STALE_PRINT_KEY, row, status, None, 0, [])
        min_bars = int(row['extra'].get('min_bars_per_session') or 0)
        samples, used = [], []
        for s in _lookback_sessions(d, row['lookback_sessions']):
            g = self.pm.get(s)
            if g is None:
                continue
            atr, pc = d.at[s, 'prior_atr'], d.at[s, 'prior_close']
            if len(g) < min_bars or not (atr == atr and atr > 0) or not pc == pc:
                continue
            if s not in self._parts:
                self._parts[s] = premarket_spread_parts(g, pc)
            x = clean_spreads(self._parts[s], spike.value * atr) / atr
            if len(x):
                samples.append(x)
                used.append(s)
        return _stat(PM_STALE_PRINT_KEY, row, np.concatenate(samples) if samples else [], used,
                     n=len(used))

    def _level_cluster(self, d: pd.DataFrame, policy: Dict[str, dict]) -> Calibrated:
        row = _policy(policy, LEVEL_CLUSTER_KEY)
        mins = int(row['extra'].get('interval_minutes') or 0)
        if mins <= 0:
            raise ValueError("level_cluster_atr policy names no interval_minutes")
        samples, used = [], []
        for s in _lookback_sessions(d, row['lookback_sessions']):
            g = self.rth.get(s)
            if g is None:
                continue
            if (s, mins) not in self._changes:
                self._changes[(s, mins)] = interval_changes(g, mins)
            ch = self._changes[(s, mins)]
            atr = d.at[s, 'prior_atr']
            if not len(ch) or not (atr == atr and atr > 0):
                continue
            samples.append(ch / atr)
            used.append(s)
        return _stat(LEVEL_CLUSTER_KEY, row, np.concatenate(samples) if samples else [], used,
                     n=len(used))

    # ── breaks ───────────────────────────────────────────────────────
    @staticmethod
    def _window_signature(policy: Dict[str, dict], atr_basis: str) -> tuple:
        sig = [atr_basis]
        for side in SIDES:
            r = _policy(policy, trigger_window_key(side))
            sig.append((r.get('method_id'), r.get('statistic_q'), r.get('lookback_sessions'),
                        r.get('min_sample')))
        return tuple(sig)

    def _break_ids_for(self, sessions, policy: Dict[str, dict], atr_basis: str,
                       d_full: pd.DataFrame, window_policy_at=None) -> tuple:
        bank = self._banks.setdefault(atr_basis, BreakBank())
        parts = []
        for s in sessions:
            pol = window_policy_at(s) if window_policy_at else policy
            key = (self._window_signature(pol, atr_basis), s)
            if key not in self._break_ids:
                if key not in self._trig:
                    before = self._cut(d_full, s)
                    self._trig[key] = replay_trigger(self.ticker, self.daily, before, pol, s,
                                                     atr_basis)
                bars = self.rth.get(s)
                if bars is not None and s not in self._rth_cents:
                    self._rth_cents[s] = (cents_array(bars['high'].to_numpy(dtype=float)),
                                          cents_array(bars['low'].to_numpy(dtype=float)))
                brks = session_breaks(s, self._trig[key], bars, d_full.at[s, 'close'],
                                      _prior_sma(d_full, s),
                                      self._rth_cents.get(s)) if s in d_full.index else []
                self._break_ids[key] = bank.add(brks)
            parts.append(self._break_ids[key])
        ids = np.concatenate(parts) if parts else np.zeros(0, dtype=int)
        return bank, ids

    # ── one effective date ───────────────────────────────────────────
    def calibrate(self, policy: Dict[str, dict], as_of,
                  window_policy_at: Optional[Callable[[pd.Timestamp], Dict[str, dict]]] = None
                  ) -> Dict[str, Calibrated]:
        as_of = pd.Timestamp(as_of).normalize()
        if as_of > self.before:
            raise ValueError(f"{as_of.date()} is after the bars this calibrator read "
                             f"(before {self.before.date()})")
        atr_basis = policy_atr_basis(policy)
        seeds = policy_seeds(policy)
        d_full = self.daily_frame(atr_basis)
        d = self._cut(d_full, as_of)
        out: Dict[str, Calibrated] = dict(seeds)
        for side in SIDES:
            out[trigger_window_key(side)] = trigger_window(d, policy, side)
        spike = self._pm_spike(d, policy)
        out[PM_SPIKE_KEY] = spike
        out[PM_STALE_PRINT_KEY] = self._pm_stale_print(d, policy, spike)
        out[LEVEL_CLUSTER_KEY] = self._level_cluster(d, policy)
        sessions = [s for s in _lookback_sessions(d, break_lookback(policy))
                    if s in self.minute_sessions]
        bank, ids = self._break_ids_for(sessions, policy, atr_basis, d_full, window_policy_at)
        out.update(break_params([], policy, bank=bank, ids=ids, session_index=d.index))
        return out


def to_rows(ticker: str, results: Dict[str, Calibrated], policy: Dict[str, dict], effective_from,
            run_id: str, source: str, calibrated_at) -> List[dict]:
    """ticker_level_params rows for one ticker and effective date."""
    atr_basis = policy_atr_basis(policy)
    rows = []
    for key, c in sorted(results.items()):
        rows.append({
            'ticker': ticker.upper(), 'param_key': key, 'value': c.value, 'status': c.status,
            'atr_basis': atr_basis, 'method_id': c.method_id,
            'policy_effective_from': _policy(policy, key).get('effective_from'),
            'sample_n': c.sample_n, 'input_from': c.input_from, 'input_to': c.input_to,
            'effective_from': _iso(effective_from), 'run_id': run_id, 'source': source,
            'calibrated_at': calibrated_at,
        })
    return rows


# ── universe ─────────────────────────────────────────────────────────────

UNIVERSE_KEY = 'calibration_universe'


# ── evidence rows (done_when 4) ─────────────────────────────────────────
#
# What the implementation PR shows beside each calibrated value, computed
# with the same samplers and the production print filter, never a second
# copy of a rule.


def window_exceedance_by_year(daily: pd.DataFrame, atr_col: str, as_of, side: str,
                              window_atr: float) -> pd.DataFrame:
    """Per calendar year, the sessions before `as_of` with a usable prior
    ATR, how many of them the side's excursion from the prior close passed
    `window_atr`, and that share. Columns: year, sessions, passed, share."""
    x = daily_excursions(normalize_daily(daily, atr_col, as_of), side)
    frame = pd.DataFrame({'year': x.index.year, 'passed': x.to_numpy() > float(window_atr)})
    g = frame.groupby('year')['passed']
    out = pd.DataFrame({'sessions': g.size(), 'passed': g.sum().astype(int)}).reset_index()
    out['share'] = out['passed'] / out['sessions']
    return out


def premarket_drops(daily: pd.DataFrame, minutes: pd.DataFrame, atr_col: str,
                    sessions: Iterable, *, stale_print_atr: Optional[float],
                    spike_atr: Optional[float]) -> pd.DataFrame:
    """Every premarket print lib.indicators.premarket_print_filter drops on
    each of `sessions`, with the close and the policy-basis ATR of the last
    daily bar before the session (what the production callers pass) and the
    two thresholds given. Columns: session, timestamp,
    field, price, rule ('stale_prior_close' or 'spike'). A session without
    premarket bars or a usable prior ATR contributes no row."""
    from lib.indicators import premarket_print_filter  # noqa: PLC0415

    want = sorted(pd.Timestamp(s).normalize() for s in sessions)
    cols = ['session', 'timestamp', 'field', 'price', 'rule']
    if not want:
        return pd.DataFrame(columns=cols)
    d = normalize_daily(daily, atr_col, want[-1])
    m = _premarket(normalize_minutes(minutes, want[-1] + pd.Timedelta(days=1)))
    by_session = dict(tuple(m.groupby('session')))
    rows = []
    for s in want:
        bars = by_session.get(s)
        prior = d[d.index < s]
        if bars is None or prior.empty:
            continue
        bars = bars.reset_index(drop=True)
        filt = premarket_print_filter(
            bars['open'], bars['high'], bars['low'], bars['close'],
            prev_close=prior['close'].iloc[-1], atr=prior['atr'].iloc[-1],
            stale_print_atr=stale_print_atr, spike_atr=spike_atr)
        for rule, masks in (('stale_prior_close', filt['stale']), ('spike', filt['spike'])):
            for fld, mask in masks.items():
                for i in np.flatnonzero(mask.to_numpy()):
                    rows.append({'session': s.date(), 'timestamp': bars.at[i, 'timestamp'],
                                 'field': fld, 'price': float(bars.at[i, fld]), 'rule': rule})
    return pd.DataFrame(rows, columns=cols).sort_values(['timestamp', 'rule', 'field'],
                                                         ignore_index=True)


def break_counts_by_year(breaks: Iterable[Break]) -> pd.DataFrame:
    """Per side and calendar year, the breaks found and how many held to the
    close. Columns: side, year, breaks, held."""
    frame = pd.DataFrame([{'side': b.side, 'year': b.session.year, 'held': bool(b.held)}
                          for b in breaks], columns=['side', 'year', 'held'])
    g = frame.groupby(['side', 'year'])['held']
    out = pd.DataFrame({'breaks': g.size(), 'held': g.sum()}).reset_index()
    return out.astype({'breaks': int, 'held': int})


def calibrate_ticker(ticker: str, session_date, *, query: Callable, write: Optional[Callable] = None,
                     run_id: Optional[str] = None):
    """On-demand calibration (Design 3): `ticker`'s parameters effective
    `session_date`, from its own bars strictly before it, under the policy
    in force on it, written to ticker_level_params with source on_demand
    through the calibration job's own reads and ON CONFLICT write
    (gcp.calibrate_level_params). `query(sql, params)` is a strict reader;
    `write(rows)` defaults to the job's engine writer.

    A ticker without enough bars gets its rows all the same, with status
    insufficient_history on the keys it cannot calibrate (daily parameters
    need the policy's minimum of daily bars, one-minute parameters
    one-minute bars), so its consumers show that state rather than
    params_unavailable. Once written, the job's on_demand universe source
    finds the ticker and the nightly run keeps it current. Returns the
    job's RunResult (failed lists the ticker when its read or calibration
    failed); a policy that cannot be read raises LevelParamsUnavailable."""
    from gcp import calibrate_level_params as job  # noqa: PLC0415 — the job owns the I/O

    session = pd.Timestamp(session_date).normalize()
    rows = job.read_policy_rows(query, session)
    return job.run([str(ticker).upper()], [session], query=query,
                   write=write if write is not None else job._engine_writer(),
                   policy_rows=rows, source='on_demand', run_id=run_id)


def load_calibration_universe(policy: Dict[str, dict], *, market_tickers: Iterable[str],
                              insight_tickers: Iterable[str],
                              watchlist_fn: Callable[[], Iterable[str]],
                              on_demand_fn: Callable[[], Iterable[str]]) -> List[str]:
    """The tickers the job calibrates: the sources the policy's
    calibration_universe row lists (market_config_tickers,
    insight_default_tickers, watchlist, on_demand), deduplicated, upper
    case, in first-seen order. A source read that fails raises (the job
    must not calibrate a silently shortened universe)."""
    sources = _policy(policy, UNIVERSE_KEY)['extra'].get('sources') or []
    readers = {
        'market_config_tickers': lambda: market_tickers,
        'insight_default_tickers': lambda: insight_tickers,
        'watchlist': watchlist_fn,
        'on_demand': on_demand_fn,
    }
    unknown = [s for s in sources if s not in readers]
    if unknown:
        raise ValueError(f"calibration_universe names unknown sources {unknown}")
    out: List[str] = []
    for src in sources:
        for t in readers[src]() or []:
            t = str(t).strip().upper()
            if t and t not in out:
                out.append(t)
    return out
