---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-10-13-feat-option-001-av-source-journal.md
branch: fix/feat-option-001-av-source-journal
pr: 1495
status: ready
---

# AV options source journal implementation plan

> For agentic workers: use superpowers:executing-plans inline, task by task. The sole author is review_indicators; root owns independent full review, publication readiness, merges and deployment. No subordinate implementers or production actions.

**Goal:** Implement the approved native whole-chain journal, truthful source/input clocks, finite admission and bounded source/retention controls without fabricated historical knowledge or current financial serving.

**Architecture:** Add immutable revision/payload/publication/claim/accounting SQL under the approved source protocol. Pure canonical payload and typed identity code feeds bounded atomic publication and claim-aware selectors; native producers and maintenance callers reuse those interfaces. Actual missing DATA/COMMON/IND/downstream capabilities return typed dependency-unavailable; no sibling implementation is copied.

**Tech stack:** Python, PostgreSQL, SQLAlchemy/pg8000, pandas, existing NYSE calendar and GCS SDK; existing native API/exporter/delivery infrastructure only.

**Spec:** docs/superpowers/specs/2026-10-13-feat-option-001-av-source-journal.md, immutable SHA2569e634992fb089c9a00d79b31234e81ede30ad93c2c66daec1fbb31f72cbc35d4, actually MAIN2ff7dfbbf23374a72e7c96c3522ec36ca355d705. Initial implementation BASE is actual MAIN2a16b7f034669d8d007b4d10301c8d52adecf1d7; the approved spec is present with identical bytes. This new initial plan precedes ALL source code. Existing CAT5bf is another preserved worktree/plan and is not this source.

## Intake and global constraints

Catalog: FEAT-OPTION-001 “Options / gamma — Flow, Greeks, GEX grid”; existing Status Retest Required, P0; owns backend `/api/options`, `/api/grid`. Touch913/914/919 without automatic closure or broader provider/model claims. Req IDs and existing note OPTIONS01/02/12 are exactly the approved primary. Canvases are empty. One plan/branch/draft PR/author; no BASE plan rebinding.

- EXACT core datasets etf_options_eod, etf_options_realtime, etf_options_closing; group JSON {source_session} or closing {source_session,close_slot}, ticker separate. Unknown dataset/key/clock/input refuses.
- Source retrieval/snapshot/admission/session are NOT post-COMMIT knowledge. Separate immutable actual publication ACK; claim clocks, latest allocated sequence, lease generation and conservative unknown/lower-bound rules are binding.
- SQL20GiB logical/40GiB physical hard,1/2GiB in-cap reserve, usable19/38; raw120GiB hard/10reserve/110usable. Existing/shared/inflight/failed/index/WAL/metadata bytes count. Unknown/stale headroom refuses BEFORE source/archive.
- UTC-day attempts regular756 (252primary+504typed-empty), closing3zero-retry, EOD4, historicalearn100, prospective100zero-retry, ondemand10. ONE initial grant90lifetime vendor AND90TOTAL billable tasks; taskcount/parallelism1; no refunds/reset/copy/API minting. Sum973/day or1063 including one90 grant is not a quota grant.
- Native realtime/closing whole150seconds under600task: ALL source15 +SQL60 +other75, <=10SQLRT/ticker/30invocation, full ticker<=14000contracts and10MiB raw/normalized caps, peak<=256MiB under512MiB resource. No prefix publication.
- Regular7/EOD30/closing90/historical/prospective38 raw/body horizons and compact90 follow exact primary. Existing cache30/floor14 unchanged. No expiry clock backdating or missing-body reconstruction.
- Maintenance SAME90: prune15+lease15+raw60 when all lanes compete, raw45GCS+SQL10+other5; <=15TOTAL SQLRT30. Conditional75+15/300payload three100 batches only WITHOUT raw. Finalized probes<=1200,2401individually billed metadata GETs, provider100/envelope,24envelopes/3parallel/8waves, actual all-in deadlines/bytes/cost.
- Foundation A4 HTTP hard/p95<=5s/complete2MiB: SAME-source recovery then serving_contract_pending, ZERO financial B response. Actual later qualified serving belongs the separately approved B/API owner after A CODE MAIN.
- Large legacy index uses exact approved nullable cache column/partial UNIQUE index, autocommit,3600whole-build/14400task, lock<=5s, actual2H/possible3H scans, >=10GiB/20% disk headroom, actual representative I/O and own-PID cancellation proof. This plan does NOT execute it on production.
- Actual DATA schema/provider/COMMON schema+parser+helper/IND typed bounded worker CODE MAIN is required where consumed. No unmerged import/copy/stub positive. Historical rate/ticker-yield/basis/source capability may remain genuinely unavailable. No new financial formulas, threshold/model/fit, jobs, resources, retries, schedules or entitlement.
- Global activation remains default-disabled until actual source/current-read/parity/alert/regeneration/retired-writer/cache-drain/root deployment proofs. SPEC/plan/main/test fixture/operation label does not establish these.
- ALL source publication/ready held until actual compatible GovVerifier/Counter/Cost CODE MAIN, own15DoD, ordinary committed source/body note/sidecar/noNEW/current-head review/CI proof. Source is private until then. Plan-only draft publication is separately authorized.

