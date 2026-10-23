# Current local validation and baseline evidence

This checkpoint supersedes pending-state statements in the chronological recovery notes. Tasks1–5E are accepted only as bounded local reconstruction partitions. Task5E passed its original reviewer’s scoped fix1 verification; Task6 actual production-entrypoint replay implementation has started with read-only source inventory. No repaired brief/insight production-entrypoint October replay, movement-outcome scoring, earnings evaluation or predictive performance acceptance has run. The Oct10–16 holdout remains quarantined and unscored.

## Actual local commands and limits

All commands below ran from `/workspace/stocks-strat-rebuild`, after sourcing `/workspace/stocks-setup/shell-env.sh`; Python is `/workspace/stocks-venv/bin/python`. They are completed evidence, not a request to repeat unchanged suites.

```bash
/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5d-rebuild/run_affected.py
# 102 passed, 45 existing utcnow warnings, 1.38s; focused synthetic only, external sockets/DB/provider refused.

/workspace/stocks-venv/bin/python -m pytest tests/gcp/test_backfill_daily_indicators.py -q --tb=short
# Task5B final affected mock:25 passed,0.32s.

/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5b-rebuild/run-tests.py tests/integration/test_strat_scheduled_capacity.py tests/integration/test_strat_schema_compatibility.py -q -k 'actual_selector_publication or actual_main_refuses or actual_supported_dispatch or scheduled_small_chunks or full_backfill_preserves_legacy or each_new_writer_preserves_its_actual_weighted_policy or scheduled_full_retains_invalid_canonical_diagnostic' --tb=short
# 23 passed,35 deselected,10.28s; actual owned localhost PostgreSQL, synthetic rows only.

/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5b-rebuild/run-tests.py /workspace/strat-rebuild-control/task5b-rebuild/fix1/single-worker/measure-complete-sessions.py -q -s --tb=short
# 1 passed,16.62s: actual scheduled main, one synthetic ticker x2500 actual NYSE-session labels xone worker, cold/warm stable2500 states.
```

The guarded PG runner admits only the owned local test endpoint and refuses external connections. Its credential mapping is excluded from public archives. Actual database tests cover changed writer/schema/rollback/readback boundaries; they do not establish full application lifespan or October main replay. The scheduled writer's accepted operating envelope is ONLY one explicitly selected ticker,<=2500 complete daily-history rows,one worker. Default full-universe/multiple-ticker/worker requests refuse; that limitation is material. The 252 earlier Task4 focused passes are pure structural evidence, not end-to-end readiness. Counts from different revisions/overlapping suites are not summed.

## Is the baseline data promising?

It supports an evaluation, but predictive performance remains unknown. Baseline Oct1–9 has seven sessions:Oct1,2,5,6,7,8,9. Twelve symbols are SPY,QQQ,IWM,ANGO,TLRY,PEP,BYRN,HELE,NG,NRIX,DAL,APLD. Daily key coverage is84/84; new current-vintage minute-label coverage is29816/32760 (91.0%),2944 absent. The denominator is12 symbols x7 sessions x390 RTH minute labels. SPY,QQQ,IWM,PEP,DAL,APLD each have2730/2730. Remaining:ANGO2050/2730,TLRY2643/2730,BYRN1812/2730,HELE1780/2730,NG2704/2730,NRIX2447/2730. Missing causes are unknown; no fill-forward. BYRN/HELE gaps materially constrain minute-path evaluation. Coverage is not proof of price-basis or historical-vintage qualification.

A separately recovered archived SQL subset contains336 daily context rows throughOct9 (including84 baseline rows) and2757 Oct9 ETF minute rows. Basic checks found zero duplicates, nonfinite/nonpositive prices, missing OHLC, incoherent OHLC or invalid volume;12 minute rows have zero volume and are flagged. This QC scope is not all new AV prices. Provenance: daily subset SHA256 `8ea22fc3b25c51b5ded33a951a204345baa44e6709e7f998ec63c86b9d64eb39`, original `db-query-fnvln.json` generation1792720053212792; minute subset SHA256 `f42db123af4ef4de493de92e4fee1be9d3eb4a2f1dba5b9887b1ed90c9fbcb23`, `db-query-6vnz7.json` generation1791784449636533. Two unverified Oct10 boundary records were excluded. Aggregate QC receipt SHA256 `fddc5122861589cb386e256571aca3d1129936560b27c14379e1401825c24521`.

