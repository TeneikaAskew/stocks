#!/usr/bin/env python3
"""
Real-time signal monitor -- Cloud Run Service during market hours.

Polls AlphaVantage every 60 seconds, maintains a rolling indicator window,
evaluates signals, and fires Discord alerts when conditions align.
"""

import os
import sys
import json
import dataclasses
import logging
import time as time_module
import requests
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# Cloud Run runs in UTC. All market-hours comparisons must be in ET so the
# monitor doesn't think the market closes at noon ET (= 16:00 UTC, which
# matches the configured market_close='16:00' under naive comparison).
_ET = ZoneInfo("America/New_York")

# RTH bounds for the session-extremes tracker (level-aware brief
# alignment). Premarket/afterhours bars must not count as "the session
# traded through the brief's stop" — the brief's plan is an RTH plan.
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from lib.indicators import add_signal_indicators
from lib.signals import evaluate_signal
from lib.strategies.exit_config_overrides import get_consecutive_periods
from lib.strat import StratClassifier
from lib.strat_levels import (LegStateTracker, LevelMap, build_level_map,
                             reanchor_triggers)
from lib.config import load_config, get_position_size, get_signal_strength_label
from lib.strategies import MOMENTUM
from lib.strategies.agreement import AGREEMENT_BONUS, detect_agreement
from lib.strategies.brief_bias import get_premarket_bias
from lib.strategies.brief_bias import level_aware_alignment as _level_aware_alignment
from lib.strategies.insight_cache import (
    InsightCache,
    evaluate_direction_gate,
    fetch_insight_for_ticker,
)
from lib.strategies.calibration import (
    get_call_rsi_range,
    get_put_rsi_range,
    get_resolution_tier,
)
from lib.strategies.base import Signal
from lib.strategies.timeframe import assign_timeframe
from lib.strategies.catalyst_proximity import get_catalyst_context


