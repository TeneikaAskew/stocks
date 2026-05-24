# Phase 7 — Multi-TF Strat-Sequence Dataset: Findings
**Date:** 2026-05-24
**Pipeline:** `gcp/research/p7_build_multi_tf_features.py` (build) → `gcp/research/p7_analyze_tf.py` (per-TF analysis, parallel) → this report

## TL;DR

(populated by inspecting the artifacts)

## 1. Model walk-forward summary (cross-TF view)

Mean IC + cost-adjusted Sharpe across 5 purged walk-forward folds per TF:

| TF | model | mean_IC | rank_IC | LS Sharpe | LS bps/day | LS win |
|---|---|---|---|---|---|---|
| 1m | lasso | 0.0193 | 0.0053 | -0.3014 | 0.226 | 0.4236 |
| 1m | lgbm | 0.0103 | 0.0063 | -2.7272 | -3.438 | 0.332 |
| 1m | ridge | 0.0192 | 0.0057 | -0.6126 | -0.23 | 0.4102 |
| 5m | lasso | 0.0219 | 0.0244 | 0.1748 | 0.726 | 0.4644 |
| 5m | lgbm | 0.0193 | 0.014 | -0.2012 | 0.15 | 0.4486 |
| 5m | ridge | 0.0209 | 0.0242 | 0.1198 | 0.622 | 0.459 |
| 15m | bayes_ridge | 0.027 | 0.03 | -0.2838 | 0.224 | 0.465 |
| 15m | elasticnet | 0.0266 | 0.0281 | 0.2634 | 1.82 | 0.4826 |
| 15m | lasso | 0.0264 | 0.0277 | 0.3098 | 1.966 | 0.4818 |
| 15m | lasso_sparse | 0.0271 | 0.0288 | 0.3028 | 1.898 | 0.4816 |
| 15m | lgbm | 0.023 | 0.0202 | 1.136 | 3.852 | 0.5066 |
| 15m | lgbm_shallow | 0.0217 | 0.0204 | 0.361 | 0.862 | 0.474 |
| 15m | pls10 | 0.0257 | 0.0282 | -1.489 | -3.968 | 0.4214 |
| 15m | pls5 | 0.0194 | 0.0242 | -0.4472 | -0.598 | 0.452 |
| 15m | ridge | 0.0232 | 0.0238 | 0.331 | 2.202 | 0.479 |
| 15m | ridge_strong | 0.0265 | 0.028 | 0.33 | 2.04 | 0.483 |
| 30m | bayes_ridge | 0.0267 | 0.0327 | 0.93 | 4.66 | 0.5038 |
| 30m | elasticnet | 0.029 | 0.0335 | 0.5208 | 2.544 | 0.4782 |
| 30m | lasso | 0.029 | 0.0335 | 0.572 | 2.772 | 0.4814 |
| 30m | lasso_sparse | 0.029 | 0.0338 | 0.5854 | 2.842 | 0.48 |
| 30m | lgbm | 0.0151 | 0.0164 | 1.1038 | 5.316 | 0.5034 |
| 30m | lgbm_shallow | 0.0268 | 0.0179 | 0.4812 | 1.946 | 0.4956 |
| 30m | pls10 | 0.0239 | 0.0292 | 0.9084 | 4.93 | 0.4994 |
| 30m | pls5 | 0.0215 | 0.0278 | 0.6756 | 3.7 | 0.4862 |
| 30m | ridge | 0.0296 | 0.0345 | 0.496 | 2.604 | 0.4784 |
| 30m | ridge_strong | 0.0293 | 0.0341 | 0.5426 | 2.648 | 0.4758 |
| 60m | bayes_ridge | 0.0235 | 0.0104 | 2.5912 | 12.766 | 0.548 |
| 60m | elasticnet | 0.0254 | 0.014 | 2.4898 | 12.114 | 0.5442 |
| 60m | lasso | 0.0254 | 0.0137 | 2.5194 | 12.252 | 0.546 |
| 60m | lasso_sparse | 0.0253 | 0.0135 | 2.522 | 12.342 | 0.545 |
| 60m | lgbm | 0.0351 | 0.0138 | 1.4168 | 6.472 | 0.5146 |
| 60m | lgbm_shallow | 0.032 | 0.0076 | 1.267 | 5.884 | 0.4944 |
| 60m | pls10 | 0.0213 | 0.0092 | 2.627 | 13.222 | 0.5452 |
| 60m | pls5 | 0.0163 | 0.0043 | 2.0444 | 11.306 | 0.5282 |
| 60m | ridge | 0.0262 | 0.0147 | 2.5756 | 12.52 | 0.5468 |
| 60m | ridge_strong | 0.0256 | 0.0145 | 2.4442 | 11.962 | 0.5416 |

