#!/bin/bash
# Full rerun of the ATR5 vs ATR14 experiment. Usage: run_all.sh <worktree of #1784> <work dir>
set -e
WT=$1; W=$2; D=$(cd $(dirname $0) && pwd); PY=/home/claude/venv/bin/python
R=$(dirname $D)
cd $WT; export PYTHONPATH=platform:.
[ -f $W/daily/daily_SPY.csv ] || $PY $D/prep_data.py $W/daily
for t in SPY QQQ IWM; do for b in atr_14 atr_5; do
  [ -f $W/calib/rows_${t}_$b.csv.gz ] || $PY $D/calibrate_basis.py $W/daily $W/calib $t $b 2025-03-03 2026-11-10 &
  [ -f $W/calib40/rows_${t}_$b.csv.gz ] || MIN_SAMPLE_BREAK=40 $PY $D/calibrate_basis.py $W/daily $W/calib40 $t $b 2025-03-03 2026-04-30 &
done; wait; done
$PY $D/make_params.py $W/calib $W/params > /dev/null
$PY $D/make_params.py $W/calib40 $W/params40 > /dev/null
# recent window, policy as seeded
for b in atr_14 atr_5; do START=2026-05-01 END=2026-11-10 $PY $D/run_basis.py $WT $W/params/$b ${b/_/} 08:30 $W/replay_recent; done
# holdout, policy as seeded (plans mostly absent: stops and targets lack 150 breaks)
for b in atr_14 atr_5; do START=2025-03-03 END=2026-04-30 $PY $D/run_basis.py $WT $W/params/$b ${b/_/} 08:30 $W/replay_holdout; done
# holdout, break-derived keys' minimum sample relaxed to 40 (deviation, both bases)
for b in atr_14 atr_5; do START=2025-03-03 END=2026-04-30 $PY $D/run_basis.py $WT $W/params40/$b ${b/_/} 08:30 $W/replay_holdout40; done
$PY $D/compare.py $W/replay_recent atr140830 $W/replay_recent atr50830 recent_2026-05-01_2026-11-10 $R
$PY $D/compare.py $W/replay_holdout atr140830 $W/replay_holdout atr50830 holdout_policy_2025-03-03_2026-04-30 $R
$PY $D/compare.py $W/replay_holdout40 atr140830 $W/replay_holdout40 atr50830 holdout_minsample40_2025-03-03_2026-04-30 $R
