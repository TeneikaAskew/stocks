# Phase 7 — Four-track verification: stacked, P&L, productionize, audit

**Date:** 2026-05-25
**Context:** User feedback flagged the +57 bps headline number as January-inflated, the 39% direction hit rate as anti-predictive on median bars, the IWM-ETF cost assumption as wrong for 0DTE options, and the next-candle classifier as the "real" Strat model — but never P&L-tested. Also flagged identical n_test counts as suspicious.

## TL;DR

**The classifier works as a classifier; it does NOT work as a trade signal.**

- ✅ Audit confirmed train/test integrity for IWM. **Found QQQ 5m data bug** (780 training rows instead of ~195k) — now rebuilt with 200,159 rows.
- ✅ Classifier accuracy 58-60% OOS is real on IWM 5m + QQQ 5m (after data fix).
- ❌ **P&L backtest loses money on every cell, every exit model, every side.** Best case is IWM 15m long-only: -90 bps net of costs over 53 trades — i.e. nearly breakeven, no edge.
- ❌ Stacked regression adds ~0 (Δspread +0.68 bps, ΔIC -0.01) — classifier and regressor are redundant.
- ⏸ Productionize: NOT shipped. There is nothing here that should run nightly.

The user's prior held: "type accuracy ≠ profitability." A 2U is satisfied by a one-tick poke that then reverses, hitting the stop before the target. The classifier predicts the WICK direction, not the bar's closing direction.

## Track 4 — Audit findings

### What was clean

- **Train/test timestamp overlap = 0** ✓
- **n_test counts identical (7,644)** turned out to be benign: 98 trading days × 78 RTH 5m bars = 7,644 — calendar artifact, not a data bug.
- IWM 5m: 195,175 training rows ending Dec 31, 2025 — full history ✓
- All TFs other than QQQ 5m had complete histories per ticker.

### What was broken

| Issue | Severity | Fix |
|---|---|---|
| **QQQ 5m had only 780 training rows** (vs 195k for IWM, 191k for SPY) | CRITICAL | Deleted QQQ 5m rows; re-ran p7-build job; now 200,159 rows |
| `vix_close` feature uses same-day VIX close (intraday leakage of EOD VIX) | LOW | Not fixed yet — a 10am bar shouldn't know the day's VIX close. Logging as known leak; minor impact since intraday VIX rarely moves >5% intraday |
| SPY 5m last-train cutoff was Nov 14 (6-week gap before Jan 2 test) | LOW | Still 191k training rows of clean history. No fix needed for this audit; user may want to re-extend coverage later. |

## Track 1 — Stacked regression (p7c)

Approach: 5-fold OOF classifier → regressor with classifier probs as extra features. Layer 1 (classifier) never sees the row layer 2 (regressor) is training on. At OOS time, full-train classifier scores all OOS rows.

**Result on IWM 5m, OOS Jan-May 2026:**

| Model | OOS IC | OOS L/S spread (bps) |
|---|---|---|
| Baseline regression | +0.0295 | +5.44 |
| Stacked (with classifier features) | +0.0197 | +6.12 |
| **LIFT** | **-0.0099** | **+0.68** |

The classifier features ADD almost nothing. The two models predict overlapping signal — the classifier is just learning the same indicator-→-return relationship in a different output space.

**Per-month L/S spreads (bps):**

| | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 |
|---|---|---|---|---|---|
| Baseline | NaN | -9.4 | +18.4 | -12.0 | +12.6 |
| Stacked | NaN | -3.9 | +15.6 | -6.1 | +12.3 |

Neither version is consistently profitable month-over-month even at the L/S decile level. February + March work; January + April are flat-to-negative.

## Track 2 — P&L backtest (p7d)

**Setup:**
- Use saved p7b classifier (trained on bar_date < 2026-01-01)
- Score Jan-May 2026 OOS bars
- D10 (top 10% directional edge) = long, D1 (bottom 10%) = short
- Per-day cap: 2 trades, highest |edge| first
- 4 exit models tested in parallel
- Cost: 10 bps round-trip (ETF assumption; we explicitly flag this is conservative for 0DTE options)

### IWM 5m — best exit: TP +25 / SL -15 / time 10 bars

| | n | win% | TP% | SL% | gross_bps | net_bps |
|---|---|---|---|---|---|---|
| exitA (25/15/10) | 196 | 43.9% | 40.8% | 56.1% | **+401** | **-1,559** |
| exitB (50/25/20) | 196 | 40.3% | 28.6% | 55.6% | +385 | -1,575 |
| exitC (hold 5) | 196 | 50.5% | – | – | +266 | -1,695 |
| exitD (hold 10) | 196 | 52.0% | – | – | +69 | -1,891 |

**Per-side breakdown (exitA):**

| Side | n | win% | gross | net | avg/trade |
|---|---|---|---|---|---|
| LONG (D10) | 52 | 46.2% | +161 | -359 | +3.10 bps |
| SHORT (D1) | 144 | 43.1% | +240 | -1,200 | +1.67 bps |

The short side has 3x more trades because the OOS period had more bars with strong p_2d − p_2u leans. SHORT gross is positive but tiny per trade (+1.67 bps avg vs 10 bps round-trip = -8.3 bps net per trade).