Stored archived brief/insight candle/combo labels differ on6/6 paired SPY/QQQ/IWM keys forOct8/9. Exact input/clock/basis equivalence is unproved; these discrepancies justify repair/evaluation, not a claim either prediction was correct. There are NO actual repaired-engine October level-validation, activation, target/stop-order or subsequent-movement outcomes yet. No profitability claim follows from recovery or synthetic passes.

## Data acquisition and safe replay dependencies

All24 planned AV payloads are captured:one Oct2026 raw extended-hours minute payload and one full adjusted daily payload per symbol. A reused SPY probe plus23 later requests completed; observed23-call run48.232s;zero planned requests remain. There was one separate connector refusal. Process-local30RPM/single-inflight pacing does not establish shared account quota, remaining balance or billing cost; those need the account contract and aggregate usage. No extra requests were made to estimate them. These are Oct23 current-vintage reacquisitions, not the missing467 original local captures or February–May archives. Raw month/full-daily payloads extend beyond the baseline and remain quarantined; no holdout scoring.

Before safe repaired local main replay:implement/reviewTask6 actual brief/insight captured-input and explicit-clock no-write routes, blocking SQL/history/GCS/notifications/CloudTasks/run transitions/level persistence and mutating cleanup. Existing no-discord/as-of switches are insufficient. A synthetic/unqualified main replay could then prove implementation behavior only. Meaningful admitted market baseline outcomes additionally require the genuine shared calendar and DATA prepare_daily_basis/restore_daily_units prerequisites plus source-clock/session/basis/factors/vintage qualification and upstream gates. Do not copy unmerged helpers, assume factor1 or fabricate historical availability. Run the real engine to freeze timestamped baseline hypotheses before comparing subsequent baseline-only movements.

Pure/mock checks are runnable now. Small owned local PostgreSQL tests can run after root health/free-space and endpoint verification; no cloud/production database is required. Spec-on-main/code-commit and actual upstream qualification remain separate gates. No unguarded production-main replay is runnable safely yet. Overall completion duration is unknown pending these remaining implementation/review/dependency gates.

Raw recovery backup is separately complete:three approved create-only objects,total6476832 bytes,authenticated generation-pinned readback,all30 archive members and manifest verified. Exact URIs/generations/hashes were returned privately to the owner. Organization-level visibility remains unknown,disclosed and accepted. No raw payload or credentials are published here.

## Task5E prechange and sensitive failure checkpoint

Before production edits,54 actual consumer synthetic cases plus two configured-weight cases were preserved. Initial sensitive selection:16 failures in2.18s, with exact argv/cwd/source/output receipt. Mother-bar numeric/planner selection already passes; these cases fail on missing source provenance and do not establish a current mother-walk defect. Resolver tests initially fail on transaction locking; a separate unchanged-source actual resolve_one-to-UPDATE capture independently confirms stale-trigger movement/return credit when opening beyond the trigger. CALL100/firstOHLC110,111,109,110 and mirrored PUT100/90,91,89,90 are synthetic counterexamples, not October data or performance.

Source-only full prechange/RED archive:71members,415712 bytes,SHA256 `ed9ad401d3439516cd62f0cf8555c004d77d66926b1a657fa4aef342a439e1d8`;15 verified parts begin [6374517445](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6374517445) and end [6374523585](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6374523585). All remote bytes/member hashes verified; no raw market data/credentials. Worker implementation continues; no final GREEN or independentTask5Eacceptance claimed.

Fresh read-only GitHub check:STRAT replacement1575 headf1b6629c,calendar1546 head5b926526,DATA1489 head69ff86fc remain open drafts/unmerged. GCP authentication/provider retrieval is not the current blocker. Task6 is prepared only,not dispatched before5Eacceptance.

## Frozen cross-consumer candidate

