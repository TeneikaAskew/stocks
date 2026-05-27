#!/usr/bin/env bash
# Dispatch one magnitude_engine phase via Cloud Run Job.
#
# Usage:
#   ./scripts/dispatch_magnitude_phase.sh phase0         # all 9 cells, async
#   ./scripts/dispatch_magnitude_phase.sh phase0 IWM 15m # one cell, sync (--wait)
#   ./scripts/dispatch_magnitude_phase.sh audit          # leakage audit on IWM 15m
#
# The job must already exist. Create with:
#   ./gcp/deploy.sh magnitude-engine
# (Run from the repo root after the :research image is built.)

set -euo pipefail

REGION=us-east1
PROJECT=adept-mountain-474619-d4

phase="${1:-phase0}"
ticker="${2:-}"
tf="${3:-}"

if [[ "$phase" == "audit" ]]; then
    args="-m,gcp.research.magnitude_engine.mag_leakage_audit,--ticker=${ticker:-IWM},--tf=${tf:-15m}"
    echo "Dispatching leakage audit: $args"
    gcloud run jobs execute magnitude-engine --region="$REGION" \
        --args="$args" --wait
    exit 0
fi

if [[ -n "$ticker" && -n "$tf" ]]; then
    args="-m,gcp.research.magnitude_engine.mag_walk_forward,--phase=${phase},--ticker=${ticker},--tf=${tf}"
    echo "Dispatching ONE cell: $args"
    gcloud run jobs execute magnitude-engine --region="$REGION" \
        --args="$args" --wait
else
    args="-m,gcp.research.magnitude_engine.mag_walk_forward,--phase=${phase},--all-cells"
    echo "Dispatching ALL 9 cells (async): $args"
    gcloud run jobs execute magnitude-engine --region="$REGION" \
        --args="$args" --async
fi
