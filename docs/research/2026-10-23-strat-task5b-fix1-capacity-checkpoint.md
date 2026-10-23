# Task 5B fix round 1: bounded capacity checkpoint

The first independent review remains NEEDS_CHANGES until the original reviewer verifies both concerns. F1 now has nine passing real-PostgreSQL selector/repair regressions. F2 admission/transaction checks pass, but capacity acceptance remains pending.

The original four-worker probe had a confirmed local OOM. The subsequent changed-candidate four-worker run failed during state inserts; Docker records exit code 1 and automatic container removal at 19:25:36 UTC, without a second OOM event. Its exact exit cause is unknown. This is not evidence of a deployed Cloud SQL failure. The blocked candidate is frozen at manifest SHA256 `4bbab78c87b42aaa91e5d72f88ab71871841f2426649615b8ea6b26461df616d` (43 paths, 42 present). All 153 preceding evidence artifacts remained unchanged.

Only the ephemeral synthetic PostgreSQL service was recreated. The workspace, source changes and real captures remain intact. The pinned image, localhost port, generated test credential and resource limits are unchanged: 384 MiB, one CPU, 128 MiB database tmpfs, 128 PIDs. The replacement is retained on failure for diagnosis. The unchanged original schema was loaded and a database/version/count query confirmed zero market rows. New OOM counters are zero; initial available database space is 79,816 KiB. No production data or cloud credentials enter this test service.

The revised candidate admits exactly one selected ticker, up to 2,500 complete history rows, and one worker. Larger requests must refuse before publication. There is no history slicing or silent ticker truncation. Default full-universe processing remains unsupported: this is a material operating limitation, not full-universe capacity acceptance. Two sensitive refusal tests failed before this narrowing; the affected mock module subsequently passed 25 tests. Complete cold and repeated single-worker dispatch measurements, final affected regressions and original scoped verification remain pending.

## Interpretation of local evidence

Task 4's 252 focused passes and Task 5A's 239 final passes are separate synthetic checkpoints. Task 5B's frozen candidate passed 42 actual PostgreSQL behavior checks; later fix-round checks are separate revisions and must not be summed as a final suite. The saved one-worker 2,500-row actual scheduled dispatch passed in 7.18 seconds. Its harness invoked actual scheduled main against synthetic data with external access refused. This is not October captured-input replay or production readiness.

Actual repaired brief/insight entrypoint replay has not run. Remaining work includes consumer repairs, a tested explicit-clock/no-write harness that refuses every production side effect, source qualification and existing specification/dependency gates. The new raw data is October 23 current vintage, not recovered original point-in-time captures. Holdout stays quarantined and unscored. Completion duration is unknown; the next checkpoint is the complete narrowed-dispatch measurement and scoped review result.

## Baseline-only descriptive findings

The archived baseline contains all 84 expected daily symbol/session keys (12 symbols × seven Oct 1–9 sessions). Newly reacquired regular-session minute labels cover 29,816 of 32,760 expected rows (91.0%). Six symbols are complete; BYRN and HELE lack roughly one-third of expected rows. Missing labels are not filled or assumed to be errors. Across the checked archived 336 daily context rows and 2,757 Oct 9 ETF minute rows there were no duplicate keys or invalid OHLC/volume values; 12 zero-volume minute rows were flagged. These archived-subset checks do not validate every new provider price.

Six stored ETF brief/insight label pairs on Oct 8–9 differ, but their clocks, price bases and input alignment are not established, so that is not a proven same-clock classification error. No actual October support/resistance validation, activation outcomes or repaired-model market-movement results exist yet. Coverage supports a credible evaluation; it establishes no predictive performance or profitability.
