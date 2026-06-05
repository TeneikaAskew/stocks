# Research Compendium — Every Model, Every Experiment, Every Result

**Status:** living master index for the trading-research program.
**Last updated:** 2026-06-05.
**Scope:** the directional/structure/magnitude research stack on the liquid index
ETFs (IWM, SPY, QQQ; SPX daily-only) plus the production analysis/signal models.

This is the **single end-to-end** document the program lacked. It consolidates,
for *every model type*: (a) the experiments tried, (b) what worked and the exact
results, (c) the features used, (d) how each was structured, (e) why the
approach/features were picked, (f) the correlation analyses, and (g) the overall
rationale. Deep per-topic docs remain the authority for full fold tables; this
doc cross-links them rather than duplicating every row.

---

## 0. TL;DR — the one-paragraph verdict

Across an exhaustive program we have established a sharp, reproducible split:
**bar STRUCTURE is predictable, bar DIRECTION is not, and bar MAGNITUDE is
predictable but already priced.** The Strat **TYPE** model (which of 1/2U/2D/3
prints next) passes every hard gate on 8/8 walk-forward folds across IWM/SPY/QQQ
at 5m/15m. **Direction** (call-vs-put) fails in every framing tried — longer
horizons, trigger-conditioning, regime models, the literature's triple-barrier
target, and two genuinely-new information classes (daily dealer-options flow;
intraday order-flow) — with exactly one unresolved IWM-only flicker that does not
replicate. **Magnitude** (TIGHT/NORMAL/EXPANDED/EXPLOSIVE) is statistically
learnable at 5m but the **realized/implied ratio is 0.83–0.92**, i.e. the option
market has already priced the calendar × vol-clustering structure, so it is not
tradeably extractable. Execution backtests confirm the consequence: the TYPE
model's ~40% hit rate at 1.5R is break-even gross and **−$0.05/share net after
friction** on 88k trades; 0DTE options can't rescue it (theta erases the
asymmetry). **The predictable, calibrated, cross-ticker quantity is
magnitude/volatility; standalone direction is a coin flip everywhere except a
narrow, unvalidated IWM pocket.**

---

## 1. The overall narrative — why this stack exists (element *g*)

The program is a funnel, each stage motivated by the previous stage's result:

1. **Start from "The Strat" methodology** (a discretionary candle-classification
   system) and ask: is any of it *learnable* and *calibrated*? → Build the
   shared feature spine + walk-forward harness (§4).
2. **TYPE works** (§5.1): the model predicts next-bar structure with a large,
   calibrated, cross-ticker edge. Encouraging — but structure ≠ tradeable, because
   a 2U by 1 tick and a 2U by 50¢ carry the same label.
3. **So test DIRECTION directly** (§5.3): can we turn structure into a
   call-vs-put decision? Exhaustively — no. 0/72 production folds; 0/47+0/8+0/29
   across the probes. Confidence does not discriminate direction.
4. **Maybe the issue is the target, not the signal** → triple-barrier first-touch
   (E4), the literature's own meta-labeling target. Still 0/8 on calibration; one
   IWM-only long flicker (z up to 4.2) that **does not replicate** on SPY/QQQ.
5. **Maybe direction needs new INFORMATION, not new targets** → the "rethink":
   bring orthogonal data the price series can't contain. Daily dealer-options
   flow (E5) — null, and it *dilutes* the lone IWM edge. Intraday order-flow
   (E5b) — *in flight* (§5.4).
6. **Separately, is MAGNITUDE the thing that's actually predictable?** (§5.2):
   yes statistically (5m gates pass 100% bootstrap) — but the implied-vs-realized
   gate fails at 0.83–0.92, so the market has it priced. Not tradeable.
7. **Reality check via execution** (§6): even where structure is real, friction
   and theta turn it negative. This is the empirical floor under every "edge."

The honest synthesis: we are looking for **direction**, the one thing the data
keeps refusing to provide, while the two things that *are* learnable (structure,
magnitude) are either non-tradeable in isolation or already priced.

