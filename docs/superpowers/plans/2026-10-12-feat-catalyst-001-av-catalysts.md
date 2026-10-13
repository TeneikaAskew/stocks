---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-10-12-feat-catalyst-001-av-catalysts.md
supplemental_specs: [docs/superpowers/specs/2026-10-12-feat-catalyst-001-av-producer-receipts.md]
branch: fix/feat-catalyst-001-av-catalysts
pr: 1430
status: ready
---

# Reconcile AV earnings revisions and make catalyst ingestion reproducible implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Reconcile AV earnings revisions and make catalyst ingestion reproducible.

**Architecture:** Persist strict endpoint outcomes and immutable vendor/timing observations, archive original responses and maintain fair bounded work queues; use source-linked permanent vintages and manifests for historical reads and derived reactions.

**Tech Stack:** Python, PostgreSQL/pg8000, GCP Cloud Run/SQL/Storage/Scheduler, existing repository test and delivery tooling.

**Spec:** docs/superpowers/specs/2026-10-12-feat-catalyst-001-av-catalysts.md

Execution method selected by the user: parallel independent workstreams, one isolated worktree and author per branch. Read the linked approved spec; its Design, File ownership, Capacity and cost and done_when are binding.

## Global constraints

- Preserve tested core price/options behavior, source values, existing valid rows and canonical symbol keys.
- No unbounded backfill, silent vendor/database failures, financial constant substitution or cross-stream imports from unmerged work.
- Exclusive file ownership: Catalyst code: `lib/earnings_history.py`; `platform/api/routers/catalysts.py` (revision earnings reads, suppression of unversioned historical sections and strict availability/error handling for every section); `gcp/fetchers/compute_earnings_reactions.py` (source adapter and price-basis safety); `gcp/fetchers/_av_ingestion.py`; `gcp/fetchers/fetch_earnings_history.py`; `gcp/fetchers/fetch_news_sentiment.py`; `gcp/backfill_ticker.py` (news identity preparation/write block only, coordinated with DATA ownership of price blocks); `gcp/fetchers/fetch_rss_news.py` (identity preparation and write path); `scripts/backfill_news_sentiment.py` (identity preparation and conflict target); `gcp/fetchers/fetch_insider_transactions.py`; `gcp/fetchers/fetch_av_earnings_estimates.py`; `scripts/fetch_earnings_calendar.py`; `gcp/schema.sql` (catalyst provenance, source identity, timing observations, estimates, revisions, durable work/lease windows and reaction-input artifact block only). Tests use the exact paths named by done_when. Runbook: `docs/EARNINGS_PIPELINE.md`. Product records: this FEAT-CATALYST-001 record and traceability entry only. Deployment/configuration files and tests remain in the sibling DEPLOY branch.
- Use installed /workspace/stocks-venv Python dependencies. Baseline failures must be recorded before changes, not dismissed after introducing them.
- Require failed regression before each fix and passed regression afterward, meaningful bounded I/O tests, independent full-diff review and the current repository gate.

## Review Focus

- Vendor or database failure after durable progress must preserve committed groups and produce incomplete/nonzero outcome.
- A later source correction must not enter an earlier knowledge cutoff or retain stale certified derived fields.
- Actual entrypoint/CLI/API callers must invoke the validated contract rather than bypassing helper-only tests.
- Limit, timeout, payload or query exhaustion must expose pending coverage without truncating the denominator.
- Legacy or absent provenance must remain unavailable; deployed schedules cannot establish publication knowledge.

## Task 1: Implement and prove the capability contract

Spec: § Problem, § Design, § File ownership, § Capacity and cost, § Risks. Advances every done_when item; this task is one independently reviewable capability workstream.

- [ ] Read the current implementation, relevant approved spec and full related tests; record exact baseline revision/results and candidate issue/PR history when claiming an issue.
- [ ] Reproduce the specified defect with a focused failing test; preserve the original failure output as evidence.
- [ ] Implement the Design only in owned files, retaining accurate vendor contracts, bounded memory/queries, explicit incomplete outcomes and the shared session calendar.
- [ ] Add and run the contract, failure, idempotence, date/DST and bounded I/O tests required by done_when; execute the actual module CLI in a dry-run/stubbed-I/O smoke.
- [ ] Document command, source revision, data volume, API/SQL round trips, timeout headroom and costs; distinguish working code from completed production repair.
- [ ] Update only this capability record's Status and Last reviewed in 02-FEATURE-CATALOG.md; avoid claiming unrelated capability completion.
- [ ] Before each commit run python scripts/gate/spec_gate.py --commit; commit only owned changes, without bypassing hooks.
- [ ] Generate an SDD review package for the full branch diff and submit it to the parent for independent spec/code review. Write a report with changed files, checks, commands, caveats and residual findings.

