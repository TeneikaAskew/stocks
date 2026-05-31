# Strat Engine & Combo Pipelines — Complete Reference

> Everything the **Strat directionality engine** and the **combination-mining
> pipelines** (regime combos + Strat-candle combos) do, end to end, with
> runnable commands and real example output. Companion to
> [`PIPELINE.md`](PIPELINE.md) (the high-level two-lane map) — this is the deep
> dive into the research/discovery lane.

Last updated: 2026-05-31. All three pipelines are **research** (Lane 2): they
discover and explain edge; they do not place trades. They feed the live lane by
(a) earning feature promotions into `lib/indicators.add_all_indicators` and
(b) informing the strategy/brief logic the live monitor fires on.

---

## 0. The shared spine (read this first)

All three pipelines are thin orchestration over four shared `lib/` modules — no
math is re-implemented (CLAUDE.md "one source of truth"):

| Module | Role |
|---|---|
| `lib/indicators.py : add_all_indicators` | the **single** indicator assembler — RSI, EMA, ATR, VWAP, RVOL, StochRSI, BB, MACD, ORB, the promoted vol/momentum features, etc. |
| `lib/strat.py : StratClassifier` | candle classification (`1` / `2U` / `2D` / `3`) + combo detection (Failed_2U/2D, RevStrat, continuations) + FTFC scoring |
| `lib/combo_mining.py` | the combination-mining engine (binarize → select → mine → model-lift) used by **both** combo pipelines |
| `gcp/research/strat_engine/strat_dataset.py : label_next_bar_type` | the **one** session-aware "next Strat candle" label |

### `lib/combo_mining.py` — the engine both combo pipelines share

| Function | What it does |
|---|---|
| `stationary_feature_filter(columns)` | keep only stationary features (slopes / ATR-normalised distances / ratios); drop raw price levels that don't generalise |
| `binarize_conditions(df, features, train_mask)` | turn each feature into two boolean masks — `{f}>med` and `{f}<=med` — where `med` is the **train-only** median (no leakage) |
| `select_top_features(df, label, cls, train_mask, k, method="spearman")` | rank features by train-only association with the target class, return top-`k` (default 12) to bound the combo search |
| `mine_combos(df, features, label, cls, train_mask, test_mask, max_order=3, min_support=500, top_k=12)` | enumerate 1-/2-/3-way AND-combos of the binarized conditions, score each **out-of-sample** by hit-rate and **lift** (= hit_rate ÷ base_rate), return the top-`top_k` with `min_support` ≥ 500 test rows |
| `model_lift(df, features, label, train_mask, test_mask, target, n_perm_repeats=2)` | train a `HistGradientBoostingClassifier` on TRAIN, score OOS accuracy + lift vs the base rate, and compute **permutation importance** (which features actually move the prediction) |
| `add_candidate_features(df)` | append still-experimental features (`MACD_Hist_Slope`) + research-only leakage-control lags (`*_Lag1`). Proven winners were promoted into `add_all_indicators` 2026-05-31, so this is now a thin staging layer |

**Key discipline baked in:** every threshold (the `med` in `>med`), every
feature ranking, and every model fit is computed on **TRAIN rows only**; hit-rate
and lift are measured on a held-out **TEST** split. A combo that looks good only
because it memorised the training data scores ~1.0× lift OOS and is discarded.

---

## 1. The Strat Directionality Engine

**Code:** `gcp/research/strat_engine/strat_orchestrator.py` (+ ~25 stage modules)
**Cloud Run Job:** `strat-engine` (research image: lightgbm + sklearn + scipy + shap)
**Cadence:** manual / on-demand (NOT scheduled)
**Question it answers:** *"Given the current bar's indicators + Strat state, what
is the next Strat candle (`1` / `2U` / `2D` / `3`) likely to be — and can we
predict it better than the base rate, with calibrated probabilities?"*

### 1.1 Data preparation — `strat_data_builder.py`

Aggregates raw 1-min bars from `market_data_intraday` up to each timeframe
(5m / 15m / 30m / 60m / 4h), then for every bar runs the shared spine:

```
1-min OHLCV → aggregate_to_timeframe → StratClassifier (candle + combo + FTFC)
            → add_all_indicators       (full indicator suite)
            → calculate_historical_levels / current-period levels / order blocks
            → forward returns at 5/15/30/60 bars
            → UPSERT into strat_features_<tf>
```