---

## 2. How to read this doc

| If you want… | Go to | Deep-dive authority |
|---|---|---|
| The model inventory at a glance | §3 | `docs/MODEL_REGISTRY.md` |
| Why structure works / TYPE engine | §5.1 | `STRAT_ENGINE_AND_COMBO_PIPELINE.md`, PRD |
| Why magnitude is priced-not-tradeable | §5.2 | `docs/MAGNITUDE_ENGINE_RESULTS.md` |
| Every direction experiment E1–E5b | §5.3–5.4 | `docs/DIRECTION_RESEARCH_RESULTS.md` |
| Feature families that failed | §5.3 | `docs/DIRECTION_FEATURES_R&D.md` |
| Execution / P&L reality | §6 | `EXEC_BACKTEST_RESULTS.md`, `OPTIONS_EXEC_BACKTEST_RESULTS.md` |
| Correlation / feature-importance | §7 | `STRAT_ENGINE_AND_COMBO_PIPELINE.md` |
| Literature priors | §8 | `docs/DIRECTION_LITERATURE_SCAN.md` |
| Production analysis/signal models | §9 | `INVESTMENT_MODELS_SUMMARY.md` |

---

## 3. Model inventory (element *a*, *g*)

Three families. **A** = validated/production-grade; **B** = direction probes
(verdict-bearing); **C** = proposed new-information-class engines.

| ID | Name | Target | Status |
|---|---|---|---|
| **A1** | Strat TYPE engine | next_bar_type ∈ {1,2U,2D,3} | ✅ PASS 8/8 (5m/15m all tickers); 30m PARTIAL |
| **A2** | Magnitude engine | bucket ∈ {TIGHT,NORMAL,EXPANDED,EXPLOSIVE} | ⚠️ learnable @5m, **not tradeable** (gate-7 fail) |
| **A3** | Strat DIRECTION (baseline) | binary next_close>next_open | ❌ FAIL 0/72 folds |
| **B1 (E1)** | fwd-return sign, h∈{1…20} | direction | ❌ 0/47 folds |
| **B2 (E2)** | direction on Strat-trigger bars | direction | ❌ 0/8 |
| **B3 (E3)** | direction within vix/gamma/session regime | direction | ❌ 0/29 |
| **B4 (E4)** | triple-barrier first-touch ±k·ATR, mag-gated | direction | ❌ 0/8 calib; IWM-only long flicker z≤4.2, no replication |
| **C1 (E5)** | Flow-Direction (daily EOD dealer greeks) | direction | ❌ null; dilutes IWM edge |
| **C1b (E5b)** | Intraday order-flow imbalance (OFI) | direction | 🚧 in flight (§5.4) |
| **C5** | Fractional differentiation | any | tested w/ E5 all-levers — null |
| **C6** | Rolling/recency-weighted window | any | tested w/ E5 all-levers — null |
| **C3** | Information-driven bars (volume/dollar) | any | ready, not run |
| **C4** | Path/sequence (signatures, LSTM/CNN) | direction/type | staged |
| **C7** | Latent-regime HMM layer | feeds A3/B4 | staged |
| **C2** | Cross-asset / relative direction | relative direction | PARTIAL (needs VIX-term feed) |

---

## 4. Shared methodology spine (element *d*) — "one source of truth"

Every model above imports the **same** label loader, feature matrix, estimator,
walk-forward cutoffs, and ECE metric, so verdicts can't drift on plumbing
differences (CLAUDE.md "one source of truth").

- **Feature surface:** `strat_features_{tf} LEFT JOIN strat_features_levels_{tf}`
  → **~143 float columns** after one-hot + dropping identity/OHLCV/forward cols.
  Families: OHLCV; Strat sequence (`strat_candle`, `strat_combo`, flags); ~30
  indicators (RSI, EMA, SMA, ATR, VWAP, RVOL, OBV, StochRSI, BB, MACD); **ORB**
  (5/15/30m, 36 level cols); **historical levels** (prev D/W/M/Q/Y HLOC +
  midpoints + breakout flags, 100 cols); **order blocks** (7 cols); regime
  context (`vix_close` prior-day, `total_gex`, `total_vex`, `dealer_regime`).
