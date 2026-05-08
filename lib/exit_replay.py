"""Single source of truth for signal exit resolution.

Used by:
  - `gcp/signal_monitor.py` for live per-tick exit evaluation,
  - `gcp/signal_monitor_eod_resolver.py` for end-of-day reconciliation
    of alerts that the live monitor never closed (network blip,
    container restart, market close before any condition fired).

Closes Track D's worry that the audit's replay logic might diverge from
production: both consumers call `decide_exit` for per-bar evaluation
and the same `PERSIST_EXIT_SQL` for the UPDATE.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
ET_MARKET_CLOSE = time(16, 0)
DEFAULT_CALL_RSI_EXIT = 80.0
DEFAULT_PUT_RSI_EXIT = 20.0


@dataclass(frozen=True)
class Position:
    ticker: str
    direction: str  # 'CALL' | 'PUT'
    alert_ts: datetime  # naive UTC (matches signal_alerts.alert_ts)
    entry_price: float
    target_price: float
    time_stop_minutes: int


@dataclass(frozen=True)
class ExitEvent:
    exit_ts: datetime  # naive UTC
    exit_reason: str   # 'target_hit' | 'time_stop' | 'rsi_extreme' | 'eod_close'
    exit_price: float
    exit_return_pct: float


def return_pct(direction: str, entry: float, exit_price: float) -> float:
    """CALL gains when price rises; PUT gains when price falls."""
    if direction == 'CALL':
        return (exit_price - entry) / entry * 100.0
    return (entry - exit_price) / entry * 100.0


def decide_exit(
    pos: Position,
    *,
    current_price: float,
    current_rsi: float,
    elapsed_minutes: float,
    call_rsi_exit: float = DEFAULT_CALL_RSI_EXIT,
    put_rsi_exit: float = DEFAULT_PUT_RSI_EXIT,
) -> Optional[str]:
    """Return the matching exit reason for a single tick, or None.

    Mirrors `gcp/signal_monitor.py:SignalMonitor._check_exits` exactly.
    The check ordering (target → time → RSI) is the same as the live
    monitor; tied conditions resolve to the first match.
    """
    if pos.direction == 'CALL':
        if current_price >= pos.target_price:
            return 'target_hit'
        if elapsed_minutes >= pos.time_stop_minutes:
            return 'time_stop'
        if current_rsi >= call_rsi_exit:
            return 'rsi_extreme'
    else:  # PUT
        if current_price <= pos.target_price:
            return 'target_hit'
        if elapsed_minutes >= pos.time_stop_minutes:
            return 'time_stop'
        if 0 < current_rsi <= put_rsi_exit:
            return 'rsi_extreme'
    return None


def simulate_exit(
    pos: Position,
    bars: pd.DataFrame,
    *,
    rsi_col: str = 'rsi_14',
    call_rsi_exit: float = DEFAULT_CALL_RSI_EXIT,
    put_rsi_exit: float = DEFAULT_PUT_RSI_EXIT,
    eod_close_et: time = ET_MARKET_CLOSE,
) -> Optional[ExitEvent]:
    """Replay the exit logic over 1-min `bars` and return the first
    matching exit event.

    `bars` must have columns ('ts', 'close') and the RSI column at
    `rsi_col`. `ts` is naive UTC (matching the rest of the system).

    If no exit triggers during the bars provided AND the last bar is
    at or after `eod_close_et` (in ET), returns an `eod_close` event
    at the last bar. If the last bar is mid-session, returns None
    (data is partial; the caller can wait for more bars).

    Returns None on empty input.
    """
    if bars is None or bars.empty:
        return None

    # Ensure chronological order; the SQL ORDER BY is the contract but
    # this defends against any caller forgetting it.
    bars = bars.sort_values('ts').reset_index(drop=True)

    for _, b in bars.iterrows():
        bar_ts = b['ts']
        elapsed = (bar_ts - pos.alert_ts).total_seconds() / 60.0
        rsi = float(b.get(rsi_col, 0) or 0)
        reason = decide_exit(
            pos,
            current_price=float(b['close']),
            current_rsi=rsi,
            elapsed_minutes=elapsed,
            call_rsi_exit=call_rsi_exit,
            put_rsi_exit=put_rsi_exit,
        )
        if reason:
            return ExitEvent(
                exit_ts=bar_ts,
                exit_reason=reason,
                exit_price=float(b['close']),
                exit_return_pct=return_pct(
                    pos.direction, pos.entry_price, float(b['close'])),
            )

    # No live condition triggered. Only emit eod_close if we walked at
    # least to market close — otherwise the data is partial and the
    # caller should wait for more bars before reconciling.
    last = bars.iloc[-1]
    last_ts = last['ts']
    last_et = last_ts.replace(tzinfo=UTC).astimezone(ET)
    if last_et.time() < eod_close_et:
        return None

    return ExitEvent(
        exit_ts=last_ts,
        exit_reason='eod_close',
        exit_price=float(last['close']),
        exit_return_pct=return_pct(
            pos.direction, pos.entry_price, float(last['close'])),
    )


# ── SQL UPDATE for persisting the exit ────────────────────────────────
#
# Both signal_monitor.py (live) and signal_monitor_eod_resolver.py
# (batch) bind these parameters and execute the same statement. Keeping
# the SQL here means a schema rename (e.g. exit_return_pct →
# exit_return_bps) is one place, not two.

PERSIST_EXIT_SQL = """
    UPDATE signal_alerts
       SET exit_ts          = :exit_ts,
           exit_reason      = :exit_reason,
           exit_price       = :exit_price,
           exit_return_pct  = :exit_return_pct,
           is_open          = FALSE
     WHERE ticker   = :ticker
       AND alert_ts = :alert_ts
"""


def persist_exit_params(pos: Position, event: ExitEvent) -> dict:
    """Build the parameter dict for `PERSIST_EXIT_SQL`."""
    return {
        'exit_ts': event.exit_ts,
        'exit_reason': event.exit_reason,
        'exit_price': float(event.exit_price),
        'exit_return_pct': float(event.exit_return_pct),
        'ticker': pos.ticker,
        'alert_ts': pos.alert_ts,
    }
