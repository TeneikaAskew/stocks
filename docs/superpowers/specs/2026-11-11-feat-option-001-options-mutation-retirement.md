---
feat_id: FEAT-OPTION-001
req_ids: [REQ-DATA-001, REQ-DATA-003, REQ-GOV-004]
issues: [919]
canvases: []
site_source_notes: [OPTIONS-01]
done_when:
  - "Migration CLI: tests/gcp/test_migrate_options_retirement.py::test_protected_selectors_refuse_before_any_io and ::test_default_sql_sequence_refuses_before_upload run gcp.migrate_to_gcp.main with fail-on-call stubs for every TABLE_FUNCS handler, upload_raw_parquets, gcs_upload, pd.read_parquet and gcp.database; for --table etf_options_snapshots, --table av_options and --table earnings_options_snapshots (each alone, with --dry-run, with --skip-gcs, with --skip-sql), for no arguments, --dry-run alone, --skip-gcs alone and --data-dir alone, main returns 2, logs unsupported_options_cache_mutation and calls nothing; ::test_cli_exit_status_is_2 runs python gcp/migrate_to_gcp.py --table av_options in a subprocess and gets exit status 2. All three fail on main."
  - "Migration supported paths and grammar: tests/gcp/test_migrate_options_retirement.py::test_supported_paths_still_dispatch shows no-table --skip-sql calls upload_raw_parquets once and no SQL handler, --skip-gcs --skip-sql calls nothing and returns 0, --table gcs_raw calls upload_raw_parquets, each of market_data_daily_av, daily_indicators, market_data_intraday and trades calls its own handler with (data_dir, dry_run) and returns 0, and --table trades --skip-sql still runs trades; ::test_last_table_wins_in_both_directions shows --table av_options --table trades runs trades and --table trades --table av_options refuses; ::test_parser_grammar_unchanged asserts sorted(TABLE_FUNCS) is the eight selectors gcs_raw, market_data_daily_av, daily_indicators, market_data_intraday, etf_options_snapshots, av_options, earnings_options_snapshots, trades and the parser options are exactly --data-dir, --dry-run, --skip-gcs, --skip-sql, --table and -h/--help. The first two fail on main."
  - "Migration direct calls: tests/gcp/test_migrate_options_retirement.py::test_direct_options_migrators_raise_before_io calls migrate_etf_options, migrate_av_options and migrate_earnings_options with a tmp data_dir holding parquet files at their real source paths, dry_run True and False: each raises UnsupportedOptionsCacheMutation whose reason is unsupported_options_cache_mutation, with zero gcp.database and pd.read_parquet calls; ::test_no_options_cache_writer_remains parses gcp/migrate_to_gcp.py and finds no upsert_dataframe or bulk_insert_dataframe call whose table argument is etf_options_snapshots or earnings_options_snapshots. Both fail on main."
  - "SPX computed columns: tests/scripts/test_retired_options_mutations.py::test_spx_main_refuses_every_argv_before_db runs scripts.maintenance.compute_spx_greeks.main with no flags, --ticker SPX, --force, --start-date/--end-date, --limit-dates 1 and --ticker NDX, with get_engine, query_to_dataframe, list_dates_to_process and process_one_date fail-on-call: each returns 2 and logs unsupported_options_cache_mutation; ::test_update_computed_columns_refuses_before_engine passes an empty and a non-empty chain and gets UnsupportedOptionsCacheMutation with zero get_engine calls; ::test_process_one_date_cannot_write stubs load_chain and enrich_av_chain_with_greeks with a fully solved chain and gets UnsupportedOptionsCacheMutation from the real writer; ::test_no_spx_update_statement_remains finds no UPDATE etf_options_snapshots text in the module. All four fail on main."
  - "Existing SPX coverage: tests/lib/test_silent_fallback_fixes.py::test_the_force_flag_reaches_the_gate_from_the_command_line is the only existing test changed: it keeps its assertion that process_one_date takes force and replaces its main-source substring assertion with one that main returns 2 for --force without calling process_one_date; every other test in that file, and tests/gcp/test_migrate_trades_tz_guard.py and tests/meta/test_production_writers.py, pass unmodified."
  - "Yahoo options deletes: tests/scripts/test_archive_yahoo_options_delete_guard.py::test_delete_selecting_an_options_table_refuses_before_engine runs scripts.archive_yahoo_data.main for --confirm etf_options_snapshots --delete, --confirm earnings_options_snapshots --delete, --confirm all --delete, --confirm market_data_daily --confirm etf_options_snapshots --delete and --dry-run --delete with get_engine and process_table fail-on-call: each exits 2 with unsupported_options_cache_mutation before any table is processed; ::test_direct_delete_boundaries_refuse calls process_table(engine, table, cfg, args) with args.delete True (dry_run True and False) and delete_chunk(conn, table, cfg, chunk_size) for both options tables against recording fakes and gets UnsupportedOptionsCacheMutation with zero engine or connection use; ::test_supported_archive_paths_unchanged shows --confirm etf_options_snapshots without --delete and --confirm market_data_daily --delete still reach process_table, and delete_chunk on market_data_daily still executes its DELETE on the fake connection. The first two fail on main."
  - "Embedded operator text: tests/gcp/test_migrate_options_retirement.py::test_usage_and_help_describe_refusal and tests/scripts/test_retired_options_mutations.py::test_spx_usage_and_help_describe_refusal and tests/scripts/test_archive_yahoo_options_delete_guard.py::test_usage_and_help_describe_refusal assert each module's --help output exits 0 and contains unsupported_options_cache_mutation, and that its module docstring no longer contains the literal commands python gcp/migrate_to_gcp.py --table av_options, python scripts/archive_yahoo_data.py --confirm etf_options_snapshots --delete, or the three python -m scripts.maintenance.compute_spx_greeks Usage invocations; the supported examples (--skip-sql, --table market_data_daily_av, --table daily_indicators --skip-gcs, --confirm market_data_intraday --delete) remain. All three fail on main."
  - "Records and generated documents: the implementation PR re-renders docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md with scripts/maintenance/doc_inventory.py from committed source and commits only that output; the FEAT-OPTION-001 / OPTIONS-01 Implementation-source note and committed sidecar pass scripts/maintenance/doc_source_snapshot.py produce then verify with the fixed ceilings; python3 scripts/maintenance/docs_audit.py on the PR head reports no finding that origin/main does not; the FEAT-OPTION-001 record shows a current Status and Last reviewed and docs/product/12-PR-ISSUE-TRACEABILITY.md lists the PR under FEAT-OPTION-001; python3 scripts/gate/spec_gate.py --pr origin/main passes."
