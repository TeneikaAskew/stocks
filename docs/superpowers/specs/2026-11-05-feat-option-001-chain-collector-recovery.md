---
feat_id: FEAT-OPTION-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-GOV-001]
issues: [1259]
canvases: []
done_when:
  - "Partial-chain collector tests prove calls-only and puts-only success responses fail before persistence and fail the job with a typed incomplete_chain error, with the side check applied to the final normalised write payload so a fixture in which normalisation removes the last contract of one side also fails typed with no persistence; caplog tests with a sentinel apikey in a raised requests exception URL and a sentinel vendor Information body prove neither the key nor the vendor text reaches any log record or exit message; actual PostgreSQL tests prove skip-existing and resume cursors require both sides."
  - "Actual PostgreSQL tests prove unavailable date markers block older snapshots; all writes of the exact write set (etf_options_snapshots, gamma_levels_eod, markers, daily_vex, options_daily_features, etf_options_daily_greeks, every strat_features_<tf> in strat_data_builder.TF_LIST, the options_partition_revisions row and the manifest rows) run in one transaction on one recovery-owned connection; a failure injected in the final strat_features_<tf> write leaves every table and the ledger byte-identical to the pre-run copy, verified from a second connection; recovery removes obsolete markers; repeated bounded backfills converge with published_at unchanged; and for every table in TF_LIST the next-session row count equals the session's bar count for that timeframe with non-null gamma context on every row (78 for 5m)."
  - "Publication-boundary tests prove the two-phase published_at: with an open recovery transaction a cutoff C read on a second connection is unavailable at every later wall time; after phase 1 commits, published_at IS NULL is unavailable; after phase 2 stores P, as_of = P is visible, P - 1 microsecond is unavailable and C < commit-return <= P is recorded; phase 2 is idempotent on retry; unreadable, missing or conflicting ledger metadata is unavailable; every refusal path makes zero recovery mutations and leaves pre-existing and competitor rows intact."
  - "Complete-result validation tests prove that an as-of reader validates, in the same database snapshot that selects the data, the complete live key set and (table, pk, content hash) tuples of every consumed partition against the recorded revision: a changed value under an unchanged key, a new key, a resurrected deleted key and a key/payload reassignment, each committed before the reader's snapshot starts, yield unavailable(unrecorded_mutation) with no partition data; a competing commit interleaved after the reader's snapshot has started is invisible to that snapshot, so the reader returns exactly the data it validated and never the later values, while a reader that cannot hold one snapshot across validation and selection returns unavailable(unrecorded_mutation) with no data; current reads show the later values; ledger and manifest rows are byte-identical; an unchanged-content retry is a no-op with zero writes and a changed-content retry refuses with zero recovery mutations."
  - "Manifest binding tests prove tampering, dangling, missing, extra, deleted and visibility-atomicity cases fail as specified and that completeness holds over rewritten, no-op and deleted dispositions; recomputing run_id from the run_header stored on the ledger row, manifest_sha256 from the stored entries and every content_sha256_after from the archived source bytes reproduces the stored values, after the recovery process has exited and from the ledger alone."
  - "A two-connection PostgreSQL test inserts and commits an October 8 row for the repaired ticker on a second connection after the repair has validated scope and before it writes; the repair aborts with a typed scope error, every table in the write set equals its pre-run copy plus the competitor's committed row, and the competitor's row is never deleted or overwritten."
  - "Negative recovery fixtures (manifest hash mismatch, duplicate (ticker, snapshot_ts, option_type, expiration, strike) with differing values, non-finite or out-of-range rate, unknown column) each make the recovery exit nonzero before any write, with the write set unchanged in PostgreSQL."
  - "Precondition for the live recovery: every as-of reader adapter (the Options-owned readers and the Briefing, Insights, Signals and STRAT readers) is merged, qualified and deployed: the recovery PR body lists each adapter by PR number and merge SHA together with the deployed image digest of every Cloud Run job and service that runs that reader, read with gcloud run jobs describe or gcloud run services describe and shown to contain the adapter's merge commit, and records that no execution of a pre-adapter image is running or pending; the recovery refuses to run while any listed adapter is absent, any reader job still pins a pre-adapter digest, or any pre-adapter execution is still running."
  - "Affected tests pass; normal current-head CODE review, required CI, own catalog/PR records, actual BASE gate and branch-versus-main documentation audit pass without waivers; the post-merge close-out records source commit, image digest, provider receipts, dry-run, the committed recovery, the ledger row and published_at, the manifest export hash, and the 12-hour cache wait described below before the repaired date is declared served."
