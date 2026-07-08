"""
Walk-forward validation and parameter sensitivity analysis.

Implements anchored walk-forward: expanding training window with fixed
test window, sliding forward one test period at a time.
"""

import re

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from itertools import product

from lib.backtest import BacktestEngine, BacktestResult
from lib.config import (
    RiskConfig, ExitConfig, SignalConfig, StratConfig,
    BacktestConfig, IndicatorConfig, WalkForwardConfig,
)
from lib.style_miner import StyleProfile

# ---------------------------------------------------------------------------
# Task 4.3: StyleProfile -> SignalConfig conversion
# ---------------------------------------------------------------------------

_CONSEC_CONDITION_RE = re.compile(r'^consec_(up|down)_ge_(\d+)$')

# Every mined vocabulary condition (lib.style_miner module docstring) EXCEPT
# the consec_(up|down)_ge_N pair, which is parsed via _CONSEC_CONDITION_RE
# instead of a static membership check (the N is data, not part of the name).
_DIRECT_TUNABLE_CONDITIONS = frozenset({
    'rsi_25_50', 'rsi_50_75', 'above_vwap', 'below_vwap',
    'stoch_oversold', 'stoch_overbought',
})


def profile_to_signal_config(profile: StyleProfile) -> SignalConfig:
    """Convert a mined `StyleProfile` (lib.style_miner, Task 4.2) into a
    `SignalConfig` override for `WalkForwardValidator.run_profile` (Task 4.3).

    Mapping mechanics (the documented design-latitude call)
    ---------------------------------------------------------
    `lib.signals.evaluate_signal` / `check_call_conditions` /
    `check_put_conditions` expose exactly four tunable levers:
    `min_conditions`, `call_rsi_range`/`put_rsi_range`, `consecutive_periods`,
    and `stoch_rsi_oversold`/`stoch_rsi_overbought`. There is NO lever that
    disables one individual scoring factor while keeping the rest (e.g. "only
    test below_vwap, not consecutive_down, for this CALL") — `SignalConfig`
    itself has no `disabled_conditions` field. That concept exists ONLY as a
    ticker-keyed, Cloud-SQL-backed override resolved inside
    `evaluate_signal(ticker=...)` via
    `lib.strategies.exit_config_overrides._latest_overrides`, which doesn't
    fit here: a mined profile is an in-memory object produced per-request,
    not a persisted per-ticker override row, and `run_profile` must not
    write one just to validate a candidate profile.

    So this function uses the ONE lever signals.py actually offers for
    "restrict to N conditions": `min_conditions = len(profile.conditions)`.
    This is an APPROXIMATION, not a literal "fires only when exactly these
    conditions are true" filter — `check_call_conditions`/
    `check_put_conditions` always score against their fixed 5-factor set
    (consecutive-move, RSI zone, VWAP side, StochRSI zone, level-break), so
    in principle a bar could satisfy `min_conditions` via a DIFFERENT
    combination of factors than the ones the profile named (e.g. a bar with
    level-break + consecutive-move true but NOT the profile's RSI zone).
    The documented interpretation — and the one
    `tests/test_style_walk_forward.py` pins with crafted days — is:
    "fires when at least len(profile.conditions) of the underlying 5-factor
    set are true", which coincides EXACTLY with "all of the profile's named
    conditions" only on bars where no other factor also fires. Callers
    relying on an exact per-condition gate should not use this conversion
    for anything more precise than the walk-forward sanity-check it's built
    for.

    RSI range / consecutive_periods / StochRSI thresholds are always left at
    fresh `SignalConfig()` DEFAULTS, never the caller's own `self.signal` or
    a per-ticker override — Task 4.3 hard seam: `style_miner.mine_style`
    snapshots conditions using a fresh `SignalConfig()` (never a per-ticker
    override, see `snapshot_entry_conditions`), so validating against any
    other thresholds would score the profile against a vocabulary it was
    never mined against.

    Raises
    ------
    ValueError
        If a condition name isn't in the mined vocabulary, or if a
        `consec_(up|down)_ge_N` condition's `N` doesn't match
        `SignalConfig().consecutive_periods` — a stale profile mined under a
        since-changed default is never silently honored.
    """
    base = SignalConfig()
    consec_values: set = set()

    for cond in profile.conditions:
        m = _CONSEC_CONDITION_RE.match(cond)
        if m:
            consec_values.add(int(m.group(2)))
            continue
        if cond not in _DIRECT_TUNABLE_CONDITIONS:
            raise ValueError(
                f"unknown style condition {cond!r} — not in the mined "
                f"vocabulary (see lib.style_miner module docstring)"
            )

    if consec_values and consec_values != {base.consecutive_periods}:
        raise ValueError(
            f"profile condition(s) reference consecutive-move threshold(s) "
            f"{sorted(consec_values)}, but SignalConfig().consecutive_periods "
            f"= {base.consecutive_periods} — the mined profile is stale "
            f"against the current default (style_miner always mines against "
            f"a fresh SignalConfig())"
        )

    return SignalConfig(
        min_conditions=len(profile.conditions),
        consecutive_periods=base.consecutive_periods,
        call_rsi_range=base.call_rsi_range,
        put_rsi_range=base.put_rsi_range,
        stoch_rsi_oversold=base.stoch_rsi_oversold,
        stoch_rsi_overbought=base.stoch_rsi_overbought,
    )