- **Timeframes built:** 1m, 5m, 15m, 30m, 60m, 4h (4h aggregated from 60m, ET
  09:30 origin). Row counts ≈ 1M (1m) → 6k (4h) per ticker.
- **Estimator:** `LGBMClassifier` (multiclass for TYPE/magnitude; binary for
  direction), locked `n_estimators=300, lr=0.05, max_depth=6, num_leaves=31,
  min_child_samples=100, seed=42`.
- **Calibration:** **NONE** (raw softmax) — LOCKED 2026-05-27. Platt/sigmoid was
  tested across 24 folds and **hurt ECE in every one** (raw 0.013–0.049 vs sigmoid
  0.042–0.125); LightGBM cross-entropy is already a calibration loss, Platt on top
  is double-calibration.
- **Walk-forward:** 8 anchored expanding folds spanning 2019→2026 (recovery /
  COVID / bull / bear / recovery / bull / current / locked-OOS). `bar_date <
  train_until` vs `≥`; embargo ≥ horizon on forward-looking targets.
- **Hard gates:** model log-loss < base-rate log-loss **AND** ECE ≤ 0.05.
  Advisory: accuracy beats base by ≥ 5pp.
- **Leakage discipline:** label computed before featurize and dropped; a
  fail-loud guard rejects any `fwd_`/`next_`/`_fwd` column in the matrix (added
  after a +47pp "impossibly good" leak from a session-label column — see
  DIRECTION_RESEARCH_RESULTS).

---

## 5. The models, in detail

### 5.1 A1 — Strat TYPE engine ✅ (the thing that works)

- **Predicts:** next bar's Strat type — `1` inside (compression), `2U` broke prior
  high only, `2D` broke prior low only, `3` outside (expansion).
- **Why this target:** it is the one structural quantity with a real conditional
  distribution (transition matrices show strong `P(next|current)` structure), and
  it underpins the whole Strat methodology.
- **Result (IWM 15m, the canonical cell):** **8/8 folds** log-loss beat (median
  **+0.179**), accuracy beat **median +17.7pp**, **8/8 ECE ≤ 0.05** (median
  **0.021**). Holds through the 2022 bear (+0.206 / +21.1pp).
- **Cross-ticker (2026-06-04):** PASS on **IWM/SPY/QQQ × 5m & 15m** (all 8/8 on
  both hard gates, median acc beat +15.4 to +19.0pp). **30m is PARTIAL** (8/8
  log-loss but only 4–5/8 ECE — calibration degrades).
- **Status:** finalized & "on the shelf" (callable, not activated). It predicts
  *structure*, which §6 shows is not tradeable on its own.
- **Known limits:** class-imbalance for `1`/`3` (model rarely argmaxes them);
  live-ECE self-mute is a no-op (writer unimplemented); provenance is best-effort
  (no top-level metrics.json).

### 5.2 A2 — Magnitude engine ⚠️ (predictable, but priced)

- **Predicts:** `magnitude_bucket` of |next_close−next_open|/ATR20 — TIGHT (<0.5),
  NORMAL (0.5–1.0), EXPANDED (1.0–1.5), **EXPLOSIVE (≥1.5)**.
- **Why:** the literature (§8) says magnitude/volatility is the predictable
  quantity at high frequency; this engine tests exactly that.
