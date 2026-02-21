"""
Walk-forward validation and parameter sensitivity analysis.

Implements anchored walk-forward: expanding training window with fixed
test window, sliding forward one test period at a time.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from itertools import product

from lib.backtest import BacktestEngine, BacktestResult
from lib.config import RiskConfig, ExitConfig, SignalConfig, StratConfig


@dataclass
class WalkForwardResult:
    fold_results: List[BacktestResult]
    fold_dates: List[Dict]  # [{train_start, train_end, test_start, test_end}, ...]
    aggregate_metrics: Dict[str, float] = field(default_factory=dict)
    stability_score: float = 0.0

    def summary(self) -> str:
        lines = [
            "Walk-Forward Validation Results",
            "=" * 50,
            f"Total Folds: {len(self.fold_results)}",
            f"Stability Score: {self.stability_score:.2f}",
            "",
        ]

        # Per-fold summary
        for i, (result, dates) in enumerate(zip(self.fold_results, self.fold_dates)):
            m = result.metrics()
            lines.append(
                f"Fold {i+1}: {dates['test_start']} to {dates['test_end']} | "
                f"Trades: {m['total_trades']} | "
                f"Win Rate: {m['win_rate']:.1%} | "
                f"Expectancy: {m['expectancy_pct']:.3%}"
            )

        # Aggregate
        lines.append("")
        lines.append("Aggregate Metrics:")
        for k, v in self.aggregate_metrics.items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.4f}")
            else:
                lines.append(f"  {k}: {v}")

        return '\n'.join(lines)


class WalkForwardValidator:
    """Anchored walk-forward validation with expanding training window."""

    def __init__(
        self,
        risk_config: RiskConfig = None,
        exit_config: ExitConfig = None,
        signal_config: SignalConfig = None,
        strat_config: StratConfig = None,
        train_months: int = 6,
        test_months: int = 1,
    ):
        self.risk = risk_config or RiskConfig()
        self.exit = exit_config or ExitConfig()
        self.signal = signal_config or SignalConfig()
        self.strat = strat_config or StratConfig()
        self.train_months = train_months
        self.test_months = test_months

    def run(
        self,
        df: pd.DataFrame,
        use_strat: bool = False,
        close_col: str = 'Close',
    ) -> WalkForwardResult:
        """Run walk-forward validation over the full dataset.

        Folds:
        - Fold 1: Train [0, train_months) → Test [train_months, train_months+test_months)
        - Fold 2: Train [0, train_months+test_months) → Test [train+test, train+2*test)
        - ... until data runs out
        """
        if 'Time' in df.columns:
            dates = pd.to_datetime(df['Time'])
        else:
            dates = pd.to_datetime(df.index)

        start_date = dates.min()
        end_date = dates.max()

        fold_results = []
        fold_dates = []

        # First test period starts after initial training window
        train_end = start_date + pd.DateOffset(months=self.train_months)

        while True:
            test_start = train_end
            test_end = test_start + pd.DateOffset(months=self.test_months)

            if test_start >= end_date:
                break

            # Clamp test_end to available data
            test_end = min(test_end, end_date)

            # Split data
            test_mask = (dates >= test_start) & (dates < test_end)
            test_df = df[test_mask]

            if len(test_df) < 50:  # Need minimum data for meaningful test
                train_end = test_end
                continue

            # Run backtest on test period only
            engine = BacktestEngine(
                risk_config=self.risk,
                exit_config=self.exit,
                signal_config=self.signal,
                strat_config=self.strat,
            )
            result = engine.run(test_df, use_strat=use_strat, close_col=close_col)

            fold_results.append(result)
            fold_dates.append({
                'train_start': start_date,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
            })

            # Slide forward
            train_end = test_end

        # Calculate aggregate metrics
        aggregate = self._aggregate_metrics(fold_results)
        stability = self._calculate_stability(fold_results)

        return WalkForwardResult(
            fold_results=fold_results,
            fold_dates=fold_dates,
            aggregate_metrics=aggregate,
            stability_score=stability,
        )

    def parameter_sensitivity(
        self,
        df: pd.DataFrame,
        param_grid: Dict[str, List],
        use_strat: bool = False,
        close_col: str = 'Close',
    ) -> pd.DataFrame:
        """Test parameter combinations and return metrics for each.

        Parameters
        ----------
        param_grid : dict mapping parameter names to lists of values.
            Supported keys:
            - consecutive_periods: [2, 3, 4]
            - call_rsi_low / call_rsi_high: RSI band bounds
            - put_rsi_low / put_rsi_high
            - call_target / put_target: profit target as decimal
            - call_time_stop / put_time_stop: minutes
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combos = list(product(*values))

        results = []
        total = len(combos)

        for i, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            print(f"  Parameter combo {i+1}/{total}: {params}")

            # Build configs from params
            sig = SignalConfig(
                consecutive_periods=params.get('consecutive_periods', self.signal.consecutive_periods),
                call_rsi_range=(
                    params.get('call_rsi_low', self.signal.call_rsi_range[0]),
                    params.get('call_rsi_high', self.signal.call_rsi_range[1]),
                ),
                put_rsi_range=(
                    params.get('put_rsi_low', self.signal.put_rsi_range[0]),
                    params.get('put_rsi_high', self.signal.put_rsi_range[1]),
                ),
            )
            exit_ = ExitConfig(
                call_target=params.get('call_target', self.exit.call_target),
                put_target=params.get('put_target', self.exit.put_target),
                call_time_stop=params.get('call_time_stop', self.exit.call_time_stop),
                put_time_stop=params.get('put_time_stop', self.exit.put_time_stop),
            )

            engine = BacktestEngine(
                risk_config=self.risk,
                exit_config=exit_,
                signal_config=sig,
                strat_config=self.strat,
            )
            result = engine.run(df, use_strat=use_strat, close_col=close_col)
            metrics = result.metrics()
            metrics.update(params)
            results.append(metrics)

        return pd.DataFrame(results)

    def _aggregate_metrics(self, fold_results: List[BacktestResult]) -> Dict[str, float]:
        """Average metrics across all folds."""
        if not fold_results:
            return {}

        all_metrics = [r.metrics() for r in fold_results]
        keys = all_metrics[0].keys()

        aggregate = {}
        for key in keys:
            values = [m[key] for m in all_metrics if isinstance(m[key], (int, float))]
            if values:
                aggregate[f'avg_{key}'] = np.mean(values)
                aggregate[f'std_{key}'] = np.std(values)

        aggregate['total_folds'] = len(fold_results)
        aggregate['total_trades_all_folds'] = sum(r.total_trades for r in fold_results)
        return aggregate

    def _calculate_stability(self, fold_results: List[BacktestResult]) -> float:
        """Stability score: what fraction of folds are profitable.

        Returns a value between 0.0 (none profitable) and 1.0 (all profitable).
        """
        if not fold_results:
            return 0.0

        profitable_folds = sum(
            1 for r in fold_results if r.expectancy > 0
        )
        return profitable_folds / len(fold_results)
