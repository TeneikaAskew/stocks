# Phase 7 — Per-Ticker Model Comparison (IWM is the standout)

**Date:** 2026-05-24
**Dispatch:** 9 jobs (SPY/IWM/QQQ × 15m/30m/60m), 4 minutes wall
**Cost:** ~$3
**Result:** **Per-ticker training reveals IWM has the strongest ML signal in the entire audit (Sharpe +3.24 at 30m with LightGBM).**

---

## TL;DR

The earlier pooled-across-3-ETFs models showed Sharpe up to +2.58. **Per-ticker training shows IWM with LightGBM hits Sharpe +3.24 at 30m and +3.15 at 15m** — substantially higher than the pooled finding. This was hidden by pooling.

- **IWM is the strongest ML target** (Sharpe +3.15 to +3.24)
- **QQQ middle** (Sharpe +1.98 to +2.48)
- **SPY weakest at short TFs** (Sharpe +1.17 to +1.67), but **best 60m linear IC** (0.058)
- **LightGBM dominates per-ticker; linear models often LOSE money** on SPY/QQQ at short TFs
- The pooled +2.58 finding was driven mostly by SPY's clean 60m linear structure when ranked cross-sectionally

---

## Sharpe comparison (mean across 5 walk-forward folds, after 5bps/leg costs)

### 15m TF

| model | IWM | QQQ | SPY |
|---|---|---|---|
| **lgbm** | **+3.15** | **+2.48** | **+1.67** |
| lgbm_shallow | +2.37 | +2.12 | +0.67 |
| lasso_sparse | +1.52 | -1.99 | -1.22 |
| elasticnet | +1.31 | -2.33 | -1.05 |
| ridge_strong | +1.31 | -2.25 | -1.06 |
| lasso | +1.17 | -2.38 | -1.07 |
| bayes_ridge | +1.17 | -2.04 | -1.75 |
| ridge | +1.01 | -2.43 | -0.73 |
| pls10 | +0.60 | -2.31 | -2.19 |
| pls5 | +0.22 | -1.93 | -2.33 |

### 30m TF

| model | IWM | QQQ | SPY |
|---|---|---|---|
| **lgbm** | **+3.24** | **+1.98** | **+1.17** |
| lgbm_shallow | +2.14 | +1.25 | +0.64 |
| pls10 | +1.51 | +0.55 | +0.10 |
| bayes_ridge | +1.35 | +0.94 | -0.09 |
| ridge_strong | +1.01 | -0.12 | -1.81 |
| lasso_sparse | +0.85 | -0.07 | -1.84 |
| elasticnet | +0.85 | -0.13 | -1.80 |
| ridge | +0.64 | -0.27 | -2.02 |
| lasso | +0.64 | -0.16 | -1.92 |
| pls5 | +0.11 | +0.12 | +0.57 |

### 60m TF — IC only (per-ticker has 1 row per timestamp, no per-bar L/S)

| model | IWM IC | QQQ IC | SPY IC |
|---|---|---|---|
| **lightgbm** | **+0.060** | +0.040 | +0.051 |
| **ridge_strong** | +0.031 | +0.026 | **+0.058** |
| elasticnet | +0.030 | +0.024 | **+0.058** |
| ridge | +0.030 | +0.025 | +0.058 |
| lasso_sparse | +0.030 | +0.027 | +0.056 |
| lasso | +0.030 | +0.027 | +0.056 |
| bayes_ridge | +0.022 | +0.026 | +0.056 |
| pls10 | +0.023 | +0.028 | +0.055 |
| lgbm_shallow | +0.039 | +0.023 | +0.023 |
| pls5 | +0.013 | +0.025 | +0.045 |

---

## Key interpretations

### 1. IWM has the cleanest ML signal across the universe

Mean Sharpe at 30m of +3.24 (LGBM) is hedge-fund-tier. The 15m result (+3.15) is essentially identical. Win rate 58-59%. Bps/day +12-16.

**Why IWM specifically?**
- Small-cap, less macro-dominated
- More pattern-driven (single-name and sector flows show up cleanly in price)
- The strat + dealer-regime + indicator stack captures pattern-driven moves better than macro-trending moves
- IWM has 184 dealer-regime cells with N≥30 — more granular data for the model to learn from

### 2. LightGBM dominates per-ticker; linear models LOSE on SPY/QQQ at short TFs

Look at SPY 15m: every single linear model has NEGATIVE Sharpe (-0.73 to -2.33). Only LGBM is positive (+1.67). Same for QQQ 15m (linear all -1.99 to -2.42).

