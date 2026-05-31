# Strat Engine & Combo Pipelines — Complete Reference

> Everything the **Strat directionality engine** and the **combination-mining
> pipelines** (regime combos + Strat-candle combos) do, end to end, with
> runnable commands and real example output. Companion to
> [`PIPELINE.md`](PIPELINE.md) (the high-level two-lane map) — this is the deep
> dive into the research/discovery lane.

Last updated: 2026-05-31. All pipelines here are **research** (Lane 2): they
discover and explain edge; they do not place trades. They feed the live lane by
(a) earning feature promotions into `lib/indicators.add_all_indicators` and
(b) informing the strategy/brief logic the live monitor fires on.

> **This session's changes (2026-05-31)** — reflected throughout this doc:
> 1. `lib/indicators.add_all_indicators` was **decomposed into ~14 idempotent
>    `_add_*` blocks** with per-capability lean selectors (`add_signal_indicators`,
>    `add_brief_indicators`, `add_regime_indicators`, `add_strat_indicators`) +
>    `FEATURE_GROUPS`. The live `signal_monitor` and the premarket brief now
>    compute only the blocks they read; `add_all_indicators` output is unchanged
>    (byte-identical, 0.0-max-abs-diff parity test). See §0.
> 2. The `indicator-correlation` job became **target-modular** — it scores
>    indicators against four prediction targets (forward_return / regime / strat /
>    signal), not just forward returns. See §4.
> 3. Fixed a `NameError` (`LABEL_COL`) in Stage 3b `strat_corr_combos.py`.

---

## 0. The shared spine (read this first)

All pipelines are thin orchestration over four shared `lib/` modules — no math is
re-implemented (CLAUDE.md "one source of truth"):

| Module | Role |
|---|---|
| `lib/indicators.py : add_all_indicators` | the **single** indicator assembler — RSI, EMA, ATR, VWAP, RVOL, StochRSI, BB, MACD, ORB, the promoted vol/momentum features, etc. Decomposed into `_add_*` blocks (see below). |
| `lib/strat.py : StratClassifier` | candle classification (`1` / `2U` / `2D` / `3`) + combo detection (Failed_2U/2D, RevStrat, continuations) + FTFC scoring |
| `lib/combo_mining.py` | the combination-mining engine (binarize → select → mine → model-lift) used by **both** combo pipelines |
| `gcp/research/strat_engine/strat_dataset.py : label_next_bar_type` | the **one** session-aware "next Strat candle" label |

### 0.1 Indicator capability tiers — compute only what you read (2026-05-31)

`add_all_indicators` is now a thin composition of ~14 idempotent block helpers
(`_add_atr`, `_add_rsi`, `_add_emas`, `_add_smas`, `_add_vwap`, `_add_rvol`,
`_add_obv`, `_add_stochrsi`, `_add_bollinger`, `_add_macd`, `_add_consecutive`,
`_add_price_levels`, `_add_orb`, `_add_promoted_regime`), composed in dependency
order. Its 89-column output is **byte-identical** to before (pinned by a parity
test at 0.0 max-abs-diff), so every existing consumer and the strat/daily
backfills are unaffected.

On top of the blocks sit per-capability selectors so latency/relevant paths skip
the heavy blocks they never read:

