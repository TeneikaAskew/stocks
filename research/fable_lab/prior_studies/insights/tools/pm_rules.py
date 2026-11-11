"""Premarket print-filter rules for experiments (FEAT-STRAT-001 research,
not production code). Each rule returns the same dict shape as
lib.indicators.calculate_premarket_context.

Rules (all but 'raw' and 'main' apply main's stale prior-close rule first):
  raw          no filter at all
  main         main's calculate_premarket_context as is (spike k = 0.5 ATR14)
  spike:K      main's isolated-spike rule with k = K x ATR14
  pr1784       main's spike rule with #1784's calibrated k per ticker
  vol:V:W      drop a wick more than W x ATR beyond its own body when the bar's
               volume is below V x the median premarket bar volume
  iso:S:W      drop a high (low) that stands more than S x ATR beyond every
               other premarket bar's high (low) and more than W x ATR beyond
               its own body; repeated until nothing more drops
  t0805:W      drop the 08:05 bar's wick when it is more than W x ATR beyond its body
"""
import numpy as np
import pandas as pd

PR1784_K = {"SPY": 0.9264959294499225, "QQQ": 1.0715904925665558, "IWM": 0.5365491180469563}


def _cents(v):
    return int(round(float(v) * 100))


def context(rule, ticker, times, o, h, l, c, v, prev_close, prev_open, atr):
    from lib.indicators import calculate_premarket_context as orig
    kw = dict(times=times, open_=o, high=h, low=l, close=c, volume=v, prev_close=prev_close, prev_open=prev_open)
    if rule == "main":
        return orig(atr14=atr, **kw)
    if rule == "raw":
        out = orig(atr14=None, **kw)
        out["pre_range_atr"] = None if not atr else round((out["pre_high"] - out["pre_low"]) / atr, 4)
        return out
    ts = pd.to_datetime(pd.Series(list(times)))
    tod = ts.dt.time
    from datetime import time as T
    m = ((tod >= T(4, 0)) & (tod < T(9, 30))).values
    O = pd.Series(np.asarray(o, float)[m]); H = pd.Series(np.asarray(h, float)[m])
    L = pd.Series(np.asarray(l, float)[m]); C = pd.Series(np.asarray(c, float)[m])
    V = pd.Series(np.asarray(v, float)[m]); TS = ts[m].reset_index(drop=True)
    o2, h2, l2, c2 = O.copy(), H.copy(), L.copy(), C.copy()
    # main's stale prior-close rule
    pc = _cents(prev_close)
    away = ((O + C) / 2 - prev_close).abs() > 0.1 * atr
    for s in (o2, h2, l2, c2):
        s[s.map(lambda x: x == x and _cents(x) == pc) & away] = np.nan
    bh = pd.concat([o2, c2], axis=1).max(axis=1); bl = pd.concat([o2, c2], axis=1).min(axis=1)
    name, *args = rule.split(":")
    dh = pd.Series(False, index=H.index); dl = dh.copy()
    if name in ("spike", "pr1784"):
        k = (PR1784_K[ticker] if name == "pr1784" else float(args[0])) * atr
        nbh = pd.concat([bh.shift(s) for s in (-2, -1, 1, 2)], axis=1).max(axis=1)
        nbl = pd.concat([bl.shift(s) for s in (-2, -1, 1, 2)], axis=1).min(axis=1)
        dh = ((h2 - bh) > k) & ((h2 - nbh) > k); dl = ((bl - l2) > k) & ((nbl - l2) > k)
    elif name == "vol":
        vv, w = float(args[0]), float(args[1]) * atr
        thin = V < vv * V.median()
        dh = ((h2 - bh) > w) & thin; dl = ((bl - l2) > w) & thin
    elif name == "iso":
        s_, w = float(args[0]) * atr, float(args[1]) * atr
        for _ in range(5):
            hh = h2.where(~dh); ll = l2.where(~dl)
            ih = hh.idxmax(); il = ll.idxmin()
            ch = False
            if ih == ih and (hh[ih] - hh.drop(ih).max()) > s_ and (hh[ih] - bh[ih]) > w:
                dh[ih] = True; ch = True
            if il == il and (ll.drop(il).min() - ll[il]) > s_ and (bl[il] - ll[il]) > w:
                dl[il] = True; ch = True
            if not ch:
                break
    elif name == "t0805":
        w = float(args[0]) * atr
        at = (TS.dt.strftime("%H:%M") == "08:05").values
        dh = ((h2 - bh) > w) & at; dl = ((bl - l2) > w) & at
    else:
        raise ValueError(rule)
    h2[dh] = np.nan; l2[dl] = np.nan
    out = orig(atr14=None, times=TS, open_=o2.fillna(O), high=h2, low=l2, close=c2.fillna(C), volume=V,
               prev_close=prev_close, prev_open=prev_open)
    # pre_high/low from surviving values exactly as main: dropped high -> body
    eh = h2.fillna(bh); el = l2.fillna(bl)
    out["pre_high"] = float(eh.max()); out["pre_low"] = float(el.min())
    typ = pd.concat([h2, l2, c2], axis=1).mean(axis=1, skipna=True); keep = typ.notna() & V.notna()
    out["pre_vwap"] = float((typ[keep] * V[keep]).sum() / V[keep].sum()) if V[keep].sum() > 0 else None
    out["pre_open"] = float(O.iloc[0]); out["gap_pct"] = round((out["pre_open"] / prev_close - 1) * 100, 4)
    out["pre_range_atr"] = round((out["pre_high"] - out["pre_low"]) / atr, 4)
    out["excluded_spike_prints"] = int(dh.sum() + dl.sum())
    return out