status: approved
supersedes: null
---

# Collector both-sides refusal, revision ledger and bounded October 8 recovery

## Decision and lineage

This specification is the second half of the bounded gamma-chain repair the owner approved on
October 13, 2026 ("Fix it") and first specified in PR #1490 as one contract. On November 5, 2026
the owner decided to deliver that repair as two parts: the unavailable-semantics part
(`docs/superpowers/specs/2026-11-05-feat-option-001-partial-chain-unavailable-api.md`) and this
part (collector refusal, the revision ledger and the bounded recovery). The owner approved the
additive ledger table `options_partition_revisions` (proposal P-DATA-002) as the way this
specification meets REQ-DATA-002 and REQ-DATA-003, decided that the API's in-process 12-hour
caches are waited out rather than probed for the repaired date (X8), and kept the question of
making later writers revision-aware (X9) out of scope. The first Codex review of #1490 raised ten
findings; every one is carried here or in the first part, and no requirement or original
acceptance item is dropped.

## Problem

At 2026-10-09 01:01 UTC, HISTORICAL_OPTIONS returned only 6,580 SPY and 2,874 IWM contracts for
October 8. The collector stored exactly those counts and reported success. The database contains
only calls for those two snapshots. Current authenticated refetches return 13,160 SPY and 5,748
IWM rows with both sides. The original raw responses were not retained; logs establish received
and persisted counts, not the vendor's reason for incompleteness. October 9 feature rows use
October 8 inputs and have 0 of 78 flips per affected ticker. The collector's diagnostics can log
a `requests` exception string that carries the request URL with `apikey`, and the
unexpected-response branch logs vendor-controlled `Information` text verbatim. The collector also
drops duplicate contract keys silently (`drop_duplicates(keep='last')`).

