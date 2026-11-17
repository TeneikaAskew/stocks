---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002, REQ-OBS-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "R1 the record is exact and reproducible: tests/gcp/test_premarket_as_read.py::test_record_is_exact_and_deterministic passes on four bars written in the test (2026-11-16 04:00 to 04:03, the values of Design 2): bars_csv is the text written in the test, bars_sha256 is 538f5b83f2e52f65f93758d5e15b787eb939c7fcb42227e1794b03cdae660ee5, the object bytes are identical when the same bars are passed in reverse order and on a second call, and read_record returns the same bars and raises ValueError, returning no rows, when one byte of bars_csv is changed"
  - "R2 the record carries the request as sent: tests/gcp/test_premarket_as_read.py::test_record_carries_the_request_as_sent passes: fetch_minute_bars calls requests.get with gcp.fetchers.fetch_market_data.minute_bars_request(symbol, month) plus apikey and nothing else, the record's vendor_params equal that dict with entitlement 'realtime', adjusted 'false' and extended_hours 'true', and no key or value of the record holds the API key"
  - "R3 each run records what the three tickers read: tests/gcp/test_fetch_premarket_refresh.py::test_run_records_what_each_of_the_three_tickers_read passes with the universe SPY, QQQ, IWM and AAPL against tests/fixtures/intraday_bars_bucket.MemoryBucket: exactly three objects exist, premarket-as-read/v1/<session date>/<TICKER>/<fetched_at>.json.gz, none for AAPL; each was written with if_generation_match 0 and after upsert_premarket returned; each record's fetched_at is the pre_fetched_at bound for that ticker and its snapshot equals the values bound for that ticker; the rows bound to upsert_premarket equal the rows of the same run with no bucket; ::test_a_failed_prior_session_lookup_is_still_recorded passes: in the same run with QQQ's prior-session lookup raising, QQQ's object exists, written with if_generation_match 0 after upsert_premarket returned, holding the bars QQQ's fetch returned and snapshot null, and no row for QQQ is bound to upsert_premarket"
  - "R4 a failed record never passes silently and never stops the brief's data: tests/gcp/test_fetch_premarket_refresh.py::test_a_failed_record_write_fails_the_run_after_the_upsert passes: with the bucket failing the QQQ write, with GCS_BUCKET unset, and with a write that finds the object already present, upsert_premarket has run for every ticker, the other tickers' objects exist, one ERROR line names each failed ticker and the error, and main() exits 1; no path exits 0 with a record missing"
  - "R5 the record step is bounded: tests/gcp/test_fetch_premarket_refresh.py::test_the_record_step_is_bounded passes with an injected clock: every write is given retry None and a timeout no larger than what is left of AS_READ_DEADLINE_S (10), and once the deadline has passed the remaining tickers are counted failed with reason deadline and no write is attempted; ::test_a_retryable_upload_error_stays_inside_the_deadline passes through the real gcp.fetchers.export_intraday_bars.GcsBucket.write on a google.cloud.storage client with anonymous credentials whose HTTP session advances the injected clock by the timeout each request is given and then answers 503, with time.sleep and time.monotonic on the same clock: SPY's upload is attempted once and nothing sleeps, SPY is counted failed, QQQ and IWM are counted failed with reason deadline, the clock reads no more than AS_READ_DEADLINE_S after the step began, and main() exits 1"
  - "R6 a zero-bar read is on file: tests/gcp/test_premarket_as_read.py::test_a_read_with_no_bars_is_recorded passes: an empty frame gives a record with bar_count 0, bars_csv of the header line alone and snapshot null, and read_record returns an empty frame for it; tests/gcp/test_fetch_premarket_refresh.py::test_an_empty_fetch_is_still_recorded passes: in a run of SPY, QQQ and IWM against the MemoryBucket with SPY's fetch returning an empty frame, SPY's object exists, written with if_generation_match 0 after upsert_premarket returned, with bar_count 0 and snapshot null, and no row for SPY is bound to upsert_premarket"
  - "R7 the comparison tool: tests/gcp/test_premarket_as_read.py::test_compare_counts_differing_bars passes on the four as-read bars of R1 and five stored bars written in the test (Design 5): compare_bars returns as_read_bars 4, stored_bars 4, matched 3, only_as_read 1, only_stored 1, differing 2, differ_open 0, differ_high 0, differ_low 1, differ_close 1, differ_volume 1; ::test_compare_cli_is_read_only passes: python -m gcp.fetchers.premarket_as_read compare --as-read <file> --stored-csv <file> prints those counts as one JSON line, exits 2 on a record whose sha256 does not match, and the module imports neither gcp.database nor requests"
  - "R8 size: tests/gcp/test_premarket_as_read.py::test_object_size_is_bounded passes: a record of 330 bars with four-decimal prices is under 16,384 bytes"
  - "R9 close: make test passes on the PR head; the PR body's Capacity section gives the measured object size and the added writes per run; the FEAT-DATA-001 catalog record and the PR traceability entry are updated; the (FEAT-DATA-001, DASHBOARD-01) implementation-source note carries the source identity that scripts/maintenance/doc_source_snapshot.py produce and verify prove on the committed head; python3 scripts/maintenance/docs_audit.py on the branch reports nothing origin/main does not; python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Keep the one-minute bars exactly as each premarket run read them (SPY, QQQ, IWM)