## File responsibilities and shared interfaces

Modify gcp/schema.sql only approved A core blocks; nullable closing cache column only. Create lib/av_options_revisions.py for canonical normalized/v1 codec, fixed dataset/group types, publication/resume/select/current/read projections and bounded native run context; lib/av_options_admission.py for measured storage/day/lifetime counters, leases and reconciliation; lib/av_options_inputs.py for actual qualified provider projections. Existing source producers, options-only watchlist component, maintenance CLI and narrow grid early recovery change only their specified A boundaries. Large index SQL is gcp/migrations/av_closing_slot_index.sql. No B/C/D/COMMON/DATA/Gov gate ownership.

Stable planned public interfaces from the spec: publish_options_group(group, *, claim, reservation, source_capture, input_revisions, dependent_invalidations, deadline) -> GroupPublicationResult; resume_options_group(group_key, *, deadline) -> GroupPublicationResult; select_options_revision(dataset,ticker,group_key,*,source_session,as_of,mode) -> RevisionObservation|RevisionUnavailable. Dependent invalidations are typed fixed registrations; no user SQL/plugin. resolve_options_input consumes actual acknowledged DATA relations, never unmerged provider code.

Pure owned codec choice: encode_normalized_payload(value, *, row_key) -> bytes; normalized_payload_identity(value, *, row_key) -> frozen PayloadIdentity(payload_sha256,serialized_bytes,payload_codec). SHA of complete deterministic UTF8 av-options-normalized/v1; source-row order uses exact source identity; other arrays registered natural key; exact Decimal plain tokens/NULL distinct0/finite/1024token bytes. PG readback numeric parse uses Decimal. Typed value/provenance/known-clock records are frozen and bounded, not invented source observations.

All module/name additions remain inside explicitly owned files. If an earlier interface needs a routine implementation choice, record the exact signature/DDL in this plan's SDD ledger and send source-owner consumers the real implemented artifact; do not claim draft choices are approved MAIN or fake provider evidence.

## Verification environment

Baseline/RED/GREEN use safe child selectors: clear CLOUD_SQL_CONNECTION_NAME/CLOUD_SQL_URL/GOOGLE_APPLICATION_CREDENTIALS and set DB_HOST127.0.0.1, DB_PORT25432, dummy trading_user/testpass, DB_NAMEav_options_source. Local av_ scratch PostgreSQL only; no production selector/schema/index, real AV/GCS/gcloud or credential logging. Preserve startup authentication/guards; hermetic Docker for broad/native tests, no auth mounts/network and pinned runtime identity. Pure/API unit suites isolate external transport; required SQL/constraint/rollback/races use actual tests/integration with an expected configured DB/schema and FAIL if missing, never SKIP. Driver/index/local/source protocol tests do not prove target cold GCP latency/RSS; record the distinction.

