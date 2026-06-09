# Data Dictionary — Cloud SQL `trading` dataset

Generated 2026-06-09 from live `information_schema.columns` (81 tables, 2,732 columns). Type + nullability for every column; category, producing code, grain, and per-column formula notes for the analytical tables. NULL semantics: per CLAUDE.md §3.7, financial fields use NULL (not 0, not NaN) for missing — see `docs/audits/NAN_AUDIT_2026-06-09.md` for columns with residual float8-NaN to remediate.


## Raw market


### `market_data_daily`

*Producer:* `gcp/fetchers/fetch_market_data.py` · *Grain:* ticker×date; AlphaVantage TIME_SERIES_DAILY_ADJUSTED + computed indicators


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `date` | date | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `ma_5` | double precision | Y |  |
| 10 | `ma_10` | double precision | Y |  |
| 11 | `ma_20` | double precision | Y |  |
| 12 | `ma_50` | double precision | Y |  |
| 14 | `ema_9` | double precision | Y |  |
| 15 | `ema_20` | double precision | Y |  |
| 16 | `ema_50` | double precision | Y |  |
| 17 | `rsi_14` | double precision | Y |  |
| 18 | `rsi_9` | double precision | Y |  |
| 19 | `rsi_30` | double precision | Y |  |
| 20 | `stoch_rsi_k` | double precision | Y |  |
| 21 | `stoch_rsi_d` | double precision | Y |  |
| 22 | `atr_14` | double precision | Y |  |
| 23 | `atr_20` | double precision | Y |  |
| 24 | `obv` | double precision | Y |  |
| 25 | `rvol` | double precision | Y |  |
| 26 | `rvol_10` | double precision | Y |  |
| 27 | `volume_ma_10` | double precision | Y |  |
| 28 | `volume_ma_20` | double precision | Y |  |
| 29 | `volume_usd` | double precision | Y |  |
| 30 | `return` | double precision | Y |  |
| 31 | `volatility_30min` | double precision | Y |  |
| 32 | `volatility_day` | double precision | Y |  |
| 33 | `volatility_5d` | double precision | Y |  |
| 34 | `volatility_20d` | double precision | Y |  |
| 35 | `intraday_return` | double precision | Y |  |
| 36 | `high_low_spread` | double precision | Y |  |
| 37 | `high_low_spread_pct` | double precision | Y |  |
| 38 | `consecutive_up` | integer | Y |  |
| 39 | `consecutive_down` | integer | Y |  |
| 40 | `vwap` | double precision | Y |  |
| 41 | `price_vs_vwap` | double precision | Y |  |
| 42 | `price_vs_ema9` | double precision | Y |  |
| 43 | `price_vs_ema20` | double precision | Y |  |
| 44 | `strat_candle` | character varying | Y |  |
| 45 | `strat_combo` | character varying | Y |  |
| 46 | `strat_setup` | boolean | Y |  |
| 47 | `ftfc_score` | double precision | Y |  |
| 48 | `ftfc_direction` | character varying | Y |  |
| 49 | `data_source` | character varying | Y |  |
| 50 | `inserted_at` | timestamp with time zone | N |  |
| 51 | `updated_at` | timestamp with time zone | N |  |
| 52 | `adjusted_close` | double precision | Y |  |
| 53 | `sma_200` | double precision | Y |  |
| 54 | `macd` | double precision | Y |  |
| 55 | `macd_signal` | double precision | Y |  |
| 56 | `macd_histogram` | double precision | Y |  |
| 57 | `bb_upper` | double precision | Y |  |
| 58 | `bb_lower` | double precision | Y |  |
| 59 | `bb_width` | double precision | Y |  |
| 60 | `bb_pct` | double precision | Y |  |
| 61 | `prev_quarter_high` | double precision | Y |  |
| 62 | `prev_quarter_low` | double precision | Y |  |
| 63 | `prev_quarter_open` | double precision | Y |  |
| 64 | `prev_quarter_close` | double precision | Y |  |
| 65 | `prev_quarter_hl_mid` | double precision | Y |  |
| 66 | `prev_quarter_oc_mid` | double precision | Y |  |
| 67 | `at_prev_quarter_high` | smallint | Y |  |
| 68 | `at_prev_quarter_low` | smallint | Y |  |
| 69 | `broke_prev_quarter_high` | smallint | Y |  |
| 70 | `broke_prev_quarter_low` | smallint | Y |  |
| 71 | `pre_high` | double precision | Y |  |
| 72 | `pre_low` | double precision | Y |  |
| 73 | `pre_vwap` | double precision | Y |  |
| 74 | `pre_volume` | bigint | Y |  |
| 75 | `gap_pct` | double precision | Y |  |
| 76 | `pre_range_atr` | double precision | Y |  |
| 77 | `realized_vol_short` | double precision | Y |  |
| 78 | `price_vs_ema9_atr` | double precision | Y |  |
| 79 | `price_vs_ema20_atr` | double precision | Y |  |
| 80 | `ema_spread_atr` | double precision | Y |  |
| 81 | `ema9_slope` | double precision | Y |  |
| 82 | `bb_squeeze` | double precision | Y |  |
| 83 | `rsi_divergence` | double precision | Y |  |


### `market_data_intraday`

*Producer:* `gcp/fetchers/fetch_alphavantage_intraday.py` · *Grain:* ticker×interval×ts (1-min bars)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


## Raw options


### `etf_options_snapshots`

*Producer:* `gcp/fetchers/fetch_av_*_options.py` · *Grain:* ticker×snapshot_ts×type×expiration×strike; AlphaVantage OPTION_CHAIN


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `snapshot_ts` | timestamp with time zone | N |  |
| 4 | `snapshot_date` | date | N |  |
| 5 | `market_session` | character varying | Y |  |
| 6 | `contract_symbol` | character varying | Y |  |
| 7 | `option_type` | character varying | N |  |
| 8 | `expiration` | date | N |  |
| 9 | `strike` | double precision | N |  |
| 10 | `in_the_money` | boolean | Y |  |
| 11 | `bid` | double precision | Y |  |
| 12 | `ask` | double precision | Y |  |
| 13 | `last_price` | double precision | Y |  |
| 14 | `change` | double precision | Y |  |
| 15 | `percent_change` | double precision | Y |  |
| 16 | `volume` | double precision | Y |  |
| 17 | `open_interest` | double precision | Y |  |
| 18 | `implied_volatility` | double precision | Y |  |
| 19 | `delta` | double precision | Y |  |
| 20 | `gamma` | double precision | Y |  |
| 21 | `theta` | double precision | Y |  |
| 22 | `vega` | double precision | Y |  |
| 23 | `rho` | double precision | Y |  |
| 24 | `underlying_price` | double precision | Y |  |
| 25 | `inserted_at` | timestamp with time zone | N |  |
| 26 | `data_source` | character varying | Y |  |
| 27 | `mark` | double precision | Y |  |
| 28 | `delta_computed` | double precision | Y |  |
| 29 | `gamma_computed` | double precision | Y |  |
| 30 | `theta_computed` | double precision | Y |  |
| 31 | `vega_computed` | double precision | Y |  |
| 32 | `rho_computed` | double precision | Y |  |
| 33 | `implied_volatility_computed` | double precision | Y |  |


## Raw macro


### `daily_rates`

*Producer:* `gcp/fetchers/fetch_fred_rates.py` · *Grain:* date PK; FRED DGS3MO + dividend yield


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `date` | date | N |  |
| 2 | `dgs3mo` | double precision | Y |  |
| 3 | `sp500_div_yld` | double precision | Y |  |
| 4 | `fetched_at` | timestamp with time zone | N |  |


## Raw catalysts


### `news_sentiment`

