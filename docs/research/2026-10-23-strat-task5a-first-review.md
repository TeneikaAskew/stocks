# Task5A first complete independent review

**Disposition: NEEDS_CHANGES. Spec compliance: FAIL for the bounded Task5A contract. Code quality/correctness: FAIL pending the four findings below.** There are **4 introduced or worsened defect classes: 3 P1/Important and 1 P2/Important; 0 Critical**. This is one complete first-review batch, not an approval inherited from an earlier implementation or a partial list held open for later findings. The task's Important/Critical completion gate applies independently of the PR two-round/P1 review cap.

Reviewer: independent agent `/root/review_rebuilt_strat5a`, 2026-10-23. Review target: the newly reconstructed, detached `/workspace/stocks-strat-rebuild` candidate on accepted local base `a5749d4c`. No candidate files were edited. No Git mutation, application entrypoint, suite rerun, network, database, vendor/capture/holdout read, notification or nested agent was used. Root retains fix dispatch, publication and all later-task authority.

## Identity and review basis

Frozen manifest SHA256: `7180cd41670b5ddb84d1fc863ddbe6dd609ad7c142e742aea1eef87025961368`.

Independent verification, repeated at review completion, matched all 26 live files to their frozen bytes and manifest, all 25 existing baseline files, all 234 preserved prior artifacts, all 15 accepted Task4 fix2 frozen files, and the 13 accepted live paths outside the two authorized evolving files. Reconstructed baseline-to-live diff exactly matches `baseline-to-candidate.diff`. The pre-self-review tree also matches its manifest. Reproducible read-only checker and result: `reviewer-identity-check.py`, `reviewer-identity-check.json`.

Key reviewed identities:

| Path | SHA256 |
|---|---|
| `lib/strat.py` | `2a2ea4a72ebdb1789f84885c5c7007e1d66ec01795bf0bf7f57e26f4483f3878` |
| `lib/data_loader.py` | `71d417a30e74c292118809865942846fb8f8e05e1a739525c99a5002219e85e0` |
| `gcp/premarket_brief.py` | `a1b50785f349592fae577b2ea8c9fc2b2d9a6aad2a7da96dff18e3968e8beb62` |
| accepted unchanged `lib/strat_levels.py` | `fff237a96f75a3570bb1cc832ff8b136fbe9fe4b7f0bc766031b13087d5ea6d8` |
| accepted unchanged level tests | `81ac17b3e12262f656b3377649cfa9bc562fe74b673f8bf915404e80071caf98` |

Binding basis was `brief.md` first, the approved `strat-approved-spec.md`, actual 15-concern `spec-round2-reconciliation.md`, repository AGENTS/CLAUDE review requirements and applicable product-delivery, subagent-driven-development/task-reviewer and TDD instructions. I also inspected preparation/plan partition, report, complete baseline diff, AST inventory, preservation manifests, command log, Tasks2–3 accepted contracts and Task4 fix2 disposition. Reports, source comments and archival backups were evidence, not approval. Missing original Task5A producer/parity source and approval are not inherited by this reconstruction.

Full executable-file review, using raw source and AST-expanded source passes plus all changed raw diff text, covered all 13 changed files: loader, Strat producer, schema, summarizers, orchestrator, planner, prompts, premarket brief, descriptive earnings brief, explanations, new parity module, and both changed existing test modules. This was not a changed-lines-only review. Direct callers/callees inspected included observed aggregation and its adjacency/coverage metadata, validation and continuity helpers, accepted intraday-level admission, summary/level/mother-bar flow, context-bundle and planner construction, conviction/key-level/schema conversion, embedding query and ranker boundary, brief render/explanation/playbook/persistence consumers, and earnings context/batch/main call shapes. No unrelated implementation changes are requested.

## Findings

### R1 — P1 / Important: minute merging clears predecessor coverage and adjacency barriers

**Location:** `lib/strat.py:927–928`, especially assignment to `gap_before_by_timestamp` after current-minute insertion. Relevant retained contract: `lib/data_loader.py:1064–1072` requires adjacent expected labels and complete coverage on *both* compared periods.

The new merge sets the current label's gap flag solely from the current coverage record. It does not preserve/recompute the predecessor's incomplete coverage or exchange-session adjacency. A complete current three-minute sample can therefore turn an invalid comparison into a directional candle. This affects the new current-period `directional_candle_continuity`, not the intentionally retained last-completed-day top-level candle or legacy vote.