Save every exact command/exit/output and task BASE in ignored .superpowers/sdd/2026-10-13-feat-option-001-av-source-journal. Run staged spec_gate --commit BEFORE each commit; no hook skip/unowned gate fix. Actual appropriate targeted tests first; repeat/broaden only on new changes or unresolved concerns.

## Review focus

1. JSONB numerical readback/reordering/huge finite decimals/NULL vs0 must retain exact normalized digest and immutable header/body/expiry receipt binding (Task1).
2. Late seq2 zombie after seq3, lost claim/source COMMIT ACK and UTC midnight must not restore old financial state, guess knowledge clocks or refund attempts (Tasks2/3/5/6).
3. Help/preopen/holiday/halfday/calendar outage and manual recovery ENV must not issue unauthorized source work or fabricate scheduled health (Tasks9/10/11).
4. Old mature still-present objects and protected payloads must not starve fair finalized probes, falsely debit bytes or exceed SAME90 after crash/softdelete/policy change (Tasks8/14).
5. Warm/coalesced API recovery cannot numerically serve B/old mutable cache, exceed5s/2MiB or use a copied unmerged positive helper (Task4).

## Task 1: Immutable normalized codec, revision and payload schema

Spec: §Exact core storage/codec and whole-tuple immutability. Advances A1.
Files: gcp/schema.sql; lib/av_options_revisions.py; tests/lib/test_av_options_normalized_payload.py; tests/integration/test_av_options_revision_schema.py.
Interfaces: produces PayloadIdentity/codec and exact av_options_revisions, av_options_revision_payloads, av_options_revision_publications, compact expiry receipt tables and named local/global expiry+smallheader indexes; same composite revision/dataset/ticker/normalized digest FK. Only actual expiry authority may delete eligible body.
- [ ] Write RED codec tests for canonical reordered objects/source rows, exact Decimal,0/NULL, nonfinite/duplicate/numeric cap and actual PG roundtrip; schema tests directly mutate ALL header/publication/body/expiry fields without changing PK/sequence and exercise mismatched identity/hash/ref.
- [ ] Run pytest tests/lib/test_av_options_normalized_payload.py tests/integration/test_av_options_revision_schema.py -q; expect FAIL for missing interface/schema or rejected broken integrity.
- [ ] Implement fixed av-options-normalized/v1 codec and schema/constraints/immutable authority, no provider/source calls; actual source codec values and receipt/source hash distinctions follow primary.
- [ ] Repeat same command; expect PASS, required SQL cases no SKIP. Native schema fresh/reapply/transaction rollback proof counted; no production upgrade.
- [ ] Gated focused commit; record actual tests/BASE and remaining cross-task receipt/claim dependencies. Do not declare later Task14 expired-deletion authority complete from pure schema alone.

## Task 2: Canonical claims, leases, finite counter and grant schema

Spec: §Claim clocks/sequence + §source attempts/grants. Advances A2.
Files: gcp/schema.sql; lib/av_options_admission.py; tests/integration/test_av_options_claim_schema.py.
Interfaces: frozen GroupClaim/Reservation typed projections; exact group locks, positive allocated sequence, origin/lower-bound/lease generation, immutable claim-publication tuple, serverUTC attempts and fixed initial grant; finalized probe exact partial index/operational due cursor.
- [ ] RED two-connection allocation/claimACK/lease/greatest-sequence cases, invalid key/origin/clock/constraint and copied/reset/second grant; test exact partial-index metadata.
- [ ] Run pytest tests/integration/test_av_options_claim_schema.py -q; expect FAIL then implement owned fixed schema/typed projections.
- [ ] Repeat; expect PASS real PG concurrency/constraints with no recycled seq or fake knowledge clock.
- [ ] Gated focused commit/ledger; source/runtime atomic caps are Task5, not inferred from schema.

## Task 3: Whole-group atomic publisher and bounded run projection

