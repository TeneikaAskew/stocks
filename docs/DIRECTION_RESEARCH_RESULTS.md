# Directionality Research — Verdict

**VERDICT: DEAD-END.** Next-bar/next-window directional sign on liquid index
ETFs is **not exploitable** from price/volume/technical/regime features. This was
confirmed across every avenue the literature pointed to — longer horizons,
trigger-conditioning, and dedicated regime/time-of-day models — all under
purged + embargoed walk-forward CV. The result is exactly what the efficient-
market literature predicts. The one genuinely predictable quantity is
**magnitude/volatility**, which is already productionized in the separate
`magnitude_engine`. Direction is a coin flip.

> Status: 2026-06-04. Branch `claude/strat-engine-directional-calibration-wHAis`.
> Companions: [`DIRECTION_LITERATURE_SCAN.md`](DIRECTION_LITERATURE_SCAN.md)
> (Phase 0 lit review) and [`DIRECTION_FEATURES_R&D.md`](DIRECTION_FEATURES_R&D.md)
> (feature-family reframe, also FAIL).

---

## The question

The strat-engine ships a strong, calibrated **structure/TYPE** model
(next candle ∈ {1,2U,2D,3}: 8/8 folds, +0.18 log-loss beat, ECE ≤ 0.05) but a
**direction** model (`next_close > next_open`, single next bar, unconditional)
that fails 0/72 folds. The user's hypothesis: "something is missing." The prior
feature-family R&D proved it is **not the features** (news/cross-asset/vol-regime
all 0/8 on the same target). This program tested whether it is the **label**.

**Organizing principle:** vary the label (horizon / barrier / conditioning /
regime), not the feature set. **Binding decision rule:** a label/conditioning
ships only if it produces net EV > +$0.02/sh in ≥6/8 folds after $0.05 friction,
with a calibrated signal (ECE ≤ 0.05) — log-loss beat is the necessary *gate*
before EV is even worth measuring.

---

## What was run (all through the production harness, no throwaway scripts)

Every probe ran on the dedicated `direction-probe` Cloud Run Job
(`gcp/research/strat_engine/strat_dir_probes.py`) through the EXACT baseline
machinery: `load_labeled_dataset` → `featurize` (143+levels cols) → same 8
anchored expanding folds (2019→2026) → same LightGBM hyperparameters. The only
changes per experiment were the **label** and an **embargo purge**. Target
ticker: **IWM** — the literature's most-timeable liquid ETF (less liquid ⇒ more
intraday predictability; Barbon-Buraschi, Gao et al.). If direction is dead on
IWM, it is deader on SPY/QQQ, so those were not spent on.

### E1 — Longer horizon (the literature's primary lever)
Session-aware forward-return sign at h ∈ {1, 3, 5, 10, 15, 20} bars (15m),
embargo ≥ horizon.

| h (bars) | median log-loss beat | positive folds | ECE |
|---:|---:|:---:|---:|
| 1 | −0.013 | 0/8 | 0.062 |
| 3 | −0.031 | 0/8 | 0.099 |
| 5 | −0.050 | 0/8 | 0.122 |
| 10 | −0.083 | 0/8 | 0.159 |
| 15 | −0.077 | 0/8 | 0.151 |
| 20 | −0.070 | 0/7 | 0.155 |

**0/47 folds positive.** Extending the horizon does not help — it makes
calibration monotonically *worse*. (Christoffersen-Diebold: sign predictability
is weakest at the highest frequencies and rides volatility dynamics; we see no
intra-session horizon where it turns tradable.)

### E2 — Trigger-conditioned follow-through (the meta-labeling gate)
Predict h=5 direction only on bars where a Strat trigger fired
(`is_continuation ∨ is_reversal`). **0/8 folds positive**, median accuracy
−2.7pp, ECE 0.11. There is **no primary directional edge** to filter — so
meta-labeling (which the literature is unanimous *cannot create* an edge a
primary lacks; one reproduction even lowered Sharpe) is evidence-backed moot and
was not built.

### E3 — Dedicated regime / time-of-day models (the one effect theory supports)
h=5, train+test restricted to each regime so regime-specific structure can be
learned (not a post-hoc slice of a global model).

| Regime | OK folds | median log-loss beat | positive | ECE |
|---|:---:|---:|:---:|---:|
| vix_low | 4 (thin) | −0.038 | 0/4 | 0.117 |
| vix_high | 8 | −0.067 | 0/8 | 0.127 |
| pos_gamma | 2 (thin) | −0.235 | 0/2 | 0.267 |
| neg_gamma | 7 | −0.082 | 0/7 | 0.159 |
| **late_session** (Gao et al.) | 8 | −0.061 | 0/8 | 0.128 |

**0/29 folds positive.** The single literature-blessed directional effect —
late-session intraday momentum — does not replicate as a tradable signal. Every
regime is *miscalibrated* (ECE 0.12–0.27), not merely unprofitable.

### Cherry-pick check
The strongest decisive (≥0.55 confidence) per-stratum, per-fold hit rate found
anywhere in the program was ~0.59 (n≈200–275, a single fold). Selected as the
max over ~3 strata × 8 folds × 12 runs against a uniformly negative aggregate,
this is exactly the multiple-comparisons artifact the literature warns about
(trend-scanning / data-snooping), not a stable edge.

### Cross-ticker confirmation (SPY + QQQ)
To rule out an IWM-specific quirk, E1 (h=1/5/15) and E2 (h=5) were re-run on the
two more-liquid index ETFs. The failure is **ticker-independent**:

| ticker | h=1 | h=5 | h=15 | E2 trigger h=5 |
|---|---|---|---|---|
| SPY | 0/8 (−0.010) | 0/8 (−0.034) | 1/8 (−0.064) | 0/8 (−0.039) |
| QQQ | 0/8 (−0.010) | 0/8 (−0.033) | 0/8 (−0.065) | 0/8 (−0.029) |

(median log-loss beat in parens; the lone SPY h=15 positive fold sits against a
−0.064 median and −5pp median accuracy — noise.) Same shape as IWM and as the
baseline's 0/72 single-bar cross-ticker result: this is an information-content
limit of the feature surface, not a per-instrument property. More-liquid names
are *harder*, not easier, consistent with the literature.

---

## Decision-rule application

- **Log-loss gate (necessary condition):** FAILED in **0 of 84** new walk-forward
  folds (E1 0/47 + E2 0/8 + E3 0/29), on top of the baseline's 0/72 and the
  feature R&D's 0/8 cells.
- **EV bar (binding constraint):** **not reached, deliberately.** EV is only
  meaningful for a calibrated signal; with the gate failing everywhere and ECE
  0.12–0.27, every candidate trades noise and is guaranteed net-negative after
  $0.05 friction. Running `exec_backtest` would spend compute to confirm the
  obvious — declined on cost discipline (Rule 0 §6), with the gate failure as the
  proof.
- **Meta-labeling / triple-barrier (E4/E5):** moot. E4 needs a primary edge E2
  shows doesn't exist. E5 (triple-barrier) re-scales labels by volatility — it
  improves *sizing* of a directional side, but horizon + trigger + regime all
  show there is no directional side to size. The predictable quantity is
  magnitude, already covered by `magnitude_engine`.

**Verdict tier: DEAD-END**, with a tightly-scoped PARTIAL footnote — *magnitude*
is predictable and shipped; *direction* is not exploitable on available data.

---

## What would change this verdict

Only genuinely new information, not new models on the same data:

1. **Order-flow / microstructure tick data** (signed trades, queue imbalance) —
   the one SPY study that moved directional accuracy used hidden-order signals,
   and even it landed at 45% (magnitude up 2.89×, direction still a coin flip).
2. **Cross-sectional factor inputs** (Aleti-Bollerslev factor-zoo: post-cost SPY
   Sharpe 1.37) — but that is a different architecture (cross-asset), not
   single-instrument technicals, and outside this engine's data scope.

Both are out of scope for the current pipeline. Absent new data, the recommended
posture is: **stop spending on single-instrument directional models**; keep the
TYPE (structure) and magnitude models, which are the genuinely predictable
targets.

---

## Methodology note — a leak we caught (transparency)

The first smoke run reported +47pp accuracy / 100% decisive hit / ECE 0.0000 —
impossibly good. Cause: the session-aware label column entered the feature
matrix (`featurize`'s drop-list is by name and didn't know the new column). Fixed
by computing the label before featurizing and dropping it, plus a **fail-loud
leakage guard** that now rejects any `fwd_`/`next_`/`_fwd` column in the matrix.
This is why hermetic helper tests are necessary-but-not-sufficient (CLAUDE.md
Rule 0 §3): the leak only appeared against real data, and the too-good number was
the tell. All results above are post-fix.

## Reproduce
```bash
# E1 horizon sweep / E2 trigger / E3 regime (research image; dedicated job):
gcloud run jobs execute direction-probe --region us-east1 --async \
  --args="-m,gcp.research.strat_engine.strat_dir_probes,\
          --experiment=e1_horizon,--ticker=IWM,--tf=15m,--horizon=5,--regime=late_session"
# Artifacts: gs://adept-mountain-474619-d4-trading-data/research/strat_engine/iwm_15m/dir_probe_*.json
```
Hermetic helper tests: `tests/test_strat_dir_probes.py` (13 passing).
