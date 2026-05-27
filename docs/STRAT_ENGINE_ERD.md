# Strat Directionality Engine — Entity-Relationship Diagram

**Companion:** [`STRAT_ENGINE_ERD.drawio`](./STRAT_ENGINE_ERD.drawio) (open in drawio.com / VS Code drawio extension)
**Sibling:** [`STRAT_ENGINE_ARCHITECTURE.md`](./STRAT_ENGINE_ARCHITECTURE.md) (layers + flow)
**Status:** v1, M2 LOCKED 2026-05-26 (calibration=sigmoid cv=3)

## At-a-glance

```
                                          UPSTREAM SOURCES
                                          (read-only inputs)
                                  ┌────────────────────────────┐
                                  │  market_data_intraday_*    │  1-min raw bars (per ticker)
                                  │  market_data_daily         │  ^VIX EOD prices
                                  │  etf_options_snapshots     │  option chains for GEX/VEX
                                  │  gamma_levels_eod          │  King/Gate/Flip per (ticker, date)
                                  └─────────────┬──────────────┘
                                                │ read by strat_data_builder.py
                                                ▼
                              ┌──────────────────────────────────────┐
                              │  strat_features_{1m,5m,15m,30m,      │  SOURCE OF TRUTH
                              │                   60m,4h}            │  69 cols × 6 tables
                              │  PK: (ticker, ts)                    │  ~17k-1M rows/ticker
                              │  OHLCV + Strat + Indicators +        │
                              │  Forward Returns + Context (VIX/     │
                              │  GEX/VEX/dealer_regime)              │
                              └──────────────┬───────────────────────┘
                                             │
                          ┌──────────────────┼──────────────────────────┐
                          │ (read OHLCV)     │ (read everything)        │ (writes back)
                          ▼                  ▼                          │
            ┌─────────────────────┐  ┌──────────────────────┐  ┌────────┴──────────┐
            │ strat_features_     │  │ strat_dataset.py     │  │ strat_pred_{tf}   │
            │ levels_{tf}         │  │ (in-memory loader)   │  │ PK: (ticker, ts)  │
            │ COMPANION TABLE     │  │ LEFT JOIN both       │  │ p_1 / p_2u / p_2d │
            │ 146 cols × 6 tables │──┤ tables, add session- │  │ p_3 / top_class / │
            │ PK: (ticker, ts)    │  │ aware lags + label   │  │ calibrated_flag   │
            │ ORB + Historical    │  └──────┬───────────────┘  │ (NOT YET CREATED  │
            │ + Order Blocks      │         │                  │  — Stage 4 OUTPUT)│
            └─────────────────────┘         │                  └───────────────────┘
                                             ▼
                                  ┌──────────────────────┐
                                  │ Stages 2/3/4 consume │
                                  │ the labeled dataset  │
                                  └──────────┬───────────┘
                                             │
                          ┌──────────────────┴──────────────────┐
                          ▼                                      ▼
            ┌─────────────────────┐                  ┌───────────────────────┐
            │ strat_corr_ranked   │                  │ strat_ftfc            │
            │ PK: (ticker, tf,    │                  │ PK: (ticker, ts)      │
            │     target_class,   │                  │ Stage 5 OUTPUT —      │
            │     feature)        │                  │ multi-TF stacked      │
            │ Stage 3 OUTPUT —    │                  │ probabilities +       │
            │ MI ranking + dir    │                  │ continuity_score      │
            │ (NOT YET CREATED)   │                  │ (NOT YET CREATED)     │
            └─────────────────────┘                  └───────────────────────┘
```

---

## Table 1: `strat_features_{1m,5m,15m,30m,60m,4h}` (source-of-truth)

**Six tables, identical schema (69 cols).** One row per (ticker × bar) at that timeframe. Built by `gcp/research/strat_engine/strat_data_builder.py`.