Spec: §Core immutable revisions/publication/actual observability. Advances A3.
Files: lib/av_options_revisions.py; tests/integration/test_av_options_whole_group_publisher.py.
Interfaces: produces exact publish_options_group and GroupPublicationResult consumed Tasks4/9–11; consumes Task1 codec and Task2 claimed reserved identities; actual input/capture records, latest-sequence lease guard and fixed dependent invalidations, not user callbacks.
- [ ] RED real PG chunk/history/payload/cache/membership/completion rollback, original→repair/removal/count/hash/side/adjusted-key collision, concurrent zombie, archive/commitACK uncertainty and bounded real run identity/watermark/terminal failure/redaction tests.
- [ ] Run pytest tests/integration/test_av_options_whole_group_publisher.py -q; expect FAIL then implement bounded staged/set-based same-TX publication, postACK clock and safe run projection. Default origin is NULLunknown; typed COMMON adoption refuses absent actual MAIN capability.
- [ ] Repeat; expect PASS, unchanged financial facts on failure, actual driver/RT/bytes/terminal counts inside <=10RT/group.
- [ ] Gated focused commit/ledger; no vendor capture or unmerged metadata/parser import.

## Task 4: SAME-revision ACK resumer and foundation HTTP refusal

Spec: §A4 foundation recovery. Advances A4.
Files: lib/av_options_revisions.py; narrowly grid.py::_fetch_on_demand/get_grid_live early probe; tests/gcp/test_av_options_ack_recovery.py; tests/api/test_grid_ack_recovery_http.py; real PG helper controls in integration collection.
Interfaces: exact resume_options_group; actual recovered source identity, no B financial response.
- [ ] RED actual publisher death after COMMIT/preACK then regular/closing/direct/HTTP cold/warm/coalesced/exception retry, newer/pending/expired/body inconsistency and slow/overcap controls.
- [ ] Run pytest tests/gcp/test_av_options_ack_recovery.py tests/api/test_grid_ack_recovery_http.py -q; expect FAIL. Implement only claimed coherent zero-call ACK recovery and typed serving_contract_pending/no-store BEFORE mutable cache.
- [ ] Repeat; expect PASS: same revision/object/membership/seq/actual later ACK,0vendor/new source/quota, complete<=2MiB/hard+p955s. Real SQL proof recorded separately, never B stub positive.
- [ ] Gated focused commit/ledger; downstream qualified serving belongs actual future API owner.

## Task 5: Atomic finite admission and every reconciliation kill point

Spec: §Global source/storage/lease/grant limits. Advances A5.
Files: lib/av_options_admission.py; tests/integration/test_av_options_admission.py.
Interfaces: reserve/admit/finalize/release/reconcile fixed typed states used source tasks, `reconcile_expired_reservations` consumes actual retained source/header/archive disposition; root alone provisions grant/measurements.
- [ ] RED every daily class and grant90/90 atlimit race, UTC midnight, size/stale/unknown/global headroom, copied IDs/date/class/target/parallelism, seq2/seq3 zombie, EVERY reservation/claim/source/archive/commit/finalize/release death/takeover and false refund.
- [ ] Run pytest tests/integration/test_av_options_admission.py -q; expect FAIL then implement SAME lock/checked counters/measured reservations and conservative unknown reconcilers.
- [ ] Repeat; expect PASS:0before-source on denial, no attempt/task refund, exact unchanged other groups, full-activation false absent downstream proof and budgeted real callbacks.
- [ ] Gated focused commit/ledger; no production grant or measurement worker.

## Task 6: Strict claim-first selector and source-current primitive

Spec: §Selector + cadence/age/due/recovery. Advances A6.
Files: lib/av_options_revisions.py; tests/integration/test_av_options_strict_selector.py; tests/lib/test_av_options_current_source_freshness.py; tests/fixtures/av_options_source_semantics_v1.json.
Interfaces: exact select_options_revision plus evaluate_current_options_source bounded shared facts; SAME source-semantic fixture for downstream actual API/replay/OPS.
- [ ] RED greatest unavailable/removed defeats complete, equalclock/sequence, pending/unknown/prelowerbound/future/legacy/expired, real cutoff source-repair parity and oldretrieval/laterACK stillstale; normal/halfday/DST/nondue exact regular150s/EOD21:45/close+30 due cases.
- [ ] Run pytest tests/integration/test_av_options_strict_selector.py tests/lib/test_av_options_current_source_freshness.py -q; expect FAIL then implement indexed bounded read and pure authoritative current facts, no per-row SQL/cache fallback.
- [ ] Repeat; expect PASS including representative query plans and returned-byte/driver bounds; OPS regular/EOD alert adoption remains pending.
- [ ] Gated focused commit/ledger; no global live coverage/monitor claim from fixture.

