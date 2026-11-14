---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-CAP-003, REQ-PERF-002, REQ-OBS-001, REQ-FRESH-001, REQ-SECRET-001, REQ-DATA-001, REQ-TENANCY-001, REQ-DEPLOY-001]
issues: [1261, 1872]
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "tests/gcp/test_fetch_watched_tickers.py passes: the watched set is read through gcp.database.query_to_dataframe_strict with SELECT w.ticker, COUNT(*) OVER () AS eligible_total FROM watched_tickers w WHERE EXISTS (SELECT 1 FROM user_watchlists u WHERE u.ticker = w.ticker AND u.removed_at IS NULL) AND w.ticker <> ALL(:exclude) ORDER BY w.created_at LIMIT :limit, where exclude is fetch_market_data.TICKERS (the default list and the sector ETFs, excluded before the limit so a static ticker never consumes the ceiling) and limit is WATCHED_TICKERS_MAX, so the window count is the exact number of eligible tickers and overflow is eligible_total minus the rows returned; a failed read, or a WATCHED_TICKERS_MAX that is not an integer, makes zero Alpha Vantage calls, records a job_runs row with status error and exits non-zero; an empty result exits 0 with status success and zero Alpha Vantage calls; with WATCHED_TICKERS_MAX=50, two static tickers among the earliest rows and 60 eligible tickers, the first 50 eligible tickers in created_at order are processed and the note records overflow=10 (the mixed static and non-static regression test), and with 51 eligible tickers it records overflow=1; a per-ticker Alpha Vantage failure is counted in items_failed while the other tickers proceed; the exit code is non-zero and the recorded status is error exactly when the set read fails or every kept ticker failed (compared by count, since the failures are a dict of ticker to reason), and success otherwise"
  - "The same test file proves the per-ticker sequence with mocks only at the Alpha Vantage and Cloud SQL boundaries and the real decision functions in between: the job reads each kept ticker's stored coverage (bar_count, max_date and bootstrapped, true when any of its rows carries data_source av_watched_backfill) through gcp.database.query_to_dataframe_strict, decides with its own fetch_watched_tickers._pick_watched_outputsize (full when bar_count is 0; None when max_date is the session date; for a bootstrapped ticker the real fetch_market_data._pick_backfill_outputsize stale rule called with the count lifted to the 1,500-bar depth threshold, compact within 90 days and full beyond; for a ticker another writer already holds the real _pick_backfill_outputsize as the earnings chain applies it), stamps data_source av_watched_backfill only on a ticker that had no bars or is already bootstrapped and writes a ticker another writer holds with today's av_daily_backfill, then calls fetch_market_data._run_backfill(group, outputsize=..., data_source=...) once per non-empty (outputsize, data_source) group, so a current ticker costs zero daily-series calls, a bootstrapped ticker a few sessions behind costs one compact call, a ticker with no rows costs one full call stamped av_watched_backfill, a bootstrapped ticker with 300 bars and the session's max_date costs zero calls, the same ticker two sessions behind costs one compact call, and an existing orphan with 300 bars from another writer that is one session behind costs one full call written with av_daily_backfill so its rows keep a non-watched source; _run_backfill called without outputsize or data_source keeps today's behaviour for --backfill --tickers and the earnings chain; compute_and_upsert_daily_indicators runs for the session date only for the kept tickers whose session-date bar exists after the pulls (read through the strict reader), so a bootstrapped ticker whose daily fetch returned nothing gets no indicator call, no session-date row and a bars failure, with a regression test for exactly that case; lib.ticker_info.get_ticker_info is called with max_age_days=30 so an OVERVIEW call happens at most once per ticker per 30 days; fetch_market_data._run_backfill returns the number of rows it passed to upsert_dataframe (0 on its early exits, unchanged behaviour otherwise) and the job records the sum over its groups as rows_written; and gcp.database.record_job_run is called exactly once with job_name fetch-watched-tickers, items_total, items_processed, items_failed, rows_written and the schema's status values success or error"
  - "The job verifies every watched ticker itself and does not call fetch_market_data._verify_post_fetch_rows (which returns without checking when none of SPY, IWM or QQQ is in the list and counts rows, not tickers): after the indicator step it reads, through gcp.database.query_to_dataframe_strict, each kept ticker's session-date row with its close and atr_14 and its total bar count, and counts a ticker as failed when the row is missing or its close is null (no bars) or when atr_14 is null while the ticker holds at least 15 daily bars (indicators not written), reporting a ticker with fewer than 15 bars as too_short in the note rather than failed; it also reads, through the same strict reader, SELECT ticker, updated_at FROM ticker_info WHERE ticker = ANY(:kept) and counts a ticker as failed with reason ticker_info when its row is missing or updated_at is older than 30 days, since lib.ticker_info._upsert_to_cloud_sql swallows a failed write and get_ticker_info still returns the overview; the test writes the session's bars for four tickers, makes the indicator history read fail for one, the vendor return nothing for another and gcp.database.execute_sql raise for a third ticker's ticker_info upsert, and asserts items_failed=3 with the three names and their reasons in the note; a failed strict read fails the run"
  - "The job resolves the session before anything else: it runs only when lib.eastern_time.is_session(today in Eastern time) is true, and otherwise writes a job_runs row with status success and note non_session and exits 0 with zero vendor calls and zero writes; the test runs the job on Thursday 2026-11-26 (Thanksgiving) and on a Saturday and asserts no Alpha Vantage call, no upsert and no indicator row dated that day"
  - "fetch_market_data._backfill_targets under BACKFILL_ALL_HISTORY=true counts a ticker into the market_data_daily arm of its union only when it holds at least one real bar from another writer, through HAVING bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill'), so a ticker whose bars all carry av_watched_backfill stays out even when it also holds an indicator-only row (null close, null data_source), while a ticker with a bar from any other writer, a ticker with null-sourced bars and every earnings_history ticker stay in; tests/gcp/test_fetch_market_data_backfill_targets.py covers a watched-only ticker, a watched-only ticker plus an indicator-only row, a mixed-source ticker, a null-sourced ticker and an earnings_history ticker, and a regression in the same file runs the job's bars step over an existing orphan (300 bars from another writer, no earnings_history row, one session behind) and shows it is still a target afterwards because the job wrote that pull with av_daily_backfill, so the earnings chain's nightly refresh never grows with the watched set and never loses a ticker it already had"
  - "A source scan in tests/gcp/test_fetch_watched_tickers.py asserts gcp/fetchers/fetch_watched_tickers.py names user_watchlists only inside the EXISTS predicate of the one set query of item 1, selects only ticker from watched_tickers, and contains no watchlists (as a whole word), watchlist_history, owner_uid, owner_email, user_id or email identifier, so no per-user row can reach this job; tests/gcp/test_watchlist_readers_default_owner.py from lock stage A and tests/gcp/test_user_watchlist_isolation.py from the user-watchlist API spec stay green"
  - "gcp/deploy.sh gains deploy_fetch_watched_tickers (image, --memory 512Mi, --cpu 1, --max-retries 0 on both the create and the update branch, --task-timeout 2400, --command python,-m,gcp.fetchers.fetch_watched_tickers, the existing DB_SECRET_FLAG and ALPHA_VANTAGE_API_KEY secrets, and WATCHED_TICKERS_MAX=50 and AV_BACKFILL_SLEEP_SECS=1.0 through --set-env-vars; no read secret and no URL) and the scheduler watched-tickers-nightly on 45 23 * * 1-5 America/New_York targeting fetch-watched-tickers, and a dispatch arm watched-tickers that runs build_image once and then deploy_fetch_watched_tickers, deploy_fetch_market_data, deploy_fetch_earnings_history and deploy_freshness_watchdog, so the _backfill_targets exclusion of item 5 reaches the two existing jobs whose images run fetch_market_data._run_backfill (the nightly fetch-market-data job and fetch-earnings-history's post-fetch chain, gcp/fetchers/fetch_earnings_history.py:558) and the heartbeat check of item 8 reaches the freshness-watchdog job, whose image runs scripts/audit_data_freshness.py (gcp/deploy.sh, deploy_freshness_watchdog), in the same deploy; tests/gcp/test_deploy_reachability.py passes with the new scheduler resolving to the new job, the arm deploying exactly fetch-watched-tickers, fetch-market-data, fetch-earnings-history and freshness-watchdog, and the flag asserted on both branches, and the PR body carries the Volume, Velocity, Wall-clock and cost numbers of section Capacity"
  - "scripts/audit_data_freshness.py gains a heartbeat check for fetch-watched-tickers, run inside audit_all's calendar guard (from _session_dependent_late_checks, its session arithmetic through _calendar) so a calendar failure yields the explicit nyse_calendar row instead of an aborted audit: a finding when job_runs holds no status success row for that job dated within the last two sessions (lib.eastern_time), and an informational row when the latest row's note carries overflow or its items_failed is above zero; tests/audits/test_audit_freshness_job_observability.py covers an absent heartbeat, an overdue one, a healthy one and an overflow note, and tests/audits/test_audit_data_freshness.py covers the calendar-failure case with job_runs present and a recorded success"
  - "docs/product/03-SITE-TRACEABILITY.md gains or updates its FEAT-DATA-001 SHARED-07 row in the Implementation-source notes table, beginning source_identity_sha256=<the PR head's source identity>; describing the fetch-watched-tickers job, its heartbeat check in the freshness watchdog and their tests, with no other byte of the document changed, and docs/review-evidence/site-source-snapshot.json is produced from that head and verifies (scripts/maintenance/doc_source_snapshot.py verify exits 0 with status identity-matched)"
  - "The FEAT-DATA-001 catalog record and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: docs/superpowers/specs/2026-11-13-feat-data-001-watched-ticker-ingest.md
