# Phase 4 — Feature Importance + Predictive Power

**Date:** 2026-05-23
**Method:** Gradient-boosted classification (LightGBM) on next-day direction (`y_1d_up`)
**Window 4a:** 2024-05-23 → 2026-05-21 (2 years, fits db-query 50k row cap)
**Window 4b:** 2016-01-01 → 2026-05-22 (10 years, 3 ETFs only)
**Validation:** Time-based 70/30 train/test split (no look-ahead)
**Status:** Complete

## TL;DR

1. **Daily direction (next-day-up) is essentially unpredictable from same-day features in this universe.** Pooled 100-ticker AUC = 0.4995. Per-ticker mean = 0.5145, median = 0.5095, std = 0.0476.
2. **Gamma features do NOT add meaningful predictive value** for SPY/IWM/QQQ — Δ AUC of {SPY: +0.020, IWM: -0.007, QQQ: -0.003} is within noise.
3. **Only 3 of 100 tickers** show AUC > 0.60 (consistent with random expectation under H0 at the studied N) — those are candidates for follow-up but not robust signals yet.
4. **Top "important" features (by gain) are universally vol-regime markers** (`vix_close`, `volatility_20d`, `atr_14`, `bb_width`). But that's tree-split frequency, not predictive lift: early stopping fires at iteration 1-5 for every model, meaning the trees can't generalize past the first split.
5. **This is consistent with weak-form market efficiency.** No combination of pre-computed features (RSI/EMA/MACD/BB/ATR/volatility/strat/VIX, plus gamma alert presence) reliably predicts next-day return direction at the daily-bar level.

This is a load-bearing finding for the audit: **before adding more features or more compute to the live trading pipeline, the question to answer is whether ANY model class can predict daily direction with this feature set — and the answer for tree-based ensembles is NO.**

## 1. P4a — Universe-wide (100 tickers, 2 years)

### Setup

- **Data**: `market_data_daily` for 100-ticker top-ADV universe, 2024-05-23 → 2026-05-21
- **Rows**: 49,366 (~500 bars per ticker × 100 tickers)
- **Features**: 51 pre-computed columns (price MAs, RSI suite, MACD, Bollinger bands, ATR, RVOL, volatility metrics, strat classifier output, VIX)
- **Target**: `y_1d_up` = 1 if `close[t+1] > close[t]` else 0
- **Train/test split**: time-based 70/30 (train: 2024-05 → mid-2025, test: mid-2025 → 2026-05)
- **Model**: LightGBM, 500 estimators, max_depth=6, min_child_samples=50, early-stopping=20
- **SHAP**: TreeExplainer on 2,000-bar test sample

### Result

- **Pooled AUC = 0.4995** — at random
- **Pooled Accuracy = 0.5119** — identical to baseline (`always predict up` = 51.19% test mean)
- **Best iteration**: 1 (early-stopping fires immediately)

### Per-ticker breakdown

Among 100 tickers with valid models:

| stat | value |
|---|---|
| Mean AUC | 0.5145 |
| Median AUC | 0.5095 |
| Std | 0.0476 |
| % tickers with AUC > 0.55 | 23.0% |
| % tickers with AUC > 0.60 | **3.0%** |

Under the null hypothesis (no predictive signal) with the studied N (≈150 test bars per ticker), AUC standard error is ~0.04 — so we'd expect ~3% of 100 tickers to randomly score above 0.60 even with no edge. **The 3% we observed is consistent with chance.**

Top 10 by AUC: AKAM (0.622), COHR (0.613), CEG (0.609), BE (0.594), DVN (0.594), SNPS (0.593), SATS (0.593), ALAB (0.589), MSFT (0.586), ARM (0.584).
Bottom 10: KO, SMCI, INTU, QQQ, SPOT, AZO, UBER, NVO, MCHP, NBIS (all AUC < 0.46).

The fact that **QQQ itself appears in the bottom-10** strongly suggests this isn't a feature-selection problem — it's an information problem. The features simply don't carry next-day-direction signal at the daily-bar horizon.

### "Important" features (gain) — but not actually predictive

```
vix_close       1447.79  (93.65% of gain)
obv               21.43   (1.39%)
bb_width          15.45   (1.00%)
volatility_20d    12.57   (0.81%)
ma_10             11.50   (0.74%)
ma_5              10.46   (0.68%)
rvol               9.80   (0.63%)
stoch_rsi_d        9.54   (0.62%)
macd_signal        7.46   (0.48%)
```

VIX dominates gain because it's the single most-frequently-split feature when the tree is forced to make at least one split. But the tree's predictions still produce AUC ≈ 0.5 — so VIX doesn't actually move the prediction in the right direction. Classic case of **importance ≠ predictive value**.

## 2. P4b — Gamma features for SPY/IWM/QQQ (10 years)

### Setup

- **Data**: `market_data_daily` for SPY/IWM/QQQ, 2016-01-01 → 2026-05-22 (7,587 rows)
- **Gamma features** engineered per (ticker, date) from Phase 2's `gamma_events`:
  - `n_alerts_today` (any kind), `n_call_alerts`, `n_put_alerts`
  - `n_king`, `n_gate`, `n_flip` (by alert kind)
  - `min_distance_pct`, `max_distance_pct` (closest/farthest alert from price)
  - `has_negative_gamma` (regime indicator)