## Task 7: Actual provider/input adapter and truthful unsupported histories

Spec: §Exact A7 provider/main mapping. Advances A7.
Files: lib/av_options_inputs.py; lib/gamma.py/lib/options_greeks.py input-consumption parameters ONLY; tests/lib/test_av_options_input_adapter.py; tests/integration/test_av_options_input_publications.py.
Interfaces: resolve_options_input actual observed source/ticker/session/basis/unit/revision/ACK/cutoff projection; no rate/yield writer or copied DATA/price policy.
- [ ] RED missing/future/legacy/inputhash/basis/wrong ticker/NULL/unit/retirement/clock proof and known qualified zero, actual NYSE provider adapter and real merged DATA joins only when present.
- [ ] Run named suites; expect FAIL then implement exact qualified input selection/forwarding and typed source_revision_unavailable on genuinely missing capabilities.
- [ ] Repeat; expect PASS actual merged input/schema positive and honest negative compatibility; do not substitute fake provider/preproduction schema for absent actual MAIN or claim completed positive acceptance until available.
- [ ] Gated focused commit/ledger with literal dependency identities/limits; holds final readiness if source/provider positive obligation unavailable.

## Task 8: Native canonical raw archive and finalized generation proof helper

Spec: §One source body/all five prefixes/native disposal. Advances A8.
Files: lib/av_options_revisions.py/lib/av_options_admission.py owned archive/proof blocks; tests/gcp/test_av_options_archive.py.
Interfaces: frozen capture/ArchiveReceipt with actual exact original bytes/hash/URI/generation/creation clock; typed absence/policy proof shared with Task14, not expected-age-as-deletion.
- [ ] RED exact raw/archive reuse, failed/orphan/empty/source validity, all horizons/prefixes, active/noncurrent/softdeleted/403/404/policy/missing-generation/slow/oversize/lasttimeout native SDK protocol controls.
- [ ] Run pytest tests/gcp/test_av_options_archive.py -q; expect FAIL then implement bounded native GCS capture/proof and one-object policy with runtime cap/retry/refusal.
- [ ] Repeat; expect PASS native recorded SDK subrequests/bytes/deadlines, no invented generation/ACK or0charged bytes; no real GCS mutation.
- [ ] Gated focused commit/ledger; real target read-only source/policy permission proof remains root readiness evidence.

## Task 9: Historical/EOD actual main/session producer

Spec: §A9 calendar/native cutover. Advances A9.
Files: gcp/fetchers/fetch_av_historical_options.py; tests/gcp/test_av_options_historical_producer.py; real PG native fixtures in integration.
Interfaces: actual main/process_ticker/_trading_days consume Tasks3/5/6/7/8 with actual job/run/source intent; no broad monthly/raw fallback.
- [ ] RED actual main/direct negative guessedweekday/calendar/holiday/weekend/future/inprogress/DST/halfday, whole native membership/counters/bytes/deadlines and every complete/skip/error/refusal/ACK recovery/terminal outcome.
- [ ] Run named suite; expect FAIL then implement strict completed-session admission before vendor/archive/financial SQL, finite EOD4 versus root grant and source whole group.
- [ ] Repeat; expect PASS hermetic native and actual PG publication/safe failures within original selected bounds, no manufactured historical source clock.
- [ ] Gated focused commit/ledger; do not run production backfill.

## Task 10: Regular realtime actual main/transport phase

