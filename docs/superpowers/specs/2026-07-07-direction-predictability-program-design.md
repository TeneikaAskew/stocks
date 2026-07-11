# Direction Predictability Program — Design

**Date:** 2026-07-07
**Status:** spec (pending user review → writing-plans)
**Branch:** `feat/direction-predictability-program`

## Goal

From historical data, walking forward, determine whether we can predict the
**DIRECTION** of intraday moves for IWM / SPY / QQQ — and if so, in which
slices. Companion outcome: a clean, pure-prediction walk-forward baseline for
all three axes (**direction / size / type**), replacing ad-hoc single-split
measurements.

This is a **pure-prediction** investigation. Options pricing, implied-vs-realized
(gate-7), transaction costs, and tradeability are **explicitly out of scope** —
they are not evaluation criteria here. The only question is: does a model beat
the base rate out-of-sample, walking forward, robustly, across tickers?

## Success criteria (pre-registered — commit before running)

A direction slice is **PREDICTABLE** iff, on the purged + embargoed expanding
walk-forward:
1. It **beats the base-rate constant** (log-loss beat > 0) in **≥ 6 of 8 folds**, AND
2. It **replicates on all three tickers** (IWM, SPY, QQQ) — not one-of-three.

Accuracy/lift and calibration (ECE) are reported alongside but the log-loss-beat
gate is the necessary bar (matches the prior program's rigor). Anything clearing
the bar gets a fresh out-of-sample confirmation before being called real.

## Non-goals

- No options / implied-vol / gate-7 / cost / EV analysis (out of scope by user
  direction; those killed *tradeability*, not *predictability*).
- No new external data ingestion. Data boundary: existing DB tables **plus new
  features derived from the raw 1-min bars we already store**
  (`market_data_intraday`).
- No production deployment in this program — research + verdict only. Winners get
  a separate productionization spec.

## Known-dead (do not re-run as-is)

From `DIRECTION_RESEARCH_RESULTS.md` / `EXPERIMENT_REGISTRY.md`: close-sign
direction on 5-min tabular features (0/72 folds); news / cross-asset-as-daily /
vol-regime feature families (0/8); triple-barrier first-touch on the EXPLOSIVE
flag; daily dealer flow. The one unresolved flicker: long-only tilt on
EXPLOSIVE bars, IWM-only, non-replicating.

**Lesson carried in:** vary the *label* and the *information class*, not just the
feature list.

## Architecture

Four parts. Reuse existing research infrastructure; add net-new only where it
doesn't exist.

### Part 1 — Protocol (foundation, mostly REUSE)

Reuse the production purged + embargoed expanding walk-forward already built for
direction research (Rule 3.6 — do not hand-roll): candidate modules to reuse/
extend — `gcp/research/strat_engine/strat_dir_walk_forward.py`,
`strat_dir_walk_forward_extended.py`, `dir_regime_walk_forward.py`,
`breakout_meta_walk_forward.py`, `strat_dir_probes.py`. Shared substrate: IWM/
SPY/QQQ, 5m primary; 8 anchored expanding folds; LightGBM; `featurize()`.

**Net-new in Part 1:**
- **Slice ledger** — a persisted log (one row per (lever, target, conditioning,
  feature-set, ticker, fold-summary)) so every combination tested is recorded.
  Enables a multiple-comparisons correction (Benjamini-Hochberg / Bonferroni on
  the per-slice fold-beat p-values) at synthesis. Without it, testing many slices
  guarantees false "discoveries."
- **Pre-registered success bar** encoded as a gate function so pass/fail is
  mechanical, not eyeballed.

### Part 2 — 3-axis baseline (net-new orchestration over existing engines)

Run **direction / size / type** through the one harness, existing features only,
pure prediction:
- **direction** — reproduce the 0/72 close-sign control (harness trust check).
- **size** — magnitude buckets (existing `mag_walk_forward`), report lift.
- **type** — next-bar-type (existing `strat_walk_forward`), confirm the validated
  baseline.
Output: the definitive "what's predictable today" table + chart (via
`scripts/magnitude_result_charts.py`).

### Part 3 — Lever experiments (net-new)

**Feature levers (new information):**
- **① Microstructure from 1-min bars** — engineer, per 5-min bar, from the five
  constituent 1-min bars in `market_data_intraday`: intrabar candle-type sequence
  (prev 1-min shapes), signed up-vol vs down-vol (1-min close>open ⇒ up-vol),
  volume timing (early-vs-late concentration), micro-momentum / acceleration over
  last N 1-min bars, run-length asymmetry (consecutive up/down 1-min bars),
  intrabar range location. All **t-known** (bars up to and including the decision
  bar). New feature block, toggleable in the harness.
- **③ Cross-asset 1-min lead-lag** — from the three tickers' 1-min bars: lead-lag
  returns (SPY/QQQ 1-min return leading IWM), relative-strength / rank features,
  and a **cross-sectional target** (which ticker's next-window return is highest).
  All t-known.

**Target / conditioning levers (new labels):**
- **② TYPE-conditioned / continuation** — target = continuation vs reversal
  relative to the strat structure; and direction meta-models fit *within* specific
  setups (RevStrat, Failed-2U/2D, FTFC-aligned). Reuse `breakout_meta_walk_forward`
  patterns. Leverages the one validated model (TYPE).
- **④ Reframe target / horizon / regime** — one-sided up-excursion target (predict
  only the more-predictable side); longer horizons (30–60 min net-direction /
  drift sign); regime-gated direction (only in negative-gamma / trending regimes,
  using existing gamma/dealer features). Reuse `dir_regime_walk_forward` patterns.

Each experiment: choose feature-set × target × conditioning, run through Part 1,
emit a slice-ledger row.

### Part 4 — Synthesis

Rank all slices by walk-forward directional lift with fold-level confidence
intervals; apply the multiple-comparisons correction over the slice ledger;
chart (small-multiples by lever/ticker/timeframe). Deliver: which slices clear
the pre-registered bar (if any), the honest MC-adjusted verdict, and a
recommendation (productionize / new-data-needed / null).

## Data flow

`market_data_intraday` (1-min) → microstructure + lead-lag feature builders →
join to `strat_features_{tf}` surface → `featurize()` → labels (per lever) →
purged/embargoed walk-forward → per-fold metrics → slice ledger → synthesis +
charts.

## Leakage & honesty discipline (non-negotiable)

- All engineered features strictly t-known (backward windows / shifts only; never
  next-bar or future 1-min bars).
- Purged + embargoed folds (inherited from the reused harness) to prevent
  label-window leakage across the split boundary.
- Slice ledger + multiple-comparisons correction — the p-hacking guard.
- Cross-ticker replication required — the luck guard.
- Pre-registered bar committed before running.

## Phasing (learn fast, fail cheap)

1. **P1** Protocol wiring + slice ledger + 3-axis baseline (Part 1 + 2). Gate:
   reproduce 0/72 direction control + confirm size/type baselines.
2. **P2** Feature levers ① + ③ → re-measure direction. Highest-EV new information.
3. **P3** Target/conditioning levers ② + ④ → label matrix.
4. **P4** Synthesis + MC correction + charts + verdict.

Stop early if P2/P3 show no slice with a pulse after MC correction — that is
itself a publishable, honest result (strengthens the standing verdict).

## Testing

- Hermetic unit tests for every new feature builder (known 1-min input → expected
  microstructure/lead-lag output; explicit leakage assertions — a next-bar
  reference must fail a test).
- A gate-function test (synthetic fold results → correct PASS/FAIL).
- Slice-ledger round-trip test.
- Harness reuse validated by reproducing the known 0/72 direction control and the
  validated TYPE result as regression anchors.

## Risks / open questions

- **1-min coverage / alignment** — confirm `market_data_intraday` spans the
  2019–2026 window at 1-min for all three tickers and aligns cleanly to 5-min
  bars (resample boundaries). Verify in planning.
- **Reuse vs rebuild** — the existing dir walk-forward modules may need light
  refactor to accept pluggable feature/target blocks; prefer extension over a new
  harness.
- **Compute** — full matrix × 8 folds × 3 tickers is heavy; run in Cloud Run
  research jobs (the `magnitude-engine` / `strat-engine` job pattern), not local.
- **Multiple comparisons** — with many slices, even the corrected bar can pass by
  luck; the fresh-OOS confirmation on any winner is the backstop.

## Deliverables

1. Reusable direction-experiment harness (extended from existing) + slice ledger.
2. 1-min microstructure + cross-asset lead-lag feature builders (tested).
3. The lever experiment runs + slice ledger populated.
4. 3-axis predictability baseline table + charts.
5. Synthesis doc with MC-adjusted verdict, appended to `DIRECTION_RESEARCH_RESULTS.md`
   and `EXPERIMENT_REGISTRY.md`.
