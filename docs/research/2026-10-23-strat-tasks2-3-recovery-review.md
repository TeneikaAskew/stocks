# Independent cumulative Tasks 2–3 recovery review

**Spec compliance: APPROVED for the bounded local Tasks 2–3 recovery checkpoint.**
**Task quality: APPROVED for that same scope.**
**Recovery findings: none requiring a source or test fix.** This is not approval of the complete feature, production integration, or missing later tasks.

## Identity verdict

I independently hashed the working files and frozen copies after the restorer confirmed all 11 paths frozen. All 11 match `cumulative-manifest.json`; six production files and four historical test files also match the retained approved Task2/Task3 manifests. The cumulative expectations agree with the original reviewer manifests in `/workspace/strat-command-recovery/task2-review-read-outputs/approved-fix2-hashes.json` and `/workspace/strat-command-recovery/task3-review-read-outputs/task-3-reviewed-files.json`, with Task3 overriding shared paths. The detailed independent results are in `independent-identity-check.json`.

| Production path | Verified approved SHA256 |
|---|---|
| `lib/data_loader.py` | `09bd3776afd57b533378d0ad9f867c24f36512f06b358cc62cc349669dcff780` |
| `lib/eastern_time.py` | `07f222ccd67a509645ea59a24144d705af578e27ee261ab4ea75b0ca6b0637ef` |
| `lib/strat.py` | `04a099e462e95353ebebe239db7537350ba1dfcbb3ca4830615b275a0001f95c` |
| `lib/exec_backtest/ftfc.py` | `4c6b337a397cb501f544bbcc789dedd6b061e748296993f6fc1e6c72f31027d0` |
| `gcp/research/p7_build_multi_tf_features.py` | `76aa11190d728fc0ecfdcc495f8e03cf68d473d8d7b47d692692e6c638bd9e43` |
| `gcp/research/strat_engine/strat_data_builder.py` | `0a93c472a40164cf44b34d0054f6c0fe6ee8ee23c7dac4d51947668b0102107d` |

The final `tests/lib/test_strat.py` is now exact, SHA256 `05e18c73f2b4ddde3240c57c95d760c8199877628a06f26870c867ed60692709`. It was the sole permitted pending file when review began; I read its completed 1,460-line file and verified the final hash.

`tests/lib/test_data_loader.py` is explicitly NEW replacement coverage, SHA256 `589ccf629f6ef75dfe97303282eff8e38467f0e646d200f22c6e91c8e8c53b92`. It does not match or inherit approval from the lost historical `24645d…` file. I independently compared its original-test prefix to the saved baseline: the prefix is unchanged except for the retained four-line coherent-OHLC fixture amendment at lines 41–44. The replacement class starts at line 696.

## Source and interface checks

I read all six production files and all five listed test files in full. I read AGENTS.md, the task-reviewer/re-review instructions, relevant CLAUDE review/no-silent-fallback rules, the recovery brief, published plan Tasks2–3/global constraints/dependencies, and the approved spec's clock, continuity and acceptance requirements. The full-file and direct-caller requirements took precedence over the narrow review template. No generator is involved in these source changes.

The previous Task2 defect classes remain repaired in the exact recovered code:

- `lib/data_loader.py:582`: default `legacy_v1` retains the historical pandas bins and OHLC calculation, rejects clock/source overrides without explicit `observed_v2`, and does not attach strict coverage. The two actual research builders keep this aggregation path and explicitly select `legacy-pattern-v1` (`p7_build_multi_tf_features.py:280`, `strat_data_builder.py:397`). Their literal feature goldens assert 77 2U plus one X and the existing winter four-hour boundaries.
- `lib/data_loader.py:872`: unknown/unsupported cadence, policy or timestamp semantics empties admitted observations before prices and cutoffs can become evidence. Daily labels use exchange closes; intraday bars use completed source intervals, capped at session close. Session labels and UTC instant keys remain distinct (`lib/data_loader.py:1060`, `lib/strat.py:88`).
- `lib/data_loader.py:1039`: missing expected observations in either aggregate of a comparison break adjacency. Coverage completeness through the clock remains separate from calendar-period completion; a valid partial period can retain its actual opening observation.
- `lib/data_loader.py:75`: concatenation reconciles all component contracts before pandas drops attrs. All three partition paths use it; explicit unknown/conflict/missing declarations survive the loaders' `setdefault` calls. Acquisition is unanimous or explicitly unknown/incomplete/mixed; price adjustment is unanimous or unknown. SQL timestamp decoding remains the existing boundary; local metadata recovery has not substituted a new Cloud SQL source policy or freshness claim.

