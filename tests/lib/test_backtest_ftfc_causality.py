"""FEAT-STRAT-001 done_when 3: the default BacktestEngine FTFC helper is causal.

Each row must keep the scalar the helper returns for the observed prefix
ending at that row. ``_frozen_pre_repair_ftfc`` is a byte-for-byte copy of the
helper as it stood on main before the repair (3ab668a); it is the oracle for
the unchanged final-as-of arithmetic and proves the fixtures are sensitive.
"""
import numpy as np
import pandas as pd
import pytest

from lib.backtest import BacktestEngine
from lib.config import ExitConfig, RiskConfig, SignalConfig, StratConfig
from lib.data_loader import RESAMPLE_RULES
from lib.strat import StratClassifier


def _frozen_pre_repair_ftfc(strat_config, strat_classifier, df, close_col='Close'):
    timeframes = strat_config.timeframes
    weights = strat_config.ftfc_weights
    classifications = {}
    for tf in timeframes:
        rule = RESAMPLE_RULES.get(tf)
        if rule is None:
            continue
        agg_dict = {'Open': 'first', 'High': 'max', 'Low': 'min',
                    close_col: 'last', 'Volume': 'sum'}
        try:
            resampled = df.resample(rule).agg(agg_dict).dropna()
        except Exception:
            continue
        if len(resampled) < 2:
            continue
        labels = strat_classifier.classify_series(resampled)
        numeric = labels.map({'2U': 1.0, '2D': -1.0, '1': 0.0, '3': 0.0, 'X': 0.0}).fillna(0.0)
        numeric_shifted = numeric.shift(1)
        classifications[tf] = numeric_shifted.reindex(df.index).ffill().fillna(0.0)
    if not classifications:
        return pd.Series(0.0, index=df.index)
    total_weight = sum(weights.get(tf, 0.0) for tf in classifications)
    if total_weight == 0:
        return pd.Series(0.0, index=df.index)
    ftfc_score = pd.Series(0.0, index=df.index)
    for tf, numeric in classifications.items():
        w = weights.get(tf, 0.0)
        ftfc_score += numeric * w
    ftfc_score /= total_weight
    return ftfc_score


SESSIONS = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05',
            '2024-01-08', '2024-01-09', '2024-01-10', '2024-01-11']


def _minutes(sessions=SESSIONS, seed=7):
    rng = np.random.default_rng(seed)
    frames, base = [], 200.0
    for day in sessions:
        times = pd.date_range(f'{day} 09:30', periods=390, freq='1min')
        close = base * np.exp(np.cumsum(rng.normal(0, 0.0015, len(times))))
        high = close * (1 + np.abs(rng.normal(0, 0.001, len(times))))
        low = close * (1 - np.abs(rng.normal(0, 0.001, len(times))))
        open_ = np.roll(close, 1)
        open_[0] = base
        frames.append(pd.DataFrame({'Time': times, 'Open': open_, 'High': high, 'Low': low,
                                    'Close': close, 'Volume': 50_000.0}, index=times))
        base = close[-1]
    return pd.concat(frames)


@pytest.fixture(scope='module')
def engine():
    return BacktestEngine(risk_config=RiskConfig(), exit_config=ExitConfig(),
                          signal_config=SignalConfig(min_conditions=2),
                          strat_config=StratConfig())


@pytest.fixture(scope='module')
def frame():
    return _minutes()


CUTS = [5, 61, 389, 390, 391, 777, 1170, 1559, 1560, 1950, 2400, 3119, 3120]
# The spec's 34 exact legacy final-as-of controls: every CUTS clock, the first
# rows, and each remaining session's open, mid-session and close boundary.
FINAL_ASOF_CUTS = sorted(set(CUTS + [1, 2] + [
    s * 390 + off for s in range(8) for off in (1, 195, 389)]) - {0})


def test_default_helper_prefix_is_unchanged_by_appending_future(engine, frame):
    full = engine._compute_ftfc_series(frame)
    for k in CUTS:
        prefix = engine._compute_ftfc_series(frame.iloc[:k])
        pd.testing.assert_series_equal(prefix, full.iloc[:k], check_exact=True,
                                       check_freq=False)
    # Fixture sensitivity: the pre-repair helper changes earlier rows when the
    # second week is appended (1w joins the whole-frame denominator).
    old_full = _frozen_pre_repair_ftfc(engine.strat_config, engine.strat_classifier, frame)
    old_week1 = _frozen_pre_repair_ftfc(engine.strat_config, engine.strat_classifier,
                                        frame.iloc[:1560])
    assert not np.array_equal(old_full.iloc[:1560].to_numpy(), old_week1.to_numpy())


