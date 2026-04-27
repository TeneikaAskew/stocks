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

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple

from lib.indicators import add_all_indicators
from lib.signals import evaluate_signal
from lib.config import (
    RiskConfig, ExitConfig, SignalConfig, StratConfig, BacktestConfig,
    IndicatorConfig, get_position_size, get_signal_strength_label,
)
from lib.strat import StratClassifier
from lib.data_loader import RESAMPLE_RULES


@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    direction: str  # 'CALL' or 'PUT'
    base_score: int
    strat_bonus: float
    total_score: float
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
        if daily_returns.std() == 0:
            return 0.0
        return (daily_returns.mean() / daily_returns.std()) * np.sqrt(self.annualization_factor)

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
        """
        # Reset filter counts
        self._filter_counts = {'ftfc_rejected': 0, 'orb_rejected': 0, 'signals_evaluated': 0}

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

            for i in range(len(day_df)):
                row = day_df.iloc[i]
                close_price = row.get(close_col, row.get('Close', row.get('Last')))

                if pd.isna(close_price):
                    continue

                bar_time = row.get('Time', day_df.index[i])
                if isinstance(bar_time, str):
                    bar_time = pd.to_datetime(bar_time)

                # --- Check exit conditions ---
                if active_trade is not None:
                    exit_result = self._check_exit(active_trade, row, bar_time, close_price)
                    if exit_result:
                        reason, exit_price = exit_result
                        active_trade.exit_time = bar_time
                        active_trade.exit_price = exit_price
                        active_trade.exit_reason = reason

                        if active_trade.direction == 'CALL':
                            active_trade.return_pct = (exit_price - active_trade.entry_price) / active_trade.entry_price
                        else:
                            active_trade.return_pct = (active_trade.entry_price - exit_price) / active_trade.entry_price

                        trades.append(active_trade)
                        day_trades += 1
                        day_pnl += active_trade.return_pct * active_trade.position_size
                        active_trade = None

                        # Check daily limits after closing
                        if day_pnl <= self.risk.daily_loss_limit:
                            break
                        if day_pnl >= self.risk.daily_profit_target:
                            break
                        continue

                    # Track MAE/MFE while in position
                    if active_trade.direction == 'CALL':
                        unrealized = (close_price - active_trade.entry_price) / active_trade.entry_price
                    else:
                        unrealized = (active_trade.entry_price - close_price) / active_trade.entry_price
                    active_trade.mae = min(active_trade.mae, unrealized)
                    active_trade.mfe = max(active_trade.mfe, unrealized)

                # --- Check entry conditions ---
                if active_trade is None and day_trades < self.risk.max_daily_trades:
                    entry = self._check_entry(
                        row, bar_time, use_strat, strat_df, ftfc_series, i, day_df,
                    )
                    if entry:
                        active_trade = entry

            # Force-close any open position at end of day
            if active_trade is not None:
                last_row = day_df.iloc[-1]
                last_price = last_row.get(close_col, last_row.get('Close', last_row.get('Last')))
                last_time = last_row.get('Time', day_df.index[-1])
                active_trade.exit_time = last_time
                active_trade.exit_price = last_price
                active_trade.exit_reason = 'eod_close'
                if active_trade.direction == 'CALL':
                    active_trade.return_pct = (last_price - active_trade.entry_price) / active_trade.entry_price
                else:
                    active_trade.return_pct = (active_trade.entry_price - last_price) / active_trade.entry_price
                trades.append(active_trade)
                day_trades += 1
                day_pnl += active_trade.return_pct * active_trade.position_size
                active_trade = None

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

        strat_bonus = 0.0
        bar_ftfc_score = 0.0
        bar_orb_trend = 0

        if use_strat and strat_df is not None:
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

        # Profit target
        target = self.exit.call_target if trade.direction == 'CALL' else self.exit.put_target
        if unrealized >= target:
            return 'target', close_price

        # Stop loss
        stop = self.exit.call_stop if trade.direction == 'CALL' else self.exit.put_stop
        if unrealized <= -stop:
            return 'stop_loss', close_price

        # Time stop
        if hasattr(bar_time, 'timestamp') and hasattr(trade.entry_time, 'timestamp'):
            elapsed_minutes = (bar_time - trade.entry_time).total_seconds() / 60.0
        else:
            elapsed_minutes = 0

        time_limit = self.exit.call_time_stop if trade.direction == 'CALL' else self.exit.put_time_stop
        if elapsed_minutes >= time_limit:
            return 'time_stop', close_price

        # RSI extreme exit
        rsi = row.get(self.ind.rsi_col, 50.0)
        if trade.direction == 'CALL' and rsi > self.exit.call_rsi_exit:
            return 'rsi_extreme', close_price
        if trade.direction == 'PUT' and rsi < self.exit.put_rsi_exit:
            return 'rsi_extreme', close_price

        return None
