# Model Catalog — Strat / Magnitude Research

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
- **Status:** ✅ **gross 24/24; NET-POSITIVE under realistic fill at true spreads — SPY/IWM/QQQ at 5m and SPY at 15m** (2026-06-05). IWM/QQQ 15m marginal. The only VRP-immune edge found (trades the underlying). Caveats: ~10% same-tf-fallback labels; no decision-latency model.

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
- **Status:** ✅ **real held-out edge** — stacking FTFC+CLV lifts P(next=2U) ~58%→74–81%; **daily logistic ~70% OOS vs ~57% base, weekly ~75–80% vs ~62%** (+12–18pp, positive log-loss beat nearly every year 2017→2026). Monthly inconclusive (thin). **Caveats:** CLV partly mechanical; predicts *which trigger breaks*, not close-to-close P&L. (E-25)
- **Lives in:** `lib/strat.py:compute_strat_history` (+1-3-1 detection, per-bar triggers) + `scripts/strat_{history_report,backtest,next_candle_analysis,forward_walk,forward_walk_oos,oos_multi_tf}.py`. Runs vs Cloud SQL as the `magnitude-engine` job.

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
