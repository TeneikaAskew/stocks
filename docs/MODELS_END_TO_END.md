# Models — Full End-to-End Experiment Log

**One document, every model/experiment ever run across the Strat + Magnitude
research program**: what it predicts, why that target/approach was picked, the
features and structure, the correlation analysis, the result, and the verdict.
Newest work (the 2026-06 directional rethink) is included alongside the older
phases. Detailed per-area docs are linked at the end; this is the index + the
story.

Scope: SPY / IWM / QQQ, intraday 5m / 15m / 30m, walk-forward 2019→2026
(8 anchored expanding folds), LightGBM throughout (locked hyperparameters so a
phase pass is attributable to *features*, not tuning).

---

## 0. The scorecard (read this first)

| # | Model | Family | Predicts | Verdict | Where it died / lived |
|---|---|---|---|---|---|
| 0 | **STRAT-RULES** | rules (deterministic) | candle 1/2U/2D/3, combos, FTFC, trigger levels | ✅ production | `lib/strat.py` — no ML; the PRIMARY in #6 + feature source for all |
| 1 | **STRAT-TYPE** | structure | next candle shape 1/2U/2D/3 | ✅ **WORKS** | beats base rate +0.11–0.16 logloss; the production structure signal |
| 2 | STRAT-DIR | direction | next_close>next_open | ❌ FAIL 24/24 | wrong target (body sign ≈ coin flip) |
| 2b | DIR feature R&D | direction | same, + 4 new feature families | ❌ FAIL/INFEASIBLE | news, cross-asset, vol-regime all 0/8; options infeasible |
| 3 | MAG-SIZE `body` | size | \|next_close−next_open\|/ATR | ❌ FAIL (gate 7) | realized ≈ implied; priced into IV |
| 3b | MAG-SIZE phases 0–4 + calendar | size | same, +feature families | mostly FAIL | only 5m strong; "Phase 3" pass was a calendar proxy |
| 3c | MAG-SIZE `excursion` | size | (next_high−next_low)/ATR | ⚠️ "passed" gate 7 | **measurement artifact** (range vs straddle is apples-to-oranges) |
| 3d | MAG-SIZE `call`/`put` | directional size | one-sided excursion vs matching IV | ❌ FAIL/INSUFF | one-sided move ≤ matching-leg IV (VRP) |
| 4 | INTRADAY-MOM | direction | last-30min from first-30min | ❌ true null | anomaly decayed post-2013; negative β in 2016–26, even conditional |
| 5 | DIR-REGIME | direction | move-continuation \| gamma regime | ❌ true null | no consistent expectancy even with fixed target+metric |
| 6 | **STRAT-BREAKOUT-META** | meta (deterministic primary + learned filter) | will a Strat trigger-break follow through | ✅ **real edge** | gross 24/24; NET-positive SPY/IWM/QQQ @5m + SPY @15m under realistic fill (2026-06-05) |

**The throughline:** *structure* and *size* are predictable; *direction* is not
(from the data we have). Anything that tries to beat the option's own implied
move loses to the variance-risk premium. The one genuine, VRP-immune edge —
breakout follow-through on the underlying — is real but marginal after costs.

---

## 1. Architecture: two engines, one feature spine

```
1-min OHLCV ─► aggregate_to_timeframe ─► StratClassifier (candle+combo+FTFC)
                                          + add_all_indicators (TA suite)
                                          + gamma (GEX/VEX/flip/king-gate)
                                          ─► strat_features_<tf>  (~140 cols)
                                                   │
                 ┌─────────────────────────────────┼─────────────────────────────┐
        STRAT engine                         MAGNITUDE engine              RETHINK models
   (predict next candle TYPE)            (predict next-bar SIZE)        (meta / regime / momentum)
```

- **`strat_features_<tf>`** is the shared spine (built by
  `gcp/research/strat_engine/strat_data_builder.py`). Both engines read it, so
  features can't drift between them.
- **~140 features:** 36 numeric TA (EMA 9/20/50/200, SMA 50/200, RSI 9/14,
  StochRSI, MACD family, ATR 14/20, Bollinger upper/lower/width/%b, OBV, RVOL,
  VWAP + price-vs-VWAP/EMA, consecutive up/down, intraday return, high-low
  spread, VIX) + gamma (total_gex, total_vex, flip_price, distance_to_king/gate)
  + 10 one-hot categoricals (strat_candle, prev1/2/3_candle, strat_combo, VIX/
  GEX/VEX terciles, dealer_regime, gamma_regime).
