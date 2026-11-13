---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-CAP-003, REQ-PERF-002, REQ-OBS-001, REQ-FRESH-001, REQ-SECRET-001, REQ-DATA-001, REQ-TENANCY-001, REQ-DEPLOY-001]
issues: [1261, 1872]
canvases: []
done_when:
  - "tests/gcp/test_fetch_watched_tickers.py passes: the watched set is read through an injected HTTP client from WATCHED_TICKERS_URL with Authorization Bearer WATCHED_TICKERS_READ_SECRET; a non-200 reply, a body without a tickers list, or an unset URL or secret makes zero Alpha Vantage calls, records a job_runs row with status failed and exits non-zero; an empty list exits 0 with zero Alpha Vantage calls; tickers already in fetch_market_data.TICKERS are skipped; with WATCHED_TICKERS_MAX=50 and 60 tickers the first 50 in the reply's order are processed and the note records overflow=10; a per-ticker Alpha Vantage failure is counted in items_failed while the other tickers proceed; the exit code is non-zero only when the set read fails or every ticker failed"
  - "The same test file proves the per-ticker sequence with mocks only at the Alpha Vantage and Cloud SQL boundaries and the real decision functions in between: the job reads each kept ticker's stored coverage (bar_count, max_date and bootstrapped, true when any of its rows carries data_source av_watched_backfill) through gcp.database.query_to_dataframe_strict, decides with its own fetch_watched_tickers._pick_watched_outputsize (full when bar_count is 0 or when the ticker is neither bootstrapped nor at the 1,500-bar depth threshold; otherwise the real fetch_market_data._pick_backfill_outputsize stale rule, called with the count lifted to the threshold: None when max_date is the session date, compact within 90 days, full beyond) and calls fetch_market_data._run_backfill(group, outputsize=..., data_source='av_watched_backfill') once per non-empty compact and full group, so a current ticker costs zero daily-series calls, a ticker a few sessions behind costs one compact call, a ticker with no rows costs one full call, a bootstrapped ticker with 300 bars and the session's max_date costs zero calls, the same ticker two sessions behind costs one compact call, and an un-bootstrapped ticker with 300 bars costs one full call once; _run_backfill called without outputsize or data_source keeps today's behaviour for --backfill --tickers and the earnings chain; compute_and_upsert_daily_indicators runs for the session date after the bars for every ticker; lib.ticker_info.get_ticker_info is called with max_age_days=30 so an OVERVIEW call happens at most once per ticker per 30 days; and gcp.database.record_job_run is called exactly once with job_name fetch-watched-tickers, items_total, items_processed, items_failed and rows_written"
  - "The job verifies every watched ticker itself and does not call fetch_market_data._verify_post_fetch_rows (which returns without checking when none of SPY, IWM or QQQ is in the list and counts rows, not tickers): after the indicator step it reads, through gcp.database.query_to_dataframe_strict, each kept ticker's session-date row with its close and atr_14 and its total bar count, and counts a ticker as failed when the row is missing or its close is null (no bars) or when atr_14 is null while the ticker holds at least 15 daily bars (indicators not written), reporting a ticker with fewer than 15 bars as too_short in the note rather than failed; it also reads, through the same strict reader, SELECT ticker, updated_at FROM ticker_info WHERE ticker = ANY(:kept) and counts a ticker as failed with reason ticker_info when its row is missing or updated_at is older than 30 days, since lib.ticker_info._upsert_to_cloud_sql swallows a failed write and get_ticker_info still returns the overview; the test writes the session's bars for four tickers, makes the indicator history read fail for one, the vendor return nothing for another and gcp.database.execute_sql raise for a third ticker's ticker_info upsert, and asserts items_failed=3 with the three names and their reasons in the note; a failed strict read fails the run"
  - "The job resolves the session before anything else: it runs only when lib.eastern_time.is_session(today in Eastern time) is true, and otherwise writes a job_runs row with status ok and note non_session and exits 0 with zero vendor calls and zero writes; the test runs the job on Thursday 2026-11-26 (Thanksgiving) and on a Saturday and asserts no Alpha Vantage call, no upsert and no indicator row dated that day"
  - "fetch_market_data._backfill_targets under BACKFILL_ALL_HISTORY=true excludes a ticker whose market_data_daily rows all carry data_source av_watched_backfill, through HAVING bool_or(data_source IS DISTINCT FROM 'av_watched_backfill') on the market_data_daily arm of its union, while keeping a ticker with rows from any other writer, a ticker with null-sourced rows and every earnings_history ticker; tests/gcp/test_fetch_market_data_backfill_targets.py shows a watched-only ticker is not a target and the other three still are, so the earnings chain's nightly refresh never grows with the watched set"
  - "A source scan in tests/gcp/test_fetch_watched_tickers.py asserts gcp/fetchers/fetch_watched_tickers.py contains no query of watchlists or watchlist_history, no user_id, owner or email identifier, and reads only the tickers list from the solyra reply, so no per-user row can reach this job; tests/gcp/test_watchlist_readers_default_owner.py from the watchlist lock spec stays green"
  - "gcp/deploy.sh gains deploy_fetch_watched_tickers (image, --memory 512Mi, --cpu 1, --max-retries 0, --task-timeout 2400, --command python,-m,gcp.fetchers.fetch_watched_tickers, the secret WATCHED_TICKERS_READ_SECRET through --set-secrets beside the existing DB_SECRET_FLAG, and WATCHED_TICKERS_URL, WATCHED_TICKERS_MAX=50 and AV_BACKFILL_SLEEP_SECS=1.0 through --set-env-vars) and the scheduler watched-tickers-nightly on 45 23 * * 1-5 America/New_York targeting fetch-watched-tickers; tests/gcp/test_deploy_reachability.py passes with the new scheduler resolving to the new job, and the PR body carries the Volume, Velocity, Wall-clock and cost numbers of section Capacity"
  - "The secret WATCHED_TICKERS_READ_SECRET exists in Secret Manager and as the solyra watched-tickers function's secret with the same value, created by the owner and recorded on the PR by name only; one manual gcloud run jobs execute fetch-watched-tickers --wait against the deployed solyra function succeeds, and the PR pastes its job_runs row"
  - "After the first scheduled run, a read-only scripts/db_query_cr.sh run of SELECT job_name, status, items_total, items_processed, items_failed, rows_written, note FROM job_runs WHERE job_name = 'fetch-watched-tickers' ORDER BY started_at DESC LIMIT 1 shows status ok, and SELECT ticker, MAX(date) FROM market_data_daily WHERE ticker = ANY(the watched set) GROUP BY ticker shows that session's date for every processed ticker; both outputs are pasted on the PR with their execution ids"
  - "scripts/audit_data_freshness.py gains a heartbeat check for fetch-watched-tickers: a finding when job_runs holds no status ok row for that job dated within the last two sessions (lib.eastern_time), and an informational row when the latest row's note carries overflow or its items_failed is above zero; tests/audits/test_audit_freshness_job_observability.py covers an absent heartbeat, an overdue one, a healthy one and an overflow note"
  - "The FEAT-DATA-001 catalog record and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Fetch daily bars and ticker info once per distinct watched ticker

