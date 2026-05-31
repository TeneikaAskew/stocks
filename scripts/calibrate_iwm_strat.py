#!/usr/bin/env python3
"""IWM Strat-config calibration orchestrator.

Runs IWM walk-forward under six different StratConfig variants, each
writing per-fold rows to ``backtest_walk_forward_folds`` under a distinct
run_id. Designed to dispatch as a Cloud Run Job with ``--tasks 6
--parallelism 6`` so all six variants run TRULY IN PARALLEL across six
separate Cloud Run task containers (each gets full memory + CPU), not as
subprocesses competing for one task's resources.

Operating modes (selected by CLI flag or env var):

  * **variant mode** (one variant, one task) — reads
    ``CLOUD_RUN_TASK_INDEX`` and ``CALIB_PARENT_RUN_ID``, picks
    ``VARIANTS[task_index]``, derives that variant's run_id via
    uuid5(parent, str(task_index)), and dispatches a single
    ``run_walk_forward.py`` subprocess. Exit code is the subprocess's
    exit code. This is what Cloud Run Job tasks execute.

  * **summarise mode** (one execute, after all tasks finish) — pass
    ``--summarise`` plus ``--parent-run-id`` to re-derive every
    variant's run_id, query ``backtest_walk_forward_folds``, and print
    the ranked comparison.

  * **local mode** — pass ``--local`` to run all six variants
    sequentially in the current process (for dev / no-Cloud-Run envs).
    Slower than parallel but no Cloud Run round-trip.

Why this exists
---------------
The 2026-05-24 walk-forward run (run_id=696f2cd8) revealed IWM-strat IS
Sharpe 0.94 → OOS 0.00. The follow-up diagnostic decomposition revealed
six structural hypotheses; each variant below tests one. The winner
gets shipped to ``STRAT_CONFIG_PER_TICKER`` in a follow-up PR after
this calibration run.

Dispatch
--------
    PARENT=$(uuidgen)

    # 1) Run the 6 variants in parallel as 6 tasks
    gcloud run jobs execute backtest-pipeline \\
      --region=us-east1 \\
      --tasks=6 --parallelism=6 \\
      --update-env-vars="CALIB_PARENT_RUN_ID=${PARENT}" \\
      --wait

    # 2) Print the ranked summary (single task, queries the DB)
    gcloud run jobs execute backtest-pipeline \\
      --region=us-east1 \\
      --update-env-vars="CALIB_PARENT_RUN_ID=${PARENT},CALIB_SUMMARISE=1" \\
      --wait

(For step 1 to work, the backtest-pipeline job must temporarily be
pinned to ``--command python,-m,scripts.calibrate_iwm_strat`` — re-pin
back to ``scripts.run_pipeline`` after the calibration completes.)
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('calibrate-iwm')

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Variant:
    """One IWM WF configuration to test."""
    label: str           # short tag, <=8 chars for schema VARCHAR(8) mode col
    description: str
    extra_flags: List[str]  # passed to run_walk_forward.py
    use_strat: bool


# Six variants, each isolating one knob suggested by the 2026-05-24
# diagnostic. ``label`` is also the persisted ``mode`` column value;
# schema constrains to VARCHAR(8). ORDER MATTERS: this is the
# task-index → variant mapping for the Cloud Run --tasks=6 dispatch.
VARIANTS: List[Variant] = [
    Variant(
        label='base',
        description='No Strat at all — baseline',
        extra_flags=[],
        use_strat=False,
    ),
    Variant(
        label='strat',
        description='Default Strat config — known-broken baseline',
        extra_flags=[],
        use_strat=True,
    ),
    Variant(
        label='s_noorb',
        description='Strat without the ORB filter (ORB=0 had best WR)',
        extra_flags=['--no-orb-filter'],
        use_strat=True,
    ),
    Variant(
        label='s_noftfc',
        description='Strat without the FTFC filter',
        extra_flags=['--no-ftfc-filter'],
        use_strat=True,
    ),
    Variant(
        label='s_tight',
        description='Strat with tight FTFC threshold=0.8 (strong-trend only)',
        extra_flags=['--ftfc-threshold', '0.8'],
        use_strat=True,
    ),
    Variant(
        label='s_call',
        description='Strat applied only to CALL direction',
        extra_flags=['--strat-directions', 'CALL'],
        use_strat=True,
    ),
]


def variant_run_id(parent: str, task_index: int) -> str:
    """Derive a stable per-variant UUID from the parent + task index.

    Using uuid5 with the parent UUID as namespace gives every task and
    the summary step the same deterministic mapping with no need to
    pass run_ids between processes — they all reconstruct the same
    six UUIDs from ``CALIB_PARENT_RUN_ID``.
    """
    return str(uuid.uuid5(uuid.UUID(parent), str(task_index)))


def run_variant(variant: Variant, ticker: str, run_id: str,
                python: Optional[str] = None) -> bool:
    """Dispatch one walk-forward subprocess for a single variant.

    Returns True on success (subprocess exit 0).
    """
    py = python or sys.executable
    cmd = [
        py, str(PROJECT_ROOT / 'scripts' / 'run_walk_forward.py'),
        '--ticker', ticker,
        '--run-id', run_id,
        '--mode-label', variant.label,
    ]
    if variant.use_strat:
        cmd.append('--use-strat')
    cmd.extend(variant.extra_flags)

    log.info('START variant=%s  run_id=%s  desc=%s',
             variant.label, run_id, variant.description)
    log.info('  cmd: %s', ' '.join(cmd))
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - t0
    ok = result.returncode == 0
    if ok:
        log.info('OK variant=%s (%.0fs)', variant.label, elapsed)
    else:
        log.error('FAILED variant=%s (%.0fs, exit %d)',
                  variant.label, elapsed, result.returncode)
    return ok


def summarise(ticker: str, parent_run_id: str) -> None:
    """Re-derive every variant's run_id from ``parent_run_id`` and
    print the ranked comparison from ``backtest_walk_forward_folds``."""
    # Deferred imports so --local mode without DB still loads.
    from gcp.database import get_engine
    from sqlalchemy import text

    run_ids = {v.label: variant_run_id(parent_run_id, i)
               for i, v in enumerate(VARIANTS)}
    in_clause = ','.join(f"'{rid}'" for rid in run_ids.values())
    sql = text(f"""
        SELECT mode AS variant, run_id,
               COUNT(*)             AS folds,
               AVG(sharpe)          AS mean_oos_sharpe,
               STDDEV(sharpe)       AS sd_oos_sharpe,
               MIN(sharpe)          AS min_oos,
               MAX(sharpe)          AS max_oos,
               SUM(CASE WHEN sharpe > 0 THEN 1 ELSE 0 END) AS pos_folds,
               AVG(stability_score) AS stability,
               AVG(win_rate)        AS mean_wr,
               AVG(profit_factor)   AS mean_pf,
               SUM(total_trades)    AS total_trades
        FROM backtest_walk_forward_folds
        WHERE run_id IN ({in_clause})
          AND ticker = '{ticker}'
        GROUP BY mode, run_id
        ORDER BY mean_oos_sharpe DESC NULLS LAST
    """)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()

    if not rows:
        log.error('No rows in backtest_walk_forward_folds for parent=%s — '
                  'did all 6 tasks fail?', parent_run_id)
        return

    print()
    print('=' * 110)
    print(f'IWM Strat-config calibration — parent run_id={parent_run_id}')
    print('=' * 110)
    print(f'{"variant":<10} {"folds":>6} {"mean_oos":>9} {"sd_oos":>7} '
          f'{"min":>7} {"max":>7} {"pos":>7} {"stab":>6} {"mean_wr":>8} '
          f'{"mean_pf":>8} {"trades":>8}')
    print('-' * 110)
    for r in rows:
        pos = f"{r['pos_folds']}/{r['folds']}"
        print(f"{r['variant']:<10} {r['folds']:>6d} "
              f"{(r['mean_oos_sharpe'] or 0):>9.3f} "
              f"{(r['sd_oos_sharpe'] or 0):>7.2f} "
              f"{(r['min_oos'] or 0):>7.2f} "
              f"{(r['max_oos'] or 0):>7.2f} "
              f"{pos:>7} "
              f"{(r['stability'] or 0):>6.2f} "
              f"{(r['mean_wr'] or 0):>8.3f} "
              f"{(r['mean_pf'] or 0):>8.2f} "
              f"{(r['total_trades'] or 0):>8d}")
    print('=' * 110)
    print()
    print('Run IDs (for follow-up queries):')
    for label, rid in run_ids.items():
        print(f'  {label:<10} {rid}')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Multi-variant IWM Strat WF calibration')
    parser.add_argument('--ticker', default='IWM',
                        help='Ticker to calibrate (default: IWM)')
    parser.add_argument('--parent-run-id', type=str, default=None,
                        help='Parent UUID — every variant run_id is '
                             'derived as uuid5(parent, str(task_idx)). '
                             'Defaults to env CALIB_PARENT_RUN_ID.')
    parser.add_argument('--task-index', type=int, default=None,
                        help='Which variant (0..5) to run. Defaults to '
                             'env CLOUD_RUN_TASK_INDEX so a parallel '
                             '--tasks=6 dispatch maps each task to one '
                             'variant automatically.')
    parser.add_argument('--summarise', action='store_true',
                        help='Skip the WF run; query the DB for all 6 '
                             'variants and print the ranked comparison. '
                             'Defaults to env CALIB_SUMMARISE.')
    parser.add_argument('--local', action='store_true',
                        help='Run all 6 variants sequentially in this '
                             'process (for dev / no-Cloud-Run envs).')
    args = parser.parse_args()

    parent = (args.parent_run_id
              or os.environ.get('CALIB_PARENT_RUN_ID'))
    summarise_flag = args.summarise or bool(
        os.environ.get('CALIB_SUMMARISE'))

    if summarise_flag:
        if not parent:
            log.error('--summarise requires --parent-run-id (or '
                      'CALIB_PARENT_RUN_ID env)')
            return 2
        summarise(args.ticker, parent)
        return 0

    if args.local:
        if not parent:
            parent = str(uuid.uuid4())
            log.info('--local: generated parent_run_id=%s', parent)
        failed = []
        t0 = time.time()
        for i, v in enumerate(VARIANTS):
            rid = variant_run_id(parent, i)
            if not run_variant(v, args.ticker, rid):
                failed.append(v.label)
        log.info('All %d variants finished (%.0fs)',
                 len(VARIANTS), time.time() - t0)
        try:
            summarise(args.ticker, parent)
        except Exception as e:
            log.error('Summary failed (data still in DB under parent=%s): %s',
                      parent, e)
        return 1 if failed else 0

    # ── Parallel task mode (default Cloud Run behaviour) ───────────────
    if not parent:
        log.error('CALIB_PARENT_RUN_ID env or --parent-run-id is required '
                  'for parallel-task mode')
        return 2
    task_index = args.task_index
    if task_index is None:
        env_idx = os.environ.get('CLOUD_RUN_TASK_INDEX')
        if env_idx is None:
            log.error('CLOUD_RUN_TASK_INDEX env or --task-index is required '
                      'for parallel-task mode (got neither)')
            return 2
        task_index = int(env_idx)

    if not (0 <= task_index < len(VARIANTS)):
        log.error('task_index=%d out of range [0, %d) — adjust --tasks N to '
                  'match len(VARIANTS)=%d',
                  task_index, len(VARIANTS), len(VARIANTS))
        return 2

    variant = VARIANTS[task_index]
    rid = variant_run_id(parent, task_index)
    log.info('Parallel task: task_index=%d variant=%s run_id=%s parent=%s',
             task_index, variant.label, rid, parent)
    ok = run_variant(variant, args.ticker, rid)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