---

# Fetch daily bars and ticker info once per distinct watched ticker (v2)

## Authority and status

Version 2, written 2026-11-14, supersedes
`docs/superpowers/specs/2026-11-13-feat-data-001-watched-ticker-ingest.md` after the owner's
correction of 2026-11-13: "Solyra doesn't use Supabase, only GCP. Stocks either." The watched set is
now read from the stocks tables of
`docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-api.md` (`watched_tickers` and
`user_watchlists` in Cloud SQL) through the strict reader, not from a Supabase function with a shared
secret. Everything else is the approved text, plus the four plan-review corrections of #1878 folded
into the done_when (`_run_backfill` reports its row count, the terminal status compares counts,
`--max-retries 0` on both deploy branches, the heartbeat inside the calendar guard) and the schema's
status words `success` and `error` (`gcp/schema.sql`, `job_runs.status`) in place of ok and failed.
The owner approves this replacement by merging it; the superseded spec is marked so in the same
change. No code before that merge.

The approved text of version 1 began: Draft, written 2026-11-13 from the owner's choice of the same day, in their words: "A stocks job
also fetches daily bars and ticker info once per distinct watched ticker, reading the owner-free
watched_tickers set, so a ticker ten users watch is fetched once. That keeps 'per-user rows never
reach a job' true, but it is a new job with a schedule, a ticker ceiling and a cost, so it would be
its own stocks spec. The brief, insight and signal surfaces would still read only the default list."

