# FEAT-STRAT-001 #1766 evidence harness (not for merge)

Read-only scripts that produce the calibrated-parameter evidence (done_when 4 and 5) and the pick
changes against #1753 (done_when 14) for stocks#1766 from production bars. Every database read goes
through `scripts/db_query_cr.sh` without `--commit`, so each run rolls back. Nothing writes to a table,
deploys or posts.

Run from the root of a stocks clone:

    git fetch origin "+refs/heads/replay/feat-strat-001-per-ticker-params:refs/remotes/origin/replay/feat-strat-001-per-ticker-params"
    git worktree add -B replay/feat-strat-001-per-ticker-params /tmp/strat-params/harness \
        origin/replay/feat-strat-001-per-ticker-params
    bash /tmp/strat-params/harness/strat-params/run_all.sh

Results are written to `strat-params/results/` and pushed back to this branch.