| Section | Columns | Notes |
|---|---|---|
| **Identity** | `ticker VARCHAR(16)`, `ts TIMESTAMPTZ`, `tf VARCHAR(8)`, `bar_date DATE` | **PK: (ticker, ts)** |
| **OHLCV** | `open / high / low / close DOUBLE PRECISION`, `volume BIGINT` | Aggregated from 1-min source |
| **Strat sequence** | `strat_candle VARCHAR(8)` ('1' \| '2U' \| '2D' \| '3'), `prev_strat_candle`, `strat_combo VARCHAR(64)` ('22_bull_continuation' etc.), `is_continuation`, `is_reversal`, `is_inside`, `strat_setup BOOLEAN`, `consecutive_1s SMALLINT`, `trigger_high`, `trigger_low DOUBLE PRECISION` | ⚠️ `prev_strat_candle` is session-contaminated (single-shift); loader recomputes session-safe via `groupby('bar_date')` |
| **Indicators — trend** | `ema_9 / ema_20 / ema_50 / ema_200`, `sma_50 / sma_200` (DOUBLE) | |
| **Indicators — momentum** | `rsi_9 / rsi_14 / stoch_rsi_k / stoch_rsi_d`, `macd / macd_signal / macd_histogram` | |
| **Indicators — volatility** | `atr_14 / atr_20`, `bb_upper / bb_lower / bb_width / bb_pct` | |
| **Indicators — volume** | `obv / rvol / rvol_10` | |
| **Indicators — VWAP/relative** | `vwap`, `price_vs_vwap`, `price_vs_ema9 / price_vs_ema20` | |
| **Indicators — price action** | `consecutive_up / consecutive_down INTEGER`, `intraday_return`, `high_low_spread_pct DOUBLE` | |
| **Forward returns** | `fwd_close_{5,15,30,60}bars DOUBLE`, `fwd_ret_{5,15,30,60}bars_bps DOUBLE` | Last N bars of each ticker × TF have nulls (no future to look at) |
| **Regime** | `vix_close`, `vix_tercile VARCHAR(8)` (LOW/MID/HIGH @ 14.65/19.40), `total_gex`, `gex_tercile`, `total_vex`, `vex_tercile`, `dealer_regime VARCHAR(32)` (9 cells = GEX × VEX), `gamma_regime VARCHAR(32)`, `flip_price`, `distance_to_king_pct`, `distance_to_gate_pct` | ⚠️ `vix_close` uses PRIOR-day VIX (same-day-leak fix 2026-05-25) |
| **Bookkeeping** | `computed_at TIMESTAMPTZ DEFAULT now()` | Set by `bulk_copy_upsert` |

**Indexes:**
- PRIMARY KEY (ticker, ts)
- `ix_strat_features_{tf}_combo (ticker, strat_combo)`
- `ix_strat_features_{tf}_date (bar_date)`
- `ix_strat_features_{tf}_dr (dealer_regime)` (5m only)

**Row counts (production, 2026-05-22):**

| TF | IWM | SPY | QQQ |
|---|---|---|---|
| 1m | 1,012,586 | 995,364 | 999,232 |
| 5m | 202,819 | 199,205 | 200,159 |
| 15m | 67,650 | 66,436 | 66,756 |
| 30m | 33,834 | 33,231 | 33,388 |
| 60m | 18,221 | 17,902 | 17,984 |
| 4h | 0 | 0 | 0 | ⚠️ rebuilding now |

---

## Table 2: `strat_features_levels_{1m,5m,15m,30m,60m,4h}` (enrichment companion)

**Six tables, M2 schema is 146 cols (143 enrichment + ticker + ts + computed_at).** Built by `gcp/research/strat_engine/strat_enrich_levels.py`. Keyed 1:1 with `strat_features_{tf}` via (ticker, ts) — joined LEFT in `strat_dataset.load_labeled_dataset()`.

