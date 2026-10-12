---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-12-feat-data-001-av-indicators.md
branch: fix/feat-data-001-av-indicators
pr: null
status: ready
---

# AV indicator ingestion and strict Phase2 input implementation plan

> **For agentic workers:** Use superpowers:executing-plans in this assigned isolated worktree; root coordinates independent whole-branch review and publication. No child agents. Each task advances the exact approved spec and its six done_when items.

**Goal:** Persist complete source-validated AV indicators with truthful immutable observations, bounded repair and receipt-backed prior-session Phase2 reads.

**Architecture:** Keep ingestion/journal/cache writes in the existing fetcher and additive owned schema blocks. The existing magnitude dataset owns the strict temporal selector and DATA receipt/publication consumer; its callers pass one validated immutable context. Preserve financial algorithms, unrelated phases, raw inputs and legacy evidence qualification. Missing producer/schema/PIT evidence is unavailable.

**Tech Stack:** Python, pandas, requests, SQLAlchemy/pg8000, PostgreSQL, shared NYSE calendar and existing google-cloud-storage SDK.

**Spec:** `docs/superpowers/specs/2026-10-12-feat-data-001-av-indicators.md`, merged in main `eca17a65f61e2e0fd86032c9704dc333ba4e0897`; SHA256 `aa940041dd2021b9a877197c914563b083bad04a491260d16885b1fcef32b38a`.

## Intake and binding dependencies

CHANGE under the catalog row: `FEAT-DATA-001 | Data platform | Ingestion, storage, freshness | — | fetcher jobs | 64 relations — see06 | Production but needs remediation | P0`. Existing backend/code ownership includes `gcp/fetchers/`, `gcp/schema.sql`, `gcp/database.py`. Requirements: REQ-DATA-001..004, REQ-CAP-001..003, REQ-FRESH-001, REQ-OBS-001, REQ-VALID-001, REQ-GOV-004. Issues919,913,914,874 are touched/partial, never automatically closed. Record source semantic, historical-artifact/rerun and remaining acceptance dispositions from the approved spec.

Fresh branch starts at current main, never an unmerged sibling. Own only the approved IND file list; shared schema changes are additive indicator blocks. In particular IND owns the bounded `replace_rows_in_window` optional after_replace hook; DATA/OPTION may consume it only after merge, retaining their own callbacks. OPS owns actual health selector and shared calendar monitoring; DEPLOY owns schedules/images/IAM. Old dispatch scratch brief is historical and cannot override the merged spec.

Code readiness remains BLOCKED until actual approved main DATA schema/publisher (journal, price revision publications, av_daily_input_publications) and producer ACK test evidence exist; no copied stand-in DDL/unmerged helper imports or fabricated ACK clocks. Unsupported adjusted-intraday/historical source remains unavailable even with daily proof. The requirements-only1440 -> separately approved superseding canonical CICD spec -> ACTUAL reviewed main implementation chain is prerequisite for same-PR trusted generated inventory changes. Existing docs-audit policy/source issues also require root-owned governance resolution; never call a DOC merge runtime code. Independent IND implementation proceeds without those prerequisites, but cannot claim the dependent tests or readiness passed.

## Global constraints