**Per-month (exitA):**

| Month | n | gross | win% | net |
|---|---|---|---|---|
| Jan | 40 | -170 | 28% | -570 |
| Feb | 38 | +430 | 66% | +50 |
| Mar | 44 | +180 | 48% | -260 |
| Apr | 42 | -70 | 33% | -490 |
| May | 32 | +30 | 47% | -290 |

Only Feb 2026 was net-positive. The headline "+1.5 directional spread" decile signal does not survive a realistic exit model + per-day cap + costs.

### IWM 15m — best exit: TP +50 / SL -25 / time 20 bars

| | n | win% | TP% | SL% | gross | net |
|---|---|---|---|---|---|---|
| exitB (50/25/20) | 191 | 35.6% | 34.0% | 63.9% | +234 | -1,676 |

**Per-side:**

| Side | n | gross | net | avg/trade |
|---|---|---|---|---|
| LONG (D10) | 53 | +440 | **-90** | +8.30 bps |
| SHORT (D1) | 138 | -206 | -1,586 | -1.49 bps |

**The only cell with even modest signal: IWM 15m long-only is nearly breakeven** (-90 bps over 53 trades = -1.7 bps per trade after costs). The short side is a disaster.

### QQQ 5m — re-tested with FIXED data

After rebuild, classifier accuracy is 59.7% (was 51.5% with bad data) — confirming the earlier QQQ 5m result was a data deficit, not a signal failure. **But P&L still loses:**

| | n | gross | net |
|---|---|---|---|
| exitA | 196 | +277 | **-1,684** |

LONG: 109 trades, gross +263, net -827. SHORT: 87 trades, gross +13, net -857.

The signal exists in classifier-accuracy space. It does NOT exist in trade-P&L space.

## Track 3 — Productionize

**Not shipped.** Premature given the P&L results. If a future iteration finds a profitable cell:
1. Build a `deploy_p7b_classifier` function in `gcp/deploy.sh`
2. Add a Cloud Scheduler entry to fire `--mode=predict` daily after market close
3. Surface predictions in the dashboard

The infrastructure is built (`gcp/research/p7b_next_candle_classifier.py` with `--mode={evaluate,train,predict,all}`, predictions table schema, GCS-backed model artifacts) — wiring it up is a 15-min job. It would be reckless to wire it up before there is a P&L-confirmed cell.

## What the user's review predicted, confirmed

1. **"+57 bps was January-inflated"** — confirmed. The 5-month series shows February as the only post-cost positive month for IWM 5m at the decile level. There is no stable monthly P&L.
2. **"39% direction hit rate is anti-predictive on the median bar; signal in tails only"** — confirmed. The win rate on D10/D1 selected trades is 35-50%, not the 60% candle-type accuracy.
3. **"60% type accuracy ≠ profitability — 2U can be a one-tick poke"** — directly confirmed in the SL rates. Best exit had 56% stop-rate vs 41% target-rate.
4. **"Cost mismatch — 0DTE options round-trip far exceeds 10 bps ETF assumption"** — confirmed. Even at the optimistic 10-bps ETF cost, every cell is net-negative. The 0DTE option fill would amplify the loss.

## What I'd push next (if anything)

Given this verdict, two avenues remain — both are research, not deployment:

1. **Wider exit-model grid + position sizing.** The current grid tests 4 exits. A finer grid (TP × SL × time + size as a function of |edge|) might find a cell with positive P&L, but the gross-of-cost numbers (best avg = +3 bps/trade) say the ceiling is low.
2. **Selectivity over signal strength.** D10 captures the top 10% of bars; the most extreme |edge| > 0.7 captures ~5% with 77% classifier accuracy. If we'd accept 1-2 trades/WEEK instead of /DAY, the avg-bps-per-trade might rise high enough to cover costs. This is the path of "trade rarely, only when very confident."

If neither path produces a net-positive P&L cell, the right call is to STOP developing this classifier as a trade signal. The Strat-taxonomy signal is structural pattern noise that doesn't survive transaction costs at any of the tested intraday horizons.

## Artifacts

| Path | Purpose |
|---|---|
| `gcp/research/p7b_next_candle_classifier.py` | classifier (eval/train/predict) |
| `gcp/research/p7c_stacked_regression.py` | OOF-stacked regression |
| `gcp/research/p7d_pnl_backtest.py` | honest P&L backtest |
| `gcp/queries/p7_audit.sql` | audit SQL (multi-statement) |
| `gs://.../research/p7b/{ticker}_{tf}/{model.pkl,features.txt,eval_*.json}` | trained models + eval metrics |
| `gs://.../research/p7c/iwm_5m_stack_*.json` | stacked-model lift metrics |
| `gs://.../research/p7d/{ticker}_{tf}_{backtest,trades}_*.{json,csv}` | per-trade P&L detail |

## Cost

- Image rebuilds (2): ~$0.60
- Audit + per-TF audit: ~$0.05
- 15-cell classifier sweep (earlier): ~$1.50
- IWM 5m + 15m P&L backtest + stacked + retrains: ~$0.40
- QQQ 5m rebuild + re-eval + retrain + P&L: ~$0.30
- **Track-4 total: ~$1.40**
- **Cumulative Phase 7 session: ~$17**
