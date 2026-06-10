# Experiment Registry

**Single source of truth for every experiment and model run across the Strat
engine, Magnitude engine, direction research, and adjacent work.** Failed,
abandoned, superseded, and inconclusive experiments are included — a negative
result is a registry entry. Every entry cites its source (file / table / GCS
artifact / commit / doc). Where a value is not recorded it says **unknown**
rather than guessing.

Compiled 2026-06-05 from the docs, configs, research modules, analysis scripts,
archived pipelines, and GCS artifact conventions listed in §"Source artifacts."

> Convention note: numbers attributed to a doc (e.g. MAGNITUDE_ENGINE_RESULTS.md)
> are the recorded results; numbers I re-ran this session (gate-7 call/put,
> breakout-meta gross+net) are independently verified. Both are flagged.

---

# PART A — GLOBAL SECTIONS (once)

## A1. Master model index

| Architecture | Used by | Predicts | Lives in | Status |
|---|---|---|---|---|
| **LightGBM multiclass (4-class)** | STRAT-TYPE, MAG-SIZE | next candle / next-bar size bucket | `strat_pred_train.py`, `mag_pred_train.py` | TYPE works; SIZE fail (gate 7) |
| **LightGBM binary** | STRAT-DIR, DIR-REGIME, BREAKOUT-META meta-model | direction / follow-through | `strat_dir_walk_forward.py`, `dir_regime_walk_forward.py`, `breakout_meta_walk_forward.py` | DIR fail; META gross-PASS all cells / net-positive only IWM 5m on extended data (2026-06-09 reconfirm) |
| **OLS / linregress** | INTRADAY-MOM replication | last-30m ~ first-30m | `intraday_momentum.py` | null |
| **LogisticRegression (sklearn)** | INTRADAY-MOM walk-forward | sign of last-30m | `intraday_momentum.py` | null |
| **Rule-based primary (no ML)** | BREAKOUT-META primary, Strat classifier | trigger break / candle class | `lib/strat.py`, `breakout_meta_walk_forward.py` | deterministic |
| **Transition table + fixed vote-rule + held-out logistic** | STRAT-NEXTBAR (E-25) | next daily/weekly candle 2U/2D | `lib/strat.py:compute_strat_history`, `scripts/strat_oos_*`, `strat_clv_demech.py`, `strat_struct_backtest.py` | ✅ held-out OOS edge, but **gap-mechanical** (de-mech 2026-06-09: CLV_LAG1≈0, gap-neutral collapses to base) — trigger-break read, NOT standalone-tradeable |
| **CalibratedClassifierCV (sigmoid/isotonic)** | calibration diagnostic only | — | sklearn wrapper, optional `--calibration` | tested, NOT used (hurt ECE) |
| **Stacked regression + voter overlay (LightGBM→Ridge/Lasso)** | archived P7 pipeline | fwd return / next candle | `gcp/research/_archive/p7c,p7f,p7g_*.py` | ARCHIVED — net-negative |
| XGBoost / SVM / HAR / torch / statsmodels-sequence | — | — | — | **NOT IMPLEMENTED** (searched; none present) |

Baselines used as nulls: train-prior class baseline (log-loss), majority-class
accuracy, naïve DoW×30-min calendar lookup, "take every breakout," "follow the
gamma regime."

## A2. Master dataset / feature-surface index

| Surface / table | Family | Cols | Tickers / TFs / span | Rows (approx) | Source |
|---|---|---|---|---|---|
| `strat_features_<tf>` | spine (price/TA + strat-seq + gamma) | ~140 | SPY/IWM/QQQ; 1m/5m/15m/30m/60m/4h; 2016→2026 | ~130k/ticker at 5m | `strat_data_builder.py` |
| `strat_features_levels_<tf>` | levels (ORB, Prev D/W/M/Q/Y, order-blocks, king/gate dist) | ~20 | same | same | `strat_enrich_levels.py` |
| `market_data_intraday` (1min) | raw OHLCV | 6 | SPY/IWM/QQQ; 1min; 2016→2026 | ~1M/ticker | `gcp/schema.sql:100` |
| `etf_options_snapshots` | options chain (IV, delta, OI) | ~20 | SPY/IWM/QQQ; EOD+intraday; 2019→2026 | ~92M total | `gcp/schema.sql:135` |
| `market_data_daily` | daily bars (incl ^VIX/^VIX3M/^VVIX) | OHLCV | many; daily; 25y | unknown | direction R&D cross_asset |
| `news_sentiment` | news/topic | 9 derived | market-wide; 2010→2026 | ~70k (sparse pre-2025) | DIRECTION_FEATURES_R&D.md:30 |
| `market_data_indicators` | AV daily indicators (ADX/MFI/Aroon/ROC) | 7 | daily | ~6.5k/ticker | MAG phase 2 |
| `market_data_cross_asset` | VIX/UST10Y/DXY/oil/gold deltas | 6 | intraday | unknown (backfill pending) | MAG phase 4 |
| `magnitude_walk_forward_results` | per-fold result rows | — | — | — | `mag_walk_forward.py` |
| `strat_pred_<tf>` | per-bar calibrated probs | — | — | — | `strat_pred_train.py` |

Feature families used as tags: **price/TA, volatility, volume, VWAP, gamma/
options, calendar/event, cross-asset, strat-sequence, levels/ORB.** Order-flow /
tick-microstructure: **NOT available** (the documented blocker for direction).

## A3. Cross-cutting reframes & decision rules

1. **Information class — INTERNAL vs EXTERNAL** (CLAUDE.md 3.7): own-code failures
   re-raise; vendor failures return typed UNAVAILABLE. Governs all data access.
2. **Variance Risk Premium wall:** any bet on a move the option market prices
   loses on average (implied ≥ realized). Killed MAG-SIZE body, excursion-as-
   straddle, and call/put. Only *underlying-vehicle* strategies escape it.
3. **Predict structure/size, not direction:** direction (close>open) is
   near-EMH-unlearnable on these instruments; structure (candle) and size (ATR
   bucket) are learnable. Drove the whole engine split.
4. **Meta-labeling (López de Prado):** when a rule gives direction (Strat
   breakout), don't predict direction — predict *whether to take it* (triple
   barrier follow-through). The one reframe that produced a real edge.
5. **A first-pass null is a hypothesis about the TEST:** self-audit every null
   for structural flaws (wrong target, wrong metric, label corruption) before
   believing it. Caught the breakout-meta false-fail.
6. **Costs are a first-class gate:** net-of-cost / friction sweep is mandatory;
   timeframe selection is cost-fraction selection.
7. **Pre-committed, immutable success bars** (per engine): set BEFORE running so
   verdicts can't be moved. Magnitude's 7 gates and the strat log-loss/ECE gates
   are pre-registered.
8. **Locked hyperparameters across experiments** so a pass is attributable to
   features, not tuning.

## A4. Literature anchors

| Anchor | Informed | Outcome |
|---|---|---|
| López de Prado, *Advances in Financial ML* (triple-barrier, meta-labeling) | STRAT-BREAKOUT-META | gross edge found |
| Gao, Han, Li & Zhou — *Market Intraday Momentum* (2018, JFE) | INTRADAY-MOM | anomaly decayed (null) |
| Cont, Kukanov & Stoikov — *Price Impact of Order Book Events* (OFI) | FLOW-OFI (proposed, deferred) | not built — needs order-flow data |
| Dealer gamma / GEX regime (SpotGamma et al.) — pos-γ revert / neg-γ momentum | DIR-REGIME | null even regime-split |
| Variance Risk Premium / gamma-scalping (RV vs IV) | gate-7, call/put | priced-in confirmed |
| Intraday volatility U-shape seasonality | gate-7 critique (HONEST-GATE7, deferred) | flat-IV benchmark flagged |