The `strat_features_<tf>` tables are the engine's input. (Note: the writer maps a
fixed column allow-list, so a freshly promoted indicator is computed here but not
persisted until its column is added — see the persistence warning in
`PIPELINE.md`.)

### 1.2 The 6 stages (+ Stage 3b)

`run_pipeline(engine, ticker, tf, train_until, ...)` runs these in order. Stages
with a **gate** can abort the pipeline; the rest are diagnostic/explainability.

| Stage | Module | What it does | Gates? |
|---|---|---|---|
| **1 — Verify** | `strat_data_builder` checks | Row-gap continuity, no duplicate timestamps, schema sanity on `strat_features_<tf>` | ✅ **hard gate** — abort if data is broken |
| **2 — EDA / base rates** | `strat_eda_baserates.py` | Class balance of `next_bar_type` (what % of bars are `1`/`2U`/`2D`/`3`), majority class, base rate to beat | no |
| **3 — Single-feature correlation** | `strat_corr_indicators.py` | Mutual-information / IC ranking of each indicator vs `next_bar_type`, per class. "Which single features matter?" | no |
| **3b — COMBINATION mining** | `strat_corr_combos.py` | Runs `lib.combo_mining` → top interpretable AND-combos per class + model permutation-importance, OOS at `train_until` → GCS JSON. **Explainability add-on (Effort B).** | **no — never blocks the train** |
| **4 — Train + calibrate** | `strat_pred_train.py` | Trains the classifier, calibrates probabilities (isotonic/Platt), measures OOS accuracy + **lift** over base rate + **ECE** (calibration error) | ✅ **THE gate** — `verdict != PASS` ⇒ skip stages 5/6 |
| **5 — FTFC assembly** | `strat_ftfc_assemble.py` | Assembles the Full-Time-Frame-Continuity context (daily+weekly agreement) for the predictions | no (skips on error) |
| **6 — Readout** | `strat_readout.py` | Human-readable summary of the run (top drivers, gate verdict, per-class metrics) | no (skips on error) |

The Stage-4 gate has two thresholds passed in by the orchestrator:
- `base_rate_beat_pp` — OOS accuracy must beat the base rate by ≥ N percentage points.
- `ece_ceiling` — expected calibration error must be ≤ ceiling (probabilities must be *honest*, not just accurate).

If the model can't clear both, the run is marked `STOPPED_AFTER_STAGE_4_FAIL`
and no model is shipped — a failed predictor is worse than none.

### 1.3 Running it

```bash
# Full pipeline, one ticker × timeframe, as-of a historical date (hermetic replay)
gcloud run jobs execute strat-engine --region us-east1 \
  --args="-m,gcp.research.strat_engine.strat_orchestrator,--mode=full,--ticker=IWM,--tf=15m" \
  --wait

# Just rebuild the feature tables for a timeframe
gcloud run jobs execute strat-engine --region us-east1 \
  --args="-m,gcp.research.strat_engine.strat_data_pipeline,--mode=summary" --wait

# Run ONLY Stage 3b (combo mining) without the full pipeline — local hermetic:
python -m gcp.research.strat_engine.strat_corr_combos --ticker IWM --tf 15m
```

### 1.4 Output shape (Stage 4 result)

```jsonc
"4_train": {
  "oos_accuracy": 0.41,      // beat base rate of ~0.30 by 11pp
  "base_rate": 0.30,
  "lift": 1.37,              // 1.37× better than guessing the majority class
  "ece": 0.038,              // calibration error (lower = honester probabilities)
  "gate_verdict": "PASS"
}
```

Stage 3b writes ranked combos per next-candle class to GCS
(`gs://<bucket>/<model-prefix>/...combos.json`) alongside the Stage-3 corr JSON.

---

## 2. Regime Combination Pipeline (Effort A)

**Code:** `gcp/regime_combo_job.py` + `scripts/analysis/regime_combo_miner.py`
**Cloud Run Job:** `regime-combo` (research image)
**Scheduler:** `regime-combo-weekly` — Sundays 05:00 ET
**Output table:** `regime_combo_results`
**Question it answers:** *"Which interpretable indicator combinations predict the
forward **price regime** — a big move, an up move, a down move, or a flat/chop —
out-of-sample, per ticker and per forward horizon?"*

### 2.1 The four regimes

For each bar it computes the forward return over horizon H (5/15/30/60 min) and
labels the regime. Thresholds (`tau_flat`, `tau_big`) are quantiles of `|return|`
fit on **TRAIN rows only**:

