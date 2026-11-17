---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md
branch: feature/feat-data-001-premarket-reads-as-read
pr: null
status: ready
---

# Keep the one-minute bars exactly as each premarket run read them (SPY, QQQ, IWM): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named as the spec names them, R1 to R9.

**Goal:** Each `fetch-premarket-refresh` run writes, after its upsert, one gzip object per SPY, QQQ and IWM holding the session's one-minute bars exactly as that run parsed them, with the request it sent and the values it upserted, and a read-only tool compares such an object with the stored bars.

**Architecture:** A new module `gcp/fetchers/premarket_as_read.py` owns the record (deterministic CSV text, sha256, gzip with mtime 0), its reader, the bounded writer and the comparison tool; it imports neither `gcp.database` nor `requests`. The vendor request moves unchanged into `fetch_market_data.minute_bars_request`, so the record stores what was sent. `compute_premarket_for_ticker` gains an `on_read` callback; `main()` collects the three frames and writes their records after `upsert_premarket` returns, then exits 1 if any record failed.

**Tech Stack:** Python 3, pandas, `gzip`, `hashlib`, `json`, `argparse`, google-cloud-storage through the existing `GcsBucket`, pytest with `tests/fixtures/intraday_bars_bucket.MemoryBucket`.

**Spec:** docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md (approved by the owner 2026-11-17 with every decision taking its recommended pick; PR #2026, not yet on `main` when this plan was written). This plan matches the spec as revised after review, head fed354413: each record write passes `retry=None` and a timeout inside the remaining deadline, proven through the real GCS adapter (R5), and an empty fetch and a failed prior-session lookup are each recorded through the refresh job (R6, R3).

## Start condition

Decision 7: build after PR #2010 (`feature/feat-playbook-001-brief-says-what-the-data-says`) merges, because both edit `gcp/fetchers/fetch_premarket_refresh.py`. Do not open the build branch until `git log origin/main --oneline -- gcp/fetchers/fetch_premarket_refresh.py` shows #2010's change (its `_newest_premarket_bar` exists on `main`). The spec (PR #2026) and this plan merge first. Do not wait for the prior-close build.

**Line numbers.** Every `file:line` below is read on 44dfa3d8c, the head of PR #2010 when this plan was written, for the two files #2010 changes (`gcp/fetchers/fetch_premarket_refresh.py`, `gcp/fetchers/fetch_market_data.py`), and on `origin/main` 3a59299ba for everything else (#2010 does not change them). First step of Task 1: `git diff --stat 44dfa3d8c origin/main -- gcp/fetchers lib/eastern_time.py tests/fixtures/intraday_bars_bucket.py tests/gcp/test_fetch_premarket_refresh.py` on the real base, and re-find any line that moved.

## Global Constraints

- Branch `feature/feat-data-001-premarket-reads-as-read` from `origin/main` once the start condition holds. One PR, title `FEAT-DATA-001: keep the premarket bars as each refresh run read them`.
- Values, copied from the spec:
  - `AS_READ_TICKERS = ('SPY', 'QQQ', 'IWM')`; `AS_READ_DEADLINE_S = 10`; record `version` 1.
  - Object name: `premarket-as-read/v1/<YYYY-MM-DD>/<TICKER>/<fetched_at as YYYYMMDDTHHMMSSffffffZ>.json.gz`, written once with `if_generation_match=0`.
  - Content: JSON with `sort_keys=True` and `separators=(',', ':')`, gzip with `mtime=0`. Keys: `version`, `ticker`, `session_date`, `fetched_at`, `execution`, `task_attempt`, `vendor_params`, `bar_count`, `newest_bar`, `bars_csv`, `bars_sha256`, `snapshot`.
  - `bars_csv`: header `ts,open,high,low,close,volume`, then one line a bar in time order; every line, the header included, ends with `\n`. `ts` as the vendor keys it (naive Eastern, `YYYY-MM-DD HH:MM:SS`), each price `repr(float(x))`, volume `str(int(x))`. Checked for this plan: the four bars of R1 in this form hash to `538f5b83f2e52f65f93758d5e15b787eb939c7fcb42227e1794b03cdae660ee5`, the spec's value; without the final `\n` they do not.
  - Log lines: `as_read_failed ticker=<T> reason=<reason>` at ERROR; on success one INFO line per ticker with the object name, `bar_count`, `newest_bar` and `bars_sha256`, and one INFO line with the count written.
  - Comparison: a price differs when the two values are `0.00005` or more apart; a volume when the integers differ. Stored bars are kept when their Eastern date is the session date and they are at or before the newest as-read bar. The `premarket` block repeats the counts for bars from 04:00 to 09:29 Eastern. A session before `lib.eastern_time.TRUE_UTC_FROM` is refused.
- What does not change (spec Design 4, Non-goals): the frames, the computation, the upsert statement and its rows, the other tickers of the universe, `gcp/schema.sql`, `gcp/deploy.sh`, any scheduler or lifecycle rule, the nightly fetcher and the history fetch.
- `gcp/fetchers/premarket_as_read.py` imports neither `gcp.database` nor `requests`, at module level or inside the comparison path (R7). It may import `gcp.fetchers.export_intraday_bars` (its top level is the standard library and pandas) and `lib.eastern_time`.
- Time (CLAUDE.md 3.9): every zone change goes through `lib/eastern_time.py` (`eastern_index_to_utc`, `market_date`, `eastern_bounds_utc`); `tests/meta/test_timezone_boundaries.py` fails on a hand-rolled conversion.
- No silent fallback (CLAUDE.md 3.7): a failed record is an ERROR line and exit 1, never a pass; a missing value in the record is `null`, never 0.
- Tests are hermetic: no network, no bucket, no database. The bucket is `MemoryBucket`; the vendor is a patched `fetch_minute_data` or `requests.get`.
- The render step. A task that changes a file under `gcp/` or `lib/` ends with
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect `1 passed`), and stages whichever of the three docs changed with the code.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. Every new test has a red then green record in the PR body.
- Capacity (CLAUDE.md rule 0; spec Capacity), written into the PR body because the PR touches `gcp/`: Volume, at most 330 premarket bars a ticker a run, the object sizes Task 2 Step 6 measures (spec: 260 bars 5,118 bytes, 330 bars 6,392, 960 bars 18,239), 6 objects and about 38 KB a day with the 09:20 run, about 9.7 MB a year; Velocity, 0 vendor calls and 0 SQL added, 3 bucket writes a run, 6 a day, about 126 a month, nothing listed or read by the job; Wall-clock, about 65 s a run today (handoff, not measured) against `--task-timeout 300` (`gcp/deploy.sh:2839`), the record step bounded at 10 s, worst case 75 s; Cost, about 126 writes and under 1 MB a month, well under $0.01 a month at list prices as recalled, not checked; no new scheduled job.