*Producer:* `gcp/fetchers/fetch_news_sentiment.py` · *Grain:* ticker×published_ts×url


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `published_ts` | timestamp with time zone | N |  |
| 4 | `title` | text | Y |  |
| 5 | `url` | text | Y |  |
| 6 | `summary` | text | Y |  |
| 7 | `sentiment_score` | double precision | Y |  |
| 8 | `relevance_score` | double precision | Y |  |
| 9 | `source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |
| 11 | `overall_sentiment_score` | double precision | Y |  |
| 12 | `overall_sentiment_label` | character varying | Y |  |
| 13 | `topics` | ARRAY | Y |  |
| 14 | `data_source` | character varying | Y |  |
| 15 | `match_method` | character varying | Y |  |


## Derived gamma


### `gamma_levels_eod`

*Producer:* `gcp/research/p2_build_gamma_levels.py` · *Grain:* ticker×date×level_kind×strike. King/Gate/gamma_balance rows + per-day gamma_balance_price/gamma_flip/total_gex/regime


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `snapshot_date` | date | N |  |
| 3 | `level_kind` | character varying | N |  |
| 4 | `level_strike` | numeric | N |  |
| 5 | `gex` | double precision | Y |  |
| 6 | `net_gamma` | double precision | Y |  |
| 7 | `score` | double precision | Y |  |
| 8 | `tags` | text | Y |  |
| 9 | `regime` | character varying | Y |  |
| 10 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 11 | `flip_price` | double precision | Y |  |
| 12 | `spot_estimate` | double precision | Y |  |
| 13 | `spot_method` | character varying | Y |  |
| 14 | `n_strikes_in_window` | integer | Y |  |
| 15 | `computed_at` | timestamp with time zone | Y |  |


### `intraday_gex_15m`

*Producer:* `lib/features/intraday_gex.py` · *Grain:* ticker×ts; re-curved EOD dealer GEX/DEX. NOTE: gamma_flip col holds cumulative-balance (legacy name)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 4 | `total_dex` | double precision | Y |  |
| 5 | `total_oi` | double precision | Y |  |
| 6 | `gamma_flip` | double precision | Y | TRUE Black-Scholes-recurved zero-gamma level (lib.gamma.compute_gamma_flip_bs), prior-day join |
| 7 | `spot` | double precision | Y |  |
| 8 | `computed_at` | timestamp with time zone | N |  |


### `realtime_gex_15m`

*Producer:* `gcp/build_realtime_gex.py` · *Grain:* ticker×ts; real intraday greeks


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 4 | `total_dex` | double precision | Y |  |
| 5 | `total_oi` | double precision | Y |  |
| 6 | `gamma_flip` | double precision | Y | TRUE Black-Scholes-recurved zero-gamma level (lib.gamma.compute_gamma_flip_bs), prior-day join |
| 7 | `spot` | double precision | Y |  |
| 8 | `computed_at` | timestamp with time zone | N |  |


## Derived feature


### `strat_features_15m`

*Producer:* `gcp/research/strat_engine/strat_data_builder.py` · *Grain:* ticker×ts (15m bar). 143-col model surface: OHLCV + indicators + strat + gamma context


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


### `strat_features_1m`

*Producer:* `strat_data_builder.py` · *Grain:* ticker×ts (1m)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


### `strat_features_30m`

*Producer:* `strat_data_builder.py` · *Grain:* ticker×ts (30m)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


### `strat_features_4h`

*Producer:* `strat_data_builder.py` · *Grain:* ticker×ts (4h)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


### `strat_features_5m`

*Producer:* `strat_data_builder.py` · *Grain:* ticker×ts (5m)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


### `strat_features_60m`

*Producer:* `strat_data_builder.py` · *Grain:* ticker×ts (60m)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `tf` | character varying | N |  |
| 4 | `bar_date` | date | N |  |
| 5 | `open` | double precision | Y |  |
| 6 | `high` | double precision | Y |  |
| 7 | `low` | double precision | Y |  |
| 8 | `close` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `prev_strat_candle` | character varying | Y |  |
| 12 | `strat_combo` | character varying | Y |  |
| 13 | `is_continuation` | boolean | Y |  |
| 14 | `is_reversal` | boolean | Y |  |
| 15 | `is_inside` | boolean | Y |  |
| 16 | `strat_setup` | boolean | Y |  |
| 17 | `consecutive_1s` | smallint | Y |  |
| 18 | `trigger_high` | double precision | Y |  |
| 19 | `trigger_low` | double precision | Y |  |
| 20 | `ema_9` | double precision | Y |  |
| 21 | `ema_20` | double precision | Y |  |
| 22 | `ema_50` | double precision | Y |  |
| 23 | `ema_200` | double precision | Y | EMA span=200 (ewm, min_periods=200) — NaN during 200-bar warmup |
| 24 | `sma_50` | double precision | Y |  |
| 25 | `sma_200` | double precision | Y |  |
| 26 | `rsi_9` | double precision | Y |  |
| 27 | `rsi_14` | double precision | Y |  |
| 28 | `stoch_rsi_k` | double precision | Y |  |
| 29 | `stoch_rsi_d` | double precision | Y |  |
| 30 | `macd` | double precision | Y |  |
| 31 | `macd_signal` | double precision | Y |  |
| 32 | `macd_histogram` | double precision | Y |  |
| 33 | `atr_14` | double precision | Y |  |
| 34 | `atr_20` | double precision | Y |  |
| 35 | `bb_upper` | double precision | Y |  |
| 36 | `bb_lower` | double precision | Y |  |
| 37 | `bb_width` | double precision | Y |  |
| 38 | `bb_pct` | double precision | Y |  |
| 39 | `obv` | double precision | Y |  |
| 40 | `rvol` | double precision | Y |  |
| 41 | `rvol_10` | double precision | Y |  |
| 42 | `vwap` | double precision | Y |  |
| 43 | `price_vs_vwap` | double precision | Y |  |
| 44 | `price_vs_ema9` | double precision | Y |  |
| 45 | `price_vs_ema20` | double precision | Y |  |
| 46 | `consecutive_up` | integer | Y |  |
| 47 | `consecutive_down` | integer | Y |  |
| 48 | `intraday_return` | double precision | Y |  |
| 49 | `high_low_spread_pct` | double precision | Y |  |
| 50 | `fwd_close_5bars` | double precision | Y |  |
| 51 | `fwd_close_15bars` | double precision | Y |  |
| 52 | `fwd_close_30bars` | double precision | Y |  |
| 53 | `fwd_close_60bars` | double precision | Y |  |
| 54 | `fwd_ret_5bars_bps` | double precision | Y |  |
| 55 | `fwd_ret_15bars_bps` | double precision | Y |  |
| 56 | `fwd_ret_30bars_bps` | double precision | Y |  |
| 57 | `fwd_ret_60bars_bps` | double precision | Y |  |
| 58 | `vix_close` | double precision | Y |  |
| 59 | `vix_tercile` | character varying | Y |  |
| 60 | `total_gex` | double precision | Y | Σ(call−put) netΓ·spot²·0.01 (GEX_MULTIPLIER) |
| 61 | `gex_tercile` | character varying | Y |  |
| 62 | `total_vex` | double precision | Y |  |
| 63 | `vex_tercile` | character varying | Y |  |
| 64 | `dealer_regime` | character varying | Y |  |
| 65 | `gamma_regime` | character varying | Y | sign(total_gex): positive_gamma | negative_gamma | unknown |
| 66 | `flip_price` | double precision | Y |  |
| 67 | `distance_to_king_pct` | double precision | Y | (close − min_king_strike)/close·100 |
| 68 | `distance_to_gate_pct` | double precision | Y | (close − min_gate_strike)/close·100 |
| 69 | `computed_at` | timestamp with time zone | Y |  |
| 70 | `realized_vol_short` | double precision | Y |  |
| 71 | `mins_since_open` | double precision | Y | minutes since 09:30 ET (Time-gated) |
| 72 | `price_vs_ema9_atr` | double precision | Y |  |
| 73 | `price_vs_ema20_atr` | double precision | Y |  |
| 74 | `price_vs_vwap_atr` | double precision | Y |  |
| 75 | `ema_spread_atr` | double precision | Y |  |
| 76 | `ema9_slope` | double precision | Y |  |
| 77 | `bb_squeeze` | double precision | Y |  |
| 78 | `rsi_divergence` | double precision | Y |  |
| 79 | `bb20_bandwidth` | double precision | Y |  |
| 80 | `realized_vol_z` | double precision | Y | z-score of per-day realized vol (rv_window=15) over cross-day window=60; NULL on coarse TFs (<15 bars/day) |
| 81 | `range_expansion_ratio` | double precision | Y |  |
| 82 | `intraday_range_vs_prevday` | double precision | Y |  |
| 83 | `atr_expansion` | double precision | Y |  |


## Derived levels


### `strat_features_levels_15m`

*Producer:* `strat_enrich_levels.py` · *Grain:* ticker×ts; horizontal level-map join (PDH/PDL/ORB/order-block/prev_year...). NOTE: ORB/order-block cols currently 100% NaN — see NAN_AUDIT_2026-06-09 §B


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


## Derived flow


### `intraday_flow_15m`

*Producer:* `gcp/build_intraday_flow.py` · *Grain:* ticker×ts (15m); OFI signed-volume aggregates


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `signed_vol` | double precision | Y |  |
| 4 | `tot_vol` | double precision | Y |  |
| 5 | `up_vol` | double precision | Y |  |
| 6 | `dn_vol` | double precision | Y |  |
| 7 | `n_min` | integer | Y |  |
| 8 | `computed_at` | timestamp with time zone | N |  |


## Derived greeks


### `etf_options_daily_greeks`

*Producer:* `gcp/build_options_daily_greeks.py` · *Grain:* ticker×date; dealer dex/vanna/charm


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `snapshot_date` | date | N |  |
| 3 | `dex` | double precision | Y |  |
| 4 | `short_dte_dex` | double precision | Y |  |
| 5 | `total_oi` | double precision | Y |  |
| 6 | `vanna` | double precision | Y |  |
| 7 | `charm` | double precision | Y |  |
| 8 | `n_contracts` | integer | Y |  |
| 9 | `computed_at` | timestamp with time zone | N |  |


## Derived earnings


### `earnings_reactions`

*Producer:* `gcp/fetchers/compute_earnings_reactions.py` · *Grain:* ticker×fiscal_date; drift/gap/sustain %


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `fiscal_date_ending` | date | N |  |
| 4 | `reported_date` | date | N |  |
| 5 | `reaction_basis` | character varying | Y |  |
| 6 | `reported_eps` | double precision | Y |  |
| 7 | `estimated_eps` | double precision | Y |  |
| 8 | `surprise_pct` | double precision | Y |  |
| 9 | `d_minus_10_close` | double precision | Y |  |
| 10 | `d_minus_1_close` | double precision | Y |  |
| 11 | `pre_earnings_drift_10d_pct` | double precision | Y |  |
| 12 | `d_open` | double precision | Y |  |
| 13 | `d_high` | double precision | Y |  |
| 14 | `d_low` | double precision | Y |  |
| 15 | `d_close` | double precision | Y |  |
| 16 | `pre_report_gap_pct` | double precision | Y |  |
| 17 | `d_plus_1_open` | double precision | Y |  |
| 18 | `d_plus_1_high` | double precision | Y |  |
| 19 | `d_plus_1_low` | double precision | Y |  |
| 20 | `d_plus_1_close` | double precision | Y |  |
| 21 | `post_gap_pct` | double precision | Y |  |
| 22 | `reaction_gap_pct` | double precision | Y |  |
| 23 | `reaction_anchor_price` | double precision | Y |  |
| 24 | `reaction_max_run_pct` | double precision | Y |  |
| 25 | `reaction_max_drawdown_pct` | double precision | Y |  |
| 26 | `d_plus_3_close` | double precision | Y |  |
| 27 | `sustain_3d_pct` | double precision | Y |  |
| 28 | `d_plus_5_close` | double precision | Y |  |
| 29 | `sustain_5d_pct` | double precision | Y |  |
| 30 | `d_plus_10_close` | double precision | Y |  |
| 31 | `sustain_10d_pct` | double precision | Y |  |
| 32 | `direction_consistent_5d` | boolean | Y |  |
| 33 | `is_reversal_5d` | boolean | Y |  |
| 34 | `inserted_at` | timestamp with time zone | N |  |
| 35 | `updated_at` | timestamp with time zone | N |  |
| 40 | `pre_report_atr` | double precision | Y |  |
| 41 | `pre_report_atr_pct` | double precision | Y |  |
| 42 | `post_report_atr` | double precision | Y |  |
| 43 | `reaction_day_range` | double precision | Y |  |
| 44 | `reaction_day_range_in_atr_units` | double precision | Y |  |
| 45 | `max_high_3d_pct` | double precision | Y |  |
| 46 | `min_low_3d_pct` | double precision | Y |  |
| 47 | `max_high_5d_pct` | double precision | Y |  |
| 48 | `min_low_5d_pct` | double precision | Y |  |
| 49 | `max_high_10d_pct` | double precision | Y |  |
| 50 | `min_low_10d_pct` | double precision | Y |  |
| 51 | `d_minus_5_close` | double precision | Y |  |
| 52 | `d_minus_3_close` | double precision | Y |  |
| 53 | `d_minus_2_close` | double precision | Y |  |
| 54 | `drift_3d_pct` | double precision | Y |  |
| 55 | `drift_5d_pct` | double precision | Y |  |
| 56 | `pre_drift_consistent_5d` | boolean | Y |  |
| 57 | `pre_drift_reverses_into_gap` | boolean | Y |  |
| 58 | `max_high_pre_3d_pct` | double precision | Y |  |
| 59 | `min_low_pre_3d_pct` | double precision | Y |  |
| 60 | `max_high_pre_5d_pct` | double precision | Y |  |
| 61 | `min_low_pre_5d_pct` | double precision | Y |  |
| 62 | `max_high_pre_10d_pct` | double precision | Y |  |
| 63 | `min_low_pre_10d_pct` | double precision | Y |  |


## Signals


### `historical_signals`

*Producer:* `gcp/historical_signals.py` · *Grain:* backtest signal fires


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `entry_time` | timestamp with time zone | N |  |
| 3 | `trade_type` | character varying | N |  |
| 4 | `entry_price` | double precision | Y |  |
| 5 | `signal_strength` | smallint | Y |  |
| 6 | `conditions_met` | character varying | Y |  |
| 7 | `duration_minutes` | smallint | Y |  |
| 8 | `return_pct` | double precision | Y |  |
| 9 | `best_return` | double precision | Y |  |
| 10 | `best_window_min` | smallint | Y |  |
| 11 | `return_5min` | double precision | Y |  |
| 12 | `return_10min` | double precision | Y |  |
| 13 | `return_15min` | double precision | Y |  |
| 14 | `return_20min` | double precision | Y |  |
| 15 | `return_30min` | double precision | Y |  |
| 16 | `return_45min` | double precision | Y |  |
| 17 | `return_60min` | double precision | Y |  |
| 18 | `entry_rsi` | double precision | Y |  |
| 19 | `entry_ema9` | double precision | Y |  |
| 20 | `entry_ema20` | double precision | Y |  |
| 21 | `entry_vwap` | double precision | Y |  |
| 22 | `entry_volume` | bigint | Y |  |
| 23 | `extra` | jsonb | Y |  |
| 24 | `inserted_at` | timestamp with time zone | N |  |
| 25 | `strategy` | character varying | N |  |
| 26 | `timeframe_tag` | character varying | Y |  |
| 27 | `expected_hold_min` | integer | Y |  |
| 28 | `next_catalyst_min` | integer | Y |  |
| 29 | `next_catalyst_type` | character varying | Y |  |
| 30 | `last_catalyst_min` | integer | Y |  |
| 31 | `last_catalyst_type` | character varying | Y |  |
| 32 | `catalyst_session` | character varying | Y |  |
| 33 | `proximity_bucket` | character varying | Y |  |


### `signal_alerts`

*Producer:* `gcp/signal_monitor.py` · *Grain:* ticker×alert_ts; live fires + exit P&L


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `alert_ts` | timestamp with time zone | N |  |
| 4 | `alert_date` | date | N |  |
| 5 | `direction` | character varying | N |  |
| 6 | `base_score` | double precision | Y |  |
| 7 | `strat_bonus` | double precision | Y |  |
| 8 | `total_score` | double precision | Y |  |
| 9 | `strength_label` | character varying | Y |  |
| 10 | `position_size` | double precision | Y |  |
| 11 | `price_at_signal` | double precision | Y |  |
| 12 | `target_price` | double precision | Y |  |
| 13 | `time_stop_minutes` | integer | Y |  |
| 14 | `rsi` | double precision | Y |  |
| 15 | `rvol` | double precision | Y |  |
| 16 | `orb_5m_high` | double precision | Y |  |
| 17 | `orb_5m_low` | double precision | Y |  |
| 18 | `orb_15m_high` | double precision | Y |  |
| 19 | `orb_15m_low` | double precision | Y |  |
| 20 | `conditions_met` | jsonb | Y |  |
| 21 | `inserted_at` | timestamp with time zone | N |  |
| 22 | `level_broken` | character varying | Y |  |
| 23 | `strategy_agreement` | jsonb | Y |  |
| 24 | `timeframe_tag` | character varying | Y |  |
| 25 | `expected_hold_min` | integer | Y |  |
| 26 | `next_catalyst_min` | integer | Y |  |
| 27 | `next_catalyst_type` | character varying | Y |  |
| 28 | `last_catalyst_min` | integer | Y |  |
| 29 | `last_catalyst_type` | character varying | Y |  |
| 30 | `catalyst_session` | character varying | Y |  |
| 31 | `proximity_bucket` | character varying | Y |  |
| 32 | `exit_ts` | timestamp with time zone | Y |  |
| 33 | `exit_reason` | character varying | Y |  |
| 34 | `exit_price` | double precision | Y |  |
| 35 | `exit_return_pct` | double precision | Y |  |
| 36 | `is_open` | boolean | Y |  |
| 37 | `brief_bias` | character varying | Y |  |
| 38 | `brief_alignment` | character varying | Y |  |
| 39 | `brief_setup_count` | integer | Y |  |
| 40 | `run_kind` | character varying | N |  |
| 41 | `replay_id` | uuid | Y |  |
| 42 | `insight_direction` | character varying | Y |  |
| 43 | `insight_conviction` | character varying | Y |  |
| 44 | `insight_regime` | character varying | Y |  |
| 45 | `gate_action` | character varying | Y |  |
| 46 | `gate_reason` | text | Y |  |
| 47 | `thesis_invalidated` | boolean | Y |  |


### `signal_metrics`

*Producer:* `scripts/signal_quality_report.py` · *Grain:* forward-return classification of signals


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `entry_time` | timestamp with time zone | N |  |
| 3 | `strategy` | character varying | N |  |
| 4 | `evaluated_at` | timestamp with time zone | N |  |
| 5 | `cls_5m` | character varying | Y |  |
| 6 | `cls_15m` | character varying | Y |  |
| 7 | `cls_30m` | character varying | Y |  |
| 8 | `cls_60m` | character varying | Y |  |
| 9 | `cls_90m` | character varying | Y |  |
| 10 | `cls_120m` | character varying | Y |  |
| 11 | `cls_240m` | character varying | Y |  |
| 12 | `best_tf` | character varying | Y |  |
| 13 | `return_5m` | double precision | Y |  |
| 14 | `return_15m` | double precision | Y |  |
| 15 | `return_30m` | double precision | Y |  |
| 16 | `return_60m` | double precision | Y |  |
| 17 | `return_90m` | double precision | Y |  |
| 18 | `return_120m` | double precision | Y |  |
| 19 | `return_240m` | double precision | Y |  |
| 20 | `atr_5m_pct` | double precision | Y |  |
| 21 | `mfe_60m_atrs` | double precision | Y |  |
| 22 | `status` | character varying | N |  |


### `trades`

*Producer:* `gcp/signal_monitor.py` · *Grain:* closed-trade exits


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `direction` | character varying | N |  |
| 4 | `entry_time` | timestamp with time zone | Y |  |
| 5 | `entry_price` | double precision | Y |  |
| 6 | `exit_time` | timestamp with time zone | Y |  |
| 7 | `exit_price` | double precision | Y |  |
| 8 | `exit_reason` | character varying | Y |  |
| 9 | `signal_strength` | double precision | Y |  |
| 10 | `total_score` | double precision | Y |  |
| 11 | `position_size` | double precision | Y |  |
| 12 | `return_pct` | double precision | Y |  |
| 13 | `conditions_met` | jsonb | Y |  |
| 14 | `strat_combo` | character varying | Y |  |
| 15 | `ftfc_score` | double precision | Y |  |
| 16 | `trade_date` | date | Y |  |
| 17 | `inserted_at` | timestamp with time zone | N |  |


## Analysis


### `premarket_analysis`

*Producer:* `gcp/premarket_brief.py` · *Grain:* date×ticker; brief + resolver outcomes


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `analysis_date` | date | N |  |
| 3 | `ticker` | character varying | N |  |
| 4 | `price` | double precision | Y |  |
| 5 | `rsi` | double precision | Y |  |
| 6 | `rsi_direction` | character varying | Y |  |
| 7 | `consecutive_up` | integer | Y |  |
| 8 | `consecutive_down` | integer | Y |  |
| 9 | `signal_status` | character varying | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `strat_combo` | character varying | Y |  |
| 12 | `strat_setup` | boolean | Y |  |
| 13 | `ftfc_score` | double precision | Y |  |
| 14 | `ftfc_direction` | character varying | Y |  |
| 15 | `ftfc_labels` | jsonb | Y |  |
| 16 | `prev_day_high` | double precision | Y |  |
| 17 | `prev_day_low` | double precision | Y |  |
| 18 | `analysis_ts` | timestamp with time zone | N |  |
| 19 | `change_pct` | double precision | Y |  |
| 20 | `rvol` | double precision | Y |  |
| 21 | `sma200` | double precision | Y |  |
| 22 | `bb_upper` | double precision | Y |  |
| 23 | `bb_lower` | double precision | Y |  |
| 24 | `ema9` | double precision | Y |  |
| 25 | `ema20` | double precision | Y |  |
| 26 | `atr14` | double precision | Y |  |
| 27 | `volatility_20d` | double precision | Y |  |
| 28 | `macd_cross` | character varying | Y |  |
| 29 | `vol_regime` | character varying | Y |  |
| 30 | `above_sma200` | boolean | Y |  |
| 31 | `stoch_rsi_k` | double precision | Y |  |
| 32 | `stoch_rsi_d` | double precision | Y |  |
| 33 | `recommended_orb_window` | character varying | Y |  |
| 34 | `recommended_orb_reason` | text | Y |  |
| 35 | `playbook` | text | Y |  |
| 36 | `data_as_of` | timestamp with time zone | Y |  |
| 37 | `data_freshness_status` | character varying | Y |  |
| 38 | `llm_overview` | text | Y |  |
| 39 | `llm_orb_explanation` | text | Y |  |
| 40 | `llm_analysis` | text | Y |  |
| 41 | `llm_playbook` | text | Y |  |
| 42 | `calls_trigger_price` | double precision | Y |  |
| 43 | `calls_trigger_name` | character varying | Y |  |
| 44 | `calls_stop_price` | double precision | Y |  |
| 45 | `calls_stop_name` | character varying | Y |  |
| 46 | `calls_t1_price` | double precision | Y |  |
| 47 | `calls_t2_price` | double precision | Y |  |
| 48 | `calls_t3_price` | double precision | Y |  |
| 49 | `puts_trigger_price` | double precision | Y |  |
| 50 | `puts_trigger_name` | character varying | Y |  |
| 51 | `puts_stop_price` | double precision | Y |  |
| 52 | `puts_stop_name` | character varying | Y |  |
| 53 | `puts_t1_price` | double precision | Y |  |
| 54 | `puts_t2_price` | double precision | Y |  |
| 55 | `puts_t3_price` | double precision | Y |  |
| 56 | `calls_trigger_hit_ts` | timestamp with time zone | Y |  |
| 57 | `calls_t1_hit_ts` | timestamp with time zone | Y |  |
| 58 | `calls_t2_hit_ts` | timestamp with time zone | Y |  |
| 59 | `calls_t3_hit_ts` | timestamp with time zone | Y |  |
| 60 | `calls_stop_hit_ts` | timestamp with time zone | Y |  |
| 61 | `calls_reversal_after_trigger` | boolean | Y |  |
| 62 | `calls_time_to_t1_min` | integer | Y |  |
| 63 | `calls_mae_pct` | double precision | Y |  |
| 64 | `calls_mfe_pct` | double precision | Y |  |
| 65 | `calls_eod_pnl_pct` | double precision | Y |  |
| 66 | `calls_eod_pnl_dollar` | double precision | Y |  |
| 67 | `puts_trigger_hit_ts` | timestamp with time zone | Y |  |
| 68 | `puts_t1_hit_ts` | timestamp with time zone | Y |  |
| 69 | `puts_t2_hit_ts` | timestamp with time zone | Y |  |
| 70 | `puts_t3_hit_ts` | timestamp with time zone | Y |  |
| 71 | `puts_stop_hit_ts` | timestamp with time zone | Y |  |
| 72 | `puts_reversal_after_trigger` | boolean | Y |  |
| 73 | `puts_time_to_t1_min` | integer | Y |  |
| 74 | `puts_mae_pct` | double precision | Y |  |
| 75 | `puts_mfe_pct` | double precision | Y |  |
| 76 | `puts_eod_pnl_pct` | double precision | Y |  |
| 77 | `puts_eod_pnl_dollar` | double precision | Y |  |
| 78 | `outcome_resolved_at` | timestamp with time zone | Y |  |
| 79 | `outcome_resolver_version` | character varying | Y |  |


## Backtest


### `backtest_trades`

*Producer:* `scripts/run_backtest.py` · *Grain:* run×ticker×mode×trade_seq


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `run_id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `use_strat` | boolean | N |  |
| 4 | `mode` | character varying | N |  |
| 5 | `trade_seq` | integer | N |  |
| 6 | `entry_time` | timestamp with time zone | Y |  |
| 7 | `exit_time` | timestamp with time zone | Y |  |
| 8 | `direction` | character varying | Y |  |
| 9 | `entry_price` | double precision | Y |  |
| 10 | `exit_price` | double precision | Y |  |
| 11 | `exit_reason` | character varying | Y |  |
| 12 | `base_score` | integer | Y |  |
| 13 | `strat_bonus` | integer | Y |  |
| 14 | `total_score` | integer | Y |  |
| 15 | `position_size` | double precision | Y |  |
| 16 | `return_pct` | double precision | Y |  |
| 17 | `mae` | double precision | Y |  |
| 18 | `mfe` | double precision | Y |  |
| 19 | `ftfc_score` | double precision | Y |  |
| 20 | `orb_trend` | integer | Y |  |
| 21 | `conditions` | text | Y |  |
| 22 | `created_at` | timestamp with time zone | N |  |