- **LightGBM, locked:** `n_estimators=300, lr=0.05, max_depth=6, num_leaves=31,
  min_child_samples=100, seed=42`. Identical across all models → a pass is the
  features talking, not hyperparameter search.
- **Leakage discipline:** `featurize()` drops every forward-looking column
  (`fwd_*`, `next_*`) and bookkeeping/derived flags before fit. The label is
  strictly t+1 (session-aware shift so it never crosses the overnight gap).

---

## 2. The correlation / feature-discovery layer (why features were picked)

Features were never hand-waved in — the Strat engine has a dedicated
correlation stack that *ranks* features against the target before the model
sees them:

- **Stage 3 — single-feature correlation** (`strat_corr_indicators.py`):
  mutual-information / information-coefficient ranking of each indicator vs
  `next_bar_type`, **per class** (one-vs-rest). Tells us which indicators carry
  marginal signal for each candle outcome.
- **Stage 3b — combination mining** (`strat_corr_combos.py` →
  `lib/combo_mining.py`): binarize conditions → `select_top_features` (top-k by
  mutual info, train-only) → `mine_combos` enumerates 1/2/3-way AND-combos and
  scores each **out-of-sample** by hit-rate and **lift** (hit_rate ÷ base_rate),
  keeping combos with ≥500 test-row support. This is how interpretable
  "if RSI<30 AND 2D AND neg-gamma → next bar 2U at 1.4× base" rules are found —
  and crucially they're scored on a held-out split so a combo that's good only
  by overfitting is rejected.
- A parallel **regime-combo** pipeline (`gcp/regime_combo_job.py`) mines
  GEX×VEX-tercile regime combos weekly.

Key finding from the correlation layer: the indicators carry real association
with *structure* (next candle type) and *size*, but the per-class direction
signal (up vs down body) is near-zero — which foreshadowed every direction
failure below.

---

## 3. STRAT-TYPE — the model that works ✅

- **Target:** `next_bar_type` ∈ {1, 2U, 2D, 3} (the next bar's Strat candle
  shape). **Why:** the Strat methodology is fundamentally about candle
  structure & continuity (FTFC), not raw direction; classifying the next
  *shape* is the native, well-posed question.
- **Structure:** LightGBM 4-class multiclass, the 6-stage pipeline (data →
  EDA/base-rates → Stage 3 corr → Stage 3b combos → **Stage 4 train+calibrate =
  the gate** → readout). Gate = OOS accuracy beats base rate by ≥N pp + ECE
  calibration check.
- **Result:** PASSES — beats the train-prior baseline by **+0.11 to +0.16
  median log-loss**, consistently across folds. This is the validated production
  "cockpit" structure signal.
- **Why it works where direction doesn't:** candle shape (did the bar make a
  higher high / lower low) is mechanically tied to volatility & range, which the
  TA/gamma features genuinely predict. Sign of the close is not.

Detail: `docs/STRAT_ENGINE_AND_COMBO_PIPELINE.md`, `docs/STRAT_METHODOLOGY.md`.

---

## 4. STRAT-DIR + direction feature R&D — direction is not learnable ❌

- **Target:** `next_close > next_open` (binary body direction). **Why picked:**
  the obvious "which way next" question; if learnable it'd be the most valuable
  signal. **Structure:** binary LightGBM, same spine, same folds.
- **Result:** **FAIL 24/24 folds** — log-loss beat is *universally negative*
  (−0.003 to −0.14); the model is worse than always-predicting the class prior.
  Decisive-call hit-rate wanders within ±2pp of 0.50.
- **The R&D extension** (`docs/DIRECTION_FEATURES_R&D.md`) added four orthogonal
  feature families on top of the spine to try to rescue it:
  | family | columns | result |
  |---|---|---|
  | news_sentiment | 9 (rolling sentiment, counts, topic flags) | FAIL 0/8 every cell |
  | cross_asset | 9 (VIX Δ/z, term structure, VVIX, IWM−SPY) | FAIL 0/8 every cell |
  | vol_regime | 7 (ATR%, realized vol, gap, range/ATR) | FAIL 0/8 every cell |
  | options_derived | PCR, IV skew/term, ATM IV | INFEASIBLE (pg8000 too slow on 14M option rows in the task budget) |
