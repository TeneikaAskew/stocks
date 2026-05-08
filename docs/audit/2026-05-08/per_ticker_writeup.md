# Per-Ticker Calibration Writeup

_Generated: 2026-05-08T16:30:12Z_


## Side-by-side comparison

| Metric | SPY | IWM | QQQ |
|---|---|---|---|
| call_rsi_range | (35.5, 50.5) | (36.2, 50.2) | (35.4, 50.5) |
| put_rsi_range | (50.5, 64.3) | (50.2, 63.7) | (50.5, 65.1) |
| call_target | 0.00184 | 0.00281 | 0.00301 |
| put_target | 0.00202 | 0.00249 | 0.00238 |
| call_stop | 0.00075 | 0.00077 | 0.00075 |
| put_stop | 0.00075 | 0.001 | 0.00075 |
| call_time_stop | 25 | 20 | 20 |
| put_time_stop | 25 | 25 | 25 |
| preferred_strategy_call | mean_reversion | mean_reversion | mean_reversion |
| preferred_strategy_put | mean_reversion | mean_reversion | mean_reversion |
| preferred_timeframe_call | 30m | 60m | 30m |
| preferred_timeframe_put | 60m | 15m | 60m |
| min_conditions_momentum | None | None | None |
| min_conditions_mr | None | None | None |
| n_signals_used | 555 | 493 | 544 |
| n_signals_with_intraday | 545 | 488 | 536 |


**Defaults today (from `lib/config.py:ExitConfig` and `lib/strategies/config.py`):**

- CALL: target +0.30%, stop -0.15%, time-stop 30min, RSI (25, 50)
- PUT:  target +0.38%, stop -0.20%, time-stop 35min, RSI (50, 75)
- MIN_CONDITIONS_MOMENTUM=5, MIN_CONDITIONS=3 (mean-rev)


## SPY — root-cause writeup

- **Signals available**: 555 (lookback 90d through 2026-05-08)
- **Signals with intraday outcome**: 545
- **Overall win-rate at global config**: 7.2%
- **Win-rate by direction**: CALL 8.3% (n=240), PUT 6.2% (n=305)
- **Time-stop hit rate** (means trade ran to time without target/stop): 64.0%
- **Median MFE / MAE on triggered side**: CALL MFE 0.096% / MAE -0.127%, PUT MFE 0.104% / MAE -0.083%
- **Strategy mix observed**: mean_reversion=100%
- **brief_alignment coverage**: n=0 alerts have a non-NULL alignment tag.
- **brief_alignment win-rate**: insufficient (n<10)
- **Notes**: mean_reversion: no score bucket net-positive; best is score=4 net_mean=-0.0622%

### SPY — multi-timeframe regime analysis (RTH-only)

| timeframe | bar_return_mean% | bar_return_std% | autocorr_lag1 | n_bars | regime |
|---|---|---|---|---|---|
| 1m | 0.0008 | 0.0498 | 0.0038 | 13649 | mixed |
| 5m | 0.0041 | 0.1093 | 0.0365 | 2729 | mixed |
| 15m | 0.0122 | 0.1878 | 0.0365 | 909 | mixed |
| 30m | 0.0241 | 0.2608 | 0.0948 | 454 | momentum |
| 60m | 0.0448 | 0.3588 | 0.0294 | 244 | mixed |
| 240m | 0.1599 | 0.6439 | 0.1672 | 69 | momentum |

_autocorr_lag1 sign tells you which strategy class the timeframe favors: positive → momentum (trends persist); negative → mean-reversion (returns flip)._

### SPY — counterfactual replay: recommended config vs global default

- Replayed **545** alerts under both configs (same alerts, different exit rules).
- **Win-rate**: global 7.2% → recommended 16.1% (Δ +9.0 pp)
- **Mean per-trade return**: global +0.0023% → recommended +0.0048% (Δ +0.0025 %)
- _Win-rate goes UP because targets are tighter (more often reached); per-trade return is the apples-to-apples economic comparison after slippage._

### SPY — factor fire-rate × discrimination