## 2. Top features by LGBM gain (per TF)

### 1m

| rank | feature | gain |
|---|---|---|
| 1 | `vix_close` | 34056797 |
| 2 | `price_vs_vwap` | 29426802 |
| 3 | `distance_to_gate_pct` | 28142297 |
| 4 | `rvol` | 27442628 |
| 5 | `distance_to_king_pct` | 26973869 |
| 6 | `macd_signal` | 26081054 |
| 7 | `bb_width` | 21267010 |
| 8 | `rvol_10` | 21047247 |
| 9 | `atr_14` | 18374143 |
| 10 | `macd_histogram` | 17782639 |

### 5m

| rank | feature | gain |
|---|---|---|
| 1 | `vix_close` | 74460310 |
| 2 | `rvol` | 50676236 |
| 3 | `rvol_10` | 36866484 |
| 4 | `atr_14` | 28417200 |
| 5 | `distance_to_gate_pct` | 27671828 |
| 6 | `macd_signal` | 26660500 |
| 7 | `distance_to_king_pct` | 26448898 |
| 8 | `price_vs_vwap` | 26168776 |
| 9 | `total_vex` | 18532409 |
| 10 | `obv` | 16893117 |

### 15m

| rank | feature | gain |
|---|---|---|
| 1 | `vix_close` | 185221203 |
| 2 | `price_vs_vwap` | 65073190 |
| 3 | `macd_signal` | 57900831 |
| 4 | `bb_width` | 56625853 |
| 5 | `macd_histogram` | 48869927 |
| 6 | `rvol` | 44140023 |
| 7 | `distance_to_gate_pct` | 41976428 |
| 8 | `atr_14` | 39629192 |
| 9 | `total_gex` | 38649551 |
| 10 | `stoch_rsi_d` | 34986907 |

### 30m

| rank | feature | gain |
|---|---|---|
| 1 | `vix_close` | 256179621 |
| 2 | `bb_width` | 70580019 |
| 3 | `macd` | 60697596 |
| 4 | `macd_signal` | 57739986 |
| 5 | `total_gex` | 55797880 |
| 6 | `atr_14` | 54321181 |
| 7 | `total_vex` | 51434467 |
| 8 | `price_vs_vwap` | 48250128 |
| 9 | `distance_to_king_pct` | 47494463 |
| 10 | `distance_to_gate_pct` | 46149552 |

### 60m

| rank | feature | gain |
|---|---|---|
| 1 | `vix_close` | 381891754 |
| 2 | `stoch_rsi_d` | 88531703 |
| 3 | `atr_14` | 77939953 |
| 4 | `distance_to_king_pct` | 74271336 |
| 5 | `macd_histogram` | 74244038 |
| 6 | `macd_signal` | 71109400 |
| 7 | `total_vex` | 70456210 |
| 8 | `bb_width` | 63671339 |
| 9 | `total_gex` | 62726013 |
| 10 | `obv` | 58850245 |


## 3. Strat-combo predictability per TF (top 5 by |hit_pct - 50|)

### 1m — top extreme cells (prev → curr → fwd hit%)

