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
from zoneinfo import ZoneInfo

# Cloud Run runs in UTC. All market-hours comparisons must be in ET so the
# monitor doesn't think the market closes at noon ET (= 16:00 UTC, which
# matches the configured market_close='16:00' under naive comparison).
_ET = ZoneInfo("America/New_York")

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from lib.indicators import (
    calculate_rsi, calculate_ema, calculate_atr, calculate_vwap,
    calculate_rvol, calculate_obv, calculate_stoch_rsi, calculate_consecutive_moves,
    calculate_rvol_recent, calculate_atr_expansion, calculate_rsi_thrust,
)
from lib.signals import evaluate_signal
from lib.strat import StratClassifier
from lib.strat_levels import LevelMap, build_level_map
from lib.config import load_config, get_position_size, get_signal_strength_label
from lib.strategies import MOMENTUM
from lib.strategies.agreement import AGREEMENT_BONUS, detect_agreement
from lib.strategies.brief_bias import alignment as _brief_alignment
from lib.strategies.brief_bias import get_premarket_bias
from lib.strategies.calibration import (
    get_call_rsi_range,
    get_put_rsi_range,
    get_resolution_tier,
)
from lib.strategies.base import Signal
from lib.strategies.timeframe import assign_timeframe
from lib.strategies.catalyst_proximity import get_catalyst_context


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
        self.proximity_cfg = self.cfg.proximity

        self.strat = StratClassifier(strat_config=self.strat_cfg)
        self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
        self.av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')

        # Resolve live signal-monitor watchlist:
        # 1. Cloud SQL `watchlists` table where signals = TRUE AND
        #    removed_at IS NULL — production source of truth, parity
        #    with the in_brief / in_insight pattern.
        # 2. Falls back to alert_config.json's "watchlist" list when
        #    Cloud SQL isn't configured (local dev / pre-migration) or
        #    when the DB query returns zero rows.
        self.tickers = self._resolve_watchlist()

        # Rolling data windows per ticker
        self.windows: dict = {t: pd.DataFrame() for t in self.tickers}
        self.daily_trades: dict = {t: 0 for t in self.tickers}
        self.daily_pnl: dict = {t: 0.0 for t in self.tickers}
        # Track D / G.P0.11 instrumentation: two counters per ticker so we
        # can answer the cross-track question (Tracks C/D/E all surfaced
        # zero momentum fires in 50 days): is momentum gated unreachably,
        # or is the path simply not being entered? Logged in the per-loop
        # summary at end of run_loop. No policy change — instrumentation
        # only. Cross-track sync issue: #304.
        self.momentum_evaluated_count: dict = {t: 0 for t in self.tickers}
        self.momentum_fired_count: dict = {t: 0 for t in self.tickers}
        # Open positions awaiting exit. Each tick the exit-watcher walks
        # this list and fires TARGET HIT / TIME STOP / RSI EXIT alerts +
        # writes the exit details back to signal_alerts. Lifetime is the
        # signal_monitor process itself (≤ one trading session), which is
        # always longer than max(call_time_stop, put_time_stop) = 35 min,
        # so in-memory tracking is sufficient for now.
        self.active_positions: dict = {t: [] for t in self.tickers}
        self.orb_levels: dict = {t: {} for t in self.tickers}

        # Strat level map per ticker, refreshed each loop iteration. Used to
        # detect level breaks (PDH, PDL, PWH, PWL, ...) once per crossing.
        self.level_maps: dict = {t: None for t in self.tickers}
        # Last seen price per ticker, for crossing detection. Avoids firing
        # the same level-break alert on every tick after the break.
        self.last_prices: dict = {t: None for t in self.tickers}
        # Set of (ticker, level_name) that have already fired today.
        self.fired_breaks: set = set()

        # Premarket-brief bias cache (filled lazily, once per ticker per
        # session). Bias is purely informational in Phase 1 — it's
        # displayed in the Discord embed and persisted to signal_alerts
        # so we can later analyse whether brief-aligned signals win more
        # often than brief-opposed ones, without changing fire behavior.
        self._brief_bias_cache: dict = {}

    def _resolve_watchlist(self) -> list[str]:
        """Return the active live-signal-monitor watchlist.

        SINGLE source of truth: `watchlists.signals = TRUE AND
        removed_at IS NULL`, queried via the centralized
        `gcp.fetchers._watchlist.load_watchlist(surface='signals')`.

        Single startup-time query — not per-cycle. A toggle to a
        ticker's `signals` flag mid-session requires a monitor
        restart to take effect.

        On empty result, the helper itself fires a Discord alert
        AND returns []. This method then raises — failing the
        monitor startup loudly rather than silently watching no
        tickers. The Cloud Run failure-notifier sink picks up the
        non-zero exit and creates a GitHub issue.
        """
        from gcp.fetchers._watchlist import load_watchlist

        tickers = load_watchlist(surface="signals")
        if not tickers:
            raise RuntimeError(
                "signal_monitor watchlist is empty — no rows in watchlists "
                "with signals=TRUE AND removed_at IS NULL, and no INSIGHT_TICKERS "
                "env override set. Cannot start monitor. Set the signals flag "
                "for at least one ticker via the platform UI or:\n"
                "  UPDATE watchlists SET signals = TRUE WHERE ticker IN (...)"
            )
        logger.info(
            "watchlist source: watchlists.signals=TRUE — %d tickers: %s",
            len(tickers), ", ".join(tickers),
        )
        return tickers

    def is_market_hours(self) -> bool:
        now = datetime.now(_ET)
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
        # Phase 0.7.x — relaxed 3-of-5 gate columns + 3 new momentum
        # confirmer indicators read by `lib.strategies.MOMENTUM.evaluate`.
        # Without these, every Phase 0.7.x condition silently fails to
        # fire in production because the row.get(...) calls return None.
        df['Consecutive_Up_5'], df['Consecutive_Down_5'] = calculate_consecutive_moves(
            price_change, ind.consecutive_relaxed_window,
        )
        df['RVol_Recent_20'] = calculate_rvol_recent(volume, ind.rvol_period)
        df['ATR_Expansion'] = calculate_atr_expansion(high, low, close, short=5, long=20)
        df['RSI_Thrust_3'] = calculate_rsi_thrust(df[ind.rsi_col], lookback=3)

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
            df = loader.load_daily(ticker, on_stale='warn')
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
        original rationale that estimated ~21% of overlapping fires
        AGREE on direction. Track D audit § 6 (2026-05-08) found the
        actual rate over the May 4-7 window was 17/782 = 2.2% (range
        1.4-3.2% per ticker, QQQ highest), far below the historical
        estimate. The 21% figure was pre-Phase-0.7.x — momentum's gate
        tightened over time, dropping its fire rate without a
        corresponding update to the schema-doc claim. See G.P2.9.
        """
        # Resolve per-ticker RSI ranges (Tier A → Tier B fallback).
        # Both strategies use the same resolved ranges so agreement
        # detection compares apples-to-apples. See
        # lib/strategies/calibration.py for the resolution chain.
        call_rng = get_call_rsi_range(ticker)
        put_rng = get_put_rsi_range(ticker)
        call_tier = get_resolution_tier(ticker, "CALL")
        put_tier = get_resolution_tier(ticker, "PUT")

        sig = evaluate_signal(
            latest,
            min_conditions=self.signal_cfg.min_conditions,
            consecutive_periods=self.signal_cfg.consecutive_periods,
            call_rsi_range=call_rng,
            put_rsi_range=put_rng,
        )
        if sig is None:
            return None, None

        logger.info(
            "%s fire: %s base_score=%.1f call_range=%s tier=%s put_range=%s tier=%s",
            ticker, sig["direction"], sig["base_score"],
            call_rng, call_tier, put_rng, put_tier,
        )

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
        mom_signal = MOMENTUM.evaluate(
            latest, call_rsi_range=call_rng, put_rsi_range=put_rng,
        )
        # Track D / G.P0.11: count every momentum evaluation (the call
        # above) and every successful fire. Combined with mr's short-
        # circuit at line 381, `evaluated` here equals "bars where
        # mr fired AND momentum was checked"; `fired` is the subset
        # where momentum's own gating passed. fired/evaluated ratio
        # directly answers the cross-track question on #304: 0/N → the
        # gate is unreachable; M/N → the gate works and the live
        # path is exercised, so the 50-day-zero-fires pattern was
        # image-lag + sampling.
        self.momentum_evaluated_count[ticker] = (
            self.momentum_evaluated_count.get(ticker, 0) + 1
        )
        if mom_signal is not None:
            self.momentum_fired_count[ticker] = (
                self.momentum_fired_count.get(ticker, 0) + 1
            )
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

        # Exit-watcher — runs FIRST so target/stop alerts fire on the
        # same bar that pushed price across the threshold, before any
        # new entry signal is evaluated for this ticker.
        self._check_exits(ticker, latest, last_price)

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

        # Phase 1.5: catalyst proximity context — looked up once per
        # fire and stashed for fire_alert + _persist_signal_alert.
        # Failure is non-fatal (returns EMPTY_CONTEXT → bucket='quiet'
        # → multiplier=1.0 → no score change). Bucket='during' applies
        # the empirically-validated 0.75x de-weight (Apr holdout
        # showed 8-10pp lower clean rate); 'next_day' gets 1.10x
        # amplification (3pp higher clean rate).
        try:
            self._latest_proximity = get_catalyst_context(
                ticker, pd.Timestamp(datetime.now())
            )
        except Exception as e:
            from lib.strategies.catalyst_proximity import EMPTY_CONTEXT
            logger.debug("catalyst proximity skipped for %s: %s", ticker, e)
            self._latest_proximity = EMPTY_CONTEXT.copy()

        prox_bucket = self._latest_proximity.get('proximity_bucket')
        prox_mult = self.proximity_cfg.get(prox_bucket)
        # Phase 1.6: agreement bonus flows into total_score so a stacked
        # fire actually gets a larger position size (not just a prettier
        # Discord embed). Order: raw_score includes strat + agreement
        # bonuses; proximity multiplier moderates the whole thing — so a
        # stacked fire during an FOMC window still gets de-weighted, but
        # a stacked fire in quiet hours sizes up to the next strength
        # tier.
        agreement_bonus = AGREEMENT_BONUS if agreement else 0.0
        raw_score = sig['base_score'] + strat_bonus + agreement_bonus
        total_score = raw_score * prox_mult
        self._latest_proximity_mult = prox_mult
        self._latest_raw_score = raw_score

        size = get_position_size(total_score, self.risk)
        strength = get_signal_strength_label(total_score, self.risk)

        self.fire_alert(ticker, sig, total_score, strength, size, strat_bonus, latest)

    def fire_alert(self, ticker, sig, total_score, strength, size, strat_bonus, latest):
        """Send signal alert to Discord."""
        direction = sig['direction']
        price = latest.get('Close', latest.get('Last', 0))
        agreement = getattr(self, '_latest_agreement', None)

        # Per-ticker exit overrides (Tier-A). Falls back to ExitConfig
        # defaults when exit_config_overrides has no row / NULL / stale.
        from lib.strategies.exit_config_overrides import (
            get_call_target, get_put_target,
            get_call_time_stop, get_put_time_stop,
        )

        if direction == 'CALL':
            target = price * (1 + get_call_target(ticker))
            time_stop = get_call_time_stop(ticker)
            color = 0x00ff00
        else:
            target = price * (1 - get_put_target(ticker))
            time_stop = get_put_time_stop(ticker)
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
        # Phase 1: timeframe tag in the title — '[15m]' or '[60m]' etc.
        tf_tag = getattr(self, '_latest_timeframe_tag', None)
        tf_label = f" [{tf_tag}]" if tf_tag else ''
        # Phase 1.5: catalyst proximity tag. Non-quiet buckets get a
        # bracket suffix so the trader sees "during FOMC in 0m" or
        # "next_day · earnings_post 4h ago" at fire time.
        proximity = getattr(self, '_latest_proximity', None) or {}
        prox_bucket = proximity.get('proximity_bucket')
        prox_label = ''
        if prox_bucket and prox_bucket != 'quiet':
            ev_type = (proximity.get('next_catalyst_type')
                       or proximity.get('last_catalyst_type') or '')
            mins = (proximity.get('next_catalyst_min')
                    if prox_bucket in ('imminent', 'pre')
                    else proximity.get('last_catalyst_min'))
            time_clause = ''
            if mins is not None:
                time_clause = f' in {mins}m' if prox_bucket in ('imminent', 'pre') else f' {mins}m ago'
            prox_label = f' [{prox_bucket}{":" + ev_type if ev_type else ""}{time_clause}]'

        # Phase 2: brief-bias tag — surfaces alignment between this fired
        # signal and the morning premarket brief. Visibility only — does
        # not modify the fire decision, score, or position size.
        brief = self._resolve_brief_bias(ticker)
        align = _brief_alignment(direction, brief)
        self._latest_brief_bias = brief
        self._latest_brief_alignment = align
        brief_label = ''
        if brief['bias'] == 'CONFLICTED':
            brief_label = ' [brief: CONFLICTED]'
        elif align == 'aligned':
            brief_label = f" [brief: {brief['bias']} ✓ ({brief['setup_count']}/5)]"
        elif align == 'opposed':
            brief_label = f" [AGAINST BRIEF: {brief['bias']} ({brief['setup_count']}/5)]"

        title = (
            f"{title_prefix}{'CALL' if direction == 'CALL' else 'PUT'} SIGNAL"
            f"{tf_label}{prox_label}{brief_label} — {ticker} @ ${price:.2f}"
        )
        agreement_block = ''
        if agreement:
            agreement_block = (
                f"\U0001F3AF STACKED — momentum + mean_reversion both fire {direction}\n"
                f"Composite score: {agreement['composite_score']:.1f}\n"
            )

        # Phase 1.5: warning block for de-weighted catalyst windows.
        # Surfaces the multiplier the empirical weighting applied so
        # the trader sees "score reduced 0.75x because we're inside
        # an FOMC window" rather than wondering why the score is low.
        prox_mult = getattr(self, '_latest_proximity_mult', 1.0)
        raw_score = getattr(self, '_latest_raw_score', total_score)
        proximity_block = ''
        if prox_bucket and prox_bucket != 'quiet' and abs(prox_mult - 1.0) > 0.001:
            verb = 'de-weighted' if prox_mult < 1.0 else 'amplified'
            proximity_block = (
                f"⚠️ Catalyst window: **{prox_bucket}** — "
                f"score {verb} {prox_mult:.2f}× ({raw_score} → {total_score:.1f})\n"
            )

        message = {
            'embeds': [{
                'title': title,
                'description': (
                    f"**Strength: {total_score:.1f}/{max_score} ({strength}) → {size:.0%} size**\n"
                    f"{agreement_block}"
                    f"{proximity_block}"
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

        # Track D / G.P2.5: gate Discord post on configured minimum
        # strength so the channel doesn't drown in weak alerts. Persist
        # always — analytics need every fire regardless of Discord gate.
        # Strength rank: weak < medium < strong < perfect.
        _STRENGTH_RANK = {'weak': 0, 'medium': 1, 'strong': 2, 'perfect': 3}
        post_strength = _STRENGTH_RANK.get((strength or '').lower(), 0)
        min_strength = _STRENGTH_RANK.get(
            (self.monitor_cfg.discord_minimum_strength or 'weak').lower(), 0
        )
        if self.webhook_url and post_strength >= min_strength:
            try:
                requests.post(self.webhook_url, json=message, timeout=self.monitor_cfg.discord_timeout)
            except Exception as e:
                print(f"  Discord send failed: {e}")
        elif self.webhook_url:
            logger.info(
                "Discord post suppressed for %s: strength=%s below minimum=%s",
                ticker, strength, self.monitor_cfg.discord_minimum_strength,
            )

        # Persist to Cloud SQL
        self._persist_signal_alert(ticker, sig, total_score, strength, size,
                                   strat_bonus, latest, target, time_stop)

        # Track D / G.P0.8: increment the per-ticker fire counter so the
        # `max_daily_trades` cap at evaluate_ticker line 437 is enforced.
        # Initialised to 0 in __init__; resets implicitly per-process
        # (the SignalMonitor instance lives one trading session). Pre-fix
        # this counter was never bumped — IWM blew through the 5-fire/day
        # cap by 22× on 5/7 because the cap check `daily_trades[ticker]
        # >= max_daily_trades` was reading a frozen 0.
        self.daily_trades[ticker] = self.daily_trades.get(ticker, 0) + 1

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
            # Pass the Python list/dict directly — SQLAlchemy + pg8000 adapt
            # to native JSONB array/object via the column type reflected by
            # `meta.reflect()` in `gcp/database.upsert_dataframe`. Calling
            # `json.dumps(...)` first causes the value to bind as a JSONB
            # scalar string (a JSON-encoded JSON-array), which breaks
            # `jsonb_array_length` / `@>` predicates and forces every
            # downstream reader to do `(col #>> '{}')::jsonb`. See Track D
            # audit § 6 / G.P0.6.
            'conditions_met': sig['conditions_met'],
            'level_broken': ','.join(getattr(self, '_latest_broken_levels', []) or []) or None,
            # Phase 1.6: JSONB payload (or None) describing the stacked-
            # agreement state. NULL on the common solo-fire path so the
            # column doesn't bloat for the 99% of rows that aren't
            # stacked. Pass dict directly (same JSONB-bind reasoning as
            # `conditions_met` above).
            'strategy_agreement': agreement if agreement else None,
            # Phase 1: timeframe horizon (one of 5m,15m,30m,60m,90m,120m,240m)
            # and the planned hold window. Tagged at fire time by the
            # heuristic in lib/strategies/timeframe.py — never None
            # post-Phase-1 (always tagged with at least the default).
            'timeframe_tag': getattr(self, '_latest_timeframe_tag', None),
            'expected_hold_min': getattr(self, '_latest_expected_hold_min', None),
            # Exit-watcher lifecycle — flipped to FALSE by _persist_exit
            # when the exit-watcher fires a TARGET HIT / TIME STOP / RSI
            # EXIT alert. Lets analytics filter for live positions in O(1)
            # via the partial index idx_signal_alerts_open.
            'is_open': True,
            # Phase 2: brief-bias capture — persists the alignment for
            # later analysis without changing fire behavior.
            'brief_bias':        (getattr(self, '_latest_brief_bias', {}) or {}).get('bias'),
            'brief_alignment':   getattr(self, '_latest_brief_alignment', None),
            'brief_setup_count': (getattr(self, '_latest_brief_bias', {}) or {}).get('setup_count'),
        }

        # Phase 1.5: catalyst proximity — already looked up + stashed
        # in the upstream signal-evaluation block (so the multiplier
        # could affect total_score before persist). Just reuse.
        from lib.strategies.catalyst_proximity import EMPTY_CONTEXT
        proximity = getattr(self, '_latest_proximity', None) or EMPTY_CONTEXT.copy()
        row.update(proximity)

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

        # Track the open position for the exit-watcher. alert_ts here is
        # the same naive UTC value written to the DB row, so the UPDATE
        # in _persist_exit can match by (ticker, alert_ts) PK.
        self.active_positions.setdefault(ticker, []).append({
            'ticker': ticker,
            'alert_ts': now,
            'direction': sig['direction'],
            'entry_price': float(latest.get('Close', latest.get('Last', 0))),
            'target_price': float(target),
            'time_stop_minutes': int(time_stop),
            'score': float(total_score),
            'strength': strength,
            # Track D / G.P0.8: store the position size so `_check_exits`
            # can accumulate sized P&L into `daily_pnl` (matches the
            # backtest path at lib/backtest.py:522 — `return_pct *
            # position_size`). Without this, `_check_exits` would fall
            # back to `size=1.0` and over-count loss accumulation by
            # 5-20× (typical sizes are 5-20% per trade).
            'size': float(size),
        })

    def _resolve_brief_bias(self, ticker: str) -> dict:
        """Lookup-and-cache the premarket-brief bias for this ticker today."""
        if ticker in self._brief_bias_cache:
            return self._brief_bias_cache[ticker]
        try:
            today_et = datetime.now(_ET).date()
            bias = get_premarket_bias(ticker, today_et)
        except Exception as e:
            logger.debug("brief bias lookup failed for %s: %s", ticker, e)
            bias = {'bias': 'UNAVAILABLE', 'alignment': None,
                    'setup_count': 0, 'ftfc_direction': None,
                    'reason': 'lookup_failed'}
        self._brief_bias_cache[ticker] = bias
        return bias

    # ── Exit-watcher ───────────────────────────────────
    # Each tick (per ticker) walks open positions and fires a Discord
    # alert + persists exit details when target/time/RSI conditions are
    # met. Universal RSI thresholds (call_rsi_exit=80, put_rsi_exit=20)
    # come from ExitConfig today; per-ticker calibration is a follow-up
    # that will read from ticker_calibration.rsi_p10/rsi_p90.

    def _check_exits(self, ticker, latest, current_price):
        """Walk open positions for `ticker`, fire exit alerts + persist."""
        positions = self.active_positions.get(ticker)
        if not positions:
            return

        rsi_col = self.indicator_cfg.rsi_col
        current_rsi = float(latest.get(rsi_col, 0) or 0)
        # Naive UTC — matches alert_ts in signal_alerts so elapsed math
        # and the UPDATE WHERE clause stay consistent.
        now_utc = datetime.now()

        for pos in positions[:]:
            elapsed_min = (now_utc - pos['alert_ts']).total_seconds() / 60.0
            exit_reason = None

            if pos['direction'] == 'CALL':
                if current_price >= pos['target_price']:
                    exit_reason = 'target_hit'
                elif elapsed_min >= pos['time_stop_minutes']:
                    exit_reason = 'time_stop'
                elif current_rsi >= self.exit.call_rsi_exit:
                    exit_reason = 'rsi_extreme'
            else:  # PUT
                if current_price <= pos['target_price']:
                    exit_reason = 'target_hit'
                elif elapsed_min >= pos['time_stop_minutes']:
                    exit_reason = 'time_stop'
                elif 0 < current_rsi <= self.exit.put_rsi_exit:
                    exit_reason = 'rsi_extreme'

            if exit_reason:
                self._fire_exit_alert(pos, current_price, exit_reason,
                                      elapsed_min, current_rsi)
                self._persist_exit(pos, current_price, exit_reason, now_utc)
                # Track D / G.P0.8: bump the running P&L counter so the
                # `daily_loss_limit` cap at evaluate_ticker line 439 is
                # enforced. The cap is in *fractional* units (-0.02 =
                # -2%, per lib/config.py:207 + the input-normalization
                # at lib/config.py:541), and the backtest path
                # accumulates `return_pct * position_size` fractional
                # (lib/backtest.py:516-522). Match those units exactly:
                # divide _exit_return_pct's percent by 100 and apply the
                # position size. Legacy positions without a 'size' key
                # default to 1.0 (no sizing). Decoupled from
                # `_persist_exit`'s DB-write success path — the trade
                # exits in-memory regardless of persist outcome.
                pct = self._exit_return_pct(
                    pos['direction'], pos['entry_price'], current_price)
                size = float(pos.get('size', 1.0))
                self.daily_pnl[pos['ticker']] = (
                    self.daily_pnl.get(pos['ticker'], 0.0)
                    + (pct / 100.0) * size
                )
                positions.remove(pos)

    @staticmethod
    def _exit_return_pct(direction, entry_price, exit_price):
        if direction == 'CALL':
            return (exit_price - entry_price) / entry_price * 100.0
        return (entry_price - exit_price) / entry_price * 100.0

    def _fire_exit_alert(self, pos, exit_price, exit_reason, elapsed_min,
                         current_rsi):
        """Post exit alert to Discord."""
        if not self.webhook_url:
            return

        direction = pos['direction']
        return_pct = self._exit_return_pct(direction, pos['entry_price'], exit_price)

        reason_label = {
            'target_hit':  '\U0001F3AF TARGET HIT',
            'time_stop':   '⏰ TIME STOP',
            'rsi_extreme': '\U0001F4CA RSI EXIT',
        }.get(exit_reason, exit_reason.upper())

        # Green for profitable target, amber for time, purple for RSI.
        color = (0x00ff00 if exit_reason == 'target_hit'
                 else 0xffaa00 if exit_reason == 'time_stop'
                 else 0xaa00ff)

        # Convert naive-UTC alert_ts to ET for human-readable display.
        try:
            entry_et = pos['alert_ts'].replace(tzinfo=ZoneInfo("UTC")).astimezone(_ET)
            entry_str = entry_et.strftime('%H:%M:%S ET')
        except Exception:
            entry_str = pos['alert_ts'].strftime('%H:%M:%S')

        title = (f"{reason_label} — {pos['ticker']} {direction} "
                 f"{return_pct:+.2f}%")
        description = (
            f"Entry: ${pos['entry_price']:.2f} @ {entry_str} "
            f"(score {pos['score']:.1f} {pos['strength']})\n"
            f"Exit:  ${exit_price:.2f} after {elapsed_min:.0f} min\n"
            f"Target was: ${pos['target_price']:.2f}"
        )
        if exit_reason == 'rsi_extreme':
            threshold = (self.exit.call_rsi_exit if direction == 'CALL'
                         else self.exit.put_rsi_exit)
            description += f"\nRSI: {current_rsi:.1f} (threshold {threshold:.0f})"

        embed = {
            'title': title,
            'description': description,
            'color': color,
            'timestamp': datetime.now(_ET).isoformat(),
        }
        try:
            requests.post(self.webhook_url, json={'embeds': [embed]},
                          timeout=self.monitor_cfg.discord_timeout)
            logger.info("Exit alert posted: %s %s %s (%+.2f%%)",
                        pos['ticker'], direction, exit_reason, return_pct)
        except Exception as e:
            logger.warning("Exit alert Discord post failed: %s", e)

    def _persist_exit(self, pos, exit_price, exit_reason, exit_ts):
        """Update the signal_alerts row with exit details."""
        try:
            from gcp.database import get_engine, is_cloud_sql_configured
        except ImportError:
            return
        if not is_cloud_sql_configured():
            return

        return_pct = self._exit_return_pct(
            pos['direction'], pos['entry_price'], exit_price)

        from sqlalchemy import text
        sql = text("""
            UPDATE signal_alerts
               SET exit_ts          = :exit_ts,
                   exit_reason      = :reason,
                   exit_price       = :price,
                   exit_return_pct  = :ret,
                   is_open          = FALSE
             WHERE ticker   = :ticker
               AND alert_ts = :alert_ts
        """)
        try:
            with get_engine().begin() as conn:
                conn.execute(sql, {
                    'exit_ts':  exit_ts,
                    'reason':   exit_reason,
                    'price':    float(exit_price),
                    'ret':      float(return_pct),
                    'ticker':   pos['ticker'],
                    'alert_ts': pos['alert_ts'],
                })
        except Exception as e:
            logger.warning("Exit persist failed for %s %s: %s",
                           pos['ticker'], pos['alert_ts'], e)

    def run_loop(self):
        """Main market-hours loop."""
        tickers = self.tickers
        poll_interval = self.monitor_cfg.poll_interval

        print("Signal Monitor started")
        print(f"Tickers: {', '.join(tickers)}")
        print(f"Poll interval: {poll_interval}s")
        print(f"Discord: {'configured' if self.webhook_url else 'NOT configured'}")

        while True:
            if not self.is_market_hours():
                now = datetime.now(_ET)
                if now.time() > self.market_cfg.market_close_time:
                    print("Market closed. Shutting down.")
                    # Track D / G.P0.11: log per-ticker momentum
                    # instrumentation summary so the cross-track sync
                    # (issue #304) can read the diagnostic counts from
                    # Cloud Logging without a separate persistence layer.
                    for t in tickers:
                        logger.info(
                            "session_summary ticker=%s momentum_evaluated=%d "
                            "momentum_fired=%d daily_trades=%d daily_pnl=%.4f",
                            t,
                            self.momentum_evaluated_count.get(t, 0),
                            self.momentum_fired_count.get(t, 0),
                            self.daily_trades.get(t, 0),
                            self.daily_pnl.get(t, 0.0),
                        )
                    break
                print(f"Waiting for market open ({now.strftime('%H:%M:%S %Z')})...")
                time_module.sleep(self.monitor_cfg.pre_market_sleep)
                continue

            print(f"\n[{datetime.now(_ET).strftime('%H:%M:%S %Z')}] Polling...")

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
    for ticker in monitor.tickers:
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
    # Configure root logger BEFORE any logger.info call lands. Pre-fix
    # the deployed `python -m gcp.signal_monitor` had no basicConfig, so
    # Python's default WARNING level suppressed every INFO log including
    # the new session_summary lines (Codex P1 review on PR #320). All
    # existing logger.info calls in this module (watchlist source at
    # line 141, mr fire at line 383, exit alerts, persist results, etc.)
    # were also silently dropped from Cloud Logging — fixing this
    # surfaces them as a positive externality.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    import argparse
    parser = argparse.ArgumentParser(description='Real-time signal monitor')
    parser.add_argument('--mode', choices=['loop', 'orb-snapshot', 'replay'],
                        default='loop',
                        help='loop = run during market hours; '
                             'orb-snapshot = one-shot ORB capture; '
                             'replay = hermetic 1-min-bar replay against '
                             'historical data (mocks Discord + DB writes; '
                             'dispatches to scripts.replay_signal_monitor)')
    parser.add_argument('--window', choices=['5m', '15m', '30m'], default='15m',
                        help='ORB window for orb-snapshot mode')
    # Replay-mode flags. Mirror scripts/replay_signal_monitor.py so a
    # user familiar with one knows the other. Env-var defaults
    # (REPLAY_TICKER / REPLAY_TICKERS / REPLAY_DATE / REPLAY_START /
    # REPLAY_END) let `gcloud run jobs execute signal-monitor
    # --update-env-vars=...` override at execute time without rebuilding
    # the job spec — the cleanest deploy pattern for one-off historical
    # replays since gcloud run jobs execute supports --update-env-vars
    # but not --args injection.
    parser.add_argument('--ticker', default=os.environ.get('REPLAY_TICKER'),
                        help='[replay] Single ticker (alias for --tickers TICKER)')
    parser.add_argument('--tickers', default=os.environ.get('REPLAY_TICKERS'),
                        help='[replay] Comma-separated tickers')
    parser.add_argument('--date', default=os.environ.get('REPLAY_DATE'),
                        help='[replay] Single date YYYY-MM-DD '
                             '(alias for --start = --end)')
    parser.add_argument('--start', default=os.environ.get('REPLAY_START'),
                        help='[replay] UTC start date YYYY-MM-DD')
    parser.add_argument('--end', default=os.environ.get('REPLAY_END'),
                        help='[replay] UTC end date YYYY-MM-DD (exclusive)')
    parser.add_argument('--limit', type=int, default=None,
                        help='[replay] Max bars per ticker (debug/dev)')
    parser.add_argument('--json', action='store_true',
                        help='[replay] Print fires as a JSON array')
    args = parser.parse_args()

    # Implicit replay activation: setting REPLAY_DATE or REPLAY_TICKER
    # at execute time is sufficient — no need to also pass
    # --mode=replay. Keeps the override surface minimal.
    if args.mode == 'loop' and (
        os.environ.get('REPLAY_DATE')
        or os.environ.get('REPLAY_TICKER')
        or os.environ.get('REPLAY_TICKERS')
    ):
        logger.info(
            "REPLAY_* env var detected — switching to --mode=replay")
        args.mode = 'replay'

    # Fail-fast on missing config so Cloud Run surfaces the error instead of
    # looping silently (see docs/incidents/2026-04-14-market-data-daily-gap.md).
    from gcp.database import is_cloud_sql_configured
    if not os.environ.get('ALPHA_VANTAGE_API_KEY') and args.mode != 'replay':
        # Replay reads from market_data_intraday (Cloud SQL only); does
        # not fetch fresh bars from AV.
        logger.error("ALPHA_VANTAGE_API_KEY is not set — aborting.")
        sys.exit(2)
    if not is_cloud_sql_configured() and args.mode in ('loop', 'replay'):
        logger.error("Cloud SQL env vars missing — aborting.")
        sys.exit(3)

    if args.mode == 'orb-snapshot':
        sys.exit(run_orb_snapshot(args.window))

    if args.mode == 'replay':
        # Dispatch to the canonical hermetic replay harness in
        # scripts/replay_signal_monitor.py. That script's main() takes
        # an argv list (or None for sys.argv); we build it from our
        # parsed args so the env-var override path produces the same
        # behaviour as a direct CLI invocation.
        from scripts.replay_signal_monitor import (
            main as _replay_main,
        )
        replay_argv: list[str] = []
        if args.ticker:
            replay_argv += ['--ticker', args.ticker]
        if args.tickers:
            replay_argv += ['--tickers', args.tickers]
        if args.date:
            replay_argv += ['--date', args.date]
        if args.start:
            replay_argv += ['--start', args.start]
        if args.end:
            replay_argv += ['--end', args.end]
        if args.limit is not None:
            replay_argv += ['--limit', str(args.limit)]
        if args.json:
            replay_argv += ['--json']
        sys.exit(_replay_main(replay_argv))

    monitor = SignalMonitor()
    monitor.run_loop()


if __name__ == '__main__':
    main()