| condition | fire_rate% | n_fired | win_when_fired% | win_when_absent% | discrimination_pp | verdict |
|---|---|---|---|---|---|---|
| near_below_emas | 22.8 | 124 | 12.1 | 5.7 | 6.4 | KEEP |
| rsi_oversold_zone | 35.8 | 195 | 9.7 | 5.7 | 4.0 | review |
| near_above_emas | 26.2 | 143 | 9.8 | 6.2 | 3.6 | review |
| stoch_rsi_oversold | 40.6 | 221 | 8.6 | 6.2 | 2.4 | review |
| rsi_overbought_zone | 41.5 | 226 | 8.4 | 6.3 | 2.1 | review |
| stoch_rsi_overbought | 50.3 | 274 | 6.6 | 7.7 | -1.2 | review |
| below_vwap | 23.3 | 127 | 5.5 | 7.7 | -2.1 | review |
| consecutive_down | 13.4 | 73 | 4.1 | 7.6 | -3.5 | review |
| consecutive_up | 19.6 | 107 | 3.7 | 8.0 | -4.3 | review |
| above_vwap | 37.6 | 205 | 1.0 | 10.9 | -9.9 | DROP (anti-signal) |



## IWM — root-cause writeup

- **Signals available**: 493 (lookback 90d through 2026-05-08)
- **Signals with intraday outcome**: 488
- **Overall win-rate at global config**: 18.2%
- **Win-rate by direction**: CALL 22.1% (n=226), PUT 14.9% (n=262)
- **Time-stop hit rate** (means trade ran to time without target/stop): 28.9%
- **Median MFE / MAE on triggered side**: CALL MFE 0.113% / MAE -0.154%, PUT MFE 0.138% / MAE -0.201%
- **Strategy mix observed**: mean_reversion=100%
- **brief_alignment coverage**: n=0 alerts have a non-NULL alignment tag.
- **brief_alignment win-rate**: insufficient (n<10)
- **Notes**: mean_reversion: no score bucket net-positive; best is score=1 net_mean=-0.0800%

### IWM — multi-timeframe regime analysis (RTH-only)

| timeframe | bar_return_mean% | bar_return_std% | autocorr_lag1 | n_bars | regime |
|---|---|---|---|---|---|
| 1m | 0.0011 | 0.0772 | -0.0370 | 13649 | mixed |
| 5m | 0.0056 | 0.1597 | 0.0513 | 2729 | momentum |
| 15m | 0.0164 | 0.2814 | 0.0252 | 909 | mixed |
| 30m | 0.032 | 0.3867 | 0.0652 | 454 | momentum |
| 60m | 0.0596 | 0.5318 | -0.0062 | 244 | mixed |
| 240m | 0.2087 | 0.9066 | 0.0825 | 69 | momentum |

_autocorr_lag1 sign tells you which strategy class the timeframe favors: positive → momentum (trends persist); negative → mean-reversion (returns flip)._

### IWM — counterfactual replay: recommended config vs global default

- Replayed **488** alerts under both configs (same alerts, different exit rules).
- **Win-rate**: global 18.2% → recommended 18.0% (Δ -0.2 pp)
- **Mean per-trade return**: global -0.0179% → recommended -0.0033% (Δ +0.0146 %)
- _Win-rate goes UP because targets are tighter (more often reached); per-trade return is the apples-to-apples economic comparison after slippage._

### IWM — factor fire-rate × discrimination

| condition | fire_rate% | n_fired | win_when_fired% | win_when_absent% | discrimination_pp | verdict |
|---|---|---|---|---|---|---|
| rsi_oversold_zone | 35.9 | 175 | 25.7 | 14.1 | 11.7 | KEEP |
| below_vwap | 24.2 | 118 | 24.6 | 16.2 | 8.4 | KEEP |
| consecutive_down | 16.6 | 81 | 23.5 | 17.2 | 6.3 | KEEP |
| near_below_emas | 22.7 | 111 | 20.7 | 17.5 | 3.2 | review |
| stoch_rsi_oversold | 42.2 | 206 | 19.4 | 17.4 | 2.0 | review |
| consecutive_up | 20.3 | 99 | 19.2 | 18.0 | 1.2 | review |
| near_above_emas | 31.8 | 155 | 16.8 | 18.9 | -2.1 | review |
| rsi_overbought_zone | 38.3 | 187 | 15.5 | 19.9 | -4.4 | review |
| stoch_rsi_overbought | 45.3 | 221 | 13.6 | 22.1 | -8.5 | DROP (anti-signal) |
| above_vwap | 33.4 | 163 | 10.4 | 22.2 | -11.7 | DROP (anti-signal) |



## QQQ — root-cause writeup

- **Signals available**: 544 (lookback 90d through 2026-05-08)
- **Signals with intraday outcome**: 536
- **Overall win-rate at global config**: 17.4%
- **Win-rate by direction**: CALL 25.8% (n=229), PUT 11.1% (n=307)
- **Time-stop hit rate** (means trade ran to time without target/stop): 39.9%
- **Median MFE / MAE on triggered side**: CALL MFE 0.112% / MAE -0.151%, PUT MFE 0.139% / MAE -0.148%
- **Strategy mix observed**: mean_reversion=100%
- **brief_alignment coverage**: n=138 alerts have a non-NULL alignment tag.
- **brief_alignment win-rate**: aligned: 20.3% (n=59) opposed: 25.3% (n=79)
- **Notes**: mean_reversion: no score bucket net-positive; best is score=1 net_mean=-0.0299%