| Class | Family | Definition |
|---|---|---|
| **BIG** | magnitude | `|forward_return|` ≥ `tau_big` (a large move, either direction) |
| **UP** | direction | forward_return > 0 and not flat |
| **DOWN** | direction | forward_return < 0 and not flat |
| **FLAT** | direction | `|forward_return|` ≤ `tau_flat` (chop / inside / sideways) |

### 2.2 The algorithm (per ticker × horizon × class)

```
market_data_intraday (trailing 365d)
  → add_all_indicators + add_candidate_features
  → label_regimes (train-only thresholds)
  → split TRAIN (early) / TEST (late) by time   ← no look-ahead
  → select_top_features (train-only ranking)
  → mine_combos (1-/2-/3-way AND, scored OOS by lift)
  → model_lift (gradient-boost + permutation importance)
  → UPSERT top combos into regime_combo_results
```

### 2.3 Running it

```bash
# Default: SPY,IWM,QQQ × horizons 5,15,30,60 × trailing 365d, as-of today
gcloud run jobs execute regime-combo --region us-east1 --wait

# Custom tickers/horizons, dry-run (no DB write)
gcloud run jobs execute regime-combo --region us-east1 \
  --update-env-vars="^|^REGIME_COMBO_TICKERS=SPY,IWM,QQQ|REGIME_COMBO_HORIZONS=15,60" \
  --args="--dry-run" --wait

# Sandbox / ad-hoc (writes reports/regime_combo_predictors_<ticker>.md):
python -m scripts.analysis.regime_combo_miner --ticker SPY --horizons 5,15,30,60
```

### 2.4 Real example output (from the 2026-05-31 run)

Top FLAT-regime combos by OOS lift — note they're dominated by the features
promoted that same day:

| Ticker | Horizon | Combo (AND-joined) | OOS hit | Base | **Lift** | Support |
|---|---|---|---|---|---|---|
| SPY | 60m | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND Price_vs_VWAP>med` | 47.1% | 23.2% | **2.04×** | 2709 |
| SPY | 60m | `BB_Width≤med AND Mins_Since_Open≤med AND Price_vs_VWAP>med` | 46.9% | 23.2% | **2.02×** | 2454 |
| SPY | 60m | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND Price_vs_VWAP_ATR>med` | 46.6% | 23.2% | **2.01×** | 2813 |
| IWM | 60m | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND ORB_15m_Within_Range>med` | 46.4% | 23.7% | **1.96×** | 1274 |
| QQQ | 60m | `BB_Width≤med AND Mins_Since_Open≤med AND ORB_15m_Within_Range>med` | 45.6% | 23.3% | **1.96×** | 1385 |

**How to read row 1:** when short-horizon realized vol is below its median AND
it's early in the session AND price is above VWAP, SPY's next 60 minutes were
flat/chop **47% of the time vs a 23% base rate — 2.04× more likely than random**,
across 2,709 out-of-sample bars. Economically sensible: low-vol + early + holding
above VWAP = consolidation, not a breakout.

### 2.5 Querying the results

```bash
# Best BIG-move combo per ticker at the 30-min horizon, latest run
./scripts/db_query_cr.sh -q "
  SELECT ticker, conditions, round(lift::numeric,2) AS lift, support
  FROM regime_combo_results
  WHERE computed_date = current_date AND target_class='BIG' AND horizon_min=30
  ORDER BY ticker, lift DESC"

# Track how a combo's lift drifts week-over-week (computed_date is the time axis)
./scripts/db_query_cr.sh -q "
  SELECT computed_date, round(lift::numeric,2) AS lift
  FROM regime_combo_results
  WHERE ticker='SPY' AND target_class='FLAT' AND horizon_min=60
    AND conditions LIKE 'Realized_Vol_Short%'
  ORDER BY computed_date DESC LIMIT 8"
