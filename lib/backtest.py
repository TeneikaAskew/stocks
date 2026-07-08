"""
Event-driven backtesting engine.

Processes each bar sequentially, enforcing risk management rules that
depend on the sequence of trades (max daily trades, daily loss limits,
max concurrent positions). Uses the signal logic from lib/signals and
exit rules from lib/config.

When ``use_strat=True`` the engine computes real FTFC (Full Timeframe
Continuity) scores from multi-timeframe resampling and reads ORB trend
columns from indicator data. Both can **filter** (reject) trades that
contradict higher-timeframe context, not just add bonus points.
"""

import math
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple

from lib.indicators import add_all_indicators, add_signal_indicators
from lib.signals import evaluate_signal
from lib.config import (
    RiskConfig, ExitConfig, SignalConfig, StratConfig, BacktestConfig,
    IndicatorConfig, get_position_size, get_signal_strength_label, load_config,
)
from lib.strat import StratClassifier
from lib.data_loader import RESAMPLE_RULES


@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    direction: str  # 'CALL' or 'PUT'
    base_score: int
    strat_bonus: int
    total_score: int
    position_size: float
    conditions_met: List[str]
    indicators_at_entry: Dict[str, float] = field(default_factory=dict)
    ftfc_score: float = 0.0     # FTFC alignment at entry (-1 to +1)
    orb_trend: int = 0          # ORB trend at entry (-1, 0, +1)
    # Filled on exit
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    return_pct: Optional[float] = None
    mae: float = 0.0  # Max Adverse Excursion
    mfe: float = 0.0  # Max Favorable Excursion