Spec: §A10 RTH/calendar/cumulative source15. Advances A10.
Files: gcp/fetchers/fetch_av_realtime_options.py; tests/gcp/test_av_options_realtime_producer.py; actual PG native fixtures.
Interfaces: pass SAME phase deadline/context through actual main/process_ticker/fetch transport; finite typed-empty attempt admission, actual native whole-chain publication.
- [ ] RED all six09:00–09:25 launches/holiday/weekend/open-inclusive/close-exclusive/halfday/DST/outage; real blocked connect/read/body/pacing/empty retries enforce15ALLsource versus150whole, no late source request.
- [ ] Run named suite; expect FAIL then replace60-second reachable transport/unguarded main with strict shared calendar/deadline/archive/publisher controls, no per-ticker15 allowance.
- [ ] Repeat; expect PASS source counters/counts/partial failures/terminal exact, no prefix/source promotion; actual PG/source protocol readback and measured whole shape recorded.
- [ ] Gated focused commit/ledger; no Scheduler/runtime changes.

## Task 11: Closing mode and lossless source/operation intent

Spec: §Closing schema/capture intent/index-compatible source rows. Advances A11.
Files: same realtime native closing-mode blocks; exact nullable capture_slot_ts cache column; tests/gcp/test_av_options_closing_producer.py; actual PG helpers.
Interfaces: exact closing normalized_values schema; source actualsession/slot/raw+normalized hashes/capture_intent distinct nullable COMMON operation pair, immutable on SAME-group later ACK.
- [ ] RED native scheduled/default/manual_recovery/--session-date admission windows and invalid pairs, normal/halfday/DST/holiday/alreadyACK/unknown origin/cap/body/side/key collision; actual real PG cache/header/payload/operation preservation.
- [ ] Run named suite; expect FAIL then implement exact3zero-retry/15+60+75 native source mode and whole latest-sequence closing cache replacement, no inferred ENV recovery/CLOSING enum/backfill.
- [ ] Repeat; expect PASS fields/hash/counts/actualACK/clocks, unknown/late recovery cannot fulfill scheduled health; missing COMMON implementation remains explicit pending.
- [ ] Gated focused commit/ledger; no existing cache constraint/identity broadening.

## Task 12: Literal closing-index admission and bounded migration

Spec: §Exact legacy index/large-heap preflight. Advances A12.
Files: gcp/migrations/av_closing_slot_index.sql; lib/av_options_revisions.py owned parent admission/report block; tests/gcp/test_av_closing_index_admission.py; real PostgreSQL migration fixtures.
Interfaces: immutable ClosingIndexAdmissionProof and pure conservative bounds plus native scoped autocommit application/cancel; exact SQL uq_etf_options_closing_slot_contract and separately idx_av_options_revisions_closing_slot ASC.
- [ ] RED metadata/incompatible column/index/stats/current107Mupper/two+three scans/representative IO/headroom/locks/long transactions/timeout-only/ownPIDabort; actual small PG index uniqueness/EXPLAIN/invalid recovery.
- [ ] Run named suite; expect FAIL then implement exact nullable-column/noDEFAULT and concurrent index literal with before-CREATE refusal and permitted proof/report controls.
- [ ] Repeat; expect PASS local correctness/refusal/abort targeting; actual fullheap/root disk/IO/artifact evidence remains pending, never extrapolate tiny tests as target qualification.
- [ ] Gated focused commit/ledger; no production ALTER/CREATE/count/operator action.

## Task 13: Options-only watchlist actual component

Spec: §A13 needs/backfill native component. Advances A13.
Files: scripts/backfill_watchlist_data.py::needs_options_backfill/backfill_options ONLY; tests/scripts/test_backfill_watchlist_options_contract.py.
Interfaces: intended actual completed NYSE session and acknowledged whole membership/source marker; existing source producer/context projection only.
- [ ] RED recentpartial/legacy/pending/future/source gaps/weekdayholiday/calendarunknown plus actual component success/failure/skip/recovery telemetry and finite source/grant path.
- [ ] Run named suite; expect FAIL then replace recent-any-row/weekday fallback for ONLY options component, preserving all other sources.
- [ ] Repeat; expect PASS no invalid vendor date or hidden unjournaled fallback; actual main/component invocation and driver counts recorded.
- [ ] Gated focused commit/ledger; no broad live watchlist dispatch.

## Task 14: Actual payload/lease/finalized-raw maintenance CLI