The [Task5E frozen report](2026-10-23-strat-task5e-frozen-candidate.md) records320 final focused mock passes, three final weighted controls, eight actual local PostgreSQL cases and one necessary provenance readback rerun at their exact disclosed revisions. Counts overlap; no actual October brief/insight production main ran. Independent complete first review is active.18changed fullfiles/1017preceding artifacts independently verified; final source/evidence archive and all62 combined source paths reconstruct from verified PR archives. Baseline data-quality evidence above remains the available market result; predictive outcomes remain unknown.

Task5E complete first review has now returned three P2/Important findings (processing-time identity, missing ordinary unavailable envelope and structural code-lineage omission), recorded in the linked frozen report. Original implementer fix1/5 is active; Task5E is not accepted and Task6 remains held. Passing checks remain valid at their disclosed revisions; they did not expose these uncovered integration edges. No new market outcome or holdout result is implied.

## Accepted Task5E fix and current Task6 checkpoint

Task5E original scoped fix1/5 review: specification PASS, quality PASS; all three original findings addressed, zero new fix-induced findings. Review SHA256 `ec61e5b558ee86ea90d5f737643bf0bfb537c3bda3d814afb661fa3919520e1d`; evidence `b7be8526dc1a4231df85334686df719221482e20d5598739694f7d4b6a9b2040`. Earlier pending/fix-active paragraphs above are chronological and superseded by this acceptance. No broader production or market-performance acceptance follows.

The final20-file manifest is `26f7181b1294a0f6f97618a52267cdc6037aa2af4314fd628c34ba3529cc3f91`. Fix1 changed five production paths and two test paths. The fixed generator uses the observation clock in canonical state identity, ordinary unavailable paths preserve a truthful structural envelope, and code identity includes its structural dependencies. Numerical rules, financial policy and unsupported temporal-PMG status remain unchanged.

Completed commands from the same detached worktree:

```bash
/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5b-rebuild/run-mock-tests.py tests/gcp/test_strat_task5e_fix1.py --mode=mock -q
# 21 passed,13.82s,six existing DataFrame fragmentation warnings; synthetic/external-refused.

/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5b-rebuild/run-tests.py tests/integration/test_strat_task5e_contract.py::test_fix1_actual_generator_observation_identity_current_history_state tests/integration/test_strat_task5e_contract.py::test_fix1_ordinary_missing_context_typed_writer_api -x -q
# Actual owned PostgreSQL:1 passed/1 failed,3.87s; second case’s synthetic ticker exceeded VARCHAR(10).

/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5b-rebuild/run-tests.py tests/integration/test_strat_task5e_contract.py::test_fix1_ordinary_missing_context_typed_writer_api -x -q
# Corrected test-only ticker:1 passed,2.29s. Both PG cases passed across separate invocations.
```

A separately approved20-selector affected selection passed40 cases in6.34s; exact selector list/argv/source receipts are retained. Earlier failed fixture attempts and revisions are preserved, including qualification-metadata and absent outer-provenance assertions. Reviewer independently verified final identities and passed-test lineage without rerunning tests or SQL. Final read-only postflight found all five inspected local tables empty and zero OOM events. Do not sum overlapping test counts or equate these with October main replay.

Final sanitized source/evidence archive:134members,317408 bytes,SHA256 `832a1bb9327677e2052f7d5363942d8bafba116d0f4b38964901e986730fae8b`;12 remote/member-verified parts [first6375556277](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6375556277) through [last6375560188](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6375560188). The seven-archive restoration proof reproduced all63 current source paths without modifying the worktree. Its review-pending flag records the proof’s creation time; the subsequent scoped review is the acceptance evidence. No raw data or credentials are in these public source backups.

Task6 is dispatched to a fresh sole implementer under the existing SDD gate. First deliverable is the actual main/source/side-effect inventory and bounded implementation plan before production edits. No-write/cutoff/capacity behavior can be implemented and proved with synthetic inputs within existing authorization. Source-qualified October results additionally depend on genuine calendar/DATA helpers and admitted provenance. No unguarded main, new retrieval, production write, holdout peek/scoring, merge or deployment is authorized here. Overall engineering completion duration remains unknown; the next substantive checkpoint is the source inventory and concrete replay design.