- **Conclusion:** next-bar body direction is **information-content-unlearnable**
  from every densely-available surface (TA, news, cross-asset, vol-regime,
  dealer-positioning). The honest next step is *new data* (order-flow / tick
  microstructure), not more features. This conclusion drove the 2026-06 rethink
  (don't predict direction — reframe the question).

---

## 5. MAGNITUDE-SIZE — predict how big, not which way

- **Target:** next-bar move bucketed in ATR-20 units → TIGHT/NORMAL/EXPANDED/
  EXPLOSIVE (thresholds 0.5/1.0/1.5). **Why:** if direction is unlearnable,
  *size* might be (volatility clusters), enabling a non-directional options bet
  (straddle/strangle).
- **Structure:** LightGBM 4-class + a **7-gate success ladder** — (1) log-loss
  beat, (2) ECE calibration, (3) confidence monotonicity, (4) EXPLOSIVE lift
  ≥1.5, (5) bootstrap fragility ≥0.80, (6) mechanism concentration ≥2.0,
  (7) **the trade test**: on EXPLOSIVE bars, realized move ÷ option-implied move
  ≥1.25.
- **Phases (each tests a feature family in isolation on top of the baseline):**
  | phase | added features | 5m | 15m | 30m |
  |---|---|---|---|---|
  | 0 baseline (140-col) | — | 2/3 | 1/3 | 0/3 |
  | 1 vol-family | ATR ratio, BB bandwidth, realized-vol z, range-expansion | 3/3 | 1/3 | 0/3 |
  | 2 AV daily indicators | ADX, MFI, Chaikin, Aroon, ROC | 3/3 | 1/3 | 0/3 |
  | 3 event proximity | hours-to/from econ events | 3/3 | 2/3 | 0/3 |
  | 3b calendar | hour/dow/week/FOMC/month-end | 3/3 | 1/3 | 0/3 |
  - Size **is** predictable at 5m (3/3 tickers), weak at 15m, absent at 30m.
    "Phase 3" looked like the winner (crossed 2-of-3-TFs) but the bootstrap +
    mechanism gates (5 & 6) showed only **IWM 5m** was robust+mechanistic; the
    15m passes were fragile gate-edge estimates, and Phase_calendar proved the
    Phase-3 signal was a **calendar proxy** (time-of-day vol), not event-driven.
- **Gate 7 — the killer (2026-05-29):** on EXPLOSIVE bars the `body` realized
  move was only **0.83–0.92×** the option-implied move (ratio < 1.0 < 1.25).
  **The options market had already priced the size.** Project closed FAIL.
- **2026-06 reopen on `excursion`** (full intrabar range): "passed" gate 7 at
  ~1.5–2× — **but this is a measurement artifact**: high−low range is
  mechanically ~1.5–2× the close-to-close move for the *same* vol, so comparing
  range to a straddle's expected move is apples-to-oranges (a held straddle only
  captures the body). Not a real edge.
- **`call`/`put` directional labels** (this session): retarget the size model to
  one-sided excursion (upside for call, downside for put) and gate-7 against the
  *matching* option's IV. **FAIL / INSUFFICIENT** — the one-sided move is ≤ the
  matching-leg implied move. Same VRP wall, now confirmed directionally.

Detail: `docs/MAGNITUDE_ENGINE_RESULTS.md`,
`docs/MAGNITUDE_DIRECTIONAL_SESSION_HANDOFF.md`.

---

## 6. The 2026-06 rethink — reframe the question

Premise (from the research synthesis): every prior failure was "predict what the
option already prices." The fix is to ask questions the option price does *not*
contain, and to **trade the underlying** (no IV/VRP to beat). Three models built;
each first-pass result was then **self-audited** for structural flaws and
re-run corrected.

### 6a. INTRADAY-MOM — true null
- **Idea:** Gao-Han-Li-Zhou — first-30min return predicts last-30min return
  (R²≈1.6%), stronger on high-vol days. Per-day model.
- **Corrected test:** ran the OLS on the high-VIX and big-open subsets (the
  conditional claim), not just pooled. β stays **negative & insignificant**
  everywhere. The 1993–2013 anomaly has **decayed/reversed** in 2016–2026. Dead.

### 6b. DIR-REGIME — true null
- **Idea:** direction is unconditional-unlearnable but maybe *regime-conditional*
  — positive gamma → mean-revert, negative gamma → momentum. A pooled model
  averages the two to zero.
- **Corrected test:** target = sign of N-bar **forward return** (move
  continuation, not body sign), verdict on **expectancy** vs a naive-regime
  control (not log-loss), P&L sign bug fixed. Still FAIL — positive expectancy in
  only 3–4/8 folds, rarely beats the naive control. Regime split doesn't unlock
  tradeable direction at 15m.

