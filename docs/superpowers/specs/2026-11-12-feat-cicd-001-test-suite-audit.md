---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Every part ships as its own PR under its own ready plan (Part A as two PRs, pin stage then live stage), each with owned FEAT-CICD-001 catalog and traceability records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head for every PR that touches a gate file, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads."
  - "Removal and rewrite rule for Parts D to F: for every test this spec removes, merges or rewrites, the PR body names the test, the covering test that stays, and a recorded mutation of product code that the removed test failed on and that the covering test still fails on in the same run (or, for a test of a retired feature, the recorded mutation showing no production caller); a test whose covering test does not fail on the same mutation stays and is listed as such. No test is removed for speed alone."
  - "Part A experiment, before any workflow change: the pin-stage PR body records, on one ordinary 4-core Linux machine and on hosted ubuntu runners, the unchanged tests/scripts/test_spec_gate.py run serially and with pytest-xdist at exactly 4 workers on identical suite and gate bytes: wall-clock of at least three runs per mode, every pass and fail node id per run, and at least three mutated-gate controls (each a one-line change to scripts/gate/spec_gate.py that the serial suite fails) whose failing node ids are identical in both modes. Part A proceeds only if every run passes the same node ids in both modes, every control fails the same node ids in both modes, and the 4-worker median is at least 40 percent below the serial median; otherwise the result is recorded and Part A stops."
  - "Part A pin stage: one PR changes only scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml, so that the step `Proposed gate passes its own suite` and the base-suite step install pytest-xdist at one exact version beside pytest and pyyaml and run tests/scripts/test_spec_gate.py with `-n 4`; tests/scripts/test_export_model_registry.py, every timeout-minutes value, permission, checkout, runner and other step stay byte-identical, and the native pin-order controls refuse a live-only and a simultaneous pin and live change (recorded)."
  - "Part A live stage: a separate later PR makes .github/workflows/registry-check.yml and .github/workflows/spec-gate.yml byte-equal to their pins (cmp recorded) and changes nothing else; its hosted registry and base-suite jobs on the exact head pass every test of the suite then on main with the exporter unchanged, and the PR body records gate-suite step and whole-job times of every attempt against the five most recent main runs."
  - "Part B never-run tests run in CI: (1) tests/conftest.py finds gcloud by PATH lookup instead of the hard-coded Windows path and the tests/lib/test_strat_levels_playbook.py tests that need no live rows run under --mode=mock in Run Tests and Research; (2) the Integration job also runs tests/agents/test_agent_model_routing.py, tests/lib/test_routers_insights_admin.py and tests/api/test_platform_auth.py::test_is_admin_email_binds_against_a_real_engine against its ephemeral Postgres; (3) the Research job can import platform/ for tests/api/test_strat_engine_predict.py and also runs tests/api/test_structure_continuation.py; (4) statsmodels is pinned in requirements-research.txt for tests/lib/test_fracdiff.py; (5) the 4 baseline tests in tests/gcp/test_deploy_ew_evaluator.py and tests/gcp/test_deploy_ew_bindings.py get DEPLOY_BASELINE_REV in CI or, where the baseline no longer applies (test_unchanged_functions_and_arms_are_byte_identical_to_the_baseline fails against its own merge base today), are retired under the removal rule; (6) the 3 CSV schema tests in tests/scripts/test_scripts.py get a committed small fixture or are retired under the removal rule; (7) tests/scripts/test_check_generated_docs.py::test_the_2026_09_02_regeneration_would_have_been_stopped gets the history it needs (fetch-depth for that job or a committed fixture). The PR body lists every node id that skipped on main CI run 43187495530 and now runs, with its result, and each job's skip count before and after."
  - "Part B earnings integration: the PR body records whether the fixture root for tests/integration/test_earnings_daily_path_persistence.py is in the repo; if it is, the Integration job creates the earnings_integration database and sets EARNINGS_TEST_DB_URL_FILE and EARNINGS_ANGO_FIXTURE_ROOT so all 28 items run; if it is not, a GitHub issue for FEAT-CATALYST-001 is opened and named in the PR body."
  - "Part B broken tests: tests/agents/test_agent_model_routing.py::test_set_route_updates_single_role registers the adapter it needs and passes; tests/lib/test_strat_levels_playbook.py::TestStalenessFilter::test_no_trigger_banner_names_the_window either passes after a test-only fix the PR shows is the fault, or is marked xfail(strict=True) naming a new FEAT-STRAT-001 issue. No newly running test is deleted, skipped again or loosened to pass; any other newly running test that fails on product code gets the same strict xfail plus issue, listed in the PR body."
  - "Part B duplicate runs removed: Run Tests no longer runs tests/scripts/test_spec_gate.py, which the pinned registry job and base-suite already run on every PR; the Research job's globs no longer select the 19 non-ML files Run Tests already runs (tests/*/test_strat*.py also matching test_strategy_*), with the PR body listing the files Research keeps and why; Run Tests and Research wall-clock on the head are recorded against the five most recent main runs."
  - "Part C experiment, before any change to scripts/maintenance/doc_source_snapshot.py or scripts/maintenance/docs_audit.py: the PR body records why a SITE source snapshot produced at main M stops verifying after main gains a commit that leaves the source identity unchanged (observed on PR 1838 after #1839, docs only, and #1830, one spec file; identity 54cf25fe both times), and shows a narrower binding that (a) verifies across those two real main moves, (b) still refuses every refused control in tests/scripts/test_doc_source_snapshot.py and tests/scripts/test_docs_audit.py, and (c) still refuses a main move that changes the source identity. Part C proceeds only if all three hold, then lands with new tests for (a) to (c) using real commits in a fresh clone and every original test unchanged and passing."
  - "Part D tests that cannot fail are made to test real code, each proven by a recorded product mutation that the rewritten test fails on and the old one passed: tests/gcp/test_premarket_brief_no_discord.py (all 16 test the copy `_resolve_no_discord` instead of gcp.premarket_brief.main; rewritten against the real policy, which also fails tests/gcp/test_brief_channel_routing.py's gap); tests/gcp/test_fetch_market_data_tz.py (4, a local copy of the timezone logic); tests/gcp/test_watchlist_helper.py::test_fallback_alert_no_op_when_webhook_unset; tests/gcp/test_fetch_av_historical_options.py::test_process_ticker_skip_existing_short_circuits; tests/gcp/test_database_connector_close.py::test_no_connector_is_not_an_error; tests/gcp/test_exit_config_overrides_schema.py::test_primary_key_is_ticker_plus_date and ::test_table_definition_present (scoped to the table's own CREATE TABLE); tests/lib/test_signals.py::TestEvaluateSignal::test_call_preferred_over_equal_put (a fixture that actually fires); tests/lib/test_strategy_momentum.py::test_fixture_audit_every_firing_bar_has_credible_setup; tests/lib/test_strat_levels.py::TestFormatLevelsForBrief::test_default_regime_is_normal; tests/lib/test_production_readiness.py::TestPipelineScript::test_backtest_runs_endpoint_serves_data and ::TestReportGeneration::test_report_listing_endpoint_serves_phases (no 404 accepted); tests/lib/test_options_exec_backtest.py::test_runner_rates_load_range_covers_final_fold; tests/scripts/test_failure_rate_threshold.py::test_backfill_exit_threshold and ::test_run_historical_signals_exit_threshold (call the product, pin the 50 percent boundary); tests/scripts/test_replay_signal_monitor.py::test_summary_median_averages_the_middle_on_even_samples; tests/scripts/test_filter_ema_period.py::test_different_periods_produce_different_trend_series; tests/scripts/test_run_historical_signals_strategy.py::test_mean_reversion_signals_returns_empty_on_no_fires; tests/scripts/test_verify_docs_against_live.py::test_snapshot_round_trips (runs --write-snapshot); tests/scripts/test_scripts.py::TestRunBacktest::test_invalid_ticker_exits_nonzero and ::TestRunPipeline::test_skip_sweep_flag_recognized; tests/api/test_strat_engine_predict.py::test_scope_statement_contains_no_disallowed_language (checks admin.STRUCTURE_BRIEF_SCOPE_STATEMENT); the 3 tests/scripts/test_spec_gate.py assertions on strings the gate no longer emits ('merge main so the file leaves', 'repeats that retirement'). New tests pin the uncovered rules the audit found: the run_historical_signals and backfill_daily_indicators 50 percent thresholds, the audit_data_freshness default settle hour 16, the conviction warn gate on high, and the replay RVOL median."
  - "Part E duplicate and superseded tests are removed under the removal rule (the covering test is named in brackets): tests/gcp/test_signal_monitor_momentum_instrumentation.py::test_cap_check_blocks_evaluate_ticker_when_at_limit [test_signal_monitor_caps.py::test_evaluate_ticker_short_circuits_when_max_daily_trades_hit] and ::test_cap_increment_runs_after_fire_alert [test_signal_monitor_caps.py::test_fire_alert_increments_daily_trades]; tests/gcp/test_signal_monitor_standalone_momentum.py::test_momentum_evaluated_when_mr_misses [test_counters_bump_every_bar_post_369]; tests/gcp/test_schema_style_tables.py::test_user_style_results_table_created and ::test_playbook_cards_staging_table_created [the file's _table_body tests]; tests/gcp/test_magnitude_evaluation_windows.py::test_walk_forward_writes_both_artifacts_under_its_window [test_mag_persist_production_model.py::test_walk_forward_writes_under_the_namespace_it_resolved]; the 4 tests/gcp/test_av_options_realtime_producer.py twins of tests/gcp/test_fetch_av_realtime_options.py (test_normalize_sets_realtime_session_and_live_snapshot_ts, test_normalize_drops_rows_missing_required_keys, test_normalize_coerces_numeric_greeks, test_empty_is_subclass_so_main_error_handling_is_unchanged; the producer file keeps its own); tests/gcp/test_brief_channel_routing.py::test_legacy_format_discord_messages_returns_list_of_dicts; tests/gcp/test_insight_pipeline_memory.py::test_memory_is_above_the_limit_that_oomed, ::test_the_update_path_sets_memory_at_all and ::test_the_update_path_sets_cpu_at_all; the 7 duplicate and 11 superseded tests in tests/lib/test_walk_forward.py, tests/lib/test_backtest.py, tests/lib/test_integration.py and tests/lib/test_strat.py listed in the audit (test_inclusive_today_default_true_legacy_contract, test_fold_dates_non_overlapping, test_stability_score_range, test_with_strat, test_exit_reasons_valid, test_strat_filtering_produces_fewer_or_equal_trades, test_filter_counts_populated_with_strat, test_run_produces_result, test_fold_count, test_fold_dates_populated, test_aggregate_metrics, test_summary_string, test_engine_runs_without_error, test_engine_produces_daily_pnl, test_all_trades_have_exit, test_equity_curve_length, test_engine_with_strat, test_ftfc_score_range_in_trades); tests/scripts/test_verify_docs_against_live.py::test_a_retired_service_is_reported_once_not_twice and ::test_the_free_tier_quota_is_still_not_a_fleet_count; tests/scripts/test_check_generated_docs.py::test_the_cli_runs_clean_on_the_repository_docs [test_committed_docs_pass_every_gate, which the README Maintenance step pins]; tests/scripts/test_scripts.py::TestValidateMarketData::test_script_importable, ::TestHandleWorkflowFailure::test_script_importable, ::TestFetchMarketData::test_script_importable, ::TestRunPipeline::test_help_flag and ::TestRunTimeframeSweep::test_help_flag; tests/api/test_grid_router.py::TestOnDemandRateLimit::test_under_limit_passes; tests/meta/test_timezone_boundaries.py::test_the_helper_module_is_the_only_place_eastern_is_built; tests/audits/test_audit_data_freshness.py::test_dst_summer_uses_edt, ::test_settle_hour_default_is_market_close and ::test_settle_hour_walks_past_weekend (after Part D adds the settle-hour pin); tests/scripts/test_spec_gate.py::test_pr_body_links_the_plan and test_capacity_values_are_numbers (the latter only if the spec that names it is updated in the same change, else kept and listed)."
  - "Part F retired-feature tests and the dead code they cover: the 49 EarningsWhispers scorer cases in tests/gcp/test_evaluate_ew_strikes.py and the 21 EW tests in tests/gcp/test_premarket_brief.py stay with their approved specs (2026-10-31 retire-ew-module-shim item 3 and 2026-11-11 retire-ew-brief-caller-scope), and this part's PR body records whether each has landed; this part removes, with the production code the PR shows has no caller: the legacy process_ticker path in gcp/fetchers/fetch_av_realtime_options.py and its 5 tests, _fetch_yahoo_one and its 5 test_fetch_yahoo_one_* tests, premarket_brief.format_discord_message and format_discord_messages and test_legacy_single_payload_preserves_playbook and test_routed_and_legacy_same_payloads, the insight_discord_push format_message shim and its 2 tests, SNAPSHOT_TOLERANCE_SECONDS and test_iv_lookup_snapshot_tolerance_constant_preserved_for_backcompat; the doc_inventory refs_digest output and the gate_transcripts check (with their 8 tests and the digest lines of 3 more), since only the retired monthly refresh used them; make test-e2e and archive/tests/test_e2e.py's Makefile target."
  - "Part G workflow and gate hygiene: scripts/gate/spec_gate.py line 110's invalid escape is fixed (gate file, red-team pass) and `python3 -W error -m py_compile scripts/gate/spec_gate.py` passes; verify-docs-against-live.yml gets a failure alert through handle-workflow-failure.yml like the other workflows; Run Tests gets an explicit timeout-minutes with at least 25 percent reserve over its slowest of the last 25 main runs; .github/workflows/fetch-market-data.yml.disabled and .github/workflows/logs.txt are deleted with their prose references; the Makefile's test help text matches what it runs and test-integration is in .PHONY; the unused requires_data_backend marker is removed; the dead create=True patches (tests/audits/test_audit_infra_drift.py lines 178 to 180, tests/audits/test_audit_p2_p3_cleanup.py line 249, the get_engine patches in tests/scripts/test_signal_quality_alarm.py and test_signal_quality_report.py) and the unused helper _run_backfill_with_outcomes are removed with their tests still passing; the `assert ... or True` at tests/scripts/test_doc_inventory.py line 2073 asserts for real; the canary and verify-docs cron comments state the observed 5 to 10 hour delay; tests/scripts/test_deploy_ew_delivery_contract.py no longer errors when its spec leaves status approved; the CPU-deadline test in tests/scripts/test_doc_source_snapshot.py has margin enough that 20 consecutive hosted runs pass; actions on Node 20 move to versions on Node 24; .devcontainer installs the pre-commit hook."
  - "Part H speed: the repeated whole-repo scans run once per session (tests/scripts/test_doc_inventory.py's 21 repo_inventory rebuilds, tests/gcp/test_compute_earnings_reactions.py's 4 test_generated_inventory_* cases, tests/lib/test_session_levels_structure.py's per-function source reads, tests/meta/test_timezone_boundaries.py's two full scans), the 3 tests/gcp/test_failure_notifier.py tests patch time.sleep like their siblings, and the walk-forward tests build their 4-month dataset once per module; the PR body records each file's serial time before and after, with every test name, case and assertion unchanged."
  - "Part I order independence, so Run Tests can later use workers: the module-level sys.modules stubs for lightgbm and sklearn in tests/gcp/test_magnitude_inference.py and tests/gcp/test_mag_persist_production_model.py are scoped to their own tests, tests/agents/test_cross_ticker_analog_universe.py::test_the_orchestrator_actually_populates_it reads its path from the repo root instead of the working directory, and the full Run Tests command passes with pytest-randomly or `-p random-order` style shuffling on three seeds (recorded), before any proposal to parallelize Run Tests."
  - "Product findings outside FEAT-CICD-001 are opened as GitHub issues for their owning capability and listed in the Part D PR body, not fixed here: the momentum core gate is dead code (MIN_CONDITIONS_MOMENTUM 5 with 3 confirmers), format_levels_for_brief's regime argument is ignored when the LevelMap carries regime_long and regime_short, gcp/build_intraday_flow.py has no job or schedule, gcp/research/direction_program/chart_baseline.py has no caller, the standing strict xfail tests/lib/test_premarket_print_filter.py::test_avgo_0805_high_is_not_an_extreme awaits the owner's AVGO decision, and tests/lib/test_av_account_allowance.py must drop gcp/fetchers/evaluate_ew_strikes.py when that file is deleted."
  - "Owner-only steps are recorded, not assumed: the stale 'Claude' workflow registration (claude.yml, absent from every branch) is disabled by the owner or left with a note; deploy-staging.yml, untested since 2026-09-04, is either dispatched once by the owner with its result recorded or noted as unproven; both outcomes are written in the Part G PR body."
