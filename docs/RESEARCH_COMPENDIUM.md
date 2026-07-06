# Research Compendium — Unified (Every Model · Every Experiment · Every Result)

**Unified record — merged 2026-06-10. Two parallel editions grew on different branches; BOTH are preserved here in full, nothing dropped. Where they describe the same model/experiment with different wording, both wordings are kept.**

- **Part A — Research Compendium (data-science log)** (was `RESEARCH_COMPENDIUM.md`)
- **Part B — Models End-to-End Experiment Log (data log)** (was `MODELS_END_TO_END.md`)

---

# PART A — Research Compendium (data-science log)

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
target, and three genuinely-new information classes (daily dealer-options flow;
intraday order-flow; reconstructed intraday dealer GEX/DEX — the last with its DEX
reconstruction validated 100%-sign-faithful against the live options feed) — with
exactly one unresolved IWM-only flicker that does not replicate. **Magnitude** (TIGHT/NORMAL/EXPANDED/EXPLOSIVE) is statistically
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
   (E5b) — also null: it *reshuffles* the flicker. Reconstructed intraday dealer
   GEX/DEX (E5c) — also null, and notably its DEX reconstruction was *validated
   100%-sign-faithful* against the live options feed, so the null is real, not a
   data-quality artifact (§5.4).
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
| **C1b (E5b)** | Intraday order-flow imbalance (OFI) | direction | ❌ null — reshuffles flicker (§5.4) |
| **C1c (E5c)** | Reconstructed intraday dealer GEX/DEX (intragex) | direction | ❌ null — DEX recon validated faithful, still dilutes IWM (§5.4) |
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

#### 5.2b Gamma reassessment (2026-06-07) — vol value confirmed, + a regime-label bug

A step-back review (prompted by domain pushback that gamma should be valuable)
**confirmed gamma's volatility value robustly and corrected an under-report.**
Over 11 years (daily gamma regime from D-1 EOD `gamma_levels_eod`, by
**sign(total_gex)**, × within-day 30m moves), **negative gamma → larger moves on
all three tickers: IWM 1.34× / QQQ 1.66× / SPY 1.87×** (n=14k–25k/cell,
literature-consistent). This is the real, usable gamma edge — "where volatility
is" — and the program had buried it (it lived in A2 but was gated as "priced").
**Caveat:** it's the same VRP-priced quantity, so it's valuable for *sizing /
strategy selection / risk*, not for cheaply buying the straddle.

Two corrections fell out: **(bug — NOW FIXED 2026-06-07)** the `regime` label in
`gamma_levels_eod` (and `lib/gamma.py`, formerly spot-vs-flip) was **inverted vs the
vol regime** — `'negative_gamma'` rows had `total_gex>0` in 2,765/2,767 cases
because `compute_gamma_flip` returns None on ~half the days (the neg-gamma ones) and
otherwise a flip far from spot. Fixed: regime now ← **sign(total_gex)** (commit
7b9e873); `:latest` rebuilt, `premarket-brief` redeployed, `gamma_levels_eod`
rebuilt + verified (regime↔sign, 0 mismatches). `strat_features.gamma_regime`
rebuild still pending (heavy). **(direction)** the regime-conditional *direction*
hypothesis (neg-gamma→momentum) is **null over 11 years** (within-day 30m autocorr
≈0 in both regimes; the 9-day blip was small-sample noise). See registry **B6**.

**Volume-at-price (POC) — same shape as gamma (registry B7).** Prior-day Point of
Control: **not a magnet** (close nearer POC than open only ~30% of days), **no
direction** (open-vs-POC return ≈0), but **distance-from-POC → volatility is real**
(SPY: open far from POC → ~2× day range, monotonic near 1.03% / mid 1.35% / far
2.01%). So "where volume sits," like gamma, forecasts **vol/sizing, not sign.**

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

