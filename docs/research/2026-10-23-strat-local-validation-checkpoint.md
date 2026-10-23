# Local validation checkpoint — reconstructed STRAT engine

Local code correctness has passing evidence; actual production-entrypoint replay has **not run**. Task4 scoped approval is not end-to-end readiness. Task5A shared-producer/in-memory consumer reconstruction passed its original reviewer's scoped fix1/5 verification. Task5B persistence reconstruction is active with isolated PostgreSQL ready; source-qualified production integration remains dependency-blocked. No production deployment or holdout scoring is authorized by this checkpoint.

## Actual executed commands

Working directory `/workspace/stocks-strat-rebuild`; shells source `/workspace/stocks-setup/shell-env.sh`; Python is `/workspace/stocks-venv/bin/python`.

```bash
/workspace/stocks-venv/bin/python -m pytest tests/lib/test_strat_levels.py -k StructuralFix2 -q --mode=mock
# Before fix2: 7 failed,16 passed,191 deselected in0.46s
/workspace/stocks-venv/bin/python -m pytest tests/lib/test_strat_levels.py -k 'StructuralFix2 or StructuralFix1Lifecycle or TypedStructuralLifecycle' -q --mode=mock
# After fix2: 57 passed,157 deselected in0.33s
/workspace/stocks-venv/bin/python -m pytest tests/lib/test_strat_levels.py tests/lib/test_strat_levels_playbook.py tests/lib/test_strat_levels_freshness.py -q --mode=mock
# 252 passed in22.66s, no skips/warnings
/workspace/stocks-venv/bin/python -m pytest tests/lib/test_strat.py -q
# Earlier Tasks2–3 recovered checkpoint:206 passed in3.36s
/workspace/stocks-venv/bin/python -m pytest tests/lib/test_data_loader.py tests/lib/test_eastern_time.py tests/lib/test_exec_ftfc_contract.py tests/lib/test_exec_backtest.py tests/lib/test_strat_history.py tests/gcp/test_strat_data_builder_gamma.py -q
# Earlier Tasks2–3 recovered checkpoint:154 passed in1.88s
```

These are local fixture-driven checks against production functions and selected adapters, not evidence of live provider/SQL or complete consumer integration. Earlier360 and final252 describe different scopes/revisions and were not rerun as a new integrated total. [Task4 scoped review and verified source backup](2026-10-23-strat-task4-fix2-review.md) preserves exact source/test identities, full test logs/argv, sensitive before-fix failures and the original reviewer PASS. No suite was rerun by the reviewer.

## Baseline-only descriptive results

No strategy movement/activation/earnings/return outcome scoring has been performed. Basic data-quality checks are useful evidence of input usability, not predictive performance.

| Source/scope | Denominator / observed | Descriptive result |
|---|---|---|
| Archived SQL daily labels,12 symbols, Oct1–9 |84 expected symbol/session keys,84 present | No duplicate keys, missing/nonfinite/nonpositive OHLC, impossible OHLC ordering or invalid volume; zero zero-volume rows |
| Same archived daily source including Sept1 context |336 rows | Same basic checks pass; does not cover prior quarter/year structural context |
| Archived SQL raw stored Oct9 ETF minute labels |2,757 rows: IWM838,QQQ960,SPY959 | No duplicate keys, invalid OHLC numbers/order or invalid volume;12 zero-volume rows retained and flagged |
| New Oct23 Alpha Vantage acquisition, Oct1–9 RTH labels |29,816 /32,760 expected labels (12×7×390) |91.0134% label coverage;2,944 absent; missing causes unknown, no fill-forward |

New-acquisition baseline labels by ticker:

| Ticker | Returned /2,730 | Absent |
|---|---:|---:|
| SPY |2,730 |0 |
| QQQ |2,730 |0 |
| IWM |2,730 |0 |
| ANGO |2,050 |680 |
| TLRY |2,643 |87 |
| PEP |2,730 |0 |
| BYRN |1,812 |918 |
| HELE |1,780 |950 |
| NG |2,704 |26 |
| NRIX |2,447 |283 |
| DAL |2,730 |0 |
| APLD |2,730 |0 |