- Preserve actual finite vendor values; exact six functions/nine source fields, ADOSC key ADOSC. No local substitute or neutral financial defaults.
- Daily keys UTC midnight. Intraday labels Eastern interval starts; shared actual NYSE grid26 regular/14 half-day, UTC DST aware, extra extended-hours allowed without replacing missing RTH slots.
- Strict native function/symbol/interval/timezone/calculation metadata, validation_policy_version=av-indicator-metadata-v1 and vendor-adjusted basis/policy. Configuration hashes exclude month/window/fetch clocks.
- Incremental seven inclusive ET dates through yesterday, max2 intraday months; backfill explicit inclusive dates/max3months. Three core tickers x six functions: max54 incremental/max72 backfill requests, zero application/adapter/redirect/job retries.
- Whole invocation<=450seconds: work<=445 with final5second terminal reserve; task timeout remains1800. Every transport/pacing/parse/SQL/pool/cleanup stage must be bounded, real slow-stream tests required. Never accept a timer checked only after an unbounded operation.
- Validate all six functions for a complete ticker/interval/month group before writing any group; prior completed groups survive later failure. Ordinary chunks each one atomic append-journal/update-known-cache SQL statement. Legacy repair explicit source/equality/concurrency verified, same transaction journal/cache/clear/refs rollback.
- Strict temporal slice<=three months plus exact leading prior session,<=40000bars, at most six indexed branches in ONE indicator read plus ONE batched DATA receipt/publication JOIN<=100receipts/20MiB; both SQL reads+conversion<=30seconds.
- Remote Phase2 loads EXACTLY two immutable generation-selected JSON objects ONCE/caller in total10seconds, config<=64KiB/manifest<=2MiB, configured bucket/av/phase2/(config|input)/<sha256>.json#generation. Remote shell rejects workstation paths; local validated-path CLI remains local only. Envelopes are transport identity, not source knowledge.
- Terminal records finally on startup/success/no_data/partial/error/repair refusal, safe counts/watermarks/mode/origin. No credentials/prepared URLs/error objects. Missing acknowledgement cannot become historical availability.
- Use `/workspace/stocks-venv/bin/python`. All database commands explicitly select localhost25432/av_indicators test DB and remove production CLOUD_SQL selectors. Existing integration CI collects both entire named integration files; expected missing DB/schema fails, never skips.
- No production action, new schedule, timeout/memory increase, unrelated capability edit, gate waiver or unmerged sibling helper. Root coordinates publication and live milestones.

## Review focus

1. Six equally truncated function responses still fail exact grid validation; test in Task2.
2. Journal callback failure after cache replacement rolls back all and preserves old/adjacent/derived rows; test in Task4.
3. Request blocking/slow byte trickle and cold/locked driver time remain in whole450/terminal5 budget; test in Tasks3/5/11.
4. Manifest/published_at fabrication and valid daily proof cannot qualify unsupported intraday or future vintage; test in Task7.
5. Remote all/plan/nine-task paths load twice per caller, never twice per cell; strict prior-session boundary includes completed-bar receipt between start/decision; test in Tasks8/9.

## Done_when mapping

The spec has six binding items: [0] vendor/grid/whole-run contract; [1] ENTIRE real PostgreSQL journal/index/upgrade/reader/CLI suites and actual caller/PIT proof; [2] source/concurrency-verified atomic legacy repair; [3] terminal/runtime/origin/runbook/catalog/issues; [4] actual remote resolver/callers plus legacy evidence qualification/export; [5] same-PR exact trusted full generated render and normal gate. The table/producer and CICD prerequisites are not waived or ticked early.

### Task 1: Immutable journal and populated partitioned-cache upgrade

Spec: Immutable observation provenance. Advances[1].
Files: both owned schema paths; tests/integration/test_av_indicator_postgres_contracts.py.
Interfaces: av_indicator_observations literal approved columns, observation_id identity tie-breaker, UNIQUE(fetch_id,ts), exact composite asof index; cache av_observation_refs maps function->fetch_id UUID.
- [ ] RED real test_upgrade_existing_cache_schema: original populated partitioned cache lacks refs; apply actual owned upgrade twice, preserve numbers/NULL oldrefs, every partition gains column/index.
- [ ] Add additive DDL to gcp/schema.sql and gcp/queries/magnitude_engine_schema.sql with owned idempotent parent ALTER, journal and index; preserve sibling blocks.
- [ ] GREEN actual upgrade/index and fresh-schema tests in isolated PostgreSQL. Commit gated owned schema/test change, ledger actual commands/results.

### Task 2: Native metadata, finite values and source session grid

Spec: Strict vendor identity, complete session coverage, price basis. Advances[0].
Files: gcp/fetchers/fetch_av_indicators.py; tests/gcp/test_fetch_av_indicators.py and bounded provenance fixtures.
Interfaces: `parse_indicator_response(payload, *, symbol, interval, function, retrieved_at, safe_parameters) -> IndicatorCapture`; capture holds frame/fetch_id/native+canonical metadata/configuration/payload/code hashes and actual aware observation clock. `validate_group(captures, *, sessions, interval, start_date, end_date)` rejects before persistence. Keep caller-visible fetch wrapper updated explicitly.
- [ ] RED exact metadata/timezone/period/series/MA/multiplier cases; recorded all-six/both-interval fixtures, actual labels including ROC without (ROC), ADOSC value, finite field rejection, split basis preserved and wrong raw basis refusal.
- [ ] Parse only expected technical key and finite known fields; add approved canonical provenance/hash and exact shared-calendar daily/RTH coverage. Daily keys remain dates; intraday timestamps localize Eastern then UTC, DST errors explicit.
- [ ] GREEN test_vendor_metadata_rejected_before_conversion, test_session_grid_rejects_truncated_complete_fields, test_halfday_start_label_grid and summer/winter tests. Preserve source-parameter/retrieval/hash note for real observed label fixtures; synthetic split marked synthetic. Commit/ledger.