**E5b — intraday order-flow imbalance (C1b) ❌ falsified (resolved 2026-06-05).**
Tick-rule signed volume / within-day CVD / 3-bar persistence from the 1-min bars
*within* each 15m bar (contemporaneous, no shift) — the one lever with a real
microstructure prior (Cont/Kukanov/Stoikov OFI). Full 2015→2026 backfill (~530k
buckets), identical E4 config, +3 OFI columns; baselines reproduced exactly.
Long/short pooled precision at fire ≥0.60 (baseline → +intraflow):

| ticker | side | baseline lift / z | +intraflow lift / z |
|---|---|---|---|
| IWM | long | **+0.053 / +2.85** | +0.005 / **+0.30** |
| SPY | long | +0.001 / +0.05 | **+0.058 / +2.97** |
| QQQ | long | −0.022 / −1.35 | +0.023 / +1.52 |
| (shorts, all tickers) | short | |z| ≤ 1.34 | |z| ≤ 1.59 |

Same outcome family as E5: OFI **destroys** the IWM long edge (z 2.85→0.30, fires
726→1054 while precision falls — overfit-dilution) and **surfaces a new,
unvalidated SPY-long flicker** (z 2.97, +5.8pp) plus a marginal QQQ-long (z 1.52).
It **reshuffles** which single ticker is significant (IWM→SPY) rather than adding
or replicating signal — the multiple-comparisons signature, not a deployable edge.
Cost-free only, miscalibrated (ECE≈0.10), net-untradeable. *(Builder:
`gcp/build_intraday_flow.py` → `intraday_flow_15m`, now COPY-based + resumable;
loader `lib/features/intraday_flow.py`; 8 hermetic tests pass.)*

**E5c — reconstructed intraday dealer GEX/DEX (C1c) ❌ null (resolved 2026-06-06).**
The "reverse-engineer what dealer positioning was at 11:30am" idea, done rigorously:
walk the T-1 EOD chain forward to each 15m spot via the delta-gamma re-curve
`δ(S)=δ_eod+γ_eod·(S−S_eod)` (→ `total_gex=NetΓ·S²·mult`, `total_dex=(A+B·(S−S_eod))·S`),
materialized over 2016→2026. Features: `dex_per_oi`, `gex_per_oi`, `dist_to_flip_pct`.

*Validated against the live feed:* the platform captures **real** intraday options
(`market_session='REALTIME'`, every 5 min, since 2026-05-23). Comparing the
reconstruction to the real intraday greeks at matched spot (n=84 bars/ticker):
**DEX sign-agreement = 100%** on IWM/SPY/QQQ (corr_dex 0.55–0.82) — the re-curve is
a faithful proxy for DEX *direction*; GEX is unreliable (corr_gex IWM −0.79) so
`gex_per_oi`/`dist_to_flip_pct` are noisy. So the result below is a real
DEX-direction null, not a reconstruction artifact.

Probe (baseline → +intragex, z at fire ≥0.60): IWM long **+2.85→+0.60** (diluted,
fires 726→874), SPY long +0.05→−0.06, QQQ short +0.19→+1.69; nothing reaches
significance. **Third dealer-positioning class to fail identically** — dilutes the
IWM flicker, no replicating edge. A bug (s_eod from NULL EOD `underlying_price` →
NaN dex/flip) was caught *by the validation step* and fixed (s_eod from
`market_data_daily.close`). *(Builder `gcp/build_intraday_gex.py` → `intraday_gex_15m`,
resumable+COPY; `lib/features/intraday_gex.py`; 8 hermetic tests.)*

**E5c addendum — a real-intraday-DEX "lead" that was raised AND killed (2026-06-06→07).**
Pushed to use the live data directly, an exploratory **pooled** IC of real intraday
DEX vs forward returns on the 9-day REALTIME window first looked like the program's
first cross-ticker-positive (pooled IC(DEX→1h): SPY +0.137 / IWM +0.111 / QQQ +0.229).
A per-day check — made cheap by materializing `realtime_gex_15m` — **demolished it**:

