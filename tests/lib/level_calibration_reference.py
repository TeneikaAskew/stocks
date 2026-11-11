"""The scalar break and premarket-spread rules of lib/level_calibration.py as
they stood before the history-mode vectorisation (FEAT-STRAT-001 review fix,
2026-11-08), kept verbatim as the reference the vectorised kernels are
checked against (tests/lib/test_level_calibration_history.py). Test-only.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from lib.level_calibration import SIDES, Break, Outcome, _rth
from lib.strat_levels import price_cents

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
        sma = d.at[s, 'prior_sma_200'] if 'prior_sma_200' in d.columns else None
        sma = float(sma) if sma is not None and sma == sma else None
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
                             held=bool(held), bars=bars.iloc[i:].reset_index(drop=True),
                             structure=(sma, trig.get(f'{side}_stop'))))
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


def persona_fill(b: Break, midpoint: float) -> Optional[int]:
    """Index of the fill bar: the first bar after the break bar that trades
    at the entry midpoint."""
    lo, hi = b.bars['low'].to_numpy(), b.bars['high'].to_numpy()
    hit = (lo[1:] <= midpoint) & (hi[1:] >= midpoint)
    return int(np.argmax(hit)) + 1 if hit.any() else None


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
    j = persona_fill(b, midpoint)
    if j is None:
        return Outcome(filled=False)
    s = b.sign
    lo, hi = b.bars['low'].to_numpy()[j:], b.bars['high'].to_numpy()[j:]
    adverse = (midpoint - lo) if s > 0 else (hi - midpoint)
    mae = max(float(np.max(adverse)), 0.0) / b.atr
    if stop is None and risk_atr is None:
        return Outcome(filled=True, mae_atr=mae)
    if stop is None:
        risk = float(risk_atr) * b.atr
        stop = midpoint - s * risk
    else:
        risk = abs(midpoint - stop)
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
