# Earnings and AV catalyst pipeline

**Last reviewed:** 2026-10-12 · **Depth:** verified · **Against:** `dbb5887de1bd1718efb86ce36bb67d5d078c45de` · **Last scanned:** 2026-10-12

Candidate implementation: [PR #1430](https://github.com/TeneikaAskew/stocks/pull/1430), [approved CAT specification](superpowers/specs/2026-10-12-feat-catalyst-001-av-catalysts.md), [implementation plan](superpowers/plans/2026-10-12-feat-catalyst-001-av-catalysts.md). Implementation and review are in progress; production rollout has not been verified. Existing unrelated catalyst providers retain their behavior and remain separately qualified.

## Source and publication contract

AV `EARNINGS` populates the latest `earnings_history` cache. Permanent `earnings_history_revisions` retains changed EPS, surprise, reported dates and timing, including A–B–A reversions. The migration seeds existing rows at actual observation time as `observed_legacy`; it never infers their original vendor availability. An atomic source lock, seed, AFTER trigger and append-only guards protect installation and normal/alternate writes. Unchanged financial refreshes retain one revision and append new `earnings_revision_observations` source proof rather than duplicate financial versions.

Yahoo timing has its own immutable `earnings_timing_observations` identity, UTC retrieval/knowledge clocks, installed-library version, safe parameters, complete timestamp/index/returned values and content hash. A Yahoo timing correction can change the effective timing while AV EPS bytes remain unchanged. Disabled or unavailable Yahoo enrichment is explicit; an observation missing the applicable quarter does not erase previous evidence. Yahoo requests are counted separately from AV quota calls.

`EARNINGS_ESTIMATES` stores every native payload field permanently in `av_earnings_estimates_observations`. Fetch identity plus ticker, fiscal date and fiscal-quarter/year horizon is idempotent; later retrievals append vintages. Observation `known_at` is the immutable proposed insertion clock. The separate `av_estimate_receipt_publications.source_commit_acknowledged_at` records the actual ACK of complete capture and observation transactions. Empty and nonempty retry receipts retain that original durable receipt clock. A validated empty response has a capture/publication and no fabricated fiscal row. The reader additionally requires matching run-manifest publication and terminal linkage; old observations without that publication are unavailable. Raw expiry cannot erase permanent earnings, estimates, timing or reaction inputs.

Original bytes for `EARNINGS`, `EARNINGS_ESTIMATES`, `NEWS_SENTIMENT`, `EARNINGS_CALENDAR` and admitted insider captures use immutable `av/raw/<FUNCTION>/<UTC date>/<capture UUID>.json.gz` objects. Gzip envelopes contain reversible original bytes, SHA256, safe parameters, UTC retrieval and code identity. Credential parameters and request URLs are excluded. GCS creation uses generation-zero preconditions; same-identity retry must match exact bytes. Missing bucket or failed/uncertain upload cannot create provenance-complete SQL rows. Dry-run performs no GCS or SQL writes.

`av_catalyst_source_captures` holds validated/validated-empty receipts. `av_catalyst_source_manifests` records complete assessed scope, source/event window, immutable IDs/digests, requested/verified/excluded/pending counts and execution/code identity. Join `av_catalyst_manifest_publications` by manifest ID: its stored `known_at` is inserted only after acknowledged source/manifest commits. Terminal `job_runs.note` repeats `source_manifest_id` and `source_manifest_known_at`. Retrieval time or a Scheduler launch cannot replace this availability proof. A manifest retry returns the original publication clock; unknown publication stays unavailable.

Calendar capture includes the full native AV three-month CSV before downstream business filtering. Native validated rows and symbols describe the raw horizon; the established AV–UW business subset is a separate selection. AV raw coverage cannot establish the EW/UW/Yahoo union or the ~1,239 configured history universe. `source_all_coverage=unavailable` and `business_subset_coverage=not_assessed` are explicit. Native malformed required rows leave coverage incomplete.

## Bounded commands

These candidate commands are for reviewed, admitted execution after deployment dependencies are satisfied. Existing production jobs must retain their qualified serving state until verification passes. No full market backfill is launched by earnings refresh.

```bash
python -m gcp.fetchers.fetch_earnings_history --scope=daily --max-tickers=100 --no-backfill
python -m gcp.fetchers.fetch_earnings_history --scope=weekly --max-tickers=100 --no-backfill
python -m gcp.fetchers.fetch_earnings_history --tickers=AAPL --max-tickers=1 --no-backfill --dry-run --no-yahoo
python -m gcp.fetchers.fetch_av_earnings_estimates --max-tickers=100
python -m gcp.fetchers.fetch_news_sentiment --tickers=IWM,SPY --max-tickers=300 --max-requests=300
python -m gcp.fetchers.fetch_news_sentiment --earnings-window-days=7 --max-tickers=300 --max-requests=300
python -m gcp.fetchers.fetch_news_sentiment --topics=earnings,technology --max-requests=30
python -m gcp.fetchers.fetch_insider_transactions --max-tickers=300
python -m gcp.fetchers.compute_earnings_reactions --scope=daily --max-tickers=100 --max-quarters=100
```

`--force` bypasses freshness selection, never count/runtime/byte admission. Above-cap news/insider universes require explicit independently assessed shards; no silent truncation. History/estimates selectors retain full resolved denominators and report selected and pending counts separately. Fair leased work chooses NULL/oldest attempt before repeating failed heads, with explicit backoff; attempt clocks never alter source freshness. Capped or timed-out required coverage is partial/nonzero. Recurring history and bounded repair must use `--no-backfill`; unsafe combined manual chains are refused. Do not run the old 77–120-minute market chain through this earnings command. Price-depth recovery belongs to the independently reviewed DATA/DEPLOY command and capacity contract.

News windows are durable half-open minute intervals, initially 48 hours and never more than seven days per requested span. Vendor calls use explicit time bounds, EARLIEST ordering and boundary overlap followed by logical filtering. Saturated responses split into smaller durable windows across invocations; all initial/subdivision calls share the request budget. A saturated minimum-minute window becomes `blocked_vendor_granularity`, not complete. Failed/uncertain commits invalidate proposed group frontiers. Cursor completeness cannot jump an unresolved gap.

## Historical and derived data

`lib.earnings_history` selects latest immutable earnings/estimate vintage at an aware cutoff in one bounded query. Pre-observation history is unavailable, not the latest cache. `/api/catalysts/asof/{ticker}?as_of=YYYY-MM-DD` resolves exchange-date end in America/New_York, including DST. Explicit historical requests suppress unversioned news, SEC, insider, calendar and prices with section-level unavailable reasons. Live database errors differ from successful empty responses.

New reactions require actual validated source-capture proof, the applicable earnings revision/knowledge clock and independent timing observation, resolved configuration/hash, rule version, code commit/image, common OHLC basis and a permanent `earnings_reaction_input_artifacts` identity/hash. Artifacts and derived rows commit consistently. The required shared DATA `lib.price_basis` interface (helper/schema not merged at this checkpoint; positive integration remains pending) validates exact canonical UTF8 `artifact_payload` bytes and ordered `price_inputs`; OHLC uses adjusted-close/raw-close factors, volume uses split factors only. Legacy raw ATR is recomputed on common basis. Missing DATA columns/helper, missing depth or unknown factors is unavailable and cannot become a successful certified reaction.

Current mutable revised prices support `current_revision_analytics` only. Historical/as-of reaction certification is refused without a real immutable price vintage satisfying the cutoff. Existing reaction/view rows with missing provenance remain legacy/unavailable for qualified admission; this does not promote them into a point-in-time strategy/model.

History assesses the full configured OPTIONS last-30-day actual reported-event cohort while fetching at most100 admitted symbols. Existing unchanged source-verified revisions can qualify. Reaction manifests bind the exact history manifest ID, event scope/hash, window, configured universe and matching per-event revision IDs. Missing, pending, wrong-scope or future acknowledgement cannot be substituted by an older scheduled launch. DEPLOY owns new Sunday scheduling and its runtime predecessor wrapper; CAT adds no Sunday-specific CLI gate. Read the approved DEPLOY plan and deployed-state verifier for actual schedule/pipeline admission evidence.

## Capacity, measurements and costs

Planning numbers below are envelopes, not measured production latency. Actual whole-path transport/archive/pg8000 Cloud SQL latency and maximum shape must pass before promotion; a failing measurement requires smaller fair shards or a bounded architecture correction, never a raised timeout or hidden slow fallback.

| Phase | Admitted volume | Network shape | Planning wall-clock and retained task cap |
|---|---|---|---|
| History primary | 100 symbols ×≤1,000 quarters ×500B≈50MB streamed; AV≤200MiB/run; Yahoo≤100×50×400B≈2MB | 100 AV calls; ≤400 Yahoo HTTP requests under100 supervised observations;100 archive PUTs;≤100 cache and100 timing writes;≤40 remaining round trips | 3,000 AV +900 Yahoo incl reaping +1,000 archive +200 cache +200 timing +80 remaining SQL +40 pacing +80 transform/startup=5,500s, below6,000 primary and7,200 quarter of28,800 task |
| Insider | 300×1,000=300,000 rows;≤360MB streamed normalized;≤600MB raw | 300 calls;30 groups≤10responses/10,000rows/16MiB;≤4SQL round trips/group | 300×(1sAPI+.4pace+.3archive+.3parse)+120×2sSQL+30setup=870s≤900 quarter of3,600 task |
| Ticker/earnings news | ≤300 calls, including subdivisions;≤300,000 articles/1.2M equity rows/1.44GB streamed;≤600MB admitted raw | ≤30calls/query identity;30groups≤10responses/40,000rows/64MiB;≤4SQL round trips/group; batched startup/cursor | 300×2s+120×2s+30setup=870s≤900 quarter of3,600 task |
| Topic news | ≤30calls;≤30,000articles/120,000rows/144MB streamed;≤60MB raw | ≤3groups and12write round trips |30×2s+12×2s+30setup=114s≤900 |
| Estimates |≤100symbols ×≤100 native rows, preserving complete payload; actual body≤2MiB each |≤100calls,100PUTs;≤10groups, bounded capture/observation commits; full vs selected scope manifest | actual450s admission with terminal reserve; retained1,800 task; exhausted scope remains pending |

Source/body reads, GCS operations and SQL acquisition/query/ACK are supervised in spawned processes. Native Yahoo curl uses≤4requests,≤2s each, no redirects and a body callback cap, within8s overall plus≤1s terminate/kill/reap. Parent bounds cover trickling bodies and provider/library hangs. Source responses outside admitted news shape are archived up to the absolute20MiB transport ceiling, then refused; an unbounded response cannot be archived by assertion. Unknown commits retain immutable identities for explicit reconciliation, never automatic fabricated acknowledgements.

Local evidence as of the implementation checkpoint: baseline184 focused tests passed; initial combined202 passed. Native300×1,000 insider parsing/identity preparation with30 bounded groups passed in a7-test batch98.07s before pacing was instrumented, observed process RSS≈132MiB; this measured CPU/shape with vendor/SQL adapters, not production network speed. Three news-mode tests exercise actual300/300/30 call paths and one full40,000-row native transformation group per mode; pacing is instrumented and SQL/vendor latency modeled explicitly. Real local pg8000 tests prove atomic migration rollback, concurrent upsert convergence, two full schema applications, actual four-writer preparation/final online identity replay, independent Yahoo timing, API correction cutoff, estimates CLI nonempty/empty/pending/uncertain publication, fair selection and news subdivision/restart. Actual local HTTP/curl/process fixtures exercise request count, body rejection,8s provider cancellation/reaping, trickling AV, blocked upload and blocked database acquisition. Final measured command/result/head package is in the PR review report; acceptance remains unticked until complete.

Illustrative oneCPU/1GiB Cloud Run price$0.000020/s: history680s expected≈$0.0136/run,5,500s admitted≈$0.11/run. Five weekday+oneweekly≈25.7runs/month yields≈$0.35expected or$2.83admitted, excluding free tier/fixed SQL/subscriptions/storage. New estimates planning250s≈$0.005/run ×1/day ×30=$0.15/month. Record actual billing/pricing revision during rollout; these are not guarantees.

The immutable `av-cost-estimate-v3` source-body illustration is6GB watchlist news +0.6GB topic news +0.6GB earnings news +3MB estimates (100×30KB typical) =7.203GB/weekday and3,700 AV response objects/weekday. It excludes EARNINGS, calendar, Yahoo and insider. Its original90day×5/7 assumption gives463.05GB; daily maxima give648.27GB, before envelope/base64/gzip/metadata. A separately declared66weekday assumption gives475.398GB. The original unsaturated30-symbol illustration is1.223GB/weekday and does not bound a300-call backlog. Estimates actual admitted body maximum is100×2MiB=200MiB/run, separately from typical30KB. Calendar adds one native response object and up to20MiB/run. History adds≤100 AVresponse objects/≤200MiB per invocation separately (six/week over90days≈15.1GiB) plus independent Yahoo/artifact objects; insider adds≤600MB/300PUTs per full run separately. Measure actual compressed object bytes and permanent SQL/index growth. Legacy seed≈74MB before indexes,≈100–200MB with indexes; pathological100×100 changed quarters adds≈10MB permanent revisions.

## Promotion and identity checklist

1. Parent verifies approved DEPLOY tests for create/update secrets/runtime, calendar secret/missing-secret preflight and every lifecycle writer preserving exact `av/raw/`90day retention. Run the targeted deployed-state verifier after merge; code tests or existing Scheduler presence do not prove deployed state. Preserve unrelated bucket rules.
2. Apply additive schema through the revision-recording schema applier. Validate populated-cache seed clocks, atomic trigger/guard installation, permanent tables/indexes and transitional nonunique identity lookup indexes. Dry-run inspection cannot prove installation.
3. Deploy every news writer (scheduled AV, ticker backfill, RSS, standalone backfill) and insider writer with the shared preparation/bulk identity function. Verify active and inactive old commands/images cannot still write outside that contract. Keep hashes nullable during this stage; do not create the final unique index yet.
4. Backfill existing NULL identity hashes in admitted≤5,000-row primary-key chunks. Record progress/evidence and reconcile collisions explicitly without deleting evidence or fabricating financial fields. Failed drain/duplicate/null checks keep the preparatory compatible state.
5. Only after accountable writer-drain proof, use `python -m gcp.fetchers._av_ingestion --identity-table=news_sentiment --finalize-identities --writer-manifest=<reviewed JSON path>` (or insider table). The manifest must prove all required current writer entrypoints, inactive-old blocking, code/image/contract versions and evidence URI. The helper checks nulls/collisions, builds its scoped UNIQUE INDEX CONCURRENTLY, sets NOTNULL and records the final checkpoint. Inspect/reconcile an invalid partial index; unknown outcome is not successful finalization. Never fill this manifest with deployment guesses.
6. Parent performs bounded primary-only refresh/repair, validates actual source bytes/clock/hash and permanent revisions/estimate vintages, and records full/selected/pending scope. Verify source publication ACK and exact history/reaction linkage before OPTION admission. Missing DATA depth/helper/basis is a named recovery dependency, not completeness.
7. Measure cold/warm full admitted shape, logical/underlying requests, raw+normalized+SQL bytes, archive latency, pg8000 group round trips, working-set peak and whole-run elapsed including failure/terminal. Admit only a measured≤quarter-timeout workload. Full transport/SQL/GCS verification remains post-merge parent promotion evidence.
8. The accountable `av-api-key` rotation role is the GCP Secret Manager key owner/on-call operator, coordinated by the parent rollout owner. Confirm the actual assignee in the deployment record; do not invent a person. Rotate the previously exposed credential, update all approved existing consumers/versions, verify source success without logging secrets, and retire the old version only after references converge. This author has not performed rotation.

Related records: [feature catalog](product/02-FEATURE-CATALOG.md#feat-catalyst-001), [traceability](product/12-PR-ISSUE-TRACEABILITY.md#feat-catalyst-001--earnings--catalysts-19-open), [DATA pipeline](product/infrastructure/05-g-DATA_PIPELINE.md), [approved specification](superpowers/specs/2026-10-12-feat-catalyst-001-av-catalysts.md). Earlier May2026 broad market-backfill commands and cron observations are historical context, not an admitted recovery command for this candidate.

## Literal producer source choices (candidate implementation)

The [complementary producer-receipts specification](superpowers/specs/2026-10-12-feat-catalyst-001-av-producer-receipts.md) merged at76783d56; immutable spec1419 remains unchanged. PR1430 is implementing both contracts, with acceptance and deployment pending. Source references below describe the candidate implementation; actual schema/producer rollout remains a prerequisite.

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
```

```sql
CREATE TABLE IF NOT EXISTS av_catalyst_source_manifests (
    manifest_id UUID PRIMARY KEY,
    job_name TEXT NOT NULL,
    variant TEXT NOT NULL,
    execution_name TEXT NOT NULL,
    manifest JSONB NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS av_catalyst_manifest_publications (
    manifest_id UUID PRIMARY KEY REFERENCES av_catalyst_source_manifests(manifest_id),
    known_at TIMESTAMPTZ NOT NULL
);
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
```

```sql
CREATE TABLE IF NOT EXISTS av_estimate_receipt_publications (
    fetch_id UUID PRIMARY KEY REFERENCES av_catalyst_source_captures(capture_id),
    ticker TEXT NOT NULL,
    validation_status TEXT NOT NULL CHECK(validation_status IN ('validated','validated_empty')),
    observation_count INTEGER NOT NULL CHECK(observation_count>=0),
    source_commit_acknowledged_at TIMESTAMPTZ NOT NULL,
    CHECK((validation_status='validated_empty' AND observation_count=0)
       OR (validation_status='validated' AND observation_count>0))
);
CREATE INDEX IF NOT EXISTS av_estimate_receipt_known_idx
    ON av_estimate_receipt_publications(ticker,source_commit_acknowledged_at DESC);
```

Source: `gcp/schema.sql` additive CAT storage block. Append-only guards cover captures, manifests, publications and estimate observations/receipt publications. Actual estimates source writer is `gcp/fetchers/fetch_av_earnings_estimates.py::main`; native adapter `parse_estimates`, grouped writer `persist_estimate_group`; manifest publication is `gcp/fetchers/_av_ingestion.py::publish_manifest`. Producer job_name is `fetch-av-earnings-estimates`, variant `daily`, pipeline_scope `estimates_daily`.

Full estimate denominator: `configured_universe`, `universe_count`, `scope_hash` = SHA256(canonical sorted configured symbols). Selection: `selected_count`≤100, `selected_scope_hash`, `pending_count` separate from full universe. Windows: `source_window_start`, `source_window_end`, `complete_through`, `coverage_complete`. Sources: `captured_receipts`, `source_revision_ids` (fetch UUIDs), `source_digest`, `predecessor_execution_name`, code/image/pipeline identity. Each selected receipt contains literal `ticker`, `fetch_id`, `status` (`validated` or `validated_empty`), `source_retrieved_at`, `known_at`, `raw_sha256`, `raw_uri`, `observation_count`. Valid empty has no fiscal observation; selected100 cannot certify configured1239. Failed or unacknowledged groups cannot contribute complete receipt coverage.

Publication uses two supervised acknowledged SQL boundaries. A duplicate manifest identity must match stored job/variant/execution/full JSON exactly; a conflict or uncertain acknowledgement is refused. The second boundary returns the actual stored publication.known_at, including retries; a future stored proposal is refused. The full strict canonical manifest is capped at8MiB before SQL. Terminal log and TEXT note contain identical <=64KiB references/counts, including source_manifest_id/source_manifest_known_at/manifest_sha256/manifest_bytes/manifest_schema_version. Complete configured/proof/event/receipt/group arrays stay in SQL and are retrieved by exact ID with digest verification. Optional detail is omitted explicitly before failing required projection; required overflow produces a <=4KiB controlled failure, never successful truncated scope. Source capture has no known_at field. Receipt known_at aliases the separate post-source-ACK receipt publication clock, including empty responses. A lost ACK may leave committed evidence; no certified receipt is returned until explicit identity-preserving reconciliation receives an ACK.

`av-catalyst-canonical/v1` uses sorted JSON keys, prescribed array order, comma/colon separators without spaces, ensure_ascii=true, UTF8 without BOM/newline and signed64-bit integers; scope/proof projections reject floats, duplicate keys and unsupported values. Symbols are trimmed uppercase ASCII, sorted/deduplicated; event multiplicity is retained. Proof clocks use awareUTC six-microsecond Z form. Known-answer bytes/hashes are committed in tests/fixtures/av_catalyst_scope_vectors.json. Independent consumer-parser integration remains pending; a producer helper test does not certify those consumers.

The receipt adds one bounded statement per <=10-response group: estimates now uses <=30 core plus6 other SQL round trips. Planning200seconds source/pace/archive/parse+36×2seconds SQL+30setup=302seconds below450 admission and1800 retained task, about$0.1812 per30-invocation month at$0.000020/second;450 cap is$0.27/month. These are assumptions, not measured production costs. Receipt publication adds <=3000rows/month (illustrative0.6MB before indexes); full manifests add at most8MiB/run, about416MiB/month at26history+26reaction runs, before SQL/index amplification and other producers.

Calendar source writer is `scripts/fetch_earnings_calendar.py::fetch_alphavantage_earnings`, job `fetch-earnings-calendar`, native variant/scope daily or weekly. Its AV-only manifest stores `source_function=EARNINGS_CALENDAR`, `coverage_scope=av_raw_horizon`, native symbol scope/hash/count, native_csv_rows and requested/verified/excluded/pending native validation counts, min/max native reportDate, source retrieval/digest/raw location, `captured_receipts`, and complete_through/coverage_complete only when every native required row validates. Downstream business filtering never changes native counts. NonAV union remains `source_all_coverage=unavailable`; `business_subset_coverage=not_assessed`.

History writer/assessment is `gcp/fetchers/fetch_earnings_history.py::main` / `assess_history_manifest`, job `fetch-earnings-history`, daily or weekly variant/pipeline_scope. Full configured universe is independent of selected≤100 fetches. Ordered `expected_events` are `{ticker,event_reported_date}`; `scope_hash` hashes these events, not calendar symbols. `verified_events` add BIGINT `revision_id`; `source_revision_ids` and source_digest bind actual immutable values, independently completed timing and validated EARNINGS capture proof. The exact inclusive30-date event window is assessment ETdate-29 through assessment ETdate, with a single aware assessment cutoff for SQL and emitted dates/clocks. Source retrieval/proof clocks are cutoff-bounded, with missing capture provenance refused. Raw refresh Run.pending is distinct from event manifest.pending_count; explicit unknown-source/joint consumer admission remains required complementary-spec work, not an implemented full-source certification here.

Reaction writer/assessment is `gcp/fetchers/compute_earnings_reactions.py::main` / `publish_reactions_manifest`, job `compute-earnings-reactions`, daily or weekly. It inherits exact configured universe/event scope/hash/window, `history_source_manifest_id` and predecessor_execution_name. Each qualified derived event must match its own exact expected revision, source known_at≤history acknowledgement, validated provenance/configuration and an actual permanent input artifact. Full requested/verified/excluded/pending counts cannot be replaced by selected output count. Current cache prices remain current_revision_analytics; no historical certification is invented.

Existing actual local acceptance: `tests/integration/test_av_catalyst_producer_writes.py::test_actual_estimates_daily_writer_publishes_selected_receipts_and_pending_scope`, `::test_actual_estimates_uncertain_publication_never_certifies_availability`, `::test_actual_estimates_group_retains_full_native_payload_and_retry_identity`, `::test_full_scope_manifests_reuse_verified_sources_and_require_acknowledgement` (daily/weekly), `::test_manifest_identity_collision_cannot_relabel_acknowledged_scope`, `::test_daily_selector_fetches_new_report_after_prior_complete_quarter` and `::test_history_event_window_is_exactly_thirty_inclusive_dates` (daily/weekly); plus `tests/gcp/test_av_catalyst_predecessor_manifests.py::test_daily_manifest_links_full_assessed_scope_and_acknowledged_sources` adapter shape and `tests/gcp/test_fetch_earnings_calendar_persist.py::test_full_feed_archive_preserves_weekly_subset`. These are synthetic native adapters and real local SQL, not production receipts. DEPLOY/OPS admission stays dependency_pending until the owning specification/code/schema and actual deployed digest/source receipts are verified.