| Selector | Used by | Runs | Skips |
|---|---|---|---|
| `add_all_indicators` | research / nightly / backfills (this whole doc's pipelines) | all 89 cols | — |
| `add_signal_indicators` | live `signal_monitor` | ATR, RSI, EMAs, VWAP, RVOL, OBV, StochRSI, MACD, consecutive, price-levels (~28 cols) | SMA, Bollinger, ORB (~39), promoted-regime |
| `add_brief_indicators` | premarket brief | + SMA, Bollinger (~35 cols); keeps VWAP + price-levels (the brief scores on `Price_vs_VWAP`) | RVOL, OBV, ORB, promoted-regime |
| `add_regime_indicators` / `add_strat_indicators` | research models | delegate to `add_all_indicators` | — |

`FEATURE_GROUPS = {signal, brief, regime, strat}` is the authoritative
output-column contract per capability (pinned by the parity test); `regime` /
`strat` mirror `combo_mining._STATIONARY_EXACT`. `select_features(df, capability)`
returns the present subset (tolerant of Time-gated absences). **Rule:** if a
consumer starts reading a new column, add the producing block to its selector AND
the column to `FEATURE_GROUPS`. The research pipelines below still call the full
`add_all_indicators`, so they see every feature.

### 0.2 `lib/combo_mining.py` — the engine both combo pipelines share

| Function | What it does |
|---|---|
| `stationary_feature_filter(columns)` | keep only stationary features (slopes / ATR-normalised distances / ratios); drop raw price levels that don't generalise |
| `binarize_conditions(df, features, train_mask)` | turn each feature into two boolean masks — `{f}>med` and `{f}<=med` — where `med` is the **train-only** median (no leakage) |
| `select_top_features(df, features, y_bin, train_mask, k=10, method="mutual_info")` | rank features by train-only association with the target class, return top-`k` to bound the combo search |
| `mine_combos(df, features, label, cls, train_mask, test_mask, max_order=3, min_support=500, top_k=12)` | enumerate 1-/2-/3-way AND-combos of the binarized conditions, score each **out-of-sample** by hit-rate and **lift** (= hit_rate ÷ base_rate), return the top-`top_k` with `min_support` ≥ 500 test rows |
| `model_lift(df, features, label, train_mask, test_mask, target, n_perm_repeats=2)` | train a gradient-boosted classifier on TRAIN, score OOS accuracy + lift vs the base rate, and compute **permutation importance** |
| `add_candidate_features(df)` | append still-experimental features (`MACD_Hist_Slope`) + research-only leakage-control lags (`*_Lag1`). Proven winners were promoted into `add_all_indicators` 2026-05-31, so this is now a thin staging layer |

**Key discipline baked in:** every threshold (the `med` in `>med`), every feature
ranking, and every model fit is computed on **TRAIN rows only**; hit-rate and lift
are measured on a held-out **TEST** split. A combo that looks good only because it
memorised the training data scores ~1.0× lift OOS and is discarded.

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

**Real table sizes** (`strat_features_<tf>`, pulled 2026-05-31):

| tf | IWM | SPY | QQQ |
|---|--:|--:|--:|
| 1m | 1,012,586 | 995,364 | 999,232 |
| 5m | 202,819 | 199,205 | 200,159 |
| 15m | 67,650 | 66,436 | 66,756 |
| 30m | 33,834 | 33,231 | 33,388 |
| 60m | 18,221 | 17,902 | 17,984 |
| 4h | 6,099 | 6,005 | 6,006 |

### 1.2 The 6 stages (+ Stage 3b)

`run_pipeline(engine, ticker, tf, train_until, ...)` runs these in order. Stages
with a **gate** can abort the pipeline; the rest are diagnostic/explainability.

| Stage | Module | What it does | Gates? |
|---|---|---|---|
| **1 — Verify** | `strat_data_builder` checks | Row-gap continuity, no duplicate timestamps, schema sanity on `strat_features_<tf>` | ✅ **hard gate** — abort if data is broken |
| **2 — EDA / base rates** | `strat_eda_baserates.py` | Class balance of `next_bar_type`, majority class, base rate to beat | no |
| **3 — Single-feature correlation** | `strat_corr_indicators.py` | Mutual-information / IC ranking of each indicator vs `next_bar_type`, per class | no |
| **3b — COMBINATION mining** | `strat_corr_combos.py` | Runs `lib.combo_mining` → top interpretable AND-combos per class + model permutation-importance, OOS at `train_until` → GCS JSON. **Explainability add-on (Effort B).** | **no — never blocks the train** |
| **4 — Train + calibrate** | `strat_pred_train.py` | Trains the classifier, calibrates probabilities, measures OOS accuracy + **lift** over base rate + **ECE** (calibration error) | ✅ **THE gate** — `verdict != PASS` ⇒ skip stages 5/6 |
| **5 — FTFC assembly** | `strat_ftfc_assemble.py` | Assembles the Full-Time-Frame-Continuity context (daily+weekly agreement) | no (skips on error) |
| **6 — Readout** | `strat_readout.py` | Human-readable summary (top drivers, gate verdict, per-class metrics) | no (skips on error) |

The Stage-4 gate has two thresholds passed in by the orchestrator:
- `base_rate_beat_pp` — OOS accuracy must beat the base rate by ≥ N percentage points.
- `ece_ceiling` — expected calibration error must be ≤ ceiling (probabilities must be *honest*, not just accurate).

If the model can't clear both, the run is marked `STOPPED_AFTER_STAGE_4_FAIL` and
no model is shipped — a failed predictor is worse than none.

### 1.3 Running it

```bash
# Full pipeline, one ticker × timeframe
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
  "oos_accuracy": 0.41,      // beat base rate by N pp
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

These are **actual rows** from `regime_combo_results` (576 rows = 3 tickers × 4
horizons × 4 classes × top-12, `computed_date = 2026-05-31`), pulled via
`db_query_cr.sh`. Top combos overall by OOS lift — every one is a 3-way AND
(`combo_order=3`) and they're dominated by the vol/momentum features promoted
that same day:

| Ticker | Horizon | Class | Combo (AND-joined) | OOS hit | Base | **Lift** | Support |
|---|--:|---|---|--:|--:|--:|--:|
| SPY | 60m | FLAT | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND Price_vs_VWAP>med` | 47.1% | 23.2% | **2.04×** | 2709 |
| SPY | 60m | FLAT | `BB_Width≤med AND Mins_Since_Open≤med AND Price_vs_VWAP>med` | 46.9% | 23.2% | **2.02×** | 2454 |
| SPY | 60m | FLAT | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND Price_vs_VWAP_ATR>med` | 46.6% | 23.2% | **2.01×** | 2813 |
| SPY | 60m | FLAT | `Realized_Vol_Short≤med AND BB_Width≤med AND Mins_Since_Open≤med` | 45.7% | 23.2% | **1.97×** | 3203 |
| IWM | 60m | FLAT | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND ORB_15m_Within_Range>med` | 46.4% | 23.7% | **1.96×** | 1274 |
| QQQ | 60m | FLAT | `BB_Width≤med AND Mins_Since_Open≤med AND ORB_15m_Within_Range>med` | 45.6% | 23.3% | **1.96×** | 1385 |
| IWM | 30m | FLAT | `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND ORB_15m_Within_Range>med` | 43.8% | 22.5% | **1.95×** | 1274 |

Best **BIG**-move combo (the magnitude class has a much higher base rate, so its
top lift is naturally lower):

| Ticker | Horizon | Class | Combo (AND-joined) | OOS hit | Base | **Lift** | Support |
|---|--:|---|---|--:|--:|--:|--:|
| QQQ | 60m | BIG | `Mins_Since_Open>med AND ORB_15m_Within_Range>med` | 72.3% | 48.8% | **1.48×** | 1129 |

**Max OOS lift per class** (latest run): FLAT **2.04×**, BIG **1.48×**, DOWN
**1.39×**, UP **1.32×**. FLAT carries by far the strongest lift because the
direction/magnitude classes (BIG/UP/DOWN) have much higher base rates (~0.49 for
BIG), leaving less headroom over random.

**How to read row 1:** for SPY, when short-horizon realized vol is below its
median AND it's early in the session (`Mins_Since_Open≤med`) AND price is holding
above VWAP, the next 60 minutes were flat/chop **47.1% of the time vs a 23.2%
base rate — 2.04× more likely than random**, across 2,709 out-of-sample bars.
Economically sensible: low-vol + early + above-VWAP = consolidation, not a
breakout.

The one clean **sign-flip**: `Mins_Since_Open` predicts FLAT when **below**
median (early session) and appears in the top BIG combo when **above** median
(late session) — early = chop, late = expansion. (The other top-FLAT features —
`Realized_Vol_Short`, `BB_Width` — are low-vol markers and don't reappear in the
top BIG combo, so this is a partial, not a perfect, symmetry.)

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
  SELECT computed_date, round(lift::numeric,2) AS lift, round(hit_rate::numeric,3) AS hit
  FROM regime_combo_results
  WHERE ticker='SPY' AND target_class='FLAT' AND horizon_min=60
    AND conditions LIKE '%Realized_Vol_Short%'
  ORDER BY computed_date DESC LIMIT 8"
```

`regime_combo_results` columns (actual schema): `id, computed_date,
window_start, window_end, ticker, horizon_min, target_class, conditions,
combo_order, hit_rate, base_rate, lift, support, train_support, computed_at`.

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

> **Fixed 2026-05-31:** `strat_corr_combos.py` imported `LABEL_CLASSES` from
> `strat_config` but not `LABEL_COL`, so `run_combos()` raised
> `NameError: name 'LABEL_COL' is not defined` on its first non-empty dataset —
> the `python -m …strat_corr_combos` entry point and the orchestrator's Stage 3b
> always failed before producing combos. `LABEL_COL` is now imported.

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

## 4. Target-Modular Indicator Correlation (new — 2026-05-31)

**Code:** `gcp/indicator_correlation_job.py`
**Cloud Run Job:** `indicator-correlation`
**Cadence:** manual / weekly
**Output table:** `indicator_correlation`
**Question it answers:** *"How strongly does each single indicator predict each of
the four things the platform actually forecasts — the forward return, the price
regime, the next Strat candle, and whether a fired signal wins?"*

Where the combo pipelines mine multi-feature AND-combos, this job ranks
**individual** indicators, but against **any target**, not just forward returns.
Targets are selectable via `--target` / `--targets` (env
`INDICATOR_CORR_TARGETS`; default = all four).

| `target_name` | Label source | Metrics written | `target_class` |
|---|---|---|---|
| `forward_return` | forward returns at each horizon | `pearson`, `rank_ic` | `''` (regression / overall) |
| `regime` | `regime_combo_miner.label_regimes` (BIG/UP/DOWN/FLAT) | per-class one-vs-rest `mutual_info` + `class_lift` + `rank_ic` | the class |
| `strat` | `StratClassifier` + `strat_dataset.label_next_bar_type` (1/2U/2D/3) | per-class `mutual_info` + `class_lift` + `rank_ic` | the class |
| `signal` | `signal_alerts` win/loss (`exit_return_pct > 0`) joined to fire-bar indicators | binary `mutual_info` + `class_lift` + `rank_ic`, scored only over `FEATURE_GROUPS['signal']` (what the live monitor actually saw) | `WIN` |

- **Metrics** reuse the label-agnostic helpers in `lib/combo_mining`:
  `mutual_info` via `mutual_info_classif`; `class_lift` = median-split
  P(class | feature-high) ÷ base-rate; `rank_ic` = one-vs-rest Spearman.
- **Rule 3.7:** every numeric metric is `NULL` when it can't be computed — never
  `0`. `target_class` uses an empty-string sentinel for the regression/overall
  row so the upsert dedups (NULLs are distinct in a Postgres UNIQUE index).
- **Rule 0:** bars are pulled once per ticker and sliced in memory (no per-row
  SQL); the `signal` target retains per-ticker frames only when requested.

### 4.1 Schema

`indicator_correlation` UNIQUE key / `ON CONFLICT` target:
`(computed_date, window_start, window_end, ticker, indicator, horizon_min,
target_name, target_class)`. Columns added this session: `target_name VARCHAR(32)
NOT NULL DEFAULT 'forward_return'`, `target_class VARCHAR(12)`,
`mutual_info DOUBLE PRECISION`, `class_lift DOUBLE PRECISION` (all idempotent
`ADD COLUMN IF NOT EXISTS`; numeric metrics NULLABLE).

### 4.2 Running it

```bash
# All four targets (default), SPY/IWM/QQQ
gcloud run jobs execute indicator-correlation --region us-east1 --wait

# Just one target
gcloud run jobs execute indicator-correlation --region us-east1 \
  --args="--target=regime" --wait

# A subset
gcloud run jobs execute indicator-correlation --region us-east1 \
  --args="--targets=forward_return,strat" --wait
```

### 4.3 Example output — pending first run

> ⚠️ **No real rows yet.** As of 2026-05-31 `indicator_correlation` is **empty**
> (verified: 0 rows): the schema migration + first target-modular run are pending
> deploy (`apply-schema-migrations` → Cloud Build → `indicator-correlation`).
> Once the first run lands, this section will be replaced with actual
> top-indicator rows per `target_name`. The **expected** shape is one row per
> `(ticker, indicator, horizon_min, target_name, target_class)`:

```text
target_name | target_class | indicator           | mutual_info | class_lift | rank_ic
------------+--------------+---------------------+-------------+------------+--------
regime      | BIG          | Realized_Vol_Short  |    <value>  |   <value>  | <value>
regime      | FLAT         | Mins_Since_Open     |    <value>  |   <value>  | <value>
strat       | 2U           | RSI_Divergence      |    <value>  |   <value>  | <value>
forward_ret | (blank)      | EMA9_Slope          |    NULL     |    NULL    | <value>   ← pearson/rank_ic only
signal      | WIN          | RVOL                |    <value>  |   <value>  | <value>
```

Verify after the first run:

```bash
./scripts/db_query_cr.sh -q "
  SELECT target_name, target_class, count(*) AS n_rows
  FROM indicator_correlation
  WHERE computed_date = current_date
  GROUP BY target_name, target_class ORDER BY target_name, target_class"
```

---

## 5. How the pipelines connect to live trading

```
        ┌─────────────────── RESEARCH (Lane 2) ───────────────────┐
        │                                                          │
  regime-combo (weekly)   strat-engine (manual)   indicator-correlation
        │                        │                        │
        └────────── surface indicators/combos with OOS edge ──────┘
                              │
            features that repeatedly rank top get PROMOTED
                              │
                    lib/indicators.add_all_indicators   ◄── single source of truth
                       (decomposed into _add_* blocks)
                              │
                 lean tiers select per-capability columns
                              │
        ┌─────────────────────┴─────────────────────┐
   signal-monitor (live, daily)            premarket-brief (daily)
   → add_signal_indicators                 → add_brief_indicators
   fires signal_alerts → Discord           morning context + levels
```

The pipelines never sit in the real-time path. They run on their own cadence,
write evidence to tables/GCS, and influence the live lane **only** through
deliberate feature promotion + strategy updates — so a research failure can never
stop a live signal, and a live change can never silently alter a backtest.

### Worked example — the 2026-05-31 loop (what actually happened this session)

1. `regime-combo` mining surfaced `Realized_Vol_Short`, `Mins_Since_Open`,
   `BB_Width`, `Price_vs_VWAP`/`Price_vs_VWAP_ATR`, and the ORB-range features as
   top OOS drivers of FLAT (low-vol/early/above-VWAP) and BIG (late session)
   across SPY/IWM/QQQ — see the **real** tables in §2.4 (576 rows,
   `computed_date=2026-05-31`; FLAT tops out at 2.04× lift).
2. The promoted vol/momentum features live in `add_all_indicators` (one place).
3. `add_all_indicators` was **decomposed into `_add_*` blocks** and the live
   `signal_monitor` was switched to the lean `add_signal_indicators` (the brief to
   `add_brief_indicators`) — so the live paths compute only what they read while
   still sharing the exact block math (output byte-identical; §0.1). Earlier the
   monitor hand-rolled a subset and silently lagged the engine.
4. The `indicator-correlation` job was made **target-modular** (§4) so we can rank
   each promoted indicator against the regime / strat / signal targets, not just
   forward returns — closing the loop with per-target evidence.
5. The next weekly `regime-combo` run keeps surfacing the *next* candidates — the
   loop continues.

---

## 6. Glossary

| Term | Meaning |
|---|---|
| **Lift** | hit_rate ÷ base_rate. 2.0× = the combo's class occurs twice as often as random under that condition. The headline metric. |
| **Support** | number of **out-of-sample** rows matching the combo. < 500 is discarded (`min_support`) — small samples lie. |
| **Base rate** | unconditional P(class) on the test split — the bar a combo must beat. |
| **OOS / out-of-sample** | measured on the held-out late-in-time TEST split, never the TRAIN split the thresholds were fit on. |
| **`>med` / `≤med`** | above / at-or-below the **train-only** median of that feature (binarized condition). |
| **`*_Lag1`** | a research-only one-bar lag of a feature (leakage-control candidate from `add_candidate_features`). |
| **Mutual information** | nonlinear association between a feature and the target class; 0 = independent. The single-feature ranking metric in §4 and Stage 3. |
| **`class_lift`** | per-class median-split lift: P(class \| feature above its median) ÷ base rate. The §4 per-class analogue of combo lift. |
| **`rank_ic`** | Spearman rank correlation (information coefficient); in §4's classification targets it's computed one-vs-rest against binary class membership. |
| **Permutation importance** | how much OOS accuracy drops when a feature is shuffled — the model's "which features actually matter" signal. |
| **ECE** | Expected Calibration Error — gap between predicted probability and observed frequency. Low ECE = honest probabilities. |
| **next_bar_type** | the t+1 Strat candle class (`1`/`2U`/`2D`/`3`), session-aware, the one shared label. |
| **FTFC** | Full-Time-Frame-Continuity — agreement of Strat direction across daily + weekly. |
| **FEATURE_GROUPS** | the per-capability output-column contract in `lib/indicators.py` ({signal, brief, regime, strat}); pins which columns each lean selector must produce. |