| ticker | prev | curr | n | mean_bps | hit_pct |
|---|---|---|---|---|---|
| IWM | X | 2U | 1 | 8.14 | 100.00 |
| SPY | X | 2D | 1 | -5.25 | 0.00 |
| QQQ | X | 2D | 1 | 7.33 | 100.00 |
| SPY | 3 | 2D | 28195 | 0.17 | 51.76 |
| QQQ | 3 | 2D | 28894 | 0.37 | 51.57 |
| SPY | 2D | 2D | 165252 | 0.29 | 51.52 |
| SPY | 1 | 2D | 64853 | 0.16 | 51.29 |
| QQQ | 2D | 2D | 166293 | 0.27 | 51.28 |

### 5m — top extreme cells (prev → curr → fwd hit%)

| ticker | prev | curr | n | mean_bps | hit_pct |
|---|---|---|---|---|---|
| IWM | X | 2U | 1 | -56.92 | 0.00 |
| SPY | X | 1 | 1 | -37.95 | 0.00 |
| QQQ | X | 2D | 1 | -24.46 | 0.00 |
| QQQ | 3 | 3 | 29 | 18.58 | 75.86 |
| QQQ | 1 | 1 | 72 | 1.45 | 56.94 |
| QQQ | 1 | 3 | 169 | 3.29 | 56.80 |
| SPY | 3 | 3 | 716 | 0.86 | 55.59 |
| QQQ | 3 | 2D | 283 | 5.86 | 55.12 |

### 15m — top extreme cells (prev → curr → fwd hit%)

| ticker | prev | curr | n | mean_bps | hit_pct |
|---|---|---|---|---|---|
| IWM | X | 2D | 1 | -113.58 | 0.00 |
| SPY | X | 2D | 1 | -64.43 | 0.00 |
| QQQ | X | 2D | 1 | -69.65 | 0.00 |
| QQQ | 1 | 1 | 506 | 2.41 | 60.87 |
| QQQ | 2D | 1 | 3335 | 0.69 | 56.07 |
| QQQ | 1 | 2D | 3111 | 4.15 | 55.64 |
| IWM | 3 | 3 | 272 | 6.53 | 55.51 |
| QQQ | 2U | 2D | 7824 | 1.48 | 55.18 |

### 30m — top extreme cells (prev → curr → fwd hit%)

| ticker | prev | curr | n | mean_bps | hit_pct |
|---|---|---|---|---|---|
| IWM | X | 2D | 1 | -1.82 | 0.00 |
| SPY | X | 2D | 1 | -2.50 | 0.00 |
| QQQ | X | 2D | 1 | 26.67 | 100.00 |
| QQQ | 3 | 1 | 574 | 8.65 | 59.76 |
| QQQ | 2U | 3 | 1344 | 4.87 | 57.14 |
| QQQ | 1 | 2D | 1548 | 6.43 | 57.11 |
| QQQ | 3 | 3 | 144 | 7.82 | 56.94 |
| QQQ | 2D | 3 | 977 | 8.13 | 56.91 |

### 60m — top extreme cells (prev → curr → fwd hit%)

| ticker | prev | curr | n | mean_bps | hit_pct |
|---|---|---|---|---|---|
| IWM | X | 2D | 1 | 42.91 | 100.00 |
| SPY | X | 2D | 1 | 92.90 | 100.00 |
| QQQ | X | 2D | 1 | 104.19 | 100.00 |
| QQQ | 3 | 3 | 70 | 14.39 | 61.43 |
| SPY | 3 | 3 | 82 | 5.18 | 60.98 |
| QQQ | 1 | 3 | 281 | 13.51 | 59.79 |
| QQQ | 3 | 2U | 681 | 11.71 | 59.77 |
| QQQ | 2U | 1 | 917 | 12.58 | 59.11 |


## 4. Strat-combo × dealer_regime (3×3 GEX × VEX grid) — top edges per TF

### 1m

| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |
|---|---|---|---|---|---|---|---|
| QQQ | 111_inside_compression | GEX_LOW_VEX_HIGH | 127 | 38.58 | 30.71 | 46.46 | -0.79 |
| SPY | 111_inside_compression | GEX_MID_VEX_MID | 135 | 60.74 | 52.59 | 68.89 | 1.70 |
| SPY | 32_bear_reversal | GEX_LOW_VEX_HIGH | 185 | 60.54 | 53.51 | 67.57 | 1.63 |
| IWM | 212_bear_reversal | GEX_nan_VEX_nan | 58 | 60.34 | 48.28 | 74.14 | 1.67 |
| QQQ | 111_inside_compression | GEX_HIGH_VEX_MID | 79 | 59.49 | 48.10 | 70.28 | 1.34 |
| SPY | 212_bull_continuation | GEX_nan_VEX_nan | 68 | 58.82 | 47.06 | 69.89 | 1.29 |
| IWM | 111_inside_compression | GEX_LOW_VEX_MID | 106 | 58.49 | 49.06 | 68.87 | -0.05 |
| QQQ | 132_bear_continuation | GEX_MID_VEX_MID | 914 | 57.55 | 54.21 | 61.00 | 1.47 |
| SPY | 22_bear_continuation | GEX_nan_VEX_nan | 310 | 57.42 | 52.09 | 63.07 | 1.86 |
| IWM | 32_bear_reversal | GEX_MID_VEX_LOW | 261 | 57.09 | 50.96 | 63.60 | 0.96 |

### 5m

| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |
|---|---|---|---|---|---|---|---|
| SPY | 22_bear_continuation | GEX_nan_VEX_nan | 60 | 68.33 | 56.67 | 80.00 | 5.92 |
| SPY | 32_bear_reversal | GEX_HIGH_VEX_MID | 102 | 61.76 | 51.96 | 72.08 | 3.96 |
| QQQ | 322_bear_continuation | GEX_LOW_VEX_LOW | 60 | 38.33 | 26.67 | 50.00 | -4.73 |
| SPY | 132_bull_continuation | GEX_HIGH_VEX_LOW | 198 | 61.62 | 54.28 | 68.18 | 2.52 |
| SPY | 212_bear_continuation | GEX_MID_VEX_HIGH | 320 | 60.94 | 55.94 | 66.25 | 3.88 |
| SPY | 212_bear_continuation | GEX_HIGH_VEX_MID | 445 | 60.90 | 56.29 | 64.94 | 1.83 |
| QQQ | clean_2d_bear | GEX_LOW_VEX_LOW | 66 | 39.39 | 28.79 | 51.52 | -1.86 |
| SPY | 32_bear_reversal | GEX_LOW_VEX_MID | 98 | 60.20 | 50.48 | 69.92 | 3.66 |
| SPY | 32_bull_reversal | GEX_HIGH_VEX_HIGH | 82 | 59.76 | 50.00 | 70.73 | 3.07 |
| SPY | 32_bear_reversal | GEX_MID_VEX_MID | 139 | 59.71 | 51.08 | 66.91 | 6.15 |

### 15m

| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |
|---|---|---|---|---|---|---|---|
| IWM | 132_bear_continuation | GEX_HIGH_VEX_MID | 53 | 71.70 | 60.38 | 84.91 | 43.72 |
| QQQ | 312_bull_reversal | GEX_HIGH_VEX_HIGH | 52 | 69.23 | 56.68 | 81.78 | 4.94 |
| IWM | 212_bear_continuation | GEX_MID_VEX_LOW | 82 | 68.29 | 58.54 | 78.05 | 10.79 |
| QQQ | 132_bear_continuation | GEX_HIGH_VEX_LOW | 75 | 68.00 | 57.33 | 77.33 | 5.56 |
| QQQ | clean_2d_bear | GEX_HIGH_VEX_MID | 96 | 66.67 | 57.29 | 75.00 | 7.78 |
| SPY | 132_bull_continuation | GEX_LOW_VEX_LOW | 60 | 66.67 | 55.00 | 78.33 | 15.02 |
| QQQ | 11_inside_compression | GEX_HIGH_VEX_HIGH | 63 | 66.67 | 53.97 | 77.78 | 2.81 |
| QQQ | 212_bear_continuation | GEX_HIGH_VEX_HIGH | 97 | 65.98 | 56.70 | 74.23 | 5.97 |
| SPY | 212_bull_continuation | GEX_MID_VEX_LOW | 108 | 65.74 | 56.48 | 74.07 | 9.02 |
| QQQ | clean_2d_bear | GEX_HIGH_VEX_HIGH | 96 | 65.62 | 56.25 | 75.00 | 7.57 |

