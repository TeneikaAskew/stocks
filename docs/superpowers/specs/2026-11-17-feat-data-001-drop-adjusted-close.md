---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-001, REQ-DEPLOY-001]
issues: []
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [CHARTS-03, DASHBOARD-03, LIVE-04]
done_when:
  - "tests/gcp/test_drop_adjusted_close.py::test_the_schema_no_longer_creates_what_is_dropped passes: the CREATE TABLE of market_data_daily in gcp/schema.sql declares no adjusted_close column, gcp/schema.sql creates neither archive_yahoo_market_data_daily nor archive_yahoo_market_data_intraday, and no unit that gcp.apply_schema.split_statement_groups returns for gcp/schema.sql names adjusted_close, archive_yahoo_market_data_daily or archive_yahoo_market_data_intraday, so an apply of the file neither re-creates nor drops any of them (on main gcp/schema.sql:110-111 declares the column and :557 and :560 create the two archives)"
  - "tests/gcp/test_drop_adjusted_close.py::test_the_drop_files_name_only_their_targets passes: gcp/queries/drop_adjusted_close.sql is the file the approved r2 spec's Design 10 gives (lock_timeout set to 5s locally, then ALTER TABLE market_data_daily DROP COLUMN adjusted_close, and no other relation or column), gcp/queries/drop_yahoo_price_archives.sql is one DO block that sets lock_timeout to 5s locally and drops archive_yahoo_market_data_daily and archive_yahoo_market_data_intraday IF EXISTS and no other relation, and the case fails on a seeded file that also drops market_data_daily (on main neither file exists)"
  - "tests/gcp/test_no_adjusted_prices.py passes with no allowance for gcp/schema.sql: test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price finds no .sql line under gcp/ naming an adjusted close except the one ALTER TABLE line of gcp/queries/drop_adjusted_close.sql, and the scan's seeded cases count each of the two former schema lines as a violation in gcp/schema.sql (on main both are allowed there)"
  - "scripts/archive_yahoo_data.py does not exist on the PR head; tests/meta/test_production_writers.py passes with it gone from VARIABLE_TABLE_WRITERS and its seeded variable-table cases kept without importing it; and grep -rn -E 'archive_yahoo_market_data_(daily|intraday)' gcp lib scripts platform returns only lines of gcp/queries/drop_yahoo_price_archives.sql"
  - "The PR body lists every Cloud Run job whose code writes market_data_daily, each with its schedule read from gcp/deploy.sh and the file and line of the write (a grep of gcp/, lib/ and scripts/ for writes to market_data_daily, pasted); Close-out step 4 waits for one successful execution of each"
  - "make test passes on the PR head; the generated inventory blocks of docs/product/infrastructure/05-a-ARCHITECTURE.md and 05-c-DATA_DEPENDENCIES.md are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes; gcp/deploy.sh and platform/api are not in the PR's diff"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DATA-001, component) row for each of the three declared components that begins with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Drop `adjusted_close`: clear it, then drop it, once nothing reads or writes it (spec B)

## Approval

Approved 2026-11-17. The owner wrote "Overcome all blockers" on 2026-11-17, and this spec is the companion that the approved `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md` (r2) already names as required: its "Split and separate specs" item B, its Decision 15 and its Close-out steps 7 and 8. The merged `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md` (no-adjusted) names it too ("#1977's spec B removes `gcp/schema.sql:110-111` and the guard's two-line allowance together").

## Where this comes from