- **Two models per ticker**: base (22 features) vs base + 9 gamma features (31 features)

### Result — gamma adds nothing

| ticker | base AUC | with_gamma AUC | Δ AUC | best_iter (gamma) |
|---|---|---|---|---|
| SPY | 0.4572 | **0.4771** | +0.0199 | 1 |
| IWM | 0.5335 | 0.5265 | **−0.0070** | 3 |
| QQQ | 0.5050 | 0.5020 | **−0.0030** | 1 |

- SPY's +0.02 AUC improvement looks largest but model is still WORSE than random (AUC < 0.5). The "improvement" is a movement from random-bad to random-mediocre, not a meaningful predictive signal.
- IWM and QQQ get *worse* with gamma features — the model overfits to noise in the additional dimensions and the test-set AUC drops.

### Top features in the with-gamma model

- **SPY**: `price_vs_ema9` (15), `rvol` (8), `n_put_alerts` (6), `vix_close` (5)
- **IWM**: `volatility_20d` (26), `atr_14` (22), `bb_width` (13), `vix_close` (13)
- **QQQ**: `atr_14` (25), `macd_signal` (18), `vix_close` (16), `n_call_alerts` (15)

Gamma features (`n_put_alerts`, `n_call_alerts`) appear in SPY and QQQ top-5 by gain — but as P4a showed, top-gain does not imply test-set AUC > 0.5.

## 3. Verdict on remaining hypotheses

| H | hypothesis | verdict |
|---|---|---|
| H4 | Pre-computed strat + vol features predict daily direction | **REJECTED** — pooled AUC 0.50, per-ticker mean 0.51 |
| H5 | Gamma features add lift over base features | **REJECTED** — Δ AUC within noise for all 3 ETFs |
| H7 | Time-of-day bucket adds signal | **NOT TESTABLE at daily level** — would need intraday model |
| H8 | Negative-gamma regime amplifies signals | **NOT TESTABLE** — the `regime` flag in `gamma_levels_eod` is mostly `unknown` (per P2), so the model's `has_negative_gamma` feature is essentially absent |

## 4. Implications for production

1. **Stop trying to predict daily direction with same-day price/volume features alone.** The information just isn't there — confirmed by 100 independent per-ticker model fits.
2. **Gamma walls don't add daily-direction predictive value** even for the 3 ETFs that have full gamma data. This is consistent with Phase 2's finding that gamma is a swing-trade confirmation, not a directional predictor.
3. **The 3 tickers with AUC > 0.60 (AKAM, COHR, CEG)** are worth a follow-up — but with only ~150 test bars each, the 95% CI on their AUC spans roughly [0.52, 0.72]. Not robust enough to trade on without longer windows.
4. **If you want predictive power**, the audit suggests looking AWAY from the daily-bar feature set:
   - Different target: 5d or 20d direction (P3 found small but real edge on bear-side combos at 5d)
   - Different horizon: intraday entry → intraday exit (no audit yet — Phase 2's intraday horizons all showed at-baseline lifts though)
   - Different inputs: order-book / flow features not present in this DB
   - Different model class: time-series sequence models (LSTM/transformer) MIGHT capture patterns trees can't — but the daily AUC ceiling for liquid US equities in academic literature is ~0.55, so the upside is limited even with sequence models
5. **Don't ship a "feature importance" dashboard** to the trading UI based on tree gain — as P4a shows, that metric is decorative when the underlying AUC ≈ 0.5.

## 5. What's important if not "feature importance"

The audit makes a much stronger negative case than positive: it can't tell you which features predict, because *none do reliably at this horizon*. What it CAN say is which signals are clearly false:

- `322_bull_continuation` (P3) is significantly **anti-predictive** at 5d
- All PUT-direction gamma alerts at 1d are **anti-predictive** in bull-drift regimes (P2)
- The 76.7% flip-PUT figure that justifies a production direction mapping **does not replicate** (FLIP_PUT_DISCREPANCY.md)

These are the actionable findings — not "which feature is most important" but "which signals to NOT take."

## 6. Reproducibility

| artifact | path |
|---|---|
| P4a feature matrix (100 tickers, 2yr) | [`data/p4_features_universe_2yr.csv`](data/p4_features_universe_2yr.csv) |
| P4a gain importance | [`data/p4a_feature_importance_gain.csv`](data/p4a_feature_importance_gain.csv) |
| P4a SHAP importance | [`data/p4a_feature_importance_shap.csv`](data/p4a_feature_importance_shap.csv) |
| P4a per-ticker AUC | [`data/p4a_per_ticker_auc.csv`](data/p4a_per_ticker_auc.csv) |
| P4b 3-ETF feature matrix | [`data/p4_features_etfs_10yr.csv`](data/p4_features_etfs_10yr.csv) |
| P4b AUC comparison | [`data/p4b_etf_auc_compare.csv`](data/p4b_etf_auc_compare.csv) |