## Choices this plan makes where the spec leaves one open

Reported to the owner with the plan.

1. **The request is computed where the frame is collected, not inside the record module.** `premarket_as_read` may not import `requests` (R7), and `gcp.fetchers.fetch_market_data` imports it at module level (`:24`). So `fetch_premarket_refresh.main()`'s collector stores `minute_bars_request(av_listed_symbol(ticker), iso_date[:7])` beside each frame, and `build_record` takes it as `vendor_params`. Both the request and the record call the same function (R2).
2. **What `snapshot` holds.** The ticker's row as `main()` passes it to `upsert_premarket`, projected on `_UPSERT_KEYS`, made JSON: `date` as `YYYY-MM-DD`, `pre_fetched_at` as ISO 8601 with offset and microseconds, `pre_filter_params` parsed from its JSON text into an object, other values as bound; `null` when `compute_premarket_for_ticker` returned None. A row `upsert_premarket` skips as holding no `pre_*` value (`:322-329`) is still recorded as computed; its values are all null there anyway.
3. **The bucket.** `main()` gets it through a module function `_as_read_bucket()` that returns `export_intraday_bars.bucket_from_env()` (`:147-158`), which raises `RuntimeError` naming `GCS_BUCKET` when it is unset. Tests patch `_as_read_bucket`; the unset case leaves it and deletes the variable. The deadline clock starts before the bucket is built, because building a `GcsBucket` creates a storage client.
4. **`timeout` and `retry` on the test double.** `MemoryBucket.write` (`tests/fixtures/intraday_bars_bucket.py`) gains `timeout: Optional[float] = None` and `retry=LIBRARY_DEFAULT` (Task 3's sentinel) and records them in new `timeouts` and `retries` lists; the export module's tests do not pass either and are unchanged.
5. **The stored CSV.** `--stored-csv` reads `ts` values that carry a UTC offset, as `./scripts/db_query_cr.sh` writes a `TIMESTAMPTZ`; a naive `ts` exits 2 with a message (its zone cannot be known), never guessed.
6. **Exit codes of the tool.** 0 with one JSON line on stdout; 2 with one line on stderr for a sha mismatch, a session before `TRUE_UTC_FROM`, a naive stored `ts`, or a usage error.
7. **R5's real-adapter test needs no production hook.** `GcsBucket` builds its own `storage.Client()` (`gcp/fetchers/export_intraday_bars.py:95-99`), so the test patches `google.cloud.storage.Client` with a factory returning a real `storage.Client(project='test-project', credentials=AnonymousCredentials(), _http=session)`, as the export's `gcs` fixture patches it with a fake; `GcsBucket`'s constructor and `_as_read_bucket` are unchanged and run as written with `GCS_BUCKET` set. The session is a `requests.Session` subclass with `is_mtls = False` (the library reads it to pick the upload host; without it the upload raises `AttributeError` before any request). Run for this plan on google-cloud-storage 3.17.1 with that session answering 503 and advancing a fake clock by the `timeout` it is given, `time.monotonic` and `time.sleep` patched to the same clock: `upload_from_string(..., if_generation_match=0, timeout=10.0, retry=None)` sent one POST, received `timeout` 10.0 as a float, slept 0 times, moved the clock 10.0 and raised `ServiceUnavailable`; the same call with the library's default retry sent 8 POSTs, slept 19 times, moved the clock 245.9 s and raised `RetryError`.

## done_when map

| done_when | What | Task |
|---|---|---|
| R1 | the record is exact and reproducible | 2 |
| R2 | the record carries the request as sent | 1, 4 |
| R3 | each run records what the three tickers read | 4 |
| R4 | a failed record never passes silently | 3, 4 |
| R5 | the record step is bounded | 3, 4 |
| R6 | a zero-bar read is on file | 2, 4 |
| R7 | the comparison tool | 5, 6 |
| R8 | size | 2 |
| R9 | close | 7 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task named.

- **The 08:20 and 09:20 runs on the same date.** Two objects under the same ticker folder, one per `fetched_at`; the second never overwrites the first. Task 3 writes two records for one ticker with different instants into one bucket.
- **A stored CSV whose `ts` has no offset.** The tool exits 2 and prints nothing on stdout. Task 6.
- **The `premarket` block's edge.** A stored bar at 03:59 Eastern (08:59Z on 2026-11-16) counts in the totals and not in the `premarket` block; a bar at 09:29 Eastern counts in both. Task 5 pins the block's values for R7's bars.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/fetchers/fetch_market_data.py` | `minute_bars_request` (new, beside `fetch_minute_bars` `:85`); `fetch_minute_bars` uses it (`:103-119`) | 1 |
| `gcp/fetchers/premarket_as_read.py` | new: constants, `object_name`, `bars_csv`, `snapshot_record`, `build_record`, `read_record`, `write_records`, `compare_bars`, `main` | 2, 3, 5, 6 |
| `gcp/fetchers/export_intraday_bars.py` | `LIBRARY_DEFAULT`; `GcsBucket.write` gains `timeout` and `retry` (`:120-137`) | 3 |
| `tests/gcp/test_export_intraday_bars.py` | `test_gcs_bucket_write_passes_timeout_and_retry_only_when_given` (existing tests unedited) | 3 |
| `tests/fixtures/intraday_bars_bucket.py` | `MemoryBucket.write` gains `timeout` and `retry`, `timeouts` and `retries` lists | 3 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `compute_premarket_for_ticker` gains `on_read` (`:184-215`); `_as_read_bucket`; `main()` collects and writes after `upsert_premarket` (`:409-471`) | 4 |
| `tests/gcp/test_premarket_as_read.py` | new: R1, R2, R6, R7, R8 tests | 1, 2, 5, 6 |
| `tests/gcp/test_fetch_premarket_refresh.py` | R3, R4, R5 and R6 (`test_an_empty_fetch_is_still_recorded`) tests and `_run_refresh` | 3, 4 |
| `docs/product/02-FEATURE-CATALOG.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `docs/product/03-SITE-TRACEABILITY.md`, `docs/review-evidence/site-source-snapshot.json` | the close | 7 |

---

## Task 1: The request as one function

Spec: Design 2, "The request". Advances R2 (the request half).

**Files:** Modify `gcp/fetchers/fetch_market_data.py` (`:85-121`); Test `tests/gcp/test_premarket_as_read.py` (new).

**Interfaces:**
- Produces: `minute_bars_request(av_symbol: str, month: str) -> dict`, the eleven keys of `:105-119` except `apikey`, with the values unchanged: `function` `TIME_SERIES_INTRADAY`, `symbol` `av_symbol`, `interval` `1min`, `month`, `outputsize` `full`, `adjusted` `false`, `entitlement` `realtime`, `extended_hours` `true`, `datatype` `json`. The comments at `:111-115` move with their keys.

- [ ] **Step 1: Check the base** with the Line numbers diff above.
- [ ] **Step 2: Write the failing test** `test_record_carries_the_request_as_sent` (first half; Task 4 Step 5 adds the record half): patch `fetch_market_data.requests.get` with a recorder returning a response whose `json()` is a one-bar `Time Series (1min)` for 2026-11-16; call `fetch_minute_bars('SPY', '2026-11-16', 'TEST-KEY-not-real')`; assert the recorded `params == {**fetch_market_data.minute_bars_request('SPY', '2026-11'), 'apikey': 'TEST-KEY-not-real'}` and that `minute_bars_request('SPY', '2026-11')` has `entitlement == 'realtime'`, `adjusted == 'false'`, `extended_hours == 'true'` and no `apikey`.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_premarket_as_read.py -q`. Expect FAIL, AttributeError on `minute_bars_request`.
- [ ] **Step 4: Implement** `minute_bars_request`; in `fetch_minute_bars` the dict at `:105-119` becomes `{**minute_bars_request(av_symbol, month), 'apikey': api_key}`.
- [ ] **Step 5: Run** the file (expect pass) and `python3 -m pytest tests/gcp -q -k "fetch_market_data or minute"` (expect all pass).
- [ ] **Step 6: Render step, then commit** `refactor(fetchers): build the intraday request in one function`.

## Task 2: The record

Spec: Design 2. Advances R1, R6, R8.

**Files:** Create `gcp/fetchers/premarket_as_read.py`; Test `tests/gcp/test_premarket_as_read.py`.

**Interfaces:**
- Produces, in `gcp/fetchers/premarket_as_read.py`:
  - `PREFIX = 'premarket-as-read/v1'`, `RECORD_VERSION = 1`, `AS_READ_TICKERS`, `AS_READ_DEADLINE_S`, `CSV_HEADER = 'ts,open,high,low,close,volume'`.
  - `object_name(ticker: str, session_date: date, fetched_at: datetime) -> str`; `fetched_at` must be aware (naive raises ValueError) and is formatted in UTC.
  - `bars_csv(bars: pd.DataFrame) -> str`: `bars` is a frame as `fetch_minute_data` returns it (naive Eastern `DatetimeIndex`, columns `Open High Low Close Volume`, any extra column ignored), sorted by index before writing; or the columnless `pd.DataFrame()` that `fetch_minute_bars` returns, and `fetch_minute_data` forwards, when the vendor has no bars for the day. Emptiness is handled before any column is selected, and the caller's frame is never modified.
  - `snapshot_record(row: Optional[dict], keys: Sequence[str]) -> Optional[dict]` (Choice 2); the caller passes `fetch_premarket_refresh._UPSERT_KEYS`, so this module never imports the job.
  - `build_record(*, ticker: str, session_date: date, fetched_at: datetime, bars: pd.DataFrame, vendor_params: dict, snapshot: Optional[dict], execution: Optional[str], task_attempt: Optional[str]) -> bytes`.
  - `read_record(data: bytes) -> tuple[dict, pd.DataFrame]`: the header (every key but `bars_csv`) and the bars with columns `ts` (naive `Timestamp`), `open`, `high`, `low`, `close` (float), `volume` (int64). Raises `ValueError` naming the expected and found sha when `bars_sha256` does not match, before any row is parsed.

- [ ] **Step 1: Write the failing test** `test_record_is_exact_and_deterministic`. Bars as the spec writes them, index `2026-11-16 04:00` to `04:03`: `752.5,752.6,752.4,752.5,500`; `752.4,752.5,752.3,752.4,300`; `752.3,752.4,752.02,752.3,968`; `752.2,752.3,752.1,752.2,10`. Decode `json.loads(gzip.decompress(data))` and assert: `bars_csv` equals the text typed in the test (header and four lines, each ending `\n`), `bars_sha256 == '538f5b83f2e52f65f93758d5e15b787eb939c7fcb42227e1794b03cdae660ee5'`, `bar_count == 4`, `newest_bar == '2026-11-16 04:03:00'`; `build_record` on the same bars in reverse order and a second call on the original give identical bytes; `read_record(data)[1]` equals the four bars; a copy whose decoded `bars_csv` has one character changed and is re-gzipped makes `read_record` raise `ValueError`.
- [ ] **Step 2: Write the failing test** `test_a_read_with_no_bars_is_recorded`, parametrised over two inputs: `pd.DataFrame()` with no columns, the shape `fetch_minute_bars` returns when the vendor has no bars (an empty time series or only other dates), and an empty frame with the five columns. For each: `bar_count == 0`, `newest_bar is None`, `bars_csv == 'ts,open,high,low,close,volume\n'`, `snapshot is None` (passed None), `read_record` returns an empty frame with the six columns, both inputs give identical bytes, and the input frame is unchanged after the call (its `columns` list and shape as before). A serializer that selects the five columns before checking for emptiness raises `KeyError` on the first input and fails this test.
- [ ] **Step 3: Write the failing test** `test_object_size_is_bounded`: 330 bars from 04:00 on 2026-11-16, prices with four decimals (for example `752.1234 + i / 10000`), volumes in the thousands, a snapshot dict of the eleven `_UPSERT_KEYS`; assert `len(build_record(...)) < 16384`.
- [ ] **Step 4: Write** `test_object_name`: `object_name('SPY', date(2026, 11, 16), datetime(2026, 11, 16, 13, 20, 1, 123456, tzinfo=timezone.utc)) == 'premarket-as-read/v1/2026-11-16/SPY/20261116T132001123456Z.json.gz'`; a naive `fetched_at` raises ValueError.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_premarket_as_read.py -q`. Expect FAIL, ModuleNotFoundError. Implement the interfaces; the JSON form and gzip mtime are in Global Constraints. Run again: expect all pass.
- [ ] **Step 6: Measure** the object sizes the PR body's Capacity section quotes: a short script in the PR body's evidence (not committed) that prints `len(build_record(...))` for 260, 330 and 960 synthetic four-decimal bars. Record the three numbers.
- [ ] **Step 7: Render step, then commit** `feat(fetchers): record the premarket bars as read in one object`.

## Task 3: The bounded writer

Spec: Design 3. Advances R5 (`test_the_record_step_is_bounded`; Task 4 adds the real-adapter test) and the bucket half of R4.

**Files:** Modify `gcp/fetchers/export_intraday_bars.py` (`GcsBucket.write`, `:120-137`), `tests/fixtures/intraday_bars_bucket.py` (`MemoryBucket.write`), `gcp/fetchers/premarket_as_read.py`; Test `tests/gcp/test_fetch_premarket_refresh.py`, `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:**
- Produces, in `gcp/fetchers/export_intraday_bars.py`: `LIBRARY_DEFAULT = object()`, and `GcsBucket.write(name, data, if_generation_match=None, timeout: Optional[float] = None, retry=LIBRARY_DEFAULT) -> int`, passing `timeout=timeout` to `upload_from_string` only when it is not None and `retry=retry` only when it is not `LIBRARY_DEFAULT`. A sentinel, not None, marks "not given" for `retry`, because `retry=None` is a value the record step must reach the upload with (no retry). A call with neither, as every export write is, leaves the library's defaults (`timeout=60`, `retry=DEFAULT_RETRY` on 3.17.1).
- Produces: `AsRead = NamedTuple('AsRead', [('bars', pd.DataFrame), ('fetched_at', datetime), ('vendor_params', dict)])` and `write_records(bucket_factory: Callable[[], Any], session_date: date, reads: dict[str, AsRead], snapshots: dict[str, Optional[dict]], *, clock: Optional[Callable[[], float]] = None, deadline_s: float = AS_READ_DEADLINE_S, env: Mapping[str, str] = os.environ) -> tuple[list[str], list[tuple[str, str]]]`, returning the object names written and the `(ticker, reason)` failures. `clock` None means `time.monotonic` looked up when `write_records` is called, not when it is defined, so R5's real-adapter test (Task 4), which patches `time.monotonic`, moves it. Order: tickers in `AS_READ_TICKERS` order. The clock is read once before `bucket_factory()` (the start) and once before each ticker's write, and nowhere else; a factory that raises fails every ticker with its message. For each ticker: `left = deadline_s - (clock() - start)`; `left <= 0` fails it with reason `deadline` and no write; otherwise one `bucket.write(name, data, if_generation_match=0, timeout=left, retry=None)`. A raise (a `GenerationMismatch` when the object exists, any other exception) fails that ticker with `f"{type(exc).__name__}: {exc}"`, and the next ticker continues. `execution` and `task_attempt` come from `env['CLOUD_RUN_EXECUTION']` and `env['CLOUD_RUN_TASK_ATTEMPT']`, None when unset. The log lines are the Global Constraints ones.

- [ ] **Step 1: Write the failing test** `test_the_record_step_is_bounded`: a clock returning, per call, `0.0` (start), `1.0`, `4.0`, `11.0`; three reads for SPY, QQQ, IWM; `MemoryBucket`. Assert two writes, with `timeouts == [9.0, 6.0]` (each at most what was left of 10) and `retries == [None, None]`, IWM in the failures with reason `deadline`, IWM's name never in `bucket.writes`, and an ERROR record `as_read_failed ticker=IWM reason=deadline`.
- [ ] **Step 2: Write the Review Focus test** `test_two_runs_on_one_date_keep_both_objects`: one bucket, SPY written by two calls whose `fetched_at` differ by an hour; both names exist, each with its own bytes.
- [ ] **Step 3: Write** `test_write_records_counts_each_failure`: `fail_write` raising `OSError('boom')` for the QQQ name: SPY and IWM written, QQQ failed with `OSError: boom`; a pre-existing object at SPY's name (`bucket.put`): SPY failed with a `GenerationMismatch` reason and its bytes unchanged; a factory raising `RuntimeError('GCS_BUCKET is not set: ...')`: three failures, no write. Every write in `bucket.preconditions` has `if_generation_match` 0.
- [ ] **Step 4: Write** `test_gcs_bucket_write_passes_timeout_and_retry_only_when_given(gcs)` in `tests/gcp/test_export_intraday_bars.py`, on the existing `gcs` fixture's fake client: `GcsBucket('b').write('x', b'{}', if_generation_match=0)` uploads with kwargs exactly `{'if_generation_match': 0}` (the export's writes keep the library's defaults); `write('x', b'{}', if_generation_match=0, timeout=3.0, retry=None)` uploads with `{'if_generation_match': 0, 'timeout': 3.0, 'retry': None}`.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_fetch_premarket_refresh.py -k "bounded or two_runs or counts_each" -q` and `python3 -m pytest tests/gcp/test_export_intraday_bars.py -k timeout_and_retry -q`. Expect FAIL. Implement the interfaces (the `MemoryBucket` change is Choice 4). Run both again (expect pass), then `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect all pass, the existing tests unedited).
- [ ] **Step 6: Render step, then commit** `feat(fetchers): write the as-read records once each, within a deadline`.

## Task 4: The refresh job records SPY, QQQ and IWM after its upsert

Spec: Design 1, Design 3, Design 4. Advances R3 (both tests), R4, R5 (`test_a_retryable_upload_error_stays_inside_the_deadline`), R6 (`test_an_empty_fetch_is_still_recorded`), and the record half of R2.

**Files:** Modify `gcp/fetchers/fetch_premarket_refresh.py` (`compute_premarket_for_ticker` `:184-215`, `main` `:409-471`); Test `tests/gcp/test_fetch_premarket_refresh.py`, `tests/gcp/test_premarket_as_read.py`.

**Interfaces:**
- Consumes: `AS_READ_TICKERS`, `AS_READ_DEADLINE_S`, `AsRead`, `write_records`, `snapshot_record`, `read_record` (Tasks 2 and 3); `minute_bars_request`, `av_listed_symbol` (Task 1, `fetch_market_data.py:76`).
- Produces: `compute_premarket_for_ticker(ticker, fetch_date, api_key, *, level_params=None, on_read: Optional[Callable[[str, pd.DataFrame, datetime], None]] = None)`, calling `on_read(ticker, df, fetched_at)` once, right after `fetched_at` is taken (`:205`) and before the empty-frame return (`:206-208`) and the failed prior-session lookup's return (`:210-215`), so both reads are recorded (spec Design 1). `_as_read_bucket()` (Choice 3).
- Produces, in the test file: `_run_refresh(monkeypatch, *, bars_for, tickers=('SPY', 'QQQ', 'IWM', 'AAPL'), prior_for=None, bucket=None, env=None) -> tuple[Optional[int], list[dict], list[str]]`: sets `sys.argv` to `--tickers <tickers> --date 2026-11-16`, `ALPHA_VANTAGE_API_KEY=TEST-KEY-not-real`, patches `fetch_market_data.fetch_minute_data` (from `bars_for`), `fpr._prior_session_from_db` (`prior_for(ticker)` when given, which may raise; otherwise close 750.0, open 749.0, `atr_14` 10.0, `atr_5` None for every ticker), `fpr.read_level_params_for_run` (returns `{}`), `fpr.datetime` (a frozen clock at 2026-11-16 13:20:01.123456 UTC, as `test_compute_logs_the_newest_premarket_bar` does at `:318-323`), `fpr.upsert_premarket` (records its rows and appends `'upsert'` to an event list), and `fpr._as_read_bucket` when `bucket` is given (its `before_write` appends the name to the same event list). Returns the `SystemExit` code or None, the rows, the events.

- [ ] **Step 1: Write the failing test** `test_run_records_what_each_of_the_three_tickers_read`: R1's four bars for every ticker. With a `MemoryBucket`: exactly three objects, `premarket-as-read/v1/2026-11-16/<T>/20261116T132001123456Z.json.gz` for SPY, QQQ and IWM, none naming AAPL; `bucket.preconditions` all 0; `'upsert'` precedes every write in the events; each decoded record's `fetched_at` equals the `pre_fetched_at` bound for that ticker (as ISO text) and its `snapshot` equals `snapshot_record(<that ticker's bound row>, fpr._UPSERT_KEYS)`. A second run with `GCS_BUCKET` deleted and `_as_read_bucket` unpatched binds rows equal to the first run's (it exits 1, Step 4).
- [ ] **Step 2: Write the failing test** `test_a_failed_prior_session_lookup_is_still_recorded` (R3): the same run (SPY, QQQ, IWM, AAPL, a `MemoryBucket`) with `prior_for` raising `RuntimeError('prior lookup down')` for QQQ only. QQQ's object exists at its name, its precondition is 0 and `'upsert'` precedes its write in the events; `read_record` of it returns the four bars QQQ's fetch returned, and its `snapshot` is null; no row bound to `upsert_premarket` has `ticker` QQQ; SPY and IWM are recorded as in Step 1; the run returns None (a failed lookup does not set the exit code today, `:210-215`, and the record step adds no failure).
- [ ] **Step 3: Write the failing test** `test_an_empty_fetch_is_still_recorded` (R6): a run of SPY, QQQ and IWM (`tickers=('SPY', 'QQQ', 'IWM')`) against a `MemoryBucket`, SPY's fetch `pd.DataFrame()` with no columns, the shape `fetch_minute_bars` returns when the vendor has no bars, and QQQ's and IWM's R1's four bars. SPY's object exists at its name, its precondition is 0 and `'upsert'` precedes its write; it has `bar_count` 0 and `snapshot` null; no row bound to `upsert_premarket` has `ticker` SPY; QQQ and IWM are recorded; the run returns None.
- [ ] **Step 4: Write the failing test** `test_a_failed_record_write_fails_the_run_after_the_upsert`, three cases: `fail_write` raising for the QQQ name; `GCS_BUCKET` unset; SPY's object put in the bucket before the run. In each: `upsert_premarket` was called once with rows for all four tickers; the tickers not failed have their objects; one ERROR line `as_read_failed ticker=<T> reason=` per failed ticker naming its error; the exit code is 1.
- [ ] **Step 5: Add the record half of R2** to `test_record_carries_the_request_as_sent`: drive `_run_refresh` with a bucket, decode SPY's object, assert `vendor_params == minute_bars_request('SPY', '2026-11')`, and that `'TEST-KEY-not-real'` and `'apikey'` appear nowhere in the decoded JSON text.
- [ ] **Step 6: Write the failing test** `test_a_retryable_upload_error_stays_inside_the_deadline` (R5), through the real `GcsBucket.write` (Choice 7). One clock holding `t = 1000.0`; `time.monotonic` returns `t` and `time.sleep(s)` appends `s` to `sleeps` and adds it to `t`, both patched on the `time` module. `google.cloud.storage.Client` is patched to return `storage.Client(project='test-project', credentials=AnonymousCredentials(), _http=_Answer503())`, the real class captured before the patch; `_Answer503` is a `requests.Session` with `is_mtls = False` whose `request(method, url, **kw)` appends `(method, url, kw['timeout'])` to `calls` and `'request'` to `_run_refresh`'s event list, adds `kw['timeout']` to `t`, and returns a `requests.Response` with status 503, a JSON error body and its request set. Run `_run_refresh(monkeypatch, bars_for=<R1's bars>, tickers=('SPY', 'QQQ', 'IWM'), env={'GCS_BUCKET': 'test-bucket'})` with `_as_read_bucket` unpatched. Assert: `'upsert'` precedes `'request'` in the events; `calls` holds one POST, SPY's upload, given timeout 10.0 (all of the deadline: nothing moved the clock before it); `sleeps == []`; ERROR lines `as_read_failed ticker=SPY reason=ServiceUnavailable: ...`, `as_read_failed ticker=QQQ reason=deadline` and `as_read_failed ticker=IWM reason=deadline`; `t - 1000.0 <= AS_READ_DEADLINE_S`; the exit code is 1.
- [ ] **Step 7: Run** `python3 -m pytest tests/gcp/test_fetch_premarket_refresh.py tests/gcp/test_premarket_as_read.py -q`. Expect the new tests to FAIL (no objects, no request).
- [ ] **Step 8: Implement.** `compute_premarket_for_ticker`: the `on_read` call as above. `main()`: a dict `reads`, and a collector passed as `on_read` that keeps `AsRead(df, fetched_at, minute_bars_request(av_listed_symbol(tk), target.isoformat()[:7]))` for a ticker in `AS_READ_TICKERS`; after `upsert_premarket` returns (`:468`), `write_records(_as_read_bucket, target, reads, {t: snapshot_record(by_ticker.get(t), _UPSERT_KEYS) for t in reads})` with `by_ticker = {r['ticker']: r for r in rows}`, so a ticker with no row gets `snapshot` null; then `sys.exit(1)` when there is a failure or `params_failed`. Nothing before the upsert changes.
- [ ] **Step 9: Run** the Step 7 command (expect all pass) and `python3 -m pytest tests/gcp -q -k premarket` (expect all pass). Then show that Step 6 has teeth: with `retry=None` taken out of `write_records`' write call, so the library's default retry applies, Step 6 fails (Choice 7's run: 8 requests, 19 sleeps, `RetryError` after 245.9 s on the fake clock). Paste that output into the PR body as its red record and put the argument back.
- [ ] **Step 10: Render step, then commit** `feat(fetchers): record SPY, QQQ and IWM premarket bars as each refresh read them`.

## Task 5: The comparison

Spec: Design 5. Advances R7 (`compare_bars`).

**Files:** Modify `gcp/fetchers/premarket_as_read.py`; Test `tests/gcp/test_premarket_as_read.py`.

**Interfaces:** Produces `compare_bars(as_read: pd.DataFrame, stored: pd.DataFrame, session_date: date) -> dict`. `as_read` is `read_record`'s frame; `stored` has `ts` as aware UTC instants and the five value columns. Returns the eleven counts `as_read_bars`, `stored_bars`, `matched`, `only_as_read`, `only_stored`, `differing`, `differ_open`, `differ_high`, `differ_low`, `differ_close`, `differ_volume`, and `premarket` holding the same eleven for bars in `eastern_bounds_utc(session_date, time(4, 0), time(9, 30))`. Raises `ValueError` for `session_date < TRUE_UTC_FROM`. As-read stamps go through `eastern_index_to_utc`; the stored session filter is `market_date(ts) == session_date` and `ts <= newest as-read instant`.

- [ ] **Step 1: Write the failing test** `test_compare_counts_differing_bars`: R1's four bars as read; stored, as UTC: 08:59Z (only stored), 09:00Z equal to 04:00, 09:02Z with low 749.74 and volume 7151 (others as 04:02), 09:03Z with close 752.25 (others as 04:03), 09:04Z (after the newest as-read bar). Assert the spec's counts: `as_read_bars 4, stored_bars 4, matched 3, only_as_read 1, only_stored 1, differing 2, differ_open 0, differ_high 0, differ_low 1, differ_close 1, differ_volume 1`; and the `premarket` block (the 08:59Z bar is 03:59 Eastern): `as_read_bars 4, stored_bars 3, matched 3, only_as_read 1, only_stored 0, differing 2, differ_open 0, differ_high 0, differ_low 1, differ_close 1, differ_volume 1`. A price 0.00004 apart is not a difference; 0.00005 is.
- [ ] **Step 2: Write** `test_compare_refuses_a_session_before_true_utc`: session 2026-09-25 raises ValueError naming `TRUE_UTC_FROM`.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_premarket_as_read.py -k compare -q` (expect FAIL), implement, run again (expect pass).
- [ ] **Step 4: Render step, then commit** `feat(fetchers): compare an as-read record with the stored bars`.

