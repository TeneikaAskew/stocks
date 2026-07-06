# Experiment Registry — Unified Complete Record

**This registry is the UNION of the two organizational schemes the research
program produced. Nothing is dropped: every section from both editions is
preserved below in full. Where the two describe the same experiment with
different wording, BOTH wordings are kept — Book I (per-experiment, `E-01…E-24`)
and Book II (thematic, `G1–G7` globals + `A/B/C/D/P/L` entries).**

Merged 2026-06-10 from:
- **Book I** — the per-experiment ledger (`E-01…E-23` + the `E-24` data-quality/
  gamma bridge entry). Granular, one section per experiment surface.
- **Book II** — the thematic ledger ("2026-06-05 edition"). Global indexes
  (`G1` architectures, `G2` datasets, `G3` decision rules, `G4` literature,
  `G5` conventions, `G6` open items, `G7` sources) + thematic entries
  (`A` engines, `B` direction probes, `C` feature-family R&D, `D` exec backtests,
  `P` precursor IWM research, `L` live-system audits).

### Cross-map (same experiments, two schemes)

| Book I (per-experiment) | Book II (thematic) | Subject |
|---|---|---|
| E-01, E-02, E-03, E-04, E-05, E-06 | A1, P-series | STRAT TYPE / next-candle structure |
| E-07, E-08, E-17 | A3, B (E1–E5b), C | Direction probes & feature-family R&D |
| E-09…E-15, E-16 | A2 | Magnitude (size) engine + intraday-momentum |
| E-18 (the one real edge) | B / breakout-meta | Meta-labeled breakout follow-through |
| E-19, E-20 | L, G6 | Leakage audits + calibration |
| E-21, E-22 | P (P1–P7), D | Archived P7 pipeline + pre-registered program + exec backtests |
| E-23 | D, G3 | Cost / EV / friction |
| E-24 | DQ1 + NAN_AUDIT + DATA_DICTIONARY | Data-quality remediation + gamma rename |

> When a number in Book I and Book II disagree, the deeper per-fold doc wins
> (`docs/RESEARCH_COMPENDIUM.md` narrative; `docs/MODELS_END_TO_END.md` log;
> `docs/DIRECTION_RESEARCH_RESULTS.md` verdict).

---

# BOOK I — Per-experiment ledger (E-series)

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
  confidence; ceiling **0.05 for ALL timeframes** (the single
  `DEFAULT_ECE_CEILING = 0.05` constant in `strat_config.py`; pinned by
  `test_ece_gate_ceiling_unchanged_at_005`). A wider "0.075 (30m)" was floated
  in an earlier draft of this doc but was NEVER code — it must not be
  reintroduced as a silent per-tf loosening. `expected_calibration_error()`
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
- ~~**options_derived** direction family **INFEASIBLE** (pg8000 timeout)~~ —
  **RESOLVED 2026-06-12** (§A6b): built the materialized `options_daily_features`
  table (`gcp/fetchers/build_options_daily_features.py`); the family then ran
  **with IV** (skew + ATM-IV) and **FAILS direction on all 6 cells** like the
  other three families.
- **HONEST-GATE7** (time-of-day IV / like-for-like / real gamma-scalp P&L) and
  **FLOW-OFI** (order-flow) proposed, **not built**.
- **Calibration decision scoped to IWM**; per-ticker re-verify pending.
- **FTFC weights** are a locked placeholder, not a walk-forward output yet.
- Exact row counts for several tables: **unknown** (not recorded).

## A6b. 2026-06 post-data-fix revalidation campaign

After the NULL-population fixes landed (market_data_daily 5 indicator cols,
strat_features `atr_expansion`/`tf`, daily_rates), every verdict was re-checked
on the corrected data to separate "experiment was faulty" from "data was
faulty." **Data epoch:** Cloud SQL as of 2026-06-11/12.

**Phase 0 — null validation (all ✅):** market_data_daily 5 cols populated
(warm-up only); strat_features `tf` 0 nulls + `atr_expansion` warm-up-only;
daily_rates 0 nulls; the 4 direction feature-family sources all populated &
null-clean — `news_sentiment` 101,939 rows (dense 2025+), `^VIX/^VIX3M/^VVIX`
0 null closes, `etf_options_snapshots` IV/delta 0 nulls; mag phase-2
`market_data_indicators` daily 2000→2026 (runnable); mag phase-4
`market_data_cross_asset` **empty → phase-4 stays data-blocked**.

**Revalidation verdicts:**
| exp | prior | re-run (clean data) | result |
|---|---|---|---|
| **E-01 STRAT-TYPE** | ✅ pass | re-run beat **+0.18–0.24** all folds (origin/main already carried the `calibration='none'` guard that had made it crash; verified live) | ✅ **CONFIRMED PASS** |
| **E-07 STRAT-DIR** | ❌ 24/24 | exhaustive sweep on clean data: **4 families** (news, cross-asset, vol-regime, **options-flow incl. IV** — the never-run one, unblocked via the materialized table) × **6 feature sets** (spine / +flow / flow-only / drop-gamma / drop-categorical / top-K-MI) × **3 targets** (uncond / high-conviction / close-to-close). **Every cell beat ≤ 0**; up-share ~0.50 even on decisive bars | ❌ **CONFIRMED FAIL — exhaustively.** Direction is unlearnable, not a feature/target/data artifact |
| **E-09 MAG gates 1–4** | ✅ structure | phase0/1/2/3 `--all-cells` re-run; **phase1 now reads the fixed `atr_expansion`** — same strong EXPLOSIVE lifts (3–15×) | ✅ **CONFIRMED PASS** |
| **E-12 MAG gate-7** | ❌ 0/23 | re-run on clean data: IWM realized/implied 0.55–1.47, **1/8 pass** | ❌ **CONFIRMED FAIL (VRP wall).** New: `etf_options_snapshots` now carries a `REALTIME` intraday session (~83 snaps/day) → an honest intraday-IV gate-7 is becoming possible going forward (Gap-1); signed order flow (Gap-2) still vendor-blocked |

**New artifacts (this campaign):**
- `gcp/research/strat_engine/dir_feature_sweep.py` — the feature-set × target sweep (reuses the production harness; no throwaway).
- `gcp/fetchers/build_options_daily_features.py` + `options_daily_features` table + `lib/features/experimental/options_derived.py` materialized loader — **perf fix**: the daily options-flow join went from ~9–20 min (52 GB scan) to **0.8 s** (indexed lookup), and now always includes IV. Doubles as a frontend-surfaceable daily options-flow series.