### `walk_forward_results`

*Producer:* `scripts/run_param_sweep.py` · *Grain:* run×ticker×label; OOS param sweep


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `run_id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `label` | character varying | N |  |
| 4 | `consecutive_periods` | integer | Y |  |
| 5 | `call_target` | double precision | Y |  |
| 6 | `put_target` | double precision | Y |  |
| 7 | `call_time_stop` | integer | Y |  |
| 8 | `put_time_stop` | integer | Y |  |
| 9 | `avg_expectancy_pct` | double precision | Y |  |
| 10 | `avg_win_rate` | double precision | Y |  |
| 11 | `std_expectancy_pct` | double precision | Y |  |
| 12 | `stability_score` | double precision | Y |  |
| 13 | `total_folds` | integer | Y |  |
| 14 | `total_trades` | integer | Y |  |
| 15 | `selected` | boolean | N |  |
| 16 | `created_at` | timestamp with time zone | N |  |


## Research


### `indicator_correlation`

*Producer:* `gcp/indicator_correlation_job.py` · *Grain:* IC: pearson/rank_ic/MI (NULL=undefined)


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `computed_date` | date | N |  |
| 3 | `window_start` | date | N |  |
| 4 | `window_end` | date | N |  |
| 5 | `lookback_days` | integer | Y |  |
| 6 | `ticker` | character varying | N |  |
| 7 | `indicator` | character varying | N |  |
| 8 | `horizon_min` | integer | N |  |
| 9 | `pearson` | double precision | Y |  |
| 10 | `rank_ic` | double precision | Y |  |
| 11 | `abs_rank_ic` | double precision | Y |  |
| 12 | `n` | integer | Y |  |
| 13 | `computed_at` | timestamp with time zone | N |  |
| 14 | `target_name` | character varying | N |  |
| 15 | `target_class` | character varying | N |  |
| 16 | `mutual_info` | double precision | Y |  |
| 17 | `class_lift` | double precision | Y |  |


## Config


### `exit_config_overrides`

*Producer:* `scripts/run_param_sweep.py` · *Grain:* ticker×calibration_date; tuned exit params


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `calibration_date` | date | N |  |
| 3 | `call_target` | double precision | Y |  |
| 4 | `put_target` | double precision | Y |  |
| 5 | `call_stop` | double precision | Y |  |
| 6 | `put_stop` | double precision | Y |  |
| 7 | `call_time_stop` | integer | Y |  |
| 8 | `put_time_stop` | integer | Y |  |
| 9 | `disabled_conditions` | jsonb | Y |  |
| 10 | `blue_sky_atr_offset` | double precision | Y |  |
| 11 | `notes` | text | Y |  |
| 12 | `inserted_at` | timestamp with time zone | N |  |
| 13 | `disabled_directions` | jsonb | Y |  |
| 14 | `consecutive_periods` | integer | Y |  |


## (uncategorized)


### `archive_yahoo_earnings_options_snapshots`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `symbol` | character varying | N |  |
| 3 | `snapshot_ts` | timestamp with time zone | N |  |
| 4 | `snapshot_date` | date | N |  |
| 5 | `contract_symbol` | character varying | Y |  |
| 6 | `option_type` | character varying | N |  |
| 7 | `expiration` | date | N |  |
| 8 | `strike` | double precision | N |  |
| 9 | `in_the_money` | boolean | Y |  |
| 10 | `contract_size` | character varying | Y |  |
| 11 | `bid` | double precision | Y |  |
| 12 | `ask` | double precision | Y |  |
| 13 | `last_price` | double precision | Y |  |
| 14 | `change` | double precision | Y |  |
| 15 | `percent_change` | double precision | Y |  |
| 16 | `last_trade_date` | timestamp with time zone | Y |  |
| 17 | `volume` | double precision | Y |  |
| 18 | `open_interest` | double precision | Y |  |
| 19 | `implied_volatility` | double precision | Y |  |
| 20 | `delta` | double precision | Y |  |
| 21 | `gamma` | double precision | Y |  |
| 22 | `theta` | double precision | Y |  |
| 23 | `vega` | double precision | Y |  |
| 24 | `rho` | double precision | Y |  |
| 25 | `underlying_price` | double precision | Y |  |
| 26 | `data_source` | character varying | Y |  |
| 27 | `inserted_at` | timestamp with time zone | N |  |


### `archive_yahoo_etf_options_snapshots`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `snapshot_ts` | timestamp with time zone | N |  |
| 4 | `snapshot_date` | date | N |  |
| 5 | `market_session` | character varying | Y |  |
| 6 | `contract_symbol` | character varying | Y |  |
| 7 | `option_type` | character varying | N |  |
| 8 | `expiration` | date | N |  |
| 9 | `strike` | double precision | N |  |
| 10 | `in_the_money` | boolean | Y |  |
| 11 | `bid` | double precision | Y |  |
| 12 | `ask` | double precision | Y |  |
| 13 | `last_price` | double precision | Y |  |
| 14 | `change` | double precision | Y |  |
| 15 | `percent_change` | double precision | Y |  |
| 16 | `volume` | double precision | Y |  |
| 17 | `open_interest` | double precision | Y |  |
| 18 | `implied_volatility` | double precision | Y |  |
| 19 | `delta` | double precision | Y |  |
| 20 | `gamma` | double precision | Y |  |
| 21 | `theta` | double precision | Y |  |
| 22 | `vega` | double precision | Y |  |
| 23 | `rho` | double precision | Y |  |
| 24 | `underlying_price` | double precision | Y |  |
| 25 | `inserted_at` | timestamp with time zone | N |  |
| 26 | `data_source` | character varying | Y |  |
| 27 | `mark` | double precision | Y |  |


### `archive_yahoo_market_data_daily`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `date` | date | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `ma_5` | double precision | Y |  |
| 10 | `ma_10` | double precision | Y |  |
| 11 | `ma_20` | double precision | Y |  |
| 12 | `ma_50` | double precision | Y |  |
| 13 | `ema_9` | double precision | Y |  |
| 14 | `ema_20` | double precision | Y |  |
| 15 | `ema_50` | double precision | Y |  |
| 16 | `rsi_14` | double precision | Y |  |
| 17 | `rsi_9` | double precision | Y |  |
| 18 | `rsi_30` | double precision | Y |  |
| 19 | `stoch_rsi_k` | double precision | Y |  |
| 20 | `stoch_rsi_d` | double precision | Y |  |
| 21 | `atr_14` | double precision | Y |  |
| 22 | `atr_20` | double precision | Y |  |
| 23 | `obv` | double precision | Y |  |
| 24 | `rvol` | double precision | Y |  |
| 25 | `rvol_10` | double precision | Y |  |
| 26 | `volume_ma_10` | double precision | Y |  |
| 27 | `volume_ma_20` | double precision | Y |  |
| 28 | `volume_usd` | double precision | Y |  |
| 29 | `return` | double precision | Y |  |
| 30 | `volatility_30min` | double precision | Y |  |
| 31 | `volatility_day` | double precision | Y |  |
| 32 | `volatility_5d` | double precision | Y |  |
| 33 | `volatility_20d` | double precision | Y |  |
| 34 | `intraday_return` | double precision | Y |  |
| 35 | `high_low_spread` | double precision | Y |  |
| 36 | `high_low_spread_pct` | double precision | Y |  |
| 37 | `consecutive_up` | integer | Y |  |
| 38 | `consecutive_down` | integer | Y |  |
| 39 | `vwap` | double precision | Y |  |
| 40 | `price_vs_vwap` | double precision | Y |  |
| 41 | `price_vs_ema9` | double precision | Y |  |
| 42 | `price_vs_ema20` | double precision | Y |  |
| 43 | `strat_candle` | character varying | Y |  |
| 44 | `strat_combo` | character varying | Y |  |
| 45 | `strat_setup` | boolean | Y |  |
| 46 | `ftfc_score` | double precision | Y |  |
| 47 | `ftfc_direction` | character varying | Y |  |
| 48 | `data_source` | character varying | Y |  |
| 49 | `inserted_at` | timestamp with time zone | N |  |
| 50 | `updated_at` | timestamp with time zone | N |  |
| 51 | `adjusted_close` | double precision | Y |  |
| 52 | `sma_200` | double precision | Y |  |
| 53 | `macd` | double precision | Y |  |
| 54 | `macd_signal` | double precision | Y |  |
| 55 | `macd_histogram` | double precision | Y |  |
| 56 | `bb_upper` | double precision | Y |  |
| 57 | `bb_lower` | double precision | Y |  |
| 58 | `bb_width` | double precision | Y |  |
| 59 | `bb_pct` | double precision | Y |  |


### `archive_yahoo_market_data_intraday`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `backtest_reports`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `run_id` | uuid | N |  |
| 2 | `tickers` | ARRAY | N |  |
| 3 | `report_md` | text | N |  |
| 4 | `total_trades` | integer | Y |  |
| 5 | `win_rate` | double precision | Y |  |
| 6 | `expectancy_pct` | double precision | Y |  |
| 7 | `sharpe` | double precision | Y |  |
| 8 | `created_at` | timestamp with time zone | N |  |


### `backtest_sweeps`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `run_id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `label` | character varying | N |  |
| 4 | `sweep_type` | character varying | N |  |
| 5 | `trades` | integer | Y |  |
| 6 | `win_rate` | double precision | Y |  |
| 7 | `avg_win` | double precision | Y |  |
| 8 | `avg_loss` | double precision | Y |  |
| 9 | `pf` | double precision | Y |  |
| 10 | `expectancy` | double precision | Y |  |
| 11 | `max_dd` | double precision | Y |  |
| 12 | `sharpe` | double precision | Y |  |
| 13 | `created_at` | timestamp with time zone | N |  |