Archived daily subset comes from `db-query-fnvln.json` generation1792720053212792; baseline-only extraction SHA256 `8ea22fc3b25c51b5ded33a951a204345baa44e6709e7f998ec63c86b9d64eb39`. Minute subset comes from `db-query-6vnz7.json` generation1791784449636533; extraction SHA256 `f42db123af4ef4de493de92e4fee1be9d3eb4a2f1dba5b9887b1ed90c9fbcb23`. Two unverified raw-date boundary records stay excluded from the baseline subset and remain only in the unchanged original archive. No timezone/session reinterpretation was inferred.

The quality script checked isolated baseline files and existing baseline metadata only, without opening monthly vendor raw payloads or any holdout price fields. Input bytes were unchanged. Local descriptive report SHA256 `fddc5122861589cb386e256571aca3d1129936560b27c14379e1401825c24521`; exact script invocation was `/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/check_recovered_baseline_quality.py`, followed by an explicit expected-seven-session-label check. No raw market values or native output blobs are published here.

Recovered baseline native outputs comprise24 briefs,22 insight records,89 alerts,1,149 calendar records and3 reaction records. These counts describe recovered records, not independent event denominators, correct predictions or validated outcomes. Task4's synthetic structural prices are not actual October level-validation results. Missing timestamp/basis/acquisition evidence still prevents engine-input qualification; numeric OHLC checks cannot establish coherent adjusted units or contemporaneous availability.

## Actual entrypoint audit and remaining prerequisites

Static source inspection only; neither production main was launched:

- `gcp/premarket_brief.py:main` calls `generate_premarket_brief` then `persist_to_cloud_sql`; `--no-discord` explicitly disables only notification. Current `BRIEF_AS_OF` also selects replay/update behavior. A replay flag is not a no-write boundary.
- `gcp/insight_pipeline_job.py:main` chooses `_run_on_demand` or `_run_scheduled`. `_run_one` transitions a run, calls the actual insight orchestrator, appends history, upserts a report and transitions again. Scheduled mode can create queued runs/fan out Cloud Tasks. `INSIGHT_AS_OF` implies update semantics; there is no demonstrated captured-input/no-write main route.
- `scripts/validation/validate_brief_accuracy.py:main` currently connects to SQL and validates existing outputs. Its existing scorecards are not a repaired production-orchestration replay. It must become only a launcher/comparator of real production outputs under Task6, not another evaluator engine.

Before a safe **repaired-system** local production-entrypoint replay: finish/review remaining5B–5E actual shared consumers, real PostgreSQL persistence/migration/readback, history/CLI cutoff, legacy monitor routing and M1 envelope/resolver handling; implement/test Task6 actual production captured-input/explicitclock/no-write modes with all SQL/history/GCS writes, notifications/fan-out and mutating cleanup paths refused. A controlled synthetic/unqualified diagnostic replay would establish implementation behavior only. Source-qualified market evidence additionally requires the actual merged shared calendar and DATA `prepare_daily_basis`/`restore_daily_units`, admitted source clock/session/basis/factor/vintage and upstream validation gates. Measure no-future inputs and actual parity at the admitted full12-symbol/two-session,≤256MB/≤6source-read envelope and fixed quarter-timeout budget. Do not treat safe execution of unqualified diagnostics as strategic baseline acceptance.

The candidate still lacks `lib/price_basis.py`. The local database-runtime dependency is now resolved using the repository CI image `pgvector/pgvector:pg15`, pinned digest `sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9`. A dedicated loopback-only PostgreSQL15.19 instance accepted a guarded identity SELECT and the unchanged baseline schema (69 public tables plus pgvector). No market/holdout rows were loaded. This is runtime/schema bootstrap evidence; actual Task5B application migration/writer/API integration tests are pending. No GCP authentication or production SQL access was needed.

Pure coherent-input math/contract reconstruction and focused synthetic checks are runnable now. Actual production integration cannot be certified using copied unmerged helpers, factor1, fabricated acquisition identity or current-vintage data presented as historical knowledge. Canonical PMG/custom anchors remain owner-undefined and explicitly unsupported. Code delivery still requires approved-spec-on-main/spec-gate compliance; no merge authorization is inferred.

Raw recovery backup is separately owner-authorized and verified by exact object generations/hashes/member readback; the private receipt was returned in owner chat. Original467 local captures remain missing; new current-vintage retrieval is distinct. No raw data is in this source-only checkpoint. Organization visibility remains unknown and accepted, not verified private. Holdout remains quarantined and unscored. Meaningful baseline outcomes await the actual admitted, reviewed no-write production replay and timestamped hypotheses compared to subsequent baseline-only movements.