status: draft
supersedes: null
---

# Retire the unguarded options mutation paths still on main (FEAT-OPTION-001)

## Problem

Three operator scripts on main can still write or delete rows in the options caches the
`/api/options` and `/api/grid` routes read, outside the scheduled collectors that own those tables:

- `gcp/migrate_to_gcp.py`: `migrate_etf_options` (line 469) upserts `etf_options_snapshots`,
  `migrate_av_options` (line 321) bulk-inserts AV historical rows into `etf_options_snapshots` from both its
  combined-parquet and daily-file branches, and `migrate_earnings_options` (line 514) upserts
  `earnings_options_snapshots`. `main` (line 781) reaches them through `--table` and, with no `--table` and no
  `--skip-sql`, through the default sequence (lines 818-822). Each migrator catches per-file errors and `main`
  returns nothing, so a failed import exits 0.
- `scripts/maintenance/compute_spx_greeks.py`: `update_computed_columns` (line 129) runs
  `UPDATE etf_options_snapshots` over the six `*_computed` columns; `main` (line 372) loops every selected date.
- `scripts/archive_yahoo_data.py`: `--delete` deletes Yahoo-sourced rows from `etf_options_snapshots` and
  `earnings_options_snapshots` through `process_table` (line 166) and `delete_chunk` (line 141); `main` (line 273)
  processes `--confirm all` and repeated `--confirm` values in order, so a mixed selection deletes from earlier
  tables before it reaches an options table.

