---
feat_id: FEAT-CATALYST-001
req_ids: ["REQ-DATA-001", "REQ-DATA-002", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-OBS-001", "REQ-SECRET-001"]
issues: []
canvases: []
done_when:
  - "tests/integration/test_av_catalyst_producer_writes.py::test_actual_estimates_daily_writer_publishes_selected_receipts_and_pending_scope executes the actual daily main/CLI producer against PostgreSQL, persists nonempty and validated-empty captures, full/selected/pending scope, immutable observations and acknowledged publication/terminal linkage without inventing empty fiscal rows."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_actual_estimates_uncertain_publication_never_certifies_availability proves native producer failure/uncertainty preserves committed observations but omits acknowledged availability; missing, future and conflicting publication identities cannot certify coverage."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_actual_estimates_group_retains_full_native_payload_and_retry_identity proves complete native field/horizon retention and unchanged observation identity/proposed transaction clock and separate durable post-source-ACK receipt clock when replaying nonempty and validated-empty captured responses; a cutoff between proposed observation clock and actual source ACK cannot certify availability."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_actual_history_cli_emits_daily_and_weekly_full_scope_receipts executes actual native history CLI paths for both variants with real PostgreSQL captures/revisions/independent timing and permanent full configured-denominator and captured observed-cohort manifests, bounded fetching and acknowledged job_runs notes; proves inclusive end-29..end dates (start included, start-1 excluded), <=100 selected from a large configured universe, honest raw refresh partial status, complete reused source-backed observed event assessment with qualified current-revision analytics only; full-current scope stays dependency_pending because this contract has no independent full-cohort proof producer. Unobserved/failed symbols have explicit nullable-evidence reasons; both old and fresh captures cannot become vendor watermarks. A completed selected slice cannot certify unknown required full scope."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_actual_reactions_cli_binds_daily_and_weekly_acknowledged_history executes actual native reaction CLI paths for both variants with the merged DATA basis helper, real source/artifact/derived rows and exact per-event revision/history-manifest linkage; observed-cohort lineage is validated, while full-current admission remains dependency_pending; wrong-scope, missing/future ACK or unproved observed events are refused, without demanding an unavailable global-proof positive path."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_full_scope_manifests_reuse_verified_sources_and_require_acknowledgement passes daily and weekly real SQL cases for full configured denominator and qualified observed-cohort reuse (not full-current completion), separate raw_refresh_pending versus event_pending_count and source_universe_unknown_count, separate calendar universe and actual publication clocks; no helper-only stub can substitute for native CLI producer cases."
  - "tests/gcp/test_fetch_earnings_calendar_persist.py::test_full_feed_archive_preserves_weekly_subset and tests/integration/test_av_catalyst_producer_writes.py::test_actual_calendar_native_capture_publishes_before_business_selection prove complete AV three-month original bytes/native validation and actual acknowledged native-source manifest, retaining the established business selection and qualifying other-feed union as unavailable."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_manifest_identity_collision_cannot_relabel_acknowledged_scope proves an immutable manifest identity cannot advertise a different job, variant, execution or source scope using an old publication clock."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_full_manifest_has_bounded_terminal_reference proves actual1239-symbol manifests/proofs persist in SQL while job_runs.note and identical structured log payload remain <=64KiB with immutable manifest ID/digest/count references; oversized manifests and partial output cannot certify completion."
  - "tests/integration/test_av_catalyst_producer_writes.py::test_reaction_maximum_batched_io_fits_admission runs the actual CLI producer with the merged DATA helper at100tickers x100quarters, bounded10-ticker price batches and100atomic artifact/derived groups; includes all119 network round trips, actual transforms/serialization/setup/final ACK in the <=450second budget and rejects the former100price-query path."
  - "tests/gcp/test_av_catalyst_predecessor_manifests.py::test_scope_hash_known_answers_match_consumer exercises published byte/digest fixtures through actual CAT emitters and separately owned DEPLOY/OPS/OPTION consumer parsers; whitespace/Unicode/date/order/duplicate/type/changed-scope controls fail, with no helper-versus-itself proof."
  - "docs/EARNINGS_PIPELINE.md commits the literal producer schemas/keys/native source choices, existing capacity/cost assumptions and measured commands, staged nullable-to-all-writer-drain-to-online-index-to-final-NOTNULL identity checklist, and merge/schema/deployed-digest/source-receipt activation prerequisites; scratch notes are not canonical repository approval."
  - "The FEAT-CATALYST-001 implementation plan references this complementary merged specification before any additional implementation acceptance work; PR1430 and its own capability/traceability record distinguish implementation verification from pending deployed producer/schema verification, and DEPLOY/OPS activation remains dependency_pending until actual merged code plus the targeted deployed-state verifier prove the producer digest, tables and acknowledged receipts."
status: approved
---

# Publish inspectable AV catalyst producer receipts and scope contracts

## Authorization and compatibility

This complementary specification records the literal existing producer boundary within the user's approved six-stream AV/GCP remediation and approved merge intent. Root owns its separate DOC publication, peer review and merge at `docs/superpowers/specs/2026-10-12-feat-catalyst-001-av-producer-receipts.md`. It does not supersede, replace or edit immutable approved specification1419 (`2026-10-12-feat-catalyst-001-av-catalysts.md`), does not add a job/endpoint/strategy and does not authorize production activation by itself. The existing CAT implementation remains PR1430. Extend its plan only after this complementary specification is merged, before additional acceptance work; keep the existing28clause contract and capacities intact.

Working source for this candidate is CAT1430 checkpoint1dfb5b2ca71e38ac64565154e60c4a553e7d9f0e. The exact30-date single-cutoff emitter, immutable manifest identity collision guard, new-quarter daily selector, native calendar malformed required-value validation and literal runbook are now committed/tested. Explicit joint accounting/unknown-source facts, consumer-required source-cutoff comparisons and the explicit unsupported-independent-proof dependency status below remain required complementary implementation; they are not properties certified by this checkpoint. The publisher must pin the exact committed implementation head when citing evidence; neither this scratch candidate nor any interface-approved scratch filename establishes repository approval or deployed state. Acceptance tests below are requirements, not claims that future/native weekly/positive DATA integration cases have run.

## Problem

DEPLOY predecessor admission and OPS estimates freshness cannot invent producer columns, confuse source retrieval with acknowledged availability, equate a selected100-ticker slice with a configured1239-symbol denominator, or use a calendar business subset as proof of all source coverage. Scratch interface notes are inspectable implementation discussion, but are absent canonical repository approval. A committed literal contract and actual native producer/PostgreSQL proof are needed before consumer admission can be called implemented and before deployed activation.

## Non-goals

No new scheduled job, Sunday-specific CAT CLI guard, schedule/IAM/lifecycle mutation, other-provider migration/archive/callback instrumentation, universal source-all coverage claim, fabricated legacy publication clock, arbitrary full backfill or historical certification from mutable prices. DEPLOY owns runtime schedule/cycle admission and wrapper artifacts; OPS owns monitoring projection and consumer prerequisite qualification. Existing nonAV behavior remains qualified separately. This document does not claim all1430 acceptance or production rollout complete.

## Approaches considered

1. Commit a complementary literal producer contract, reuse existing additive tables/publications and bounded native producers, then require actual implementation/deployed proof: selected.
2. Infer availability from scheduler launches or guessed tables: cannot distinguish missing/partial/uncertain scope and would certify unsupported freshness.
3. Add new source jobs or migrate all providers: exceeds the approved scope and is unnecessary for AV-defined coverage.

## Design

### Additive permanent schema and identities

These are the actual CAT-owned column/constraint choices in `gcp/schema.sql`, not an OPS/DEPLOY-authored projection. Retain the source-scope, manifest-source/publication-clock and estimate-asof indexes shown below and append-only UPDATE/DELETE guards. Existing populated caches and unrelated schema are preserved. Do not auto-finalize source identity constraints or pretend legacy rows contain a receipt.

```sql
CREATE TABLE IF NOT EXISTS av_catalyst_source_captures (
    capture_id UUID PRIMARY KEY,
    function TEXT NOT NULL,
    ticker TEXT,
    source_retrieved_at TIMESTAMPTZ NOT NULL,
    raw_uri TEXT NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    metadata JSONB NOT NULL,
    validation_status TEXT NOT NULL CHECK(validation_status IN ('validated','validated_empty')),
    normalized_count INTEGER NOT NULL CHECK(normalized_count>=0)
);
CREATE INDEX IF NOT EXISTS av_catalyst_capture_scope_idx
    ON av_catalyst_source_captures(function,ticker,source_retrieved_at DESC);
```

```sql
CREATE TABLE IF NOT EXISTS av_catalyst_source_manifests (
    manifest_id UUID PRIMARY KEY,
    job_name TEXT NOT NULL,
    variant TEXT NOT NULL,
    execution_name TEXT NOT NULL,
    manifest JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS av_catalyst_manifest_source_idx
    ON av_catalyst_source_manifests(job_name,variant,execution_name);
```

```sql
CREATE TABLE IF NOT EXISTS av_catalyst_manifest_publications (
    manifest_id UUID PRIMARY KEY REFERENCES av_catalyst_source_manifests(manifest_id),
    known_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS av_catalyst_manifest_known_idx
    ON av_catalyst_manifest_publications(known_at DESC);
```

```sql
CREATE TABLE IF NOT EXISTS av_earnings_estimates_observations (
    observation_id UUID PRIMARY KEY,
    fetch_id UUID NOT NULL REFERENCES av_catalyst_source_captures(capture_id),
    ticker TEXT NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    horizon TEXT NOT NULL,
    known_at TIMESTAMPTZ NOT NULL,
    source_retrieved_at TIMESTAMPTZ NOT NULL,
    raw_uri TEXT NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE(fetch_id,ticker,fiscal_date_ending,horizon)
);
CREATE INDEX IF NOT EXISTS av_estimates_asof_idx
    ON av_earnings_estimates_observations(ticker,fiscal_date_ending,horizon,known_at DESC);
```

The following small additive receipt-publication table is NEW complementary implementation, absent at checkpoint1dfb. Keep append-only guards and the source FK/index. It persists the actual ACK of complete capture+observation source transactions, not a timestamp chosen before those transactions:

```sql
CREATE TABLE IF NOT EXISTS av_estimate_receipt_publications (
    fetch_id UUID PRIMARY KEY REFERENCES av_catalyst_source_captures(capture_id),
    ticker TEXT NOT NULL,
    validation_status TEXT NOT NULL CHECK(validation_status IN ('validated','validated_empty')),
    observation_count INTEGER NOT NULL CHECK(observation_count>=0),
    source_commit_acknowledged_at TIMESTAMPTZ NOT NULL,
    CHECK ((validation_status='validated_empty' AND observation_count=0)
        OR (validation_status='validated' AND observation_count>0))
);
CREATE INDEX IF NOT EXISTS av_estimate_receipt_known_idx
    ON av_estimate_receipt_publications(ticker,source_commit_acknowledged_at DESC);
```

`Capture.observation_id` is the source `capture_id`; estimates `fetch_id` is that same UUID. Estimate observation UUID derives deterministically from fetch identity/fiscal-date/horizon, with ticker bound by the native symbol. `payload` retains every original native estimate field, including revisions/ranges/counts and fiscal-quarter/year distinction. A later retrieval creates a new vintage; replay of one captured response does not create another vintage or rewrite its observation transaction clock. Existing observations.known_at remains its actual proposed insertion/observation clock; it is not called a durable post-observation-commit ACK clock. Permanent SQL payload remains after raw expiry. Horizon validation accepts actual fiscal-quarter/year strings; no SQL enum or additional invented CHECK is claimed.

`av_catalyst_source_captures` has no `known_at` column. Retrieval is an actual completed vendor retrieval clock, not fiscal/report date, request-start time, scheduler launch or publication acknowledgement. Raw URI/SHA256 identify immutable original response capture. `metadata` includes safe parameters, original body digest, query identity and actual code/pipeline identity. Validation `validated_empty` is reserved for a structurally valid native empty response, not a failed request, zero selected business events or a provider error.

### Byte-exact scope and manifest hashing

Protocol `av-catalyst-canonical/v1`: canonical bytes are UTF8 of JSON with dictionary keys sorted by Unicode code point, arrays retaining the prescribed order, separators comma/colon with NO spaces, ensure_ascii=true (nonASCII escaped lowercase \uXXXX; supplementary characters as UTF16 surrogate escape pairs), allow_nan=false and no BOM/trailing newline. Duplicate object keys, nonfinite numbers, implicit/default coercions or unsupported value types refuse validation. Hash is lowercase SHA256 hex over exactly those bytes. Integers are signed64-bit; scope/proof/hash input projections contain no float financial values. Normalize symbols BEFORE hashing to trimmed uppercase ASCII canonical ticker keys, deduplicate/sort ASCII lexicographically. Dates are exact validated YYYY-MM-DD. Proof clocks are explicitly normalized awareUTC strings YYYY-MM-DDTHH:MM:SS.ffffffZ. UUIDs are lowercase canonical hyphenated strings; nullable evidence is JSONnull, never empty string/default0.

Exact field inputs: scope_hash for estimates/calendar and source_universe_scope_hash hash the full configured sorted unique symbol ARRAY; selected_scope_hash hashes the selected sorted unique symbol ARRAY. History/reaction scope_hash hashes expected_events ARRAY of exact {ticker,event_reported_date}, sorted by ticker/date with multiplicity retained; no undocumented string concatenation. Financial revisions are separately bound by source facts, not imputed into the event key. `source_digest_kind=canonical_source_facts/v1` hashes a sorted typed projected ARRAY: history keys ticker,event_reported_date,revision_id,capture_id,source_retrieved_at,known_at,validation_status,yahoo_timing_observation_id; estimate keys ticker,fetch_id,status,source_retrieved_at,known_at,raw_sha256,raw_uri,observation_count; reaction keys ticker,event_reported_date,source_revision_id,input_artifact_sha256,configuration_sha256. Sort each by its identity tuple then canonical bytes as the deterministic tie-break. Omitted fields are not null substitutes: every listed projected key must exist, with declared null only for genuinely absent evidence. Current raw CSV digest is the separately tagged exception `source_digest_kind=raw_body_sha256` and hashes ORIGINAL body bytes directly, never JSON. Every consumer checks the kind and expected projection.

`manifest_sha256` hashes the entire stored SQL manifest JSON under this same protocol; it is returned in terminal references, not inserted into its own hashed body (no self-reference). Publication/terminal reference metadata outside that SQL body is bound by actual manifest identity/ACK. Consumers reserialize the stored full JSON by this protocol, not by default SQL JSONB text spacing. Future implementation must normalize projected clock/types before hashing; current1dfb digest helper is not evidence that all cross-consumer normalizations already exist.

Shared committed known-answer fixture path: tests/fixtures/av_catalyst_scope_vectors.json. CAT emitters and independently owned DEPLOY/OPS/OPTION parsers must each verify these literal bytes/digests plus their endpoint projections without generating expected hashes via the helper under test. Required independent test controls: different symbol/event/selection, duplicate keys, changed ordering, whitespace insertion, nonASCII escape, null/empty/0 distinction and naive clock. Literal vectors below are calculated draft design constants, not executed acceptance evidence:

```json
[
  {
    "kind": "configured_symbols",
    "input": ["AAPL", "MSFT"],
    "canonical_utf8_hex": "5b224141504c222c224d534654225d",
    "sha256": "a1c55462c19f91d1b39e57f5337c6639db0783d72b4671bff74dcc9eabd7c958"
  },
  {
    "kind": "selected_symbols",
    "input": ["AAPL"],
    "canonical_utf8_hex": "5b224141504c225d",
    "sha256": "fcbb30b4ee6baa4d3f82a772009dc5186286d0a0b9be62a6c897abb4e08623e6"
  },
  {
    "kind": "expected_events",
    "input": [{"ticker":"AAPL","event_reported_date":"2026-10-12"}],
    "canonical_utf8_hex": "5b7b226576656e745f7265706f727465645f64617465223a22323032362d31302d3132222c227469636b6572223a224141504c227d5d",
    "sha256": "ddd0602285b5841b551d2182c3455d4ce5adbfb9499926d3251b15f8620ec8a2"
  },
  {
    "kind": "escaping",
    "input": {"text":"caf\u00e9","missing":null,"count":0},
    "canonical_utf8_hex": "7b22636f756e74223a302c226d697373696e67223a6e756c6c2c2274657874223a226361665c7530306539227d",
    "sha256": "a23dd3fa95608fd09c89e36d31944ace9e5e32a42e35530922a336561f5c5a5c"
  }
]
```

### Acknowledgement and immutable publication

Use existing `gcp/fetchers/_av_ingestion.py::publish_manifest`. Commit source observations/groups before the manifest boundary. The first supervised SQL transaction inserts immutable `av_catalyst_source_manifests` and receives an actual acknowledgement. If an ID already exists, require exact stored job_name, variant, execution_name and manifest JSON equality. A conflicting or unacknowledged identity is unavailable, never a relabeled old scope.

Only after that acknowledgement capture the proposal for publication `known_at` and commit the second immutable publication row. Return the actual stored publication clock, including reconciliation/retry. Missing, future or uncertain publication does not establish consumer availability. A committed source/manifest may remain without eligible publication when acknowledgement is interrupted; immutable IDs allow explicit reconciliation, not an invented successful clock or automatic replay of uncertain writes. The publication clock may precede receipt of its own ACK by the physical SQL operation, so consumer/terminal certification additionally requires the received acknowledgement; never publish a proposed timestamp as an acknowledged fact.

Consumer projection joins manifests/publications by manifest_id, bounds publication.known_at by an aware cutoff, and checks actual job/variant/execution/source scope and producer terminal status. `job_runs.note` is actual TEXT JSON, `schema_version=av_catalyst_run/v1`, containing a BOUNDED terminal projection, not the complete manifest/proof arrays. Exact required reference fields: `source_manifest_id`, stored `source_manifest_known_at`, `manifest_sha256`, `manifest_bytes`, `manifest_schema_version`, job/variant/execution, code_revision/image_digest/pipeline_version, `scope_hash`, `source_universe_scope_hash` where applicable, selected_scope_hash/count, universe_count, requested/verified/event-pending/source-unknown/raw-refresh counts and qualification/status, source_window_start/end, expected/attempted/processed/failed/pending/rows_written, task/attempt-unknown, request/application retry totals. Full configured_universe, event lists, source_scope_proofs, receipts, per-event revision lists and complete group detail stay in immutable SQL manifest JSON. Optional error summary is <=16 controlled reason classes plus exact omitted/group counts; financial/source facts are never truncated into a purported full manifest.

Serialize the entire note to <=64KiB UTF8 and emit exactly that same JSON payload once to structured logs. This leaves margin below Cloud Logging256KiB LogEntry; measure actual deployed envelope separately. If optional summaries exceed the cap, retain required references/counts and explicit omitted-detail count; if required fields cannot fit, fail terminal certification with one <=4KiB controlled error note. Do not split an ordinary successful terminal into unlinked log entries. Full canonical manifest has an8MiB serialization cap before its SQL write; >cap leaves explicit capacity/pending, no publication or partial/full certification. Required1239-symbol fixtures must prove full SQL proof retention plus bounded terminal references and consumer retrieval by exact ID/hash. Terminal schema/consumer checks must compare the stored full JSON digest, not assume its arrays were logged. An interrupted terminal delivery is nonzero/unavailable, not evidence that an older launch completed the intended current scope.

### Estimates daily native producer and receipt denominator

Actual caller: `python -m gcp.fetchers.fetch_av_earnings_estimates --max-tickers=100`; no new job. Job_name is `fetch-av-earnings-estimates`, variant `daily`, **pipeline_scope is literal `estimates_daily`**, not `daily`. Native body is `{symbol,estimates:[...]}`. `parse_estimates` validates native symbol/list/date/horizon identities and preserves complete payload; `persist_estimate_group` durably batches at most10 captures and their at most100native records/capture.

Literal manifest keys:

- `schema_version`, `pipeline_scope`, `configured_universe` (sorted native configured ticker list), `universe_count`, `scope_hash` (SHA256 canonical full sorted universe);
- `selected_count`≤100 and `selected_scope_hash` (canonical selected list), separate from full denominator; `pending_count` reports unselected/unprocessed scope and cannot become0 because a smaller slice finished;
- `source_window_start`, `source_window_end`, `complete_through`, `coverage_complete`;
- `captured_receipts`≤100 actual acknowledged selected receipt facts;
- `source_revision_ids` (fetch UUIDs), `source_digest`, `predecessor_execution_name`, code/image/pipeline identity.

Each receipt has exact keys `ticker`, `fetch_id`, `status` (`validated`/`validated_empty`), `source_retrieved_at`, `known_at`, `raw_sha256`, `raw_uri`, `observation_count`. Receipt `known_at` aliases av_estimate_receipt_publications.source_commit_acknowledged_at, not observations.known_at. After ALL source capture and nonempty observation transactions return actual ACK, capture that aware clock and insert the <=10 publication rows in one additional bounded statement. Valid-empty waits for its capture ACK and uses the same durable publication shape with0observations. Only after the receipt-publication ACK may the receipt join the run manifest. The clock records the preceding source commit ACK; it does not falsely timestamp receipt of its own later publication ACK. Overall manifest publication/terminal ACK remains a further certification prerequisite.

On replay, validate existing receipt ticker/status/count against immutable captured body identity and actual observation set; return the original stored source_commit_acknowledged_at for empty AND nonempty, without rewriting observation clocks. Conflict is unavailable. Missing/uncertain source ACK or receipt-publication ACK cannot append a certified receipt. Source rows may survive without publication; explicit idempotent reconciliation may create a later conservative clock after a newly received real source ACK, never invent the lost earlier ACK. Readers/OPS availability join observations/capture to the matching durable receipt publication and actual eligible run-manifest publication, using post-source-ACK clock for receipt availability; a pre-transaction observation clock alone never passes a cutoff. Existing old rows without that publication are qualified unavailable, not backfilled with guessed clocks. Valid empty writes no invented fiscal observation row but keeps capture and acknowledged receipt. Every nonempty observation joins the same fetch/capture identity. Actual manifest publication acknowledgement additionally bounds consumer availability; retrieval or fiscal date alone cannot do so. Failed source/group/publication outcomes never become valid empty or full coverage. A configured1239/full100selected invocation remains incomplete until actual required scope qualifies.

### Calendar AV-native capture and separate selections

Actual native source is `scripts/fetch_earnings_calendar.py::fetch_alphavantage_earnings`, called by the existing calendar CLI; job_name `fetch-earnings-calendar`, native variant/pipeline_scope `daily` or `weekly`. Capture/archive complete `EARNINGS_CALENDAR horizon=3month` original CSV before native parsing or established downstream business filtering. Record native required-field validation independently of business selection.

Literal calendar manifest uses `source_function=EARNINGS_CALENDAR`, `coverage_scope=av_raw_horizon`; configured_universe is sorted native CSV symbols and scope_hash their canonical hash. Counts: `native_csv_rows`, requested_count native rows, verified_count actually valid native records, excluded_count/pending_count native unvalidated rows. Source window is min/max native reportDate, source_revision_ids=[capture UUID], source_digest=original bytes SHA256, captured_receipts=[capture record], raw_uri/raw_sha256/source_retrieved_at. Coverage_complete/complete_through require actual complete required native validation. Malformed required rows leave pending scope even when original bytes were archived.

`source_all_coverage=unavailable` and `business_subset_coverage=not_assessed` are literal qualifications. Preserve the existing AV–UW weekly/business filter without treating approximately70 selected names as all raw native rows, or as the independent approximately1239 configured history universe. EW/UW/Yahoo and other-provider union remains qualified unknown; this supplemental document adds no instrumentation or global health prerequisite for those providers. DEPLOY wrapper admits only actually tested AV-defined coverage and independently supported cohort/selection facts.

### History and reactions daily/weekly exact linkage

History actual CLI is `python -m gcp.fetchers.fetch_earnings_history --scope=daily|weekly --max-tickers=100 --no-backfill`. Job `fetch-earnings-history`, variant and pipeline_scope match explicit daily/weekly. `assess_history_manifest` makes one bounded indexed assessment of the full configured universe and OPTIONS last30-day actual reported-event cohort: inclusive source_window_start=source_window_end-29 calendar days through source_window_end, both in America/New_York. Use one captured aware assessment cutoff for the query, stated window and source/proof clocks. Include previously source-verified immutable observations while fetching at most100 pending tickers; the former incorrect end-30 emitter is corrected at1dfb5b2c, with actual daily/weekly PostgreSQL start/start-1 boundary regressions; native CLI inheritance still requires the acceptance below. Configured symbols are independent of native-calendar/business scopes. Attempts/backoff cannot invent source freshness.

History `expected_events` are ordered `{ticker,event_reported_date}` objects, with `scope_hash` hashing that complete event list. `verified_events` add exact BIGINT revision_id; `source_revision_ids`, source_digest, full configured_universe/universe_count, source_window_start/end, complete_through/coverage_complete and requested/verified/excluded/pending counts bind the complete assessed denominator. Qualifying revision must be financially coherent, have reported EPS and actual validated EARNINGS capture joined through permanent `earnings_revision_observations`, with bounded retrieval/proof clocks. Reused unchanged financial revision requires real new/retained source proof; a raw pointer or source_verified label without a capture is insufficient. Applicable independent Yahoo timing observation/content/knowledge remains linked, never inferred from AV bytes or an absent Yahoo event.

The required accounting separates three denominators. Native `run.expected`, `run.attempted`, `run.processed`, `run.failed`, `run.pending` and physical job_runs.status remain refresh-attempt facts. `raw_refresh_pending` repeats actual run.pending without erasing an unselected or unprocessed backlog; `raw_refresh_status` repeats actual Run.status. Event `requested_count`, `verified_count`, `pending_count` refer only to the ordered actual reported-event cohort; `event_pending_count` repeats this event pending_count. They never equal the configured symbol count merely because those symbols are in the universe. `event_cohort_complete` certifies only the captured-source-derived cohort, not all possible unobserved vendor reports. `source_universe_unknown_count` and `source_universe_unknown_symbols` explicitly identify configured symbols that lack the literal qualifying source-window/clock and independent expected-cohort proof defined below; `source_universe_scope_hash` binds the sorted complete configured universe. Reused source evidence remains identifiable by actual capture IDs, source retrieval clocks, validation status and per-event observation/revision joins. An unobserved configured symbol, unsupported source, missing required event, failed new source or uncertain write is UNKNOWN/pending, never interpreted as a zero-event ticker. A retained old receipt does not establish new unobserved vendor freshness; qualification is limited to its actual captured knowledge. No current full-universe certification from mutable cached rows or calendar business selection is allowed.

After complementary merge, immutable manifest JSON carries `source_scope_quality=observed_snapshot`, awareUTC `assessment_cutoff`, `source_scope_proofs` (exactly one tagged object for every configured symbol) and `independent_expected_cohort_proof=NULL`. No independent full-current cohort producer exists in this authorized contract; do not manufacture one. The enclosing manifest ID/canonical digest/post-ACK publication bind these facts to job/variant/execution/code/image/full configured scope.

Literal per-symbol tagged shape:

```json
{"ticker":"AAPL","state":"observed_snapshot","reason":null,
 "capture_id":"actual UUID","source_retrieved_at":"actual aware UTC clock",
 "function":"EARNINGS","validation_status":"validated",
 "normalized_count":1,"raw_sha256":"actual64hex","raw_uri":"actual immutable URI",
 "quarter_observations":[{"revision_id":123,"capture_id":"actual UUID","known_at":"actual aware UTC clock","yahoo_timing_observation_id":null}],
 "vendor_covered_through":null,"required_window_status":"not_assessed",
 "required_window_reason":"required_cutoff_missing","full_scope_reason":"independent_cohort_proof_unavailable"}
```

`state` is exactly observed_snapshot, unknown or failed. For unknown/failed without a completed capture, capture_id/source_retrieved_at/function/validation_status/normalized_count/raw_sha256/raw_uri are JSONnull and quarter_observations is[]; ticker is always the real configured symbol, `reason` is a controlled class such as no_capture, retrieval_failed, source_ack_unknown, receipt_outside_required_window, provenance_missing or unsupported_source. Failed/unknown may retain actual completed evidence if it exists, but never fill absent fields with defaults. `state` describes actual observation evidence; independent `required_window_status` is matched, unknown or not_assessed, with controlled required_window_reason (nullable only for matched). Old retained valid evidence can remain observed_snapshot while its required-window/current-scope qualification is unknown; the axes cannot be conflated. Observed_snapshot requires real immutable validated/validated-empty capture identity and actual cohort-quarter composite keys `{revision_id,capture_id}`, known_at and optional Yahoo observation ID; earnings_revision_observations has no standalone observation_id column. A zero native observation count means validated_empty only with an actual empty native response. Missing capture, a failed source and a never-selected symbol have distinct honest representations. All branches retain vendor_covered_through=NULL and full_scope_reason; counts derive from the tagged objects, not omission. Only actual cohort-quarter links are copied, not each ticker's lifetime.

`required_source_cutoff` is an aware consumer-supplied cohort-source clock, distinct from producer assessment_cutoff, revision known_at and later manifest publication/terminal ACK. The consumer records that required value in its admission context/artifact, not a fabricated vendor field or new Sunday CAT CLI flag. Compare actual receipt `source_retrieved_at >= required_source_cutoff AND source_retrieved_at <= assessment_cutoff`, observation known_at <= assessment_cutoff, and actual source/publication/terminal acknowledgement and exact scope/code/image identities. A missing required cutoff, absent capture, wrong function/symbol/validation, late/future receipt, unsupported event or mismatched scope makes required_window_status unknown/not_assessed; it cannot certify full-current coverage. That clock test does not erase an actually observed older snapshot or require an unavailable global positive proof for its explicitly labeled current-revision diagnostic analysis. A retained old receipt before the required cutoff never qualifies later reports/corrections. A newly retrieved receipt passing that clock inequality is necessary observed-snapshot evidence ONLY; it is not a vendor watermark or sufficient full-window completeness proof. Do not populate vendor_covered_through from request/retrieval, maximum reportDate, cache update, Scheduler launch or publication clocks.

There is no specified existing producer for independent_expected_cohort_proof. Accordingly this contract REQUIRES it to remain NULL and full-current `coverage_complete=false`, `complete_through=NULL`, `full_current_cohort_status=dependency_pending` with reason independent_cohort_proof_unavailable. `source_universe_unknown_count` counts all configured symbols whose complete required current window is unproved, including observed snapshots; it is distinct from observed/unknown/failed tagged-state counts. Old or fresh EARNINGS snapshots, mutable cache rows, business subsets and unsupported calendar horizons cannot zero that full-current unknown denominator. A later independently approved producer could change that contract; this specification adds none and does not require an impossible positive path or fake independent fixture. Manual bounded repair may obtain missing captured observations but does not create a vendor watermark/full-current guarantee by itself.

The ATTAINABLE positive path is qualified current-revision observed-cohort analytics: all native-captured expected event facts/revisions in the declared observed cohort are proven, event_pending_count=0, and `event_cohort_complete=true` with source_scope_quality=observed_snapshot. Reused verified source evidence can qualify those observed facts while full-current admission remains dependency_pending. Tests require actual daily AND weekly CLI/PostgreSQL observed-cohort positive cases and global/current negative cases; both old and fresh captures improperly promoted as vendor watermarks fail. No historical or global live activation follows from this diagnostic positive path.

Raw1239 refreshes/100 selected may yield raw_refresh_pending=1139 and physical terminal partial. Preserve raw_refresh_status/Run.pending exactly; do not equate1139 symbols with1139 reported events or erase that backlog. Observed analytics may accept a raw-backlog-only partial terminal only under an explicit scoped predicate: exact matching acknowledged terminal/manifest/code/image/full/selected hashes, failed=0, no failed/unknown REQUIRED OBSERVED EVENT groups, event_cohort_complete=true/event_pending_count=0, and lineage matching the declared observed cohort. That permits source-backed current diagnostics only; full-current source_unknown/coverage/activation remain pending, never success. Error/unknown terminal, failed source or missing event/ACK refuses even observed certification. Consumer plans must preserve this distinction. All new facts/predicates are future complementary implementation, not certified by checkpoint1dfb.

Reaction actual CLI is `python -m gcp.fetchers.compute_earnings_reactions --scope=daily|weekly --max-tickers=100 --max-quarters=100`. Job `compute-earnings-reactions`, variant/pipeline_scope explicit daily/weekly. Bind latest actual eligible same-variant history acknowledgement under the explicit observed-cohort/terminal policy above, exact `history_source_manifest_id` and predecessor_execution_name, configured universe/event scope/hash/window, expected_events and source revisions. Native caller computes bounded eligible event tickers; full manifest assessment includes existing qualified rows for the inherited scope, not only selected outputs.

Each qualified event must match its own exact ticker/reported-date/revision, source_known_at≤history publication, validated provenance/configuration and actual permanent `earnings_reaction_input_artifacts`. No ANY-revision-list match can replace per-event identity. Missing/failed OBSERVED event proof, wrong-scope/future ACK and legacy/unlinked derived inputs refuse observed-cohort completion. A qualified observed-cohort diagnostic reaction retains inherited full-current dependency_pending; absent independent global proof does not block that labeled current-revision computation, and never enables full-current or historical admission. Price projection is DATA-author-owned `daily_source_journal_id AS source_journal_id`, split_coefficient and daily_provenance; retain actual receipt metadata or explicit legacy-unlinked qualification. No unmerged DATA helper is imported/copied. Real positive CLI integration requires the actual merged common-basis helper; a dummy replacement cannot certify adjusted OHLC/split-volume or provenance. Current mutable prices remain current_revision_analytics; strict historical certification requires a real immutable vintage and otherwise refuses.

DEPLOY alone derives intended Sunday cycle/admission artifact and enforces schedule/dependency context; it does not require a new Sunday CAT CLI flag or pretend Scheduler presence is source knowledge. OPS reads indexed bounded permanent facts, with pending schema/producer/deployed-digest qualification until actual ownership prerequisites land. No activation from this DOC merge alone.

## Capacity and cost

No new jobs, cron frequency, retained task timeout or source envelopes. The existing1419 workload/retention/cost contract is preserved; the literal manifest assessment/publication is within its existing40-extra-roundtrip/80second history allowance, not additional per-ticker SQL. Numbers below are planning envelopes; native worst-shape CPU/bytes/working-set, real pg8000/source/archive/whole-run timing and actual billed usage remain required measurements before promotion.

| Producer | Volume/storage bound | Native/SQL network shape | Runtime admission |
|---|---|---|---|
| History primary |≤100×1000quarters×500B≈50MB streamed normalized;≤200MiB AVoriginal bytes/run;≤100×50Yahoo rows×400B≈2MB observations |100AV requests;≤400Yahoo underlying requests under100observations;100archivePUTs;≤100cache+100timing writes;≤40otherbounded SQL |AV3000 +Yahoo900 incl reaping +archive1000 +cache200 +timing200 +other80 +pace40 +startup/transform80=5500s<6000hard<7200quarter of retained28800task |
| Calendar AV component |one full3month CSV, existing observed planning~180kB/4582native rows; actual transport maximum20MiB, native validation/business count separately |oneAV request+oneoriginalarchivePUT, onecapture write+two acknowledged manifest/publication statements, no per-row network write for receipt |AV<=30s+archive<=10s+capture/manifests within existing bounded phase; this does not prove full nonAV/enrichment calendar450s completion; DEPLOY admission remains pending until its actual supported path is measured |
| Estimates |≤100responses×100native observations=10000records; original body≤2MiB/response,≤200MiB/run; typical100×41×700B≈2.87MB complete payload plus observation metadata |≤100AV calls+100PUTs;≤10groups×3capture/observation/post-source-ACK publication statements=30coreSQL; oneeligible query, oneclaim, oneoutcome, two manifest/publication, oneterminal statement=6otherSQL; no per-fiscal network calls |actual450s admission with reserve for archive/finalgroup/outcome/publication/terminal, retained1800task. Slow30s sources exhaust admission and leave durable pending, never claim100full completion by count alone |
| Reaction source/receipt component |100tickers×100quarters=10000rows; artifacts<=10KB/row (<=100MB total),100groups<=100rows,<=1MiB artifact parameter plus<=1MiB derived-row parameter (<=2MiB combined); streamed price batches<=10tickers/26000bars/16MiB each,<=260000bars/160MiB across10batches; no full-lifetime buffers |1predecessor+1claim+1compact earnings query+1deduplicated timing observation query+10batched price reads+100atomic artifact/derived writes+1queue outcome+1full observed assessment+1manifest+1publication+1terminal=119 network round trips; no vendor calls/per-quarter reads |119×2s=238s SQL +100s actual transform/basis/formula CPU (10000×10ms) +30sstartup/schema/config +20sserialization/hash/materialization +32sfinal/reserve=420s<=450s (30sremaining), retained1800task; actual maximum-shape proof required, timeout never raised |

The reaction batch architecture is mandatory future implementation: select <=10000 compact financial revision rows in one indexed batch and <=100 distinct complete independent timing observations in one indexed batch (<=100×50×400B≈2MB timing content), without duplicating a20KB timing payload into each of10000 financial rows; read exact selected ticker/event windows in ten <=10ticker indexed queries, split/stream by the returned row/byte caps, reuse each source frame inside its batch, and flush <=100artifact/derived rows in ONE atomic SQL statement/group. Bound artifact JSON to1MiB and derived-row JSON to1MiB separately (combined<=2MiB), measuring both actual serialized parameters rather than claiming an artifact-only cap bounds the whole statement. Full raw selected price/financial inputs reside in the artifact; applicable timing row values plus the actual immutable whole timing observation ID/content hash preserve reproducibility, while its complete native50row payload remains in the permanent timing observation table. Derived rows store bounded lineage/configuration references, not another whole input body. Do not retain all160MiB prices/all100MiB artifacts together, re-query a ticker/quarter, or use the former100per-ticker price queries (those add180s at the declared driver allowance, exceeding450s). All setup, SQL pool/acquisition, output/JSON/hash/basis/ATR work and actual final ACK count in the deadline. The10ms/quarter CPU and2s/round-trip are acceptance planning assumptions, not measurements; exercise actual native maximum caller with the merged DATA helper, all10000row transformations, real PostgreSQL group writes and explicit driver-delay instrumentation, then retain whole-run elapsed and peak-memory evidence. If actual admitted shape exceeds the allowance, preserve committed groups/pending scope and revise bounded grouping/streaming within this same scope rather than claim full completion or raise timeout. Oversized row/byte batches refuse or flush admitted groups without silently truncating the selected/full observed denominator. This10000-row cap calculation does not launch an arbitrary multi-year rebuild; normal CLI still restricts its captured recent observed event cohort.

Full source-manifest storage is separate:8MiB/run maximum ×actual producer invocations; at roughly26history+26reaction runs/month this is at most416MiB/month before SQL JSONB/index amplification, with estimate/calendar manifests counted separately. Persist no full native ticker lifetime in each proof. Actual1239symbol payload byte size and SQL storage/index headroom must be recorded. New estimate receipt publication is <=100rows/run, <=3000rows/30invocation-day month, roughly0.6MB/month at illustrative200B/row before indexes; this small table does not erase retained estimate observation growth or actual native payload size. Terminal proof/log bytes remain<=64KiB/run separately.

Estimates planning at actual I/O shape:100×(API1s+pacing.4s+archive.3s+parse.3s)=200s;30coreSQL×2s=60s;6otherSQL×2s=12s; startup/transformation allowance30s gives302s<450. This refines the original approximate270s scheduling illustration without raising admission: at illustrative oneCPU/1GiB $0.000020/s,302s≈$0.00604/run ×1existing daily run ×30=$0.1812/month;450s admitted≈$0.009/run ×30=$0.27/month. Actual full configured scope may require multiple scheduled bounded slices; do not multiply sources/compute by claiming unperformed full1239 refreshes in one invocation. History existing fiveweekday+oneweekly≈25.7runs/month gives680s expected×rate≈$0.35/month or5500s admitted≈$2.83/month; no cadence added here.

Estimates raw:typical2.87MB/run×90daily runs≈258MB before envelope/compression; absolute200MiB/run×90=17.58GiB original source bodies, before base64/envelope/gzip/metadata. At≤100objects/day,≤3000ClassA PUTs/month; original base64 envelope adds up to4/3 before gzip, which must be measured rather than assumed savings. Permanent estimate SQL grows≤10000native payload rows/day (300000/month at maximum) with actual native payload sizes and UUID/clock/URI/hash/index overhead; do not expire those SQL vintages with raw lifecycle. History six/week over90days adds separately≈15.1GiB maximum raw; initial legacy seed≈74MB before indexes≈100–200MB with indexes; changed revisions/timing/artifacts grow permanently and must be measured.

Preserve the exact immutable1419 `av-cost-estimate-v3` illustration: watchlist news3000 requests×2MB +earnings news300×2MB +topics300×2MB +estimates100×30KB =7.203GB modeled original source bodies/weekday and3700 AV vendor-response objects/weekday. This illustration excludes EARNINGS, calendar, Yahoo and insider; it is not an all-feed bound. At the original illustrative5/7 weekday fraction, 90 calendar days give463.05GB before envelope/compression; assuming a weekday maximum every calendar day gives648.27GB. A separately stated66-weekday assumption gives475.398GB, not the original5/7 figure. Estimates30KB is a typical modeling assumption; its actual admitted maximum is2MiB/response×100=200MiB/run, accounted separately above and not silently substituted into7.203GB. Calendar adds its actual one native response object/invocation and up to20MiB original body; history adds up to100 AV response objects/run plus independent Yahoo observation/artifact objects and up to200MiB AV body/run. Insider adds up to300 native response objects/run×2MB admitted raw bodies plus streamed normalized rows; compute its actual scheduling multiplier separately from news rather than invent6640PUTs under the3700-object model. Count each actual source response once, each separate Yahoo/artifact object separately and SQL permanent growth independently. No extra invocation or raised timeout is authorized by these calculations. Existing `av/raw/` narrow90day lifecycle must be verified through every writer before assuming steady-state cost. Illustrative storage/request pricing is the already declared2026-10-12 `av-cost-estimate-v3`; record actual region/class/pricing date/GB–GiB/observed compressed bytes and billed usage, not a guaranteed tariff. Fixed SQL, AVsubscription, network/build charges remain separate.

## Validation, ownership and activation

CAT owns producer code and additive source tables, literal repository runbook and native/SQL tests listed above. Root owns this pure DOC branch/publication. DEPLOY owns executable schedule/dependency wrapper, create/update secret/runtime/lifecycle tests and targeted deployed-state verifier; OPS owns bounded registry monitoring and dependency_pending statuses. Both consumer plans link this actual merged canonical specification and actual implementation/schema/deployed digest evidence; a scratch filename or merely present table is insufficient.

Before readiness, run real Postgres schema/trigger/rollback/identity/source-vintage tests with explicit ephemeral selectors; the mandatory integration collection fails absent its expected DB/schema, no new skip/xfail masks coverage. Actual daily AND weekly module/main/CLI caller cases exercise native parsers, bounded selection, permanent source/version/timing/artifact writes, full configured/observed-scope assessment with explicit unsupported global dependency status, real manifest/publication ACK, actual job_runs notes and failures. External vendor/archive adapters may be controlled native fixtures for local hermetic tests, but must not replace producers with a function returning a successful synthetic manifest. Publish commands/head/input bytes/calls/SQLshape/runtime/working-set evidence and distinguish synthetic adapters from live deployed receipts.

The committed runbook includes literal DDL/keys, all capacity assumptions and measurements, original raw/source clocks vs availability, valid-empty distinctions, exact linked daily/weekly callers, and source identity promotion: nullable hashes/preparatory compatible indexes → deploy/verify every active and inactive legacy news/insider writer → admitted bounded backfill/reconcile without deleting evidence → accountable drain proof → scoped online UNIQUE INDEX CONCURRENTLY → final NOTNULL/checkpoint. Unknown/invalid indexes or incomplete writer drain cannot finalize. AV key rotation remains accountable GCP Secret Manager owner/on-call coordinated by parent; no secret values are logged or new permission granted here.

Only after complementary DOC approval/merge, actual reviewed CAT1430 implementation merge, additive schema apply, reviewed DEPLOY prerequisite implementation and targeted actual deployed digest/producer/receipt verification may tested producer/receipt deployment be called complete. Full-current/global cohort admission remains dependency_pending under this contract because no independent proof producer exists; no positive activation assertion can remove that explicit dependency. Code/unit/Postgres success is implementation evidence, not production health. Keep consumer eligibility dependency_pending for absent/unverified schema, source receipt, publication, scope or digest. No post-merge live milestone is pre-ticked in a draft PR.

## Risks

Retrieval/launch clocks substituted for acknowledged availability; immutable ID retry collision relabeling;100selected accidentally certifying1239full; calendar70business reporters confused with fullraw source or history; wrong daily/weekly linkage; unbacked source_verified labels; future/corrected timing/EPS entering earlier scope; raw expiry destroying only provenance; mock helper substituting real native caller/common-basis integration; capacity measured on a smaller shape; automatic source identity finalization before all writers drain. The named native/realSQL cases and deployment prerequisite tests must fail on each broken behavior, including missing/future/uncertain ACK, invalid scope and old qualified serving state retained as pending rather than falsely current, old captures before required_source_cutoff and fresh captures incorrectly treated as temporal/vendor watermarks without independent full-window proof.