**Open follow-ups:** `etf_options_snapshots` is 52 GB / bloated (needs a non-transactional `VACUUM` runner); wire `build_options_daily_features` into the daily fetcher schedule to keep the materialized table current.

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
- **Follow-up (#646, 2026-06-21) — `isotonic_oos` + `calib_frac` sweep on TYPE 30m:**
  `isotonic_oos` (per-class isotonic on a date-carved TRAIN slice, distinct
  from the CV-refit path E-20 rejected) lifts the raw-`none` 30m cells: QQQ-30m
  `none` 5/8 → `isotonic_oos@0.2` **7/8** (2025 fold ECE 0.0567, just over).
  A full `--calib-frac` sweep through the production walk-forward harness:
  - QQQ-30m: cf0.20 7/8 (2025=.057) · cf0.30 7/8 (2020=.054) · cf0.35 7/8
    (2020=.056) · cf0.40 **8/8** · cf0.45 **8/8**.
  - IWM-30m: cf0.20 **8/8** (worst .048) · cf0.40 **7/8** (2023=.057) ← REGRESS.
  - SPY-30m: cf0.20 **8/8** · cf0.40 **8/8**.
  **Honest verdict: STAYS-HIDDEN.** QQQ reaches 8/8 only at frac ≥ 0.40, but
  that REGRESSES IWM-30m to 7/8, and the QQQ failing fold hops (2025→2020→2020)
  as frac moves — the 8/8 is the frac hyperparameter being curve-fit to the
  gate, not a robust win. No single `calib_frac` clears all three 30m cells
  simultaneously. Production default stays `calib_frac=0.2` (IWM/SPY-30m 8/8
  preserved); **QQQ-30m remains gated/hidden until more data accrues.** The
  0.05 ECE gate was NOT loosened. Cost: ~$0.29 (10 walk-forward dispatches).
  - **Artifacts:** `gs://…/research/strat_engine/qqq_30m/walk_forward_isotonic_oos_cf{20,30,35,40,45}_*.json`,
    `…/iwm_30m/…_cf40_*.json`, `…/spy_30m/…_cf40_*.json`; `--calib-frac` flag +
    docstring finding in `strat_walk_forward.py`.

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


---

# BOOK II — Thematic ledger (Globals G1–G7 + entries A/B/C/D/P/L)

*Originally the standalone "Experiment Registry — Complete Record of Every Model
& Experiment", 2026-06-05 edition. Preserved here in full; every section retained.*

**Purpose:** the single, exhaustive source of truth for every experiment and model
run across the research program — passed, failed, abandoned, superseded,
precursor, and in-progress alike. A negative result is a registry entry.

**Last updated:** 2026-06-05. **Compiled from:** the source artifacts listed in §G7.

**Companion docs:** `docs/RESEARCH_COMPENDIUM.md` is the narrative synthesis; this
registry is the line-item ledger. When a number here and in a deep doc disagree,
the deep doc (full fold tables) wins.

**Reading the IDs:** `A*`=production engines, `B*`=direction probes (E1–E5b),
`C*`=feature-family R&D, `D*`=execution backtests, `P*`=precursor IWM intraday
research (2026-05-23→25), `L*`=live-system audit experiments (2026-05-08).

---

# PART I — GLOBAL SECTIONS

## G1. Master model-architecture & baseline index

| Architecture | Used as | Where | Predicted | Status |
|---|---|---|---|---|
| **LightGBM multiclass** (300 trees, lr0.05, depth6, leaves31, min_child100, seed42) | primary | A1 TYPE, A2 magnitude, P-series classifiers | next_bar_type / magnitude_bucket / next_candle | A1 ✅, A2 closed |
| **LightGBM binary** (same params, objective=binary) | primary | A3, B1–B5 direction probes | next_close>next_open / triple-barrier touch | ❌ null |
| **Ridge** (α=1.0) | baseline + signal | P4.5, P7.1–7.3 | y_1d_bps / fwd_return_bps | signal IC real, not tradeable |
| **Lasso** (α=0.001) | baseline | P4.5, P7.1–7.3 | same | converges w/ Ridge (robust) |
| **ElasticNet / Bayesian Ridge / PLS-5 / PLS-10** | robustness ensemble | P7.2 | fwd_return_bps | 8 linear models cluster Sharpe +2.4–2.6 @60m |
| **LightGBM regressor** | non-linear comp | P4.5, P7.1–7.3 | fwd_return_bps | wins @15–30m, lower IC, overfits |
| **CalibratedClassifierCV (sigmoid / isotonic)** | calibration wrapper (diagnostic) | strat/mag harness | — | **rejected** — hurt ECE 24/24 folds |
| **LightGBM stacked (OOF classifier→regressor)** | 2-layer | P7-T1.2 | fwd_return_bps | ❌ adds 0 (IC 0.0295→0.0197) |
| **`gamma_proximity` rule evaluator** (non-ML) | conditioner/replay | P2, P5 | gamma-alert direction | ❌ no intraday edge |
| **Production "voter" (rule ensemble, strength≥3)** | live signal gen | P7-T2/T3, L-series | CALL/PUT | ❌ net −7 to −12 bps |

No SVM or sequence model (LSTM/CNN/path-signature) has been *run*; C4 is staged
only (§B / G3). HAR-style vol baselines were not run; the magnitude engine used
LightGBM, not HAR (open gap, §G6).

## G2. Master dataset / feature-surface index

| Surface / table | Family tags | Rows / span | Used by |
|---|---|---|---|
| `strat_features_{1m,5m,15m,30m,60m,4h}` | price/TA, strat-sequence, vol, volume, VWAP | 1m≈1.0M, 5m≈200k, 15m≈67k, 30m≈34k, 60m≈18k, 4h≈6k per ticker; 2015→2026 | all strat/direction/magnitude |
| `strat_features_levels_{tf}` | ORB (36), historical levels (100), order blocks (7) | joined 1:1 to above | TYPE, direction |
| **~143-col featurized matrix** | union of above after one-hot + drops | — | A1/A3/B/A2 P0 |
| `market_data_indicators[_spy/_iwm/_qqq/_other]` | AV indicators (ADX/MFI/Chaikin/Aroon/ROC/BBANDS) | partitioned | A2 phase2 |
| `economic_events` | calendar/event | — | A2 phase3 |
| `market_data_cross_asset` | cross-asset (VIX/UST/DXY/oil/gold) | partial backfill | A2 phase4 (cancelled) |
| `market_data_daily` | daily OHLCV+VIX | top-100, 2016→2026, ~2.5k/ticker | P1/P4/P4.5, C2/C3/C4 |
| `market_data_intraday` | 1-min OHLCV (RTH+ext) | IWM 1.93M / SPY 2.36M / QQQ 2.20M; 2015→2026 | exec backtests, E5b OFI |
| `etf_options_snapshots` | gamma/options (EOD AV) | ~14M; 2016→2026 | C1 flow, A2 phase5(def), gate-7, C3 features |
| `etf_options_daily_greeks` (materialized) | options/flow (dex/vanna/charm) | ~7.5k; built once | B5/E5 flow probe |
| `intraday_flow_15m` (materialized) | order-flow (OFI/CVD) | ~6.5k/yr/ticker | B5b/E5b |
| `intraday_gex_15m` (materialized) | reconstructed dealer GEX/DEX (delta-gamma re-curve of T-1 EOD chain) | IWM 157k / SPY 167k / QQQ 163k; 2016→2026 | B5c/E5c |
| `etf_options_snapshots` `market_session='REALTIME'` | **real** intraday greeks (5-min) | ~1.2M rows/ticker/day; since 2026-05-23 | E5c validation; future real-intraday verdict |
| `gamma_events` | gamma-alert outcomes | 8,119 alerts; 2016→2026 | P2, P5 |
| `news_sentiment` | news/text | ~70k mkt-wide (sparse pre-2025) | C-news |
| `historical_signals` / `signal_alerts` | live voter fires | — | P7-T2/T3, L-series |
| `regime_combo_results`, `strat_combo_results`, `indicator_correlation`, `walk_forward_results`, `magnitude_walk_forward_results` | result tables | — | correlation pipelines |

## G3. Cross-cutting reframes & pre-committed decision rules

- **Information-class principle:** every failure is INTERNAL (a bug — re-raise) or
  EXTERNAL (vendor — typed UNAVAILABLE), never a silent fallback (CLAUDE.md §3.7).
  Direction research extends this: re-representing price (fracdiff, info-bars) is
  not new information; only a new *data class* (flow, OFI) is.
- **Meta-labeling needs a primary edge** (López de Prado / Hudson&Thames): drove
  the decision that E2/E4 meta-labels can't manufacture alpha on an edgeless
  primary — confirmed empirically.
- **Asymmetric / cost-free payoff lens:** a combined size+direction signal is
  judged cost-free (precision at fire) *and* after-friction (EV vs bps). The IWM
  E4 flicker is significant cost-free, negative after friction.
- **Magnitude ⟂ direction:** size is the predictable axis, sign is the coin flip;
  pre-committed that magnitude must clear an *implied-vs-realized* gate (variance
  risk premium) to be tradeable — it did not (0.83–0.92).
- **Structure ≠ profitability:** an accurate next-bar/next-candle classifier
  (58–60%) still loses net after costs because a 2U can be a one-tick poke.
- **Pre-committed gates are immutable once set** (magnitude 7-gate bar set before
  results; strat hard gates log-loss<base AND ECE≤0.05).

## G4. Literature anchors → experiments informed

| Anchor | Claim | Informed |
|---|---|---|
| arXiv 2512.15720; Christoffersen-Diebold (NBER w10009, MgmtSci 2006) | magnitude predictable, **sign not** at minute scale (SPY 5m abs-ret ↑2.89× t=12.41 yet 45% dir acc) | the TYPE/DIRECTION/MAGNITUDE split; A2 |
| Gao-Han-Li-Zhou (JFE 2018); Baltussen et al. (JFE 2021) | intraday momentum **conditional** (late-session, high-vol, macro) | B3 (E3) regime models |
| López de Prado; Hudson&Thames | triple-barrier + meta-labeling lifts **precision only if primary edge** | B2 (E2), B4 (E4); purged-WF in P4.5 |
| QuantConnect meta-label reproductions | cannot manufacture alpha on edgeless primary | interpretation of B2/B4 nulls |
| Dim-Eraker-Vilkov (SSRN 4692190); gamma-feedback (arXiv 2511.22766) | dealer gamma → **volatility, direction-symmetric** | GEX in *magnitude* surface; B5 uses directional DEX not GEX |
| Cont-Kukanov-Stoikov | order-flow imbalance carries short-horizon directional info | **B5b (E5b)** intraday OFI |
| "The Strat" (discretionary) | FTFC continuity; **no peer-reviewed backtest** | FTFC treated as feature/filter, never assumed valid (P3 tests it) |

## G5. Shared conventions (exact)

- **Folds:** `DEFAULT_CUTOFFS = 2019..2026-01-01` → **8 anchored expanding folds**
  (train all bars `< cutoff`, test to next cutoff; first trains 2016–2018).
  Source `strat_walk_forward.py`.
- **Embargo:** `embargo_days_for(tf,h) = ceil(h / bars_per_day) + 1`; applied to
  horizon labels (E1/E4); single-bar `next_bar_type` uses none.
  `strat_dir_probes.py:158`.
- **ECE:** 10 equal-width confidence bins; `Σ (n_bin/N)·|avg_conf − avg_acc|` on
  argmax-confidence. `strat_pred_train.py:89`.
- **Leakage guard:** rejects any feature col matching `fwd_*`, `next_*`, `_fwd*`,
  `fwd_ret`, `fwd_close` (raises `SystemExit`); intraday shifts grouped by
  `bar_date` (no overnight cross). `strat_dir_probes.py:332`.
- **Estimator:** LightGBM params in G1; `random_state=42`, `verbose=-1`.
- **Calibration:** `DEFAULT_CALIBRATION="none"` (LOCKED 2026-05-27). sigmoid/
  isotonic available as diagnostics; `DEFAULT_CV=3` only when calibrating.
- **Strat gates:** `DEFAULT_ECE_CEILING=0.05`, `DEFAULT_BASE_RATE_BEAT_PP=5.0`;
  HARD = {log-loss<base, ECE≤0.05}, advisory = accuracy beat ≥5pp.
- **Magnitude gates (per cell, ≥6/8 folds each):** G1 log-loss beat>0; G2 ECE≤0.05
  (5m/15m) /0.075 (30m); G3 hit-rate monotone over (0.40,0.50,0.60,0.70); G4
  EXPLOSIVE lift≥1.5×; G5 bootstrap pass≥0.80 (1000 iters); G6 mechanism ratio≥2.0;
  **G7 realized/implied ratio≥1.25** in ≥6 IV-covered folds. Phase passes if ≥2/3
  tickers on ≥2/3 TFs. `mag_config.py`.
- **Combo mining:** `binarize_conditions` (train-median split), `select_top_features
  (k=10, mutual_info|spearman)`, `mine_combos(max_order=3, min_support=500,
  top_k=12)`; lift=hit_rate/base_rate on TEST. `lib/combo_mining.py`.

## G6. Open items & reproducibility gaps

- **B5b / E5b (intraday OFI): RESOLVED 2026-06-05** — ❌ no robust edge (destroys
  the IWM long flicker, surfaces an unvalidated SPY-long one; see B5b). Builder
  backfill (full 2015→2026) completed; the slow per-row upsert was replaced with
  the COPY path and made resumable (commit 6323cfd). The **SPY-long z=2.97** and
  **IWM E4 long z=2.85** flickers are the two standing replicate-or-reject items.
- **B5c / E5c (reconstructed intraday GEX/DEX): RESOLVED 2026-06-06** — ❌ null
  (third dealer-positioning class to dilute the IWM flicker; see B5c). Notably the
  **live REALTIME options feed** (`market_session='REALTIME'`, since 2026-05-23) was
  used to validate the reconstruction: DEX sign-agreement 100% / corr 0.55–0.82, so
  the null is real, not a reconstruction artifact (GEX recon is noisy, corr_gex IWM
  −0.79). An exploratory **pooled** IC of real DEX first looked cross-ticker-positive
  (DEX→1h +0.11..+0.23) but a per-day check **killed it**: Simpson's paradox
  (within-day IC −0.58..−0.63, 8/9 days negative) + `dex_per_oi` is a mechanical
  spot-level proxy (corr 0.66–0.93 with spot). No independent signal. The
  `realtime_gex_15m` table + `realtime-gex-daily` scheduler (5 PM ET weekdays) are
  LIVE and retained for validation + properly controlled future tests (within-day,
  level-residualized — never pooled).
- **No HAR / GARCH baseline** was run for magnitude (used LightGBM only) — a
  classical vol baseline would strengthen the "priced" conclusion.
- **No SVM / sequence model** (C4 LSTM/CNN/path-signatures) run; staged only.
- **C2 cross-asset relative direction** needs a VIX-futures term-structure feed
  not yet fetched — PARTIAL.
- **C3 information-driven bars** ready, not run.
- **Flip-PUT discrepancy (P2.5):** live 76.7% vs replay 28.6% unreconciled (the
  original live SQL was never committed) — open.
- **Calibration of the one live edge (IWM E4):** ECE≈0.10 — trust ranking not
  probabilities; isotonic on the long-only head untried.
- **Live ECE self-mute** is a no-op (writer unimplemented); TYPE provenance is
  best-effort (no top-level metrics.json).
- **30m TYPE** is PARTIAL (4–5/8 ECE) — not shipped.
- Several live-system items are P0 fixes, not research gaps (§L: dead risk-caps,
  momentum orchestration, MR-only degeneracy).

## G7. Source artifacts consulted

Docs: `DIRECTION_RESEARCH_RESULTS.md`, `DIRECTION_FEATURES_R&D.md`,
`DIRECTION_LITERATURE_SCAN.md`, `MAGNITUDE_ENGINE_RESULTS.md`,
`EXEC_BACKTEST_RESULTS.md`, `OPTIONS_EXEC_BACKTEST_RESULTS.md`,
`STRAT_ENGINE_AND_COMBO_PIPELINE.md`, `STRAT_ENGINE_ARCHITECTURE.md`,
`STRAT_METHODOLOGY.md`, `MODEL_REGISTRY.md`, `MODEL_SUMMARY.md`,
`INVESTMENT_MODELS_SUMMARY.md`, `RESEARCH_COMPENDIUM.md`,
`gcp/research/strat_engine/STRAT_DIRECTIONALITY_ENGINE_PRD.md`,
`docs/research/2026-05-23/P1..P6 + FLIP_PUT_DISCREPANCY`,
`docs/research/2026-05-24/P7_*`, `docs/research/2026-05-25/P7_*`,
`docs/audit/2026-05-08/track-A..G + momentum_eligibility_report + per_ticker_writeup + validation-2026-05-09`.
Code: `strat_config.py`, `strat_walk_forward.py`, `strat_pred_train.py`,
`strat_dataset.py`, `strat_dir_probes.py`, `lib/combo_mining.py`,
`magnitude_engine/mag_config.py + mag_pred_train.py`,
`lib/features/experimental/{news_sentiment,cross_asset,options_derived,vol_regime}.py`,
`lib/features/{flow_direction,intraday_flow,fracdiff}.py`,
`gcp/build_options_daily_greeks.py`, `gcp/build_intraday_flow.py`,
`scripts/research/{p2_stratify_outcomes,p5_walkforward_stability,p45_deep_data_science}.py`.
GCS: `gs://adept-mountain-474619-d4-trading-data/research/{strat_engine,magnitude_engine,exec_backtest,options_exec_backtest,p7a..g,p7-analysis*}/`.
DB result tables: `walk_forward_results`, `magnitude_walk_forward_results`,
`strat_combo_results`, `regime_combo_results`, `indicator_correlation`.

---

# PART II — EXPERIMENT ENTRIES

> Each entry fills the template. Fields that are genuinely unrecorded say
> "unknown". Numbers are quoted from the source in the Artifacts line.

## A — Production / validated engines

### A1 — Strat TYPE engine
- **Engine/area:** strat (structure). **Status:** production/validated (5m,15m all tickers); 30m PARTIAL.
- **Dates/PR:** validated 2026-05-27 (IWM), cross-ticker 2026-06-04. **Branch/commit:** unknown (see PRD).
- **Question:** Is next-bar Strat type learnable + calibrated, cross-ticker?
- **Target:** `next_bar_type ∈ {1,2U,2D,3}`, session-aware `groupby(bar_date).shift(-1)`.
- **Data:** IWM/SPY/QQQ × 1m–4h; 2016→2026; bars per G2.
- **Features:** ~143-col surface (price/TA, strat-sequence, ORB, levels, order blocks, regime ctx). Chosen as the full Strat-methodology surface.
- **Structure:** LightGBM multiclass (G1); 8 anchored folds; no embargo (1-bar label); calibration none.
- **Gates:** log-loss<base AND ECE≤0.05 (hard); +5pp acc (advisory). Null = majority-class base rate.
- **Variants/results:** IWM15m **8/8 log-loss (median +0.179), +17.7pp acc, ECE 0.021**. Cross-ticker 5m/15m: all PASS 8/8 (median acc beat +15.4..+19.0pp); **30m PARTIAL** (8/8 log-loss, only 4–5/8 ECE).
- **Correlation analysis:** indicator-correlation shows `Close_vs_Range`→2U rank-IC +0.465 (2D −0.466); structure carries strong single-feature signal.
- **Approach/why:** start from the one quantity with real conditional structure (transition matrices) before attempting direction.
- **Worked/not:** structure prediction works & calibrates; does NOT imply tradeable (see D1).
- **Verdict:** ✅ validated, on the shelf (callable, not activated).
- **Leaks/bugs:** +47pp "impossibly good" leak (session-label col entered matrix) → fixed by computing label pre-featurize + fail-loud guard.
- **Open items:** class imbalance for 1/3; 30m calibration; live-ECE mute is no-op.
- **Artifacts:** `gs://…/research/strat_engine/<tk>_<tf>/walk_forward_adaptive_none_*.json`, `model.pkl`; PRD.

### A2 — Magnitude (SIZE) engine
- **Engine/area:** magnitude. **Status:** learnable @5m but **closed 2026-05-29** (not tradeable).
- **Question:** Is bar magnitude predictable, and is the predictability unpriced?
- **Target:** `magnitude_bucket = bisect((0.5,1.0,1.5), |next_close−next_open|/atr_20)` → TIGHT/NORMAL/EXPANDED/EXPLOSIVE.
- **Data:** IWM/SPY/QQQ × 5m/15m/30m; 8 folds 2019→2026.
- **Features (per-phase, isolated on P0):** P0=143-col; P1 vol-expansion (atr5/atr20, bb20_bw, realized_vol_z15, range_expansion, intraday_range_vs_prior); P2 AV (adx,mfi,chaikin,aroon±,roc,bbands_bw); P3 event (hrs_until/since_hi_event, is_event_day_pm4h); P_calendar (hour,minute,dow,wom,first_friday,fomc_week,month_end,quarter_end); P4 cross-asset (cancelled); P5 gamma (deferred).
- **Structure:** LightGBM multiclass; 7-gate immutable bar (G5).
- **Variants/results:** P0 FAIL (only 5m crosses 2/3 tickers). P1/P2 FAIL (5m 3/3 PASS but 15m/30m no gain). **P3 PASS (5m 3/3, 15m 2/3)**; P_calendar **replicates P3, 100% bootstrap all 5m**. Mechanism: lift is calendar×vol-clustering, not event. **Gate-7 (implied-vs-realized): 0/23 IV-covered folds ≥1.25; aggregate ratio IWM 0.92 / SPY 0.87 / QQQ 0.83** (best fold 1.23).
- **Correlation:** `Daily_Range`→BIG-regime rank-IC +0.286; magnitude features carry the regime signal.
- **Approach/why:** literature says size is the predictable axis; gate-7 added to test if the option market already prices it.
- **Worked/not:** statistically learnable @5m; **not tradeably extractable** (priced).
- **Verdict:** ⚠️→❌ closed; no investment. P4/P5 cancelled (same gate-7 wall).
- **Leaks/bugs:** none recorded.
- **Open items:** no HAR/GARCH baseline; gate-7 only at 5m.
- **Artifacts:** `gs://…/research/magnitude_engine/phase*/<tk>_<tf>/walk_forward_magnitude-engine-*.json`; `magnitude_walk_forward_results`; MAGNITUDE_ENGINE_RESULTS.md.

## B — Direction probes (E1–E5b)

### A3 / B0 — Direction baseline
- **Status:** failed. **Target:** binary `next_close>next_open`. **Data:** shared surface, 8 folds.
- **Structure:** LightGBM binary. **Result:** **0/72 folds** beat base log-loss. **Verdict:** ❌. **Artifacts:** `dir_walk_forward_*.json`.

### B1 (E1) — Horizon sweep
- **Status:** failed. **Question:** does longer horizon recover sign? **Target:** sign of session-aware fwd-return, h∈{1,3,5,10,15,20}, embargo≥h.
- **Structure:** LightGBM binary; 8 folds. **Results:** **0/47 folds positive**; ECE worsens monotonically 0.062→0.159. **Verdict:** ❌.
- **Artifacts:** `dir_probe_e1_horizon_h{N}_*.json`.

### B2 (E2) — Trigger-conditioned
- **Status:** failed. **Question:** direction only on Strat-trigger bars (meta-label gate)? **Target:** h=5 sign on continuation∨reversal bars.
- **Results:** **0/8**, median acc −2.7pp, ECE 0.11. **Verdict:** ❌ no primary edge to filter. **Artifacts:** `dir_probe_e2_trigger_h5_*.json`.

### B3 (E3) — Regime-restricted
- **Status:** failed. **Question:** does direction emerge inside a regime? **Target:** h=5 sign, train+test within {vix_low,vix_high,pos_gamma,neg_gamma,late_session}.
- **Results:** **0/29 folds** (vix_low 0/4, vix_high 0/8, pos_gamma 0/2, neg_gamma 0/7, late_session 0/8); ECE 0.12–0.27. **Verdict:** ❌ even Gao's late-session effect doesn't replicate tradeably.
- **Artifacts:** `dir_probe_e1_horizon_h5_{regime}_*.json`, `dir_regime_wf_*.json`.

### B4 (E4) — Triple-barrier first-touch (primary target)
- **Status:** failed on calibration; **one unresolved IWM-only flicker**.
- **Question:** is the literature's triple-barrier target learnable as primary (not meta)?
- **Target:** which of ±k·ATR20 touched first within H=12 bars; explicit neutral; separate long-vs-rest & short-vs-rest; symmetric 3-class; k∈{1.0,1.5}; magnitude-EXPLOSIVE-gated (OOF).
- **Structure:** LightGBM binary/multiclass; 8 folds; embargo≥H.
- **Variants/results:** symmetric 0/8 (prec ≤0.49); short 0/8 (≈base); **long mag-gated:** calibration 0/8 (ECE≈0.10) but **cost-free precision SIGNIFICANT on IWM**: k1.0≥0.60 **+5.3pp z=2.85**; k1.5≥0.65 **+13.4pp z=4.21**, 7/8 folds incl 2022 bear. **Cross-ticker FAILS:** SPY +0.1pp (z=0.05), QQQ −2.2pp (z=−1.35). Tradeability ≈ **−0.5 bps** net.
- **Approach/why:** target the literature's own meta-label as a primary; judge cost-free then after-friction.
- **Verdict:** ❌ no generalizable edge; one IWM long flicker — small-cap timeability vs 1/3 multiple-comparisons luck. Miscalibrated.
- **Open items:** replicate-or-reject on more small-caps / OOS IWM window.
- **Artifacts:** `dir_probe_e4_tb_h12_k{1.0,1.5}_{none,topq,explosive,big}_*.json`.

### B5 (E5) — Flow-Direction (daily EOD dealer greeks)
- **Status:** failed (null + dilutive). **Question:** does an orthogonal info class (dealer options positioning) add direction?
- **Target:** E4 long/short triple-barrier; +6 flow cols (dex, dex_per_oi, dex_chg_5d, vanna, charm, short_dte_dex), d-1 leak-safe, joined by date.
- **Features/why:** DEX = −Σδ·OI (dealer lean); vanna/charm = BSM 2nd-order, dealer-short negation; 100% coverage. Chosen because price features are null and flow is information not re-representation.
- **Structure:** identical E4 (k1.0, topq-0.2, h12, expanding); materialized `etf_options_daily_greeks` (scan-once builder, Rule 0).
- **Results (long fire≥.60, baseline→+flow):** IWM **+0.053/z2.85 → −0.008/z−0.49** (edge destroyed; fires 726→881 while precision falls); SPY +0.001→+0.001 (z≈0); QQQ −0.022/z−1.35 → +0.011/z0.76. Short side: all |z|<1.4.
- **Correlation:** n/a (ablation A/B). **Verdict:** ❌ falsified; slow daily positioning adds nothing, dilutes the lone edge.
- **Leaks/bugs:** first cut re-aggregated 14M-row snapshots per experiment → starved Cloud SQL (2026-06-05 incident) → fixed via materialized table + builder job.
- **Also tested:** fracdiff (C5) + rolling-window (C6) all-levers on IWM → null (long z +2.85→−0.58).
- **Artifacts:** `dir_probe_e4_tb_h12_k1.0_topq_flow_*.json`; `lib/features/flow_direction.py`; `gcp/build_options_daily_greeks.py`; commit `46f4058`.

### B5b (E5b) — Intraday order-flow imbalance (OFI)
- **Status:** failed (no robust edge; reshuffles the flicker). **Dates:** dispatched + resolved 2026-06-05 (6 direction-probe execs). **Question:** does *intraday* order-flow (vs slow daily flow) add direction?
- **Target:** E4 long/short triple-barrier (k=1.0·ATR20, h=12, mag-cond=topq-0.2, tf=15m); +3 OFI cols (`ofi_norm`=signed_vol/tot_vol, `ofi_3bar`, `cvd_intraday`), **contemporaneous (no shift)**, merged on 15m `ts`. nfeat 248→251 (IWM), 227→230 (SPY), 224→227 (QQQ).
- **Features/why:** tick-rule signed volume from 1-min bars within each 15m bar — microstructure (Cont-Kukanov-Stoikov), the one remaining lever with a real prior. §3.7: zero/missing vol→NaN.
- **Structure:** materialized `intraday_flow_15m` (scan-once builder, Rule 0; full 2015→2026 backfill = 169,150 IWM / 183,246 SPY / 177,524 QQQ buckets); 8 anchored folds; baselines reproduced the documented E4 topq numbers exactly.
- **Results — pooled precision at fire ≥0.60 (baseline → +intraflow):**
  | ticker | side | baseline prec/base/z (n) | +intraflow prec/base/z (n) | Δz |
  |---|---|---|---|---|
  | IWM | long | 0.547/0.494/**+2.85** (726) | 0.502/0.497/**+0.30** (1054) | **−2.56** |
  | IWM | short | 0.492/0.490/+0.14 (2687) | 0.506/0.497/+0.86 (2283) | +0.72 |
  | SPY | long | 0.484/0.483/+0.05 (907) | 0.538/0.480/**+2.97** (658) | **+2.93** |
  | SPY | short | 0.508/0.493/+1.34 (2074) | 0.516/0.501/+1.59 (2589) | +0.25 |
  | QQQ | long | 0.470/0.492/−1.35 (920) | 0.510/0.487/**+1.52** (1070) | +2.87 |
  | QQQ | short | 0.497/0.495/+0.19 (2330) | 0.503/0.492/+1.04 (2273) | +0.85 |
- **Approach/why:** E5 tested *slow daily* positioning; OFI tests *fast contemporaneous* flow at the same 15m alignment that worked for baseline RSI.
- **Worked/not:** OFI **destroys** the lone IWM long edge (z 2.85→0.30; fires 726→1054 while precision falls — identical overfit-dilution signature to E5 flow) and **surfaces a NEW unvalidated SPY-long flicker** (z 2.97, +5.8pp cost-free, n=658) plus a marginal QQQ-long (z 1.52). It does not augment or replicate cross-ticker — it **moves** which single ticker is significant (IWM→SPY).
- **Verdict:** ❌ falsified as a robust directional edge. Swapping the significant ticker rather than adding/replicating signal is the multiple-comparisons signature (one of 6 tests crossing z≈3 while the prior winner vanishes). Cost-free only; E4-family miscalibration (ECE≈0.10); net-untradeable like the rest of the E-series.
- **Open items:** the **SPY-long intraflow flicker (z 2.97)** is now the standing E4-style candidate alongside the IWM E4 long flicker — both need replicate-or-reject (more names / OOS window) before any belief; neither is deployable today.
- **Artifacts:** `dir_probe_e4_tb_h12_k1.0_topq{,_intraflow}_178067926x.json` per ticker; `lib/features/intraday_flow.py`; `gcp/build_intraday_flow.py`; `tests/test_intraday_flow.py`; commits e60a114 (feature), 6323cfd (resumable builder).

### B5c (E5c) — Reconstructed intraday dealer GEX/DEX (intragex)
- **Status:** failed (null; dilutes the IWM flicker). **Dates:** 2026-06-05/06. **Question:** does *reconstructed intraday dealer positioning* (the "reverse-engineer what GEX/DEX was at 11:30am" idea) add direction?
- **Target:** E4 long/short triple-barrier (k1.0, h12, topq-0.2, tf15m); +3 cols `dist_to_flip_pct`, `gex_per_oi`, `dex_per_oi` from `intraday_gex_15m`. nfeat 248→251 / 227→230 / 224→227.
- **Reconstruction:** walk the T-1 EOD chain forward to each 15m spot via the delta-gamma re-curve `δ(S)=δ_eod+γ_eod·(S−S_eod)` → per-day scalars + vectorized per-bar (`total_gex=NetΓ·S²·mult`, `total_dex=(A+B·(S−S_eod))·S`, flip once/day). S_eod from `market_data_daily.close` (EOD chain `underlying_price` is NULL — a bug caught & fixed mid-build, see below). Full 2016→2026 backfill (IWM 157k / SPY 167k / QQQ 163k buckets).
- **VALIDATION against REAL intraday greeks** (the live `REALTIME` AV chain, 2026-06-02→06, n=84 bars/ticker, at matched spot): **DEX sign-agreement = 100% on all 3 tickers**, corr_dex 0.55–0.82 → the re-curve is a *faithful proxy for DEX direction*. GEX is unreliable (corr_gex IWM **−0.79**, SPY 0.51, QQQ 0.67; SPY sign 66%) → `gex_per_oi`/`dist_to_flip_pct` are noisy proxies; `dex_per_oi` is the trustworthy one. This means the null below is a REAL DEX-direction null, not a reconstruction artifact.
- **Results — pooled precision at fire ≥0.60 (baseline → +intragex):**
  | ticker | side | baseline z (n) | +intragex z (n) | Δz |
  |---|---|---|---|---|
  | IWM | long | **+2.85** (726) | **+0.60** (874) | **−2.26** |
  | IWM | short | +0.14 | +0.20 | +0.06 |
  | SPY | long | +0.05 | −0.06 | −0.11 |
  | SPY | short | +1.34 | −0.34 | −1.68 |
  | QQQ | long | −1.35 | −0.71 | +0.64 |
  | QQQ | short | +0.19 | +1.69 | +1.50 |
- **Verdict:** ❌ null. Same outcome family as E5/E5b: dilutes the IWM long flicker (z 2.85→0.60, fires↑ precision↓), no arm reaches significance (|z|<1.7). With a *validated-faithful* DEX reconstruction, dealer delta positioning still carries no tradeable cross-ticker direction.
- **Leaks/bugs:** first backfill wrote `total_dex`/`gamma_flip` as NaN (s_eod from NULL EOD `underlying_price`); GEX survived (no s_eod dep). Fixed → s_eod from `market_data_daily.close`; --restart recompute. Caught by the validation step.
- **Exploratory real-intraday DEX read — RAISED then KILLED (2026-06-06→07):** a
  **pooled** IC of real DEX vs forward returns first looked like the program's first
  cross-ticker-positive (pooled IC(DEX→1h) SPY +0.137 / IWM +0.111 / QQQ +0.229).
  A per-day check (cheap once `realtime_gex_15m` was materialized) **overturned it**:
  within-day IC is **−0.58 to −0.63, negative on 8/9 days for all 3 tickers**; the
  positive pooled IC was **Simpson's paradox** (between-day level shifts). Root cause:
  `dex_per_oi` correlates **0.66–0.93 with spot level** (option delta is monotonic in
  moneyness), so it's a mechanical spot-level proxy, not dealer-positioning alpha —
  the within-day relationship is ordinary intraday price-level mean-reversion. **No
  independent directional signal.** Strengthens the direction-null: even exact real
  intraday greeks add nothing once you control for the day.
- **Infra retained (LIVE):** `build-realtime-gex` job + `realtime-gex-daily` scheduler
  (5 PM ET weekdays) + `realtime_gex_15m` (282 buckets/ticker, 252 finite DEX,
  2026-05-23→06-05). Kept as validation ground-truth and for **properly controlled**
  future real-intraday tests (within-day, spot-level-residualized — never pooled).
- **Lesson:** an IC must be evaluated within-day (the tradeable frame); pooled IC on
  intraday data is Simpson-paradox-prone. Any option-greek feature monotonic in
  moneyness must be residualized against spot before it can claim directional signal.
- **Artifacts:** `dir_probe_e4_tb_h12_k1.0_topq_intragex_178070441x.json`; `lib/features/intraday_gex.py`; `gcp/build_intraday_gex.py`; `intraday_gex_15m`; `tests/test_intraday_gex.py`; commits 2e36c50 (feature), c8265ff (s_eod fix).

### B6 (gamma reassessment) — VOL confirmed, DIRECTION null, + a regime-label BUG (2026-06-07)
- **Status:** done. **Trigger:** domain-expert pushback that gamma should be valuable — prompted a step-back reevaluation of how gamma was tested.
- **Question:** Did the program's "gamma adds nothing" headline mis-handle gamma? (Separate the 3 questions gamma actually answers.)
- **Finding 1 — Gamma → VOLATILITY: CONFIRMED, robust, 11 years.** Daily gamma regime (D-1 EOD, leak-safe, from `gamma_levels_eod`) × within-day 30m moves over 2016→2026, regime by **sign(total_gex)**: negative-gamma forward |30m move| vs positive — IWM **21.1 vs 15.8 bps (1.34×)**, QQQ **21.7 vs 13.1 (1.66×)**, SPY **18.5 vs 9.9 (1.87×)**; n=14k–25k bars/cell. Literature-consistent (Dim-Eraker-Vilkov). This is gamma's real value ("where vol is") — the program had it (A2 magnitude) but **under-reported it** by gating it as "priced."
- **Finding 2 — production BUG: the `regime` text label is inverted vs `total_gex` sign.** In `gamma_levels_eod`, `regime='negative_gamma'` has `total_gex>0` in **2,765 of 2,767** rows. `lib/gamma.py:747` sets `regime = 'positive_gamma' if spot>flip else 'negative_gamma'` (standard rule) — but the *flip-based* label does NOT track the vol regime (it gives the inverted/weaker vol split), whereas **sign(total_gex) does** (Finding 1). ⇒ the spot-vs-flip `regime` / downstream `dealer_regime` feature mislabels the vol regime. NEEDS FIX (affects the 143-col surface, gamma alerts P2, dealer_regime). My first 11-yr run was fooled by this label and got the backwards answer until I switched to the numeric sign.
- **Finding 3 — Gamma → DIRECTION (regime-conditional momentum): NULL, 11 years.** Hypothesis: neg-gamma→intraday momentum, pos-gamma→mean-reversion. Powered test (1,177 neg vs 438 pos days): within-day 30m return autocorr ≈ **0 in both** (−0.012 vs −0.020), mom-hit 0.489/0.496. The 9-day real-intraday blip (neg-gamma autocorr +0.10..+0.56) was small-sample noise (per-day check: QQQ's +0.56 was 2 days). Correctly-framed, spot-invariant, powered — and still null.
- **Verdict:** gamma's value is **volatility/regime/sizing (real, confirmed)**, not raw call-vs-put direction. The original blanket null mis-framed it (pooled classifier; conflated vol/direction; a label bug masked the vol effect). Vindicates the vol intuition; direction-null now far better supported (11yr, right frame).
- **BUG FIX SHIPPED (2026-06-07):** `lib/gamma.py` build_summary + grid now derive
  regime from **sign(total_gex)** (commit 7b9e873; 48 gamma + 75 consumer tests
  green). `:latest` image rebuilt; **`premarket-brief` redeployed** (live regime
  display fixed); **`gamma_levels_eod` rebuilt + VERIFIED** — `negative_gamma`↔neg
  4,940 / `positive_gamma`↔pos 3,136, **0 mismatches, 0 'unknown'** (was 2,765/2,767
  inverted). Root cause confirmed: `compute_gamma_flip` returns None on ~half the
  days (the neg-gamma ones → dumped to 'unknown') and otherwise returns a flip far
  from spot (avg 217 vs spot 337). **flip itself is still unreliable** as a level
  (separate fix tracked). **`strat_features.gamma_regime` DATA FIX DONE (2026-06-07):**
  surgically corrected via in-row `UPDATE gamma_regime = sign(total_gex)` across all
  6 tables (1m 2.87M rows chunked by ticker, 5m 602k, 15m 201k, 30m 100k, 60m 54k,
  4h 18k) — **0 mismatches verified**. Not a workaround: `gamma_regime` is a cached
  copy of the (now-fixed) source, and `total_gex` (unchanged by the fix) is already
  in-row, so `sign(total_gex)` is the exact corrected value with no re-derivation /
  no drift; the builder produces the same on future runs automatically.
- **Open / next:** (1) ✅ regime fix shipped + data corrected end-to-end;
  (2) productionize vol-regime for position sizing / strategy selection;
  (3) ⏳ full column audit of strat_features for OTHER bugs of this class (in progress).
- **Artifacts:** `lib/gamma.py:743-762,933-952`; commit 7b9e873; gamma_levels_eod (rebuilt p2-build-gamma-levels-z5hdc).

### B7 (volume-at-price / POC) — VOL signal real, magnet/direction null (2026-06-07)
- **Status:** done (first cut). **Question:** does volume profile (Point of Control = the prior-day price level with the most traded volume) act as a level / predict direction or vol? ("where volume sits")
- **Method:** prior-day POC via 1-min volume histogram (price binned to $0.5 / IWM $0.2), leak-safe (D-1 for day D), from `market_data_intraday`. Tests over 2016→2026 (magnet/direction) and 2022→2026 (vol, single-ticker scan to beat the 600s timeout).
- **Finding 1 — POC magnet: NULL.** Day close lands nearer the prior-day POC than the open did only **~30% of days** (IWM 0.294 / QQQ 0.316; n=2,600+); mean close-distance > open-distance. POC is not a magnet — *caveat:* the metric is partly confounded by intraday time-dispersion (close is later ⇒ naturally farther).
- **Finding 2 — position vs POC → direction: ≈0.** Open-above vs open-below prior POC → negligible forward-return difference (e.g. QQQ +0.0004 vs +0.0001). No directional edge.
- **Finding 3 — distance-from-POC → VOLATILITY: REAL.** SPY 2022→2026, day range by open-distance-from-prior-POC: near(<0.3%) **1.03%** / mid **1.35%** / far(>1.2%) **2.01%** (monotonic, ~2× near→far; n=478/508/92). Opening far from the high-volume node ⇒ ~2× bigger day. *Caveat:* partly vol-clustering / gap-mechanical (a far-open often follows a big move).
- **Verdict:** volume-at-price, **like gamma, is a VOLATILITY signal, not a direction one.** Coherent with B6: dealer-positioning AND volume-structure both forecast vol/regime/sizing robustly; neither gives clean direction. Direction null stands.
- **Open / next:** confirm Finding 3 cross-ticker (per-ticker scans to fit the timeout) and de-confound the gap/vol-clustering component; combine POC-distance with gamma regime as a sizing input.
- **Artifacts:** `db_query_cr` over `market_data_intraday` (POC histogram); execs db-query-fg7cv (magnet/dir), -8ggcg/b1gsew0vt (vol).

### DQ1 (data-quality audit) — strat_features column sweep (2026-06-07)
- **Trigger:** after the gamma_regime bug, audit ALL ~83 columns of `strat_features_{tf}` for the same class of silent failure. **52 OK / 17 SUSPECT / 14 BUG** (15m, 200,842 rows; bugs confirmed across 5m/15m/30m/60m/4h).
- **BUG family A — 10 columns 100% NULL (never backfilled):** `realized_vol_short, mins_since_open, price_vs_ema9_atr, price_vs_ema20_atr, price_vs_vwap_atr, ema_spread_atr, ema9_slope, bb_squeeze, rsi_divergence` (+ `realized_vol_z`). Schema cols added 2026-05-31 (`strat_data_builder.py:462-472`) but the strat-engine builder has **not been re-run since** (data ends 2026-05-22). `realized_vol_z` also has a name mismatch (mag_dataset writes `realized_vol_z15`). `mins_since_open` will stay NULL on 1m even after rebuild (1m path skips `df_tf["Time"]`, `strat_data_builder.py:~355`; `lib/indicators.py:899` gates on Time). **Fix:** code (name + 1m Time) then strat-engine `--rebuild`.
- **BUG family B — §3.7 NaN-as-float8 (not SQL NULL):** `flip_price` 56.7% IEEE-NaN (IWM 77.5% / QQQ 54.9% / SPY 37.4%), `distance_to_king_pct` 416, `distance_to_gate_pct` 5,209. Root cause `strat_data_builder.py:547-552` pandas `.map()` → float NaN → stored as float8 NaN, invisible to `IS NULL`. **Fix:** `.where(notna, None)` cast at write (§3.7).
- **BUG family C — dead feature `ema_200` (100% IEEE-NaN):** `lib/config.py:28 ema_periods=[9,20,50]` lacks 200; `_safe("EMA200")` returns empty (silent fallback); yet `ema_200` is in `strat_config.py:35 NUMERIC_FEATURES` → models "use" an all-NaN feature. **Fix:** add 200 to `ema_periods` OR drop `ema_200` from NUMERIC_FEATURES.
- **NEEDS INVESTIGATION — `distance_to_king_pct`/`distance_to_gate_pct` ranges:** 91.5% / 93.3% of rows have |distance|>50% (king/gate ±50%+ from spot) — likely `min_king_strike`/`min_gate_strike` far-OTM or NaN-derived; verify vs `gamma_levels_eod`. Compounds family B.
- **SUSPECT (not bugs):** `gex_tercile` HIGH includes negative GEX for IWM (39%) — rank-based by design but semantically misleading (same *class* as gamma_regime — label≠sign — but here it's the intended tercile semantics; flag for consumers); `stoch_rsi_k/d` exceed 100 by machine-epsilon (cosmetic clip); `intraday_return`/`high_low_spread_pct` stored as % not ratio (unit-name ambiguity); warmup NaN on `ema_50/sma_50/sma_200`; early-history `'nan'`-string in `gex_tercile/vex_tercile/dealer_regime` (pre-options era). All explained, none blocking.
- **Impact note:** family A means recent direction/TYPE runs trained the ~143-col surface with these 10 features all-NULL (dead, not harmful — LightGBM treats as missing — but the surface was weaker than assumed). The regime-/strat-combo pipelines compute features via mag_dataset/combo_mining directly (not from these strat_features columns), so their reported lifts are unaffected.
- **Artifacts:** data-pipeline-validator agent sweep; `strat_data_builder.py`, `lib/config.py`, `lib/indicators.py:899`, `strat_config.py`.
- **RESOLUTION (2026-06-08) — all fixed AT SOURCE + full backfill, 0 float8-NaN verified:**
  - **Family C (`ema_200` dead):** added 200 to the per-build `IndicatorConfig.ema_periods` so `add_all_indicators` actually computes EMA200 (`strat_data_builder.py:~374`). Kept in `NUMERIC_FEATURES` (now a live feature). Verified: 15m all 3 tickers **0 non-finite**, populated = rows − ~199-bar warmup.
  - **Family A (10 cols 100% NULL):** the schema cols were present but the builder hadn't re-run; `realized_vol_z` was wired to the shared `lib/indicators.realized_vol_zscore` (one source of truth — `mag_dataset` now calls the same helper, killing the `realized_vol_z15` name fork). The `mins_since_open` 1m concern was **disproven** — `df_cap["Time"]` IS set before the 1m branch (`:349-353`); 1m `mins_since_open` populates correctly. Full `--rebuild` populated all 10.
  - **`realized_vol_zscore` formula fix:** first rebuild left it all-NULL on every TF — the z-window `rolling(60)` was computed WITHIN each day, impossible on coarse TFs (~26 bars/day at 15m, fewer above). Corrected so the rv is per-day but the z-score window spans days with `min_periods` (`lib/indicators.py`, commits 5c91cc8→8ffe683). Verified coverage SPY 1m=96.1% / 5m=80.6% / 15m=41.6% / 30m=60m=4h=0% — fine TFs populated, coarse TFs **genuinely NULL** (correct per §3.7, not fabricated).
  - **Family B (§3.7 NaN-as-float8 in `flip_price`/`distance_to_king_pct`/`distance_to_gate_pct`):** root-caused deeper than the audit thought. The `.map()`→float-NaN write was real, BUT the systemic carrier was a **broken write path**: `gcp.database.bulk_copy_upsert` called `cur.copy_from(...)` which **pg8000 cursors don't implement** — every COPY silently raised and fell back to the slow multi-row INSERT, AND the NaN→NULL conversion never ran. Fixed the COPY to the pg8000 `cur.execute("COPY … FROM STDIN WITH (FORMAT csv …)", stream=sio)` API and added `_na_to_none_records` applied **per-chunk** inside `upsert_dataframe` (NaN/NaT→None, preserves 0.0 and the literal string "nan"; per-chunk avoids the 1M-row memory-doubling that OOM'd the first rebuild). Commits 4b9d113, e1c57ea. This fix benefits **every** DataFrame writer in the repo, not just strat_features.
  - **`distance_to_king/gate` "out-of-range" NEEDS-INVESTIGATION item:** **disproven** — the data-pipeline-validator's ">90% out of range" was a NaN-poisoned average; true out-of-range is ~0.2%. No bug. Final sweep: **0 float8-NaN** in both columns across all 6 TFs.
  - **`gamma_levels_eod.flip_price` (sibling table, same NaN class):** the strat-engine rebuild fixed `strat_features`, but the EOD gamma table needed its own `p2-build-gamma-levels` re-run on the fixed image. First p2 re-run (n79r7) ran on a stale image (pre-`_na_to_none`) and a falsely-"Completed" monitor misread led to a premature mid-run measurement showing ~40k residual NaN that looked like strike-orphans. The **full** fresh-image p2 rebuild (hx8ft, ~57 min, 2015→2026 × SPY/IWM/QQQ) overwrote every row via `ON CONFLICT DO UPDATE`: **gate 0 NaN / 35,364 NULL / 23,389 real; king 0 NaN / 18,697 NULL / 10,561 real; flip 0 NaN / 3,503 real.** NULLs are legitimate "no cumulative-GEX zero-crossing"; no DELETE needed (the apparent orphans were just unprocessed dates mid-run). The level count/date dropped vs the 5-23 build because the options chain grew (~600k rows/quarter), so King/Gate selection picks a tighter strike set.
  - **gamma_regime (the original bug):** confirmed still correct post-rebuild — 15m all 3 tickers **0 mismatches** vs `sign(total_gex)` (the source fix in `lib/gamma.py` build_summary + grid, commit 7b9e873, is now reflected in the data, not just an in-row UPDATE patch).
  - **Net:** every formerly-broken column is fixed in the **producing code** and the full 2015→2026 × 3-ticker × 6-TF history is backfilled and verified clean (0 float8-NaN, 0 regime mismatch, 0 non-finite EMA200). No prior experiment artifacts overwritten — only the derived `strat_features_{tf}` / `gamma_levels_eod` tables were rebuilt from `etf_options_snapshots` + bars.
  - **STILL OPEN (user decision):** the `flip_price`/`flip` column computes the **cumulative-net-gamma balance price**, not a true dealer-gamma regime flip (GEX is monotonic in spot → no true flip). Proposed rename to `gamma_balance_price`, freeing `gamma_flip` for a future Black-Scholes-recurved value. Coordinated change across `lib/gamma.py` + 2 tables + brief/alerts/API/frontend — **not executed**, awaiting sign-off.

## C — Feature-family R&D (all on `next_close>next_open`, IWM 5m/15m/30m, 0/8 each)

### C-news — News sentiment
- **Status:** failed×3 cells. **Features (8):** news_sent_24h_mean/pos_share/neg_share, news_count_24h(+z), topic flags earnings/macro/m&a/fed. **Data:** `news_sentiment` (~70k mkt-wide, only ~184 IWM rows pre-2025; 6,882 in 2025, 61,328 in 2026). **Result:** 0/8 per cell. **Verdict:** ❌ too sparse pre-2025. **Artifacts:** `dir_extended_walk_forward_news_sentiment_*.json`; `lib/features/experimental/news_sentiment.py`.

### C-xasset — Cross-asset
- **Status:** failed×3. **Features (9):** vix_chg_1d/5d, vix_level_z_60d, vix3m_minus_vix, vvix_z_60d, iwm_minus_spy_5d/20d, qqq_minus_spy_5d, iwm_corr_spy_20d (all d-1). **Result:** 0/8. **Verdict:** ❌ dominated by baseline vix/dealer cols. **Artifacts:** `dir_extended_walk_forward_cross_asset_*.json`; `cross_asset.py`.

### C-vol — Volatility regime
- **Status:** failed×3. **Features (7):** atr_pct_d1, atr_ratio_d1_vs_d20, rv_5d, rv_20d, rv_ratio_5d_20d, gap_open_pct_d, true_range_vs_atr_d1. **Result:** 0/8. **Verdict:** ❌ near-duplicate of baseline vix/atr. **Artifacts:** `dir_extended_walk_forward_vol_regime_*.json`; `vol_regime.py`.

### C-options — Options-derived (PCR/skew)
- **Status:** INFEASIBLE (old architecture), feature module built. **Features (6):** pcr_volume_d1, pcr_oi_d1, iv_skew_25d_d1, iv_term_slope_d1, atm_iv_d1, iv_atm_chg_5d. **Blocker:** 14.1M-row table, pg8000 timeouts (>140s for PCR alone). **Verdict:** documented-not-tested; prior says would FAIL. **Note:** motivated the B5 materialized-table architecture. **Artifacts:** `options_derived.py`.

## D — Execution backtests

### D1 — Shares execution backtest (TYPE setups)
- **Status:** failed (0/8 every cell). **Question:** does the validated TYPE signal make money traded?
- **Structure:** argmax 2U/2D, top_prob≥0.55; entry stop-order at trigger extreme; stop=opposite extreme; target=1.5R; time-stop 30/60min; per-1m precedence target>stop>time, ties→stop; friction $0.05 round-trip.
- **Data:** IWM 5m/15m/30m; **88,138 trades** (62k/18.5k/7.5k); 8 folds 2019→2026.
- **Results:** hit **40.5/43.1/43.3%** (break-even ≈40%); **gross −$0.008..−$0.015/sh; net −$0.052..−$0.061/sh**; 0/8 every fold.
- **Verdict:** ❌ **structure-vs-magnitude gap** — knows a 2U prints, not how far; friction kills zero gross. Variants not run.
- **Artifacts:** `gs://…/research/exec_backtest/exec-backtest-*/base_*.{json,csv}`; EXEC_BACKTEST_RESULTS.md.

### D2 — Options execution backtest (0DTE ATM)
- **Status:** failed (all cells, both windows). **Question:** can 0DTE options rescue the hit-rate problem?
- **Structure:** long ATM 0DTE call/put on same setups; BSM with T-1 EOD IV anchor; 3-fold (2024–26) + 5-fold (2022–26); cost $1.38/contract round-trip.
- **Data:** 22,115 trades (5-fold); hit ~37–38%.
- **Results:** net/contract 5-fold **+$0.08/+$0.01/+$1.90**; fails **c2 (≥$5)** and **c3 (asymmetry≥1.20; actual 1.001/1.008/1.141)** every cell×window; theta **46–68%** of friction; exits stop40.1%/time33.8%/target21.6%/eod4.5%. Only positive folds 2022&2026 30m (high-trend/IV).
- **Verdict:** ❌ options can't fix a hit-rate problem.
- **Artifacts:** `gs://…/research/options_exec_backtest/options-exec-backtest-*/`; OPTIONS_EXEC_BACKTEST_RESULTS.md.

## P — Precursor IWM intraday research (2026-05-23 → 05-25)

> Common harness: bootstrap 95% CI, BH-FDR q=0.10 (P2/P3); purged walk-forward
> 5-fold 20-day embargo (P4.5/P7); 5 bps/leg cost on Sharpe. Sources cited per entry.

### P1 — Return baselines & VIX terciles
- **Status:** worked (reference). **Question:** random-walk forward-return distribution + vol segmentation.
- **Targets:** pct_up & mean-bps at 5m–240m (intraday) and 1d/5d/20d (daily); VIX terciles.
- **Data:** SPY/IWM/QQQ 1-min 1M+/ticker + top-100 daily; 2015→2026.
- **Results:** SPY intraday 50.52%→54.63% up (0.03→1.31 bps); SPY daily 55.2/61.5/68.8% (1d/5d/20d bull-drift); IWM lower (49.6–52.3% intraday); VIX p33=14.65/p67=19.40.
- **Verdict:** ✅ baselines for all later phases. **Artifacts:** `docs/research/2026-05-23/P1_data_inventory.md`, `data/baselines_*.csv`.

### P2 — Gamma alerts × outcomes (10yr)
- **Status:** failed intraday / confounded daily. **Question:** do king/gate/flip gamma alerts predict direction?
- **Target:** fwd_return>0 at 7 horizons. **Data:** 8,119 alerts, SPY/IWM/QQQ, 2016→2026.
- **Method:** production replay (D-1 EOD chain→`gamma.build_summary`→`gamma_proximity.evaluate_all`), bootstrap+BH-FDR.
- **Results:** intraday |lift|≤5pp (noise); 1d CALL +27.7..+32.6pp / PUT −19.3..−30.6pp (**FTFC+bull-drift confound**); flip_cross 94 events/10yr (14 PUT) hit_1d 28.6% (vs live 76.7%); gate_break CALL×LOW-VIX −319.5 bps.
- **Verdict:** ❌ H1 rejected; H2 confounded; H5 (flip) doesn't replicate. **Leak:** gate_break CALL prefiltered (ftfc=UP always). **Artifacts:** `P2_gamma_outcomes.md`, `gamma_events.parquet`, `scripts/research/p2_stratify_outcomes.py`.

### P2.5 — Flip-PUT discrepancy
- **Status:** inconclusive/open. **Question:** why live 76.7% ≠ replay 28.6%? **Data:** 30d live (N=18 claimed) vs 10yr replay (N=14) vs SQL (1 matching event in window). **Verdict:** unreconcilable under production logic; original live SQL not committed. **Artifacts:** `FLIP_PUT_DISCREPANCY.md`.

### P3 — Strat-combo edges (99 tickers, 10yr daily)
- **Status:** partial (2 edges, 1 anti). **Target:** direction at 1d/5d/20d. **Data:** 204,275 events, 99 tickers, 2016→2026.
- **Method:** Z-test per (combo,vix_tercile) vs baseline, BH-FDR.
- **Results (5d):** `212_bear_continuation` **+2.59pp p=0.003** (HIGH-VIX +5.15pp); `clean_2d_bear` +1.86pp p=0.044 (HIGH-VIX +5.05pp); `322_bull_continuation` **−2.79pp p=0.002 (anti)**; `22_bull_continuation` (N=41,304) −0.36pp ns.
- **Verdict:** ⚠️ 2 real edges, 1 anti-predictive (avoid). **Bugs:** NBIS 0% hit_1d (split); ftfc_direction unpopulated 99.99%. **Artifacts:** `P3_strat_methodology_audit.md`, `p3_combo_pooled.csv`.

### P4 — Feature importance / predictive power
- **Status:** failed. **Sub-exps:** (4.1) 100-ticker daily direction `y_1d_up`, 49,366 rows×51 feat, LightGBM+SHAP → **pooled AUC 0.4995**, only 3% tickers>0.60, top feature vix_close 93.65% gain. (4.2) gamma add-on ETF: ΔAUC SPY +0.020/IWM −0.007/QQQ −0.003.
- **Verdict:** ❌ feature importance ≠ predictive power; AUC≈0.5. **Artifacts:** `P4_feature_importance.md`, `p4a/p4b_*.csv`.

### P4.5 — Deep-data-science multi-model (the key linear-signal finding)
- **Status:** partial (signal real, not tradeable). **Question:** any linear/non-linear daily-direction signal with proper CV?
- **Target:** `y_1d_bps` (reg) + `y_1d_up`. **Data:** 222,397 rows, top-100, 2016→2026, **310 engineered features** (27 base + lags[1,3,5,10] + rolling[5,20,60] + cross-sectional ranks).
- **Structure:** **purged walk-forward 5-fold, 20-day embargo**; **Ridge(α1.0), Lasso(α0.001), LightGBM(300,0.05)**; metrics IC/rank-IC/AUC/long-short Sharpe (10L/10S, 5bps).
- **Results:** **Ridge IC +0.0339±0.031, Lasso +0.0344** (converge → robust), **LightGBM IC +0.0117** (3× lower, overfits); AUC ~0.51; **L/S Sharpe net −0.10..−0.31; net bps/day −1.56..−2.22**. Fold-5 (AI rally) Ridge Sharpe +2.06 (only positive). Top features: VIX derivatives (12/12), price_vs_ema9.
- **Verdict:** ⚠️ linear IC 0.034 is *real* but regime-dependent and **not retail-tradeable** at 5+ bps. **Artifacts:** `P4_5_deep_data_science.md`, `scripts/research/p45_deep_data_science.py`, `p45/walkforward_*.csv`.

### P5 — Walk-forward stability (17 rolling 2yr windows)
- **Status:** success (confirmed robustness). **Method:** recompute P2/P3 metrics in 17 windows (6-mo step).
- **Results:** `212_bear_cont×HIGH-VIX,5d` +4.33pp (88.2% windows +); `clean_2d_bear×HIGH-VIX` +3.89pp (88.2%); `322_bull,5d` −2.50pp anti (82% windows); `gate_break PUT×LOW-VIX,1d` **−6.41pp (100% windows negative, worst −20.3pp)**; `king_approach CALL,15m` −2.10pp anti (NEW); `22_bull_cont` −0.49pp 0% sig (confirmed no edge).
- **Verdict:** ✅ 2 edges hold 88%; strong anti-signals confirmed (mute in production). **Artifacts:** `P5_walkforward_stability.md`, `scripts/research/p5_walkforward_stability.py`, `p5_*.csv`.

### P6 — Synthesis (meta, no new experiment)
- **Status:** synthesis. **Artifacts:** `P6_synthesis.md`.

### P7.1 — Multi-TF Ridge/Lasso/LGBM (intraday)
- **Status:** success @15m+. **Target:** fwd_return_bps per TF. **Data:** 1m–60m, SPY/IWM/QQQ, 5-fold purged CV.
- **Results:** 1m Lasso IC +0.019 Sharpe −0.30; 5m IC +0.022 Sharpe +0.17; **15m LGBM Sharpe +1.14; 30m +1.10; 60m Ridge Sharpe +2.58 (IC 0.034)**. Top60m: vix_close, stoch_rsi_d, atr_14, distance_to_king_pct (gamma 4th), total_vex/gex.
- **Verdict:** ✅ positive IC+Sharpe @15m+ (gross, pre-deep-cost). **Artifacts:** `docs/research/2026-05-24/P7_*`, `p7-analysis/`.

### P7.2 — 10-model family robustness
- **Status:** success (signal linear). **Models:** Ridge, Lasso, ElasticNet, BayesRidge, PLS-5, PLS-10, LGBM(+shallow). **Result (60m):** PLS-10 +2.63, BayesRidge +2.59, Ridge +2.58, Lasso +2.52, LGBM +1.42 Sharpe — 8 linear cluster tight. **Verdict:** ✅ genuinely linear @60m. **Artifacts:** `gcp/research/p7_analyze_tf.py`.

### P7.3 — Per-ticker single-model training
- **Status:** success (IWM standout). **Result:** **IWM Sharpe +3.24 (30m LGBM), +3.15 (15m), WR 58–59%**; QQQ +2.48 (15m); SPY +1.67 (15m) but best 60m linear IC 0.058; SPY/QQQ linear negative @15m, LGBM positive. **Verdict:** ✅ per-ticker > pooled @15–30m; IWM special. **Note:** these Sharpes are pre-deep-cost; P7-T1/T3 show net-negative after 10bps. **Artifacts:** `data/p7_per_ticker/{TK}_{TF}_model_summary.csv`.

### P7.4 — Dealer-regime × combo (9-cell GEX×VEX)
- **Status:** success (regime structure). **Target:** hit_pct @60m. **Results (top):** SPY `322_bull×GEX_MID_VEX_LOW` 80% (N=30); IWM `11_inside×GEX_HIGH_VEX_MID` 73.3% (+47.2 bps); QQQ `322_bull×GEX_HIGH_VEX_LOW` 71.7%; anti: QQQ `clean_2d_bear×GEX_LOW_VEX_MID` 33.3%. **Verdict:** ✅ regime-dependent edge structure (small N). **Artifacts:** `p7-analysis-per-ticker/*/03b_combo_gex.csv`.

### P7-T1.1 — Next-candle classifier
- **Status:** classifier works, P&L fails. **Target:** next_candle_type (categorical). **Data:** SPY/IWM/QQQ 5m, 195–200k train, Jan–May 2026 OOS. **Result:** **58–60% OOS accuracy** (QQQ 59.7% post data-fix). **Verdict:** ⚠️ accurate but doesn't survive to P&L. **Bug:** same-day VIX leak (trivial). **Artifacts:** `gcp/research/p7b_next_candle_classifier.py`.

### P7-T1.2 — Stacked regression
- **Status:** failed. **Method:** 5-fold OOF classifier probs → layer-2 LGBM regressor. **Result:** baseline IC 0.0295 → stacked **0.0197** (down); L/S +0.68 bps (negligible). **Verdict:** ❌ classifier adds 0 (overlapping signal). **Artifacts:** `p7c_stacked_regression.py`.

### P7-T1.3 — Classifier P&L backtest
- **Status:** failed. **Target:** daily PnL after 10bps. **Data:** IWM/QQQ/SPY 5m/15m, Jan–May 2026, 4 exit models, 2 trades/day cap. **Result (IWM 5m exitA):** gross +3.0 bps, **net −7.0 bps**; LONG 46.2% −3.59, SHORT 43.1% −8.33; only Feb 2026 positive. IWM 15m long-only −1.7 bps (best). QQQ 5m −8.42. **Verdict:** ❌ accuracy ≠ profitability (2U = one-tick poke). **Artifacts:** `p7d_pnl_backtest.py`.

### P7-T1.4 — Structural backtest + high-N combo
- **Status:** closed. **Method:** fix entry-bar indexing; min_n_cell=500. **Result:** indexing +0.55 bps (net still −2.02); high-n combos only 2 OOS matches/5mo (uninformative). **Verdict:** ❌ classifier standalone not deployable. **Artifacts:** `p7e_structural_backtest.py`.

### P7-T2.1 — Voter overlay (7-week)
- **Status:** promising/flagged. **Question:** filter production voter by |classifier_edge|≥thr? **Data:** historical_signals Apr–May 2026. **Result:** voter −5.83 bps → +|edge|≥0.30 **+9.14 bps (+14.97 lift)**, n=93, CI[−9.34,+27.62]. **Verdict:** ⚠️ promising, small-sample. **Artifacts:** `p7f_voter_overlay.py`.

### P7-T2.2 — Voter backfill 5-month OOS
- **Status:** partial (signal real, baseline too negative). **Data:** backfilled Jan–May 2026, 6 cells. **Result:** overlay lift +1.80..**+8.73 bps** (QQQ 60m closest, −1.50 net, CI spans 0), win-rate lift +3..+9.1pp; voter baseline −7..−12 bps. **Verdict:** ⚠️ overlay is real signal but can't net-positive a too-negative voter. **Artifacts:** `gs://…/research/p7f/{tk}_{tf}_R*.json`.

### P7-T3.1 — Gross-vs-net cost check (the cost-reality finding)
- **Status:** failed (major bug exposed). **Question:** was the production historical backtest net of costs? **Result:** historical Sharpe 0.43 / +0.3 bps was **GROSS**; after 10bps → −9.7 bps; 5-mo OOS −9.37 (n=845, CI[−10.75,−8.00]) — matches. **Verdict:** ❌ the published +133% Sharpe lift was costless fantasy; true net ≈0/negative. **Bug:** gross-of-cost backtest. **Artifacts:** `p7g_voter_rulebook_sweep.py`, `P7_final_cost_finding.md`.

### P7-T3.2 — Time-of-day segmentation
- **Status:** failed. **Result:** best TOD bucket still −8..−9 bps; rulebook TOD ordering inverted. **Verdict:** ❌ multiplier can't save negative baseline.

### P7-T3.3 — Strength-floor sweep
- **Status:** failed. **Result:** strength≥3 −9.37, strength≥5 −9.19 (no EV stratification). **Verdict:** ❌ strength doesn't rank EV; flatten the sizing ladder.

## L — Live-system audit experiments (2026-05-08)

> These probe the *deployed* premarket-brief / AI-insights / signal-monitor stack,
> not research models. Many are P0 production bugs surfaced empirically.

| ID | Experiment | Result | Verdict | Source |
|---|---|---|---|---|
| **L1** | Brief bias accuracy (5/4–5/7) | 4/8 = 50%, frozen 4/27 input | ❌ stuck-thermostat artifact | track-B |
| **L2** | Brief trigger touch/hold | 1/12 sessions in-range; only testable case faded | ❌ plans not actionable | track-B |
| **L3** | Strat candle manual re-derivation | SPY/IWM 2U✓, QQQ 1✓ (match) | ✅ classifier correct, bug is data | track-B |
| **L4** | Earnings/econ embed quality (5/5) | calendar+events VERIFIED; gap-reaction degraded by freeze | ⚠️ mostly correct | W8-followup |
| **L5** | brief_bias NULL root-cause | writer merged 08:52 ET 5/7 (PR#279) | ✅ deploy-timing, not bug | W4-followup |
| **L6** | AI-insights factor discrimination | 8 MR factors hit 8.9–13.8% (noise); 7 momentum factors on 0 alerts | ❌ MR-only degenerate, no discrimination | track-C |
| **L7** | Insights cost / orb_only rate | $0.0029/report ($3.18/yr); 10/12 orb_only placeholder, 0/12 actionable | ⚠️ runs, not actionable | track-C |
| **L8** | Signal-monitor hit-rate matrix (5/7, n=360) | global 11.4%; **SPY CALL 0/78, SPY PUT 0/53** | ❌ +0.30% target too aggressive for SPY | track-D |
| **L9** | Score-quartile discrimination | Q1 12.2% vs Q4 11.1% | ❌ score non-discriminative | track-D |
| **L10** | Brief-alignment vs hit-rate | opposed CALL 20.5% vs aligned PUT 17.0%, n=1 day | ⚠️ do NOT ship "fade the brief" | track-D/G |
| **L11** | Risk-cap dead-code confirm | fires 111/137/138 vs cap 5 → 22–28× blow-through | ❌ caps are dead code (P0) | track-D |
| **L12** | Strategy-agreement / momentum fire | stacked 2.2% (vs claimed 21%); momentum dormant (image-lag) | ❌ stacked-boost inactive | track-D |
| **L13** | Per-ticker calibration counterfactual | replay net: SPY +0.0023→+0.0048%, IWM −0.0179→−0.0033%, QQQ −0.0005→+0.0127%; win-rate +9pp | ⚠️ all 3 need custom exit config | track-E |
| **L14** | Factor discrimination per ticker | `above_vwap` anti-signal: SPY −9.9 / IWM −11.7 / QQQ −16.1 pp; below_vwap CALL +20.3 (QQQ) | ⚠️ DROP above_vwap everywhere | per_ticker_writeup |
| **L15** | Multi-TF autocorrelation regime | all 3 ETFs momentum @30m & 240m (SPY 240m +0.167) | ❌ system fires MR at momentum horizons | per_ticker/track-E |
| **L16** | Momentum fire-eligibility replay | would-fire @MIN=5: 4.6–6.4%/ticker (thousands of bars) vs production 0 | ❌ orchestration excludes strategy, not tuning | momentum_eligibility_report |
| **L17** | Post-fix PR validation replay (16 PRs) | freeze plugged (19/19); conditions_met 100% JSONB; gate 92% aligned 5/8; **per-ticker resolver inert ~19h 5/9 (schema migration didn't auto-run)** | ⚠️ most verified; one 19h silent degradation | validation-2026-05-09 |

---

*End of registry. The B5b/E5b results row and the §0 of RESEARCH_COMPENDIUM will be
updated when the intraday-OFI pipeline completes.*

---

# 2026-07-06 SESSION — Forward-window & directional re-probe (E-25 … E-31 + P0.1)

**Scratch-harness re-examination of the magnitude/direction question, prompted
by "what features or changes would make this model effective?" Read the harness
caveat before trusting any number — these are preliminary signals, not
gate-cleared edges.**

## Harness (WEAKER than the production standard — this bounds every claim below)
- Testbed: IWM/SPY/QQQ 5m, phase0 features (~248 cols), 2022-01→2026-06 (~79–83k bars/ticker).
- Split: **single chronological 70/30** (train = first 70% by ts, test = last 30% OOS,
  never shuffled). Tempered class weights α=0.75 (the shipped default). LightGBM,
  calibration `none`.
- Metric: OOS EXPLOSIVE (top-bucket) precision + lift over base rate + precision at
  p_EXPLOSIVE thresholds. **No** cost/EV, **no** purged+embargoed CV, **no** gate-7
  implied-vs-realized, **no** multiple-comparisons control.
- ⚠️ The production standard is 8 anchored purged+embargoed walk-forward folds +
  cost-aware EV gate + gate-7 (`MAGNITUDE_ENGINE_RESULTS.md`) + cross-ticker
  replication (`DIRECTION_RESEARCH_RESULTS.md`). **Nothing below has cleared those.**
- Baseline reproduced: single-bar body magnitude (current production target) OOS
  EXPLOSIVE argmax precision ~10–12% / lift ~4.3–5.3×; p≥0.55 ~23% / ~9.8× (IWM).

| E | probe | result | verdict |
|---|---|---|---|
| E-25 | Feature-family ablation | signal DISTRIBUTED; `prev` most load-bearing (drop −24% EXPLOSIVE lift); macd/rsi/strat/dealer/gex prunable dead weight; no slim subset beats full 248 | feature engineering near ceiling |
| E-26 | Engineered vol-regime feats (realized vol, range-expansion, vol-of-vol) | NEUTRAL (+0.18× lift); vol-only-without-patterns HURT — existing feats already carry the vol signal | null |
| E-27 | Time-of-day / session features | modest+ (+0.6× argmax lift); `mins_since_open` is the #1 feature in the fwd-window model; EXPLOSIVE calls enrich ~5× at open/close | small, cheap |
| **E-28** | **Forward-window target (30-min RANGE, K=6 bars)** | **argmax precision 50–59% / 8–10× lift; p≥0.55 56–64%; generalizes IWM/SPY/QQQ.** Audited: NOT atr-denominator artifact (trivial atr-rank 3% prec / 0.5×), NOT overlap artifact (non-overlap holds 65%); driven by vol + time-of-day | ⚠️ statistically strong; see reconciliation |
| E-29 | Regression head (continuous move/ATR + threshold) | NEGATIVE — fixed-threshold 0% (mean-reversion suppresses tail); ranking only matches the classifier | null |
| **E-30** | **Directional excursion (single-bar call/put)** | CALL(up) 5.6–6.8× argmax lift > PUT(down) 3.5–3.7×; asymmetry generalizes | ⚠️ see reconciliation |
| **P0.1** | **Forward-window directional (30-min up/down excursion)** | CALL(up) 4.8–7.0× > PUT(down) 3.0–4.7×; p≥0.55 up ~32–40% prec / 6–7× lift (184–581 bars); generalizes | ⚠️ see reconciliation |
| E-31 | External data: event-calendar + options IV/skew joins | NEUTRAL (+0.4× lift combined argmax; p≥0.55 combined bump noisy, 52 bars). Limited: `economic_events.event_time` 95% NULL → no intraday event timing | marginal, data-limited |

## Reconciliation to the standing verdicts (the load-bearing part)
- **E-28 (forward-window range) is a MAGNITUDE/VOL signal.** Its audit shows it's
  driven by vol-clustering + time-of-day — precisely the effects **gate-7 found are
  already priced** (`MAGNITUDE_ENGINE_RESULTS.md`: EXPLOSIVE-bar realized/implied
  ratio 0.83–0.92; magnitude closed 2026-05-29 as "statistically learnable, not
  tradeably-extractable as a non-directional play"). A 30-min forward range is a
  cleaner vol *forecast*, but the straddle/strangle that would trade it prices the
  same forecast. **Open action:** run gate-7 (implied-vs-realized) on the
  forward-window target before any tradeability claim. Prior predicts it fails.
  **→ GATE-7 RAN (2026-07-06):** raw ratio looked like a strong PASS (30-min
  realized range 2.43× / directional displacement 1.57× the daily-ATM-IV-√t
  implied move, 910 bars, 5/5 quarters). **But it is a benchmark artifact.** A
  time-of-day control shows **96% of the fwd-window-EXPLOSIVE bars are the last
  30 min of the session**, and at **midday** (where flat daily-IV×√t scaling is
  valid) the displacement ratio is **0.74 — below 1.0 (over-priced)**. Flat
  daily-ATM-IV √-scaling under-states close-of-day vol that the actual 0DTE/
  intraday options price correctly. **Verdict HOLDS: priced, not tradeable.** The
  model's residual "signal" reduces to "it's near the close."
  **→ By-timeframe check (2026-07-06):** the fwd-window range's high precision is a
  **5m-only** phenomenon — at IWM 15m and 30m (window held ≈30 min) it collapses
  (top-bucket precision falls toward the noise floor / 0% at high confidence).
  Consistent with the close-concentration artifact: coarser bars have fewer
  observations near the close, so there is less priced seasonality to exploit —
  further evidence it is not a robust cross-timeframe edge.
- **E-30 / P0.1 (directional asymmetry) re-tread the direction program.** That
  program (purged+embargoed CV, cost-aware EV, all 3 tickers, incl. triple-barrier
  meta-labeling on the magnitude-EXPLOSIVE flag) found **no generalizable directional
  edge**; the up/down asymmetry is the well-known equity **skew** (puts richer than
  calls), already in option prices. The up-excursion "predictability" here is partly
  the vol signal re-measured (volatile bars have large excursions both ways) plus
  that priced skew. **Open action:** the call/put probe must clear purged+embargoed
  walk-forward + cost-aware EV before it counts — the single 70/30 split does not.

## Net
Nothing here overturns the standing FAIL/null verdicts. The session's value is a
sharper statement of WHERE residual signal concentrates (target-framing + an upside
asymmetry) and a concrete gating plan (gate-7 on the fwd-window target;
purged/embargoed cost-aware EV on the fwd-directional probe). Scratch harness +
per-experiment result JSONs retained by the author; not committed to the repo.

