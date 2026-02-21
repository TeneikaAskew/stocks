#!/usr/bin/env python3
"""
Real-time signal monitor -- Cloud Run Service during market hours.

Polls Yahoo Finance every 60 seconds, maintains a rolling indicator window,
evaluates signals, and fires Discord alerts when conditions align.
"""

import os
import sys
import json
import time as time_module
import requests
from pathlib import Path
from datetime import datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from lib.indicators import (
    calculate_rsi, calculate_ema, calculate_atr, calculate_vwap,
    calculate_rvol, calculate_obv, calculate_stoch_rsi, calculate_consecutive_moves,
)
from lib.signals import evaluate_signal
from lib.strat import StratClassifier
from lib.config import load_config, get_position_size, get_signal_strength_label


class SignalMonitor:
    """Real-time signal monitor for market hours."""

    def __init__(self):
        self.cfg = load_config()
        self.risk = self.cfg.risk
        self.exit = self.cfg.exit
        self.signal_cfg = self.cfg.signal
        self.strat_cfg = self.cfg.strat
        self.indicator_cfg = self.cfg.indicator
        self.monitor_cfg = self.cfg.monitor
        self.market_cfg = self.cfg.market

        self.strat = StratClassifier(strat_config=self.strat_cfg)
        self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')

        tickers = self.market_cfg.tickers
        # Rolling data windows per ticker
        self.windows: dict = {t: pd.DataFrame() for t in tickers}
        self.daily_trades: dict = {t: 0 for t in tickers}
        self.daily_pnl: dict = {t: 0.0 for t in tickers}
        self.active_positions: dict = {t: None for t in tickers}
        self.orb_levels: dict = {t: {} for t in tickers}

    def is_market_hours(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        return self.market_cfg.market_open_time <= now.time() <= self.market_cfg.market_close_time

    def fetch_latest_bar(self, ticker: str) -> pd.DataFrame:
        """Fetch the latest 1-minute bar from Yahoo Finance."""
        try:
            import yfinance as yf
            symbol = ticker if ticker != 'SPX' else '^GSPC'
            data = yf.download(symbol, period='1d', interval='1m', progress=False, prepost=False)
            if data.empty:
                return pd.DataFrame()
            # Normalize columns
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(-1)
            data['Time'] = data.index
            return data
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")
            return pd.DataFrame()

    def update_window(self, ticker: str, new_data: pd.DataFrame):
        """Append new data to the rolling window, keep last N bars."""
        if new_data.empty:
            return
        existing = self.windows[ticker]
        combined = pd.concat([existing, new_data]).drop_duplicates(subset=['Time'], keep='last')
        self.windows[ticker] = combined.tail(self.monitor_cfg.rolling_window_bars).reset_index(drop=True)

    def calculate_indicators(self, ticker: str) -> pd.DataFrame:
        """Calculate indicators on the rolling window."""
        df = self.windows[ticker].copy()
        if len(df) < self.monitor_cfg.min_bars_for_indicators:
            return df

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        ind = self.indicator_cfg

        df[ind.rsi_col] = calculate_rsi(close, ind.rsi_period)
        df[f'EMA{ind.ema_fast_period}'] = calculate_ema(close, ind.ema_fast_period)
        df[f'EMA{ind.ema_mid_period}'] = calculate_ema(close, ind.ema_mid_period)
        df[ind.atr_col] = calculate_atr(high, low, close, ind.atr_period)

        # VWAP
        dates = pd.to_datetime(df['Time']).dt.date
        df['VWAP'] = calculate_vwap(high, low, close, volume, dates)

        df['RVOL'] = calculate_rvol(volume, ind.rvol_period)
        df['OBV'] = calculate_obv(close, volume)

        stoch_k, stoch_d = calculate_stoch_rsi(df[ind.rsi_col])
        df['StochRSI_K'] = stoch_k
        df['StochRSI_D'] = stoch_d

        price_change = close.pct_change() * 100
        df['Price_Change'] = price_change
        df['Consecutive_Up'], df['Consecutive_Down'] = calculate_consecutive_moves(
            price_change, ind.consecutive_periods,
        )

        df['Price_vs_VWAP'] = (close - df['VWAP']) / df['VWAP'] * 100
        df[ind.price_vs_ema_fast_col] = (close - df[f'EMA{ind.ema_fast_period}']) / df[f'EMA{ind.ema_fast_period}'] * 100
        df[ind.price_vs_ema_mid_col] = (close - df[f'EMA{ind.ema_mid_period}']) / df[f'EMA{ind.ema_mid_period}'] * 100

        return df

    def check_orb(self, ticker: str, df: pd.DataFrame):
        """Track ORB levels as they form."""
        if df.empty or 'Time' not in df.columns:
            return

        market_open = self.market_cfg.market_open_time
        times = pd.to_datetime(df['Time'])
        for minutes, label in [(5, '5m'), (15, '15m'), (30, '30m')]:
            orb_end = time(9, 30 + minutes) if minutes < 30 else time(10, 0)
            in_orb = (times.dt.time >= market_open) & (times.dt.time <= orb_end)
            orb_data = df[in_orb]
            if not orb_data.empty:
                self.orb_levels[ticker][f'{label}_high'] = orb_data['High'].max()
                self.orb_levels[ticker][f'{label}_low'] = orb_data['Low'].min()
                self.orb_levels[ticker][f'{label}_mid'] = (
                    self.orb_levels[ticker][f'{label}_high'] +
                    self.orb_levels[ticker][f'{label}_low']
                ) / 2

    def evaluate_ticker(self, ticker: str):
        """Evaluate signals for a single ticker."""
        df = self.calculate_indicators(ticker)
        if len(df) < self.monitor_cfg.min_bars_for_signals:
            return

        self.check_orb(ticker, df)

        latest = df.iloc[-1]

        # Skip if at daily limits
        if self.daily_trades[ticker] >= self.risk.max_daily_trades:
            return
        if self.daily_pnl[ticker] <= self.risk.daily_loss_limit:
            return

        # Evaluate signal
        sig = evaluate_signal(
            latest,
            min_conditions=self.signal_cfg.min_conditions,
            consecutive_periods=self.signal_cfg.consecutive_periods,
            call_rsi_range=self.signal_cfg.call_rsi_range,
            put_rsi_range=self.signal_cfg.put_rsi_range,
        )

        if sig is None:
            return

        # Strat bonus
        strat_bonus = 0
        if self.strat_cfg.enabled:
            strat_data = self.strat.detect_combos(df)
            combo = strat_data['strat_combo'].iloc[-1] if not strat_data.empty else 'none'
            orb_trend = 0
            orb_5m_high = self.orb_levels[ticker].get('5m_high')
            orb_5m_low = self.orb_levels[ticker].get('5m_low')
            if orb_5m_high and latest['Close'] > orb_5m_high:
                orb_trend = 1
            elif orb_5m_low and latest['Close'] < orb_5m_low:
                orb_trend = -1

            strat_bonus = self.strat.get_strat_bonus(
                signal_direction=sig['direction'],
                combo=combo,
                ftfc_score=0.0,
                orb_trend=orb_trend,
            )

        total_score = sig['base_score'] + strat_bonus
        size = get_position_size(total_score, self.risk)
        strength = get_signal_strength_label(total_score, self.risk)

        self.fire_alert(ticker, sig, total_score, strength, size, strat_bonus, latest)

    def fire_alert(self, ticker, sig, total_score, strength, size, strat_bonus, latest):
        """Send signal alert to Discord."""
        direction = sig['direction']
        price = latest.get('Close', latest.get('Last', 0))

        if direction == 'CALL':
            target = price * (1 + self.exit.call_target)
            time_stop = self.exit.call_time_stop
            color = 0x00ff00
        else:
            target = price * (1 - self.exit.put_target)
            time_stop = self.exit.put_time_stop
            color = 0xff0000

        max_score = self.risk.max_score
        conditions_str = '\n'.join([f"  {c}" for c in sig['conditions_met']])
        orb_info = ""
        for label in ['5m', '15m']:
            h = self.orb_levels[ticker].get(f'{label}_high')
            l = self.orb_levels[ticker].get(f'{label}_low')
            if h and l:
                orb_info += f"\nORB {label}: ${l:.2f} - ${h:.2f}"

        message = {
            'embeds': [{
                'title': f"{'CALL' if direction == 'CALL' else 'PUT'} SIGNAL \u2014 {ticker} @ ${price:.2f}",
                'description': (
                    f"**Strength: {total_score}/{max_score} ({strength}) \u2192 {size:.0%} size**\n"
                    f"Base: {sig['base_score']}/5 | Strat bonus: +{strat_bonus}\n\n"
                    f"Conditions met:\n{conditions_str}\n\n"
                    f"Target: ${target:.2f} | Time stop: {time_stop} min\n"
                    f"RSI: {latest.get(self.indicator_cfg.rsi_col, 0):.1f} | "
                    f"RVOL: {latest.get('RVOL', 0):.2f}x"
                    f"{orb_info}"
                ),
                'color': color,
                'timestamp': datetime.utcnow().isoformat(),
            }]
        }

        print(f"\n{'='*50}")
        print(json.dumps(message['embeds'][0], indent=2))
        print(f"{'='*50}\n")

        if self.webhook_url:
            try:
                requests.post(self.webhook_url, json=message, timeout=self.monitor_cfg.discord_timeout)
            except Exception as e:
                print(f"  Discord send failed: {e}")

    def run_loop(self):
        """Main market-hours loop."""
        tickers = self.market_cfg.tickers
        poll_interval = self.monitor_cfg.poll_interval

        print("Signal Monitor started")
        print(f"Tickers: {', '.join(tickers)}")
        print(f"Poll interval: {poll_interval}s")
        print(f"Discord: {'configured' if self.webhook_url else 'NOT configured'}")

        while True:
            if not self.is_market_hours():
                now = datetime.now()
                if now.time() > self.market_cfg.market_close_time:
                    print("Market closed. Shutting down.")
                    break
                print(f"Waiting for market open ({now.strftime('%H:%M:%S')})...")
                time_module.sleep(self.monitor_cfg.pre_market_sleep)
                continue

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Polling...")

            for ticker in tickers:
                new_data = self.fetch_latest_bar(ticker)
                self.update_window(ticker, new_data)
                self.evaluate_ticker(ticker)

            time_module.sleep(poll_interval)


def main():
    monitor = SignalMonitor()
    monitor.run_loop()


if __name__ == '__main__':
    main()