**Demonstrated on actual functions:** `reviewer-probe.py` passes an aware October 9 09:33 clock, declared same-unit source metadata and supplied session evidence, with only bounded synthetic frames:

- Historical daily observations on October 6 and 7, absent October 8, followed by valid October 9 09:30–09:32 minutes yield current daily `label=2U`, no reasons and `coverage_complete=true`. The current day is compared across the missing prior session. The requested weekly frame remains unavailable, so this particular case does **not** claim aggregate full continuity.
- A prior week represented only by October 2, complete October 5–8 observations, and the same current Friday minutes yield both daily and weekly `2U` and **`directional_candle_continuity.available=true`, `full_continuity=true`**, despite the incomplete prior week.
- Negative control with malformed prior-session OHLC remains `X`/unavailable. The historical invalid-OHLC self-review correction is working; it does not cover missing predecessor sessions or incomplete predecessor periods. This finding does not reopen the already-correct invalid-constituent case.

**Contract/impact:** binding global “gaps cannot create false adjacent patterns,” strict required-frame agreement, and the already accepted Tasks2–3 both-sides comparison contract. The observed full agreement is false even under isolated coherent input; production dependency blocking does not make that local fact correct.

**Required correction:** preserve or recompute adjacency and both participating periods' coverage when adding/updating the current period. Add bounded sensitive cases for an absent previous session, incomplete previous period and valid adjacent control; retain the passing invalid-OHLC behavior. Do not relax current coverage, retune weights or alter legacy scores.

### R2 — P1 / Important: minute prices and coverage use different admitted observations

**Location:** `lib/data_loader.py:1156–1174` and returned `regular_frame` at 1195–1197; downstream use in `lib/strat.py:894–910`. Coverage comes from `aggregate_to_timeframe`, which filters to its minute grid and normalizes numeric columns (`data_loader.py:925–926,941–943`), while extrema, quotes and the returned frame use the unfiltered/unconverted `regular` frame.

**Demonstrated on actual functions:** the two retained probe files show independent manifestations of this single admission/normalization defect class:

- Add a 09:31:30 observation with high 999 and low 1 to otherwise complete 09:30/31/32 bars. The aggregate reports three observed/three expected minutes and complete regular coverage, but `regular.high=999`; the actual shared snapshot emits an available current daily candle `3` with complete coverage. The accepted extended-level helper independently reports `off_grid_observations`. Thus the snapshot consumes an observation excluded from its own claimed coverage.
- Valid numeric-string OHLC with highs `"99"`, `"100"`, `"101"` passes `validate_ohlc_rows`, but raw string maximum produces `regular.high=99`, while the accepted numeric HOD is 101; coverage is still complete. The first probe's different string values did not expose this lexicographic error and is preserved unchanged; the second uses the sensitive values above.

**Contract/impact:** source admission must precede reductions and all current price/extrema/classification facts must share coherent admitted evidence. This is an actual false candle/extremum, not a hypothetical provider concern. It is also a code-quality defect from independently deriving prices and coverage from different representations.

**Required correction:** establish one validated, normalized, clock/session/grid-admitted minute representation and consistently derive regular quotes/extrema/current-period rows from it. Preserve explicit unavailable reasons where admission fails. Cover off-grid positions (including a latest off-grid quote), numeric strings and valid numeric controls through the real adapter and producer. No new calendar primitive or basis policy is needed.

### R3 — P1 / Important: the new unavailable status escapes existing brief consumer guards

**Introducing location:** `gcp/premarket_brief.py:1105–1113` changes missing/short input to `STRAT_UNAVAILABLE`. Direct consumers still recognize only the older status at `3252–3253`, `3379–3390`, and `2173–2185`.

Previously missing/short data produced `NO DATA`, which the existing persistence loop skipped. The new status correctly retains a shared unavailable snapshot in memory, but the same file's existing writer no longer skips that ticker: it constructs a row with null price/levels/score, `strat_candle='X'`, string `strat_combo='None'`, and no unavailable reason in history notes. It includes the row in canonical writes. With `allow_update=True`, that can overwrite an existing canonical row; without an existing row, the insert path also admits it. This consequence follows from the unchanged writer receiving the changed status.

