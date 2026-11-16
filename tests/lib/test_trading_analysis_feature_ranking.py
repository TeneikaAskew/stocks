"""FEAT-SIGNAL-001: the offline feature ranking ranks no future value and scores out of sample.

docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md

``exit_*`` values are read at the best future bar and ``realized_*``,
``return_*`` and ``best_*`` are outcomes, so none of them, nor
``duration_minutes`` (the bars to the peak), may be ranked as a predictor. The
printed model score is fitted on the chronologically first 80% of signals by
``entry_time`` and computed on the last 20%. The run summary calls the
best-of-20 share what it is.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from lib.trading_analysis import MarketAnalyzer

FORBIDDEN_PREFIXES = ('exit_', 'realized_', 'return_', 'best_')


def _signals(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    entry = pd.date_range('2026-03-02 09:35', periods=n, freq='37min')
    target = rng.normal(0.3, 0.2, n)
    df = pd.DataFrame({
        'entry_time': entry,
        'trade_type': np.where(rng.random(n) > 0.5, 'call', 'put'),
        'entry_price': rng.normal(500, 5, n),
        'entry_rsi': rng.uniform(20, 80, n),
        'entry_vwap': rng.normal(500, 5, n),
        'entry_atr': rng.uniform(0.2, 0.8, n),
        'entry_orb_5m_high': rng.normal(501, 5, n),
        'return_pct': target,
        # Copies of the target the old exclusion list let through.
        'exit_rsi': target.copy(),
        'exit_vwap': target * 2,
        'exit_obv': target * 3,
        'exit_price': target + 500,
        'realized_return_pct': target - 0.4,
        'return_5min': target * 0.5,
        'best_return': target,
        'best_window_minutes': rng.integers(5, 60, n).astype(float),
        'duration_minutes': rng.integers(1, 20, n).astype(float),
        'signal_strength': 5,
    })
    # Rows arrive shuffled: the split must sort by entry_time itself.
    return df.sample(frac=1.0, random_state=1).reset_index(drop=True)


def test_no_outcome_column_is_ranked_even_when_exit_rsi_copies_the_target(capsys):
    results = MarketAnalyzer().analyze_feature_importance(_signals(), top_n=50)
    ranked = set(results['feature'])
    assert ranked, 'the ranking still runs'
    assert not {f for f in ranked if f.startswith(FORBIDDEN_PREFIXES)}
    assert 'duration_minutes' not in ranked
    assert 'exit_rsi' not in capsys.readouterr().out


def test_model_score_is_out_of_sample_on_the_last_20_percent(monkeypatch, capsys):
    import sklearn.ensemble as ensemble

    real = ensemble.RandomForestRegressor
    seen = {}

    class Spy(real):
        def fit(self, X, y, *a, **k):
            seen['fit_y'] = np.asarray(y, dtype=float)
            return super().fit(X, y, *a, **k)

        def score(self, X, y, *a, **k):
            seen['score_y'] = np.asarray(y, dtype=float)
            seen['score'] = super().score(X, y, *a, **k)
            return seen['score']

    monkeypatch.setattr(ensemble, 'RandomForestRegressor', Spy)
    df = _signals()
    MarketAnalyzer().analyze_feature_importance(df, top_n=5)
    out = capsys.readouterr().out

    ordered = df.sort_values('entry_time')['return_pct'].to_numpy()
    n_train = int(len(df) * 0.8)
    np.testing.assert_array_equal(seen['fit_y'], ordered[:n_train])
    np.testing.assert_array_equal(seen['score_y'], ordered[n_train:])
    line = next(l for l in out.splitlines() if 'R²' in l)
    assert 'out-of-sample' in line.lower()
    assert 'last 20%' in line and 'entry_time' in line
    assert float(line.rsplit(':', 1)[1]) == pytest.approx(round(seen['score'], 4), abs=1e-4)


def test_run_summary_does_not_call_the_best_of_20_share_profitable(capsys):
    df = _signals(20)
    df['realized_return_pct'] = [0.1, -0.2, np.nan, 0.3] * 5
    MarketAnalyzer.print_signal_summary(df)
    out = capsys.readouterr().out
    assert 'profitable' not in out.lower()
    moved = int((df['return_pct'] > 0).sum())
    line = next(l for l in out.splitlines() if 'moved in favour within 20 bars' in l)
    assert f'{moved} ({moved / 20 * 100:.1f}%)' in line
    # The realized win share sits beside it: 10 of the 15 scoreable signals.
    assert re.search(r'realized win share \(next-open-20m-1c-v1\): 66\.7% of 15 scoreable', line)
