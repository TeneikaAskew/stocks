---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md
branch: fix/feat-data-001-av-market-data
pr: 1489
status: ready
---

# Qualified AV Market Data Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, one sole DATA author. Root arranges independent whole-branch review and normal merge; no child agents or sibling source imports. Each task carries real RED/GREEN, checked verification and ledger evidence.

**Goal:** Preserve actual AV economic/source evidence, publish bounded coherent adjusted daily data and selected reference feeds, and make every enumerated consumer fail closed on unavailable inputs.

**Architecture:** Add owned nullable/source-journal schema, immutable raw/canonical artifact and post-ACK publication paths. Keep raw executable prices distinct from adjusted continuous analytics, use one pure typed adapter, and share actual transactional source-revision guards. Existing jobs keep their approved finite budgets; unsupported research writers are retired rather than given a new algorithm platform.

**Tech Stack:** Existing Python/pandas/SQLAlchemy/pg8000/PostgreSQL/GCS tooling, stdlib JSON/SHA256/UUID, pytest and existing delivery commands; no new dependency, job platform or provider.

**Spec:** docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md, immutable SHA256445a1095ba925ffae883a67074ee5e976db6015b97d0d563438b56d456229a9b, actually merged a9ecbf9973b4ab922801ad4db348449e3f113890 via PR1483. This branch starts at that actual main, not an unmerged implementation.

## Intake and ownership

CHANGE under existing FEAT-DATA-001: Data platform / Ingestion, storage, freshness / fetcher jobs / Production but needs remediation. All fourteen original DATA/capacity/freshness/observability/reliability/replay/governance/performance requirements plus REQ-GOV-001/REQ-REVIEW-001 from the approved primary apply. Issue913 is touched, not automatically closed; the one listed LXZ5iRtXogCyFfApfsxXVN canvas retains its registered mode and final marker obligations. Only exact File ownership blocks and newly declared DATA source/availability changes are authorized. Common telemetry, IND after_replace/native timeout, OPTION derived invalidation helpers, CAT/schema/adoption, DEP resources and Gov/Counter/Cost each require their ACTUAL independently reviewed main before use; no copies, invented compatibility or self-approval. Deferred external dependencies do not authorize fake positive acceptance.

## Global Constraints

- Preserve actual raw observations, native aliases, NULLs, original NOTE/PK/identity and aware source/observation/ACK clocks. Source COMMIT+ACK precedes canonical artifact construction; separate artifact/derived COMMIT+ACK precedes input publication; unknown/crash gaps never backdate proof.
- Pure interface prepare_daily_basis(frame, *, basis_date, observed_at, mode, as_of=None, input_artifact) -> DailyBasisResult and restore_daily_units(values, *, basis, units) -> DataFrame; DAILY_BASIS_VERSION='av-adjusted-daily-v1'. Closed data_daily_input/v1+uuid versus catalyst_reaction_input/v1+sha256 identities bind actual payload bytes/hash/frame; no fake UUID/FK or PIT inference. Volume uses only verified splits, never dividend price factors or synthetic0.
- Full <=10,000-row available prefix before recursive metrics; actual maximum30 max-size prefixes together within120MiB. Explicit target selection, no implicit full-universe mutation or silent truncation. Legacy/unknown/current-only source cannot become strict replay, a neutral score or old nonNULL healthy fallback.
- Normal immutable FULL<=800 cohort, native100tasks/<=8parallel/<=8groups per task/1CPU1Gi/5400task/zero retry. <=50s shared any-first setup, <=32TOTALSQLRT/group, <=1170estimated/1200hard per task, whole <=17400s before original05:00 due; all100 actual task terminals required, no-work charged. Hard compute100x1200x.000020=$2.40/execution, not fast-idle60s assumption.
- Input120MiB/reference520MiB/seven-day3200MiB and shared20/40GiB remain. DATA GCS100GiB includes10reserve/90usable, exact raw/input prefixes Delete90; one shared complete inventory<=100kobjects/16MiB/20s, conservative reservations and no free unknown/orphan/inflight bytes. Conditional800 cannot guarantee216k steady objects fit.
- Index3AV/38TOTALRT (VIX20+SPX9+catalog9)/227estimate/300hard/1200task; fixed6-table<=20kTOTAL NULL-only VIX invalidation. Weekly<=3000TOTAL actions/sixresponses/54normalizedRT/637estimate/650hard/2700task; shared journal/action cleanup20s/10RT/4transactions plus existing listing bound. No resource/cadence/SQL/vendor/storage increase.
- Each HTTP route's complete qualified-success p95, aggregate guarded driver I/O, query/byte/source-window caps and absolute deadline match the spec, including sectors/movement2s/750ms/256KiB, watchlist100candidate preflight/50return/shared DATA+OPTION2s within5s/512KiB. Fast refusal is not qualified p95; all actual authentication/routing/driver/conversion/upstream/serialization counted.
- Expected job_runs TEXT declaration<=128KiB and actual postACK pointer<=1KiB, reserved nonterminal variants excluded from native completion; SAMEq1 md.data_source/md.close expected envelope<=256KiB within ALLfive1MiB/4s. No fake JSON column/source table or healthy prefix of an800 request.
- Actual COMMON metadata schema/helper CODE main precedes Task14 adoption; default helper remains UNBOUNDED/no timeout_s, same12legacy/14typed application INSERT and NOTE, not one cold physicalRT. Every caller bounds/counts its own driver work; missing compatibility refuses.
- Final SOURCE push/readiness holds actual GovVerifier/Counter/Bridge/Cost/common compatible CODE main, own ordinary SHARED-07 hash-bound note/committed sidecar/realCLI proof/noNEW/full trusted inventory/OpenAPI/35DoD/currentHEAD CODE+CI+conversations. CORE1458 stays its separate branch/plan; no gate/workflow/initializer/registry-watcher edit here. Source identity is not production availability.
- PostgreSQL evidence uses explicit dummy localhost DB/private namespaces; actual mandatory integration CI fails missing schema/DB, no skip/xfail/fake atomicity. No live vendor/production mutation or rollout in implementation. Required actual deployed/native/staging/retirement proof remains root-owned postmerge acceptance.