def _rebuild_consecutive(
    df: pd.DataFrame, consecutive_periods: int, close_col: str = 'Close',
) -> pd.DataFrame:
    """Return a copy of `df` with Consecutive_Up/Down rebuilt for a given
    window.

    The consecutive-bar columns are a rolling-N sum, so when the sweep
    varies `consecutive_periods` the column's window must move with the
    evaluate_signal threshold — a check of `>= 4` against a column built
    with window 3 can never fire. Called once per distinct swept value.
    """
    from lib.indicators import calculate_consecutive_moves
    out = df.copy()
    if 'Price_Change' in out.columns:
        price_change = out['Price_Change']
    else:
        price_change = out[close_col].pct_change() * 100
    up, down = calculate_consecutive_moves(price_change, consecutive_periods)
    out['Consecutive_Up'] = up
    out['Consecutive_Down'] = down
    return out


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
        backtest_config: BacktestConfig = None,
        indicator_config: IndicatorConfig = None,
        walk_forward_config: WalkForwardConfig = None,
        train_months: int = None,
        test_months: int = None,
    ):
        self.risk = risk_config or RiskConfig()
        self.exit = exit_config or ExitConfig()
        self.signal = signal_config or SignalConfig()
        self.strat = strat_config or StratConfig()
        self.bt_config = backtest_config or BacktestConfig()
        self.ind_config = indicator_config or IndicatorConfig()
        self.wf_config = walk_forward_config or WalkForwardConfig()

        # train_months / test_months: explicit args override config defaults
        self.train_months = train_months if train_months is not None else self.wf_config.default_train_months
        self.test_months = test_months if test_months is not None else self.wf_config.default_test_months

    def run(
        self,
        df: pd.DataFrame,
        use_strat: bool = False,
        close_col: str = 'Close',
    ) -> WalkForwardResult:
        """Run walk-forward validation over the full dataset.

        Folds:
        - Fold 1: Train [0, train_months) -> Test [train_months, train_months+test_months)
        - Fold 2: Train [0, train_months+test_months) -> Test [train+test, train+2*test)
        - ... until data runs out
        """
        return self._run_anchored_folds(
            df, signal_config=self.signal, use_strat=use_strat, close_col=close_col,
        )

    def run_profile(
        self,
        df: pd.DataFrame,
        profile: StyleProfile,
        close_col: str = 'Close',
    ) -> WalkForwardResult:
        """Walk-forward validate a mined `StyleProfile` (Task 4.3).

        Converts `profile` into a `SignalConfig` override via the
        module-level `profile_to_signal_config` (also unit-tested standalone
        in `tests/test_style_walk_forward.py` — see its docstring for
        exactly how vocabulary conditions become `min_conditions` / range /
        threshold tunables, and why that mapping is a documented
        approximation rather than a literal per-condition filter) and then
        runs the IDENTICAL anchored fold loop `run()` uses — same
        train/test slicing, same `_aggregate_metrics` / `_calculate_stability`
        — via the shared `_run_anchored_folds` helper. The only difference
        from `run()` is which `SignalConfig` each fold's `BacktestEngine` is
        built from; `risk`/`exit`/`strat`/`backtest`/`indicator` configs
        still come from `self.*` (set at validator construction), and
        `use_strat` is always False — a mined profile is about ENTRY
        conditions only, not the Strat FTFC/ORB overlay.
        """
        signal_config = profile_to_signal_config(profile)
        return self._run_anchored_folds(
            df, signal_config=signal_config, use_strat=False, close_col=close_col,
        )

    def _run_anchored_folds(
        self,
        df: pd.DataFrame,
        signal_config: SignalConfig,
        use_strat: bool,
        close_col: str,
    ) -> WalkForwardResult:
        """Shared anchored walk-forward fold loop for `run()` and
        `run_profile()` (Task 4.3) — extracted so the two callers can never
        drift on fold construction / train-test slicing. The only per-call
        variable is which `SignalConfig` each fold's `BacktestEngine` is
        built from; every other engine config (`risk`/`exit`/`strat`/
        `backtest`/`indicator`) always comes from `self.*`.
        """
        if 'Time' in df.columns:
            dates = pd.to_datetime(df['Time'])
        else:
            dates = pd.to_datetime(df.index)

        start_date = dates.min()
        end_date = dates.max()

        fold_results = []
        fold_dates = []

        min_test_bars = self.wf_config.min_test_bars

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

            if len(test_df) < min_test_bars:  # Need minimum data for meaningful test
                train_end = test_end
                continue

            # Run backtest on test period only
            engine = BacktestEngine(
                risk_config=self.risk,
                exit_config=self.exit,
                signal_config=signal_config,
                strat_config=self.strat,
                backtest_config=self.bt_config,
                indicator_config=self.ind_config,
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
                backtest_config=self.bt_config,
                indicator_config=self.ind_config,
            )
            result = engine.run(df, use_strat=use_strat, close_col=close_col)
            metrics = result.metrics()
            metrics.update(params)
            results.append(metrics)

        return pd.DataFrame(results)

    def walk_forward_sweep(
        self,
        df: pd.DataFrame,
        param_grid: Dict[str, List],
        use_strat: bool = True,
        close_col: str = 'Close',
    ) -> pd.DataFrame:
        """Walk-forward validate every parameter combination in `param_grid`.

        Unlike `parameter_sensitivity` (one full-period backtest per
        combo), this runs the full anchored walk-forward per combo, so
        each row carries out-of-sample aggregate metrics and a
        `stability_score` across folds — the inputs the calibration
        sweep ranks on.

        `param_grid` keys are the same as `parameter_sensitivity`:
        consecutive_periods, call_rsi_low/high, put_rsi_low/high,
        call_target, put_target, call_time_stop, put_time_stop.

        Returns one row per combo: the param values plus
        avg_expectancy_pct, avg_win_rate, std_expectancy_pct,
        stability_score, total_folds, total_trades.
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combos = list(product(*values))

        # When consecutive_periods is swept, process combos grouped by
        # its value so the Consecutive_Up/Down indicator columns are
        # rebuilt once per distinct value rather than per combo (the
        # column window must track the threshold — see
        # _rebuild_consecutive).
        cp_idx = (keys.index('consecutive_periods')
                  if 'consecutive_periods' in keys else None)
        if cp_idx is not None:
            combos.sort(key=lambda c: c[cp_idx])

        rows = []
        total = len(combos)
        _active_cp = None
        df_active = df
        for i, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            print(f"  WF sweep combo {i + 1}/{total}: {params}")

            cp = params.get('consecutive_periods')
            if cp is not None and cp != _active_cp:
                _active_cp = cp
                df_active = _rebuild_consecutive(df, int(cp), close_col)

            # Same param→config mapping as parameter_sensitivity, so the
            # two sweep entry points can't drift on how a combo is built.
            sig = SignalConfig(
                consecutive_periods=params.get(
                    'consecutive_periods', self.signal.consecutive_periods),
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

            validator = WalkForwardValidator(
                risk_config=self.risk,
                exit_config=exit_,
                signal_config=sig,
                strat_config=self.strat,
                backtest_config=self.bt_config,
                indicator_config=self.ind_config,
                walk_forward_config=self.wf_config,
                train_months=self.train_months,
                test_months=self.test_months,
            )
            wf = validator.run(df_active, use_strat=use_strat, close_col=close_col)
            agg = wf.aggregate_metrics

            row = dict(params)
            row['stability_score'] = wf.stability_score
            row['avg_expectancy_pct'] = agg.get('avg_expectancy_pct', 0.0)
            row['avg_win_rate'] = agg.get('avg_win_rate', 0.0)
            row['std_expectancy_pct'] = agg.get('std_expectancy_pct', 0.0)
            row['total_folds'] = int(agg.get('total_folds', 0))
            row['total_trades'] = int(agg.get('total_trades_all_folds', 0))
            rows.append(row)

        return pd.DataFrame(rows)

    def _aggregate_metrics(self, fold_results: List[BacktestResult]) -> Dict[str, float]:
        """Average metrics across all folds."""
        if not fold_results:
            return {}

        all_metrics = [r.metrics() for r in fold_results]
        keys = set()
        for m in all_metrics:
            keys.update(m.keys())

        aggregate = {}
        for key in keys:
            values = [m[key] for m in all_metrics if key in m and isinstance(m.get(key), (int, float))]
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


def select_calibration_winner(
    sweep_df: pd.DataFrame,
    min_stability: float = 0.6,
    min_avg_expectancy: float = 0.0,
    min_total_trades: int = 40,
) -> Optional[dict]:
    """Pick the strategic winner from a `walk_forward_sweep()` result frame.

    The ETF calibration sweep auto-applies its winner, so the guardrails
    *are* the review: a combo is eligible only if it clears all three
    hard gates —

      * stability_score >= min_stability   (profitable in most folds)
      * avg_expectancy_pct > min_avg_expectancy  (positive out-of-sample)
      * total_trades >= min_total_trades   (enough sample to trust)

    Among the survivors the highest `avg_expectancy_pct` wins. Returns
    None when no combo clears the gates — the caller then leaves the
    ticker's existing params untouched rather than applying a weak or
    overfit combo.
    """
    if sweep_df is None or sweep_df.empty:
        return None
    gated = sweep_df[
        (sweep_df['stability_score'] >= min_stability)
        & (sweep_df['avg_expectancy_pct'] > min_avg_expectancy)
        & (sweep_df['total_trades'] >= min_total_trades)
    ]
    if gated.empty:
        return None
    return gated.loc[gated['avg_expectancy_pct'].idxmax()].to_dict()