| ticker | within-day IC (mean) | days negative | pooled IC | corr(dex, spot) |
|---|---|---|---|---|
| IWM | **−0.63** | **8/9** | +0.259 | **+0.93** |
| SPY | **−0.58** | 8/9 | +0.434 | +0.69 |
| QQQ | **−0.63** | 8/9 | +0.454 | +0.66 |

Two killers: (1) **Simpson's paradox** — the positive *pooled* IC was driven by
*between-day* level shifts; *within* each day (the only tradeable frame) the IC is
strongly **negative and consistent** (8/9 days, all tickers). (2) **It's mechanical,
not informational** — `dex_per_oi` correlates **0.66–0.93 with spot level** because
option delta is monotonic in moneyness, so "DEX" is just a proxy for *where spot
sits in the day's range*; the within-day relationship is ordinary intraday
mean-reversion of price level, not dealer-positioning alpha. **Verdict: no
independent directional signal** — the apparent lead was a pooled-correlation
artifact. This makes the direction-null *stronger*: even the real, exact intraday
greeks add nothing once you control for the day. The episode is the program's
discipline working — and the `realtime_gex_15m` table + `realtime-gex-daily`
scheduler still earn their keep as validation ground-truth and as the substrate for
*properly controlled* (within-day, level-residualized) real-intraday tests later.

**Production-grade architecture note (Rule 0):** E5/E5b/E5c each scan their large
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
- Direction is not, across 6 framings + 3 new information classes (E5 daily flow,
  E5b intraday OFI, E5c reconstructed intraday GEX/DEX — all null). ❌
- Magnitude is predictable @5m but **priced** (realized/implied 0.83–0.92). ⚠️
- **Gamma → volatility is real & robust (11yr): neg-gamma → 1.34–1.87× larger moves,
  all tickers** (§5.2b). Usable for sizing/risk, not for arbing the straddle (priced).
- **Volume-at-price (POC) → volatility is real too** (§5.2b/B7): open far from prior
  POC → ~2× day range. Like gamma: vol/sizing yes, direction no.
- The TYPE edge is **non-tradeable** after friction; options don't rescue it. ❌
- Correlation lenses agree: structure/magnitude/vol yes, sign no.

**Open / unresolved:**
- ✅ **Regime-label bug FIXED end-to-end** (§5.2b; commit 7b9e873) — `lib.gamma` uses
  `sign(total_gex)`, `gamma_levels_eod` rebuilt+verified, brief redeployed, AND
  `strat_features.gamma_regime` surgically corrected across all 6 tables (in-row
  `= sign(total_gex)`, 0 mismatches; no re-derivation). A full column audit for
  OTHER bugs of this class is in progress.
- **Productionize the vol signal** — gamma regime + POC-distance as a position-sizing
  / strategy-gating input (the real, confirmed edge); de-confound POC-vol from
  gap/vol-clustering and confirm cross-ticker.
- **Two single-cell long flickers, both replicate-or-reject:** the **IWM E4 long**
  (z≤4.2, price-only, mag-gated) and the new **SPY-long +intraday-OFI** (z 2.97,
  +5.8pp). Each is 1-of-N, cost-free, miscalibrated — possible multiple-comparisons
  luck. Neither deployable; need more names / OOS windows to confirm or kill.
- **E5b OFI and E5c reconstructed GEX/DEX are resolved (null)** — the two strongest
  remaining microstructure/positioning levers; both reshuffled/diluted rather than
  added signal. E5c's DEX reconstruction was validated 100%-sign-faithful vs the
  live feed, so its null is not a data-quality artifact.