Full synthesis with URLs: `docs/MODELS_END_TO_END.md` §refs and the session
research notes.

## A5. Shared conventions

- **Fold scheme:** 8 anchored **expanding** walk-forward windows, test years
  2019→2026 (`DEFAULT_CUTOFFS`). `MIN_TEST_BARS=200`.
- **Embargo/purge:** **no explicit purge/embargo gap.** Mitigation = strictly
  t+1 session-aware label (never crosses overnight gap) so train/test overlap is
  one bar at the boundary. (A formal purge is an open item — §A6.)
- **Hyperparameters (locked):** `n_estimators=300, lr=0.05, max_depth=6,
  num_leaves=31, min_child_samples=100, seed=42`, no bagging (deterministic).
- **ECE:** multiclass expected calibration error, 10 bins by max-proba
  confidence; ceiling 0.05 (5m/15m), 0.075 (30m). `expected_calibration_error()`
  in `strat_pred_train.py`.
- **Calibration:** `"none"` (raw LightGBM softmax) — sigmoid/isotonic available
  as diagnostics; sigmoid tested and rejected (§E-20).
- **Leakage guards:** `featurize()` drops all `fwd_*`/`next_*`/derived-flag
  columns; label strictly t+1; ATR denominator t-known; ORB fixed post-window;
  level lookups prior-day. Audited (§E-19).

## A6. Open items & reproducibility gaps

- **BREAKOUT-META net:** ⚠️ **PARTIAL / fragile** (E-24 + 2026-06-09 reconfirmation).
  META (gross) reproduces PASS on all cells, but on data extended to 2026-06 the
  NET edge at realistic fill is **only a clean net-positive on IWM 5m (+0.110 R,
  8/8)** — SPY 5m, QQQ 5m, SPY 15m all NET_FAIL (4/8–4/7, median R ≈ 0). The
  2026-06-05 "net-positive across all 3 tickers" did NOT robustly survive. The
  stop-limit/realistic-entry execution model is confirmed correct; net edge is
  marginal and ticker-specific — not yet shippable multi-ticker. Remaining:
  decision-latency model, ~10% same-tf-fallback labels, real L2/tick order-flow
  vendor, IWM/QQQ 15m weak.
- **No formal purge/embargo** around fold boundaries (mitigated by t+1 label).
- **No cutoff-shift perturbation** robustness test (only bootstrap-on-test-bars;
  seed-replication is a no-op on deterministic LightGBM).
- **MAG Phase 4 (cross-asset) never executed** (backfill pending); **Phase 5
  (gamma) deferred** — both moot after gate-7.
- **options_derived** direction family **INFEASIBLE** (pg8000 timeout) — needs a
  pre-materialized `option_daily_features` table to test.
- **HONEST-GATE7** (time-of-day IV / like-for-like / real gamma-scalp P&L) and
  **FLOW-OFI** (order-flow) proposed, **not built**.
- **Calibration decision scoped to IWM**; per-ticker re-verify pending.
- **FTFC weights** are a locked placeholder, not a walk-forward output yet.
- Exact row counts for several tables: **unknown** (not recorded).

## A7. Source artifacts consulted

Docs: `MAGNITUDE_ENGINE_RESULTS.md`, `MODEL_RETHINK_PLANS.md`, `MODEL_CATALOG.md`,
`MODELS_END_TO_END.md`, `MAGNITUDE_DIRECTIONAL_SESSION_HANDOFF.md`,
`DIRECTION_FEATURES_R&D.md`, `STRAT_ENGINE_AND_COMBO_PIPELINE.md`,
`STRAT_ENGINE_ARCHITECTURE.md`, `STRAT_METHODOLOGY.md`, `STRAT_IMPLEMENTATION_PLAN.md`,
`COST_ANALYSIS.md`, `docs/research/2026-05-23/RESEARCH_PLAN.md`.
Code: `gcp/research/magnitude_engine/*`, `gcp/research/strat_engine/*`,
`scripts/implied_vs_realized_check.py`, `scripts/magnitude_movement_sim.py`,
`scripts/bootstrap_gate_fragility.py`, `scripts/naive_calendar_lookup_baseline.py`,
`scripts/model_vs_calendar_explosive_decomp.py`,
`scripts/check_event_window_concentration.py`, `scripts/analysis/phase{1..7}_*.py`,
`gcp/research/_archive/p7*`, `lib/strat.py`, `lib/combo_mining.py`.
Artifacts: `gs://adept-mountain-474619-d4-trading-data/research/{strat,magnitude}_engine/<ticker>_<tf>/*.json`.

---

# PART B — PER-EXPERIMENT REGISTRY