## Review Focus

- Latest completed NULL/invalidated source after an older valid row stays unavailable; never filter it out before selecting the anchor (Tasks4/9/12/13).
- Changed action date, source revision between read/calculation/write, failed COMMIT delivery and retry must preserve actual identity/clock and conservative unknown state (Tasks1/4/7/8).
- Complete source/archive/quota failures across100/800 tasks, noncore GCS versus core3 SQL and permanent uncertain reservations must preserve full requested/deferred denominator (Tasks3/4/8).
- Split-volume-unavailable can permit qualified price-only analysis but not RVOL/liquidity/volume-dependent reactions or imputation; output levels/ATR/quotes share one known raw target basis (Tasks2/5/9/12/13).
- Legacy CLI catches, direct mutable helper calls, P1 SQL clients continuing after errors, stale TTL and current-only public persistence cannot evade refusal or counterfeit success (Tasks10/11/13/14).

## Test and execution discipline

Use /workspace/stocks-venv/bin/python and checked subprocess return codes. Baseline actual existing backfill/applier99tests PASS2.05s; artifact work/av-execution/market-data-baseline-tests.log. Per component record meaningful real RED/main before production changes, targeted GREEN+neighbors and actual PG where specified. Final whole affected suites/required gates are mandatory; unrelated live/source operations are not run merely to inflate counts. No completion ledger line without actual named full-task verification. Task interface names below are author implementation choices within the approved source semantics; no body/proof stands in for an unavailable producer or external prerequisite.

## Task 1: Endpoint/schema/provenance and quota metadata

Spec: Storage, revision and provenance contracts; Packaged registry proof. Advances one-based done_when[2, 3, 4, 6, 12, 20].

**Files:** `gcp/schema.sql (owned nullable daily/ref/journal/source/quota blocks only)`; `gcp/config/alphavantage_endpoints.json`; `gcp/fetchers/fetch_av_reference_data.py (installed registry loader only)`; `tests/gcp/test_av_endpoint_registry.py`; `tests/integration/test_av_data_storage_contracts.py`.

**Interfaces:** load_endpoint_registry() -> dict from module-relative gcp/config; actual av_response_journal, revision/publication/reference keys and indexes EXACT approved DDL; typed-only source records never synthesize known_at.

- [ ] Step1: Write meaningful failing actual tests for test_registry_accounts_for_128_functions/test_packaged_registry_path plus realPG declared keys/invalid types/atomic constraints/publication quota/retention EXPLAIN; incompatible existing schema refuses without rewriting.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_endpoint_registry.py tests/integration/test_av_data_storage_contracts.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 2: Pure certified daily economic basis