Repairing October 8 in place has a second problem: a replay run with an as-of clock of October 10
would read the refetched puts that did not exist on October 10, which REQ-DATA-002 forbids, and no
derived table today carries the source, pipeline, configuration or code identity REQ-DATA-003
requires. Five writers touch the repaired partitions afterwards (REALTIME retention, the nightly
`gamma_levels_eod` rebuild, the feature builders, the monthly HISTORICAL backfill, and the
recovery's own re-run), so no per-row column on the derived tables can carry a revision mark
through all of them.

## Design

1. **Both sides before persistence.** The EOD collector requires both call and put contracts
   in the final normalised write payload, checked immediately before persistence (normalisation
   coerces invalid strikes and drops rows missing a type, expiration or strike, so a response
   with both raw types can still become one-sided). A one-sided payload raises a typed
   `incomplete_chain` error; `main` records the failure and exits nonzero. A regression fixture
   in which normalisation removes the last contract of one side must fail the same way with
   no persistence. Existing HTTP and
   no-data handling is preserved, except that no diagnostic message may contain a
   credential-bearing exception URL or vendor-controlled text: the HTTP-exception path and the
   unexpected-response path log a fixed safe reason. No automatic retries or new API calls.
   Duplicate `(ticker, snapshot_ts, option_type, expiration, strike)` keys with differing values
   are a refusal, never a silent dedupe.
2. **Cursors need both sides.** An existing EOD date is skipped only when both calls and puts are
   present. Resume watermarks derive from dates with both sides. Historical gaps behind a later
   complete watermark require an explicit bounded date repair.
3. **Unavailable markers.** The recovery emits a nontradable unavailable date marker keyed to an
   actual source strike, with a `level_kind` the nightly builder never writes so a rebuild cannot
   overwrite it. Markers are removed on a later successful recovery of the same partition.
4. **Revision ledger (P-DATA-002, approved).** One additive table, written only by the recovery
   and read by every as-of reader:

   ```sql
   CREATE TABLE IF NOT EXISTS options_partition_revisions (
       ticker                   VARCHAR(10)  NOT NULL,
       snapshot_date            DATE         NOT NULL,
       run_id                   CHAR(64)     NOT NULL,   -- sha256 of run_header
       run_header               JSONB        NOT NULL,   -- the canonical run header (design 5), verbatim
       captured_at              TIMESTAMPTZ  NOT NULL,   -- vendor bytes captured
       computed_at              TIMESTAMPTZ  NOT NULL,   -- derived rows computed (informational)
       published_at             TIMESTAMPTZ,             -- NULL until phase 2; the only as-of boundary
       partition_content_sha256 CHAR(64)     NOT NULL,   -- over the sorted per-row content hashes
       manifest_sha256          CHAR(64)     NOT NULL,   -- over the canonical manifest entries
       PRIMARY KEY (ticker, snapshot_date, run_id)
   );
   CREATE TABLE IF NOT EXISTS options_recovery_manifest (
       run_id               CHAR(64)  NOT NULL,
       table_name           TEXT      NOT NULL,
       pk_json              TEXT      NOT NULL,          -- full primary key, canonical column order
       disposition          TEXT      NOT NULL,          -- rewritten | no_op | deleted
       content_sha256_before CHAR(64),
       content_sha256_after  CHAR(64),
       source_identity      JSONB     NOT NULL,          -- endpoint, parameters, byte sha256, captured_at
       pipeline             TEXT      NOT NULL,          -- module path and git commit
       configuration_sha256 CHAR(64)  NOT NULL,
       model_rule           TEXT      NOT NULL,
       artifact_sha256      TEXT      NOT NULL,
       code_identity        TEXT      NOT NULL,          -- image digest
       PRIMARY KEY (run_id, table_name, pk_json)
   );
   ```

   Both tables are added to `gcp/schema.sql` and applied through the existing
   `apply-schema-migrations` job; no other schema, scheduler, IAM or bucket change. The ledger
   survives the five writers because none of them touches these tables.
5. **Run identity and canonical hashing.** `run_id` is the sha256 of the canonical JSON of the run
   header: the specification path and blob OID, the recovery entrypoint's module path and git
   commit, the image digest, the resolved configuration hash, the scope (tickers, source dates,
   dependent dates, tables), and for each source capture its endpoint, parameters, byte sha256
   and `captured_at`, plus each fixture's sha256. It excludes `computed_at`, `published_at`,
   every manifest entry, every row content hash, `manifest_sha256`, `partition_content_sha256`
   and itself, so a retry with the same inputs is the same run. The canonical header is stored
   verbatim in the ledger row's `run_header` column, written in the same transaction as the row,
   and copied into the manifest export, so `run_id` can be recomputed and verified from the
   ledger alone after the process has exited; a retry reads the stored header to decide that it
   is the same run. `manifest_sha256` is the sha256
   of the canonical JSON of the manifest entries sorted by `(table_name, pk_json)`. Canonical
   JSON is RFC 8785 style: UTF-8, keys sorted bytewise, no insignificant whitespace,
   `NULL`/`NaN` as `null`, floats as shortest round-trip repr, `TIMESTAMPTZ` as RFC 3339 UTC with
   microseconds, `DATE` as `YYYY-MM-DD`, bytes as lowercase hex. The per-row content hash covers
   the non-key columns in sorted column order.
6. **Two-phase publication boundary.** PostgreSQL `now()` is the transaction start and
   `clock_timestamp()` before COMMIT precedes the commit; the exact commit instant needs
   `track_commit_timestamp`, a Cloud SQL flag not proposed here. Phase 1 (the recovery
   transaction) writes the data, the ledger row with `published_at = NULL` and the manifest rows,
   then commits; from that instant current reads see the repaired data and every as-of read sees
   the partition as unavailable. Phase 2, one short transaction opened only after phase 1's
   commit has returned to the client, runs
   `UPDATE options_partition_revisions SET published_at = clock_timestamp() WHERE ... AND published_at IS NULL`,
   so `published_at` is at or after the true commit instant (conservative) and the update is
   idempotent. If the job dies between the phases, the close-out re-runs phase 2 only.
7. **One transaction, one connection.** Every write of the exact write set, the ledger row and
   the manifest rows run inside one database transaction on one connection the recovery owns.
   The recovery does not call the nightly builders, whose own `engine.begin()` blocks commit
   independently; independent committed steps followed by convergence are not atomic. Where a
   table's existing write path (`bulk_copy_upsert`, chunk-committing `upsert_dataframe`) cannot
   run inside a caller-owned transaction, the recovery uses a recovery-only write routine for
   that table that accepts an open connection. Scope is validated and locked inside the same
   transaction; a competing committed row between validation and write aborts the run with a
   typed scope error and leaves the competitor's row in place.
8. **Exact write set.** `etf_options_snapshots` (October 8, both sides), `gamma_levels_eod`
   (October 8), `daily_vex` (October 8), `options_daily_features` (October 8),
   `etf_options_daily_greeks` (October 8), and the October 9 rows of every `strat_features_<tf>`
   in `strat_data_builder.TF_LIST` (1m, 5m, 15m, 30m, 60m, 4h). `daily_vex` is cache-only in
   both builders and never recomputes a stored date; the two materialised tables are rebuilt only
   inside a 7-day incremental window; all three are therefore rebuilt explicitly here.
9. **Manifest binding (REQ-DATA-003).** One manifest entry per record the recovery touches or
   decides not to touch, with the full primary key, disposition (`rewritten`, `no_op`,
   `deleted`), canonical content hashes before and after, source identity and capture clock,
   pipeline and code identities, configuration hash, rule identity and artifact hashes, written
   as rows in the recovery transaction and exported to GCS afterwards with an equal sha256.
10. **As-of visibility (REQ-DATA-002).** A shared helper
    `lib.options_revisions.revision_visible(ticker, snapshot_date, as_of) -> Visibility`, where
    `Visibility` is `visible` or `unavailable(reason)`, never a bare boolean. A reader that
    evaluates an as-of clock treats a repaired partition as unavailable when
    `as_of < published_at` or `published_at IS NULL`, when the ledger is unreadable, missing or
    conflicting, and, inside the one consistent snapshot (`REPEATABLE READ` or one statement)
    that also selects the data, whenever the complete live key set and
    `(table, pk, content hash)` tuples of any consumed partition differ from the recorded
    revision or a recorded deletion is present again (`unavailable(unrecorded_mutation)`), with
    no partition data returned. Pre-repair rows are not reconstructed; the only honest answer for
    an earlier as-of clock is unavailable. Current reads are unchanged and consult no ledger.
    Options-owned readers adopt the helper in this part; the Briefing, Insights, Signals and
    STRAT readers receive a precise proposal and adopt it in their own PRs, and every adapter
    lands, qualifies and is deployed before the live recovery runs (done_when item 8): a merged
    adapter does not change a running reader, because `gcp/deploy.sh` pins each job to a build
    digest until that job is redeployed, so the precondition is the deployed image digest of every
    reader job and service, not the merge alone, plus the completion or termination of every
    execution still running a pre-adapter image.
11. **Later writers (X9 out of scope).** A later writer that touches a repaired partition
    (monthly backfill, nightly rebuild, feature rebuild) is not made revision-aware here. Its
    first write after a repair is an unrecorded mutation and fails as-of reads of that partition
    closed, which is correct and keeps the repaired partition's as-of visibility bounded to the
    interval before the next such write. The owner may revisit this separately.
12. **Caches (X8).** The API's in-process caches (`_CHAIN_CACHE` and the historical grid and
    nodes caches, 12-hour TTL) can serve a pre-repair payload for the repaired date after
    `published_at`. This specification adds no cache probe: the close-out declares the repaired
    date served only after twelve hours have elapsed since `published_at`, or after an API
    revision restart, and verifies the served payload against the ledger at that point.
