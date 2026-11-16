# Independent review — new Task4 reconstruction

**Spec compliance: Issues found in the bounded Task4 implementation.**
**Code quality: Needs fixes.** Five defect classes are listed below as one complete batch. These findings concern the new candidate, not historical-source recovery or inherited approval. All findings are P2 / Important at this task gate; no P0/P1 finding is asserted. Root owns disposition and fix dispatch. This is not a whole-feature acceptance or a merge review.

## Identity, scope and method

Reviewed `/workspace/stocks-strat-rebuild` against the supplied `baseline-to-candidate.diff`, both changed files in full, the approved specification, Task4 brief/report/preparation, applicable repository review instructions, published Task4/global constraints, methodology §§12–15 and the second-review reconciliation, including S4/S6/S7. The repository's full-file/direct-caller review rule overrides the generic SDD template's diff-only shortcut.

Independent byte checks matched all 15 live files to their frozen copies and manifest. The two new identities are:

- `lib/strat_levels.py`: `f72882e03817495ff154a5f883b397d7bdd19157550b39b9a66e5fde150af65c`
- `tests/lib/test_strat_levels.py`: `43b3e2dfd64139c24a115c87bb24828b87080bf6ade58c306e3bc1896fa85134`

The three existing level test files retain their complete baseline byte prefixes. An independent AST comparison confirms `LegStateTracker.update` and `.state` are unchanged. The supplied preservation record reports the previous 11-path checkpoint unchanged; the current 15-path live/frozen manifest comparison passed.

Immediate dependencies and callers checked for concrete contract risks:

- `lib/strat.py:61,76,152`: numerical OHLC validation and scalar range classification.
- `lib/data_loader.py:590,639,852,974,1027`: explicit aggregation version, one clock, completed source admission, partial higher-period coverage, session-label keys and adjacency records.
- `gcp/premarket_brief.py:1395,1426,1440`: existing dated legacy builder and separate legacy PMK append.
- `gcp/signal_monitor.py:513,580,643,693,935`: reanchoring, tracker construction, actual legacy update calls and dated legacy refresh.
- `gcp/premarket_playbook_resolver.py:110,158`: dated legacy reconstruction and extraction of trigger/target prices.
- `platform/api/routers/dashboard.py:470,512`: existing dated legacy level-map caller.
- `lib/agents/summarizers.py:439,478,499,517` and `lib/agents/trade_planner.py:885,901`: unchanged positional mother-bar route and actual planner consumption, to distinguish Task5A obligations from Task4 changes.
- Internal level/target helpers, map formatting and persistence were included in the full-file read. The production call-site search found no `observe_bar` consumer outside its definition; monitor consumers still invoke legacy `update`.

No tests, mutation checks or production functions were executed by this reviewer. No source, Git, network, cloud or capture operations occurred. Read-only hashes/AST comparisons were performed; only this requested review report was written. The sensitive cases below are **static branch traces, not claimed executed reproductions**. They give the implementer concrete inputs for RED tests.

## Strengths and verification evidence

The explicit strict clock refusal and labelled legacy compatibility are present (`lib/strat_levels.py:1600`). Exact prior-label selection, coverage checks and basis/unit refusal are implemented without adding an adjustment formula or replacement calendar (`:1730,1920`). Distinct-cent targets retain source metadata (`:1293`), canonical PMG/custom anchors remain explicitly unsupported (`:1973,2013`), and activation/invalidation are separated from executable fill claims (`:187`). Tracker history and per-frame caches are bounded (`:212,314`).

Read the actual RED/GREEN logs, command log, mutation script/results and mock rerun argv. The baseline RED contains 43 failures; later RED evidence identifies session/clipped-boundary admission, inappropriate executable eligibility and wrong-side targets. The initial fixture mistakes are retained and disclosed. The seven mutation controls replace actual production branches and call the production test assertions: same-frame clustering, duplicate-cent targets, stale trigger admission, premature close activation, gap-as-fresh, ignored aggregate clock and incomplete-period admission. All seven are recorded rejected. These are meaningful local sensitivities; they do not cover the counterexamples below.

Final recorded evidence is 169 passing plus 19 skipped cases in the three level suites, followed by all 19 skipped nodes passing under explicit `--mode=mock`, and 60 existing tracker/refresh cases passing: **248 distinct covering cases**. The 24 warnings are emitted at unchanged monitor lines 1594 and 907 (six UTC deprecations and eighteen fragmentation warnings). They are disclosed existing noise, not an introduced-code finding. The default-live invocation was a process error and is not accepted as live integration evidence. `tests/conftest.py:77,98,111,134,212` confirms the fixture routing and skip behavior; the quiet log does not prove a particular connection exception. The mock rerun is the positive fixture evidence.

## Findings — complete batch

### R1 — P2 / Important: Pre-activation evidence creates permanent ordering ambiguity

**Locations:** `lib/strat_levels.py:389`, `:439`, `:448`, `:456`; new tests `tests/lib/test_strat_levels.py:1317,1330,1341` do not cover these cases.