## Authority and status

Draft. The owner has not approved it (handoff of 2026-11-16, section 4 item 1: "The owner has not yet
said yes to this"). Line numbers are as of `origin/main` at 21e4de31d unless a line names the brief
branch, which is 8250bff75, the head of
`origin/feature/feat-playbook-001-brief-says-what-the-data-says` (PR #2010, not merged). "Read" means
read at that commit; "run" means run by this spec's author in a scratch checkout, removed afterwards.
No production system and no vendor was read.

## Review changes, 2026-11-17

Two Codex findings on PR #2026, each checked first (google-cloud-storage 3.17.1 run here; the refresh
job read on main at 3a59299ba). Changed for re-approval: Design 3 and R5 (each write passes
`retry=None` and a timeout inside the remaining deadline, and a test through the real GCS adapter
with a transport answering 503 shows the step ends inside the deadline), and Design 1, R3 and R6 (an
empty fetch and a failed prior-session lookup are each recorded through the refresh job with a null
snapshot). No decision changed.

## Capability

FEAT-DATA-001 (`docs/product/02-FEATURE-CATALOG.md:35`): Data platform; "Ingestion, storage,
freshness"; no route of its own; backend "fetcher jobs"; data "64 relations", see
`06-DATA-ARCHITECTURE.md`; status "Production but needs remediation"; P0; phase 1. Requirements:
REQ-DATA-002 (a replay reads no revised observation), REQ-DATA-003 (a derived record carries source,
as-of and configuration), REQ-DATA-001 (a failed write is never a silent pass), REQ-REPLAY-001,
REQ-CAP-001 and REQ-CAP-002 (capacity), REQ-OBS-001 (run identity and counts).

## Problem

The vendor revises a session's one-minute bars after the close. Measured once, on 2026-11-16,
read-only, by the author of the handoff (`docs/superpowers/spikes/2026-11-16-session-handoff.md` on
`origin/docs/handoff-2026-11-16`, section 4 item 1; not re-measured here): a vendor read taken at
about 15:00 ET against the bars stored after the close, bar by bar, differs in a price or the volume on
322 of 327 SPY premarket bars, 330 of 330 QQQ and 183 of 199 IWM. Examples: SPY 04:02 volume 968
against 7,151 and low 752.02 against 749.74; IWM 08:05 close 278.92 volume 1 against close 276.24
volume 81. **This is one day's evidence.** How large the revision is on other days is not known.

Both reads ask for the same thing: `entitlement=realtime` in the daily fetcher's request
(`gcp/fetchers/fetch_market_data.py:105-119`, the key at `:115`, read) and in the nightly history
fetch (`gcp/fetchers/fetch_alphavantage_intraday.py:141`, read). So the difference is when the vendor
was asked, not how.

What that means for the brief:

- `fetch-premarket-refresh` runs at 08:20 ET (`gcp/deploy.sh:4840`, read) and, once PR #2020 is
  deployed, again at 09:20 (`premarket-refresh-late`, read on its branch). Each run fetches the month
  from the vendor, keeps the session's bars (`fetch_market_data.py:162-164`), computes the premarket
  high, low, VWAP, volume and gap (`gcp/fetchers/fetch_premarket_refresh.py:203-270`) and upserts them
  with `pre_fetched_at`, `pre_filter_status` and `pre_filter_params` into `market_data_daily`
  (`:302-391`). **The bars themselves are dropped when the function returns.** Read.
- Every stored bar is a later, revised read. Every measurement made so far, and the dry run of PR
  #2010 (`BRIEF_PREMARKET_FROM_BARS`, `gcp/premarket_brief.py:4676-4681` and `:1105-1150` on the brief
  branch, read), computes from `market_data_intraday`. A replay therefore cannot reproduce a morning.
