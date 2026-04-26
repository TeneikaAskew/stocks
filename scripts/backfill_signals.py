#!/usr/bin/env python3
"""Backfill signal_alerts and trades tables from historical intraday bars.

Reads market_data_intraday for the specified tickers and lookback window,
computes indicators on a rolling window, runs evaluate_signal() per bar,
and writes any resulting signals to both signal_alerts and trades.

This mirrors what gcp/signal_monitor.py does in realtime, but operates on
historical data so the Insights page "Supporting Signals" and "Backtest"
sections have data to display outside of market hours.

Usage:
    python scripts/backfill_signals.py --tickers SPY,IWM,QQQ --days 30
    python scripts/backfill_signals.py --tickers IWM --days 60 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import IndicatorConfig, SignalConfig, load_config
from lib.indicators import (
    calculate_atr,
    calculate_consecutive_moves,
    calculate_ema,
    calculate_obv,
    calculate_rsi,
    calculate_rvol,
    calculate_stoch_rsi,
    calculate_vwap,
)
from lib.signals import evaluate_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def fetch_intraday(ticker: str, days: int) -> pd.DataFrame:
    from gcp.database import query_to_dataframe

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sql = (
        "SELECT ts, open, high, low, close, volume "
        "FROM market_data_intraday "
        "WHERE ticker = :ticker AND ts >= CAST(:cutoff AS timestamptz) "
        "ORDER BY ts"
    )
    df = query_to_dataframe(sql, {"ticker": ticker.upper(), "cutoff": cutoff})
    if df.empty:
        return df
    df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        },
        inplace=True,
    )
    df.set_index("ts", inplace=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def enrich(df: pd.DataFrame, ind_cfg: IndicatorConfig) -> pd.DataFrame:
    out = df.copy()
    out[ind_cfg.rsi_col] = calculate_rsi(out["Close"], ind_cfg.rsi_period)
    out["EMA_9"] = calculate_ema(out["Close"], 9)
    out["EMA_21"] = calculate_ema(out["Close"], 21)
    out["ATR"] = calculate_atr(out["High"], out["Low"], out["Close"], ind_cfg.atr_period)
    dates = pd.Series(out.index.date, index=out.index)
    out["VWAP"] = calculate_vwap(out["High"], out["Low"], out["Close"], out["Volume"], dates)
    out["RVOL"] = calculate_rvol(out["Volume"], ind_cfg.rvol_period)
    out["OBV"] = calculate_obv(out["Close"], out["Volume"])
    k, d = calculate_stoch_rsi(out[ind_cfg.rsi_col], ind_cfg.rsi_period)
    out["StochRSI_K"] = k
    out["StochRSI_D"] = d
    price_change = out["Close"].diff()
    up, down = calculate_consecutive_moves(price_change, periods=3)
    out["ConsecutiveUp"] = up
    out["ConsecutiveDown"] = down
    return out


def run_ticker(
    ticker: str,
    days: int,
    sig_cfg: SignalConfig,
    ind_cfg: IndicatorConfig,
    dry_run: bool,
) -> tuple[int, int]:
    """Return (signals_found, rows_written)."""
    log.info("%s: fetching %d days of intraday bars", ticker, days)
    df = fetch_intraday(ticker, days)
    if df.empty:
        log.warning("%s: no intraday data", ticker)
        return 0, 0

    log.info("%s: %d bars loaded, computing indicators", ticker, len(df))
    df = enrich(df, ind_cfg)

    rows_alerts = []
    rows_trades = []
    # Cooldown: 4h per direction + only keep medium+ signals (total_score>=5).
    # This mirrors what a reasonable live monitor would surface — not every
    # bar that technically passes evaluate_signal() becomes an alert.
    last_signal_ts: dict[str, pd.Timestamp] = {}
    cooldown = pd.Timedelta(hours=4)
    min_score = 3

    for ts, bar in df.iterrows():
        if pd.isna(bar.get(ind_cfg.rsi_col)) or pd.isna(bar.get("ATR")):
            continue

        strat_bonus = 0

        sig = evaluate_signal(
            bar,
            min_conditions=sig_cfg.min_conditions,
            consecutive_periods=sig_cfg.consecutive_periods,
            call_rsi_range=sig_cfg.call_rsi_range,
            put_rsi_range=sig_cfg.put_rsi_range,
            strat_bonus=strat_bonus,
        )
        if not sig:
            continue

        total_score = sig["base_score"] + strat_bonus
        if total_score < min_score:
            continue

        # Respect cooldown per direction
        direction = sig["direction"]
        last = last_signal_ts.get(direction)
        if last is not None and (ts - last) < cooldown:
            continue
        last_signal_ts[direction] = ts
        price = float(bar["Close"])
        atr = float(bar["ATR"])
        # Targets: 1.5 ATR in signal direction; time_stop: 60 min
        target = price + (1.5 * atr if sig["direction"] == "CALL" else -1.5 * atr)

        strength = "weak"
        if total_score >= 7:
            strength = "strong"
        elif total_score >= 5:
            strength = "medium"

        rows_alerts.append(
            {
                "ticker": ticker,
                "alert_ts": ts.to_pydatetime(),
                "alert_date": ts.date(),
                "direction": sig["direction"],
                "base_score": sig["base_score"],
                "strat_bonus": strat_bonus,
                "total_score": total_score,
                "strength_label": strength,
                "position_size": 1.0,
                "price_at_signal": price,
                "target_price": target,
                "time_stop_minutes": 60,
                "rsi": float(bar.get(ind_cfg.rsi_col, 0)),
                "rvol": float(bar.get("RVOL", 0) or 0),
                "orb_5m_high": None,
                "orb_5m_low": None,
                "orb_15m_high": None,
                "orb_15m_low": None,
                "conditions_met": json.dumps(sig.get("conditions_met", [])),
            }
        )

        # Simulate trade outcome over the next 60 bars (~60 min)
        future = df.loc[ts:].iloc[1:61]
        if len(future) == 0:
            continue
        if sig["direction"] == "CALL":
            hit_target = (future["High"] >= target).any()
            exit_reason = "target_hit" if hit_target else "time_stop"
            exit_row = future[future["High"] >= target].iloc[0] if hit_target else future.iloc[-1]
            exit_price = float(target) if hit_target else float(exit_row["Close"])
        else:
            hit_target = (future["Low"] <= target).any()
            exit_reason = "target_hit" if hit_target else "time_stop"
            exit_row = future[future["Low"] <= target].iloc[0] if hit_target else future.iloc[-1]
            exit_price = float(target) if hit_target else float(exit_row["Close"])

        ret = (exit_price - price) / price * 100.0 * (1 if sig["direction"] == "CALL" else -1)

        rows_trades.append(
            {
                "ticker": ticker,
                "direction": sig["direction"],
                "entry_time": ts.to_pydatetime(),
                "entry_price": price,
                "exit_time": exit_row.name.to_pydatetime() if hasattr(exit_row.name, "to_pydatetime") else None,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "signal_strength": total_score,
                "total_score": total_score,
                "position_size": 1.0,
                "return_pct": round(ret, 4),
                "conditions_met": json.dumps(sig.get("conditions_met", [])),
                "strat_combo": None,
                "ftfc_score": 0.0,
                "trade_date": ts.date(),
            }
        )

    log.info("%s: %d signals generated, %d trades simulated", ticker, len(rows_alerts), len(rows_trades))

    if dry_run or not rows_alerts:
        return len(rows_alerts), 0

    from gcp.database import upsert_dataframe

    df_alerts = pd.DataFrame(rows_alerts)
    n_alerts = upsert_dataframe(df_alerts, "signal_alerts", ["ticker", "alert_ts"])
    log.info("%s: wrote %d rows to signal_alerts", ticker, n_alerts)

    df_trades = pd.DataFrame(rows_trades)
    n_trades = upsert_dataframe(df_trades, "trades", ["ticker", "entry_time"])
    log.info("%s: wrote %d rows to trades", ticker, n_trades)

    return len(rows_alerts), n_alerts + n_trades


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default="SPY,IWM,QQQ", help="Comma-separated tickers")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write")
    args = parser.parse_args()

    cfg = load_config()
    sig_cfg = cfg.signal
    ind_cfg = cfg.indicator

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    totals = {"signals": 0, "rows": 0}
    for t in tickers:
        s, r = run_ticker(t, args.days, sig_cfg, ind_cfg, args.dry_run)
        totals["signals"] += s
        totals["rows"] += r

    log.info("DONE: %d signals across %d tickers, %d rows written", totals["signals"], len(tickers), totals["rows"])


if __name__ == "__main__":
    main()