13. **Fixtures.** Captured fixtures are packaged portably with hashes and revised-history
    timestamps; no production credential is a fixture; measured historical rate inputs are used
    for operational reconstruction, with local fixed-rate controls identified as test
    assumptions.

## Bounded operational recovery and capacity

Initial scope: IWM and SPY EOD October 8 and the dependent October 9 gamma context. Two provider
calls; 18,908 returned records. Existing tables and jobs are retained; the two ledger tables are
the only schema change. Archive the refetch bytes, hashes, capture times and an exact pre-write
backup; session snapshot markers are not fetch-availability timestamps. New source rows retain
current insertion time and derived rows current computation time; `captured_at` comes from the
archived capture record and `published_at` from phase 2. Recovery is revised historical data,
never a claim that the missing puts were available originally.

Compute and test the exact write set before committing it. Validate source hashes, both sides,
unique keys, measured rates, expected existing scope and unchanged unrelated rows. Dry-run first
with rollback; the real-PostgreSQL verification exercises the same bounded transaction. A resumed
invocation recomputes the same `run_id`, compares the complete partition tuples, and is a no-op
on equal content or a refusal with zero recovery mutations on different content; re-publishing
over a later writer's rows is a new, owner-authorised run with a new capture.

- Volume: raw JSON at a conservative 1 KiB per record is under 19 MiB; the write set is 18,908
  source rows plus tens of level rows, three single-row daily tables, and one session of feature
  rows per timeframe for two tickers; double and quadruple copies plus the largest
  Black-Scholes vector grid fit within 512 MiB (measure the actual working set in the intended
  image). The ledger adds two rows and about 19K manifest rows.