- The thin-bar line of PR #2010, 100 shares (`PM_MIN_EXTREME_VOLUME`, `lib/indicators.py:544` on the
  brief branch, read), and the prior-close print numbers were tuned on stored volumes that, on the one
  day measured, are several times the volumes the morning run saw.

## Non-goals

- No change to any rule, threshold or computed value. The brief reads exactly what it reads today.
- No trading costs. SPY, QQQ and IWM only; the other tickers of the refresh are not recorded.
- No schema change, no scheduler, no lifecycle rule, no change to `gcp/deploy.sh`.
- The vendor's raw reply and its metadata block are not kept. The record is the session's bars as
  parsed, which is everything the computation reads.
- Reading the record in a replay is a later change (Design 6). Nothing reads the objects here except
  the comparison tool.
- The nightly fetcher and the history fetch are not recorded: their reads are what is stored.

## Decisions for the owner (recommended pick first)

Owner, 2026-11-17: approved with every decision below taking its recommended pick (the first option listed).

1. **Where the record lives.** Recommended: the existing bucket (`GCS_BUCKET`, already in the job's
   environment: `gcp/deploy.sh:1127` and `:2843`, read), one gzip object a ticker a run under a dated
   prefix. No schema change, so the merge changes nothing in production; the bucket writer and its
   in-memory test double already exist (`gcp/fetchers/export_intraday_bars.py:86-145`,
   `tests/fixtures/intraday_bars_bucket.py`, read). Its cost: the bars cannot be joined in SQL, so the
   comparison downloads an object. Alternative: a new table, about 1,980 rows a day. It could be
   compared with `market_data_intraday` in one query, but it changes `gcp/schema.sql`, whose merge
   applies to production and needs the owner's yes, and it adds a second table of bars for every
   reader to tell apart.
2. **A failed record write.** Recommended: the run still upserts first, then exits 1 with the ticker
   and error logged (R4). The reason: the brief must still go out, and the late brief waits on this
   job's `pre_fetched_at` (`gcp/premarket_brief.py:3215-3235`, read), so the record step comes after
   the upsert and never delays it; but a morning with no record is a hole in the evidence and must be
   seen. The job already does this when the level parameters cannot be read
   (`gcp/fetchers/fetch_premarket_refresh.py:457-458`, read).
   Consequence: the job has `--max-retries 1` (`gcp/deploy.sh:2838`), so a failed record causes one
   more run about a minute later, which refetches and upserts again. Alternative: log only and exit 0,
   which nobody is alerted to.