Spec: Literal shared price-basis interface; Complementary identity and volume. Advances one-based done_when[1, 7, 30].

**Files:** `lib/price_basis.py`; `tests/lib/test_price_basis.py`.

**Interfaces:** prepare_daily_basis and restore_daily_units literal signature/result from Global Constraints; PriceBasisUnavailable(reason_code) sanitized; whole canonical artifact_payload/hash/frame binding before math.

- [ ] Step1: Write meaningful failing actual tests for split200→100/adjusted100→100 and dividend100→98/adjusted98→98; exact raw/price/share/dimensionless restoration; UUID versus actualCAT SHA namespace; wrong bytes/frame/clock/current-vintage/NaN/missing factors/volume refuse; caller inputs unchanged.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/lib/test_price_basis.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 3: Finite native cohort and GCS source admission

Spec: Normal nightly automatic native-task cohort; Finite raw/input archive. Advances one-based done_when[6, 16, 18, 26].

**Files:** `gcp/fetchers/fetch_market_data.py (preflight/topology/archive selection)`; `gcp/av_price_publication.py (source admission/archive/reservations)`; `tests/gcp/test_av_daily_nightly_admission.py`; `tests/gcp/test_av_source_archive_contract.py`; `tests/integration/test_av_daily_cohort_admission.py`; `tests/integration/test_av_source_archive_reservations.py`.

**Interfaces:** immutable complete cohort plus actual native task index assignment; owned source-quota CAS/reservation and exact URI#generation/hash/ACK; full declaration/pub SQL and core3 input format remain exact spec.

- [ ] Step1: Write meaningful failing actual tests for 100/800 full requested identities, any-first winner/race/crash, no-work all100 runtime/cost and fixed50/1200 budgets; unknown/over100GiB/100k/bytes source refuses BEFORE mutation, conservative retained reservation; no core3 shrink/synthetic resolver.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_daily_nightly_admission.py tests/gcp/test_av_source_archive_contract.py tests/integration/test_av_daily_cohort_admission.py tests/integration/test_av_source_archive_reservations.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 4: Atomic raw daily/minute publication and guarded reads

Spec: Atomic revision guard; Raw minute source; Every intraday publication. Advances one-based done_when[1, 3, 9, 10, 18].

**Files:** `gcp/av_price_publication.py`; `gcp/fetchers/fetch_market_data.py`; `gcp/fetchers/fetch_alphavantage_intraday.py (fixed native hook/source blocks)`; `gcp/fetchers/fetch_premarket_refresh.py`; `scripts/deep_backfill_ticker.py`; `scripts/backfill_watchlist_data.py`; `gcp/backfill_ticker.py`; `gcp/migrate_to_gcp.py (owned source blocks)`; `scripts/fetch_market_data.py`; `tests/gcp/test_av_market_repair.py`; `tests/integration/test_av_price_revision_atomicity.py`.

**Interfaces:** actual UUID source revisions and postsource ACK publications; sameTX journal/financial/NULL invalidation, stable bounded source snapshot; consume actual MAIN IND after_replace(conn) and OPTION prepare/append/ack interfaces ONLY when available, otherwise predelete dependency refusal.

- [ ] Step1: Write meaningful failing actual tests for raw adjusted=False actual default/manual/repair writes and every marker; concurrent stable read/changed-watermark refusal; hybrid actual build_daily_row field receipts and rollback; all9 derived clears preserved, only3 OPTION claims/5extraRT within32; missing dependency never copied or bypassed.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_market_repair.py tests/integration/test_av_price_revision_atomicity.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 5: Full-prefix indicator/STRAT regeneration and retained repair

Spec: Inception-consistent daily compute; Full-retained-prefix migration. Advances one-based done_when[1, 3, 10].

**Files:** `gcp/fetchers/backfill_daily_indicators.py`; `lib/data_loader.py (qualified frame transport)`; `lib/strat.py (daily adapter only)`; `tests/gcp/test_av_daily_basis_parity.py`; `tests/integration/test_av_retained_prefix_migration.py`.

**Interfaces:** Task2 basis analysis_frame/raw_frame, Task4 protected read/source identity; existing formulas/classifier unchanged, restored price units and exact av-adjusted-daily-v1 provenance.