status: approved
supersedes: null
---

# Make every test and gate count: gate suite on four workers, never-run tests run, cannot-fail and duplicate tests fixed, retired code and tests removed

## Authority

On 2026-11-12 the owner asked whether every test and gate is still valid and current after months of
change, said yes to checking all of them before this spec was drafted, then asked for this spec to
cover "everything that needs to be done" from all six audit reports (thread "Time the slowest registry
check tests", 15:07, 16:31 and 16:34 UTC). Standing owner rulings: experiment first and report whether a
change meets its hypothesis before swapping it in; test locally before a PR; nothing leaves the suite
without the owner's say. Approving this spec is that say for the tests it names, under the removal rule
in done_when item 2.

## Problem

The audit covered about 9,400 tests and all CI workflows on main d438cc94 (2026-11-12), in six slices:
tests/gcp in two halves, tests/lib, tests/scripts, tests/api with integration, agents, research, meta and
audits, and the workflows and gates. Every non-keep verdict below was backed by a product mutation or a
CI log, not by reading alone, unless the slice report said otherwise.

| Finding | Tests | Where it goes |
|---|---|---|
| Never run in CI | 109 | Part B |
| Broken today, hidden by a skip | 2 | Part B |
| Cannot fail | 57, plus 3 dead gate assertions | Part D |
| Duplicate or superseded | 47, plus 2 in the gate suite | Part E |
| Retired features | 93 (70 already under approved EW specs) | Part F |
| Workflow and gate issues | 16 | Parts A, C, G |
| Avoidable slowness | about 10 minutes serial | Part H |
| Order dependence | 3 spots | Part I |
| Product gaps outside CI | 6 | issues for owners |

The three findings that matter most:

1. **The gate suite is the slowest required step and keeps growing.** tests/scripts/test_spec_gate.py
   (185 tests) runs serially three times per PR: Run Tests, the registry job (236 to 294 seconds) and
   base-suite (167 seconds on 2026-10-01, 380 on 2026-11-12, against a 10 minute cap). Six of 25 registry
   runs were cancelled at the old 6 minute cap. Locally, 4 workers cut it from 373 to about 130 seconds
   and a broken gate failed the same four tests either way (one machine, one control: a hypothesis).
2. **Real failures are hidden.** tests/lib/test_strat_levels_playbook.py's 17 data tests skip on every CI
   run because of a hard-coded Windows gcloud path, and one of them fails on main in mock mode;
   test_agent_model_routing.py's set_route test is broken behind a DB_HOST skip. Run Tests has no time
   limit and grew from 7 to 27 minutes since 2026-09-15.
3. **Tests that look like coverage are not.** The brief's real Discord posting rule is untested (16
   tests check a copy written inside the test file); no test pins the 50 percent failure thresholds,
   the default settle hour or the CALL-on-tie rule. A SITE source snapshot stops verifying on any main
   move, even a docs-only one, which forced two review-cap exceptions on PR 1838.

