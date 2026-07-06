# Model Registry — Unified (Strat / Magnitude / Direction)

**Unified record — merged 2026-06-10. Two parallel editions grew on different branches; BOTH are preserved here in full, nothing dropped. Where they describe the same model/experiment with different wording, both wordings are kept.**

- **Part A — Model Registry edition** (was `MODEL_REGISTRY.md`)
- **Part B — Model Catalog edition** (was `MODEL_CATALOG.md`)

---

# PART A — Model Registry edition

Canonical inventory of every model and probe in the program: what it **targets**,
its **key features**, the **data** it trains on, and **status**. Three families:
**A** = production/validated, **B** = direction research probes (this program),
**C** = proposed (the "rethink" — new information classes / representations).

> **Shared substrate (A, B, and most of C):** tickers IWM/SPY/QQQ; intraday
> timeframes 5m/15m/30m; 8 anchored expanding walk-forward folds (2019→2026);
> LightGBM; calibration `none`; gates = log-loss beat vs train-prior constant
> + ECE ≤ 0.05 (0.075 @ 30m). **Feature surface:** `strat_features_{tf}`
> (~50 indicators) LEFT JOIN `strat_features_levels_{tf}` (ORB / historical
> levels / order blocks) → ~143–248 cols after `featurize()`. **Bars:**
> `market_data_intraday` (1-min, resampled).

---

## A. Production / validated models

### A1 — Strat TYPE engine  ·  targets: STRUCTURE
- **Target:** `next_bar_type` ∈ {1, 2U, 2D, 3} (Strat candle classification).
- **Key features:** shared surface (strat class, FTFC, RSI/ATR/VWAP/stoch, ORB & levels).
- **Data:** `strat_features_{tf}` + `strat_features_levels_{tf}`.
- **Status:** ✅ VALIDATED — 8/8 folds log-loss beat, ECE ≤ 0.05 (5m/15m); 30m PARTIAL.
- **Code:** `gcp/research/strat_engine/strat_walk_forward.py`.

### A2 — Magnitude engine  ·  targets: SIZE
- **Target:** `magnitude_bucket` ∈ {TIGHT, NORMAL, EXPANDED, EXPLOSIVE} =
  \|next_close−next_open\| / ATR20, cuts at 0.5 / 1.0 / 1.5.
- **Key features:** Phase 0 = shared surface; Phase 1 vol-expansion (atr5/atr20,
  BB width, realized-vol z, range expansion); Phase 2 AV indicators; Phase 3
  event-calendar; Phase 4 cross-asset.
- **Data:** strat features + `market_data_indicators` (P2) + event calendar (P3)
  + `market_data_cross_asset` (P4).
- **Status:** ✅ VALIDATED on 5m/15m; **the predictable quantity.**
- **Code:** `gcp/research/magnitude_engine/`.

### A3 — Strat DIRECTION (baseline)  ·  targets: DIRECTION
- **Target:** binary `next_close > next_open`.
- **Key features / data:** shared surface.
- **Status:** ❌ FAILS — 0/72 folds. The reason this program exists.
- **Code:** `gcp/research/strat_engine/strat_dir_walk_forward.py`.

---

## B. Direction research probes (this program — verdict-bearing)

All target DIRECTION; all reuse the shared surface + harness; they vary the
**label / conditioning / model form**, not the features. Code:
`gcp/research/strat_engine/strat_dir_probes.py`; dedicated `direction-probe` CR Job.

| ID | Reframe | Result |
|---|---|---|
| **B1 E1 — Horizon** | sign of session-aware fwd-return at h ∈ {1…20} | 0/47 folds |
| **B2 E2 — Trigger** | direction only on Strat-trigger bars | 0/8 (no primary edge) |
| **B3 E3 — Regime** | direction trained within vix/gamma/session regime | 0/29 |
| **B4 E4 — Triple-barrier** | first-touch ±k·ATR (neutral band); symmetric 3-class + long/short meta-models; magnitude-EXPLOSIVE gated | log-loss 0/8; IWM-only long flicker (z≤4.2) that does **not** replicate on SPY/QQQ |