### `backtest_walk_forward_folds`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `run_id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `use_strat` | boolean | N |  |
| 4 | `mode` | character varying | N |  |
| 5 | `fold_index` | integer | N |  |
| 6 | `train_start` | date | Y |  |
| 7 | `train_end` | date | Y |  |
| 8 | `test_start` | date | Y |  |
| 9 | `test_end` | date | Y |  |
| 10 | `total_trades` | integer | Y |  |
| 11 | `win_rate` | double precision | Y |  |
| 12 | `profit_factor` | double precision | Y |  |
| 13 | `expectancy` | double precision | Y |  |
| 14 | `sharpe` | double precision | Y |  |
| 15 | `max_dd` | double precision | Y |  |
| 16 | `avg_win` | double precision | Y |  |
| 17 | `avg_loss` | double precision | Y |  |
| 18 | `stability_score` | double precision | Y |  |
| 19 | `created_at` | timestamp with time zone | N |  |


### `daily_vex`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `snapshot_date` | date | N |  |
| 3 | `total_vex` | double precision | Y |  |
| 4 | `spot_estimate` | double precision | Y |  |
| 5 | `computed_at` | timestamp with time zone | Y |  |


### `earnings_calendar`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `earnings_date` | date | N |  |
| 4 | `company_name` | character varying | Y |  |
| 5 | `earnings_time` | character varying | Y |  |
| 6 | `eps_estimate` | double precision | Y |  |
| 7 | `market_cap` | double precision | Y |  |
| 8 | `sector` | character varying | Y |  |
| 9 | `has_options` | boolean | Y |  |
| 10 | `expected_move` | double precision | Y |  |
| 11 | `strategy` | character varying | N |  |
| 12 | `strike` | double precision | Y |  |
| 13 | `expiration` | date | Y |  |
| 14 | `premium` | double precision | Y |  |
| 15 | `score` | double precision | Y |  |
| 16 | `data_source` | character varying | N |  |
| 17 | `fetched_at` | timestamp with time zone | Y |  |
| 18 | `strike_hit` | jsonb | Y |  |
| 19 | `hit_date` | date | Y |  |
| 20 | `max_favorable` | jsonb | Y |  |
| 21 | `min_unfavorable` | jsonb | Y |  |
| 22 | `day0_check` | double precision | Y |  |
| 23 | `day1_check` | double precision | Y |  |
| 24 | `day2_check` | double precision | Y |  |
| 25 | `day3_check` | double precision | Y |  |
| 26 | `day4_check` | double precision | Y |  |
| 27 | `day5_check` | double precision | Y |  |
| 28 | `exp_result` | double precision | Y |  |
| 29 | `risk_reward` | double precision | Y |  |
| 30 | `hit_rsi` | jsonb | Y |  |
| 31 | `hit_sma20` | jsonb | Y |  |
| 32 | `hit_sma50` | jsonb | Y |  |
| 33 | `hit_ema9` | jsonb | Y |  |
| 34 | `hit_ema21` | jsonb | Y |  |
| 35 | `hit_vwap` | jsonb | Y |  |
| 36 | `hit_rvol` | jsonb | Y |  |
| 37 | `hit_atr` | jsonb | Y |  |
| 38 | `hit_price_vs_sma20` | jsonb | Y |  |
| 39 | `hit_price_vs_vwap` | jsonb | Y |  |
| 40 | `ohlc_volume` | jsonb | Y |  |
| 41 | `inserted_at` | timestamp with time zone | N |  |
| 42 | `updated_at` | timestamp with time zone | N |  |
| 43 | `av_earnings_date` | date | Y |  |
| 44 | `is_s_p_500` | boolean | Y |  |
| 45 | `stock_volume` | bigint | Y |  |
| 46 | `options_volume` | bigint | Y |  |
| 47 | `open_interest` | bigint | Y |  |
| 48 | `rv_1d_last_12q` | double precision | Y |  |
| 49 | `last_1d_reactions` | jsonb | Y |  |
| 50 | `eps_actual` | double precision | Y |  |
| 51 | `eps_surprise_pct` | double precision | Y |  |
| 52 | `ew_high_on_day` | double precision | Y |  |
| 53 | `ew_low_on_day` | double precision | Y |  |
| 54 | `ew_close_on_day` | double precision | Y |  |
| 55 | `ew_strike_verdict` | character varying | Y |  |
| 56 | `ew_strike_move_pct` | double precision | Y |  |
| 57 | `ew_minutes_to_hit` | integer | Y |  |
| 58 | `ew_minutes_in_zone` | integer | Y |  |
| 59 | `ew_day_change_pct` | double precision | Y |  |