The ambiguity branches do not consistently respect when the configured activation becomes true. Once set, `_typed_ambiguous` is permanent and overrides the actual lifecycle state.

Sensitive case A, entirely on 1m bars: call trigger100, target102, stop98; both activation and invalidation require `bar_close`. Observe completed 09:30–09:31 OHLC `(99,103,97,99)`. The close did not activate or invalidate the leg. Line389 correctly selects `failed`, but line448 sees a trigger touch plus both extrema and overwrites the result with `ambiguous`. Then observe 09:31–09:32 `(99,101,99,100.5)`: activation is confirmed, yet line456 keeps the result `ambiguous` because excursions **before confirmation** permanently contaminated the leg. Expected: failed close attempt, then activated, with the earlier extrema retained only as descriptive facts; no post-activation stop/target-order uncertainty was established. Mirror for puts and hold confirmation.

Sensitive case B exposes the adjacent-interval instance at line439: call activation is 1m `hold` for120 seconds, invalidation is 5m `bar_close` below98. First observe completed 09:30–09:35 `(99,99,97,97.5)`; then completed 09:35–09:36 and09:36–09:37 `(100,101,100,100.5)`. The stop close is wholly prior to the holding interval. On activation, its endpoint09:35 equals `_typed_activation_interval[0]`, so `>=` marks unknown ordering. The exclusion only applies to touch activation. Expected `held`, not ambiguous, with no confirmed post-activation invalidation. This uses ordinary adjacent session bars, without any calendar or financial-policy choice.

**Required correction/sensitivity:** Scope ambiguity to evidence that can occur at/after the configured activation; treat wholly preceding intervals consistently across touch/hold/close. Preserve genuine overlapping touch-order ambiguity and same-bar opposing-close proof. Add both counterexamples and call/put mirrors, including prior evidence delivered before/after activation at equal knowledge time where admissible. Do not invent intrabar fills or simply clear valid ambiguity on later bars.

### R2 — P2 / Important: Late opening-gap evidence leaves the lifecycle dependent on frame delivery order

**Locations:** `lib/strat_levels.py:332`, `:378`, `:386`, `:393`. Tests `tests/lib/test_strat_levels.py:1306` cover only same-frame gap arrival with activation.

Use call trigger100/target102/stop98, 1m touch activation and 5m bar-close invalidation. Deliver these two compatible bars, both known at09:35:

| Frame / interval | OHLC | Session open |
|---|---|---|
| 1m09:31–09:32 | `(99,100.5,99,100.5)` | false |
| 5m09:30–09:35 | `(101,101.5,99,100.5)` | true |

Fine-first delivery sets state `activated`. The coarse opening observation subsequently sets `_typed_gap=True`, but the state assignment at line393 is guarded by `not self._typed_activated`, so the final state remains `activated`. Coarse-first delivery establishes the gap before the fine activation; line386 then chooses `already_crossed_at_open`. Both orders end with gap flag true, activation true, no invalidation, and identical evidence, but different lifecycle state. Equal `observed_at` is admitted by the method, and neither per-frame order rule rejects either order.

**Expected:** Both permutations represent the opening displacement as already crossed under the declared lifecycle, with executable credit still unavailable/ineligible. **Required correction/sensitivity:** Reconcile late opening evidence into the state without losing held/failed/invalidated/ambiguous precedence. Add both permutations and put mirrors; retain separate evidence and reconciliation timestamps rather than rewriting earlier knowledge.

### R3 — P2 / Important: A valid partial current day suppresses all observable gap history

**Locations:** `lib/strat_levels.py:1891`, especially `:1897` calling `_structural_period` with the default `current=False`, together with `:1782` and `:1910`; caller `:1996`.

The observed aggregator legitimately emits a current daily row from completed minute observations with `partial=True`, `coverage_complete=True`, and `completed=False` (`lib/data_loader.py:974,1034`). `_observed_gaps` nevertheless validates every tail row as a completed **prior** period. One normal current row adds `prior_period_not_completed` and causes the helper to return no gaps at all.

Sensitive fixture: complete regular-session minute history for March30 and31, plus complete observations through10:00 on April1. Aggregate daily OHLCs are respectively `(99,100,98,99)`, `(102,103,101,102)`, and current `(102,103,101.5,102)` in declared coherent units. The100–101 gap from March31 remains unfilled as of10:00. Actual branch result: `gaps=[]` with prior-period-not-completed coverage because April1 is partial. Expected: retain the observed March31 gap boundaries; the current valid partial row can establish whether an existing gap has filled without requiring its future closing bar. A companion fixture with current low99 must remove the filled gap.

**Required correction/sensitivity:** Distinguish completed historical gap origins from observable current-period fill evidence, retaining explicit coverage and cutoff refusal. Do not remove the current row and silently ignore an observed fill. Add a positive strict gap fixture, current partial unfilled/filled cases, invalid/missing current evidence and a future-row control through the real aggregator/builder. Current new tests use constant-price daily histories and make no assertion on a nonempty strict gap result, so the recorded GREEN does not exercise this path.