**Verdict (cost-free):** no *generalizable* directional edge from price-history
features; one unresolved IWM-only candidate. See `DIRECTION_RESEARCH_RESULTS.md`.

---

## C. Proposed — the rethink (new information classes / representations)

The binding limitation of A3/B1–B4 is the **information class**: every feature is
a deterministic transform of the instrument's own past OHLCV — exactly what EMH
says is already priced. C-models inject information that surface lacks.

### C1 — Flow-Direction engine ⭐  ·  targets: DIRECTION  ·  **READY**
- **Target:** direction (triple-barrier first-touch, reusing B4 harness).
- **Key NEW features (dealer positioning — never seen by A3/B4):**
  - **DEX** — net dealer delta exposure = aggregate(delta × OI), dealer-signed.
  - **Vanna / charm** — 2nd-order greeks → newsless intraday drift / afternoon pin.
  - **Short-DTE (0–2 DTE) DEX** — the charm-pin driver.
  - Reuse existing `pcr_*`, `iv_skew_25d`, `iv_term_slope`, `atm_iv` (Family-3).
- **Data:** `etf_options_snapshots` AV-EOD (delta+IV 100% filled, **2016→2026**),
  d-1 leak-safe shift. Spot via `options_greeks.derive_spot_from_chain`.
- **Calculations to build:** DEX aggregation; vanna/charm from BS `d1/d2`
  (validate against finite-difference of delta). New module `lib/features/flow_direction.py`.
- **Falsifiable prediction:** should help SPY/QQQ **more** than IWM (richer dealer flow).
- **Status:** ✅ READY (data + history confirmed).

### C1b — Flow-Direction intraday (per-bar DEX)  ·  DEFER
- AV-REALTIME intraday snapshots dense but **recent only** → can't span 8 folds. v2.

### C3 — Information-driven bars  ·  targets: any (re-runs A1/A2/A3)  ·  **READY**
- **Change:** replace fixed time bars with **volume / dollar bars** (sample on
  information arrival). No tick data → dollar bars approximated via Σ close×volume.
- **Data:** `market_data_intraday` 1-min `volume` (2019→2026). New module
  `lib/features/information_bars.py`.

### C5 — Fractional-differentiation features  ·  targets: any  ·  **READY (cheap)**
- **Change:** add fractionally-differentiated price (d*≈0.3–0.5) — stationary
  **and** memory-preserving — vs. today's memoryless returns.
- **Data:** bars. New module `lib/features/fracdiff.py` (FFD + ADF d* search).

### C6 — Rolling-window / recency-weighted training  ·  targets: any  ·  **READY (trivial)**
- **Change:** rolling recent window instead of anchored-expanding (tests whether
  direction lives in the current regime but is diluted by 2019 history).
- **Data:** none new — fold-construction flag in `strat_dir_probes.py`.

### C4 — Path / sequence representation  ·  targets: DIRECTION / TYPE  ·  staged
- **Change:** feed the bar *trajectory* (path signatures or temporal CNN/LSTM)
  instead of point-in-time snapshots. Data: bars. Build: new model class.

### C7 — Latent-regime (HMM) layer  ·  feeds A3/B4  ·  staged
- **Change:** infer a hidden regime state; predict direction conditional on it,
  instead of feeding `vix_tercile` as a flat column. Data: existing features.

### C2 — Cross-asset / Relative Direction  ·  targets: RELATIVE DIRECTION  ·  PARTIAL
- **Change:** predict *relative* direction (IWM−SPY spread, rotation) + VIX
  term-structure regime. Data: `market_data_cross_asset` (have: VIX spot/UST/DXY/
  oil/gold) **+ VIX futures term structure (NOT yet fetched — new feed needed).**

---

## Build sequence
1. **C1** (highest payoff, data ready, carries the falsifiable SPY/QQQ test).
2. **C5 + C6** as near-free add-ons to the C1 run (isolate memory / recency).
3. **C3** if C1 promising.
4. **C4 / C7** only if the above hint at signal.
5. **C2** needs a VIX-term-structure feed first.