- [ ] Step1: Write meaningful failing actual tests for >300/inception EMA/OBV/RSI/ATR/STRAT/combo parity live/backfill; nullable index volume price-only; old factor/basis/source rejects; full retained coefficient migration real500-row chunks rather than100-row tail, bytes/target caps.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_daily_basis_parity.py tests/integration/test_av_retained_prefix_migration.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 6: Dedicated native indices and fixed VIX invalidation

Spec: Native VIX replacement; Session dates and bounds. Advances one-based done_when[2, 18, 24].

**Files:** `gcp/fetchers/fetch_av_reference_data.py (index/catalog)`; `gcp/av_price_publication.py (fixed VIX atomic source blocks)`; `gcp/research/strat_engine/strat_data_builder.py`; `gcp/research/strat_engine/strat_dataset.py`; `gcp/research/strat_engine/strat_pred_serve.py`; `gcp/research/strat_engine/intraday_momentum.py`; `gcp/research/magnitude_engine/mag_inference.py`; `lib/movement_statement.py (pre-imputation VIX guard)`; `tests/gcp/test_av_reference_data.py`; `tests/gcp/test_av_vix_feature_consumer_contract.py`; `tests/integration/test_av_vix_feature_invalidation.py`.

**Interfaces:** INDEX_DATA/CATALOG actual SPX/^VIX native observations/settled dates/NULL volume; fixed6-table old/new-next-date union<=20k, atomic NULL ONLYvix_close/vix_tercile under38TOTALRT and300hard.

- [ ] Step1: Write meaningful failing actual tests for normal native writer ZERO SPX/VIX calls (one dedicated producer); actual old/new lost/acquired date, rollback/overcap-before-source; every actual model/magnitude/movement/cached pre-imputation caller refuses invalidated VIX instead of legacy-cache/neutral0.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_reference_data.py tests/gcp/test_av_vix_feature_consumer_contract.py tests/integration/test_av_vix_feature_invalidation.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 7: Bounded weekly ETF/actions/listing and retention

Spec: Bounded normalized-action expiry; Listing snapshots retain90days. Advances one-based done_when[2, 6, 15, 20, 22].

**Files:** `gcp/fetchers/fetch_av_reference_data.py (weekly mode)`; `gcp/schema.sql (scoped indexes/expiry state only)`; `tests/gcp/test_av_reference_data.py`; `tests/gcp/test_av_data_capacity.py`; `tests/integration/test_av_data_storage_contracts.py`.

**Interfaces:** exact actual native response-scoped action snapshot IDs/revisions supersede moved-date/same-key/empty facts; <=3000TOTAL action rows before publication; 54normalized batches/637estimate650hard; shared20s cleanup.

- [ ] Step1: Write meaningful failing actual tests for six fragmented action responses cap/order, moved-date+empty snapshot atomic ACK/rollback; listing90-day bounded prune/date/source admission; indexed publication/cleanup EXPLAIN, partial retained backlog charged/no dryrun mutations, no failure→empty/default row.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_reference_data.py tests/gcp/test_av_data_capacity.py tests/integration/test_av_data_storage_contracts.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 8: Canonical input artifact and independently acknowledged proof

Spec: Permanent acknowledged daily-input publication; Hybrid provenance. Advances one-based done_when[3, 9, 10, 18, 28].

**Files:** `gcp/av_price_publication.py`; `gcp/schema.sql (exact av_daily_input_publications FK/index/binding)`; `tests/integration/test_av_daily_input_publication_ack.py`; `tests/integration/test_av_price_revision_atomicity.py`.

**Interfaces:** actual artifact UUID FK av_response_journal.journal_id, complete bytes/source_scope/binding/economic/code facts; source COMMIT/ACK THEN artifact/derived COMMIT/ACK THEN actual publication known_at; core3 SQL versus noncore exactGCS source resolver.

- [ ] Step1: Write meaningful failing actual tests for realPG source-to-artifact ordering, preACK gap, rollback/crash/lostACK/retry actual laterclock without backdating; whole hash/frame/source/basis/producer equality and strict <=as_of; copied operator metadata no proof; all8/32RT counted.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/integration/test_av_daily_input_publication_ack.py tests/integration/test_av_price_revision_atomicity.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 9: Daily live/analog/earnings analytical consumers

Spec: Actual daily consumers; Latest-row availability. Advances one-based done_when[7, 8, 17].