### Task 3: Bounded actual incremental/backfill orchestration and transport

Spec: Design, capacity, complete group, whole runtime. Advances[0]/[1].
Files: fetcher; same gcp suite; later PG main tests.
Interfaces: `build_groups(symbols,intervals,mode,start_date,end_date,lookback_days,max_months,now)` finite admitted groups; `fetch_indicator(..., month=None, deadline)` one call; main argv testable with safe result/exit. Absolute work deadline derived450-5, no retry; clamped response/pacing/chunk budgets.
- [ ] RED actual-main incremental seven-inclusive-date/month-crossing54 max, explicit backfill72 max, oversized3months/invalidsymbols/intervals/date missing refuse before calls, holiday empty only no_data.
- [ ] Implement admission before network/DB, daily once + per-month15min requests, no retry/redirect/adapter fallback; bounded body/stream/parser and pacing, group validation before writes, earlier durable group preserved.
- [ ] RED/GREEN controlled actual slow-stream/stalled-transport fixture proves enforceable entire deadline and no late work; idle timeout alone cannot pass. Assert safe failure fields and request count0 retry. Commit/ledger measured limits.

### Task 4: Atomic ordinary writes and source-verified legacy replacement hook

Spec: Immutable observation provenance; atomic bounded journal hook. Advances[1]/[2].
Files: fetcher; gcp/database.py ONLY helper optional after_replace; real PG contract suite and existing no-hook caller suite.
Interfaces: `persist_capture_chunk(conn/caller engine, capture, frame, deadline)` one CTE atomic journal insert/known-field cache refs; source repair uses existing replace_rows_in_window(...,verify=verify_source,after_replace=append_matching_journal). No second transaction/network in hook.
- [ ] RED journal/cache rollback, identical-fetch immutability, later vendor revision retention/unknown-field preservation, real simultaneous window change, journal-hook failure after replacement/clear.
- [ ] Implement single-statement ordinary per-function bounded writes; explicit legacy repair full six-source grid/non-ADOSC equal-value verification, locked unchanged-source check before DELETE; optional callback after inserts/clears before same COMMIT, None preserves old API/default/return.
- [ ] GREEN test_journal_cache_atomic_rollback, test_legacy_repair_atomic_scope, test_repair_rejects_unverified_rows/test_repair_rejects_concurrent_change and entire existing test_intraday_replace_months.py. Verify adjacent/original/derived rows/no orphan refs on failure, positive exact references once. Commit/ledger.

### Task 5: Deadline-safe terminal telemetry and source origin facts

Spec: Durable terminal telemetry. Advances[3]/[1].
Files: fetcher; gcp/database.py ONLY redacted record_job_run warning/optional execute_sql timeout path; gcp/PG tests.
Interfaces: shared `execute_sql(...,timeout_s=None)` backward-compatible; `record_job_run(...,timeout_s=None)` bounded optional path. main finally reserves5seconds and returns nonzero on partial/error, records actual variant/mode/safe counts/origin, no producer self-certification.
- [ ] RED main startup failure/no_data/success/partial/repair refusal all attempt exactly one terminal; sentinel key/URL/exceptions remain absent from real helper warning; real blocked PG server/pool/cleanup bound tested.
- [ ] Implement approved safe invocation-kind/Scheduler resource/source code/image fields and aware counts/watermarks, zero retries; persistence false/timeout logged redacted, cannot mask original failure or claim DB ACK.
- [ ] GREEN test_main_records_every_terminal_path/test_terminal_records_invocation_origin/test_real_record_job_run_failure_redacts_credentials and real test_record_job_run_server_timeout. Existing database timeout/rowcount/caller suites unchanged. Commit/ledger.

### Task 6: Indexed finite immutable observation selector