### R4 — P2 / Important: Rejected single-frame clusters consume members needed by a valid multi-frame cluster

**Locations:** `lib/strat_levels.py:1084,1089,1099,1101`; new criterion in the diff is at1101. New test at `tests/lib/test_strat_levels.py:1233` does not exercise a rejected leading group.

For levels `(100.00, day)`, `(100.14, day)`, `(100.20, week)` with the existing0.15% tolerance, the first anchor consumes the first two day levels and the new distinct-frame criterion rejects that group. The second day level is now skipped because it is already `used`; the week level is alone. Result: no zone. The100.14 day and100.20 week levels form a valid0.06% multi-frame cluster; removing the unrelated100.00 day level restores it.

This is the new acceptance criterion interacting with the existing greedy consumption, not a request to change the documented tolerance/strength formula. Under the repaired multi-frame contract, a rejected candidate group must not prevent a valid group from being considered.

**Required correction/sensitivity:** Consume members only when an eligible group is selected, or use an equivalent bounded selection that preserves valid candidates. Add the three-level fixture and an assertion naming the day/week source members; preserve same-frame rejection and the existing strength formula.

### R5 — P2 / Important: The public LevelMap drops the new trigger-absence reasons

**Locations:** `lib/strat_levels.py:1374` produces reasons, but strict assembly at `:1999,2005,2015` and legacy assembly at `:1646` discard them. Test `tests/lib/test_strat_levels.py:1258` checks only direct `identify_triggers` output.

A valid coherent observed map with current price100, period opens/closes100, and available highs120/lows80 has no eligible trigger under the unchanged freshness budget. `identify_triggers` correctly returns `no_fresh_trigger` for both sides. The public result contains two null triggers, an otherwise clean basis reason list, and leg reasons only `missing_activation_observations` / `missing_confirmation_rule`. No field retains `no_fresh_trigger`. Consumers cannot distinguish a missing viable hypothesis from a viable hypothesis awaiting activation evidence using the advertised reason contract.

**Required correction/sensitivity:** Preserve per-side selection reasons in additive LevelMap coverage/leg metadata, keeping hypothesis selection and activation-evidence reasons distinguishable. Cover the actual builder for stale-only candidates, no candidates and a valid candidate. This is local Task4 reason propagation, not the downstream typed activation-envelope serialization obligation M1.

## Explicit remaining obligations, not duplicate Task4 findings

- **Real source/calendar/basis integration remains blocked.** Supplied session and clipped-boundary declarations are low-level input contracts; they are not proof of the actual merged calendar guard or DATA `prepare_daily_basis` / `restore_daily_units`. `production_adapters_verified=False` and dependency blocks are truthful. Holiday/DST/half-day fixture math does not establish real calendar parity, delayed-open integration, factor/vintage admission or adjusted/raw conversion. No replacement calendar, factor1 or new financial convention is requested by these findings.
- **Owner definitions remain unresolved.** Canonical temporal PMG and custom2D/4D/5D/8D/10D/11D anchor definitions remain unavailable. Explicit unsupported results are appropriate and do not justify choosing new rules for GREEN tests.
- **Task5A/5E still owns actual consumer migration.** The legacy no-clock route, summarizer mother-bar/planner anchoring, actual live-None clock forwarding and unchanged legacy consumers are not declared repaired by this additive helper. S4/S7 acceptance must reach those real paths. The brief's old PMK append and resolver's historical credit behavior were inspected for ownership, not posted as newly introduced defects.
- **Task5E/M1 remains open.** Local `typed_state.activation` now contains normalized price/side/timeframe/confirmation/hold duration (`lib/strat_levels.py:203`) and invalidation carries the rule plus confirmed flag (`:209`). That improves the local interface; it does not prove full consumer envelope serialization, rule/evidence preservation, persistence or propagation. LevelMap currently exposes unavailable hypotheses when activation observations/rules are absent (`:2015`). Do not mark original M1 complete on these local assertions alone.
- **S6/#908 and qualification remain open.** Opening-gap state must reach actual resolver persistence with no unobserved fresh-entry/fill-dependent credit. No new executable fill, spread, latency or dollar-return model is authorized. Cross-consumer parity, real schema compatibility, source/PIT admission, no-write production replay, bounded production timing/memory/read measurements, dataset/model qualification and delivery gates remain later required work. The local fixed-frame math and bounded tracker do not certify the whole replay budget or deployment.

## Assessment

The reconstruction provides a substantive, inspectable strict interface and preserves the legacy tracker implementation, but the five local defects above prevent approval of this Task4 candidate. The recorded tests establish useful bounded behavior; they do not reject these concrete lifecycle, current-gap, cluster-selection and reason-propagation failures. Send the complete batch for sensitive RED reproductions and fixes, then review the scoped fix diff against this frozen identity. No source acceptance or Task5A start is granted by this report.