**Files:** `lib/agents/summarizers.py (daily market/analog branches)`; `lib/earnings_reactions.py (owned daily source/context)`; `lib/options_greeks.py (daily close clock only)`; `platform/api/routers/dashboard.py (live daily overlay/bias only)`; `tests/agents/test_av_daily_consumer_contract.py`; `tests/lib/test_options_greeks_daily_clock.py`; `tests/api/test_av_market_dashboard_contract.py`.

**Interfaces:** same aware source clock/context and Task2/4/8 qualified frames before existing daily market/analog/STRAT/HV/earnings math; live raw observation independently bound, analytical outputs restored.

- [ ] Step1: Write meaningful failing actual tests for same/cross-ticker split/dividend/late-revision controls and >300-prefix parity; latest completed invalidated/NULL no older/neutral fallback; raw executable prices/known truezero remain distinct; volume-required fields refuse without capability.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/agents/test_av_daily_consumer_contract.py tests/lib/test_options_greeks_daily_clock.py tests/api/test_av_market_dashboard_contract.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 10: Actual replay/sweep/signal and calibration clocks

Spec: Direct daily replay; Every intraday replay; Style calibration. Advances one-based done_when[7, 11, 14, 25].

**Files:** `scripts/replay_signal_monitor.py`; `gcp/signal_monitor.py (source guards only)`; `scripts/run_backtest.py`; `scripts/run_walk_forward.py`; `scripts/run_param_sweep.py`; `scripts/run_timeframe_sweep.py`; `platform/api/routers/backtest.py (replay/style source only)`; `tests/api/test_av_price_replay_routes.py`; `tests/scripts/test_av_price_replay_entrypoints.py`; `tests/scripts/test_replay_signal_monitor_source_revision.py`.

**Interfaces:** explicit aware as_of/mode/input identity before read, raw native minute validation, current_revision_analytics diagnosed only; exact public persist_trades/persist_walk_forward/persist_results/persist_sweeps guard.

- [ ] Step1: Write meaningful failing actual tests for actual API/CLI/default/parameter/timeframe chain propagation and later daily/minute revision refusal; ZERO four canonical research tables/live winners/user_style/card writes for current/unknown, real strict positive only eligible immutable source; preserve existing formulas.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/api/test_av_price_replay_routes.py tests/scripts/test_av_price_replay_entrypoints.py tests/scripts/test_replay_signal_monitor_source_revision.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 11: Registered research adapters and unsafe writer retirement

Spec: Remaining research; Registered STRAT; Retire legacy writers/P1. Advances one-based done_when[7, 11, 14, 25, 29, 32, 34].

**Files:** `scripts/strat_oos_multi_tf.py`; `scripts/strat_oos_clv_ablation.py`; `scripts/strat_clv_demech.py`; `scripts/strat_struct_backtest.py`; `scripts/strat_next_candle_analysis.py`; `scripts/strat_backtest.py`; `scripts/strat_history_report.py`; `scripts/strat_forward_walk.py`; `scripts/strat_forward_walk_oos.py`; `gcp/research/p45_deep_ds_job.py`; `lib/features/experimental/cross_asset.py`; `lib/features/experimental/vol_regime.py`; `gcp/research/strat_engine/strat_dir_walk_forward_extended.py`; `gcp/migrate_to_gcp.py (daily_indicators guard)`; `gcp/research/p7_build_multi_tf_features.py (main/_process/_load_vix guards)`; `gcp/research/p2_outcomes_grid.py (main/_process/_load_daily guards)`; `gcp/queries/p1_vix_backfill.sql`; `gcp/research/strat_engine/README.md`; `tests/scripts/test_av_daily_research_basis.py`; `tests/gcp/test_av_legacy_writer_retirement.py`; `tests/integration/test_av_legacy_writer_retirement.py`.

**Interfaces:** explicit --as-of aware plus --current-revision-analytics and literal shared helper context; controlled unavailable/nonzero native launchers; P1 whole file ONE SQLSTATE55000 exception, no mutating tail; no new algorithm/persistence platform.

- [ ] Step1: Write meaningful failing actual tests for each actual/direct/native entrypoint split/dividend/required-volume guard before imputation; actual source-matched persisted labels; migrator/P7/P2 zero source/DDL/math/write; P1 full realSQL stop/continue unchanged VIX/VVIX/6caches; direct options-specific bypass guards remain OPTION-owned after actual MAIN, not duplicated.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/scripts/test_av_daily_research_basis.py tests/gcp/test_av_legacy_writer_retirement.py tests/integration/test_av_legacy_writer_retirement.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 12: Nullable ranker/live-volume and bounded API admission

