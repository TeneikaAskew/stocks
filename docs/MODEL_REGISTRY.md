# Model Registry — Strat / Magnitude / Direction research program

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
