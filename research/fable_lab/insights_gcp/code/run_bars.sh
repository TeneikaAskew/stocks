#!/bin/bash
# Sequentially dispatch the bar pulls (read only, no --commit) and download each results.json.
# Usage: run_bars.sh <scratch_dir>   (expects <scratch_dir>/bars/bars_0*.sql from gen_bars_sql.py; run from the repo root)
set -u
S=$1
for f in "$S"/bars/bars_0*.sql; do
  b=$(basename "$f" .sql)
  echo "=== $b $(date -u +%H:%M:%S) ==="
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "$(cat "$f")" --timeout 300 2>"$S/bars/$b.err" >"$S/bars/$b.summary.md"
  echo "exit=$?"
  grep -E "execution:|results at:|error" "$S/bars/$b.err"
  ex=$(grep -oE "db-query-[a-z0-9]{5}" "$S/bars/$b.err" | head -1)
  if [[ -n "$ex" ]]; then
    env -u CLOUDSDK_AUTH_ACCESS_TOKEN timeout 600 gcloud storage cp "gs://adept-mountain-474619-d4-trading-data/query-results/$ex/results.json" "$S/bars/$b.results.json" 2>&1 | tail -1
  fi
done
echo "=== all done $(date -u +%H:%M:%S) ==="