## Authority and status

Draft, written 2026-11-13 from the owner's choice of the same day, in their words: "A stocks job
also fetches daily bars and ticker info once per distinct watched ticker, reading the owner-free
watched_tickers set, so a ticker ten users watch is fetched once. That keeps 'per-user rows never
reach a job' true, but it is a new job with a schedule, a ticker ceiling and a cost, so it would be
its own stocks spec. The brief, insight and signal surfaces would still read only the default list."

This is the third spec of the watchlist split. The first two are
`docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock.md` (stocks, the
default list locked to Discord and the CLI) and
`docs/superpowers/specs/2026-11-13-feat-insight-001-user-watchlist.md` in TeneikaAskew/solyra (the
per-user list in solyra's Supabase project with one shared `watched_tickers` row per ticker). The
lock spec's decision 5 said "no job fetches data for a user's own tickers for now"; this spec is
that change. The draft merged through #1870 after two Codex review rounds; this revision folds in
the three findings of the second round (#1872) and carries `status: approved`, which the owner
records by merging it. No code before that merge.

## Problem

A ticker a web user adds to their own list gets no data unless an operator also adds it to the
default list in Discord (stocks #1261 was this complaint in its old form). After the split the
per-user list lives in solyra and never reaches a stocks job, so without this spec a user's ticker
shows "no data yet" forever: no daily bars in `market_data_daily`, no indicators, no `ticker_info`
row, so Briefing, Charts and the ranked panel have nothing to show for it.

The owner's constraint is dedup: ten users watching one ticker must cost one fetch, not ten.
Solyra's `watched_tickers` table already holds exactly one row per watched ticker with no owner on
it, so it is the right input, and stocks already stores every data table once per ticker.

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
- No per-user data in stocks. The job receives tickers only; it never sees who watches them.
- Two additive keywords on `_run_backfill`, `outputsize` and `data_source`, both defaulting to today's
  values, and one `HAVING` clause on the `market_data_daily` arm of `_backfill_targets`' all-history
  union (section Leaving the set). No change to `compute_and_upsert_daily_indicators`,
  `_pick_backfill_outputsize` or `get_ticker_info`; `_verify_post_fetch_rows` is not used by this job.
  The 10-year cap and the smart switch stay as they are for every other caller.
- No change to the default list's own nightly fetch (`fetch-market-data-daily`, 23:00 ET).
- No UI. What the web shows for a ticker before and after the first fetch is the solyra spec's.
- No feedback channel from stocks to solyra about a symbol Alpha Vantage does not serve. The
  solyra snapshot's coverage read, refreshed once per ticker per 24 hours, is how the web learns a
  ticker has no data after a fetch.

## Approaches considered

1. The job connects to solyra's Supabase Postgres directly and selects from `watched_tickers`.
   Rejected: a service-role database credential for another cloud inside GCP, a second driver, and a
   read of a table whose other table holds owners. The boundary belongs at HTTPS with a scoped secret.
2. Solyra pushes the distinct set into a stocks table through a stocks API route. Rejected: a write
   path from solyra into stocks is the opposite of the lock spec, and a second copy of the set.
3. Chosen: a secret-protected, owner-free `watched-tickers` function in solyra (defined in the
   solyra spec) returns the distinct active tickers; this job pulls it once a night and feeds the
   existing fetch functions, once per ticker.

## Design

### Entry point and schedule

`gcp/fetchers/fetch_watched_tickers.py`, Cloud Run Job `fetch-watched-tickers`, scheduler
`watched-tickers-nightly` at `45 23 * * 1-5` America/New_York: after `fetch-market-data-daily`
(23:00 ET, settle deadline 23:30) has finished the default list, before the 04:00 ET premarket.
`--max-retries 0` (REQ-CAP-003; a failure is a heartbeat failure, not something a retry fixes).

Environment: `WATCHED_TICKERS_URL`
(`https://hajmcfkqmtgidstpggrh.supabase.co/functions/v1/watched-tickers`, non-secret, `--set-env-vars`),
`WATCHED_TICKERS_READ_SECRET` (Secret Manager, `--set-secrets`, the same value stored as the solyra
function's secret; rotation owner: the project owner; the function accepts a previous value during
rotation the way `supabase/functions/_shared/cron-auth.ts` does), `WATCHED_TICKERS_MAX` (default 50),
`AV_BACKFILL_SLEEP_SECS=1.0` (60 calls a minute, under the 150 RPM local allocation of
`lib/config.py:124`), plus the existing `ALPHA_VANTAGE_API_KEY` and Cloud SQL secrets.

### Steps

0. **Resolve the session.** `today` is the Eastern date (`lib.eastern_time.market_today()`). If
   `is_session(today)` is false (a weekend, or a weekday holiday the scheduler still fires on), the
   job writes a `job_runs` row with `status = 'ok'` and `note = 'non_session'` and exits 0 with zero
   vendor calls and zero writes. Otherwise `fetch_date = today`; at 23:45 ET the session is complete.
   This is what keeps a holiday from producing an indicator-only row dated on a day with no bars.
1. **Read the set.** `GET WATCHED_TICKERS_URL` with `Authorization: Bearer <secret>`. Reply shape
   (solyra spec): `{as_of, count, truncated, tickers: ["AAPL", ...]}`, distinct tickers with at least
   one active membership, ordered by first watched, no owner fields. Anything but a 200 with a
   `tickers` list is a failure: the job writes a `job_runs` row with `status = 'failed'` and exits
   non-zero without calling Alpha Vantage (REQ-DATA-001: a failed read is never an empty universe).
   An empty list is a legitimate answer: `status = 'ok'`, `items_total = 0`, exit 0.
2. **Dedup and cap.** Drop tickers in `fetch_market_data.TICKERS` (IWM, SPY, QQQ, SPX and the sector
   ETFs; the default list is already fetched nightly). Keep the first `WATCHED_TICKERS_MAX` in the
   reply's order and record `overflow=<n>` in the run note when any are dropped; the log line is at
   ERROR so the operator sees that users are watching more than the ceiling. The freshness watchdog
   reads the note from `job_runs`.
3. **Daily bars.** The job plans, `_run_backfill` executes. Before any vendor call the job reads
   `SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date, bool_or(data_source = 'av_watched_backfill') AS bootstrapped FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker`
   through `query_to_dataframe_strict` (a ticker absent from the result has `(0, None, false)`) and
   decides per ticker with its own `_pick_watched_outputsize(bar_count, max_date, bootstrapped, today)`:
   `full` when `bar_count = 0`, or when the ticker is neither `bootstrapped` nor at
   `BACKFILL_DEPTH_THRESHOLD_BARS` (1,500 bars): one bootstrap pull, after which its rows carry the
   watched source and it never bootstraps again. Otherwise the existing stale rule, by calling the
   real `_pick_backfill_outputsize` with the count lifted to the threshold: `None` when `max_date` is
   the session date (zero calls), `compact` within 90 days, `full` beyond. The unchanged switch alone
   would answer `full` for every ticker under 1,500 bars whatever its `max_date` (`:901-903`). The
   job then calls `_run_backfill(group, outputsize='compact', data_source='av_watched_backfill')` and
   the same for the `full` group, skipping an empty group. The two new keywords: `outputsize` makes
   every explicit ticker pull at that size instead of the `(0, None)` planning at `:990-991`, and
   `data_source` replaces the constant at `:1041`; both default to today's values, so
   `--backfill --tickers` and the earnings chain are unchanged. Rows are upserted on `(ticker, date)`,
   so a re-run converges (REQ-CAP-002).
4. **Indicators.** For each kept ticker, `compute_and_upsert_daily_indicators(ticker, fetch_date,
   level_params=read_level_params_for_run(kept, fetch_date)[ticker])`, the same call the default
   list gets. It reads 250 bars and writes the day's indicator columns.
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
`SELECT ticker FROM market_data_daily GROUP BY ticker HAVING bool_or(data_source IS DISTINCT FROM 'av_watched_backfill')`:
a ticker whose rows all came from this job stays out; a ticker with rows from any other writer, or
with null-sourced rows (`data_source` is nullable, which is why `IS DISTINCT FROM` and not `<>`),
stays in; the `earnings_history` arm is untouched. This is the one change outside the job's own
module besides the two `_run_backfill` keywords.

### Capacity (CLAUDE.md Rule 0, REQ-CAP-001 to 003)

Ceiling: 50 watched tickers beyond the default list per run.

- **Volume.** First run worst case: 50 tickers x about 2,520 daily rows (10 years) x about 200 bytes
  = about 25 MB written once. Steady state: at most 50 bar rows and 50 indicator upserts a day (about
  20 KB), plus at most 50 `ticker_info` rows per 30 days.
- **Velocity.** Per run: 1 HTTPS GET for the set, 1 coverage query and 2 verification queries (bars
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
no `status = 'ok'` row for the job dated within the last two sessions. Today the watchdog
(`scripts/audit_data_freshness.py`) has no such check: its only `job_runs` reader is
`_query_job_duration_regression`, so a scheduler that silently stops would never be noticed. This
spec adds a heartbeat check beside it: a finding when the latest `ok` row is older than two sessions
or absent, and an informational row when the latest note carries `overflow` or `items_failed` is
above zero, so one unserved symbol is visible without paging anyone nightly. Recovery:
`gcloud run jobs execute fetch-watched-tickers --region us-east1 --wait`; the run is idempotent.

### Tests

`tests/gcp/test_fetch_watched_tickers.py` with mocks at the HTTP, Alpha Vantage and Cloud SQL
boundaries only, so `_pick_watched_outputsize` (and the real `_pick_backfill_outputsize` it calls for
the stale rule), the session check and the per-ticker verification run for real; one test per
done_when clause, plus the source scan, the holiday case and the three sub-threshold coverage cases.
`tests/gcp/test_deploy_reachability.py` already asserts every scheduler target is a job some `deploy_*`
function creates; the new pair is covered by it. The watchdog heartbeat check is covered in
`tests/audits/test_audit_freshness_job_observability.py`, and the all-history union's new `HAVING`
clause in `tests/gcp/test_fetch_market_data_backfill_targets.py`.

## Cross-repo contract

| Side | What | Who writes | Who reads |
|---|---|---|---|
| solyra Supabase `hajmcfkqmtgidstpggrh` | `watched_tickers` (one row per ticker) and the `watched-tickers` function: `GET`, `Authorization: Bearer <WATCHED_TICKERS_READ_SECRET>`, reply `{as_of, count, truncated, tickers}` of distinct active tickers in first-watched order, capped at 200, no owner fields | the `user-watchlist` function on a user's add | this job, nightly |
| stocks Cloud SQL | `market_data_daily` rows (`data_source = 'av_watched_backfill'`) and indicators, `ticker_info` rows, `job_runs` heartbeat | this job (and the default list's fetchers for their own tickers) | Briefing, Charts, the ranker and the solyra coverage snapshot, as today |
| stocks Cloud SQL | `watchlists` | unchanged | unchanged; this job never reads it |

Ordering: the solyra `watched-tickers` function and its secret are deployed first (solyra spec
#330's implementation), then this job; the scheduler is created only after the manual execution in
done_when item 5 succeeds, so a job with nothing to read is never scheduled.

## Risks

- Alpha Vantage returns nothing for a symbol it does not serve. The ticker is counted as failed every
  night and never gets a row; the owner sees it in `job_runs.items_failed` and the web shows "no
  data for this symbol" through the coverage snapshot. A later change could tell solyra to stop
  watching such symbols; not here.
- Users watch more than the ceiling. The job fetches the first 50 by first-watched order and records
  the overflow; raising `WATCHED_TICKERS_MAX` is a one-line deploy change with the cost line above
  as the guide (each extra ticker is about one call and a handful of round trips a night).
- The solyra function is down at 23:45 ET. The run fails loudly and the next night catches up; the
  smart switch makes the catch-up one compact call per ticker.
- A weekday holiday: the scheduler fires, the session check writes a `non_session` heartbeat and
  nothing else, so no indicator row is dated on a day without bars and no ticker is counted failed.
- The scheduler stops firing: the watchdog's new heartbeat check raises a finding after two sessions
  without an `ok` row; without it the watched data would go stale in silence.
- The secret is rotated in one store but not the other. The function accepts the previous value
  during rotation; done_when item 5 proves the pair works before scheduling.
- A ticker leaves the watched set: its rows stay, nothing refreshes them, and the all-history union
  excludes it (section Leaving the set), so the earnings chain's universe does not grow with churn.
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

No question remains open on the stocks side. The solyra side adds the `watched-tickers` function
and its secret to its spec (#330).