## Non-goals

- No change to product behaviour, except deleting code Part F proves has no production caller.
- Product gaps outside FEAT-CICD-001 are filed as issues for their owners (done_when item 17), not
  fixed here.
- Run Tests is not parallelized here; Part I removes the blockers and a later spec can propose it.
- No raised timeout values beyond Run Tests getting its first cap.
- The regex start-up proposal (2026-11-11-feat-cicd-001-registry-startup-current.md) stays separate.

## Approaches considered

- **One spec, nine small PRs (chosen).** Each part is its own plan, branch and PR, so no plan passes
  about 15 tasks, a gate-file change is never mixed with test cleanup, and the owner can stop after any
  part. Order: A pin, C, B, A live, D, E, F, G, H, I (D before E, because E's settle-hour removals rely on
  D's new pin).
- One spec per finding type: more specs to approve for the same decisions.
- Only Parts A and B now, cleanup later: leaves 57 tests that cannot fail counted as coverage.

## Design

### Part A: gate suite on four workers (two PRs, gate files)

`-n 4` fixed, pytest-xdist pinned in the same pip line, `--noconftest` and `-p no:cacheprovider` kept,
test_export_model_registry.py stays serial, pin stage first. The experiment (item 3) decides whether it
proceeds. Capacity (CLAUDE.md rule 0): volume 185 tests per run; velocity two runs per PR push once
Part B drops the third; wall-clock hypothesis about 100 to 140 seconds hosted from 236 to 380 today;
cost lower runner minutes, no new service. Hosted runners for this public repository have 4 vCPU.

### Part B: never-run and broken tests (one PR)

Wiring only, in backtest-pipeline.yml, tests/conftest.py and requirements-research.txt, with fixtures
where item 6 calls for them. Every newly running result is listed; failures become strict xfails
with issues, never skips. Duplicate runs are dropped from Run Tests and Research.

### Part C: source record survives unrelated main moves (one PR, experiment first)

Find what in the "complete current MAIN source/body" binding changes when an unrelated document lands,
bind to what the SITE row certifies, and keep every existing refusal.

### Parts D, E, F: rewrite, remove, retire (three PRs)

Each under the removal rule (item 2): a recorded mutation proves the covering or rewritten test catches
what the old one did. Part F deletes only code with no production caller, shown in the PR.

### Parts G, H, I: hygiene, speed, order independence (three PRs)

G touches a gate file only for the spec_gate.py escape fix and takes the red-team pass for it. H changes
fixtures and patching, never test names, cases or assertions. I prepares for a later parallel Run Tests.

## Risks

- **Removing a test loses coverage.** Item 2 requires a product mutation that the covering test still
  catches; otherwise the test stays.
- **Parallel runs hide an order-dependent failure.** Item 3's repeated runs and mutated-gate controls.
- **Newly running tests turn CI red.** Strict xfails with issues keep each failure visible.
- **Part C weakens provenance.** Item 10 keeps every existing refusal and adds one for a real source change.
- **Deleting code that is still used.** Part F shows no production caller for each deletion.

## Close-out

Each PR updates the FEAT-CICD-001 record and the PR traceability entry; after each merge its plan is
set to done on a docs branch.