- Velocity: batch writes, never per-row round trips; at most 60 application round trips at 2 s
  each plus 60 s of local calculation and serialisation, about 180 s; phase 2 is one further
  statement.
- Wall-clock: existing task-timeout of at least 720 s, or reduce the measured path before
  execution; one-off execution bounded to two tickers, one source date, one dependent session.
- Cost: one-off execution, no recurring spend; the two provider calls are within the existing
  plan; record the actual resource sizing and cost estimate before launch. $0 per month ongoing.

## Non-goals

No gamma, Greeks, valuation or strategy formula change; no cadence or freshness classifier; no
scheduler, IAM, bucket policy or model-promotion change; no change to the API's unavailable
semantics (first part); no revision-awareness for later writers (X9); no cache probe (X8); no
`track_commit_timestamp` flag. The historical gap is not issue-wide options or UI remediation
completion, and recovery of other one-sided partitions is a separately authorised run.

## Delivery and close-out

The code branch (`feature/feat-option-001-chain-collector-recovery`) uses this immutable
main-approved specification and one ready plan, opened only after this specification is on
`main`. The first part merges first where the two share `platform/api/schemas.py`; this part
rebases onto it. The ready plan folds each acceptance test into the task that implements the
behaviour it proves so the plan stays near the fifteen-task guideline; if it cannot, the owner
decides on a further split before implementation begins. Existing protected files, pins and
specifications remain untouched; only after the separately reviewed source-identity verifier is
on `main` may declared implementation-source note rows be used.

Post-merge close-out records the actual source commit and image digest, the narrow job
deployment, provider receipts, the dry-run, the committed recovery with its `run_id`, ledger row,
`published_at` and manifest export hash, the downstream tables and API after the twelve-hour
cache wait, and unchanged-scope comparisons. Never tick a deployment claim from local tests.
Keep the original source-provider root cause and the historical-as-available limitation explicit.