**Demonstrated boundary, not a real write:** `reviewer-probe-2.py` invokes the actual `persist_to_cloud_sql` using an in-memory `gcp.database` stub. The captured call targets `premarket_analysis` with the null payload above. Log messages saying “Inserted”/“UPSERTED” are the production function's logging against that stub; **no database connection or write occurred**. Actual overwriting of a stored row was not executed and is the direct consequence of the captured upsert call and its keys, not an asserted integration test.

The same status omission in overview color is also reproduced: an all-unavailable brief produces bearish red `0xe74c3c` instead of excluding unavailable tickers as the old `NO DATA` path did. This is a secondary symptom of the same incomplete status propagation, not a fifth finding.

**Contract/scope:** S3 and Task5A require unavailable facts to survive the actual brief consumers without becoming normal market evidence. Full v2 persistence/migration/dashboard parity remains Task5B; preserving existing no-data guards for a newly introduced status is a Task5A regression fix and does not require implementing Task5B. Do not use deferred ownership to allow changed input to break an existing caller.

**Required correction:** propagate the new unavailable state through existing canonical-write and rendering guards, retaining the previous no-data protection. If retaining a history row, make its reason explicit under the existing contract; do not invent a schema migration in this fix. Add actual consumer boundary tests with mocked I/O and an unavailable-only color case.

### R4 — P2 / Important: declared extended-session latest quotes are truncated at the RTH close

**Location:** `lib/data_loader.py:1175–1179`, especially unconditional `declared.index < closing` after choosing `NYSE_extended` observations.

The adapter accepts a declared extended-session source and an aware observation clock, but discards every completed after-hours observation before selecting the top-level and extended latest quote. That silently substitutes an older RTH observation even though a newer valid quote was supplied. The regular frame is already separately bounded to RTH at 1156; the extra truncation affects the extended fact itself.

**Demonstrated:** `reviewer-probe.py` supplies the original RTH minutes plus a valid 16:29 bar closing at 121, with observation time 16:30. Both `latest_quote` and `extended.latest_quote` return the old 09:33 price 108 with age 25,020 seconds, instead of the supplied completed extended quote 121 with age zero. The fixture has sparse later RTH coverage, which is correctly allowed to remain incomplete; missing intervening RTH bars do not justify discarding a separately observed completed extended quote.

**Contract/impact:** binding Task5A requires preserving RTH versus extended quote/extrema and a single inspectable observed price/source age. This is a local descriptive fact defect within the supported declared source policy, even though production action is blocked. No after-hours trading, fill or signal policy is being requested.

**Required correction:** preserve regular-session limits for regular extrema/opens while retaining the latest admitted completed extended observation for the separately named extended quote. If an extended observation truly lacks required admission evidence, return an explicit unavailable reason rather than silently selecting a stale regular substitute. Add premarket, RTH, after-close and future-bar controls.

## Evidence assessment and checks that do not constitute additional findings

The preserved actual logs support the implementation chronology: initial 32 RED; focused fixes; 753 mock passes before self-review; three genuine self-review failures (summary rounding, unavailable legacy composition, historical invalid coverage); then four genuine adapter failures (stale snapshot retention, legacy earnings date override, future brief date guard, optional-level failure). The first adapter GREEN's remaining failure was a test wrapper-shape error, followed by four passes. The final source has a justified affected covering subset of **458 passes in 6.32 seconds, including 59 new parity cases**. I read the literal commands and failure/output logs, inspected the self-review source delta, and did not rerun suites. The 753 result is evidence for earlier bytes, not misrepresented as a final-byte full batch. Preserved final checks do not cover R1–R4.

The implementation does useful work: it resolves the snapshot clock before daily selection, carries orthogonal/unavailable facts into finite typed output, preserves a separate completed-daily legacy composition and summary rounding, and carries completed mother-bar levels into the actual planner. The changed thresholds/configurations and legacy ranker formulas are not retuned. The current-action capability explicitly reports absent genuine calendar/DATA/source qualification. The three legacy boundary cases and actual schema/summary/conviction/planner adapters were inspected, rather than accepting a metadata-only version assertion.

