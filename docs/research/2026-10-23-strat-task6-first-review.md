# Task6 first complete independent task review

Reviewed detached reconstruction based on `a5749d4c0b9395582181e8884d2b33af889f5f91`, against the exact eleven-path freeze in `final-source/manifest.json` (SHA256 `9ad088d00f44cf2931db34e3e0bf43e21dcf0e37439f5291737fcee41b01a19f`). This is the first complete Task6 review, covering introduced defects at all severities in one batch. No finding is reserved for another broad review.

**Specification verdict: FAIL for the bounded synthetic code-proof stage. Task quality: NEEDS FIXES.** Findings R1–R6 below prevent accepting the stated diagnostic/evidence contract; R7 is minor. R1 is P1 and also crosses the repository's P1 merge-blocking threshold. P2 findings remain real task-specification/quality gaps; this report does not silently waive them based on the PR threshold.

**Full Task6 verdict: BLOCKED / NOT RUN.** Actual October baseline/outcomes, acquisition/current-vintage qualification, genuine spec-on-main, merged shared-calendar integration and merged DATA `prepare_daily_basis`/`restore_daily_units` are not established by synthetic replay. Neither a repaired bounded stage nor the retained maximum-capacity result can complete those requirements. No October market payload or holdout was opened here. No predictive edge, execution fill, deployment suitability, model promotion or production calendar/basis certification is awarded.

## Complete finding batch

### R1 — P1 / Important: Parse diagnostic selectors before replacing process argv

**Location:** `gcp/premarket_brief.py:3551–3554`; early render at 3591–3600.

The new guard recognizes only exact option names, while the actual argparse parser accepts unambiguous long-option abbreviations. With `BRIEF_POST_EXISTING_TICKER=T600`, `BRIEF_POST_EXISTING_DATE=2026-10-09`, an aware `BRIEF_AS_OF`, and process argv `--replay diagnostic --captured MUST_NOT_OPEN_SYNTHETIC_PATH --no-w`, the guard misses every diagnostic selector and replaces argv with `--post-existing`. Consequently `context_from_arguments` sees no diagnostic tuple and the main calls `render_existing_brief_to_discord`. The actual render function reads the stored brief and can post to configured Discord webhooks. This violates the explicit requirement that contradictions/no-write be resolved before every early live branch.

**Confirmed by the one root-authorized offline probe:** the recording render sentinel received `T600, 2026-10-09`; main raised `SystemExit(1)` because the sentinel returned false. External-attempt count was zero, no real rendering/posting ran, and the synthetic nonexistent capture path was not reached. All eleven source hashes remained unchanged. The evidence is `reviewer-abbreviation-probe.py`, `reviewer-abbreviation-probe-result.json`, the empty stderr log, and `review-probe-ruling.md`. This is proof of an attempted forbidden boundary, not a claim that a real notification was sent.

Parse/preserve the actual CLI before applying legacy environment translation, with one coherent grammar for diagnostic detection and conflict rejection. Merely setting `allow_abbrev=False` after the existing argv replacement is insufficient: replacement can still swallow the original unparsed diagnostic arguments. Preserve the ordinary no-selector environment dispatch. Add the abbreviated/partial diagnostic plus post-existing-environment cases through actual `main(argv=None)` with refusing boundaries. Existing coverage at `test_strat_production_replay.py:284–292` exercises exact spellings only.

### R2 — P2 / Important: Preserve the unavailable ORB choice through actual formatting

**Introduced location:** `gcp/premarket_brief.py:1370–1373`; affected formatter at 3074 and 3111.

The diagnostic generator now deliberately emits `recommended_orb_window=None` because event inputs are unsupported. The real `_build_playbook_embed` immediately converts that value to `5m` and titles the payload `Strat Playbook — 5m ORB`. Actual diagnostic main executes this routed formatter, so a valid synthetic playbook gains a concrete recommendation that the generator expressly could not make. The unavailable reason in the description does not undo the contradictory recommendation in the title.

Carry the unsupported/unavailable state through the rendered payload while preserving established live behavior for genuine choices. Add an assertion on the actual routed embed, not only the raw dictionary. The new test at line128 checks raw `None`; the capacity spy only proves that formatting ran. This finding follows the new producer value into the existing formatter; it does not request a different ORB selection rule.

### R3 — P2 / Important: Refuse invalid daily market inputs before indicator/market summarization

**Location:** `lib/agents/summarizers.py:1953–1966`; affected raw-market branch at 240–247 and available result around 356.

Captured OHLCV deliberately admits null/invalid observations so the canonical STRAT producer can report them unavailable. The new `captured_market` adapter only tests whether the daily frame is empty, then computes indicators and forwards its final row. This bypasses the existing SQL producer's `close IS NOT NULL` predicate and adds no OHLC validity guard. For a newest completed daily row with `Close=None` (or incoherent high/low), the market summary still returns `available=True`; a null close becomes `close=None` with regime `ranging`, while rolling/EMA/RSI calculations can retain or synthesize numeric context. The canonical STRAT section independently identifies the invalid last row, but the market section is not marked failed and reaches the actual graph as usable market evidence.

