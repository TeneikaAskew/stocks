---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001]
issues: [884, 866, 907, 908]
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
dollar returns. The intake audit is
`docs/superpowers/audits/2026-10-12-earnings-strat-engine-intake.md`.

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

The existing briefing, insight summarizer, Strat history API and earnings snapshot
paths use the same production functions with an explicit clock. Maintain October 8-9
fixtures for IWM/SPY/QQQ and adversarial calendar/boundary fixtures. Include 08:30,
opening, meaningful break and closing checkpoints; prohibit future-minute highs and
later daily closes from entering earlier snapshots.

Extend existing replay/validation tooling where feasible, rather than maintaining
another permanent throwaway engine. Reports distinguish observed/reconstructed inputs
from contemporaneously acquired inputs and never relabel a retrospective replay as live.

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
before claiming deployability. Shared snapshot math adds no per-row remote calls.
Existing jobs only; no new schedule or recurring infrastructure charge is introduced.

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
