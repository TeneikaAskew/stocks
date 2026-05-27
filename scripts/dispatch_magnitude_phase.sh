#!/usr/bin/env bash
# Dispatch one magnitude_engine plan via Cloud Run Job task-parallel execution.
#
# The job spreads N cells across N parallel worker instances. Wall-clock
# is the slowest single cell (~30-60 min), not the sum.
#
# Usage:
#   ./scripts/dispatch_magnitude_phase.sh no_backfill     # 27 cells (phases 0+1+3) parallel
#   ./scripts/dispatch_magnitude_phase.sh phase0          # 9 cells of phase0 parallel
#   ./scripts/dispatch_magnitude_phase.sh phase1          # 9 cells of phase1
#   ./scripts/dispatch_magnitude_phase.sh phase3          # 9 cells of phase3
#   ./scripts/dispatch_magnitude_phase.sh phase2          # 9 cells of phase2  (needs backfill!)
#   ./scripts/dispatch_magnitude_phase.sh phase4          # 9 cells of phase4  (needs backfill!)
#   ./scripts/dispatch_magnitude_phase.sh audit           # leakage audit (IWM 15m), single task
#
# The job must already exist:  ./gcp/deploy.sh magnitude-engine
# (Run from repo root after the :research image is built.)

set -euo pipefail
REGION=us-east1
JOB=magnitude-engine

plan="${1:-no_backfill}"

case "$plan" in
  audit)
    echo "Dispatching leakage audit (IWM 15m, single task)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        --update-env-vars="MAG_PLAN=" \
        --args="-m,gcp.research.magnitude_engine.mag_leakage_audit,--ticker=IWM,--tf=15m" \
        --tasks=1 --parallelism=1 \
        --wait
    ;;
  no_backfill)
    echo "Dispatching plan=no_backfill (27 cells = 3 phases × 9, parallel)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        --update-env-vars="MAG_PLAN=no_backfill" \
        --tasks=27 --parallelism=27 \
        --async
    ;;
  phase0|phase1|phase2|phase3|phase4)
    echo "Dispatching plan=$plan (9 cells parallel)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        --update-env-vars="MAG_PLAN=$plan" \
        --tasks=9 --parallelism=9 \
        --async
    ;;
  *)
    echo "Unknown plan: $plan"
    echo "Valid: no_backfill | phase0 | phase1 | phase2 | phase3 | phase4 | audit"
    exit 1
    ;;
esac