Validate the observed daily row/history required by these indicators before invoking the market adapter, preserving explicit unavailable reasons and invalid positions rather than replacing the invalid last observation with an older apparently current row. Keep the existing financial formulas unchanged. Add an actual-main/context test with a valid prior history and a null/incoherent final completed daily row, asserting market unavailable and no fabricated neutral regime. Current negative controls cover empty daily data and invalid minutes, not this admitted invalid-daily path. This is a static producer-to-consumer proof; no additional application probe was run.

### R4 — P2 / Important: Count unexpected physical source reads in the capacity proof

**Location:** `tests/fixtures/strat_replay_capacity_runner.py:36–41` and assertions at 84–87.

The supposedly independent read counter wraps only `os.open` and records only the exact manifest path and the hard-coded sibling `source.jsonl`. It ignores `os.open` on any other file and all normal `builtins.open`/`io.open`/`Path.read_text` reads. A production regression that loads config or another data file through those paths leaves the accepted count at four. Comparing this partial counter with the adapter's hard-coded `source_reads=2` per main does not close the blind spot. The root ruling specifically requires actual opens/config/routes/context/provider work across both mains, and the spec's capacity check must reject extra uncounted source work.

Instrument all relevant physical-open mechanisms with a documented narrow runtime/import distinction, count or refuse unexpected data/config sources, and add a bounded sensitivity control showing that an injected extra source read is detected. Keep the original six-read/256MiB/timeout limits. The retained four expected opens are valid observations; this finding does not assert that the frozen code actually performed additional hidden reads. It identifies why the present acceptance test cannot establish the claimed complete read boundary.

### R5 — P2 / Important: Compare canonical identity and classification, not only eight selected fields

**Location:** `scripts/validation/validate_brief_accuracy.py:689–701`.

The new launcher reports top-level `matching=True` after comparing only observation time/price, minute context, two continuities, validity and two failed flags. It ignores `rule_version`, `available`/`reason`, coverage, `last_candle`, `in_force_combo`, `pattern_facts`, pending setup, and weighted-alignment version/contributions. Two serialized production outputs can disagree on the core candle/combo or drop a rule version while the validator exits zero. The spec expressly requires rejecting dropped rule/failure/coverage facts and disagreement at the same clock; excluding unsupported legacy structural-action geometry is a separate justified limitation, not a reason to omit canonical descriptive facts.

Define and compare the complete shared canonical envelope, with explicit normalization only for declared adapter presentation differences, required-field presence checks and matching symbol sets. Continue to avoid outcome scoring. Add negative comparator controls that alter/drop a classification, rule identity or coverage field in one actual output and demonstrate nonmatching/nonzero status. The new validator test asserts only a positive matching case.

### R6 — P2 / Important: Correct the indicator null/warm-up audit claim

**Location:** `docs/research/2026-10-23-strat-production-replay.md:30`.

The new MODEL-IND-001 audit says “warm-up NaN remains missing.” The source bound by its own hash does not support that general claim: `lib/indicators.py:37–51` replaces RSI NaN with 50, lines67–88 fill raw StochRSI NaN with 50 before smoothing, and ATR uses an EWM without a period-length warm-up gate. EMA/SMA/MACD do preserve their respective warm-up NaNs. These are meaningful differences in the very null semantics the Task6 source audit is required to record, and the registry itself flags RSI/ATR warm-up as unresolved.

Document the actual per-indicator behavior and distinguish executed positive arithmetic from unavailable/warm-up guarantees. Do not change preexisting financial formulas under this task. The indicator implementation is not an introduced defect; the new source-audit assertion is. No issue-state network lookup or model outcome execution is needed to correct it.

### R7 — P3 / Minor: Name the actual live exit consumer in the source audit

**Location:** `docs/research/2026-10-23-strat-production-replay.md:34`.

The new MODEL-EXIT-001 row identifies `signal_monitor._check_position_exits`, which does not exist in the frozen source. The audited target/time/RSI/fixed-horizon branches are in `SignalMonitor._check_exits` at `gcp/signal_monitor.py:2076`. Correct the function pointer so the claimed source audit is reproducible. The substantive description of those branches is supported; this is a minor evidence-navigation defect, not a request to rewrite exit policy.

## Scope, lineage and retained evidence

Read the complete eleven changed source/test/research files and complete baseline diff, not only the patch hunks. Read the binding task brief, review brief, actual plan, root ruling, 447-line replacement spec and published execution-plan requirements, applicable repository/SDD/task-review instructions, and implementation report. Traced the modified mains, loader, captured source, graph/provider and summarizer paths, real render/formatting boundaries, shared `compute_strat_status`, structural serialization and indicators. Checked the actual relevant algorithm definitions for all nineteen deterministic/heuristic registry rows; no issue prose or old predictive claim was substituted for current execution evidence. Broader unchanged financial defects were not raised as introduced findings.

