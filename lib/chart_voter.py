"""Chart-page teaching voter — the July-6 (pre-#700) 5-condition readout.

Ported line-for-line from the deleted client voter
(platform/src/lib/indicators.ts::computeStrategySignals @ commit 969187eb).
PR #700's one-source-of-truth migration removed the client math but also the
readable presentation; this module restores the math server-side so the
Charts page card can show the same five conditions per side.

Voter taxonomy (issue #701): this is the chart TEACHING voter (trend
confirmation in a pullback band). It is distinct from the production
alerting voter (lib/signals.py::evaluate_signal, mean-reversion) and from
the Live-page trend framework (platform/api/routers/live.py::_build_signals).
"""
from __future__ import annotations

import math
from typing import List, Optional


def _fmt(n: Optional[float], digits: int = 2) -> str:
    if n is None or not math.isfinite(n):
        return "--"
    return f"{n:.{digits}f}"


def _num(n: Optional[float]) -> Optional[float]:
    """None-ify NaN/inf so comparisons below can rely on `is not None`."""
    if n is None or not math.isfinite(n):
        return None
    return n


def evaluate_chart_voter(
    closes: List[float],
    rsi: Optional[float],
    stoch_k: Optional[float],
    ema9: Optional[float],
    vwap: Optional[float],
) -> dict:
    rsi, stoch_k, ema9, vwap = _num(rsi), _num(stoch_k), _num(ema9), _num(vwap)
    last = closes[-1] if closes else None

    # Last 3 bars' direction — pct_change>0 semantics from the TS original.
    up_run = 0
    down_run = 0
    n = len(closes)
    for i in range(n - 3, n):
        if i <= 0:
            continue
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            up_run += 1
        if diff < 0:
            down_run += 1

    call_conds = [
        {"id": "call_consec_up", "label": "3 consecutive up moves",
         "met": up_run >= 3, "detail": f"{up_run}/3 last bars up"},
        {"id": "call_rsi_band", "label": "RSI 25–50 (bullish band)",
         "met": rsi is not None and 25 < rsi < 50, "detail": f"RSI {_fmt(rsi, 1)}"},
        {"id": "call_stoch_room", "label": "StochRSI K < 80 (room to run)",
         "met": stoch_k is not None and stoch_k < 80, "detail": f"K {_fmt(stoch_k, 1)}"},
        {"id": "call_above_vwap", "label": "Price > VWAP",
         "met": last is not None and vwap is not None and last > vwap,
         "detail": (f"{_fmt(last)} {'>' if last > vwap else '<'} VWAP {_fmt(vwap)}"
                    if last is not None and vwap is not None else "--")},
        {"id": "call_above_ema9", "label": "Price > EMA9",
         "met": last is not None and ema9 is not None and last > ema9,
         "detail": (f"{_fmt(last)} {'>' if last > ema9 else '<'} EMA9 {_fmt(ema9)}"
                    if last is not None and ema9 is not None else "--")},
    ]
    put_conds = [
        {"id": "put_consec_down", "label": "3 consecutive down moves",
         "met": down_run >= 3, "detail": f"{down_run}/3 last bars down"},
        {"id": "put_rsi_band", "label": "RSI 50–75 (bearish band)",
         "met": rsi is not None and 50 < rsi < 75, "detail": f"RSI {_fmt(rsi, 1)}"},
        {"id": "put_stoch_room", "label": "StochRSI K > 20 (room to fall)",
         "met": stoch_k is not None and stoch_k > 20, "detail": f"K {_fmt(stoch_k, 1)}"},
        {"id": "put_below_vwap", "label": "Price < VWAP",
         "met": last is not None and vwap is not None and last < vwap,
         "detail": (f"{_fmt(last)} {'<' if last < vwap else '>'} VWAP {_fmt(vwap)}"
                    if last is not None and vwap is not None else "--")},
        {"id": "put_below_ema9", "label": "Price < EMA9",
         "met": last is not None and ema9 is not None and last < ema9,
         "detail": (f"{_fmt(last)} {'<' if last < ema9 else '>'} EMA9 {_fmt(ema9)}"
                    if last is not None and ema9 is not None else "--")},
    ]

    call_met = sum(1 for c in call_conds if c["met"])
    put_met = sum(1 for c in put_conds if c["met"])
    call_fires = call_met >= 3 and call_met > put_met
    put_fires = put_met >= 3 and put_met > call_met
    firing = "CALL" if call_fires else "PUT" if put_fires else None

    return {
        "call": {"direction": "CALL", "conditions": call_conds,
                 "met_count": call_met, "total_count": 5, "fires": call_fires},
        "put": {"direction": "PUT", "conditions": put_conds,
                "met_count": put_met, "total_count": 5, "fires": put_fires},
        "firing": firing,
    }