- **Real-intraday DEX lead — RAISED then KILLED (§5.4 E5c addendum):** a pooled IC
  first looked cross-ticker-positive, but a per-day check showed it was Simpson's
  paradox (within-day IC −0.58 to −0.63, 8/9 days negative) and that `dex_per_oi`
  is mechanically a spot-level proxy (corr 0.66–0.93 with spot). **No independent
  signal.** Now-resolved, not open. The `realtime_gex_15m` table + `realtime-gex-daily`
  scheduler are LIVE and retained — as validation ground-truth and for properly
  controlled (within-day, level-residualized) real-intraday tests as data accrues.
  Any future real-intraday direction test must residualize the spot-level proxy and
  evaluate within-day, never pooled.
- **C3 information bars**, **C4 path/LSTM**, **C7 HMM**, **C2 cross-asset relative**
  — staged, lower prior given the consistent null.

**The standing recommendation:** productionize **magnitude/volatility** as the
forecastable quantity (sizing, not sign), keep TYPE as a structural context
feature, and treat standalone direction as **not extractable from any data class
tested so far** — including the microstructure levers (E5b OFI, E5c reconstructed
intraday DEX) that carried the strongest priors and still failed, the latter even
with its reconstruction validated faithful against live data. The remaining hope is
*genuinely* new data accumulated **forward** (the live REALTIME options feed, going
since 2026-05-23 — usable for a real-intraday-greeks verdict once ≥6 months
accrue), not another re-representation of the OHLCV+EOD-options we already hold.

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
- **Reconstructed intraday GEX/DEX (E5c):** `lib/features/intraday_gex.py` +
  `gcp/build_intraday_gex.py` → `intraday_gex_15m`. Validated against the live
  `etf_options_snapshots` `market_session='REALTIME'` feed (real intraday greeks).
- **Correlation pipelines:** `lib/combo_mining.py`; jobs `regime-combo-weekly`,
  `indicator-correlation`; tables `regime_combo_results`, `indicator_correlation`.
- **Hermetic tests:** `tests/test_strat_dir_probes.py` (19), `test_flow_direction.py`
  (22), `test_intraday_flow.py` (8), `test_fracdiff.py` (11), `test_information_bars.py`.

*This compendium cross-links but does not supersede the per-topic deep docs listed
in §2; when a number here and there disagree, the deep doc (with full fold tables)
wins and this doc should be corrected.*


---

# PART B — Models End-to-End Experiment Log (data log)

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

---

## 2026-07-06 — Forward-window & directional re-probe (does NOT change any verdict)

Prompted by "what would make the magnitude model effective?" A scratch-harness
program (single chronological 70/30 split, IWM/SPY/QQQ 5m, tempered α=0.75 —
**weaker than the 8-fold purged/embargoed + EV + gate-7 standard**) tested target
reframing, feature additions, and direction. Full record:
`EXPERIMENT_REGISTRY.md` §2026-07-06 (E-25…E-31 + P0.1); model entry
`MODEL_REGISTRY.md` §C-mf (PROPOSED/OPEN); addenda in
`MAGNITUDE_ENGINE_RESULTS.md` and `DIRECTION_RESEARCH_RESULTS.md`.

**Headline (all preliminary, none gate-cleared):**
- Reframing the target to a **30-min forward range** (E-28) is far more statistically
  predictable (50–59% top-bucket precision / 8–10× lift, generalizes, audited real —
  not an atr-denominator or overlap artifact). But it is a magnitude/vol signal driven by
  vol-clustering + time-of-day — the same effects **gate-7 already found priced** — so
  tradeability is unproven; it must clear gate-7 on the forward-window target first.
- A consistent **up>down excursion asymmetry** (E-30/P0.1) generalizes across tickers, but
  is the priced **option skew** and hasn't cleared purged/embargoed CV + cost-aware EV; the
  direction verdict (no confirmed cross-ticker edge) stands.
- **Feature engineering on bar data is near ceiling** (ablation: signal distributed, no slim
  subset beats full; engineered vol-regime and external event/options-IV joins neutral/marginal).

Net: sharpens *where* residual (largely priced) predictability lives; overturns nothing.
Concrete next gate: implied-vs-realized (gate-7) on the forward-window target.

