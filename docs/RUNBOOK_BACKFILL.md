# Runbook — Backfilling `market_data_daily` (and any other date-driven fetcher)

**Audience:** anyone running a one-shot backfill of a Cloud Run Job that
takes `--date=YYYY-MM-DD` as input.
**Last incident this prevents:** [docs/incidents/2026-04-14-market-data-daily-gap.md](incidents/2026-04-14-market-data-daily-gap.md)
plus a related freeze identified during the 2026-05-08 audit (Track A
G.P0.1) where a backfill ran via `gcloud run jobs update --args="--date=..."`
and left the `--date` flag latched — every subsequent scheduled execution
re-fetched the same stale date, producing 8 days of NULL-close placeholder
rows in `market_data_daily`.

---

## Golden rule

**Use `gcloud run jobs execute --args=...` for backfills.**
**Never use `gcloud run jobs update --args=...`.**

`execute --args` is **transient** — the args apply only to the single
execution. `update --args` is **sticky** — every subsequent scheduled
execution inherits the args until you clear them.

If you ever need to clear sticky args from a previous mistake:

```bash
gcloud run jobs update <job-name> --args="" \
  --region=us-east1 --project=adept-mountain-474619-d4
```

> **Why `--args=""` and not `--clear-args`:** Cloud Run Jobs' `gcloud run
> jobs update` does NOT expose a `--clear-args` flag (verified
> 2026-05-08 against gcloud 566.0.0). The supported clear flags are
> `--clear-env-vars`, `--clear-secrets`, `--clear-volumes`, and others
> — but for container args, you reset by passing the empty list via
> `--args=""`. The job's container then runs with no extra CLI args.

---

## Backfill recipe (single date)

```bash
JOB=fetch-market-data           # or fetch-alphavantage-intraday, etc.
REGION=us-east1
PROJECT=adept-mountain-474619-d4
DATE=2026-04-15                 # YYYY-MM-DD

gcloud run jobs execute "$JOB" \
  --region="$REGION" --project="$PROJECT" \
  --args="--tickers=ALL,--date=$DATE" --wait
```

The `--wait` flag makes the call block until the execution finishes and
returns its exit status, so you can chain multiple invocations.

> **Note on `--args` syntax:** when an arg value starts with `-` (like
> `--date=2026-04-15`), pass `--args="--key=value"` (with `=`). gcloud
> otherwise parses `--date=...` as a new gcloud flag. See CLAUDE.md §0
> rule 5.

---

## Backfill recipe (date range)

A short bash loop is fine for ranges under ~30 days. Each execution is
independent and idempotent (`ON CONFLICT DO UPDATE` in the upsert).

```bash
JOB=fetch-market-data
REGION=us-east1
PROJECT=adept-mountain-474619-d4

for d in $(seq 0 7); do
  DATE=$(date -u -d "2026-04-14 +${d} days" +%F)
  # Skip weekends — fetcher will produce 0 rows but still costs a Cloud Run minute
  DOW=$(date -u -d "$DATE" +%u)
  if [ "$DOW" -ge 6 ]; then continue; fi
  echo "Backfilling $DATE..."
  gcloud run jobs execute "$JOB" \
    --region="$REGION" --project="$PROJECT" \
    --args="--tickers=ALL,--date=$DATE" --wait
done
```

For ranges over ~30 days, prefer a backfill-mode flag in the fetcher
itself (one Cloud Run execution that loops over dates internally) rather
than N executions — N executions × cold-start = wasted runtime.

---

## Verification after backfill

Always verify before declaring a backfill done. The most reliable check
is a SQL aggregate against the table you just wrote into. For
`market_data_daily`:

```bash
gh workflow run db-query.yml \
  -f sql="SELECT ticker, MIN(date) AS first_dt, MAX(date) AS last_dt, COUNT(*) AS rows
          FROM market_data_daily
          WHERE ticker IN ('SPY','IWM','QQQ')
            AND date BETWEEN '<RANGE_START>' AND '<RANGE_END>'
          GROUP BY ticker ORDER BY ticker"
```

Expected: each ticker has `rows = trading-days-in-range` and no NULL
closes (`COUNT(*) FILTER (WHERE close IS NULL)` should be 0; this is
checked by the freshness watchdog).

---

## After any `update --args` mistake

If you discover that a prior `gcloud run jobs update --args="..."` left
the job with sticky args:

1. **Clear the args immediately** with `--args=""`. Do not wait for the
   next scheduled execution.

   ```bash
   gcloud run jobs update fetch-market-data --args="" \
     --region=us-east1 --project=adept-mountain-474619-d4
   ```

2. **Identify the affected window.** Read the job's execution history
   (`gcloud run jobs executions list --job=...`) and find the first
   execution that ran with the bad args. Every scheduled run from that
   point until the args were cleared is suspect.

3. **Backfill the affected window** using the recipe above (the
   transient `execute --args` form).

4. **Drop the placeholder rows** the freeze inserted. For
   `market_data_daily`, look for rows where `close IS NULL` — those are
   the symptom. (Once Track A's `chk_close_not_null` constraint lands in
   PR-A6, this step becomes "the constraint already prevented them".)

5. **Document the incident.** Add a one-pager to `docs/incidents/` so
   the next person searching for this pattern finds your write-up.

---

## Related guards

- **Fail-fast in the fetcher** ([PR-A2](audit/2026-05-08/track-A-E-implementation-plan.md#pr-a2-—-fail-fast-in-fetcher-gp02)):
  exits non-zero if `fetch_date < today − 1 trading day`, so a stale arg
  fails loudly the first run instead of silently writing 8 days of bad
  rows.
- **Freshness watchdog** ([PR-A3](audit/2026-05-08/track-A-E-implementation-plan.md#pr-a3-—-re-enable-freshness-watchdog-gp03)):
  separate workflow that diffs `MAX(date)` against today and files an
  issue if the gap exceeds 1 trading day.
- **NULL-close CHECK constraint** ([PR-A6](audit/2026-05-08/track-A-E-implementation-plan.md#pr-a6-schema-check-constraint-on-market_data_daily-gp115)):
  schema-level prevention of placeholder rows ever landing.

Each of these is independently necessary; relying on any one alone is
how the audit caught the same shape of failure twice.