This is the third spec of the watchlist split. The first two are the lock specs
`docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md` and
`...-watchlist-write-routes-410.md` (stocks, the default list locked to Discord and the CLI) and the
per-user list, now `docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-api.md` in
stocks (Cloud SQL, one shared `watched_tickers` row per ticker) with its solyra half
`docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-v3.md`. The
lock spec's decision 5 said "no job fetches data for a user's own tickers for now"; this spec is
that change. The draft merged through #1870 after two Codex review rounds; this revision folds in
the three findings of the second round (#1872) and carries `status: approved`, which the owner
records by merging it. No code before that merge.

## Problem

A ticker a web user adds to their own list gets no data unless an operator also adds it to the
default list in Discord (stocks #1261 was this complaint in its old form). After the split the
per-user list lives in the stocks tables `user_watchlists` and `watched_tickers`, which no brief,
insight or signal job reads, so without this spec a user's ticker
shows "no data yet" forever: no daily bars in `market_data_daily`, no indicators, no `ticker_info`
row, so Briefing, Charts and the ranked panel have nothing to show for it.

The owner's constraint is dedup: ten users watching one ticker must cost one fetch, not ten.
The `watched_tickers` table holds exactly one row per watched ticker with no owner on it; joined to
the active memberships it is the owner-free input, and stocks already stores every data table once
per ticker.

What exists to reuse, read at origin/main 61bbd17:

- `gcp/fetchers/fetch_market_data.py:971-1060` `_run_backfill(tickers)`: pulls each ticker's daily
  series from Alpha Vantage TIME_SERIES_DAILY_ADJUSTED, choosing `full` (about 20 years, cut to 10
  on write, `BACKFILL_LOOKBACK_DAYS`) for a ticker with no rows, `compact` for one that is behind,
  and nothing for one that is current (`_pick_backfill_outputsize`, `:869`); writes
  `data_source = 'av_daily_backfill'` through `upsert_dataframe`, idempotent on `(ticker, date)`;
  paces calls with `AV_BACKFILL_SLEEP_SECS` (default 13 s, `:784`). Two gaps for this job: called
  with an explicit list it pairs every ticker with `(0, None)` (`:990`), so the smart switch always
  answers `full`; and the switch itself answers `full` for any ticker under 1,500 bars whatever its
  `max_date` (`BACKFILL_DEPTH_THRESHOLD_BARS`, `:780`, the final `return 'full'` at `:903`), which
  for a ticker listed less than about six years ago is a full rewrite every night. Only its default
  targets carry stored coverage (`_backfill_targets`, `:787`, whose `mdd` subquery reads `COUNT(*)`
  and `MAX(date)` per ticker). Section Steps has the job plan its own pulls.
- `fetch_market_data.py:814-833` `_backfill_targets` under `BACKFILL_ALL_HISTORY=true`: unions every
  ticker in `market_data_daily` into its targets; `fetch-earnings-history` runs with that flag
  (`gcp/deploy.sh:2982`) and chains `_run_backfill()` with no explicit targets every night
  (`gcp/fetchers/fetch_earnings_history.py:559`). Section Leaving the set bounds it.
- `fetch_market_data.py:332` `compute_and_upsert_daily_indicators(ticker, fetch_date, level_params)`:
  reads the last 250 daily bars and upserts the day's indicators (ATR, SMA200, RSI and the rest).
- `fetch_market_data.py:1091-1136` `_verify_post_fetch_rows(fetch_date, tickers)`: confirms that at
  least one of SPY, IWM or QQQ has a row for the date, and returns without checking when none of
  them is in the list. It cannot verify watched tickers, so this job verifies per ticker itself.
- `scripts/audit_data_freshness.py`: the watchdog's only `job_runs` check is
  `_query_job_duration_regression` (`:1303`), and its daily-bar checks cover IWM, SPY and QQQ only, so
  a scheduler that stops firing this job would raise no alert today. Section Freshness adds one.
- `lib/eastern_time.py:501` `is_session(day)`: the NYSE session calendar (REQ-DATA-004), used to skip
  weekday holidays.
- `lib/ticker_info.py:306` `get_ticker_info(ticker, max_age_days=30)`: one row per ticker in
  `ticker_info` from Alpha Vantage OVERVIEW, refetched only when older than 30 days. Its Cloud SQL
  write, `_upsert_to_cloud_sql` (`:60-94`), catches every exception and logs a warning, and
  `get_ticker_info` still returns the overview from its local cache (`:357-373`), so a caller cannot
  tell a durable row from a failed write. Section Steps verifies the table instead.
- `gcp/database.py:1091` `record_job_run(...)`: the `job_runs` heartbeat the freshness watchdog reads.
- `gcp/deploy.sh:4101` `_schedule NAME CRON JOB` and the `deploy_fetch_*` pattern with
  `${DB_SECRET_FLAG}` for secrets (REQ-SECRET-001).

## Non-goals

- No change to which list the brief, the insight pipeline and the signal monitor read: `'default'`
  only, through their existing surface flags. This job touches none of their inputs.
- No minute bars, options, news, SEC filings, insider transactions or earnings for watched tickers.
  Daily bars with indicators and the `ticker_info` row are the whole scope.
- No per-user data in the job. Its one set query selects tickers only; it never reads who watches them.
- Two additive keywords on `_run_backfill`, `outputsize` and `data_source`, both defaulting to today's
  values, and one `HAVING` clause on the `market_data_daily` arm of `_backfill_targets`' all-history
  union (section Leaving the set). No change to `compute_and_upsert_daily_indicators`,
  `_pick_backfill_outputsize` or `get_ticker_info`; `_verify_post_fetch_rows` is not used by this job.
  The 10-year cap and the smart switch stay as they are for every other caller.
- No change to the default list's own nightly fetch (`fetch-market-data-daily`, 23:00 ET).
- No UI. What the web shows for a ticker before and after the first fetch is the solyra spec's.
- No feedback channel to the web beyond the data itself: `GET /api/me/watchlist` reads each row's
  latest daily bar from `market_data_daily` at request time, which is how the web learns a ticker has
  no data after a fetch.

## Approaches considered

1. Version 1's choice: a secret-protected, owner-free `watched-tickers` function in solyra's
   Supabase project. Ruled out by the owner on 2026-11-13 (GCP only).
2. A copy of the distinct set pushed into a stocks table by the web. Rejected: a second copy of the
   set, and the stocks tables already hold the set.
3. Chosen: the job reads the distinct active tickers from the stocks tables `watched_tickers` and
   `user_watchlists` through the strict reader, selecting the ticker column only, and feeds the
   existing fetch functions, once per ticker. Same database, same connector, no secret, no HTTP.

## Design

### Entry point and schedule

`gcp/fetchers/fetch_watched_tickers.py`, Cloud Run Job `fetch-watched-tickers`, scheduler
`watched-tickers-nightly` at `45 23 * * 1-5` America/New_York: after `fetch-market-data-daily`
(23:00 ET, settle deadline 23:30) has finished the default list, before the 04:00 ET premarket.
`--max-retries 0` (REQ-CAP-003; a failure is a heartbeat failure, not something a retry fixes).

Environment: `WATCHED_TICKERS_MAX` (default 50),
`AV_BACKFILL_SLEEP_SECS=1.0` (60 calls a minute, under the 150 RPM local allocation of
`lib/config.py:124`), plus the existing `ALPHA_VANTAGE_API_KEY` and Cloud SQL secrets.

### Steps

0. **Resolve the session.** `today` is the Eastern date (`lib.eastern_time.market_today()`). If
   `is_session(today)` is false (a weekend, or a weekday holiday the scheduler still fires on), the
   job writes a `job_runs` row with `status = 'success'` and `note = 'non_session'` and exits 0 with zero
   vendor calls and zero writes. Otherwise `fetch_date = today`; at 23:45 ET the session is complete.
   This is what keeps a holiday from producing an indicator-only row dated on a day with no bars.
1. **Read the set.** Through `query_to_dataframe_strict`:
   `SELECT w.ticker, COUNT(*) OVER () AS eligible_total FROM watched_tickers w WHERE EXISTS (SELECT 1 FROM user_watchlists u WHERE u.ticker = w.ticker AND u.removed_at IS NULL) AND w.ticker <> ALL(:exclude) ORDER BY w.created_at LIMIT :limit`
   with `exclude = fetch_market_data.TICKERS` and `limit = WATCHED_TICKERS_MAX`: the distinct tickers
   with at least one active membership that the default list does not already fetch, ordered by first
   watched, no owner column selected. The exclusion sits before the limit, so a static ticker among the
   earliest rows never consumes the ceiling, and the window count carries the exact number of eligible
   tickers, so `overflow = eligible_total - len(rows)` is exact however many were cut. A failed read is a failure: the job writes a `job_runs` row with `status = 'error'` and
   exits non-zero without calling Alpha Vantage (REQ-DATA-001: a failed read is never an empty
   universe). An empty result is a legitimate answer: `status = 'success'`, `items_total = 0`, exit 0.
2. **Dedup and record the overflow.** Upper-case, trim and de-duplicate the returned tickers (the
   query already excluded `fetch_market_data.TICKERS`, IWM, SPY, QQQ, SPX and the sector ETFs, which
   the default list fetches nightly; the job drops any that still appear, as a second guard). Record
   `overflow=<eligible_total - len(rows)>` in the run note when it is above zero; the log line is at
   ERROR so the operator sees that users are watching more than the ceiling. The freshness watchdog
   reads the note from `job_runs`.
3. **Daily bars.** The job plans, `_run_backfill` executes. Before any vendor call the job reads
   `SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date, bool_or(data_source = 'av_watched_backfill') AS bootstrapped FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker`
   through `query_to_dataframe_strict` (a ticker absent from the result has `(0, None, false)`) and
   decides per ticker with its own `_pick_watched_outputsize(bar_count, max_date, bootstrapped, today)`:
   `full` when `bar_count = 0` (new to stocks); `None` when `max_date` is the session date (current,
   zero calls, whatever the depth); for a `bootstrapped` ticker the existing stale rule, by calling
   the real `_pick_backfill_outputsize` with the count lifted to `BACKFILL_DEPTH_THRESHOLD_BARS`
   (1,500 bars): `compact` within 90 days, `full` beyond, never the nightly depth bootstrap the
   unchanged switch alone would answer for a young ticker (`:901-903`); for a ticker another writer
   already holds (an `earnings_history` name, or an orphan with bars and no `earnings_history` row),
   the real `_pick_backfill_outputsize` as the earnings chain applies it. The stamp follows ownership:
   `data_source = 'av_watched_backfill'` only when `bar_count = 0` or `bootstrapped`, so a ticker new
   to stocks is the job's from its first pull on; a ticker another writer already holds is written
   with today's `av_daily_backfill`, because `upsert_dataframe` overwrites `data_source` on conflict
   (`gcp/database.py:417-480`, `update_cols` defaults to every non-key column) and a full pull would
   otherwise re-stamp every existing row and drop the ticker out of the earnings chain's union
   (section Leaving the set) the moment a user watched it. The job then calls
   `_run_backfill(group, outputsize=..., data_source=...)` once per non-empty `(outputsize,
   data_source)` group, at most four calls. The two new keywords: `outputsize` makes
   every explicit ticker pull at that size instead of the `(0, None)` planning at `:990-991`, and
   `data_source` replaces the constant at `:1041`; both default to today's values, so
   `--backfill --tickers` and the earnings chain are unchanged. Rows are upserted on `(ticker, date)`,
   so a re-run converges (REQ-CAP-002).
4. **Indicators.** Only for the kept tickers whose session-date bar exists after step 3: the job
   reads `SELECT ticker FROM market_data_daily WHERE date = :fetch_date AND ticker = ANY(:kept) AND close IS NOT NULL`
   through `query_to_dataframe_strict` and calls `compute_and_upsert_daily_indicators(ticker, fetch_date,
   level_params=read_level_params_for_run(kept, fetch_date)[ticker])`, the same call the default list
   gets, for those only. The guard matters: the helper reads the last 250 bars up to `fetch_date` and
   upserts a row keyed `(ticker, fetch_date)` with the indicator columns (`:380-381`, `:544`), so for a
   ticker whose fetch returned nothing it would insert a session-date row with no close and no
   `data_source`, a fabricated partial bar that would also count as another writer's row in the
   all-history union (section Leaving the set). A ticker without its session bar skips this step and
   is a bars failure in step 6.
5. **Ticker info.** `get_ticker_info(ticker, max_age_days=30)`: an OVERVIEW call only when the row
   is missing or older than 30 days, so ten users watching one ticker cost one call a month.
6. **Verify, per ticker.** Not `_verify_post_fetch_rows` (it returns without checking when none of
   SPY, IWM or QQQ is in the list, and counts rows rather than tickers). The job reads, through
   `query_to_dataframe_strict`,
   `SELECT m.ticker, m.close, m.atr_14, c.bar_count FROM market_data_daily m JOIN (SELECT ticker, COUNT(*) AS bar_count FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker) c USING (ticker) WHERE m.date = :fetch_date AND m.ticker = ANY(:kept)`
   and judges each kept ticker: no row or a null `close` is a bars failure (`_run_backfill` only logs a
   vendor reply with no data, `:1033-1035`); a null `atr_14` with `bar_count >= 15` is an indicators
   failure (`compute_and_upsert_daily_indicators` returns on a failed history read with a warning,
   `:355-358`, so bar presence alone would miss it); `bar_count < 15` is reported as `too_short` in
   the note, not failed, because the indicator needs that many sessions. The job also reads
   `SELECT ticker, updated_at FROM ticker_info WHERE ticker = ANY(:kept)` the same way and counts a
   ticker failed with reason `ticker_info` when its row is missing or `updated_at` is older than 30
   days: `_upsert_to_cloud_sql` catches a failed write and logs a warning (`lib/ticker_info.py:93-94`)
   and `get_ticker_info` still returns the overview (`:357-373`), so only the table can say whether
   the row is durable. Each failure is counted in `items_failed` with the ticker and its reason in
   the note. A failed strict read fails the run.
7. **Record.** `record_job_run('fetch-watched-tickers', started_at, status, items_total=len(kept),
   items_processed, items_failed, rows_written, note)` once, at the end, whatever the outcome. Exit
   non-zero when the set read failed or when every ticker failed; otherwise exit 0 with
   `items_failed` recorded, so one delisted symbol does not open an issue every night while still
   being visible (REQ-OBS-001: run identity, counts, duration, error class, terminal status).

Per-ticker progress is logged as `ticker=%s step=%s processed=%d/%d` (CLAUDE.md Rule 0, observable
progress).

### Leaving the set

A ticker that drops out of the watched set is absent from the next night's `kept`: its bars,
indicators and `ticker_info` row stay, nothing refreshes them, and no other job picks it up. The
last clause is false today: `_backfill_targets` under `BACKFILL_ALL_HISTORY=true` unions every
ticker in `market_data_daily` (`fetch_market_data.py:814-833`), `fetch-earnings-history` runs with
that flag (`gcp/deploy.sh:2982`) and chains `_run_backfill()` with no explicit targets
(`fetch_earnings_history.py:559`), so every ticker this job ever wrote would join that nightly
refresh for good, one compact call a night once stale, outside this job's ceiling and growing with
watched churn. The `market_data_daily` arm of that union therefore becomes
`SELECT ticker FROM market_data_daily GROUP BY ticker HAVING bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill')`:
a ticker counts only when it holds at least one real bar (a close) from another writer. A ticker
whose bars all came from this job stays out, even when it also holds an indicator-only row (null
close, null `data_source`, which `compute_and_upsert_daily_indicators` writes when it runs without
the session's bar; step 4 guards against that too, and the clause holds if some other path writes
one); a ticker with a bar from any other writer, or with null-sourced bars (`data_source` is
nullable, which is why `IS DISTINCT FROM` and not `<>`), stays in; the `earnings_history` arm is
untouched. This is the one change outside the job's own module besides the two `_run_backfill`
keywords.

The clause only holds because the stamp follows ownership (Steps item 3). `upsert_dataframe`
overwrites `data_source` on conflict (`gcp/database.py:417-480`), so if the job stamped every pull
`av_watched_backfill`, a full pull over a ticker another writer already holds, the orphans
`tests/gcp/test_backfill_targets_orphans.py` keeps in the union included, would re-stamp all of its
rows and the clause would drop a ticker the chain had been refreshing; once unwatched, its data
would stop moving. The job therefore stamps only a ticker that had no bars before its first pull or
already carries the stamp, and writes any other ticker with today's `av_daily_backfill`, so a
ticker's eligibility for the earnings chain is exactly what it was before anyone watched it.

### Capacity (CLAUDE.md Rule 0, REQ-CAP-001 to 003)

Ceiling: 50 watched tickers beyond the default list per run.

- **Volume.** First run worst case: 50 tickers x about 2,520 daily rows (10 years) x about 200 bytes
  = about 25 MB written once. Steady state: at most 50 bar rows and 50 indicator upserts a day (about
  20 KB), plus at most 50 `ticker_info` rows per 30 days.
- **Velocity.** Per run: 1 set query, 1 coverage query and 2 verification queries (bars
  with indicators, `ticker_info`), each over the kept tickers at once. Per ticker: at most 1 Alpha
  Vantage daily-series call (0 when current), 1 bars upsert, 1 history query of 250 rows, 1
  indicator upsert, at most 1 OVERVIEW call per 30 days and 1 `ticker_info` upsert. Worst case about
  100 Alpha Vantage calls (first run) and about 200 Cloud SQL round trips. The job's own outputsize
  decision is what keeps a young ticker at zero calls on a current night; the unchanged switch would
  have cost a full pull per sub-1,500-bar ticker every night, which these numbers never counted.
- **Wall-clock.** Alpha Vantage at 1 call a second: about 50 s of bars plus 50 s of OVERVIEW on the
  first run. Cloud SQL through pg8000 and the connector at 0.5 to 2 s a round trip: about 200 round
  trips, 100 to 400 s. Worst case about 8 minutes on the first run; a steady night 2 to 4 minutes.
  `--task-timeout 2400` is at least 4x the worst case.
- **Cost.** Cloud Run at 1 vCPU and 512 MiB: 480 s x ($0.000024 per vCPU-second + 0.5 GiB x
  $0.0000025 per GiB-second) is about $0.012 a run worst case, about $0.005 on a steady night; x 1
  run a day x 22 trading days is under $0.30 a month, plus one Cloud Scheduler job ($0.10 a month
  beyond the free tier). Alpha Vantage calls are within the purchased 600 RPM plan and carry no
  per-call fee. Cloud SQL reads are free on the always-on instance.
- **Memory.** One ticker's 10-year frame at a time; the daily fetcher runs the same code in 512 MiB.

The runbook workload is this nightly run; nothing in it is left as future work (Rule 0.1).

### Freshness (REQ-FRESH-001)

Owner: the project owner. Cadence: nightly on weekdays. Measured age: `job_runs.finished_at` for
`fetch-watched-tickers` and `MAX(date)` per watched ticker in `market_data_daily`. Alert threshold:
no `status = 'success'` row for the job dated within the last two sessions. Today the watchdog
(`scripts/audit_data_freshness.py`) has no such check: its only `job_runs` reader is
`_query_job_duration_regression`, so a scheduler that silently stops would never be noticed. This
spec adds a heartbeat check beside it: a finding when the latest `success` row is older than two sessions
or absent, and an informational row when the latest note carries `overflow` or `items_failed` is
above zero, so one unserved symbol is visible without paging anyone nightly. Recovery:
`gcloud run jobs execute fetch-watched-tickers --region us-east1 --wait`; the run is idempotent.

### Tests

`tests/gcp/test_fetch_watched_tickers.py` with mocks at the Alpha Vantage and Cloud SQL
boundaries only, so `_pick_watched_outputsize` (and the real `_pick_backfill_outputsize` it calls for
the stale rule), the session check and the per-ticker verification run for real; one test per
done_when clause, plus the source scan, the holiday case, the three sub-threshold coverage cases and
the failed-fetch-after-bootstrap regression (no indicator call, no session-date row, one bars failure)
and the orphan-preservation regression (an existing orphan pulled by the job is still a target of the
all-history union afterwards).
`tests/gcp/test_deploy_reachability.py` already asserts every scheduler target is a job some `deploy_*`
function creates; the new pair is covered by it. The watchdog heartbeat check is covered in
`tests/audits/test_audit_freshness_job_observability.py`, and the all-history union's new `HAVING`
clause in `tests/gcp/test_fetch_market_data_backfill_targets.py`.

## Cross-repo contract

| Side | What | Who writes | Who reads |
|---|---|---|---|
| stocks Cloud SQL | `watched_tickers` (one row per ticker) and `user_watchlists` (membership), the tables of the user-watchlist API spec | `POST` and `DELETE /api/me/watchlist` | this job's one set query, nightly, selecting tickers only |
| stocks Cloud SQL | `market_data_daily` rows (`data_source = 'av_watched_backfill'`) and indicators, `ticker_info` rows, `job_runs` heartbeat | this job (and the default list's fetchers for their own tickers) | Briefing, Charts, the ranker and `GET /api/me/watchlist` (`last_daily_bar`, `name`, `exchange`, `asset_type`), as today |
| stocks Cloud SQL | `watchlists` | unchanged | unchanged; this job never reads it |

Ordering: the user-watchlist API spec's tables are on main first (its PR merged, its apply-schema
build green), then this job; the scheduler is created only after the manual execution of step 3 of section Post-merge close-out.

## Post-merge close-out (recorded on the PR after the merge, not acceptance items)

The job's production steps follow the merge in this order, each recorded as a PR comment by the
author; the owner's authorization of 2026-11-14 ("run gcp side") covers them:

1. Precondition: the user-watchlist API PR is merged and its `apply-schema-on-change` build is green,
   so `watched_tickers` and `user_watchlists` exist in production (that PR's own close-out comment
   shows the `information_schema` query).
2. `./gcp/deploy.sh watched-tickers` builds main once and from that image deploys `fetch-watched-tickers`
   (no scheduler) and redeploys `fetch-market-data` and `fetch-earnings-history`, the two existing jobs
   whose images run `fetch_market_data._run_backfill` and so must carry item 5's `_backfill_targets`
   exclusion before any watched ticker exists, and `freshness-watchdog`, whose image runs
   `scripts/audit_data_freshness.py` and so must carry item 8's heartbeat check before the scheduler
   exists; each of the four jobs' `gcloud run jobs describe <job> --region us-east1
   --format='value(spec.template.spec.template.spec.containers[0].image)'` names that build's image
   before step 3 (Codex on #1899 and #1901: a job left on its old pinned image would backfill
   watched-only tickers with `av_daily_backfill` on its next session, or audit without the heartbeat
   that reports a stopped scheduler).
3. One manual `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs execute fetch-watched-tickers
   --region us-east1 --wait` succeeds (an empty active set is a valid first run: status `success`,
   `items_total` 0); the comment pastes its `job_runs` row with the execution id.
4. Only then `./gcp/deploy.sh schedulers` creates `watched-tickers-nightly`.
5. After the first scheduled run, a read-only `scripts/db_query_cr.sh` run of `SELECT job_name,
   status, items_total, items_processed, items_failed, rows_written, note FROM job_runs WHERE
   job_name = 'fetch-watched-tickers' ORDER BY started_at DESC LIMIT 1` shows status `success`, and
   `SELECT ticker, MAX(date) FROM market_data_daily WHERE ticker = ANY(the watched set) GROUP BY
   ticker` shows that session's date for every processed ticker; both outputs are pasted with their
   execution ids.

Any other result stops for the owner. The gate ticks every done_when item before the PR is marked
ready, so none of these is an acceptance item (Codex on #1897); the hermetic tests of items 1 to 6
and 8 and the deploy-script test of item 7 are the pre-merge proof.

## Risks

- Alpha Vantage returns nothing for a symbol it does not serve. The ticker is counted as failed every
  night and never gets a row; the owner sees it in `job_runs.items_failed` and the web shows "no
  data for this symbol" through `GET /api/me/watchlist`'s `last_daily_bar`. A later change could tell solyra to stop
  watching such symbols; not here.
- Users watch more than the ceiling. The job fetches the first 50 by first-watched order and records
  the overflow; raising `WATCHED_TICKERS_MAX` is a one-line deploy change with the cost line above
  as the guide (each extra ticker is about one call and a handful of round trips a night).
- Cloud SQL is unreachable at 23:45 ET. The run fails loudly (the set read raises) and the next
  night catches up; the smart switch makes the catch-up one compact call per ticker.
- A weekday holiday: the scheduler fires, the session check writes a `non_session` heartbeat and
  nothing else, so no indicator row is dated on a day without bars and no ticker is counted failed.
- The scheduler stops firing: the watchdog's new heartbeat check raises a finding after two sessions
  without an `ok` row; without it the watched data would go stale in silence.
- A ticker leaves the watched set: its rows stay, nothing refreshes them, and the all-history union
  excludes it (section Leaving the set), so the earnings chain's universe does not grow with churn.
- A user watches a ticker the earnings chain already refreshes: the job writes it with the chain's
  own source, so nothing about its eligibility changes, and when unwatched the chain keeps refreshing
  it as before.
- A bootstrapped ticker's fetch returns nothing one night: no indicator call, no session-date row,
  a counted bars failure; and because the union counts only real bars from another writer, an
  indicator-only row could not smuggle the ticker into the earnings chain either.
- A ticker listed less than six years ago: one bootstrap pull, then the stale rule; never a nightly
  full pull. A `ticker_info` write that fails is counted, not hidden behind the returned overview.

## Decisions (owner, 2026-11-13)

1. Build the job (this spec), rather than leave user tickers without data.
2. Daily bars with indicators and `ticker_info` only; nothing else per watched ticker.
3. The brief, insight and signal surfaces keep reading only the default list.
4. Ceiling 50 tickers a run, nightly on weekdays, `--max-retries 0`.
5. After #1870's second Codex round (#1872): the job plans its own pulls, verifies `ticker_info`
   durability, and bounds the earnings chain's all-history union, as sections Steps and Leaving the
   set say.

6. 2026-11-13: GCP only. The set is read from the stocks tables (this version); solyra's v3 spec
   consumes the user-watchlist API and has no function and no secret.

No question remains open.