Independent read-only byte verification is retained in `reviewer-source-verification.json`:

- All eleven live files equal their frozen fullfiles and manifest identities.
- Reconstructing unified diffs from retained baselines yields the complete submitted diff byte-for-byte: SHA256 `47a95a188b141bf7e1e5e80803f26cd92827f0fcdc4c4d335d2ecd27eeba2354`.
- All 675 prechange source/config/instruction identities were checked: exactly seven existing owned files changed; no outside-owned change. The original parity-test prefix is byte-exact.
- All 1,365 retained predecessor artifacts and 350 safe-allowlist entries match. All enumerated model-source hashes and the actual registry `docs/product/07-MODEL-REGISTRY.md` hash match; the nineteen-row enumeration is complete.
- Structured retained test receipts match their logs and before/after source hashes. The early compact interface RED receipt has a different schema and no output digest/before-after fields; it is not represented as a final-revision sensitive test.

The final affected selection is **117 passed in 0.61s**, on the final production/test bytes (the research file was not yet present during that selection). Final maximum capacity is **1 passed in 38.98s** on all eleven frozen files. Its recorded whole child wall is 38.700387883s, inside-process wall 38.591844118s, process CPU 38.999746344s, and lifetime peak RSS 131,332KiB (128.25390625MiB). The outer test wrapper separately records 39.590052735s wall and 40.385949s child CPU; these scopes are not interchangeable.

The capacity fixture admits 12 symbols × 2 sessions × 390 RTH rows = 9,360, plus 4,800 daily and 2,880 context rows: 17,040 rows per main. The two mains each report those same raw admitted counts and identical source hashes (content `103c374721d93eff8f96d1e00d88c1c78b712310a98f8ee22c64bbec10d5cbdb`, manifest `e72d69c4d79f3ca0aeda6bfb857977dcfe122d15fa664335b167b168d43d8b19`, content size 2,710,430 bytes). The retained process executes 168 graph nodes, both actual producers, aggregations, indicators, summaries, planner and formatting, with zero counted external attempts. R4 qualifies the completeness of the file-read measurement, not these positive producer/counter observations.

Four recorded reads × assumed 2s plus measured CPU = 46.999746344s, below the most conservative recorded quarter-timeout of 150s; peak RSS is below 256MiB. These are synthetic local measurements and an I/O estimate, not cloud RTT/provider latency. Source deploy hash `ff289ae505ae8f700c722e8c92ef104b5f83d62b15e9680691691684b9b18c6b` records brief create/update 1800s and insight create 1800s (quarters 450s), earnings 600s (quarter150s); insight's updated deployed timeout remains unknown. No timeout or workload budget was increased.

Earlier controls remain attached to their actual revisions: initial two interface failures; subsequent fixture/schema failures and fixes; both-main positive pass; sensitivity run 24 passes/5 failures followed by the five corrected cases plus three added cases passing; eight session-boundary passes; genuine per-symbol 401-row preflight RED/GREEN; immutable-clock control; first capacity pass; final affected and final capacity selections. There is no claim that one final complete suite was run, and the reviewer did not rerun any accepted suite. Positive controls and future-minute/completed-minute mutations are meaningful retained evidence. They do not cover R1–R5's demonstrated blind spots.

Root separately reports the final 354-member/298,612-byte archive SHA256 `92eed9c5ac74f4ce332b832b6836562e286eae249feae7d8092119d20db0502e`, all eleven remote parts verified, combined restoration of all 69 source paths from eight verified archives, and the controller 10-member/6,280-byte checkpoint SHA256 `d7cb243f5269bf6fe61f8d808736fdfd3627f5fed234958da2bedeae56849c72`. These are controller-retained backup claims, not downloads/restorations repeated by this reviewer. Public docs commit `0925f5e3`/PR1573 is likewise controller-reported byte-exact publication with pending review explicit; it does not constitute acceptance.

## Limits and disposition

This review performed static reads/hashes plus exactly the one bounded authorized abbreviation probe. It made no source changes, Git operations, test-suite runs, SQL/application data queries, real provider/network/cloud/Docker operations, market/raw/holdout reads or notifications. Review artifacts are the only files written. The probe's sole application boundary replacement was the authorized recording render sentinel, with network/HTTP/psycopg2 refusals installed before main.

The shared source adapter, cutoff-before-producer design, actual typed graph execution, explicit synthetic qualification, unsupported-domain refusals and retained source/test lineage are useful foundations. Acceptance still requires repairing the complete finding batch and providing covering sensitive evidence under the root's bounded execution rulings. Existing upstream blockers remain open without waiver. This report supplies one complete first batch; any subsequent review should be scoped to these findings and new fix-diff breakage within the existing five-round cap. Reviewer STOPPED.
