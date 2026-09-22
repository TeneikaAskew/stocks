# MODEL-FLOW-001 — Dealer flow-direction features (DEX / vanna / charm)

**Code:** `lib/features/flow_direction.py` (587 lines), `gcp/build_options_daily_greeks.py` ·
**Table:** `etf_options_daily_greeks` ·
**Job:** `build-options-greeks` — scheduled `options-daily-greeks`, `15 23 * * 1-5`, **ENABLED** ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** **Failed** · **Rec:** PAUSE
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> **Registered 2026-09-18, after running unregistered on a daily cron.** Until this document
> existed, `lib/features/flow_direction.py` was named by no `MODEL-*` row, so the
> scheduler-completeness gate could not see `build-options-greeks` — the gate's rule is *"a job
> is model-bearing when it executes code cited in a `MODEL-*` row"*, and it was correctly
> excluding a job whose code the registry had never claimed. Found by review on
> [#1111](https://github.com/TeneikaAskew/stocks/pull/1111); recorded as DOC-32.

## What it decides

Per ticker per day, from `etf_options_snapshots`: which **way** dealers are leaning, and which
way their hedging will push price as time and volatility move. Deliberately distinct from the
magnitude features in `lib/features/experimental/options_derived.py` (PCR, IV skew, ATM IV),
which answer *how much* exposure there is rather than *which direction*.

| Feature | Meaning |
|---|---|
| `dex_d1` | net **dealer** delta exposure |
| `dex_per_oi_d1` | `dex_d1 / total OI` — scale-free positioning tilt |
| `dex_chg_5d` | `dex_d1 / dex_d1.shift(5) - 1` — momentum of positioning |
| `vanna_d1` | net dealer vanna, `-Σ(vanna · OI)` |
| `charm_d1` | net dealer charm (delta decay per calendar day), `-Σ(charm · OI)` |
| `short_dte_dex_d1` | `dex_d1` restricted to `dte <= 2` — the 0-2DTE charm-pin driver |

All six are shifted `d-1` in the joiner (`add_flow_features`) for leak safety.

**The sign convention is the dealer-short negation, not `lib.gamma`'s net-gamma balance.**
`dex_d1 = -(Σ_calls delta·OI + Σ_puts delta·OI)`, and vanna/charm use the same negation, which
matches `lib/gamma.py`'s `total_vex = -(call_vex + put_vex)` ("dealers are SHORT both calls AND
puts") and **not** the calls-add/puts-subtract convention `lib.gamma` uses for net *gamma*. The
module states this explicitly and records that it was corrected under review H-1. Reading a
`dex_d1` sign with the gamma-balance convention in mind inverts it.

## Why this is Failed

The ledger evaluated it and falsified it. [EXPERIMENT_REGISTRY](../EXPERIMENT_REGISTRY.md)
**B5 (E5) — Flow-Direction (daily EOD dealer greeks)**, status *failed (null + dilutive)*:

> *"❌ falsified; slow daily positioning adds nothing, dilutes the lone edge."*

Measured as an ablation against the E4 long/short triple-barrier baseline, six flow columns
added, `d-1` leak-safe, 100% coverage — so the null is not a coverage artifact:

| Ticker | baseline → +flow (long, fire ≥ 0.60) |
|---|---|
| **IWM** | **+0.053 / z 2.85 → −0.008 / z −0.49** — the edge is destroyed, and fires rise 726 → 881 while precision falls |
| SPY | +0.001 → +0.001 (z ≈ 0) |
| QQQ | −0.022 / z −1.35 → +0.011 / z 0.76 |

The IWM row is the finding: adding the features did not merely fail to help, it removed the one
directional edge the program had, by firing more often and worse.

## Why `PAUSE` rather than `REMOVE`

**A daily scheduler has been materializing a feature set its own experiment falsified.**
`options-daily-greeks` fires `build-options-greeks` every weekday at 23:15 ET and is ENABLED
live (confirmed 2026-09-18 against `gcloud scheduler jobs list`).

The only reader of `add_flow_features` in the repository is
`gcp/research/strat_engine/strat_dir_probes.py:836-837` — a research probe. **No production
path reads `etf_options_daily_greeks`.** So the cron is paying, every trading day, to keep a
table current for a falsified line of research.

[MODEL-DIR-001](../product/07-MODEL-REGISTRY.md)'s precedent is *"archive rather than delete —
the negative result is evidence"*, and that applies to the code and the table. It does not
apply to the cron, because MODEL-DIR-001 has none. Whether to disable the scheduler is a cost
decision, not a documentation one; this document records the position rather than taking it.

## Entry points

| Symbol | Role |
|---|---|
| `compute_chain_features` | per-chain aggregation — pure, numpy/pandas/scipy only |
| `compute_daily_features` | per-`snapshot_date` rollup |
| `compute_daily_greeks_frame` | the builder's entry point (`engine, ticker, since, until`) |
| `add_flow_features` | the joiner — reads the materialized table, applies the `d-1` shift |
| `bs_delta` · `bs_vanna` · `bs_charm_per_day` | Black-Scholes-Merton closed forms with continuous dividend yield |

The DB-bound helpers lazy-import SQLAlchemy so the pure compute functions stay unit-testable
without a database. `gcp/build_options_daily_greeks.py:131` imports `compute_daily_greeks_frame`
inside `build()` for the same reason — which also means a top-level-import scanner cannot see
this edge, and is part of why the job went unclassified.

## Rationale

**Recorded, and negative.** The feature choice is explained — *"chosen because price features
are null and flow is information not re-representation"* — and the result is a measured
ablation rather than an assertion. The sign convention carries its derivation and a review
correction. What is **UNKNOWN** is why the materialization job still runs after the verdict.

One operational lesson is recorded in the ledger and worth repeating: the first cut
re-aggregated 14M-row snapshots per experiment and starved Cloud SQL (2026-06-05 incident),
which is what produced the materialized table and the scan-once builder, per CLAUDE.md Rule 0.

## Tests

`tests/lib/test_flow_direction.py` — the scorer.

**`gcp/build_options_daily_greeks.py`, the other half of the Code line, is imported by no test
and mentioned by none.** The scorer is covered; the job that runs it daily and writes its
output is not. Recorded here because an unstated gap reads as no gap. DOC-44.

## Known issues

**None filed.** The open question is operational, not a defect: the scheduler is live for a
falsified feature set (see [Why `PAUSE`](#why-pause-rather-than-remove)). Titles and severity
are owned by [12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