## Task 2: Complete review and delivery records

Spec: § Validation and rollout and all done_when items. Completes reviewable delivery without claiming unperformed live data repairs.

- [ ] Fix the complete first-review findings as one batch, rerun affected checks and provide a scoped review package of that fix range; max two PR review rounds.
- [ ] Compare docs_audit.py on this branch and origin/main; report no new findings. Run generated-doc checks and preserve any baseline failures explicitly.
- [ ] Push only this authored branch, open its draft PR with FEAT-ID title and exact spec/plan links, copied done_when boxes and populated Capacity section.
- [ ] Set this plan's pr field to its returned PR number; add that number under this FEAT-ID in 12-PR-ISSUE-TRACEABILITY.md in this same PR, then rerun spec_gate.py --pr origin/main.
- [ ] Tick each done_when item only with concrete test/file/query evidence, retain required canvas report-only marker and present the final head to review.
- [ ] Parent coordinates current-head reviews/CI, merge, additive schema rollout, targeted deployment and bounded repair; no author merges or deploys independently. After actual merge, set plan status done on a separate docs branch.

## Acceptance evidence

These exact approved specification acceptance items require actual implementation evidence. Live production promotion remains the parent post-merge milestone.

- tests/gcp/test_fetch_earnings_history.py::test_refresh_selector_is_bounded_one_strict_query proves daily pending-quarter selection, weekly fair leased attempts capped at 100, failed-head rotation/backoff and force behavior.
- tests/integration/test_earnings_history_revisions.py::test_migration_and_updates_preserve_observed_versions proves real-clock legacy seeding, permanent append-only versions, unchanged-refresh idempotence and value reversions.
- tests/integration/test_earnings_history_revisions.py::test_revision_and_cache_rollback_together proves atomic installation and rollback, alternate-writer capture and concurrent upsert convergence.
- tests/lib/test_earnings_history.py::test_asof_excludes_future_revisions_and_reports_legacy_gap proves aware-cutoff validation, one bounded query and no current-cache fallback.
- tests/api/test_catalysts_asof_revisions.py::test_snapshot_before_eps_correction_returns_known_revision proves /api/catalysts/asof/{ticker} uses the revision reader and exposes unavailable legacy coverage.
- tests/gcp/test_compute_earnings_reactions.py::test_split_windows_are_rejected_without_point_in_time_factors proves exact -50 percent and smaller-split rejection, consistent OHLC normalization and rejection of current revised factors in historical mode.
- tests/api/test_catalysts_asof_revisions.py::test_historical_snapshot_suppresses_unversioned_sections proves late news, SEC, insider, calendar and price observations are omitted with explicit unavailable markers.
- tests/api/test_catalysts_asof_revisions.py::test_every_section_query_failure_is_explicit proves database/schema failures in every queried section differ from successful zero-row results.
- tests/gcp/test_compute_earnings_reactions.py::test_every_derived_row_carries_reproducible_provenance proves source revision/observation IDs, source/as-of clocks, configuration/rule, durable input artifact and code version on each new reaction.
- tests/gcp/test_av_catalyst_ingestion.py::test_mixed_failure_preserves_success_and_exits_nonzero proves valid empty, transport/vendor/malformed failure, durable group persistence and terminal accounting.
- tests/gcp/test_av_catalyst_ingestion.py::test_universe_failure_is_not_valid_empty proves strict eligibility failures cannot become fallback-only success while successful zero-row queries remain valid empty.
- tests/integration/test_av_catalyst_source_identity.py::test_nullable_feed_replay_converges proves repeated nullable news and insider payloads produce one economic/source identity without fabricated field defaults.
- tests/integration/test_av_catalyst_source_identity.py::test_all_news_writers_replay_under_migrated_constraints proves scheduled AV, ticker backfill, RSS and standalone backfill writers converge with NULL URLs and their ON CONFLICT targets remain valid throughout rollout.
- tests/gcp/test_av_catalyst_ingestion.py::test_terminal_note_includes_source_watermark_and_attempts proves structured watermark, coverage-completeness, Cloud Run task-attempt and vendor retry metadata on complete, empty, partial and failed terminal runs.
- tests/gcp/test_fetch_news_sentiment_capacity.py::test_news_modes_io_shape_and_quarter_timeout_budget proves per-mode call, expanded-row, byte, SQL-round-trip and bounded-group limits fit the quarter-timeout calculation without a silent slow fallback.
- tests/gcp/test_av_ingestion.py::test_exact_archive_and_failure_contract proves byte-exact capture, safe parameters/logs, missing-bucket and archive-failure handling, immutable object creation and dry-run isolation.
- tests/gcp/test_fetch_earnings_history.py::test_yahoo_timing_revision_has_independent_observation proves Yahoo timing changes retain their own observation clock, content and attribution independently of AV EPS bytes.
- tests/gcp/test_fetch_earnings_history.py::test_yahoo_provider_process_cancels_blocking_request proves actual child-process cancellation/reaping, instrumented HTTP-count/timeout bounds, rejected late results and the complete 100-ticker weekly budget.
- tests/gcp/test_av_catalyst_ingestion.py::test_failed_weekly_head_does_not_starve_universe proves 100 failed oldest successes do not prevent later eligible tickers being selected and retry/backoff clocks never alter source freshness.
- tests/gcp/test_av_catalyst_ingestion.py::test_saturated_news_subdivisions_eventually_advance_watermark proves ticker and topic windows split durably, survive restart, deduplicate boundary overlaps and eventually complete across bounded executions.
- tests/gcp/test_av_catalyst_ingestion.py::test_insider_full_scope_batched_capacity proves all 300 ticker outcomes, normalized bytes and SQL/queue round trips fit the admitted 900-second quarter budget with durable bounded groups.
- tests/integration/test_av_earnings_estimates_vintages.py::test_estimate_vintages_survive_refresh_and_raw_expiry proves immutable SQL estimate observations, retry idempotence and latest-known-at-cutoff reads without future consensus leakage.
- tests/gcp/test_fetch_earnings_calendar_persist.py::test_full_feed_archive_preserves_weekly_subset proves the complete AV calendar bytes are archived before the established business window is filtered.
- tests/gcp/test_fetch_earnings_history.py::test_backfill_phase_budget_preserves_primary_outcome proves recurring/repair primary-only calls do not launch the market backfill, unsafe combined manual chains are refused and an admitted manual chain cannot hide phase failures.
- docs/EARNINGS_PIPELINE.md records bounded CLI commands, measured per-phase volume/calls/runtime/archive bytes, estimate cost multiplication, point-in-time coverage limits, source identities and the accountable av-api-key rotation role.
- Reviewed FEAT-DEPLOY-001 contract evidence includes tests/gcp/test_deploy_av_remediation.py::test_catalyst_create_update_runtime_and_secrets and ::test_all_lifecycle_writers_preserve_av_prefix_retention, tests/gcp/test_deploy_av_remediation.py::test_calendar_secret_refs_and_missing_secret_preflight, a targeted deployed-state verifier and docs/EARNINGS_PIPELINE.md staged-identity/primary-only promotion checklist; actual deployed verification is the mandatory post-merge parent milestone.
- docs/product/02-FEATURE-CATALOG.md FEAT-CATALYST-001 record and docs/product/12-PR-ISSUE-TRACEABILITY.md identify this implementation PR as implementation verified / rollout pending; they do not claim production rollout complete before post-merge verification.
- tests/gcp/test_av_catalyst_predecessor_manifests.py::test_daily_manifest_links_full_assessed_scope_and_acknowledged_sources proves full-window eligibility with bounded fetching, reused verified revisions, matching history/reactions linkage and refusal of pending, wrong-scope, missing or future acknowledgement before OPTION admission.

