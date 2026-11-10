#!/usr/bin/env bash
# FEAT-STRAT-001 #1766 evidence (done_when 4, 5 and 14) from production bars.
# READ-ONLY: every database read goes through scripts/db_query_cr.sh WITHOUT
# --commit (each run rolls back); nothing writes to any table, nothing deploys,
# nothing posts. Outputs land in this folder's results/ and are pushed to this
# replay branch only (not for merge).
#
# Run from the root of a stocks clone, after:
#   git fetch origin "+refs/heads/replay/feat-strat-001-per-ticker-params:refs/remotes/origin/replay/feat-strat-001-per-ticker-params"
#   git worktree add -B replay/feat-strat-001-per-ticker-params /tmp/strat-params/harness \
#       origin/replay/feat-strat-001-per-ticker-params
#   bash /tmp/strat-params/harness/strat-params/run_all.sh
set -euo pipefail

H="$(cd "$(dirname "$0")" && pwd)"
R="$(git rev-parse --show-toplevel)"
W="${STRAT_PARAMS_WORK:-/tmp/strat-params}"
DAILY_GCS="gs://adept-mountain-474619-d4-trading-data/query-results/db-query-8k8gh/result_001.csv"
OUT="$H/results"
mkdir -p "$W" "$OUT"
log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$OUT/run.log"; }

# The branch measured: the #1766 re-cut by default (spec revision 2).
B="${STRAT_PARAMS_BRANCH:-feature/feat-strat-001-level-params-recut}"
log "1/7 worktrees: $B head and origin/main (#1753 as merged)"
git -C "$R" fetch -q origin "+refs/heads/$B:refs/remotes/origin/$B" "+refs/heads/main:refs/remotes/origin/main"
# An existing worktree (an earlier run) is moved to the fetched heads, so a
# rerun measures the current branch head and main. Minute bars already
# exported and checked are not read again (export_minutes.py skips them).
for wt in "branch:origin/$B" "main:origin/main"; do
    d="$W/${wt%%:*}"; ref="${wt#*:}"
    if [[ -d "$d" ]]; then git -C "$d" checkout -q --detach "$ref"; else git -C "$R" worktree add -q --detach "$d" "$ref"; fi
done
log "branch $(git -C "$W/branch" rev-parse --short HEAD), main $(git -C "$W/main" rev-parse --short HEAD)"

log "2/7 daily export (already in GCS from the #1753 replay)"
[[ -s "$W/daily.csv" ]] || gcloud storage cp -q "$DAILY_GCS" "$W/daily.csv"
log "daily rows: $(( $(wc -l < "$W/daily.csv") - 1 ))"

log "3/7 one-minute bars, read-only, chunked under the 50,000-row cap"
(cd "$W/main" && python3 "$H/export_minutes.py" "$W/export") 2>&1 | tee -a "$OUT/run.log"
cp "$W/export/counts.csv" "$OUT/minute_counts_by_month.txt"

log "4/7 history-mode calibration through the job's own run() (#1766 worktree)"
(cd "$W/branch" && PYTHONPATH=platform:. python3 "$H/calib.py" "$W/daily.csv" "$W/export/minutes" "$W/calib") \
    2>&1 | tee -a "$OUT/run.log"
cp "$W/calib/in_force_2026-11-06.json" "$OUT/"

log "5/7 done_when 4 evidence"
(cd "$W/branch" && PYTHONPATH=platform:. python3 "$H/evidence.py" "$W/daily.csv" "$W/export/minutes" "$W/calib") \
    > /dev/null 2>> "$OUT/run.log"
cp "$W/calib/evidence.md" "$W/calib/evidence.json" "$OUT/"
log "5b/7 spike threshold diagnostic (wick excess, regular session vs premarket)"
(cd "$W/branch" && PYTHONPATH=platform:. python3 "$H/spike_diag.py" "$W/daily.csv" "$W/export/minutes" "$OUT") \
    2>> "$OUT/run.log"

log "6/7 picks through the brief path, #1766 and #1753"
(cd "$W/branch" && PYTHONPATH=platform:. python3 "$H/picks.py" "$W/daily.csv" "$W/picks_branch.jsonl.gz" \
    "$W/calib/ticker_level_params.csv.gz") > "$W/picks_branch.log" 2>&1 & pb=$!
(cd "$W/main" && PYTHONPATH=platform:. python3 "$H/picks.py" "$W/daily.csv" "$W/picks_main.jsonl.gz") \
    > "$W/picks_main.log" 2>&1 & pm=$!
wait "$pb" && wait "$pm" || { tail -20 "$W/picks_branch.log" "$W/picks_main.log"; exit 1; }
grep -hv "days old" "$W/picks_branch.log" "$W/picks_main.log" | tee -a "$OUT/run.log"

log "7/7 done_when 14 comparison"
python3 -I "$H/diff.py" "$W/picks_main.jsonl.gz" "$W/picks_branch.jsonl.gz" "$OUT" > /dev/null
cp "$W/picks_main.jsonl.gz" "$W/picks_branch.jsonl.gz" "$W/calib/ticker_level_params.csv.gz" "$OUT/"
log "done; pushing results"
if [[ -n "${STRAT_PARAMS_NO_PUSH:-}" ]]; then log "STRAT_PARAMS_NO_PUSH set: not committing"; exit 0; fi
cd "$H"
git add results
git commit -q -m "replay: $B calibration evidence and pick changes from production bars ($(git -C "$W/branch" rev-parse --short HEAD))

Read-only (db_query_cr.sh without --commit). Not for merge."
git push -q -u origin replay/feat-strat-001-per-ticker-params
log "pushed $(git rev-parse --short HEAD)"
