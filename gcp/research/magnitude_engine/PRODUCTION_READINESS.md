# Magnitude Engine Production-Readiness Contract

**Criteria version:** `magnitude-production-readiness-v1`  
**Status:** locked prospectively; all requirements are mandatory and conjunctive.

This document is the human-readable production-promotion contract. Its exact
machine-readable counterpart is `PRODUCTION_READINESS_CRITERIA` in
`mag_config.py`. Every experiment summary and every model `CONTRACT.json` must
record the criteria version above. A version mismatch, a missing version, or an
unmeasurable mandatory metric blocks promotion.

## Objective boundary

The primary target is the existing four-class **next-bar magnitude bucket**:
`TIGHT`, `NORMAL`, `EXPANDED`, or `EXPLOSIVE`, obtained by bucketing
`abs(next_close - next_open) / atr_20` at 0.5, 1.0, and 1.5. This is the
canonical `body`/ATR label contract; alternative label modes or thresholds are
research targets and cannot be promoted under this contract.

Binary **EXPLOSIVE detection is a separate model objective**. It requires its
own prospectively specified training, calibration, decision threshold, and
untouched validation. It must not be created by inspecting four-class
validation probabilities and choosing a threshold post hoc. Four-class
EXPLOSIVE diagnostics do not turn the multiclass model into the binary model.

## Unit of evaluation and data discipline

Promotion is decided independently for each `(ticker, timeframe)`. All metrics
below must be computed on untouched, chronological out-of-sample data. Splits,
regime definitions, materially populated-class rules, bootstrap method,
reliability-failure rule, catastrophic-degradation boundary, execution-cost
assumptions, abstention policy, and any binary threshold must be registered
before examining the corresponding validation window.

The criteria may be changed only prospectively under a new version. They must
never be revised after examining the validation window to which they apply.

## Mandatory promotion gates

For a cell to be promoted, **all** of the following must pass:

1. **Discrimination:** multiclass log loss is lower than an expanding
   class-prior baseline. Bootstrap the paired difference (`model - baseline`)
   and require its 95% confidence interval to exclude zero on the favorable
   (negative) side.
2. **Calibration:** ECE is below the existing timeframe ceiling (5m: 0.05,
   15m: 0.05, 30m: 0.075), and no materially populated class has a material
   reliability-curve failure under the pre-registered rule.
3. **Probability quality:** multiclass Brier score improves on the same
   expanding class-prior baseline.
4. **EXPLOSIVE operating characteristics:** report precision **and** recall,
   each with confidence intervals. Lift alone is insufficient. For a binary
   EXPLOSIVE detector these are metrics of that separately validated model;
   multiclass diagnostics remain explicitly multiclass diagnostics.
5. **Regime robustness:** demonstrate performance in at least three
   pre-registered market regimes, with no regime crossing the pre-registered
   catastrophic-degradation boundary.
6. **Economic utility:** net utility is positive after spread, slippage,
   latency, and the economic/opportunity effect of abstention, using
   prospectively fixed assumptions.
7. **Evidence floor:** use at least 20 independent trading sessions and at
   least 50 realized observations of **each tail class proposed for promotion**
   (`EXPANDED` and/or `EXPLOSIVE`). If either floor is unmet, extend the
   chronological collection window; do not waive or extrapolate the gate.
8. **Completeness:** if any mandatory metric cannot be measured, the decision
   is **NO PROMOTION**, not “not applicable,” an implicit pass, or a fallback
   to another metric.

Existing research gates and distribution-collapse checks may remain useful
diagnostics, but they do not replace any requirement in this contract.