Spec: §Expiry receipt/native fair disposal/SAME90. Advances A14.
Files: gcp/options_retention_job.py; lib/av_options_admission.py owned helpers; tests/integration/test_av_options_retention.py; tests/gcp/test_av_options_retention_cli.py.
Interfaces: Task1 receipt/hash/expiry body deletion authority, Task5 no-refund lease reconciliation, Task8 native proof, Task2 indexed fair last/nextprobe cursor and actual postACK debit.
- [ ] RED actual main and real PG expired/unexpired/protected/FK/digest bodyDELETE+receipt rollback/commitpreACK recovery, ALL kill/takeover/no-false-refund states, fair growing-ledger1200/SKIPLOCKED/lateCAS/doubledebit/multiprefix/stillpresent/unknown/policy cases.
- [ ] Run named suites; expect FAIL then implement metadata-only100payload batches and native claim/proof/ACK credit inside SAME90, fair due cursor absolute86400 and no extra query/job/metadata allowance.
- [ ] Repeat; expect PASS real representative EXPLAIN/index/scanned rows and native SDK cap/bytes/deadline/query/driver/terminal counts; source/task attempts never refunded, measured unavailable stays charged.
- [ ] Gated focused commit/ledger; no remote lifecycle or production deletion.

## Task 15: Complete own delivery and qualified close-out package

Spec: §A15 ordinary source identity/actual main/staging. Advances A15.
Files: own FEAT-OPTION-00102/12 record, this plan, docs/runbooks/av-options-source-journal.md, docs/audits/av-options-source-journal-evidence.md; only declared eligible OPTIONS01/02/12 appended source notes/actual trusted sidecar and authorized exact05a/c/e outputs after compatible code MAIN.
- [ ] Record literal source/codec/schema/capability/cadence/retrieved-age/due/recovery/alert dependencies and exact all A1–14 test/hash/count/bytes/latency/quarter/cost/refusal/current-main identities; no hidden implementation code or premarked acceptance.
- [ ] With ACTUAL compatible GovVerifier/Counter/Cost CODE MAIN only, run unchanged trusted renderer/verifier and ordinary BASE gate/body/own-note/sidecar rejection proof. Baseline and branch actual docs audit: no NEW findings. Existing immutable historical/frontend/Chain/product cells untouched.
- [ ] Run exact spec_gate --pr origin/main and appropriate full source/native/integration/OpenAPI checks; expect PASS without skip/mask/unowned gate or false source snapshot.
- [ ] Prepare/test/review real separate post-CODE MAIN/staging/sidecar retirement/zero unexplained drift plan. Tick only actually executed code acceptance after independent root review, never pretend deployed/main/input regeneration/parity/alert/index proof.
- [ ] Gated own record/generated commits; source PUSH/ready only after root reads actual current review history/normal mandatory proofs and author publication guard. Root alone merges/deploys/provisions/repairs. After actual merge lawful docs-only plan close-out; all broader source/provider/global gaps remain explicit.

## Acceptance preservation and self-review

TaskN maps EXACT primary AN (15 true implementation/integration units); schema/codec/keys/indexes and native lifecycle checks assigned to their actual owners, no extra unit in delivery. All primary fifteen literal done_when entries are preserved in the draft PR body unticked; plan is their argument, not a changed contract. Shared interface scan: T1codec→T3/6/14; T2claim/lease/probe→T3/5/6/14; T3publish/resume→T4/9/10/11; T5admission→all producers/T14; T6selector/currentfacts→T7/9/13; T7actualinput→source/consumer qualification; T8archive/proof→source/T14; T12index→T11activation. Missing actual upstream/downstream capability refuses and keeps final acceptance pending; no fake positive resolves a dependency.

Baseline and every RED/GREEN command/output/BASE goes to the SDD ledger. New tests use real PG for SQL guarantees with expected DB/schema fail-not-skip. Schema prepare/legacy writer rollout/drain/final enforcement follows approved actual ownership, not a silent production upgrade. Root final independent review/current-head external cap precedes source publication/merge; no author claim replaces that review. This initial plan is ready to execute privately under existing approval; no task or production acceptance is marked complete here.