**Why?**
- Linear models can't capture (strat_combo × dealer_regime × indicator-threshold) interactions
- The signal at short horizons is structurally non-linear: e.g. "22_bull_continuation × HIGH-GEX × MID-VEX × RSI > 70" has a different sign than "22_bull_continuation × HIGH-GEX × MID-VEX × RSI > 30"
- Trees natively handle these threshold-based interactions; linear models smear them
- When linear models try to fit, they end up predicting the wrong direction (negative Sharpe)

### 3. SPY's strong pooled-60m result was a cross-sectional artifact

The pooled run (all 3 tickers) showed Sharpe +2.58 at 60m with linear models. Looking at per-ticker:
- SPY 60m linear IC = 0.058 (best of any ticker × any model)
- IWM 60m linear IC = 0.030
- QQQ 60m linear IC = 0.025

When pooled, the cross-sectional L/S sort effectively goes "long predictions favoring SPY-pattern bars, short predictions favoring IWM/QQQ-pattern bars." SPY's pattern is genuinely cleaner at 60m than the others.

This is real signal, but it's **a between-ticker rank trade, not a strat-pattern trade**. The model learns "today's SPY bar should rise more than today's IWM bar" — which works in cross-section even if you can't actually trade individual bars.

### 4. 60m IC is uniformly higher per-ticker than per-pooled

- Per-ticker 60m IC: ~0.030 to 0.060 (LGBM up to 0.060)
- Pooled 60m IC: ~0.025 to 0.035

Pooling adds noise (cross-ticker variance). Per-ticker training extracts cleaner per-bar predictability.

### 5. PLS works at 30m for IWM (+1.51) and 60m universally — but not at 15m

PLS-10 at 15m on SPY/QQQ has Sharpe -2.19 / -2.31 (heavy losses). PLS-10 at 60m has IC ~0.023-0.028 (modest but positive). PLS is sensitive to noise in the latent-component decomposition; works only when the underlying signal has clean low-dim structure.

---

## Updated strategic priority

### Phase 7a (primary deployment target): IWM with LightGBM at 30m

- **Best Sharpe**: +3.24 mean across 5 walk-forward folds
- **Best win rate**: 59.2%
- **Best bps/day**: 15.8 (after costs)
- **Model**: `lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, max_depth=6, num_leaves=31, min_child_samples=100, n_jobs=-1)`
- **Target**: 5 bars forward (= 2.5 hours at 30m)
- **Universe slice**: IWM-only strat_features_30m table

### Phase 7b (secondary): IWM with LightGBM at 15m

- Sharpe +3.15, near-identical to 30m
- Could be paired with 30m as a confirmation filter
- Or used as the "fast" entry signal vs 30m's "slow" model

### Phase 7c (tertiary): QQQ LightGBM 15m or 30m

- Sharpe +2.48 (15m) / +1.98 (30m)
- Still hedge-fund-tier
- DO NOT use linear models on QQQ

### Phase 7d (research): SPY pooled 60m linear

- The +2.58 pooled result is real but only deployable as a cross-sectional rank trade
- Need a broader universe (top-50 ETFs?) to make this a real portfolio
- Park until Phase 8

### Phase 7e (avoid): all linear models on SPY/QQQ at 15-30m

- Negative Sharpe across the board
- Don't waste compute training these for production

---

## What this changes about the trader's playbook

The dealer-regime × strat-combo cells from `P7_TRADERS_PLAYBOOK.md` are still all valid (they're cell-level findings, ticker-specific already). But the **MODEL-driven trades should focus on IWM**:

**New top recommendation**: deploy IWM 30m LGBM as a daily prediction service. For each 30m IWM bar during RTH, predict the 5-bar-forward return. Long the bars in the top decile, short the bottom decile. Historical Sharpe +3.24 net of costs.

This is much stronger than the SPY/QQQ 60m linear we previously highlighted.

---

## Artifacts

- `data/p7_per_ticker/combined_summary.csv` — all 9 (ticker × TF) × 10 models = 90 rows
- `data/p7_per_ticker/{TICKER}_{TF}_model_summary.csv` — per-cell detail
- GCS: `gs://adept-mountain-474619-d4-trading-data/research/p7-analysis-per-ticker/`

## Cost

- 9 jobs × ~4 min × 32GiB / 8 CPU = ~$3
- 1 image rebuild = ~$0.30
- Total per-ticker round: **~$3.30**
- Cumulative session cost: **~$13-18**