## E-01 · STRAT-TYPE (next-candle structure model)
- **Engine/area:** strat
- **Status:** validated (production cockpit signal)
- **Date/branch/commit:** ~2026-05-26; strat_engine; commit `5abef53` area. unknown exact run id.
- **Question:** can we predict the next bar's Strat candle *shape* from the spine?
- **Target:** `next_bar_type ∈ {1, 2U, 2D, 3}` (t+1 lead of `strat_candle`, session-aware).
- **Data:** SPY/IWM/QQQ; 5m/15m/30m (also 1m/60m/4h built); 2019→2026; ~130k bars/ticker at 5m.
- **Features:** ~140 spine — price/TA + volatility + volume + VWAP + gamma/options + strat-sequence one-hots (chosen: it's the full persisted surface; dtype-discovered so level cols are included).
- **Structure:** LightGBM 4-class; 8-fold anchored expanding; calibration none; 6-stage pipeline with Stage 4 as the gate.
- **Gates / null:** HARD = OOS log-loss < train-prior baseline AND ECE ≤ 0.05; ADVISORY = accuracy beat ≥ 5pp. Null = train-prior class baseline.
- **Variants/results:** beats baseline by **+0.11 to +0.16 median log-loss** across TFs (per `STRAT_ENGINE_AND_COMBO_PIPELINE.md`); adaptive + per-class variants in E-02. Exact per-fold ECE: unknown here (in GCS JSON).
- **Correlation analysis:** Stage 3 MI ranking + Stage 3b combo lift fed feature understanding (E-04/E-05).
- **Approach/why:** Strat methodology is about candle structure/continuity, so the next *shape* is the native, well-posed target.
- **Worked / not:** worked — structure is learnable.
- **Verdict:** ✅ WORKS.
- **Leaks/bugs:** reviewer flagged the +0.11–0.16 beat as possible shared leak → `strat_leakage_audit.py` ruled it out (E-19).
- **Gaps:** FTFC weights placeholder; per-ticker calibration re-verify.
- **Artifacts:** `strat_walk_forward.py`; `gs://.../research/strat_engine/<ticker>_<tf>/walk_forward_*.json`; `strat_pred_<tf>` table.

## E-02 · STRAT-TYPE variants (adaptive, per-class)
- **Engine/area:** strat · **Status:** partial/diagnostic · **Date:** unknown.
- **Question:** does an adaptive-lag or one-vs-rest framing improve the TYPE model?
- **Target:** same `next_bar_type`. **Data:** same.
- **Structure:** `strat_walk_forward_adaptive.py` (adaptive mode), `strat_pred_per_class.py` (OvR per class).
- **Results:** unknown (artifacts in GCS; not summarized in a doc).
- **Verdict:** inconclusive/diagnostic.
- **Artifacts:** `strat_walk_forward_adaptive.py`, `strat_pred_per_class.py`; `gs://.../walk_forward_adaptive_*.json`, `per_class_predictions_*.json`.

## E-03 · STRAT Stage 2 — EDA / base rates
- **Engine/area:** strat · **Status:** validated (descriptive) · **Date:** ~2026-05-25.
- **Question:** class balance & transition structure of `next_bar_type`; the base rate the model must beat.
- **Target:** distribution of `next_bar_type`; P(next|prev) transition matrices.
- **Data:** SPY/IWM/QQQ all TFs.
- **Structure:** `strat_eda_baserates.py`; also reproducible 2/3-bar sequence analyses in `scripts/analysis/phase1_strat_mining.py`.
- **Results:** base rates + transitions (exact numbers: unknown here; in artifacts).
- **Approach/why:** you can't claim "beat base rate" without measuring it.
- **Verdict:** ✅ descriptive baseline.
- **Artifacts:** `strat_eda_baserates.py`, `scripts/analysis/phase1_strat_mining.py`.

## E-04 · STRAT Stage 3 — single-feature correlation (MI rank)
- **Engine/area:** strat (correlation analysis) · **Status:** validated · **Date:** ~2026-05-26.
- **Question:** which indicators carry marginal association with each next-candle class?
- **Target:** per-class (one-vs-rest) association vs `next_bar_type`.
- **Method:** mutual-information rank per (ticker, tf, class). **Not** Pearson/rank-IC (no IC implementation exists — see E-22 note).
- **Features:** all numeric spine cols (dtype-discovered).
- **Results:** per-class indicator rankings; key finding — strong association with structure/size, **near-zero for body direction** (foreshadowed E-07).
- **Verdict:** ✅ feeds feature selection.
- **Artifacts:** `strat_corr_indicators.py`; GCS corr JSON.

## E-05 · STRAT Stage 3b — combination mining
- **Engine/area:** strat (correlation/interaction) · **Status:** validated · **Date:** ~2026-05-27.
- **Question:** which interpretable AND-combos of conditions beat base rate, out-of-sample?
- **Method:** `lib/combo_mining.py` — binarize → `select_top_features` (top-k MI, train-only) → `mine_combos` (1/2/3-way AND, scored OOS by hit-rate and **lift = hit_rate ÷ base_rate**, ≥500 test-row support).
- **Results:** ranked combos per class; validated combos promoted to the indicator engine (commit `d4943f2`). Exact lifts: in GCS `*combos.json`.
- **Approach/why:** interpretable, OOS-scored interaction discovery (redundancy/overfit guarded by held-out lift + min-support).
- **Verdict:** ✅ production feature-discovery layer.
- **Artifacts:** `strat_corr_combos.py`, `lib/combo_mining.py`; `regime_combo_results` table; `regime-combo` weekly job.

## E-06 · STRAT Stage 5 — FTFC multi-TF assembly
- **Engine/area:** strat (integration) · **Status:** built, weights placeholder · **Date:** ~2026-05-26.
- **Question:** combine per-TF TYPE probabilities into a Full-Timeframe-Continuity score.
- **Method:** per 1-min clock bar, as-of stack calibrated probs from `strat_pred_{1m..4h}`, weight by FTFC_WEIGHTS (1m 0.00, 5m 0.15, 15m 0.30, 30m 0.30, 60m 0.15, 4h 0.10).
- **Results:** continuity score + consensus call. Weights are a **locked placeholder**, not yet a walk-forward output.
- **Verdict:** ✅ integration layer; ⚠️ weights unvalidated.
- **Artifacts:** `strat_ftfc_assemble.py`, `strat_config.py:117`.

## E-07 · STRAT-DIR baseline (body-direction)
- **Engine/area:** direction · **Status:** failed · **Date:** ~2026-05-26; commit `5abef53` (#565).
- **Question:** can the spine predict next-bar body direction?
- **Target:** `next_close > next_open` (binary; flat-close rows dropped).
- **Data:** SPY/IWM/QQQ; 5m/15m/30m; 2019→2026.
- **Structure:** binary LightGBM (`make_direction_lgbm`), same folds/calibration.
- **Gates/null:** log-loss beat > 0 in ≥6/8 folds + ECE + monotonic decisive hit-rate. Null = train-prior.
- **Results:** **FAIL 24/24 cells** (8 folds × 3 TF × 3 ticker). Log-loss beat universally **negative** (−0.003 to −0.14); decisive hit-rate ±2pp of 0.50.
- **Verdict:** ❌ direction unlearnable from spine.
- **Approach/why:** the obvious "which way" question; its failure is the pivot to size (E-09) and meta-labeling (E-18).
- **Artifacts:** `strat_dir_walk_forward.py`; `gs://.../dir_walk_forward_*.json`.

## E-08 · Direction feature-family R&D (E-07 extension)
- **Engine/area:** direction · **Status:** failed / 1 infeasible · **Date:** 2026-05-27; branch `feature/direction-features-experimental`.
- **Question:** do orthogonal feature families rescue direction?
- **Target:** same body direction. **Data:** IWM 5m/15m/30m.
- **Structure:** `strat_dir_walk_forward_extended.py --family=<name>`; identical harness + an extra joiner before featurize.
- **Variants/results:**
  - `news_sentiment` (9 cols) — FAIL 0/8 every cell (sparse pre-2025).
  - `cross_asset` (9: VIX Δ/z, term, VVIX, IWM−SPY) — FAIL 0/8 (redundant w/ baseline VIX/gamma).
  - `vol_regime` (7: ATR%, realized-vol z, gap, range/ATR) — FAIL 0/8 (dominated by baseline).
  - `options_derived` (PCR, IV skew/term, ATM IV) — **INFEASIBLE** (pg8000 ~10× psycopg2; 14.1M IWM option rows; 2025+ explosion > task budget).
  - baseline passthrough — reproduces 0/8 (harness sanity check).
- **Correlation:** the new cols re-encode volatility-regime info the spine already has — the prior reason they add variance not signal.
- **Verdict:** ❌ FAIL (3 measured) + INFEASIBLE (1). Direction needs *new data* (order flow), not more features.
- **Leaks:** strict `published_ts < bar_ts`; daily inputs shifted D-1; audited clean.
- **Gaps:** options_derived needs a materialized `option_daily_features` table to test.
- **Artifacts:** `strat_dir_walk_forward_extended.py`; `DIRECTION_FEATURES_R&D.md`; `gs://.../dir_extended_walk_forward_{family}_*.json`.

## E-09 · MAG-SIZE (magnitude) — phases 0–4 + calendar
- **Engine/area:** magnitude · **Status:** failed (closed 2026-05-29) · **Date:** 2026-05-27→29.
- **Question:** is next-bar *size* learnable + tradeable as a non-directional bet?
- **Target:** `magnitude_bucket` = bucket of `|next_close−next_open|/atr_20` at thresholds (0.5,1.0,1.5) → TIGHT/NORMAL/EXPANDED/EXPLOSIVE (the `body` label).
- **Data:** SPY/IWM/QQQ; 5m/15m/30m; 2019→2026.
- **Features (phase ablations, each on top of 143-col baseline):**
  - P0 baseline; P1 vol-family (atr_expansion, bb20_bw, realized_vol_z, range_expansion, intraday_range_vs_prevday); P2 AV daily (ADX/MFI/Chaikin/Aroon/ROC/BB-bw); P3 event-proximity (hours_to/from_hi_event, is_event_day_pm4h); P3b/calendar (hour/min/dow/week/first-Friday/FOMC/month-end/quarter-end); P4 cross-asset (pending); P5 gamma (deferred).
- **Structure:** LightGBM 4-class; 8-fold; **7-gate** ladder. Phase rule: ≥2/3 tickers per TF, ≥2/3 TF rows.
- **Variants/results (cells passing 5m/15m/30m):** P0 2/1/0 FAIL · P1 3/1/0 FAIL · P2 3/1/0 FAIL · P3 3/2/0 **PASS** · calendar 3/1/0 (replicates P3 5m → calendar-proxy). Only **IWM 5m** robust+mechanistic (99.6% bootstrap, 3.14× event-conc); other P3 passes fragile/no-mechanism.
- **Correlation:** model-vs-calendar decomposition (E-11) shows ~3× lift from calendar concentration + ~2–3× within-cell bar selection.
- **Verdict:** ❌ learnable at 5m (calendar) but see gate-7 (E-12).
- **Leaks:** audited clean (E-19).
- **Artifacts:** `mag_walk_forward.py`, `mag_config.py`, `mag_dataset.py`; `MAGNITUDE_ENGINE_RESULTS.md`; `gs://.../magnitude_engine/<phase>/<ticker>_<tf>/walk_forward_*.json`.

## E-10 · MAG gate-5 — bootstrap fragility
- **Engine/area:** magnitude (robustness) · **Status:** validated (added retroactively) · **Date:** 2026-05-28.
- **Question:** are the gate counts robust to test-bar sampling noise?
- **Method:** resample test bars WITH replacement (no retrain), recompute 4 gates ×1000 iters; PASS-rate ≥0.80.
- **Results:** IWM 5m 99.6%, QQQ 5m 100%, SPY 5m 77.6%, IWM 15m 7.8%, SPY 15m 9.0% → most P3 15m passes fragile.
- **Verdict:** ✅ exposed fragility; demoted 4/5 P3 cells.
- **Artifacts:** `scripts/bootstrap_gate_fragility.py`; `MAGNITUDE_ENGINE_RESULTS.md:43`.

## E-11 · MAG gate-6 — mechanism (event-conc, calendar decomp, naïve baseline)
- **Engine/area:** magnitude (mechanism) · **Status:** validated · **Date:** 2026-05-28.
- **Question:** does the EXPLOSIVE signal come from its claimed mechanism, or from calendar?
- **Methods/results:** event-window concentration (`check_event_window_concentration.py`); model-vs-calendar decomposition (`model_vs_calendar_explosive_decomp.py`) — IWM 5m 3.09× cell-rate, 63% in top-10% cells; naïve DoW×30-min lookup (`naive_calendar_lookup_baseline.py`) passes gates 1–3, fails gate 4 by construction → calendar slot fully explains gates 1–3.
- **Verdict:** ✅ "Phase 3" signal is a **calendar proxy**, not event causality.
- **Artifacts:** the three scripts; `MAGNITUDE_ENGINE_RESULTS.md:284,336,374`.

## E-12 · MAG gate-7 — implied-vs-realized (body) ★ project-killer
- **Engine/area:** magnitude (tradeability) · **Status:** failed · **Date:** 2026-05-28/29.
- **Question:** on EXPLOSIVE bars, does the realized move beat the option-implied move?
- **Method:** realized `|next_open−next_close|` vs `spot × ATM_IV × √(5/98280)`; ratio ≥ **1.25** in ≥6 IV-covered folds.
- **Results:** **0/23 IV-covered folds pass**; mean ratio 0.83–0.92; best 1.23 (SPY 5m 2020). Within-cell boost is calendar + vol-clustering (priced).
- **Verdict:** ❌ closed the magnitude project (2026-05-29). The empirical VRP/cost gate.
- **Artifacts:** `scripts/implied_vs_realized_check.py`; `MAGNITUDE_ENGINE_RESULTS.md:444`.

## E-13 · MAG-SIZE `excursion` label
- **Engine/area:** magnitude · **Status:** superseded/artifact · **Date:** 2026-06; this session.
- **Question:** does intrabar *range* (not body) beat implied — a gamma-scalp thesis?
- **Target:** `(next_high−next_low)/atr_20` bucketed.
- **Results (verified this session):** "passed" gate-7 ~1.5–2× on SPY/IWM/QQQ (7/8,8/8,8/8 folds) — **but it's a measurement artifact**: high−low range is mechanically ~1.5–2× the close-to-close move for the same vol, vs a straddle's body-expected-move (apples-to-oranges). A held straddle captures the body, which failed (E-12).
- **Verdict:** ⚠️ not a real edge (artifact).
- **Artifacts:** `mag_config.py` LABEL_MODES, `mag_dataset.py`; movement sim (E-15); MODELS_END_TO_END.md §5.

## E-14 · MAG-SIZE `call`/`put` directional labels + directional gate-7
- **Engine/area:** magnitude (directional) · **Status:** failed · **Date:** 2026-06; this session.
- **Question:** does a one-sided move beat the matching call/put IV?
- **Target:** call=`(next_high−next_open)/atr_20`, put=`(next_open−next_low)/atr_20`, clipped ≥0, bucketed.
- **Structure:** LightGBM 4-class per label; gate-7 with realized one-sided move vs **matching-leg** IV (calls delta+0.5; puts delta−0.5, `option_type='puts'`).
- **Results (verified this session):** **FAIL / INSUFFICIENT_DATA** — nowhere passes. Where IV coverage ≥4 folds (SPY put 5/8, QQQ put 6/8) it FAILS (one-sided move ≤ matching IV). Call side too rare to reach coverage.
- **Verdict:** ❌ directional move priced in (VRP), confirmed apples-to-apples.
- **Artifacts:** `scripts/implied_vs_realized_check.py` (`--label-mode call/put`), `mag_walk_forward.py`; `MAGNITUDE_DIRECTIONAL_SESSION_HANDOFF.md`.

## E-15 · Magnitude movement simulator (4 position types)
- **Engine/area:** magnitude (movement, frictionless) · **Status:** built/diagnostic · **Date:** 2026-06.
- **Question:** gross movement P&L on EXPLOSIVE bars for straddle/strangle/call/put (COSTS DEFERRED).
- **Method:** read predictions CSV + dataset OHLC; entry at next_open; payoff per position in ATR units; `--direction none|label|strat`.
- **Results (verified):** straddle ~1.3 ATR mean, 100% positive; ARM-A call/put ~0.9–1.2 ATR (selective); ARM-B Strat-overlay ~0.8 ATR (broad). Movement-only upper bound, not net.
- **Verdict:** diagnostic — quantifies movement, not tradability.
- **Artifacts:** `scripts/magnitude_movement_sim.py`; `gs://.../movement_sim_<pos>_<dir>_*.json`.

## E-16 · INTRADAY-MOM (Gao-Han-Li-Zhou replication)
- **Engine/area:** direction (rethink Model 3) · **Status:** failed (true null) · **Date:** 2026-06-04/05.
- **Question:** does first-30m return predict last-30m return (stronger on volatile days)?
- **Target:** sign/level of last-30m return (15:30–16:00 ET) from first-30m (09:30–10:00) [+ 12th half-hour].
- **Data:** SPY/IWM/QQQ per-day from `strat_features_30m`; ~2,500 days 2016→2026.
- **Structure:** OLS replication (go/no-go) + walk-forward LogisticRegression with conditioning (VIX, gap, RVOL).
- **Variants/results (verified this session):** pooled OLS β **negative** (SPY −0.049 t=−2.39; IWM −0.019; QQQ −0.014; R²≈0.0003–0.002). **Corrected** test on high-VIX and big-open subsets — β still negative & insignificant. WF logistic ~coin-flip, exp ≈1 bp.
- **Verdict:** ❌ **true null** — the 1993–2013 anomaly decayed/reversed in 2016→2026.
- **Leaks/bugs caught:** first pass tested only the *unconditional* effect (the published claim is conditional) → corrected to subset OLS; still null.
- **Artifacts:** `intraday_momentum.py`; `gs://.../qqq_30m/intraday_mom_*.json`; `MODEL_RETHINK_PLANS.md`.

## E-17 · DIR-REGIME (gamma-regime-conditional direction)
- **Engine/area:** direction (rethink Model 2) · **Status:** failed (true null) · **Date:** 2026-06-04/05.
- **Question:** is direction learnable *conditional* on dealer-gamma regime (pos→revert, neg→momentum)?
- **Target:** first pass `next_close>next_open`; **corrected** to sign of N-bar **forward return** `fwd_ret_5bars_bps` (move continuation).
- **Data:** SPY/IWM/QQQ 15m; gamma coverage 22–63% (IWM low, sparse pre-2021).
- **Structure:** split train/test by `gamma_regime` / sign(close−flip_price); binary LightGBM per regime; verdict on **expectancy** vs a naive-regime-follow control (not log-loss).
- **Variants/results (verified):** first pass (body sign, log-loss verdict) FAIL. Corrected (fwd-return, expectancy verdict, P&L sign-bug fixed) **still FAIL** — positive expectancy in only 3–4/8 folds, rarely beats naive control; log-loss beat 0/8.
- **Verdict:** ❌ **true null** — regime split doesn't unlock tradeable direction at 15m.
- **Leaks/bugs caught:** (1) wrong target carried over (body sign); (2) verdict gated on wrong metric (log-loss); (3) expectancy multiplied side by |move| not signed move — all fixed; still null.
- **Artifacts:** `dir_regime_walk_forward.py`; `gs://.../dir_regime_wf_*.json`.

## E-18 · STRAT-BREAKOUT-META (meta-labeled breakout follow-through) ★ the one real edge
- **Engine/area:** strat/meta (rethink Model 1) · **Status:** validated gross / **net marginal** · **Date:** 2026-06-04/05; commits `da000b0`,`1e3fd0d`,`9256534`,`446ae91`.
- **Question:** given a deterministic Strat trigger break (direction fixed by rule), can we predict whether it *follows through*?
- **Target (meta-label):** triple-barrier — from entry (trigger price), did price hit +1.0·ATR profit-target before −0.5·ATR stop within 12 bars? Binary (1=PT first). Primary = t+1 breaks bar-t high/low; side from the break.
- **Data:** SPY/IWM/QQQ; 5m (142k breakouts), also 15m/30m; 2019→2026; barriers resolved on **1-minute** bars.
- **Features:** spine at decision bar + breakout `side` (both known at entry; no leak). 1-min bars used only for labels.
- **Structure:** binary LightGBM on event-sampled rows; 8-fold; take-threshold 0.55; verdict = take≥0.55 beats base precision+expectancy in ≥5/8 folds; **net-of-cost sweep** (spread bps + slippage·ATR → cost_R).
- **Variants/results (verified this session):**
  - **GROSS:** PASS **24/24** ticker-folds (8/8 ×3); take≥0.55 precision 0.40–0.57 vs 0.33 base; expectancy **+0.1 to +0.36 R**.
  - **Self-audit fix:** first pass FAILED due to same-tf "both-barriers-in-one-bar=stop" labeling deflating base to 0.28 + corrupting labels; 1-min labeling raised base to 0.33 and flipped to 24/24.
  - **NET-of-cost (1bp spread + slippage sweep):** SPY 5m FAIL, **SPY 15m NET_PASS 5/8**, SPY 30m FAIL; IWM all FAIL; QQQ all FAIL. Diagnosis: 5m 0.5-ATR stop ≈ $0.18 so 1bp spread eats ~0.19 R > gross edge; 15m SPY is the sweet spot.
- **Approach/why:** meta-labeling reframe — the only path that's VRP-immune (trades the underlying).
- **Verdict:** ✅ **real edge** — gross 24/24; net-positive on SPY/IWM/QQQ @5m + SPY @15m under realistic fill at true spreads (see E-24). PRIMARY (trigger break) is the deterministic `STRAT-RULES`; only the take/skip filter is learned.
- **Gaps:** stop-limit entry, PT/SL sweep, true ~0.6bp SPY spread untested; would change the verdict.
- **Artifacts:** `breakout_meta_walk_forward.py`; `gs://.../<ticker>_<tf>/breakout_meta_wf_pt1.0_sl0.5_h12_*.json`; `MODEL_RETHINK_PLANS.md` §RESULTS.

## E-19 · Leakage audits (magnitude + strat)
- **Engine/area:** both (integrity) · **Status:** validated clean · **Date:** ~2026-05-26/28.
- **Question:** is any forward information leaking into features?
- **Methods/results:** `mag_leakage_audit.py` — feature drop-set (234 numeric, 0 forbidden), `atr_20` t-known (0/50 adjacent-pair leaks), phase-1 perturbed-OHLCV (0 leaked). `strat_leakage_audit.py` — ORB fixed post-window, level lookups prior-day, order-blocks [t-4..t]+ffill clean.
- **Verdict:** ✅ CLEAN (ran before walk-forwards, so verdicts stand).
- **Artifacts:** `mag_leakage_audit.py`, `strat_leakage_audit.py`; `MAGNITUDE_ENGINE_RESULTS.md:596`.

## E-20 · Calibration experiment (sigmoid vs none vs isotonic)
- **Engine/area:** both (calibration) · **Status:** validated, decision locked · **Date:** 2026-05-27.
- **Question:** does post-hoc calibration improve ECE over raw LightGBM softmax?
- **Method:** 24 folds (IWM ×5m/15m/30m) with `--calibration sigmoid` vs `none`.
- **Results:** sigmoid **hurt** every cell (ECE 0.013–0.049 raw → 0.042–0.125 sigmoid) — double-calibration on an already-cross-entropy model.
- **Verdict:** ✅ DEFAULT_CALIBRATION="none"; sigmoid/isotonic kept as diagnostics. Scope IWM — per-ticker re-verify open.
- **Artifacts:** `strat_config.py:130`, `mag_config.py:231`.

## E-21 · Archived P7 pipeline (LightGBM + stacked regression + voter)
- **Engine/area:** precursor (return regression / next-candle / backtests) · **Status:** abandoned/quarantined · **Date:** Jan 2026; quarantined 2026-05-26.
- **Question:** can a stacked/voter ensemble on IWM 30m produce net-positive intraday returns?
- **Target:** fwd return / next candle (multiple sub-scripts). **Data:** IWM 30m (per `p7a`).
- **Structure:** `p7b` next-candle classifier, `p7c` LightGBM→Ridge/Lasso stack, `p7d` P&L backtest, `p7e` structural backtest, `p7f`/`p7g` voter overlay + rulebook sweep.
- **Results:** all cells **net-negative after costs** (per `_archive/README.md`: gross small positive → net ~−2–3 bps; exact figures **per README, not re-verified**).
- **Verdict:** ❌ abandoned — motivated the pivot to structure/size prediction. DO NOT REUSE.
- **Artifacts:** `gcp/research/_archive/p7*`, `_archive/README.md`.

## E-22 · 2026-05-23 pre-registered research program (P1–P7) + analysis phases
- **Engine/area:** strat methodology / FTFC edge · **Status:** mixed (superseded by engine work) · **Date:** 2026-05-23→25.
- **Question:** replicate the FTFC/gamma edge across the full subgroup space (time-of-day, VIX tercile, per-combo) with walk-forward stability.
- **Structure:** 7 pre-registered phases — P1 data inventory + baselines, P2 gamma×FTFC×horizon grid, P3 strat-methodology audit, P4–5 deep DS + walk-forward stability, P6 synthesis, P7 multi-TF EDA + playbook. Reproducible via `scripts/analysis/phase{1..7}_*.py`, `per_factor_walkforward.py`, `per_ticker_calibration.py`, `regime_combo_miner.py`, `earnings_reaction_walkforward.py`.
- **Results:** P1–P7 deliverables in `docs/research/2026-05-23..25/`; cost findings led toward the engine reframes. Exact per-phase numbers: **unknown here** (in the dated research docs).
- **Note:** a true **IC screen** and **feature-redundancy-clustering** as named in the seed do **not** exist as code — the closest are Stage-3 MI ranking (E-04) and combo mining (E-05). "Triple-barrier" exists as E-18. "True ORB redo" = engineering in `strat_enrich_levels.py`, not a study.
- **Verdict:** mixed/superseded; foundational for the engines.
- **Artifacts:** `docs/research/2026-05-23/RESEARCH_PLAN.md` + dated deliverables; `scripts/analysis/*`.

## E-24 · BREAKOUT-META execution-quality + OFI-proxy follow-up
- **Engine/area:** strat/meta + flow · **Status:** validated (improved net) · **Date:** 2026-06-05.
- **Question:** does realistic stop-limit entry rescue the net edge; do order-flow proxies help; can AlphaVantage supply order-flow / time-of-day IV?
- **Target/data:** same as E-18; SPY/IWM/QQQ; 5m+15m; 1-min barriers; realistic 0.6bp spread.
- **Variants/results (verified this session):**
  - **Limit/stop-limit entry** (entry slip = 0; only stop-out exits pay slip): **SPY 15m pt1.0/sl0.5 → NET_PASS 6/8, +0.108 R**; **SPY 5m → NET_PASS 6/8, +0.092 R** (142k trades). Robust across the full one-way-slippage sweep.
  - **PT/SL sweep:** 1.0/0.5 optimal; 1.5/0.5 FAIL (hit rate falls below the lift); 1.5/0.75 marginal.
  - **OFI proxies** (CLV, signed-vol z, wicks): **do NOT help** (5/8 vs 6/8, lower median) — OHLCV proxies aren't a substitute for real order flow.
- **Data availability (answer to "get it from AlphaVantage?"):** **NO** for both — AV intraday is OHLCV-only (no L2/quote/tick → no true OFI); `etf_options_snapshots` is EOD-only (1 snap/day 2019→2026) and AV HISTORICAL_OPTIONS is EOD-only → no time-of-day IV for HONEST-GATE7. True OFI needs Polygon/Databento/IEX.
- **Realistic fill + labeling fix (2026-06-05):** scan barriers from the cross bar (not window start) → base follow-through 0.33→0.41 (more accurate); `--entry-mode realistic` = actual 1-min gap past trigger. Net @ realistic entry, 0.6bp: **net-positive across ALL 3 tickers at 5m** (SPY +0.081 5/8, IWM +0.096 6/7, QQQ +0.068 5/7) and **SPY 15m** (+0.038 6/7); IWM/QQQ 15m marginal-negative.
- **IV-flow family** (ATM put-call skew, IV level/changes from EOD options, D-1 shifted, 99.8% coverage): **worse** (NET_FAIL where clean passes) — like OFI proxies, re-encodes spine vol-regime info.
- **Live real-time options (market open):** SPY ATM IV ~15%, ETF penny-wide → ~0.26bp round-trip, so 0.6bp cost is conservative.
- **Verdict:** ✅ upgraded — **net-positive across SPY/IWM/QQQ at 5m and SPY at 15m under a realistic fill model at true spreads** *(as of 2026-06-05; see reconfirmation below — this did NOT robustly survive extended data).* Extra feature families (OFI, IV-flow) don't help; edge is self-contained in structural breakout features. FLOW-OFI(true) data-blocked; HONEST-GATE7 data-blocked.
- **RECONFIRMATION (2026-06-09, data extended to 2026-06-06, `--entry-mode realistic --cost-bps 0.6`, NET judged at 0.02-ATR one-way slip):** the **META layer (gross follow-through prediction) reproduces robustly — PASS on all four cells** (SPY 5m 8/8, IWM 5m 8/8, QQQ 5m 8/8, SPY 15m 6/8). **But the NET tradeable edge did NOT survive the 2025–26 data on most cells:**
  | cell | META | NET @ 0.02 ATR realistic | vs 2026-06-05 |
  |---|---|---|---|
  | **IWM 5m** | PASS 8/8 | **NET_PASS 8/8, +0.110 R** | reproduces (stronger; was +0.096) |
  | SPY 5m | PASS 8/8 | NET_FAIL 4/8, +0.042 R | was +0.081 5/8 → now marginal |
  | QQQ 5m | PASS 8/8 | NET_FAIL 4/8, −0.027 R | was +0.068 5/7 → now negative |
  | SPY 15m | PASS 6/8 | NET_FAIL 4/7, +0.022 R | was +0.038 6/7 → now marginal |
  Executions `magnitude-engine-{49mzz,bh97m,jvfbn,sbjbh}`. The 5m cells OOM at the job's 8Gi default (142k breakouts × 1-min barriers) — re-run at `--memory 16Gi`, reverted after. **Read: the realistic stop-limit execution model is CONFIRMED as the correct framework and the META edge is robust, but the NET edge is marginal and ticker-specific — only IWM 5m is a clean net-positive on current data. NOT shippable as a multi-ticker strategy without further work.**
- **Gaps:** decision-latency model; ~10% same-tf-fallback labeling (sparse early 1-min); real L2/tick order-flow vendor; net edge fragile/ticker-specific over time (only IWM 5m clean on extended data); IWM/QQQ 15m weak.
- **Artifacts:** `breakout_meta_walk_forward.py` (`--entry-mode`, `--ofi-proxies`); `gs://.../<ticker>_<tf>/breakout_meta_wf_*.json`; `MODEL_RETHINK_PLANS.md` §execution-quality.

## E-23 · Cost / EV / friction analysis
- **Engine/area:** cross-cutting (tradeability) · **Status:** partial · **Date:** ongoing.
- **Question:** what frictions must an edge clear; do ours?
- **Method/results:** `COST_ANALYSIS.md` (spread+slippage+commission+theta assumptions; VRP framing). Empirical cost gates realized in E-12 (gate-7 0/23) and E-18 (net-of-cost sweep — SPY-15m only).
- **Verdict:** ⚠️ partial — BREAKOUT-META net done (marginal); broader EV model open.
- **Artifacts:** `COST_ANALYSIS.md`; E-12/E-18 artifacts.

## E-25 · STRAT-NEXTBAR — historical tape + next-bar directional forward-walk
- **Engine/area:** strat (direction / next-candle) · **Status:** ✅ validated OOS (daily + weekly); edge proven **gap-mechanical, not standalone-tradeable** (de-mech 2026-06-09) · **Dates:** 2026-06-07 → 06-09 · **PRs (all merged to main):** #592 (backend), #593 (daily held-out OOS), #594 (multi-TF OOS + this registry entry), #595 (CLV ablation), #596 (registry self-contained), + CLV de-mechanization & costed structural backtest (this PR).
- **Question:** given all bars so far, what is the next candle (continue / reverse / stay-inside / expand-outside), how often, and is it forecastable **out-of-sample**? And how much of any edge is genuine vs mechanical?
- **Target:** next Strat candle ∈ {2U, 2D, 1, 3} at daily / weekly / monthly / quarterly. The tradeable "directional call" = next ∈ {2U, 2D} (which trigger breaks).
- **Data:** `market_data_daily` (Cloud SQL) resampled to 1d/1w/1mo/1q via `lib.data_loader` (added `'1q'`=QE). Tickers SPY/QQQ/IWM/AAPL/NVDA; ~2016→2026 (~2,000 daily bars/ticker). Classification cross-checked 100% vs persisted `market_data_daily.strat_candle` (production).
- **Features (all causal, known at bar T close):** close-location-value `clv=((C-L)-(H-C))/(H-L)`; 1/2/3-bar returns (momentum); RSI-14; EMA-distance (10/20/50/200); MACD-hist; Bollinger %b; volume-z; gap; range%; up/down streaks; current-candle one-hots; **FTFC** = prior-COMPLETED weekly+monthly Strat direction (strictly-before `merge_asof`, no lookahead). Stacked "UP-votes" = (clv>0) + (ret3d>0) + (FTFC>0).
- **Structure:** (1) deterministic transition table P(next|current); (2) fixed vote-rule ≥2 UP-votes→UP (no fitted params); (3) held-out logistic fit strictly before each test year; (4) CLV ablation across FULL / NO_CLV / CLV_ONLY / STRUCT_ONLY feature sets. LightGBM 4-class also used for the daily next_bar_type model-vs-base check.

- **Scripts & roles (repo paths):**
  | Path | Role |
  |---|---|
  | `lib/strat.py` → `compute_strat_history()` | D/W/M/Q tape + upcoming setup + per-bar triggers; **1-3-1 (`131_setup`) detection** added to `detect_combos` |
  | `lib/data_loader.py` | `'1q'` (QE) quarterly resample rule |
  | `scripts/strat_history_report.py` | past-week daily tape + causal forward-walk + W/M/Q + upcoming setup (the "what's the Tuesday call" log) |
  | `scripts/strat_backtest.py` | PART1 classification-vs-production (100%), PART2 combo follow-through, PART3 next-bar transition distribution |
  | `scripts/strat_next_candle_analysis.py` | FTFC-conditioned transition + daily next-candle model-vs-base-rate + feature mutual-information; defines `build_daily()` |
  | `scripts/strat_forward_walk.py` | stacks FTFC+CLV+momentum; PART1 sharpening, PART2 hit-count, PART3 day-to-day call log + live next-session call |
  | `scripts/strat_forward_walk_oos.py` | **daily held-out** (train<Y / test=Y) fixed-rule + logistic |
  | `scripts/strat_oos_multi_tf.py` | **multi-TF held-out** (daily/weekly/monthly); defines `build_bars()`, `FEATS` |
  | `scripts/strat_oos_clv_ablation.py` | **CLV ablation** held-out (FULL / NO_CLV / CLV_ONLY / STRUCT_ONLY); imports `build_bars` read-only |
  | `scripts/strat_clv_demech.py` | **CLV de-mechanization** — 2 targets (gap-aided `next_up` vs gap-neutral `next_intrabar`) × 5 sets incl. `CLV_LAG1`; imports `build_bars`+`FEATS` read-only |
  | `scripts/strat_struct_backtest.py` | **costed underlying backtest** of the STRUCT (momentum+FTFC) residual — held-out per-year, 2bps/side, `oc`/`cc` holds, vs buy-hold; imports `build_bars`+`FEATS` read-only |
  | `tests/test_strat_history.py` · `tests/test_strat_clv_demech.py` · `tests/test_strat_struct_backtest.py` | hermetic tests (history+1-3-1; demech wiring/mechanical-signature; backtest cost/band monotonicity) — 8 + 7 + 6 pass |

- **Results — descriptive (full-sample, SPY representative):**
  - Single current-candle is a **weak** predictor: after 2U → next 2U ~47–57% (continuation) vs 2D ~23–33%; after 2D ≈ coin-flip; inside(1) rarely stays inside, ~14–26% expand to a 3; the candle *type* itself ranks LOW in mutual information.
  - **Stacking sharpens P(next=2U):** FTFC alone ≈ +1pp → **FTFC+CLV ≈ 74–81%** → +momentum ~flat. CLV is the workhorse (MI rank #1 every ticker, corr→2U ≈ +0.4).
  - Fixed-rule forward-walk: ~65–68% overall / ~72–76% on unanimous (3/3 or 0/3) days, over ~1,600 predictions/ticker.

- **Results — HELD-OUT OOS (train strictly before each test year):**
  | TF | logistic OOS | base | lift | log-loss beat |
  |---|---|---|---|---|
  | **Daily** | ~70–72% | ~54–60% | +12–16pp | positive nearly every year 2017→2026 |
  | **Weekly** | ~75–80% | ~57–67% | +13–18pp | large (+0.1 to +0.3) |
  | Monthly | ~70–73% | ~65–71% | small | **inconclusive (~100 bars total)** |

- **Results — CLV ABLATION (held-out, per feature set):**
  | set | daily OOS | weekly OOS | read |
  |---|---|---|---|
  | FULL (all) | ~70–72% | ~77–80% | reference |
  | **CLV_ONLY** | ~71–73% | ~78–83% | **≈ FULL — CLV carries the whole edge** |
  | NO_CLV (all−clv) | ~64–66% | ~72–74% | −5–7pp daily; still > base |
  | STRUCT_ONLY (mom+FTFC) | ~65–66% | ~70–75% | the genuine non-mechanical residual (+6–13pp over base) |

- **Results — CLV DE-MECHANIZATION (held-out, all 5 tickers, `strat_clv_demech.py`, run 2026-06-09 `magnitude-engine-t2n8q`):** two de-mechanizing levers — a **gap-neutral target** (`next_close>next_open`, measured inside the next bar so the open-gap gives no free advantage) and **prior-bar CLV** (`clv.shift(1)`, which cannot set the next open). Both are decisive and consistent across SPY/QQQ/IWM/AAPL/NVDA:
  | lever | result | read |
  |---|---|---|
  | `CLV_NOW` on gap-aided `next_up` | lift **+10 to +20pp** (reproduces headline) | the inflated edge |
  | **`CLV_LAG1`** (prior-bar CLV) on `next_up` | lift **≈ 0 everywhere** (−1.5 to +0.0pp, LLbeat ≈ 0) | close-location has NO predictive persistence once a full bar separates it from the open — the CLV edge is **entirely the contemporaneous open-gap mechanism** |
  | **all sets** (incl. FULL/CLV_NOW/STRUCT) on **gap-neutral** `next_intrabar` | lift **≈ base** (−7 to +0.5pp, LLbeat ≈ 0) | the whole next-bar edge **vanishes** when the open-gap advantage is removed — *nothing* predicts the next bar's own (open→close) direction |
  - **Conclusion:** the ~70/75–80% next-bar accuracy is a **gap-aided trigger-break** phenomenon, not directional foresight. CLV's contribution is mechanical (CLV_LAG1 = 0, gap-neutral = 0); even the STRUCT_ONLY residual predicts *which trigger breaks*, not the bar's own direction.

- **Results — STRUCTURAL-RESIDUAL COSTED UNDERLYING BACKTEST (held-out per-year, 2 bps/side, `strat_struct_backtest.py`, runs `magnitude-engine-6qmsf` `oc` / `6px6b` `cc`):** trades the underlying on P(next_up) for STRUCT/FULL/CLV_ONLY; `oc`=next_open→next_close (gap NOT capturable, honest), `cc`=cur_close→next_close (captures the overnight gap).
  | frequency / mode | STRUCT net (per-trade) | tradeable? |
  |---|---|---|
  | **Daily `oc`** (honest) | ≈ 0 bps (SPY −0.5, QQQ −1.2, IWM −3.2, AAPL +5.9, NVDA +1.0), Sharpe ≈ 0 | **NO** — dies after 2bps/side |
  | **Daily `cc`** (gap-captured) | +3–15 bps, beats `oc` by ~3–4 bps/trade everywhere | edge lives in the **overnight gap** (matches de-mech); Sharpe still <0.5 |
  | **Weekly `oc`/`cc`** | positive net but **buy-and-hold the same bars is comparable or HIGHER** (SPY 1w STRUCT +7.0 net vs bench +51.1 → underperforms B&H) | **NO alpha** — weekly "profit" is market beta; thin (6 yrs) |
  - **Conclusion:** the structural residual is **not independently tradeable on the underlying** at daily frequency (net ≈ 0 honest); the small edge that exists is the overnight gap (needs close-execution) and the weekly apparent profit is beta. Confirms with hard P&L that the model predicts *trigger breaks*, not close-to-close return.

- **Verdict:** ✅ a **real, held-out** edge on the directional next-bar at daily & weekly — **but de-mechanization (2026-06-09) proves it is a gap-aided trigger-break, not directional foresight.** `CLV_LAG1`≈0 and the gap-neutral target collapses every set to base; the costed underlying backtest nets ≈0 (daily, honest `oc`) and shows weekly "profit" is beta. The model answers *which trigger (2U/2D) the next bar pokes* — useful as a **structural/regime read and as the PRIMARY-side directional input to a barrier strategy (BREAKOUT-META)** — but is **NOT a standalone tradeable close-to-close signal.** Monthly/quarterly remain too thin.
- **Leaks/bugs caught:** (a) `aggregate_to_timeframe` requires `Volume` — `_ftfc` initially passed OHLC-only → all-zero FTFC, fixed; (b) `load_daily` can carry persisted indicator columns → duplicate-name 2-D selection in correlation, fixed by drop-then-concat dedup. FTFC uses strictly-before `merge_asof` (no in-progress-bar lookahead); all features known at bar-T close.
- **Reproduce (Cloud Run Job `magnitude-engine`, research image, vs Cloud SQL):**
  ```
  gcloud run jobs execute magnitude-engine --region us-east1 \
    --args="-m,scripts.strat_oos_multi_tf,--tickers=SPY,QQQ,IWM,AAPL,NVDA,--timeframes=1d,1w,1mo"
  gcloud run jobs execute magnitude-engine --region us-east1 --tasks 1 \
    --args="^|^-m|scripts.strat_oos_clv_ablation|--tickers=SPY,QQQ,IWM,AAPL,NVDA|--timeframes=1d,1w"
  gcloud run jobs execute magnitude-engine --region us-east1 --tasks 1 \
    --args="^|^-m|scripts.strat_clv_demech|--tickers=SPY,QQQ,IWM,AAPL,NVDA|--timeframes=1d,1w"
  gcloud run jobs execute magnitude-engine --region us-east1 --tasks 1 \
    --args="^|^-m|scripts.strat_struct_backtest|--tickers=SPY,QQQ,IWM,AAPL,NVDA|--timeframes=1d,1w|--hold=oc|--slippage-bps=2|--band=0.05"
  ```
  Output → Cloud Logging for the execution. Use `--tasks 1` (the job defaults to 27 parallel tasks) and the `^|^` arg delimiter (so comma-separated ticker lists survive). Build with `./gcp/deploy.sh build-research`; SHA-fingerprint-verify scripts in the image before each run (verified 2026-06-09: all four `strat_*` scripts matched local `sha256sum`).
- **Open items:** ✅ **CLOSED 2026-06-09** — de-mechanize CLV (done: `strat_clv_demech.py` → edge is gap-mechanical, CLV_LAG1≈0); costed underlying backtest of the structural residual (done: `strat_struct_backtest.py` → not tradeable daily, weekly is beta). Remaining: the directional read is best used as the PRIMARY side of a barrier strategy — see BREAKOUT-META (E-18/E-24), the only net-tradeable path in this family.

---

*End of registry. Additions: append a new `E-NN` entry using the template in
the original request; keep §A1/A2/A6 in sync.*

---

## E-24 · Data-quality remediation + gamma rename (2026-06-07 → 06-09)

- **DQ1** — strat_features column audit fixed 14 bugs at source (gamma_regime
  inversion → `sign(total_gex)`; dead `ema_200`; NaN-as-float8 in
  `flip_price`/`distance_to_king/gate`; `realized_vol_z` wiring + cross-day
  z-window formula; the systemic `bulk_copy_upsert` broken-COPY carrier). Full
  3-ticker × 6-TF backfill verified **0 float8-NaN**.
- **DQ-wide NaN audit** — `docs/audits/NAN_AUDIT_2026-06-09.md`: swept all 1,863
  float8 columns / 81 tables; 20 tables hold residual float8-NaN; new **DQ2**
  finding = `strat_features_levels_{tf}` 100%-NaN ORB/order-block columns.
- **Gamma rename + true flip** — `flip_price`→`gamma_balance_price` (it's a
  cumulative-net-gamma balance, not a regime flip) and a NEW true
  Black-Scholes-recurved `gamma_flip` (`lib.gamma.compute_gamma_flip_bs`),
  backfilled across `gamma_levels_eod` (96.9%) + `strat_features_{tf}` (95.5%),
  0 NaN. Added as model features + `dist_to_gamma_flip_pct`; `gamma_flip_cross`
  strategy repointed to the true level.
- **Data dictionary** — `docs/DATA_DICTIONARY.md`: all 81 tables / 2,745 columns.