The missing-OHLC-column probe raises `ValueError` through the existing required-column validator. I do not count that as a new silently fabricated fact: the existing internal shape contract treats absent required columns as caller error. No fifth defect is inferred from that exception. Likewise, date-only descriptive earnings returns a missing-observation-clock reason; completing actual precise-clock entrypoint/replay orchestration remains later work, not an invented completed Task5A acceptance claim. Existing ranker nomenclature/legacy missing-score behavior and deferred research rebuild migration were not used to retune policy.

## Separately outstanding requirements and limits

1. **Task5A completion:** fix the four classes above and validate their bounded regressions against the frozen identity. Root owns any ensuing authorization and review disposition. This report does not start Task5B.
2. **Actual upstream integration remains BLOCKED:** real merged shared calendar and DATA adjusted-basis/restoration/source-vintage prerequisites are absent. Synthetic coherent-input correctness is not source qualification. Corporate-action factors, delayed-open/calendar parity, actual source point-in-time identity and production action capability remain unaccepted; no factor-1 assumption or copied unmerged helper is authorized.
3. **Task5B:** actual persisted producers, all named writers/backfill modes, migrations including stale reflected schema/history mirror, legacy protection and dashboard readback remain required. R3 is only preservation of existing consumers against the new status, not acceptance of those larger requirements.
4. **Task5C–5E:** actual history/CLI clock propagation, monitor version/fallback compatibility, remaining complete legacy numerical/research feature goldens, M1 envelope and resolver work remain open under their partitions.
5. **Task6 / full feature acceptance:** actual production no-write entrypoints and replay, refused persistence/notification calls, acquired-input identity and cutoff evidence, stated source-read/memory/batch limits, required calendar/DATA checks, docs/registry/spec gate and reviewable before/after label evidence remain required. No capture/holdout data were used or scored here, and none of these larger gates is represented by the synthetic parity module or this review.

## Reviewer command and reproduction provenance

Only two application-level reviewer probes ran, each justified by concrete unresolved changed-code risks and using actual functions with synthetic injected input. The exact immutable scripts and stdout/stderr are `reviewer-probe.py`, `reviewer-probe-output.txt`, `reviewer-probe-2.py`, and `reviewer-probe-2-output.txt`. Their hashes are in `reviewer-identity-check.json`. Both scripts explicitly set mock mode and blank SQL configuration, block data-loader acquisition and socket connection creation, and use no production entrypoint. The second replaces the database module with an in-memory capture stub before invoking the writer boundary.

Literal probe invocations, from `/workspace/stocks-strat-rebuild`:

```sh
source /workspace/stocks-setup/shell-env.sh
CLOUD_SQL_CONNECTION_NAME='' /workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5a-rebuild/reviewer-probe.py > /workspace/strat-rebuild-control/task5a-rebuild/reviewer-probe-output.txt 2>&1
```

```sh
source /workspace/stocks-setup/shell-env.sh
CLOUD_SQL_CONNECTION_NAME='' /workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5a-rebuild/reviewer-probe-2.py > /workspace/strat-rebuild-control/task5a-rebuild/reviewer-probe-2-output.txt 2>&1
```

Literal final read-only identity invocation:

```sh
source /workspace/stocks-setup/shell-env.sh
/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5a-rebuild/reviewer-identity-check.py > /workspace/strat-rebuild-control/task5a-rebuild/reviewer-identity-check.json
```

All other reviewer shell operations were read-only source/evidence inspection or output summarization, with the required shell environment sourced. Reviewer-created files are confined to this control directory; all implementation and preexisting evidence bytes remain unchanged.

## Durable original review evidence

The exact original report, two literal synthetic probe scripts/outputs, and identity-check script/result are in the [verified eight-member evidence archive](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371135847). Archive12,140bytes,SHA256`b00f11e9a46506fc669333e65ed493a7f0a18f03ac11b16dab95ea60950687b8`; original review SHA256`f7289de977b2c87910b9e41e6af634c7be1043abcafae32f1153fed9247d6812`. Remote bytes and every memberhash verified. Local relative artifact links above are shown as filenames in this publication; original link text/bytes remain intact inside the archive. No real DB or source/holdout capture was read or written by these probes.

All four findings are dispatched as one batch to the original implementer in existing Task5A fixround1/5. No severity/requirement waiver, Task5B start, merged-spec/production integration acceptance, deployment or scoring is implied.
