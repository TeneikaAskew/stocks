# Magnitude Engine — Directional (Call/Put) + Movement-Sim Session Handoff

**Date:** 2026-06-04
**Branch:** `feature/magnitude-indicator-spine`
**Author context:** extends the magnitude engine from a non-directional (straddle)
size model to directional call/put plays, and adds a frictionless movement-only
options P&L simulator. Comparison of two direction sources (model-learned label
vs Strat-structure overlay).

---

## 0. TL;DR for the next engineer

- **Magnitude engine = a SIZE predictor.** Given the current 5-min bar + 140ish
  features, it predicts how *big* the next bar will be, bucketed in ATR-20 units
  (TIGHT / NORMAL / EXPANDED / EXPLOSIVE). It does **not** natively predict
  direction.
- **Strat engine = a STRUCTURE predictor + feature factory.** It classifies each
  bar into Rob-Smith Strat candles (1 / 2U / 2D / 3) and combos, persists ~140
  features per bar into `strat_features_<tf>` (the magnitude engine consumes
  these), and has a TYPE model (next candle shape) that works and a DIRECTION
  model (next close>open) that **failed 24/24 folds**.
- **The original magnitude verdict (2026-05-29): FAIL.** The `body` label
  (|next_close−next_open|/ATR) realized move was ~0.83–0.92× the option-implied
  move — i.e. the options market had already priced the size. Closed.
- **This session reopened it on a different label.** The `excursion` label
  (full intrabar range, `(next_high−next_low)/ATR`) **PASSED gate 7** (~1.5–2×
  implied, 8/8 folds, all 3 tickers). Intrabar *path/range* is under-priced even
  though close-to-close *body* is not. That's a long-gamma / straddle-scalp edge,
  not a buy-and-hold straddle edge — see the honesty caveat in §6.