Spec: Immutable observation provenance, Phase2 reader. Advances[1].
Files: gcp/research/magnitude_engine/mag_dataset.py IND-only helpers/branch; gcp/Pg tests.
Interfaces: `select_av_indicator_observations(engine, *, ticker, interval, configuration_hashes, price_basis, keys, as_of, deadline) -> DataFrame`; keys are finite ts/prior-session/cutoff tuples<=40000, range<=3months+exact leading key; ONE six-branch indexed query, retrieval/tie-break cutoffs before latest selection.
- [ ] RED after-asof correction/config/basis mismatch, unversioned cache fallback, out-of-range/40001bar refusal; actual20k journal indexed EXPLAIN index conditions, no whole-journal sort/fullscan.
- [ ] Implement actual bounded query/merge only finite known requested fields, explicit unavailable on missing/incompatible facts; retain prior revisions and exact configuration identities.
- [ ] GREEN test_as_of_retains_vendor_revision/test_as_of_rejects_configuration_mismatch/test_asof_composite_index_plan and real query-shape/range count cases. Commit/ledger.

### Task 7: Actual DATA producer ACK receipt join and input-frame validator

Spec: Self-contained DATA input-receipt dependency. Advances[1]/[4].
Files: mag_dataset.py strict input helper; ENTIRE tests/integration/test_av_indicator_input_receipts.py; matching gcp consumer tests.
Interfaces: `validate_av_input_receipts(engine, *, manifest, loaded_frame, as_of, deadline)` ONE batched journal/pub/source JOIN<=100IDs/20MiB; consume exact merged DATA av_daily_input_publications hashes/scope/economic_basis_version/producer/known_at and source ACK; manifest only locator/selector.
- [ ] RED missing actual schema/producer returns controlled dependency unavailable; manifest/published_at clock fabrication, wrong loaded hash/scope/source/basis/producer, future/retired proof refuse. No copied DDL or unmerged DATA helper import.
- [ ] Implement literal actual SQL/retained content/loaded frame comparison and known_at<=bar decision; daily ACK is only supported daily component, unsupported adjusted-intraday/whole historical input stays unavailable.
- [ ] When DATA main producer actually exists, run two-connection actual producer beforeACK/intermediatecutoff/recovery/retry/conflict/retirement tests plus whole receipt suite. Until then positive actual integration is BLOCKED (not skipped/claimed green). Commit safe consumer/negative implementation with explicit ledger dependency.

### Task 8: Completed-bar prior-session Phase2 integration

Spec: Existing Phase2 consumer and bar-completion cutoff. Advances[1]/[4].
Files: mag_dataset.py existing load/_add_table_join_features IND branch; tests/gcp/test_mag_dataset_av_point_in_time.py and real reader benchmark.
Interfaces: load_magnitude_dataset(...,indicator_as_of=None,indicator_configuration_hashes=None,indicator_input_manifest=None) validates required context ONLY phase2; prior-session calendar and min(context_asof,actualbarcompletion) passed to Tasks6/7; other phases unchanged.
- [ ] RED previous-session holiday/Monday/halfday/DST mapping, same-session daily leakage, receipt after start/before decision eligible, after decision/future correction refuses, January leadingDec31 exactkey without unbounded fourth month.
- [ ] Use actual NYSE sessions/open/close and timeframe completion; do not broadcast current same-session daily cache or silence SQL failure into NaNs. Validate actual loaded dataset identity and context before strict reads.
- [ ] GREEN actual real branch tests and two-query/count/window cases; record40k reader+receipt SQL/conversion<=30seconds once DATA dependency qualifies. Commit/ledger no financial/model algorithm changes.

### Task 9: Immutable remote artifacts and real caller/wrapper propagation

Spec: Remote artifact contract and caller propagation. Advances[4]/[1].
Files: new gcp/research/magnitude_engine/av_phase2_artifacts.py; mag_walk_forward.py; scripts/dispatch_magnitude_phase.sh; scripts/magnitude_movement_sim.py; exact approved tests.
Interfaces: `load_indicator_context(as_of,configuration_reference,input_reference,*,remote,bucket) -> validated context`; immutable SHA+positivegeneration parser; two total bounded SDK reads<=10seconds once per actual main caller, reuse single/all/plan context; local validated paths ONLY local.
- [ ] RED actual resolver/controlled stream transport caps64KiB/2MiB/10seconds, wrongbucket/prefix/hash/generation/malformed/missing403/404/slow coldauth, exactly2GETs even repeated cells, envelope with incompatible DATA proof still refuses.
- [ ] Implement actual pinned GCS conditional generation reads/no retry/uncapped SDK buffer; propagate context to walk_forward/run_all/main and actual movement simulator. Shell accepts exact flags/URI and records all nine real RunJob args; workstation paths fail before gcloud, other phases unchanged.
- [ ] GREEN test_remote_loader_pins_generation_hash_and_once_only_context/test_remote_loader_bounds_slow_stream_and_rejects_unavailable and real caller/simulator/shell tests; actual image import/loader fixture without host mounts. No live upload/image promotion performed. Commit/ledger.