- **Phases & features (element c):**
  - P0 = 143-col baseline. P1 = atr5/atr20 ratio, BB20 bandwidth, realized-vol-z15,
    range-expansion ratio, intraday-range vs prior-day. P2 = AV ADX/MFI/Chaikin/
    Aroon/ROC/BBANDS. **P3 = event proximity** (hrs-until/since high-impact event,
    is_event_day_pm4h). P_calendar = day_of_week/hour/minute/week_of_month/
    is_first_friday/is_fomc_week/is_month_end/is_quarter_end. P4 = cross-asset
    (cancelled). P5 = gamma (deferred).
- **Result:** statistically **PASS at 5m** — P3/P_calendar clear gates 1–4 with
  **100% bootstrap across all 3 tickers**; mechanism check shows the "event" lift
  is really a **calendar × vol-clustering** effect.
- **The kill shot — gate 7 (implied-vs-realized):** for each EXPLOSIVE-predicted
  bar, realized move vs EOD-ATM-IV implied move. Threshold ratio ≥ 1.25. **Result:
  0 of 23 IV-covered folds pass; aggregate ratio 0.83–0.92** (IWM 0.92, SPY 0.87,
  QQQ 0.83); best single fold 1.23. → The option market has **already priced** the
  structure. **Closed 2026-05-29; no investment recommended.** P4/P5 cancelled
  (same gate-7 wall).

### 5.3 A3 / B — Direction ❌ (the exhaustive null)

Baseline **A3** (binary next_close>next_open on the shared surface): **0/72 folds**.
Then the probes, each a different reframing:

| Exp | Hypothesis | Structure | Result |
|---|---|---|---|
| **E1** | longer horizon recovers sign | fwd-return sign, h∈{1,3,5,10,15,20}, embargo≥h | **0/47 folds**; ECE worsens monotonically with h (0.062→0.159) |
| **E2** | meta-label on Strat triggers | direction only on continuation∨reversal bars | **0/8**; median acc −2.7pp — no primary edge to filter |
| **E3** | regime-specific models | per vix_low/high, pos/neg_gamma, late_session | **0/29**; even Gao's late-session effect doesn't replicate |
| **E4** | triple-barrier as primary target | which of ±k·ATR20 touched first in H=12; symmetric 3-class + long/short meta-models; magnitude-EXPLOSIVE gated; k∈{1.0,1.5} | **0/8 calibration** all arms; **one IWM-only long flicker** |

**The E4 IWM flicker (the single unresolved candidate), cost-free view:**
- IWM long, mag-gated, k1.0 ≥0.60 conf: **+5.3pp vs 0.494 base, z=2.85**.
- IWM long, k1.5 ≥0.65 conf: **+13.4pp vs 0.412 base, z=4.21** (sharpens with
  confidence, **7/8 folds positive incl. 2022 bear**).
- **Does NOT replicate:** SPY +0.1pp (z=0.05), QQQ −2.2pp (z=−1.35). Miscalibrated
  (ECE ≈ 0.10 — trust ranking not probabilities).
- **Tradeability:** gross ≈ 1.0–1.1 bps/trade vs ~1.5 bps IWM friction → **net ≈
  −0.5 bps.** Either small-cap timeability (literature-plausible) or one-of-three
  multiple-comparisons luck. Unresolved, not confirmed.

**Direction feature families tried (element c, all FAIL on IWM 5m/15m/30m, 0/8 each):**
- **news_sentiment** (9 cols: 24h sentiment/pos-share/neg-share, news-count z,
  topic flags) — sparse pre-2025 (30–630 articles/yr).
- **cross_asset** (9 cols: VIX 1d/5d delta + z, term structure, VVIX z, IWM−SPY,
  QQQ−SPY, correlation) — already dominated by baseline vix/dealer cols.
- **vol_regime** (7 cols: ATR%, ATR ratios, 5d/20d realized vol, gap%) —
  near-duplicate of baseline vix_close/tercile/atr_14.
- **options_derived** (PCR/skew/GEX) — **INFEASIBLE** in the old per-query
  architecture (14.1M-row table, pg8000 timeouts). *This motivated the
  materialized-table architecture used by E5/E5b — see §5.4.*

