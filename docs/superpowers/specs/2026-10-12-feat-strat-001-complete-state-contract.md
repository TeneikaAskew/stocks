---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001, REQ-REPLAY-001, REQ-REPLAY-002, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002, REQ-PERF-002]
issues: [884, 866, 907, 908]
site_source_notes: [DASHBOARD-01, INSIGHTS-08]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "The Strat truth-table suite covers every documented candle, combo, compression, failure flag and pattern collision, and passes against the production classifiers"
  - "Live and replay snapshots exclude unfinished or invalid OHLC and retain IWM October 8 failed-2D independently of its continuation combo"
  - "Strict timeframe continuity and weighted candle alignment have separate versioned fields with per-timeframe availability and contribution, and no consumer labels a weighted majority as full continuity"
  - "The structural-level suite covers D/W/M/Q/Y boundaries, holiday and DST sessions, custom multi-day periods, PMG forms and gap-crossed trigger state without future bars"
  - "A checked-in October 8-9 replay artifact demonstrates snapshot parity across brief, earnings and insight consumers, with observed state changes timestamped rather than inferred from later closes"
  - "The affected model records, FEAT-STRAT-001 capability record and PR traceability are updated, and focused tests, docs audit and spec gate pass"
status: approved
supersedes: null
---

# Complete and consistent Strat state contract

## Problem and intended outcome