- **No-adjusted (#2047, merged 2026-11-17 as f5a9fd018)** removed every read and write of `adjusted_close` in code. Its guard, `tests/gcp/test_no_adjusted_prices.py`, still allows exactly two `.sql` lines, the column and its comment at `gcp/schema.sql:110-111` (`SQL_ALLOWANCE`, `:353-356`), "which the companion data spec removes together with this allowance" (`:340-342`). Its Order section: "#1977's steps 7 and 8 wait for this spec's Close-out step 2. Dropping the column first would break the two SELECTs of Design 5 and `DataLoader.load_daily`, which name it." Its Decision 4: code first, then deploy everywhere, then clear, then drop.
- **r2, Split item B (FEAT-DATA-001, schema)**: "after the companion spec is deployed and Close-out step 8 has run, remove `adjusted_close` from `gcp/schema.sql:111`, drop `archive_yahoo_market_data_intraday` and its script. It keeps the DEFAULT partition of `market_data_intraday` (Decision 14)." r2's Close-out step 7 clears the column and step 8 drops it with `gcp/queries/drop_adjusted_close.sql`, a file r2's implementation creates (r2 Design 10: "the same lock timeout, then `ALTER TABLE market_data_daily DROP COLUMN adjusted_close`").
- This spec owns the whole sequence: the schema text, how the migration path treats it, the order, and the production steps. Its Close-out steps 3 and 5 are the operations r2 lists as its Close-out steps 7 and 8; each runs once, and its record is posted on both implementation PRs.

## Problem

### 1. Two live columns, still written (read 2026-11-17, read only)

- `SELECT ... FROM information_schema.columns WHERE column_name ILIKE '%adj%'` (`db-query-pzfr8`): two columns, both `double precision`: `market_data_daily.adjusted_close` and `archive_yahoo_market_data_daily.adjusted_close`. The second exists because `gcp/schema.sql:557-558` creates that archive `LIKE market_data_daily INCLUDING ALL`.
- `market_data_daily`: 5,830,927 rows, 34,993 with a non-NULL `adjusted_close` (`db-query-pzfr8`; the count took 13,261 ms); 4,211,539,968 bytes with indexes (`db-query-l4c9f`). r2 counted 34,847 on 2026-11-16 (`db-query-bxrxg`), so the count grows every night.
- Who still writes it, by `data_source` (`db-query-l4c9f`):

| `data_source` | rows | first date | last date | last `updated_at` (UTC) |
|---|---|---|---|---|
| `av_daily_backfill` | 23,002 | 2025-04-29 | 2026-11-13 | 2026-11-17 08:30:59 |
| `alphavantage_daily` | 10,160 | 2016-05-02 | 2026-11-16 | 2026-11-17 08:19:40 |
| `alphavantage` | 1,686 | 2022-05-06 | 2026-04-07 | 2026-11-15 11:13:58 |
| `yahoo` | 145 | 2026-04-27 | 2026-11-16 | 2026-11-17 04:03:59 |

  The deployed images predate #2047 (the last `fetchers` deploy ran 2026-11-17 12:32Z to 12:48Z, before #2047 merged at 14:22Z; `docs/superpowers/spikes/2026-11-16-session-handoff.md`), so the nightly fetch, the earnings history chain's backfill and the `^VIX` fetch still write the column and `DataLoader._load_daily_from_sql` on those images still selects it.
- Nothing in the database depends on the column: no view uses it (`information_schema.view_column_usage`, 0 rows, `db-query-pzfr8`), no object depends on it (`pg_depend` joined to `pg_attribute` on the column, 0 rows, `db-query-l4c9f`), and no function body names it (`pg_proc.prosrc ILIKE '%adjusted_close%'`, 0 rows, same execution).
- The archives (`db-query-l4c9f`): `archive_yahoo_market_data_daily` 0 rows, `archive_yahoo_market_data_intraday` 51,471 rows (r2 Decision 11 truncates them, Close-out step 6), `archive_yahoo_etf_options_snapshots` 0, `archive_yahoo_earnings_options_snapshots` 0.
- No statement log exists to show readers: the database's extensions are `plpgsql` and `vector` only (`db-query-pzfr8`), so `pg_stat_statements` is not available. Readers are shown gone by the image each job runs (no-adjusted Close-out steps 1 and 2) and by the logs after the drop.

### 2. The migration path

- `apply-schema-migrations` runs `gcp/apply_schema.py`, which applies the whole of `gcp/schema.sql` idempotently on every `./gcp/deploy.sh apply-schema` (`gcp/apply_schema.py:1-17`), whatever change that apply was for; a revision guard refuses an older revision but not a statement (`:316-437`).
- `CREATE TABLE IF NOT EXISTS` does not alter an existing table, and `gcp/schema.sql` holds no `ADD COLUMN IF NOT EXISTS adjusted_close` (grep: the name appears only at `:110-111`). So the live column outlives any edit of the file, and removing the line changes nothing live; only a fresh environment stops getting the column.
- The file does create the two archive tables (`:557`, `:560`). Dropped by hand while the file still creates them, the next apply re-creates them empty.
- A `DROP COLUMN IF EXISTS` in the file is how a column was dropped once before (`earnings_reactions`, `gcp/schema.sql:904-912`). Placed there, this drop would run at the next apply by any lane, possibly before the readers are redeployed or the clear has shown no writer left.

### 3. `scripts/archive_yahoo_data.py`

The only writer of the four archive tables (`TABLES`, `:57-79`): it copies the rows whose `data_source` is NULL, `yfinance`, `yahoo` or `yahooquery` (`YAHOO_PREDICATE`, `:51-53`) into the archive with `INSERT INTO <archive> SELECT t.*` (`:126-135`) and, with `--delete`, deletes them from the source. In `market_data_daily` that predicate holds the live `^VIX` rows (`yahoo`, written nightly) and the 4,770,116 rows with a NULL `data_source` (r2 Problem 4, `db-query-bxrxg`), and its positional `SELECT t.*` would misalign once the source loses a column the archive keeps. It is run by hand only (`tests/meta/test_production_writers.py:2347-2353`); nothing schedules it.

## Non-goals

- The DEFAULT partition of `market_data_intraday` stays (r2 Decision 14).
- `archive_yahoo_etf_options_snapshots` and `archive_yahoo_earnings_options_snapshots` stay. Both are empty and hold no price; with the script retired nothing writes them. Dropping them is a separate clean-up.
- No row other than the cleared values changes. No `VACUUM FULL`: the dispatcher runs every statement in a transaction, where it cannot run (r2 Capacity), and a dropped column's bytes stay in the heap until each row is next rewritten.
- No API, job, scheduler or deploy change: `gcp/deploy.sh` and `platform/api` are not in the diff.
- The data dictionary (`docs/product/infrastructure/05-h-DATA_DICTIONARY.md:68` and `:1597` list the column for both tables) is not edited from the implementation branch, which may not edit `docs/product/` beyond its own records (product-delivery skill, Never); a `docs/` PR after Close-out step 7 updates it.

## Approaches considered

1. **Chosen: the schema stops creating what is dropped, and the live drops run from one-statement files the owner dispatches at Close-out, after the checks.** The implementation PR has no live effect when it merges or when any later apply runs, so the order is held by the Close-out steps alone: code deployed, then the clear, then the writer probe, then the drop.
2. **The drop in the migration path** (`ALTER TABLE market_data_daily DROP COLUMN IF EXISTS adjusted_close` in `gcp/schema.sql`, as `:904-912` did). One path converges a fresh and a live database, but it arms the drop for the next apply by any lane, which can come before the readers are redeployed (a reader on an old image would then fail) or before the clear has shown no writer left. Rejected for the populated column. For the two archives the same reasoning holds: `archive_yahoo_market_data_intraday` holds rows until r2's Close-out step 6.
3. **Remove only the schema line and leave the live column** (r2 Split B read narrowly). A fresh environment and production would then differ for good, and the guard keeps a `.sql` allowance with no reason left. Rejected.
4. **Drop only the archive daily table's column rather than the table.** The table is empty and its only writer is retired here; dropping the table leaves no adjusted column anywhere and no empty table that mirrors a source it no longer matches. Chosen: drop the table.

## Design

### 1. `gcp/schema.sql`

- The `adjusted_close` line and its comment go from `CREATE TABLE IF NOT EXISTS market_data_daily` (`:110-111`).
- The `CREATE TABLE IF NOT EXISTS archive_yahoo_market_data_daily` and `archive_yahoo_market_data_intraday` statements (`:557-561`) go, and the comment above them (`:547-555`) names only the two options archives and says the script was retired.
- No `DROP` statement is added. After this change no unit of the file names `adjusted_close` or either archive, so an apply neither re-creates nor drops them (done_when 1). That is the migration path's whole part: `gcp/apply_schema.py` and the `apply-schema-migrations` job are not changed, and no apply is needed for this spec.

### 2. The drop files (`gcp/queries/`)

- `drop_adjusted_close.sql`, exactly as r2 Design 10 gives it, one DO block so the dispatcher sends it as one statement: `DO $$ BEGIN PERFORM set_config('lock_timeout', '5s', true); ALTER TABLE market_data_daily DROP COLUMN adjusted_close; END $$;`. r2's implementation creates the same file with the same text; whichever merges second keeps it unchanged, and the guard's allowance for its `ALTER TABLE` line (r2 plan Task 13) is added by whichever merges first.
- `drop_yahoo_price_archives.sql`, one DO block: `PERFORM set_config('lock_timeout', '5s', true); DROP TABLE IF EXISTS archive_yahoo_market_data_daily, archive_yahoo_market_data_intraday;`. It names no adjusted close, so the guard needs no allowance for it.
- Both are sent with `./scripts/db_query_cr.sh -f`, dry run first: DDL is transactional, so the rolled-back dry run takes the lock, proves it can be granted within 5 s, and changes nothing.

### 3. The guard (`tests/gcp/test_no_adjusted_prices.py`)

`SQL_ALLOWANCE` loses `gcp/schema.sql` and its two lines; its only `.sql` allowance is the `ALTER TABLE` line of `gcp/queries/drop_adjusted_close.sql`. The comment at `:340-342` says so. The seeded case that put the two lines in `gcp/schema.sql` and expected 0 now expects 2.

### 4. The script

`scripts/archive_yahoo_data.py` is deleted. `tests/meta/test_production_writers.py` drops it from `VARIABLE_TABLE_WRITERS` (`:2365-2368`) and rewrites the case that imports it (`:2459-2463`) so the variable-table checks keep their seeded inputs without it; the explanatory comment at `:2345-2353` is reduced to what remains true. The generated inventory blocks that list the two archives (`docs/product/infrastructure/05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md`) are re-rendered in this PR. The hand-written docs that name the script, the archives or the column under `docs/product/` (`06-DATA-ARCHITECTURE.md`, and under `infrastructure/` the `05-b`, `05-h`, `05-i` and `05-j` pages and `manual/05-a` and `manual/05-c`; grep, 2026-11-17) wait for the Close-out docs PR, with one exception that cannot wait: the backticked script paths that the docs audit's dead-link check flags once the script is gone (`docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1052` and `05-j-GCP_IMPLEMENTATION_STATUS.md:508`, per the review of this spec running `docs_audit.check_dead_links` without the script; a feature branch may not edit those pages) are reworded in a prerequisite `docs/` PR that names the script as retired by this change and merges before the implementation PR is marked ready, so its no-new-finding item holds. That PR re-runs the dead-link check with the script removed and lists any other reference it flags. Dated records (specs, plans, `docs/changelog/`, `docs/BRIEFING_DECK.md`) stay as written.

### 5. Site traceability

The declared components read `market_data_daily` for display: `CHARTS-03` (crosshair bar), `DASHBOARD-03` (daily KPIs, prior-session OHLC) and `LIVE-04` (live history). Each note says, backend source and local tests only: `gcp/schema.sql` no longer declares `market_data_daily.adjusted_close` nor creates the two Yahoo price archives, `gcp/queries/drop_adjusted_close.sql` and `drop_yahoo_price_archives.sql` hold the Close-out drops, no response this component reads changes; tests `tests/gcp/test_drop_adjusted_close.py`, `tests/gcp/test_no_adjusted_prices.py`. Each extends the component's existing FEAT-DATA-001 note with "Earlier:".

### 6. Capacity (CLAUDE.md rule 0)

| Step | Volume | Velocity | Wall-clock | Bound |
|---|---|---|---|---|
| the clear | 34,993 values today, in a 5,830,927-row, 4,211,539,968-byte table (`db-query-pzfr8`, `-l4c9f`); about 8,092 if r2's Close-out deletes ran first (r2 Capacity), plus the nights between | one UPDATE, one dispatch | a sequential scan of the heap (no index on the column): the count over it took 13.3 s (`db-query-pzfr8`) and a full scan 29.8 s (r2, `db-query-bxrxg`); the rewrite of at most 34,993 rows not measured | `--timeout 300` |
| the writer probe | the same count | one SELECT a check | about 13 s each (`db-query-pzfr8`) | 120 s default timeout |
| the column drop | catalog only | one ALTER, one dispatch | the lock wait plus a catalog update; not measured | 5 s lock timeout |
| the archive drop | 0 and 51,471 rows (`db-query-l4c9f`), 5,920 kB for the second (05-a inventory) | one DROP TABLE, one dispatch | not measured | 5 s lock timeout |

- Cost: four to six `db-query` dispatches of about 5 to 15 s each on the existing job, under $0.01 in all (estimate, list prices not re-read). No new job, schedule or vendor call.
- Disk: about 6 MB freed by the archive drop; the column's values stay in the heap until each row is rewritten, so the drop frees nothing measurable.

## Close-out (after the merge, each step on the owner's yes)

None runs from the implementation PR and none is a `done_when` box. Each step is recorded as a comment on this spec's implementation PR, and steps 3 and 5 also on r2's implementation PR. Every command runs from a checkout of `main`, with `gcloud` prefixed `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`.

1. **Preconditions.**
   - No-adjusted Close-out steps 1 and 2 are done: every job and service on #2047's reader list runs an image built from a `main` at or after f5a9fd018, read with `gcloud run jobs describe <job> --region=us-east1` and `gcloud run services describe <service> --region=us-east1` (that list waits, in turn, for r2's implementation and spec C, as #2047's body says).
   - This spec's implementation is on `main`, so no later apply re-creates the archives.
2. **Baseline, read only**: `SELECT coalesce(data_source, 'NULL') AS data_source, count(*), max(updated_at) FROM market_data_daily WHERE adjusted_close IS NOT NULL GROUP BY 1 ORDER BY 2 DESC; SELECT table_name FROM information_schema.columns WHERE column_name = 'adjusted_close'; SELECT count(*) FROM archive_yahoo_market_data_daily; SELECT count(*) FROM archive_yahoo_market_data_intraday`.
3. **Clear** (r2's Close-out step 7): `./scripts/db_query_cr.sh --timeout 300 -q "UPDATE market_data_daily SET adjusted_close = NULL WHERE adjusted_close IS NOT NULL"`, first without and then with `--commit`. Check: `SELECT count(adjusted_close) FROM market_data_daily` returns 0. Run it outside the 23:00 ET weekday fetch window, so no nightly upsert waits on its row locks.
4. **Writer probe.** After one successful execution of each job the implementation PR body lists (done_when 5), read with `gcloud run jobs executions list --job=<job> --region=us-east1`, the same count still returns 0. A non-zero count means a writer left on an old image: its rows' `data_source` and `updated_at` name it; redeploy that job from `main` and repeat steps 3 and 4. The column is never dropped with a writer left.
5. **Drop the column** (r2's Close-out step 8): `./scripts/db_query_cr.sh -f gcp/queries/drop_adjusted_close.sql`, then the same with `--commit`. Check: `SELECT count(*) FROM information_schema.columns WHERE table_name = 'market_data_daily' AND column_name = 'adjusted_close'` returns 0.
6. **Drop the archives**, once r2's Close-out step 6 has truncated `archive_yahoo_market_data_intraday` (count 0), or with the owner's word that its rows go here, which is r2 Decision 11's outcome either way: `./scripts/db_query_cr.sh -f gcp/queries/drop_yahoo_price_archives.sql`, then with `--commit`. Check: `SELECT to_regclass('archive_yahoo_market_data_daily') IS NULL AND to_regclass('archive_yahoo_market_data_intraday') IS NULL` returns true, and `SELECT count(*) FROM information_schema.columns WHERE column_name ILIKE '%adj%'` returns 0.
7. **One day later, read only.** Every scheduled job's executions in the 24 hours after step 5 succeeded or failed for a reason other than the column (`gcloud run jobs executions list`), and `gcloud logging read 'textPayload:"adjusted_close"' --freshness=1d --project=adept-mountain-474619-d4` returns no line holding `does not exist`. A job that fails on the column is redeployed from `main`; the column is never re-added (it would come back empty and re-admit a writer). The weekly dump `cloud-sql-weekly-export` of the Sunday before step 3 holds the column and its values for 30 days.
8. **Records**: a `docs/` PR updates the hand-written docs Design 4 lists (`05-h-DATA_DICTIONARY.md:68` and `:1597` name the column for both tables) so none describes the column, the two archives or the script as present, and sets the plan's `status: done`.

## Risks

- **A reader on an old image fails after the drop.** No-adjusted's reader list (step 1) is what prevents it; step 7 finds one that was missed, and redeploying it from `main` is the fix.
- **A writer on an old image fails after the drop.** Step 4's probe finds it first, without breaking it.
- **The lock is not granted.** A long read holding `market_data_daily` makes the 5 s lock timeout fail the dispatch; it is run again later, and nothing changed.
- **The clear waits on row locks.** Run outside the nightly fetch (step 3).
- **A checkout older than this spec, applied to a fresh database, re-creates the column and the archives.** Harmless: no code reads or writes them.
- **r2's implementation and this one both write `gcp/queries/drop_adjusted_close.sql`.** Same text, pinned by both specs; the second to merge keeps it.

## What was not verified

- The wall-clock of the UPDATE's row rewrites, of the column drop and of the archive drop; the WAL the UPDATE writes.
- Whether any job outside #2047's reader list selects the column through a path the import walk cannot see (a subprocess, as `backtest-pipeline` does); step 7's log search is the check.
- The writer list of done_when 5 is to be produced from the code in the implementation PR; it was not built for this spec.
- List prices for the dispatches, not re-read.
