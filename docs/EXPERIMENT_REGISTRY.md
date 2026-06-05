# Experiment Registry — Complete Record of Every Model & Experiment

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
| `intraday_flow_15m` (materialized) | order-flow (OFI/CVD) | ~6.5k/yr/ticker | B5b/E5b (in progress) |
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

- **B5b / E5b (intraday OFI):** backfill in progress at write time (per-row upsert
  is slow — ~530k INSERT round-trips; a `COPY`/`executemany` rewrite is the fix);
  3 experiments queued. **Results row below is a placeholder.**
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

### B5b (E5b) — Intraday order-flow imbalance (OFI)  🚧 IN PROGRESS
- **Status:** in-progress (backfill running at write time). **Question:** does *intraday* order-flow (vs slow daily flow) add direction?
- **Target:** E4 long/short triple-barrier; +3 OFI cols (`ofi_norm`=signed_vol/tot_vol, `ofi_3bar`, `cvd_intraday`), **contemporaneous (no shift)**, merged on 15m `ts`.
- **Features/why:** tick-rule signed volume from 1-min bars within each 15m bar — microstructure (Cont-Kukanov-Stoikov), the one remaining lever with a real prior. §3.7: zero/missing vol→NaN.
- **Structure:** materialized `intraday_flow_15m` (scan-once builder, Rule 0); SQL signed-Σ push-down; 8 hermetic tests pass.
- **Results:** **PENDING** — IWM/SPY/QQQ × {baseline vs +intraflow} long/short z. To be filled when poller completes.
- **Approach/why:** E5 tested *slow daily* positioning; OFI tests *fast contemporaneous* flow at the same 15m alignment that worked for baseline RSI.
- **Verdict:** TBD.
- **Open/known gap:** builder per-row upsert is slow (~530k round-trips) — COPY/executemany rewrite pending.
- **Artifacts:** `lib/features/intraday_flow.py`; `gcp/build_intraday_flow.py`; `tests/test_intraday_flow.py`; commits e60a114 (feature), this branch.

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