### 5.4 C1 / C1b — the "rethink": new information classes

The premise: direction may need *orthogonal information*, not new targets/models.

**E5 — daily EOD dealer-options flow (C1) ❌ falsified.** Net dealer DEX, 0-2DTE
DEX, vanna, charm from the AlphaVantage EOD chain, **d-1 leak-safe**, joined by
date. Identical E4 config, +6 flow columns (100% coverage). Long/short pooled
precision at fire ≥0.60:

| ticker | side | baseline lift / z | +flow lift / z |
|---|---|---|---|
| IWM | long | **+0.053 / +2.85** | −0.008 / **−0.49** |
| IWM | short | +0.001 / +0.14 | −0.001 / −0.07 |
| SPY | long | +0.001 / +0.05 | +0.001 / +0.07 |
| SPY | short | +0.015 / +1.34 | +0.010 / +1.02 |
| QQQ | long | −0.022 / −1.35 | +0.011 / +0.76 |
| QQQ | short | +0.002 / +0.19 | +0.015 / +1.38 |

No SPY/QQQ side reaches significance; flow **destroys** the lone IWM edge
(2.85→−0.49), fire count rises 726→881 while precision falls — spurious in-sample
overfitting. **Scope caveat:** this tests *slow daily* positioning, not *live
intraday* flow.

**E5b — intraday order-flow imbalance (C1b) 🚧 in flight.** Tick-rule signed
volume / within-day CVD / 3-bar persistence computed from the 1-min bars *within*
each 15m bar (contemporaneous, no shift). This is the one remaining lever with a
real microstructure prior (Cont/Kukanov/Stoikov OFI). **Results pending** — to be
filled when the backfill + 3 experiments complete. *(Builder:
`gcp/build_intraday_flow.py` → `intraday_flow_15m`; loader
`lib/features/intraday_flow.py`; 8 hermetic tests pass.)*

**Production-grade architecture note (Rule 0):** E5/E5b both scan their large
source table (`etf_options_snapshots` ~14M rows; `market_data_intraday` ~2M/ticker)
**once** in a dedicated builder job into a small materialized table; experiments
read the materialized table. This replaced a first cut that re-aggregated per
experiment and starved the shared Cloud SQL under concurrent runs (the 2026-06-05
incident).

---

## 6. Execution reality — the cost wall (element *b*)

Structure being *real* is necessary, not sufficient. Two execution backtests on
the TYPE model's setups (argmax 2U/2D, top_prob ≥ 0.55; entry stop-order at
trigger extreme; stop = opposite extreme; target = 1.5R; time stop 30–60 min;
per-1m precedence target>stop>time, ties → stop):

**Shares (EXEC_BACKTEST_RESULTS):** 88,138 trades (5m 62k / 15m 18.5k / 30m 7.5k),
hit rate **40.5 / 43.1 / 43.3%** (1.5R break-even is ~40%), **gross ≈ −$0.008 to
−$0.015/sh**, **net −$0.052 to −$0.061/sh** after $0.05 round-trip friction.
**0/8 folds positive, every cell.** Diagnostic: the **structure-vs-magnitude
gap** — the model knows a 2U will print, not how far it travels; friction kills a
zero-gross edge.

**0DTE options (OPTIONS_EXEC_BACKTEST):** long ATM call/put on the same setups,
22,115 trades (5-fold). Hit rate ~37–38%. Net **+$0.08 / +$0.01 / +$1.90** per
contract by cell, but **fails c2 (≥$5/contract) and c3 (asymmetry ≥1.20; actual
1.001–1.141) on every cell × window.** Theta is **46–68%** of friction; the only
positive folds (2022 & 2026 30m) are high-trend/high-IV regimes, not setup edge.
**Options cannot fix a hit-rate problem.**

---

## 7. Correlation analyses (element *f*)

Three pipelines, all using `lib.combo_mining` with strict train-only binarization
(median splits, feature ranking, fits on TRAIN; hit-rate/lift on held-out TEST):