| Section | Columns | Notes |
|---|---|---|
| **Identity / FK** | `ticker VARCHAR(16)`, `ts TIMESTAMPTZ` | **PK: (ticker, ts)** matches strat_features_{tf} 1:1 |
| **ORB** (36 cols, 3 windows × 12) | `orb_{5m,15m,30m}_high / _low / _mid / _range`, `orb_*_high_pct / _low_pct / _mid_pct`, `orb_*_broke_high / _broke_low / _within_range / _trend / _distance` | Opening Range Breakout, 5/15/30-min windows |
| **Historical levels — Prev Day** (20 cols) | `prev_day_high / _low / _open / _close`, `prev_day_hl_mid / _oc_mid`, each `_pct` distance + `at_*` flag, `broke_prev_day_high / broke_prev_day_low` | PDH, PDL, PDO, PDC + derivatives |
| **Historical levels — Prev Week** (20 cols) | Same pattern: `prev_week_*` | PWH, PWL, etc. |
| **Historical levels — Prev Month** (20 cols) | `prev_month_*` | PMH, PML, etc. |
| **Historical levels — Prev Quarter** (20 cols) | `prev_quarter_*` | PQH, PQL, etc. |
| **Historical levels — Prev Year** (20 cols) | `prev_year_*` | PYH, PYL, etc. |
| **Order Blocks** (7 cols) | `ob_zone / ob_order_block_high / ob_order_block_low / ob_order_block_mid / ob_position / ob_distance / ob_test` | Institutional consolidation zones |
| **Bookkeeping** | `computed_at TIMESTAMPTZ DEFAULT now()` | |

⚠️ **NOT YET IN SCHEMA (gated OFF for M2):** the 40 `cur_*` columns from `calculate_current_period_levels` (today / WTD / MTD / QTD / YTD running HLO + position + range_pct + pct_from_open). Code is wired but `--include-current-period=False` by default. Will enable post-M2.

**Indexes:**
- PRIMARY KEY (ticker, ts)
- `ix_strat_features_levels_{tf}_ts (ts)`

**Row counts:**

| TF | IWM rows |
|---|---|
| 15m | 67,650 (full backfill) |
| 1m | 1,012,586 (backfill running now) |
| 5m | 202,819 (backfill running now) |
| 30m | 33,834 (backfill running now) |
| 60m | 18,221 (backfill running now) |
| 4h | 0 (pending 4h source build) |

---

## Table 3: `strat_pred_{tf}` (per-bar calibrated probabilities — Stage 4 output, NOT YET CREATED)

**Six tables planned.** Will hold per-bar predictions from each trained model. Currently the predictions are computed on-the-fly by Stages 5 + 6; persistence is deferred until the model is wired to a daily-refresh schedule.

| Column | Type | Notes |
|---|---|---|
| `ticker` | VARCHAR(16) | PK |
| `ts` | TIMESTAMPTZ | PK |
| `tf` | VARCHAR(8) | redundant with table name, kept for cross-table joins |
| `p_1` | DOUBLE PRECISION | calibrated P(next bar is inside) |
| `p_2u` | DOUBLE PRECISION | calibrated P(next bar breaks high) |
| `p_2d` | DOUBLE PRECISION | calibrated P(next bar breaks low) |
| `p_3` | DOUBLE PRECISION | calibrated P(next bar is outside) |
| `top_class` | VARCHAR(4) | argmax |
| `calibration` | VARCHAR(16) | 'sigmoid' \| 'isotonic' |
| `model_version` | VARCHAR(64) | model.pkl provenance |
| `computed_at` | TIMESTAMPTZ | |

**PK:** (ticker, ts) — joins to strat_features_{tf} 1:1.

---

## Table 4: `strat_corr_ranked` (Stage 3 driver rankings — NOT YET CREATED)

Currently the rankings are written to GCS JSON only (`gs://.../research/strat_engine/{ticker}_{tf}/corr_*.json`). Promotion to a SQL table is deferred until Stage 6 readout needs to query historical driver rankings.

| Column | Type | Notes |
|---|---|---|
| `ticker` | VARCHAR(16) | PK |
| `tf` | VARCHAR(8) | PK |
| `target_class` | VARCHAR(4) | PK ('1' \| '2U' \| '2D' \| '3') |
| `feature` | VARCHAR(64) | PK |
| `mi` | DOUBLE PRECISION | mutual information |
| `direction` | VARCHAR(4) | '+' \| '-' \| 'flat' \| '?' |
| `abs_pointbiserial` | DOUBLE PRECISION | linear sanity check |
| `rank` | INTEGER | 1 = strongest driver for this class |
| `computed_at` | TIMESTAMPTZ | |

