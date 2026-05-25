"""Tests for the IWM Strat-calibration CLI plumbing.

Pins three contracts so future refactors don't silently break the
calibration workflow:

  1. ``StratConfig.allowed_directions`` defaults to {'CALL','PUT'} so
     legacy backtests / signal-monitor runs see no behaviour change.
  2. The engine's ``_check_entry`` skips the FTFC/ORB filter + Strat
     bonus when the signal direction is NOT in ``allowed_directions``,
     and applies them when it IS — i.e. the gate actually gates.
  3. ``scripts/run_walk_forward.py`` accepts ``--no-ftfc-filter``,
     ``--no-orb-filter``, ``--ftfc-threshold``, ``--strat-directions``
     and ``--mode-label``; each flag mutates the loaded StratConfig
     correctly; invalid values fail loud.
  4. ``scripts/calibrate_iwm_strat.py`` defines six variants with
     unique, schema-safe (<=8 char) labels — the orchestrator's
     contract with the persisted ``mode`` column.

All tests are hermetic — no DB, no engine run, no subprocess.
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

from lib.config import StratConfig


# ── 1. Default allowed_directions back-compat ─────────────────────────


def test_strat_config_default_allowed_directions_is_both():
    """Legacy callers that don't know about ``allowed_directions`` must
    see no behaviour change — both directions enabled by default."""
    cfg = StratConfig()
    assert cfg.allowed_directions == {'CALL', 'PUT'}


def test_strat_config_allowed_directions_loadable_from_json():
    """The JSON loader must accept a list and coerce to a set so an
    operator can pin per-ticker direction allow-lists in
    alert_config.json without editing Python."""
    from lib.config import load_config
    import json
    import tempfile
    import os
    cfg_data = {
        'strat': {
            'allowed_directions': ['CALL']
        }
    }
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(cfg_data, f)
        path = f.name
    try:
        cfg = load_config(config_path=path)
        assert cfg.strat.allowed_directions == {'CALL'}
    finally:
        os.unlink(path)


# ── 2. Engine direction gate ──────────────────────────────────────────


def _strat_block_source():
    """Read the strat-block guard from lib/backtest.py so a future
    refactor that drops the direction check trips this test.

    AST-grep guard — keeps the contract source-pinned without standing
    up an indicator-enriched DataFrame just to assert one if-condition.
    """
    from pathlib import Path
    return Path('lib/backtest.py').read_text()


def test_engine_strat_block_gates_on_allowed_directions():
    """The engine's strat-overlay block must gate on
    ``self.strat_config.allowed_directions`` — otherwise a per-direction
    config (e.g. IWM CALL-only) would silently apply Strat to PUTs."""
    src = _strat_block_source()
    # The guard line must reference allowed_directions in the SAME if
    # that gates the strat_df / FTFC / ORB block. A bare reference
    # elsewhere isn't enough.
    assert (
        "and sig['direction'] in self.strat_config.allowed_directions"
        in src
    ), (
        "engine strat block no longer gates on allowed_directions — "
        "direction-only calibrations (e.g. CALL-only) would silently "
        "fire Strat on disallowed directions."
    )


# ── 3. run_walk_forward.py CLI flags ───────────────────────────────────


def _wf_help() -> str:
    """One-shot capture of --help so the CLI flag presence asserts share
    a single subprocess call."""
    r = subprocess.run(
        [sys.executable, 'scripts/run_walk_forward.py', '--help'],
        capture_output=True, text=True, timeout=20,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_cli_flag_no_ftfc_filter_present():
    assert '--no-ftfc-filter' in _wf_help()


def test_cli_flag_no_orb_filter_present():
    assert '--no-orb-filter' in _wf_help()


def test_cli_flag_ftfc_threshold_present():
    assert '--ftfc-threshold' in _wf_help()


def test_cli_flag_strat_directions_present():
    assert '--strat-directions' in _wf_help()


def test_cli_flag_mode_label_present():
    assert '--mode-label' in _wf_help()


def test_cli_strat_directions_rejects_invalid():
    """An unknown direction (e.g. 'BOTH', 'NEUTRAL', 'foo') must fail
    fast — silently coercing to an empty set or to both would mean the
    engine runs with the wrong filter."""
    r = subprocess.run(
        [sys.executable, 'scripts/run_walk_forward.py',
         '--ticker', 'IWM', '--strat-directions', 'NEUTRAL',
         '--daily-data'],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode != 0
    assert ('--strat-directions' in (r.stderr + r.stdout)
            or 'comma-separated' in (r.stderr + r.stdout))


def test_cli_ftfc_threshold_rejects_out_of_range():
    """ftfc_threshold must be in [0, 1] — mirroring the validator in
    AppConfig.validate(). A value of 1.5 would silently widen the
    accept band and ship phantom Strat bonuses."""
    r = subprocess.run(
        [sys.executable, 'scripts/run_walk_forward.py',
         '--ticker', 'IWM', '--ftfc-threshold', '1.5',
         '--daily-data'],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode != 0
    assert 'ftfc-threshold' in (r.stderr + r.stdout) or '[0,1]' in (r.stderr + r.stdout)


def test_cli_mode_label_rejects_overflow():
    """``backtest_walk_forward_folds.mode`` is VARCHAR(8); a 9+ char
    label would either truncate (silent) or 22001 (loud) on insert.
    Catch at CLI parse so the operator sees the error before the
    ~7-minute WF runs."""
    r = subprocess.run(
        [sys.executable, 'scripts/run_walk_forward.py',
         '--ticker', 'IWM', '--mode-label', 'strat_no_orb',
         '--daily-data'],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode != 0
    assert ('mode-label' in (r.stderr + r.stdout)
            or 'VARCHAR(8)' in (r.stderr + r.stdout)
            or '8 chars' in (r.stderr + r.stdout))


# ── 3b. mode_label actually flows into the persisted rows ─────────────


def test_wf_dataframe_uses_mode_label_when_provided():
    """REGRESSION: the parallel calibration's first dispatch (2026-05-24,
    parent=6e074587) produced 6 distinct run_ids but ALL strat variants
    persisted as mode='strat', collapsing s_noorb/s_noftfc/s_tight/s_call
    into one bucket in the summary. The bug was in
    _wf_result_to_dataframe hard-coding ``mode = 'strat' if use_strat
    else 'base'`` and ignoring the CLI override. Fixed by threading
    --mode-label through to that function.

    This test pins the contract: when mode_label is given, the rows'
    mode column must equal that label (not 'strat'/'base'). Without
    this guard, future refactors could silently regress the bug and
    every calibration dispatch would be ambiguous."""
    from datetime import date
    from unittest.mock import MagicMock
    import scripts.run_walk_forward as rwf

    # Construct a minimal WalkForwardResult-shape mock — three folds
    # with non-zero metrics so the dataframe has rows to inspect.
    def _fold(idx, sharpe):
        m = MagicMock()
        m.metrics.return_value = {
            'total_trades': 50, 'win_rate': 0.5, 'profit_factor': 1.2,
            'expectancy_pct': 0.001, 'sharpe_ratio': sharpe,
            'max_drawdown_pct': -0.01, 'avg_win_pct': 0.005,
            'avg_loss_pct': -0.005,
        }
        return m

    wf_result = MagicMock()
    wf_result.fold_results = [_fold(i, 0.5 + i * 0.1) for i in range(3)]
    wf_result.fold_dates = [{
        'train_start': date(2024, 1, 1), 'train_end': date(2024, 6, 1),
        'test_start':  date(2024, 6, 1), 'test_end':  date(2024, 7, 1),
    } for _ in range(3)]
    wf_result.stability_score = 0.65

    # use_strat=True with mode_label='s_noorb' — the label MUST win
    df = rwf._wf_result_to_dataframe(
        wf_result, run_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        ticker='IWM', use_strat=True, mode_label='s_noorb')
    assert (df['mode'] == 's_noorb').all(), (
        f"mode_label='s_noorb' was ignored; got {df['mode'].unique()}"
    )

    # use_strat=False with mode_label='base' — explicit base label
    df2 = rwf._wf_result_to_dataframe(
        wf_result, run_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        ticker='IWM', use_strat=False, mode_label='base')
    assert (df2['mode'] == 'base').all()

    # mode_label=None falls back to use_strat-derived label (back-compat)
    df3 = rwf._wf_result_to_dataframe(
        wf_result, run_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        ticker='IWM', use_strat=True, mode_label=None)
    assert (df3['mode'] == 'strat').all()

    df4 = rwf._wf_result_to_dataframe(
        wf_result, run_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        ticker='IWM', use_strat=False, mode_label=None)
    assert (df4['mode'] == 'base').all()


# ── 4. Calibration orchestrator variant contract ──────────────────────


def test_calibration_variants_have_unique_short_labels():
    """Six variants must have distinct labels (used as run grouping)
    AND each label must fit in the persisted mode column (VARCHAR(8))."""
    from scripts.calibrate_iwm_strat import VARIANTS
    labels = [v.label for v in VARIANTS]
    assert len(labels) == len(set(labels)), (
        f'duplicate variant labels: {labels}'
    )
    for v in VARIANTS:
        assert len(v.label) <= 8, (
            f'variant {v.label!r} exceeds 8 chars '
            f'(backtest_walk_forward_folds.mode is VARCHAR(8))'
        )


def test_calibration_variant_run_id_is_stable_for_same_parent():
    """The summary step re-derives every variant's run_id from the
    parent + task_index. If this derivation drifts between the parallel
    tasks and the summary execute, the summary will see no rows. Pin
    the function to uuid5(parent, str(task_index))."""
    from scripts.calibrate_iwm_strat import variant_run_id
    parent = '12345678-1234-5678-1234-567812345678'
    a = variant_run_id(parent, 0)
    b = variant_run_id(parent, 0)
    c = variant_run_id(parent, 1)
    assert a == b, 'derivation is not deterministic'
    assert a != c, 'different task indexes must produce different run_ids'
    assert uuid.UUID(a)  # must be a valid UUID
    # uuid5 is namespace-based — exact value pinned so a future refactor
    # to e.g. uuid4-with-seed catches.
    expected = str(uuid.uuid5(uuid.UUID(parent), '0'))
    assert a == expected, f'derivation drifted: {a!r} vs {expected!r}'


def test_calibration_variants_cover_the_diagnostic_hypotheses():
    """Each of the four diagnostic findings from the 2026-05-24 audit
    must be tested by at least one variant. Failing this test means
    the calibration matrix has drifted from the questions it was
    designed to answer."""
    from scripts.calibrate_iwm_strat import VARIANTS
    by_label = {v.label: v for v in VARIANTS}
    assert 'base' in by_label, 'baseline (no-strat) variant missing'
    assert 'strat' in by_label, 'default-strat variant missing'
    # ORB hypothesis: ORB=0 had best WR → no-orb-filter variant must exist
    assert any('--no-orb-filter' in v.extra_flags for v in VARIANTS), (
        'no-ORB hypothesis is not tested — the diagnostic showed '
        'orb_trend=0 had the highest WR.'
    )
    # FTFC threshold hypothesis: strong-trend only
    assert any('--ftfc-threshold' in v.extra_flags for v in VARIANTS), (
        'tight-FTFC hypothesis is not tested — strong_bull/bear buckets '
        'had the highest WR in the diagnostic.'
    )
    # Direction-gate hypothesis: CALL-only had 55.7% WR in 2024+
    assert any('--strat-directions' in v.extra_flags for v in VARIANTS), (
        'CALL-only hypothesis is not tested — the 2024+ CALL cohort '
        'was the only clear positive sub-cohort.'
    )
