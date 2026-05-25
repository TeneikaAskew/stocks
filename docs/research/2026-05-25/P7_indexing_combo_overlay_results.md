# Phase 7 — Indexing fix + high-n combo + voter overlay

**Date:** 2026-05-25 (follow-up to P7_4track_verdict.md)
**Context:** Reviewer flagged three issues with the prior verdict:
  1. **Indexing bug**: `df.iloc[entry_idx+1 : entry_idx+1+LOOKFWD]` in p7d/p7e skipped the entry bar — the predicted bar's own H/L was never checked for TP/SL.
  2. **OOS decile leak**: `pd.qcut` refit decile cutoffs on OOS distribution.
  3. **Combo-regime "failure" was uninformative**: 9.9 bp structural stop + n=17 + top-by-t-stat picked small-n overfit candidates.

Also asked for: high-n-only combo test, voter overlay as the only remaining constructive path.

## TL;DR

- **Indexing fix lifted gross by +0.55 bps/trade** at R=3 — confirms reviewer's prediction that the fix matters but doesn't quadruple the edge. IWM 15m classifier-long net still -2 bps/trade with CI spanning zero.
- **High-n combo (n≥500) cells produced only 2 OOS matches** — these cells are very restrictive at 15m. Both wins, but n=2 is too small to draw any conclusion.
- **Voter overlay IWM 60m is the strongest result of the session.** Voter alone loses money (net -5.83 bps/trade). Adding `|classifier_edge| ≥ 0.30` filter LIFTS net by ~+15 bps/trade to +9.14. 93 trades over Apr-May 2026. CI still spans zero but the effect size is consistent and meaningful.

## Track 1 — Indexing fix on IWM 15m classifier-long

| Run | n | R=3 gross | R=3 net | 95% CI gross | Notes |
|---|---|---|---|---|---|
| Pre-fix (p7e with `idx+2` skip) | 148 | +7.43 | -2.57 | [-3.97, +18.83] | exit walk skipped entry bar |
| **Post-fix** (`idx`) | 132 | **+7.98** | **-2.02** | **[-4.15, +20.11]** | exit walk starts at entry bar; deciles fit on train, not OOS |

**Magnitude of fix:** +0.55 bps/trade at R=3. As predicted. The bar we predict does carry SOME of the move, but not enough to overcome the cost line.

Win rate improvement is also small but real:
- R=1: 51.4% → **53.0%** (+1.6pp)
- R=3: 35.8% → **37.9%** (+2.1pp)

## Track 2 — High-n-only combo (n_train ≥ 500)

With the small-n cells filtered out, the top 10 training cells now all have n≥500:

| combo | regime | n_train | mean_bps |
|---|---|---|---|
| 22_bear_continuation | GEX_MID_VEX_HIGH | 1,677 | +5.2 |
| 22_bear_continuation | GEX_HIGH_VEX_HIGH | 1,238 | +3.4 |
| 22_bull_reversal | GEX_MID_VEX_MID | 901 | +5.4 |
| 22_bull_reversal | GEX_HIGH_VEX_HIGH | 892 | +3.2 |
| 22_bull_reversal | GEX_LOW_VEX_HIGH | 530 | +4.2 |
| 22_bull_continuation | GEX_LOW_VEX_HIGH | 745 | +3.2 |
| none | GEX_MID_VEX_MID | 1,544 | +3.5 |
| 22_bull_continuation | GEX_LOW_VEX_MID | 1,658 | +3.8 |
| 22_bear_continuation | GEX_MID_VEX_MID | 1,237 | +3.7 |
| 22_bear_continuation | GEX_HIGH_VEX_MID | 899 | +4.3 |

**Only 2 OOS matches** in Jan-May 2026. Both winners at every R-multiple. 95% CI at R=3 = [+21.49, +113.08] — excludes zero on the positive side. **But n=2 is too small to draw conclusions** — the wide CI happens to start above zero, that's a sample-size artifact.

**Confirms reviewer's structural read**: trustworthy high-n cells have +3-5 bps base edges. A 10 bp cost eats that before OOS even starts. The cells fire SO rarely at 15m on tight n≥500 filtering that we can't get a powered test from 5 months of OOS.

## Track 3 — Voter overlay (the real result)

`historical_signals` schema (real, probed):
- Voter writes at minute granularity, often 5+ alerts within the same 15m bar for one setup
- OOS only goes back to **2026-04-01** (~7 weeks of overlap with classifier OOS)
- `timeframe_tag` ∈ {15m, 60m, 240m}; no 5m or 1m
- `trade_type` ∈ {call, put}; `signal_strength` 3-7

**Fix applied**: floor `entry_time` to TF boundary → signal bar; dedupe per (signal_bar, side) keeping highest strength.

### IWM 15m R=2.0