### QQQ — multi-timeframe regime analysis (RTH-only)

| timeframe | bar_return_mean% | bar_return_std% | autocorr_lag1 | n_bars | regime |
|---|---|---|---|---|---|
| 1m | 0.0013 | 0.063 | 0.0083 | 13649 | mixed |
| 5m | 0.0063 | 0.14 | 0.0406 | 2729 | mixed |
| 15m | 0.0185 | 0.2399 | 0.0348 | 909 | mixed |
| 30m | 0.0364 | 0.3321 | 0.1043 | 454 | momentum |
| 60m | 0.0678 | 0.4583 | 0.0456 | 244 | mixed |
| 240m | 0.241 | 0.8306 | 0.1714 | 69 | momentum |

_autocorr_lag1 sign tells you which strategy class the timeframe favors: positive → momentum (trends persist); negative → mean-reversion (returns flip)._

### QQQ — counterfactual replay: recommended config vs global default

- Replayed **536** alerts under both configs (same alerts, different exit rules).
- **Win-rate**: global 17.4% → recommended 17.2% (Δ -0.2 pp)
- **Mean per-trade return**: global -0.0005% → recommended +0.0127% (Δ +0.0133 %)
- _Win-rate goes UP because targets are tighter (more often reached); per-trade return is the apples-to-apples economic comparison after slippage._

### QQQ — factor fire-rate × discrimination

| condition | fire_rate% | n_fired | win_when_fired% | win_when_absent% | discrimination_pp | verdict |
|---|---|---|---|---|---|---|
| below_vwap | 21.3 | 114 | 33.3 | 13.0 | 20.3 | KEEP |
| stoch_rsi_oversold | 41.2 | 221 | 25.3 | 11.7 | 13.6 | KEEP |
| rsi_oversold_zone | 36.2 | 194 | 25.3 | 12.9 | 12.4 | KEEP |
| near_below_emas | 21.6 | 116 | 23.3 | 15.7 | 7.6 | KEEP |
| consecutive_down | 12.7 | 68 | 20.6 | 16.9 | 3.7 | review |
| consecutive_up | 17.9 | 96 | 15.6 | 17.7 | -2.1 | review |
| near_above_emas | 25.7 | 138 | 12.3 | 19.1 | -6.8 | DROP (anti-signal) |
| rsi_overbought_zone | 45.9 | 246 | 11.0 | 22.8 | -11.8 | DROP (anti-signal) |
| stoch_rsi_overbought | 52.2 | 280 | 11.1 | 24.2 | -13.1 | DROP (anti-signal) |
| above_vwap | 39.4 | 211 | 7.6 | 23.7 | -16.1 | DROP (anti-signal) |



## Methodology

- **Replay engine**: every alert is re-simulated against 1-min intraday bars using the production global config (CALL ±0.30%, PUT +0.38%/−0.20%, time-stops 30/35min). The recorded `exit_reason`/`exit_return_pct` columns are NOT trusted (Track A finding: 76% of historical alerts have NULL exits).
- **Recommended target_pct**: 0.7 × median MFE on triggered direction (anchors target on observed favorable excursion; 0.7 leaves room for slippage).
- **Recommended stop_pct**: 0.5 × median |MAE| on triggered direction (tight enough to bound loss without being whipped by normal noise).
- **Recommended time_stop**: 75th-percentile of time-to-target among winning trades, rounded up to nearest 5 min, capped at 90 min.
- **Strategy classification**: derived from `conditions_met` set membership against the strategy-exclusive condition lists. Conditions like `rvol_above_recent`, `atr_expansion`, `rsi_thrust`, `rsi_bullish_recovery` are momentum-only; `rsi_oversold_zone`, `stoch_rsi_*`, `level_break_*` are mean-reversion-only.
- **min_conditions per strategy**: lowest score (within the strategy) at which empirical win-rate ≥ 50%. Below that, signals fire net-negative after costs.
- **Discrimination_pp**: win-rate-when-fired minus win-rate-when-absent. Inspired by the Phase 0.7.1 `stoch_rsi_not_overbought` removal (72% fire rate, 0 discrimination = pure free score).
- **Equal treatment**: every ticker runs through the SAME pipeline. Differences are data-driven, not configuration-driven.