- **Direction was then added two ways and compared** (this session's core work):
  - **Arm A** — train the magnitude model directly on a directional label
    (`call` = upside-only excursion, `put` = downside-only). Fewer signals,
    bigger moves (~0.9–1.2 ATR).
  - **Arm B** — keep the symmetric `excursion` size model, take direction from
    Strat structure (2U/continuation→call, 2D→put). Many more signals, ~0.8 ATR.
- **Movement-only simulator** (`scripts/magnitude_movement_sim.py`, NEW): gross
  P&L for straddle/strangle/call/put on EXPLOSIVE bars, in ATR units, COSTS
  DEFERRED (no spread/commission/theta — by explicit request).
- **Open as of this writing:** directional gate-7 (does the one-sided move beat
  the matching call/put IV) is re-running with a 6h timeout after several
  image-desync false starts (see §7).

---

## 1. What "the magnitude engine" is (data-science detail)

| Aspect | Detail | Source |
|---|---|---|
| **Task** | 4-class multiclass classification of next-bar move size | `mag_pred_train.py:169` |
| **Algorithm** | `LGBMClassifier(objective="multiclass", num_class=4, n_estimators=300, learning_rate=0.05, max_depth=6, num_leaves=31, min_child_samples=100)`; seed 42; no bagging → deterministic | `mag_pred_train.py:169-175` |
| **Label** | bucket of `move / atr_20`; thresholds `(0.5, 1.0, 1.5)` → TIGHT/NORMAL/EXPANDED/EXPLOSIVE | `mag_config.py:39-70`, `mag_dataset.py` |
| **Label modes** | `body`=\|nc−no\|; `excursion`=nh−nl; **`call`=nh−no (new)**; **`put`=no−nl (new)** — all ÷ atr_20 | `mag_config.py:52-70`, `mag_dataset.py:351-365` |
| **Features** | ~140: 36 numeric indicators (EMA/SMA/RSI/StochRSI/MACD/ATR/BB/OBV/RVOL/VWAP/VIX/GEX/VEX/flip/king-gate dist) + 10 one-hot categoricals (strat_candle, prev1-3_candle, strat_combo, vix/gex/vex terciles, dealer/gamma regime) | `mag_dataset.py`, baseline = `strat_features_<tf>` ⨝ `strat_features_levels_<tf>` |
| **Leakage guards** | drops fwd_* / next_open/high/low/close / atr_20_computed / is_continuation etc. before fit | `mag_pred_train.py:35-68` |
| **Scope** | TICKERS = {SPY, IWM, QQQ}; TIMEFRAMES = {5m, 15m, 30m} | `mag_config.py:18-22` |
| **Validation** | 8 anchored expanding walk-forward folds (test 2019→2026), MIN_TEST_BARS=200, calibration="none" (raw softmax) | `mag_config.py:24-35` |

### The gate ladder (all must pass for a phase to "pass")
1. **Gate 1** log-loss beats train-prior in ≥6/8 folds
2. **Gate 2** ECE ≤ 0.05 (5m/15m), ≤0.075 (30m), ≥6 folds
3. **Gate 3** decisive-call hit rate monotone across conf thresholds [.40,.50,.60,.70]
4. **Gate 4** EXPLOSIVE lift over base rate ≥ 1.5, ≥6 folds
5. **Gate 5** bootstrap-on-test-bars PASS ≥ 0.80 (fragility)
6. **Gate 6** mechanism: predicted-EXPLOSIVE concentration ÷ base rate ≥ 2.0
7. **Gate 7** *the trade test* — on EXPLOSIVE bars, realized move ÷ option-implied
   move ≥ **1.25** in ≥6 IV-covered folds. Implied move =
   `spot × IV × sqrt(5 / 98280)` (252×390 RTH min/yr); IV from ATM contract in
   `etf_options_snapshots` at/before T-1 EOD. — `scripts/implied_vs_realized_check.py`

---

## 2. What "the strat engine" is

Two roles:

1. **Feature factory (Stage 1).** `strat_data_builder.py` aggregates OHLCV to each
   TF, runs `lib.strat.StratClassifier.detect_combos` + `lib.indicators.add_all_indicators`
   + gamma, and upserts ~140 cols into `strat_features_<tf>` (1m/5m/15m/30m/60m/4h).
   **The magnitude engine reads these tables** — so the two engines share one
   feature spine (no drift).
2. **Models.**
   - **TYPE model** — predicts next bar's *candle shape* (1/2U/2D/3). Validates
     consistently. This is the production "cockpit" structure signal.
   - **DIRECTION model** (`strat_dir_walk_forward.py`) — target `next_close>next_open`,
     binary LightGBM. **FAILED 24/24 folds** (0/8 log-loss beat per cell). Extended
     R&D (`docs/DIRECTION_FEATURES_R&D.md`) tried news-sentiment, cross-asset,
     options-derived, vol-regime families — all failed. **Conclusion: bar-level
     direction is not learnable from these features.**

Production Strat math lives in `lib/strat.py` (candle classify 1/2U/2D/3; combo
detection 212/312/132/322/f2u/f2d; FTFC continuity scoring across TFs with
weights). The research strat engine reuses it.

---

## 3. Side-by-side: magnitude vs strat

| | **Magnitude engine** | **Strat engine** |
|---|---|---|
| **Predicts** | SIZE of next bar (ATR buckets) | STRUCTURE (candle type) + supplies direction *heuristically* |
| **Algorithm** | LightGBM 4-class multiclass | LightGBM (TYPE: 4-class; DIR: binary) |
| **Direction?** | No (natively). New `call`/`put` labels make it directional (Arm A) | TYPE=no; DIR model failed; **structure used as a heuristic direction filter (Arm B)** |
| **Feature source** | `strat_features_<tf>` (consumes strat output) | builds `strat_features_<tf>` |
| **Status** | Research; `body` failed gate-7, `excursion` passed | Research; TYPE works, DIR failed |
| **Trade vehicle implied** | straddle/strangle (size); call/put (new directional) | direction overlay on the size signal |
| **Cloud Run job** | `magnitude-engine` (`gcp/deploy.sh:889`) | `strat-engine` |
| **Hyperparams** | identical to strat (locked for apples-to-apples) | identical |

**How they integrate (this session's design):** magnitude supplies the *size*
conviction (is a big move coming?), strat supplies a *direction* lean
(up or down?). Neither alone is a directional trade; combined they nominate a
call or a put. The session measured whether that combination produces real
directional movement (yes, ~0.8 ATR) and — pending — whether it beats option IV.

---

## 4. What this session tried / researched / applied

### Researched
- Confirmed the strat DIRECTION predictor failed (24/24) and exports no per-bar
  probability → strat cannot supply a *trained* direction; only structural
  heuristic. This is why direction had to be generated here.
- Confirmed `strat_features_<tf>` already persists `strat_candle`, `strat_combo`,
  `is_continuation`, `is_reversal` → Arm B overlay needs no new fetch.
- Confirmed `etf_options_snapshots` stores per-`option_type` rows → put-side IV is
  directly queryable for the directional gate-7.

### Applied (code, committed)
1. `mag_config.py` — `LABEL_MODES` += `call`, `put`.
2. `mag_dataset.py` — call = `(next_high−next_open).clip(0)`, put =
   `(next_open−next_low).clip(0)`, both ÷ atr_20, bucketed.
3. `mag_walk_forward.py` — `--label-mode` choices now reference `list(LABEL_MODES)`
   (was hardcoded `["body","excursion"]` → caused first call/put run to fail).
4. `implied_vs_realized_check.py` — `--label-mode call/put`; directional realized
   move; **matching-leg IV** (call→ATM call delta+0.5; put→ATM put delta−0.5,
   `option_type='puts'`).
5. `scripts/magnitude_movement_sim.py` (NEW) — frictionless 4-position movement
   P&L, `--direction none|label|strat`, ATR-unit reporting, per-fold + GCS json,
   COSTS-DEFERRED banner.

### Verified
- Local label parity: UP bar→call≫put, DOWN bar→put≫call, wide-flat→excursion
  large/body small. Exactly as intended.

---

## 5. Results so far

### Straddle (symmetric `excursion`, movement-only)
~**1.3 ATR** mean gross move on EXPLOSIVE bars, **100% positive**, all 3 tickers.
Cross-checks the excursion gate-7 PASS.

### Directional movement (ATR units, COSTS DEFERRED)

| | Arm A (model label) | Arm B (Strat overlay) |
|---|---|---|
| call | SPY .87 / IWM 1.00 / QQQ .97 | SPY .74 / IWM .78 / QQQ .78 |
| put | SPY 1.18 / IWM .92 / QQQ 1.02 | SPY .87 / IWM .80 / QQQ .84 |
| n (signals) | 69–303 (selective) | 494–1873 (broad) |

### Per-year durability (Arm B, the Strat side)
- **PUT (down): rock-solid** — every ticker-year 0.71–0.96 ATR, %>0 = 0.95–1.00,
  through COVID / 2022 bear / 2024-25 bull. Fires 2–3× more than call.
- **CALL (up): positive every ticker-year** but softer (~0.7–0.8 ATR) and noisier;
  weakest cells are small-n early years (2019–21). Up-grinds slower than down-spikes.
- **No negative or near-zero year** → the overall average is not masking a bad
  stretch.

### Directional gate-7 (tradable vs IV) — **PENDING** (running, 6h cap)

---

## 6. Honesty caveats (read before trusting any number)

1. **Movement-only = gross upper bound.** No bid-ask, commission, slippage, or
   theta. Every sim banners `COSTS DEFERRED`. A real long-option P&L is lower.
2. **Excursion gate-7 ≠ straddle hold-to-close.** The `excursion` label is full
   intrabar high−low; a straddle held to bar close only captures the *body*
   (which failed gate-7). The excursion edge requires *scalping the path*
   (long-gamma), which itself incurs the very frictions deferred here. Don't
   conflate "excursion beats implied" with "buy a straddle, hold, profit."
3. **Arm B direction is a heuristic, not a model.** Strat structure is a rule
   (2U→up). It is *not* a trained, calibrated probability. The ~0.8 ATR is the
   realized move conditional on that rule firing, measured ex-post.
4. **Small-n cells are noisy** (IWM-call 2020 n=15; QQQ-call 2026 n=32). Treat
   those years as indicative, not conclusive.
5. **Directional gate-7 not yet in.** Until it lands, we know the move is *real*
   (~0.8–1.2 ATR) but not whether it *beats the call/put option's price*.

---

## 7. Operational notes / gotchas (Cloud Run)

- **Job:** `magnitude-engine` (Cloud Run Job, region us-east1). Single-task
  dispatch pattern used here: `gcloud run jobs update magnitude-engine
  --image …:research --command python --args="^@@@^-m@@@<module>@@@…"` then
  `execute --async`.
- **Image:** `…/trading-system:research`, built via `./gcp/deploy.sh build-research`
  (`cp -r scripts/ gcp/ lib/` into a tmpdir → `gcloud builds submit`). ~6.5 min.
- **DESYNC GOTCHA (cost ~3 false-start rounds this session):** the build packages
  whatever is on **disk** at build time. The harness occasionally lags flushing
  `Edit`/`Write` to disk, so a build can ship a *stale* copy of an edited file —
  the job then dies with argparse exit-2 ("unrecognized/invalid argument") even
  though the local file is correct. **Always fingerprint-verify the file inside
  the image before dispatching a real run:**
  ```bash
  gcloud run jobs update magnitude-engine --image …:research --command python \
    --args="^@@@^-c@@@import hashlib;print(hashlib.sha256(open('scripts/X.py','rb').read()).hexdigest()[:12])"
  # compare to: python3 -c "import hashlib;print(hashlib.sha256(open('scripts/X.py','rb').read()).hexdigest()[:12])"
  ```
  A substring check (`'--label-mode' in src`) is NOT enough — it false-passes on
  stale files. Use the full SHA.
- **Gate-7 timeout:** the scoped IV query over the 92M-row `etf_options_snapshots`
  needs >30 min for the call/put date sets; first runs died at the 1800s cap.
  Re-run with `--task-timeout 21600` (6h). Cloud Run charges runtime, not the cap.
- **DB access from sandbox:** only port 443 egress. Direct SQL is blocked; use
  `./scripts/db_query_cr.sh` or run the analysis *inside* a Cloud Run Job.
- **Log freshness quirk:** `gcloud logging read --freshness` can miss recently
  completed runs; prefer reading the durable GCS json summary the sim writes.

---

## 8. Where the artifacts live

- **Predictions:** `gs://…-trading-data/research/magnitude_engine/phase0/<ticker>_5m/predictions_<exec>.csv`
- **Movement-sim summaries:** same prefix, `movement_sim_<position>_<direction>_<ts>.json`
  (fields: n_bars, overall_mean/median_payoff_atr, per-fold array, costs banner).
- **Run-id tracking (this session, /tmp):** `wfx.txt` (excursion), `wf_call.txt`,
  `wf_put.txt`, `sim_*.txt`, `g7_*.txt`.

## 9. Suggested next steps

1. Land directional gate-7 verdict (running). If call/put one-sided move beats
   matching-leg IV → directional edge is tradable-before-costs.
2. Add a friction model to the simulator (the deferred costs) — turn gross ATR
   into net, the real go/no-go.
3. If Arm B (Strat) is the chosen direction source, formalize the structural
   direction rule (currently 2U/2D/continuation heuristic) and calibrate it.
4. Re-run call/put with a ≥40-bars/year floor to get the clean call baseline.