Task3's strict price/open and strict candle results remain separate from the legacy weighted result (`lib/strat.py:497`, `:678`, `:714`). They require all requested frames, reject ambiguous aliases and incomplete evidence, and preserve unknown price provenance/freshness. Snapshot computation does not fabricate a current quote. The direct execution lookup retains its completed-bar shift, UTC-origin grid, original weight keys and NaN denominator behavior (`lib/exec_backtest/ftfc.py:66`).

Immediate caller/callee inspection included the two research builders and their indicator/configuration boundaries; DataLoader's normalization/filtering/SQL paths and the Eastern helpers; `lib/exec_backtest/cli.py:171` and `runner.py:267`; snapshot use in `lib/agents/summarizers.py:408` and `gcp/premarket_brief.py:1214`; classifier/weighted use in signal_monitor, lib/backtest, fetch_market_data, backfill_ticker, backfill_daily_indicators and indicator_correlation_job; and the two history report/backtest scripts. This confirmed which paths remain legacy and which still require later consumer migration.

## Fresh coverage verdict

**Adequate for this recovery checkpoint, not equivalent to the lost historical loader test module.** I inspected the actual assertions and saved outputs, not just the implementer's summary:

- `new-tests-red.txt`: 28 failed, two passed against the pre-restoration baseline. Much of this RED is missing API/helper shape; it is not by itself proof of every semantic guard.
- `new-tests-green-initial.txt`: all 30 replacement cases passed on the recovered source.
- `run-negative-controls.py` and `negative-controls.json`: actual assertions rejected three isolated deliberately broken implementations—future/incomplete minute admission, substitution for a missing period open, and first-partition metadata winning. This adds semantic sensitivity beyond the baseline's missing API failures.
- `covering-green.txt`: 154 passed in 1.88s across the six named modules.
- `strat-green.txt`: 206 passed in 3.36s after exact historical Strat-test restoration. Production hashes were unchanged between runs. Thus 360 distinct final cases passed; the 30-case preliminary run is a subset and is not counted again. No warnings or skips appear in those final logs.

The replacement tests exercise real local parquet loading, actual observed aggregation, concrete OHLC/count/cutoff expectations, one frozen live clock, DST/holiday/half-day daily availability, W/M/Q/Y opening evidence, invalid/missing minute adjacency, unsupported contracts, explicit policy admission, legacy bins and acquisition uncertainty. Fixture loading disables Cloud SQL. Recovered original tests additionally cover live/replay snapshot parity, invalid/gapped daily rows, strict continuity, UTC key conversion, research feature numerics and direct execution FTFC.

Coverage limitations, not newly demonstrated production defects: the replacement class does not directly cover annotated multi-file `minute/` metadata reconciliation (its partition matrix uses monthly `intraday/` and yearly daily paths), conflicting price-adjustment metadata, the daily-to-intraday refusal branch, or holes inside adjacent weekly/monthly aggregates on both sides of a comparison. Those guards are present in the hash-identical source and were previously reviewed; do not represent the replacement suite as restoring every historical regression test. The recovered Strat tests do cover daily missing-session refusal and successful UTC-key conversion, but those are not substitutes for all of the omitted loader edge cases.

## Explicit limits and handoff

The temporary `lib/eastern_time.py:403` NYSE cache/helper is restored old local code. As the published plan's canonical dependency section states, final production integration must adopt the actual merged shared `session_schedule` and DATA `prepare_daily_basis`/`restore_daily_units` interfaces, with real admission/guard/parity checks. This review does not certify calendar overrides/delayed opens, price-basis lineage, point-in-time source acquisition or corporate-action integration.

Later consumer work is still absent from this checkpoint: for example, the summarizer reconstructs a narrow old dictionary (`lib/agents/summarizers.py:420`), the brief still substitutes neutral values for unavailable state (`gcp/premarket_brief.py:1225`), the signal monitor still constructs the default classifier (`gcp/signal_monitor.py:131`), and history CLI calls do not forward a clock/basis contract. These are known Task5 handoffs, not recovery-introduced changes or certifications that the whole feature is ready.

No duplicate test suite or semantic probe was run by this reviewer. No code, tests, Git state, source captures, database, GCP or external messages were changed; only this report and the independent hash-check artifact were written. Approval applies to local recovery identity and the stated pure-contract coverage only. Root retains publication, later-task recovery, integration and delivery gates.