Spec: Latest-row/response; Interactive latency and schema. Advances one-based done_when[8, 17, 21, 33].

**Files:** `lib/agents/ranker/signals.py (daily/HV/liquidity)`; `lib/agents/ranker/scoring.py`; `lib/agents/ranker/rank.py (nullable daily transport)`; `gcp/auto_refresh_top_n.py`; `platform/api/routers/insights.py`; `platform/api/routers/live.py`; `platform/api/main.py (market/date/reference/sector source)`; `platform/api/schemas.py`; `tests/api/test_av_ranker_watchlist_contract.py`; `tests/api/test_av_live_daily_volume.py`; `tests/gcp/test_av_auto_refresh_ranker_availability.py`; `tests/api/test_av_sector_rotation_basis.py`; `tests/api/test_av_data_interactive_capacity.py`; `tests/integration/test_av_data_interactive_postgres_capacity.py`.

**Interfaces:** decision_as_of/admitted_candidates<=100/candidate_scope_sha256/request_deadline_monotonic/guarded_source_deadline_monotonic/options_preload actual merged OPTION contract; <=50returned, shared2s guards within5s; NULL score/points end-to-end; sectors one11ticker<=121row batch.

- [ ] Step1: Write meaningful failing actual tests for actual rank/scoring/audit/schema/watchlist/auto-refresh no dispatch for unknown; qualified zero/order preserved; raw/split-volume denominator and fallback units; sectors adjusted1d/5d+raw outward close/latest NULL/cache invalidation; actual whole-route p95/bytes/query/driver release at max/concurrency4, no mocked-success timing.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/api/test_av_ranker_watchlist_contract.py tests/api/test_av_live_daily_volume.py tests/gcp/test_av_auto_refresh_ranker_availability.py tests/api/test_av_sector_rotation_basis.py tests/api/test_av_data_interactive_capacity.py tests/integration/test_av_data_interactive_postgres_capacity.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 13: Premarket brief/playability/resolver and movement daily levels

Spec: Brief/sector/movement boundaries; Resolver clocks; Replay guards. Advances one-based done_when[1, 19, 23, 33, 34].

**Files:** `gcp/premarket_brief.py (qualified daily math/levels/write guard and retired DELETE)`; `gcp/premarket_playbook_resolver.py`; `lib/earnings_reactions.py (playability boundary)`; `platform/api/routers/dashboard.py (_build_movement_level_map daily block)`; `tests/gcp/test_premarket_brief_daily_revision.py`; `tests/gcp/test_av_premarket_brief_consumer_basis.py`; `tests/gcp/test_av_premarket_playability_basis.py`; `tests/lib/test_av_playability_daily_basis.py`; `tests/gcp/test_av_playbook_resolver_source_clock.py`; `tests/integration/test_av_playbook_resolver_source_clock.py`; `tests/api/test_av_movement_daily_level_basis.py`.

**Interfaces:** one genuine aware daily context, original date-only08:30ET request semantics not knowledge; adjusted full-prefix indicators/change/share-RVOL/levels+ATR restored before raw comparisons; actual persistence context and distinct original analysis/outcome clocks.

- [ ] Step1: Write meaningful failing actual tests for actual both load/math/level/persist paths no completed-NULL older fallback/RSI50/neutral STRAT; source changes between read/write refuse; retired _delete helper zeroI/O; resolver later source/currentdiagnostic zero writes; movement actual404/503/unavailable and same raw target units with real HTTP fixtures.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_premarket_brief_daily_revision.py tests/gcp/test_av_premarket_brief_consumer_basis.py tests/gcp/test_av_premarket_playability_basis.py tests/lib/test_av_playability_daily_basis.py tests/gcp/test_av_playbook_resolver_source_clock.py tests/integration/test_av_playbook_resolver_source_clock.py tests/api/test_av_movement_daily_level_basis.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 14: Native/reference telemetry, dryrun and freshness

Spec: Runner telemetry; Common typed adoption. Advances one-based done_when[4, 5, 15, 27, 31].