None of these writes carries source, as-of or pipeline identity (REQ-DATA-003), and the migration path reports
success on failure (REQ-DATA-001). The approved companion
`docs/superpowers/specs/2026-10-16-feat-deploy-001-av-options-legacy-dispatch-retirement.md` (FEAT-DEPLOY-001,
merged in #1529) retires the `gcp/deploy.sh migrate` and `spx-greeks` wrapper paths and states that the module
guards in `gcp/migrate_to_gcp.py` and `scripts/maintenance/compute_spx_greeks.py`, and the maintained-guide
companion, belong to this FEAT-OPTION-001 contract. This spec is that contract, re-cut small from current main.

## Relation to the approved DEPLOY companion

This spec builds on the DEPLOY spec and changes nothing in it (`supersedes: null`). It uses the same refusal
reason, `unsupported_options_cache_mutation`, the same exit status 2, the same protected selectors
(`etf_options_snapshots`, `av_options`, `earnings_options_snapshots`) and the same support matrix: explicit
protected selector refuses whatever the dry or skip flags; no `--table` and no `--skip-sql` refuses; no
`--table` with `--skip-sql` is raw upload only; `--skip-gcs --skip-sql` is a no-op; `gcs_raw` and the four named
non-options selectors keep their native behavior, including native explicit-table handling that ignores skip
flags; the last valid `--table` wins. The DEPLOY wrapper uses the module's real parser as its grammar oracle, so
this spec keeps the parser's options, defaults and the eight `TABLE_FUNCS` keys unchanged; only help text
changes. DEPLOY owns `gcp/deploy.sh`; this spec does not edit it.

## Non-goals

- No change to `gcp/deploy.sh`, Cloud Run jobs, schedulers or deployed images. Draining old images is DEPLOY's.
- No change to the scheduled options collectors (`gcp/fetchers/fetch_av_realtime_options.py`,
  `gcp/fetchers/fetch_av_historical_options.py`, the earnings options backfill) or the retention job.
- No new publisher, source journal or provenance table, and nothing that reads or writes `av_options_*` tables:
  they are not in `gcp/schema.sql` and the owner excluded them from scope.
- `scripts/fetch_alphavantage_options.py` is out of scope: it writes local parquet files only (lines 327, 410,
  673) and no database row; the database path that consumed those files, `--table av_options`, is retired here.
- No change to `lib/options_greeks.py` math, `process_one_date`'s computation and failure rules, the archive copy
  step, or Yahoo deletes on `market_data_daily` and `market_data_intraday`.
- `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/p2_outcomes_grid.py`,
  `gcp/queries/strat_features_gamma_backfill.sql` and `gcp/queries/gamma_rename_migration.sql` are not retired
  here (see "Dropped from the replaced PRs").

## Approaches considered

1. Guard each write boundary and each CLI entry, remove the write bodies, keep the parser grammar. Chosen: it
   refuses direct calls and CLI calls alike, leaves no write reachable behind a prepended return, and keeps the
   DEPLOY oracle valid.
2. Remove the protected choices from argparse. Rejected: it changes the grammar the approved DEPLOY spec pins
   (an unknown selector becomes invalid rather than refused) and leaves direct function calls writable.
3. Guard only `main`. Rejected: `migrate_*`, `update_computed_columns`, `process_table` and `delete_chunk` are
   importable and would still write.

## Design

One shared refusal type, `lib/options_mutation_retirement.py`: `REASON = "unsupported_options_cache_mutation"`
and `class UnsupportedOptionsCacheMutation(RuntimeError)` carrying `reason` and the refused target name. CLI
refusals log one line with the reason and the selector or table name only (no argv, paths or environment) and
exit 2.

### `gcp/migrate_to_gcp.py`

- `migrate_etf_options`, `migrate_av_options`, `migrate_earnings_options` keep their names and `(data_dir,
  dry_run)` signatures and raise `UnsupportedOptionsCacheMutation` as their first statement, before any import of
  `gcp.database`, filesystem check, `_get_av_existing_dates` read or parquet read. Their insert and upsert
  bodies are deleted; helpers used only by them (`_normalize_av_options`, `_get_av_existing_dates`,
  `_normalize_options_df`, `AV_OPTIONS_TICKERS`) are deleted with them.
- `TABLE_FUNCS` keeps all eight keys; the three protected keys still map to the three refusing functions.
- `main` returns an int. After `parse_args`, and before the dry-run banner, `upload_raw_parquets` or any handler:
  a protected `args.table` returns 2; no `args.table` and not `args.skip_sql` returns 2. Otherwise the existing
  dispatch runs unchanged and returns 0. The no-table SQL branch (lines 818-822) is deleted, since every
  remaining no-table path skips SQL. `if __name__ == '__main__': sys.exit(main())`.
- Module docstring and the parser description/epilog state the support matrix above, drop the full-migration
  and `--table av_options` commands, and keep the supported examples.

### `scripts/maintenance/compute_spx_greeks.py`

- `update_computed_columns` raises `UnsupportedOptionsCacheMutation` as its first statement, for any frame,
  before `get_engine`; the `UPDATE etf_options_snapshots` body is deleted.
- `main` parses arguments (so `--help` still exits 0 and malformed flags still exit 2 from argparse), then
  returns 2 before ticker validation, `list_dates_to_process`, `get_engine` or `process_one_date`. The date loop
  is deleted.
- `process_one_date`, `list_dates_to_process`, `load_chain` and the pure helpers stay unchanged. A direct
  `process_one_date` call may still read a chain; its only write goes through `update_computed_columns`, which
  refuses, so it cannot mutate. This keeps the ten existing `process_one_date` tests in
  `tests/lib/test_silent_fallback_fixes.py` (lines 458 to 957, from
  `test_a_date_that_computes_nothing_is_a_failure_not_a_no_op` to
  `test_a_forced_partial_date_reports_the_rows_it_failed_to_recompute`) passing unmodified: each substitutes
  `update_computed_columns` or stops at an empty chain before it. The one test that inspects `main`'s source for the `force=args.force` call (line 960) is
  converted as `done_when` item 5 states, because `main` no longer calls `process_one_date`.
- Module docstring and parser description say the write mode is retired with the reason; the three Usage
  invocations are removed.

### `scripts/archive_yahoo_data.py`

- `PROTECTED_DELETE_TABLES = {'etf_options_snapshots', 'earnings_options_snapshots'}`.
- `main` resolves the table list as today, then, before `get_engine` and before the loop, exits 2 when
  `args.delete` is set and any resolved table is protected. This covers `--confirm all`, repeated and mixed-order
  `--confirm` values and `--dry-run --delete`, so no earlier table is processed before the refusal.
- `process_table` raises when `args.delete` and the table is protected, before using the engine. `delete_chunk`
  raises for a protected table before `conn.execute`. Copy-only runs on the options tables and deletes on the
  two market-data tables are unchanged. `if __name__ == '__main__': sys.exit(main())` with `main` returning 0 on
  success.
- The docstring drops the `--confirm etf_options_snapshots --delete` example and says options deletes refuse;
  the `--delete` help text says the same.

### Tests

New files: `tests/gcp/test_migrate_options_retirement.py`, `tests/scripts/test_retired_options_mutations.py`,
`tests/scripts/test_archive_yahoo_options_delete_guard.py`, with the test functions `done_when` names. Collaborator
stubs fail on call and record calls, so a guard placed after any I/O fails the test, and each refusal case is
paired with a supported control so an implementation that refuses everything fails too. `TABLE_FUNCS` handlers
are replaced with `monkeypatch.setitem`, since the dict holds function references. No test touches a database,
GCS or the network.

### Capacity

Refused paths do no database, GCS or provider work: zero rows, zero queries, zero uploads, and wall-clock bounded
by module import plus argument parsing. Supported paths keep their existing volume, velocity and wall-clock. No
new job, scheduler, query, retry or resource; cost does not increase. The implementation PR states Volume,
Velocity, Wall-clock and cost in its Capacity section on these terms.

## Dropped from the replaced PRs

- R7, R8 (P7 `_compute_daily_vex`, P2 `_load_levels_for_prior_day`): their only callers are
  `_process_ticker` in the same modules, whose retirement the approved
  `docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md` assigns to FEAT-DATA-001, and their parent
  controls depended on that unlanded code. `_load_levels_for_prior_day` is also a read, not a mutation.
- R9, R10 (raw gamma SQL files) and their PostgreSQL integration suite: their retirement rested on routing gamma
  context through the immutable publisher of the closed #1525; without it `strat_features_gamma_backfill.sql`
  is the repair path matching `strat_data_builder`, and retiring it is a separate owner decision.
- Every dependency on the A/P/Q/C/D option specs, the `av_options_*` tables, #1525 and #1527, shared storage
  budgets, issue-level review records, a runbook and an evidence audit file. Issues #913 and #914 (corporate
  actions, exchange calendar) are not touched by this scope.