### 30m

| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |
|---|---|---|---|---|---|---|---|
| SPY | clean_2u_bull | GEX_MID_VEX_LOW | 54 | 72.22 | 61.11 | 83.33 | 22.58 |
| SPY | 212_bull_continuation | GEX_MID_VEX_LOW | 54 | 70.37 | 57.41 | 81.48 | 10.45 |
| IWM | 212_bull_continuation | GEX_MID_VEX_MID | 74 | 70.27 | 60.81 | 81.08 | 19.13 |
| SPY | 212_bear_reversal | GEX_HIGH_VEX_LOW | 107 | 65.42 | 57.01 | 73.83 | 10.92 |
| QQQ | 312_bull_reversal | GEX_MID_VEX_HIGH | 71 | 64.79 | 54.19 | 76.06 | 12.76 |
| QQQ | 212_bear_reversal | GEX_LOW_VEX_HIGH | 59 | 64.41 | 52.54 | 76.27 | 15.39 |
| SPY | 212_bear_continuation | GEX_HIGH_VEX_LOW | 75 | 64.00 | 52.00 | 74.67 | 6.57 |
| SPY | clean_2u_bull | GEX_MID_VEX_HIGH | 58 | 63.79 | 53.45 | 75.86 | 9.36 |
| QQQ | 322_bull_continuation | GEX_MID_VEX_MID | 80 | 63.75 | 53.09 | 73.75 | 4.55 |
| SPY | 322_bear_continuation | GEX_LOW_VEX_LOW | 80 | 63.75 | 53.09 | 73.16 | 16.27 |

### 60m

| ticker | combo | dealer_regime | n | hit_pct | ci_lo | ci_hi | mean_bps |
|---|---|---|---|---|---|---|---|
| QQQ | 322_bull_continuation | GEX_HIGH_VEX_LOW | 53 | 71.70 | 58.49 | 83.02 | 19.88 |
| SPY | 212_bull_reversal | GEX_LOW_VEX_LOW | 55 | 67.27 | 56.36 | 80.00 | 38.39 |
| IWM | 212_bull_reversal | GEX_HIGH_VEX_MID | 54 | 66.67 | 53.70 | 79.63 | 9.04 |
| QQQ | 212_bear_reversal | GEX_MID_VEX_HIGH | 107 | 64.49 | 56.07 | 73.83 | 22.17 |
| SPY | 212_bear_reversal | GEX_HIGH_VEX_HIGH | 61 | 63.93 | 52.46 | 75.41 | 14.45 |
| SPY | none | GEX_MID_VEX_LOW | 304 | 62.17 | 56.25 | 66.95 | 10.75 |
| SPY | 212_bull_reversal | GEX_LOW_VEX_MID | 58 | 62.07 | 50.00 | 74.14 | 16.05 |
| QQQ | clean_2u_bull | GEX_LOW_VEX_MID | 52 | 61.54 | 48.08 | 73.08 | 3.57 |
| SPY | 322_bull_continuation | GEX_HIGH_VEX_MID | 52 | 61.54 | 48.08 | 75.00 | -3.71 |
| QQQ | clean_2u_bull | GEX_MID_VEX_HIGH | 70 | 61.43 | 50.00 | 72.86 | 18.77 |