## Complementary approved contract intake — 2026-10-13

Actual canonical main merge76783d56642a633cac4d7f0b6d258b52901a2fd0 (PR1446), approved producer-receipts spec SHA25608035b3816975ae05b41f4cdd9aa3b0e08eafa5226687e3985a0e61b6eb72c5f. Original1419 specification and its28 done_when items remain unchanged. All13 complementary done_when items are additionally binding (the original10 plus terminal bounds, full reaction I/O and cross-consumer canonical vectors). The sole author updated this still-DRAFT branch onto actual main only; preserved former1dfb checkpoint in local backup/catalyst-before-supp-76783. No sibling implementation was imported. All acceptance remains unticked.

## Task 3: Canonical identities and bounded permanent publication

Spec: complementary § Byte-exact scope and manifest hashing; § Acknowledgement and immutable publication. Advances complementary done_when[1,7,8,10].

- [ ] Preserve a pre-fix failure from actual publisher collision/malformed canonical input/oversized manifest and bounded-terminal reference cases.
- [ ] Commit the four exact known-answer inputs/bytes/digests at tests/fixtures/av_catalyst_scope_vectors.json; implement typed symbol/event/proof clock normalization, duplicate/nonfinite/type refusal and explicit digest kinds in owned producer code. Actual independent consumer parsers remain separately owned integration prerequisites; no helper-versus-itself claim.
- [ ] Bound full SQL manifests to8MiB before publication; emit identical structured log/job_runs.note projection <=64KiB with exact ID/digest/bytes/scope/counter references and bounded error details. Preserve full1239-symbol SQL proof, reject partial/oversized identity, and prove missing/future/uncertain/colliding ACK refusal using actual PostgreSQL.