## Task 6: The read-only command

Spec: Design 5, "Command"; decision 5. Advances R7 (`::test_compare_cli_is_read_only`).

**Files:** Modify `gcp/fetchers/premarket_as_read.py` (`main(argv: Optional[list[str]] = None) -> int` and the `__main__` guard); Test `tests/gcp/test_premarket_as_read.py`.

**Interfaces:** `python -m gcp.fetchers.premarket_as_read compare --as-read FILE (--stored-csv FILE | --bars-root DIR)`. `--stored-csv` reads `ts,open,high,low,close,volume` (Choice 5); `--bars-root` reads the record's ticker and month through `export_intraday_bars.read_bars(root, ticker, month, month)` (`:577`). Prints `json.dumps(result, sort_keys=True)` as one line; exit codes per Choice 6.

- [ ] **Step 1: Write the failing test** `test_compare_cli_is_read_only`: write Task 5's record and stored CSV (with `+00:00` offsets) to `tmp_path`; run `subprocess.run([sys.executable, '-m', 'gcp.fetchers.premarket_as_read', 'compare', '--as-read', rec, '--stored-csv', csv], cwd=<repo root>, capture_output=True)`; assert return code 0 and `json.loads(stdout)` holds Task 5's counts. A record with one byte of `bars_csv` changed: return code 2. A subprocess `python -c "import sys, gcp.fetchers.premarket_as_read as m; m.compare_bars; print('requests' in sys.modules, 'gcp.database' in sys.modules)"` prints `False False`.
- [ ] **Step 2: Write the Review Focus test** `test_compare_cli_refuses_a_naive_stored_ts`: the same CSV without offsets: return code 2, empty stdout, stderr naming `ts`.
- [ ] **Step 3: Run** (expect FAIL), implement, run again (expect pass).
- [ ] **Step 4: Render step, then commit** `feat(fetchers): a read-only command to compare an as-read record`.