---

# PART B — Model Catalog edition

**As of 2026-06-05.** Every model and experiment, existing and proposed, with
target / features / training data / status. Naming convention:
`<DOMAIN>-<FAMILY>`; FAMILY ∈ {RULES, SIZE, TYPE, DIRECTION, FLOW, META}.

> **Two senses of "deterministic":** (1) **rule-based** models — `STRAT-RULES`
> below and the naive baselines — have NO learning; given the bars, the output is
> fixed. (2) The **LightGBM** models are *learned* but *reproducible* (fixed
> seed, no bagging) — deterministic given the same data, not rule-based. When we
> say "the deterministic Strat model," we mean sense (1): `lib/strat.py`.

---

## A. Existing (built + run)

### A0 · `STRAT-RULES` — the DETERMINISTIC Strat classifier ★ (rule-based, no ML)
- **Family:** RULES (deterministic) · **Algorithm:** pure rules, no training.
- **What it computes:** single-bar Strat candle `1 / 2U / 2D / 3`; combo detection
  (Failed-2U/2D, RevStrat reversals, 212/312/132/322 continuations); FTFC
  (Full-Timeframe-Continuity) scoring across TFs; `trigger_high`/`trigger_low`
  (= prior bar's High/Low — the breakout levels).
- **Lives in:** `lib/strat.py` (`StratClassifier`) — the Strat engine's shared
  library. `gcp/research/strat_engine/strat_data_builder.py` runs it to persist
  `strat_candle`, `strat_combo`, `is_continuation/reversal`, `strat_setup`,
  `trigger_high/low` into `strat_features_<tf>`.
- **Roles in the ecosystem:**
  1. **PRIMARY signal in `STRAT-BREAKOUT-META` (A5)** — the trigger-break that
     *fixes the trade direction* is this deterministic rule; only the take/skip
     meta-filter is learned.
  2. **Feature source** for every ML model (the `strat_candle`/combo one-hots in
     the ~140-col spine).
  3. Production "cockpit" Strat methodology + FTFC.
- **Status:** ✅ production (deterministic, always-on). Spec: `docs/STRAT_METHODOLOGY.md`.

### A1 · `MAG-SIZE` — the size model
- **Family:** SIZE · **Algorithm:** LightGBM 4-class multiclass (300 trees, lr 0.05, depth 6, leaves 31, min_child 100, seed 42).
- **Target:** next-bar move bucketed in ATR-20 units → TIGHT/NORMAL/EXPANDED/EXPLOSIVE (0.5/1.0/1.5).
- **Features:** ~140 spine (`strat_features_<tf>` ⨝ `strat_features_levels_<tf>`): TA + Strat one-hots (from A0) + gamma + VIX.
- **Training data:** `strat_features_<tf>` (SPY/IWM/QQQ; 5m/15m/30m); `etf_options_snapshots` for gate-7 only.
- **Label-mode variants:** `body` → FAILED gate-7 (priced in); `excursion` → "passed" but **VRP/measurement artifact**; `call`/`put` → directional gate-7 **FAIL/INSUFFICIENT**.
- **Status:** Research, **closed**. Size is predictable; **nothing beats option IV.**

### A2 · `STRAT-TYPE` — the structure model
- **Family:** TYPE · **Algorithm:** LightGBM 4-class (same hyperparams).
- **Target:** next bar's Strat candle `next_bar_type` ∈ {1,2U,2D,3}.
- **Features/data:** ~140 spine; `strat_features_<tf>`.
- **Variants:** `strat_walk_forward`, `_adaptive`, `strat_pred_per_class` (OvR).
- **Status:** ✅ **Validates** (+0.11–0.16 logloss beat). Production structure signal.

### A3 · `STRAT-DIR` — the direction failure
- **Family:** DIRECTION · **Algorithm:** LightGBM binary.
- **Target:** `next_close > next_open`. **Features:** spine (+ news/cross-asset/vol-regime/options families in `_extended`).
- **Status:** ❌ **FAILED 24/24** (base + 4 feature families). Root cause = wrong target, not a bad model.

### A4 · `STRAT-CORR` — feature-discovery (not predictors)
`strat_corr_indicators` (MI ranking per `next_bar_type`) + `strat_corr_combos` (OOS combo-lift mining via `lib/combo_mining.py`). Feed A2 feature selection.

### A5 · `STRAT-BREAKOUT-META` — the one real edge ★ (deterministic primary + learned filter)
- **Family:** META · **Primary:** `STRAT-RULES` trigger break (deterministic, sets direction). **Meta-model:** LightGBM binary (learned take/skip).
- **Target (meta-label):** triple-barrier — did price hit +1.0·ATR profit target before −0.5·ATR stop within 12 bars? Barriers resolved on **1-minute** bars.
- **Features:** spine at decision bar + breakout side (no leak). OFI-proxy & IV-flow families A/B-tested → **both hurt**; edge is self-contained in structural features.
- **Data:** SPY/IWM/QQQ; 5m+15m; `strat_features_<tf>` + `market_data_intraday` (1-min, labels/fill).
- **Status:** ⚠️ **gross 24/24; META reproduces PASS on all cells, but NET is fragile/ticker-specific.** 2026-06-09 reconfirm on data extended to 2026-06 (realistic entry, 0.6bp): **only IWM 5m is a clean net-positive (+0.110 R, 8/8)**; SPY 5m (+0.042, 4/8), QQQ 5m (−0.027, 4/8), SPY 15m (+0.022, 4/7) all NET_FAIL — the 2026-06-05 "net across all 3 @5m" did NOT survive 2025–26. The stop-limit/realistic execution model is confirmed correct; net edge marginal — **not yet shippable multi-ticker.** The only VRP-immune path (trades the underlying). Caveats: ~10% same-tf-fallback labels; no decision-latency model. (E-18/E-24)

### A6 · `DIR-REGIME` — regime-conditional direction
- **Family:** DIRECTION · **Algorithm:** LightGBM binary per gamma regime.
- **Target:** sign of N-bar forward return (corrected from body sign); judged on expectancy.
- **Status:** ❌ **true null** — no consistent expectancy even split by gamma regime.

### A7 · `INTRADAY-MOM` — intraday momentum
- **Family:** DIRECTION · **Algorithm:** OLS replication + walk-forward LogisticRegression.
- **Target:** last-30-min return from first-30-min. **Data:** per-day from `strat_features_30m`.
- **Status:** ❌ **true null** — 1993–2013 anomaly decayed; negative β in 2016–26 even conditional on high-vol.

### A8 · `STRAT-NEXTBAR` — historical tape + next-bar directional forward-walk ✅ (validated OOS)
- **Family:** DIRECTION (next-candle) · **Algorithm:** deterministic transition table + fixed FTFC+CLV+momentum vote rule (no params) + held-out logistic.
- **Target:** next daily/weekly/monthly Strat candle; directional call = next ∈ {2U,2D}.
- **Features:** **close-location-value (CLV, the workhorse)** + 1–3-bar momentum + RSI/EMA-dist/streaks + **FTFC** (prior-completed weekly+monthly). Data: `market_data_daily` resampled to 1d/1w/1mo/1q.
- **Status:** ✅ **real held-out edge** — stacking FTFC+CLV lifts P(next=2U) ~58%→74–81%; **daily logistic ~70% OOS vs ~57% base, weekly ~75–80% vs ~62%** (+12–18pp). **But de-mechanization (2026-06-09) proves the edge is gap-mechanical, not directional foresight, and not standalone-tradeable.** Monthly inconclusive (thin). (E-25)
- **CLV ablation (held-out):** CLV_ONLY ≈ FULL edge; NO_CLV / STRUCT_ONLY (momentum+FTFC) ≈ 64–66% daily / 70–75% weekly, still +6–13pp over base.
- **CLV de-mechanization (2026-06-09):** **`CLV_LAG1` (prior-bar CLV) ≈ 0 lift everywhere**, and the **gap-neutral target (`next_close>next_open`) collapses every set to base** — the entire next-bar edge is the **contemporaneous open-gap mechanism**, not directional content. The structural residual predicts *which trigger breaks*, not the bar's own direction.
- **Costed underlying backtest (2026-06-09):** trading the underlying on P(next_up) nets **≈0 after 2bps/side at daily (honest open→close), Sharpe ≈0**; the small edge is the overnight gap (needs close-execution); weekly "profit" is **market beta** (underperforms buy-and-hold). → use as a structural/regime read and the PRIMARY-side direction for a barrier strategy (BREAKOUT-META), **not** a standalone close-to-close signal.
- **Lives in:** `lib/strat.py:compute_strat_history` (+1-3-1 detection, per-bar triggers), `lib/data_loader.py` (`'1q'`) + `scripts/strat_{history_report,backtest,next_candle_analysis,forward_walk,forward_walk_oos,oos_multi_tf,oos_clv_ablation,clv_demech,struct_backtest}.py`, `tests/test_strat_{history,clv_demech,struct_backtest}.py`. PRs #592–#596 (merged) + CLV de-mech / costed structural backtest (this PR). Full detail + per-script roles + reproduce commands: **`EXPERIMENT_REGISTRY.md` §E-25**. Runs vs Cloud SQL as the `magnitude-engine` job.

### Deterministic baselines (rule-based nulls, no ML)
Naive DoW×30-min calendar lookup (MAG gate-6), "follow the gamma regime" (DIR-REGIME control), "take every breakout" (BREAKOUT-META base), train-prior class baseline (all log-loss gates).

---

## B. Deferred / not built

| Name | Family | Predicts | Status |
|---|---|---|---|
| `FLOW-OFI` (true) | FLOW | short-horizon direction | **data-blocked** — needs L2/tick (AlphaVantage = OHLCV only; Polygon/Databento/IEX required) |
| `HONEST-GATE7` (eval) | — | excursion vs time-of-day IV | **data-blocked** — options are EOD-only (1 snap/day 2019→2026) |

Full results + self-audit story: `MODEL_RETHINK_PLANS.md` §RESULTS;
end-to-end log: `EXPERIMENT_REGISTRY.md`; master narrative: `MODELS_END_TO_END.md`.

---

## C (proposed / open) — Movement-Forecast head (2026-07-06 probe)

### C-mf — Forward-window magnitude + directional excursion  ·  targets: SIZE + DIRECTION (30-min horizon)
- **Target (proposed):** over the next K=6 bars (~30 min) — (a) range bucket
  `(max(high[t+1..t+K])−min(low[t+1..t+K]))/atr20[t]`, cuts ~1.5/3/6; and (b) up/down
  excursion `(max(high)−next_open)/atr20` and `(next_open−min(low))/atr20`, cuts ~1/2/3.5.
- **Key features / data:** same shared surface + `mins_since_open` (top feature); no new
  data required. External event-calendar + options IV joins tested, only marginal (E-31).
- **Status:** 🔬 **PROBE ONLY — NOT validated, NOT shipped.** On a weak single 70/30 split
  (IWM/SPY/QQQ 5m) the fwd-window range hits 50–59% top-bucket precision / 8–10× lift and
  the up-excursion 4.8–7.0× (both generalize) — but **neither has cleared the program's
  gates**, and both re-tread already-priced ground: the range is the vol/calendar signal
  gate-7 found priced (`MAGNITUDE_ENGINE_RESULTS.md` §2026-07-06 addendum), and the up>down
  asymmetry is the option skew the direction program already gated as null
  (`DIRECTION_RESEARCH_RESULTS.md` §2026-07-06 addendum).
- **Gate to advance to B/A:** purged+embargoed 8-fold walk-forward, cost-aware EV
  (+$0.02/sh net, ≥6/8 folds, $0.05 friction), and gate-7 (realized/implied ≥1.25) on the
  forward-window target — net against the straddle/skew it would trade.
- **Provenance:** scratch harness, `EXPERIMENT_REGISTRY.md` §2026-07-06 (E-28/E-30/P0.1).