## Task 4: Durable post-source-ACK estimate receipt publication

Spec: complementary § Additive permanent schema and identities; § Estimates daily native producer and receipt denominator. Advances complementary done_when[0,1,2,11].

- [ ] First fail an actual empty/nonempty group replay/ACK/cutoff case against old proposed transaction known_at semantics.
- [ ] Add exact append-only av_estimate_receipt_publications DDL/index/FK/check constraints; persist its source_commit_acknowledged_at only after complete source ACK, then require receipt publication ACK. Preserve original observation ID/transaction clock; return stable stored receipt clock for empty AND nonempty retries and reject collisions/uncertainty.
- [ ] Execute actual estimates daily CLI producer against isolated PostgreSQL for native payload retention, valid empty, full/selected/pending counters and publication/terminal linkage. Update bounded asof availability reader to use the matching durable receipt/run publication, never a proposed observation clock alone.

## Task 5: Native daily/weekly observed-cohort lineage and honest unknown scope

Spec: complementary § Calendar AV-native capture; § History and reactions daily/weekly exact linkage. Advances complementary done_when[3,4,5,6].

- [ ] First fail native daily AND weekly CLI cases at configured1239/selected<=100 with reused source-backed observed events, exact inclusive end-29..end boundary and nullable no-capture/failure evidence.
- [ ] Persist actual observed_snapshot/unknown/failed per-symbol shapes, distinct observation/window/raw-refresh/event counters and actual lineage clocks. independent_expected_cohort_proof remainsNULL and full-current coverage remains dependency_pending; never require or fake a nonexistent independent proof producer.
- [ ] Qualify only current-revision observed analytics under exact source/event/revision/ACK/code/image scope. Refuse wrong/future/missing lineage and both old/fresh captures promoted to vendor watermarks. No new Sunday CLI flag/job/source call or nonAV instrumentation.
- [ ] Execute actual native calendar producer against PostgreSQL before business filtering; preserve raw complete AV horizon separately from business/nonAV selections and source-clock/availability proof.

## Task 6: Batched reaction I/O within unchanged450second admission

Spec: complementary § Capacity and cost; § History/reactions linkage. Advances complementary done_when[4,9].

- [ ] First fail actual source-adapter/caller shape controls for the former100 per-ticker price queries and repeated whole timing payloads.
- [ ] One compact financial query plus one deduplicated independent timing query, ten<=10ticker/26000bar/16MiB streamed price reads,100<=100row atomic artifact/derived writes with <=1MiB each parameter (<=2MiB combined); all119 network round trips and actual CPU/serialization/setup/final ACK count.
- [ ] Actual merged DATA helper/schema remains missing at intake. Implement honest refusal/batched source paths without copying or faking a helper. Required native positive lineage/max10000-row integration becomes executable only after actual DATA main merge; no new skip/xfail or premature positive evidence.
- [ ] Prove actual maximum caller with real PostgreSQL and the merged helper fits declared420s planning/450s admission and peak working-set, with complete driver-delay accounting. If actual bounds fail, preserve durable groups/pending and revise bounded architecture; never raise timeout or hide fallback.

## Task 7: Supplementary delivery evidence and final review

Spec: complementary § Validation, ownership and activation; original § Validation/rollout. Advances complementary done_when[11,12] and original delivery clauses.

- [ ] Record exact commands/source hashes/data/SQL counts/serialized bytes/runtime/peak/storage headroom; distinguish observed analytics from unsupported full-current vendor/global/historical coverage and deployed milestones.
- [ ] Update only owned runbook/catalog/traceability with original28 plus complementary13 exact acceptance in draft1430; actual independent consumer fixtures, DATA positive integration, generated-documentation and Gov runtime/audit are honest dependencies until tested.
- [ ] Run appropriate focused/native mandatory PostgreSQL cases with fail-on-missing integration selectors, compare branch/main docs audit and actual PR gate, then submit full combined branch for root-owned independent review/CI/merge and promotion. No author deployment or acceptance ticks borrowed from proposed contracts.