### `earnings_calibration`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `calibration_date` | date | N |  |
| 2 | `min_nq` | integer | Y |  |
| 3 | `lookback_quarters` | integer | Y |  |
| 4 | `quintile_spread` | double precision | Y |  |
| 5 | `overall_hit_rate` | double precision | Y |  |
| 6 | `n_predictions` | integer | Y |  |
| 7 | `notes` | text | Y |  |
| 8 | `created_at` | timestamp with time zone | N |  |
| 9 | `n_q5_directional` | integer | Y |  |
| 10 | `avg_win_pct` | double precision | Y |  |
| 11 | `avg_loss_pct` | double precision | Y |  |
| 12 | `payoff_ratio` | double precision | Y |  |
| 13 | `expectancy_pct` | double precision | Y |  |
| 14 | `expectancy_dollars_per_1k` | double precision | Y |  |
| 15 | `profit_factor` | double precision | Y |  |
| 16 | `max_drawdown_pct` | double precision | Y |  |
| 17 | `sharpe_per_trade` | double precision | Y |  |
| 18 | `best_hold_horizon_days` | integer | Y |  |
| 19 | `n_with_options` | integer | Y |  |
| 20 | `avg_atm_straddle_iv_pct` | double precision | Y |  |
| 21 | `avg_implied_move_pct` | double precision | Y |  |
| 22 | `avg_realized_move_pct` | double precision | Y |  |
| 23 | `realized_vs_implied_ratio` | double precision | Y |  |
| 24 | `avg_long_straddle_pnl_pct` | double precision | Y |  |
| 25 | `avg_short_strangle_pnl_pct` | double precision | Y |  |
| 26 | `avg_long_call_pnl_pct` | double precision | Y |  |
| 27 | `avg_long_put_pnl_pct` | double precision | Y |  |


### `earnings_history`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `fiscal_date_ending` | date | N |  |
| 4 | `reported_date` | date | Y |  |
| 5 | `reported_eps` | double precision | Y |  |
| 6 | `estimated_eps` | double precision | Y |  |
| 7 | `surprise` | double precision | Y |  |
| 8 | `surprise_pct` | double precision | Y |  |
| 9 | `inserted_at` | timestamp with time zone | N |  |
| 10 | `report_time` | character varying | Y |  |
| 11 | `yahoo_report_time` | character varying | Y |  |


### `earnings_options_snapshots`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `symbol` | character varying | N |  |
| 3 | `snapshot_ts` | timestamp with time zone | N |  |
| 4 | `snapshot_date` | date | N |  |
| 5 | `contract_symbol` | character varying | Y |  |
| 6 | `option_type` | character varying | N |  |
| 7 | `expiration` | date | N |  |
| 8 | `strike` | double precision | N |  |
| 9 | `in_the_money` | boolean | Y |  |
| 10 | `contract_size` | character varying | Y |  |
| 11 | `bid` | double precision | Y |  |
| 12 | `ask` | double precision | Y |  |
| 13 | `last_price` | double precision | Y |  |
| 14 | `change` | double precision | Y |  |
| 15 | `percent_change` | double precision | Y |  |
| 16 | `last_trade_date` | timestamp with time zone | Y |  |
| 17 | `volume` | double precision | Y |  |
| 18 | `open_interest` | double precision | Y |  |
| 19 | `implied_volatility` | double precision | Y |  |
| 20 | `delta` | double precision | Y |  |
| 21 | `gamma` | double precision | Y |  |
| 22 | `theta` | double precision | Y |  |
| 23 | `vega` | double precision | Y |  |
| 24 | `rho` | double precision | Y |  |
| 25 | `underlying_price` | double precision | Y |  |
| 26 | `data_source` | character varying | Y |  |
| 27 | `inserted_at` | timestamp with time zone | N |  |


### `earnings_options_strategy_insights`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `calculation_date` | date | N |  |
| 3 | `quintile` | text | N |  |
| 4 | `ratio_bucket` | text | N |  |
| 5 | `structure` | text | N |  |
| 6 | `n_events` | integer | N |  |
| 7 | `hit_rate_pct` | double precision | Y |  |
| 8 | `mean_pnl_pct` | double precision | Y |  |
| 9 | `median_pnl_pct` | double precision | Y |  |
| 10 | `p10_pnl_pct` | double precision | Y |  |
| 11 | `p90_pnl_pct` | double precision | Y |  |
| 12 | `avg_implied_move_pct` | double precision | Y |  |
| 13 | `avg_realized_move_pct` | double precision | Y |  |
| 14 | `notes` | text | Y |  |
| 15 | `created_at` | timestamp with time zone | N |  |


### `earnings_options_strategy_winners`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `calculation_date` | date | N |  |
| 3 | `structure` | text | N |  |
| 4 | `quintile` | text | N |  |
| 5 | `rank` | integer | N |  |
| 6 | `ticker` | text | N |  |
| 7 | `event_date` | date | N |  |
| 8 | `archetype` | text | Y |  |
| 9 | `spot_entry` | double precision | Y |  |
| 10 | `spot_exit` | double precision | Y |  |
| 11 | `strike` | double precision | Y |  |
| 12 | `premium_per_share` | double precision | Y |  |
| 13 | `exit_value_per_share` | double precision | Y |  |
| 14 | `pnl_pct` | double precision | Y |  |
| 15 | `implied_move_pct` | double precision | Y |  |
| 16 | `realized_move_pct` | double precision | Y |  |
| 17 | `ratio` | double precision | Y |  |
| 18 | `created_at` | timestamp with time zone | N |  |