The owner explicitly requests the complete Strat engine as a first-class part of the
earnings repair. Success means accurate, consistent price-action interpretation, not
dollar returns. The captured baseline and evaluation protocol are recorded in
[issue #1563](https://github.com/TeneikaAskew/stocks/issues/1563).

The capability row is: **FEAT-STRAT-001 — STRAT / levels — Candle classification,
FTFC, structural levels — `lib/strat.py`, `lib/strat_levels.py`,
`lib/exec_backtest/ftfc.py`**. Relevant existing issues are #884 (continuity semantics),
#866/#907 (historical-level anchoring) and #908 (gap repricing). Do not close an issue
merely because its file was edited: its own acceptance criteria must pass.

Observed defects:

- All six ETF AI snapshots for October 8-9 say inside/none, contrary to the original
  daily 2D reversal/continuation brief. A null daily placeholder reproduces this.
- Production `detect_combos` assigns 212/312 directional reversals to some type-3
  outside bars. The documented 3-2 definition also differs from the code's extra
  prior-candle-color condition.
- IWM's failed 2D on October 8 is hidden by combo priority.
- `calculate_ftfc` is a normalized weighted candle vote. The daily/weekly/monthly
  caller gives monthly zero default weight. Strict continuity is not exposed.
- An execution-research FTFC implementation duplicates candle math and uses a
  different timeframe/weight configuration. Research artifacts must retain their
  historical semantics; they cannot be silently reinterpreted.

## Approaches considered

1. Patch individual consumers. Small diffs, but preserves contradictory state.
2. **Recommended: one versioned shared snapshot contract and explicit legacy
   compatibility.** Fix the documented truth table and invalid-data handling; expose
   strict continuity separately from weighted alignment; migrate consumers explicitly.
3. Replace all strategies and retrain every model. Much larger scope and would obscure
   whether the deterministic defects were actually repaired.

## Design

### 1. One observation clock and valid-bar policy

`lib/strat.py` owns the pure classification/snapshot semantics. A snapshot carries
symbol, decision timestamp, session, raw/adjusted policy, source timestamps, rule
version and timeframe coverage. Live callers resolve an explicit Eastern observation
clock; the absence of a replay override must not authorize unfinished daily rows.

Completed daily classification requires finite OHLC, high >= low, and coherent OHLC
ordering. A placeholder is unavailable, never an inside candle. Invalid observations
must not be removed in a way that falsely makes nonadjacent intraday bars consecutive.
Return reason codes and gaps; valid first observations remain unknown rather than 1.
Keep partial higher-period state explicitly marked as partial/observable.

Daily analytics adopt approved `2026-10-12-feat-data-001-av-market-data.md`:
coherent split-and-dividend adjusted daily OHLC/returns/ATR/Strat through the actual
merged `lib.price_basis.prepare_daily_basis`, version `av-adjusted-daily-v1` and its
artifact/clock/factor admission. Never mix raw OHL and adjusted Close. Restore all
price-dimensional levels/ATR into target-session raw execution units through merged
`restore_daily_units`; raw minute quotes/opening gaps remain separately named raw
observations. Split-only share/volume conversion is not a new price-analytics policy.
Missing/future/mismatched factor or vintage evidence is unavailable; no factor1 or
current retrieval fabricates earlier knowledge. Production adoption waits for the
real merged DATA helper; no copied unmerged helper or independent adjustment math.

Clocked production consumers adopt actual shared `session_schedule`/session helpers
from approved `2026-10-19-feat-data-001-shared-market-calendar.md` after that CODE
implementation lands. Its fail-closed guard/parity covers holidays, DST, half-days
and delayed opens. Do not add another calendar/cache primitive. Isolated coherent-
input math/tests may proceed dependency-blocked; production integration/validation
cannot claim calendar/basis completion before actual merged prerequisites.

### 2. Full pattern coverage with orthogonal facts

Maintain a human-reviewable truth table and parameterized fixtures covering 1/2U/2D/3,
inclusive boundaries, dojis, 22 reversal/continuation, 212 reversal/continuation, 312,
132, 322, 32, 11/111 compression, failed/clean 2U/2D, and the shipped 131 pending
setup. Directional combos must actually terminate in their specified 2U/2D class.
Document the existing 131 addition and settle the 32 color mismatch by following the
source-of-truth `STRAT_METHODOLOGY.md` contract. Update misleading source comments.

Expose independent `failed_2u`, `failed_2d`, candle color, close location, compression
count, pending setup, all applicable pattern facts and the selected priority combo.
No lower-priority flag disappears because a higher-priority label won.

### 3. FTFC semantics and migration

Publish distinct results:

- `weighted_candle_alignment`: the existing candle-type vote, with actual configured
  weights, used denominator and contributing/zero-weight/missing frames.
- `timeframe_continuity`: strict directional agreement across the explicitly requested
  frames, using the same observed price relative to each current period open. Per-frame
  above/below/at-open and data age are inspectable. Missing required frames make full
  continuity unavailable; a partial subset cannot claim full agreement.
- `directional_candle_continuity`: strict agreement of directional candle classes,
  when a consumer needs that structural fact instead of price/open continuity.

Legacy `ftfc_score` consumers retain their numeric behavior under an explicit legacy
version during migration; the display explains weighted alignment. Do not silently
change score thresholds, training features or existing research artifacts. Any caller
that moves to strict continuity declares the new rule/version and replays before
promotion. This resolves #884 through separate semantics, not by declaring a majority
vote accurate continuity.

Daily/weekly/monthly/quarterly/yearly and configured intraday frames share exchange
session aggregation. Required frames and weights are configuration, not inferred from
available data. Confirm exact equal-open and mixed/unknown cases in the truth table.

### 4. Structural levels and activation

Reuse `lib/strat_levels.py` for previous/current D/W/M/Q/Y levels, historical closes,
opens, gap boundaries, premarket extremes, ORB and custom multi-day aggregates. Verify
the supplied observation clock rather than positional assumptions. All forward-looking
levels use only observations available then. Expose level provenance and period state.

Keep spatial level clusters and temporal PMG patterns separately named. Audit both
against their documented definitions and add explicit fixtures; do not present an
arbitrary cluster as a different temporal pattern. Do not add an unreviewed PMG definition.

Represent triggers as fresh, already-crossed-at-open, activated, held, failed or
invalidated, with observation timestamps. Return meaningful distinct targets and
unsupported/insufficient-room reasons. A 09:30 gap-crossed target is not a newly
predicted intraday move. Typed invalidation includes level, side, timeframe and
touch/hold/bar-close confirmation rule.

### 5. Consumer parity and replay

The existing briefing, insight summarizer, Strat history tooling and API readers,
and earnings snapshot paths use the same production functions with an explicit clock.
This includes the persisted daily producers
`gcp/fetchers/fetch_market_data.py` and
`gcp/fetchers/backfill_daily_indicators.py`, on-demand replay writer
`gcp/backfill_ticker.py`, and the
`platform/api/routers/dashboard.py` reader of their stored Strat fields. Persist
rule/alignment versions and independent pattern facts with new writes, expose them
through the actual dashboard API response, and identify old unversioned records as
legacy/unverified rather than retrospectively assigning the repaired version. A
three-consumer fixture that omits these writers/readers does not meet parity. Maintain October 8-9
fixtures for IWM/SPY/QQQ and adversarial calendar/boundary fixtures. Include 08:30,
opening, meaningful break and closing checkpoints; prohibit future-minute highs and
later daily closes from entering earlier snapshots.

Decision evidence must execute the actual production replay orchestration through
`BRIEF_AS_OF` in `gcp/premarket_brief.py` and, for insight-consumer proof, the
`INSIGHT_AS_OF` production pipeline with deterministic/mocked-provider output where
needed. Add precise observation-clock, captured-input and no-write modes to those
production entrypoints first. `--no-discord` alone is insufficient: the current brief
still writes SQL. Acceptance must prove that dry-run refuses all persistence and
notification calls, enforces cutoff before source selection/aggregation, and runs the
same production producers/adapters. Extend `scripts/validation/validate_brief_accuracy.py`
only as a launcher/comparator of those production outputs, not as an alternate engine.
Reports distinguish observed/reconstructed inputs from contemporaneously acquired
inputs and never relabel a retrospective replay as live.

The October captures are immutable regression inputs. Under REQ-VALID-001, arithmetic,
code-correctness and reconstructed diagnostics are separate from admissible system or
model validation: repair actual upstream input-semantics/replay blockers and regenerate
the affected derived dataset before claiming a qualified baseline, validation result
or promotion. Missing historical vintage evidence remains explicit; a later source
retrieval cannot certify an earlier publication.

### 6. Model evaluation and capacity

The deterministic/heuristic model inventory is audited for coverage, shared producer,
units, null behavior, horizon, time safety and consumer parity. Pure arithmetic
correctness and historical predictive evidence are separate verdicts. Gamma/options,
momentum/reversion and research consumers must not silently receive changed meanings.
Record their compatibility findings without claiming all models have proven an edge.

Replay capacity envelope: 12 case symbols × 2 sessions × 390 minute bars = 9,360 rows,
plus at most 400 daily bars each = 4,800 rows. At ~250 bytes/source row the core frame
budget is ~3.6 MB before pandas overhead; use a 256 MB bounded replay budget and
fail explicitly on oversized requests. Batch sources by symbol/date; at most six
read round-trips for the frozen replay, rather than one per minute/frame. At 2 seconds
per round-trip, estimated I/O is <=12 seconds plus CPU; measure actual CPU/wall-clock
before claiming deployability. Compare with the pre-change configured task timeout;
if estimated completion exceeds one quarter of that timeout, revise architecture or
reduce the admitted bounded workload, rather than raise the timeout. Apply
REQ-CAP-001/002 to changed existing scheduled paths. Shared snapshot math adds no
per-row remote calls.
Existing jobs only; no new schedule or recurring infrastructure charge is introduced.

### Storage and live-version compatibility

Deliver an idempotent additive migration for versioned state/facts covering market-
data writers, premarket_analysis and premarket_analysis_history. Schema lands before
new writers/readers. Old app revisions keep reading legacy fields; a new writer on
old schema refuses required-column preflight, and a new reader returns explicit
migration-unavailable/legacy state rather than querying absent fields. Never allow
upsert_dataframe to drop required unknown columns and report success. Real PostgreSQL
checks cover migration twice, rolling old/new revision compatibility and rollback.

Keep canonical v2 state in separate versioned storage from legacy candle/combo/FTFC
training features. Storage keys/lineage distinguish symbol/session/observation,
source revision, rule/configuration, basis, artifact and code identities; no ambiguous
latest record may merge v2 facts with a legacy alignment. Full scheduled backfill and on-demand replay cannot overwrite
protected legacy rows. Test complete full-mode runs, protected-column equality and
idempotent separate v2 output. The persisted research builder also selects an explicit
legacy feature rule or refuses an unversioned rebuild; no default-classifier repair
may silently relabel its training output. The actual signal-monitor classifier/bonus
path stays explicitly legacy unless a separately declared migration is selected and
replayed; an informational v2 tag alone does not preserve its arithmetic. Missing
legacy inputs cannot silently recompute under v2. No threshold tuning, live setting
promotion, alert quota or direction-gate change is implied.

## Executable acceptance mapping

The implementation must add/extend the named checks below; a listed future test is
an acceptance requirement, not evidence it already exists. Each runs production code
and must fail on the specified broken behavior. Keep the done_when contract above.

| done_when (1-based) | Required command/check | Broken behavior the check must reject |
|---|---|---|
| 1 | `python -m pytest tests/lib/test_strat.py tests/lib/test_strat_history.py -q`, including `TestInvalidObservations`, `TestPatternTruthTable`, `TestFailedTwoPriority` | Invalid/missing OHLC becomes inside; type-3 terminal receives 212/312; documented32 is color-filtered; priority erases failure facts; unknown labels become false facts. |
| 2 | `python -m pytest tests/lib/test_strat.py::TestComputeStratStatusAsOf tests/lib/test_strat.py::TestFailedTwoPriority -q` | Live None reads unfinished daily data, differs from the same frozen replay clock, or loses actual IWM October8 failed-2D. |
| 3 | Add `tests/lib/test_strat.py::TestContinuityContracts`; run it with `python -m pytest tests/lib/test_strat.py::TestContinuityContracts -q` | Missing/equal-open/opposing required frames pass strict agreement, monthly zero weight becomes agreement, or legacy weighted values/versions/contributions drift silently. |
| 4 | Add `tests/lib/test_strat_levels.py::TestStructuralStateContract`; run all existing level/playbook/freshness modules | Wrong D/W/M/Q/Y/calendar/custom-period levels, incomplete prior-year coverage called complete, conflated PMG definitions, duplicate targets or gap-crossed/touch-only evidence becomes fresh/close-confirmed activation. |
| 5 | Add `tests/gcp/test_strat_snapshot_parity.py`; run it with the actual dashboard API tests and production captured-input replay under BRIEF_AS_OF/INSIGHT_AS_OF | Any brief/earnings/insight, fetch-market-data, backfill writer or dashboard response drops rule version/failure/coverage facts or disagrees at the same clock; old records are falsely stamped v2; later data enter an earlier checkpoint; dry-run writes/posts. |
| 6 | Run affected focused suites, registry exporter, branch/main docs audits and `python scripts/gate/spec_gate.py --pr origin/main`; check named evidence for every preceding row | Delivery records or generated registry omit changed models, source identity is invalid, or an earlier behavioral row has no passing sensitive check. |

Record production-entrypoint revision, exact invocations, input hashes, per-case
verdicts, missingness, current-vintage limitations and before/after changed-label
populations in the checked-in replay artifact. The broader October1–9/10–16 corpus
from issue1563 is partitioned into the same admitted batches, with no holdout outcome
scoring before repaired revision/settings freeze. This does not enlarge a batch cap.

## Sensitive acceptance cases (mandatory additions)

- `tests/lib/test_strat_history.py::TestHistoryObservationContract` (new) invokes
  actual compute_strat_history with aware as_of, an invalid middle observation and
  a later post-cutoff row. History tooling propagates the cutoff, retains invalid
  positions and cannot bridge a pattern/trigger across them. Add
  `tests/scripts/test_strat_history_contract.py::test_actual_report_and_backtest_propagate_clock_basis_and_rule_version`
  through actual report/backtest CLI/shared-helper paths. Clock/basis admission
  precedes loading/resampling; persisted comparisons require matching input/rule/
  basis identity or explicitly report incomparable, never v2-v1 label accuracy.
- `tests/lib/test_exec_ftfc_contract.py::TestLegacyFtfcGolden` (new) runs actual
  build_ftfc_lookup/ftfc_score_at/batched scoring on fixed pre-change expected values:
  configured frames/aliases, bucket/completion shift, weights, NaN/missing denominator
  and between-bar lookup. Expected values are frozen literals, not mirrored code.
  Actual persisted research-builder tests include valid 32-color/outside212/312 cases
  whose canonical/legacy labels differ, proving an explicit feature version pin or
  refusal of unversioned rebuilding, not just unchanged simple directional counts.
- `tests/gcp/test_strat_snapshot_parity.py::TestPersistedWriterContract` invokes all
  three named writers, including backfill_ticker, and actual dashboard readback.
  Reject unversioned independent weekly/weight math, combo/strat_combo mismatch
  and dropped facts. Different explicitly preserved legacy weight configurations
  need not yield equal numeric scores; compare each declared weights/denominator
  and expected per-configuration result under matching clock/basis/input identity.
- `tests/integration/test_strat_schema_compatibility.py` (new, no-skip PG) applies
  actual migration twice and invokes actual upsert_dataframe/writers/dashboard on
  old/new schema and app combinations, including mirrored brief-history schema.
  Required-column absence fails before partial publication; no warning-only success.
  Include stale per-process reflected schema after DDL, required refresh/restart
  behavior, old writers retaining v2 sidecar values and history-mirror readback.
- `tests/gcp/test_strat_snapshot_parity.py::test_full_backfill_preserves_legacy`
  executes actual full-mode backfill on seeded legacy labels. Protected columns
  remain identical, separate v2 state is correct and retries are idempotent.
- `tests/gcp/test_signal_monitor_strat_compatibility.py` (new) exercises actual
  monitor-to-classifier/bonus strength/fire-selection behavior under explicit legacy
  and explicitly migrated v2. Prove legacy numerical stability, unsupported-input
  refusal of unadmitted version/basis migration, version selection and no implicit
  live promotion. Existing legacy missing-FTFC fallback/threshold behavior stays
  golden; this test does not introduce a new financial monitor rule.
- `tests/lib/test_strat.py::TestCorporateActionBasis` (new) plus structural/actual
  adapter tests use the real merged DATA helper on split/reverse-split/dividend,
  missing-factor and future-vintage fixtures. Assert coherent adjusted facts,
  restored raw levels/ATR and mixed-basis refusal. Run merged calendar guard/parity
  and consumer checks, including delayed opens; dependency absence is blocked
  integration, not a passing mock substitute for this acceptance.

## Risks

Fixing pattern truth tables changes some historical labels. Version the rule and report
the before/after population; do not rewrite training data or automatically promote a
model trained against the old labels. Explicit legacy alignment avoids an unmeasured
strategy-threshold migration. Sparse symbols, corporate actions, live partial periods,
DST, holidays and equal-price boundaries require dedicated acceptance fixtures.

## Scope boundary

This spec repairs shared Strat facts and their consumer contract. It does not redesign
options payoff calculations or dollar-return objectives. Live signal caps and direction
gate enforcement have separate ownership under FEAT-SIGNAL-001; audit their compatibility
and avoid implying that changes to this library alone repair those live controls.
The earnings integration is the separate FEAT-CATALYST-001 spec below. Each capability
lands in its own non-stacked PR after the approved spec is merged.