## Task 7: Close: product record, site note and the gate

Spec: done_when R9; Capacity; Close-out; product-delivery Phase 4 and Phase 5. Closes R9. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

- [ ] Run `make test` on the head; paste the summary line into the PR body.
- [ ] Push with `git push -u origin feature/feat-data-001-premarket-reads-as-read` and open a **draft** PR titled as in Global Constraints. Body: the spec's and this plan's paths; R1 to R9 as `- [ ]` lines; `Red then green`; the Capacity section with the three object sizes Task 2 Step 6 measured and "3 bucket writes a run, 6 a day once the 09:20 run is deployed"; this plan's "Choices" list.
- [ ] Set `pr:` in this plan to the PR's number and commit it.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record (`:513` on 44dfa3d8c): append this PR to its Status text (implementation under review, not deployed) and set Last reviewed to the date of the PR's head commit. `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-DATA-001` (`:320`): append the PR to its PR lineage, naming spec PR #2026. Commit: `docs(product): record the premarket as-read bars under FEAT-DATA-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-DATA-001 | DASHBOARD-01 |` row (`:1309` on 44dfa3d8c) and no other byte: `source_identity_sha256=<the hash>; `, then this change's prose (each `fetch-premarket-refresh` run writes the SPY, QQQ and IWM one-minute bars as it read them to `premarket-as-read/v1/` after its upsert, and exits 1 when a record fails; `python -m gcp.fetchers.premarket_as_read compare` reads one back; the brief's values are unchanged; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the premarket as-read bars on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, update the branch by merge (never rebase), re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence; only then mark the PR ready. No gate file is touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out and decision 6. None is done by the implementer and none is a done_when box.

- Deploy `fetch-premarket-refresh` from `main` after the merge (`./gcp/deploy.sh market-data`), then check the next scheduled morning: three objects under that date's prefix and the three INFO lines in the run's log. If the service account cannot write the prefix, every run exits 1 after its upsert from that morning (R4 is that behaviour); the brief is unaffected.
- After 20 sessions of 08:20 records (60 objects), run the comparison over all of them and repeat the thin-bar and prior-close measurements on the as-read bars; any rule change is its own spec (decision 6).
- On a `docs/` branch after the merge: this plan's `status: done`.