## Close-out (after merge, tracked on the PR, never pre-ticked)

1. Maintained-guide companion, the one the DEPLOY spec assigns to this contract. It may be prepared early as
   `docs/review-evidence/av-options-retirement-operator-guides.patch` (the path the DEPLOY spec names) and lands
   as one `docs/` PR only after both this spec's code and the DEPLOY wrapper code are on main. It covers
   `docs/product/infrastructure/05-g-DATA_PIPELINE.md` line 99, `05-i-GCP_IMPLEMENTATION_GUIDE.md` lines
   1052-1061 and 1185-1238, `05-j-GCP_IMPLEMENTATION_STATUS.md` lines 122-127 and `docs/BRIEFING_DECK.md` lines 47,
   500, 1032-1034 and 1223: each retired command or status is removed or marked as refusing with the reason;
   dated history entries stay.
2. `docs/product/03-SITE-TRACEABILITY.md`: the Chain rows OPTIONS-01, 02, 05, 08 and 12 stop listing
   `gcp/migrate_to_gcp.py` as a writer of `etf_options_snapshots`, and the two "Writers left out" notes that
   describe `compute-spx-greeks-backfill` as updating the `*_computed` columns (lines 530 and 617) say it refuses.
   This goes through the product-delivery skill's documentation close-out route, together with the stamp and
   sidecar retirement, so the durable rows stay true after the sidecar is removed.
3. Verify main's source and SITE body identity in a fresh clone; set the plan `status: done` on a `docs/` branch.

## Risks

- A guard placed after I/O, or a prepended refusal that leaves a write body behind: caught by the fail-on-call
  stubs and the static writer checks in `done_when` items 1, 3, 4 and 6.
- Refusing supported work (raw upload, no-op, named non-options tables, copy-only archive, market-data deletes):
  caught by the paired controls in items 2 and 6.
- Drifting from the DEPLOY grammar oracle: caught by `test_parser_grammar_unchanged`.
- A mixed `--confirm` selection deleting market-data rows before refusing: caught by item 6's mixed-order and
  `all` cases asserting `process_table` is never called.
- Misleading guides between the code merge and the companion: bounded by close-out item 1, which the DEPLOY spec
  also requires before global retirement.