- **Regime-combo** (`regime_combo_results`, 576 rows): which AND-combos predict
  forward **regime** (BIG/UP/DOWN/FLAT, thresholds = train-only |return|
  quantiles). **Max OOS lift by class: FLAT 2.04×, BIG 1.48×, DOWN 1.39×, UP
  1.32×.** The strongest, most repeatable structure is **FLAT/chop** (e.g. SPY 60m
  `Realized_Vol_Short≤med AND Mins_Since_Open≤med AND Price_vs_VWAP>med` → 47.1%
  vs 23.2% base, 2.04×) — i.e. we predict *quiet*, consistent with §5.2.
- **Strat-combo:** which combos predict the next Strat type (e.g. `RSI_Divergence
  >med AND Price_vs_EMA9_ATR>med` → 2U lift 1.52×).
- **Indicator-correlation** (`indicator_correlation`, target-modular): single
  indicators vs forward_return / regime / strat / signal, ranked by |rank-IC|.
  Strongest single-feature signals are **structural/magnitude**, not directional —
  e.g. `Close_vs_Range` → next-bar 2U rank-IC **+0.465** (2D −0.466); `Daily_Range`
  → BIG-regime rank-IC +0.286. **No single indicator shows meaningful directional
  (forward-return-sign) rank-IC** — the quantitative echo of §5.3.

**Consolidated takeaway:** every correlation lens points the same way — features
carry **structure and magnitude** information and **negligible directional-sign**
information.

---

## 8. Literature → experiment rationale (element *e*)

Each experiment was chosen against a specific prior:

| Prior (source) | Conclusion | Drove |
|---|---|---|
| arXiv 2512.15720; Christoffersen-Diebold (NBER w10009) | magnitude predictable, **sign not** at minute scale (SPY 5m: abs-return ↑2.89×, t=12.41, yet 45% direction accuracy) | the whole TYPE-vs-DIRECTION-vs-MAGNITUDE split; A2 |
| Gao-Han-Li-Zhou (JFE 2018); Baltussen et al. (JFE 2021) | intraday momentum is **conditional** (late-session, high-vol, macro days) | E3 regime/late-session models |
| López de Prado; Hudson & Thames | triple-barrier + meta-labeling lifts precision **only if a primary edge exists** | E4 target; E2 meta-label test |
| Meta-labeling reproductions (QuantConnect) | cannot manufacture alpha on an edgeless primary | interpretation of E2/E4 nulls |
| Dim-Eraker-Vilkov (SSRN 4692190); gamma-feedback (arXiv 2511.22766) | dealer gamma predicts **volatility, symmetric in direction** | why GEX is in the *magnitude* surface, not direction; framed E5 as DEX/vanna/charm (directional dealer lean), not GEX |
| Cont-Kukanov-Stoikov (OFI) | order-flow imbalance carries short-horizon directional info | **E5b** (intraday OFI) |
| "The Strat" FTFC | discretionary, **no peer-reviewed backtest** | FTFC treated as a *feature/filter*, never assumed validated |

---

## 9. Production analysis & signal models (element *a*–*d*)

Separate from the research engines, five operational models (INVESTMENT_MODELS_
SUMMARY) run the live analysis/signal surface. These are **contrarian
mean-reversion** systems, distinct from the ML research above:

1. **IWM Deep Analysis** — 195 indicator cols on 1-min IWM (2015→2025, 1.8M bars).
2. **Multi-Ticker Pipeline** — daily collection + 28 indicators, IWM/SPY/QQQ/SPX.
3. **Enhanced Signal Generator** — 3-of-5 condition scoring (consecutive moves /
   RSI band / vs-VWAP / vs-EMA / StochRSI) → CALL/PUT, position-sized 25/50/75–100%;
   +Strat/+FTFC/+ORB bonuses → 8-pt score. ORB+FTFC reject **~90%** of raw signals.