3. **Retention.** Recommended: keep every object, no lifecycle rule (about 10 MB a year, Capacity).
   The rules the repo sets cover `sql-dumps/` and `raw/` only (`gcp/deploy.sh:3344-3362`, read).
4. **A read that returned no bars is recorded** (R6). Recommended: yes; it is what the run read.
5. **A new module.** Recommended: `gcp/fetchers/premarket_as_read.py` holds the record format, the
   reader and the comparison tool. The tool is a read-only command; putting it in the refresh job's
   entry point would put a tool next to a job that writes. The job gains one call.
6. **Re-check the thin-bar line and the prior-close numbers.** Recommended: after 20 sessions of 08:20
   records (60 objects), run the comparison over all of them, then repeat the two measurements on the
   as-read bars. Whether either rule changes is a decision then, in its own spec.
7. **Order.** Recommended: build after PR #2010 merges (both edit `fetch_premarket_refresh.py`), and do
   not wait for the prior-close build: every day not recorded is a day that cannot be recovered.

## Approaches considered

Store the raw vendor reply (a month of bars each run, megabytes, for one session's use); a new table
(decision 1); record only a hash (proves a change, cannot replay or measure it); one small object a
ticker a run in the existing bucket (chosen).

## Design

### 1. What is recorded, and when

`compute_premarket_for_ticker` already holds the frame and the instant (`df` at `:203`, `fetched_at`
at `:205`). It gains an optional `on_read(ticker, df, fetched_at)` callback, called once right after
the fetch and before any early return, so an empty read and a read whose prior-session lookup failed
are seen too (the returns at `:206-208` and `:210-215`; R6 and R3 run each through `main()`).
`main()` passes a collector that keeps the frames of `AS_READ_TICKERS = ('SPY', 'QQQ',
'IWM')`. After `upsert_premarket` returns (`:455`), `main()` builds and writes one record per collected
ticker, then exits 1 if any failed or if the level parameters failed, as today.

### 2. The record (`gcp/fetchers/premarket_as_read.py`)

Object name: `premarket-as-read/v1/<YYYY-MM-DD>/<TICKER>/<fetched_at as YYYYMMDDTHHMMSSffffffZ>.json.gz`.
Written once with `if_generation_match=0`; an existing object is a failure, never overwritten.

Content, JSON with sorted keys and no spaces, gzip with mtime 0, so equal input gives equal bytes:

| Key | Value |
|---|---|
| `version` | 1 |
| `ticker`, `session_date` | as run |
| `fetched_at` | the UTC instant also written to `pre_fetched_at` |
| `execution`, `task_attempt` | `CLOUD_RUN_EXECUTION` and `CLOUD_RUN_TASK_ATTEMPT`, null when unset |
| `vendor_params` | the request as sent, without the key (below) |
| `bar_count`, `newest_bar` | bars in the frame; the last bar's Eastern wall time or null |
| `bars_csv` | `ts,open,high,low,close,volume` and one line a bar in time order: `ts` as the vendor keys it (naive Eastern, `YYYY-MM-DD HH:MM:SS`), each price as Python's `repr` of the parsed float, volume as an integer |
| `bars_sha256` | sha256 of `bars_csv` |
| `snapshot` | the values this run bound for the ticker in `upsert_premarket` (`_UPSERT_KEYS`, `:349-350`), with `pre_filter_params` as JSON; null when the run computed none |

`read_record(bytes)` returns the header and the bars and raises when `bars_sha256` does not match.

Run on a scratch prototype of this format, on four bars written out (04:00 `752.5,752.6,752.4,752.5,500`;
04:01 `752.4,752.5,752.3,752.4,300`; 04:02 `752.3,752.4,752.02,752.3,968`; 04:03
`752.2,752.3,752.1,752.2,10`): `bars_sha256` was `538f5b83...660ee5` (in full in R1); the object bytes
were equal with the rows passed in reverse; the sha check passed after a round trip. The prototype's
header fields were fewer than this table's, so only `bars_csv` and its sha are pinned in R1.

The request: `fetch_minute_bars` builds its parameters inline (`fetch_market_data.py:105-119`). They
move, unchanged, into `minute_bars_request(av_symbol, month)`, which returns them without `apikey`;
`fetch_minute_bars` adds the key. The record stores that function's result, so the record and the
request cannot drift (R2). Not run: the function does not exist yet.

### 3. A failed write

Each write is one `GcsBucket.write` call; `write` gains an optional `timeout` and an optional
`retry`, both passed to the upload and left at the library's own defaults when not given, so the
export's writes are unchanged (`upload_from_string` has `timeout=60` and `retry=DEFAULT_RETRY` by
default; signature run here on google-cloud-storage 3.17.1, the image's version was not read). The
whole record step has one deadline, `AS_READ_DEADLINE_S = 10` (R5). `timeout` bounds one request, not
the library's retries: run here with `if_generation_match=0`, `timeout=5` and an HTTP session that
answers 503 to every request, on a simulated clock, the upload was attempted 9 to 19 times over 99 to
210 s of backoff in five runs and ended in `RetryError: Timeout of 120.0s exceeded`; with
`retry=None` it was attempted once and raised `ServiceUnavailable`. So the record step passes
`retry=None` and a `timeout` no larger than what is left of the deadline: each write is one attempt,
and a transient error is a failed record (R4) that the job's one retry runs again (decision 2). A
retry built from the remaining budget was not chosen: `google.api_core` checks its timeout only before
starting another attempt, so the last attempt can run a whole request timeout past it.
A write that raises, a missing `GCS_BUCKET`, an object already present, or the deadline: one
ERROR line `as_read_failed ticker=... reason=...`, the other tickers continue, and the run exits 1
after the last one (R4). On success one INFO line per ticker gives the object name, `bar_count`,
`newest_bar` and `bars_sha256`, and one line gives the count written.

### 4. What does not change

The frames, the computation, the upsert statement and its rows (R3 compares them with a run that has
no bucket). The other tickers of the universe (up to 50, `:53`) are untouched.

### 5. The comparison tool (read-only)

`compare_bars(as_read, stored) -> dict`. The as-read timestamps are converted with
`lib.eastern_time.eastern_index_to_utc` (`lib/eastern_time.py:142`; run: 2026-11-16 04:02 Eastern is
09:02Z). Stored bars are kept when their Eastern date is the session date and they are at or before
the newest as-read bar, so bars the vendor had not yet published are not counted. A price differs when
the two values are 0.00005 or more apart (`market_data_intraday` prices are DOUBLE PRECISION,
`gcp/schema.sql:144-147`, read); a volume differs when the integers differ. The result: `as_read_bars`,
`stored_bars`, `matched`, `only_as_read`, `only_stored`, `differing` (a matched bar with any field
different) and `differ_open`, `differ_high`, `differ_low`, `differ_close`, `differ_volume`; the same
counts again under `premarket` for bars from 04:00 to 09:29 Eastern. A session before
`lib.eastern_time.TRUE_UTC_FROM` (`:196`) is refused: its stored instants are not known to be UTC.

Command: `python -m gcp.fetchers.premarket_as_read compare --as-read <file> --stored-csv <file>`, the
CSV being `ts,open,high,low,close,volume` as `./scripts/db_query_cr.sh` writes a result (a read-only
query the owner or a session runs), or `--bars-root <dir>` for a download of the bucket copy read
through `export_intraday_bars.read_bars` (`:577`). It opens no database and calls no vendor (R7).

Run on the prototype, with the four bars above against five stored bars (09:00Z equal; 09:02Z low
749.74 and volume 7,151, the measured SPY 04:02 pair; 09:03Z close 752.25; 08:59Z and 09:04Z present
only in the store): `as_read_bars 4, stored_bars 4, matched 3, only_as_read 1, only_stored 1,
differ_open 0, differ_high 0, differ_low 1, differ_close 1, differ_volume 1, differing 2`. The 09:04Z
bar is after the newest as-read bar and is not counted. The `premarket` block and the command line
were not prototyped.

### 6. Later: a faithful replay (not this change)

The dry run of PR #2010 cuts the stored bars at the instant the brief recorded,
`level_basis.premarket.fetched_at` (brief branch, `gcp/premarket_brief.py:1135-1143`, read). A later
change can list `premarket-as-read/v1/<date>/<TICKER>/`, take the object whose `fetched_at` is that
instant, verify its sha and compute from its bars; with no such object it says so and keeps the stored
values, as it does today for a missing cutoff. That change belongs to FEAT-PLAYBOOK-001.

## Capacity

- **Volume.** At most 330 premarket bars a ticker a run (04:00 to 09:30 is 330 minutes; an 08:20 read
  holds at most 260, a 09:20 read at most 320). Run on synthetic four-decimal bars: 260 bars is 15,890
  bytes of text and 5,118 bytes as an object; 330 bars 20,170 and 6,392; 960 bars (a whole extended
  day, a manual late rerun) 58,648 and 18,239. Three tickers, two runs a day once PR #2020 is deployed
  (one until then): 6 objects, about 38 KB a day; over 252 sessions 1,512 objects, about 9.7 MB a year.
- **Velocity.** Vendor calls added: 0. SQL added: 0. Bucket writes added: 3 a run, 6 a day, about 126
  a month. Nothing is listed or read by the job.
- **Wall-clock.** The run takes about 65 s today (handoff section 3.3, not measured here) against
  `--task-timeout 300` (`gcp/deploy.sh:2839`). Three small uploads are expected to add about a second
  (not measured). The deadline bounds the step at 10 s, so the worst case is 75 s, a quarter of the
  timeout; memory holds three frames of a few hundred rows inside 512 Mi.
- **Cost.** About 126 writes and under 1 MB added a month: well under $0.01 a month at list prices as
  recalled, not checked. No new scheduled job.

## Close-out

Deploy `fetch-premarket-refresh` from `main` after the merge (the owner's step), then check the next
scheduled morning: three objects under that date's prefix and the three INFO lines in the run's log.

## Risks

- **The service account cannot write the prefix.** Then every run exits 1 after its upsert from the
  first morning (R4 is that behaviour); the brief is unaffected. Its role was not read (below).
- **A retry after a failed record** rewrites `pre_*` a minute later (decision 2). The brief records the
  instant it used, and the retry's record has its own `fetched_at`.
- **The record is the parsed frame, not the wire.** A parsing fault would be recorded as read.
- **One day's evidence** may overstate the revision; decision 6 is how that gets answered.
  Drift between record and request is R2, a changed upsert R3, a silent miss R4.

## What was not verified

- The measurement itself (the counts and the examples) was not repeated; no vendor or database read
  was made. No as-read object exists yet, so the tool has run only on bars written by hand.
- The live bucket: its lifecycle configuration, whether the job's service account may write
  `premarket-as-read/`, and whether the bucket copy of the stored bars (#1943) is deployed.
- The per-upload latency and the google-cloud-storage version in the image (`requirements-gcp.txt:51`
  says `>=2.14.0`). The default retry was run on 3.17.1 only (Design 3).
- Whether Cloud Run sets `CLOUD_RUN_TASK_ATTEMPT` for this job: the code on main reads
  `CLOUD_RUN_EXECUTION` (12 lines under `gcp/`, `lib/` and `scripts/`) and never the attempt.
- PR #2020's branch was read for the 09:20 entries only; PR #2010's changes to
  `fetch_premarket_refresh.py` (27 lines) were read as a diff, not run with this design.
- R2 to R6 and R8's exact bound describe code that does not exist; their values were not run except
  where a Design section says "run on a scratch prototype".
