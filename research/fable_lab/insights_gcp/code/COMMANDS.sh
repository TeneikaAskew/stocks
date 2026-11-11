#!/bin/bash
# Exact commands of the 2026-11-11 read-only Insights review (GCP+Stocks conversation). Every database read goes through
# scripts/db_query_cr.sh WITHOUT --commit (each statement runs in its own transaction and is rolled back). Exports stay in
# the scratch directory S; nothing from the database is committed. Run from the stocks repo root on this branch.
set -u
S=${1:-/tmp/insights_review}; C=research/fable_lab/insights_gcp/code; mkdir -p "$S/bars"
# The session exports CLOUDSDK_AUTH_ACCESS_TOKEN as a 14-character placeholder; the dispatcher's probe now sees
# CREDENTIALS_MISSING instead of ACCESS_TOKEN_TYPE_UNSUPPORTED and refuses, so strip the variable (CLAUDE.md, GCP credentials).
# sql/b1.sql is needs_gcp.sql Q01,Q05,Q07,Q12,Q13,Q15 with Q05's `||` rewritten as concat(): the dispatcher passes the SQL
# through gcloud --update-env-vars with the ^|^ delimiter, and a pipe inside the SQL breaks the flag ("Invalid flag value []").
for b in b0_probe b1 b2 b3a b3b b4_holiday b5_export; do
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "$(cat $C/sql/$b.sql)" --timeout 300 2>"$S/$b.err" >"$S/$b.summary.md"
  ex=$(grep -oE "db-query-[a-z0-9]{5}" "$S/$b.err" | head -1)
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp "gs://adept-mountain-474619-d4-trading-data/query-results/$ex/results.json" "$S/$b.results.json"
done
python3 -I $C/tocsv.py "$S/b1.results.json" "$S/out" Q01,Q05,Q07,Q12,Q13,Q15
python3 -I $C/tocsv.py "$S/b2.results.json" "$S/out" Q02,Q03,Q04,Q06
python3 -I $C/tocsv.py "$S/b3a.results.json" "$S/out" Q08,Q09,Q11
python3 -I $C/tocsv.py "$S/b3b.results.json" "$S/out" Q10,Q14
python3 -I $C/tocsv.py "$S/b4_holiday.results.json" "$S/out" brief_kinds,holiday_rows,brief_coverage,holiday_history
# 1-minute bars: 36 ticker-month statements, 4 dispatches, ~720k rows, then Eastern-time files via lib.eastern_time
python3 -I $C/gen_bars_sql.py "$S/bars" && bash $C/run_bars.sh "$S"
python3 -I $C/prep_bars.py "$S"
# scoring (seed 7, 2,000 day resamples, 90% ranges)
python3 -I $C/score_daily.py "$S"      # direction from the official daily open; brief vs insight (Q08)
python3 -I $C/score_bars.py "$S"       # 1-minute bars: direction from the 09:30 open, stored plan, both sides on the 08:20 premarket high/low
python3 -I $C/validate_sim.py "$S"     # simulator check against the local lane's E0 baseline