### Task 10: Native PostgreSQL CLI, capacity and rollback acceptance

Spec: Capacity, validation/rollout, entire integration CI. Advances[0]/[1]/[2]/[3].
Files: ENTIRE two approved integration files; fetcher/gcp fixtures as needed.
Interfaces: actual main with isolated PostgreSQL and native deterministic vendor fixtures, actual SQL producer/index/rollback (not adapter-only replacement).
- [ ] RED/GREEN test_cli_incremental_bounded_postgres54 calls, test_cli_max_backfill_request_count72, test_cli_legacy_repair_bounded_postgres source repair, partial durable earliergroup; 20k index and40k two-read benchmark, real cold/blocked driver and whole deadline/cancellation.
- [ ] Run BOTH entire integration files under explicit isolated DB selectors. Missing DATA ACK producer is a named failing dependency, never fake positive fixture/skip. Measure request/SQL chunks/rows*bytes/peak working set/timing and safe terminal shape, preserve cost350s estimate/450hard/1800task ceiling.
- [ ] Run meaningful relevant existing helper/simulator tests once after shared modifications; checkpoint gated task with exact failures/dependency evidence and no readiness tick until all mandatory checks pass.

### Task 11: Historical evidence qualification, runbook and exact generated inventory

Spec: Legacy Phase2 evidence, generated inventory prerequisite, runbook. Advances[3]/[4]/[5].
Files: owned indicator docs/legacy magnitude Phase2 qualification documents, generated model registry, three generated infrastructure outputs ONLY trusted full renderer result.
Interfaces: real upload prefix/SHA/create-only/generation instructions, exact incremental/backfill/repair forms and reconciliation queries; legacy magnitude-engine-qh7s9 status incompatible/input_provenance_unavailable; unrelated phases/direction_program evidence unchanged.
- [ ] Qualify only affected AV Phase2 history/A2 status, retain old numbers/execution as legacy, require actual receipt-backed rerun before admissible evidence/calibration; regenerate unchanged exporter model JSON and --check.
- [ ] Write literal merged source/schema/ACK/context/caller/repair/telemetry commands, capacity cost and original issue partial/artifact dispositions; remote object upload steps are instructions, not performed work.
- [ ] After ACTUAL main CICD implementation lands, run unchanged-main trusted full doc_inventory render05a/c/e including fixedcounts/asof and check_generated_docs + normal gate. If absent, keep existing refusal and readinessBLOCKED, never bypass/restore counts/forge generated result. Commit owned evidence/docs when gates permit, ledger actual prerequisite revision.

### Task 12: Independent review and gated draft close-out

Spec: File ownership, all six done_when, validation. Advances[0..5].
Files: FEAT-DATA-001 catalog record/traceability ONLY, same plan PR number, scoped report.
- [ ] Record draft PR then real implementation checkpoints; preserve actual approved spec/plan/main base SHA, all issue919/913/914/874 partial dispositions; update capability only with truthful evidence and Last reviewed.
- [ ] Run relevant focused tests plus both entire actual PostgreSQL files and required exporter/generated/delivery/docs checks; record branch versus main docs findings and explicit dependency blockers. No future acceptance/live grant/production smoke pre-ticked.
- [ ] Root assigns fresh independent whole-branch review after implementation; fix concrete findings in one gated batch with RED->GREEN evidence. Root owns final publication/merge/live rollout, max two external rounds.
- [ ] Draft becomes ready ONLY when six actual done_when and independent review pass, including DATA producer and CICD/main governance prerequisites. Root later performs source-reconciled deployments/smokes, actual PIT-compatible historical rerun and artifact issue closure; code tests alone never certify production restoration.