### `earnings_upcoming_with_history`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `refresh_date` | date | N |  |
| 3 | `ticker` | text | N |  |
| 4 | `earnings_date` | date | N |  |
| 5 | `earnings_time` | text | Y |  |
| 6 | `company_name` | text | Y |  |
| 7 | `market_cap` | double precision | Y |  |
| 8 | `sector` | text | Y |  |
| 9 | `eps_estimate` | double precision | Y |  |
| 10 | `expected_move` | double precision | Y |  |
| 11 | `prev_close` | double precision | Y |  |
| 12 | `implied_move_pct` | double precision | Y |  |
| 13 | `options_volume` | bigint | Y |  |
| 14 | `open_interest` | bigint | Y |  |
| 15 | `playability_score` | double precision | Y |  |
| 16 | `quintile` | text | Y |  |
| 17 | `archetype` | text | Y |  |
| 18 | `confidence_label` | text | Y |  |
| 19 | `recommended_structure_long_only` | text | Y |  |
| 20 | `recommended_structure_ic_mode` | text | Y |  |
| 21 | `total_quarters` | integer | Y |  |
| 22 | `n_beats` | integer | Y |  |
| 23 | `n_meets` | integer | Y |  |
| 24 | `n_misses` | integer | Y |  |
| 25 | `beat_rate_pct` | numeric | Y |  |
| 26 | `avg_abs_gap_pct` | numeric | Y |  |
| 27 | `dir_consistency_pct` | numeric | Y |  |
| 28 | `reversal_rate_pct` | numeric | Y |  |
| 29 | `avg_ratio` | numeric | Y |  |
| 30 | `lean_score` | numeric | Y |  |
| 31 | `long_winner_count` | integer | Y |  |
| 32 | `short_winner_count` | integer | Y |  |
| 33 | `last_3_events` | jsonb | Y |  |
| 34 | `created_at` | timestamp with time zone | N |  |


### `economic_events`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `event_date` | date | N |  |
| 3 | `event_time` | time without time zone | Y |  |
| 4 | `event_name` | character varying | N |  |
| 5 | `country` | character varying | Y |  |
| 6 | `importance` | character varying | Y |  |
| 7 | `actual` | character varying | Y |  |
| 8 | `forecast` | character varying | Y |  |
| 9 | `previous` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `gamma_events`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `alert_ts` | timestamp with time zone | N |  |
| 3 | `alert_date` | date | N |  |
| 4 | `alert_kind` | character varying | N |  |
| 5 | `alert_direction` | character varying | N |  |
| 6 | `level_kind` | character varying | N |  |
| 7 | `level_strike` | numeric | N |  |
| 8 | `distance_pct` | double precision | Y |  |
| 9 | `regime` | character varying | Y |  |
| 10 | `bar_close` | double precision | N |  |
| 11 | `bar_open` | double precision | Y |  |
| 12 | `ftfc_prev_day_dir` | character varying | Y |  |
| 13 | `vix_level` | double precision | Y |  |
| 14 | `vix_tercile` | character varying | Y |  |
| 15 | `tod_bucket` | character varying | Y |  |
| 16 | `dow` | smallint | Y |  |
| 17 | `fwd_close_5m` | double precision | Y |  |
| 18 | `fwd_close_15m` | double precision | Y |  |
| 19 | `fwd_close_30m` | double precision | Y |  |
| 20 | `fwd_close_60m` | double precision | Y |  |
| 21 | `fwd_close_240m` | double precision | Y |  |
| 22 | `fwd_close_1d` | double precision | Y |  |
| 23 | `fwd_close_5d` | double precision | Y |  |
| 24 | `fwd_ret_5m_bps` | double precision | Y |  |
| 25 | `fwd_ret_15m_bps` | double precision | Y |  |
| 26 | `fwd_ret_30m_bps` | double precision | Y |  |
| 27 | `fwd_ret_60m_bps` | double precision | Y |  |
| 28 | `fwd_ret_240m_bps` | double precision | Y |  |
| 29 | `fwd_ret_1d_bps` | double precision | Y |  |
| 30 | `fwd_ret_5d_bps` | double precision | Y |  |
| 31 | `computed_at` | timestamp with time zone | Y |  |


### `insider_transactions`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `transaction_date` | date | N |  |
| 4 | `executive` | character varying | Y |  |
| 5 | `title` | character varying | Y |  |
| 6 | `transaction_type` | character varying | Y |  |
| 7 | `shares` | double precision | Y |  |
| 8 | `share_price` | double precision | Y |  |
| 9 | `transaction_value` | double precision | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `insight_reports`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `as_of` | timestamp with time zone | N |  |
| 4 | `report` | jsonb | N |  |
| 5 | `model_versions` | jsonb | N |  |
| 6 | `cost_usd` | numeric | Y |  |
| 7 | `latency_ms` | integer | Y |  |
| 8 | `created_at` | timestamp with time zone | N |  |
| 9 | `per_role_cost` | jsonb | Y |  |


### `insight_reports_history`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `insight_run_id` | uuid | Y |  |
| 3 | `ticker` | character varying | N |  |
| 4 | `as_of` | timestamp with time zone | N |  |
| 5 | `report` | jsonb | N |  |
| 6 | `model_versions` | jsonb | Y |  |
| 7 | `cost_usd` | numeric | Y |  |
| 8 | `latency_ms` | integer | Y |  |
| 9 | `written_at` | timestamp with time zone | N |  |
| 10 | `run_kind` | character varying | N |  |
| 11 | `triggered_by` | character varying | Y |  |
| 12 | `notes` | text | Y |  |
| 13 | `per_role_cost` | jsonb | Y |  |


### `insight_runs`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `status` | character varying | N |  |
| 4 | `trigger` | character varying | N |  |
| 5 | `started_at` | timestamp with time zone | Y |  |
| 6 | `finished_at` | timestamp with time zone | Y |  |
| 7 | `error` | text | Y |  |
| 8 | `report_id` | uuid | Y |  |
| 9 | `created_at` | timestamp with time zone | N |  |


### `iwm_30m_predictions`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `bar_ts` | timestamp with time zone | N |  |
| 3 | `bar_date` | date | N |  |
| 4 | `bar_close` | double precision | Y |  |
| 5 | `pred_fwd_bps` | double precision | Y |  |
| 6 | `pred_direction` | character varying | Y |  |
| 7 | `pred_decile` | smallint | Y |  |
| 8 | `model_version` | character varying | Y |  |
| 9 | `computed_at` | timestamp with time zone | Y |  |


### `journal_entries`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | uuid | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `direction` | character varying | N |  |
| 4 | `entry_ts` | timestamp with time zone | N |  |
| 5 | `exit_ts` | timestamp with time zone | N |  |
| 6 | `entry_price` | double precision | N |  |
| 7 | `exit_price` | double precision | N |  |
| 8 | `return_pct` | double precision | Y |  |
| 9 | `notes` | text | Y |  |
| 10 | `created_at` | timestamp with time zone | N |  |
| 11 | `updated_at` | timestamp with time zone | N |  |
| 12 | `embedding` | USER-DEFINED | Y |  |


### `magnitude_walk_forward_results`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `phase` | character varying | N |  |
| 3 | `ticker` | character varying | N |  |
| 4 | `tf` | character varying | N |  |
| 5 | `fold` | character varying | N |  |
| 6 | `train_end` | date | Y |  |
| 7 | `test_end` | date | Y |  |
| 8 | `n_train` | integer | Y |  |
| 9 | `n_test` | integer | Y |  |
| 10 | `status` | character varying | Y |  |
| 11 | `logloss` | double precision | Y |  |
| 12 | `base_logloss` | double precision | Y |  |
| 13 | `beat` | double precision | Y |  |
| 14 | `ece` | double precision | Y |  |
| 15 | `ece_ceiling` | double precision | Y |  |
| 16 | `ece_pass` | boolean | Y |  |
| 17 | `accuracy` | double precision | Y |  |
| 18 | `base_accuracy` | double precision | Y |  |
| 19 | `accuracy_beat_pp` | double precision | Y |  |
| 20 | `explosive_base_rate` | double precision | Y |  |
| 21 | `explosive_precision` | double precision | Y |  |
| 22 | `explosive_lift` | double precision | Y |  |
| 23 | `decisive_hit_json` | text | Y |  |
| 24 | `fold_seconds` | integer | Y |  |
| 25 | `computed_at` | timestamp with time zone | N |  |
| 26 | `run_id` | character varying | Y |  |