| filter | signals | filled | win% | net | net/trade | 95% CI net/trade |
|---|---|---|---|---|---|---|
| voter_only | 117 | 113 | 35.4% | -93 | **-0.82** | [-7.81, +6.18] |
| voter + agree, \|edge\|≥0.00 | 79 | 78 | 41.0% | -9 | -0.12 | [-8.58, +8.35] |
| voter + agree, \|edge\|≥0.10 | 71 | 71 | 40.8% | -13 | -0.18 | [-9.32, +8.96] |
| voter + agree, \|edge\|≥0.20 | 62 | 62 | 43.5% | +55 | **+0.88** | [-9.37, +11.13] |
| voter + agree, \|edge\|≥0.30 | 51 | 51 | 43.1% | +9 | +0.17 | [-11.69, +12.03] |
| voter + agree, \|edge\|≥0.50 | 36 | 36 | 47.2% | +122 | **+3.38** | [-12.41, +19.17] |

15m voter is approximately breakeven. Classifier filter shifts net positive but small (+4 bps lift from voter_only).

### IWM 60m R=2.0 — **the meaningful one**

| filter | signals | filled | win% | gross | net | net/trade | 95% CI net/trade |
|---|---|---|---|---|---|---|---|
| voter_only | 349 | 323 | 34.7% | +1,346 | -1,884 | **-5.83** | [-12.46, +0.80] |
| voter + agree, \|edge\|≥0.00 | 178 | 169 | 40.8% | +1,871 | +181 | **+1.07** | [-10.61, +12.75] |
| voter + agree, \|edge\|≥0.10 | 149 | 142 | 40.1% | +1,859 | +439 | **+3.09** | [-10.40, +16.59] |
| voter + agree, \|edge\|≥0.20 | 118 | 112 | 40.2% | +1,835 | +715 | **+6.38** | [-9.40, +22.17] |
| **voter + agree, \|edge\|≥0.30** | **97** | **93** | **40.9%** | **+1,780** | **+850** | **+9.14** | **[-9.34, +27.62]** |
| voter + agree, \|edge\|≥0.50 | 64 | 64 | 37.5% | +992 | +352 | +5.50 | [-17.06, +28.05] |

**What this says, plainly:**

1. **Voter alone at 60m loses money** on this 7-week OOS slice (net -5.83 bps/trade).
2. **Classifier agreement filter monotonically improves net up to |edge|≥0.30**, where it peaks at +9.14 bps/trade — a **+14.97 bps/trade lift** vs voter_only.
3. **Filtering at 0.20-0.30 retains 30-40% of signals** (118-97 of 349) — meaningful sample size kept.
4. **None of the CIs exclude zero**, but the effect size is consistent and the win-rate lift (35% → 41%) is robust across thresholds.
5. **At |edge|≥0.50**, the lift degrades — the filter is so restrictive (64 trades) the smaller sample dominates.

## Statistical power for "is this real?"

The +9.14 bps/trade lift at |edge|≥0.30 has SE = 9.43 bps over n=93. To reject the null at 95% with current effect size, we'd need n ≈ 370 trades — roughly 4x more OOS. With Apr-May 2026 producing 93 trades, that's ~28 additional weeks (7 months) of voter data.

**Forward expectation:** if the +9 bps lift is real, an additional 7 months of voter data should produce a CI that clears zero. If it's noise, the lift will regress toward zero.

## Where this lands the verdict

Updated narrative:

- **Standalone classifier as entry trigger**: closed. Indexing fix didn't rescue it. +7-8 gross, -2 net, CI spans zero. Not deployable.
- **Combo × regime as standalone signal**: closed. Trustworthy high-n cells have +3-5 bp edges that don't survive costs. Small-n cells were overfit and decisively fail OOS.
- **Voter overlay as filter**: **OPEN AND PROMISING.** 60m IWM shows a meaningful +14 bp lift from voter_only when adding |classifier_edge|≥0.30. Needs more OOS data to clear the statistical-significance bar, but the effect is consistent across thresholds.

## What to do next

1. **Forward-paper-trade** the voter+|edge|≥0.30 overlay on IWM 60m. Track daily P&L for ~4-7 months until n>250. If lift persists, productionize.
2. **Replicate on SPY/QQQ.** Same overlay logic, separate classifiers. If the lift is structural (classifier picking the right voter trades), it should generalize. If only IWM-specific, it's a fluke.
3. **Don't extend coverage of voter data backwards.** historical_signals only starts Apr 1 — the gap before that means we can't extend the OOS without backfilling the voter, which would be a separate large project.

## Artifacts

| Path | Purpose |
|---|---|
| `gcp/research/p7e_structural_backtest.py` | indexing-fixed structural backtest + `--min-n-cell` flag |
| `gcp/research/p7f_voter_overlay.py` | voter overlay with floor+dedupe + structural exit |
| `gs://.../research/p7e/iwm_15m_classifier-long_*.json` | indexing-fixed classifier-long |
| `gs://.../research/p7e/iwm_15m_combo-regime_*.json` | n≥500 combo test + n≥30 baseline |
| `gs://.../research/p7f/iwm_15m_R*.json`, `iwm_60m_R2.0_*.json` | overlay results |

## Cost

This session: ~$0.80 (1 image rebuild, 7 short Cloud Run jobs, 6 SQL dispatches).

Cumulative Phase 7: ~$18.
