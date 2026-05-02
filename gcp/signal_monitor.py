#!/usr/bin/env python3
"""
Real-time signal monitor -- Cloud Run Service during market hours.

Polls AlphaVantage every 60 seconds, maintains a rolling indicator window,
evaluates signals, and fires Discord alerts when conditions align.
"""

import os
import sys
import json
import logging
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
from lib.strat_levels import LevelMap, build_level_map
from lib.config import load_config, get_position_size, get_signal_strength_label
from lib.strategies import MOMENTUM
from lib.strategies.agreement import detect_agreement
from lib.strategies.base import Signal
from lib.strategies.timeframe import assign_timeframe


logger = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'


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
        self.av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')

        tickers = self.market_cfg.tickers
        # Rolling data windows per ticker
        self.windows: dict = {t: pd.DataFrame() for t in tickers}
        self.daily_trades: dict = {t: 0 for t in tickers}
        self.daily_pnl: dict = {t: 0.0 for t in tickers}
        self.active_positions: dict = {t: None for t in tickers}
        self.orb_levels: dict = {t: {} for t in tickers}

        # Strat level map per ticker, refreshed each loop iteration. Used to
        # detect level breaks (PDH, PDL, PWH, PWL, ...) once per crossing.
        self.level_maps: dict = {t: None for t in tickers}
        # Last seen price per ticker, for crossing detection. Avoids firing
        # the same level-break alert on every tick after the break.
        self.last_prices: dict = {t: None for t in tickers}
        # Set of (ticker, level_name) that have already fired today.
        self.fired_breaks: set = set()

    def is_market_hours(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        return self.market_cfg.market_open_time <= now.time() <= self.market_cfg.market_close_time

    def fetch_latest_bar(self, ticker: str) -> pd.DataFrame:
        """Fetch the latest 1-minute bars from AlphaVantage TIME_SERIES_INTRADAY."""
        if not self.av_api_key:
            print(f"  No AV API key — cannot fetch {ticker}")
            return pd.DataFrame()

        symbol = ticker  # AV uses plain symbols (SPX, not ^GSPC)
        params = {
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': symbol,
            'interval': '1min',
            'outputsize': 'compact',  # last 100 data points
            'adjusted': 'true',
            # signal_monitor checks live triggers — must use realtime
            # entitlement, otherwise AV returns historical-only.
            'entitlement': 'realtime',
            'extended_hours': 'true',
            'apikey': self.av_api_key,
            'datatype': 'json',
        }
        try:
            resp = requests.get(AV_BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if 'Error Message' in data or 'Information' in data or 'Note' in data:
                print(f"  AV error for {ticker}: {data.get('Error Message', data.get('Information', data.get('Note', '')))}")
                return pd.DataFrame()

            ts_key = 'Time Series (1min)'
            ts = data.get(ts_key, {})
            if not ts:
                return pd.DataFrame()

            df = pd.DataFrame.from_dict(ts, orient='index')
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = pd.to_numeric(df[col])
            df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Filter to today only
            today = datetime.now().date()
            df = df[df.index.date == today]

            if df.empty:
                return pd.DataFrame()

            df['Time'] = df.index
            return df
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

    def refresh_level_map(self, ticker: str) -> None:
        """Load the latest market_data_daily row + indicators and rebuild
        the LevelMap for this ticker. Called at startup and periodically
        through the day (prev-period levels do not change intraday but
        current-period classifications do).
        """
        try:
            from lib.data_loader import DataLoader
            from lib.indicators import calculate_historical_levels
            loader = DataLoader(data_dir=self.market_cfg.data_dir)
            df = loader.load_daily(ticker)
            if df.empty:
                self.level_maps[ticker] = None
                return
            close_col = 'Close' if 'Close' in df.columns else 'Last'
            ts = df['Time'] if 'Time' in df.columns else pd.Series(df.index)
            levels_df = calculate_historical_levels(
                ts, df['High'], df['Low'], df['Open'], df[close_col],
            )
            for col in levels_df.columns:
                df[col] = levels_df[col].values

            # Use the latest live close as current_price; the actual price
            # will be passed in check_level_breaks for crossing detection.
            current_price = float(df[close_col].iloc[-1])
            self.level_maps[ticker] = build_level_map(
                ticker=ticker, daily_df=df, current_price=current_price,
            )
        except Exception as e:
            logger.warning("refresh_level_map(%s) failed: %s", ticker, e)
            self.level_maps[ticker] = None

    def check_level_breaks(
        self,
        ticker: str,
        last_price: float,
        prev_price,
        level_map: LevelMap,
    ) -> list:
        """Return level names that were crossed between prev_price and
        last_price, deduped against the day's already-fired breaks.

        Fires once per (ticker, level_name) per session.
        """
        if level_map is None or prev_price is None:
            return []
        broken: list = []
        for lev in level_map.levels:
            crossed_up = prev_price <= lev.price < last_price
            crossed_down = prev_price >= lev.price > last_price
            if not (crossed_up or crossed_down):
                continue
            key = (ticker, lev.name, 'up' if crossed_up else 'down')
            if key in self.fired_breaks:
                continue
            self.fired_breaks.add(key)
            broken.append(lev.name)
        return broken

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

    def _evaluate_strategies_for_bar(self, latest, last_price: float, ticker: str):
        """Run mean-reversion + momentum on the same bar; detect agreement.

        Returns a (sig_dict, agreement_payload) tuple:
          * `sig_dict` — the existing mean-reversion dict from
            `evaluate_signal`, or `None` when mean-reversion didn't
            fire. Existing fire/persist code paths consume this
            unchanged, so the fire criteria are not expanded by this
            change. (When mean-reversion doesn't fire, agreement can't
            apply; we short-circuit to avoid running momentum.)
          * `agreement_payload` — `None` when fewer than two strategies
            fired or they disagree on direction; otherwise the dict
            from `lib.strategies.agreement.detect_agreement` carrying
            the composite score for embed sort + JSONB persistence.

        See `docs/plans/SIGNAL_QUALITY_TEST_PLAN.md` Phase 1.6 for the
        rationale: ~21% of overlapping fires AGREE on direction (high-
        conviction stacked signals); ~79% DISAGREE (informative noise).
        """
        sig = evaluate_signal(
            latest,
            min_conditions=self.signal_cfg.min_conditions,
            consecutive_periods=self.signal_cfg.consecutive_periods,
            call_rsi_range=self.signal_cfg.call_rsi_range,
            put_rsi_range=self.signal_cfg.put_rsi_range,
        )
        if sig is None:
            return None, None

        # Build a Signal facade from the mr dict so detect_agreement
        # can compare it against MomentumStrategy's Signal output. We
        # don't replace the existing mr eval call because the dict
        # shape is what every downstream consumer (fire_alert,
        # _persist_signal_alert, TradeLogger) reads — replacing it
        # would balloon this PR into a cross-cutting refactor.
        mr_signal = Signal(
            strategy="mean_reversion",
            direction=sig["direction"],
            timestamp=pd.Timestamp(latest.get("Time") or datetime.now()),
            entry_price=float(last_price),
            base_score=float(sig["base_score"]),
            weighted_score=float(sig["base_score"]),
            conditions_met=list(sig["conditions_met"]),
        )
        mom_signal = MOMENTUM.evaluate(latest)
        agreement = detect_agreement(mom_signal, mr_signal)
        return sig, agreement

    def evaluate_ticker(self, ticker: str):
        """Evaluate signals for a single ticker."""
        df = self.calculate_indicators(ticker)
        if len(df) < self.monitor_cfg.min_bars_for_signals:
            return

        self.check_orb(ticker, df)

        latest = df.iloc[-1]
        last_price = float(latest.get('Close', latest.get('Last', 0)))

        # Level-break detection. Refreshes lazily once per day per ticker.
        if self.level_maps.get(ticker) is None:
            self.refresh_level_map(ticker)
        broken_levels = self.check_level_breaks(
            ticker, last_price, self.last_prices.get(ticker),
            self.level_maps.get(ticker),
        )
        self.last_prices[ticker] = last_price
        self._latest_broken_levels = broken_levels

        # Skip if at daily limits
        if self.daily_trades[ticker] >= self.risk.max_daily_trades:
            return
        if self.daily_pnl[ticker] <= self.risk.daily_loss_limit:
            return

        # Evaluate signal — Phase 1.6: also runs momentum on the same
        # bar and detects agreement when both fire same direction.
        sig, agreement = self._evaluate_strategies_for_bar(latest, last_price, ticker)
        if sig is None:
            return
        # Stash for fire_alert + _persist_signal_alert (per-call frame,
        # mirrors the `_latest_broken_levels` pattern just above).
        self._latest_agreement = agreement

        # Phase 1: predict the timeframe horizon for this fire.
        # Pure helper, no I/O. Uses RVOL + ATR + condition pattern to
        # tag the signal with one of {5m,15m,30m,60m,...}. Persisted
        # to signal_alerts so consumers can match exit logic to the
        # signal class.
        tf_tag, tf_hold = assign_timeframe(
            sig['conditions_met'],
            rsi=latest.get(self.indicator_cfg.rsi_col),
            rvol=latest.get('RVOL'),
            atr_5m_pct=(latest.get('ATR14', 0) / last_price) if last_price > 0 else None,
        )
        self._latest_timeframe_tag = tf_tag
        self._latest_expected_hold_min = tf_hold

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
        agreement = getattr(self, '_latest_agreement', None)

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

        # Phase 1.6: stacked-agreement signals get a visual prefix so
        # they jump out in the Discord channel scroll.
        title_prefix = '\U0001F3AF STACKED ' if agreement else ''
        # Phase 1: timeframe tag in the title \u2014 '[15m]' or '[60m]' etc.
        tf_tag = getattr(self, '_latest_timeframe_tag', None)
        tf_label = f" [{tf_tag}]" if tf_tag else ''
        title = (
            f"{title_prefix}{'CALL' if direction == 'CALL' else 'PUT'} SIGNAL"
            f"{tf_label} \u2014 {ticker} @ ${price:.2f}"
        )
        agreement_block = ''
        if agreement:
            agreement_block = (
                f"\U0001F3AF STACKED \u2014 momentum + mean_reversion both fire {direction}\n"
                f"Composite score: {agreement['composite_score']:.1f}\n"
            )

        message = {
            'embeds': [{
                'title': title,
                'description': (
                    f"**Strength: {total_score}/{max_score} ({strength}) \u2192 {size:.0%} size**\n"
                    f"{agreement_block}"
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

        # Persist to Cloud SQL
        self._persist_signal_alert(ticker, sig, total_score, strength, size,
                                   strat_bonus, latest, target, time_stop)

    def _persist_signal_alert(self, ticker, sig, total_score, strength, size,
                              strat_bonus, latest, target, time_stop):
        """Write signal alert row to Cloud SQL signal_alerts table."""
        try:
            from gcp.database import is_cloud_sql_configured, upsert_dataframe
        except ImportError:
            return

        if not is_cloud_sql_configured():
            return

        now = datetime.now()
        agreement = getattr(self, '_latest_agreement', None)
        row = {
            'ticker': ticker,
            'alert_ts': now,
            'alert_date': now.date(),
            'direction': sig['direction'],
            'base_score': sig['base_score'],
            'strat_bonus': strat_bonus,
            'total_score': total_score,
            'strength_label': strength,
            'position_size': size,
            'price_at_signal': float(latest.get('Close', latest.get('Last', 0))),
            'target_price': float(target),
            'time_stop_minutes': int(time_stop),
            'rsi': float(latest.get(self.indicator_cfg.rsi_col, 0)),
            'rvol': float(latest.get('RVOL', 0)),
            'orb_5m_high': self.orb_levels[ticker].get('5m_high'),
            'orb_5m_low': self.orb_levels[ticker].get('5m_low'),
            'orb_15m_high': self.orb_levels[ticker].get('15m_high'),
            'orb_15m_low': self.orb_levels[ticker].get('15m_low'),
            'conditions_met': json.dumps(sig['conditions_met']),
            'level_broken': ','.join(getattr(self, '_latest_broken_levels', []) or []) or None,
            # Phase 1.6: JSONB payload (or None) describing the stacked-
            # agreement state. NULL on the common solo-fire path so the
            # column doesn't bloat for the 99% of rows that aren't
            # stacked.
            'strategy_agreement': json.dumps(agreement) if agreement else None,
            # Phase 1: timeframe horizon (one of 5m,15m,30m,60m,90m,120m,240m)
            # and the planned hold window. Tagged at fire time by the
            # heuristic in lib/strategies/timeframe.py — never None
            # post-Phase-1 (always tagged with at least the default).
            'timeframe_tag': getattr(self, '_latest_timeframe_tag', None),
            'expected_hold_min': getattr(self, '_latest_expected_hold_min', None),
        }

        try:
            df = pd.DataFrame([row])
            n = upsert_dataframe(df, 'signal_alerts', ['ticker', 'alert_ts'])
            logger.info("Upserted %d row(s) to signal_alerts for %s", n, ticker)
        except Exception as e:
            logger.warning("signal_alerts upsert failed: %s", e)

        # Also log as a trade entry via TradeLogger
        try:
            from gcp.trade_logger import TradeLogger
            trade_data = {
                'ticker': ticker,
                'direction': sig['direction'],
                'entry_time': now,
                'entry_price': float(latest.get('Close', latest.get('Last', 0))),
                'signal_strength': total_score,
                'total_score': total_score,
                'position_size': size,
                'conditions_met': sig['conditions_met'],
                'trade_date': str(now.date()),
            }
            TradeLogger().log_trade(trade_data)
            logger.info("Trade logged for %s %s", ticker, sig['direction'])
        except Exception as e:
            logger.warning("Trade logging failed: %s", e)

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


def run_orb_snapshot(window: str) -> int:
    """One-shot ORB capture mode for Cloud Scheduler (9:45 / 10:00 ET).

    Computes the ORB H/L/Mid for the requested window and posts a Discord
    embed per ticker. Returns process exit code (0 on success).
    """
    if window not in {'5m', '15m', '30m'}:
        logger.error("Invalid ORB window: %s (expected 5m/15m/30m)", window)
        return 2

    monitor = SignalMonitor()
    for ticker in monitor.market_cfg.tickers:
        df = monitor.fetch_latest_bar(ticker)
        if df.empty:
            logger.warning("No intraday data for %s", ticker)
            continue
        monitor.check_orb(ticker, df)
        levels = monitor.orb_levels.get(ticker, {})
        h = levels.get(f'{window}_high')
        l = levels.get(f'{window}_low')
        m = levels.get(f'{window}_mid')
        if h is None or l is None:
            logger.warning("ORB %s incomplete for %s", window, ticker)
            continue
        message = {
            'embeds': [{
                'title': f'{ticker} {window} ORB',
                'description': (
                    f'High: ${h:.2f}\nLow: ${l:.2f}\nMid: ${m:.2f}\n'
                    f'Range: ${h - l:.2f}'
                ),
                'color': 0x9b59b6,
            }],
        }
        if monitor.webhook_url:
            try:
                requests.post(monitor.webhook_url, json=message,
                              timeout=monitor.monitor_cfg.discord_timeout)
            except Exception as e:
                logger.warning("Discord ORB snapshot send failed for %s: %s", ticker, e)
        else:
            print(json.dumps(message['embeds'][0], indent=2))
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Real-time signal monitor')
    parser.add_argument('--mode', choices=['loop', 'orb-snapshot'], default='loop',
                        help='loop = run during market hours; orb-snapshot = one-shot ORB capture')
    parser.add_argument('--window', choices=['5m', '15m', '30m'], default='15m',
                        help='ORB window for orb-snapshot mode')
    args = parser.parse_args()

    # Fail-fast on missing config so Cloud Run surfaces the error instead of
    # looping silently (see docs/incidents/2026-04-14-market-data-daily-gap.md).
    from gcp.database import is_cloud_sql_configured
    if not os.environ.get('ALPHA_VANTAGE_API_KEY'):
        logger.error("ALPHA_VANTAGE_API_KEY is not set — aborting.")
        sys.exit(2)
    if not is_cloud_sql_configured() and args.mode == 'loop':
        logger.error("Cloud SQL env vars missing — aborting.")
        sys.exit(3)

    if args.mode == 'orb-snapshot':
        sys.exit(run_orb_snapshot(args.window))

    monitor = SignalMonitor()
    monitor.run_loop()


if __name__ == '__main__':
    main()