def test_multiple_clocks_and_sessions_ignore_future_ohlc(engine, frame):
    baseline = engine._compute_ftfc_series(frame)
    for clock in [61, 390, 1170, 1560, 2400]:
        perturbed = frame.copy()
        later = perturbed.index[clock:]
        tripled = perturbed.loc[later, 'Close'].to_numpy() * 3
        perturbed.loc[later, 'Open'] = tripled
        perturbed.loc[later, 'Close'] = tripled
        perturbed.loc[later, 'High'] = tripled * 1.5
        perturbed.loc[later, 'Low'] = tripled * 0.2
        # Also drop later sessions so membership and bins change: before the
        # second week, drop all of it (1w loses its second period).
        cut = pd.Timestamp('2024-01-08') if clock < 1560 else pd.Timestamp('2024-01-11')
        perturbed = perturbed.loc[(perturbed.index < cut) | (perturbed.index >= cut + pd.Timedelta(days=1))
                                  if clock >= 1560 else perturbed.index < cut]
        changed = engine._compute_ftfc_series(perturbed)
        pd.testing.assert_series_equal(changed.iloc[:clock], baseline.iloc[:clock],
                                       check_exact=True, check_freq=False)


def test_final_asof_matches_frozen_old_production_helper(engine, frame):
    full = engine._compute_ftfc_series(frame)
    nonzero = 0
    assert len(FINAL_ASOF_CUTS) == 34
    for k in FINAL_ASOF_CUTS:
        prefix = frame.iloc[:k]
        old = _frozen_pre_repair_ftfc(engine.strat_config, engine.strat_classifier, prefix)
        new = engine._compute_ftfc_series(prefix)
        assert new.iloc[-1] == old.iloc[-1]          # exact scalar arithmetic
        assert full.iloc[k - 1] == old.iloc[-1]
        nonzero += old.iloc[-1] != 0.0
    assert nonzero >= 3
    # Weights are untouched literals.
    assert StratConfig().ftfc_weights == {'5m': 0.05, '15m': 0.10, '1h': 0.15, '4h': 0.15,
                                          '12h': 0.15, '1d': 0.30, '1w': 0.10}


def test_default_engine_dispatch_and_trade_ledger_use_causal_helper(engine, frame, monkeypatch):
    import lib.backtest as backtest

    # Stub ONLY base signal generation: a CALL on the 09:50 bar of each
    # session (inside the default CALL window). FTFC lookup, filters, entry
    # and exit stay the actual engine.
    def signal(row, **_kwargs):
        stamp = pd.Timestamp(row['Time'])
        if stamp.hour == 9 and stamp.minute == 50:
            return {'direction': 'CALL', 'base_score': 3, 'strat_bonus': 0,
                    'total_score': 3, 'conditions_met': ['stub']}
        return None
    monkeypatch.setattr(backtest, 'evaluate_signal', signal)
    calls = []
    original = BacktestEngine._compute_ftfc_series
    def spy(self, df, close_col='Close'):
        calls.append(len(df))
        return original(self, df, close_col)
    monkeypatch.setattr(BacktestEngine, '_compute_ftfc_series', spy)

    week1 = frame.iloc[:1560]
    full_run = engine.run(frame, use_strat=True)
    week1_run = engine.run(week1, use_strat=True)
    assert calls == [len(frame), len(week1)]
    causal = original(engine, frame)
    full_week1 = [t for t in full_run.trades if t.entry_time < pd.Timestamp('2024-01-06')]
    assert full_week1, 'fixture must produce week-one trades'
    assert [(t.entry_time, t.ftfc_score) for t in full_week1] == \
        [(t.entry_time, t.ftfc_score) for t in week1_run.trades]
    for trade in full_run.trades:
        assert trade.ftfc_score == causal.loc[pd.Timestamp(trade.entry_time)]
    # The pre-repair helper would have recorded different week-one scores.
    old = _frozen_pre_repair_ftfc(engine.strat_config, engine.strat_classifier, frame)
    assert any(old.loc[pd.Timestamp(t.entry_time)] != t.ftfc_score for t in full_week1) or \
        all(t.ftfc_score == 0.0 for t in full_week1)