@dataclass
class BacktestResult:
    trades: List[Trade]
    daily_pnl: List[Dict]
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    annualization_factor: int = 252
    filter_counts: Dict[str, int] = field(default_factory=lambda: {
        'ftfc_rejected': 0, 'orb_rejected': 0, 'signals_evaluated': 0,
    })

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winners(self) -> List[Trade]:
        return [t for t in self.trades if t.return_pct and t.return_pct > 0]

    @property
    def losers(self) -> List[Trade]:
        return [t for t in self.trades if t.return_pct and t.return_pct <= 0]

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return len(self.winners) / len(self.trades)

    @property
    def avg_win(self) -> float:
        if not self.winners:
            return 0.0
        return np.mean([t.return_pct for t in self.winners])

    @property
    def avg_loss(self) -> float:
        if not self.losers:
            return 0.0
        return np.mean([t.return_pct for t in self.losers])

    @property
    def profit_factor(self) -> float:
        gross_wins = sum(t.return_pct for t in self.winners)
        gross_losses = abs(sum(t.return_pct for t in self.losers))
        if gross_losses == 0:
            return float('inf') if gross_wins > 0 else 0.0
        return gross_wins / gross_losses

    @property
    def expectancy(self) -> float:
        """Expected return per trade."""
        if not self.trades:
            return 0.0
        return np.mean([t.return_pct for t in self.trades if t.return_pct is not None])

    @property
    def max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown in percentage terms."""
        if self.equity_curve.empty:
            return 0.0
        peak = self.equity_curve.expanding().max()
        drawdown = (self.equity_curve - peak) / peak
        return drawdown.min() if len(drawdown) > 0 else 0.0

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio from daily PnL."""
        if not self.daily_pnl:
            return 0.0
        daily_returns = pd.Series([d['pnl'] for d in self.daily_pnl])
        std = daily_returns.std()
        # Guard against NaN AND zero. A fold with a single trading day has
        # pandas std(ddof=1)=NaN (degrees of freedom = 0). Before this guard
        # the NaN propagated into backtest_walk_forward_folds.sharpe as
        # Postgres `NaN`, which then poisoned downstream AVG/MAX aggregates
        # across the SPY/QQQ WF reports (`NaN == 0` is False in IEEE 754
        # so the original `== 0` guard didn't catch it). 0.0 is the
        # honest answer when there's no return variance to measure.
        if pd.isna(std) or std == 0:
            return 0.0
        return (daily_returns.mean() / std) * np.sqrt(self.annualization_factor)

    def _trade_durations(self) -> List[float]:
        """Duration of each trade in minutes."""
        return [(t.exit_time - t.entry_time).total_seconds() / 60.0
                for t in self.trades if t.entry_time and t.exit_time]

    def duration_metrics(self) -> Dict[str, float]:
        """Trade duration statistics in minutes."""
        durations = self._trade_durations()
        if not durations:
            return {}
        s = pd.Series(durations)
        winners = [d for d, t in zip(durations, self.trades) if t.return_pct and t.return_pct > 0]
        losers = [d for d, t in zip(durations, self.trades) if t.return_pct and t.return_pct <= 0]
        result = {
            'avg_duration_min': s.mean(), 'median_duration_min': s.median(),
            'p25_duration_min': s.quantile(0.25), 'p75_duration_min': s.quantile(0.75),
        }
        if winners:
            ws = pd.Series(winners)
            result['avg_win_duration_min'] = ws.mean()
            result['median_win_duration_min'] = ws.median()
        if losers:
            ls = pd.Series(losers)
            result['avg_loss_duration_min'] = ls.mean()
            result['median_loss_duration_min'] = ls.median()
        return result

    def duration_by_exit_reason(self) -> pd.DataFrame:
        """Duration and return breakdown by exit reason."""
        rows = []
        for t in self.trades:
            if t.entry_time and t.exit_time and t.return_pct is not None:
                rows.append({
                    'exit_reason': t.exit_reason,
                    'duration_min': (t.exit_time - t.entry_time).total_seconds() / 60.0,
                    'return_pct': t.return_pct, 'won': t.return_pct > 0,
                })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.groupby('exit_reason').agg(
            trades=('duration_min', 'count'),
            avg_duration=('duration_min', 'mean'),
            median_duration=('duration_min', 'median'),
            avg_return_bps=('return_pct', lambda x: x.mean() * 10000),
            win_rate=('won', 'mean'),
        ).round(2)

    def metrics(self) -> Dict[str, float]:
        """Summary metrics as a dict."""
        return {
            'total_trades': self.total_trades,
            'win_rate': self.win_rate,
            'avg_win_pct': self.avg_win,
            'avg_loss_pct': self.avg_loss,
            'profit_factor': self.profit_factor,
            'expectancy_pct': self.expectancy,
            'max_drawdown_pct': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'total_winners': len(self.winners),
            'total_losers': len(self.losers),
            **self.duration_metrics(),
        }

    def metrics_by_strength(self, risk_config: RiskConfig = None) -> pd.DataFrame:
        """Performance breakdown by signal strength."""
        rows = []
        for t in self.trades:
            if t.return_pct is not None:
                rows.append({
                    'total_score': t.total_score,
                    'strength': get_signal_strength_label(t.total_score, risk_config),
                    'return_pct': t.return_pct,
                    'won': t.return_pct > 0,
                })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.groupby('strength').agg(
            trades=('return_pct', 'count'),
            win_rate=('won', 'mean'),
            avg_return=('return_pct', 'mean'),
            total_return=('return_pct', 'sum'),
        ).round(4)

    def metrics_by_exit_reason(self) -> pd.DataFrame:
        """Performance breakdown by exit reason."""
        rows = []
        for t in self.trades:
            if t.return_pct is not None and t.exit_reason is not None:
                rows.append({
                    'exit_reason': t.exit_reason,
                    'return_pct': t.return_pct,
                    'won': t.return_pct > 0,
                })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.groupby('exit_reason').agg(
            trades=('return_pct', 'count'),
            win_rate=('won', 'mean'),
            avg_return=('return_pct', 'mean'),
            total_return=('return_pct', 'sum'),
        ).round(4)

    def metrics_by_direction(self) -> pd.DataFrame:
        """Performance breakdown by trade direction (CALL vs PUT)."""
        rows = []
        for t in self.trades:
            if t.return_pct is not None:
                rows.append({
                    'direction': t.direction,
                    'return_pct': t.return_pct,
                    'won': t.return_pct > 0,
                })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.groupby('direction').agg(
            trades=('return_pct', 'count'),
            win_rate=('won', 'mean'),
            avg_return=('return_pct', 'mean'),
            total_return=('return_pct', 'sum'),
        ).round(4)

    def summary(self, risk_config: RiskConfig = None) -> str:
        """Human-readable summary string."""
        m = self.metrics()
        lines = [
            f"Backtest Results",
            f"{'='*50}",
            f"Total Trades:    {m['total_trades']}",
            f"Win Rate:        {m['win_rate']:.1%}",
            f"Avg Win:         {m['avg_win_pct']:.3%}",
            f"Avg Loss:        {m['avg_loss_pct']:.3%}",
            f"Profit Factor:   {m['profit_factor']:.2f}",
            f"Expectancy:      {m['expectancy_pct']:.3%} per trade",
            f"Max Drawdown:    {m['max_drawdown_pct']:.2%}",
            f"Sharpe Ratio:    {m['sharpe_ratio']:.2f}",
        ]

        # Duration stats
        dm = self.duration_metrics()
        if dm:
            lines.append(f"\nTrade Duration:")
            lines.append(f"  Avg hold (all):    {dm.get('avg_duration_min', 0):.1f} min")
            lines.append(f"  Median hold (all): {dm.get('median_duration_min', 0):.1f} min")
            if 'avg_win_duration_min' in dm:
                lines.append(f"  Avg hold (wins):   {dm['avg_win_duration_min']:.1f} min")
            if 'avg_loss_duration_min' in dm:
                lines.append(f"  Avg hold (losses): {dm['avg_loss_duration_min']:.1f} min")

        # Duration by exit reason
        dur_df = self.duration_by_exit_reason()
        if not dur_df.empty:
            lines.append(f"\nDuration by Exit Reason:")
            lines.append(dur_df.to_string())

        # Filter rejection stats
        fc = self.filter_counts
        if fc.get('signals_evaluated', 0) > 0:
            lines.append(f"\nFiltering:")
            lines.append(f"  Signals evaluated: {fc['signals_evaluated']}")
            lines.append(f"  FTFC rejected:     {fc['ftfc_rejected']}")
            lines.append(f"  ORB rejected:      {fc['orb_rejected']}")
            total_rejected = fc['ftfc_rejected'] + fc['orb_rejected']
            if total_rejected > 0:
                lines.append(f"  Total filtered:    {total_rejected} "
                             f"({total_rejected / fc['signals_evaluated']:.1%} of signals)")

        # Exit reason breakdown
        exit_df = self.metrics_by_exit_reason()
        if not exit_df.empty:
            lines.append(f"\nBy Exit Reason:")
            lines.append(exit_df.to_string())

        # Direction breakdown
        dir_df = self.metrics_by_direction()
        if not dir_df.empty:
            lines.append(f"\nBy Direction:")
            lines.append(dir_df.to_string())

        strength_df = self.metrics_by_strength(risk_config)
        if not strength_df.empty:
            lines.append(f"\nBy Signal Strength:")
            lines.append(strength_df.to_string())

        return '\n'.join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert trades to a DataFrame."""
        rows = []
        for t in self.trades:
            rows.append({
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'direction': t.direction,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'exit_reason': t.exit_reason,
                'base_score': t.base_score,
                'strat_bonus': t.strat_bonus,
                'total_score': t.total_score,
                'position_size': t.position_size,
                'return_pct': t.return_pct,
                'mae': t.mae,
                'mfe': t.mfe,
                'ftfc_score': t.ftfc_score,
                'orb_trend': t.orb_trend,
                'conditions': ', '.join(t.conditions_met),
            })
        return pd.DataFrame(rows)


class BacktestEngine:
    """Bar-by-bar backtester using the 3-of-5 signal logic and risk management.

    When ``use_strat=True``, the engine:
    1. Classifies Strat candle types and detects combo patterns
    2. Computes real FTFC scores by resampling to multiple timeframes
    3. Reads ORB trend from indicator columns
    4. **Filters** trades that contradict FTFC / ORB (not just bonus)
    5. Adds bonus points for aligned trades that pass the filter
    """

    def __init__(
        self,
        risk_config: RiskConfig = None,
        exit_config: ExitConfig = None,
        signal_config: SignalConfig = None,
        strat_config: StratConfig = None,
        backtest_config: BacktestConfig = None,
        indicator_config: IndicatorConfig = None,
    ):
        self.risk = risk_config or RiskConfig()
        self.exit = exit_config or ExitConfig()
        self.signal = signal_config or SignalConfig()
        self.strat_config = strat_config or StratConfig()
        self.bt = backtest_config or BacktestConfig()
        self.ind = indicator_config or IndicatorConfig()
        self.strat_classifier = StratClassifier(strat_config=self.strat_config)
        self._filter_counts = {'ftfc_rejected': 0, 'orb_rejected': 0, 'signals_evaluated': 0}

    def _compute_ftfc_series(self, df: pd.DataFrame, close_col: str = 'Close') -> pd.Series:
        """Pre-compute FTFC alignment score for each bar.

        Resamples the input data to each configured timeframe, classifies
        Strat candle type, and computes a weighted FTFC score.

        Uses shift(1) on the higher-TF classifications to avoid lookahead
        bias — only completed bars' classifications are used.

        Returns a Series aligned to the input index with values in [-1, +1].
        """
        timeframes = self.strat_config.timeframes
        weights = self.strat_config.ftfc_weights

        classifications = {}

        for tf in timeframes:
            rule = RESAMPLE_RULES.get(tf)
            if rule is None:
                continue

            # Resample to higher timeframe
            agg_dict = {
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                close_col: 'last',
                'Volume': 'sum',
            }
            try:
                resampled = df.resample(rule).agg(agg_dict).dropna()
            except Exception:
                continue

            if len(resampled) < 2:
                continue

            # Classify Strat type on higher TF
            labels = self.strat_classifier.classify_series(resampled)

            # Map to numeric: 2U = +1, 2D = -1, neutral = 0
            numeric = labels.map({
                '2U': 1.0, '2D': -1.0, '1': 0.0, '3': 0.0, 'X': 0.0,
            }).fillna(0.0)

            # Shift by 1 so we only use the COMPLETED bar's classification
            # (avoids lookahead bias — current bar is still forming)
            numeric_shifted = numeric.shift(1)

            # Forward-fill into the 1m index
            classifications[tf] = numeric_shifted.reindex(
                df.index,
            ).ffill().fillna(0.0)

        if not classifications:
            return pd.Series(0.0, index=df.index)

        # Compute weighted FTFC score
        total_weight = sum(weights.get(tf, 0.0) for tf in classifications)
        if total_weight == 0:
            return pd.Series(0.0, index=df.index)

        ftfc_score = pd.Series(0.0, index=df.index)
        for tf, numeric in classifications.items():
            w = weights.get(tf, 0.0)
            ftfc_score += numeric * w

        ftfc_score /= total_weight
        return ftfc_score

    def run(
        self,
        df: pd.DataFrame,
        use_strat: bool = False,
        close_col: str = 'Close',
        ticker: Optional[str] = None,
    ) -> BacktestResult:
        """Run backtest over an indicator-enriched DataFrame.

        The DataFrame should already have indicator columns from
        ``add_all_indicators()``. Alternatively, the engine will compute
        them if the primary RSI column is missing.

        Parameters
        ----------
        df : OHLCV DataFrame with Time index or column
        use_strat : whether to apply Strat filtering + bonus scoring
        close_col : name of the close price column
        ticker : when provided, _check_exit_conditions reads
            target/stop/time-stop from `lib.strategies.exit_config_overrides`
            (Tier-A → ExitConfig defaults). When None, the existing
            `self.exit.*` reads are used unchanged — so walk-forward
            grid searches are unaffected.
        """
        # Reset filter counts
        self._filter_counts = {'ftfc_rejected': 0, 'orb_rejected': 0, 'signals_evaluated': 0}
        self._current_ticker = ticker

        # Ensure indicators exist
        if self.ind.rsi_col not in df.columns:
            df = add_all_indicators(df, close_col=close_col, indicator_config=self.ind)

        # Add Strat columns and compute FTFC if requested
        strat_df = None
        ftfc_series = None
        if use_strat and self.strat_config.enabled:
            strat_df = self.strat_classifier.detect_combos(df)
            ftfc_series = self._compute_ftfc_series(df, close_col=close_col)

        trades: List[Trade] = []
        daily_pnl: List[Dict] = []
        equity = [self.bt.starting_equity]

        # Get unique trading days
        if 'Time' in df.columns:
            df_dates = pd.to_datetime(df['Time']).dt.date
        else:
            df_dates = df.index.date

        unique_days = sorted(set(df_dates))

        for day in unique_days:
            day_mask = df_dates == day
            day_df = df[day_mask]

            if len(day_df) < self.bt.min_bars_per_day:
                continue

            day_trades = 0
            day_pnl = 0.0
            active_trade: Optional[Trade] = None

            i = 0
            while i < len(day_df):
                row = day_df.iloc[i]
                close_price = row.get(close_col, row.get('Close', row.get('Last')))

                if pd.isna(close_price):
                    i += 1
                    continue

                bar_time = row.get('Time', day_df.index[i])
                if isinstance(bar_time, str):
                    bar_time = pd.to_datetime(bar_time)

                # --- Check entry conditions ---
                # active_trade is always None here: once an entry fires
                # (below) it is immediately walked to full resolution via
                # _simulate_exit_indexed before the loop advances, so this
                # bar is only ever reached when no position is open —
                # matching the original bar-by-bar "active_trade is None"
                # gate exactly, just without an idle trade lingering
                # across loop iterations.
                if active_trade is None and day_trades < self.risk.max_daily_trades:
                    entry = self._check_entry(
                        row, bar_time, use_strat, strat_df, ftfc_series, i, day_df,
                    )
                    if entry:
                        active_trade, last_idx = self._simulate_exit_indexed(
                            entry, day_df, i, close_col=close_col,
                        )
                        trades.append(active_trade)
                        day_trades += 1
                        day_pnl += active_trade.return_pct * active_trade.position_size
                        active_trade = None

                        # Check daily limits after closing
                        if day_pnl <= self.risk.daily_loss_limit:
                            break
                        if day_pnl >= self.risk.daily_profit_target:
                            break

                        i = last_idx + 1
                        continue

                i += 1

            daily_pnl.append({'date': day, 'trades': day_trades, 'pnl': day_pnl})
            equity.append(equity[-1] * (1 + day_pnl))

        # Build equity curve
        eq_dates = [d['date'] for d in daily_pnl]
        equity_curve = pd.Series(equity[1:], index=eq_dates) if eq_dates else pd.Series(dtype=float)

        return BacktestResult(
            trades=trades,
            daily_pnl=daily_pnl,
            equity_curve=equity_curve,
            annualization_factor=self.bt.annualization_factor,
            filter_counts=dict(self._filter_counts),
        )

    def simulate_exit(
        self,
        trade: Trade,
        bars: pd.DataFrame,
        entry_idx: int,
        close_col: str = 'Close',
    ) -> Trade:
        """Walk ``bars`` forward from an entry to resolve a trade's exit.

        Extracted from the exit-handling block that used to be inline in
        ``run()`` (Task 3.1) so it can be reused by the labeled-trade
        replay path without re-running the full event-driven ``run()``
        loop. For each bar after ``entry_idx``, calls the existing
        ``_check_exit`` (target / stop / time-stop / RSI-extreme), tracks
        MAE/MFE while the position remains open, and force-closes with
        ``exit_reason='eod_close'`` at the LAST bar in ``bars`` if no exit
        condition fires before bars run out.

        ``_check_exit`` reads ``self._current_ticker`` for per-ticker exit
        overrides. This method does not set that attribute itself — it
        follows the same convention as ``run()``, which sets
        ``self._current_ticker = ticker`` once at the top of its own body
        before any bar processing starts. Callers invoking
        ``simulate_exit`` directly (outside of ``run()``) are responsible
        for setting ``self._current_ticker`` beforehand (or leaving it
        unset/None to use the engine's ``self.exit.*`` defaults).

        ``return_pct`` is filled as a RAW FRACTION (e.g. 0.003 == +0.30%),
        sign-corrected for PUT direction — the same engine-internal
        convention used throughout ``BacktestResult``.

        Parameters
        ----------
        trade : a Trade with entry fields populated and exit fields None
        bars : the bar DataFrame to walk (e.g. a single day's OHLCV slice)
        entry_idx : positional (``iloc``) index of the entry bar within
            ``bars`` — the walk starts at ``entry_idx + 1``
        close_col : name of the close price column

        Returns
        -------
        The same ``Trade`` instance, mutated in place with exit_time,
        exit_price, exit_reason, return_pct, mae, mfe filled in.
        """
        resolved_trade, _last_idx = self._simulate_exit_indexed(
            trade, bars, entry_idx, close_col=close_col,
        )
        return resolved_trade

    def _simulate_exit_indexed(
        self,
        trade: Trade,
        bars: pd.DataFrame,
        entry_idx: int,
        close_col: str = 'Close',
    ) -> Tuple[Trade, int]:
        """Core implementation shared by ``simulate_exit()`` and ``run()``.

        Identical to ``simulate_exit()`` except it also returns the
        positional index of the last bar consumed (the exit bar, or
        ``len(bars) - 1`` on an eod_close) so ``run()`` can resume its own
        per-bar loop immediately after the bar that closed this trade,
        without re-deriving that position via a timestamp lookup.
        """
        last_idx = entry_idx
        for i in range(entry_idx + 1, len(bars)):
            row = bars.iloc[i]
            close_price = row.get(close_col, row.get('Close', row.get('Last')))

            if pd.isna(close_price):
                continue

            bar_time = row.get('Time', bars.index[i])
            if isinstance(bar_time, str):
                bar_time = pd.to_datetime(bar_time)

            last_idx = i

            exit_result = self._check_exit(trade, row, bar_time, close_price)
            if exit_result:
                reason, exit_price = exit_result
                trade.exit_time = bar_time
                trade.exit_price = exit_price
                trade.exit_reason = reason

                if trade.direction == 'CALL':
                    trade.return_pct = (exit_price - trade.entry_price) / trade.entry_price
                else:
                    trade.return_pct = (trade.entry_price - exit_price) / trade.entry_price

                return trade, last_idx

            # Track MAE/MFE while in position
            if trade.direction == 'CALL':
                unrealized = (close_price - trade.entry_price) / trade.entry_price
            else:
                unrealized = (trade.entry_price - close_price) / trade.entry_price
            trade.mae = min(trade.mae, unrealized)
            trade.mfe = max(trade.mfe, unrealized)

        # No exit triggered before bars ran out — force-close at day end,
        # using the LAST bar in `bars` (matches the pre-extraction
        # post-loop "Force-close any open position at end of day" block).
        last_row = bars.iloc[-1]
        last_price = last_row.get(close_col, last_row.get('Close', last_row.get('Last')))
        last_time = last_row.get('Time', bars.index[-1])
        trade.exit_time = last_time
        trade.exit_price = last_price
        trade.exit_reason = 'eod_close'
        if trade.direction == 'CALL':
            trade.return_pct = (last_price - trade.entry_price) / trade.entry_price
        else:
            trade.return_pct = (trade.entry_price - last_price) / trade.entry_price

        return trade, len(bars) - 1

    def _check_entry(
        self,
        row: pd.Series,
        bar_time,
        use_strat: bool,
        strat_df: Optional[pd.DataFrame],
        ftfc_series: Optional[pd.Series],
        bar_idx: int,
        day_df: pd.DataFrame,
    ) -> Optional[Trade]:
        """Check if signal conditions are met for entry.

        When ``use_strat`` is True, this method:
        1. Evaluates the base 3-of-5 signal
        2. Checks time window
        3. Looks up FTFC score and ORB trend
        4. **Rejects** the trade if FTFC or ORB contradicts the signal direction
        5. Computes strat bonus for aligned trades that pass filtering
        """
        # Time window check
        if hasattr(bar_time, 'time'):
            t = bar_time.time() if not isinstance(bar_time, time) else bar_time
        elif hasattr(bar_time, 'hour'):
            t = time(bar_time.hour, bar_time.minute)
        else:
            t = None

        # Evaluate base signal (3-of-5)
        sig = evaluate_signal(
            row,
            min_conditions=self.signal.min_conditions,
            consecutive_periods=self.signal.consecutive_periods,
            call_rsi_range=self.signal.call_rsi_range,
            put_rsi_range=self.signal.put_rsi_range,
            signal_config=self.signal,
            indicator_config=self.ind,
        )

        if sig is None:
            return None

        # Time window filtering
        if t is not None:
            call_start = time(*[int(x) for x in self.signal.call_entry_start.split(':')])
            call_end = time(*[int(x) for x in self.signal.call_entry_end.split(':')])
            put_start = time(*[int(x) for x in self.signal.put_entry_start.split(':')])
            put_end = time(*[int(x) for x in self.signal.put_entry_end.split(':')])

            if sig['direction'] == 'CALL' and not (call_start <= t <= call_end):
                return None
            if sig['direction'] == 'PUT' and not (put_start <= t <= put_end):
                return None

        # --- Strat: FTFC score + ORB trend + filtering + bonus ---
        self._filter_counts['signals_evaluated'] += 1

        strat_bonus = 0
        bar_ftfc_score = 0.0
        bar_orb_trend = 0

        # Direction-gated Strat overlay: when the signal's direction is
        # not in StratConfig.allowed_directions, fall through with
        # strat_bonus=0 (base-mode scoring). The trade still enters; we
        # just don't apply the FTFC/ORB filter or the per-direction Strat
        # bonus. Added 2026-05-24 to let per-ticker configs disable Strat
        # on one direction (e.g. IWM PUTs) without losing the working
        # direction. Default allowed_directions = {'CALL','PUT'} preserves
        # legacy behaviour.
        if (use_strat and strat_df is not None
                and sig['direction'] in self.strat_config.allowed_directions):
            bar_index = day_df.index[bar_idx]

            # 1) Look up real FTFC score
            if ftfc_series is not None:
                bar_ftfc_score = ftfc_series.get(bar_index, 0.0)

            # 2) Look up ORB trend
            orb_label = self.ind.orb_windows[0]['label'] if self.ind.orb_windows else '5m'
            bar_orb_trend = int(row.get(f'ORB_{orb_label}_Trend', 0))

            # 3) FTFC FILTER: reject trades contradicted by higher-TF alignment
            if self.strat_config.ftfc_filter_enabled:
                threshold = self.strat_config.ftfc_threshold
                if sig['direction'] == 'CALL' and bar_ftfc_score <= -threshold:
                    self._filter_counts['ftfc_rejected'] += 1
                    return None
                if sig['direction'] == 'PUT' and bar_ftfc_score >= threshold:
                    self._filter_counts['ftfc_rejected'] += 1
                    return None

            # 4) ORB FILTER: reject trades contradicted by ORB breakout direction
            if self.strat_config.orb_filter_enabled:
                if sig['direction'] == 'CALL' and bar_orb_trend == -1:
                    self._filter_counts['orb_rejected'] += 1
                    return None
                if sig['direction'] == 'PUT' and bar_orb_trend == 1:
                    self._filter_counts['orb_rejected'] += 1
                    return None

            # 5) Strat bonus for aligned trades (only if not filtered)
            try:
                combo = 'none'
                if bar_index in strat_df.index:
                    combo = strat_df.loc[bar_index, 'strat_combo']
                strat_bonus = self.strat_classifier.get_strat_bonus(
                    signal_direction=sig['direction'],
                    combo=combo,
                    ftfc_score=bar_ftfc_score,
                    ftfc_threshold=self.strat_config.ftfc_threshold,
                    orb_trend=bar_orb_trend,
                )
            except (KeyError, IndexError):
                pass

        total_score = sig['base_score'] + strat_bonus
        close_col = 'Close' if 'Close' in row.index else 'Last'
        entry_price = row[close_col]

        return Trade(
            entry_time=bar_time,
            entry_price=entry_price,
            direction=sig['direction'],
            base_score=sig['base_score'],
            strat_bonus=strat_bonus,
            total_score=total_score,
            position_size=get_position_size(total_score, self.risk),
            conditions_met=sig['conditions_met'],
            ftfc_score=bar_ftfc_score,
            orb_trend=bar_orb_trend,
            indicators_at_entry={
                'rsi': row.get(self.ind.rsi_col),
                'stoch_rsi_k': row.get('StochRSI_K'),
                'ema_fast': row.get(f'EMA{self.ind.ema_fast_period}'),
                'vwap': row.get('VWAP'),
                'atr': row.get(self.ind.atr_col),
                'rvol': row.get('RVOL'),
            },
        )

    def _check_exit(
        self,
        trade: Trade,
        row: pd.Series,
        bar_time,
        close_price: float,
    ) -> Optional[Tuple[str, float]]:
        """Check if an active position should be exited.

        Returns (reason, exit_price) or None.
        """
        entry = trade.entry_price

        # Calculate unrealized return
        if trade.direction == 'CALL':
            unrealized = (close_price - entry) / entry
        else:
            unrealized = (entry - close_price) / entry

        # Per-ticker exit overrides (Tier-A) when ticker was passed to run().
        # Falls back to ExitConfig defaults when no override row / NULL / stale.
        ticker = getattr(self, '_current_ticker', None)
        if ticker is not None:
            from lib.strategies.exit_config_overrides import (
                get_call_target, get_put_target,
                get_call_stop, get_put_stop,
                get_call_time_stop, get_put_time_stop,
            )
            target = (get_call_target(ticker) if trade.direction == 'CALL'
                      else get_put_target(ticker))
            stop = (get_call_stop(ticker) if trade.direction == 'CALL'
                    else get_put_stop(ticker))
            time_limit = (get_call_time_stop(ticker) if trade.direction == 'CALL'
                          else get_put_time_stop(ticker))
        else:
            target = self.exit.call_target if trade.direction == 'CALL' else self.exit.put_target
            stop = self.exit.call_stop if trade.direction == 'CALL' else self.exit.put_stop
            time_limit = self.exit.call_time_stop if trade.direction == 'CALL' else self.exit.put_time_stop

        # Profit target
        if unrealized >= target:
            return 'target', close_price

        # Stop loss
        if unrealized <= -stop:
            return 'stop_loss', close_price

        # Time stop
        if hasattr(bar_time, 'timestamp') and hasattr(trade.entry_time, 'timestamp'):
            elapsed_minutes = (bar_time - trade.entry_time).total_seconds() / 60.0
        else:
            elapsed_minutes = 0
        if elapsed_minutes >= time_limit:
            return 'time_stop', close_price

        # RSI extreme exit
        rsi = row.get(self.ind.rsi_col, 50.0)
        if trade.direction == 'CALL' and rsi > self.exit.call_rsi_exit:
            return 'rsi_extreme', close_price
        if trade.direction == 'PUT' and rsi < self.exit.put_rsi_exit:
            return 'rsi_extreme', close_price

        return None


# ---------------------------------------------------------------------------
# Task 3.2: labeled-trade replay — score a user's journal trades against
# actual bars and benchmark them against the system.
# ---------------------------------------------------------------------------

# Minimum bars (inclusive of the entry bar) required before `evaluate_signal`
# is trusted — mirrors platform/api/routers/live.py's `compute_live_signal_series`
# 14-bar warm-up gate (that endpoint 422s below this; here we degrade a single
# trade's `system_signal_at_entry` to the "unavailable" shape instead, since
# the rest of the scorecard — fill_check, system_exit, actual_return_pct — is
# independent of indicator warm-up and shouldn't be thrown away with it).
_SIGNAL_WARMUP_BARS = 14


def _unavailable(trade_id, reason: str) -> dict:
    """An 'unavailable' scorecard — CLAUDE.md Rule 3.7: never zero-fill a
    trade we can't actually score. Deliberately omits actual_return_pct /
    fill_check / system_signal_at_entry / system_exit / exit_edge_bps so a
    caller can't mistake an unavailable row for a scored one."""
    return {'id': trade_id, 'status': 'unavailable', 'reason': reason}


def _score_one_trade(
    labeled_trade: dict,
    bars_by_date: Dict[str, pd.DataFrame],
    engine: 'BacktestEngine',
    signal_cache: Dict[str, pd.DataFrame],
) -> dict:
    """Score a single labeled trade. See `replay_labeled_trades` for the
    scorecard shape and unit conventions."""
    trade_id = labeled_trade.get('id')
    direction = str(labeled_trade.get('direction') or '').upper()
    entry_ts_raw = labeled_trade.get('entry_ts')
    entry_price = labeled_trade.get('entry_price')
    exit_ts_raw = labeled_trade.get('exit_ts')
    exit_price = labeled_trade.get('exit_price')

    # An active (still-open) trade has no exit yet — nothing to benchmark.
    if exit_ts_raw is None or exit_price is None:
        return _unavailable(trade_id, 'trade still open')

    if direction not in ('CALL', 'PUT'):
        return _unavailable(trade_id, f'invalid direction: {labeled_trade.get("direction")!r}')

    if (
        entry_price is None
        or entry_price == 0
        or (isinstance(entry_price, float) and math.isnan(entry_price))
    ):
        return _unavailable(trade_id, 'invalid entry price')

    try:
        entry_dt = pd.to_datetime(entry_ts_raw)
    except (ValueError, TypeError):
        return _unavailable(trade_id, 'invalid entry_ts')

    date_key = entry_dt.strftime('%Y-%m-%d')
    day_bars = bars_by_date.get(date_key)
    if day_bars is None or day_bars.empty:
        return _unavailable(trade_id, 'no bars for date')

    # Reconcile formats: the journal's entry_ts wall-clock (minute precision)
    # against the bars' 'Time' strings — sort + reset so `entry_idx` below is
    # a valid positional (iloc) index into the frame we actually walk.
    day_bars = day_bars.sort_values('Time').reset_index(drop=True)
    entry_minute_key = entry_dt.strftime('%Y-%m-%d %H:%M')
    bar_minutes = pd.to_datetime(day_bars['Time']).dt.strftime('%Y-%m-%d %H:%M')
    matches = day_bars.index[bar_minutes == entry_minute_key]
    if len(matches) == 0:
        return _unavailable(trade_id, 'entry bar not found')
    entry_idx = int(matches[0])
    entry_bar = day_bars.iloc[entry_idx]

    fill_check = 'ok'
    if not (entry_bar['Low'] <= entry_price <= entry_bar['High']):
        fill_check = 'price_outside_bar_range'

    # User's actual return — TRUE PERCENT, sign-corrected for PUT (journal
    # convention; mirrors platform/api/routers/journal.py's `_return_pct`).
    raw_pct = (exit_price - entry_price) / entry_price * 100.0
    actual_return_pct = raw_pct if direction == 'CALL' else -raw_pct

    # --- System signal at entry: the exact production path
    # /api/live/signal-series uses (add_signal_indicators + evaluate_signal,
    # ticker-agnostic default configs — see live.py's compute_live_signal_series
    # docstring). Below the warm-up floor the indicators aren't trustworthy,
    # so the field degrades to the explicit "unavailable" shape rather than
    # silently reporting a spurious no-signal result.
    if entry_idx + 1 < _SIGNAL_WARMUP_BARS:
        system_signal_at_entry: dict = {'status': 'unavailable'}
    else:
        if date_key not in signal_cache:
            signal_cache[date_key] = add_signal_indicators(day_bars, close_col='Close')
        sig_row = signal_cache[date_key].iloc[entry_idx]
        sig = evaluate_signal(sig_row)
        if sig is not None:
            system_signal_at_entry = {'direction': sig['direction'], 'score': sig['total_score']}
        else:
            system_signal_at_entry = {'direction': None, 'score': 0}

    # --- System exit: walk the SAME day's bars forward from the entry bar
    # via Task 3.1's simulate_exit(), using the LABEL's entry_price (that's
    # what we're benchmarking) and entry_time from the matched bar.
    system_trade = Trade(
        entry_time=pd.to_datetime(entry_bar['Time']),
        entry_price=float(entry_price),
        direction=direction,
        base_score=0, strat_bonus=0, total_score=0, position_size=1.0,
        conditions_met=[],
    )
    resolved = engine.simulate_exit(system_trade, day_bars, entry_idx, close_col='Close')
    system_return_pct = None if resolved.return_pct is None else resolved.return_pct * 100.0  # fraction -> percent
    system_exit = {
        'exit_reason': resolved.exit_reason,
        'return_pct': system_return_pct,
        'exit_time': None if resolved.exit_time is None else str(resolved.exit_time),
    }

    exit_edge_bps = None
    if system_return_pct is not None:
        # (user_return_pct - system_return_pct) * 100 -- percent -> bps.
        exit_edge_bps = (actual_return_pct - system_return_pct) * 100.0

    return {
        'id': trade_id,
        'status': 'ok',
        'actual_return_pct': round(actual_return_pct, 4),
        'fill_check': fill_check,
        'system_signal_at_entry': system_signal_at_entry,
        'system_exit': {
            **system_exit,
            'return_pct': None if system_return_pct is None else round(system_return_pct, 4),
        },
        'exit_edge_bps': None if exit_edge_bps is None else round(exit_edge_bps, 4),
    }


def _aggregate_scorecards(scorecards: List[dict]) -> dict:
    """Aggregate metrics over a list of per-trade scorecards. `n` counts
    every trade passed in; `scored_n` counts only status=='ok' rows — an
    unavailable trade is never zero-filled into the average (Rule 3.7).

    `system_agreement_rate` definition (medium finding, PR review on
    bca2c899): a scored trade's `system_signal_at_entry` is one of three
    shapes —
      1. ``{"status": "unavailable"}`` — the 14-bar indicator warm-up
         hadn't completed; the system never got a chance to opine.
      2. ``{"direction": None, "score": 0}`` — the benchmark RAN but its
         conditions didn't fire; the system had no setup.
      3. ``{"direction": "CALL"|"PUT", "score": N}`` — the benchmark
         produced an actual directional call. Only these are
         "system-resolved".
    Folding (1) and (2) into "disagreement" (the original implementation)
    silently penalizes trades the system never actually took a position
    on, understating the user's real edge whenever the system was simply
    silent. The rate is now computed ONLY over system-resolved trades:
    ``system_resolved_n`` is the denominator, and `system_agreement_rate`
    is ``None`` (never 0.0) when that denominator is 0 — an honest null,
    not a fabricated "0% agreement". `system_no_signal_n` separately
    counts case (2) so a caller/UI can say "the system had no setup on N
    of your entries" without conflating it with disagreement.
    """
    n = len(scorecards)
    scored = [c for c in scorecards if c.get('status') == 'ok']
    scored_n = len(scored)

    # LOW finding: an "ok" card is a promise that these two numeric
    # fields are populated. Assert it loudly here (not a silent skip) so
    # a future _score_one_trade regression surfaces immediately, at the
    # trade that violated the invariant, rather than as a downstream
    # None-arithmetic TypeError far from its cause.
    for c in scored:
        if c.get('exit_edge_bps') is None or c.get('actual_return_pct') is None:
            raise ValueError(
                f"trade {c.get('id')!r}: status=='ok' but exit_edge_bps/"
                f"actual_return_pct is None — ok-card invariant violated"
            )

    if scored_n == 0:
        return {
            'n': n, 'scored_n': 0, 'win_rate': 0.0, 'avg_return_pct': 0.0,
            'system_resolved_n': 0, 'system_no_signal_n': 0,
            'system_agreement_rate': None, 'avg_exit_edge_bps': 0.0,
        }

    wins = [c for c in scored if c['actual_return_pct'] > 0]
    win_rate = len(wins) / scored_n
    avg_return_pct = sum(c['actual_return_pct'] for c in scored) / scored_n

    # 'direction' key absent -> warm-up "unavailable" shape (case 1).
    # 'direction' present and None -> benchmark ran, no setup (case 2).
    # 'direction' present and non-None -> system-resolved (case 3).
    resolved = [
        c for c in scored
        if c['system_signal_at_entry'].get('direction') is not None
    ]
    system_resolved_n = len(resolved)
    no_signal = [
        c for c in scored
        if 'direction' in c['system_signal_at_entry']
        and c['system_signal_at_entry']['direction'] is None
    ]
    system_no_signal_n = len(no_signal)

    # The labeled trade's own direction is threaded through as
    # '_labeled_direction' by the caller (replay_labeled_trades) since the
    # public scorecard shape doesn't otherwise carry it.
    agreements = sum(
        1 for c in resolved
        if c['system_signal_at_entry']['direction'] == c.get('_labeled_direction')
    )
    system_agreement_rate = (
        agreements / system_resolved_n if system_resolved_n else None
    )

    avg_exit_edge_bps = sum(c['exit_edge_bps'] for c in scored) / scored_n

    return {
        'n': n,
        'scored_n': scored_n,
        'win_rate': round(win_rate, 4),
        'avg_return_pct': round(avg_return_pct, 4),
        'system_resolved_n': system_resolved_n,
        'system_no_signal_n': system_no_signal_n,
        'system_agreement_rate': (
            None if system_agreement_rate is None
            else round(system_agreement_rate, 4)
        ),
        'avg_exit_edge_bps': round(avg_exit_edge_bps, 4),
    }


def replay_labeled_trades(
    labeled: List[dict],
    bars_by_date: Dict[str, pd.DataFrame],
    exit_config: Optional[ExitConfig] = None,
    ticker: Optional[str] = None,
) -> dict:
    """Score user-labeled trades against actual bars + benchmark vs the system.

    Parameters
    ----------
    labeled : list of ``{id, direction (CALL|PUT), entry_ts (ISO string),
        entry_price, exit_ts (ISO string or None), exit_price (or None)}``.
        A trade with ``exit_ts``/``exit_price`` of None (still open) is
        scored as ``unavailable`` / ``"trade still open"`` — never
        zero-filled.
    bars_by_date : ``{"YYYY-MM-DD": DataFrame}`` — each frame must carry
        uppercase ``Open``/``High``/``Low``/``Close``/``Volume`` columns
        plus a ``Time`` column (string or datetime-like) at 1-minute
        resolution for that date. A date missing from this dict (or an
        empty frame) marks every trade on that date ``unavailable`` /
        ``"no bars for date"``.
    exit_config : optional override for the engine's exit thresholds
        (target/stop/time-stop). When omitted, ``load_config(ticker=ticker)``
        supplies them (per-ticker ``alert_config.json`` overrides apply).
    ticker : when provided, set on the engine as ``_current_ticker`` — the
        SAME per-ticker Tier-A DB override contract ``BacktestEngine.run()``
        uses (see ``simulate_exit``'s docstring, Task 3.1). When ``None``,
        the engine uses ``exit_config``/``cfg.exit`` directly with no DB
        round-trip — the path every hermetic test in this module exercises.

    Returns
    -------
    ``{"trades": [...per-trade scorecards...], "aggregate": {...}}``.

    UNITS: every ``*_pct`` field is TRUE PERCENT (0.3-style values, e.g.
    +0.30, not the engine's raw-fraction 0.003) — the conversion happens
    here, once, at the fraction -> percent boundary. ``exit_edge_bps =
    (user_return_pct - system_return_pct) * 100`` (percent -> bps).

    Per-trade scorecard (``status == "ok"``):
    ``{id, status: "ok", actual_return_pct, fill_check: "ok"|
    "price_outside_bar_range", system_signal_at_entry: {direction, score} |
    {"status": "unavailable"}, system_exit: {exit_reason, return_pct,
    exit_time}, exit_edge_bps}``.
    ``status == "unavailable"``: ``{id, status: "unavailable", reason}`` —
    no other fields are populated (never zero-filled; CLAUDE.md Rule 3.7).

    Aggregate: ``{n, scored_n, win_rate (0-1), avg_return_pct,
    system_resolved_n, system_no_signal_n, system_agreement_rate,
    avg_exit_edge_bps}``. ``n`` counts every input trade; ``scored_n``
    counts only ``status == "ok"`` trades — unavailable trades never enter
    an average.

    ``system_agreement_rate`` is computed ONLY over "system-resolved"
    scored trades — those whose ``system_signal_at_entry`` produced an
    actual ``CALL``/``PUT`` direction. Trades where the benchmark's
    indicator warm-up hadn't completed (``system_signal_at_entry ==
    {"status": "unavailable"}``), or where it ran but fired no direction
    (``{"direction": None, ...}``), are EXCLUDED from the rate's
    denominator entirely — they are NOT folded in as "disagreement",
    since the system never took a position to disagree with.
    ``system_resolved_n`` is that denominator; ``system_no_signal_n``
    separately counts the "ran but no setup" case so a caller can
    surface "the system had no setup on N of your entries" without
    conflating it with disagreement. When ``system_resolved_n == 0``,
    ``system_agreement_rate`` is ``None`` — an honest null, never a
    fabricated ``0.0`` (CLAUDE.md Rule 3.7).

    System signal at entry reuses ``lib.indicators.add_signal_indicators`` +
    ``lib.signals.evaluate_signal`` with plain (uncalibrated, ticker-agnostic)
    default configs — the exact path
    ``platform/api/routers/live.py::compute_live_signal_series`` (the
    ``/api/live/signal-series`` endpoint) uses, so the benchmark can't drift
    from what the Charts page's "Sig" overlay already shows. System exit
    reuses ``BacktestEngine.simulate_exit`` (Task 3.1) with configs from
    ``load_config(ticker=ticker)`` — the SAME engine construction
    ``scripts/run_backtest.py`` uses (Rule 3.6: no re-derived math).

    Capacity: one in-memory pandas pass per trade over its day's bars
    (<=~390 rows/day); indicator computation is cached per date so trades
    sharing a day only pay for it once. No DB writes. No new DB reads beyond
    what the caller already loaded into ``bars_by_date``.
    """
    cfg = load_config(ticker=ticker)
    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=exit_config or cfg.exit,
        signal_config=cfg.signal,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )
    # Matches BacktestEngine.run()'s own convention (sets this once at the
    # top of its body, even when ticker is None) — see simulate_exit's
    # docstring (Task 3.1) for the full contract.
    engine._current_ticker = ticker

    signal_cache: Dict[str, pd.DataFrame] = {}
    scorecards = [
        _score_one_trade(t, bars_by_date, engine, signal_cache)
        for t in labeled
    ]

    # system_agreement_rate needs each scorecard compared against ITS OWN
    # trade's labeled direction (the scorecard itself doesn't carry
    # 'direction' — only the input labeled dict does), so thread it through
    # as a parallel list rather than mutating the public scorecard shape.
    directions_by_id = {t.get('id'): str(t.get('direction') or '').upper() for t in labeled}
    for c in scorecards:
        c['_labeled_direction'] = directions_by_id.get(c.get('id'))

    aggregate = _aggregate_scorecards(scorecards)

    # Strip the internal bookkeeping key before returning.
    for c in scorecards:
        c.pop('_labeled_direction', None)

    return {'trades': scorecards, 'aggregate': aggregate}