```

---

## 3. Strat-Candle Combination Pipeline (Effort B)

**Code:** `scripts/analysis/strat_combo_miner.py` (ad-hoc) + `strat_corr_combos.py` (Stage 3b, in the engine)
**Output table:** `strat_combo_results` (ad-hoc) / GCS JSON (Stage 3b)
**Question it answers:** *"Which indicator combinations predict the **next Strat
candle type** (`1` inside / `2U` directional-up / `2D` directional-down / `3`
outside) out-of-sample, per ticker and timeframe?"*

This is the same `lib.combo_mining` engine as Effort A, but the target is the
discrete next-candle class instead of a price regime. The label comes from the
**one** shared definition, `strat_dataset.label_next_bar_type` (session-aware
t+1) — no bar-iteration logic is re-implemented (Rule 3.6).

### 3.1 The four target classes

| Class | Strat meaning |
|---|---|
| `1` | inside bar (compression — neither prior high nor low broken) |
| `2U` | directional up (took out prior high only) |
| `2D` | directional down (took out prior low only) |
| `3` | outside bar (took out both — expansion) |

### 3.2 Running it

```bash
# Ad-hoc, multiple timeframes incl. daily (writes reports/strat_combo_predictors_<ticker>.md)
python -m scripts.analysis.strat_combo_miner --ticker IWM --tf 5m,15m,D

# As Stage 3b inside the full engine (runs automatically whenever Stage 3 runs):
gcloud run jobs execute strat-engine --region us-east1 \
  --args="-m,gcp.research.strat_engine.strat_orchestrator,--mode=full,--ticker=IWM,--tf=15m" --wait
```

### 3.3 Output shape

```jsonc
{
  "model": { "oos_accuracy": 0.38, "base_rate": 0.29, "lift": 1.31 },
  "combos": {
    "2U": [
      { "conditions": "RSI_Divergence>med AND Price_vs_EMA9_ATR>med",
        "hit_rate": 0.41, "base_rate": 0.27, "lift": 1.52, "support": 980 }
    ],
    "2D": [ ... ], "1": [ ... ], "3": [ ... ]
  }
}
```

---

## 4. How the three pipelines connect to live trading

```
        ┌─────────────────── RESEARCH (Lane 2) ───────────────────┐
        │                                                          │
  regime-combo (weekly)   strat-engine (manual)   strat-combo (Stage 3b)
        │                        │                        │
        └────────── surface combos with OOS edge ─────────┘
                              │
            features that repeatedly rank top get PROMOTED
                              │
                    lib/indicators.add_all_indicators   ◄── single source of truth
                              │
        ┌─────────────────────┴─────────────────────┐
   signal-monitor (live, daily)            premarket-brief (daily)
   fires signal_alerts → Discord           morning context + levels
```

The pipelines never sit in the real-time path. They run on their own cadence,
write evidence to tables/GCS, and influence the live lane **only** through
deliberate feature promotion + strategy updates — so a research failure can
never stop a live signal, and a live change can never silently alter a backtest.

### Worked example — the 2026-05-31 loop

1. `regime-combo` + `strat-engine` mining repeatedly surfaced `Realized_Vol_Short`,
   `Mins_Since_Open`, `Price_vs_VWAP_ATR`, `EMA9_Slope`, `EMA_Spread_ATR`,
   `BB_Squeeze`, `RSI_Divergence` as top OOS drivers across IWM/SPY/QQQ.
2. Those 9 features were **promoted** into `add_all_indicators` (one place).
3. `signal_monitor.calculate_indicators` was refactored to **delegate** to
   `add_all_indicators` — so the promoted features now reach **live firing**, not
   just research. (Before this, the monitor hand-rolled a subset and silently
   lagged the engine.)
4. The next weekly `regime-combo` run keeps surfacing the *next* candidates — the
   loop continues.

---

## 5. Glossary

| Term | Meaning |
|---|---|
| **Lift** | hit_rate ÷ base_rate. 2.0× = the combo's class occurs twice as often as random under that condition. The headline metric. |
| **Support** | number of **out-of-sample** rows matching the combo. < 500 is discarded (`min_support`) — small samples lie. |
| **Base rate** | unconditional P(class) on the test split — the bar a combo must beat. |
| **OOS / out-of-sample** | measured on the held-out late-in-time TEST split, never the TRAIN split the thresholds were fit on. |
| **`>med` / `≤med`** | above / at-or-below the **train-only** median of that feature (binarized condition). |
| **Permutation importance** | how much OOS accuracy drops when a feature is shuffled — the model's "which features actually matter" signal. |
| **ECE** | Expected Calibration Error — gap between predicted probability and observed frequency. Low ECE = honest probabilities. |
| **next_bar_type** | the t+1 Strat candle class (`1`/`2U`/`2D`/`3`), session-aware, the one shared label. |
| **FTFC** | Full-Time-Frame-Continuity — agreement of Strat direction across daily + weekly. |