## Historical preparation and checkpoint1 (superseded by fix1 approval below)

Read-only GitHub recheck confirms replacement STRAT specification [#1575](https://github.com/TeneikaAskew/stocks/pull/1575) head`f1b6629c5eb4292c02899ef5da4ebd88824e6e3d`, shared-calendar CODE [#1546](https://github.com/TeneikaAskew/stocks/pull/1546) head`5b9265263ce517582b95c3a662fb6fe0d7b12278`, and DATA prerequisite [#1489](https://github.com/TeneikaAskew/stocks/pull/1489) head`69ff86fc19489581e36f8af74e446dd2724bcba2` all remain open drafts/unmerged. No denied organization IAM retry, API enablement, deployment or production replay was attempted.

Static baseline inspection also confirms internal brief-generation level persistence/commit and a daily-data correction/cleanup DELETE path. Task6 must protect these as well as main persistence, insight run transitions/history/upserts, fan-out, notifications and other mutating cleanup. Test-isolating these paths for5A does not implement a production no-write mode.

The baseline quality helper and aggregate receipt are preserved in a [four-member source-only archive](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370591727):4,192 bytes,SHA256`bf7393c7041a24282802e4cd253cb609fc26549cc68ea6befa4dbf6b7725470f`, round-trip bytes/member hashes verified. The helper now includes the exact84-label check internally; a rerun reproduced the original report without changing its receipt hash. No raw source rows or holdout values are in this backup.

Task5A remains **in progress and unreviewed**. Checkpoint1 has48 focused synthetic adapter/producer cases passing; its actual final affected-suite batch and independent task review are not yet complete. This does not replace the earlier Task4 frozen source/test identities or prove production readiness. Source-only archive `task5a-in-progress-checkpoint-1.tar.xz`:154,168 bytes,37 members,SHA256`7948d1fd4600e1c33411bd5ce9481e9aaef9bd2ff01f2c0add4a9f0b13c29b77`; all remote bytes/member hashes verified. Its26-path manifest records11 changed producer/consumer/test paths versus acceptedTask4. Changed files and exact prechange baselines are included; unchanged checkpoint source is recoverable from earlier Task4 archives. No raw data or credentials are included.

- [Task5A checkpoint1 archive part 1/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370663234)
- [Task5A checkpoint1 archive part 2/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370663987)
- [Task5A checkpoint1 archive part 3/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370664523)
- [Task5A checkpoint1 archive part 4/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370664982)
- [Task5A checkpoint1 archive part 5/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370665436)
- [Task5A checkpoint1 archive part 6/6](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370665886)

## Additional archived baseline consistency evidence

A read-only check of the recovered original native-output subsets finds **6/6 unique paired date/ticker keys** (SPY/QQQ/IWM×Oct8/9) have different stored candle/combo labels: all six insights store`1 / none`; all six briefs store`2D`, with bearish22 reversal onOct8 and bearish22 continuation onOct9. Brief data-source labels are prior-sessionOct7/8. There are exactly six selected records on each side, no duplicate pair keys.

This is a categorical stored-output discrepancy, not a verified equal-clock parity failure or an outcome score: exact observation clock, completed/current session, price basis and source alignment still need the admitted production replay before declaring which output was correct. No native payload blob, price series, holdout value or predictive/profitability claim is published. Derived receipt SHA256`8573b443487ed53e314530d5ec4fb1436734f9355e2d8311f71668ef2436ce72`; input subset hashes: insights`6bf15ab7d48613bb145243ba2a94de9e26ff24ec40cf2858e55a85e01b109f74`, briefhistory`8ef45846765f4aa7d7a770e7ce9a95e0a39a81e421eaf8e78dbadaa83391a0bf`. Source: already-recovered`db-query-c5558.json` native archive, baseline-only subsets.

## Frozen Task5A candidate under first independent review

The candidate is frozen at26 source/test paths and13 changes, manifest SHA256`7180cd41670b5ddb84d1fc863ddbe6dd609ad7c142e742aea1eef87025961368`. Actual affected mock batch:753 passed in9.70s before complete self-review. Additional actual RED3 andRED4 cases prompted legacy precision/composition, coverage retention, stale/optional-level snapshot and historical clock compatibility corrections; the justified post-correction subset passed458 in6.32s, including all59 new parity cases. The runs concern different source phases and overlapping suites: do not sum them as a distinct final count or assert end-to-end readiness. Full literal argv, fixture corrections and source chronology are preserved. No job main or captured-input production replay ran.

At this frozen-candidate backup checkpoint, the first independent completeTask5Areview was active and had **not granted approval**. Its completed result is recorded below. It independently matched live/frozen26paths,25baselinefiles,234priorartifacts,15acceptedfrozenpaths and the complete diff. A bounded pure synthetic probe confirmed a remaining gap-retention risk in current-minute merging; a coverage/extrema minute-grid mismatch is also being checked within the same complete review batch. No piecemeal source fix or new review loop was dispatched; Task5B remains held at this task gate. This is separate from the unchanged calendar/DATA/spec-main and actual production-proof gates.

Source-only final candidate delta:184,636bytes,62members,SHA256`b90916301a43341a0a1db7bb13a201b7b518b5657d746502b09486dd96c38e5c`; all remote archive bytes/member hashes verified after retrieval. EarlierTask4 fullfiles +Task5Acheckpoint1 +this delta reconstruct every final26path byte/hash in memory, without using patches from summaries or writing live source. No rawprovider/nativecaptures/privateIAM/credentials/holdoutvalues are included. The source archive is labelled reviewpending; the separate final review report will carry its own exact identity.

- [Final Task5A source archive part 1/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370913500)
- [Final Task5A source archive part 2/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370914221)
- [Final Task5A source archive part 3/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370914775)
- [Final Task5A source archive part 4/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370915245)
- [Final Task5A source archive part 5/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370915671)
- [Final Task5A source archive part 6/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370916048)
- [Final Task5A source archive part 7/7](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370916470)

## First complete Task5A review and historical fix gate

The [complete first independent review](2026-10-23-strat-task5a-first-review.md) returned **NEEDS_CHANGES:3P1/Important +1P2/Important;0Critical**. All four classes are one batch: predecessor gap/period coverage preservation; consistent minute grid/numeric admission; the new unavailable status escaping existing brief canonical-write/render guards; and separately declared extended quotes truncated at RTH close. Exact reviewer probes are synthetic and the persistence boundary used only an in-memory capture stub, with no real database connection/write. All frozen identities/diffs/test chronology matched.

The original implementer is active on existing **Task5A fixround1/5**, limited to these fourclasses and their necessary regression controls. Four ownedpaths are planned; no schema migration, levelmodule edit, new calendar/policy, production data/entrypoint, Task5B, deployment or holdout scoring is included. Task5A remains unapproved pending fullbatch RED/fixes/GREEN/freeze and scoped independent verification. Source archives preserve the original reviewed candidate rather than overwriting its evidence.

## Accepted Task5A fix1 and current Task5B work

The [original reviewer scoped fix1 verification](2026-10-23-strat-task5a-fix1-review.md) returned **PASS**, with zero remaining or new findings across the four-class batch. Sensitive corrected RED:16 failures plus6 controls. Final affected selection:239 passed in6.81s, including all85 parity cases; the separate85-case run is overlapping, not additive. These remain explicit mock/synthetic checks, including actual brief writer functions against in-memory database stubs. No repaired production-entrypoint replay has run. Exact commands and source identities are in the linked report and verified archives.

Fix1 source delta:25 members,91,696bytes,SHA256 `9c2e3d8ebee0e9d7ddfcd82887217c3fdc9fcb4b7efe5c2dfe99d01ee1cf978d`, [part1](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371306139), [part2](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371306734), [part3](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371307366), [part4](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371307947). Five-archive in-memory full-file restoration verifies all26 accepted paths against frozen bytes; no summary patches or live writes. Local combined receipt SHA256 `f497c046b0bd0aaf67795f5104f2ce218319c3a785278f15e1a972f053311b77`.

Task5B has preserved41 accepted/prospective paths and begun bounded persistence/schema/dashboard reconstruction under the existing scope. Initial pure synthetic capacity evidence found12 repeated full snapshot calls cost14.505s, unsuitable for historical full backfills. A minimal shared descriptive daily batch API using the existing classifier is authorized locally; date-only labels retain unknown observation/acquisition/basis and unavailable current action. Actual caller weights and protected legacy nulls must remain unchanged. This is not production capacity or baseline predictive evidence.