### 6c. STRAT-BREAKOUT-META — the one real edge ⚠️
- **Idea (López de Prado meta-labeling):** the Strat is a stop-entry *breakout*
  system — direction is **deterministic** (break trigger_high → long). So don't
  predict direction; predict **whether the breakout follows through**.
  - **Primary (rule):** t+1 breaks bar t's high/low; side fixed by the rule.
  - **Meta (ML):** triple-barrier label — did price hit +1.0·ATR profit target
    before −0.5·ATR stop within 12 bars? Binary. Features = spine at decision bar
    + side.
- **The self-audit catch:** first pass FAILED — but because *my* labeling was
  wrong (same-tf "both barriers in one bar = stop" deflated base follow-through
  to 0.28 and corrupted labels). Corrected to **1-minute barrier labeling** (true
  intra-bar order). Base rose to 0.33; with clean labels the model at take≥0.55
  lifts precision to **0.40–0.57** and expectancy to **+0.1 to +0.36 R** in
  **24/24** ticker-folds (8/8 × 3 tickers). **Gross edge is real and
  out-of-sample.** This is the only signal in the whole program that beats its
  baseline AND sidesteps the VRP wall (trades the underlying).
- **Net-of-cost gate (the honest finish):** per-trade friction = spread (bps) +
  breakout-chase slippage (ATR fraction), swept.
  | | 5m | 15m | 30m |
  |---|---|---|---|
  | SPY | NET_FAIL | **NET_PASS 5/8** | NET_FAIL |
  | IWM | NET_FAIL | NET_FAIL | NET_FAIL |
  | QQQ | NET_FAIL | mixed | NET_FAIL |
  - At 5m the 0.5-ATR stop risks only ~$0.18 on SPY, so a 1bp spread ($0.035)
    alone eats ~0.19 R — bigger than the gross edge. Higher TF enlarges the
    dollar risk (cost shrinks as a fraction of R) but the gross edge thins too;
    they race, and **15m SPY is the sweet spot**.
  - **Verdict: a real but MARGINAL edge — net-positive on SPY-15m under
    conservative costs, breakeven elsewhere.** Not a robust multi-ticker
    money-printer. Pursue only with execution-quality focus (stop-limit entry,
    SPY-first, 15m).

Detail: `docs/MODEL_RETHINK_PLANS.md` §RESULTS, `docs/MODEL_CATALOG.md`.

---

## 7. Cross-cutting lessons

1. **Structure & size are predictable; direction is not** — from TA/gamma/news/
   cross-asset/vol-regime. Direction needs order-flow/microstructure data we
   don't have.
2. **The variance-risk-premium wall:** any bet on a move the option market has
   priced loses on average (implied ≥ realized). Magnitude size, directional
   call/put — all hit this. Only underlying-vehicle strategies escape it.
3. **A first-pass null is a hypothesis about the *test*, not just the signal.**
   The flagship "failure" (breakout-meta) was my labeling artifact; corrected, it
   passed 24/24 gross. Always self-audit a null for structural flaws before
   believing it.
4. **Costs are a first-class gate.** A +0.2 R gross edge on a 0.5-ATR/5m stop is
   ~4 cents — below the spread. Net-of-cost analysis is mandatory, and timeframe
   selection is really cost-fraction selection.
5. **Replayability + locked hyperparameters + walk-forward + bootstrap/mechanism
   gates** are what let us tell a real signal from a lucky fold.

---

## 8. Where everything lives

- **This index:** `docs/MODELS_END_TO_END.md` (you are here).
- Strat engine: `docs/STRAT_ENGINE_AND_COMBO_PIPELINE.md`,
  `docs/STRAT_ENGINE_ARCHITECTURE.md`, `docs/STRAT_ENGINE_ERD.md`,
  `docs/STRAT_ENGINE_OPERATIONS.md`, `docs/STRAT_METHODOLOGY.md`.
- Magnitude engine: `docs/MAGNITUDE_ENGINE_RESULTS.md`,
  `docs/MAGNITUDE_DIRECTIONAL_SESSION_HANDOFF.md`.
- Direction R&D: `docs/DIRECTION_FEATURES_R&D.md`.
- Rethink models + verdicts: `docs/MODEL_CATALOG.md`, `docs/MODEL_RETHINK_PLANS.md`.
- Code: `gcp/research/strat_engine/` (strat + the 3 rethink models),
  `gcp/research/magnitude_engine/` (magnitude), `scripts/implied_vs_realized_check.py`
  (gate 7), `scripts/magnitude_movement_sim.py` (movement sim).
- Result artifacts (per-fold JSON):
  `gs://adept-mountain-474619-d4-trading-data/research/{strat,magnitude}_engine/<ticker>_<tf>/`.
