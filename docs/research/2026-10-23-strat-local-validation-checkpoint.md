# Local validation checkpoint — reconstructed STRAT engine

Local code correctness has passing evidence; actual production-entrypoint replay has **not run**. Task4 scoped approval is not end-to-end readiness. Task5A shared-producer/in-memory consumer reconstruction is now active under the existing approved scope; source-qualified production integration remains dependency-blocked. No production deployment or holdout scoring is authorized by this checkpoint.

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

Before a safe **repaired-system** local production replay: finish/review5A–5E actual shared consumers, real PostgreSQL persistence/migration/readback, history/CLI cutoff, legacy monitor routing, M1 envelope/resolver handling; adopt actual merged shared calendar and DATA `prepare_daily_basis`/`restore_daily_units`; admit source clock/session/basis/factor/vintage; implement/test Task6 actual production captured-input/explicitclock/no-write modes with all SQL/history/GCS writes, notifications/fan-out and mutating cleanup paths refused. Then measure no-future inputs and actual parity at the admitted full12-symbol/two-session,≤256MB/≤6source-read envelope and fixed quarter-timeout budget.

The candidate currently lacks `lib/price_basis.py`. Discovery found no host `postgres`, `initdb`, `pg_ctl` or `psql` executable and no `/usr/lib/postgresql`; Docker CLI exists but no isolated PostgreSQL instance was started or tested in this checkpoint. Python psycopg2,pg8000 andSQLAlchemy are installed. This is a local test-runtime dependency to address at5B, not an asserted GCP authentication failure.

Pure coherent-input math/contract reconstruction and focused synthetic checks are runnable now. Actual production integration cannot be certified using copied unmerged helpers, factor1, fabricated acquisition identity or current-vintage data presented as historical knowledge. Canonical PMG/custom anchors remain owner-undefined and explicitly unsupported. Code delivery still requires approved-spec-on-main/spec-gate compliance; no merge authorization is inferred.

Raw recovery backup is separately owner-authorized and verified by exact object generations/hashes/member readback; the private receipt was returned in owner chat. Original467 local captures remain missing; new current-vintage retrieval is distinct. No raw data is in this source-only checkpoint. Organization visibility remains unknown and accepted, not verified private. Holdout remains quarantined and unscored. Meaningful baseline outcomes await the actual admitted, reviewed no-write production replay and timestamped hypotheses compared to subsequent baseline-only movements.

## Continued local preparation and checkpoint1

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
