"""Trade-lifecycle simulator — options edition.

Same stop / target / time-stop detection as lib.exec_backtest.engine
(Track B): the trade hits when the UNDERLYING crosses the trigger bar's
opposite extreme (stop) or the 1.5R-from-entry target. The DIFFERENCE
is the P&L:

  Track B  : gross_pnl = (underlying_exit - underlying_entry) signed
             net_pnl   = gross - $0.05 round-trip per share
  Track B' : entry_premium = BSM(spot=entry_fill, K, T_entry, sigma=anchor_IV, ...)
             exit_premium  = BSM(spot=underlying_at_exit, K, T_exit, sigma=anchor_IV, ...)
             gross_pnl     = (exit_premium - entry_premium) per contract
             net_pnl       = gross - $1.38 round-trip per contract
                           = gross - (commission 0.65 + spread 0.03 + slippage 0.01) × 2

The anchor IV is set ONCE at entry from IVLookup and held constant
through the trade — no IV path modeling per the brief.

This module is hermetic: takes pre-loaded numpy / pandas arrays + the
preloaded IVLookup; returns OptionTrade dicts or None on void.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from lib.options_exec_backtest.iv_lookup import IVLookup, IVQuote
from lib.options_exec_backtest.pricing import bs_price, years_to_expiry

log = logging.getLogger(__name__)


# Per-side option execution costs, in DOLLARS-per-contract.
# Spec: 3¢ spread, 65¢ commission, 1¢ slippage per side.
SPREAD_PER_SIDE = 0.03
COMMISSION_PER_SIDE = 0.65
SLIPPAGE_PER_SIDE = 0.01
COST_PER_SIDE = SPREAD_PER_SIDE + COMMISSION_PER_SIDE + SLIPPAGE_PER_SIDE  # $0.69
COST_ROUND_TRIP = 2 * COST_PER_SIDE                                       # $1.38

# Each option contract represents 100 shares of the underlying. BSM
# returns a per-share premium; multiply by 100 for the per-contract dollar.
CONTRACT_MULTIPLIER = 100


@dataclass
class OptionTrade:
    """One executed option trade. Premiums are PER-SHARE BSM mids; dollar
    P&L is per CONTRACT (× 100 multiplier)."""
    setup_id: int
    fold: str
    cell: str
    direction: str                  # 'long' (call) / 'short' (put)
    kind: str                       # 'call' or 'put' (== direction translated)

    # Setup context (underlying space)
    trigger_ts_open: pd.Timestamp
    trigger_ts_close: pd.Timestamp
    trigger_high: float
    trigger_low: float
    top_prob: float

    # IV anchor
    iv_snapshot_ts: pd.Timestamp
    iv_snapshot_age_sec: float
    iv_source: str
    anchor_iv: float

    # Contract
    strike: float
    expiration: pd.Timestamp
    risk_free: float
    div_yield: float

    # Entry — underlying space
    entry_ts: pd.Timestamp
    entry_underlying: float          # fill price on the underlying (gap-aware)
    entry_T_years: float             # time-to-expiry at entry, years
    entry_premium: float             # BSM mid at entry, $/share

    # Trade plan
    initial_stop_underlying: float
    initial_target_underlying: float
    target_multiple: float
    time_stop_minutes: int

    # Exit
    exit_ts: pd.Timestamp
    exit_underlying: float
    exit_T_years: float
    exit_premium: float
    exit_reason: str                 # 'target' / 'stop' / 'time' / 'eod' / 'expired'

    # P&L per CONTRACT (multiplier already applied)
    gross_pnl_per_contract: float
    cost_per_contract: float
    net_pnl_per_contract: float

    # Diagnostics
    theta_drag_share: float          # frac of total cost attributable to theta
    delta_implied_at_entry: float    # delta sign sanity for the report


@dataclass
class OptionTradeSpec:
    """Lifecycle parameters that vary per variant."""
    target_multiple: float = 1.5
    time_stop_minutes: int = 30
    otm_offset: int = 0              # Variant 1: 1 = +1 OTM
    expiration_dte: int = 0          # Variant 2: 1 = 1DTE
    # Cost knobs (defaults match spec)
    spread_per_side: float = SPREAD_PER_SIDE
    commission_per_side: float = COMMISSION_PER_SIDE
    slippage_per_side: float = SLIPPAGE_PER_SIDE


@dataclass
class OptionSetup:
    """One prediction → potential trade."""
    setup_id: int
    fold: str
    cell: str
    direction: str                   # 'long' (2U → call) / 'short' (2D → put)
    trigger_ts_open: pd.Timestamp
    trigger_ts_close: pd.Timestamp
    trigger_high: float
    trigger_low: float
    top_prob: float


def _cost_per_side(spec: OptionTradeSpec) -> float:
    return spec.spread_per_side + spec.commission_per_side + spec.slippage_per_side


def simulate_option_setup(
    setup: OptionSetup,
    m1_bars: pd.DataFrame,
    iv_lookup: IVLookup,
    spec: OptionTradeSpec,
    risk_free: float,
    div_yield: float,
) -> Optional[OptionTrade]:
    """Run the trade lifecycle for ONE setup. Returns OptionTrade or None.

    Voiding reasons (None returned):
      - 1m bars empty inside bar T+1 window
      - underlying trigger never hit during bar T+1
      - IV lookup returned None (no snapshot within 5 min, or no IV for
        the chosen contract)
      - entry-side BSM produced NaN/zero premium

    Args:
        setup: prediction → trade plan context
        m1_bars: UTC-indexed 1m OHLC RTH-only DataFrame
        iv_lookup: preloaded for the fold's date range
        spec: lifecycle knobs (target, time-stop, variant offsets)
        risk_free: annualized decimal, from daily_rates for the trade date
        div_yield: annualized decimal, from daily_rates
    """
    if len(m1_bars) == 0:
        return None

    tf_minutes = int(round(
        (setup.trigger_ts_close - setup.trigger_ts_open).total_seconds() / 60
    ))
    is_long = setup.direction == "long"
    kind = "call" if is_long else "put"
    side_cost = _cost_per_side(spec)

    # ── Underlying-space entry detection ────────────────────────────────
    bar_tplus1_start = setup.trigger_ts_close
    bar_tplus1_end = setup.trigger_ts_close + timedelta(minutes=tf_minutes)
    bars_in_window = m1_bars.loc[
        (m1_bars.index >= bar_tplus1_start) & (m1_bars.index < bar_tplus1_end)
    ]
    if bars_in_window.empty:
        return None

    stop_price = setup.trigger_high if is_long else setup.trigger_low

    entry_ts = None
    entry_fill = None  # underlying-space fill (no option slippage yet)
    for ts, row in bars_in_window.iterrows():
        o, h, l = row["Open"], row["High"], row["Low"]
        if is_long:
            if h >= stop_price:
                entry_fill = o if o >= stop_price else stop_price
                entry_ts = ts
                break
        else:
            if l <= stop_price:
                entry_fill = o if o <= stop_price else stop_price
                entry_ts = ts
                break
    if entry_ts is None:
        return None

    # ── Trade plan (underlying space) ───────────────────────────────────
    if is_long:
        initial_stop = setup.trigger_low
        risk = entry_fill - initial_stop
        initial_target = entry_fill + spec.target_multiple * risk
    else:
        initial_stop = setup.trigger_high
        risk = initial_stop - entry_fill
        initial_target = entry_fill - spec.target_multiple * risk

    if risk <= 0:
        return None

    # ── IV / strike lookup ──────────────────────────────────────────────
    quote = iv_lookup.find(
        trigger_ts=entry_ts,
        spot=float(entry_fill),
        side=setup.direction,
        otm_offset=spec.otm_offset,
        expiration_dte=spec.expiration_dte,
    )
    if quote is None:
        return None

    # ── Entry premium (BSM) ─────────────────────────────────────────────
    entry_T = years_to_expiry(entry_ts, quote.expiration)
    if not np.isfinite(entry_T) or entry_T <= 0:
        return None

    entry_premium = bs_price(
        S=float(entry_fill), K=quote.strike, T=entry_T,
        sigma=quote.iv, r=risk_free, q=div_yield, kind=kind,
    )
    if not np.isfinite(entry_premium) or entry_premium <= 0:
        return None

    # Approximate delta-at-entry for the diagnostics column. BSM d1:
    # Sign convention: positive for calls, negative for puts (long).
    # We don't recompute it formally — close enough by sign and magnitude
    # via finite-difference is overkill; the report only uses sign.
    delta_sign = +1.0 if is_long else -1.0
    delta_implied = delta_sign * 0.5  # ATM 0DTE ≈ 0.5; sign matters

    # ── Exit detection (underlying space) — same as Track B ─────────────
    time_stop_deadline = entry_ts + timedelta(minutes=spec.time_stop_minutes)
    eval_bars = m1_bars.loc[m1_bars.index >= entry_ts]

    exit_ts = None
    exit_underlying = None
    exit_reason = None

    for ts, row in eval_bars.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        if is_long:
            target_hit = h >= initial_target
            stop_hit = l <= initial_stop
        else:
            target_hit = l <= initial_target
            stop_hit = h >= initial_stop

        if target_hit and stop_hit:
            # Conservative: STOP first on collision (per Track B contract)
            exit_ts = ts
            exit_underlying = initial_stop
            exit_reason = "stop"
            break
        if stop_hit:
            exit_ts = ts
            exit_underlying = initial_stop
            exit_reason = "stop"
            break
        if target_hit:
            exit_ts = ts
            exit_underlying = initial_target
            exit_reason = "target"
            break
        if ts >= time_stop_deadline:
            exit_ts = ts
            exit_underlying = c
            exit_reason = "time"
            break

    if exit_ts is None:
        # Ran out of bars (EOD before time stop) — close at last bar's close
        last = eval_bars.iloc[-1]
        exit_ts = eval_bars.index[-1]
        exit_underlying = float(last["Close"])
        exit_reason = "eod"

    # ── Exit premium (BSM, same anchor IV) ──────────────────────────────
    exit_T = years_to_expiry(exit_ts, quote.expiration)
    if not np.isfinite(exit_T) or exit_T < 0:
        exit_T = 0.0
    exit_premium = bs_price(
        S=float(exit_underlying), K=quote.strike, T=exit_T,
        sigma=quote.iv, r=risk_free, q=div_yield, kind=kind,
    )
    if not np.isfinite(exit_premium):
        # BSM math broke — extremely rare with positive-IV inputs. Void.
        return None

    # ── P&L per CONTRACT ────────────────────────────────────────────────
    gross_per_share = exit_premium - entry_premium  # signed (long option only)
    gross_per_contract = gross_per_share * CONTRACT_MULTIPLIER
    cost_per_contract = 2 * side_cost  # spread + commission + slippage × 2 sides
    net_per_contract = gross_per_contract - cost_per_contract

    # Theta drag estimate: if underlying had been UNCHANGED, the entire
    # P&L move would be theta. We compute a counterfactual exit price at
    # the same underlying but real exit_T, and the difference is the
    # pure-theta delta.
    counterfactual_exit = bs_price(
        S=float(entry_fill), K=quote.strike, T=exit_T,
        sigma=quote.iv, r=risk_free, q=div_yield, kind=kind,
    )
    theta_per_share = entry_premium - counterfactual_exit  # positive = theta hurt the long
    theta_per_contract = theta_per_share * CONTRACT_MULTIPLIER
    total_friction = abs(net_per_contract - gross_per_contract) + max(abs(theta_per_contract), 1e-9)
    theta_drag_share = float(abs(theta_per_contract) / total_friction)

    return OptionTrade(
        setup_id=setup.setup_id, fold=setup.fold, cell=setup.cell,
        direction=setup.direction, kind=kind,
        trigger_ts_open=setup.trigger_ts_open,
        trigger_ts_close=setup.trigger_ts_close,
        trigger_high=setup.trigger_high, trigger_low=setup.trigger_low,
        top_prob=setup.top_prob,
        iv_snapshot_ts=quote.snapshot_ts,
        iv_snapshot_age_sec=quote.snapshot_age_seconds,
        iv_source=quote.iv_source,
        anchor_iv=quote.iv,
        strike=quote.strike,
        expiration=quote.expiration,
        risk_free=risk_free,
        div_yield=div_yield,
        entry_ts=entry_ts,
        entry_underlying=float(entry_fill),
        entry_T_years=entry_T,
        entry_premium=float(entry_premium),
        initial_stop_underlying=float(initial_stop),
        initial_target_underlying=float(initial_target),
        target_multiple=spec.target_multiple,
        time_stop_minutes=spec.time_stop_minutes,
        exit_ts=exit_ts,
        exit_underlying=float(exit_underlying),
        exit_T_years=exit_T,
        exit_premium=float(exit_premium),
        exit_reason=exit_reason,
        gross_pnl_per_contract=float(gross_per_contract),
        cost_per_contract=float(cost_per_contract),
        net_pnl_per_contract=float(net_per_contract),
        theta_drag_share=float(theta_drag_share),
        delta_implied_at_entry=float(delta_implied),
    )


def fold_stats(trades: list) -> dict:
    """Aggregate per-contract net P&L into the spec's reported stats."""
    n = len(trades)
    if n == 0:
        return {
            "n": 0, "hit_rate": 0.0, "gross_exp": 0.0, "net_exp": 0.0,
            "total_net": 0.0, "max_dd": 0.0, "sharpe": 0.0, "avg_win": 0.0,
            "avg_loss": 0.0,
        }
    nets = np.array([t.net_pnl_per_contract for t in trades])
    grosses = np.array([t.gross_pnl_per_contract for t in trades])
    wins_mask = nets > 0
    cum = np.cumsum(nets)
    peak = np.maximum.accumulate(cum)
    dd = float((cum - peak).min())
    sd = nets.std(ddof=1) if len(nets) > 1 else 0.0
    sharpe = float(nets.mean() / sd) if sd > 0 else 0.0
    avg_win = float(nets[wins_mask].mean()) if wins_mask.any() else 0.0
    avg_loss = float(nets[~wins_mask].mean()) if (~wins_mask).any() else 0.0
    return {
        "n": n,
        "hit_rate": float(wins_mask.mean()),
        "gross_exp": float(grosses.mean()),
        "net_exp": float(nets.mean()),
        "total_net": float(nets.sum()),
        "max_dd": dd,
        "sharpe": sharpe,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }
