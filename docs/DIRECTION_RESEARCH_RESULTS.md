# Directionality Research — Verdict

**VERDICT: no *generalizable* directional edge; one unresolved IWM-only
candidate.** Intraday directional sign on liquid index ETFs is not predictable
from price/volume/technical/regime features in any way that survives across
tickers. Confirmed across every avenue the literature pointed to — longer
horizons, trigger-conditioning, regime/time-of-day models, **and the
literature's own triple-barrier first-touch target with separate long/short
meta-models conditioned on the magnitude engine's EXPLOSIVE flag (E4)** — all
under purged + embargoed walk-forward CV.

Evaluated **cost-free** (the right lens for a combined size+direction signal),
there is exactly **one** statistically-significant edge: a *long-only* tilt on
magnitude-EXPLOSIVE bars, **z up to 4.2, sharpening with confidence, surviving
the 2022 bear — but only on IWM.** It **does not replicate on SPY or QQQ**
(z≈0), so it is an unresolved candidate (literature-plausible small-cap
timeability vs. one-of-three multiple-comparisons luck), not a confirmed edge —
and it is miscalibrated (ECE ≈ 0.10; trust ranking, not probabilities). The one
genuinely predictable, calibrated, cross-ticker quantity is
**magnitude/volatility**, already productionized in the separate
`magnitude_engine`. Standalone direction is a coin flip everywhere except a
narrow, unvalidated IWM pocket.

> **Honesty note (post-review).** An earlier draft claimed "0-for-everything
> across labels" and dismissed triple-barrier as a sizing rescale. That was
> overstated and the dismissal was a reasoning error: the return-sign family was
> tested exhaustively, but triple-barrier *as a primary target* had not been run.
> It now has (§E4) — same null on the gate, with one sub-friction long flicker
> documented rather than hand-waved.

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

### E4 — Triple-barrier first-touch, the closing experiment (added 2026-06-04)

**Why this section exists.** An external code audit correctly flagged that E1–E3
all used a *return-sign* label (`sign(fwd_ret at h)`) and that an earlier draft of
this doc *reasoned triple-barrier away* as a "volatility sizing rescale" rather
than running it. That dismissal conflated two different objects: triple-barrier
as a **meta-label** (binary "did the primary's bet hit profit before stop") does
presuppose a primary side and cannot manufacture an absent edge — but
triple-barrier as the **primary directional target** is a different quantity
that was never tested. It was built and run here. The reviewer was right; the
gap was real.

The proper target (López de Prado): for each bar, which of ±k·ATR20 is touched
**first** within H bars, with an explicit **neutral** class on timeout. This
differs from sign(return) in two ways that matter: (1) the neutral class
**discards the chop bars** a sign label is forced to ±-label (the noise that
pins sign at 0.50), and (2) it scores **directional travel / order-of-arrival**,
not where price sits at bar H. Run with all the levers the prior probes missed:
- separate **long-vs-rest** and **short-vs-rest** meta-models *and* a symmetric
  3-class model (up moves and down moves load on different features);
- **magnitude-conditioned** — restricted to bars the `magnitude_engine` model
  independently predicts EXPLOSIVE (in-sample for train-selection, **OOF** for
  test — leak-free, t-known), via a fold-relative top-quantile of P(EXPLOSIVE);
- k ∈ {1.0, 1.5}, H=12 bars (15m), same 8 folds, same embargo, same gates.

**Result.** Costs never enter the model, the labels, or the predictive metrics —
only the final "tradeable?" judgment. So the result is reported two ways: the
**signal-quality** view (cost-free; the right lens for a combined size+direction
research signal) and the **tradeability** view (after friction).

| arm | log-loss beat (calibration gate) | decisive precision (cost-free) |
|---|---|---|
| symmetric 3-class | **0/8** all variants | ≤ coin (0.43–0.49) |
| short-vs-rest | **0/8** | ≈ base (+0.01) |
| **long-vs-rest, mag-gated (IWM)** | **0/8** (ECE ≈ 0.10) | **0.547 / 0.499 — significant, see below** |

**Cost-free signal-quality view (IWM).** The long-vs-rest arm on
magnitude-EXPLOSIVE bars is a genuine, statistically-significant directional
edge — *but only on IWM*:
- pooled decisive (≥0.60) precision **0.547 vs 0.494 base, +5.3pp, z=2.85** (k1.0)
  and **0.499 vs 0.412 base, +8.7pp, z=3.72** (k1.5); positive in **7/8 folds
  including the 2022 bear** (not bull-drift);
- **sharpens monotonically with model confidence** — k1.5 lift goes +5.9pp (≥.55)
  → +8.7pp (≥.60) → **+13.4pp, z=4.21 (≥.65)** — the signature of real signal, not
  noise. (The earlier "weakens when tightened" caveat was about the *magnitude*-gate
  fraction, a different axis; on the *confidence* axis it strengthens.)
- The **calibration gate still fails** (0/8, ECE ≈ 0.10): trust the *ranking*
  (most-confident long calls hit up-first more often), not the probability
  *values* — a fire-when-confident usage, with an empirically-set threshold.

**Cross-ticker robustness — the decider — is a clean negative.** Re-run on the
two more-liquid names, the IWM edge **does not replicate**:

| ticker | k1.0 ≥.60 | k1.5 ≥.65 |
|---|---|---|
| **IWM** | +5.3pp (z=2.85) | +13.4pp (z=4.21) |
| SPY | +0.1pp (z=0.05) | −1.7pp (z=−0.61) |
| QQQ | −2.2pp (z=−1.35) | +1.9pp (z=1.00) |

SPY and QQQ are flat-to-negative, coin-flip fold splits. Two readings, not yet
separable: (a) a **literature-consistent small-cap effect** — IWM is the
less-liquid Russell ETF, and Gao et al. / Barbon-Buraschi predict directional
timeability concentrates in less-liquid names; the within-IWM coherence (two
independent barrier widths, monotonic confidence-sharpening, bear-year survival)
argues against pure noise; or (b) **one-of-three multiple-comparisons luck**,
which is exactly where a disciplined reviewer demands replication. Resolving it
needs IWM cross-timeframe (5m/30m) + a true locked holdout before the IWM tilt
is trusted.

**Tradeability view (after friction).** Even the IWM long edge is sub-friction:
gross EV ≈ k·(2p−1) ≈ **1.0–1.1 bps/trade** vs ~1.5 bps round-trip IWM friction
⇒ net ≈ **−0.5 bps**. (Reported for completeness; per the size+direction use case
this gate is set aside — the signal-quality view above is the operative one.)

---

## Decision-rule application

- **Log-loss / calibration gate (cost-free, necessary for trustworthy
  probabilities):** FAILED in **0 of ~150** walk-forward folds across every label
  family — baseline 0/72, feature R&D 0/8, E1 0/47, E2 0/8, E3 0/29, SPY/QQQ 0/63,
  **and the triple-barrier first-touch target (E4) 0/8 on every arm and variant.**
- **Cross-ticker robustness (cost-free):** the one significant cost-free edge —
  E4 magnitude-gated long, IWM, z=2.85–4.21 — **does not replicate on SPY/QQQ**
  (z≈0). No edge generalizes across the 3-ticker universe.
- **EV bar (set aside for the size+direction use case):** even the IWM long edge
  is net ≈ −0.5 bps/trade after friction. Reported for completeness; not the
  operative gate when direction is consumed as a research signal alongside size.
- **Triple-barrier as PRIMARY target (E4):** run, not moot (correcting the prior
  draft). The neutral class and first-touch travel did **not** rescue direction
  broadly: symmetric and short arms are dead on every ticker; the long arm is a
  real but **IWM-only**, miscalibrated edge.
- **Meta-labeling (the *other* triple-barrier use):** still moot — it needs a
  primary edge, and E2 + E4-symmetric show there isn't a calibrated, generalizable
  one to filter.

**Verdict tier (cost-free, size+direction lens):**
- **SPY / QQQ — DEAD.** No directional signal survives, cost-free, on any label
  family. Treat direction as 50/50; lean entirely on `magnitude_engine` (size).
- **IWM — UNRESOLVED CANDIDATE.** A real, significant (z up to 4.2),
  confidence-sharpening, bear-surviving **long-only tilt on magnitude-EXPLOSIVE
  bars**, but **unreplicated** on the other two names and **miscalibrated**
  (use ranking, not probabilities). Literature-plausible (small-cap timeability)
  but one-of-three is the multiple-comparisons danger zone. **Do not trust until
  validated** on IWM 5m/30m + a locked holdout.
- *Magnitude* remains the predictable, calibrated, shipped quantity.

---

## What would change this verdict

Genuinely new information, not new models on the same data:

1. **Order-flow / microstructure tick data** (signed trades, queue imbalance) —
   the one SPY study that moved directional accuracy used hidden-order signals,
   and even it landed at 45% (magnitude up 2.89×, direction still a coin flip).
2. **Cross-sectional factor inputs** (Aleti-Bollerslev factor-zoo: post-cost SPY
   Sharpe 1.37) — a different architecture (cross-asset), not single-instrument
   technicals, outside this engine's data scope.

…or a change to the **cost or calibration** of the one E4 flicker:

3. **Beat the friction** on the magnitude-gated long lean — its gross ~1 bp edge
   is real but eaten by ~1.5 bp round-trip cost. A **passive/maker entry** (post,
   don't cross) that captures rather than pays the spread could flip net EV
   positive. This is an *execution* change, not a modeling one, and only worth it
   if the lean first survives calibration (#4).
4. **Calibrate the long arm** (isotonic/Platt on the gated subset) and re-test:
   the flicker fails the log-loss gate at ECE ≈ 0.10, so today its confidence
   threshold can't be trusted. If calibration doesn't bring ECE under ceiling,
   the precision lift is noise; if it does, re-run the EV gate with #3.

Absent one of these, the recommended posture is: **stop spending on standalone
single-instrument directional models**; keep the TYPE (structure) and magnitude
models, which are the genuinely predictable, calibrated, tradeable targets. The
E4 long lean is logged as a *possible weak filter on `magnitude_engine` EXPLOSIVE
bars* — not a standalone engine, and not worth pursuing until #3/#4 are cheap.

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

# E4 triple-barrier first-touch (symmetric + long/short), magnitude-gated:
gcloud run jobs execute direction-probe --region us-east1 --async \
  --args="-m,gcp.research.strat_engine.strat_dir_probes,\
          --experiment=e4_triple_barrier,--ticker=IWM,--tf=15m,--horizon=12,\
          --barrier-atr=1.0,--mag-cond=topq,--mag-thresh=0.2"
# Artifacts: gs://adept-mountain-474619-d4-trading-data/research/strat_engine/iwm_15m/dir_probe_*.json
```
Hermetic helper tests: `tests/test_strat_dir_probes.py` (19 passing, incl. 6 for
`triple_barrier_labels`).
