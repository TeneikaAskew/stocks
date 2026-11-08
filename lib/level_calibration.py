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
* ``calibrate``: every Design 2 parameter for one ticker and effective date,
  in the spec's order (windows, breaks, entry buffers, fills, stops and the
  floor, targets; the three one-minute thresholds from their own bars).
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
    LEVEL_CLUSTER_KEY, MIN_STOP_KEY, PARAM_OK, PM_SPIKE_KEY, PM_STALE_PRINT_KEY, LevelParam,
    LevelParams, build_session_levels, entry_buffer_key, policy_atr_basis, price_cents, stop_key,
    target_key, trigger_window_key,
)

logger = logging.getLogger(__name__)

INSUFFICIENT_HISTORY = 'insufficient_history'
INPUT_UNAVAILABLE = 'input_unavailable'
NO_POSITIVE_TARGET = 'no_positive_target'

PERSONAS = ('aggressive', 'neutral', 'conservative')
SIDES = ('long', 'short')

PREMARKET_START = time(4, 0)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


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
    date index, with columns high, low, close, atr (the policy-basis ATR) and
    prior_close and prior_atr (the previous session's close and ATR)."""
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
    df = df[df.index < pd.Timestamp(as_of)].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    out = pd.DataFrame({
        'open': pd.to_numeric(df.get('open'), errors='coerce') if 'open' in df else np.nan,
        'high': pd.to_numeric(df['high'], errors='coerce'),
        'low': pd.to_numeric(df['low'], errors='coerce'),
        'close': pd.to_numeric(df['close'], errors='coerce'),
        'atr': pd.to_numeric(df[atr_name], errors='coerce'),
    }, index=df.index)
    out = out[out['close'].notna()]
    out['prior_close'] = out['close'].shift(1)
    out['prior_atr'] = out['atr'].shift(1)
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
        ts = ts.dt.tz_convert('America/New_York').dt.tz_localize(None)
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
    return m[(m['tod'] >= RTH_OPEN) & (m['tod'] < RTH_CLOSE)]


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
    exc = daily_excursions(d, side).iloc[-int(row['lookback_sessions']):]
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
    for s, g in _session_minutes(_rth(m), sessions).items():
        atr = d.at[s, 'prior_atr']
        if len(g) < min_bars or not (atr == atr and atr > 0):
            continue
        x = wick_excesses(g) / atr
        if len(x):
            samples.extend(list(x))
            used.append(s)
    return _stat(PM_SPIKE_KEY, row, samples, used, n=len(used))


def clean_premarket_spreads(bars: pd.DataFrame, prior_close: float, spike_price: float) -> np.ndarray:
    """max(high - midpoint, midpoint - low) of each premarket bar with no
    print on the prior close's cent and no wick beyond `spike_price` (the
    spike rule at the ticker's calibrated pm_spike_atr), where the midpoint
    is the bar's open-close midpoint, the one the stale-print rule measures
    from."""
    b = bars.reset_index(drop=True)
    pc = price_cents(prior_close)
    echo = np.zeros(len(b), dtype=bool)
    for col in ('open', 'high', 'low', 'close'):
        echo |= b[col].map(lambda v: v == v and price_cents(v) == pc).to_numpy()
    body_hi = b[['open', 'close']].max(axis=1)
    body_lo = b[['open', 'close']].min(axis=1)
    shifts = (-2, -1, 1, 2)
    nb_hi = pd.concat([body_hi.shift(s) for s in shifts], axis=1).max(axis=1)
    nb_lo = pd.concat([body_lo.shift(s) for s in shifts], axis=1).min(axis=1)
    spike = ((((b['high'] - body_hi) > spike_price) & ((b['high'] - nb_hi) > spike_price))
             | (((body_lo - b['low']) > spike_price) & ((nb_lo - b['low']) > spike_price))).to_numpy()
    keep = ~(echo | spike)
    mid = (b['open'] + b['close']) / 2
    spread = np.maximum(b['high'] - mid, mid - b['low']).to_numpy(dtype=float)
    out = spread[keep]
    return out[np.isfinite(out)]


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
    RTH intervals of one session (each interval's last close)."""
    t = bars['timestamp']
    since_open = (t - t.dt.normalize() - pd.Timedelta(hours=RTH_OPEN.hour, minutes=RTH_OPEN.minute))
    bucket = (since_open // pd.Timedelta(minutes=int(minutes))).to_numpy()
    closes = bars.assign(_b=bucket).groupby('_b')['close'].last().to_numpy(dtype=float)
    return np.abs(np.diff(closes))


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

    @property
    def sign(self) -> float:
        return 1.0 if self.side == 'long' else -1.0


def replay_triggers(ticker: str, daily: pd.DataFrame, d: pd.DataFrame, policy: Dict[str, dict],
                    sessions: Iterable[pd.Timestamp], atr_basis: str) -> Dict[pd.Timestamp, dict]:
    """Each session's long and short trigger as lib.strat_levels
    build_session_levels picks it from daily bars before the session, with no
    premarket snapshot (reference = the prior close) and the trigger windows
    in force that session (calibrated from the excursions before it)."""
    out = {}
    for s in sessions:
        before = d[d.index < s]
        windows = {side: trigger_window(before, policy, side) for side in SIDES}
        atr = before['atr'].iloc[-1] if len(before) else None
        atrs = {'atr_14': None, 'atr_5': None}
        atrs[atr_basis] = float(atr) if atr == atr and atr is not None else None
        lp = _window_params(ticker, s, atr_basis, windows, policy)
        sl = build_session_levels(ticker, s.date(), daily, atrs, None, lp)
        out[s] = {side: (float(sl.side(side).trigger['price']) if sl.side(side).trigger else None)
                  for side in SIDES}
        out[s]['atr'] = atrs[atr_basis]
    return out


def find_breaks(d: pd.DataFrame, m: pd.DataFrame,
                triggers: Dict[pd.Timestamp, dict]) -> List[Break]:
    """The break of each session and side whose trigger exists: the first
    RTH bar whose high (long) or low (short) is one cent or more beyond the
    trigger's cent. A held break's session close is beyond the trigger on
    its side."""
    out = []
    rth = _rth(m)
    by_session = dict(tuple(rth.groupby('session')))
    for s, trig in sorted(triggers.items()):
        bars = by_session.get(s)
        atr = trig.get('atr')
        if bars is None or not len(bars) or not (atr and atr > 0) or s not in d.index:
            continue
        close = d.at[s, 'close']
        for side in SIDES:
            t = trig.get(side)
            if t is None:
                continue
            tc = price_cents(t)
            if side == 'long':
                hit = bars['high'].map(price_cents).to_numpy() > tc
            else:
                hit = bars['low'].map(price_cents).to_numpy() < tc
            if not hit.any():
                continue
            i = int(np.argmax(hit))
            held = (price_cents(close) > tc) if side == 'long' else (price_cents(close) < tc)
            out.append(Break(session=s, side=side, trigger=float(t), atr=float(atr),
                             held=bool(held), bars=bars.iloc[i:].reset_index(drop=True)))
    return out


def follow_through(b: Break, minutes: int) -> float:
    """F: the furthest the break ran beyond the trigger, in ATR, from the
    break bar until the first later bar that trades back to the trigger's
    cent or until `minutes` after the break bar, whichever comes first."""
    t0 = b.bars['timestamp'].iloc[0]
    tc = price_cents(b.trigger)
    best = 0.0
    for j, r in enumerate(b.bars.itertuples(index=False)):
        if r.timestamp >= t0 + pd.Timedelta(minutes=int(minutes)):
            break
        if j > 0:
            back = price_cents(r.low) <= tc if b.side == 'long' else price_cents(r.high) >= tc
            if back:
                break
        run = (r.high - b.trigger) if b.side == 'long' else (b.trigger - r.low)
        best = max(best, run / b.atr)
    return best


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
    lo, hi = b.bars['low'].to_numpy(), b.bars['high'].to_numpy()
    hit = (lo[1:] <= midpoint) & (hi[1:] >= midpoint)
    return int(np.argmax(hit)) + 1 if hit.any() else None


def persona_outcome(b: Break, midpoint: float, risk_atr: Optional[float] = None) -> Outcome:
    """Fill at `midpoint`, then, from the fill bar to the close:

    * mae_atr: the largest adverse excursion from the fill price, the fill
      bar's adverse extreme included (taken as after the fill);
    * reach_r (when `risk_atr` is given): the largest favourable excursion,
      in R = risk_atr x ATR, on bars after the fill bar, before a bar that
      touches the stop at fill - R (a stop touched on the fill bar, or on the
      same bar as a favourable extreme, is taken as first). The fill bar's
      favourable extreme counts toward nothing.
    """
    j = persona_fill(b, midpoint)
    if j is None:
        return Outcome(filled=False)
    s = b.sign
    lo, hi = b.bars['low'].to_numpy()[j:], b.bars['high'].to_numpy()[j:]
    adverse = (midpoint - lo) if s > 0 else (hi - midpoint)
    mae = max(float(np.max(adverse)), 0.0) / b.atr
    if risk_atr is None:
        return Outcome(filled=True, mae_atr=mae)
    risk = float(risk_atr) * b.atr
    stop = midpoint - s * risk
    reach = 0.0
    for k in range(len(lo)):
        stopped = (lo[k] <= stop) if s > 0 else (hi[k] >= stop)
        if stopped:
            break
        if k == 0:
            continue
        fav = (hi[k] - midpoint) if s > 0 else (midpoint - lo[k])
        reach = max(reach, fav / risk)
    return Outcome(filled=True, mae_atr=mae, reach_r=reach)


def _midpoint(b: Break, lo_atr: float, hi_atr: float) -> float:
    return b.trigger + b.sign * (lo_atr + hi_atr) / 2 * b.atr


def _not_ok(key: str, row: dict, upstream: Calibrated) -> Calibrated:
    status = upstream.status if upstream.status == INSUFFICIENT_HISTORY else INPUT_UNAVAILABLE
    return _result(key, row, status, None, upstream.sample_n, [])


def break_params(breaks: List[Break], policy: Dict[str, dict]) -> Dict[str, Calibrated]:
    """Entry buffers, stops, the floor and targets from the breaks (both
    sides pooled), in the spec's order. A parameter measured with another
    that is not ok carries that one's status."""
    out: Dict[str, Calibrated] = {}
    dates = [b.session for b in breaks]

    # Entry buffers: quantiles of follow-through over all breaks.
    for persona in PERSONAS:
        for edge in ('lo', 'hi'):
            key = entry_buffer_key(persona, edge)
            row = _policy(policy, key)
            minutes = int(row['extra'].get('follow_through_minutes') or 0)
            if row.get('method_id') == 'at_trigger':
                out[key] = _stat(key, row, [0.0] * len(breaks), dates, value_fn=lambda _s: 0.0)
                continue
            ft = [follow_through(b, minutes) for b in breaks]
            out[key] = _stat(key, row, ft, dates)

    # Fills at each persona's entry midpoint; stops on filled held breaks.
    fills: Dict[str, List[tuple]] = {}
    for persona in PERSONAS:
        lo, hi = out[entry_buffer_key(persona, 'lo')], out[entry_buffer_key(persona, 'hi')]
        skey = stop_key(persona)
        srow = _policy(policy, skey)
        if not (lo.ok and hi.ok):
            out[skey] = _not_ok(skey, srow, lo if not lo.ok else hi)
            fills[persona] = []
            continue
        fl = []
        for b in breaks:
            o = persona_outcome(b, _midpoint(b, lo.value, hi.value))
            if o.filled:
                fl.append((b, o))
        fills[persona] = fl
        held = [(b, o) for b, o in fl if b.held]
        out[skey] = _stat(skey, srow, [o.mae_atr for _b, o in held], [b.session for b, _o in held])

    mrow = _policy(policy, MIN_STOP_KEY)
    floor_persona = mrow['extra'].get('persona') or 'neutral'
    flo, fhi = out[entry_buffer_key(floor_persona, 'lo')], out[entry_buffer_key(floor_persona, 'hi')]
    if not (flo.ok and fhi.ok):
        out[MIN_STOP_KEY] = _not_ok(MIN_STOP_KEY, mrow, flo if not flo.ok else fhi)
    else:
        held = [(b, o) for b, o in fills[floor_persona] if b.held]
        out[MIN_STOP_KEY] = _stat(MIN_STOP_KEY, mrow, [o.mae_atr for _b, o in held],
                                  [b.session for b, _o in held])

    # Targets: reach shares on filled breaks, in the persona's own R.
    for persona in PERSONAS:
        k = 1
        stop_c, floor_c = out[stop_key(persona)], out[MIN_STOP_KEY]
        prev, blocked = None, None
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
            risk_atr = max(stop_c.value, floor_c.value)
            lo = out[entry_buffer_key(persona, 'lo')].value
            hi = out[entry_buffer_key(persona, 'hi')].value
            reaches, used = [], []
            for b, _o in fills[persona]:
                o = persona_outcome(b, _midpoint(b, lo, hi), risk_atr)
                reaches.append(o.reach_r)
                used.append(b.session)
            share = _q(row)
            c = _stat(key, row, reaches, used, value_fn=lambda s, share=share: reach_share_value(s, share))
            if c.ok and (c.value <= 0 or (prev is not None and c.value <= prev)):
                c = _result(key, row, NO_POSITIVE_TARGET, None, c.sample_n, used)
                blocked = c
            elif c.ok:
                prev = c.value
            out[key] = c
    return out


# ── one ticker, one effective date ───────────────────────────────────────


def prepare(daily: pd.DataFrame, minutes: Optional[pd.DataFrame], policy: Dict[str, dict],
            before) -> tuple:
    """Normalize a ticker's bars once for several calibrations (history
    mode): calibrate(..., prepared=...) then cuts them to each as_of."""
    atr_basis = policy_atr_basis(policy)
    return normalize_daily(daily, atr_basis, before), normalize_minutes(minutes, before)


def calibrate(ticker: str, daily: pd.DataFrame, minutes: Optional[pd.DataFrame],
              policy: Dict[str, dict], as_of, *,
              triggers: Optional[Dict[pd.Timestamp, dict]] = None,
              prepared: Optional[tuple] = None) -> Dict[str, Calibrated]:
    """Every Design 2 parameter for `ticker`, effective `as_of`, from bars
    dated strictly before it. `daily` carries High, Low, Close and the
    policy's ATR column (atr_14 or atr_5, or ATR14/ATR5); `minutes` the
    one-minute bars (timestamp in ET, open, high, low, close). `triggers`
    (session -> {'long', 'short', 'atr'}) may be passed precomputed (history
    mode computes them once); sessions on or after `as_of` are ignored."""
    as_of = pd.Timestamp(as_of).normalize()
    atr_basis = policy_atr_basis(policy)
    if prepared is not None:
        d_all, m_all = prepared
        d = d_all[d_all.index < as_of]
        m = m_all[m_all['session'] < as_of] if len(m_all) else m_all
    else:
        d = normalize_daily(daily, atr_basis, as_of)
        m = normalize_minutes(minutes, as_of)
    out: Dict[str, Calibrated] = {}
    for side in SIDES:
        out[trigger_window_key(side)] = trigger_window(d, policy, side)
    spike = pm_spike(d, m, policy)
    out[PM_SPIKE_KEY] = spike
    out[PM_STALE_PRINT_KEY] = pm_stale_print(d, m, policy, spike)
    out[LEVEL_CLUSTER_KEY] = level_cluster(d, m, policy)

    lookback = max(int(_policy(policy, entry_buffer_key(p, e))['lookback_sessions'])
                   for p in PERSONAS for e in ('lo', 'hi'))
    sessions = _lookback_sessions(d, lookback)
    minute_sessions = set(m['session'].unique()) if len(m) else set()
    sessions = [s for s in sessions if s in minute_sessions]
    if triggers is None:
        trig = replay_triggers(ticker, daily_before(daily, as_of), d, policy, sessions, atr_basis)
    else:
        trig = {s: triggers[s] for s in sessions if s in triggers}
    out.update(break_params(find_breaks(d, m, trig), policy))
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