4. **Trade Analysis** — enriches completed trades, mines winning patterns.
5. **Earnings Options Analytics** — IV mispricing / unusual activity around earnings.

**10-yr backtest (2015–2025):** base strategies are ~break-even (IWM PF 1.02,
Sharpe 0.30); the **Strat (FTFC/ORB) overlay** improves Sharpe (IWM 0.30→0.51,
SPY −0.19→0.18, QQQ −0.40→−0.06) by *removing* low-quality trades, not adding
edge. The **multi-timeframe combo** (1m signal + higher-TF EMA20 filter +
FTFC/ORB) reports much higher Sharpe (IWM 1m+15m: Sharpe 9.31, WR 57.1%,
+0.078%/trade) — **note these are pre-friction and not walk-forward-validated to
the §4 standard**; treat as exploratory vs the rigorously-gated research verdicts.
RSI bands are per-ticker Tier-A calibrated (IWM 36.2/50.2/63.7, etc.).

> ⚠️ **Rigor caveat.** The §9 production backtests use a lighter methodology than
> the §4–§6 walk-forward gates. Where they appear to show a large edge (e.g.
> Sharpe 9.31), the rigorously-gated execution backtests (§6) on the *same*
> structural signals are net-negative after friction. Trust §6 for tradeability.

---

## 10. What we know, and the open avenues

**Established (high confidence):**
- Structure (TYPE) is predictable & calibrated, cross-ticker. ✅
- Direction is not, across 6 framings + 2 new information classes (E5b pending). ❌
- Magnitude is predictable @5m but **priced** (realized/implied 0.83–0.92). ⚠️
- The TYPE edge is **non-tradeable** after friction; options don't rescue it. ❌
- Correlation lenses agree: structure/magnitude yes, sign no.

**Open / unresolved:**
- **IWM E4 long flicker** (z≤4.2, mag-gated) — replicate-or-reject (needs more
  small-cap names or an out-of-sample IWM window; currently 1-of-3 = possible luck).
- **E5b intraday OFI** — *in flight*; the last lever with a literature prior.
- **C3 information bars**, **C4 path/LSTM**, **C7 HMM**, **C2 cross-asset relative**
  — staged, lower prior given the consistent null.

**The standing recommendation:** productionize **magnitude/volatility** as the
forecastable quantity (sizing, not sign), keep TYPE as a structural context
feature, and stop treating standalone direction as extractable until a genuinely
new, *fast* information class (intraday flow / microstructure) demonstrates
cross-ticker significance.

---

## 11. Reproduce & provenance

- **TYPE / direction probes:** `gcp/research/strat_engine/strat_dir_probes.py`,
  `strat_walk_forward.py`; CR Job `direction-probe`. Artifacts:
  `gs://…/research/strat_engine/<ticker>_<tf>/dir_probe_*.json`.
- **Magnitude:** `gcp/research/magnitude_engine/`; see MAGNITUDE_ENGINE_RESULTS.
- **Exec backtests:** `lib/exec_backtest/`, `lib/options_exec_backtest/`.
- **Flow (E5):** `lib/features/flow_direction.py` + `gcp/build_options_daily_greeks.py`
  → `etf_options_daily_greeks`.
- **Intraday OFI (E5b):** `lib/features/intraday_flow.py` +
  `gcp/build_intraday_flow.py` → `intraday_flow_15m`.
- **Correlation pipelines:** `lib/combo_mining.py`; jobs `regime-combo-weekly`,
  `indicator-correlation`; tables `regime_combo_results`, `indicator_correlation`.
- **Hermetic tests:** `tests/test_strat_dir_probes.py` (19), `test_flow_direction.py`
  (22), `test_intraday_flow.py` (8), `test_fracdiff.py` (11), `test_information_bars.py`.

*This compendium cross-links but does not supersede the per-topic deep docs listed
in §2; when a number here and there disagree, the deep doc (with full fold tables)
wins and this doc should be corrected.*
