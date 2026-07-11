# Direction Predictability Program — Phase 2 Design

**Date:** 2026-07-09
**Status:** approved design → implementation plan next

## Goal

Enrich the DIRECTION and SIZE walk-forward engines with new feature families
and measure, per family, whether they move each axis toward the pre-registered
gate — **beats base-rate log-loss in ≥6 of 8 folds AND replicates on all 3
tickers (IWM, SPY, QQQ)** — using the honest baseline from Phase 1 as the
anchor. TYPE already passes and is out of scope (left untouched).

## Context / evidence (from Phase 1 + the importance audit)

- **Baseline (5m, strict gate):** TYPE ✅ (3/3), SIZE ❌ (0/3), DIRECTION ❌ (0/3).
- **Importance audit** (`gcp/research/direction_program/feature_importance.py`,
  gain + SHAP over the exact production engines, 8 folds × 3 tickers):
  - **DIRECTION is diffuse** — top feature `range_expansion_ratio` = 4.6% of
    gain; 63 features to reach 80%; **116 / 259 columns near-dead** (<1% of top
    gain). Top features are volatility-expansion / opening-range / time-of-day —
    "a move is coming and how big," but almost no "which way" signal.
  - **SIZE is concentrated** — top-2 (`mins_since_open` 9.9%, `rvol_10` 8.4%) =
    ~18% of gain; **156 / 254 columns near-dead**. Real drivers (time-of-day,
    relative volume) exist; the missing piece is the market's own move-size
    forecast (implied vol).
- **Already-built, leak-safe features** in
  `lib/features/experimental/options_derived.py` (uses `etf_options_snapshots`,
  d-1 EOD snapshots): `pcr_volume_d1`, `pcr_oi_d1`, `iv_skew_25d_d1`,
  `iv_term_slope_d1`, `atm_iv_d1`, `iv_atm_chg_5d`. Never wired into the
  production engines — only a side-script uses them.
- **Magnitude engine already defines** (in `mag_config.py`) `phase3` (event
  proximity), `phase4` (cross-asset VIX/UST/DXY/oil/gold), `phase_calendar` —
  coded but un-backfilled. Phase 2 reuses/backfills these, does not reinvent.
- **No order-book / tick data.** True order-flow imbalance (the dominant
  intraday-direction signal in the literature) is unavailable; we use bar-level
  and daily-regime proxies only.

## Non-goals

- No changes to the TYPE engine or its behavior.
- No options *cost* / P&L / EV modelling — pure prediction only.
- No new model architecture. Reuse the existing LightGBM walk-forward engines.
- No order-book / tick acquisition.

## Architecture (combination of ablation + isolation + selective materialization)

**Backbone — ablation on the real engines.** The DIRECTION and SIZE
walk-forward engines gain a `--features` flag that toggles feature families on
and off. Each configuration runs the *exact* production path (loader →
featurize → LightGBM factory → same anchored cutoffs) and records its per-ticker
fold-beats in the existing `slice_ledger`. This gives clean per-lever
attribution and reuses the code that produced the baseline (no parallel harness
— CLAUDE.md Rule 3.6).

**Isolation — one feature module.** New feature assembly lives in a single
well-bounded module, `gcp/research/direction_program/phase2_features.py`,
exposing `attach_families(df, families, engine, ticker, tf) -> df`. The engines
call it; they do not grow tangled. Feature *math* stays in `lib/features/`
(one-source-of-truth); the module orchestrates.

**Selective materialization.** The daily options family (PCR, IV-skew, ATM-IV,
term slope) is expensive to aggregate over the 52 GB `etf_options_snapshots`
table (~9 min/run). Materialize it **once** into the existing
`options_daily_features` table (extend, do not fork) via an idempotent backfill
job; ablation runs then join it. The intraday cross-asset family is cheap and
per-bar — join at load from the 1-min bar tables.

**Pruning is per-engine.** The `prune` family drops each engine's near-dead
columns at featurize time, inside the DIRECTION/SIZE engines only. TYPE's engine
is a separate code path and is never touched — no TYPE audit needed.

## Feature families (each a `--features` toggle)

| Family | Contents | Target | Delivery |
|---|---|---|---|
| `prune` | drop each engine's near-dead columns (~116 dir / ~156 size); keep the ~100 carrying 95% gain | both | featurize-time column filter, per-engine |
| `options_iv` | `atm_iv_d1`, `iv_term_slope_d1`, `iv_atm_chg_5d` | SIZE | daily, materialized in `options_daily_features` |
| `positioning` | `pcr_volume_d1`, `pcr_oi_d1`, `iv_skew_25d_d1` | DIRECTION | daily, materialized |
| `cross_asset` | other two tickers' strictly-prior intraday returns/momentum; VIX regime | DIRECTION | intraday join-at-load (1-min bars); VIX daily |
| `calendar` | day-of-week, week-of-month, FOMC week, month/quarter-end, event-day proximity | both | derived, no fetch |