### `market_data_cross_asset`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `vix_5m_delta` | double precision | Y |  |
| 5 | `vix_z_15` | double precision | Y |  |
| 6 | `ust10y_delta` | double precision | Y |  |
| 7 | `dxy_delta` | double precision | Y |  |
| 8 | `oil_z` | double precision | Y |  |
| 9 | `gold_z` | double precision | Y |  |
| 10 | `data_source` | character varying | N |  |
| 11 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_indicators`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `av_adx` | double precision | Y |  |
| 5 | `av_mfi` | double precision | Y |  |
| 6 | `av_chaikin_ad_osc` | double precision | Y |  |
| 7 | `av_aroon_up` | double precision | Y |  |
| 8 | `av_aroon_down` | double precision | Y |  |
| 9 | `av_roc` | double precision | Y |  |
| 10 | `av_bbands_upper` | double precision | Y |  |
| 11 | `av_bbands_middle` | double precision | Y |  |
| 12 | `av_bbands_lower` | double precision | Y |  |
| 13 | `av_bbands_bandwidth` | double precision | Y |  |
| 14 | `data_source` | character varying | N |  |
| 15 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_indicators_iwm`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `av_adx` | double precision | Y |  |
| 5 | `av_mfi` | double precision | Y |  |
| 6 | `av_chaikin_ad_osc` | double precision | Y |  |
| 7 | `av_aroon_up` | double precision | Y |  |
| 8 | `av_aroon_down` | double precision | Y |  |
| 9 | `av_roc` | double precision | Y |  |
| 10 | `av_bbands_upper` | double precision | Y |  |
| 11 | `av_bbands_middle` | double precision | Y |  |
| 12 | `av_bbands_lower` | double precision | Y |  |
| 13 | `av_bbands_bandwidth` | double precision | Y |  |
| 14 | `data_source` | character varying | N |  |
| 15 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_indicators_other`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `av_adx` | double precision | Y |  |
| 5 | `av_mfi` | double precision | Y |  |
| 6 | `av_chaikin_ad_osc` | double precision | Y |  |
| 7 | `av_aroon_up` | double precision | Y |  |
| 8 | `av_aroon_down` | double precision | Y |  |
| 9 | `av_roc` | double precision | Y |  |
| 10 | `av_bbands_upper` | double precision | Y |  |
| 11 | `av_bbands_middle` | double precision | Y |  |
| 12 | `av_bbands_lower` | double precision | Y |  |
| 13 | `av_bbands_bandwidth` | double precision | Y |  |
| 14 | `data_source` | character varying | N |  |
| 15 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_indicators_qqq`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `av_adx` | double precision | Y |  |
| 5 | `av_mfi` | double precision | Y |  |
| 6 | `av_chaikin_ad_osc` | double precision | Y |  |
| 7 | `av_aroon_up` | double precision | Y |  |
| 8 | `av_aroon_down` | double precision | Y |  |
| 9 | `av_roc` | double precision | Y |  |
| 10 | `av_bbands_upper` | double precision | Y |  |
| 11 | `av_bbands_middle` | double precision | Y |  |
| 12 | `av_bbands_lower` | double precision | Y |  |
| 13 | `av_bbands_bandwidth` | double precision | Y |  |
| 14 | `data_source` | character varying | N |  |
| 15 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_indicators_spy`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `av_adx` | double precision | Y |  |
| 5 | `av_mfi` | double precision | Y |  |
| 6 | `av_chaikin_ad_osc` | double precision | Y |  |
| 7 | `av_aroon_up` | double precision | Y |  |
| 8 | `av_aroon_down` | double precision | Y |  |
| 9 | `av_roc` | double precision | Y |  |
| 10 | `av_bbands_upper` | double precision | Y |  |
| 11 | `av_bbands_middle` | double precision | Y |  |
| 12 | `av_bbands_lower` | double precision | Y |  |
| 13 | `av_bbands_bandwidth` | double precision | Y |  |
| 14 | `data_source` | character varying | N |  |
| 15 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_intraday_iwm`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_intraday_other`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_intraday_qqq`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_intraday_spx`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `market_data_intraday_spy`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `interval` | character varying | N |  |
| 3 | `ts` | timestamp with time zone | N |  |
| 4 | `open` | double precision | Y |  |
| 5 | `high` | double precision | Y |  |
| 6 | `low` | double precision | Y |  |
| 7 | `close` | double precision | Y |  |
| 8 | `volume` | bigint | Y |  |
| 9 | `data_source` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `model_routing`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `role` | character varying | N |  |
| 2 | `provider` | character varying | N |  |
| 3 | `model` | character varying | N |  |
| 4 | `updated_at` | timestamp with time zone | N |  |
| 5 | `updated_by` | character varying | Y |  |


### `premarket_analysis_history`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `analysis_date` | date | N |  |
| 3 | `ticker` | character varying | N |  |
| 4 | `price` | double precision | Y |  |
| 5 | `rsi` | double precision | Y |  |
| 6 | `rsi_direction` | character varying | Y |  |
| 7 | `consecutive_up` | integer | Y |  |
| 8 | `consecutive_down` | integer | Y |  |
| 9 | `signal_status` | character varying | Y |  |
| 10 | `strat_candle` | character varying | Y |  |
| 11 | `strat_combo` | character varying | Y |  |
| 12 | `strat_setup` | boolean | Y |  |
| 13 | `ftfc_score` | double precision | Y |  |
| 14 | `ftfc_direction` | character varying | Y |  |
| 15 | `ftfc_labels` | jsonb | Y |  |
| 16 | `prev_day_high` | double precision | Y |  |
| 17 | `prev_day_low` | double precision | Y |  |
| 18 | `change_pct` | double precision | Y |  |
| 19 | `rvol` | double precision | Y |  |
| 20 | `sma200` | double precision | Y |  |
| 21 | `bb_upper` | double precision | Y |  |
| 22 | `bb_lower` | double precision | Y |  |
| 23 | `ema9` | double precision | Y |  |
| 24 | `ema20` | double precision | Y |  |
| 25 | `atr14` | double precision | Y |  |
| 26 | `volatility_20d` | double precision | Y |  |
| 27 | `macd_cross` | character varying | Y |  |
| 28 | `vol_regime` | character varying | Y |  |
| 29 | `above_sma200` | boolean | Y |  |
| 30 | `stoch_rsi_k` | double precision | Y |  |
| 31 | `stoch_rsi_d` | double precision | Y |  |
| 32 | `recommended_orb_window` | character varying | Y |  |
| 33 | `recommended_orb_reason` | text | Y |  |
| 34 | `playbook` | text | Y |  |
| 35 | `written_at` | timestamp with time zone | N |  |
| 36 | `run_kind` | character varying | N |  |
| 37 | `triggered_by` | character varying | Y |  |
| 38 | `notes` | text | Y |  |
| 39 | `data_as_of` | timestamp with time zone | Y |  |
| 40 | `data_freshness_status` | character varying | Y |  |
| 41 | `llm_overview` | text | Y |  |
| 42 | `llm_orb_explanation` | text | Y |  |
| 43 | `llm_analysis` | text | Y |  |
| 44 | `llm_playbook` | text | Y |  |
| 45 | `calls_trigger_price` | double precision | Y |  |
| 46 | `calls_trigger_name` | character varying | Y |  |
| 47 | `calls_stop_price` | double precision | Y |  |
| 48 | `calls_stop_name` | character varying | Y |  |
| 49 | `calls_t1_price` | double precision | Y |  |
| 50 | `calls_t2_price` | double precision | Y |  |
| 51 | `calls_t3_price` | double precision | Y |  |
| 52 | `puts_trigger_price` | double precision | Y |  |
| 53 | `puts_trigger_name` | character varying | Y |  |
| 54 | `puts_stop_price` | double precision | Y |  |
| 55 | `puts_stop_name` | character varying | Y |  |
| 56 | `puts_t1_price` | double precision | Y |  |
| 57 | `puts_t2_price` | double precision | Y |  |
| 58 | `puts_t3_price` | double precision | Y |  |


### `qqq_30m_predictions`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `bar_ts` | timestamp with time zone | N |  |
| 3 | `bar_date` | date | N |  |
| 4 | `bar_close` | double precision | Y |  |
| 5 | `pred_fwd_bps` | double precision | Y |  |
| 6 | `pred_direction` | character varying | Y |  |
| 7 | `pred_decile` | smallint | Y |  |
| 8 | `model_version` | character varying | Y |  |
| 9 | `computed_at` | timestamp with time zone | Y |  |


### `ranker_runs`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | uuid | N |  |
| 2 | `run_at` | timestamp with time zone | N |  |
| 3 | `candidate_count` | integer | N |  |
| 4 | `excluded_count` | integer | N |  |
| 5 | `weights_used` | jsonb | N |  |
| 6 | `results` | jsonb | N |  |
| 7 | `duration_ms` | integer | Y |  |


### `regime_combo_results`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `computed_date` | date | N |  |
| 3 | `window_start` | date | N |  |
| 4 | `window_end` | date | N |  |
| 5 | `ticker` | character varying | N |  |
| 6 | `horizon_min` | integer | N |  |
| 7 | `target_class` | character varying | N |  |
| 8 | `conditions` | text | N |  |
| 9 | `combo_order` | integer | Y |  |
| 10 | `hit_rate` | double precision | Y |  |
| 11 | `base_rate` | double precision | Y |  |
| 12 | `lift` | double precision | Y |  |
| 13 | `support` | integer | Y |  |
| 14 | `train_support` | integer | Y |  |
| 15 | `computed_at` | timestamp with time zone | N |  |


### `sec_filings`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `ticker` | character varying | Y |  |
| 3 | `cik` | character varying | N |  |
| 4 | `accession_number` | character varying | N |  |
| 5 | `form` | character varying | N |  |
| 6 | `filing_date` | date | N |  |
| 7 | `report_date` | date | Y |  |
| 8 | `items` | ARRAY | Y |  |
| 9 | `primary_doc` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `spy_30m_predictions`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `bar_ts` | timestamp with time zone | N |  |
| 3 | `bar_date` | date | N |  |
| 4 | `bar_close` | double precision | Y |  |
| 5 | `pred_fwd_bps` | double precision | Y |  |
| 6 | `pred_direction` | character varying | Y |  |
| 7 | `pred_decile` | smallint | Y |  |
| 8 | `model_version` | character varying | Y |  |
| 9 | `computed_at` | timestamp with time zone | Y |  |


### `strat_combo_results`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `computed_date` | date | N |  |
| 3 | `window_start` | date | N |  |
| 4 | `window_end` | date | N |  |
| 5 | `ticker` | character varying | N |  |
| 6 | `tf` | character varying | N |  |
| 7 | `target_class` | character varying | N |  |
| 8 | `conditions` | text | N |  |
| 9 | `combo_order` | integer | Y |  |
| 10 | `hit_rate` | double precision | Y |  |
| 11 | `base_rate` | double precision | Y |  |
| 12 | `lift` | double precision | Y |  |
| 13 | `support` | integer | Y |  |
| 14 | `train_support` | integer | Y |  |
| 15 | `computed_at` | timestamp with time zone | N |  |


### `strat_features_levels_1m`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


### `strat_features_levels_30m`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


### `strat_features_levels_4h`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


### `strat_features_levels_5m`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


### `strat_features_levels_60m`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `ts` | timestamp with time zone | N |  |
| 3 | `orb_5m_high` | double precision | Y |  |
| 4 | `orb_5m_low` | double precision | Y |  |
| 5 | `orb_5m_range` | double precision | Y |  |
| 6 | `orb_5m_mid` | double precision | Y |  |
| 7 | `orb_5m_high_pct` | double precision | Y |  |
| 8 | `orb_5m_low_pct` | double precision | Y |  |
| 9 | `orb_5m_mid_pct` | double precision | Y |  |
| 10 | `orb_5m_broke_high` | double precision | Y |  |
| 11 | `orb_5m_broke_low` | double precision | Y |  |
| 12 | `orb_5m_within_range` | double precision | Y |  |
| 13 | `orb_5m_trend` | double precision | Y |  |
| 14 | `orb_5m_distance` | double precision | Y |  |
| 15 | `orb_15m_high` | double precision | Y |  |
| 16 | `orb_15m_low` | double precision | Y |  |
| 17 | `orb_15m_range` | double precision | Y |  |
| 18 | `orb_15m_mid` | double precision | Y |  |
| 19 | `orb_15m_high_pct` | double precision | Y |  |
| 20 | `orb_15m_low_pct` | double precision | Y |  |
| 21 | `orb_15m_mid_pct` | double precision | Y |  |
| 22 | `orb_15m_broke_high` | double precision | Y |  |
| 23 | `orb_15m_broke_low` | double precision | Y |  |
| 24 | `orb_15m_within_range` | double precision | Y |  |
| 25 | `orb_15m_trend` | double precision | Y |  |
| 26 | `orb_15m_distance` | double precision | Y |  |
| 27 | `orb_30m_high` | double precision | Y |  |
| 28 | `orb_30m_low` | double precision | Y |  |
| 29 | `orb_30m_range` | double precision | Y |  |
| 30 | `orb_30m_mid` | double precision | Y |  |
| 31 | `orb_30m_high_pct` | double precision | Y |  |
| 32 | `orb_30m_low_pct` | double precision | Y |  |
| 33 | `orb_30m_mid_pct` | double precision | Y |  |
| 34 | `orb_30m_broke_high` | double precision | Y |  |
| 35 | `orb_30m_broke_low` | double precision | Y |  |
| 36 | `orb_30m_within_range` | double precision | Y |  |
| 37 | `orb_30m_trend` | double precision | Y |  |
| 38 | `orb_30m_distance` | double precision | Y |  |
| 39 | `prev_day_high` | double precision | Y |  |
| 40 | `prev_day_low` | double precision | Y |  |
| 41 | `prev_day_open` | double precision | Y |  |
| 42 | `prev_day_close` | double precision | Y |  |
| 43 | `prev_day_hl_mid` | double precision | Y |  |
| 44 | `prev_day_oc_mid` | double precision | Y |  |
| 45 | `prev_day_high_pct` | double precision | Y |  |
| 46 | `at_prev_day_high` | double precision | Y |  |
| 47 | `prev_day_low_pct` | double precision | Y |  |
| 48 | `at_prev_day_low` | double precision | Y |  |
| 49 | `prev_day_open_pct` | double precision | Y |  |
| 50 | `at_prev_day_open` | double precision | Y |  |
| 51 | `prev_day_close_pct` | double precision | Y |  |
| 52 | `at_prev_day_close` | double precision | Y |  |
| 53 | `prev_day_hl_mid_pct` | double precision | Y |  |
| 54 | `at_prev_day_hl_mid` | double precision | Y |  |
| 55 | `prev_day_oc_mid_pct` | double precision | Y |  |
| 56 | `at_prev_day_oc_mid` | double precision | Y |  |
| 57 | `broke_prev_day_high` | double precision | Y |  |
| 58 | `broke_prev_day_low` | double precision | Y |  |
| 59 | `prev_week_high` | double precision | Y |  |
| 60 | `prev_week_low` | double precision | Y |  |
| 61 | `prev_week_open` | double precision | Y |  |
| 62 | `prev_week_close` | double precision | Y |  |
| 63 | `prev_week_hl_mid` | double precision | Y |  |
| 64 | `prev_week_oc_mid` | double precision | Y |  |
| 65 | `prev_week_high_pct` | double precision | Y |  |
| 66 | `at_prev_week_high` | double precision | Y |  |
| 67 | `prev_week_low_pct` | double precision | Y |  |
| 68 | `at_prev_week_low` | double precision | Y |  |
| 69 | `prev_week_open_pct` | double precision | Y |  |
| 70 | `at_prev_week_open` | double precision | Y |  |
| 71 | `prev_week_close_pct` | double precision | Y |  |
| 72 | `at_prev_week_close` | double precision | Y |  |
| 73 | `prev_week_hl_mid_pct` | double precision | Y |  |
| 74 | `at_prev_week_hl_mid` | double precision | Y |  |
| 75 | `prev_week_oc_mid_pct` | double precision | Y |  |
| 76 | `at_prev_week_oc_mid` | double precision | Y |  |
| 77 | `broke_prev_week_high` | double precision | Y |  |
| 78 | `broke_prev_week_low` | double precision | Y |  |
| 79 | `prev_month_high` | double precision | Y |  |
| 80 | `prev_month_low` | double precision | Y |  |
| 81 | `prev_month_open` | double precision | Y |  |
| 82 | `prev_month_close` | double precision | Y |  |
| 83 | `prev_month_hl_mid` | double precision | Y |  |
| 84 | `prev_month_oc_mid` | double precision | Y |  |
| 85 | `prev_month_high_pct` | double precision | Y |  |
| 86 | `at_prev_month_high` | double precision | Y |  |
| 87 | `prev_month_low_pct` | double precision | Y |  |
| 88 | `at_prev_month_low` | double precision | Y |  |
| 89 | `prev_month_open_pct` | double precision | Y |  |
| 90 | `at_prev_month_open` | double precision | Y |  |
| 91 | `prev_month_close_pct` | double precision | Y |  |
| 92 | `at_prev_month_close` | double precision | Y |  |
| 93 | `prev_month_hl_mid_pct` | double precision | Y |  |
| 94 | `at_prev_month_hl_mid` | double precision | Y |  |
| 95 | `prev_month_oc_mid_pct` | double precision | Y |  |
| 96 | `at_prev_month_oc_mid` | double precision | Y |  |
| 97 | `broke_prev_month_high` | double precision | Y |  |
| 98 | `broke_prev_month_low` | double precision | Y |  |
| 99 | `prev_quarter_high` | double precision | Y |  |
| 100 | `prev_quarter_low` | double precision | Y |  |
| 101 | `prev_quarter_open` | double precision | Y |  |
| 102 | `prev_quarter_close` | double precision | Y |  |
| 103 | `prev_quarter_hl_mid` | double precision | Y |  |
| 104 | `prev_quarter_oc_mid` | double precision | Y |  |
| 105 | `prev_quarter_high_pct` | double precision | Y |  |
| 106 | `at_prev_quarter_high` | double precision | Y |  |
| 107 | `prev_quarter_low_pct` | double precision | Y |  |
| 108 | `at_prev_quarter_low` | double precision | Y |  |
| 109 | `prev_quarter_open_pct` | double precision | Y |  |
| 110 | `at_prev_quarter_open` | double precision | Y |  |
| 111 | `prev_quarter_close_pct` | double precision | Y |  |
| 112 | `at_prev_quarter_close` | double precision | Y |  |
| 113 | `prev_quarter_hl_mid_pct` | double precision | Y |  |
| 114 | `at_prev_quarter_hl_mid` | double precision | Y |  |
| 115 | `prev_quarter_oc_mid_pct` | double precision | Y |  |
| 116 | `at_prev_quarter_oc_mid` | double precision | Y |  |
| 117 | `broke_prev_quarter_high` | double precision | Y |  |
| 118 | `broke_prev_quarter_low` | double precision | Y |  |
| 119 | `prev_year_high` | double precision | Y |  |
| 120 | `prev_year_low` | double precision | Y |  |
| 121 | `prev_year_open` | double precision | Y |  |
| 122 | `prev_year_close` | double precision | Y |  |
| 123 | `prev_year_hl_mid` | double precision | Y |  |
| 124 | `prev_year_oc_mid` | double precision | Y |  |
| 125 | `prev_year_high_pct` | double precision | Y |  |
| 126 | `at_prev_year_high` | double precision | Y |  |
| 127 | `prev_year_low_pct` | double precision | Y |  |
| 128 | `at_prev_year_low` | double precision | Y |  |
| 129 | `prev_year_open_pct` | double precision | Y |  |
| 130 | `at_prev_year_open` | double precision | Y |  |
| 131 | `prev_year_close_pct` | double precision | Y |  |
| 132 | `at_prev_year_close` | double precision | Y |  |
| 133 | `prev_year_hl_mid_pct` | double precision | Y |  |
| 134 | `at_prev_year_hl_mid` | double precision | Y |  |
| 135 | `prev_year_oc_mid_pct` | double precision | Y |  |
| 136 | `at_prev_year_oc_mid` | double precision | Y |  |
| 137 | `broke_prev_year_high` | double precision | Y |  |
| 138 | `broke_prev_year_low` | double precision | Y |  |
| 139 | `ob_order_block_zone` | double precision | Y |  |
| 140 | `ob_order_block_high` | double precision | Y |  |
| 141 | `ob_order_block_low` | double precision | Y |  |
| 142 | `ob_order_block_mid` | double precision | Y |  |
| 143 | `ob_order_block_position` | double precision | Y |  |
| 144 | `ob_order_block_distance` | double precision | Y |  |
| 145 | `ob_order_block_test` | double precision | Y |  |
| 146 | `computed_at` | timestamp with time zone | Y |  |


### `strat_levels`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `as_of` | timestamp with time zone | N |  |
| 3 | `level_name` | character varying | N |  |
| 4 | `price` | numeric | N |  |
| 5 | `timeframe` | character varying | Y |  |
| 6 | `level_type` | character varying | Y |  |
| 7 | `strat_class` | character varying | Y |  |
| 8 | `is_current` | boolean | Y |  |
| 9 | `period_label` | character varying | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |
| 11 | `source_data_as_of` | timestamp with time zone | Y |  |


### `ticker_calibration`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `calibration_date` | date | N |  |
| 3 | `lookback_days` | integer | N |  |
| 4 | `atr_5m_median` | double precision | Y |  |
| 5 | `atr_15m_median` | double precision | Y |  |
| 6 | `atr_30m_median` | double precision | Y |  |
| 7 | `atr_60m_median` | double precision | Y |  |
| 8 | `atr_90m_median` | double precision | Y |  |
| 9 | `atr_120m_median` | double precision | Y |  |
| 10 | `atr_240m_median` | double precision | Y |  |
| 11 | `rvol_p25` | double precision | Y |  |
| 12 | `rvol_p50` | double precision | Y |  |
| 13 | `rvol_p75` | double precision | Y |  |
| 14 | `rvol_p95` | double precision | Y |  |
| 15 | `rsi_p10` | double precision | Y |  |
| 16 | `rsi_p25` | double precision | Y |  |
| 17 | `rsi_p50` | double precision | Y |  |
| 18 | `rsi_p75` | double precision | Y |  |
| 19 | `rsi_p90` | double precision | Y |  |
| 20 | `threshold_clean` | jsonb | Y |  |
| 21 | `threshold_wrong` | jsonb | Y |  |
| 22 | `threshold_noise` | jsonb | Y |  |
| 23 | `rvol_min` | double precision | Y |  |
| 24 | `rvol_max` | double precision | Y |  |
| 25 | `atr_expansion_x` | double precision | Y |  |
| 26 | `n_bars_used` | integer | Y |  |
| 27 | `earliest_bar_date` | date | Y |  |
| 28 | `latest_bar_date` | date | Y |  |
| 29 | `inserted_at` | timestamp with time zone | N |  |
| 30 | `drift_flagged` | boolean | Y |  |


### `ticker_info`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | N |  |
| 2 | `name` | character varying | Y |  |
| 3 | `exchange` | character varying | Y |  |
| 4 | `sector` | character varying | Y |  |
| 5 | `industry` | character varying | Y |  |
| 6 | `market_cap` | bigint | Y |  |
| 7 | `description` | text | Y |  |
| 8 | `asset_type` | character varying | Y |  |
| 9 | `raw_json` | jsonb | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |
| 11 | `updated_at` | timestamp with time zone | N |  |
| 12 | `relationships` | jsonb | Y |  |


### `top_movers_daily`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `id` | bigint | N |  |
| 2 | `snapshot_date` | date | N |  |
| 3 | `ticker` | character varying | N |  |
| 4 | `category` | character varying | N |  |
| 5 | `rank` | integer | Y |  |
| 6 | `price` | double precision | Y |  |
| 7 | `change_amount` | double precision | Y |  |
| 8 | `change_pct` | double precision | Y |  |
| 9 | `volume` | bigint | Y |  |
| 10 | `inserted_at` | timestamp with time zone | N |  |


### `v_etf_options_node`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `ticker` | character varying | Y |  |
| 2 | `snapshot_ts` | timestamp with time zone | Y |  |
| 3 | `snapshot_date` | date | Y |  |
| 4 | `market_session` | character varying | Y |  |
| 5 | `expiration` | date | Y |  |
| 6 | `strike` | double precision | Y |  |
| 7 | `net_gamma` | double precision | Y |  |
| 8 | `net_vega` | double precision | Y |  |
| 9 | `call_gamma_oi` | double precision | Y |  |
| 10 | `put_gamma_oi` | double precision | Y |  |
| 11 | `call_vega_oi` | double precision | Y |  |
| 12 | `put_vega_oi` | double precision | Y |  |
| 13 | `call_oi` | double precision | Y |  |
| 14 | `put_oi` | double precision | Y |  |
| 15 | `call_volume` | double precision | Y |  |
| 16 | `put_volume` | double precision | Y |  |


### `watchlists`


| # | column | type | null | notes |
|--:|---|---|:--:|---|
| 1 | `user_id` | character varying | N |  |
| 2 | `ticker` | character varying | N |  |
| 3 | `added_at` | timestamp with time zone | N |  |
| 4 | `removed_at` | timestamp with time zone | Y |  |
| 5 | `source` | character varying | Y |  |
| 6 | `notes` | text | Y |  |
| 7 | `in_brief` | boolean | N |  |
| 8 | `in_insight` | boolean | N |  |
| 9 | `signals` | boolean | N |  |
