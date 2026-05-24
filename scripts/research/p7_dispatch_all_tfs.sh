#!/usr/bin/env bash
# Phase 7 — dispatch 5 parallel per-TF analysis Cloud Run Job executions.
#
# Each execution gets its own --tf arg, runs on its own 32GiB + 8 CPU
# container, and writes results to gs://{bucket}/research/p7-analysis/{tf}/.
# Maximum parallelism for credits-by-end-of-day mode.
#
# Usage:
#   bash scripts/research/p7_dispatch_all_tfs.sh
#
# Prereqs:
#   - Job p7-analyze-tf exists (run scripts/research/p7_create_analyze_job.sh first)
#   - strat_features_<tf> tables are populated (p7-build-multi-tf-features run first)

set -euo pipefail

REGION="us-east1"
PROJECT="adept-mountain-474619-d4"
JOB="p7-analyze-tf"

TFS=("1m" "5m" "15m" "30m" "60m")

echo "Dispatching p7-analyze-tf for each TF in parallel..."
for tf in "${TFS[@]}"; do
  echo "  Dispatching tf=$tf..."
  gcloud run jobs execute "$JOB" \
    --region="$REGION" --project="$PROJECT" \
    --args="-m,gcp.research.p7_analyze_tf,--tf=$tf" \
    --async 2>&1 | grep -E "executions" | head -1
done
echo ""
echo "All 5 dispatched. Monitor:"
echo "  gcloud run jobs executions list --job=$JOB --region=$REGION --project=$PROJECT"
echo ""
echo "Results will land at:"
for tf in "${TFS[@]}"; do
  echo "  gs://adept-mountain-474619-d4-trading-data/research/p7-analysis/$tf/"
done