# 2026-05-10 (issue #386 logging gap): basicConfig was previously inside
# main() — but module-level `logger.info` calls fire BEFORE main() runs
# (e.g. during `from gcp.signal_monitor import ...` in unit tests), and
# more importantly the previous structure meant Python's default WARNING
# level dropped every INFO log including session_summary, mr fire, and
# the new cap-diagnostics. Cloud Logging from production runs showed
# zero `INFO` lines pre-fix. Move logger configuration to module-level so
# handlers + INFO level are set BEFORE any logger.info call in this file.
#
# Codex P2 review on PR #391: a naive `if not handlers: basicConfig()`
# guard preserves the same failure mode when ANY transitively-imported
# module (requests, pandas, lib/* code) has already attached a root
# handler — basicConfig is then skipped AND the existing handler keeps
# the default WARNING level, so our INFO logs stay suppressed. Fix is
# two-step: (1) always set root level to INFO so any existing handler
# inherits it; (2) only basicConfig when no handler exists, to avoid
# duplicating handler output if some other module already configured one.
import logging as _logging
_logging.getLogger().setLevel(_logging.INFO)
if not _logging.getLogger().handlers:
    _logging.basicConfig(
        level=_logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

logger = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'


def rvol_gate_verdict(rvol: float, min_rvol: float, mode: str):
    """Pure verdict for the RVOL entry gate.

    Returns 'pass' / 'below', or None when the gate is off. A missing or
    zero RVOL counts as 'below' — an unconfirmed-volume fire is exactly
    what the gate exists to flag (audit 2026-08-25 §10), and NaN must
    never silently pass a gate (CLAUDE.md §3.7).
    """
    if mode == 'off':
        return None
    if rvol is None or not rvol == rvol:  # None or NaN
        return 'below'
    return 'pass' if rvol >= min_rvol else 'below'


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
        # Signal entries, in-session exits and ORB snapshots route to the
        # dedicated signals channel when configured; fall back to the main
        # webhook so deploys without the secret behave identically.
        self.webhook_url = (
            os.environ.get('DISCORD_WEBHOOK_SIGNALS_URL')
            or os.environ.get('DISCORD_WEBHOOK_URL')
        )
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
        # Track D / G.P1.1 instrumentation: three counters per ticker so we
        # can answer "why is signal_alerts.level_broken 100% NULL?". The
        # 2026-05-09 verification (issue #301) confirmed the bug is
        # independent of the data freeze — fresh strat_levels were
        # available on 2026-05-08 but level_broken stayed 0% populated
        # across 396 alerts. The counters split refresh_level_map's
        # outcomes into the three observable failure modes:
        #   * success → level_map built (the only path where
        #     check_level_breaks can return non-empty results)
        #   * empty_df → loader.load_daily(ticker) returned empty
        #     (likely _query_cloud_sql swallowed an exception)
        #   * exception → calculate_historical_levels or
        #     build_level_map raised; previously caught silently.
        # Logged in session_summary so Cloud Logging shows the
        # distribution per ticker per session, no separate persistence
        # layer needed.
        self.level_refresh_success_count: dict = {t: 0 for t in self.tickers}
        self.level_refresh_empty_df_count: dict = {t: 0 for t in self.tickers}
        self.level_refresh_exception_count: dict = {t: 0 for t in self.tickers}
        # Open positions awaiting exit. Each tick the exit-watcher walks
        # this list and fires TARGET HIT / TIME STOP / RSI EXIT alerts +
        # writes the exit details back to signal_alerts. Lifetime is the
        # signal_monitor process itself (≤ one trading session), which is
        # always longer than max(call_time_stop, put_time_stop) = 35 min,
        # so in-memory tracking is sufficient for now.
        self.active_positions: dict = {t: [] for t in self.tickers}
        self.orb_levels: dict = {t: {} for t in self.tickers}
        # Running RTH high/low for today's session, per ticker — fed
        # incrementally by update_window because the rolling window keeps
        # only rolling_window_bars (200) bars, less than a full 390-bar
        # session, so an early stop breach would age out of the window by
        # the afternoon. Consumed by the level-aware brief-alignment tag
        # in fire_alert. Shape: {'date': date, 'high': float, 'low': float}.
        self.session_extremes: dict = {t: {} for t in self.tickers}
        # Per-ticker playbook leg-state trackers (audit §15). Shape:
        # {ticker: {'date': date, 'call': LegStateTracker,
        #           'put': LegStateTracker}} — built lazily on the first
        # RTH bar of the session from the cached brief-bias dict (one DB
        # read per ticker per session, shared with _resolve_brief_bias).
        self.leg_trackers: dict = {t: {} for t in self.tickers}
        # Per-ticker minute-of-day volume baselines for the corrected RVOL
        # (audit §16). Shape: {ticker: {'date': date, 'baseline': {mod: med}}}
        # — one bounded query per ticker per session, loaded lazily.
        self.volume_baselines: dict = {t: {} for t in self.tickers}
        # Timestamp of the most recent fire per ticker, for the
        # fire-spacing measurement in audit §16.3.
        self._last_fire_ts: dict = {}

        # Strat level map per ticker, refreshed each loop iteration. Used to
        # detect level breaks (PDH, PDL, PWH, PWL, ...) once per crossing.
        self.level_maps: dict = {t: None for t in self.tickers}
        # Daily ATR-14 used when each ticker's level map was built, so the
        # put re-anchor can re-apply the brief's 3xATR staleness filter.
        self.level_map_atr: dict = {}
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

        # Replay clock override. When the replay harness feeds bars from
        # a historical date, downstream calls that key off "now" — the
        # premarket-brief lookup (_resolve_brief_bias) and the catalyst
        # proximity lookup (get_catalyst_context) — must use the BAR's
        # timestamp, not wall-clock-now. Without this, replay reads
        # today's brief (which doesn't exist for a 2026-05-06 replay run
        # on 2026-05-10) so ftfc_score defaults to 0.0 and the PR #379
        # FTFC fix is architecturally inert during replay.
        #
        # `replay_clock_ts` is a pandas Timestamp (the bar's Time). When
        # None, `_now()` falls back to wall-clock-now (live behaviour).
        # The harness in scripts/replay_signal_monitor.py sets this
        # per-bar.
        self.replay_clock_ts: Optional[pd.Timestamp] = None

        # Phase 1 — InsightCache (per docs/replays/2026-05-10-corrected-baseline-v2.md
        # §6 + docs/audits/2026-05-10-risk-reviewer-validation.md):
        #
        # Empirical baseline (951 directional fires across 36 days
        # SPY/IWM/QQQ): aligned-with-plan fires win 55.7%, opposite
        # fires win 35.4% (-20.3pp). Filtering opposing weak removes
        # most of the loss-rich opposite bucket without dropping
        # legitimate reversal signals (medium+ kept with tag).
        #
        # Pull-based cache with 60s staleness check — picks up a fresh
        # insight publish within one poll cycle. Default fetcher is
        # disabled when INSIGHT_GATE_MODE='disabled' so the gate can be
        # killed via env var without a redeploy. Default mode 'active'
        # applies the matrix; 'shadow' logs decisions but does NOT
        # apply (for counterfactual measurement before flipping live).
        self.insight_cache = InsightCache(refresh_after_seconds=60.0)
        self.insight_invalidated: dict[str, bool] = {}
        self.insight_gate_mode = os.environ.get('INSIGHT_GATE_MODE', 'active').lower()

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
        """True if wall-clock is inside RTH on a weekday, evaluated in ET.

        Cloud Run runs in UTC, so naïve ``datetime.now()`` would put the
        close at 21:00 and break weekend / holiday gating. Always go
        through the explicit ET zone (``_ET``) and the configured
        ``market_open_time`` / ``market_close_time`` so a future
        early-close / half-day can be parameterized without code change.
        Holidays are NOT checked here — the loop's per-bar staleness
        guard catches them via "no new bar" naturally.
        """
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
        self._update_session_extremes(ticker, new_data)
        self._update_leg_trackers(ticker, new_data)

    def _update_session_extremes(self, ticker: str, new_data: pd.DataFrame) -> None:
        """Fold new bars into the running RTH high/low for today's session.

        Called from update_window — the one choke point both the live
        loop and scripts/replay_signal_monitor.py feed bars through, so
        replay parity is free.

        Bar `Time` tz convention differs by mode, mirroring `_now`:
        live AV bars carry naive US/Eastern stamps (fetch_latest_bar),
        replay bars from market_data_intraday carry naive UTC
        (replay_clock_ts is set per-bar before update_window). tz-aware
        stamps are converted outright.
        """
        if new_data is None or new_data.empty or 'Time' not in new_data.columns:
            return
        try:
            times = pd.to_datetime(new_data['Time'])
            if getattr(times.dt, 'tz', None) is not None:
                times_et = times.dt.tz_convert(_ET)
            elif self.replay_clock_ts is not None:
                times_et = times.dt.tz_localize('UTC').dt.tz_convert(_ET)
            else:
                times_et = times
            today = self._now(_ET).date()
            rth = ((times_et.dt.date == today)
                   & (times_et.dt.time >= _RTH_OPEN)
                   & (times_et.dt.time < _RTH_CLOSE))
            if not bool(rth.any()):
                return
            bars = new_data.loc[rth.values]
            bar_high = float(bars['High'].max()) if 'High' in bars.columns \
                else float(bars['Close'].max())
            bar_low = float(bars['Low'].min()) if 'Low' in bars.columns \
                else float(bars['Close'].min())
        except Exception:
            # Malformed bar batch (garbage Time, non-numeric OHLC).
            # Extremes simply don't advance this poll — the level-aware
            # tag degrades to plain alignment (never a false
            # 'invalidated'), and the window/indicator path will surface
            # the bad batch on its own. Log so it's not invisible.
            logger.warning("session-extremes update skipped for %s: bad bar batch",
                           ticker, exc_info=True)
            return
        if bar_high != bar_high or bar_low != bar_low:  # all-NaN batch
            return
        ext = self.session_extremes.get(ticker) or {}
        if ext.get('date') != today:
            ext = {'date': today, 'high': None, 'low': None}
        ext['high'] = bar_high if ext['high'] is None else max(ext['high'], bar_high)
        ext['low'] = bar_low if ext['low'] is None else min(ext['low'], bar_low)
        self.session_extremes[ticker] = ext

    def _reanchor_put_leg(self, ticker, times_et, new_data, rth) -> Optional[dict]:
        """Recompute the put leg against today's OPEN (audit §15.5).

        The brief anchors the playbook on the 8:31 price — yesterday's close —
        so an overnight gap (mean |gap| 0.62% in the study window) can leave
        the published put trigger far from where the session actually starts.
        Re-anchoring the put leg on the open was the one variant with a
        significant paired improvement (+0.126%/leg, t=+3.75).

        Returns None when the re-anchor cannot be computed — mode off, no
        cached level map, no opening bar, or no fresh structural level below
        the open. None means "not computed" and persists as NULL; it is never
        substituted with the published trigger, which would make the shadow
        comparison compare a leg against itself (Rule 3.7).

        One aggregate-free, in-memory computation per ticker per day: the
        structural levels are already in the cached LevelMap and
        `identify_triggers` is pure. The single DB write is the shadow persist.
        """
        if self.signal_cfg.put_reanchor_mode == 'off':
            return None
        level_map = self.level_maps.get(ticker)
        if level_map is None:
            # Codex P1 on PR #810: run_loop calls update_window BEFORE
            # evaluate_ticker, and evaluate_ticker holds the ONLY lazy
            # refresh_level_map call. So on the first RTH poll of the day the
            # map is still None here — and because the tracker dict is stamped
            # with today's date regardless, this whole initialization block
            # never runs again. The re-anchor silently recorded nothing in
            # live sessions and enforce mode could never take effect.
            # Refresh on demand instead: this is the same load evaluate_ticker
            # performs moments later (and caches), so it is a reorder, not
            # extra load — one load_daily per ticker per day either way.
            self.refresh_level_map(ticker)
            level_map = self.level_maps.get(ticker)
        if level_map is None:
            logger.info("put_reanchor: %s skipped — level map unavailable "
                        "after refresh", ticker)
            return None
        try:
            bars = new_data.loc[rth.values]
            if bars.empty:
                return None
            order = times_et[rth].argsort()
            first = bars.iloc[order.values[0]] if hasattr(order, 'values') else bars.iloc[0]
            o_col = 'Open' if 'Open' in bars.columns else 'Close'
            open_px = float(pd.to_numeric(first[o_col], errors='coerce'))
            if not (open_px == open_px) or open_px <= 0:
                logger.info("put_reanchor: %s skipped — no usable open", ticker)
                return None

            # Codex P2 on PR #810: the published playbook is built with
            # build_level_map(atr=atr_for_filter), which drops levels beyond
            # 3xATR. Re-anchoring with atr=None applies only identify_triggers'
            # looser 8% bound, so on a low-volatility ticker the re-anchored leg
            # could select a stale trigger the brief deliberately excluded —
            # making the shadow comparison non-equivalent and, under enforce,
            # arming an invalid leg. Pass the same daily ATR the level map was
            # refreshed with; None only when the daily row carries no ATR, which
            # is the same state the brief would have seen.
            legs = reanchor_triggers(
                level_map, open_px, atr=self.level_map_atr.get(ticker))
            put = legs.get('puts')
            if not put or put.get('trigger_level') is None:
                logger.info(
                    "put_reanchor: %s skipped — no fresh structural level "
                    "below open=%.4f", ticker, open_px)
                return None
            tgts = [t.get('price') for t in (put.get('targets') or [])]
            out = {
                'open': open_px,
                'trigger': float(put['trigger_level']),
                'trigger_name': put.get('trigger_name'),
                'stop': put.get('stop'),
                't1': tgts[0] if len(tgts) > 0 else None,
                't2': tgts[1] if len(tgts) > 1 else None,
                't3': tgts[2] if len(tgts) > 2 else None,
            }
            self._persist_put_reanchor(ticker, out)
            return out
        except Exception:
            # INTERNAL (Rule 3.7): this is our own pure math over a cached
            # level map. Log the traceback rather than swallowing it, and
            # return None so the tracker keeps the published leg — a failed
            # SHADOW measurement must never change what the monitor trades.
            logger.exception("put_reanchor: %s failed", ticker)
            return None

    def _persist_put_reanchor(self, ticker: str, r: dict) -> None:
        """Write the shadow re-anchor onto today's premarket_analysis row.

        One UPDATE per ticker per day. Never INSERTs: if the brief did not
        publish a row there is nothing to attach the counterfactual to, and
        fabricating one would put a playbook row in the table that no brief
        ever produced.
        """
        try:
            from gcp.database import execute_sql
            today = (pd.Timestamp(self.replay_clock_ts).date()
                     if self.replay_clock_ts is not None
                     else self._now(_ET).date())
            rows = execute_sql(
                "UPDATE premarket_analysis SET "
                "  puts_reanchor_open = :o, puts_reanchor_trigger = :t, "
                "  puts_reanchor_trigger_name = :tn, puts_reanchor_stop = :s, "
                "  puts_reanchor_t1 = :t1, puts_reanchor_t2 = :t2, "
                "  puts_reanchor_t3 = :t3, puts_reanchor_at = NOW() "
                "WHERE analysis_date = :d AND ticker = :tk",
                {'o': r['open'], 't': r['trigger'], 'tn': r.get('trigger_name'),
                 's': r.get('stop'), 't1': r.get('t1'), 't2': r.get('t2'),
                 't3': r.get('t3'), 'd': today, 'tk': ticker},
            )
            if rows == 0:
                logger.warning(
                    "put_reanchor: %s computed (open=%.4f trigger=%.4f) but no "
                    "premarket_analysis row for %s to attach it to — the "
                    "shadow measurement is lost for this ticker-day",
                    ticker, r['open'], r['trigger'], today)
                return
            logger.info(
                "put_reanchor: %s open=%.4f trigger=%.4f (%s) stop=%s persisted",
                ticker, r['open'], r['trigger'], r.get('trigger_name'),
                r.get('stop'))
        except Exception:
            # EXTERNAL: DB round-trip. The measurement is lost for this
            # ticker-day and that is visible in the traceback + a NULL row;
            # it must not take the monitor down mid-session.
            logger.exception("put_reanchor: %s persist failed", ticker)

    def _update_leg_trackers(self, ticker: str, new_data: pd.DataFrame) -> None:
        """Advance the per-leg playbook state machines with today's RTH bars.

        Unlike ``_update_session_extremes`` (batch min/max is order-free),
        leg state is ORDER-dependent — the resolver-parity contract in
        ``lib.strat_levels.LegStateTracker`` counts T1/stop touches only
        from the trigger bar onward — so bars are folded in one at a time,
        chronologically. Called from update_window, the shared choke point
        with the replay harness (Rule 3.6 parity, same as the extremes).

        Gate mode 'off' skips everything, including the lazy brief lookup —
        and therefore also skips the put-side re-anchor, which rides on this
        same once-per-day setup (it needs the day's leg trackers and the
        published put leg to fall back to). `put_reanchor_mode` is only
        consulted when `level_gate_mode` is not 'off'.
        """
        if self.signal_cfg.level_gate_mode == 'off':
            return
        if new_data is None or new_data.empty or 'Time' not in new_data.columns:
            return
        try:
            times = pd.to_datetime(new_data['Time'])
            if getattr(times.dt, 'tz', None) is not None:
                times_et = times.dt.tz_convert(_ET)
            elif self.replay_clock_ts is not None:
                times_et = times.dt.tz_localize('UTC').dt.tz_convert(_ET)
            else:
                times_et = times
            today = self._now(_ET).date()
            rth = ((times_et.dt.date == today)
                   & (times_et.dt.time >= _RTH_OPEN)
                   & (times_et.dt.time < _RTH_CLOSE))
            if not bool(rth.any()):
                return
            trackers = self.leg_trackers.get(ticker) or {}
            if trackers.get('date') != today:
                brief = self._resolve_brief_bias(ticker)
                # No playbook row / failed lookup → no trackers at all, so
                # fires tag NULL ("we weren't looking") rather than
                # 'no_setup' ("a real row published no trigger for this
                # leg"). Merging missing-data days into the no_setup
                # cohort would bias the shadow GROUP BY (Codex P2 on
                # PR #799). The 'unavailable' sentinel keeps the day
                # keyed so the (cached) lookup isn't re-derived per bar.
                if brief.get('bias') == 'UNAVAILABLE':
                    self.leg_trackers[ticker] = {'date': today,
                                                 'unavailable': True}
                    return
                # Put-side 9:31 re-anchor (audit §15.5). Computed from the
                # session's OPEN — the first RTH bar's open, which is exactly
                # the anchor the counterfactual measured. In 'shadow' the
                # published leg still drives the tracker; in 'enforce' the
                # re-anchored trigger/stop replace it.
                reanchor = self._reanchor_put_leg(ticker, times_et, new_data, rth)
                put_trigger = brief.get('puts_trigger_price')
                put_t1 = brief.get('puts_t1_price')
                put_stop = brief.get('puts_stop_price')
                if (self.signal_cfg.put_reanchor_mode == 'enforce'
                        and reanchor and reanchor.get('trigger') is not None):
                    put_trigger = reanchor['trigger']
                    put_t1 = reanchor.get('t1')
                    put_stop = reanchor.get('stop')
                    logger.info(
                        "put_reanchor: %s put leg re-anchored on open=%.4f "
                        "trigger %.4f -> %.4f", ticker, reanchor['open'],
                        brief.get('puts_trigger_price') or float('nan'),
                        put_trigger)
                trackers = {
                    'date': today,
                    'call': LegStateTracker(
                        direction='call',
                        trigger=brief.get('calls_trigger_price'),
                        t1=brief.get('calls_t1_price'),
                        stop=brief.get('calls_stop_price')),
                    'put': LegStateTracker(
                        direction='put',
                        trigger=put_trigger,
                        t1=put_t1,
                        stop=put_stop),
                    'reanchor': reanchor,
                }
                self.leg_trackers[ticker] = trackers
            if trackers.get('unavailable'):
                return
            bars = new_data.loc[rth.values]
            h_col = 'High' if 'High' in bars.columns else 'Close'
            l_col = 'Low' if 'Low' in bars.columns else 'Close'
            o_col = 'Open' if 'Open' in bars.columns else None
            sub = pd.DataFrame({
                '_et': times_et[rth].values,
                '_h': pd.to_numeric(bars[h_col].values, errors='coerce'),
                '_l': pd.to_numeric(bars[l_col].values, errors='coerce'),
                '_o': (pd.to_numeric(bars[o_col].values, errors='coerce')
                       if o_col else pd.Series([float('nan')] * len(bars))),
            }).sort_values('_et')
            # Live polls re-deliver an overlapping snapshot of the session
            # (fetch_latest_bar returns the last ~100 bars each cycle).
            # The tracker is ORDER-dependent, so re-folding bars older
            # than the watermark would replay pre-trigger bars with
            # `triggered` already set and let an earlier, correctly-
            # ignored stop touch flip the leg 'invalidated' (Codex P1 on
            # PR #799). Fold only bars AT or after the watermark: the
            # at-watermark bar is re-folded on purpose — it may be the
            # still-forming current minute whose H/L are still widening,
            # and re-folding it is safe because it is never earlier than
            # the trigger bar when `triggered` is set (trigger-bar-
            # inclusive semantics, same as the resolver).
            last_ts = trackers.get('last_ts')
            if last_ts is not None:
                sub = sub[sub['_et'] >= last_ts]
            if sub.empty:
                return
            for et, hi, lo, op in zip(sub['_et'], sub['_h'], sub['_l'], sub['_o']):
                # bar_key = the bar's ET minute, so a re-delivered snapshot
                # of the still-forming minute is folded again WITHOUT being
                # counted as a new bar (Codex review, PR #803).
                key = pd.Timestamp(et).floor('min')
                op_f = float(op) if op == op else None
                trackers['call'].update(float(hi), float(lo), op_f, key)
                trackers['put'].update(float(hi), float(lo), op_f, key)
            trackers['last_ts'] = sub['_et'].iloc[-1]
        except Exception:
            # Same posture as the extremes tracker: a malformed batch must
            # never crash the monitor; the state simply doesn't advance
            # this poll (tag degrades toward 'fresh', never a false
            # 'invalidated' — LegStateTracker only escalates on real bars).
            logger.warning("leg-state update skipped for %s: bad bar batch",
                           ticker, exc_info=True)

    def calculate_indicators(self, ticker: str) -> pd.DataFrame:
        """Calculate indicators on the rolling window via the ONE shared
        engine, ``lib.indicators.add_all_indicators``.

        This used to hand-roll a subset of indicators inline, which meant the
        live monitor silently lagged the engine whenever a feature was added
        to ``add_all_indicators`` (research / brief saw it, live firing did
        not). It now delegates to the single source of truth so every
        indicator we use is computed in exactly one place and the live set can
        never diverge from research again.

        The ONE live-specific nuance is preserved: ``Consecutive_Up/Down`` use
        a per-ticker window (Tier-A from the walk-forward calibration sweep),
        threaded through a per-ticker ``IndicatorConfig`` so the column window
        still matches the threshold ``evaluate_signal`` checks. Parity with the
        former inline path was verified exact (0.0 max-abs-diff) across all 20
        columns the strategies read; see ``tests/test_signal_monitor_indicators``.
        """
        df = self.windows[ticker].copy()
        if len(df) < self.monitor_cfg.min_bars_for_indicators:
            return df

        # Per-ticker consecutive window (Tier-A calibration). consecutive_relaxed_window
        # (the *_5 columns) stays at the config default, matching prior behaviour.
        cfg = dataclasses.replace(
            self.indicator_cfg,
            consecutive_periods=get_consecutive_periods(ticker),
        )
        return add_signal_indicators(df, close_col='Close', indicator_config=cfg)

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
                # Track D / G.P1.1: previously this path was silent —
                # df.empty meant either a real zero-row condition or a
                # swallowed _query_cloud_sql exception, and we couldn't
                # tell which. Now log explicitly so Cloud Logging shows
                # the empty-df failure mode and bumps a counter that
                # session_summary surfaces. _query_cloud_sql itself logs
                # the underlying exception via logger.exception (see
                # lib/data_loader.py).
                self.level_refresh_empty_df_count[ticker] = (
                    self.level_refresh_empty_df_count.get(ticker, 0) + 1
                )
                logger.warning(
                    "refresh_level_map(%s): loader.load_daily returned empty df; "
                    "level_map will be None and check_level_breaks will return [] "
                    "for this poll cycle. See lib/data_loader._query_cloud_sql "
                    "logs for the underlying cause if this persists.",
                    ticker,
                )
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
            # Daily ATR-14 for the level-staleness filter, kept alongside the
            # map so the put re-anchor can apply the SAME filter the premarket
            # brief applied when it published the playbook. None when the
            # column is absent or non-finite — never a fabricated ATR (§3.7).
            # Codex P2 on PR #811: read the LATEST row's scalar, never
            # dropna().iloc[-1]. The brief takes atr14 from that one row
            # (`_safe_float(latest.get('ATR14'))`) and disables the ATR axis
            # entirely when it is missing. Falling back to an older row's ATR
            # would apply a staleness filter the published playbook did not,
            # so the re-anchor could REJECT levels the brief accepted — the
            # same non-equivalence this filter exists to prevent, just
            # inverted. Unusable latest ATR -> None, matching the brief.
            _atr = None
            if 'ATR14' in df.columns:
                _a = pd.to_numeric(df['ATR14'].iloc[-1], errors='coerce')
                if _a is not None and _a == _a and float(_a) > 0:
                    _atr = float(_a)
            self.level_map_atr[ticker] = _atr
            # PR #400 fix applied to this code path: pass analysis_date
            # so build_level_map → compute_previous_levels uses period-
            # filter semantics. Replay-aware: use the replay clock when
            # set, fall back to today's ET date in live mode. Without
            # this, replay runs picked day-before-yesterday's PDH/PDL.
            if self.replay_clock_ts is not None:
                _analysis_date = pd.Timestamp(self.replay_clock_ts).date()
            else:
                _analysis_date = datetime.now(_ET).date()
            self.level_maps[ticker] = build_level_map(
                ticker=ticker, daily_df=df, current_price=current_price,
                analysis_date=_analysis_date,
            )
            self.level_refresh_success_count[ticker] = (
                self.level_refresh_success_count.get(ticker, 0) + 1
            )
        except Exception:
            # Track D / G.P1.1: replace logger.warning("...%s", e) with
            # logger.exception so the full traceback reaches Cloud
            # Logging. The pre-fix one-liner only printed str(e), which
            # made it impossible to tell calculate_historical_levels vs
            # build_level_map vs an inner DataLoader path failure apart
            # in production. Verification dispatch on 2026-05-09
            # confirmed signal_alerts.level_broken was 0% populated
            # across 1,178 alerts in the post-thaw window despite fresh
            # strat_levels — so this exception path was firing silently
            # for every refresh attempt. Counter splits success vs
            # empty_df vs exception so session_summary shows which
            # failure mode dominates.
            self.level_refresh_exception_count[ticker] = (
                self.level_refresh_exception_count.get(ticker, 0) + 1
            )
            logger.exception(
                "refresh_level_map(%s) raised; level_map cleared to None "
                "and check_level_breaks will return [] for this cycle",
                ticker,
            )
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

    @staticmethod
    def _momentum_signal_to_dict(sig: 'Signal', strat_bonus: int = 0) -> dict:
        """Convert a momentum `Signal` dataclass to the mr-style dict
        every downstream consumer (`fire_alert`, `_persist_signal_alert`,
        `TradeLogger.log_trade`) reads.

        This is the cross-cutting compatibility surface that lets the
        stand-alone-momentum path reuse all existing fire/persist
        infrastructure without per-strategy mapping at every call site.
        Per #369: post-hoc `_infer_strategy(conditions_met)` in
        `scripts/analysis/per_factor_walkforward.py` distinguishes mr
        vs momentum from the conditions_met namespace (disjoint per
        `lib/strategies/momentum.py` vs `lib/signals.py`), so no extra
        column on `signal_alerts` is needed to mark which strategy
        fired.
        """
        return {
            'direction':      sig.direction,
            'base_score':     sig.base_score,
            'strat_bonus':    strat_bonus,
            'total_score':    sig.weighted_score,
            'conditions_met': list(sig.conditions_met),
        }

    def _evaluate_strategies_for_bar(self, latest, last_price: float, ticker: str):
        """Run mean-reversion + momentum on the same bar; detect agreement.

        Returns a (sig_dict, agreement_payload) tuple:
          * `sig_dict` — mr dict when mean-reversion fires; the
            momentum-adapter dict when mr misses but momentum fires
            AND `signal_cfg.enable_standalone_momentum=True` (#369);
            otherwise `None`. The dict shape is identical in either
            case so downstream consumers (fire_alert, persist,
            TradeLogger) work uniformly.
          * `agreement_payload` — `None` when only one strategy fired
            OR they disagreed on direction; otherwise the dict from
            `lib.strategies.agreement.detect_agreement`. Stand-alone
            momentum fires never carry an agreement payload (no mr
            to agree with).

        Counter semantics (G.P0.11 / #369):
          `momentum_evaluated_count` is bumped on EVERY bar reaching
          this function — not just bars where mr fired. Pre-#369 the
          counter sat inside the mr-fires branch, which made the
          fired/evaluated ratio meaningless because the denominator
          was tiny and biased. Now `evaluated` = "every bar
          evaluate_ticker reached the strategy block"; `fired` =
          "every bar momentum's internal gate passed regardless of
          mr". This is a strict superset of pre-#369 semantics — no
          information loss, much more useful denominator.

        See `docs/plans/SIGNAL_QUALITY_TEST_PLAN.md` Phase 1.6 for the
        agreement rationale; Track D audit § 6 (2026-05-08) for the
        17/782 stacked rate observed in the May 4-7 window; #369 for
        the always-evaluate orchestration fix.
        """
        # Resolve per-ticker RSI ranges (Tier A → Tier B fallback).
        # Both strategies use the same resolved ranges so agreement
        # detection compares apples-to-apples. See
        # lib/strategies/calibration.py for the resolution chain.
        call_rng = get_call_rsi_range(ticker)
        put_rng = get_put_rsi_range(ticker)
        call_tier = get_resolution_tier(ticker, "CALL")
        put_tier = get_resolution_tier(ticker, "PUT")

        # 1) Always evaluate momentum first so the counters reflect
        # every bar — not just bars where mr fired. This is the #369
        # fix: pre-fix the momentum eval was inside the mr-fires
        # branch, so `momentum_evaluated_count` was structurally
        # biased to the mr-fires intersection AND momentum could
        # never fire stand-alone (line 381 short-circuit).
        mom_signal = MOMENTUM.evaluate(
            latest, call_rsi_range=call_rng, put_rsi_range=put_rng,
        )
        self.momentum_evaluated_count[ticker] = (
            self.momentum_evaluated_count.get(ticker, 0) + 1
        )
        if mom_signal is not None:
            self.momentum_fired_count[ticker] = (
                self.momentum_fired_count.get(ticker, 0) + 1
            )

        # 2) Evaluate mean-reversion.
        sig = evaluate_signal(
            latest,
            min_conditions=self.signal_cfg.min_conditions,
            consecutive_periods=get_consecutive_periods(ticker),
            call_rsi_range=call_rng,
            put_rsi_range=put_rng,
            ticker=ticker,
        )

        # 3) Three-way return:
        if sig is not None:
            logger.info(
                "%s mr fire: %s base_score=%.1f call_range=%s tier=%s put_range=%s tier=%s",
                ticker, sig["direction"], sig["base_score"],
                call_rng, call_tier, put_rng, put_tier,
            )
            # Build a Signal facade from the mr dict so detect_agreement
            # can compare it against MomentumStrategy's Signal output.
            # mr_dict (not the Signal) flows downstream because every
            # consumer reads dict-shaped sig.
            mr_signal = Signal(
                strategy="mean_reversion",
                direction=sig["direction"],
                timestamp=pd.Timestamp(latest.get("Time") or datetime.now()),
                entry_price=float(last_price),
                base_score=float(sig["base_score"]),
                weighted_score=float(sig["base_score"]),
                conditions_met=list(sig["conditions_met"]),
            )
            agreement = detect_agreement(mom_signal, mr_signal) if mom_signal else None
            return sig, agreement

        if mom_signal is not None and self.signal_cfg.enable_standalone_momentum:
            # Honor `disabled_directions` for the stand-alone path
            # too — pre-Codex-P2 (PR #371) the kill switch lived only
            # inside `lib.signals.evaluate_signal`, so a momentum-only
            # PUT on a `["PUT"]`-disabled ticker (e.g. QQQ) would have
            # bypassed the same protection mr respects. Resolver
            # exception is non-fatal: log and degrade to "no kill
            # switch known" rather than blocking a fire on a transient
            # DB error (mirrors the resolver-failure handling inside
            # evaluate_signal at lib/signals.py:207-210).
            try:
                from lib.strategies.exit_config_overrides import (
                    get_disabled_directions,
                )
                if mom_signal.direction.upper() in get_disabled_directions(ticker):
                    logger.info(
                        "%s standalone momentum %s suppressed: direction in disabled_directions",
                        ticker, mom_signal.direction,
                    )
                    return None, None
            except Exception:
                logger.exception(
                    "get_disabled_directions(%s) raised; allowing momentum fire "
                    "(degrade-open mirrors evaluate_signal's resolver-failure handling)",
                    ticker,
                )

            logger.info(
                "%s standalone momentum fire: %s base_score=%.1f core=%d call_range=%s tier=%s put_range=%s tier=%s",
                ticker, mom_signal.direction, mom_signal.base_score,
                mom_signal.core_count, call_rng, call_tier, put_rng, put_tier,
            )
            return self._momentum_signal_to_dict(mom_signal), None

        # Neither fires (or momentum fired but flag is off → no fire,
        # but the counter already recorded the eligibility so the
        # cross-track sync questions are answerable from the log).
        return None, None

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
        # 2026-05-10 #386 diagnostics: log every cap-check decision so we
        # can prove from Cloud Logging whether the counter is actually
        # being read (and what value it holds) at fire time. Pre-fix the
        # production data showed 300+ alerts/day on a 5/ticker cap,
        # indicating the check was either reading 0 every time or never
        # short-circuiting. These logs let the next session prove or
        # disprove that.
        cap = self.risk.max_daily_trades
        cur = self.daily_trades.get(ticker, 0)
        if cur >= cap:
            logger.info(
                "cap_diag: SKIP ticker=%s daily_trades=%d cap=%d (cap reached)",
                ticker, cur, cap,
            )
            return
        if self.daily_pnl[ticker] <= self.risk.daily_loss_limit:
            logger.info(
                "cap_diag: SKIP ticker=%s daily_pnl=%.4f loss_limit=%.4f",
                ticker, self.daily_pnl[ticker], self.risk.daily_loss_limit,
            )
            return

        # Emergency exposure ceiling (#816). Enforced, unlike the shadow
        # controls below it. See the RiskConfig note for why the defaults are
        # deliberately no-ops: they equal the bound `max_daily_trades` already
        # implies, so this cannot censor a fire today. It exists so that
        # exposure stops being a side effect of an unrelated cap, and so the
        # ceiling can be tightened by config once shadow data exists.
        _blocked, _why, _exposure = self._emergency_ceiling_block(ticker)
        if _blocked:
            logger.warning(
                "EMERGENCY CEILING: blocked ticker=%s %s "
                "(count=%d gross=%.2f portfolio_gross=%.2f)",
                ticker, _why, _exposure['count'], _exposure['gross'],
                _exposure['portfolio_gross'],
            )
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

            # FTFC alignment is computed in the morning brief and persisted to
            # `premarket_analysis.ftfc_score`. The brief-bias resolver (cached
            # per-ticker per-session) reads it; this call is free after the
            # first hit. Pre-2026-05-10 this argument was hardcoded to 0.0,
            # which silently disabled the FTFC alignment branch in
            # `Strat.get_strat_bonus` — counter-FTFC fires (e.g. 5/6/2026 PUTs
            # on a bullish-FTFC day) escaped the −ftfc_bonus penalty they
            # were supposed to receive.
            brief_bias = self._resolve_brief_bias(ticker)
            ftfc_score = brief_bias.get('ftfc_score')
            if ftfc_score is None:
                ftfc_score = 0.0  # treat missing brief / NULL ftfc as neutral

            strat_bonus = self.strat.get_strat_bonus(
                signal_direction=sig['direction'],
                combo=combo,
                ftfc_score=ftfc_score,
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
            # Use the bar's clock during replay so proximity is keyed
            # to bar-time, not wall-clock. Live runs are unaffected
            # (`_now()` falls through to `datetime.now()`).
            self._latest_proximity = get_catalyst_context(
                ticker, pd.Timestamp(self._now())
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

        # Phase 1 direction gate: read today's insight (cached, 60s
        # refresh) and decide pass/suppress/downgrade/tag/annotate.
        # Mode 'disabled' → bypass entirely. Mode 'shadow' → compute
        # decision but always pass (for counterfactual logging).
        gate_action = 'pass'
        gate_reason = ''
        if self.insight_gate_mode != 'disabled':
            try:
                today = self._now(_ET).date()
                from gcp.database import get_engine
                _engine = get_engine()
                ctx = self.insight_cache.get(
                    ticker,
                    fetcher=lambda t: fetch_insight_for_ticker(t, today, _engine),
                )
                decision = evaluate_direction_gate(
                    fire_direction=sig['direction'],
                    fire_strength=strength,
                    insight=ctx,
                    insight_invalidated=self.insight_invalidated.get(ticker, False),
                )
                gate_action = decision.action
                gate_reason = decision.reason
                # Stash for fire_alert / persist (visibility into gate decision)
                self._latest_insight_ctx = ctx
                self._latest_gate_action = gate_action
                self._latest_gate_reason = gate_reason
                # Apply the gate (unless shadow mode)
                if self.insight_gate_mode != 'shadow':
                    if gate_action == 'suppress':
                        logger.info(
                            "%s %s fire SUPPRESSED by direction gate: %s",
                            ticker, sig['direction'], gate_reason,
                        )
                        return  # short-circuit: do not fire
                    elif gate_action == 'downgrade':
                        old = strength
                        strength = decision.new_strength or 'weak'
                        size = get_position_size(total_score, self.risk)  # re-resolve
                        logger.info(
                            "%s %s fire DOWNGRADED %s → %s by direction gate: %s",
                            ticker, sig['direction'], old, strength, gate_reason,
                        )
                    # 'pass', 'tag', 'annotate' all proceed to fire as-is
            except Exception as exc:
                # Gate must never crash the monitor — fall through to fire.
                logger.warning(
                    "direction gate raised for %s: %s — fire proceeds as-is",
                    ticker, exc,
                )

        self.fire_alert(ticker, sig, total_score, strength, size, strat_bonus, latest)

    def fire_alert(self, ticker, sig, total_score, strength, size, strat_bonus, latest):
        """Send signal alert to Discord."""
        # 2026-05-10 #386 diagnostics: prove that fire_alert is reached
        # (i.e. the cap check at line 593 didn't short-circuit) and what
        # the counter looks like at entry. The increment at the bottom of
        # this method is the only thing that bumps daily_trades — if we
        # see "fire_alert ENTER ... daily_trades=N" with N never crossing
        # the cap, the counter isn't accumulating (pre-increment failure
        # or post-counter-reset). If we see counter values >= cap, the
        # cap check is broken upstream.
        logger.info(
            "fire_alert ENTER: ticker=%s direction=%s daily_trades=%d cap=%d",
            ticker, sig.get('direction', '?'),
            self.daily_trades.get(ticker, 0),
            self.risk.max_daily_trades,
        )
        direction = sig['direction']
        price = latest.get('Close', latest.get('Last', 0))
        agreement = getattr(self, '_latest_agreement', None)

        # RVOL entry gate (audit 2026-08-25 §10). Verdict is computed for
        # every fire; 'shadow' (default) tags the persisted row and
        # changes nothing else, 'enforce' suppresses the fire entirely —
        # before Discord, persist, and the daily-trades counter, so a
        # suppressed fire is invisible to the risk caps too.
        # No `.get('RVOL', 0)` default here (CLAUDE.md §3.7): a missing
        # RVOL must reach rvol_gate_verdict() as None/NaN so its
        # always-'below' guarantee applies — coercing to 0 would let a
        # missing value PASS the gate under a legal rvol_gate_min=0.
        rvol_value = latest.get('RVOL')
        self._latest_rvol_gate = rvol_gate_verdict(
            rvol_value, self.signal_cfg.rvol_gate_min,
            self.signal_cfg.rvol_gate_mode)
        if (self.signal_cfg.rvol_gate_mode == 'enforce'
                and self._latest_rvol_gate == 'below'):
            logger.info(
                "rvol_gate: suppressed %s %s fire (rvol=%s < min=%.2f)",
                ticker, direction, rvol_value, self.signal_cfg.rvol_gate_min,
            )
            return

        # Playbook level-state gate (audit 2026-08-26 §15). The fire's
        # own-direction leg state comes from the resolver-parity trackers
        # advanced per bar in update_window. Validated Jun–Aug + 35-day
        # holdout: fires placed after the leg already broke two levels
        # ('post_t1') or broke its stop ('invalidated') lose (fwd30
        # t=-3.6; holdout Welch t=-2.7) while 'fresh'/'triggered' fires
        # win — suppressing the late states flips the book from -5.4pct
        # to +8.2pct over the window. 'shadow' (default) only persists
        # both states; 'enforce' suppresses late-state fires before
        # Discord, persist, and the daily-trades counter (same contract
        # as the RVOL gate above).
        own_state, opp_state = self._resolve_level_state(ticker, direction)
        self._latest_level_state = own_state
        self._latest_opp_level_state = opp_state
        # Corrected RVOL against a historical minute-of-day baseline
        # (audit §16). Shadow only — recorded, never gates.
        self._latest_rvol_mod = self._corrected_rvol(ticker)
        # Declared-but-unenforced risk controls (codebase review T5).
        # Shadow only — records what max_concurrent_positions and a
        # mark-to-market daily_loss_limit WOULD have done at this fire.
        # Never gates: the stop-loss counterfactual (−12.70pct over 736 real
        # fires, every swept level worse than none) is why a control that
        # looks prudent gets measured here before it is switched on.
        _risk_shadow = self._risk_control_shadow(ticker, float(price or 0))
        self._latest_risk_shadow = _risk_shadow
        if _risk_shadow['would_block_concurrent'] or _risk_shadow['would_block_mtm_loss']:
            logger.info(
                "risk_shadow: %s %s WOULD be blocked — concurrent=%d/%d(%s) "
                "mtm=%.4f vs limit=%.4f(%s) [not enforced]",
                ticker, direction,
                _risk_shadow['concurrent_positions'],
                self.risk.max_concurrent_positions,
                _risk_shadow['would_block_concurrent'],
                _risk_shadow['total_mtm_pnl'], self.risk.daily_loss_limit,
                _risk_shadow['would_block_mtm_loss'])
        # Both post_t1 routes stay suppressed under enforce. 2026-08-27 was
        # a live counterexample for the gap-through route (5 winners that
        # a carve-out would have kept, +1.32pct), but that is n=5 against
        # n=197 gap-through fires over Jun-Aug whose forward returns are
        # significantly negative (fwd30 -0.077%, t=-2.81); carving them out
        # historically turns -5.37 -> -0.70pct instead of -5.37 -> +8.20pct.
        # One session does not outrank four months (audit §16.1). The tag
        # is split so the question can be settled per-route on live shadow
        # data; the enforce RULE is unchanged until it is.
        if (self.signal_cfg.level_gate_mode == 'enforce'
                and own_state in ('post_t1', 'post_t1_open', 'invalidated')):
            logger.info(
                "level_gate: suppressed %s %s fire (level_state=%s opp=%s)",
                ticker, direction, own_state, opp_state,
            )
            return

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
        brief, align = self._resolve_brief_alignment(ticker, direction)
        brief_label = ''
        if brief['bias'] == 'CONFLICTED':
            brief_label = ' [brief: CONFLICTED]'
        elif align == 'aligned':
            brief_label = f" [brief: {brief['bias']} ✓ ({brief['setup_count']}/5)]"
        elif align == 'invalidated':
            brief_label = (f" [brief: {brief['bias']} ✗ stop broken "
                           f"({brief['setup_count']}/5)]")
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
        # 2026-05-10 #386 diagnostic: paired with the fire_alert ENTER log
        # above, this lets us prove from Cloud Logging whether the
        # increment runs (and what counter value it produced) for each
        # fire. If we see N "fire_alert ENTER" logs but only K "incremented"
        # logs with K < N, control is exiting fire_alert before the
        # increment.
        logger.info(
            "cap_diag: incremented ticker=%s daily_trades=%d cap=%d",
            ticker, self.daily_trades[ticker], self.risk.max_daily_trades,
        )

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
            # RVOL entry-gate verdict ('pass'/'below', NULL when the gate
            # is off). Shadow mode's whole output is this column — the
            # out-of-sample check is a GROUP BY on it.
            'rvol_gate':         getattr(self, '_latest_rvol_gate', None),
            # Playbook leg state at fire time (audit §15): the fire
            # direction's leg ('fresh'/'triggered'/'post_t1'/
            # 'invalidated'/'no_setup', NULL when the gate is off or no
            # playbook row) and the opposite leg's state. Shadow mode's
            # out-of-sample check is a GROUP BY on these.
            'level_state':       getattr(self, '_latest_level_state', None),
            'opp_level_state':   getattr(self, '_latest_opp_level_state', None),
            # Corrected RVOL vs the historical minute-of-day median (audit
            # §16). NULL when the baseline is unavailable — never a
            # fabricated ratio. The legacy `rvol` column above stays as-is
            # so the two can be compared on identical fires.
            'rvol_mod':          getattr(self, '_latest_rvol_mod', None),
            # Declared-but-unenforced risk controls at fire time (review T5).
            # `concurrent_positions` is what max_concurrent_positions (=1)
            # would have capped; `mtm_pnl` is realized + open mark-to-market,
            # the number a daily_loss_limit would need to read to bind
            # intraday (the live check reads realized only, which is still
            # 0.0 for most fires). Recorded, never enforced.
            'concurrent_positions': (getattr(self, '_latest_risk_shadow', None)
                                     or {}).get('concurrent_positions'),
            'mtm_pnl':           (getattr(self, '_latest_risk_shadow', None)
                                  or {}).get('total_mtm_pnl'),
            # Position of this fire in the ticker's day (1-based) and
            # minutes since the previous fire for the same ticker (NULL on
            # the first). Audit §16.3: 91% of ticker-days burn the 5-fire
            # cap in a median 17 minutes across a median 0.16% price range,
            # so a genuine later setup cannot fire. Recorded to measure
            # that; no rule keys on it yet, because the P&L case for
            # de-duplicating repeat fires did NOT survive the §14 holdout.
            'fire_seq':          self.daily_trades.get(ticker, 0) + 1,
            'min_since_prev_fire': self._minutes_since_prev_fire(ticker),
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

    def _now(self, tz: Optional[ZoneInfo] = None) -> datetime:
        """Return current time, respecting the replay clock override.

        When ``replay_clock_ts`` is set by the replay harness, returns
        that timestamp converted to the requested timezone. Otherwise
        falls back to wall-clock ``datetime.now(tz)`` (live behaviour).

        Used by call sites whose semantics depend on "as-of bar time"
        rather than wall-clock — e.g. ``_resolve_brief_bias`` (which
        looks up the day's premarket_analysis row for FTFC + bias) and
        ``get_catalyst_context`` (which buckets catalysts by proximity
        to the bar's timestamp, not the current time).

        Live signal-monitor runs always have ``replay_clock_ts=None``
        so this method is a no-op overhead — one None-check.
        """
        if self.replay_clock_ts is not None:
            ts = self.replay_clock_ts
            # Normalize to datetime in the requested tz.
            if hasattr(ts, 'to_pydatetime'):
                ts = ts.to_pydatetime()
            if tz is None:
                return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts
            # If ts has no tz, assume UTC (matches market_data_intraday's
            # storage convention) before converting.
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ZoneInfo("UTC"))
            return ts.astimezone(tz)
        return datetime.now(tz)

    def _resolve_brief_alignment(self, ticker: str, direction: str) -> tuple:
        """Resolve the brief bias + level-aware alignment tag for a fire.

        Stashes _latest_brief_bias / _latest_brief_alignment for
        _persist_signal_alert and returns (brief, align). Shared by
        fire_alert and the replay harness's capturing fire stub
        (scripts/replay_signal_monitor.make_capturing_fire_alert) so
        replay exercises the exact tag logic live runs — Rule 3.6
        parity: the tag must never be re-derived in a harness.

        Level-aware: 'aligned' downgrades to 'invalidated' when today's
        session has already traded through the brief's stop for the
        recommended side, so a frozen 8:31 opinion can't keep endorsing
        a plan whose protective level broke intraday (the 2026-05-07/08
        QQQ put-leg days: 176 'aligned' PUT fires past a broken stop).
        """
        brief = self._resolve_brief_bias(ticker)
        _ext = self.session_extremes.get(ticker) or {}
        align = _level_aware_alignment(direction, brief,
                                       _ext.get('high'), _ext.get('low'))
        if align == 'invalidated':
            logger.info(
                "brief_alignment invalidated for %s %s: bias=%s stop=%s "
                "session_low=%s session_high=%s",
                ticker, direction, brief.get('bias'),
                brief.get('calls_stop_price') if brief.get('bias') == 'CALL'
                else brief.get('puts_stop_price'),
                _ext.get('low'), _ext.get('high'),
            )
        self._latest_brief_bias = brief
        self._latest_brief_alignment = align
        return brief, align

    def _minutes_since_prev_fire(self, ticker: str) -> Optional[float]:
        """Minutes since this ticker's previous fire today, None if first.

        Measurement only (audit §16.3). Reads the in-process fire clock so
        it costs no DB round-trip; resets per session with the process.
        """
        prev = self._last_fire_ts.get(ticker)
        now = self._now(_ET)
        self._last_fire_ts[ticker] = now
        if prev is None:
            return None
        try:
            return round((now - prev).total_seconds() / 60.0, 2)
        except Exception:
            return None

    def _volume_baseline(self, ticker: str) -> dict:
        """Median volume per minute-of-day from the prior N RTH sessions.

        The corrected RVOL denominator (audit §16). Loaded once per ticker
        per session — a single aggregate query returning at most 390 rows,
        so this adds one bounded round-trip per ticker per day and nothing
        per bar (CLAUDE.md §0).

        Returns {} when the history is unavailable; callers then record a
        NULL rvol_mod rather than a fabricated ratio (CLAUDE.md §3.7).
        """
        today = self._now(_ET).date()
        cached = self.volume_baselines.get(ticker) or {}
        if cached.get('date') == today:
            return cached['baseline']
        baseline: dict = {}
        try:
            from sqlalchemy import text
            from gcp.database import get_engine
            sql = text(
                "SELECT EXTRACT(hour FROM ts AT TIME ZONE 'America/New_York') * 60 "
                "       + EXTRACT(minute FROM ts AT TIME ZONE 'America/New_York') AS mod, "
                "       percentile_cont(0.5) WITHIN GROUP (ORDER BY volume) AS med_vol "
                "  FROM market_data_intraday "
                " WHERE ticker = :t "
                "   AND ts >= :start AND ts < :end "
                "   AND volume > 0 "
                " GROUP BY 1"
            )
            with get_engine().connect() as conn:
                rows = conn.execute(sql, {
                    't': ticker,
                    'start': str(today - timedelta(days=self.monitor_cfg.rvol_baseline_lookback_days)),
                    'end': str(today),
                }).fetchall()
            baseline = {int(r[0]): float(r[1]) for r in rows if r[1] is not None}
            logger.info("rvol baseline loaded for %s: %d minute buckets", ticker, len(baseline))
        except Exception as exc:
            # EXTERNAL/INTERNAL split per CLAUDE.md §3.7: we cannot fix a
            # missing baseline here, but we must not invent one. Log loudly
            # and cache the empty result so the failing query is not retried
            # every bar; rvol_mod then persists as NULL, which is
            # distinguishable from a real ratio.
            logger.warning("rvol baseline unavailable for %s: %s — rvol_mod will be NULL",
                           ticker, exc)
        self.volume_baselines[ticker] = {'date': today, 'baseline': baseline}
        return baseline

    def _corrected_rvol(self, ticker: str) -> Optional[float]:
        """RVOL of the last COMPLETED bar vs the historical minute-of-day median.

        Shadow metric (audit §16): recorded on every fire, read by nothing
        that changes fire behavior. The scoring path still consumes the
        legacy same-session `RVOL` column, so this deploy cannot alter
        which alerts fire.

        Completed-bar, not `latest`. `latest` is the minute currently
        forming, whose volume is only what has accumulated so far, while
        the baseline holds full-minute medians. Dividing a partial
        numerator by a whole-minute denominator makes the ratio depend on
        how far into the minute the poll landed — reintroducing the exact
        irreproducibility this metric exists to remove (Codex review,
        PR #803). Taking the last bar strictly before the current minute
        makes both sides whole minutes, and yields the same value in live
        and replay for a given clock.
        """
        baseline = self._volume_baseline(ticker)
        if not baseline:
            return None
        window = self.windows.get(ticker)
        if window is None or window.empty or 'Time' not in window.columns:
            return None
        try:
            now_min = self._now(_ET).replace(second=0, microsecond=0, tzinfo=None)
            times = pd.to_datetime(window['Time'])
            if getattr(times.dt, 'tz', None) is not None:
                times = times.dt.tz_convert(_ET).dt.tz_localize(None)
            elif self.replay_clock_ts is not None:
                times = times.dt.tz_localize('UTC').dt.tz_convert(_ET).dt.tz_localize(None)
            completed = window.loc[(times < now_min).values]
            if completed.empty or 'Volume' not in completed.columns:
                return None
            row = completed.iloc[-1]
            t = pd.Timestamp(times.loc[completed.index[-1]])
            ref = baseline.get(int(t.hour) * 60 + int(t.minute))
            vol = float(row['Volume'])
            if ref is None or ref <= 0 or vol != vol:
                return None
            return vol / ref
        except Exception:
            logger.warning("corrected rvol failed for %s", ticker, exc_info=True)
            return None

    def _resolve_level_state(self, ticker: str, direction: str) -> tuple:
        """Read the fire direction's playbook leg state + the opposite leg's.

        Returns ``(own_state, opp_state)`` — each one of
        ``lib.strat_levels.LEG_STATES`` — or ``(None, None)`` when the
        gate is 'off' or the trackers haven't been built for today (no
        bars seen yet / no playbook row). None is deliberately distinct
        from 'no_setup': None = "we weren't looking", 'no_setup' = "we
        looked and the brief published no trigger for that leg".
        """
        if self.signal_cfg.level_gate_mode == 'off':
            return None, None
        trackers = self.leg_trackers.get(ticker) or {}
        if trackers.get('date') != self._now(_ET).date():
            return None, None
        if trackers.get('unavailable'):
            # No playbook row / failed brief lookup for today — NULL tags,
            # never 'no_setup' (see _update_leg_trackers).
            return None, None
        own_key = 'call' if direction == 'CALL' else 'put'
        opp_key = 'put' if own_key == 'call' else 'call'
        return trackers[own_key].state, trackers[opp_key].state

    def _resolve_brief_bias(self, ticker: str) -> dict:
        """Lookup-and-cache the premarket-brief bias for this ticker today."""
        if ticker in self._brief_bias_cache:
            return self._brief_bias_cache[ticker]
        try:
            today_et = self._now(_ET).date()
            bias = get_premarket_bias(ticker, today_et)
        except Exception as e:
            logger.debug("brief bias lookup failed for %s: %s", ticker, e)
            bias = {'bias': 'UNAVAILABLE', 'alignment': None,
                    'setup_count': 0, 'ftfc_direction': None,
                    'ftfc_score': None, 'reason': 'lookup_failed'}
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

            is_call = pos['direction'] == 'CALL'
            dir_mode = (self.exit.call_exit_mode if is_call
                        else self.exit.put_exit_mode)
            if dir_mode == 'fixed_horizon':
                # Audit 2026-08-25 §12: hold this direction's positions
                # exactly N minutes — no target truncation, no RSI exit.
                # Per-direction because the paired tests show upside
                # fades (CALLs want quick targets) while downside trends
                # (PUTs want the hold). Mirrored in the EOD resolver's
                # _detect_exit; the two must stay in lock-step.
                horizon = (self.exit.call_fixed_horizon_minutes if is_call
                           else self.exit.put_fixed_horizon_minutes)
                if elapsed_min >= horizon:
                    exit_reason = 'fixed_horizon'
            elif pos['direction'] == 'CALL':
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

    def _exposure_state(self, ticker: str) -> dict:
        """Simultaneous exposure: count and gross size, ticker and portfolio.

        `size` is the position-sizing fraction (see RiskConfig.position_sizing,
        max 1.00), so `gross` is a sum of fractions rather than a currency
        amount — the same unit the sizing config is expressed in.
        """
        per = self.active_positions.get(ticker) or []
        gross = 0.0
        for pos in per:
            try:
                gross += float(pos.get('size', 1.0))
            except (TypeError, ValueError):
                # Rule 3.7: a malformed size must not silently count as 0 and
                # make exposure look smaller than it is. Count it at the
                # maximum instead, so the ceiling errs toward blocking.
                logger.warning(
                    "exposure: %s position has unusable size=%r; counting 1.0",
                    ticker, pos.get('size'))
                gross += 1.0
        portfolio = 0.0
        for _t, poss in (self.active_positions or {}).items():
            for pos in (poss or []):
                try:
                    portfolio += float(pos.get('size', 1.0))
                except (TypeError, ValueError):
                    portfolio += 1.0
        return {'count': len(per), 'gross': gross,
                'portfolio_gross': portfolio}

    def _emergency_ceiling_block(self, ticker: str):
        """Would the emergency exposure ceiling refuse another position?

        Returns ``(blocked, reason, exposure_state)``. Three independent
        bounds, any of which blocks:

        * per-ticker concurrent count
        * per-ticker gross size
        * portfolio-wide gross size  (the only aggregate bound that exists;
          nothing else in the system looks across tickers at all)

        This is a circuit breaker, not a policy. See RiskConfig (#816).
        """
        st = self._exposure_state(ticker)
        r = self.risk
        if st['count'] >= r.emergency_max_concurrent_positions:
            return True, ("concurrent=%d >= %d"
                          % (st['count'],
                             r.emergency_max_concurrent_positions)), st
        if st['gross'] >= r.emergency_max_gross_exposure:
            return True, ("gross=%.2f >= %.2f"
                          % (st['gross'],
                             r.emergency_max_gross_exposure)), st
        if st['portfolio_gross'] >= r.emergency_max_portfolio_gross:
            return True, ("portfolio_gross=%.2f >= %.2f"
                          % (st['portfolio_gross'],
                             r.emergency_max_portfolio_gross)), st
        return False, None, st

    def _risk_control_shadow(self, ticker: str, price: float) -> dict:
        """What the DECLARED-but-unenforced risk controls would say right now.

        Codebase review 2026-08-27 (T5) found three controls that are
        configured, validated, and never consulted in the live monitor:

        * ``risk.max_concurrent_positions`` (alert_config.json: 1) — nothing
          reads it. ``active_positions`` is only appended to and walked for
          exits, so the monitor can carry an unbounded number of simultaneous
          positions per ticker, bounded only by ``max_daily_trades``.
        * ``risk.daily_loss_limit`` — IS checked before a fire, but
          ``daily_pnl`` is written only in the exit path. Since §16 measured
          the daily cap being burned in a median 17 minutes, most of a day's
          fires open before any position has exited, so the value read at the
          cap check is still 0.0. It cannot bind intraday as written.
        * ``risk.daily_profit_target`` — referenced only by lib/backtest.py.

        This does NOT enforce any of them. The stop-loss counterfactual
        (§17-era work: adding the backtest's stop cost −12.70pct over 736 real
        fires, and every swept level was worse than none) is a standing warning
        that a control which looks prudent can be expensive here. So measure
        first: record what each control would have done, and decide from live
        data whether any of them is worth switching on.

        Returns realized + mark-to-market P&L so a loss limit that COULD bind
        intraday is measurable, not just the realized one that cannot.
        """
        positions = self.active_positions.get(ticker) or []
        realized = float(self.daily_pnl.get(ticker, 0.0))
        open_mtm = 0.0
        for pos in positions:
            try:
                entry = float(pos['entry_price'])
                if entry <= 0 or price <= 0:
                    # No usable mark. Rule 3.7: skip this leg and say so
                    # rather than folding a fabricated 0% into the total.
                    logger.warning(
                        "risk_shadow: %s skipping position with entry=%s "
                        "mark=%s", ticker, entry, price)
                    continue
                pct = self._exit_return_pct(pos['direction'], entry, price)
                open_mtm += (pct / 100.0) * float(pos.get('size', 1.0))
            except Exception:
                # One malformed position must not cost the whole measurement.
                logger.exception("risk_shadow: bad position for %s", ticker)
        return {
            'concurrent_positions': len(positions),
            'realized_pnl': realized,
            'open_mtm_pnl': open_mtm,
            'total_mtm_pnl': realized + open_mtm,
            'would_block_concurrent': bool(
                len(positions) >= self.risk.max_concurrent_positions),
            'would_block_mtm_loss': bool(
                (realized + open_mtm) <= self.risk.daily_loss_limit),
        }

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
        """Update the signal_alerts row AND mirror the exit onto trades.

        The trades row is matched on (ticker, entry_time == alert_ts):
        `_persist_signal_alert` writes signal_alerts.alert_ts and
        trades.entry_time from the SAME `now` value, and (ticker,
        entry_time) is the trades upsert conflict key — verified
        2071/2071 live rows since 2026-05-01 join exactly on it.
        Both UPDATEs run in one transaction so the two tables can't
        drift on a mid-write failure. The trades UPDATE is guarded by
        `exit_time IS NULL` (idempotent — a recorded exit is never
        overwritten); a rowcount of 0 logs a WARNING per Rule 3.7
        rather than silently no-oping.
        """
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
        # return_pct is the direction-aware underlying-move percent
        # ((exit-entry)/entry*100 for CALL, negated for PUT) — the same
        # units as the pre-existing closed trades rows (April backfill)
        # and signal_alerts.exit_return_pct.
        trades_sql = text("""
            UPDATE trades
               SET exit_time   = :exit_ts,
                   exit_price  = :price,
                   exit_reason = :reason,
                   return_pct  = :ret
             WHERE ticker     = :ticker
               AND entry_time = :entry_time
               AND exit_time IS NULL
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
                trade_result = conn.execute(trades_sql, {
                    'exit_ts':    exit_ts,
                    'reason':     exit_reason,
                    'price':      float(exit_price),
                    'ret':        float(return_pct),
                    'ticker':     pos['ticker'],
                    'entry_time': pos['alert_ts'],
                })
                if (trade_result.rowcount or 0) == 0:
                    logger.warning(
                        "exit mirror matched no open trades row for %s "
                        "entry_time=%s reason=%s — row missing or already "
                        "closed; signal_alerts exit still recorded",
                        pos['ticker'], pos['alert_ts'], exit_reason,
                    )
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
                            "momentum_fired=%d daily_trades=%d daily_pnl=%.4f "
                            "level_refresh_success=%d level_refresh_empty_df=%d "
                            "level_refresh_exception=%d",
                            t,
                            self.momentum_evaluated_count.get(t, 0),
                            self.momentum_fired_count.get(t, 0),
                            self.daily_trades.get(t, 0),
                            self.daily_pnl.get(t, 0.0),
                            self.level_refresh_success_count.get(t, 0),
                            self.level_refresh_empty_df_count.get(t, 0),
                            self.level_refresh_exception_count.get(t, 0),
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
    # Logging is configured at module-level (see top of file). Re-running
    # basicConfig here would no-op because a handler is already attached;
    # call removed to keep the configuration in one place.
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