**Files:** `gcp/fetchers/fetch_market_data.py (terminal context)`; `gcp/fetchers/fetch_av_reference_data.py (main/terminal)`; `gcp/av_price_publication.py (bounded terminal caller only)`; `gcp/config/alphavantage_endpoints.json (planned lifecycle)`; `tests/gcp/test_av_data_observability.py`; `tests/gcp/test_av_data_operation_metadata.py`; `tests/integration/test_av_data_operation_metadata.py`; `tests/gcp/test_av_rollout_contract.py`.

**Interfaces:** actually merged common read_av_operation_metadata and same12/14 terminal INSERT, immutable presource context; genericNone remainsNULLunknown, no Scheduler authentication; DATA independently owned actual caller deadline/driver bounds, no default timeout_s invention.

- [ ] Step1: Write meaningful failing actual tests for success/validempty/partial/failed/preflight/dryrun actual native outputs/nonzero; dryrun ZERO SQL/job_runs/archive/vendor/maintenance mutation; declaration/ACK events nonterminal exclusion; actual cold/TX/count/false/lostACK/late limits; planned until DEP/source/OPS evidence.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_data_observability.py tests/gcp/test_av_data_operation_metadata.py tests/integration/test_av_data_operation_metadata.py tests/gcp/test_av_rollout_contract.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Task 15: Lawful generated/OpenAPI/source-note delivery and complete capacity closeout

Spec: Exact generated contracts; DATA-owned ordinary declaration; Postmerge closeout. Advances one-based done_when[6, 13, 21, 31, 35].

**Files:** `platform/api/openapi.json`; `docs/product/infrastructure/05-a-ARCHITECTURE.md`; `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`; `docs/product/infrastructure/05-e-API.md`; `docs/RUNBOOK_BACKFILL.md`; `docs/product/03-SITE-TRACEABILITY.md (own FEATDATA/SHARED07 note only)`; `docs/review-evidence/site-source-snapshot.json (merged producer only)`; `docs/product/02-FEATURE-CATALOG.md (own record)`; `docs/product/12-PR-ISSUE-TRACEABILITY.md (own entry)`; `existing named full affected suites`.

**Interfaces:** actual approved primary/main/unique plan/sourcehash and real ordinary committed note/sidecar; trusted full renderer BASE prose+committed sources; actual OpenAPI export and snapshot; no gate/renderer/provider source edit.

- [ ] Step1: Write meaningful failing actual tests for all35 DoD literal checklist with actual evidence; all named hermetic/PG/current-head/full native/capacity/error controls and required unchanged BASE/gates/audit noNEW; independent whole-branch peer/root-authenticated CODE/SEC/CI/conversations; hold absent Gov/Counter/Cost/common/owner implementations. Separately track genuine postmerge root MAIN/staging/old-writer-drain/AV reconciliation and marker-only OR body-first pending/squash/second stamp+sidecar retirement; never pre-tick future rollout.
- [ ] Step2: Run `/workspace/stocks-venv/bin/python -m pytest -q tests/gcp/test_av_data_capacity.py tests/api/test_openapi_snapshot.py tests/scripts/test_check_generated_docs.py` with explicit dummy PG selectors for integration cases; record the real preimplementation failure, not missing external dependency disguised as positive proof.
- [ ] Step3: Implement only the owned source/availability/schema unit above under exact Global Constraints; isolate modules by source identity responsibility and refuse missing actual dependencies before side effects.
- [ ] Step4: Run the same complete named command plus affected existing neighbors; expect actual PASS/no persistence skips. Record source hashes, actual query/byte/runtime/clock measurements and any unresolved managed/owner dependency separately.
- [ ] Step5: Run checked `python scripts/gate/spec_gate.py --commit` on the exact stage, commit only this independently tested component and record task brief/base/commit/RED→GREEN/result/rulings in the ledger. Do not claim the whole task complete until every listed acceptance case is green; no source push/readiness before final prerequisites.

## Acceptance index and separate close-out

The full literal35-item approved checklist is the linked immutable primary; this plan neither rewrites it nor removes an item. Each task family preserves its exact source/PG/consumer/capacity requirements even when external actual-main compatibility is pending. Final plan status remains ready until actual PR merge; close plan on normal DOC branch afterward. Root-owned actual deployed availability/reconciliation/native all-task/source/staging/retirement proof and lawful terminal sidecar cleanup remain separate unfinished close-out, never claims from a code commit or local source identity.