**PK:** (ticker, tf, target_class, feature).

---

## Table 5: `strat_ftfc` (Stage 5 multi-TF stacked read — NOT YET CREATED)

Currently materialized on-demand in Stages 5+6, samples saved to GCS CSV. SQL table planned for production readout.

| Column | Type | Notes |
|---|---|---|
| `ticker` | VARCHAR(16) | PK |
| `ts` | TIMESTAMPTZ | PK (1m clock) |
| `{1m,5m,15m,30m,60m,4h}_p_{1,2u,2d,3}` | DOUBLE × 24 | per-TF calibrated probs |
| `{tf}_top` | VARCHAR(4) × 6 | per-TF argmax |
| `continuity_score` | DOUBLE PRECISION | weighted agreement [-1, +1] |
| `aligned_direction` | VARCHAR(8) | 'UP' \| 'DOWN' \| 'MIXED' |
| `computed_at` | TIMESTAMPTZ | |

**PK:** (ticker, ts).

---

## Upstream sources (read-only)

| Table | Used for | Joined how |
|---|---|---|
| `market_data_intraday_{IWM,SPY,QQQ}` | 1-min raw bars (the build input) | `WHERE ticker=X AND ts BETWEEN start AND end` |
| `market_data_daily` | `^VIX` EOD close → `vix_close` | by `bar_date - 1` (prior-day, no leak) |
| `etf_options_snapshots` | Option chains → `total_vex` via `lib.gamma.total_vex` | by (ticker, snapshot_date) quarterly batched |
| `gamma_levels_eod` | King/Gate/Flip price levels → `flip_price`, `distance_to_king_pct`, `distance_to_gate_pct` | by `bar_date - 1` (prior-day) |

---

## GCS artifacts (not SQL, but part of the data model)

```
gs://adept-mountain-474619-d4-trading-data/research/strat_engine/
├── {ticker}_{tf}/                   (per-cell artifacts)
│   ├── model.pkl                    CalibratedClassifierCV (Stage 4)
│   ├── features.txt                 column order at fit time
│   ├── classes.txt                  ['1', '2U', '2D', '3']
│   ├── metrics_*.json               OOS metrics + gate verdict + ECE bins
│   ├── eda_*.json                   base rates + transition matrices
│   ├── corr_*.json                  per-class MI rankings + binned curves
│   └── verify_*.json                Stage 1 gate results
└── _ftfc/{ticker}/                  (per-ticker FTFC samples)
    ├── sample_*.csv                 head/tail of stacked OOS predictions
    └── summary_*.json               continuity distribution + aligned_direction counts
```

---

## Open architecture decisions visible in the ERD

1. **Companion table vs schema migration.** `strat_features_levels_{tf}` exists separately from `strat_features_{tf}` because the source schema is locked in `gcp/queries/p7_schema.sql` and adding 143 cols would require careful migration. Reviewer's call: keep companion for M2; schema-migrate after M5.

2. **Predictions stored to GCS, not SQL.** Stages 4-6 write JSON + pickle to GCS rather than to SQL tables. Faster iteration during M2-M5; SQL tables (`strat_pred_{tf}`, `strat_corr_ranked`, `strat_ftfc`) become valuable when a UI or scheduled job needs to query historical predictions.

3. **`tf` as redundant column** in source tables (kept for cross-table joins like `strat_pred_1m JOIN strat_pred_15m USING (ticker)`).

4. **`prev_strat_candle` in source is session-contaminated.** Loader explicitly ignores it and recomputes session-safe lags via `groupby('bar_date').shift(N)`. Source column kept for backward compatibility but is functionally deprecated.

5. **Current-period gated OFF for M2.** 40 `cur_*` columns from `calculate_current_period_levels` are wired in code (`--include-current-period` flag) but DEFAULT FALSE so M2 comparison is fair vs the pre-existing 15m 143-col enrichment.
