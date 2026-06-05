# Model Catalog — Strat / Magnitude Research

**As of 2026-06-04.** Every model and experiment, existing and proposed, with
target / features / training data / status. Naming convention:
`<DOMAIN>-<FAMILY>`; FAMILY ∈ {SIZE, TYPE, DIRECTION, FLOW, META}.

---

## A. Existing (built + run)

### A1 · `MAG-SIZE` — the size model
- **Family:** SIZE
- **Target:** next-bar move bucketed in ATR-20 units → TIGHT/NORMAL/EXPANDED/EXPLOSIVE (thresholds 0.5/1.0/1.5)
- **Algorithm:** LightGBM 4-class multiclass (300 trees, lr 0.05, depth 6, leaves 31, min_child 100, seed 42)
- **Features:** ~140 spine = `strat_features_<tf>` ⨝ `strat_features_levels_<tf>`: TA (EMA/SMA/RSI/StochRSI/MACD/ATR/BB/OBV/RVOL/VWAP) + Strat one-hots (strat_candle, prev1-3, combo) + gamma (GEX/VEX/flip/king-gate) + VIX
- **Training data:** `strat_features_<tf>`, `strat_features_levels_<tf>` (SPY/IWM/QQQ; 5m/15m/30m). `etf_options_snapshots` used in gate-7 eval only.
- **Label-mode variants (same model, different target math):**
  - `body` |next_close−next_open|/ATR → **FAILED gate-7** (2026-05-29; priced in)
  - `excursion` (next_high−next_low)/ATR → "passed" gate-7 — **suspected VRP/measurement artifact** (range-vs-straddle is apples-to-oranges; see RETHINK §1)
  - `call` (next_high−next_open)/ATR — new 2026-06-04 → directional gate-7 **FAIL/INSUFFICIENT**
  - `put` (next_open−next_low)/ATR — new 2026-06-04 → directional gate-7 **FAIL/INSUFFICIENT**
- **Status:** Research. Size is predictable; **nothing beats option IV.**

### A2 · `STRAT-TYPE` — the structure model
- **Family:** TYPE · **Target:** next bar's Strat candle 1/2U/2D/3 (`next_bar_type`)
- **Algorithm:** LightGBM 4-class (same hyperparams as A1)
- **Features / data:** ~140 spine; `strat_features_<tf>`
- **Variants:** `strat_walk_forward`, `_adaptive`, `strat_pred_per_class` (OvR)
- **Status:** **Validates — the working one.** Production "cockpit" structure signal.

### A3 · `STRAT-DIR` — the direction failure
- **Family:** DIRECTION · **Target:** next_close > next_open (binary body-sign)
- **Algorithm:** LightGBM binary · **Features/data:** spine (+ news/cross-asset/vol-regime in `_extended`)
- **Status:** **FAILED 24/24 folds** (base + extended). Root cause = wrong target (RETHINK §2), not a bad model.

### A4 · `STRAT-CORR` — feature-discovery experiments (not predictors)
`strat_corr_indicators` (MI ranking per next_bar_type), `strat_corr_combos` (combo-lift mining). Feed A2 feature selection.

---

## B. Proposed (endorsed 2026-06-04) — see MODEL_RETHINK_PLANS.md

| Name | Family | Predicts | New data? | Status (2026-06-05) |
|---|---|---|---|---|
| `STRAT-BREAKOUT-META` | META | will a Strat trigger-break follow through | no (uses 1-min bars) | **PASS 24/24 GROSS** — net-of-cost gate open |
| `DIR-REGIME` | DIRECTION | move-continuation \| gamma regime | no | true null (corrected) |
| `INTRADAY-MOM` | DIRECTION | last-30-min move from first-30-min | no | true null (anomaly decayed) |
| `FLOW-OFI` (deferred) | FLOW | short-horizon direction | **yes — order flow** | not built |
| `HONEST-GATE7` (eval, deferred) | — | re-tests excursion vs time-of-day IV | no | not built |

Full results + the self-audit story: `MODEL_RETHINK_PLANS.md` §RESULTS.