## Experiment ladder (slice_ledger, gate + partial credit)

- **Rung 0 — baseline** (Phase 1 anchor; already recorded).
- **Rung 1 — isolation:** baseline + each family alone (5 × 2 axes). Marginal
  per-lever effect → the per-family verdict.
- **Rung 2 — cumulative best stack:** from `+prune`, add families in Rung-1
  effect order, keep those that help → best combined model per axis.
- Every config records per-ticker fold-beats in `slice_ledger`. Synthesis
  applies the multiple-comparisons correction (as the original program spec
  planned) across all recorded slices.

## Success criteria — verdict + partial credit

Deliverable is a **rigorous per-lever verdict**, not just a pass/fail:

- **Gate pass** — axis reaches ≥6/8 folds beating base rate on all 3 tickers
  with a family/stack. Recorded as PREDICTABLE.
- **Partial credit** — a family that improves median fold-beat, or lifts
  ticker-pass count (e.g. 0→2/3), or ranks high in importance, is recorded as a
  positive even without a gate pass. A well-measured "SIZE now passes, DIRECTION
  still not tradeable but +X on beat" is a SUCCESS outcome.
- **Near-miss flag** — passes on 2/3 tickers or 5/8 folds with an improving
  trend → flagged as a candidate for a follow-up push, not closed.

## Production-grade guardrails (CLAUDE.md Rule 0 / 3.6 / 3.7 — non-negotiable)

1. **Capacity math (Rule 0 §2), written before merge.**
   - Volume: ~5 families × (isolation + cumulative) ≈ 10 configs × 2 axes ×
     3 tickers × 8 folds.
   - Velocity: 1 batched feature SELECT per (ticker, tf) per config; daily
     options family read from the materialized table (no per-run re-aggregation).
   - Wall-clock: a single config ≈ the baseline (~40 min for both axes ×
     3 tickers). Serial over ~10 configs ≈ 7 h — **unacceptable as one task.**
   - **Therefore the ablation runs as a task-parallel Cloud Run job** (one task
     per config, like `magnitude-engine`'s fan-out), bounding wall-clock to
     ~one config regardless of config count. `max-retries 0`, task-timeout ≥ 4×.
2. **No silent fallbacks (Rule 3.7).** Missing new-feature values (sparse early
   dates) flow as **NaN straight to LightGBM** (which handles missing natively)
   — **never `fillna(0)`**. Per-feature coverage rate is logged; a family below
   a coverage floor on a fold is reported, not silently zero-filled. This
   *removes* the existing `fillna(0)` fallback in `options_derived.py`, not
   inherits it.
3. **Idempotent materialization (Rule 0 §4).** The options backfill extends
   `options_daily_features` with `ON CONFLICT DO UPDATE`, batched by year
   (reusing `options_derived.py`'s existing year-chunking, <5 s/query),
   coverage-logged. One-shot, `max-retries 0`, with a $/run estimate.
4. **Reuse, don't reinvent (Rule 3.6 / DRY).** Backbone = the production
   engines; feature math = `lib/features/`; cross-asset/event/calendar =
   the magnitude engine's existing `phase3`/`phase4`/`phase_calendar`
   definitions, backfilled.
5. **Cost discipline.** All jobs one-shot, on-demand, `max-retries 0`, no
   scheduler. Materialization is a one-time backfill; ablation is manual.

## Testing

- **Unit (hermetic):** `phase2_features.attach_families` — each family attaches
  the expected columns, leak-safe (daily = strictly d-1 EOD; cross-asset =
  strictly-prior bars), missing values are NaN not 0, unknown family raises.
  The `prune` filter drops exactly the audit's near-dead set and keeps the rest.
  Column-count / coverage assertions per family.
- **I/O-shape test (Rule 0 §3):** assert one config triggers exactly the
  expected number of feature queries (no per-row / per-bar N+1).
- **Production smoke:** one isolation config per axis run on the real
  task-parallel job against Cloud SQL, verifying the ledger row and coverage
  logs — the documented data-volume smoke, not a synthetic DataFrame.

## Deliverables

1. `phase2_features.py` (+ tests) — the family-assembly module.
2. `--features` flag on the DIRECTION and SIZE engines + per-engine `prune`.
3. Options backfill extending `options_daily_features` (idempotent, coverage-logged).
4. Task-parallel `direction-phase2` Cloud Run job + `deploy.sh` entry.
5. Ablation run → `slice_ledger` populated → per-lever verdict + partial-credit
   report + gate/near-miss table, with the multiple-comparisons correction.
