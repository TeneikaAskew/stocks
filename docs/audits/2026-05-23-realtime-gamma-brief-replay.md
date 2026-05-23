# Track 1 + Track 5 deploy verification — historical brief replay

**Created:** 2026-05-23
**Branch:** `claude/realtime-gamma-brief-rsACl`
**Plan:** [`docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md`](../plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md) Tracks 1 and 5.
**Deploys:** `gcp/premarket_brief.py`, `lib/agents/summarizers.py`,
`lib/agents/orchestrator.py`, `lib/agents/prompts.py`.

## Hypothesis

The Track 1 brief footer renders correctly across five historical
brief dates, exercising the EOD fallback path (the only path
reachable for pre-Track-0 dates, since the realtime fetcher started
writing rows on 2026-05-23). The Track 5 key-level suffix likewise
ships `Gamma Flip (EOD)` / `Gamma King Above (EOD)` / etc. into the
insight reports written for those dates.

Per CLAUDE.md Rule 3.5 verification happens against historical data
NOW — not "next session." Per Rule 3.6 the replay runs through the
production Cloud Run Job, not a throwaway harness.

## Dates picked

Two weekday-to-weekday, one Tuesday-after-Monday-holiday, two
long-weekend crossings (per plan §Track 1 Tests).

| # | Date | Day | Rationale | Expected `data_source` |
|---|---|---|---|---|
| 1 | `2026-05-22` | Fri | Weekday-to-weekday (reads Thu 5/21 EOD) | `eod_fallback` |
| 2 | `2026-05-19` | Tue | Weekday-to-weekday (reads Mon 5/18 EOD) | `eod_fallback` |
| 3 | `2026-02-18` | Tue | After Presidents Day Mon (reads Fri 2/13 EOD) — 3-day-weekend cross | `eod_fallback` (1 trading day behind) |
| 4 | `2026-04-20` | Mon | After Good Friday (reads Thu 4/17 EOD) — non-Monday holiday cross | `eod_fallback` (1 trading day behind) |
| 5 | `2026-01-20` | Tue | After MLK Day Mon (reads Fri 1/16 EOD) — 3-day-weekend cross | `eod_fallback` (1 trading day behind) |

All five are pre-Track-0 (pre-2026-05-23) so the realtime path returns
zero rows on every dispatch — the validation is specifically that the
EOD fallback path produces the brief gamma footer without crashing.
Track 0 realtime-path validation runs separately once the fetcher has
accumulated ≥1 trading day of data (see plan §Verification §1).

## Prerequisites

The brief Cloud Run Job must be running the code from this branch.
Steps:

```bash
# 1. Merge this PR to main.
# 2. Build a new image with the merged code:
./gcp/deploy.sh build
# 3. Update the premarket-brief job to the new image:
./gcp/deploy.sh deploy-premarket
```

Confirm the deployed image matches the merge SHA:

```bash
gcloud run jobs describe premarket-brief --region=us-east1 \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
```

The tag should end with the merged commit SHA (or `latest` pointing
to a fresh build).

## Replay procedure

For each date, dispatch the premarket-brief job with `BRIEF_AS_OF=`
set and Discord output suppressed so we don't spam the channel with
historical posts.

```bash
for d in 2026-05-22 2026-05-19 2026-02-18 2026-04-20 2026-01-20; do
  echo "=== Dispatching brief for $d ==="
  gcloud run jobs execute premarket-brief \
    --region=us-east1 \
    --update-env-vars="^|^BRIEF_AS_OF=$d|BRIEF_POST_TO_DISCORD=0" \
    --wait
done
```

`BRIEF_POST_TO_DISCORD=0` suppresses the Discord webhook call (see
`PR #500: rename BRIEF_NO_DISCORD to BRIEF_POST_TO_DISCORD`). The
brief still persists its outputs to Cloud SQL and to GCS, so the
replay is observable end-to-end without operator-visible noise.

## Verification

After all 5 dispatches finish, query the resulting `insight_reports`
rows for the gamma key-level shape via `db-query.yml`:

```bash
gh workflow run db-query.yml -f sql="
SELECT
  ticker,
  as_of_date,
  key_levels::text AS key_levels_text,
  insight_run_id,
  created_at
FROM insight_reports
WHERE as_of_date IN
  ('2026-05-22','2026-05-19','2026-02-18','2026-04-20','2026-01-20')
  AND ticker IN ('SPY','IWM','QQQ')
ORDER BY as_of_date, ticker
"
```

**Pass criteria:**

1. **Track 1 footer renders.** Every dispatch should emit a brief
   even on dates where pre-Track-1 code would have silenced the
   section. Check Cloud Run job logs for the line
   `[brief] gamma freshness footer:` (or the rendered embed text).
2. **Track 5 EOD suffix applied.** Every `key_levels` JSON in the
   5 dates' rows should contain keys like `"Gamma Flip (EOD)"`,
   `"Gamma King Above (EOD)"`, `"Gamma Gate Below (EOD)"`. The
   un-suffixed forms (`"Gamma Flip"`, etc.) should be absent
   because all 5 dates are pre-Track-0 → EOD-fallback path.
3. **No crashes.** The brief job should exit zero on all 5 dispatches.
   Cloud Run logs should have no stack traces from
   `_load_gamma_freshness` or `_build_gamma_footer`.
4. **3-day-weekend cross dates render too.** Dates 3, 4, 5 (the
   post-holiday crosses) historically silenced the gamma section
   when chains were >2 trading days behind. With the Track 1
   widening they should now serve as `eod_fallback` (1 trading day
   behind the holiday Friday close) — confirm the key_levels JSON
   on those dates is populated rather than empty.

## Recording results

Once dispatches complete, append a section below with the actual
findings. If any check fails, file an issue rather than re-running
the dispatch — the brief job's outputs are durable in
`insight_reports` so the failure is debuggable from SQL.

### Results

_To be populated post-deploy-and-dispatch._
